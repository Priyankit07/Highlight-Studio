import React, { useRef, useState, useEffect } from 'react';
import { Play, Pause, RotateCcw, Volume2, VolumeX, Maximize, Film, Eye, Sparkles, Plus } from 'lucide-react';
import { WindowItem } from '../../types';
import { formatTimeHMS, cn } from '../../lib/utils';

export interface VideoPlayerProps {
  jobId: string;
  renderId: string;
  proxyReady: boolean;
  windows: WindowItem[];
  focusedMomentIndex: number;
  onSelectMoment: (index: number) => void;
  onToggleInclude: (index: number) => void;
  reelReady: boolean;
  isRendering: boolean;
  onAddMomentAtTime?: (time: number) => void;
}

export const VideoPlayer: React.FC<VideoPlayerProps> = ({
  jobId,
  renderId,
  proxyReady,
  windows,
  focusedMomentIndex,
  onSelectMoment,
  onToggleInclude,
  reelReady,
  isRendering,
  onAddMomentAtTime,
}) => {
  const [activeTab, setActiveTab] = useState<'reel' | 'source'>('reel');
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isMuted, setIsMuted] = useState(false);

  const focusedMoment = windows[focusedMomentIndex];

  // Video sources
  const reelSrc = `/api/jobs/${jobId}/media/renders/${renderId}/highlights.mp4`;
  const proxySrc = `/api/jobs/${jobId}/media/proxy.mp4`;

  // Seek and loop when in source preview mode
  useEffect(() => {
    if (activeTab === 'source' && focusedMoment && videoRef.current && proxyReady) {
      const v = videoRef.current;
      v.currentTime = focusedMoment.start;
      v.play().catch(() => {});
      setIsPlaying(true);
    }
  }, [activeTab, focusedMomentIndex, proxyReady]);

  // Handle loop boundaries in source mode
  const handleTimeUpdate = () => {
    if (!videoRef.current) return;
    const cur = videoRef.current.currentTime;
    setCurrentTime(cur);

    if (activeTab === 'source' && focusedMoment) {
      if (cur >= focusedMoment.end || cur < focusedMoment.start - 0.5) {
        videoRef.current.currentTime = focusedMoment.start;
      }
    }
  };

  const togglePlay = () => {
    if (!videoRef.current) return;
    if (isPlaying) {
      videoRef.current.pause();
      setIsPlaying(false);
    } else {
      videoRef.current.play().catch(() => {});
      setIsPlaying(true);
    }
  };

  const seekRelative = (seconds: number) => {
    if (!videoRef.current) return;
    videoRef.current.currentTime = Math.max(0, Math.min(duration || 99999, videoRef.current.currentTime + seconds));
  };

  // Global keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't intercept when typing in text fields
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target as HTMLElement)?.tagName)) return;

      if (e.code === 'Space') {
        e.preventDefault();
        togglePlay();
      } else if (e.code === 'KeyJ') {
        e.preventDefault();
        seekRelative(-5);
      } else if (e.code === 'KeyL') {
        e.preventDefault();
        seekRelative(5);
      } else if (e.key === '[') {
        e.preventDefault();
        if (focusedMomentIndex > 0) onSelectMoment(focusedMomentIndex - 1);
      } else if (e.key === ']') {
        e.preventDefault();
        if (focusedMomentIndex < windows.length - 1) onSelectMoment(focusedMomentIndex + 1);
      } else if (e.code === 'KeyX') {
        e.preventDefault();
        if (focusedMomentIndex >= 0) onToggleInclude(focusedMomentIndex);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isPlaying, focusedMomentIndex, windows.length, duration]);

  const selectedWindows = windows.filter((w) => w.selected);

  return (
    <div className="bg-surface border border-border rounded-xl overflow-hidden flex flex-col shadow-md">
      {/* Player Header Tabs */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-card/60 border-b border-border">
        <div className="flex items-center gap-1">
          <button
            onClick={() => setActiveTab('reel')}
            className={cn(
              'flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all',
              activeTab === 'reel'
                ? 'bg-primary text-slate-950 shadow-sm'
                : 'text-muted hover:text-text hover:bg-surface'
            )}
          >
            <Film className="w-3.5 h-3.5" />
            <span>Highlight Reel</span>
          </button>
          <button
            onClick={() => setActiveTab('source')}
            className={cn(
              'flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all',
              activeTab === 'source'
                ? 'bg-accent text-slate-950 shadow-sm'
                : 'text-muted hover:text-text hover:bg-surface'
            )}
          >
            <Eye className="w-3.5 h-3.5" />
            <span>Source Moment Preview</span>
          </button>
        </div>

        {/* Keyboard hints tooltip chip */}
        <div className="hidden lg:flex items-center gap-2 text-[11px] text-muted font-mono bg-surface px-2.5 py-1 rounded border border-border/60">
          <span>Space: Play</span>
          <span>•</span>
          <span>J/L: ±5s</span>
          <span>•</span>
          <span>[/]: Moment</span>
          <span>•</span>
          <span>X: Include</span>
        </div>
      </div>

      {/* Video Viewport Area */}
      <div className="relative aspect-video bg-black flex items-center justify-center overflow-hidden">
        {activeTab === 'reel' ? (
          reelReady ? (
            <video
              ref={videoRef}
              key={reelSrc}
              src={reelSrc}
              className="w-full h-full object-contain"
              onTimeUpdate={handleTimeUpdate}
              onLoadedMetadata={() => setDuration(videoRef.current?.duration || 0)}
              onPlay={() => setIsPlaying(true)}
              onPause={() => setIsPlaying(false)}
              onClick={togglePlay}
              playsInline
            />
          ) : (
            <div className="flex flex-col items-center justify-center p-8 text-center text-muted gap-3">
              <Sparkles className="w-10 h-10 text-primary animate-pulse" />
              <p className="text-sm font-medium text-text">
                {isRendering ? 'Rendering highlight reel with fade transitions...' : 'Reel not generated yet.'}
              </p>
              <p className="text-xs text-muted max-w-sm">
                You can review, trim, and adjust moments below while the reel encodes.
              </p>
            </div>
          )
        ) : proxyReady ? (
          <video
            ref={videoRef}
            key={proxySrc}
            src={proxySrc}
            className="w-full h-full object-contain"
            onTimeUpdate={handleTimeUpdate}
            onLoadedMetadata={() => setDuration(videoRef.current?.duration || 0)}
            onPlay={() => setIsPlaying(true)}
            onPause={() => setIsPlaying(false)}
            onClick={togglePlay}
            playsInline
          />
        ) : (
          <div className="flex flex-col items-center justify-center p-8 text-center text-muted gap-3">
            {focusedMoment?.thumb_url ? (
              <img
                src={focusedMoment.thumb_url}
                alt="Moment frame"
                className="max-h-48 rounded border border-border object-contain"
              />
            ) : null}
            <p className="text-sm text-text font-medium">Scrubbable proxy preview is being generated...</p>
            <p className="text-xs text-muted">Thumbnail preview shown above in the meantime.</p>
          </div>
        )}

        {/* Source mode loop badge */}
        {activeTab === 'source' && focusedMoment && (
          <div className="absolute top-3 left-3 bg-black/80 backdrop-blur-md px-3 py-1 rounded-full text-xs font-mono text-accent border border-accent/30 flex items-center gap-1.5 shadow">
            <RotateCcw className="w-3 h-3 animate-spin" style={{ animationDuration: '4s' }} />
            <span>Looping: {focusedMoment.start_hms} → {focusedMoment.end_hms}</span>
          </div>
        )}
      </div>

      {/* Video Controls Bar */}
      <div className="px-4 py-3 bg-surface border-t border-border flex flex-col gap-2.5">
        <div className="flex items-center gap-3">
          <button
            onClick={togglePlay}
            className="p-2 rounded-lg bg-primary/10 text-primary hover:bg-primary hover:text-slate-950 transition-colors"
            title={isPlaying ? 'Pause (Space)' : 'Play (Space)'}
          >
            {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
          </button>

          <button
            onClick={() => seekRelative(-5)}
            className="p-1.5 rounded text-muted hover:text-text hover:bg-card transition-colors font-mono text-xs"
            title="Back 5s (J)"
          >
            -5s
          </button>
          <button
            onClick={() => seekRelative(5)}
            className="p-1.5 rounded text-muted hover:text-text hover:bg-card transition-colors font-mono text-xs"
            title="Forward 5s (L)"
          >
            +5s
          </button>

          <span className="font-mono text-xs text-text tabular-nums ml-2">
            {formatTimeHMS(currentTime)} / {formatTimeHMS(duration)}
          </span>

          {activeTab === 'source' && onAddMomentAtTime && (
            <button
              onClick={() => onAddMomentAtTime(currentTime)}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 text-xs font-semibold hover:bg-emerald-500/25 transition-all ml-2"
              title={`Add highlight moment at ${formatTimeHMS(currentTime)}`}
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add at current time ({formatTimeHMS(currentTime)})</span>
            </button>
          )}

          <div className="flex-1" />

          <button
            onClick={() => {
              if (videoRef.current) {
                videoRef.current.muted = !isMuted;
                setIsMuted(!isMuted);
              }
            }}
            className="p-1.5 rounded text-muted hover:text-text hover:bg-card transition-colors"
          >
            {isMuted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
          </button>

          <button
            onClick={() => videoRef.current?.requestFullscreen()}
            className="p-1.5 rounded text-muted hover:text-text hover:bg-card transition-colors"
          >
            <Maximize className="w-4 h-4" />
          </button>
        </div>

        {/* Chapter Markers in Reel Mode */}
        {activeTab === 'reel' && selectedWindows.length > 0 && (
          <div className="flex items-center gap-1.5 overflow-x-auto pt-1 pb-0.5 scrollbar-thin">
            <span className="text-[11px] font-semibold text-muted uppercase tracking-wider shrink-0 mr-1">
              Chapters:
            </span>
            {selectedWindows.map((w, idx) => {
              const offset = w.reel_offset ?? 0;
              const isCurrent = currentTime >= offset && (idx === selectedWindows.length - 1 || currentTime < (selectedWindows[idx + 1].reel_offset ?? 999999));
              return (
                <button
                  key={idx}
                  onClick={() => {
                    if (videoRef.current) {
                      videoRef.current.currentTime = offset;
                    }
                  }}
                  className={cn(
                    'shrink-0 px-2.5 py-1 rounded-md text-xs font-mono transition-all flex items-center gap-1.5',
                    isCurrent
                      ? 'bg-primary/20 text-primary font-bold border border-primary/40'
                      : 'bg-card text-muted hover:text-text hover:bg-surface border border-border'
                  )}
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-primary" />
                  <span>#{idx + 1} ({formatTimeHMS(offset)})</span>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
