import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { PanelManager } from '../panel-manager.js';
import { renderAgentPanel } from '../panels/agent-panel.js';

describe('PanelManager', () => {
  let manager;
  let panelRoot;

  beforeEach(() => {
    panelRoot = document.createElement('div');
    panelRoot.id = 'panel-root';
    document.body.appendChild(panelRoot);
    manager = new PanelManager(panelRoot);
  });

  afterEach(() => {
    manager.close();
    panelRoot.remove();
  });

  it('should open a panel and append to root', () => {
    const panel = document.createElement('div');
    panel.setAttribute('role', 'dialog');
    const trigger = document.createElement('button');
    document.body.appendChild(trigger);

    manager.open(panel, trigger);

    expect(panelRoot.contains(panel)).toBe(true);
    expect(manager.isOpen()).toBe(true);
    expect(manager.getActivePanel()).toBe(panel);
    trigger.remove();
  });

  it('should close panel and return focus to trigger', () => {
    const panel = document.createElement('div');
    panel.setAttribute('role', 'dialog');
    const trigger = document.createElement('button');
    document.body.appendChild(trigger);
    trigger.focus();

    manager.open(panel, trigger);
    manager.close();

    expect(manager.isOpen()).toBe(false);
    expect(panelRoot.contains(panel)).toBe(false);
    expect(document.activeElement).toBe(trigger);
    trigger.remove();
  });

  it('should close on Esc keydown', () => {
    const panel = document.createElement('div');
    panel.setAttribute('role', 'dialog');
    const trigger = document.createElement('button');
    document.body.appendChild(trigger);

    manager.open(panel, trigger);

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));

    expect(manager.isOpen()).toBe(false);
    trigger.remove();
  });

  it('should close previous panel when opening a new one', () => {
    const panel1 = document.createElement('div');
    panel1.setAttribute('role', 'dialog');
    const panel2 = document.createElement('div');
    panel2.setAttribute('role', 'dialog');
    const trigger = document.createElement('button');
    document.body.appendChild(trigger);

    manager.open(panel1, trigger);
    manager.open(panel2, trigger);

    expect(panelRoot.contains(panel1)).toBe(false);
    expect(panelRoot.contains(panel2)).toBe(true);
    expect(manager.getActivePanel()).toBe(panel2);
    trigger.remove();
  });
});

describe('renderAgentPanel', () => {
  it('should render agent name, role, status', () => {
    const panel = renderAgentPanel({
      id: 'agent_scout_falcon',
      name: 'Scout Falcon',
      role: 'Crawler',
      status: 'active',
      current_task: 'Scanning greenhouse jobs',
      subtask_progress: 0.8,
      workstation: 'Discovery Zone',
      uptime_pct: 98.7,
      error_count_7d: 2,
    });

    expect(panel.getAttribute('role')).toBe('dialog');
    expect(panel.textContent).toContain('Scout Falcon');
    expect(panel.textContent).toContain('Crawler');
    expect(panel.textContent).toContain('80%');
    expect(panel.textContent).toContain('98.7%');
    expect(panel.textContent).toContain('2');
  });

  it('should include action buttons', () => {
    const panel = renderAgentPanel({
      id: 'agent_cmd_apex',
      name: 'Commander Apex',
      role: 'Boss',
      status: 'active',
      current_task: null,
      subtask_progress: 0,
      workstation: 'Executive Suite',
      uptime_pct: 99.9,
      error_count_7d: 0,
    });

    const buttons = Array.from(panel.querySelectorAll('button'));
    const labels = buttons.map(b => b.textContent.trim());
    expect(labels).toContain('View Logs');
    expect(labels).toContain('Pause Agent');
    expect(labels).toContain('Copy ID');
  });
});
