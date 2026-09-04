import { EventEmitter } from './event-emitter.js';

/**
 * CameraController — pan/zoom state with focal-preserving zoom,
 * LOD threshold emission, and tweens for focus/reset.
 *
 * Events:
 *   - 'change'     { scale, offsetX, offsetY } — any transform mutation
 *   - 'lod-change' { level } — level ∈ {'top-down','simplified','standard','full'}
 */
export class CameraController extends EventEmitter {
  constructor({ screen, minZoom = 0.25, maxZoom = 2.0, panSpeed = 8 } = {}) {
    super();
    this._screen = screen || { width: 800, height: 600 };
    this._minZoom = minZoom;
    this._maxZoom = maxZoom;
    this._panSpeed = panSpeed; // px per frame at dt=16ms

    this._scale = 1.0;
    this._offsetX = 0;
    this._offsetY = 0;

    this._heldKeys = new Set();
    this._tween = null; // { from, to, elapsed, duration }
    this._lodLevel = 'standard';
    this._motionGate = null;
  }

  get scale()   { return this._scale; }
  get offsetX() { return this._offsetX; }
  get offsetY() { return this._offsetY; }
  get lodLevel(){ return this._lodLevel; }

  /** Attach MotionGate (optional) — lets focus/reset tweens be skipped under reduced-motion. */
  setMotionGate(gate) { this._motionGate = gate; }

  /** World → screen transform */
  worldToScreen(wx, wy) {
    return { x: wx * this._scale + this._offsetX, y: wy * this._scale + this._offsetY };
  }

  /** Screen → world transform */
  screenToWorld(sx, sy) {
    return { x: (sx - this._offsetX) / this._scale, y: (sy - this._offsetY) / this._scale };
  }

  panBy(dx, dy) {
    this._offsetX += dx;
    this._offsetY += dy;
    this._emitChange();
  }

  panTo(worldX, worldY) {
    this._offsetX = this._screen.width / 2 - worldX * this._scale;
    this._offsetY = this._screen.height / 2 - worldY * this._scale;
    this._emitChange();
  }

  zoomBy(delta, focalX, focalY) {
    this.zoomTo(this._scale * (1 + delta), focalX, focalY);
  }

  zoomTo(level, focalX, focalY) {
    const prev = this._scale;
    const next = Math.max(this._minZoom, Math.min(this._maxZoom, level));
    if (focalX != null && focalY != null) {
      const worldX = (focalX - this._offsetX) / prev;
      const worldY = (focalY - this._offsetY) / prev;
      this._scale = next;
      this._offsetX = focalX - worldX * next;
      this._offsetY = focalY - worldY * next;
    } else {
      const cx = this._screen.width / 2;
      const cy = this._screen.height / 2;
      const worldX = (cx - this._offsetX) / prev;
      const worldY = (cy - this._offsetY) / prev;
      this._scale = next;
      this._offsetX = cx - worldX * next;
      this._offsetY = cy - worldY * next;
    }
    this._updateLod();
    this._emitChange();
  }

  setZoom(level, focalX, focalY) {
    return this.zoomTo(level, focalX, focalY);
  }

  /** Jump camera to center on entity at 1.5× zoom. */
  focusEntity(entity) {
    const to = {
      offsetX: this._screen.width / 2 - entity.x * 1.5,
      offsetY: this._screen.height / 2 - entity.y * 1.5,
      scale: 1.5,
    };
    this._startTween(to, 300);
  }

  reset() {
    this._startTween({ offsetX: 0, offsetY: 0, scale: 1.0 }, 300);
  }

  applyTo(container) {
    container.scale.set(this._scale);
    container.position.set(this._offsetX, this._offsetY);
  }

  setHeldKey(code, isDown) {
    if (isDown) this._heldKeys.add(code);
    else this._heldKeys.delete(code);
  }

  update(dt) {
    if (this._tween) {
      this._tween.elapsed += dt;
      const t = Math.min(1, this._tween.elapsed / this._tween.duration);
      const e = 1 - Math.pow(1 - t, 3); // ease-out cubic
      this._scale   = this._tween.from.scale   + (this._tween.to.scale   - this._tween.from.scale)   * e;
      this._offsetX = this._tween.from.offsetX + (this._tween.to.offsetX - this._tween.from.offsetX) * e;
      this._offsetY = this._tween.from.offsetY + (this._tween.to.offsetY - this._tween.from.offsetY) * e;
      if (t >= 1) {
        this._tween = null;
        this._updateLod();
      }
      this._emitChange();
    }

    const step = this._panSpeed * (dt / 16);
    let dx = 0, dy = 0;
    if (this._heldKeys.has('KeyW') || this._heldKeys.has('ArrowUp'))    dy += step;
    if (this._heldKeys.has('KeyS') || this._heldKeys.has('ArrowDown'))  dy -= step;
    if (this._heldKeys.has('KeyA') || this._heldKeys.has('ArrowLeft'))  dx += step;
    if (this._heldKeys.has('KeyD') || this._heldKeys.has('ArrowRight')) dx -= step;
    if (dx || dy) this.panBy(dx, dy);
  }

  dispose() {
    this._heldKeys.clear();
    this._tween = null;
    this.removeAllListeners();
  }

  _startTween(to, duration) {
    if (this._motionGate?.reduced) {
      this._scale   = to.scale;
      this._offsetX = to.offsetX;
      this._offsetY = to.offsetY;
      this._updateLod();
      this._emitChange();
      return;
    }
    this._tween = {
      from: { scale: this._scale, offsetX: this._offsetX, offsetY: this._offsetY },
      to,
      elapsed: 0,
      duration,
    };
  }

  _updateLod() {
    let level;
    if (this._scale < 0.5)      level = 'top-down';
    else if (this._scale <= 0.75) level = 'simplified';
    else if (this._scale <= 1.0)  level = 'standard';
    else                         level = 'full';
    if (level !== this._lodLevel) {
      this._lodLevel = level;
      this.emit('lod-change', { level });
    }
  }

  _emitChange() {
    this.emit('change', { scale: this._scale, offsetX: this._offsetX, offsetY: this._offsetY });
  }
}
