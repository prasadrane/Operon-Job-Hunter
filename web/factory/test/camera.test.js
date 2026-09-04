import { describe, it, expect, beforeEach } from 'vitest';
import { CameraController } from '../camera.js';

describe('CameraController', () => {
  let cam;

  beforeEach(() => {
    cam = new CameraController({
      screen: { width: 800, height: 600 },
      minZoom: 0.25,
      maxZoom: 2.0,
    });
  });

  it('starts at zoom 1.0 and origin offset', () => {
    expect(cam.scale).toBe(1.0);
    expect(cam.offsetX).toBe(0);
    expect(cam.offsetY).toBe(0);
  });

  it('clamps zoom to [0.25, 2.0]', () => {
    cam.zoomTo(5.0);
    expect(cam.scale).toBe(2.0);
    cam.zoomTo(0.01);
    expect(cam.scale).toBe(0.25);
  });

  it('zoomBy preserves focal point under cursor', () => {
    // focal point at screen (400, 300) — world (400, 300) at zoom=1
    cam.zoomBy(0.5, 400, 300);
    // new scale = 1.5; world point (400,300) should still map to screen (400,300)
    const screenX = 400 * cam.scale + cam.offsetX;
    const screenY = 300 * cam.scale + cam.offsetY;
    expect(screenX).toBeCloseTo(400, 1);
    expect(screenY).toBeCloseTo(300, 1);
  });

  it('panBy adds to offset', () => {
    cam.panBy(10, -5);
    expect(cam.offsetX).toBe(10);
    expect(cam.offsetY).toBe(-5);
    cam.panBy(5, 5);
    expect(cam.offsetX).toBe(15);
    expect(cam.offsetY).toBe(0);
  });

  it('reset returns to zoom=1 and offset=(0,0)', () => {
    cam.panBy(100, 100);
    cam.zoomTo(1.5);
    cam.reset();
    // After synchronous portion (tween may be queued), final state after drain:
    cam.update(1000); // consume any tween
    expect(cam.scale).toBe(1.0);
    expect(cam.offsetX).toBe(0);
    expect(cam.offsetY).toBe(0);
  });

  it('emits lod-change when crossing LOD thresholds', () => {
    const events = [];
    cam.on('lod-change', (e) => events.push(e.level));
    cam.zoomTo(0.4); // below 0.5 → top-down map
    expect(events).toContain('top-down');
    cam.zoomTo(0.6); // 0.5–0.75 → simplified
    expect(events).toContain('simplified');
    cam.zoomTo(0.9); // 0.75–1.0 → standard
    expect(events).toContain('standard');
    cam.zoomTo(1.5); // ≥1.0 → full
    expect(events).toContain('full');
  });

  it('setHeldKey integrates pan per frame', () => {
    cam.setHeldKey('KeyD', true); // D = pan right (camera moves right → world shifts left → offsetX decreases)
    cam.update(16); // one frame
    expect(cam.offsetX).toBeLessThan(0);
    cam.setHeldKey('KeyD', false);
    const before = cam.offsetX;
    cam.update(16);
    expect(cam.offsetX).toBe(before); // no further drift
  });
});
