import { ensurePanelStyles } from './panel-styles.js';

/**
 * Standup meeting overlay — shown when Commander Apex calls a standup.
 * Displays banner with progress, elapsed time, overrun warning.
 */
export class StandupOverlay {
  /**
   * @param {HTMLElement} overlayRoot - The #overlay-root container
   */
  constructor(overlayRoot) {
    this.overlayRoot = overlayRoot;
    this._el = null;
    this._startedAt = null;
    this._expectedDuration = 300; // 5 min default
    this._tickInterval = null;
  }

  /**
   * Start the standup overlay.
   * @param {Object} meetingData - { started_at, expected_duration_sec, agenda }
   */
  start(meetingData) {
    ensurePanelStyles();
    this.stop();

    this._startedAt = meetingData.started_at || Date.now();
    this._expectedDuration = meetingData.expected_duration_sec || 300;

    this._el = document.createElement('div');
    this._el.className = 'overlay standup-overlay';
    this._el.setAttribute('role', 'status');
    this._el.setAttribute('aria-live', 'polite');

    this._render();

    this.overlayRoot.appendChild(this._el);

    // Update every second
    this._tickInterval = setInterval(() => this._render(), 1000);
  }

  /**
   * Stop the standup overlay.
   */
  stop() {
    if (this._tickInterval) {
      clearInterval(this._tickInterval);
      this._tickInterval = null;
    }
    if (this._el && this._el.parentNode) {
      this._el.parentNode.removeChild(this._el);
    }
    this._el = null;
    this._startedAt = null;
  }

  /**
   * Update progress display.
   * @param {number} elapsedSec - Seconds elapsed
   * @param {number} expectedSec - Expected duration
   */
  updateProgress(elapsedSec, expectedSec) {
    this._expectedDuration = expectedSec;
    this._render();
  }

  /**
   * @returns {boolean} True if standup is active
   */
  isActive() {
    return this._el !== null;
  }

  _render() {
    if (!this._el) return;

    const elapsed = Math.floor((Date.now() - this._startedAt) / 1000);
    const progressPct = Math.min(100, (elapsed / this._expectedDuration) * 100);
    const isOverrun = elapsed > this._expectedDuration;
    const elapsedLabel = formatDuration(elapsed);

    this._el.innerHTML = `
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" aria-hidden="true">
        <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
      </svg>
      <span style="font-weight:600">Standup in progress</span>
      <span style="color:#fde68a">— started ${elapsedLabel} ago</span>
      <div class="standup-progress" style="max-width:200px">
        <div class="standup-progress-fill" style="width:${progressPct}%;${isOverrun ? 'background:#ef4444' : ''}"></div>
      </div>
      ${isOverrun ? '<span class="standup-overrun">⚠ Overrun</span>' : ''}
    `;
  }
}

function formatDuration(seconds) {
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins < 60) return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m`;
}
