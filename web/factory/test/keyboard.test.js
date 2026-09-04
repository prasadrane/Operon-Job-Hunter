import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { KeyboardNavigator } from '../keyboard.js';

function makeFocusable(id, kind, order, extra = {}) {
  const domNode = document.createElement('button');
  domNode.tabIndex = 0;
  document.body.appendChild(domNode);
  const item = { id, kind, order, domNode, focus: () => domNode.focus(), ...extra };
  item._cleanup = () => domNode.remove();
  return item;
}

describe('KeyboardNavigator', () => {
  let nav, camera, items;

  beforeEach(() => {
    camera = { reset: () => { camera.resetCalls = (camera.resetCalls || 0) + 1; } };
    nav = new KeyboardNavigator({ camera });
    nav.attach();
    items = [];
  });

  afterEach(() => {
    nav.detach();
    for (const it of items) it._cleanup?.();
  });

  it('focusNext cycles through registered items in tab order', () => {
    const a = makeFocusable('a', 'agent', 0);
    const b = makeFocusable('b', 'job', 1);
    const c = makeFocusable('c', 'zone', 2);
    items.push(a, b, c);
    nav.register(a); nav.register(b); nav.register(c);
    nav.setTabOrder(['agent', 'job', 'zone', 'error', 'control']);
    nav.focusNext();
    expect(document.activeElement).toBe(a.domNode);
    nav.focusNext();
    expect(document.activeElement).toBe(b.domNode);
    nav.focusNext();
    expect(document.activeElement).toBe(c.domNode);
    nav.focusNext();
    expect(document.activeElement).toBe(a.domNode); // wraps
  });

  it('E shortcut focuses latest error', () => {
    const err = makeFocusable('err1', 'error', 0, { newest: true });
    items.push(err);
    nav.register(err);
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'e' }));
    expect(document.activeElement).toBe(err.domNode);
  });

  it('0 shortcut calls camera.reset', () => {
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '0' }));
    expect(camera.resetCalls).toBe(1);
  });

  it('Esc closes open panel and returns focus to trigger', () => {
    const trigger = makeFocusable('t', 'error', 0);
    items.push(trigger);
    nav.register(trigger);
    nav.focusById('t');
    nav._onPanelOpen(trigger); // simulate panel open
    // Esc should refocus trigger
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(document.activeElement).toBe(trigger.domNode);
  });
});
