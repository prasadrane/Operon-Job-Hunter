import { describe, it, expect, beforeEach, vi } from 'vitest';
import { SSEBridge } from '../sync.js';

// Minimal stubs — we don't want real PixiJS or EventSource
function makeState() {
  return {
    applyStateSync: vi.fn(),
    applyAgentUpdate: vi.fn(),
    recordNodeEvent: vi.fn(),
    recordError: vi.fn(),
    appendLog: vi.fn(),
  };
}
function makeEntities() {
  return {
    handleNodeEntry: vi.fn(),
    handleNodeExit: vi.fn(),
    handleStructuredError: vi.fn(),
  };
}

describe('SSEBridge.normalize', () => {
  let bridge;
  beforeEach(() => { bridge = new SSEBridge(makeState(), makeEntities()); });

  it('normalizes direct-shape state_sync', () => {
    const out = bridge.normalize({ type: 'state_sync', seq_no: 42, pipeline_state: {} });
    expect(out.type).toBe('state_sync');
    expect(out.seq_no).toBe(42);
    expect(out.payload.pipeline_state).toEqual({});
  });

  it('normalizes direct-shape heartbeat', () => {
    const out = bridge.normalize({
      type: 'heartbeat', server_unix_ms: 1000, throttle_level: 'normal',
      max_event_interval_ms: 5000, drop_count: 0,
    });
    expect(out.type).toBe('heartbeat');
    expect(out.payload.server_unix_ms).toBe(1000);
  });

  it('normalizes envelope-shape agent_update', () => {
    const out = bridge.normalize({
      id: 77, event: 'agent_update',
      payload: { agent: 'scout_falcon', state: { status: 'active' } },
      priority: 1, timestamp: '2026-08-25T00:00:00',
    });
    expect(out.type).toBe('agent_update');
    expect(out.seq_no).toBe(77);
    expect(out.payload.agent).toBe('scout_falcon');
  });

  it('returns type=unknown for garbage input', () => {
    expect(bridge.normalize(null).type).toBe('unknown');
    expect(bridge.normalize(42).type).toBe('unknown');
    expect(bridge.normalize({}).type).toBe('unknown');
  });
});

describe('SSEBridge.dispatch', () => {
  let bridge, state, entities;
  beforeEach(() => {
    state = makeState();
    entities = makeEntities();
    bridge = new SSEBridge(state, entities);
    bridge.reconnect = { onHeartbeat: vi.fn() };
    // Register default handlers (same as connect() does)
    bridge._registerDefaultHandlers();
  });

  it('routes state_sync to state.applyStateSync', () => {
    bridge.dispatch({ type: 'state_sync', seq_no: 1, payload: { pipeline_state: { a: 1 } } });
    expect(state.applyStateSync).toHaveBeenCalledWith({ pipeline_state: { a: 1 } });
  });

  it('routes agent_update to state.applyAgentUpdate', () => {
    bridge.dispatch({
      type: 'agent_update', seq_no: 2,
      payload: { agent: 'scout_falcon', state: { status: 'active' } },
    });
    expect(state.applyAgentUpdate).toHaveBeenCalledWith('scout_falcon', { status: 'active' });
  });

  it('routes node_entry to entities + state', () => {
    const p = { node: 'eval_node', job_id: 'j1', stage: 'evaluation' };
    bridge.dispatch({ type: 'node_entry', seq_no: 3, payload: p });
    expect(entities.handleNodeEntry).toHaveBeenCalledWith(p);
    expect(state.recordNodeEvent).toHaveBeenCalledWith(p);
  });

  it('routes node_exit to entities + state', () => {
    const p = { node: 'eval_node', job_id: 'j1' };
    bridge.dispatch({ type: 'node_exit', seq_no: 4, payload: p });
    expect(entities.handleNodeExit).toHaveBeenCalledWith(p);
    expect(state.recordNodeEvent).toHaveBeenCalledWith(p);
  });

  it('routes structured_error to entities + state', () => {
    const p = { correlation_id: 'c1', error_code: 'ERR_TIMEOUT', tier: 1 };
    bridge.dispatch({ type: 'structured_error', seq_no: 5, payload: p });
    expect(entities.handleStructuredError).toHaveBeenCalledWith(p);
    expect(state.recordError).toHaveBeenCalledWith(p);
  });

  it('routes heartbeat to reconnect.onHeartbeat', () => {
    const p = { server_unix_ms: 999, max_event_interval_ms: 5000 };
    bridge.dispatch({ type: 'heartbeat', seq_no: 6, payload: p });
    expect(bridge.reconnect.onHeartbeat).toHaveBeenCalledWith(p);
  });

  it('routes log to state.appendLog', () => {
    const p = { level: 'ERROR', message: 'boom' };
    bridge.dispatch({ type: 'log', seq_no: 7, payload: p });
    expect(state.appendLog).toHaveBeenCalledWith(p);
  });
});

describe('SSEBridge.connect', () => {
  it('creates EventSource with correct url', () => {
    global.EventSource = class {
      constructor(url) { this.url = url; this.readyState = 0; }
      close() {}
      addEventListener() {}
    };
    const bridge = new SSEBridge(makeState(), makeEntities());
    bridge.connect('/api/v2/factory/stream');
    expect(bridge.eventSource).not.toBeNull();
    expect(bridge.eventSource.url).toBe('/api/v2/factory/stream');
    bridge.disconnect();
  });

  it('disconnect closes EventSource', () => {
    const closed = { called: false };
    global.EventSource = class {
      constructor() { this.readyState = 1; }
      close() { closed.called = true; }
      addEventListener() {}
    };
    const bridge = new SSEBridge(makeState(), makeEntities());
    bridge.connect('/api/v2/factory/stream');
    bridge.disconnect();
    expect(closed.called).toBe(true);
    expect(bridge.connectionState).toBe('closed');
  });
});
