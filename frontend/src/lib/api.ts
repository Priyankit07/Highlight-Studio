import { z } from 'zod';
import {
  HealthInfo,
  ConfigFieldSchema,
  JobSummary,
  JobDetail,
  AnalysisResponse,
  RenderRecord,
  ImportCheckResult,
  CookiesConfig,
  WindowItem,
  LabelItem,
  LabelsResponse,
  SweepResultItem,
} from '../types';
import {
  HealthInfoSchema,
  ConfigSchemaResponseSchema,
  UploadInitResponseSchema,
  UploadStatusResponseSchema,
  JobSummarySchema,
  JobDetailSchema,
  JobListResponseSchema,
  AnalysisResponseSchema,
  RenderRecordSchema,
  LabelsResponseSchema,
  SweepResultItemSchema,
  ImportCheckResultSchema,
  CookiesConfigSchema,
  WindowItemSchema,
} from './schemas';

const API_BASE = '/api';

export class ApiError extends Error {
  code: string;
  detail?: any;

  constructor(message: string, code = 'ERROR', detail?: any) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.detail = detail;
  }
}

async function request<T>(endpoint: string, schema?: z.ZodType<T>, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('api_token');
  const headers = new Headers(options.headers || {});

  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  if (options.body && !(options.body instanceof Blob || options.body instanceof FormData || options.body instanceof ArrayBuffer)) {
    if (!headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });
  } catch (netErr: any) {
    throw new ApiError(netErr?.message || 'Network connection failed', 'NETWORK_ERROR');
  }

  if (!response.ok) {
    let errorData: any;
    try {
      errorData = await response.json();
    } catch {
      errorData = { error: { message: response.statusText, code: `HTTP_${response.status}` } };
    }

    let message: string;
    let code = `HTTP_${response.status}`;
    let detail: any = errorData?.detail;

    if (errorData?.error && typeof errorData.error === 'object') {
      message = errorData.error.message || `Request failed with status ${response.status}`;
      code = errorData.error.code || code;
      detail = errorData.error.detail ?? detail;
    } else if (typeof errorData?.detail === 'string') {
      message = errorData.detail;
    } else if (errorData?.detail && typeof errorData.detail === 'object' && !Array.isArray(errorData.detail)) {
      message = errorData.detail.message || errorData.detail.msg || `Request failed with status ${response.status}`;
      code = errorData.detail.code || code;
    } else if (Array.isArray(errorData?.detail)) {
      message = errorData.detail.map((d: any) => d.msg || `${d.loc?.join('.')}: ${d.type}`).join(', ');
      code = 'VALIDATION_ERROR';
    } else {
      message = errorData?.message || `Request failed with status ${response.status}`;
      if (errorData?.code) code = errorData.code;
    }

    throw new ApiError(message, code, detail);
  }

  if (response.status === 204) {
    return {} as T;
  }

  const rawJson = await response.json();

  if (schema) {
    const parseResult = schema.safeParse(rawJson);
    if (!parseResult.success) {
      console.error(`API response shape mismatch at ${endpoint}:`, parseResult.error.issues);
      throw new ApiError(
        `API data format error for ${endpoint}. Expected format did not match server response.`,
        'RESPONSE_SHAPE_MISMATCH',
        parseResult.error.issues
      );
    }
    return parseResult.data;
  }

  return rawJson as T;
}

export const api = {
  // Health
  getHealth: () => request<HealthInfo>('/health', HealthInfoSchema),

  // Config Schema
  getConfigSchema: () =>
    request<{ fields: ConfigFieldSchema[] }>('/config/schema', ConfigSchemaResponseSchema),

  // Uploads
  initUpload: (filename: string, size: number) =>
    request<{ upload_id: string; chunk_size: number }>('/uploads', UploadInitResponseSchema, {
      method: 'POST',
      body: JSON.stringify({ filename, size }),
    }),

  uploadChunk: async (uploadId: string, chunkIndex: number, chunkData: Blob) => {
    const token = localStorage.getItem('api_token');
    const headers = new Headers();
    if (token) headers.set('Authorization', `Bearer ${token}`);

    const res = await fetch(`${API_BASE}/uploads/${uploadId}/chunks/${chunkIndex}`, {
      method: 'PUT',
      headers,
      body: chunkData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: { message: res.statusText } }));
      throw new ApiError(err.error?.message || 'Failed to upload chunk', err.error?.code);
    }
    return res.json();
  },

  getUploadStatus: (uploadId: string) =>
    request<{ upload_id: string; received: number[] }>(`/uploads/${uploadId}`, UploadStatusResponseSchema),

  completeUpload: (uploadId: string) =>
    request<{ upload_id: string; filename: string; duration_s: number; ready: boolean }>(
      `/uploads/${uploadId}/complete`,
      z.object({
        upload_id: z.string(),
        filename: z.string(),
        duration_s: z.number(),
        ready: z.boolean(),
      }),
      { method: 'POST' }
    ),

  // Jobs
  createJob: (payload: { source: { type: 'upload' | 'url'; upload_id?: string; url?: string }; title?: string; config?: Record<string, any> }) =>
    request<{ job_id: string; title: string; status: string; queue_position: number }>(
      '/jobs',
      z.object({
        job_id: z.string().min(1, 'Server returned an empty job_id'),
        title: z.string(),
        status: z.string(),
        queue_position: z.number(),
      }),
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    ),

  listJobs: (limit = 50, offset = 0) =>
    request<{ jobs: JobSummary[] }>(`/jobs?limit=${limit}&offset=${offset}`, JobListResponseSchema),

  getJob: (jobId: string) => request<JobDetail>(`/jobs/${jobId}`, JobDetailSchema),

  updateJobTitle: (jobId: string, title: string) =>
    request<{ status: string }>(
      `/jobs/${jobId}`,
      z.object({ status: z.string() }),
      {
        method: 'PATCH',
        body: JSON.stringify({ title }),
      }
    ),

  cancelJob: (jobId: string) =>
    request<{ status: string; job_id: string }>(
      `/jobs/${jobId}/cancel`,
      z.object({ status: z.string(), job_id: z.string() }),
      { method: 'POST' }
    ),

  retryJob: (jobId: string) =>
    request<{ status: string; job_id: string }>(
      `/jobs/${jobId}/retry`,
      z.object({ status: z.string(), job_id: z.string() }),
      { method: 'POST' }
    ),

  deleteJob: (jobId: string) =>
    request<{ status: string; job_id: string }>(
      `/jobs/${jobId}`,
      z.object({ status: z.string(), job_id: z.string() }),
      { method: 'DELETE' }
    ),

  // Analysis & Tuning
  getJobAnalysis: (jobId: string) =>
    request<AnalysisResponse>(`/jobs/${jobId}/analysis`, AnalysisResponseSchema),

  retuneJob: (jobId: string, configOverrides: Record<string, any>) =>
    request<AnalysisResponse>(
      `/jobs/${jobId}/retune`,
      AnalysisResponseSchema,
      {
        method: 'POST',
        body: JSON.stringify({ config: configOverrides }),
      }
    ),

  saveWindows: (jobId: string, windows: WindowItem[]) =>
    request<{ windows: WindowItem[]; moment_count: number }>(
      `/jobs/${jobId}/windows`,
      z.object({
        windows: z.array(WindowItemSchema),
        moment_count: z.number(),
      }),
      {
        method: 'PUT',
        body: JSON.stringify({ windows }),
      }
    ),

  getJobLabels: (jobId: string) =>
    request<LabelsResponse>(`/jobs/${jobId}/labels`, LabelsResponseSchema),

  addJobLabel: (jobId: string, label: { time: number; label: string; id?: string }) =>
    request<LabelsResponse & { added: LabelItem }>(
      `/jobs/${jobId}/labels`,
      LabelsResponseSchema.extend({
        added: z.object({ id: z.string().optional(), time: z.number(), label: z.string() }),
      }),
      {
        method: 'POST',
        body: JSON.stringify(label),
      }
    ),

  deleteJobLabel: (jobId: string, labelId: string) =>
    request<LabelsResponse & { deleted: string }>(
      `/jobs/${jobId}/labels/${labelId}`,
      LabelsResponseSchema.extend({ deleted: z.string() }),
      {
        method: 'DELETE',
      }
    ),

  findBetterSettings: (jobId: string) =>
    request<{ results: SweepResultItem[] }>(
      `/jobs/${jobId}/find-settings`,
      z.object({ results: z.array(SweepResultItemSchema) }),
      {
        method: 'POST',
      }
    ),

  // Rendering
  createRender: (
    jobId: string,
    payload: {
      windows: Array<{ start: number; end: number }>;
      fade_duration_s?: number;
      crf?: number;
      preset?: string;
    }
  ) =>
    request<{ render_id: string; status: string; clip_count: number }>(
      `/jobs/${jobId}/renders`,
      z.object({
        render_id: z.string(),
        status: z.string(),
        clip_count: z.number(),
      }),
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    ),

  getRender: (jobId: string, renderId: string) =>
    request<RenderRecord>(`/jobs/${jobId}/renders/${renderId}`, RenderRecordSchema),

  // Import preflight check
  checkImport: (url: string) =>
    request<ImportCheckResult>('/import/check', ImportCheckResultSchema, {
      method: 'POST',
      body: JSON.stringify({ url }),
    }),

  // Cookies
  getCookies: () => request<CookiesConfig>('/cookies', CookiesConfigSchema),

  setBrowserCookies: (browser: string) =>
    request<CookiesConfig>(
      '/cookies/browser',
      CookiesConfigSchema,
      {
        method: 'POST',
        body: JSON.stringify({ browser }),
      }
    ),

  uploadCookiesFile: async (file: File) => {
    const token = localStorage.getItem('api_token');
    const headers = new Headers();
    if (token) headers.set('Authorization', `Bearer ${token}`);

    const formData = new FormData();
    formData.append('file', file);

    const res = await fetch(`${API_BASE}/cookies/upload`, {
      method: 'POST',
      headers,
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: { message: res.statusText } }));
      throw new ApiError(err.error?.message || err.detail?.message || 'Failed to upload cookies file', err.error?.code || err.detail?.code);
    }
    const data = await res.json();
    return CookiesConfigSchema.parse(data);
  },

  clearCookies: () => request<CookiesConfig>('/cookies', CookiesConfigSchema, { method: 'DELETE' }),
};
