import { TuningPreset } from '../types';

export const DEFAULT_PRESETS: TuningPreset[] = [
  {
    name: 'Standard Match (3 min)',
    config: {
      target_duration: 180,
      sensitivity: 3,
      min_rise_db: 4.0,
      min_sustain_s: 3.0,
      skip_start_s: 30,
      pre_roll: 12.0,
      post_roll: 6.0,
    },
  },
  {
    name: 'Derby / Noisy Crowd',
    config: {
      target_duration: 300,
      sensitivity: 2,
      min_rise_db: 5.0,
      min_sustain_s: 3.5,
      skip_start_s: 30,
      pre_roll: 10.0,
      post_roll: 5.0,
    },
  },
  {
    name: 'Quiet Stadium / Broadcaster',
    config: {
      target_duration: 180,
      sensitivity: 4,
      min_rise_db: 3.0,
      min_sustain_s: 2.5,
      skip_start_s: 0,
      pre_roll: 14.0,
      post_roll: 8.0,
    },
  },
  {
    name: 'Extended Reel (5 min)',
    config: {
      target_duration: 300,
      sensitivity: 3,
      min_rise_db: 4.0,
      min_sustain_s: 3.0,
      skip_start_s: 15,
      pre_roll: 12.0,
      post_roll: 6.0,
    },
  },
];

const PRESETS_STORAGE_KEY = 'custom_presets';

export function getSavedPresets(): TuningPreset[] {
  try {
    const raw = localStorage.getItem(PRESETS_STORAGE_KEY);
    if (!raw) {
      localStorage.setItem(PRESETS_STORAGE_KEY, JSON.stringify(DEFAULT_PRESETS));
      return DEFAULT_PRESETS;
    }
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) && parsed.length > 0 ? parsed : DEFAULT_PRESETS;
  } catch {
    return DEFAULT_PRESETS;
  }
}

export function savePresets(presets: TuningPreset[]): void {
  localStorage.setItem(PRESETS_STORAGE_KEY, JSON.stringify(presets));
}

export function validatePresetName(name: string, existing: TuningPreset[], editingIndex?: number): string | null {
  const trimmed = name.trim();
  if (!trimmed) {
    return 'Preset name cannot be empty.';
  }
  const duplicate = existing.some((p, i) => i !== editingIndex && p.name.toLowerCase() === trimmed.toLowerCase());
  if (duplicate) {
    return `A preset named "${trimmed}" already exists.`;
  }
  return null;
}
