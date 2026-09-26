import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatTimeHMS(seconds: number): string {
  if (isNaN(seconds) || seconds < 0) return '00:00';
  const total = Math.floor(seconds);
  const hrs = Math.floor(total / 3600);
  const mins = Math.floor((total % 3600) / 60);
  const secs = total % 60;

  if (hrs > 0) {
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

export function formatDuration(seconds: number): string {
  if (isNaN(seconds) || seconds <= 0) return '0s';
  const total = Math.round(seconds);
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  if (mins > 0) {
    return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
  }
  return `${secs}s`;
}

export function formatBytes(bytes: number): string {
  if (bytes <= 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export const SENSITIVITY_LEVELS = [
  { level: 1, min_rise_db: 6.0, min_sustain_s: 4.0, label: '1 - Low', desc: 'Fewer, bigger moments' },
  { level: 2, min_rise_db: 5.0, min_sustain_s: 3.5, label: '2 - Moderate', desc: 'High crowd volume' },
  { level: 3, min_rise_db: 4.0, min_sustain_s: 3.0, label: '3 - Standard', desc: 'Balanced broadcast default' },
  { level: 4, min_rise_db: 3.0, min_sustain_s: 2.5, label: '4 - Dynamic', desc: 'Chances and commentary rises' },
  { level: 5, min_rise_db: 3.0, min_sustain_s: 2.0, label: '5 - Maximum', desc: 'Captures all crowd excitement' },
];

export function sensitivityToParams(level: number): { min_rise_db: number; min_sustain_s: number } {
  const match = SENSITIVITY_LEVELS.find((s) => s.level === level) || SENSITIVITY_LEVELS[2];
  return { min_rise_db: match.min_rise_db, min_sustain_s: match.min_sustain_s };
}

export function paramsToSensitivity(rise: number, sustain: number): number {
  let closest = 3;
  let minDiff = Infinity;
  for (const item of SENSITIVITY_LEVELS) {
    const diff = Math.abs(item.min_rise_db - rise) * 2 + Math.abs(item.min_sustain_s - sustain);
    if (diff < minDiff) {
      minDiff = diff;
      closest = item.level;
    }
  }
  return closest;
}

export interface WindowTimeItem {
  start: number;
  end: number;
  selected?: boolean;
}

/**
 * Calculates the starting offset in the concatenated reel for each selected window.
 * Non-selected windows get null.
 */
export function calculateReelOffsets(windows: WindowTimeItem[]): (number | null)[] {
  let currentOffset = 0;
  return windows.map((w) => {
    if (w.selected !== false) {
      const offset = currentOffset;
      const duration = Math.max(0, w.end - w.start);
      currentOffset += duration;
      return offset;
    }
    return null;
  });
}

/**
 * Calculates total selected count, total selected duration, and progress towards target duration cap.
 */
export function calculateSelectionTotals(
  windows: WindowTimeItem[],
  targetDurationCap: number = 0
): { count: number; totalDuration: number; capPercent: number } {
  let count = 0;
  let totalDuration = 0;

  for (const w of windows) {
    if (w.selected !== false) {
      count++;
      totalDuration += Math.max(0, w.end - w.start);
    }
  }

  const capPercent = targetDurationCap > 0 ? Math.min(100, (totalDuration / targetDurationCap) * 100) : 100;

  return {
    count,
    totalDuration,
    capPercent,
  };
}

