import { describe, it, expect, beforeEach } from 'vitest';
import { ErrorGlow, ERROR_VIS } from '../error-glow.js';

describe('ErrorGlow', () => {
  let glow;

  beforeEach(() => {
    glow = new ErrorGlow();
  });

  it('should initialize with no error (tier 0)', () => {
    expect(glow.tier).toBe(0);
    expect(glow.isActive).toBe(false);
    expect(glow.errorCode).toBe('');
  });

  it('should set tier 1 (root cause) with error code', () => {
    glow.setTier(1, 'ERR_TIMEOUT');
    expect(glow.tier).toBe(1);
    expect(glow.errorCode).toBe('ERR_TIMEOUT');
    expect(glow.isActive).toBe(true);
  });

  it('should set tier 2 (direct downstream) with no error code badge', () => {
    glow.setTier(2, null);
    expect(glow.tier).toBe(2);
    expect(glow.errorCode).toBe(null);
    expect(glow.isActive).toBe(true);
  });

  it('should pulse tier 1 glow alpha between 0.0 and 0.3 over 2s cycle', () => {
    glow.setTier(1, 'ERR_TIMEOUT');

    // At t=0, alpha should be at min (0.0)
    glow.update(0);
    expect(glow.glowAlpha).toBeCloseTo(0.0, 2);

    // At t=1000ms (halfway), alpha should be at max (0.3)
    glow.update(1000);
    expect(glow.glowAlpha).toBeCloseTo(0.3, 2);

    // At t=2000ms (full cycle), alpha should return to min (0.0)
    glow.update(1000);
    expect(glow.glowAlpha).toBeCloseTo(0.0, 2);
  });

  it('should NOT pulse tier 2 (static amber outline)', () => {
    glow.setTier(2, null);

    glow.update(500);
    expect(glow.glowAlpha).toBe(0); // tier 2 has no glow
    expect(glow.outlineAlpha).toBe(1.0); // static outline
  });

  it('should return correct render data for tier 1', () => {
    glow.setTier(1, 'ERR_TIMEOUT');
    glow.update(0);

    const data = glow.getRenderData();
    expect(data.tier).toBe(1);
    expect(data.glowColor).toBe('#ef4444');
    expect(data.glowAlpha).toBeCloseTo(0.0, 2);
    expect(data.outlineColor).toBeNull();
    expect(data.showBadge).toBe(true);
    expect(data.badgeText).toBe('ERR_TIMEOUT');
  });

  it('should return correct render data for tier 2', () => {
    glow.setTier(2, null);

    const data = glow.getRenderData();
    expect(data.tier).toBe(2);
    expect(data.glowColor).toBeNull();
    expect(data.glowAlpha).toBe(0);
    expect(data.outlineColor).toBe('#f59e0b');
    expect(data.outlineAlpha).toBe(1.0);
    expect(data.showBadge).toBe(false);
  });

  it('should clear error state', () => {
    glow.setTier(1, 'ERR_TIMEOUT');
    glow.clear();
    expect(glow.tier).toBe(0);
    expect(glow.isActive).toBe(false);
    expect(glow.errorCode).toBe('');
  });

  it('should freeze pulse when prefers-reduced-motion', () => {
    glow.setTier(1, 'ERR_TIMEOUT');
    glow.setReducedMotion(true);
    glow.update(1000);
    // Reduced motion: static red outline instead of pulse
    expect(glow.glowAlpha).toBe(0);
    expect(glow.outlineColor).toBe('#ef4444');
    expect(glow.outlineAlpha).toBe(1.0);
  });
});
