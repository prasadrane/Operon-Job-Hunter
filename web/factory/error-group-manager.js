/**
 * Manages structured_error SSE events: groups by correlation_id,
 * assigns tiers to entities, maintains failure chains.
 *
 * Ring buffer: max 128 errors (drop oldest), per spec §10.
 */
export class ErrorGroupManager {
  /**
   * @param {Object} options
   * @param {number} options.maxCapacity - Max errors in ring buffer (default 128)
   */
  constructor(options = {}) {
    this.maxCapacity = options.maxCapacity || 128;

    // correlation_id → { correlationId, errors: [], rootError: null }
    this.groups = new Map();

    // Flat ring buffer of all errors (for pruning + capacity management)
    this.allErrors = [];

    // entityKey (agent_id or node) → { tier, correlationId, errorCode }
    this.entityTierMap = new Map();
  }

  /**
   * Add a structured_error event
   * @param {Object} errorEvent - { correlation_id, error_code, node, job_id, agent_id, tier, stack_trace, timestamp }
   */
  addError(errorEvent) {
    // Enforce ring buffer capacity
    while (this.allErrors.length >= this.maxCapacity) {
      const oldest = this.allErrors.shift();
      this._removeFromGroup(oldest);
    }

    this.allErrors.push(errorEvent);

    const { correlation_id, tier, agent_id, node, error_code } = errorEvent;

    // Ensure group exists
    if (!this.groups.has(correlation_id)) {
      this.groups.set(correlation_id, {
        correlationId: correlation_id,
        errors: [],
        rootError: null,
      });
    }

    const group = this.groups.get(correlation_id);
    group.errors.push(errorEvent);

    // Track root error (tier 1)
    if (tier === 1) {
      group.rootError = errorEvent;
    }

    // Update entity tier map (prefer higher tier — tier 1 > tier 2)
    if (agent_id) {
      this._setEntityTier(agent_id, tier, correlation_id, error_code);
    }
    if (node) {
      this._setEntityTier(node, tier, correlation_id, error_code);
    }
  }

  /**
   * Set entity tier, preferring lower tier number (tier 1 > tier 2 > tier 3)
   * @param {string} entityKey - agent_id or node
   * @param {number} tier - Error tier
   * @param {string} correlationId - Correlation ID
   * @param {string} errorCode - Error code
   */
  _setEntityTier(entityKey, tier, correlationId, errorCode) {
    const existing = this.entityTierMap.get(entityKey);
    if (!existing || tier < existing.tier) {
      this.entityTierMap.set(entityKey, {
        tier,
        correlationId,
        errorCode,
      });
    }
  }

  /**
   * Remove an error from its group (for ring buffer eviction)
   * @param {Object} errorEvent
   */
  _removeFromGroup(errorEvent) {
    const { correlation_id, agent_id, node } = errorEvent;
    const group = this.groups.get(correlation_id);
    if (!group) return;

    group.errors = group.errors.filter(e => e !== errorEvent);

    // Re-calculate root error
    group.rootError = group.errors.find(e => e.tier === 1) || null;

    // Remove group if empty
    if (group.errors.length === 0) {
      this.groups.delete(correlation_id);
    }

    // Clean up entity tier map (simplified: just remove; will be re-set if other errors remain)
    if (agent_id) this.entityTierMap.delete(agent_id);
    if (node) this.entityTierMap.delete(node);
  }

  /**
   * Get error group by correlation ID
   * @param {string} correlationId
   * @returns {Object|null} Group object { correlationId, errors, rootError }
   */
  getGroup(correlationId) {
    return this.groups.get(correlationId) || null;
  }

  /**
   * Get top N groups sorted by most recent root error timestamp
   * @param {number} maxGroups - Max groups to return (0 = all)
   * @returns {Array} Array of group objects with `hasMore` property
   */
  getTopGroups(maxGroups = 5) {
    const sorted = Array.from(this.groups.values())
      .sort((a, b) => {
        const aTime = a.rootError
          ? new Date(a.rootError.timestamp).getTime()
          : new Date(a.errors[0].timestamp).getTime();
        const bTime = b.rootError
          ? new Date(b.rootError.timestamp).getTime()
          : new Date(b.errors[0].timestamp).getTime();
        return bTime - aTime; // newest first
      });

    const limit = maxGroups === 0 ? sorted.length : maxGroups;
    const result = sorted.slice(0, limit);
    result.hasMore = sorted.length > limit;
    return result;
  }

  /**
   * Get error tier for entity (agent_id or node name)
   * @param {string} entityId - Agent ID or node name
   * @returns {number} Tier (0 = no error, 1/2/3)
   */
  getTierForEntity(entityId) {
    const entry = this.entityTierMap.get(entityId);
    return entry ? entry.tier : 0;
  }

  /**
   * Get error code and correlation ID for entity
   * @param {string} entityId - Agent ID or node name
   * @returns {Object|null} { tier, correlationId, errorCode } or null
   */
  getEntityErrorInfo(entityId) {
    return this.entityTierMap.get(entityId) || null;
  }

  /**
   * Prune errors older than maxAgeMs from reference time
   * @param {number} maxAgeMs - Maximum age in milliseconds
   * @param {number} nowMs - Reference time (default: Date.now())
   */
  pruneOlderThan(maxAgeMs, nowMs = Date.now()) {
    const cutoff = nowMs - maxAgeMs;
    const toRemove = [];

    for (const err of this.allErrors) {
      const errTime = new Date(err.timestamp).getTime();
      if (errTime < cutoff) {
        toRemove.push(err);
      }
    }

    for (const err of toRemove) {
      const idx = this.allErrors.indexOf(err);
      if (idx !== -1) {
        this.allErrors.splice(idx, 1);
        this._removeFromGroup(err);
      }
    }
  }

  /**
   * Total number of errors currently stored
   * @returns {number}
   */
  get totalErrorCount() {
    return this.allErrors.length;
  }
}
