/**
 * SSE Bridge — connects to /api/v2/factory/stream and routes events
 * to StateManager + EntityManager + ReconnectionController.
 *
 * Normalizes two backend event shapes into one canonical form:
 *   { type, seq_no, payload, raw }
 *
 * Backend emits two shapes:
 *   Shape A (direct): { type: 'state_sync', seq_no, ... } or { type: 'heartbeat', ... }
 *   Shape B (envelope from broadcast_subagent_event):
 *     { id, event: 'agent_update', payload: {...}, priority, timestamp }
 */
export class SSEBridge {
  /**
   * @param {import('./state.js').StateManager} state
   * @param {import('./entities.js').EntityManager} entities
   */
  constructor(state, entities) {
    this.state = state;
    this.entities = entities;
    /** @type {EventSource|null} */
    this.eventSource = null;
    /** @type {string|null} Last event id seen (for reconnect header) */
    this.lastEventId = null;
    /** @type {'connected'|'connecting'|'degraded'|'closed'} */
    this.connectionState = 'closed';
    /** @type {Map<string, Function>} */
    this.handlers = new Map();
    /** @type {ReconnectionController|null} */
    this.reconnect = null;
    /** Current url; stored for reconnect-with-Last-Event-ID retries */
    this._url = null;
    /** Retry delay (doubles on failure, capped at 30s) */
    this.retryDelayMs = 1000;
    this._retryTimer = null;
  }

  /** Open EventSource. Idempotent. */
  connect(url) {
    if (this.eventSource) this.disconnect();
    this._url = url;
    this.connectionState = 'connecting';
    this.reconnect = new ReconnectionController(this);
    this._bindEventSource(url);
  }

  disconnect() {
    if (this._retryTimer) { clearTimeout(this._retryTimer); this._retryTimer = null; }
    if (this.reconnect) { this.reconnect.destroy(); this.reconnect = null; }
    if (this.eventSource) {
      try { this.eventSource.close(); } catch (_) {}
      this.eventSource = null;
    }
    this.connectionState = 'closed';
  }

  /** Register a handler for a normalized event type. */
  on(type, handler) {
    this.handlers.set(type, handler);
  }

  /**
   * Normalize raw SSE payload → { type, seq_no, payload, raw }.
   * Handles both direct shapes ({type,...}) and envelope shapes ({id,event,payload,...}).
   * @param {Object} raw
   * @returns {{ type: string, seq_no: number, payload: Object, raw: Object }}
   */
  normalize(raw) {
    // Shape A — direct: { type: 'state_sync', seq_no, ... } or { type: 'heartbeat', ... }
    if (raw && typeof raw === 'object' && typeof raw.type === 'string') {
      return { type: raw.type, seq_no: raw.seq_no ?? raw.id ?? 0, payload: raw, raw };
    }
    // Shape B — envelope from broadcast_subagent_event:
    //   { id, event: 'agent_update', payload: {...}, priority, timestamp }
    if (raw && typeof raw === 'object' && typeof raw.event === 'string') {
      return { type: raw.event, seq_no: raw.id ?? 0, payload: raw.payload ?? {}, raw };
    }
    return { type: 'unknown', seq_no: 0, payload: raw, raw };
  }

  /**
   * Dispatch a normalized event to the registered handler.
   * No-op if no handler registered for that type.
   * @param {{ type: string, seq_no: number, payload: Object, raw: Object }} normalized
   */
  dispatch(normalized) {
    const h = this.handlers.get(normalized.type);
    if (h) {
      try { h(normalized.payload, normalized); }
      catch (err) { console.error(`[SSEBridge] handler for ${normalized.type} threw:`, err); }
    }
  }

  /** Register default handlers for every known backend event type. */
  _registerDefaultHandlers() {
    this.on('state_sync', (payload, normalized) => {
      if (payload && payload.reconciling) {
        this.reconnect?.reconcile(payload.seq_no, payload);
      } else {
        this.state.applyStateSync(payload);
      }
    });

    this.on('agent_update', (payload) => {
      // Envelope payload shape: { agent: 'scout_falcon', state: {...}, orchestrator_speech }
      const agentId = payload?.agent;
      const agentState = payload?.state;
      if (agentId && agentState) {
        this.state.applyAgentUpdate(agentId, agentState);
      }
    });

    this.on('node_entry', (payload) => {
      this.entities.handleNodeEntry?.(payload);
      this.state.recordNodeEvent(payload);
    });

    this.on('node_exit', (payload) => {
      this.entities.handleNodeExit?.(payload);
      this.state.recordNodeEvent(payload);
    });

    this.on('structured_error', (payload) => {
      this.entities.handleStructuredError?.(payload);
      this.state.recordError(payload);
    });

    this.on('heartbeat', (payload) => {
      this.reconnect?.onHeartbeat(payload);
    });

    this.on('log', (payload) => {
      this.state.appendLog(payload);
    });
  }

  /** Internal: open EventSource, wire message handler + reconnect. */
  _bindEventSource(url) {
    const es = new EventSource(url);
    this.eventSource = es;

    es.onopen = () => {
      this.connectionState = 'connected';
      this.retryDelayMs = 1000;
    };

    es.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        if (evt.lastEventId) this.lastEventId = evt.lastEventId;
        const normalized = this.normalize(data);
        // Feed every event into ring buffer for reconciliation
        this.reconnect?.bufferEvent(normalized);
        this.dispatch(normalized);
      } catch (err) {
        console.error('[SSEBridge] parse/dispatch error:', err);
      }
    };

    es.onerror = () => {
      this.connectionState = 'connecting';
      // EventSource auto-reconnects; we just track state and lastEventId
    };

    this._registerDefaultHandlers();
  }
}

/**
 * ReconnectionController — manages client-side ring buffers, heartbeat
 * staleness detection, and seq_no reconciliation.
 *
 * Ring buffer capacities (from spec Section 10):
 *   node_entry|node_exit: 64 — never drop (safety valve at 2× = 128)
 *   agent_update:         256 — coalesce consecutive same agent_id
 *   structured_error|log: 128 — drop oldest
 *   heartbeat:            16 — keep last 16
 *   state_sync:           8 — keep last 8
 */
export class ReconnectionController {
  /**
   * @param {SSEBridge} bridge - Owning bridge (for lastEventId + state + dispatch)
   */
  constructor(bridge) {
    this.bridge = bridge;
    /** Per-type ring buffers. node_entry+node_exit share a 64-slot buffer. */
    this.buffers = {
      node: [],            // node_entry | node_exit
      agent_update: [],
      structured_error: [], // also receives 'log' events
      heartbeat: [],
      state_sync: [],
    };
    this.CAP = { node: 64, agent_update: 256, structured_error: 128, heartbeat: 16, state_sync: 8 };
    /** Timestamp of last heartbeat received (client clock, ms) */
    this.lastHeartbeatAt = 0;
    /** Last heartbeat payload (for threshold calc) */
    this.lastHeartbeat = null;
    /** Watchdog interval handle */
    this._watchdogHandle = null;
    /** Watchdog tick interval (ms) — checks staleness every 1s */
    this.WATCHDOG_INTERVAL_MS = 1000;
    /** 'ok' | 'degraded' */
    this.healthState = 'ok';
    /** Subscribers to health state changes */
    this._healthSubs = [];
    this._startWatchdog();
  }

  /**
   * Push a normalized event into the correct ring buffer.
   * Applies per-type drop policy and coalescing.
   * @param {{ type: string, seq_no: number, payload: Object, raw: Object }} normalized
   */
  bufferEvent(normalized) {
    const t = normalized.type;
    if (t === 'node_entry' || t === 'node_exit') {
      // LIFECYCLE — never drop under normal conditions.
      // Safety valve at 2× cap prevents unbounded growth in pathological cases.
      this.buffers.node.push(normalized);
      if (this.buffers.node.length > this.CAP.node * 2) this.buffers.node.shift();
      return;
    }
    if (t === 'agent_update') {
      const buf = this.buffers.agent_update;
      const incomingAgent = normalized.payload?.agent;
      // Coalesce with last event if same agent_id
      if (buf.length > 0 && buf[buf.length - 1].payload?.agent === incomingAgent) {
        buf[buf.length - 1] = normalized; // replace
      } else {
        buf.push(normalized);
      }
      if (buf.length > this.CAP.agent_update) buf.shift();
      return;
    }
    if (t === 'structured_error' || t === 'log') {
      this.buffers.structured_error.push(normalized);
      if (this.buffers.structured_error.length > this.CAP.structured_error) {
        this.buffers.structured_error.shift();
      }
      return;
    }
    if (t === 'heartbeat') {
      this.buffers.heartbeat.push(normalized);
      if (this.buffers.heartbeat.length > this.CAP.heartbeat) {
        this.buffers.heartbeat.shift();
      }
      return;
    }
    if (t === 'state_sync') {
      this.buffers.state_sync.push(normalized);
      if (this.buffers.state_sync.length > this.CAP.state_sync) {
        this.buffers.state_sync.shift();
      }
      return;
    }
  }

  /**
   * Called by SSEBridge when a heartbeat arrives.
   * Updates staleness tracking; may trigger degraded transition.
   * @param {Object} hb - { server_unix_ms, throttle_level, max_event_interval_ms, drop_count, seq_no }
   */
  onHeartbeat(hb) {
    this.lastHeartbeatAt = Date.now();
    this.lastHeartbeat = hb;
    // Check staleness immediately
    const staleness = Date.now() - hb.server_unix_ms;
    const threshold = 3 * (hb.max_event_interval_ms ?? 5000);
    const shouldBeDegraded = staleness > threshold || hb.throttle_level === 'degraded';
    if (shouldBeDegraded && this.healthState !== 'degraded') {
      this.healthState = 'degraded';
      this._emitHealth();
    } else if (!shouldBeDegraded && this.healthState !== 'ok') {
      this.healthState = 'ok';
      this._emitHealth();
    }
  }

  /**
   * Reconcile: discard buffered events with seq_no ≤ N, apply state_sync,
   * drain remainder in ascending id order. Must run inside one rAF.
   * @param {number} seqNo - state_sync.seq_no
   * @param {Object} stateSyncPayload - full state_sync payload
   */
  reconcile(seqNo, stateSyncPayload) {
    // 1. Discard buffered events with seq_no ≤ N
    for (const key of Object.keys(this.buffers)) {
      this.buffers[key] = this.buffers[key].filter(e => (e.seq_no ?? 0) > seqNo);
    }
    // 2. Apply state_sync snapshot (full replace)
    this.bridge.state.applyStateSync(stateSyncPayload);
    // 3. Drain remaining buffered events in ascending seq_no order (merge-sort)
    const all = [];
    for (const buf of Object.values(this.buffers)) all.push(...buf);
    all.sort((a, b) => (a.seq_no ?? 0) - (b.seq_no ?? 0));
    for (const evt of all) this.bridge.dispatch(evt);
    // 4. Clear buffers after drain (they've been applied)
    for (const key of Object.keys(this.buffers)) this.buffers[key] = [];
  }

  /** Current health state: 'ok' | 'degraded' */
  getHealth() { return this.healthState; }

  /**
   * Subscribe to health changes. Returns unsubscribe function.
   * @param {Function} fn
   * @returns {Function}
   */
  onHealthChange(fn) {
    this._healthSubs.push(fn);
    return () => {
      const i = this._healthSubs.indexOf(fn);
      if (i >= 0) this._healthSubs.splice(i, 1);
    };
  }

  /** Get snapshot of all buffer lengths (for debugging / tests). */
  getBufferSnapshot() {
    return {
      node: this.buffers.node.length,
      agent_update: this.buffers.agent_update.length,
      structured_error: this.buffers.structured_error.length,
      heartbeat: this.buffers.heartbeat.length,
      state_sync: this.buffers.state_sync.length,
    };
  }

  /** Tear down watchdog timer. */
  destroy() {
    if (this._watchdogHandle) {
      clearInterval(this._watchdogHandle);
      this._watchdogHandle = null;
    }
  }

  /** @private — starts the heartbeat staleness watchdog (runs every 1s). */
  _startWatchdog() {
    this._watchdogHandle = setInterval(() => {
      if (!this.lastHeartbeat) return; // never received one yet
      const threshold = 3 * (this.lastHeartbeat.max_event_interval_ms ?? 5000);
      const since = Date.now() - this.lastHeartbeatAt;
      if (since > threshold && this.healthState !== 'degraded') {
        this.healthState = 'degraded';
        this._emitHealth();
      }
    }, this.WATCHDOG_INTERVAL_MS);
  }

  /** @private */
  _emitHealth() {
    for (const fn of this._healthSubs) {
      try { fn(this.healthState); } catch (err) { console.error('[Reconnect] health sub error:', err); }
    }
  }
}
