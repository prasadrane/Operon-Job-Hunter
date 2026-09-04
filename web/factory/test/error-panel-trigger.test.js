import { describe, it, expect, beforeEach, vi } from 'vitest';
import { ErrorPanelTrigger, ErrorPanelOpenEvent } from '../error-panel-trigger.js';
import { ErrorGroupManager } from '../error-group-manager.js';

describe('ErrorPanelTrigger', () => {
  let trigger;
  let groupManager;

  beforeEach(() => {
    groupManager = new ErrorGroupManager();
    trigger = new ErrorPanelTrigger(groupManager);

    // Seed with an error
    groupManager.addError({
      correlation_id: 'corr-abc',
      error_code: 'ERR_TIMEOUT',
      node: 'eval_node',
      job_id: 'job1',
      agent_id: 'judge_minerva',
      tier: 1,
      stack_trace: 'TimeoutError at state_machine.py:123',
      timestamp: '2026-08-25T10:00:00Z',
    });
    groupManager.addError({
      correlation_id: 'corr-abc',
      error_code: 'ERR_CASCADE',
      node: 'tailor_node',
      job_id: 'job1',
      agent_id: 'master_scribe',
      tier: 2,
      stack_trace: 'Dependency failed',
      timestamp: '2026-08-25T10:00:05Z',
    });
  });

  it('should emit ErrorPanelOpenEvent on handleEntityClick for error-affected entity', () => {
    const handler = vi.fn();
    trigger.onPanelOpen(handler);

    trigger.handleEntityClick('judge_minerva');

    expect(handler).toHaveBeenCalledTimes(1);
    const event = handler.mock.calls[0][0];
    expect(event).toBeInstanceOf(ErrorPanelOpenEvent);
    expect(event.correlationId).toBe('corr-abc');
    expect(event.tier).toBe(1);
    expect(event.errorCode).toBe('ERR_TIMEOUT');
    expect(event.entityKey).toBe('judge_minerva');
    expect(event.failureChain).toHaveLength(2);
  });

  it('should NOT emit event for entity with no error', () => {
    const handler = vi.fn();
    trigger.onPanelOpen(handler);

    trigger.handleEntityClick('scout_falcon');

    expect(handler).not.toHaveBeenCalled();
  });

  it('should emit event on keyboard Enter key', () => {
    const handler = vi.fn();
    trigger.onPanelOpen(handler);

    trigger.handleKeyboard('master_scribe', 'Enter');

    expect(handler).toHaveBeenCalledTimes(1);
    const event = handler.mock.calls[0][0];
    expect(event.tier).toBe(2);
    expect(event.errorCode).toBe('ERR_CASCADE');
  });

  it('should NOT emit event on Space key (only Enter)', () => {
    const handler = vi.fn();
    trigger.onPanelOpen(handler);

    trigger.handleKeyboard('judge_minerva', 'Space');

    expect(handler).not.toHaveBeenCalled();
  });

  it('should populate failureChain from correlation group', () => {
    const handler = vi.fn();
    trigger.onPanelOpen(handler);

    trigger.handleEntityClick('judge_minerva');

    const event = handler.mock.calls[0][0];
    expect(event.failureChain).toHaveLength(2);
    // Failure chain sorted by timestamp, tier 1 first
    expect(event.failureChain[0].tier).toBe(1);
    expect(event.failureChain[0].agent_id).toBe('judge_minerva');
    expect(event.failureChain[1].tier).toBe(2);
    expect(event.failureChain[1].agent_id).toBe('master_scribe');
  });

  it('should support multiple listeners', () => {
    const handler1 = vi.fn();
    const handler2 = vi.fn();
    trigger.onPanelOpen(handler1);
    trigger.onPanelOpen(handler2);

    trigger.handleEntityClick('judge_minerva');

    expect(handler1).toHaveBeenCalledTimes(1);
    expect(handler2).toHaveBeenCalledTimes(1);
  });

  it('should remove listener with offPanelOpen', () => {
    const handler = vi.fn();
    trigger.onPanelOpen(handler);
    trigger.offPanelOpen(handler);

    trigger.handleEntityClick('judge_minerva');

    expect(handler).not.toHaveBeenCalled();
  });
});
