import { describe, it, expect, beforeEach, vi } from 'vitest';
import { Canvas2DFallback } from '../canvas2d-fallback.js';

describe('Canvas2DFallback', () => {
  let fallback;

  beforeEach(() => {
    fallback = new Canvas2DFallback();
  });

  it('should detect WebGL capability', () => {
    // Mock WebGL available
    global.document = {
      createElement: vi.fn(() => ({
        getContext: vi.fn((type) => type === 'webgl2' ? {} : null),
      })),
    };

    const mode = fallback.getRendererMode();
    expect(mode).toBe('webgl');
  });

  it('should fallback to Canvas2D if WebGL unavailable', () => {
    // Mock WebGL not available
    global.document = {
      createElement: vi.fn(() => ({
        getContext: vi.fn(() => null),
      })),
    };

    const mode = fallback.getRendererMode();
    expect(mode).toBe('canvas2d');
  });

  it('should cap entities at 20 in Canvas2D mode', () => {
    fallback.rendererMode = 'canvas2d';
    expect(fallback.getEntityCap()).toBe(20);
  });

  it('should allow 50 entities in WebGL mode', () => {
    fallback.rendererMode = 'webgl';
    expect(fallback.getEntityCap()).toBe(50);
  });

  it('should disable particles in Canvas2D mode', () => {
    fallback.rendererMode = 'canvas2d';
    expect(fallback.shouldEnableParticles()).toBe(false);
  });

  it('should enable particles in WebGL mode', () => {
    fallback.rendererMode = 'webgl';
    expect(fallback.shouldEnableParticles()).toBe(true);
  });

  it('should pause rendering when tab hidden', () => {
    fallback.handleVisibilityChange({ target: { hidden: true } });
    expect(fallback.shouldPauseRendering()).toBe(true);
  });

  it('should resume rendering when tab visible', () => {
    fallback.handleVisibilityChange({ target: { hidden: true } });
    fallback.handleVisibilityChange({ target: { hidden: false } });
    expect(fallback.shouldPauseRendering()).toBe(false);
  });

  it('should use top-down projection in Canvas2D mode', () => {
    fallback.rendererMode = 'canvas2d';
    expect(fallback.getProjection()).toBe('top-down');
  });

  it('should use isometric projection in WebGL mode', () => {
    fallback.rendererMode = 'webgl';
    expect(fallback.getProjection()).toBe('isometric');
  });
});
