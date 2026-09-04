import { describe, it, expect, beforeEach } from 'vitest';
import { JobToken } from '../job-token.js';

describe('JobToken', () => {
  let token;

  beforeEach(() => {
    token = new JobToken();
  });

  it('should initialize with default values', () => {
    expect(token.jobId).toBe(null);
    expect(token.company).toBe('');
    expect(token.score).toBe(0);
    expect(token.alpha).toBe(1.0);
  });

  it('should set job data', () => {
    token.setJob({
      id: 'job123',
      company: 'TechCorp',
      title: 'Software Engineer',
      score: 87,
    });

    expect(token.jobId).toBe('job123');
    expect(token.company).toBe('TechCorp');
    expect(token.score).toBe(87);
  });

  it('should fade out over 5 seconds', () => {
    token.fadeOut();

    // After 2.5s (halfway), alpha should be ~0.5
    token.update(2500);
    expect(token.alpha).toBeCloseTo(0.5, 1);

    // After 5s, alpha should be 0
    token.update(2500);
    expect(token.alpha).toBe(0);
  });
});
