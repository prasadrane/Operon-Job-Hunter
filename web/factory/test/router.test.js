import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { Router } from '../router.js';

describe('Router', () => {
  let router;

  beforeEach(() => {
    // Reset URL
    window.history.replaceState(null, '', '/factory');
    router = new Router();
  });

  afterEach(() => {
    router.destroy();
  });

  it('should parse query params from URL', () => {
    window.history.replaceState(null, '', '/factory?zoom=1.5&focus=agent_1&mode=advanced');
    router = new Router();
    const params = router.getParams();
    expect(params.zoom).toBe('1.5');
    expect(params.focus).toBe('agent_1');
    expect(params.mode).toBe('advanced');
    router.destroy();
  });

  it('should push update to URL via pushState', () => {
    router.pushUpdate({ zoom: '2.0', focus: 'job_abc' });
    const url = new URL(window.location.href);
    expect(url.searchParams.get('zoom')).toBe('2.0');
    expect(url.searchParams.get('focus')).toBe('job_abc');
  });

  it('should preserve existing params when pushing partial update', () => {
    window.history.replaceState(null, '', '/factory?mode=beginner&zoom=1.0');
    router = new Router();
    router.pushUpdate({ focus: 'agent_x' });
    const url = new URL(window.location.href);
    expect(url.searchParams.get('mode')).toBe('beginner');
    expect(url.searchParams.get('zoom')).toBe('1.0');
    expect(url.searchParams.get('focus')).toBe('agent_x');
    router.destroy();
  });

  it('should persist last 5 views in localStorage', () => {
    for (let i = 0; i < 7; i++) {
      router.pushUpdate({ focus: `agent_${i}` });
    }
    const recent = router.getRecentViews();
    expect(recent.length).toBeLessThanOrEqual(5);
    // Most recent first
    expect(recent[0]).toContain('agent_6');
  });

  it('should generate copyable link', () => {
    router.pushUpdate({ zoom: '1.5', focus: 'job_1' });
    const link = router.copyLink();
    expect(link).toContain('zoom=1.5');
    expect(link).toContain('focus=job_1');
  });
});
