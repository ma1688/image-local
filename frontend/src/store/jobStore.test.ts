import { beforeEach, describe, expect, it } from 'vitest';
import { useJobStore } from './jobStore';

describe('jobStore SSE guards', () => {
  beforeEach(() => {
    useJobStore.getState().reset();
  });

  it('ignores events from a stale job id', () => {
    useJobStore.getState().setCurrentJob({
      id: 2,
      template_code: 'ref_batch',
      api_profile_id: 1,
      model: 'gpt-image-2',
      size: '1024x1024',
      prompt: '',
      candidates_per_image: 1,
      auto_retry: false,
      retry_max: 1,
      output_dir: 'outputs',
      status: 'running',
      total_candidates: 1,
      succeeded_count: 0,
      failed_count: 0,
      last_error: null,
      created_at: '2026-05-08T00:00:00Z',
      updated_at: '2026-05-08T00:00:00Z',
    });

    useJobStore.getState().appendEvent({
      id: '1-0',
      receivedAt: '2026-05-08T00:00:01Z',
      payload: {
        event: 'job.updated',
        job_id: 1,
        status: 'failed',
        succeeded: 0,
        failed: 1,
        total: 1,
      },
    });

    expect(useJobStore.getState().events).toHaveLength(0);
    expect(useJobStore.getState().currentJob?.id).toBe(2);
    expect(useJobStore.getState().currentJob?.status).toBe('running');
  });
});

