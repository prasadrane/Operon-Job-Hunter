import { ensurePanelStyles } from '../panel-styles.js';

const TIER_COLORS = {
  1: '#ef4444', // red — critical
  2: '#f59e0b', // amber — warning
  3: '#3b82f6', // blue — info
};

/**
 * Render error detail panel (spec §13A).
 * @param {Object} error - Error data
 * @param {Function} onClose - Close callback
 * @returns {HTMLElement} Panel DOM element
 */
export function renderErrorPanel(error, onClose) {
  ensurePanelStyles();

  const el = document.createElement('div');
  el.className = 'detail-panel';
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-modal', 'true');
  el.setAttribute('aria-labelledby', 'error-panel-title');

  const tierColor = TIER_COLORS[error.tier] || '#6b7280';

  // Build failure chain timeline
  const timelineHtml = (error.failure_chain || []).map((item) => {
    const age = formatAge(item.timestamp);
    const cls = item.type === 'root' ? 'root' : '';
    return `<div class="panel-timeline-item ${cls}">[${escapeHtml(item.node)}] (${escapeHtml(item.type)}) · ${age}</div>`;
  }).join('');

  // Build recovery actions
  const actionsHtml = (error.recovery_actions || []).map((action) => {
    const cls = action.type === 'state-changing' ? 'danger' : '';
    return `<button class="panel-action-btn ${cls}" data-action="recovery" data-label="${escapeHtml(action.label)}" data-type="${escapeHtml(action.type)}">${escapeHtml(action.label)}</button>`;
  }).join('');

  el.innerHTML = `
    <div class="panel-header">
      <div style="flex:1;min-width:0">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
          <span class="panel-badge" style="background:${tierColor};color:#fff">Tier ${error.tier}</span>
          <h2 class="panel-title" id="error-panel-title" style="font-family:'SF Mono',Menlo,monospace;font-size:13px">${escapeHtml(error.code)}</h2>
        </div>
        <div class="panel-subtitle" style="font-family:'SF Mono',Menlo,monospace;font-size:10px">
          Correlation: ${escapeHtml(error.correlation_id)}
        </div>
      </div>
      <button class="panel-close-btn" aria-label="Close panel" data-action="close">✕</button>
    </div>

    <div class="panel-section">
      <div class="panel-stat-row">
        <span class="label">Node</span>
        <span class="value">${escapeHtml(error.node || '—')}</span>
      </div>
      <div class="panel-stat-row">
        <span class="label">Agent</span>
        <span class="value">${escapeHtml(error.agent || '—')}</span>
      </div>
      <div class="panel-stat-row">
        <span class="label">Job</span>
        <span class="value">${escapeHtml(error.job_label || error.job_id || '—')}</span>
      </div>
    </div>

    <div class="panel-section">
      <button class="panel-section-label" data-action="toggle-trace" style="cursor:pointer;background:none;border:none;padding:0;text-align:left;width:100%;display:flex;align-items:center;gap:4px">
        <span class="trace-chevron" style="transition:transform 150ms;display:inline-block">▼</span>
        Stack Trace
      </button>
      <div class="panel-stack-trace" data-trace-content>${escapeHtml(error.stack_trace || 'No stack trace available')}</div>
    </div>

    ${(error.failure_chain || []).length > 0 ? `
      <div class="panel-section">
        <div class="panel-section-label">Failure Chain (${error.failure_chain.length} errors)</div>
        <div class="panel-timeline">${timelineHtml}</div>
      </div>
    ` : ''}

    <div class="panel-actions">
      ${actionsHtml}
      <button class="panel-action-btn" data-action="copy-error">Copy Error</button>
    </div>
  `;

  // Wire close
  el.querySelector('[data-action="close"]').addEventListener('click', () => onClose && onClose());

  // Wire stack trace toggle
  const toggleBtn = el.querySelector('[data-action="toggle-trace"]');
  const traceContent = el.querySelector('[data-trace-content]');
  const chevron = toggleBtn.querySelector('.trace-chevron');
  let traceOpen = true;
  toggleBtn.addEventListener('click', () => {
    traceOpen = !traceOpen;
    traceContent.style.display = traceOpen ? '' : 'none';
    chevron.style.transform = traceOpen ? '' : 'rotate(-90deg)';
  });

  // Wire recovery actions
  el.querySelectorAll('[data-action="recovery"]').forEach(btn => {
    btn.addEventListener('click', () => {
      const label = btn.getAttribute('data-label');
      const type = btn.getAttribute('data-type');
      if (type === 'state-changing') {
        if (!confirm(`Action "${label}" will modify pipeline state. Continue?`)) return;
      }
      executeRecoveryAction(error, label);
    });
  });

  // Copy Error
  el.querySelector('[data-action="copy-error"]').addEventListener('click', () => {
    const text = `[${error.code}] ${error.correlation_id}\n${error.stack_trace || ''}`;
    navigator.clipboard.writeText(text).catch(() => {});
  });

  return el;
}

async function executeRecoveryAction(error, label) {
  try {
    if (label === 'Retry Stage') {
      await fetch(`/api/v2/jobs/${encodeURIComponent(error.job_id)}/retry`, { method: 'POST' });
    } else if (label === 'View Logs') {
      window.open(`/logs?correlation_id=${encodeURIComponent(error.correlation_id)}`, '_blank');
    } else if (label === 'Mark Manual') {
      await fetch(`/api/v2/jobs/${encodeURIComponent(error.job_id)}/mark-manual`, { method: 'POST' });
    } else if (label === 'Modify Input') {
      window.open(`/jobs/${encodeURIComponent(error.job_id)}/edit`, '_blank');
    }
  } catch (err) {
    console.error(`Recovery action "${label}" failed:`, err);
  }
}

function formatAge(timestamp) {
  if (!timestamp) return '—';
  const diffMs = Date.now() - timestamp;
  const seconds = Math.floor(diffMs / 1000);
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
