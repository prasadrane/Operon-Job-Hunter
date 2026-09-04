import { TouchHandler } from './touch.js';

const DRAG_THRESHOLD = 5; // px

/**
 * InteractionManager — dispatches pointer events to hit-test targets.
 * Responsibilities:
 *   - Click → dispatch 'factory:open-detail' with { kind, data, trigger }
 *   - Hover → show/hide tooltip with screen-space positioning
 *   - Drag  → pan camera (1:1 with cursor beyond DRAG_THRESHOLD)
 *   - Double-click empty space → camera.reset()
 */
export class InteractionManager {
  constructor(app, entities, state, camera, tooltip, motionGate) {
    this.app = app;
    this.entities = entities;
    this.state = state;
    this.camera = camera;
    this.tooltip = tooltip;
    this.motionGate = motionGate;

    this._pointerDown = null;
    this._dragging = false;
    this._lastHover = null;

    this._onPointerMove = this._onPointerMove.bind(this);
    this._onPointerDown = this._onPointerDown.bind(this);
    this._onPointerUp   = this._onPointerUp.bind(this);
    this._onDblClick    = this._onDblClick.bind(this);

    app.canvas.addEventListener('pointermove', this._onPointerMove);
    app.canvas.addEventListener('pointerdown', this._onPointerDown);
    app.canvas.addEventListener('pointerup',   this._onPointerUp);
    app.canvas.addEventListener('dblclick',    this._onDblClick);

    this._cameraOnChange = () => { if (this.tooltip) this.tooltip.hide(); };
    if (this.camera && typeof this.camera.on === 'function') {
      this.camera.on('change', this._cameraOnChange);
    }

    // Touch / pinch / long-press handler (shares hit-test logic with mouse)
    this._touch = new TouchHandler({
      canvas: app.canvas,
      hitTest: (x, y) => this._hitTest(x, y),
      onTap: (target) => {
        window.dispatchEvent(new CustomEvent('factory:focus-entity', {
          detail: { id: target.id, kind: target.kind },
        }));
      },
      onDoubleTap: (_target) => { /* context-menu path handles the follow-up */ },
      onContextMenu: (target, cx, cy) => {
        window.dispatchEvent(new CustomEvent('factory:context-menu', {
          detail: { kind: target.kind, data: target.data, screenX: cx, screenY: cy },
        }));
      },
      onPanStart: () => { /* camera drag mode engaged */ },
      onPinch: ({ scale }) => {
        if (this.camera) this.camera.zoomBy(scale - 1);
      },
    });
  }

  _screenToCanvas(e) {
    const r = this.app.canvas.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  _hitTest(screenX, screenY) {
    const targets = this.entities.getHitTargets ? this.entities.getHitTargets() : [];
    for (const t of targets) {
      const s = this.camera.worldToScreen(t.worldX, t.worldY);
      const w = t.width * this.camera.scale;
      const h = t.height * this.camera.scale;
      if (screenX >= s.x && screenX <= s.x + w && screenY >= s.y && screenY <= s.y + h) {
        return t;
      }
    }
    return null;
  }

  _onPointerMove(e) {
    const { x, y } = this._screenToCanvas(e);
    if (this._pointerDown && !this._dragging) {
      const dx = x - this._pointerDown.x;
      const dy = y - this._pointerDown.y;
      if (Math.hypot(dx, dy) > DRAG_THRESHOLD) {
        this._dragging = true;
      }
    }
    if (this._dragging) {
      this.camera.panBy(e.movementX, e.movementY);
      return;
    }
    const hit = this._hitTest(x, y);
    if (hit) {
      this._lastHover = hit;
      const label = this._tooltipTextFor(hit);
      if (this.tooltip) this.tooltip.show(label, e.clientX, e.clientY, { variant: hit.kind });
    } else if (this._lastHover) {
      this._lastHover = null;
      if (this.tooltip) this.tooltip.hide();
    }
  }

  _onPointerDown(e) {
    const { x, y } = this._screenToCanvas(e);
    this._pointerDown = { x, y, clientX: e.clientX, clientY: e.clientY };
    this._dragging = false;
  }

  _onPointerUp(e) {
    if (!this._pointerDown) return;
    const { x, y } = this._screenToCanvas(e);
    const moved = Math.hypot(x - this._pointerDown.x, y - this._pointerDown.y);
    const wasDrag = this._dragging;
    this._pointerDown = null;
    const dragEnded = this._dragging;
    this._dragging = false;
    if (wasDrag || moved > DRAG_THRESHOLD) return;

    const hit = this._hitTest(x, y);
    if (hit) {
      window.dispatchEvent(new CustomEvent('factory:open-detail', {
        detail: { kind: hit.kind, data: hit.data, trigger: 'click' },
      }));
    }
  }

  _onDblClick(e) {
    const { x, y } = this._screenToCanvas(e);
    const hit = this._hitTest(x, y);
    if (!hit) this.camera.reset();
  }

  _tooltipTextFor(target) {
    switch (target.kind) {
      case 'agent': return `${target.data.name} · ${target.data.role || ''} · ${target.data.status || ''}`;
      case 'job':   return `${target.data.company} · ${target.data.title} · score ${target.data.score}`;
      case 'zone':  return `${target.data.name} · ${target.data.count ?? 0} jobs`;
      case 'station': return `${target.data.name} · ${target.data.status || ''}`;
      default: return '';
    }
  }

  dispose() {
    this.app.canvas.removeEventListener('pointermove', this._onPointerMove);
    this.app.canvas.removeEventListener('pointerdown', this._onPointerDown);
    this.app.canvas.removeEventListener('pointerup',   this._onPointerUp);
    this.app.canvas.removeEventListener('dblclick',    this._onDblClick);
    if (this.camera && typeof this.camera.off === 'function') {
      this.camera.off('change', this._cameraOnChange);
    }
    if (this._touch) this._touch.dispose();
  }
}
