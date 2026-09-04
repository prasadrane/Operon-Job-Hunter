// Vitest global setup: mock PIXI + browser globals not present in jsdom.

// --- PIXI mock (modules reference the global `PIXI` loaded via CDN in-browser) ---
class MockContainer {
  constructor() {
    this.children = [];
    this.visible = true;
    this.x = 0;
    this.y = 0;
    this.scale = { set: (v) => { this.scale.x = v; this.scale.y = v; }, x: 1, y: 1 };
    this.alpha = 1;
  }
  addChild(c) { this.children.push(c); return c; }
  removeChild(c) { this.children = this.children.filter((x) => x !== c); }
  destroy() {}
}

class MockGraphics {
  constructor() { this.x = 0; this.y = 0; }
  lineStyle() { return this; }
  beginFill() { return this; }
  endFill() { return this; }
  moveTo() { return this; }
  lineTo() { return this; }
  closePath() { return this; }
  drawCircle() { return this; }
  drawRect() { return this; }
  clear() { return this; }
  destroy() {}
}

class MockSprite {
  constructor() { this.x = 0; this.y = 0; this.anchor = { set: () => {} }; }
  static from() { return new MockSprite(); }
  destroy() {}
}

class MockText {
  constructor(text) { this.text = text || ''; }
  destroy() {}
}

class MockApplication {
  constructor(opts = {}) {
    this.screen = { width: opts.width || 800, height: opts.height || 600 };
    this.stage = new MockContainer();
    this.renderer = { resize: () => {} };
    this.canvas = document.createElement('canvas');
    this.ticker = { add: () => {}, remove: () => {}, start: () => {}, stop: () => {} };
  }
  destroy() {}
}

globalThis.PIXI = {
  Container: MockContainer,
  Graphics: MockGraphics,
  Sprite: MockSprite,
  Text: MockText,
  Application: MockApplication,
  utils: { TextureCache: {} },
  Texture: { from: () => ({}) },
};

// --- matchMedia (jsdom lacks it) ---
if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  });
}

// --- requestAnimationFrame ---
if (!globalThis.requestAnimationFrame) {
  globalThis.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 0);
  globalThis.cancelAnimationFrame = (id) => clearTimeout(id);
}

// --- EventSource (SSE) stub ---
if (!globalThis.EventSource) {
  globalThis.EventSource = class EventSource {
    constructor(url) {
      this.url = url;
      this.readyState = 0;
      this.listeners = {};
    }
    addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
    removeEventListener() {}
    close() { this.readyState = 2; }
  };
}

// --- navigator.clipboard (jsdom lacks it) ---
if (!navigator.clipboard) {
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: () => Promise.resolve(), readText: () => Promise.resolve('') },
    writable: true,
    configurable: true,
  });
}

// --- PointerEvent (jsdom lacks it) ---
if (!globalThis.PointerEvent) {
  globalThis.PointerEvent = class PointerEvent extends Event {
    constructor(type, init = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 1;
      this.clientX = init.clientX ?? 0;
      this.clientY = init.clientY ?? 0;
      this.pointerType = init.pointerType ?? 'touch';
      this.isPrimary = init.isPrimary ?? true;
    }
  };
}

// --- ResizeObserver (jsdom lacks it) ---
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
