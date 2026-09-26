import { describe, it, expect } from 'vitest';
import {
  formatTimeHMS,
  formatDuration,
  formatBytes,
  sensitivityToParams,
  paramsToSensitivity,
  calculateReelOffsets,
  calculateSelectionTotals,
  SENSITIVITY_LEVELS,
} from '../lib/utils';

describe('formatTimeHMS', () => {
  it('formats MM:SS correctly for times under an hour', () => {
    expect(formatTimeHMS(0)).toBe('00:00');
    expect(formatTimeHMS(5)).toBe('00:05');
    expect(formatTimeHMS(65)).toBe('01:05');
    expect(formatTimeHMS(599)).toBe('09:59');
  });

  it('formats HH:MM:SS for times over an hour', () => {
    expect(formatTimeHMS(3600)).toBe('01:00:00');
    expect(formatTimeHMS(3665)).toBe('01:01:05');
    expect(formatTimeHMS(7325)).toBe('02:02:05');
  });

  it('handles negative or NaN inputs safely', () => {
    expect(formatTimeHMS(-10)).toBe('00:00');
    expect(formatTimeHMS(NaN)).toBe('00:00');
  });
});

describe('formatDuration', () => {
  it('formats short durations in seconds', () => {
    expect(formatDuration(15)).toBe('15s');
    expect(formatDuration(45.4)).toBe('45s');
  });

  it('formats durations in minutes and seconds', () => {
    expect(formatDuration(60)).toBe('1m');
    expect(formatDuration(125)).toBe('2m 5s');
  });

  it('handles zero or negative duration safely', () => {
    expect(formatDuration(0)).toBe('0s');
    expect(formatDuration(-5)).toBe('0s');
  });
});

describe('formatBytes', () => {
  it('formats byte sizes correctly', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(500)).toBe('500 B');
    expect(formatBytes(1024)).toBe('1 KB');
    expect(formatBytes(1024 * 1024 * 4.5)).toBe('4.5 MB');
    expect(formatBytes(1024 * 1024 * 1024 * 2.1)).toBe('2.1 GB');
  });
});

describe('sensitivity mappings', () => {
  it('maps level 1 to 5 to expected (min_rise_db, min_sustain_s)', () => {
    expect(sensitivityToParams(1)).toEqual({ min_rise_db: 6.0, min_sustain_s: 4.0 });
    expect(sensitivityToParams(2)).toEqual({ min_rise_db: 5.0, min_sustain_s: 3.5 });
    expect(sensitivityToParams(3)).toEqual({ min_rise_db: 4.0, min_sustain_s: 3.0 });
    expect(sensitivityToParams(4)).toEqual({ min_rise_db: 3.0, min_sustain_s: 2.5 });
    expect(sensitivityToParams(5)).toEqual({ min_rise_db: 3.0, min_sustain_s: 2.0 });
  });

  it('maps inverse (rise, sustain) back to sensitivity level', () => {
    expect(paramsToSensitivity(4.0, 3.0)).toBe(3);
    expect(paramsToSensitivity(6.0, 4.0)).toBe(1);
    expect(paramsToSensitivity(3.0, 2.0)).toBe(5);
  });
});

describe('calculateReelOffsets', () => {
  it('calculates running cumulative offset for selected moments', () => {
    const windows = [
      { start: 10, end: 20, selected: true }, // duration 10 -> offset 0
      { start: 50, end: 65, selected: true }, // duration 15 -> offset 10
      { start: 100, end: 120, selected: false }, // dropped -> null
      { start: 150, end: 160, selected: true }, // duration 10 -> offset 25
    ];

    const offsets = calculateReelOffsets(windows);
    expect(offsets).toEqual([0, 10, null, 25]);
  });

  it('handles empty window list', () => {
    expect(calculateReelOffsets([])).toEqual([]);
  });
});

describe('calculateSelectionTotals', () => {
  it('calculates total selected moments, duration and percentage cap', () => {
    const windows = [
      { start: 0, end: 30, selected: true }, // 30s
      { start: 60, end: 90, selected: true }, // 30s
      { start: 120, end: 180, selected: false }, // dropped 60s
      { start: 200, end: 260, selected: true }, // 60s
    ];

    const totals = calculateSelectionTotals(windows, 300); // 300s cap = 5 min
    expect(totals.count).toBe(3);
    expect(totals.totalDuration).toBe(120);
    expect(totals.capPercent).toBe(40); // 120 / 300 * 100
  });

  it('handles targetDurationCap 0 as unlimited 100%', () => {
    const windows = [{ start: 0, end: 30, selected: true }];
    const totals = calculateSelectionTotals(windows, 0);
    expect(totals.count).toBe(1);
    expect(totals.totalDuration).toBe(30);
    expect(totals.capPercent).toBe(100);
  });
});
