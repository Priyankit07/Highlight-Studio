import { describe, it, expect } from 'vitest';

describe('Job Studio Stepper Stage Status Logic', () => {
  const steps = [
    { key: 'importing', label: 'Import Video' },
    { key: 'extracting_audio', label: 'Extract Audio' },
    { key: 'detecting', label: 'Detect Excitement' },
    { key: 'rendering', label: 'Build Reel' },
  ];

  const computeStepStatus = (
    stepKey: string,
    job: { status: string; stage?: string } | null
  ) => {
    if (!job) return 'pending';
    const s = job.status;

    const order = ['importing', 'extracting_audio', 'detecting', 'rendering', 'completed'];
    const curStage = job.stage || (s === 'analysis_ready' ? 'rendering' : s);
    const curIdx = order.indexOf(curStage);
    const stepIdx = order.indexOf(stepKey);

    if (s === 'failed' || s === 'cancelled' || s === 'interrupted') {
      if (curIdx >= 0 && stepIdx === curIdx) return 'failed';
      if (curIdx >= 0 && stepIdx < curIdx) return 'done';
      return 'pending';
    }

    if (curIdx > stepIdx || s === 'completed') return 'done';
    if (curIdx === stepIdx) return 'active';
    return 'pending';
  };

  it('only marks importing as failed when download fails during importing', () => {
    const job = { status: 'failed', stage: 'importing' };
    expect(computeStepStatus('importing', job)).toBe('failed');
    expect(computeStepStatus('extracting_audio', job)).toBe('pending');
    expect(computeStepStatus('detecting', job)).toBe('pending');
    expect(computeStepStatus('rendering', job)).toBe('pending');
  });

  it('marks completed stages as done, current stage as failed, and later stages as pending', () => {
    const job = { status: 'failed', stage: 'detecting' };
    expect(computeStepStatus('importing', job)).toBe('done');
    expect(computeStepStatus('extracting_audio', job)).toBe('done');
    expect(computeStepStatus('detecting', job)).toBe('failed');
    expect(computeStepStatus('rendering', job)).toBe('pending');
  });

  it('marks all stages done when completed', () => {
    const job = { status: 'completed', stage: 'completed' };
    expect(computeStepStatus('importing', job)).toBe('done');
    expect(computeStepStatus('extracting_audio', job)).toBe('done');
    expect(computeStepStatus('detecting', job)).toBe('done');
    expect(computeStepStatus('rendering', job)).toBe('done');
  });

  it('correctly parses real API response from backend', async () => {
    const { JobDetailSchema } = await import('../lib/schemas');
    const apiResponse = {
      id: "02e82f23-be51-4183-b8d2-30d9a53d9c79",
      title: "FULL MATCH | Manchester City v Liverpool",
      status: "completed",
      stage: "completed",
      progress: 1.0,
      created_at: "2026-09-25T17:13:23.562490+00:00",
      updated_at: "2026-09-25T17:13:39.043731+00:00",
      duration_s: 5628.01,
      moment_count: 5,
      config: { min_rise_db: 5.0, min_sustain_s: 3.5, target_duration: 300.0 },
      active_render_id: "default",
      queue_position: 0,
      proxy_ready: true,
      renders: [{
        id: "default",
        job_id: "02e82f23-be51-4183-b8d2-30d9a53d9c79",
        created_at: "2026-09-25T17:13:23.574044+00:00",
        status: "completed",
        duration_s: 94.82,
        clip_count: 0,
        windows_json: "[]",
        error_message: null,
        windows: []
      }],
      labels: [],
      error: null
    };
    const res = JobDetailSchema.safeParse(apiResponse);
    if (!res.success) {
      console.log('Validation issues:', JSON.stringify(res.error.issues, null, 2));
    }
    expect(res.success).toBe(true);
  });
});
