export interface JsRuntimeInfo {
  available: boolean;
  runtime: string | null;
  path: string | null;
  version: string | null;
  ejs_installed: boolean;
  guidance: string | null;
}

export interface CookiesConfig {
  source: 'none' | 'browser' | 'file';
  browser: string | null;
  file_configured: boolean;
}

export interface HealthInfo {
  status: 'healthy' | 'degraded';
  ffmpeg: {
    available: boolean;
    path: string;
  };
  yt_dlp: {
    version: string;
    ejs_installed?: boolean;
  };
  js_runtime?: JsRuntimeInfo;
  cookies?: CookiesConfig;
  disk: {
    free_bytes: number;
    total_bytes: number;
    free_gb: number;
    total_gb: number;
  };
  limits: {
    max_upload_gb: number;
    allowed_extensions: string[];
  };
  auth_required?: boolean;
  app_env?: string;
  url_import_enabled?: boolean;
}

export interface ImportCheckSuccess {
  ok: true;
  title: string;
  duration_s: number;
  thumbnail: string | null;
  is_live: boolean;
  est_size_mb: number | null;
  extractor?: string;
}

export interface ImportCheckFailure {
  ok: false;
  error_code: string;
  message: string;
  hint: string;
}

export type ImportCheckResult = ImportCheckSuccess | ImportCheckFailure;

export interface ConfigFieldSchema {
  name: string;
  type: 'float' | 'int' | 'str';
  default: any;
  description: string;
  group: 'basic' | 'advanced';
  step?: number;
  unit?: string;
  min?: number;
  max?: number;
  choices?: string[];
}

export interface WindowItem {
  start: number;
  end: number;
  duration: number;
  start_hms: string;
  end_hms: string;
  score: number;
  peak_time: number;
  peak_time_hms: string;
  spike_count: number;
  selected: boolean;
  thumb_url?: string;
  reel_offset?: number | null;
  tag?: 'Goal' | 'Chance' | 'Card' | 'Other';
  note?: string;
  source?: 'auto' | 'manual' | 'suggestion' | string;
  drop_reason?: 'over_length_cap' | 'top_k' | 'below_min_score' | string | null;
  peak_rise_db?: number;
  original_start?: number | null;
  original_end?: number | null;
  is_cropped?: boolean;
}

export interface SuggestionItem {
  start: number;
  end: number;
  duration: number;
  start_hms: string;
  end_hms: string;
  score: number;
  peak_time: number;
  peak_time_hms: string;
  peak_rise_db: number;
  source: 'suggestion';
  spike_count: number;
}

export interface LabelItem {
  id?: string;
  time: number;
  label: string;
  caught?: boolean;
}

export interface LabelSummary {
  total: number;
  caught: number;
  missed: number;
  recall: number;
}

export interface LabelsResponse {
  labels: LabelItem[];
  summary?: LabelSummary;
}

export interface SweepResultItem {
  min_rise_db: number;
  min_sustain_s: number;
  pre_roll: number;
  windows: number;
  reel_duration_s: number;
  recall: number;
  precision: number;
  f1: number;
}

export interface SpikeItem {
  onset: number;
  offset: number;
  peak_time: number;
  peak_rise_db: number;
  score: number;
  duration: number;
}

export interface EnvelopeData {
  t: number[];
  db: number[];
  baseline: number[];
  rise: number[];
}

export interface AnalysisResponse {
  duration_s: number;
  envelope: EnvelopeData;
  spikes: SpikeItem[];
  windows: WindowItem[];
  suggestions: SuggestionItem[];
  config: Record<string, any>;
}

export interface RenderRecord {
  id: string;
  job_id: string;
  created_at: string;
  status: 'rendering' | 'completed' | 'failed' | 'cancelled';
  duration_s: number;
  clip_count: number;
  windows: Array<{ start: number; end: number }>;
  error_message?: string | null;
}

export interface JobSummary {
  id: string;
  title: string;
  status: 'queued' | 'importing' | 'extracting_audio' | 'detecting' | 'analysis_ready' | 'rendering' | 'completed' | 'failed' | 'cancelled' | 'interrupted';
  created_at: string;
  updated_at: string;
  duration_s: number;
  moment_count: number;
  reel_length: number;
  queue_position: number;
  thumbnail_url?: string | null;
  error?: {
    code: string;
    message: string;
  } | null;
}

export interface JobDetail extends JobSummary {
  stage?: string | null;
  progress: number;
  config: Record<string, any>;
  active_render_id?: string | null;
  proxy_ready: boolean;
  renders: RenderRecord[];
  labels?: LabelItem[] | null;
}

export interface TuningPreset {
  name: string;
  config: {
    target_duration: number; // seconds (0 for full reel cap)
    sensitivity: number;     // 1 to 5
    min_rise_db: number;    // dB
    min_sustain_s: number;  // seconds
    skip_start_s: number;   // seconds
    pre_roll: number;       // seconds
    post_roll: number;      // seconds
    [key: string]: any;
  };
}
