import { describe, it, expect, vi } from 'vitest';
import { renderZonePanel } from '../panels/zone-panel.js';

describe('renderZonePanel', () => {
  const sampleZone = {
    name: 'Discovery',
    stage: 1,
    queue: [
      { id: 'job1', company: 'TechCorp', title: 'SWE', wait_seconds: 120 },
      { id: 'job2', company: 'DataFlow', title: 'ML Engineer', wait_seconds: 300 },
      { id: 'job3', company: 'StartupXYZ', title: 'Full Stack', wait_seconds: 480 },
    ],
    avg_duration_seconds: 45,
    active_agents: 3,
  };

  it('should render zone name and stage', () => {
    const panel = renderZonePanel(sampleZone, () => {}, () => {});
    expect(panel.textContent).toContain('Discovery');
    expect(panel.textContent).toContain('Stage 1');
  });

  it('should render queue count and avg duration', () => {
    const panel = renderZonePanel(sampleZone, () => {}, () => {});
    expect(panel.textContent).toContain('3 jobs');
    expect(panel.textContent).toContain('45s');
  });

  it('should render queue rows for each job', () => {
    const panel = renderZonePanel(sampleZone, () => {}, () => {});
    const rows = panel.querySelectorAll('.panel-queue-row');
    expect(rows.length).toBe(3);
    expect(rows[0].textContent).toContain('TechCorp');
  });

  it('should call onInspectJob when > button clicked', () => {
    const onInspect = vi.fn();
    const panel = renderZonePanel(sampleZone, () => {}, onInspect);
    const inspectBtn = panel.querySelector('[data-action="inspect"]');
    inspectBtn.click();
    expect(onInspect).toHaveBeenCalledWith('job1');
  });

  it('should include Pause Zone and View Metrics actions', () => {
    const panel = renderZonePanel(sampleZone, () => {}, () => {});
    const buttons = Array.from(panel.querySelectorAll('button'));
    const labels = buttons.map(b => b.textContent.trim());
    expect(labels).toContain('Pause Zone');
    expect(labels).toContain('View Metrics');
  });
});
