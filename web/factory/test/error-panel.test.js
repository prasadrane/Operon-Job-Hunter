import { describe, it, expect, vi } from 'vitest';
import { renderErrorPanel } from '../panels/error-panel.js';

describe('renderErrorPanel', () => {
  const sampleError = {
    tier: 1,
    code: 'ERR_TIMEOUT',
    correlation_id: 'abc-123-def',
    node: 'eval_node',
    agent: 'Judge Minerva',
    job_id: 'job_abc123',
    job_label: 'TechCorp SWE',
    stack_trace: 'TimeoutError: 45s budget exceeded\n  at state_machine.py:123\n  at rubric_evaluator.py:456',
    failure_chain: [
      { node: 'eval_node', type: 'root', timestamp: Date.now() - 120000 },
      { node: 'tailor_node', type: 'downstream', timestamp: Date.now() - 60000 },
      { node: 'submit_node', type: 'indirect', timestamp: Date.now() - 30000 },
    ],
    recovery_actions: [
      { label: 'Retry Stage', type: 'state-changing' },
      { label: 'View Logs', type: 'safe' },
      { label: 'Mark Manual', type: 'state-changing' },
      { label: 'Copy Error', type: 'safe' },
    ],
  };

  it('should render tier badge, error code, correlation ID', () => {
    const panel = renderErrorPanel(sampleError, () => {});
    expect(panel.textContent).toContain('Tier 1');
    expect(panel.textContent).toContain('ERR_TIMEOUT');
    expect(panel.textContent).toContain('abc-123-def');
  });

  it('should render context: node, agent, job', () => {
    const panel = renderErrorPanel(sampleError, () => {});
    expect(panel.textContent).toContain('eval_node');
    expect(panel.textContent).toContain('Judge Minerva');
    expect(panel.textContent).toContain('TechCorp SWE');
  });

  it('should render collapsible stack trace', () => {
    const panel = renderErrorPanel(sampleError, () => {});
    const trace = panel.querySelector('.panel-stack-trace');
    expect(trace).not.toBeNull();
    expect(trace.textContent).toContain('TimeoutError');
    // Check toggle button exists
    const toggle = panel.querySelector('[data-action="toggle-trace"]');
    expect(toggle).not.toBeNull();
  });

  it('should render failure chain with 3 items', () => {
    const panel = renderErrorPanel(sampleError, () => {});
    const items = panel.querySelectorAll('.panel-timeline-item');
    expect(items.length).toBe(3);
    expect(items[0].classList.contains('root')).toBe(true);
  });

  it('should render ≥2 recovery actions', () => {
    const panel = renderErrorPanel(sampleError, () => {});
    const actionBtns = panel.querySelectorAll('.panel-actions .panel-action-btn');
    expect(actionBtns.length).toBeGreaterThanOrEqual(2);
  });

  it('should classify safe vs state-changing actions', () => {
    const panel = renderErrorPanel(sampleError, () => {});
    const dangerBtns = panel.querySelectorAll('.panel-action-btn.danger');
    // state-changing actions should have danger class
    expect(dangerBtns.length).toBeGreaterThanOrEqual(1);
  });
});
