import { describe, it, expect, beforeEach } from 'vitest';
import { ErrorGroupManager } from '../error-group-manager.js';

describe('ErrorGroupManager', () => {
  let manager;

  beforeEach(() => {
    manager = new ErrorGroupManager();
  });

  it('should start with no groups', () => {
    expect(manager.getTopGroups()).toHaveLength(0);
  });

  it('should group errors by correlation_id', () => {
    const corrId = 'corr-abc-123';
    manager.addError({
      correlation_id: corrId,
      error_code: 'ERR_TIMEOUT',
      node: 'eval_node',
      job_id: 'job1',
      agent_id: 'judge_minerva',
      tier: 1,
      stack_trace: 'TimeoutError at state_machine.py:123',
      timestamp: '2026-08-25T10:00:00Z',
    });
    manager.addError({
      correlation_id: corrId,
      error_code: 'ERR_CASCADE',
      node: 'tailor_node',
      job_id: 'job1',
      agent_id: 'master_scribe',
      tier: 2,
      stack_trace: 'Dependency failed',
      timestamp: '2026-08-25T10:00:05Z',
    });

    const group = manager.getGroup(corrId);
    expect(group).not.toBeNull();
    expect(group.correlationId).toBe(corrId);
    expect(group.errors).toHaveLength(2);
    expect(group.rootError.error_code).toBe('ERR_TIMEOUT');
    expect(group.rootError.tier).toBe(1);
  });

  it('should identify root error (tier 1) in each group', () => {
    const corrId = 'corr-xyz-789';
    // Add tier 2 first, then tier 1 — should still find root
    manager.addError({
      correlation_id: corrId,
      error_code: 'ERR_CASCADE',
      node: 'tailor_node',
      job_id: 'job2',
      agent_id: 'master_scribe',
      tier: 2,
      stack_trace: 'Dependency failed',
      timestamp: '2026-08-25T10:01:00Z',
    });
    manager.addError({
      correlation_id: corrId,
      error_code: 'ERR_RATE_LIMIT',
      node: 'eval_node',
      job_id: 'job2',
      agent_id: 'judge_minerva',
      tier: 1,
      stack_trace: 'Rate limit exceeded',
      timestamp: '2026-08-25T10:00:55Z',
    });

    const group = manager.getGroup(corrId);
    expect(group.rootError).not.toBeNull();
    expect(group.rootError.error_code).toBe('ERR_RATE_LIMIT');
    expect(group.rootError.tier).toBe(1);
  });

  it('should return tier for entity by agent_id', () => {
    manager.addError({
      correlation_id: 'corr-1',
      error_code: 'ERR_TIMEOUT',
      node: 'eval_node',
      job_id: 'job1',
      agent_id: 'judge_minerva',
      tier: 1,
      stack_trace: '',
      timestamp: '2026-08-25T10:00:00Z',
    });
    manager.addError({
      correlation_id: 'corr-1',
      error_code: 'ERR_CASCADE',
      node: 'tailor_node',
      job_id: 'job1',
      agent_id: 'master_scribe',
      tier: 2,
      stack_trace: '',
      timestamp: '2026-08-25T10:00:05Z',
    });

    expect(manager.getTierForEntity('judge_minerva')).toBe(1);
    expect(manager.getTierForEntity('master_scribe')).toBe(2);
    expect(manager.getTierForEntity('scout_falcon')).toBe(0); // not affected
  });

  it('should return tier for entity by node name', () => {
    manager.addError({
      correlation_id: 'corr-2',
      error_code: 'ERR_TIMEOUT',
      node: 'eval_node',
      job_id: 'job3',
      agent_id: 'judge_minerva',
      tier: 1,
      stack_trace: '',
      timestamp: '2026-08-25T10:02:00Z',
    });

    expect(manager.getTierForEntity('eval_node')).toBe(1);
  });

  it('should cap top groups and expose show-all flag', () => {
    // Add 7 different correlation groups
    for (let i = 0; i < 7; i++) {
      manager.addError({
        correlation_id: `corr-${i}`,
        error_code: `ERR_${i}`,
        node: `node_${i}`,
        job_id: `job_${i}`,
        agent_id: `agent_${i}`,
        tier: 1,
        stack_trace: '',
        timestamp: `2026-08-25T10:0${i}:00Z`,
      });
    }

    const top5 = manager.getTopGroups(5);
    expect(top5).toHaveLength(5);
    expect(top5.hasMore).toBe(true);

    const all = manager.getTopGroups(0); // 0 = all
    expect(all).toHaveLength(7);
    expect(all.hasMore).toBe(false);
  });

  it('should enforce ring buffer capacity of 128', () => {
    for (let i = 0; i < 150; i++) {
      manager.addError({
        correlation_id: `corr-${i}`,
        error_code: `ERR_${i}`,
        node: `node_${i}`,
        job_id: `job_${i}`,
        agent_id: `agent_${i}`,
        tier: 1,
        stack_trace: '',
        timestamp: `2026-08-25T10:00:${String(i).padStart(2, '0')}Z`,
      });
    }

    // Total errors stored capped at 128
    expect(manager.totalErrorCount).toBeLessThanOrEqual(128);
  });

  it('should prune errors older than maxAgeMs', () => {
    manager.addError({
      correlation_id: 'corr-old',
      error_code: 'ERR_OLD',
      node: 'eval_node',
      job_id: 'job1',
      agent_id: 'judge_minerva',
      tier: 1,
      stack_trace: '',
      timestamp: '2026-08-25T09:00:00Z',
    });
    manager.addError({
      correlation_id: 'corr-new',
      error_code: 'ERR_NEW',
      node: 'tailor_node',
      job_id: 'job2',
      agent_id: 'master_scribe',
      tier: 1,
      stack_trace: '',
      timestamp: '2026-08-25T10:00:00Z',
    });

    // Prune errors older than 30 minutes from 10:05
    const now = new Date('2026-08-25T10:05:00Z').getTime();
    manager.pruneOlderThan(30 * 60 * 1000, now);

    expect(manager.getGroup('corr-old')).toBeNull();
    expect(manager.getGroup('corr-new')).not.toBeNull();
  });
});
