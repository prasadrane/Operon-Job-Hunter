import { ensurePanelStyles } from '../panel-styles.js';

const ZONE_COLORS = {
  discovery:  '#3b82f6',
  evaluation: '#10b981',
  tailoring:  '#f59e0b',
  submission: '#ef4444',
  lifecycle:  '#8b5cf6',
};

/**
 * Render zone queue panel (spec §13A).
 * @param {Object} zone - Zone data { name, stage, queue, avg_duration_seconds, active_agents }
 * @param {Function} onClose - Close callback
 * @param {Function} onInspectJob - Callback(jobId) when user clicks inspect on a row
 * @returns {HTMLElement} Panel DOM element
 */
export function renderZonePanel(zone, onClose, onInspectJob) {
  ensurePanelStyles();

  const el = document.createElement('div');
  el.className = 'detail-panel';
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-modal', 'true');
  el.setAttribute('aria-labelledby', 'zone-panel-title');

  const zoneKey = (zone.name || '').toLowerCase();
  const zoneColor = ZONE_COLORS[zoneKey] || '#6b7280';

  // Build queue rows
  const queueRowsHtml = (zone.queue || []).map((item, idx) => {
    const waitLabel = formatWait(item.wait_seconds);
    return `
      <div class="panel-queue-row" tabindex="0" data-job-id="${escapeHtml(item.id)}">
        <div style="flex:1;min-width:0">
          <div style="font-weight:600;color:#e2e8f0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
            ${escapeHtml(item.company)} ${escapeHtml(item.title)}
          </div>
          <div style="font-size:10px;color:#64748b;margin-top:1px">
            ${waitLabel} · Queue position: ${idx + 1}
          </div>
        </div>
        <button class="panel-action-btn" data-action="inspect" data-job-id="${escapeHtml(item.id)}" aria-label="Inspect job" style="padding:4px 8px">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
        </button>
      </div>
    `;
  }).join('');

  el.innerHTML = `
    <div class="panel-header">
      <div style="flex:1;min-width:0">
        <h2 class="panel-title" id="zone-panel-title" style="color:${zoneColor}">${escapeHtml(zone.name)} Zone</h2>
        <div class="panel-subtitle">Stage ${zone.stage || '?'} · ${zone.queue ? zone.queue.length : 0} jobs · Avg: ${zone.avg_duration_seconds ?? '—'}s</div>
      </div>
      <button class="panel-close-btn" aria-label="Close panel" data-action="close">✕</button>
    </div>

    <div class="panel-section">
      <div class="panel-section-label">Queue (newest first)</div>
      <div class="panel-queue-list">
        ${queueRowsHtml || '<div style="color:#64748b;font-size:12px;padding:8px;text-align:center">Queue empty</div>'}
      </div>
    </div>

    <div class="panel-section">
      <div class="panel-stat-row">
        <span class="label">Active Agents</span>
        <span class="value">${zone.active_agents ?? '—'}</span>
      </div>
    </div>

    <div class="panel-actions">
      <button class="panel-action-btn primary" data-action="pause-zone">Pause Zone</button>
      <button class="panel-action-btn" data-action="view-metrics">View Metrics</button>
    </div>
  `;

  // Wire actions
  el.querySelector('[data-action="close"]').addEventListener('click', () => onClose && onClose());

  el.querySelectorAll('[data-action="inspect"]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const jobId = btn.getAttribute('data-job-id');
      if (onInspectJob) onInspectJob(jobId);
    });
  });

  // Clicking row also inspects
  el.querySelectorAll('.panel-queue-row').forEach(row => {
    row.addEventListener('click', () => {
      const jobId = row.getAttribute('data-job-id');
      if (onInspectJob) onInspectJob(jobId);
    });
    row.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const jobId = row.getAttribute('data-job-id');
        if (onInspectJob) onInspectJob(jobId);
      }
    });
  });

  el.querySelector('[data-action="pause-zone"]').addEventListener('click', async () => {
    try {
      await fetch(`/api/v2/zones/${encodeURIComponent(zoneKey)}/pause`, { method: 'POST' });
    } catch (err) { console.error('Pause zone failed:', err); }
  });

  el.querySelector('[data-action="view-metrics"]').addEventListener('click', () => {
    window.open(`/metrics?zone=${encodeURIComponent(zoneKey)}`, '_blank');
  });

  return el;
}

function formatWait(seconds) {
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

function escapeHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
