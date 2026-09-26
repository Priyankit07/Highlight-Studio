import React, { useState } from 'react';
import { Download, Film, Sparkles, Check, ChevronDown, Clock, History } from 'lucide-react';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';
import { RenderRecord } from '../../types';
import { formatDuration, formatTimeHMS } from '../../lib/utils';

export interface RenderBarProps {
  jobId: string;
  hasUnrenderedChanges: boolean;
  isRendering: boolean;
  renderProgressText?: string;
  renders: RenderRecord[];
  activeRenderId: string;
  onSelectRender: (renderId: string) => void;
  onRenderReel: () => void;
  selectedMomentsCount: number;
  totalSelectedDuration: number;
}

export const RenderBar: React.FC<RenderBarProps> = ({
  jobId,
  hasUnrenderedChanges,
  isRendering,
  renderProgressText,
  renders,
  activeRenderId,
  onSelectRender,
  onRenderReel,
  selectedMomentsCount,
  totalSelectedDuration,
}) => {
  const [showDownloads, setShowDownloads] = useState(false);
  const [showVersions, setShowVersions] = useState(false);

  const activeRender = renders.find((r) => r.id === activeRenderId);

  return (
    <div className="sticky bottom-0 z-30 bg-surface/95 backdrop-blur-md border-t border-border px-6 py-3.5 shadow-2xl transition-all">
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-4 flex-wrap">
        {/* Left: Summary & Unrendered Changes Status */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted uppercase tracking-wider font-semibold">Selection:</span>
            <span className="font-mono text-sm font-bold text-text">
              {selectedMomentsCount} moments ({formatTimeHMS(totalSelectedDuration)})
            </span>
          </div>

          {hasUnrenderedChanges && (
            <Badge variant="warning" className="animate-pulse">
              Unrendered Changes
            </Badge>
          )}

          {isRendering && (
            <Badge variant="accent" className="flex items-center gap-1.5 font-mono">
              <Sparkles className="w-3 h-3 animate-spin" />
              <span>{renderProgressText || 'Rendering reel...'}</span>
            </Badge>
          )}
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-3">
          {/* Versions Dropdown */}
          {renders.length > 1 && (
            <div className="relative">
              <button
                onClick={() => {
                  setShowVersions(!showVersions);
                  setShowDownloads(false);
                }}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-card border border-border text-xs text-muted hover:text-text transition-colors font-medium"
              >
                <History className="w-3.5 h-3.5" />
                <span>Version: {activeRenderId === 'default' ? 'v1 (Initial)' : `v${renders.length - renders.findIndex((r) => r.id === activeRenderId)}`}</span>
                <ChevronDown className="w-3 h-3 ml-1" />
              </button>

              {showVersions && (
                <div className="absolute bottom-full right-0 mb-2 w-64 bg-surface border border-border rounded-xl shadow-xl p-2 z-50 space-y-1">
                  <div className="text-[11px] font-semibold text-muted px-2 py-1 uppercase tracking-wider">
                    Render Versions
                  </div>
                  {renders.map((r, i) => (
                    <button
                      key={r.id}
                      onClick={() => {
                        onSelectRender(r.id);
                        setShowVersions(false);
                      }}
                      className="w-full flex items-center justify-between p-2 rounded-lg hover:bg-card text-left text-xs text-text transition-colors"
                    >
                      <div>
                        <div className="font-bold">
                          {r.id === 'default' ? 'Initial Reel (v1)' : `Custom Render (${r.clip_count} clips)`}
                        </div>
                        <div className="text-[10px] text-muted font-mono">
                          {formatDuration(r.duration_s)} • {new Date(r.created_at).toLocaleTimeString()}
                        </div>
                      </div>
                      {r.id === activeRenderId && <Check className="w-4 h-4 text-primary" />}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Downloads Dropdown */}
          <div className="relative">
            <Button
              variant="secondary"
              size="md"
              onClick={() => {
                setShowDownloads(!showDownloads);
                setShowVersions(false);
              }}
              className="gap-2 text-xs"
            >
              <Download className="w-4 h-4" />
              <span>Downloads</span>
              <ChevronDown className="w-3.5 h-3.5" />
            </Button>

            {showDownloads && (
              <div className="absolute bottom-full right-0 mb-2 w-56 bg-surface border border-border rounded-xl shadow-xl p-2 z-50 space-y-1 text-xs">
                <div className="text-[11px] font-semibold text-muted px-2 py-1 uppercase tracking-wider">
                  Export Files
                </div>
                <a
                  href={`/api/jobs/${jobId}/media/renders/${activeRenderId}/highlights.mp4?download=1`}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-card text-text transition-colors"
                  download
                >
                  <Film className="w-4 h-4 text-primary" />
                  <span>Highlight Reel (MP4)</span>
                </a>
                <a
                  href={`/api/jobs/${jobId}/media/windows.json?download=1`}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-card text-text transition-colors"
                  download
                >
                  <span className="font-mono text-accent text-xs">{}</span>
                  <span>Manifest (JSON)</span>
                </a>
                <a
                  href={`/api/jobs/${jobId}/media/windows.csv?download=1`}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-card text-text transition-colors"
                  download
                >
                  <span className="font-mono text-accent text-xs">CSV</span>
                  <span>Manifest (CSV)</span>
                </a>
                <a
                  href={`/api/jobs/${jobId}/media/debug.png?download=1`}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-card text-text transition-colors"
                  download
                >
                  <span className="font-mono text-purple-400 text-xs">PNG</span>
                  <span>Analysis Plot (PNG)</span>
                </a>
              </div>
            )}
          </div>

          {/* Primary Render Button */}
          <Button
            variant="primary"
            size="md"
            onClick={onRenderReel}
            isLoading={isRendering}
            disabled={selectedMomentsCount === 0}
            className="gap-2 font-bold px-6"
          >
            <Sparkles className="w-4 h-4" />
            <span>Render Reel</span>
          </Button>
        </div>
      </div>
    </div>
  );
};
