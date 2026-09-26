import { test, expect } from '@playwright/test';

const JOB_STATES = [
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
] as const;

test.describe('P0: Stability across all job states', () => {
  test('handles unknown job id (404) gracefully with header intact and no crashes', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !msg.text().includes('404')) {
        consoleErrors.push(msg.text());
      }
    });

    await page.route('/api/jobs/unknown-uuid', async (route) => {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({
          error: { code: 'JOB_NOT_FOUND', message: 'Job not found' },
        }),
      });
    });

    await page.goto('/jobs/unknown-uuid');
    await expect(page.locator('header')).toBeVisible();
    await expect(page.getByText('This job no longer exists')).toBeVisible();
    await expect(page.getByRole('button', { name: /Go to Library/i })).toBeVisible();
    expect(consoleErrors).toHaveLength(0);
  });

  for (const status of JOB_STATES) {
    test(`renders safely in state: ${status}`, async ({ page }) => {
      const consoleErrors: string[] = [];
      page.on('console', (msg) => {
        if (msg.type() === 'error') {
          consoleErrors.push(msg.text());
        }
      });

      const mockJob = {
        id: `job-${status}`,
        title: `Test Match - ${status}`,
        status,
        stage: status === 'failed' ? 'detecting' : status,
        progress: status === 'completed' ? 1.0 : 0.45,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        duration_s: 720,
        moment_count: status === 'completed' ? 2 : 0,
        reel_length: status === 'completed' ? 45 : 0,
        queue_position: 1,
        proxy_ready: status === 'completed' || status === 'analysis_ready',
        config: { target_duration: 480, min_rise_db: 4.0, min_sustain_s: 3.0 },
        renders: [],
        error: status === 'failed' ? { code: 'PROCESS_FAILED', message: 'Pipeline crashed' } : null,
      };

      const mockAnalysis = {
        duration_s: 720,
        envelope: {
          t: [0, 1, 2, 3],
          db: [-30, -25, -20, -15],
          baseline: [-30, -30, -30, -30],
          rise: [0, 5, 10, 15],
        },
        spikes: [],
        windows: status === 'completed' || status === 'analysis_ready' ? [
          {
            start: 10,
            end: 25,
            duration: 15,
            start_hms: '00:10',
            end_hms: '00:25',
            score: 12.5,
            peak_time: 18,
            peak_time_hms: '00:18',
            spike_count: 1,
            selected: true,
            source: 'auto',
          },
        ] : [],
        suggestions: [],
        config: {},
      };

      await page.route(`/api/jobs/job-${status}`, async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockJob),
        });
      });

      await page.route(`/api/jobs/job-${status}/analysis`, async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockAnalysis),
        });
      });

      await page.route(`/api/jobs/job-${status}/labels`, async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ labels: [], summary: { total: 0, caught: 0, missed: 0, recall: 0 } }),
        });
      });

      await page.goto(`/jobs/job-${status}`);
      await expect(page.locator('header')).toBeVisible();

      if (status === 'failed') {
        await expect(page.getByText(/Failed at:/i)).toBeVisible();
      }

      expect(consoleErrors).toHaveLength(0);
    });
  }

  test('renders safely when completed with zero moments', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !msg.text().includes('Failed to load resource') && !msg.text().includes('404')) {
        consoleErrors.push(msg.text());
      }
    });

    const mockJob = {
      id: 'job-zero-moments',
      title: 'Zero Moments Match',
      status: 'completed',
      stage: 'completed',
      progress: 1.0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      duration_s: 600,
      moment_count: 0,
      reel_length: 0,
      queue_position: 1,
      proxy_ready: true,
      config: { target_duration: 480, min_rise_db: 4.0, min_sustain_s: 3.0 },
      renders: [],
    };

    const mockAnalysis = {
      duration_s: 600,
      envelope: { t: [0, 1], db: [-40, -40], baseline: [-40, -40], rise: [0, 0] },
      spikes: [],
      windows: [],
      suggestions: [],
      config: {},
    };

    await page.route('/api/jobs/job-zero-moments', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockJob),
      });
    });

    await page.route('/api/jobs/job-zero-moments/analysis', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockAnalysis),
      });
    });

    await page.route('/api/jobs/job-zero-moments/labels', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ labels: [], summary: { total: 0, caught: 0, missed: 0, recall: 0 } }),
      });
    });

    await page.goto('/jobs/job-zero-moments');
    await expect(page.locator('header')).toBeVisible();
    await expect(page.getByText(/No Crowd Peaks Detected/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /Try More Sensitive Detection/i })).toBeVisible();
    expect(consoleErrors).toHaveLength(0);
  });
});
