import React, { useRef, useState, useEffect, useMemo, useCallback } from 'react';
import { scaleLinear } from 'd3-scale';
import { EnvelopeData, WindowItem, SuggestionItem, LabelItem } from '../../types';
import { formatTimeHMS, cn } from '../../lib/utils';
import { ZoomIn, ZoomOut, Maximize2, Activity, Layers, PlusCircle, BookmarkCheck, BookmarkX } from 'lucide-react';

export interface TimelineProps {
  envelope: EnvelopeData;
  duration: number;
  windows: WindowItem[];
  suggestions?: SuggestionItem[];
  labels?: LabelItem[];
  skipStartSeconds: number;
  minRiseDb: number;
  focusedIndex: number;
  onSelectMoment: (index: number) => void;
  onUpdateWindow: (index: number, start: number, end: number) => void;
  onAddMomentAtTime?: (time: number) => void;
  onAddSuggestion?: (suggestion: SuggestionItem) => void;
  currentTime?: number;
  onSeek?: (time: number) => void;
}

export const Timeline: React.FC<TimelineProps> = ({
  envelope,
  duration,
  windows,
  suggestions = [],
  labels = [],
  skipStartSeconds,
  minRiseDb,
  focusedIndex,
  onSelectMoment,
  onUpdateWindow,
  onAddMomentAtTime,
  onAddSuggestion,
  currentTime = 0,
  onSeek,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const minimapCanvasRef = useRef<HTMLCanvasElement>(null);

  const [viewMode, setViewMode] = useState<'db' | 'rise'>('db');
  const [zoomRange, setZoomRange] = useState<[number, number]>([0, duration || 100]);
  const [hoverData, setHoverData] = useState<{
    x: number;
    time: number;
    db: number;
    rise: number;
    label?: { text: string; caught: boolean; time: number };
    suggestion?: SuggestionItem;
  } | null>(null);

  // Dragging state for trimming window edges
  const [draggingHandle, setDraggingHandle] = useState<{
    windowIndex: number;
    edge: 'start' | 'end';
    initialVal: number;
  } | null>(null);

  // Reset zoom when duration changes
  useEffect(() => {
    if (duration > 0 && (zoomRange[1] <= 0 || zoomRange[1] > duration * 1.5)) {
      setZoomRange([0, duration]);
    }
  }, [duration]);

  // Compute Scales
  const [zoomStart, zoomEnd] = zoomRange;
  const visibleDuration = Math.max(5, zoomEnd - zoomStart);

  // Main Canvas Rendering
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !envelope || envelope.t.length === 0) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const xScale = scaleLinear().domain([zoomStart, zoomEnd]).range([0, width]);

    // Y Scale depending on viewMode
    let yMin = -80;
    let yMax = 0;
    if (viewMode === 'rise') {
      yMin = -5;
      yMax = Math.max(15, ...envelope.rise);
    } else {
      yMin = Math.min(-60, ...(envelope.db && envelope.db.length > 0 ? envelope.db : [-70]));
      yMax = Math.max(-5, ...(envelope.db && envelope.db.length > 0 ? envelope.db : [-5]));
    }
    const yScale = scaleLinear().domain([yMin, yMax]).range([height - 20, 15]);

    // 1. Draw Grid Lines
    ctx.strokeStyle = 'rgba(36, 50, 71, 0.4)';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);

    // Time intervals
    const step = visibleDuration > 300 ? 60 : visibleDuration > 60 ? 15 : 5;
    const firstTick = Math.ceil(zoomStart / step) * step;
    ctx.fillStyle = '#64748b';
    ctx.font = '10px "JetBrains Mono", monospace';
    ctx.textAlign = 'center';

    for (let t = firstTick; t <= zoomEnd; t += step) {
      const x = xScale(t);
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height - 18);
      ctx.stroke();
      ctx.fillText(formatTimeHMS(t), x, height - 4);
    }

    // 2. Draw Skip Start Hatched Region
    if (skipStartSeconds > 0 && skipStartSeconds > zoomStart) {
      const xStart = xScale(0);
      const xEnd = xScale(Math.min(skipStartSeconds, zoomEnd));
      ctx.fillStyle = 'rgba(239, 68, 68, 0.12)';
      ctx.fillRect(xStart, 0, xEnd - xStart, height - 20);

      // Hatch lines
      ctx.strokeStyle = 'rgba(239, 68, 68, 0.25)';
      ctx.setLineDash([3, 3]);
      for (let x = xStart; x < xEnd; x += 12) {
        ctx.beginPath();
        ctx.moveTo(x, height - 20);
        ctx.lineTo(x + 12, 0);
        ctx.stroke();
      }
    }

    // 3a. Draw Suggestion Bands (Possible Moments - Dashed Outlines)
    ctx.setLineDash([5, 4]);
    suggestions.forEach((sugg) => {
      if (sugg.end < zoomStart || sugg.start > zoomEnd) return;
      const x1 = Math.max(0, xScale(sugg.start));
      const x2 = Math.min(width, xScale(sugg.end));
      const bandWidth = Math.max(2, x2 - x1);

      ctx.fillStyle = 'rgba(192, 132, 252, 0.12)';
      ctx.fillRect(x1, 0, bandWidth, height - 20);

      ctx.strokeStyle = '#c084fc'; // purple-400
      ctx.lineWidth = 1.5;
      ctx.strokeRect(x1, 0, bandWidth, height - 20);

      // "+ Add" badge indicator at top if wide enough
      if (bandWidth >= 30) {
        ctx.setLineDash([]);
        ctx.fillStyle = 'rgba(147, 51, 234, 0.9)';
        const badgeW = Math.min(44, bandWidth - 4);
        const badgeX = x1 + (bandWidth - badgeW) / 2;
        ctx.beginPath();
        if (ctx.roundRect) {
          ctx.roundRect(badgeX, 4, badgeW, 16, 4);
        } else {
          ctx.rect(badgeX, 4, badgeW, 16);
        }
        ctx.fill();

        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 9px system-ui, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('+ Add', badgeX + badgeW / 2, 15);
        ctx.setLineDash([5, 4]);
      }
    });
    ctx.setLineDash([]);

    // 3b. Draw Window Bands
    windows.forEach((w, idx) => {
      if (w.end < zoomStart || w.start > zoomEnd) return;
      const x1 = Math.max(0, xScale(w.start));
      const x2 = Math.min(width, xScale(w.end));
      const bandWidth = Math.max(2, x2 - x1);

      if (w.selected) {
        ctx.fillStyle = idx === focusedIndex ? 'rgba(16, 185, 129, 0.38)' : 'rgba(16, 185, 129, 0.22)';
        ctx.fillRect(x1, 0, bandWidth, height - 20);
        ctx.strokeStyle = idx === focusedIndex ? '#34d399' : '#10b981';
        ctx.lineWidth = idx === focusedIndex ? 2 : 1;
        ctx.strokeRect(x1, 0, bandWidth, height - 20);
      } else {
        ctx.fillStyle = idx === focusedIndex ? 'rgba(100, 116, 139, 0.3)' : 'rgba(100, 116, 139, 0.15)';
        ctx.fillRect(x1, 0, bandWidth, height - 20);
        ctx.strokeStyle = '#64748b';
        ctx.lineWidth = 1;
        ctx.strokeRect(x1, 0, bandWidth, height - 20);
      }

      // Mark Peak Point
      if (w.peak_time >= zoomStart && w.peak_time <= zoomEnd) {
        const xPeak = xScale(w.peak_time);
        ctx.fillStyle = w.selected ? '#34d399' : '#94a3b8';
        ctx.beginPath();
        ctx.arc(xPeak, 18, 3.5, 0, 2 * Math.PI);
        ctx.fill();
      }

      // Show small badge for manual or cropped windows
      if (w.source === 'manual') {
        ctx.fillStyle = '#38bdf8';
        ctx.font = 'bold 8px system-ui, sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText('MANUAL', x1 + 4, height - 26);
      } else if (w.is_cropped) {
        ctx.fillStyle = '#f59e0b';
        ctx.font = 'bold 8px system-ui, sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText('CROPPED', x1 + 4, height - 26);
      }
    });

    // 4. Draw Audio Envelope Area Fill & Stroke
    const pts = envelope.t.length;
    const activeCurve = viewMode === 'rise' ? envelope.rise : envelope.db;

    if (pts > 1) {
      // Area gradient
      const gradient = ctx.createLinearGradient(0, 0, 0, height);
      if (viewMode === 'rise') {
        gradient.addColorStop(0, 'rgba(168, 85, 247, 0.45)');
        gradient.addColorStop(1, 'rgba(168, 85, 247, 0.02)');
      } else {
        gradient.addColorStop(0, 'rgba(56, 189, 248, 0.45)');
        gradient.addColorStop(1, 'rgba(56, 189, 248, 0.02)');
      }

      ctx.beginPath();
      let started = false;
      let firstX = 0;
      let lastX = 0;

      for (let i = 0; i < pts; i++) {
        const t = envelope.t[i];
        if (t < zoomStart - 2 || t > zoomEnd + 2) continue;
        const x = xScale(t);
        const y = yScale(activeCurve[i]);

        if (!started) {
          ctx.moveTo(x, height - 20);
          ctx.lineTo(x, y);
          firstX = x;
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
        lastX = x;
      }

      if (started) {
        ctx.lineTo(lastX, height - 20);
        ctx.closePath();
        ctx.fillStyle = gradient;
        ctx.fill();
      }

      // Stroke line
      ctx.beginPath();
      started = false;
      for (let i = 0; i < pts; i++) {
        const t = envelope.t[i];
        if (t < zoomStart - 2 || t > zoomEnd + 2) continue;
        const x = xScale(t);
        const y = yScale(activeCurve[i]);
        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.strokeStyle = viewMode === 'rise' ? '#a855f7' : '#38bdf8';
      ctx.lineWidth = 1.6;
      ctx.setLineDash([]);
      ctx.stroke();

      // 5. Baseline / Threshold lines
      if (viewMode === 'db') {
        // Baseline dashed line
        ctx.beginPath();
        started = false;
        for (let i = 0; i < pts; i++) {
          const t = envelope.t[i];
          if (t < zoomStart - 2 || t > zoomEnd + 2) continue;
          const x = xScale(t);
          const y = yScale(envelope.baseline[i]);
          if (!started) {
            ctx.moveTo(x, y);
            started = true;
          } else {
            ctx.lineTo(x, y);
          }
        }
        ctx.strokeStyle = '#f59e0b';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([5, 4]);
        ctx.stroke();
      } else {
        // Threshold line in rise mode
        const yThresh = yScale(minRiseDb);
        ctx.beginPath();
        ctx.moveTo(0, yThresh);
        ctx.lineTo(width, yThresh);
        ctx.strokeStyle = '#ef4444';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 4]);
        ctx.stroke();
      }
    }

    // 6. Draw Label Pins (Ground Truth Events)
    const labelTolerance = 3.0;
    labels.forEach((lbl) => {
      if (lbl.time < zoomStart || lbl.time > zoomEnd) return;
      const x = xScale(lbl.time);
      const isCaught = windows.some(
        (w) => w.selected && (w.start - labelTolerance) <= lbl.time && lbl.time <= (w.end + labelTolerance)
      );

      // Vertical Pin Line
      ctx.beginPath();
      ctx.moveTo(x, 22);
      ctx.lineTo(x, height - 20);
      ctx.strokeStyle = isCaught ? '#10b981' : '#f43f5e';
      ctx.lineWidth = 1.8;
      ctx.setLineDash([3, 3]);
      ctx.stroke();
      ctx.setLineDash([]);

      // Pin Head Badge
      const badgeText = `${lbl.label} ${isCaught ? '✓' : '✗'}`;
      ctx.font = 'bold 9px system-ui, sans-serif';
      const textWidth = ctx.measureText(badgeText).width;
      const pad = 6;
      const boxW = Math.max(28, textWidth + pad * 2);
      const boxX = Math.max(2, Math.min(width - boxW - 2, x - boxW / 2));

      ctx.fillStyle = isCaught ? 'rgba(16, 185, 129, 0.95)' : 'rgba(244, 63, 94, 0.95)';
      ctx.strokeStyle = isCaught ? '#34d399' : '#fb7185';
      ctx.lineWidth = 1;
      ctx.beginPath();
      if (ctx.roundRect) {
        ctx.roundRect(boxX, 4, boxW, 16, 4);
      } else {
        ctx.rect(boxX, 4, boxW, 16);
      }
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = '#ffffff';
      ctx.textAlign = 'center';
      ctx.fillText(badgeText, boxX + boxW / 2, 15);

      // Pointer triangle
      ctx.beginPath();
      ctx.moveTo(x - 3, 20);
      ctx.lineTo(x + 3, 20);
      ctx.lineTo(x, 23);
      ctx.closePath();
      ctx.fillStyle = isCaught ? '#10b981' : '#f43f5e';
      ctx.fill();
    });

    // 7. Current Playhead
    if (currentTime >= zoomStart && currentTime <= zoomEnd) {
      const xPlayhead = xScale(currentTime);
      ctx.beginPath();
      ctx.moveTo(xPlayhead, 0);
      ctx.lineTo(xPlayhead, height - 20);
      ctx.strokeStyle = '#f8fafc';
      ctx.lineWidth = 1.8;
      ctx.setLineDash([]);
      ctx.stroke();

      // Top triangle
      ctx.fillStyle = '#f8fafc';
      ctx.beginPath();
      ctx.moveTo(xPlayhead - 4, 0);
      ctx.lineTo(xPlayhead + 4, 0);
      ctx.lineTo(xPlayhead, 7);
      ctx.closePath();
      ctx.fill();
    }
  }, [envelope, zoomStart, zoomEnd, viewMode, windows, suggestions, labels, focusedIndex, currentTime, skipStartSeconds, minRiseDb]);

  // Minimap Rendering
  useEffect(() => {
    const canvas = minimapCanvasRef.current;
    if (!canvas || !envelope || envelope.t.length === 0 || duration <= 0) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const xScale = scaleLinear().domain([0, duration]).range([0, width]);
    const yScale = scaleLinear().domain([-70, 0]).range([height, 0]);

    // Envelope Sparkline
    ctx.beginPath();
    const pts = envelope.t.length;
    for (let i = 0; i < pts; i++) {
      const x = xScale(envelope.t[i]);
      const y = yScale(envelope.db[i]);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.4)';
    ctx.lineWidth = 1;
    ctx.stroke();

    // Suggestions highlights on minimap
    suggestions.forEach((s) => {
      const x1 = xScale(s.start);
      const x2 = xScale(s.end);
      ctx.fillStyle = 'rgba(192, 132, 252, 0.35)';
      ctx.fillRect(x1, 0, Math.max(2, x2 - x1), height);
    });

    // Windows highlights on minimap
    windows.forEach((w) => {
      const x1 = xScale(w.start);
      const x2 = xScale(w.end);
      ctx.fillStyle = w.selected ? 'rgba(16, 185, 129, 0.5)' : 'rgba(100, 116, 139, 0.3)';
      ctx.fillRect(x1, 0, Math.max(2, x2 - x1), height);
    });

    // Label pins on minimap
    labels.forEach((lbl) => {
      const x = xScale(lbl.time);
      const isCaught = windows.some(
        (w) => w.selected && (w.start - 3.0) <= lbl.time && lbl.time <= (w.end + 3.0)
      );
      ctx.fillStyle = isCaught ? '#10b981' : '#f43f5e';
      ctx.fillRect(x - 1, 0, 2, height);
    });

    // Viewport Box
    const vx1 = xScale(zoomStart);
    const vx2 = xScale(zoomEnd);
    ctx.fillStyle = 'rgba(56, 189, 248, 0.15)';
    ctx.fillRect(vx1, 0, Math.max(4, vx2 - vx1), height);
    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 1.5;
    ctx.strokeRect(vx1, 0, Math.max(4, vx2 - vx1), height);
  }, [envelope, duration, windows, suggestions, labels, zoomStart, zoomEnd]);

  // Resize listener
  useEffect(() => {
    const updateSize = () => {
      if (containerRef.current && canvasRef.current && minimapCanvasRef.current) {
        const w = containerRef.current.clientWidth;
        canvasRef.current.width = w;
        canvasRef.current.height = 180;
        minimapCanvasRef.current.width = w;
        minimapCanvasRef.current.height = 36;
      }
    };
    updateSize();
    window.addEventListener('resize', updateSize);
    return () => window.removeEventListener('resize', updateSize);
  }, []);

  // Mouse Interaction: Hover Tooltip & Seek & Trim Handles
  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!canvasRef.current || duration <= 0) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const xScale = scaleLinear().domain([0, canvasRef.current.width]).range([zoomStart, zoomEnd]);
    const t = xScale(x);

    // If dragging a trim handle
    if (draggingHandle) {
      const { windowIndex, edge } = draggingHandle;
      const w = windows[windowIndex];
      // Snap to 0.5s
      const snappedT = Math.round(t * 2) / 2;
      if (edge === 'start') {
        const newStart = Math.max(0, Math.min(w.end - 2.0, snappedT));
        onUpdateWindow(windowIndex, newStart, w.end);
      } else {
        const newEnd = Math.min(duration, Math.max(w.start + 2.0, snappedT));
        onUpdateWindow(windowIndex, w.start, newEnd);
      }
      return;
    }

    // Find closest envelope data point
    const pts = envelope.t;
    let closestIdx = 0;
    let minD = Infinity;
    for (let i = 0; i < pts.length; i += 5) {
      const diff = Math.abs(pts[i] - t);
      if (diff < minD) {
        minD = diff;
        closestIdx = i;
      }
    }

    // Check if hovering near a label
    let hoveredLabel: { text: string; caught: boolean; time: number } | undefined;
    for (const lbl of labels) {
      const lblX = scaleLinear().domain([zoomStart, zoomEnd]).range([0, canvasRef.current.width])(lbl.time);
      if (Math.abs(x - lblX) <= 14) {
        const isCaught = windows.some(
          (w) => w.selected && (w.start - 3.0) <= lbl.time && lbl.time <= (w.end + 3.0)
        );
        hoveredLabel = { text: lbl.label, caught: isCaught, time: lbl.time };
        break;
      }
    }

    // Check if hovering over a suggestion
    const hoveredSuggestion = suggestions.find((s) => t >= s.start && t <= s.end);

    setHoverData({
      x,
      time: t,
      db: envelope.db[closestIdx] || 0,
      rise: envelope.rise[closestIdx] || 0,
      label: hoveredLabel,
      suggestion: hoveredSuggestion,
    });
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const xScale = scaleLinear().domain([0, canvasRef.current.width]).range([zoomStart, zoomEnd]);
    const t = xScale(x);

    // Check if clicking near a label pin head (seek to label)
    for (const lbl of labels) {
      const lblX = scaleLinear().domain([zoomStart, zoomEnd]).range([0, canvasRef.current.width])(lbl.time);
      if (Math.abs(x - lblX) <= 16 && y <= 26) {
        if (onSeek) onSeek(lbl.time);
        return;
      }
    }

    // Check if clicking a suggestion "+ Add" badge or band
    if (onAddSuggestion) {
      for (const sugg of suggestions) {
        if (t >= sugg.start && t <= sugg.end) {
          onAddSuggestion(sugg);
          return;
        }
      }
    }

    // Check if clicking near a window boundary handle (within 8px)
    for (let i = 0; i < windows.length; i++) {
      const w = windows[i];
      const startX = scaleLinear().domain([zoomStart, zoomEnd]).range([0, canvasRef.current.width])(w.start);
      const endX = scaleLinear().domain([zoomStart, zoomEnd]).range([0, canvasRef.current.width])(w.end);

      if (Math.abs(x - startX) <= 8) {
        setDraggingHandle({ windowIndex: i, edge: 'start', initialVal: w.start });
        onSelectMoment(i);
        return;
      }
      if (Math.abs(x - endX) <= 8) {
        setDraggingHandle({ windowIndex: i, edge: 'end', initialVal: w.end });
        onSelectMoment(i);
        return;
      }

      // Check if clicking inside band
      if (t >= w.start && t <= w.end) {
        onSelectMoment(i);
        if (onSeek) onSeek(w.start);
        return;
      }
    }

    // Clicked empty region -> seek
    if (onSeek) {
      onSeek(Math.max(0, Math.min(duration, t)));
    }
  };

  const handleDoubleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!canvasRef.current || duration <= 0 || !onAddMomentAtTime) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const xScale = scaleLinear().domain([0, canvasRef.current.width]).range([zoomStart, zoomEnd]);
    const t = Math.max(0, Math.min(duration, xScale(x)));
    onAddMomentAtTime(t);
  };

  const handleMouseUp = () => {
    setDraggingHandle(null);
  };

  const handleWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    e.preventDefault();
    const zoomFactor = e.deltaY > 0 ? 1.2 : 0.8;
    const centerTime = (zoomStart + zoomEnd) / 2;
    const newHalf = (visibleDuration * zoomFactor) / 2;
    const newStart = Math.max(0, centerTime - newHalf);
    const newEnd = Math.min(duration, centerTime + newHalf);
    if (newEnd - newStart >= 5) {
      setZoomRange([newStart, newEnd]);
    }
  };

  const zoomIn = () => {
    const center = (zoomStart + zoomEnd) / 2;
    const span = visibleDuration * 0.6;
    setZoomRange([Math.max(0, center - span / 2), Math.min(duration, center + span / 2)]);
  };

  const zoomOut = () => {
    const center = (zoomStart + zoomEnd) / 2;
    const span = visibleDuration * 1.5;
    setZoomRange([Math.max(0, center - span / 2), Math.min(duration, center + span / 2)]);
  };

  const resetZoom = () => {
    setZoomRange([0, duration]);
  };

  return (
    <div
      ref={containerRef}
      className="bg-surface border border-border rounded-xl p-4 flex flex-col gap-3 shadow-md select-none"
      onWheel={handleWheel}
      onMouseUp={handleMouseUp}
    >
      {/* Timeline Controls Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-text uppercase tracking-wider">Timeline Analysis</span>
            <span className="text-[11px] text-muted font-mono">({formatTimeHMS(duration)} total)</span>
          </div>

          <div className="flex items-center bg-card rounded-lg p-0.5 border border-border text-xs">
            <button
              onClick={() => setViewMode('db')}
              className={cn(
                'px-2.5 py-1 rounded-md transition-all font-medium',
                viewMode === 'db' ? 'bg-primary/20 text-primary font-semibold' : 'text-muted hover:text-text'
              )}
            >
              Envelope & Baseline (dB)
            </button>
            <button
              onClick={() => setViewMode('rise')}
              className={cn(
                'px-2.5 py-1 rounded-md transition-all font-medium',
                viewMode === 'rise' ? 'bg-purple-500/20 text-purple-400 font-semibold' : 'text-muted hover:text-text'
              )}
            >
              Rise Above Baseline
            </button>
          </div>
        </div>

        {/* Zoom Buttons */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={zoomIn}
            className="p-1.5 rounded-lg bg-card border border-border text-muted hover:text-text hover:bg-card/80 transition-colors"
            title="Zoom in"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={zoomOut}
            className="p-1.5 rounded-lg bg-card border border-border text-muted hover:text-text hover:bg-card/80 transition-colors"
            title="Zoom out"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={resetZoom}
            className="p-1.5 rounded-lg bg-card border border-border text-muted hover:text-text hover:bg-card/80 transition-colors"
            title="Fit to match length"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Main Canvas with Interactive Hover */}
      <div className="relative w-full h-[180px] bg-card/40 rounded-lg overflow-hidden border border-border cursor-crosshair">
        <canvas
          ref={canvasRef}
          onMouseMove={handleMouseMove}
          onMouseDown={handleMouseDown}
          onDoubleClick={handleDoubleClick}
          onMouseLeave={() => setHoverData(null)}
          className="w-full h-full block"
        />

        {/* Hover Crosshair Tooltip */}
        {hoverData && (
          <div
            className="absolute top-2 pointer-events-none transform -translate-x-1/2 bg-black/90 backdrop-blur-md px-2.5 py-1.5 rounded-lg border border-border text-xs font-mono shadow-lg flex items-center gap-2 z-10 whitespace-nowrap"
            style={{ left: hoverData.x }}
          >
            <span className="text-text font-bold">{formatTimeHMS(hoverData.time)}</span>
            <span className="text-sky-400">{hoverData.db.toFixed(1)} dB</span>
            <span className="text-purple-400">+{hoverData.rise.toFixed(1)} dB rise</span>
            {hoverData.label && (
              <span
                className={cn(
                  'px-1.5 py-0.5 rounded text-[10px] font-bold font-sans flex items-center gap-1',
                  hoverData.label.caught
                    ? 'bg-emerald-500/25 text-emerald-300 border border-emerald-500/40'
                    : 'bg-rose-500/25 text-rose-300 border border-rose-500/40'
                )}
              >
                {hoverData.label.caught ? 'CAUGHT' : 'MISSED'}: {hoverData.label.text}
              </span>
            )}
            {hoverData.suggestion && (
              <span className="px-1.5 py-0.5 rounded text-[10px] font-bold font-sans bg-purple-500/25 text-purple-300 border border-purple-500/40">
                Possible Moment (Click to Add)
              </span>
            )}
          </div>
        )}
      </div>

      {/* Minimap Overview */}
      <div className="space-y-1">
        <div className="relative w-full h-[36px] bg-card/60 rounded-md overflow-hidden border border-border/80 cursor-pointer">
          <canvas
            ref={minimapCanvasRef}
            onClick={(e) => {
              if (!minimapCanvasRef.current) return;
              const rect = minimapCanvasRef.current.getBoundingClientRect();
              const clickX = e.clientX - rect.left;
              const t = (clickX / minimapCanvasRef.current.width) * duration;
              const half = visibleDuration / 2;
              setZoomRange([Math.max(0, t - half), Math.min(duration, t + half)]);
            }}
            className="w-full h-full block"
          />
        </div>
        <div className="flex items-center justify-between text-[10px] text-muted font-mono">
          <span>00:00</span>
          <span>Click minimap to pan • Double-click timeline to add moment • Click dashed outlines to add possible moments</span>
          <span>{formatTimeHMS(duration)}</span>
        </div>
      </div>
    </div>
  );
};
