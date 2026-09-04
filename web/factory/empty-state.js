import { ensurePanelStyles } from './panel-styles.js';

const HEALTH_LABELS = {
  ok:       { label: 'All systems go',     cls: 'ok' },
  warn:     { label: 'Some services degraded', cls: 'warn' },
  critical: { label: 'System errors detected', cls: 'critical' },
};

/**
 * Empty state overlay shown when 0 active jobs for > 5 seconds.
 * Displays idle factory illustration, CTA, and system health.
 */
export class EmptyStateOverlay {
  /**
   * @param {HTMLElement} overlayRoot - The #overlay-root container
   */
  constructor(overlayRoot) {
    this.overlayRoot = overlayRoot;
    this._el = null;
  }

  /**
   * Show the empty state overlay.
   * @param {'ok'|'warn'|'critical'} systemHealth - System health status
   */
  show(systemHealth = 'ok') {
    ensurePanelStyles();
    this.hide();

    const health = HEALTH_LABELS[systemHealth] || HEALTH_LABELS.ok;

    this._el = document.createElement('div');
    this._el.className = 'overlay empty-state-overlay';
    this._el.setAttribute('role', 'status');
    this._el.setAttribute('aria-live', 'polite');

    this._el.innerHTML = `
      <svg width="120" height="80" viewBox="0 0 120 80" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <!-- Idle conveyor belt -->
        <rect x="10" y="50" width="100" height="8" rx="4" fill="#1e293b" stroke="#334155" stroke-width="1"/>
        <circle cx="20" cy="54" r="3" fill="#475569"/>
        <circle cx="40" cy="54" r="3" fill="#475569"/>
        <circle cx="60" cy="54" r="3" fill="#475569"/>
        <circle cx="80" cy="54" r="3" fill="#475569"/>
        <circle cx="100" cy="54" r="3" fill="#475569"/>
        <!-- Factory building -->
        <rect x="35" y="20" width="50" height="30" rx="2" fill="#1e293b" stroke="#334155" stroke-width="1"/>
        <rect x="45" y="28" width="8" height="8" rx="1" fill="#0f172a" stroke="#475569" stroke-width="0.5"/>
        <rect x="58" y="28" width="8" height="8" rx="1" fill="#0f172a" stroke="#475569" stroke-width="0.5"/>
        <rect x="71" y="28" width="8" height="8" rx="1" fill="#0f172a" stroke="#475569" stroke-width="0.5"/>
        <!-- Chimney (no smoke = idle) -->
        <rect x="75" y="10" width="6" height="12" fill="#1e293b" stroke="#334155" stroke-width="1"/>
      </svg>

      <div class="empty-title">No active jobs in pipeline</div>
      <div class="empty-sub">Start a discovery scan to find new opportunities</div>

      <button class="panel-action-btn primary" data-action="scan" style="font-size:13px;padding:8px 20px">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        Scan for Jobs
      </button>

      <div class="system-health">
        <span class="system-health-dot ${health.cls}"></span>
        <span>System Status: ${health.label}</span>
      </div>
    `;

    // Wire scan button
    this._el.querySelector('[data-action="scan"]').addEventListener('click', () => {
      fetch('/api/v2/discovery/scan', { method: 'POST' }).catch(err => {
        console.error('Scan failed:', err);
      });
    });

    this.overlayRoot.appendChild(this._el);
  }

  /**
   * Hide the empty state overlay.
   */
  hide() {
    if (this._el && this._el.parentNode) {
      this._el.parentNode.removeChild(this._el);
    }
    this._el = null;
  }

  /**
   * @returns {boolean} True if overlay is currently visible
   */
  isVisible() {
    return this._el !== null;
  }
}
