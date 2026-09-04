import { describe, it, expect, beforeEach } from 'vitest';
import { QueueBadge } from '../queue-badge.js';

describe('QueueBadge', () => {
  let badge;

  beforeEach(() => {
    badge = new QueueBadge('discovery');
  });

  it('should initialize with zone color', () => {
    expect(badge.zone).toBe('discovery');
    expect(badge.count).toBe(0);
    expect(badge.color).toBe('#3b82f6'); // blue for discovery
  });

  it('should set count', () => {
    badge.setCount(12);
    expect(badge.count).toBe(12);
  });

  it('should pulse when count increases', () => {
    badge.setCount(5);
    badge.pulse();

    expect(badge.isPulsing).toBe(true);
    expect(badge.pulseScale).toBeGreaterThan(1.0);

    // After 500ms, pulse should be done
    badge.update(500);
    expect(badge.isPulsing).toBe(false);
    expect(badge.pulseScale).toBe(1.0);
  });

  it('should auto-pulse when count increases', () => {
    badge.setCount(5);
    expect(badge.isPulsing).toBe(true);
  });
});
