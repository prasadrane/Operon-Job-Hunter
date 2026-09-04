import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { SSEBridge, ReconnectionController } from '../sync.js';

function makeBridge() {
  const state = {
    applyStateSync: vi.fn(),
    applyAgentUpdate: vi.fn(),
    recordNodeEvent: vi.fn(),
    recordError: vi.fn(),
    appendLog: vi.fn(),
  };
  const entities = {
    handleNodeEntry: vi.fn(),
    handleNodeExit: vi.fn(),
    handleStructuredError: vi.fn(),
  };
  const bridge = new SSEBridge(state, entities);
  // Bypass EventSource creation; construct ReconnectionController manually
  bridge.reconnect = new ReconnectionController(bridge);
  bridge._registerDefaultHandlers();
  return { bridge, state, entities };
}

describe('ReconnectionController ring buffer capacities', () => {
  let rc;
  beforeEach(() => { rc = makeBridge().bridge.reconnect; });
  afterEach(() => rc.destroy());

  it('caps node buffer at 64 × 2 safety valve, never drops normally', () => {
    for (let i = 0; i < 100; i++) {
      rc.bufferEvent({ type: 'node_entry', seq_no: i, payload: { i } });
    }
    expect(rc.buffers.node.length).toBe(100); // under 128 safety valve
    for (let i = 0; i < 50; i++) {
      rc.bufferEvent({ type: 'node_entry', seq_no: 100 + i, payload: { i } });
    }
    expect(rc.buffers.node.length).toBe(128); // 150 total, capped at 2x64
  });

  it('caps agent_update at 256, drops oldest', () => {
    for (let i = 0; i < 300; i++) {
      rc.bufferEvent({ type: 'agent_update', seq_no: i, payload: { agent: `a${i}` } });
    }
    expect(rc.buffers.agent_update.length).toBe(256);
  });

  it('coalesces consecutive agent_update for same agent_id', () => {
    rc.bufferEvent({ type: 'agent_update', seq_no: 1, payload: { agent: 'scout_falcon', state: { status: 'active' } } });
    rc.bufferEvent({ type: 'agent_update', seq_no: 2, payload: { agent: 'scout_falcon', state: { status: 'busy' } } });
    rc.bufferEvent({ type: 'agent_update', seq_no: 3, payload: { agent: 'scout_falcon', state: { status: 'sleeping' } } });
    expect(rc.buffers.agent_update.length).toBe(1);
    expect(rc.buffers.agent_update[0].payload.state.status).toBe('sleeping');
    expect(rc.buffers.agent_update[0].seq_no).toBe(3);
  });

  it('does NOT coalesce when agent_id alternates', () => {
    rc.bufferEvent({ type: 'agent_update', seq_no: 1, payload: { agent: 'a' } });
    rc.bufferEvent({ type: 'agent_update', seq_no: 2, payload: { agent: 'b' } });
    rc.bufferEvent({ type: 'agent_update', seq_no: 3, payload: { agent: 'a' } });
    expect(rc.buffers.agent_update.length).toBe(3);
  });

  it('caps structured_error at 128', () => {
    for (let i = 0; i < 150; i++) {
      rc.bufferEvent({ type: 'structured_error', seq_no: i, payload: { i } });
    }
    expect(rc.buffers.structured_error.length).toBe(128);
    expect(rc.buffers.structured_error[0].payload.i).toBe(22);
  });

  it('keeps only last 16 heartbeats', () => {
    for (let i = 0; i < 20; i++) {
      rc.bufferEvent({ type: 'heartbeat', seq_no: i, payload: { i } });
    }
    expect(rc.buffers.heartbeat.length).toBe(16);
    expect(rc.buffers.heartbeat[0].payload.i).toBe(4);
  });

  it('keeps only last 8 state_sync events', () => {
    for (let i = 0; i < 12; i++) {
      rc.bufferEvent({ type: 'state_sync', seq_no: i, payload: { i } });
    }
    expect(rc.buffers.state_sync.length).toBe(8);
  });
});

describe('ReconnectionController heartbeat staleness', () => {
  let rc;
  beforeEach(() => {
    vi.useFakeTimers();
    rc = makeBridge().bridge.reconnect;
  });
  afterEach(() => { rc.destroy(); vi.useRealTimers(); });

  it('starts in ok state', () => {
    expect(rc.getHealth()).toBe('ok');
  });

  it('transitions to degraded when server_unix_ms is stale (>3× max_event_interval_ms)', () => {
    const now = Date.now();
    rc.onHeartbeat({
      server_unix_ms: now - 20000, // 20s old
      max_event_interval_ms: 5000, // threshold = 15s
      throttle_level: 'normal',
      drop_count: 0,
    });
    expect(rc.getHealth()).toBe('degraded');
  });

  it('transitions to degraded when throttle_level=degraded', () => {
    rc.onHeartbeat({
      server_unix_ms: Date.now(),
      max_event_interval_ms: 5000,
      throttle_level: 'degraded',
      drop_count: 5,
    });
    expect(rc.getHealth()).toBe('degraded');
  });

  it('recovers to ok when heartbeat becomes fresh again', () => {
    rc.onHeartbeat({ server_unix_ms: Date.now() - 20000, max_event_interval_ms: 5000, throttle_level: 'normal' });
    expect(rc.getHealth()).toBe('degraded');
    rc.onHeartbeat({ server_unix_ms: Date.now(), max_event_interval_ms: 5000, throttle_level: 'normal' });
    expect(rc.getHealth()).toBe('ok');
  });

  it('watchdog detects stale heartbeat after 15s of silence', () => {
    rc.onHeartbeat({ server_unix_ms: Date.now(), max_event_interval_ms: 5000, throttle_level: 'normal' });
    expect(rc.getHealth()).toBe('ok');
    vi.advanceTimersByTime(16000); // > 3 × 5000ms threshold
    expect(rc.getHealth()).toBe('degraded');
  });

  it('emits health change events', () => {
    const cb = vi.fn();
    rc.onHealthChange(cb);
    rc.onHeartbeat({ server_unix_ms: Date.now() - 20000, max_event_interval_ms: 5000, throttle_level: 'normal' });
    expect(cb).toHaveBeenCalledWith('degraded');
  });
});

describe('ReconnectionController.reconcile', () => {
  let bridge, rc, state;
  beforeEach(() => {
    const b = makeBridge();
    bridge = b.bridge; state = b.state; rc = bridge.reconnect;
  });
  afterEach(() => rc.destroy());

  it('discards buffered events with seq_no ≤ state_sync.seq_no', () => {
    rc.bufferEvent({ type: 'node_entry', seq_no: 1, payload: { i: 1 } });
    rc.bufferEvent({ type: 'node_entry', seq_no: 2, payload: { i: 2 } });
    rc.bufferEvent({ type: 'node_entry', seq_no: 3, payload: { i: 3 } });
    rc.bufferEvent({ type: 'node_entry', seq_no: 4, payload: { i: 4 } });
    rc.bufferEvent({ type: 'node_entry', seq_no: 5, payload: { i: 5 } });

    rc.reconcile(3, { pipeline_state: {}, agent_states: {}, job_queue: {} });

    // Events with seq_no 1,2,3 should be discarded
    // state.applyStateSync should be called once with the payload
    expect(state.applyStateSync).toHaveBeenCalledWith({ pipeline_state: {}, agent_states: {}, job_queue: {} });
    // Events with seq_no 4,5 should be dispatched (via bridge.dispatch)
    const calls = state.recordNodeEvent.mock.calls.map(c => c[0].i);
    expect(calls).toContain(4);
    expect(calls).toContain(5);
    expect(calls).not.toContain(1);
    expect(calls).not.toContain(2);
    expect(calls).not.toContain(3);
  });

  it('drains remaining events in ascending seq_no order', () => {
    rc.bufferEvent({ type: 'structured_error', seq_no: 10, payload: { i: 10 } });
    rc.bufferEvent({ type: 'agent_update', seq_no: 7, payload: { agent: 'a', state: {} } });
    rc.bufferEvent({ type: 'node_entry', seq_no: 12, payload: { i: 12 } });
    rc.bufferEvent({ type: 'heartbeat', seq_no: 5, payload: {} });

    // Intercept dispatch order
    const dispatched = [];
    const origDispatch = bridge.dispatch.bind(bridge);
    bridge.dispatch = (n) => { dispatched.push(n.seq_no); origDispatch(n); };

    rc.reconcile(6, { pipeline_state: {}, agent_states: {}, job_queue: {} });
    // seq_no 5 (heartbeat) also ≤ 6 → discarded
    // remaining: 7 (agent_update), 10 (structured_error), 12 (node_entry)
    expect(dispatched).toEqual([7, 10, 12]);
  });

  it('clears buffers after drain', () => {
    rc.bufferEvent({ type: 'node_entry', seq_no: 100, payload: {} });
    rc.reconcile(50, { pipeline_state: {}, agent_states: {}, job_queue: {} });
    expect(rc.buffers.node.length).toBe(0);
  });
});

describe('ReconnectionController integration with SSEBridge.dispatch', () => {
  it('state_sync with reconciling=true routes through reconcile()', () => {
    const { bridge } = makeBridge();
    const reconcileSpy = vi.spyOn(bridge.reconnect, 'reconcile');
    // Buffer some events first
    bridge.reconnect.bufferEvent({ type: 'node_entry', seq_no: 1, payload: {} });
    // Dispatch a reconciling state_sync
    bridge.dispatch({
      type: 'state_sync',
      seq_no: 5,
      payload: { reconciling: true, seq_no: 5, pipeline_state: {}, agent_states: {}, job_queue: {} },
    });
    expect(reconcileSpy).toHaveBeenCalledWith(5, expect.objectContaining({ reconciling: true }));
    bridge.reconnect.destroy();
  });

  it('state_sync with reconciling=false routes through applyStateSync directly', () => {
    const { bridge, state } = makeBridge();
    bridge.dispatch({
      type: 'state_sync',
      seq_no: 6,
      payload: { reconciling: false, pipeline_state: { a: 1 }, agent_states: {}, job_queue: {} },
    });
    expect(state.applyStateSync).toHaveBeenCalledWith(expect.objectContaining({ pipeline_state: { a: 1 } }));
    bridge.reconnect.destroy();
  });
});
