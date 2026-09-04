import { describe, it, expect, beforeEach } from 'vitest';
import { InteractionManager } from '../interaction.js';

class FakeApp {
  constructor() {
    this.canvas = document.createElement('canvas');
    this.screen = { width: 800, height: 600 };
    document.body.appendChild(this.canvas);
  }
  destroy() { this.canvas.remove(); }
}
class FakeEntities {
  constructor() { this.targets = []; }
  getHitTargets() { return this.targets; }
}
class FakeState {}
class FakeCamera {
  constructor() { this.scale = 1; this.offsetX = 0; this.offsetY = 0; this.resetCalls = 0; this._listeners = new Map(); }
  worldToScreen(wx, wy) { return { x: wx * this.scale + this.offsetX, y: wy * this.scale + this.offsetY }; }
  screenToWorld(sx, sy) { return { x: (sx - this.offsetX) / this.scale, y: (sy - this.offsetY) / this.scale }; }
  panBy(dx, dy) { this.offsetX += dx; this.offsetY += dy; }
  reset() { this.resetCalls++; }
  on(evt, fn) { if (!this._listeners.has(evt)) this._listeners.set(evt, new Set()); this._listeners.get(evt).add(fn); }
  off(evt, fn) { const s = this._listeners.get(evt); if (s) s.delete(fn); }
}
class FakeTooltip { constructor() { this.last = null; } show(t, x, y, o) { this.last = { t, x, y, o }; } hide() { this.last = null; } }
class FakeMotion { get reduced() { return false; } }

describe('InteractionManager click/hover', () => {
  let app, entities, camera, tooltip, interaction;

  beforeEach(() => {
    app = new FakeApp();
    entities = new FakeEntities();
    camera = new FakeCamera();
    tooltip = new FakeTooltip();
    interaction = new InteractionManager(app, entities, new FakeState(), camera, tooltip, new FakeMotion());
    entities.targets = [
      { id: 'agent-1', kind: 'agent', worldX: 100, worldY: 100, width: 48, height: 48, data: { name: 'Scout Falcon' } },
    ];
  });

  afterEach(() => interaction.dispose());

  it('hover over agent shows tooltip at screen coords', () => {
    app.canvas.dispatchEvent(new PointerEvent('pointermove', { clientX: 110, clientY: 110 }));
    expect(tooltip.last).toBeTruthy();
    expect(tooltip.last.t).toContain('Scout Falcon');
  });

  it('click on agent dispatches factory:open-detail', () => {
    let detail = null;
    const handler = (e) => { detail = e.detail; };
    window.addEventListener('factory:open-detail', handler);
    app.canvas.dispatchEvent(new PointerEvent('pointerdown', { clientX: 110, clientY: 110 }));
    app.canvas.dispatchEvent(new PointerEvent('pointerup',   { clientX: 110, clientY: 110 }));
    expect(detail).toBeTruthy();
    expect(detail.kind).toBe('agent');
    expect(detail.data.name).toBe('Scout Falcon');
    window.removeEventListener('factory:open-detail', handler);
  });

  it('double-click empty space resets camera', () => {
    app.canvas.dispatchEvent(new MouseEvent('dblclick', { clientX: 500, clientY: 500 }));
    expect(camera.resetCalls).toBe(1);
  });
});
