import { ensurePanelStyles } from '../panel-styles.js';

/**
 * Render agent detail panel (spec §13A).
 * @param {Object} agent - Agent data
 * @param {Function} onClose - Called when panel closes
 * @returns {HTMLElement} Panel DOM element
 */
export function renderAgentPanel(agent, onClose) {
  ensurePanelStyles();

  const el = document.createElement('div');
  el.className = 'detail-panel';
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-modal', 'true');
  el.setAttribute('aria-labelledby', 'agent-panel-title');

  const progressPct = Math.round((agent.subtask_progress || 0) * 100);
  const statusClass = agent.status || 'idle';

  el.innerHTML = `
    <div class="panel-header">
      <div class="status-orb ${statusClass}" title="${statusClass}"></div>
      <div style="flex:1;min-width:0">
        <h2 class="panel-title" id="agent-panel-title">${escapeHtml(agent.name)}</h2>
        <div class="panel-subtitle">${escapeHtml(agent.role)} · ${escapeHtml(agent.status)}</div>
      </div>
      <button class="panel-close-btn" aria-label="Close panel" data-action="close">✕</button>
    </div>

    <div class="panel-section">
      <div class="panel-section-label">Current Task</div>
      <div class="panel-section-value">${agent.current_task ? escapeHtml(agent.current_task) : '<em style="color:#64748b">Idle</em>'}</div>
      ${agent.current_task ? `
        <div class="panel-progress" title="${progressPct}%">
          <div class="panel-progress-fill" style="width:${progressPct}%;background:#3b82f6"></div>
        </div>
        <div class="panel-progress-label">${progressPct}%</div>
      ` : ''}
    </div>

    <div class="panel-section">
      <div class="panel-stat-row">
        <span class="label">Workstation</span>
        <span class="value">${escapeHtml(agent.workstation || '—')}</span>
      </div>
      <div class="panel-stat-row">
        <span class="label">Uptime (7d)</span>
        <span class="value">${agent.uptime_pct != null ? agent.uptime_pct.toFixed(1) + '%' : '—'}</span>
      </div>
      <div class="panel-stat-row">
        <span class="label">Errors (7d)</span>
        <span class="value">${agent.error_count_7d ?? '—'}</span>
      </div>
    </div>

    <div class="panel-actions">
      <button class="panel-action-btn" data-action="view-logs">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        View Logs
      </button>
      <button class="panel-action-btn primary" data-action="pause">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
        Pause Agent
      </button>
      <button class="panel-action-btn" data-action="copy-id">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
        Copy ID
      </button>
    </div>
  `;

  // Wire up actions
  el.querySelector('[data-action="close"]').addEventListener('click', () => onClose && onClose());
  el.querySelector('[data-action="view-logs"]').addEventListener('click', () => {
    window.open(`/logs?agent=${encodeURIComponent(agent.id)}`, '_blank');
  });
  el.querySelector('[data-action="pause"]').addEventListener('click', async () => {
    try {
      await fetch(`/api/v2/agents/${encodeURIComponent(agent.id)}/pause`, { method: 'POST' });
    } catch (err) {
      console.error('Failed to pause agent:', err);
    }
  });
  el.querySelector('[data-action="copy-id"]').addEventListener('click', () => {
    navigator.clipboard.writeText(agent.id).catch(() => {});
  });

  return el;
}

function escapeHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
