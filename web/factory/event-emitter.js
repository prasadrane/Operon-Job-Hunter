/**
 * Tiny EventEmitter shim. Mirrors node EventEmitter surface
 * (on/off/emit/removeAllListeners) without pulling in a dep.
 */
export class EventEmitter {
  constructor() {
    /** @type {Map<string, Set<Function>>} */
    this._listeners = new Map();
  }

  on(event, fn) {
    if (!this._listeners.has(event)) this._listeners.set(event, new Set());
    this._listeners.get(event).add(fn);
    return this;
  }

  off(event, fn) {
    const s = this._listeners.get(event);
    if (s) s.delete(fn);
    return this;
  }

  emit(event, payload) {
    const s = this._listeners.get(event);
    if (!s) return;
    for (const fn of s) {
      try { fn(payload); } catch (e) { console.error(`EventEmitter '${event}' handler error:`, e); }
    }
  }

  removeAllListeners(event) {
    if (event === undefined) this._listeners.clear();
    else this._listeners.delete(event);
  }
}
