import { ensurePanelStyles } from '../panel-styles.js';

const STAGES = [
  { key: 'discovery',  label: 'Discover' },
  { key: 'evaluation', label: 'Eval' },
  { key: 'tailoring',  label: 'Tailor' },
  { key: 'submission', label: 'Submit' },
  { key: 'lifecycle',  label: 'Lifecycle' },
];

const STAGE_COLORS = {
  discovery:  '#3b82f6',
  evaluation: '#10b981',
  tailoring:  '#f59e0b',
  submission: '#ef4444',
  lifecycle:  '#8b5cf6',
};

/**
 * Render job detail panel (spec §13A).
 * @param {Object} job - Job data
 * @param {Function} onClose - Callback to close panel
 * @returns {HTMLElement} Panel DOM element
 */
export function renderJobPanel(job, onClose) {
  ensurePanelStyles();

  const el = document.createElement('div');
  el.className = 'detail-panel';
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-modal', 'true');
  el.setAttribute('aria-labelledby', 'job-panel-title');

  const stageIdx = STAGES.findIndex(s => s.key === job.stage);
  const progressPct = Math.round((job.progress || 0) * 100);
  const stageColor = STAGE_COLORS[job.stage] || '#6b7280';

  // Build pipeline stepper
  const stepperHtml = STAGES.map((s, i) => {
    let cls = 'step';
    if (i < stageIdx) cls += ' done';
    else if (i === stageIdx) cls += ' active';
    const color = i === stageIdx ? stageColor : '';
    const style = color ? `color:${color};border-color:${color}` : '';
    const arrow = i < STAGES.length - 1 ? '<span class="arrow">→</span>' : '';
    return `<span class="${cls}" style="${style}">${s.label}</span>${arrow}`;
  }).join('');

  // Build artifact buttons
  const artifactHtml = (job.artifacts || []).map(a => `
    <a href="${escapeHtml(a.url)}" download class="panel-action-btn" data-action="download" data-type="${escapeHtml(a.type)}">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
      ${escapeHtml(formatArtifactType(a.type))}
    </a>
  `).join('');

  el.innerHTML = `
    <div class="panel-header">
      <div style="flex:1;min-width:0">
        <h2 class="panel-title" id="job-panel-title">${escapeHtml(job.company)} · ${escapeHtml(job.title)}</h2>
        <div class="panel-subtitle" style="display:flex;gap:6px;align-items:center;margin-top:4px">
          <span class="panel-badge" style="background:${scoreColor(job.score)};color:#fff">Score: ${job.score ?? '—'}</span>
          <span class="panel-badge" style="background:${stageColor};color:#fff">${escapeHtml(job.stage)}</span>
        </div>
      </div>
      <button class="panel-close-btn" aria-label="Close panel" data-action="close">✕</button>
    </div>

    <div class="panel-section">
      <div class="panel-section-label">Pipeline</div>
      <div class="pipeline-stepper">${stepperHtml}</div>
    </div>

    <div class="panel-section">
      <div class="panel-section-label">Current Subtask</div>
      <div class="panel-section-value">${job.subtask ? escapeHtml(job.subtask) : '<em style="color:#64748b">None</em>'}</div>
      ${job.subtask ? `
        <div class="panel-progress" title="${progressPct}%">
          <div class="panel-progress-fill" style="width:${progressPct}%;background:${stageColor}"></div>
        </div>
      ` : ''}
    </div>

    ${(job.artifacts || []).length > 0 ? `
      <div class="panel-section">
        <div class="panel-section-label">Artifacts</div>
        <div class="panel-actions" style="border:none;padding:0;margin-top:4px">
          ${artifactHtml}
        </div>
      </div>
    ` : ''}

    <div class="panel-actions">
      <button class="panel-action-btn primary" data-action="retry">Retry Stage</button>
      <button class="panel-action-btn danger" data-action="cancel">Cancel Job</button>
      <button class="panel-action-btn" data-action="copy-id">Copy ID</button>
    </div>
  `;

  // Wire up actions
  el.querySelector('[data-action="close"]').addEventListener('click', () => onClose && onClose());
  el.querySelector('[data-action="retry"]').addEventListener('click', async () => {
    if (!confirm(`Retry stage "${job.stage}" for job ${job.id}?`)) return;
    try {
      await fetch(`/api/v2/jobs/${encodeURIComponent(job.id)}/retry`, { method: 'POST' });
    } catch (err) { console.error('Retry failed:', err); }
  });
  el.querySelector('[data-action="cancel"]').addEventListener('click', async () => {
    if (!confirm(`Cancel job ${job.id}?`)) return;
    try {
      await fetch(`/api/v2/jobs/${encodeURIComponent(job.id)}/cancel`, { method: 'POST' });
    } catch (err) { console.error('Cancel failed:', err); }
  });
  el.querySelector('[data-action="copy-id"]').addEventListener('click', () => {
    navigator.clipboard.writeText(job.id).catch(() => {});
  });

  return el;
}

function scoreColor(score) {
  if (score >= 80) return '#10b981';
  if (score >= 60) return '#f59e0b';
  return '#ef4444';
}

function formatArtifactType(type) {
  const map = {
    resume_pdf: 'Resume PDF',
    cover_letter: 'Cover Letter',
    linkedin_pdf: 'LinkedIn PDF',
  };
  return map[type] || type.replace(/_/g, ' ');
}

function escapeHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
