import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { MotionGate } from '../motion-gate.js';

describe('MotionGate', () => {
  let gate;
  let mmListener;
  const mmState = { matches: false };
  const mm = {
    get matches() { return mmState.matches; },
    addEventListener: (_e, fn) => { mmListener = fn; },
    removeEventListener: () => { mmListener = null; },
  };

  beforeEach(() => {
    mmState.matches = false;
    vi.stubGlobal('matchMedia', vi.fn(() => mm));
    localStorage.clear();
    gate = new MotionGate();
  });

  afterEach(() => {
    gate.dispose();
    vi.unstubAllGlobals();
  });

  it('defaults to not reduced when system prefers-motion', () => {
    mmState.matches = false;
    gate = new MotionGate();
    expect(gate.reduced).toBe(false);
    expect(gate.systemReduced).toBe(false);
  });

  it('reflects system prefers-reduced-motion', () => {
    mmState.matches = true;
    gate = new MotionGate();
    expect(gate.reduced).toBe(true);
    expect(gate.systemReduced).toBe(true);
  });

  it('user override wins over system', () => {
    mmState.matches = true;
    gate = new MotionGate();
    gate.setUserOverride(false);
    expect(gate.reduced).toBe(false);
  });

  it('emits change event on flip', () => {
    const calls = [];
    gate.on('change', (v) => calls.push(v));
    gate.setUserOverride(true);
    expect(calls).toEqual([true]);
    mmState.matches = true;
    gate.setUserOverride(null); // clear → fall back to system (now true, no flip)
    mmListener({ matches: true }); // no-op, already true
    mmState.matches = false;       // system flips to false
    mmListener({ matches: false }); // now _maybeEmit sees reduced=false, emits
    expect(calls).toContain(false);
  });

  it('persists user override to localStorage', () => {
    gate.setUserOverride(true);
    expect(localStorage.getItem('factory.reduceMotion')).toBe('true');
  });
});
