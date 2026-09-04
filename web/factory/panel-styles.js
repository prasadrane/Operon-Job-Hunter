/**
 * Shared CSS for all detail panels.
 * Injected once into <head> on first panel open.
 */

const STYLES = `
/* --- Panel root --- */
#panel-root {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  pointer-events: none;
  z-index: 100;
}
#panel-root > .detail-panel {
  pointer-events: auto;
}

/* --- Detail panel base --- */
.detail-panel {
  position: fixed;
  right: 16px;
  top: 50%;
  transform: translateY(-50%);
  width: 380px;
  max-width: calc(100vw - 32px);
  max-height: 400px;
  overflow-y: auto;
  background: #0d121f;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.6);
  padding: 16px;
  font-family: system-ui, -apple-system, sans-serif;
  color: #e2e8f0;
  animation: panel-fade-in 150ms ease-out;
}

@keyframes panel-fade-in {
  from { opacity: 0; transform: translateY(-50%) translateX(8px); }
  to   { opacity: 1; transform: translateY(-50%) translateX(0); }
}

@media (prefers-reduced-motion: reduce) {
  .detail-panel { animation: none; }
}

/* --- Panel header --- */
.panel-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.panel-header .panel-title {
  font-size: 14px;
  font-weight: 700;
  color: #f1f5f9;
  margin: 0;
}
.panel-header .panel-subtitle {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 2px;
}
.panel-close-btn {
  margin-left: auto;
  background: none;
  border: none;
  color: #94a3b8;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  line-height: 1;
}
.panel-close-btn:hover,
.panel-close-btn:focus-visible {
  background: rgba(255,255,255,0.08);
  color: #f1f5f9;
  outline: 2px solid #3b82f6;
  outline-offset: 1px;
}

/* --- Panel sections --- */
.panel-section {
  margin-bottom: 12px;
}
.panel-section-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
  margin-bottom: 4px;
}
.panel-section-value {
  font-size: 12px;
  color: #e2e8f0;
}

/* --- Progress bar --- */
.panel-progress {
  height: 6px;
  background: rgba(255,255,255,0.06);
  border-radius: 3px;
  overflow: hidden;
  margin-top: 4px;
}
.panel-progress-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 200ms ease;
}

/* --- Action row --- */
.panel-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(255,255,255,0.06);
}
.panel-action-btn {
  font-size: 11px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.04);
  color: #e2e8f0;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: background 100ms;
}
.panel-action-btn:hover,
.panel-action-btn:focus-visible {
  background: rgba(255,255,255,0.1);
  outline: 2px solid #3b82f6;
  outline-offset: 1px;
}
.panel-action-btn.primary {
  background: #3b82f6;
  border-color: #3b82f6;
  color: #fff;
}
.panel-action-btn.primary:hover {
  background: #2563eb;
}
.panel-action-btn.danger {
  background: rgba(239,68,68,0.15);
  border-color: rgba(239,68,68,0.3);
  color: #fca5a5;
}
.panel-action-btn.danger:hover {
  background: rgba(239,68,68,0.25);
}

/* --- Status orb --- */
.status-orb {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}
.status-orb.active   { background: #22c55e; box-shadow: 0 0 6px #22c55e; }
.status-orb.idle     { background: #94a3b8; }
.status-orb.paused   { background: #f59e0b; }
.status-orb.error    { background: #ef4444; box-shadow: 0 0 6px #ef4444; }

/* --- Stat row --- */
.panel-stat-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  padding: 4px 0;
}
.panel-stat-row .label { color: #94a3b8; }
.panel-stat-row .value { color: #e2e8f0; font-family: 'SF Mono', Menlo, monospace; }

/* --- Badge --- */
.panel-badge {
  display: inline-block;
  font-size: 10px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 10px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-family: 'SF Mono', Menlo, monospace;
}

/* --- Queue list --- */
.panel-queue-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 180px;
  overflow-y: auto;
}
.panel-queue-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  background: rgba(255,255,255,0.03);
  font-size: 12px;
  cursor: pointer;
  border: 1px solid transparent;
}
.panel-queue-row:hover,
.panel-queue-row:focus-visible {
  background: rgba(255,255,255,0.08);
  border-color: rgba(255,255,255,0.1);
  outline: none;
}

/* --- Stack trace (error panel) --- */
.panel-stack-trace {
  font-family: 'SF Mono', Menlo, monospace;
  font-size: 11px;
  line-height: 1.5;
  background: #07090e;
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 6px;
  padding: 8px;
  color: #fca5a5;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 160px;
  overflow-y: auto;
}

/* --- Failure chain timeline --- */
.panel-timeline {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-left: 12px;
  border-left: 2px solid rgba(255,255,255,0.1);
}
.panel-timeline-item {
  font-size: 11px;
  color: #cbd5e1;
  position: relative;
  padding: 2px 0;
}
.panel-timeline-item::before {
  content: '';
  position: absolute;
  left: -16px;
  top: 8px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ef4444;
}
.panel-timeline-item.root::before { background: #f59e0b; }

/* --- Overlay base --- */
#overlay-root {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  pointer-events: none;
  z-index: 50;
}
#overlay-root > .overlay {
  pointer-events: auto;
}

/* --- Empty state overlay --- */
.empty-state-overlay {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  color: #e2e8f0;
  animation: panel-fade-in 300ms ease-out;
}
.empty-state-overlay .empty-title {
  font-size: 18px;
  font-weight: 600;
  margin: 16px 0 8px;
}
.empty-state-overlay .empty-sub {
  font-size: 13px;
  color: #94a3b8;
  margin-bottom: 20px;
}
.system-health {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #94a3b8;
  margin-top: 16px;
}
.system-health-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
}
.system-health-dot.ok      { background: #22c55e; box-shadow: 0 0 6px #22c55e; }
.system-health-dot.warn    { background: #f59e0b; }
.system-health-dot.critical{ background: #ef4444; box-shadow: 0 0 6px #ef4444; }

/* --- Standup overlay --- */
.standup-overlay {
  position: absolute;
  top: 0; left: 0; right: 0;
  padding: 12px 16px;
  background: linear-gradient(180deg, rgba(245,158,11,0.15), transparent);
  border-bottom: 1px solid rgba(245,158,11,0.3);
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: #fef3c7;
}
.standup-progress {
  flex: 1;
  height: 4px;
  background: rgba(255,255,255,0.1);
  border-radius: 2px;
  overflow: hidden;
}
.standup-progress-fill {
  height: 100%;
  background: #f59e0b;
  border-radius: 2px;
  transition: width 1s linear;
}
.standup-overrun {
  color: #fbbf24;
  font-weight: 700;
  animation: pulse-amber 1.5s ease-in-out infinite;
}
@keyframes pulse-amber {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* --- Pipeline stepper (job panel) --- */
.pipeline-stepper {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
}
.pipeline-stepper .step {
  padding: 3px 8px;
  border-radius: 4px;
  background: rgba(255,255,255,0.04);
  color: #64748b;
  border: 1px solid rgba(255,255,255,0.06);
}
.pipeline-stepper .step.active {
  color: #fff;
  border-color: currentColor;
}
.pipeline-stepper .step.done {
  background: rgba(34,197,94,0.15);
  color: #86efac;
  border-color: rgba(34,197,94,0.3);
}
.pipeline-stepper .arrow {
  color: #475569;
}
`;

let injected = false;

export function ensurePanelStyles() {
  if (injected) return;
  injected = true;
  const style = document.createElement('style');
  style.textContent = STYLES;
  document.head.appendChild(style);
}
