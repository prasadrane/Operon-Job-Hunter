import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { EmptyStateOverlay } from '../empty-state.js';

describe('EmptyStateOverlay', () => {
  let overlayRoot;
  let overlay;

  beforeEach(() => {
    overlayRoot = document.createElement('div');
    overlayRoot.id = 'overlay-root';
    document.body.appendChild(overlayRoot);
    overlay = new EmptyStateOverlay(overlayRoot);
  });

  afterEach(() => {
    overlay.hide();
    overlayRoot.remove();
  });

  it('should show empty state with message', () => {
    overlay.show('ok');
    expect(overlay.isVisible()).toBe(true);
    const text = overlayRoot.textContent;
    expect(text).toContain('No active jobs');
  });

  it('should render Scan for Jobs CTA button', () => {
    overlay.show('ok');
    const btn = overlayRoot.querySelector('[data-action="scan"]');
    expect(btn).not.toBeNull();
    expect(btn.textContent).toContain('Scan for Jobs');
  });

  it('should render system health indicator', () => {
    overlay.show('warn');
    const dot = overlayRoot.querySelector('.system-health-dot');
    expect(dot).not.toBeNull();
    expect(dot.classList.contains('warn')).toBe(true);
  });

  it('should hide when hide() called', () => {
    overlay.show('ok');
    overlay.hide();
    expect(overlay.isVisible()).toBe(false);
    expect(overlayRoot.children.length).toBe(0);
  });
});
