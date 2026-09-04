import { describe, it, expect } from 'vitest';
import { renderJobPanel } from '../panels/job-panel.js';

describe('renderJobPanel', () => {
  const sampleJob = {
    id: 'job_abc123',
    company: 'TechCorp',
    title: 'Senior SWE',
    score: 87,
    stage: 'tailoring',
    status: 'active',
    subtask: 'Generating resume',
    progress: 0.6,
    artifacts: [
      { type: 'resume_pdf', url: '/api/pdf/job_abc123' },
      { type: 'cover_letter', url: '/api/cover/job_abc123' },
    ],
  };

  it('should render company, title, score, stage', () => {
    const panel = renderJobPanel(sampleJob, () => {});
    expect(panel.textContent).toContain('TechCorp');
    expect(panel.textContent).toContain('Senior SWE');
    expect(panel.textContent).toContain('87');
    expect(panel.textContent).toContain('tailoring');
  });

  it('should render pipeline stepper with 5 stages', () => {
    const panel = renderJobPanel(sampleJob, () => {});
    const steps = panel.querySelectorAll('.pipeline-stepper .step');
    expect(steps.length).toBe(5);
    // Current stage highlighted
    const activeStep = panel.querySelector('.pipeline-stepper .step.active');
    expect(activeStep.textContent.toLowerCase()).toContain('tailor');
  });

  it('should render progress bar with correct percentage', () => {
    const panel = renderJobPanel(sampleJob, () => {});
    const fill = panel.querySelector('.panel-progress-fill');
    expect(fill).not.toBeNull();
    expect(fill.style.width).toBe('60%');
  });

  it('should render artifact download buttons', () => {
    const panel = renderJobPanel(sampleJob, () => {});
    const links = panel.querySelectorAll('[data-action="download"]');
    expect(links.length).toBe(2);
  });

  it('should include Retry, Cancel, Copy ID action buttons', () => {
    const panel = renderJobPanel(sampleJob, () => {});
    const buttons = Array.from(panel.querySelectorAll('button'));
    const labels = buttons.map(b => b.textContent.trim());
    expect(labels).toContain('Retry Stage');
    expect(labels).toContain('Cancel Job');
    expect(labels).toContain('Copy ID');
  });

  it('should have role=dialog and aria-modal', () => {
    const panel = renderJobPanel(sampleJob, () => {});
    expect(panel.getAttribute('role')).toBe('dialog');
    expect(panel.getAttribute('aria-modal')).toBe('true');
  });
});
