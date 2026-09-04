/**
 * Event emitted when an error detail panel should open.
 * Panel content rendering is deferred to Phase 8.
 * This class only provides the data payload.
 */
export class ErrorPanelOpenEvent {
  /**
   * @param {Object} data
   * @param {string} data.correlationId - Correlation UUID
   * @param {number} data.tier - Error tier (1/2/3)
   * @param {string} data.errorCode - Error code (e.g., 'ERR_TIMEOUT')
   * @param {string} data.entityKey - Agent ID or node name that was clicked
   * @param {Array} data.failureChain - All errors in the correlation group, sorted by timestamp
   */
  constructor({ correlationId, tier, errorCode, entityKey, failureChain }) {
    this.correlationId = correlationId;
    this.tier = tier;
    this.errorCode = errorCode;
    this.entityKey = entityKey;
    this.failureChain = failureChain;
  }
}

/**
 * Wires click/keyboard events on error-affected entities to emit
 * a panel-open signal carrying tier + correlation data.
 *
 * Panel content rendering is Phase 8. This module only produces the
 * ErrorPanelOpenEvent data model.
 */
export class ErrorPanelTrigger {
  /**
   * @param {ErrorGroupManager} groupManager - Error group manager instance
   */
  constructor(groupManager) {
    this.groupManager = groupManager;
    this._listeners = [];
  }

  /**
   * Register a callback for panel-open events
   * @param {Function} callback - Receives ErrorPanelOpenEvent
   */
  onPanelOpen(callback) {
    this._listeners.push(callback);
  }

  /**
   * Remove a panel-open callback
   * @param {Function} callback
   */
  offPanelOpen(callback) {
    this._listeners = this._listeners.filter(cb => cb !== callback);
  }

  /**
   * Handle entity click (from interaction.js click handler)
   * @param {string} entityId - Agent ID or node name
   */
  handleEntityClick(entityId) {
    const event = this._buildEvent(entityId);
    if (event) {
      this._emit(event);
    }
  }

  /**
   * Handle keyboard input (from keyboard accessibility handler)
   * Only Enter key opens panel (per spec §9A)
   * @param {string} entityId - Agent ID or node name
   * @param {string} key - Key name ('Enter', 'Space', etc.)
   */
  handleKeyboard(entityId, key) {
    if (key !== 'Enter') return;

    const event = this._buildEvent(entityId);
    if (event) {
      this._emit(event);
    }
  }

  /**
   * Build ErrorPanelOpenEvent from entity ID
   * @param {string} entityId - Agent ID or node name
   * @returns {ErrorPanelOpenEvent|null} Event or null if entity has no error
   */
  _buildEvent(entityId) {
    const errorInfo = this.groupManager.getEntityErrorInfo(entityId);
    if (!errorInfo) return null;

    const group = this.groupManager.getGroup(errorInfo.correlationId);
    if (!group) return null;

    // Sort failure chain by timestamp (oldest first)
    const failureChain = [...group.errors].sort((a, b) => {
      return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
    });

    return new ErrorPanelOpenEvent({
      correlationId: errorInfo.correlationId,
      tier: errorInfo.tier,
      errorCode: errorInfo.errorCode,
      entityKey: entityId,
      failureChain,
    });
  }

  /**
   * Emit event to all listeners
   * @param {ErrorPanelOpenEvent} event
   */
  _emit(event) {
    for (const listener of this._listeners) {
      listener(event);
    }
  }
}
