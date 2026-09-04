import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { TooltipManager } from '../tooltip.js';

describe('TooltipManager', () => {
  let tooltip, root;

  beforeEach(() => {
    root = document.createElement('div');
    document.body.appendChild(root);
    tooltip = new TooltipManager(root);
  });

  afterEach(() => {
    tooltip.dispose();
    root.remove();
  });

  it('is hidden by default', () => {
    expect(tooltip.isVisible).toBe(false);
  });

  it('show() makes tooltip visible with text', () => {
    tooltip.show('Hello agent', 100, 200, { variant: 'agent' });
    expect(tooltip.isVisible).toBe(true);
    expect(root.textContent).toContain('Hello agent');
  });

  it('positions tooltip near cursor, clamped to root bounds', () => {
    Object.defineProperty(root, 'getBoundingClientRect', {
      value: () => ({ left: 0, top: 0, right: 800, bottom: 600, width: 800, height: 600 }),
    });
    tooltip.show('x', 790, 590);
    const el = root.querySelector('[data-tooltip]');
    // Should be shifted left/up to avoid overflow
    expect(parseInt(el.style.left, 10)).toBeLessThan(790);
  });

  it('hide() hides tooltip', () => {
    tooltip.show('x', 0, 0);
    tooltip.hide();
    expect(tooltip.isVisible).toBe(false);
  });
});
