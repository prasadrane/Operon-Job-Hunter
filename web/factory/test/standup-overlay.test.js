import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { StandupOverlay } from '../standup-overlay.js';

describe('StandupOverlay', () => {
  let overlayRoot;
  let overlay;

  beforeEach(() => {
    overlayRoot = document.createElement('div');
    overlayRoot.id = 'overlay-root';
    document.body.appendChild(overlayRoot);
    overlay = new StandupOverlay(overlayRoot);
    vi.useFakeTimers();
  });

  afterEach(() => {
    overlay.stop();
    overlayRoot.remove();
    vi.useRealTimers();
  });

  it('should show standup banner when started', () => {
    overlay.start({ started_at: Date.now(), expected_duration_sec: 300 });
    expect(overlay.isActive()).toBe(true);
    expect(overlayRoot.textContent).toContain('Standup');
  });

  it('should show progress bar', () => {
    overlay.start({ started_at: Date.now(), expected_duration_sec: 300 });
    const progress = overlayRoot.querySelector('.standup-progress-fill');
    expect(progress).not.toBeNull();
  });

  it('should show overrun warning after expected duration', () => {
    overlay.start({ started_at: Date.now() - 360000, expected_duration_sec: 300 });
    overlay.updateProgress(360, 300);
    const overrun = overlayRoot.querySelector('.standup-overrun');
    expect(overrun).not.toBeNull();
  });

  it('should hide when stopped', () => {
    overlay.start({ started_at: Date.now(), expected_duration_sec: 300 });
    overlay.stop();
    expect(overlay.isActive()).toBe(false);
    expect(overlayRoot.children.length).toBe(0);
  });

  it('should show elapsed time', () => {
    overlay.start({ started_at: Date.now() - 120000, expected_duration_sec: 300 });
    overlay.updateProgress(120, 300);
    expect(overlayRoot.textContent).toContain('2m');
  });
});
