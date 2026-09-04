import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { TouchHandler } from '../touch.js';

class FakeCanvas {
  constructor() {
    this.el = document.createElement('div');
  }
  dispatch(type, init = {}) {
    const ev = new PointerEvent(type, { pointerId: 1, clientX: 0, clientY: 0, bubbles: true, ...init });
    this.el.dispatchEvent(ev);
  }
}

describe('TouchHandler', () => {
  let canvas, handler, events;

  beforeEach(() => {
    canvas = new FakeCanvas();
    events = { tap: [], doubleTap: [], contextMenu: [] };
    handler = new TouchHandler({
      canvas: canvas.el,
      hitTest: (x, y) => ({ id: 'a', kind: 'agent' }),
      onTap: (t) => events.tap.push(t),
      onDoubleTap: (t) => events.doubleTap.push(t),
      onContextMenu: (t, x, y) => events.contextMenu.push({ t, x, y }),
    });
  });

  afterEach(() => handler.dispose());

  it('registers tap on quick down/up within threshold', () => {
    canvas.dispatch('pointerdown', { clientX: 100, clientY: 100 });
    canvas.dispatch('pointerup',   { clientX: 102, clientY: 102 });
    expect(events.tap).toHaveLength(1);
    expect(events.tap[0].id).toBe('a');
  });

  it('double tap on same target fires onDoubleTap', async () => {
    canvas.dispatch('pointerdown', { clientX: 100, clientY: 100 });
    canvas.dispatch('pointerup',   { clientX: 100, clientY: 100 });
    await new Promise(r => setTimeout(r, 100));
    canvas.dispatch('pointerdown', { clientX: 100, clientY: 100 });
    canvas.dispatch('pointerup',   { clientX: 100, clientY: 100 });
    expect(events.doubleTap).toHaveLength(1);
  });

  it('drag beyond threshold does not fire tap', () => {
    canvas.dispatch('pointerdown', { clientX: 100, clientY: 100 });
    canvas.dispatch('pointermove', { clientX: 150, clientY: 150 });
    canvas.dispatch('pointerup',   { clientX: 150, clientY: 150 });
    expect(events.tap).toHaveLength(0);
  });
});
