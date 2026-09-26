import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  CheckCircle2,
  Circle,
  AlertTriangle,
  XCircle,
  Clock,
  Sliders,
  ChevronDown,
  ChevronUp,
  Terminal,
  RotateCcw,
  Sparkles,
  Copy,
  Check,
  Upload,
  Plus,
  Tag,
  Trash2,
  Percent,
  Film,
  Loader2,
} from 'lucide-react';
import { api } from '../lib/api';
import { JobDetail, AnalysisResponse, WindowItem, SuggestionItem, LabelItem, LabelsResponse, SweepResultItem } from '../types';
import { VideoPlayer } from '../components/studio/VideoPlayer';
import { Timeline } from '../components/studio/Timeline';
import { MomentList } from '../components/studio/MomentList';
import { TuningDrawer } from '../components/studio/TuningDrawer';
import { RenderBar } from '../components/studio/RenderBar';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { ProgressBar } from '../components/ui/ProgressBar';
import { formatTimeHMS, cn } from '../lib/utils';

const ERROR_GUIDES: Record<string, { title: string; message: string; fix: string; command?: string }> = {
  SOURCE_BLOCKED: {
    title: 'YouTube Blocked Download',
    message: 'YouTube bot-check triggered. Google is requiring bot verification or sign-in.',
    fix: 'Configure browser cookies in Settings, or upload the video file directly.',
  },
  JS_RUNTIME_MISSING: {
    title: 'JavaScript Runtime Missing',
    message: 'yt-dlp requires a JavaScript runtime to solve YouTube signature deciphering challenges.',
    fix: 'Install Deno >= 2.3 to enable seamless video extraction.',
    command: 'curl -fsSL https://deno.land/install.sh | sh',
  },
  EJS_MISSING: {
    title: 'yt-dlp-ejs Missing',
    message: 'The yt-dlp JavaScript challenge solver plugin is missing.',
    fix: 'Install the default yt-dlp package with challenge solver dependencies.',
    command: 'uv add "yt-dlp[default]"',
  },
  UNSUPPORTED_URL: {
    title: 'Unsupported URL',
    message: 'The URL provided could not be processed as a video stream.',
    fix: 'Verify the video URL in a browser or upload the video file directly.',
  },
  PRIVATE_VIDEO: {
    title: 'Private or Restricted Video',
    message: 'This video is private or requires sign-in credentials.',
    fix: 'Configure cookies in Settings or upload the video file directly.',
  },
  GEO_BLOCKED: {
    title: 'Geo-Blocked Content',
    message: 'This video is restricted in your server region.',
    fix: 'Provide a direct video link or upload the video file directly.',
  },
  LIVE_STREAM_UNSUPPORTED: {
    title: 'Live Stream Unsupported',
    message: 'Ongoing live streams cannot be imported until broadcasting has finished.',
    fix: 'Wait for the stream to conclude so the VOD is available, or upload a recorded clip.',
  },
  TOO_LARGE: {
    title: 'File Too Large',
    message: 'The requested video exceeds server storage capacity.',
    fix: 'Choose a lower quality (e.g. 480p or 720p) or upload a shorter match segment.',
  },
  DOWNLOAD_FAILED: {
    title: 'Download Failed',
    message: 'The stream download failed due to network or connection errors.',
    fix: 'Check the link or network connection and retry, or upload the video file directly.',
  },
};

export const JobStudioPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const jobId = id!;

  // Local Studio State
  const [focusedIndex, setFocusedIndex] = useState<number>(0);
  const [isTuningOpen, setIsTuningOpen] = useState(false);
  const [isCancelModalOpen, setIsCancelModalOpen] = useState(false);
  const [showLogDrawer, setShowLogDrawer] = useState(false);
  const [logMessages, setLogMessages] = useState<string[]>([]);
  const [activeRenderId, setActiveRenderId] = useState<string>('default');

  // Modified windows state (edits by user)
  const [editedWindows, setEditedWindows] = useState<WindowItem[]>([]);
  const [hasUnrenderedChanges, setHasUnrenderedChanges] = useState(false);
  const [isCustomRendering, setIsCustomRendering] = useState(false);
  const [customRenderProgressText, setCustomRenderProgressText] = useState<string>('');
  const [liveStageMessage, setLiveStageMessage] = useState<string>('');
  const [showHowToFix, setShowHowToFix] = useState(false);
  const [copiedCmd, setCopiedCmd] = useState(false);

  // Player seek synchronization
  const [playerCurrentTime, setPlayerCurrentTime] = useState(0);
  const [isRetrying, setIsRetrying] = useState(false);

  // Manual Add Moment State
  const [isAddMomentModalOpen, setIsAddMomentModalOpen] = useState(false);
  const [manualMomentTimeInput, setManualMomentTimeInput] = useState<string>('');

  // Overlap Modal State
  const [overlapModalData, setOverlapModalData] = useState<{
    targetTime: number;
    newWindow: { start: number; end: number };
    overlappingIndices: number[];
  } | null>(null);

  // Labels & Sweep Modal State
  const [isLabelsModalOpen, setIsLabelsModalOpen] = useState(false);
  const [newLabelTime, setNewLabelTime] = useState<string>('');
  const [newLabelText, setNewLabelText] = useState<string>('');
  const [sweepModalData, setSweepModalData] = useState<{ results: SweepResultItem[] } | null>(null);
  const [isSweeping, setIsSweeping] = useState(false);

  const handleRetry = async () => {
    if (!jobId) return;
    setIsRetrying(true);
    try {
      await api.retryJob(jobId);
      await refetchJob();
    } catch (err: any) {
      console.error('Failed to retry job:', err);
    } finally {
      setIsRetrying(false);
    }
  };

  const [sseActive, setSseActive] = useState(false);

  // Poll Job Status with short polling/retry mechanism on initial fetch
  const {
    data: job,
    refetch: refetchJob,
    isLoading: isJobLoading,
    isError: isJobError,
  } = useQuery<JobDetail>({
    queryKey: ['job', jobId],
    queryFn: () => api.getJob(jobId),
    retry: (failureCount, error: any) => {
      // Retry up to 5 times (total ~6-8s) on initial fetch if the backend/worker
      // is still finalizing the job record or registering it in the database
      if (failureCount < 5) {
        return true;
      }
      return false;
    },
    retryDelay: (attemptIndex) => Math.min(600 * (attemptIndex + 1), 2000),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'completed' || status === 'failed' || status === 'cancelled' || status === 'interrupted'
        ? false
        : sseActive
        ? 8000
        : 2000;
    },
  });

  // Fetch Analysis
  const { data: analysis, refetch: refetchAnalysis } = useQuery<AnalysisResponse>({
    queryKey: ['analysis', jobId],
    queryFn: () => api.getJobAnalysis(jobId),
    enabled: !!job && (job.status === 'analysis_ready' || job.status === 'rendering' || job.status === 'completed'),
    retry: 2,
  });

  // Fetch Labels
  const { data: labelsData, refetch: refetchLabels } = useQuery<LabelsResponse>({
    queryKey: ['labels', jobId],
    queryFn: () => api.getJobLabels(jobId),
    enabled: !!jobId && !!job,
  });
  const labels = labelsData?.labels || [];
  const labelSummary = labelsData?.summary;

  // Sync analysis windows to local editable state
  useEffect(() => {
    if (analysis && analysis.windows) {
      setEditedWindows(analysis.windows);
    }
  }, [analysis]);

  // Set active render ID from job if available
  useEffect(() => {
    if (job?.active_render_id) {
      setActiveRenderId(job.active_render_id);
    }
  }, [job?.active_render_id]);

  // Listen to Server-Sent Events (SSE) with auto-reconnect backoff and fallback
  useEffect(() => {
    if (!jobId || !job) return;
    let eventSource: EventSource | null = null;
    let reconnectTimeout: any = null;
    let backoff = 1000;
    let isMounted = true;

    const connectSSE = () => {
      if (!isMounted) return;
      try {
        eventSource = new EventSource(`/api/jobs/${jobId}/events`);

        eventSource.onopen = () => {
          if (!isMounted) return;
          setSseActive(true);
          backoff = 1000;
        };

        eventSource.onerror = () => {
          if (!isMounted) return;
          setSseActive(false);
          if (eventSource) {
            eventSource.close();
            eventSource = null;
          }
          const delay = Math.min(15000, backoff);
          backoff = Math.min(15000, backoff * 1.5);
          reconnectTimeout = setTimeout(connectSSE, delay);
        };

        eventSource.addEventListener('log', (e: MessageEvent) => {
          try {
            const data = JSON.parse(e.data);
            if (data.message) {
              setLogMessages((prev) => [...prev.slice(-150), data.message]);
            }
          } catch {}
        });

        eventSource.addEventListener('stage', (e: MessageEvent) => {
          try {
            const data = JSON.parse(e.data);
            if (data.message) {
              setLiveStageMessage(data.message);
            }
            if (data.stage === 'rendering') {
              setCustomRenderProgressText(data.message || 'Rendering clips...');
            }
            refetchJob();
          } catch {}
        });

        eventSource.addEventListener('analysis_ready', () => {
          refetchJob();
          refetchAnalysis();
        });

        eventSource.addEventListener('render_done', (e: MessageEvent) => {
          try {
            const data = JSON.parse(e.data);
            if (data.render_id) {
              setActiveRenderId(data.render_id);
            }
            setIsCustomRendering(false);
            setHasUnrenderedChanges(false);
            refetchJob();
          } catch {}
        });

        eventSource.addEventListener('completed', () => {
          refetchJob();
          setIsCustomRendering(false);
          setHasUnrenderedChanges(false);
        });

        eventSource.addEventListener('error', () => {
          refetchJob();
          setIsCustomRendering(false);
        });
      } catch {
        setSseActive(false);
      }
    };

    connectSSE();

    return () => {
      isMounted = false;
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (eventSource) eventSource.close();
    };
  }, [jobId, !!job]);

  // Actions
  const handleToggleInclude = (index: number) => {
    setEditedWindows((prev) => {
      const next = [...prev];
      if (next[index]) {
        next[index] = { ...next[index], selected: !next[index].selected };
      }
      return next;
    });
    setHasUnrenderedChanges(true);
  };

  const handleUpdateWindow = (index: number, newStart: number, newEnd: number) => {
    setEditedWindows((prev) => {
      const next = [...prev];
      if (next[index]) {
        const dur = Math.max(0.1, newEnd - newStart);
        next[index] = {
          ...next[index],
          start: Math.round(newStart * 2) / 2,
          end: Math.round(newEnd * 2) / 2,
          duration: Math.round(dur * 2) / 2,
          start_hms: formatTimeHMS(newStart),
          end_hms: formatTimeHMS(newEnd),
        };
      }
      return next;
    });
    setHasUnrenderedChanges(true);
  };

  const handleUpdateTag = (index: number, tag?: 'Goal' | 'Chance' | 'Card' | 'Other', note?: string) => {
    setEditedWindows((prev) => {
      const next = [...prev];
      if (next[index]) {
        next[index] = { ...next[index], tag, note };
      }
      return next;
    });
  };

  const handleBulkSelect = (mode: 'all' | 'top5' | 'clear') => {
    setEditedWindows((prev) => {
      if (mode === 'all') {
        return prev.map((w) => ({ ...w, selected: true }));
      }
      if (mode === 'clear') {
        return prev.map((w) => ({ ...w, selected: false }));
      }
      // Top 5 by score
      const sortedByScore = [...prev]
        .map((w, idx) => ({ score: w.score, idx }))
        .sort((a, b) => b.score - a.score)
        .slice(0, 5)
        .map((x) => x.idx);
      return prev.map((w, idx) => ({ ...w, selected: sortedByScore.includes(idx) }));
    });
    setHasUnrenderedChanges(true);
  };

  const parseTimeInput = (val: string): number => {
    const s = val.trim();
    if (s.includes(':')) {
      const parts = s.split(':').map((p) => parseFloat(p));
      if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {
        return parts[0] * 60 + parts[1];
      }
      if (parts.length === 3 && !isNaN(parts[0]) && !isNaN(parts[1]) && !isNaN(parts[2])) {
        return parts[0] * 3600 + parts[1] * 60 + parts[2];
      }
    }
    const n = parseFloat(s);
    return isNaN(n) ? 0 : n;
  };

  const handleRequestAddMoment = (t: number) => {
    const preRoll = job?.config?.pre_roll ?? 12.0;
    const postRoll = job?.config?.post_roll ?? 6.0;
    const maxDur = analysis?.duration_s || 999999;
    const newStart = Math.max(0, Math.round((t - preRoll) * 2) / 2);
    const newEnd = Math.min(maxDur, Math.round((t + postRoll) * 2) / 2);

    // Check overlap with existing windows
    const overlappingIndices: number[] = [];
    editedWindows.forEach((w, idx) => {
      if (Math.max(newStart, w.start) < Math.min(newEnd, w.end)) {
        overlappingIndices.push(idx);
      }
    });

    if (overlappingIndices.length > 0) {
      setOverlapModalData({
        targetTime: t,
        newWindow: { start: newStart, end: newEnd },
        overlappingIndices,
      });
      return;
    }

    // Create new window
    const newWindow: WindowItem = {
      start: newStart,
      end: newEnd,
      duration: Math.round((newEnd - newStart) * 10) / 10,
      start_hms: formatTimeHMS(newStart),
      end_hms: formatTimeHMS(newEnd),
      score: 1.0,
      peak_time: t,
      peak_time_hms: formatTimeHMS(t),
      spike_count: 1,
      selected: true,
      source: 'manual',
      drop_reason: null,
      peak_rise_db: 0,
      is_cropped: false,
    };

    const nextWindows = [...editedWindows, newWindow].sort((a, b) => a.start - b.start);
    setEditedWindows(nextWindows);
    setHasUnrenderedChanges(true);
    api.saveWindows(jobId, nextWindows).catch(console.error);

    const newIdx = nextWindows.findIndex((w) => w.start === newStart);
    if (newIdx >= 0) setFocusedIndex(newIdx);
    setIsAddMomentModalOpen(false);
  };

  const handleConfirmMerge = () => {
    if (!overlapModalData) return;
    const { targetTime, newWindow, overlappingIndices } = overlapModalData;

    const allStarts = [newWindow.start, ...overlappingIndices.map((i) => editedWindows[i].start)];
    const allEnds = [newWindow.end, ...overlappingIndices.map((i) => editedWindows[i].end)];
    const mergedStart = Math.min(...allStarts);
    const mergedEnd = Math.max(...allEnds);

    const remaining = editedWindows.filter((_, idx) => !overlappingIndices.includes(idx));
    const mergedWindow: WindowItem = {
      start: mergedStart,
      end: mergedEnd,
      duration: Math.round((mergedEnd - mergedStart) * 10) / 10,
      start_hms: formatTimeHMS(mergedStart),
      end_hms: formatTimeHMS(mergedEnd),
      score: Math.max(1.0, ...overlappingIndices.map((i) => editedWindows[i].score)),
      peak_time: targetTime,
      peak_time_hms: formatTimeHMS(targetTime),
      spike_count: overlappingIndices.reduce((acc, i) => acc + (editedWindows[i].spike_count || 1), 1),
      selected: true,
      source: 'manual',
      drop_reason: null,
      peak_rise_db: Math.max(0, ...overlappingIndices.map((i) => editedWindows[i].peak_rise_db || 0)),
      is_cropped: false,
    };

    const nextWindows = [...remaining, mergedWindow].sort((a, b) => a.start - b.start);
    setEditedWindows(nextWindows);
    setHasUnrenderedChanges(true);
    api.saveWindows(jobId, nextWindows).catch(console.error);

    const newIdx = nextWindows.findIndex((w) => w.start === mergedStart);
    if (newIdx >= 0) setFocusedIndex(newIdx);
    setOverlapModalData(null);
    setIsAddMomentModalOpen(false);
  };

  const handleAddSuggestion = (sugg: SuggestionItem) => {
    const overlappingIndices: number[] = [];
    editedWindows.forEach((w, idx) => {
      if (Math.max(sugg.start, w.start) < Math.min(sugg.end, w.end)) {
        overlappingIndices.push(idx);
      }
    });

    if (overlappingIndices.length > 0) {
      setOverlapModalData({
        targetTime: sugg.peak_time,
        newWindow: { start: sugg.start, end: sugg.end },
        overlappingIndices,
      });
      return;
    }

    const newWindow: WindowItem = {
      start: sugg.start,
      end: sugg.end,
      duration: sugg.duration,
      start_hms: sugg.start_hms,
      end_hms: sugg.end_hms,
      score: sugg.score,
      peak_time: sugg.peak_time,
      peak_time_hms: sugg.peak_time_hms,
      spike_count: sugg.spike_count || 1,
      selected: true,
      source: 'suggestion',
      drop_reason: null,
      peak_rise_db: sugg.peak_rise_db,
      is_cropped: false,
    };

    const nextWindows = [...editedWindows, newWindow].sort((a, b) => a.start - b.start);
    setEditedWindows(nextWindows);
    setHasUnrenderedChanges(true);
    api.saveWindows(jobId, nextWindows).catch(console.error);

    const newIdx = nextWindows.findIndex((w) => w.start === sugg.start);
    if (newIdx >= 0) setFocusedIndex(newIdx);
  };

  const handleAddLabel = async () => {
    if (!newLabelText.trim()) return;
    const t = parseTimeInput(newLabelTime || String(playerCurrentTime));
    try {
      await api.addJobLabel(jobId, { time: t, label: newLabelText.trim() });
      setNewLabelText('');
      setNewLabelTime('');
      refetchLabels();
    } catch (err: any) {
      alert(`Failed to add label: ${err.message}`);
    }
  };

  const handleDeleteLabel = async (labelId: string) => {
    try {
      await api.deleteJobLabel(jobId, labelId);
      refetchLabels();
    } catch (err: any) {
      alert(`Failed to delete label: ${err.message}`);
    }
  };

  const handleRunSweep = async () => {
    setIsSweeping(true);
    try {
      const res = await api.findBetterSettings(jobId);
      setSweepModalData(res);
    } catch (err: any) {
      alert(`Sweep failed: ${err.message || 'No labels or audio file found'}`);
    } finally {
      setIsSweeping(false);
    }
  };

  const handleApplySweepResult = async (res: SweepResultItem) => {
    await handleRetune({
      min_rise_db: res.min_rise_db,
      min_sustain_s: res.min_sustain_s,
      pre_roll: res.pre_roll,
    });
    setSweepModalData(null);
    refetchLabels();
  };

  const handleRetune = async (overrides: Record<string, any>) => {
    try {
      const updated = await api.retuneJob(jobId, overrides);
      queryClient.setQueryData(['analysis', jobId], updated);
      setEditedWindows(updated.windows);
      setHasUnrenderedChanges(true);
      refetchLabels();
    } catch (err) {
      console.error('Retune failed:', err);
    }
  };

  const handleRenderReel = async () => {
    const selected = editedWindows.filter((w) => w.selected);
    if (selected.length === 0) return;

    setIsCustomRendering(true);
    setCustomRenderProgressText('Submitting render...');
    try {
      const res = await api.createRender(jobId, {
        windows: selected.map((w) => ({ start: w.start, end: w.end })),
      });
      setActiveRenderId(res.render_id);
    } catch (err: any) {
      setIsCustomRendering(false);
      alert(`Render failed: ${err.message}`);
    }
  };

  const handleCancelJob = async () => {
    try {
      await api.cancelJob(jobId);
      setIsCancelModalOpen(false);
      refetchJob();
    } catch (err) {
      console.error(err);
    }
  };

  // Steps definition for the Stepper
  const steps = [
    { key: 'importing', label: 'Import Video' },
    { key: 'extracting_audio', label: 'Extract Audio' },
    { key: 'detecting', label: 'Detect Excitement' },
    { key: 'rendering', label: 'Build Reel' },
  ];

  const getStepStatus = (stepKey: string) => {
    if (!job) return 'pending';
    const s = job.status;

    const order = ['importing', 'extracting_audio', 'detecting', 'rendering', 'completed'];
    const curStage = job.stage || (s === 'analysis_ready' ? 'rendering' : s);
    const curIdx = order.indexOf(curStage);
    const stepIdx = order.indexOf(stepKey);

    if (s === 'failed' || s === 'cancelled' || s === 'interrupted') {
      if (curIdx >= 0 && stepIdx === curIdx) return 'failed';
      if (curIdx >= 0 && stepIdx < curIdx) return 'done';
      return 'pending';
    }

    if (curIdx > stepIdx || s === 'completed') return 'done';
    if (curIdx === stepIdx) return 'active';
    return 'pending';
  };

  const isJobRunning = job && ['queued', 'importing', 'extracting_audio', 'detecting'].includes(job.status);
  const hasAnalysis = !!analysis;

  if (isJobLoading || (!job && !isJobError)) {
    return (
      <div className="min-h-[calc(100vh-70px)] flex flex-col bg-bg">
        <div className="bg-surface border-b border-border px-6 py-4">
          <div className="max-w-7xl mx-auto flex items-center justify-between">
            <h1 className="text-xl font-extrabold text-text tracking-tight">Highlight Studio</h1>
          </div>
        </div>
        <div className="flex-1 max-w-7xl w-full mx-auto p-12 flex flex-col items-center justify-center text-center space-y-4">
          <Loader2 className="w-8 h-8 text-primary animate-spin" />
          <p className="text-sm font-mono text-muted">Loading match studio...</p>
        </div>
      </div>
    );
  }

  if (isJobError || !job) {
    return (
      <div className="min-h-[calc(100vh-70px)] flex flex-col bg-bg">
        <div className="bg-surface border-b border-border px-6 py-4">
          <div className="max-w-7xl mx-auto flex items-center justify-between">
            <h1 className="text-xl font-extrabold text-text tracking-tight">Highlight Studio</h1>
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate('/library')}
              className="gap-1.5"
            >
              <Film className="w-3.5 h-3.5" />
              <span>Back to Library</span>
            </Button>
          </div>
        </div>
        <div className="flex-1 max-w-md w-full mx-auto p-8 flex flex-col items-center justify-center text-center space-y-4">
          <div className="w-14 h-14 rounded-2xl bg-surface border border-border flex items-center justify-center text-2xl shadow-sm">
            🔍
          </div>
          <div className="space-y-1">
            <h2 className="text-xl font-bold text-text">This job no longer exists</h2>
            <p className="text-xs text-muted">
              The requested job ID could not be found or has expired.
            </p>
          </div>
          <Button
            variant="primary"
            onClick={() => navigate('/library')}
            className="gap-2 text-xs"
          >
            <Film className="w-4 h-4" />
            <span>Go to Library</span>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-[calc(100vh-70px)] flex flex-col bg-bg">
      {/* Top Status Header */}
      <div className="bg-surface border-b border-border px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-extrabold text-text tracking-tight">{job?.title || 'Highlight Studio'}</h1>
            {job && (
              <span
                className={cn(
                  'px-2.5 py-0.5 rounded-full text-xs font-mono font-semibold uppercase border',
                  job.status === 'completed'
                    ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                    : job.status === 'failed' || job.status === 'cancelled' || job.status === 'interrupted'
                    ? 'bg-rose-500/15 text-rose-400 border-rose-500/30'
                    : 'bg-accent/15 text-accent border-accent/30 animate-pulse'
                )}
              >
                {job.status.replace('_', ' ')}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {hasAnalysis && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setManualMomentTimeInput(formatTimeHMS(playerCurrentTime));
                    setIsAddMomentModalOpen(true);
                  }}
                  className="gap-1.5 border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/15"
                  title="Manually add a highlight moment"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>+ Add Moment</span>
                </Button>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setIsLabelsModalOpen(true)}
                  className="gap-1.5 border-purple-500/40 text-purple-400 hover:bg-purple-500/15"
                  title="Event labels and recall evaluation"
                >
                  <Tag className="w-3.5 h-3.5" />
                  <span>
                    Labels {labelSummary && labelSummary.total > 0 ? `(${labelSummary.caught}/${labelSummary.total})` : ''}
                  </span>
                </Button>
              </>
            )}

            {isJobRunning && (
              <Button
                variant="danger"
                size="sm"
                onClick={() => setIsCancelModalOpen(true)}
              >
                Cancel Job
              </Button>
            )}

            {hasAnalysis && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setIsTuningOpen(true)}
                className="gap-1.5"
              >
                <Sliders className="w-3.5 h-3.5" />
                <span>Tuning Controls</span>
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Main Studio View Container */}
      <div className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 space-y-6">
        {/* Processing View Stepper & Live Drawer (shown when running or if errored) */}
        {(!hasAnalysis || job?.status === 'failed' || job?.status === 'cancelled' || job?.status === 'interrupted') && (
          <div className="bg-surface border border-border rounded-2xl p-6 shadow-md space-y-6">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {steps.map((st, i) => {
                const status = getStepStatus(st.key);
                return (
                  <div key={st.key} className="flex flex-col items-center text-center gap-2">
                    <div
                      className={cn(
                        'w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm border-2 transition-all',
                        status === 'done'
                          ? 'bg-primary/20 border-primary text-primary'
                          : status === 'active'
                          ? 'bg-accent/20 border-accent text-accent animate-pulse'
                          : status === 'failed'
                          ? 'bg-danger/20 border-danger text-danger'
                          : 'bg-card border-border text-muted'
                      )}
                    >
                      {status === 'done' ? (
                        <CheckCircle2 className="w-5 h-5" />
                      ) : status === 'failed' ? (
                        <XCircle className="w-5 h-5" />
                      ) : (
                        <span>{i + 1}</span>
                      )}
                    </div>
                    <span className="text-xs font-semibold text-text">{st.label}</span>
                  </div>
                );
              })}
            </div>

            {/* Live Progress Feedback (hide when failed/cancelled/interrupted) */}
            {job && isJobRunning && (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs font-mono">
                  <span className="text-text font-medium truncate max-w-xl">
                    {liveStageMessage || (job.stage ? `Step: ${job.stage.replace(/_/g, ' ')}` : 'Processing match...')}
                  </span>
                  {job.queue_position > 1 && (
                    <span className="text-amber-400 font-bold shrink-0">Queue position: #{job.queue_position}</span>
                  )}
                </div>
                <ProgressBar value={job.progress} />
              </div>
            )}

            {/* Failure stage callout */}
            {job && job.status === 'failed' && (
              <div className="text-xs font-mono font-medium text-danger">
                Failed at: {job.stage ? job.stage.replace(/_/g, ' ') : 'processing'}.
              </div>
            )}

            {/* Cancelled / Failed Banner */}
            {job && ['failed', 'cancelled', 'interrupted'].includes(job.status) && (() => {
              const code = job.error?.code || (job.status === 'cancelled' ? 'JOB_CANCELLED' : 'UNKNOWN');
              const guide = ERROR_GUIDES[code];
              const title = guide?.title || (
                job.status === 'cancelled'
                  ? 'Job was cancelled'
                  : job.status === 'interrupted'
                  ? 'Process was interrupted by a server restart'
                  : 'Processing failed'
              );
              const desc = job.error?.message || guide?.message || 'The pipeline halted execution.';
              const fix = guide?.fix;
              const cmd = guide?.command;

              return (
                <div className="p-4 rounded-xl bg-danger/10 border border-danger/30 space-y-3">
                  <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                    <div className="flex items-start gap-3">
                      <AlertTriangle className="w-5 h-5 text-danger shrink-0 mt-0.5" />
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="text-sm font-bold text-text">{title}</h4>
                          {job.error?.code && (
                            <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-danger/20 text-danger border border-danger/30">
                              {job.error.code}
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-muted mt-0.5">{desc}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0 flex-wrap">
                      <Button
                        variant="primary"
                        size="sm"
                        className="whitespace-nowrap shrink-0 gap-1.5"
                        onClick={() => navigate('/?tab=upload')}
                      >
                        <Upload className="w-3.5 h-3.5" />
                        <span>Upload video file</span>
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        className="whitespace-nowrap shrink-0"
                        onClick={handleRetry}
                        isLoading={isRetrying}
                      >
                        Retry
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="whitespace-nowrap shrink-0"
                        onClick={() => navigate('/')}
                      >
                        New highlight
                      </Button>
                    </div>
                  </div>

                  {/* Collapsible How to fix */}
                  {fix && (
                    <div className="border-t border-danger/20 pt-2">
                      <button
                        type="button"
                        onClick={() => setShowHowToFix(!showHowToFix)}
                        className="flex items-center gap-1.5 text-xs font-semibold text-danger/90 hover:text-danger"
                      >
                        <span>How to fix</span>
                        {showHowToFix ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                      </button>
                      {showHowToFix && (
                        <div className="mt-2 text-xs text-text/80 space-y-2 bg-card/60 p-3 rounded-lg border border-danger/20">
                          <p>{fix}</p>
                          {cmd && (
                            <div className="flex items-center justify-between bg-black/40 px-3 py-1.5 rounded font-mono text-[11px] text-text border border-border">
                              <code>{cmd}</code>
                              <button
                                type="button"
                                onClick={() => {
                                  navigator.clipboard.writeText(cmd);
                                  setCopiedCmd(true);
                                  setTimeout(() => setCopiedCmd(false), 2000);
                                }}
                                className="ml-2 p-1 hover:text-primary transition-colors text-muted"
                                title="Copy command"
                              >
                                {copiedCmd ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                              </button>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })()}

            {/* Log Drawer Toggle */}
            <div>
              <button
                onClick={() => setShowLogDrawer(!showLogDrawer)}
                className="flex items-center gap-1.5 text-xs text-muted hover:text-text font-mono font-medium"
              >
                <Terminal className="w-3.5 h-3.5" />
                <span>{showLogDrawer ? 'Hide Logs' : 'View Real-time Logs'}</span>
                {showLogDrawer ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              </button>

              {showLogDrawer && (
                <div className="mt-3 p-4 rounded-xl bg-black border border-border font-mono text-xs text-slate-300 max-h-60 overflow-y-auto space-y-1">
                  {logMessages.length === 0 ? (
                    <p className="text-muted">Waiting for log stream...</p>
                  ) : (
                    logMessages.map((m, idx) => <div key={idx}>{m}</div>)
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Studio Layout (Revealed once analysis exists, even while reel is still encoding!) */}
        {hasAnalysis && (
          <div className="space-y-6">
            {/* Top Grid: Player (Left) + Moment List (Right) */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-7 space-y-4">
                <VideoPlayer
                  jobId={jobId}
                  renderId={activeRenderId}
                  proxyReady={job?.proxy_ready || false}
                  windows={editedWindows}
                  focusedMomentIndex={focusedIndex}
                  onSelectMoment={setFocusedIndex}
                  onToggleInclude={handleToggleInclude}
                  reelReady={Boolean(job?.status === 'completed' || (job?.renders && job.renders.some((r) => r.id === activeRenderId && r.status === 'completed')))}
                  isRendering={job?.status === 'rendering' || isCustomRendering}
                  onAddMomentAtTime={handleRequestAddMoment}
                />
              </div>

              <div className="lg:col-span-5 h-[480px]">
                <MomentList
                  windows={editedWindows}
                  suggestions={analysis.suggestions || []}
                  targetDuration={job?.config?.target_duration || 480}
                  focusedIndex={focusedIndex}
                  onSelectMoment={setFocusedIndex}
                  onToggleInclude={handleToggleInclude}
                  onUpdateWindow={handleUpdateWindow}
                  onUpdateTag={handleUpdateTag}
                  onBulkSelect={handleBulkSelect}
                  onTryMoreSensitive={() => {
                    const currentRise = job?.config?.min_rise_db || 4.0;
                    const currentSustain = job?.config?.min_sustain_s || 3.0;
                    handleRetune({
                      min_rise_db: Math.max(1.0, currentRise - 1.0),
                      min_sustain_s: Math.max(1.0, currentSustain - 0.5),
                    });
                  }}
                  onPreviewSource={(idx) => {
                    setFocusedIndex(idx);
                  }}
                  onAddSuggestion={handleAddSuggestion}
                />
              </div>
            </div>

            {/* Match Timeline (Spans full width below player) */}
            <Timeline
              envelope={analysis.envelope}
              duration={analysis.duration_s}
              windows={editedWindows}
              suggestions={analysis.suggestions || []}
              labels={labels}
              skipStartSeconds={job?.config?.skip_start_s || 30}
              minRiseDb={job?.config?.min_rise_db || 4.0}
              focusedIndex={focusedIndex}
              onSelectMoment={setFocusedIndex}
              onUpdateWindow={handleUpdateWindow}
              onAddMomentAtTime={handleRequestAddMoment}
              onAddSuggestion={handleAddSuggestion}
              currentTime={playerCurrentTime}
              onSeek={(t) => setPlayerCurrentTime(t)}
            />
          </div>
        )}
      </div>

      {/* Sticky Bottom Render Bar */}
      {hasAnalysis && (
        <RenderBar
          jobId={jobId}
          hasUnrenderedChanges={hasUnrenderedChanges}
          isRendering={job?.status === 'rendering' || isCustomRendering}
          renderProgressText={customRenderProgressText}
          renders={job?.renders || []}
          activeRenderId={activeRenderId}
          onSelectRender={(rid) => setActiveRenderId(rid)}
          onRenderReel={handleRenderReel}
          selectedMomentsCount={editedWindows.filter((w) => w.selected).length}
          totalSelectedDuration={editedWindows.filter((w) => w.selected).reduce((acc, w) => acc + w.duration, 0)}
        />
      )}

      {/* Tuning Drawer */}
      {hasAnalysis && (
        <TuningDrawer
          isOpen={isTuningOpen}
          onClose={() => setIsTuningOpen(false)}
          config={job?.config || {}}
          schemaFields={[]}
          onRetune={handleRetune}
          isRetuning={false}
        />
      )}

      {/* Cancel Confirmation Modal */}
      <Modal
        isOpen={isCancelModalOpen}
        onClose={() => setIsCancelModalOpen(false)}
        title="Cancel Job Processing?"
        description="Terminating will stop audio extraction or video cutting immediately."
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => setIsCancelModalOpen(false)}>
              Keep Running
            </Button>
            <Button variant="danger" size="sm" onClick={handleCancelJob}>
              Confirm Cancel
            </Button>
          </>
        }
      >
        <p className="text-xs text-muted">
          All running child FFmpeg processes for this job will be immediately stopped and no partial files will be kept.
        </p>
      </Modal>

      {/* Manual Add Moment Modal */}
      <Modal
        isOpen={isAddMomentModalOpen}
        onClose={() => setIsAddMomentModalOpen(false)}
        title="Add Highlight Moment"
        description="Create a manual highlight window around an exciting match moment."
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => setIsAddMomentModalOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => handleRequestAddMoment(parseTimeInput(manualMomentTimeInput))}
            >
              Add Moment
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="text-xs font-bold text-text uppercase tracking-wider block mb-1">
              Event Timestamp (Seconds or MM:SS)
            </label>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={manualMomentTimeInput}
                onChange={(e) => setManualMomentTimeInput(e.target.value)}
                placeholder="e.g. 14:32 or 872"
                className="flex-1 bg-card border border-border rounded-lg px-3 py-2 text-sm text-text font-mono focus:outline-none focus:border-primary"
              />
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setManualMomentTimeInput(formatTimeHMS(playerCurrentTime))}
                className="whitespace-nowrap"
              >
                Use Player Time ({formatTimeHMS(playerCurrentTime)})
              </Button>
            </div>
          </div>
          <p className="text-xs text-muted leading-relaxed">
            A window of <strong className="text-text">[{job?.config?.pre_roll ?? 12}s pre-roll + {job?.config?.post_roll ?? 6}s post-roll]</strong> will be created, clamped to duration, marked as manual, selected by default, and included in renders.
          </p>
        </div>
      </Modal>

      {/* Overlap Rejection / Merge Modal */}
      <Modal
        isOpen={!!overlapModalData}
        onClose={() => setOverlapModalData(null)}
        title="Moment Overlap Detected"
        description="Highlights in the reel cannot overlap with one another."
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => setOverlapModalData(null)}>
              Cancel
            </Button>
            <Button variant="primary" size="sm" onClick={handleConfirmMerge}>
              Merge with Existing Moment
            </Button>
          </>
        }
      >
        {overlapModalData && (
          <div className="space-y-3">
            <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs space-y-1">
              <div className="font-semibold text-amber-300">
                New candidate span: {formatTimeHMS(overlapModalData.newWindow.start)} → {formatTimeHMS(overlapModalData.newWindow.end)}
              </div>
              <div>
                Overlaps with:{' '}
                {overlapModalData.overlappingIndices
                  .map((i) => `#${i + 1} (${editedWindows[i]?.start_hms} → ${editedWindows[i]?.end_hms})`)
                  .join(', ')}
              </div>
            </div>
            <p className="text-xs text-muted leading-relaxed">
              Highlights cannot overlap in the final reel. Would you like to merge these moments into a single continuous highlight window?
            </p>
          </div>
        )}
      </Modal>

      {/* Ground-Truth Event Labels & Recall Modal */}
      <Modal
        isOpen={isLabelsModalOpen}
        onClose={() => setIsLabelsModalOpen(false)}
        title="Ground-Truth Event Labels"
        description="Enter known key events (crowd peaks, cards) to measure recall and optimize hyperparameters."
        footer={
          <Button variant="secondary" size="sm" onClick={() => setIsLabelsModalOpen(false)}>
            Close
          </Button>
        }
      >
        <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-1">
          {/* Recall Summary Card */}
          <div className="p-3.5 rounded-xl bg-card border border-border flex items-center justify-between gap-3 flex-wrap">
            <div>
              <div className="text-[11px] uppercase tracking-wider text-muted font-bold">Detection Recall</div>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-lg font-mono font-extrabold text-text">
                  {labelSummary && labelSummary.total > 0 ? `${(labelSummary.recall * 100).toFixed(0)}%` : '0%'}
                </span>
                <span className="text-xs text-muted font-mono">
                  ({labelSummary?.caught || 0} of {labelSummary?.total || 0} caught
                  {labelSummary && labelSummary.missed > 0 ? `, ${labelSummary.missed} missed` : ''})
                </span>
              </div>
            </div>

            {labels.length > 0 && (
              <Button
                variant="primary"
                size="sm"
                onClick={handleRunSweep}
                isLoading={isSweeping}
                className="gap-1.5 whitespace-nowrap"
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>Find Better Settings</span>
              </Button>
            )}
          </div>

          {/* Add Label Form */}
          <div className="p-3 rounded-xl bg-surface border border-border space-y-3">
            <h4 className="text-xs font-bold text-text uppercase tracking-wider">Add Known Event</h4>
            <div className="grid grid-cols-1 sm:grid-cols-12 gap-2">
              <div className="sm:col-span-4">
                <input
                  type="text"
                  value={newLabelTime}
                  onChange={(e) => setNewLabelTime(e.target.value)}
                  placeholder={`Time (e.g. ${formatTimeHMS(playerCurrentTime)})`}
                  className="w-full bg-card border border-border rounded-lg px-2.5 py-1.5 text-xs text-text font-mono focus:outline-none focus:border-primary"
                />
              </div>
              <div className="sm:col-span-6">
                <input
                  type="text"
                  value={newLabelText}
                  onChange={(e) => setNewLabelText(e.target.value)}
                  placeholder="Event label (e.g. Roar 1-0)"
                  className="w-full bg-card border border-border rounded-lg px-2.5 py-1.5 text-xs text-text focus:outline-none focus:border-primary"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleAddLabel();
                  }}
                />
              </div>
              <div className="sm:col-span-2">
                <Button variant="primary" size="sm" onClick={handleAddLabel} className="w-full text-xs py-1.5">
                  Add
                </Button>
              </div>
            </div>
            <div className="flex items-center justify-between text-[11px] text-muted">
              <span>* Events within ±3s of selected windows are marked as caught.</span>
              <button
                type="button"
                onClick={() => setNewLabelTime(formatTimeHMS(playerCurrentTime))}
                className="text-primary hover:underline"
              >
                Set to current time ({formatTimeHMS(playerCurrentTime)})
              </button>
            </div>
          </div>

          {/* Labels List */}
          <div className="space-y-2">
            <h4 className="text-xs font-bold text-text uppercase tracking-wider">
              Entered Labels ({labels.length})
            </h4>
            {labels.length === 0 ? (
              <p className="text-xs text-muted italic p-3 bg-card/40 rounded-lg border border-border/60 text-center">
                No ground-truth labels added yet. Add known crowd events to evaluate recall.
              </p>
            ) : (
              <div className="space-y-1.5">
                {labels.map((lbl) => (
                  <div
                    key={lbl.id || lbl.time}
                    className="flex items-center justify-between p-2.5 rounded-lg bg-card border border-border text-xs"
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className={cn(
                          'px-2 py-0.5 rounded text-[10px] font-bold font-mono border',
                          lbl.caught
                            ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                            : 'bg-rose-500/15 text-rose-400 border-rose-500/30'
                        )}
                      >
                        {lbl.caught ? 'CAUGHT ✓' : 'MISSED ✗'}
                      </span>
                      <span className="font-mono font-bold text-text">{formatTimeHMS(lbl.time)}</span>
                      <span className="text-text font-medium">{lbl.label}</span>
                    </div>

                    <button
                      onClick={() => lbl.id && handleDeleteLabel(lbl.id)}
                      className="text-muted hover:text-rose-400 p-1 rounded transition-colors"
                      title="Delete label"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </Modal>

      {/* Sweep Results Modal */}
      <Modal
        isOpen={!!sweepModalData}
        onClose={() => setSweepModalData(null)}
        title="Optimal Parameter Recommendations"
        description="Proposed settings from hyperparameter sweep evaluated against your ground-truth labels."
        footer={
          <Button variant="ghost" size="sm" onClick={() => setSweepModalData(null)}>
            Close
          </Button>
        }
      >
        {sweepModalData && (
          <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
            {sweepModalData.results.length === 0 ? (
              <p className="text-xs text-muted">No sweep results returned.</p>
            ) : (
              sweepModalData.results.slice(0, 5).map((r, idx) => (
                <div
                  key={idx}
                  className={cn(
                    'p-3.5 rounded-xl border space-y-2.5 transition-all',
                    idx === 0
                      ? 'bg-primary/10 border-primary/40 ring-1 ring-primary/20'
                      : 'bg-card border-border'
                  )}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span
                        className={cn(
                          'px-2 py-0.5 rounded text-xs font-mono font-bold',
                          idx === 0 ? 'bg-primary text-slate-950' : 'bg-surface text-muted'
                        )}
                      >
                        Rank #{idx + 1}
                      </span>
                      <span className="text-xs font-bold text-text">
                        {(r.recall * 100).toFixed(0)}% Recall • F1: {r.f1.toFixed(3)}
                      </span>
                    </div>

                    <Button
                      variant={idx === 0 ? 'primary' : 'outline'}
                      size="sm"
                      onClick={() => handleApplySweepResult(r)}
                      className="text-xs"
                    >
                      Apply Settings
                    </Button>
                  </div>

                  <div className="grid grid-cols-3 gap-2 text-xs font-mono bg-surface/60 p-2 rounded-lg border border-border/40">
                    <div>
                      <span className="text-muted text-[10px] block">Min Rise</span>
                      <strong className="text-text">{r.min_rise_db} dB</strong>
                    </div>
                    <div>
                      <span className="text-muted text-[10px] block">Min Sustain</span>
                      <strong className="text-text">{r.min_sustain_s} s</strong>
                    </div>
                    <div>
                      <span className="text-muted text-[10px] block">Pre-Roll</span>
                      <strong className="text-text">{r.pre_roll} s</strong>
                    </div>
                  </div>

                  <div className="text-[11px] text-muted flex items-center justify-between font-mono">
                    <span>Precision: {(r.precision * 100).toFixed(0)}%</span>
                    <span>
                      Reel: {r.reel_duration_s}s ({r.windows} clips)
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};
