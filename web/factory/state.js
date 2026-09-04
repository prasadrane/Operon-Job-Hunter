/**
 * StateManager — single source of truth for the factory visualization.
 *
 * Holds:
 *   - pipeline_state: full pipeline snapshot (from state_sync)
 *   - agent_states: Map<agentId, latestState>
 *   - job_queue: { discovered, evaluation, tailored, applied }
 *
 * Dispatches to:
 *   - AgentManager (agent state changes)
 *   - JobManager (job queue changes)
 *   - Subscribers (generic event bus)
 *
 * Key semantics:
 *   - applyStateSync replaces all three stores atomically
 *   - applyAgentUpdate merges (shallow) into existing agent state
 *   - fadeAgentToUnknown sets status='unknown' but never removes entity
 *   - Bounded buffers: nodeEvents=64, errors=128, logs=128 (drop oldest)
 */
export class StateManager {
  constructor() {
    /** @type {Object} Latest pipeline_state snapshot from state_sync */
    this.pipelineState = {};
    /** @type {Map<string, Object>} agent_id → latest agent state */
    this.agentStates = new Map();
    /** @type {Object} job_queue snapshot (discovered/evaluation/tailored/applied) */
    this.jobQueue = { discovered: [], evaluation: [], tailored: [], applied: [] };
    /** @type {Array<Object>} Recent node_entry/node_exit events (bounded) */
    this.nodeEvents = [];
    /** @type {Array<Object>} Recent structured_error events (bounded) */
    this.errors = [];
    /** @type {Array<Object>} Recent log events (bounded) */
    this.logs = [];
    /** @type {Map<string, Function[]>} eventName → subscribers */
    this._subscribers = new Map();
    /** @type {import('./agent-manager.js').AgentManager|null} */
    this.agentManager = null;
    /** @type {import('./job-manager.js').JobManager|null} */
    this.jobManager = null;
    /** Bound node-event and error caps (matches ring buffer capacities) */
    this.NODE_EVENT_CAP = 64;
    this.ERROR_CAP = 128;
    this.LOG_CAP = 128;
  }

  /**
   * Wire downstream managers. Call once at startup.
   * Either may be null.
   * @param {{ agentManager?: Object, jobManager?: Object }} managers
   */
  attach({ agentManager, jobManager } = {}) {
    this.agentManager = agentManager ?? null;
    this.jobManager = jobManager ?? null;
  }

  /**
   * Replace pipeline_state/agent_states/job_queue from a state_sync payload.
   * Dispatches each agent to AgentManager, each job bucket to JobManager.
   * @param {Object} payload - { pipeline_state, agent_states, job_queue }
   */
  applyStateSync(payload) {
    if (!payload || typeof payload !== 'object') return;
    if (payload.pipeline_state) this.pipelineState = payload.pipeline_state;
    if (payload.agent_states && typeof payload.agent_states === 'object') {
      this.agentStates.clear();
      for (const [agentId, state] of Object.entries(payload.agent_states)) {
        this.agentStates.set(agentId, { ...state });
        this.agentManager?.updateAgentState(agentId, state);
      }
    }
    if (payload.job_queue && typeof payload.job_queue === 'object') {
      this.jobQueue = {
        discovered: payload.job_queue.discovered ?? [],
        evaluation: payload.job_queue.evaluation ?? [],
        tailored: payload.job_queue.tailored ?? [],
        applied: payload.job_queue.applied ?? [],
      };
      // Push each bucket into JobManager if attached
      if (this.jobManager) {
        for (const job of this.jobQueue.discovered) {
          this.jobManager.updateJob?.({ ...job, stage: 'discovery', status: 'queued' });
        }
        for (const job of this.jobQueue.evaluation) {
          this.jobManager.updateJob?.({ ...job, stage: 'evaluation', status: 'queued' });
        }
        for (const job of this.jobQueue.tailored) {
          this.jobManager.updateJob?.({ ...job, stage: 'tailoring', status: 'queued' });
        }
        for (const job of this.jobQueue.applied) {
          this.jobManager.updateJob?.({ ...job, stage: 'submission', status: 'queued' });
        }
      }
    }
    this._emit('state_sync', this.getSnapshot());
  }

  /**
   * Merge one agent_update into stored state; dispatch to AgentManager.
   * @param {string} agentId
   * @param {Object} state - fields to merge
   */
  applyAgentUpdate(agentId, state) {
    if (!agentId || !state || typeof state !== 'object') return;
    const prev = this.agentStates.get(agentId) ?? {};
    const merged = { ...prev, ...state };
    this.agentStates.set(agentId, merged);
    this.agentManager?.updateAgentState(agentId, merged);
    this._emit('agent_update', { agentId, state: merged });
  }

  /**
   * Record a node_entry or node_exit event, capped at 64 (drops oldest).
   * @param {Object} event
   */
  recordNodeEvent(event) {
    this.nodeEvents.push(event);
    if (this.nodeEvents.length > this.NODE_EVENT_CAP) {
      this.nodeEvents.shift();
    }
    this._emit('node_event', event);
  }

  /**
   * Record a structured_error, capped at 128 (drops oldest).
   * @param {Object} error
   */
  recordError(error) {
    this.errors.push(error);
    if (this.errors.length > this.ERROR_CAP) this.errors.shift();
    this._emit('error', error);
  }

  /**
   * Record a log event, capped at 128 (drops oldest).
   * @param {Object} log
   */
  appendLog(log) {
    this.logs.push(log);
    if (this.logs.length > this.LOG_CAP) this.logs.shift();
    this._emit('log', log);
  }

  /**
   * Get full state snapshot (for renderers / debugging).
   * @returns {Object}
   */
  getSnapshot() {
    return {
      pipeline_state: this.pipelineState,
      agent_states: Object.fromEntries(this.agentStates),
      job_queue: this.jobQueue,
      node_events: this.nodeEvents,
      errors: this.errors,
      logs: this.logs,
    };
  }

  /**
   * Get current state of one agent, or null.
   * @param {string} agentId
   * @returns {Object|null}
   */
  getAgentState(agentId) {
    return this.agentStates.get(agentId) ?? null;
  }

  /**
   * Get all agent states as a plain object.
   * @returns {Object}
   */
  getAllAgentStates() {
    return Object.fromEntries(this.agentStates);
  }

  /** Get current pipeline_state. */
  getPipelineState() { return this.pipelineState; }

  /** Get current job_queue. */
  getJobQueue() { return this.jobQueue; }

  /**
   * Subscribe to a state-change event.
   * Events: 'state_sync', 'agent_update', 'node_event', 'error', 'log'
   * @param {string} eventName
   * @param {Function} fn
   * @returns {Function} unsubscribe function
   */
  subscribe(eventName, fn) {
    if (!this._subscribers.has(eventName)) this._subscribers.set(eventName, []);
    this._subscribers.get(eventName).push(fn);
    return () => {
      const arr = this._subscribers.get(eventName);
      if (!arr) return;
      const i = arr.indexOf(fn);
      if (i >= 0) arr.splice(i, 1);
    };
  }

  /**
   * Fade an agent to 'unknown' (dimmed sprite). Never removes entity.
   * Used by ReconnectionController when heartbeat staleness threshold exceeded.
   * @param {string} agentId
   */
  fadeAgentToUnknown(agentId) {
    const prev = this.agentStates.get(agentId);
    if (!prev) return;
    const faded = { ...prev, status: 'unknown' };
    this.agentStates.set(agentId, faded);
    this.agentManager?.updateAgentState(agentId, faded);
    this._emit('agent_update', { agentId, state: faded });
  }

  /** @private */
  _emit(eventName, data) {
    const arr = this._subscribers.get(eventName);
    if (!arr) return;
    for (const fn of arr) {
      try { fn(data); } catch (err) { console.error(`[StateManager] subscriber error (${eventName}):`, err); }
    }
  }
}
