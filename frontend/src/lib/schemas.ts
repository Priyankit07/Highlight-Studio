import { z } from 'zod';

export const JsRuntimeInfoSchema = z.object({
  available: z.boolean().default(false),
  runtime: z.string().nullable().default(null),
  path: z.string().nullable().default(null),
  version: z.string().nullable().default(null),
  ejs_installed: z.boolean().default(false),
  guidance: z.string().nullable().default(null),
});

export const CookiesConfigSchema = z.object({
  source: z.enum(['none', 'browser', 'file']).default('none'),
  browser: z.string().nullable().default(null),
  file_configured: z.boolean().default(false),
});

export const HealthInfoSchema = z.object({
  status: z.enum(['healthy', 'degraded']).default('healthy'),
  ffmpeg: z.object({
    available: z.boolean().default(false),
    path: z.string().default(''),
  }).default({ available: false, path: '' }),
  yt_dlp: z.object({
    version: z.string().default('Installed (version unknown)'),
    ejs_installed: z.boolean().optional().default(false),
  }).default({ version: 'Installed (version unknown)', ejs_installed: false }),
  js_runtime: JsRuntimeInfoSchema.optional(),
  cookies: CookiesConfigSchema.optional(),
  disk: z.object({
    free_bytes: z.number().default(0),
    total_bytes: z.number().default(0),
    free_gb: z.number().default(0),
    total_gb: z.number().default(0),
  }).default({ free_bytes: 0, total_bytes: 0, free_gb: 0, total_gb: 0 }),
  limits: z.object({
    max_upload_gb: z.number().default(10),
    allowed_extensions: z.array(z.string()).default([]),
  }).default({ max_upload_gb: 10, allowed_extensions: [] }),
  auth_required: z.boolean().optional().default(false),
  app_env: z.string().optional().default('local'),
  url_import_enabled: z.boolean().optional().default(true),
});

export const ImportCheckResultSchema = z.discriminatedUnion('ok', [
  z.object({
    ok: z.literal(true),
    title: z.string().default(''),
    duration_s: z.number().default(0),
    thumbnail: z.string().nullable().default(null),
    is_live: z.boolean().default(false),
    est_size_mb: z.number().nullable().default(null),
    extractor: z.string().optional(),
  }),
  z.object({
    ok: z.literal(false),
    error_code: z.string().default('DOWNLOAD_FAILED'),
    message: z.string().default('Failed to check URL'),
    hint: z.string().default(''),
  }),
]);

export const ConfigFieldSchemaObj = z.object({
  name: z.string(),
  type: z.enum(['float', 'int', 'str']),
  default: z.any(),
  description: z.string().default(''),
  group: z.enum(['basic', 'advanced']).default('basic'),
  step: z.number().optional(),
  unit: z.string().optional(),
  min: z.number().optional(),
  max: z.number().optional(),
  choices: z.array(z.string()).optional(),
});

export const ConfigSchemaResponseSchema = z.object({
  fields: z.array(ConfigFieldSchemaObj),
});

export const WindowItemSchema = z.object({
  start: z.number(),
  end: z.number(),
  duration: z.number(),
  start_hms: z.string().default('00:00'),
  end_hms: z.string().default('00:00'),
  score: z.number().default(0),
  peak_time: z.number().default(0),
  peak_time_hms: z.string().default('00:00'),
  spike_count: z.number().default(1),
  selected: z.boolean().default(false),
  thumb_url: z.string().optional(),
  reel_offset: z.number().nullable().optional(),
  tag: z.enum(['Goal', 'Chance', 'Card', 'Other']).optional(),
  note: z.string().optional(),
  source: z.string().optional().default('auto'),
  drop_reason: z.string().nullable().optional(),
  peak_rise_db: z.number().optional().default(0),
  original_start: z.number().nullable().optional(),
  original_end: z.number().nullable().optional(),
  is_cropped: z.boolean().optional().default(false),
});

export const SuggestionItemSchema = z.object({
  start: z.number(),
  end: z.number(),
  duration: z.number(),
  start_hms: z.string().default('00:00'),
  end_hms: z.string().default('00:00'),
  score: z.number().default(0),
  peak_time: z.number().default(0),
  peak_time_hms: z.string().default('00:00'),
  peak_rise_db: z.number().default(0),
  source: z.literal('suggestion').default('suggestion'),
  spike_count: z.number().default(1),
});

export const LabelItemSchema = z.object({
  id: z.string().optional(),
  time: z.number(),
  label: z.string(),
  caught: z.boolean().optional(),
});

export const LabelSummarySchema = z.object({
  total: z.number().default(0),
  caught: z.number().default(0),
  missed: z.number().default(0),
  recall: z.number().default(0),
});

export const LabelsResponseSchema = z.object({
  labels: z.array(LabelItemSchema).default([]),
  summary: LabelSummarySchema.optional(),
});

export const SweepResultItemSchema = z.object({
  min_rise_db: z.number(),
  min_sustain_s: z.number(),
  pre_roll: z.number(),
  windows: z.number(),
  reel_duration_s: z.number(),
  recall: z.number(),
  precision: z.number(),
  f1: z.number(),
});

export const SpikeItemSchema = z.object({
  onset: z.number(),
  offset: z.number(),
  peak_time: z.number(),
  peak_rise_db: z.number(),
  score: z.number(),
  duration: z.number(),
});

export const EnvelopeDataSchema = z.object({
  t: z.array(z.number()).default([]),
  db: z.array(z.number()).default([]),
  baseline: z.array(z.number()).default([]),
  rise: z.array(z.number()).default([]),
});

export const AnalysisResponseSchema = z.object({
  duration_s: z.number().default(0),
  envelope: EnvelopeDataSchema.default({ t: [], db: [], baseline: [], rise: [] }),
  spikes: z.array(SpikeItemSchema).default([]),
  windows: z.array(WindowItemSchema).default([]),
  suggestions: z.array(SuggestionItemSchema).default([]),
  config: z.record(z.string(), z.any()).default({}),
});

export const RenderRecordSchema = z.object({
  id: z.string(),
  job_id: z.string(),
  created_at: z.string(),
  status: z.enum(['rendering', 'completed', 'failed', 'cancelled']),
  duration_s: z.number().default(0),
  clip_count: z.number().default(0),
  windows: z.array(z.object({ start: z.number(), end: z.number() })).default([]),
  error_message: z.string().nullable().optional(),
});

export const JobSummarySchema = z.object({
  id: z.string(),
  title: z.string().default('Highlight Studio'),
  status: z.enum([
    'queued',
    'importing',
    'extracting_audio',
    'detecting',
    'analysis_ready',
    'rendering',
    'completed',
    'failed',
    'cancelled',
    'interrupted',
  ]).default('queued'),
  created_at: z.string().default(''),
  updated_at: z.string().default(''),
  duration_s: z.number().default(0),
  moment_count: z.number().default(0),
  reel_length: z.number().default(0),
  queue_position: z.number().default(1),
  thumbnail_url: z.string().nullable().optional(),
  error: z.object({
    code: z.string().default('ERROR'),
    message: z.string().default('An error occurred'),
  }).nullable().optional(),
});

export const JobDetailSchema = JobSummarySchema.extend({
  stage: z.string().nullable().optional(),
  progress: z.number().default(0),
  config: z.record(z.string(), z.any()).default({}),
  active_render_id: z.string().nullable().optional(),
  proxy_ready: z.boolean().default(false),
  renders: z.array(RenderRecordSchema).default([]),
  labels: z.array(LabelItemSchema).nullable().optional(),
});

export const JobListResponseSchema = z.object({
  jobs: z.array(JobSummarySchema).default([]),
});

export const UploadInitResponseSchema = z.object({
  upload_id: z.string(),
  chunk_size: z.number(),
});

export const UploadStatusResponseSchema = z.object({
  upload_id: z.string(),
  received: z.array(z.number()).default([]),
});
