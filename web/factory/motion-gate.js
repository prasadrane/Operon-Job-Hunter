import { EventEmitter } from './event-emitter.js';

const LS_KEY = 'factory.reduceMotion';

/**
 * MotionGate — singleton that resolves `prefers-reduced-motion` and user override.
 *
 * `reduced` is the single source of truth for consumers:
 *   - If userOverride != null, reduced = userOverride
 *   - Else reduced = systemReduced (matchMedia)
 *
 * Emits 'change' (boolean) on every flip of `reduced`.
 */
export class MotionGate extends EventEmitter {
  constructor() {
    super();
    this._mq = typeof window !== 'undefined' ? window.matchMedia?.('(prefers-reduced-motion: reduce)') : null;
    this._onSystemChange = this._onSystemChange.bind(this);
    this._mq?.addEventListener?.('change', this._onSystemChange);
    let stored = null;
    try { stored = localStorage.getItem(LS_KEY); } catch (_) { /* private-mode / sandbox */ }
    this._userOverride = stored == null ? null : stored === 'true';
    this._lastReduced = this.reduced;
  }

  get systemReduced() { return !!this._mq?.matches; }
  get userOverride()  { return this._userOverride; }
  get reduced() {
    return this._userOverride != null ? this._userOverride : this.systemReduced;
  }

  /** Set or clear user override. null = follow system. Persists to localStorage. */
  setUserOverride(value) {
    this._userOverride = value;
    try {
      if (value == null) localStorage.removeItem(LS_KEY);
      else localStorage.setItem(LS_KEY, String(value));
    } catch (_) { /* storage blocked */ }
    this._maybeEmit();
  }

  dispose() {
    this._mq?.removeEventListener?.('change', this._onSystemChange);
    this.removeAllListeners();
  }

  _onSystemChange() { this._maybeEmit(); }

  _maybeEmit() {
    if (this.reduced !== this._lastReduced) {
      this._lastReduced = this.reduced;
      this.emit('change', this.reduced);
    }
  }
}
