import { describe, it, expect, beforeEach, vi } from 'vitest';
import { StateManager } from '../state.js';

describe('StateManager.applyStateSync', () => {
  let sm;
  beforeEach(() => { sm = new StateManager(); });

  it('replaces pipeline_state, agent_states, job_queue', () => {
    sm.applyStateSync({
      pipeline_state: { active_jobs: 3 },
      agent_states: { scout_falcon: { status: 'active' } },
      job_queue: { discovered: [{ id: 'j1' }], evaluation: [], tailored: [], applied: [] },
    });
    expect(sm.getPipelineState()).toEqual({ active_jobs: 3 });
    expect(sm.getAgentState('scout_falcon')).toEqual({ status: 'active' });
    expect(sm.getJobQueue().discovered).toHaveLength(1);
  });

  it('dispatches each agent to AgentManager if attached', () => {
    const am = { updateAgentState: vi.fn() };
    sm.attach({ agentManager: am, jobManager: null });
    sm.applyStateSync({
      pipeline_state: {},
      agent_states: {
        scout_falcon: { status: 'active' },
        evaluator: { status: 'sleeping' },
      },
      job_queue: {},
    });
    expect(am.updateAgentState).toHaveBeenCalledTimes(2);
    expect(am.updateAgentState).toHaveBeenCalledWith('scout_falcon', { status: 'active' });
    expect(am.updateAgentState).toHaveBeenCalledWith('evaluator', { status: 'sleeping' });
  });
});

describe('StateManager.applyAgentUpdate', () => {
  let sm, am;
  beforeEach(() => {
    sm = new StateManager();
    am = { updateAgentState: vi.fn() };
    sm.attach({ agentManager: am });
    sm.applyStateSync({
      pipeline_state: {},
      agent_states: { scout_falcon: { status: 'sleeping', jobs_processed: 10 } },
      job_queue: {},
    });
    am.updateAgentState.mockClear();
  });

  it('merges new fields into existing agent state', () => {
    sm.applyAgentUpdate('scout_falcon', { status: 'active', current_task: 'scanning' });
    const s = sm.getAgentState('scout_falcon');
    expect(s.status).toBe('active');
    expect(s.current_task).toBe('scanning');
    expect(s.jobs_processed).toBe(10); // preserved
  });

  it('creates a new agent entry if unknown id arrives', () => {
    sm.applyAgentUpdate('mystery_agent', { status: 'active' });
    expect(sm.getAgentState('mystery_agent')).toEqual({ status: 'active' });
  });

  it('dispatches merged state to AgentManager', () => {
    sm.applyAgentUpdate('scout_falcon', { status: 'active' });
    expect(am.updateAgentState).toHaveBeenCalledTimes(1);
    const [id, st] = am.updateAgentState.mock.calls[0];
    expect(id).toBe('scout_falcon');
    expect(st.status).toBe('active');
  });
});

describe('StateManager entity caps', () => {
  let sm;
  beforeEach(() => { sm = new StateManager(); });

  it('caps nodeEvents at 64, drops oldest', () => {
    for (let i = 0; i < 70; i++) sm.recordNodeEvent({ i });
    expect(sm.nodeEvents).toHaveLength(64);
    expect(sm.nodeEvents[0].i).toBe(6); // first 6 dropped
  });

  it('caps errors at 128, drops oldest', () => {
    for (let i = 0; i < 140; i++) sm.recordError({ i });
    expect(sm.errors).toHaveLength(128);
    expect(sm.errors[0].i).toBe(12);
  });

  it('caps logs at 128, drops oldest', () => {
    for (let i = 0; i < 150; i++) sm.appendLog({ i });
    expect(sm.logs).toHaveLength(128);
    expect(sm.logs[0].i).toBe(22);
  });
});

describe('StateManager.fadeAgentToUnknown', () => {
  it('sets status=unknown but keeps agent in map', () => {
    const sm = new StateManager();
    const am = { updateAgentState: vi.fn() };
    sm.attach({ agentManager: am });
    sm.applyStateSync({
      pipeline_state: {},
      agent_states: { scout_falcon: { status: 'active' } },
      job_queue: {},
    });
    sm.fadeAgentToUnknown('scout_falcon');
    expect(sm.getAgentState('scout_falcon').status).toBe('unknown');
    expect(sm.getAgentState('scout_falcon')).not.toBeNull();
    expect(am.updateAgentState).toHaveBeenLastCalledWith('scout_falcon', expect.objectContaining({ status: 'unknown' }));
  });

  it('no-ops for unknown agent id', () => {
    const sm = new StateManager();
    sm.fadeAgentToUnknown('nonexistent');
    expect(sm.getAgentState('nonexistent')).toBeNull();
  });
});

describe('StateManager.subscribe', () => {
  it('notifies subscribers on state_sync', () => {
    const sm = new StateManager();
    const cb = vi.fn();
    sm.subscribe('state_sync', cb);
    sm.applyStateSync({ pipeline_state: {}, agent_states: {}, job_queue: {} });
    expect(cb).toHaveBeenCalled();
  });

  it('returns unsubscribe function', () => {
    const sm = new StateManager();
    const cb = vi.fn();
    const unsub = sm.subscribe('state_sync', cb);
    unsub();
    sm.applyStateSync({ pipeline_state: {}, agent_states: {}, job_queue: {} });
    expect(cb).not.toHaveBeenCalled();
  });
});
