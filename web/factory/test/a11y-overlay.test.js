import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { A11yOverlay } from '../a11y-overlay.js';

class FakeCamera {
  constructor() { this.scale = 1; this.offsetX = 0; this.offsetY = 0; }
  worldToScreen(wx, wy) { return { x: wx * this.scale + this.offsetX, y: wy * this.scale + this.offsetY }; }
}

describe('A11yOverlay', () => {
  let overlay, container, camera;

  beforeEach(() => {
    container = document.createElement('div');
    const canvas = document.createElement('canvas');
    container.appendChild(canvas);
    document.body.appendChild(container);
    camera = new FakeCamera();
    overlay = new A11yOverlay(canvas, camera);
  });

  afterEach(() => {
    overlay.dispose();
    container.parentElement?.removeChild(container);
  });

  it('creates an #a11y-overlay root inside canvas parent', () => {
    const root = container.querySelector('#a11y-overlay');
    expect(root).toBeTruthy();
  });

  it('sync() creates one button per hit target with min 44px hit area', () => {
    const targets = [
      { id: 'agent-1', kind: 'agent', worldX: 100, worldY: 100, width: 20, height: 20, ariaLabel: 'Scout' },
      { id: 'job-1',   kind: 'job',   worldX: 200, worldY: 200, width: 60, height: 60, ariaLabel: 'Job A' },
    ];
    overlay.sync(targets);
    const root = container.querySelector('#a11y-overlay');
    const buttons = root.querySelectorAll('button');
    expect(buttons.length).toBe(2);

    // agent-1: 20px wide but min 44px
    const agentBtn = root.querySelector('button[data-id="agent-1"]');
    expect(parseInt(agentBtn.style.width, 10)).toBe(44);
    expect(parseInt(agentBtn.style.height, 10)).toBe(44);
    expect(agentBtn.getAttribute('aria-label')).toBe('Scout');

    // job-1: 60px wide (scale=1), bigger than 44
    const jobBtn = root.querySelector('button[data-id="job-1"]');
    expect(parseInt(jobBtn.style.width, 10)).toBe(60);
  });

  it('sync() removes stale buttons when targets shrink', () => {
    overlay.sync([{ id: 'a', kind: 'agent', worldX: 0, worldY: 0, width: 50, height: 50 }]);
    overlay.sync([]); // empty
    const root = container.querySelector('#a11y-overlay');
    expect(root.querySelectorAll('button').length).toBe(0);
  });

  it('focus on hit-area dispatches factory:focus-entity', () => {
    overlay.sync([{ id: 'agent-1', kind: 'agent', worldX: 0, worldY: 0, width: 50, height: 50 }]);
    let detail = null;
    const handler = (e) => { detail = e.detail; };
    window.addEventListener('factory:focus-entity', handler);
    const btn = container.querySelector('#a11y-overlay button');
    btn.dispatchEvent(new FocusEvent('focus', { bubbles: true }));
    expect(detail).toBeTruthy();
    expect(detail.id).toBe('agent-1');
    expect(detail.kind).toBe('agent');
    window.removeEventListener('factory:focus-entity', handler);
  });
});
