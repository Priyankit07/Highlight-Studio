import React, { useState, useRef, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Upload,
  Link as LinkIcon,
  Sparkles,
  AlertCircle,
  Play,
  CheckCircle2,
  FileVideo,
  Pause,
  RotateCcw,
  Sliders,
  ChevronDown,
  ChevronUp,
  Loader2,
  Copy,
  Check,
  Download,
  BookmarkPlus,
} from 'lucide-react';
import { api, ApiError } from '../lib/api';
import { ImportCheckResult, TuningPreset } from '../types';
import { getSavedPresets, savePresets, validatePresetName } from '../lib/presets';
import { Button } from '../components/ui/Button';
import { Slider } from '../components/ui/Slider';
import { ProgressBar } from '../components/ui/ProgressBar';
import {
  SENSITIVITY_LEVELS,
  sensitivityToParams,
  formatBytes,
  formatDuration,
  cn,
} from '../lib/utils';

export const NewJobPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const initialTab = searchParams.get('tab') === 'url' ? 'url' : 'upload';
  const [activeTab, setActiveTab] = useState<'upload' | 'url'>(initialTab);

  useEffect(() => {
    const tabParam = searchParams.get('tab');
    if (tabParam === 'upload' || tabParam === 'url') {
      setActiveTab(tabParam);
    }
  }, [searchParams]);

  // Form State
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [urlInput, setUrlInput] = useState('');
  const [customTitle, setCustomTitle] = useState('');
  const [quality, setQuality] = useState<number>(720);

  // URL Preflight State
  const [urlChecking, setUrlChecking] = useState(false);
  const [checkResult, setCheckResult] = useState<ImportCheckResult | null>(null);
  const [showHowToFix, setShowHowToFix] = useState(false);
  const [copiedCmd, setCopiedCmd] = useState(false);

  // Settings State
  const [targetDuration, setTargetDuration] = useState<number>(480);
  const [sensitivity, setSensitivity] = useState<number>(3);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [advancedOverrides, setAdvancedOverrides] = useState<Record<string, any>>({});

  // Preset Management State
  const [savedPresets, setSavedPresets] = useState<TuningPreset[]>(() => getSavedPresets());
  const [selectedPresetName, setSelectedPresetName] = useState<string>('');
  const [showSavePresetModal, setShowSavePresetModal] = useState(false);
  const [newPresetSaveName, setNewPresetSaveName] = useState('');
  const [savePresetError, setSavePresetError] = useState<string | null>(null);
  const [savePresetSuccess, setSavePresetSuccess] = useState<string | null>(null);

  // Load active draft preset if applied from Settings page
  useEffect(() => {
    try {
      const draftRaw = localStorage.getItem('active_draft_preset');
      if (draftRaw) {
        const draft = JSON.parse(draftRaw) as TuningPreset;
        localStorage.removeItem('active_draft_preset');
        if (draft && draft.config) {
          setSelectedPresetName(draft.name);
          if (draft.config.target_duration !== undefined) setTargetDuration(draft.config.target_duration);
          if (draft.config.sensitivity !== undefined) setSensitivity(draft.config.sensitivity);
          setAdvancedOverrides((prev) => ({
            ...prev,
            min_rise_db: draft.config.min_rise_db,
            min_sustain_s: draft.config.min_sustain_s,
            skip_start_s: draft.config.skip_start_s,
            pre_roll: draft.config.pre_roll,
            post_roll: draft.config.post_roll,
          }));
        }
      }
    } catch {
      // ignore
    }
  }, []);

  const handleSelectPreset = (name: string) => {
    setSelectedPresetName(name);
    const p = savedPresets.find((x) => x.name === name);
    if (!p) return;
    if (p.config.target_duration !== undefined) setTargetDuration(p.config.target_duration);
    if (p.config.sensitivity !== undefined) setSensitivity(p.config.sensitivity);
    setAdvancedOverrides((prev) => ({
      ...prev,
      min_rise_db: p.config.min_rise_db,
      min_sustain_s: p.config.min_sustain_s,
      skip_start_s: p.config.skip_start_s,
      pre_roll: p.config.pre_roll,
      post_roll: p.config.post_roll,
    }));
  };

  const handleSaveCurrentAsPreset = (e: React.FormEvent) => {
    e.preventDefault();
    setSavePresetError(null);
    const err = validatePresetName(newPresetSaveName, savedPresets);
    if (err) {
      setSavePresetError(err);
      return;
    }

    const sensParams = sensitivityToParams(sensitivity);
    const newPreset: TuningPreset = {
      name: newPresetSaveName.trim(),
      config: {
        target_duration: targetDuration,
        sensitivity,
        min_rise_db: advancedOverrides.min_rise_db ?? sensParams.min_rise_db,
        min_sustain_s: advancedOverrides.min_sustain_s ?? sensParams.min_sustain_s,
        skip_start_s: advancedOverrides.skip_start_s ?? 30,
        pre_roll: advancedOverrides.pre_roll ?? 12.0,
        post_roll: advancedOverrides.post_roll ?? 6.0,
      },
    };

    const updated = [...savedPresets, newPreset];
    setSavedPresets(updated);
    savePresets(updated);
    setSelectedPresetName(newPreset.name);
    setSavePresetSuccess(`Saved preset "${newPreset.name}"!`);
    setShowSavePresetModal(false);
    setNewPresetSaveName('');
    setTimeout(() => setSavePresetSuccess(null), 3000);
  };

  // Upload Progress State
  const [uploadId, setUploadId] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [uploadSpeed, setUploadSpeed] = useState<string>('');
  const [uploadEta, setUploadEta] = useState<string>('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Debounced URL preflight check (600ms)
  useEffect(() => {
    if (activeTab !== 'url') return;
    const trimmed = urlInput.trim();
    if (!trimmed) {
      setCheckResult(null);
      setUrlChecking(false);
      return;
    }

    setUrlChecking(true);
    setErrorMessage(null);
    const timer = setTimeout(async () => {
      try {
        const res = await api.checkImport(trimmed);
        setCheckResult(res);
        if (res.ok && res.title && !customTitle) {
          setCustomTitle(res.title);
        }
      } catch (err: any) {
        setCheckResult({
          ok: false,
          error_code: 'DOWNLOAD_FAILED',
          message: err.message || 'Failed to check URL.',
          hint: 'Please check your connection or upload the video file directly.',
        });
      } finally {
        setUrlChecking(false);
      }
    }, 600);

    return () => clearTimeout(timer);
  }, [urlInput, activeTab]);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const isPausedRef = useRef(isPaused);
  isPausedRef.current = isPaused;

  // Fetch Health & Config Schema
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: api.getHealth,
  });

  const { data: schemaData } = useQuery({
    queryKey: ['configSchema'],
    queryFn: api.getConfigSchema,
  });

  // Resume active upload on mount if saved in localStorage
  useEffect(() => {
    const saved = localStorage.getItem('active_upload');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (parsed.uploadId && parsed.filename) {
          setUploadId(parsed.uploadId);
        }
      } catch {}
    }
  }, []);

  const handleFileSelect = (file: File) => {
    setErrorMessage(null);
    const ext = `.${file.name.split('.').pop()?.toLowerCase()}`;
    const allowed = health?.limits?.allowed_extensions || ['.mp4', '.mkv', '.mov', '.avi', '.ts', '.webm', '.m4v'];

    if (!allowed.includes(ext)) {
      setErrorMessage(`Unsupported format '${ext}'. Supported video formats: ${allowed.join(', ')}`);
      return;
    }

    const maxBytes = (health?.limits?.max_upload_gb || 10) * 1024 * 1024 * 1024;
    if (file.size > maxBytes) {
      setErrorMessage(`File is too large (${formatBytes(file.size)}). Limit is ${health?.limits?.max_upload_gb || 10} GB`);
      return;
    }

    setSelectedFile(file);
    if (!customTitle) {
      setCustomTitle(file.name.replace(/\.[^/.]+$/, ''));
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  // Resumable, Parallel Chunked Uploader (3 in parallel with backoff)
  const executeChunkedUpload = async (file: File): Promise<string> => {
    setIsUploading(true);
    setErrorMessage(null);

    let activeUpId = uploadId;
    let chunkSize = 8 * 1024 * 1024;

    // 1. Initialize session if not already initialized
    if (!activeUpId) {
      const initRes = await api.initUpload(file.name, file.size);
      activeUpId = initRes.upload_id;
      chunkSize = initRes.chunk_size;
      setUploadId(activeUpId);
      localStorage.setItem('active_upload', JSON.stringify({ uploadId: activeUpId, filename: file.name }));
    }

    // 2. Query already received chunks
    const statusRes = await api.getUploadStatus(activeUpId);
    const receivedSet = new Set(statusRes.received || []);

    const totalChunks = Math.ceil(file.size / chunkSize);
    const chunksToUpload: number[] = [];
    for (let i = 0; i < totalChunks; i++) {
      if (!receivedSet.has(i)) chunksToUpload.push(i);
    }

    let uploadedBytes = receivedSet.size * chunkSize;
    const startTime = Date.now();
    let lastBytes = uploadedBytes;
    let lastTime = startTime;

    // Concurrency pool (up to 3 parallel chunks)
    const CONCURRENCY = 3;
    let poolIndex = 0;

    const uploadSingleChunk = async (chunkIndex: number) => {
      const startByte = chunkIndex * chunkSize;
      const endByte = Math.min(file.size, startByte + chunkSize);
      const chunkBlob = file.slice(startByte, endByte);

      let attempts = 0;
      while (attempts < 4) {
        if (isPausedRef.current) {
          // Poll while paused
          await new Promise((r) => setTimeout(r, 500));
          continue;
        }

        try {
          await api.uploadChunk(activeUpId!, chunkIndex, chunkBlob);
          uploadedBytes += chunkBlob.size;

          // Compute progress, speed, ETA
          const now = Date.now();
          const pct = Math.min(0.99, uploadedBytes / file.size);
          setUploadProgress(pct);

          const timeDelta = (now - lastTime) / 1000;
          if (timeDelta > 0.8) {
            const bytesDelta = uploadedBytes - lastBytes;
            const speedMbps = (bytesDelta / timeDelta) / (1024 * 1024);
            setUploadSpeed(`${speedMbps.toFixed(1)} MB/s`);

            const remainingBytes = file.size - uploadedBytes;
            const etaSeconds = speedMbps > 0 ? remainingBytes / (speedMbps * 1024 * 1024) : 0;
            setUploadEta(`${Math.round(etaSeconds)}s remaining`);

            lastTime = now;
            lastBytes = uploadedBytes;
          }
          return;
        } catch (err) {
          attempts++;
          if (attempts >= 4) throw err;
          // Exponential backoff
          await new Promise((r) => setTimeout(r, 1000 * Math.pow(2, attempts)));
        }
      }
    };

    // Run pool
    const workers = Array.from({ length: CONCURRENCY }).map(async () => {
      while (poolIndex < chunksToUpload.length) {
        const idx = chunksToUpload[poolIndex++];
        await uploadSingleChunk(idx);
      }
    });

    await Promise.all(workers);

    // 3. Complete and assemble
    await api.completeUpload(activeUpId!);
    localStorage.removeItem('active_upload');
    setUploadProgress(1.0);
    return activeUpId!;
  };

  const handleStartPipeline = async () => {
    setErrorMessage(null);
    const sensitivityParams = sensitivityToParams(sensitivity);
    const effectiveConfig = {
      ...sensitivityParams,
      target_duration: targetDuration,
      quality,
      ...advancedOverrides,
    };

    try {
      let jobRes: { job_id: string; title: string; status: string; queue_position: number };

      if (activeTab === 'upload') {
        if (!selectedFile) {
          setErrorMessage('Please select or drop a football match video to upload.');
          return;
        }

        const completedUploadId = await executeChunkedUpload(selectedFile);
        jobRes = await api.createJob({
          source: { type: 'upload', upload_id: completedUploadId },
          title: customTitle || selectedFile.name,
          config: effectiveConfig,
        });
      } else {
        if (!urlInput.trim()) {
          setErrorMessage('Please provide a match stream or video URL.');
          return;
        }

        if (!checkResult || !checkResult.ok) {
          setErrorMessage('URL preflight check must pass before generating highlights.');
          return;
        }

        setIsUploading(true);
        jobRes = await api.createJob({
          source: { type: 'url', url: urlInput.trim() },
          title: customTitle || checkResult.title || 'Stream Highlights',
          config: effectiveConfig,
        });
      }

      // Strictly verify that a valid job_id was returned before navigating
      if (!jobRes || typeof jobRes.job_id !== 'string' || !jobRes.job_id.trim()) {
        throw new Error('Job creation failed: Server did not return a valid job ID.');
      }

      // Only navigate once the job is confirmed to exist
      navigate(`/jobs/${jobRes.job_id}`);
    } catch (err: any) {
      setIsUploading(false);
      setErrorMessage(err.message || 'Failed to start highlight generation.');
    }
  };

  return (
    <div className="min-h-[calc(100vh-70px)] bg-pitch-lines flex flex-col items-center justify-center p-6 sm:p-10">
      <div className="w-full max-w-2xl space-y-6">
        {/* Hero Pitch Headline */}
        <div className="text-center space-y-2">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 border border-primary/20 text-xs font-mono text-primary font-semibold">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Audio Excitement Detection</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-text">
            Generate Match Highlights
          </h1>
          <p className="text-sm text-muted max-w-lg mx-auto leading-relaxed">
            Turn full 90-minute matches into concise excitement reels. Detects crowd roars and commentator crescendos with adaptive audio baseline filtering.
          </p>
        </div>

        {/* Hackathon Judge / Sample Match Banner */}
        <div className="p-4 rounded-2xl bg-gradient-to-r from-primary/15 via-emerald-500/10 to-surface border border-primary/30 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/20 border border-primary/40 flex items-center justify-center text-xl shrink-0">
              ⚡
            </div>
            <div>
              <h3 className="text-sm font-bold text-text">Instant Demo</h3>
              <p className="text-xs text-muted">
                Explore a pre-processed 12-minute synthetic match, or test live with a 60s sample clip.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0 flex-wrap">
            <Button
              variant="primary"
              size="sm"
              onClick={() => navigate('/jobs/demo-match')}
              className="gap-1.5 text-xs whitespace-nowrap shadow-sm shadow-primary/20"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Try with a sample match</span>
            </Button>

            <a
              href="/api/sample/clip"
              download="sample_match_60s.mp4"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-card hover:bg-surface border border-border text-xs font-semibold text-text transition-colors whitespace-nowrap"
              title="Download 60s test clip (805 KB) for 1-minute live pipeline run"
            >
              <Download className="w-3.5 h-3.5 text-primary" />
              <span>Get 60s Clip (805 KB)</span>
            </a>
          </div>
        </div>

        {/* Source Mode Tabs */}
        <div className="bg-surface border border-border rounded-2xl p-6 shadow-xl space-y-6">
          <div className="flex bg-card p-1 rounded-xl border border-border">
            <button
              onClick={() => setActiveTab('upload')}
              className={cn(
                'flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-semibold transition-all',
                activeTab === 'upload' ? 'bg-surface text-text shadow-sm' : 'text-muted hover:text-text'
              )}
            >
              <Upload className="w-4 h-4" />
              <span>Upload Video File</span>
            </button>
            {health?.url_import_enabled !== false && (
              <button
                onClick={() => setActiveTab('url')}
                className={cn(
                  'flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-semibold transition-all',
                  activeTab === 'url' ? 'bg-surface text-text shadow-sm' : 'text-muted hover:text-text'
                )}
              >
                <LinkIcon className="w-4 h-4" />
                <span>Import from URL</span>
              </button>
            )}
          </div>

          {/* Tab 1: Drag & Drop Zone */}
          {activeTab === 'upload' ? (
            <div>
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={cn(
                  'border-2 border-dashed rounded-xl p-8 flex flex-col items-center justify-center text-center cursor-pointer transition-all',
                  selectedFile
                    ? 'border-primary/50 bg-primary/5'
                    : 'border-border hover:border-accent hover:bg-card/40'
                )}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".mp4,.mkv,.mov,.avi,.ts,.webm,.m4v"
                  className="hidden"
                  onChange={(e) => e.target.files?.[0] && handleFileSelect(e.target.files[0])}
                />

                {selectedFile ? (
                  <div className="flex items-center gap-3 text-left">
                    <div className="w-12 h-12 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center text-primary">
                      <FileVideo className="w-6 h-6" />
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-text truncate max-w-sm">{selectedFile.name}</h4>
                      <p className="text-xs text-muted font-mono">{formatBytes(selectedFile.size)} • Ready to upload</p>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="w-12 h-12 rounded-full bg-card border border-border flex items-center justify-center mx-auto text-muted group-hover:text-text">
                      <Upload className="w-6 h-6" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-text">Drop match video here, or click to browse</p>
                      <p className="text-xs text-muted mt-1">MP4, MKV, MOV, TS, AVI, WebM (up to 10 GB)</p>
                    </div>
                  </div>
                )}
              </div>

              {/* Upload Progress Bar if Uploading */}
              {isUploading && (
                <div className="mt-4 p-4 rounded-xl bg-card border border-border space-y-2">
                  <div className="flex items-center justify-between text-xs font-mono">
                    <span className="font-bold text-text">Uploading chunks ({Math.round(uploadProgress * 100)}%)</span>
                    <span className="text-muted">{uploadSpeed} • {uploadEta}</span>
                  </div>
                  <ProgressBar value={uploadProgress} />
                  <div className="flex items-center justify-end gap-2 pt-1">
                    <button
                      onClick={() => setIsPaused(!isPaused)}
                      className="text-xs text-muted hover:text-text flex items-center gap-1"
                    >
                      {isPaused ? <RotateCcw className="w-3 h-3" /> : <Pause className="w-3 h-3" />}
                      <span>{isPaused ? 'Resume' : 'Pause'}</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            /* Tab 2: URL Import */
            <div className="space-y-4">
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-text">Match Video or Stream URL</label>
                  {urlChecking && (
                    <span className="text-[11px] text-accent flex items-center gap-1 font-mono">
                      <Loader2 className="w-3 h-3 animate-spin" />
                      Checking URL...
                    </span>
                  )}
                </div>
                <input
                  type="url"
                  value={urlInput}
                  onChange={(e) => {
                    setUrlInput(e.target.value);
                    setErrorMessage(null);
                  }}
                  placeholder="https://www.youtube.com/watch?v=... or direct MP4/stream URL"
                  className="w-full bg-card border border-border rounded-xl px-4 py-2.5 text-sm text-text placeholder:text-muted focus:outline-none focus:border-accent"
                />
                <p className="text-[11px] text-muted leading-relaxed">
                  Direct files (.mp4, .mkv, .mov, .ts, .webm) and platform streams are supported.
                </p>
                {health?.app_env === 'demo' && (
                  <p className="text-[11px] text-amber-400 font-medium">
                    Experimental: works best when self-hosted.
                  </p>
                )}
              </div>

              {/* Quality Selector */}
              <div className="flex items-center justify-between p-3 rounded-xl bg-card border border-border">
                <div>
                  <span className="text-xs font-bold text-text block">Download Quality</span>
                  <span className="text-[11px] text-muted block">Merged with best audio</span>
                </div>
                <div className="flex gap-1.5">
                  {[
                    { q: 480, label: '480p' },
                    { q: 720, label: '720p' },
                    { q: 1080, label: '1080p' },
                  ].map((item) => (
                    <button
                      key={item.q}
                      type="button"
                      onClick={() => setQuality(item.q)}
                      className={cn(
                        'px-3 py-1.5 rounded-lg text-xs font-mono font-semibold transition-all border',
                        quality === item.q
                          ? 'bg-primary/20 text-primary border-primary/40'
                          : 'bg-surface text-muted hover:text-text border-border'
                      )}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Preflight Preview Card: Success */}
              {checkResult && checkResult.ok && (
                <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-start gap-4">
                  {checkResult.thumbnail ? (
                    <img
                      src={checkResult.thumbnail}
                      alt={checkResult.title}
                      className="w-24 h-16 object-cover rounded-lg border border-border shrink-0 bg-black/40"
                    />
                  ) : (
                    <div className="w-24 h-16 rounded-lg bg-card border border-border flex items-center justify-center shrink-0 text-muted">
                      <FileVideo className="w-8 h-8 text-emerald-400" />
                    </div>
                  )}
                  <div className="flex-1 min-w-0 space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                        <CheckCircle2 className="w-3 h-3" />
                        Ready
                      </span>
                      {checkResult.duration_s > 0 && (
                        <span className="text-[11px] font-mono text-muted">
                          {formatDuration(checkResult.duration_s)}
                        </span>
                      )}
                      {checkResult.est_size_mb && (
                        <span className="text-[11px] font-mono text-muted">
                          • ~{Math.round(checkResult.est_size_mb)} MB
                        </span>
                      )}
                    </div>
                    <h4 className="text-sm font-semibold text-text truncate" title={checkResult.title}>
                      {checkResult.title}
                    </h4>
                    <p className="text-[11px] text-emerald-400/90 font-mono">
                      Stream verified & ready for highlight generation.
                    </p>
                  </div>
                </div>
              )}

              {/* Preflight Preview Card: Error */}
              {checkResult && !checkResult.ok && (
                <div className="p-4 rounded-xl bg-danger/10 border border-danger/30 space-y-3">
                  <div className="flex items-start gap-3">
                    <AlertCircle className="w-5 h-5 text-danger shrink-0 mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-danger/20 text-danger border border-danger/30">
                          {checkResult.error_code}
                        </span>
                      </div>
                      <p className="text-xs font-semibold text-text mt-1">{checkResult.message}</p>
                      {checkResult.error_code === 'SOURCE_BLOCKED' && (
                        <p className="text-xs text-amber-300 font-medium mt-1">
                          Video sites often block downloads from cloud servers. Upload the file instead.
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Collapsible How to fix */}
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
                        <p>{checkResult.hint}</p>
                        {(checkResult.hint.includes('curl') || checkResult.hint.includes('uv add')) && (
                          <div className="flex items-center justify-between bg-black/40 px-3 py-1.5 rounded font-mono text-[11px] text-text border border-border">
                            <code>
                              {checkResult.hint.includes('curl')
                                ? 'curl -fsSL https://deno.land/install.sh | sh'
                                : 'uv add "yt-dlp[default]"'}
                            </code>
                            <button
                              type="button"
                              onClick={() => {
                                const cmd = checkResult.hint.includes('curl')
                                  ? 'curl -fsSL https://deno.land/install.sh | sh'
                                  : 'uv add "yt-dlp[default]"';
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

                  {/* Prominent fallback: Upload video file */}
                  <div className="pt-2 flex items-center justify-between border-t border-danger/20">
                    <span className="text-xs text-muted">Prefer local file?</span>
                    <button
                      type="button"
                      onClick={() => setActiveTab('upload')}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface border border-border text-xs font-semibold text-text hover:bg-card hover:border-accent transition-colors"
                    >
                      <Upload className="w-3.5 h-3.5" />
                      <span>Upload video file instead</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Title Input */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-text">Project Title (Optional)</label>
            <input
              type="text"
              value={customTitle}
              onChange={(e) => setCustomTitle(e.target.value)}
              placeholder="e.g. Manchester United vs Liverpool - 2nd Half"
              className="w-full bg-card border border-border rounded-xl px-4 py-2 text-sm text-text placeholder:text-muted focus:outline-none focus:border-accent"
            />
          </div>

          {/* Compact Reel Settings Row */}
          <div className="pt-4 border-t border-border space-y-4">
            {/* Preset Dropdown & Save as Preset Bar */}
            <div className="space-y-2">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 bg-card/60 border border-border/80 rounded-xl">
                <div className="flex items-center gap-2.5 flex-1">
                  <Sparkles className="w-4 h-4 text-primary shrink-0" />
                  <span className="text-xs font-bold text-text shrink-0">Tuning Preset:</span>
                  <select
                    value={selectedPresetName}
                    onChange={(e) => handleSelectPreset(e.target.value)}
                    className="bg-surface border border-border rounded-lg px-3 py-1.5 text-xs text-text focus:outline-none focus:border-primary flex-1 max-w-xs font-medium"
                  >
                    <option value="">Custom / Ad-hoc</option>
                    {savedPresets.map((p) => (
                      <option key={p.name} value={p.name}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </div>

                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setSavePresetError(null);
                    setShowSavePresetModal(!showSavePresetModal);
                  }}
                  className="gap-1.5 text-xs py-1 text-muted hover:text-text self-start sm:self-auto"
                >
                  <BookmarkPlus className="w-3.5 h-3.5 text-accent" />
                  <span>Save as preset</span>
                </Button>
              </div>

              {savePresetSuccess && (
                <div className="p-2 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-xs font-medium text-emerald-400 flex items-center gap-2">
                  <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                  <span>{savePresetSuccess}</span>
                </div>
              )}

              {/* Inline Save As Preset Form */}
              {showSavePresetModal && (
                <form
                  onSubmit={handleSaveCurrentAsPreset}
                  className="p-3 bg-surface border border-primary/40 rounded-xl space-y-3 animate-in fade-in"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-text">Save Current Settings as Preset</span>
                    <button
                      type="button"
                      onClick={() => setShowSavePresetModal(false)}
                      className="text-xs text-muted hover:text-text"
                    >
                      Cancel
                    </button>
                  </div>

                  {savePresetError && (
                    <div className="p-2 bg-danger/10 border border-danger/30 rounded-lg text-xs text-danger flex items-center gap-1.5">
                      <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                      <span>{savePresetError}</span>
                    </div>
                  )}

                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={newPresetSaveName}
                      onChange={(e) => setNewPresetSaveName(e.target.value)}
                      placeholder="Preset name (e.g. World Cup Final 5m)"
                      className="flex-1 bg-card border border-border rounded-lg px-3 py-1.5 text-xs text-text focus:outline-none focus:border-primary"
                      autoFocus
                    />
                    <Button type="submit" size="sm" variant="primary" className="gap-1 text-xs">
                      <Check className="w-3.5 h-3.5" />
                      <span>Save</span>
                    </Button>
                  </div>
                </form>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Length Presets */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-bold text-text uppercase tracking-wider">Length Preset</label>
                  <span className="text-xs font-mono font-semibold text-primary">
                    {targetDuration === 0 ? 'All' : `${targetDuration / 60} min`}
                  </span>
                </div>
                <div className="grid grid-cols-5 gap-1">
                  {[
                    { label: '2m', val: 120 },
                    { label: '5m', val: 300 },
                    { label: '8m', val: 480 },
                    { label: '12m', val: 720 },
                    { label: 'All', val: 0 },
                  ].map((p) => (
                    <button
                      key={p.val}
                      type="button"
                      onClick={() => setTargetDuration(p.val)}
                      className={cn(
                        'py-1.5 rounded-lg text-xs font-mono font-semibold border transition-all',
                        targetDuration === p.val
                          ? 'bg-primary/20 text-primary border-primary/40'
                          : 'bg-card text-muted hover:text-text border-border'
                      )}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
                <p className="text-[11px] text-muted">A cap, not a target. Reel only includes moments actually detected.</p>
              </div>

              {/* Sensitivity Slider */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-bold text-text uppercase tracking-wider">Sensitivity</label>
                  <span className="text-xs font-mono font-semibold text-accent">
                    {SENSITIVITY_LEVELS.find((s) => s.level === sensitivity)?.label}
                  </span>
                </div>
                <input
                  type="range"
                  min={1}
                  max={5}
                  step={1}
                  value={sensitivity}
                  onChange={(e) => setSensitivity(parseInt(e.target.value))}
                  className="w-full h-1.5 bg-border rounded-lg appearance-none cursor-pointer accent-primary"
                />
                <p className="text-[11px] text-muted">
                  {SENSITIVITY_LEVELS.find((s) => s.level === sensitivity)?.desc}
                </p>
              </div>
            </div>

            {/* Advanced Disclosure */}
            <div className="pt-2">
              <button
                type="button"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="flex items-center gap-1.5 text-xs font-semibold text-muted hover:text-text transition-colors"
              >
                <Sliders className="w-3.5 h-3.5" />
                <span>Advanced Pipeline Configuration</span>
                {showAdvanced ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              </button>

              {showAdvanced && schemaData && (
                <div className="mt-3 p-4 rounded-xl bg-card border border-border grid grid-cols-1 sm:grid-cols-2 gap-4 animate-in fade-in duration-150">
                  {schemaData.fields
                    .filter((f) => f.group === 'advanced' && f.min !== undefined && f.max !== undefined)
                    .map((field) => (
                      <Slider
                        key={field.name}
                        label={field.name.replace(/_/g, ' ')}
                        description={field.description}
                        min={field.min}
                        max={field.max}
                        step={field.step || 1}
                        unit={field.unit}
                        value={advancedOverrides[field.name] ?? field.default}
                        onChange={(e) =>
                          setAdvancedOverrides({
                            ...advancedOverrides,
                            [field.name]: parseFloat(e.target.value),
                          })
                        }
                      />
                    ))}

                  {/* Score Ranking Mode Selection */}
                  <div className="space-y-1.5 sm:col-span-2 pt-2 border-t border-border/40">
                    <label className="text-xs font-bold text-text uppercase tracking-wider">Score Ranking Mode</label>
                    <div className="grid grid-cols-3 gap-2">
                      {[
                        { id: 'area', label: 'Area (Default)', desc: 'Rank by excitement integral' },
                        { id: 'peak', label: 'Peak (Rise dB)', desc: 'Rank by highest spike rise' },
                        { id: 'blend', label: 'Blend', desc: 'Normalized blend of area and peak' },
                      ].map((mode) => (
                        <button
                          key={mode.id}
                          type="button"
                          onClick={() =>
                            setAdvancedOverrides({
                              ...advancedOverrides,
                              score_mode: mode.id,
                            })
                          }
                          className={cn(
                            'px-3 py-2 rounded-lg text-xs font-medium border text-center transition-all',
                            (advancedOverrides.score_mode || 'area') === mode.id
                              ? 'bg-primary/20 text-primary border-primary/40 font-bold'
                              : 'bg-surface text-muted hover:text-text border-border'
                          )}
                          title={mode.desc}
                        >
                          <div className="font-semibold">{mode.label}</div>
                          <div className="text-[10px] text-muted font-normal mt-0.5">{mode.desc}</div>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Error Banner */}
          {errorMessage && (
            <div className="p-3.5 rounded-xl bg-danger/10 border border-danger/30 text-danger text-xs flex items-center gap-2.5">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}

          {/* Primary CTA Button */}
          <Button
            onClick={handleStartPipeline}
            disabled={
              activeTab === 'url'
                ? (!checkResult || !checkResult.ok || urlChecking || isUploading)
                : (!selectedFile || isUploading)
            }
            isLoading={isUploading}
            size="lg"
            className="w-full text-base font-bold shadow-lg shadow-primary/20 gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Sparkles className="w-5 h-5" />
            <span>Generate Highlights</span>
          </Button>
        </div>
      </div>
    </div>
  );
};
