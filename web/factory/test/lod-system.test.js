import { describe, it, expect, beforeEach } from 'vitest';
import { LODSystem } from '../lod-system.js';

describe('LODSystem', () => {
  let lod;

  beforeEach(() => {
    lod = new LODSystem();
  });

  it('should return top-down map tier for zoom < 0.5', () => {
    expect(lod.getTier(0.25)).toBe('top-down');
    expect(lod.getTier(0.49)).toBe('top-down');
  });

  it('should return simplified iso tier for zoom 0.5–0.75', () => {
    expect(lod.getTier(0.5)).toBe('simplified');
    expect(lod.getTier(0.6)).toBe('simplified');
    expect(lod.getTier(0.75)).toBe('simplified');
  });

  it('should return standard iso tier for zoom 0.75–1.0', () => {
    expect(lod.getTier(0.76)).toBe('standard');
    expect(lod.getTier(0.9)).toBe('standard');
    expect(lod.getTier(1.0)).toBe('standard');
  });

  it('should return full detail tier for zoom ≥ 1.0', () => {
    expect(lod.getTier(1.01)).toBe('full');
    expect(lod.getTier(1.5)).toBe('full');
    expect(lod.getTier(2.0)).toBe('full');
  });

  it('should cull entities outside viewport + 1 tile buffer', () => {
    const viewport = { x: 0, y: 0, width: 800, height: 600 };
    const tileWidth = 48;

    const entityInside = { x: 400, y: 300, width: 32, height: 32 };
    const entityOutside = { x: 1000, y: 1000, width: 32, height: 32 };

    expect(lod.shouldRender(entityInside, viewport, tileWidth)).toBe(true);
    expect(lod.shouldRender(entityOutside, viewport, tileWidth)).toBe(false);
  });

  it('should include entities within 1 tile buffer', () => {
    const viewport = { x: 0, y: 0, width: 800, height: 600 };
    const tileWidth = 48;

    const entityNearEdge = { x: 820, y: 300, width: 32, height: 32 }; // within 48px buffer
    expect(lod.shouldRender(entityNearEdge, viewport, tileWidth)).toBe(true);
  });

  it('should handle crossfade transitions over 200ms', () => {
    lod.setZoom(0.4); // top-down
    expect(lod.currentTier).toBe('top-down');

    lod.setZoom(0.8); // standard
    expect(lod.isTransitioning).toBe(true);

    // After 100ms (halfway), should still be transitioning
    lod.update(100);
    expect(lod.transitionProgress).toBeCloseTo(0.5, 1);

    // After 200ms total, transition complete
    lod.update(100);
    expect(lod.isTransitioning).toBe(false);
    expect(lod.currentTier).toBe('standard');
  });
});
