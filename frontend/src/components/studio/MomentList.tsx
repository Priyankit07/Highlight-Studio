import React, { useState, useMemo } from 'react';
import { WindowItem, SuggestionItem } from '../../types';
import { formatTimeHMS, formatDuration, cn } from '../../lib/utils';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Toggle } from '../ui/Toggle';
import {
  Sparkles,
  ArrowUpDown,
  CheckSquare,
  Square,
  Play,
  Clock,
  Tag,
  AlertTriangle,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Flame,
  Plus,
} from 'lucide-react';

export interface MomentListProps {
  windows: WindowItem[];
  suggestions?: SuggestionItem[];
  targetDuration: number;
  focusedIndex: number;
  onSelectMoment: (index: number) => void;
  onToggleInclude: (index: number) => void;
  onUpdateWindow: (index: number, start: number, end: number) => void;
  onUpdateTag: (index: number, tag?: 'Goal' | 'Chance' | 'Card' | 'Other', note?: string) => void;
  onBulkSelect: (mode: 'all' | 'top5' | 'clear') => void;
  onTryMoreSensitive?: () => void;
  onPreviewSource?: (index: number) => void;
  onAddSuggestion?: (suggestion: SuggestionItem) => void;
}

export const MomentList: React.FC<MomentListProps> = ({
  windows,
  suggestions = [],
  targetDuration,
  focusedIndex,
  onSelectMoment,
  onToggleInclude,
  onUpdateWindow,
  onUpdateTag,
  onBulkSelect,
  onTryMoreSensitive,
  onPreviewSource,
  onAddSuggestion,
}) => {
  const [sortBy, setSortBy] = useState<'time' | 'intensity'>('time');
  const [showPossibleMoments, setShowPossibleMoments] = useState(false);

  // Compute selected totals
  const selectedWindows = useMemo(() => windows.filter((w) => w.selected), [windows]);
  const totalSelectedSeconds = useMemo(
    () => selectedWindows.reduce((acc, w) => acc + w.duration, 0),
    [selectedWindows]
  );

  // Maximum score for intensity normalization (1 to 5 bars)
  const maxScore = useMemo(
    () => Math.max(1, ...windows.map((w) => w.score)),
    [windows]
  );

  // Sorted indices mapping
  const sortedIndices = useMemo(() => {
    const indices = windows.map((_, i) => i);
    if (sortBy === 'intensity') {
      indices.sort((a, b) => windows[b].score - windows[a].score);
    } else {
      indices.sort((a, b) => windows[a].start - windows[b].start);
    }
    return indices;
  }, [windows, sortBy]);

  if (windows.length === 0) {
    return (
      <div className="bg-surface border border-border rounded-xl p-8 flex flex-col items-center justify-center text-center gap-4 shadow-sm">
        <div className="w-12 h-12 rounded-full bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
          <AlertTriangle className="w-6 h-6" />
        </div>
        <div>
          <h4 className="text-base font-bold text-text">No Crowd Peaks Detected</h4>
          <p className="text-xs text-muted max-w-sm mt-1 leading-relaxed">
            The broadcast crowd audio might be subdued, or the current detection thresholds are too conservative for this match acoustics.
          </p>
        </div>

        {onTryMoreSensitive && (
          <Button onClick={onTryMoreSensitive} variant="primary" size="sm" className="gap-2 mt-2">
            <Sparkles className="w-4 h-4" />
            <span>Try More Sensitive Detection</span>
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="bg-surface border border-border rounded-xl flex flex-col h-full shadow-md overflow-hidden">
      {/* Header with summary and bulk actions */}
      <div className="p-4 bg-card/60 border-b border-border space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-text uppercase tracking-wider">Candidate Moments</h3>
              <Badge variant="accent">{windows.length} found</Badge>
            </div>
            <p className="text-xs text-muted font-mono mt-0.5">
              Selected: <span className="text-primary font-semibold">{selectedWindows.length}</span> ({formatTimeHMS(totalSelectedSeconds)}
              {targetDuration > 0 ? ` of ${formatTimeHMS(targetDuration)} cap` : ''})
            </p>
          </div>

          {/* Sort Switcher */}
          <button
            onClick={() => setSortBy(sortBy === 'time' ? 'intensity' : 'time')}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-surface border border-border text-xs text-muted hover:text-text hover:border-accent/40 transition-colors font-medium"
            title="Toggle sort order"
          >
            <ArrowUpDown className="w-3.5 h-3.5" />
            <span>{sortBy === 'time' ? 'Chronological' : 'By Intensity'}</span>
          </button>
        </div>

        {/* Bulk Action Buttons */}
        <div className="flex items-center gap-2 pt-1 border-t border-border/40">
          <button
            onClick={() => onBulkSelect('all')}
            className="text-[11px] text-muted hover:text-text transition-colors flex items-center gap-1 font-medium"
          >
            <CheckSquare className="w-3 h-3" />
            <span>Select all</span>
          </button>
          <span className="text-border">•</span>
          <button
            onClick={() => onBulkSelect('top5')}
            className="text-[11px] text-muted hover:text-text transition-colors flex items-center gap-1 font-medium"
          >
            <Flame className="w-3 h-3 text-amber-400" />
            <span>Top 5 only</span>
          </button>
          <span className="text-border">•</span>
          <button
            onClick={() => onBulkSelect('clear')}
            className="text-[11px] text-muted hover:text-text transition-colors flex items-center gap-1 font-medium"
          >
            <Square className="w-3 h-3" />
            <span>Clear</span>
          </button>
        </div>
      </div>

      {/* Scrollable Moments List */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2.5 max-h-[580px]">
        {sortedIndices.map((originalIdx) => {
          const w = windows[originalIdx];
          const isFocused = originalIdx === focusedIndex;

          // Normalized intensity 1 to 5 bars
          const intensityScore = Math.max(1, Math.min(5, Math.ceil((w.score / maxScore) * 5)));

          return (
            <div
              key={originalIdx}
              onClick={() => onSelectMoment(originalIdx)}
              className={cn(
                'group relative rounded-xl border p-3 transition-all cursor-pointer flex flex-col gap-2.5',
                w.selected
                  ? isFocused
                    ? 'bg-emerald-950/20 border-primary ring-1 ring-primary/40 shadow-sm'
                    : 'bg-surface border-border hover:border-border/80'
                  : 'bg-card/40 border-border/60 opacity-70 hover:opacity-100 hover:bg-card'
              )}
            >
              {/* Row 1: Thumbnail, Timecodes, Include Switch */}
              <div className="flex items-start gap-3">
                {/* Thumbnail Preview */}
                <div className="w-20 h-14 bg-black rounded-lg overflow-hidden border border-border shrink-0 relative">
                  {w.thumb_url ? (
                    <img
                      src={w.thumb_url}
                      alt="Moment frame"
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-muted text-xs font-mono">
                      {formatTimeHMS(w.peak_time)}
                    </div>
                  )}

                  {/* Intensity Bars Overlay */}
                  <div className="absolute bottom-1 right-1 flex items-end gap-0.5 bg-black/70 px-1 py-0.5 rounded">
                    {[1, 2, 3, 4, 5].map((bar) => (
                      <span
                        key={bar}
                        className={cn(
                          'w-1 rounded-sm transition-all',
                          bar <= intensityScore ? 'bg-primary' : 'bg-slate-600',
                          bar === 1 ? 'h-1' : bar === 2 ? 'h-1.5' : bar === 3 ? 'h-2' : bar === 4 ? 'h-2.5' : 'h-3'
                        )}
                      />
                    ))}
                  </div>
                </div>

                {/* Details */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 font-mono text-xs font-bold text-text">
                      <span>#{originalIdx + 1}</span>
                      <span className="text-muted font-normal">•</span>
                      <span>{w.start_hms} → {w.end_hms}</span>
                    </div>

                    {/* Include Switch */}
                    <div onClick={(e) => e.stopPropagation()}>
                      <Toggle
                        checked={w.selected}
                        onChange={() => onToggleInclude(originalIdx)}
                      />
                    </div>
                  </div>

                  <div className="flex items-center gap-2 mt-1 text-[11px] text-muted font-mono flex-wrap">
                    <span>Duration: {formatDuration(w.duration)}</span>
                    {w.spike_count > 1 && (
                      <span className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30 text-[10px]">
                        Merged x{w.spike_count}
                      </span>
                    )}
                    {w.source === 'manual' && (
                      <span className="px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-400 border border-sky-500/30 text-[10px] font-semibold">
                        Manual
                      </span>
                    )}
                    {!w.selected && w.drop_reason && (
                      <span className="px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/30 text-[10px] font-mono">
                        {w.drop_reason === 'over_length_cap'
                          ? 'Over length cap'
                          : w.drop_reason === 'top_k'
                          ? 'Top K'
                          : w.drop_reason === 'below_min_score'
                          ? 'Below min score'
                          : w.drop_reason}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Cropped to max_clip_s warning & Restore full span */}
              {w.is_cropped && w.original_start !== undefined && w.original_end !== undefined && (
                <div
                  className="p-2 rounded-lg bg-amber-500/10 border border-amber-500/30 flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 text-xs"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="flex items-center gap-1.5 text-amber-300 text-[11px] leading-tight">
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                    <span>cropped around the loudest peak; the moment you want may be outside</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => onUpdateWindow(originalIdx, w.original_start!, w.original_end!)}
                    className="px-2 py-0.5 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 border border-amber-500/40 text-[11px] font-semibold whitespace-nowrap self-start sm:self-auto transition-colors"
                  >
                    Restore full span
                  </button>
                </div>
              )}

              {/* Row 2: Manual Trimming Buttons & Tag Controls */}
              <div
                className="pt-2 border-t border-border/40 flex items-center justify-between gap-2 text-xs"
                onClick={(e) => e.stopPropagation()}
              >
                {/* Trim Buttons */}
                <div className="flex items-center gap-1 font-mono text-[11px]">
                  <span className="text-muted mr-1">Trim:</span>
                  <button
                    onClick={() => onUpdateWindow(originalIdx, Math.max(0, w.start - 0.5), w.end)}
                    className="px-1.5 py-0.5 rounded bg-card hover:bg-surface border border-border text-text"
                    title="Expand start by 0.5s"
                  >
                    -0.5s
                  </button>
                  <button
                    onClick={() => onUpdateWindow(originalIdx, Math.min(w.end - 2.0, w.start + 0.5), w.end)}
                    className="px-1.5 py-0.5 rounded bg-card hover:bg-surface border border-border text-text"
                    title="Shorten start by 0.5s"
                  >
                    +0.5s
                  </button>
                  <span className="text-muted mx-0.5">|</span>
                  <button
                    onClick={() => onUpdateWindow(originalIdx, w.start, Math.max(w.start + 2.0, w.end - 0.5))}
                    className="px-1.5 py-0.5 rounded bg-card hover:bg-surface border border-border text-text"
                    title="Shorten end by 0.5s"
                  >
                    -0.5s
                  </button>
                  <button
                    onClick={() => onUpdateWindow(originalIdx, w.start, w.end + 0.5)}
                    className="px-1.5 py-0.5 rounded bg-card hover:bg-surface border border-border text-text"
                    title="Expand end by 0.5s"
                  >
                    +0.5s
                  </button>
                </div>

                {/* User Tag Selector & Preview Button */}
                <div className="flex items-center gap-1.5">
                  <select
                    value={w.tag || ''}
                    onChange={(e) => onUpdateTag(originalIdx, e.target.value as any, w.note)}
                    className="bg-card border border-border text-text rounded px-1.5 py-0.5 text-[11px] focus:outline-none focus:border-accent"
                  >
                    <option value="">Tag moment...</option>
                    <option value="Goal">⚽ Goal</option>
                    <option value="Chance">⚡ Chance</option>
                    <option value="Card">🟨 Card</option>
                    <option value="Other">📌 Other</option>
                  </select>

                  {onPreviewSource && (
                    <button
                      onClick={() => onPreviewSource(originalIdx)}
                      className="p-1 rounded bg-card text-accent hover:bg-surface border border-border"
                      title="Preview this moment in source player"
                    >
                      <Play className="w-3 h-3" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Collapsible Possible Moments Panel */}
      {suggestions && suggestions.length > 0 && (
        <div className="border-t border-border bg-card/40 p-3 space-y-2">
          <button
            type="button"
            onClick={() => setShowPossibleMoments(!showPossibleMoments)}
            className="w-full flex items-center justify-between text-xs font-bold text-muted hover:text-text uppercase tracking-wider"
          >
            <div className="flex items-center gap-2">
              <Sparkles className="w-3.5 h-3.5 text-purple-400" />
              <span>Possible Moments</span>
              <span className="px-1.5 py-0.2 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 text-[10px] font-mono font-bold">
                {suggestions.length}
              </span>
            </div>
            {showPossibleMoments ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>

          {showPossibleMoments && (
            <div className="space-y-2 pt-1 max-h-48 overflow-y-auto">
              {suggestions.map((s, idx) => (
                <div
                  key={idx}
                  className="p-2 rounded-lg bg-surface border border-purple-500/30 flex items-center justify-between gap-2 text-xs"
                >
                  <div>
                    <div className="font-mono text-xs text-text font-semibold">
                      {s.start_hms} → {s.end_hms} ({formatDuration(s.duration)})
                    </div>
                    <div className="text-[10px] text-purple-400 font-mono">
                      +{s.peak_rise_db} dB rise • sub-threshold
                    </div>
                  </div>

                  {onAddSuggestion && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="gap-1 text-xs py-1 border-purple-500/40 text-purple-300 hover:bg-purple-500/20"
                      onClick={() => onAddSuggestion(s)}
                    >
                      <Plus className="w-3 h-3" />
                      <span>Add</span>
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Footer Notice on Audio Detection */}
      <div className="px-4 py-2 bg-card/40 border-t border-border text-[10px] text-muted leading-tight">
        * Crowd peaks detected from audio excitement analysis. Custom tags are user-defined.
      </div>
    </div>
  );
};
