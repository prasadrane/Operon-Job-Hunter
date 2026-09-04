import { describe, it, expect, beforeEach } from 'vitest';
import { JobManager } from '../job-manager.js';

describe('JobManager', () => {
  let manager;

  beforeEach(() => {
    manager = new JobManager();
  });

  it('should track active jobs', () => {
    manager.updateJob({
      id: 'job1',
      company: 'TechCorp',
      stage: 'evaluation',
      status: 'active',
    });

    const activeJobs = manager.getActiveJobs();
    expect(activeJobs).toHaveLength(1);
    expect(activeJobs[0].jobId).toBe('job1');
  });

  it('should track queue counts per zone', () => {
    manager.updateJob({ id: 'job1', stage: 'discovery', status: 'queued' });
    manager.updateJob({ id: 'job2', stage: 'discovery', status: 'queued' });
    manager.updateJob({ id: 'job3', stage: 'evaluation', status: 'queued' });

    const queues = manager.getQueueCounts();
    expect(queues['discovery']).toBe(2);
    expect(queues['evaluation']).toBe(1);
  });

  it('should fade out completed jobs', () => {
    manager.updateJob({ id: 'job1', stage: 'lifecycle', status: 'completed' });

    // Job should be fading
    const token = manager.getToken('job1');
    expect(token.isFading).toBe(true);
  });

  it('should remove fully faded jobs', () => {
    manager.updateJob({ id: 'job1', stage: 'lifecycle', status: 'completed' });

    // Fast forward 5 seconds
    for (let i = 0; i < 50; i++) {
      manager.update(100);
    }

    const activeJobs = manager.getActiveJobs();
    expect(activeJobs).toHaveLength(0);
  });
});
