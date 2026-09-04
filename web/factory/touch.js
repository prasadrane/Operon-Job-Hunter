const TAP_MAX_MS = 300;
const TAP_MAX_PX = 10;
const DOUBLE_TAP_WINDOW_MS = 350;
const LONG_PRESS_MS = 500;

/**
 * TouchHandler — unified pointer handler for tap / double-tap / long-press / pinch.
 *
 * Uses pointer events (mouse + touch + pen unified). All tap gestures are routed
 * through callbacks, letting the consumer dispatch appropriate custom events
 * ('factory:focus-entity', 'factory:context-menu') for parity with keyboard/mouse.
 *
 * Callbacks:
 *   onTap(target)             — single tap within threshold
 *   onDoubleTap(target)       — two taps on same target within DOUBLE_TAP_WINDOW_MS
 *   onContextMenu(target, x, y) — fires alongside onDoubleTap (context menu shown at x/y)
 *   onPanStart()              — long-press (500ms hold) engaged
 *   onPinch({ scale })        — two-finger pinch; scale = current / start distance
 */
export class TouchHandler {
  constructor({ canvas, hitTest, onTap, onDoubleTap, onContextMenu, onPanStart, onPinch }) {
    this._canvas = canvas;
    this._hitTest = hitTest;
    this._onTap = onTap || (() => {});
    this._onDoubleTap = onDoubleTap || (() => {});
    this._onContextMenu = onContextMenu || (() => {});
    this._onPanStart = onPanStart || (() => {});
    this._onPinch = onPinch || (() => {});

    /** @type {Map<number, { startX, startY, startTime, moved }>} */
    this._active = new Map();
    /** @type {{ targetId, time }|null} */
    this._lastTap = null;
    this._longPressTimer = null;
    this._pinchStartDist = null;

    this._onDown = this._onDown.bind(this);
    this._onMove = this._onMove.bind(this);
    this._onUp   = this._onUp.bind(this);

    canvas.addEventListener('pointerdown', this._onDown);
    canvas.addEventListener('pointermove', this._onMove);
    canvas.addEventListener('pointerup',   this._onUp);
    canvas.addEventListener('pointercancel', this._onUp);
  }

  _rect() { return this._canvas.getBoundingClientRect(); }

  _onDown(e) {
    const r = this._rect();
    this._active.set(e.pointerId, {
      startX: e.clientX - r.left,
      startY: e.clientY - r.top,
      startTime: performance.now(),
      moved: false,
    });
    if (this._active.size === 1) {
      this._longPressTimer = setTimeout(() => {
        const rec = this._active.get(e.pointerId);
        if (rec && !rec.moved) this._onPanStart();
      }, LONG_PRESS_MS);
    } else if (this._active.size === 2) {
      clearTimeout(this._longPressTimer);
      const pts = Array.from(this._active.values());
      this._pinchStartDist = Math.hypot(pts[0].startX - pts[1].startX, pts[0].startY - pts[1].startY);
    }
  }

  _onMove(e) {
    const rec = this._active.get(e.pointerId);
    if (!rec) return;
    const r = this._rect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    if (Math.hypot(x - rec.startX, y - rec.startY) > TAP_MAX_PX) {
      rec.moved = true;
      if (this._longPressTimer) {
        clearTimeout(this._longPressTimer);
        this._longPressTimer = null;
      }
    }
    if (this._active.size === 2 && this._pinchStartDist) {
      const pts = Array.from(this._active.entries()).map(([id, p]) => {
        if (id === e.pointerId) return { x, y };
        return { x: p.startX, y: p.startY };
      });
      const dist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
      this._onPinch({ scale: dist / this._pinchStartDist });
    }
  }

  _onUp(e) {
    if (this._longPressTimer) {
      clearTimeout(this._longPressTimer);
      this._longPressTimer = null;
    }
    const rec = this._active.get(e.pointerId);
    this._active.delete(e.pointerId);
    if (!rec || rec.moved) { this._pinchStartDist = null; return; }
    const elapsed = performance.now() - rec.startTime;
    if (elapsed > TAP_MAX_MS) { this._pinchStartDist = null; return; }
    const r = this._rect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    const target = this._hitTest(x, y);
    if (!target) { this._pinchStartDist = null; return; }

    const now = performance.now();
    if (this._lastTap && this._lastTap.targetId === target.id && (now - this._lastTap.time) < DOUBLE_TAP_WINDOW_MS) {
      this._onDoubleTap(target);
      this._onContextMenu(target, e.clientX, e.clientY);
      this._lastTap = null;
    } else {
      this._onTap(target);
      this._lastTap = { targetId: target.id, time: now };
    }
    this._pinchStartDist = null;
  }

  dispose() {
    if (this._longPressTimer) clearTimeout(this._longPressTimer);
    this._canvas.removeEventListener('pointerdown', this._onDown);
    this._canvas.removeEventListener('pointermove', this._onMove);
    this._canvas.removeEventListener('pointerup',   this._onUp);
    this._canvas.removeEventListener('pointercancel', this._onUp);
  }
}
