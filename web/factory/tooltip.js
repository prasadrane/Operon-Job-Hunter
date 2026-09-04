const TOOLTIP_OFFSET = 12; // px from cursor

/**
 * TooltipManager — single DOM tooltip positioned over PixiJS world coords.
 * Variant styling via data-variant attribute ('agent' | 'job' | 'zone' | 'station' | 'default').
 */
export class TooltipManager {
  constructor(rootEl = document.body) {
    this._root = rootEl;
    this._el = document.createElement('div');
    this._el.setAttribute('data-tooltip', '');
    this._el.setAttribute('role', 'tooltip');
    this._el.setAttribute('aria-live', 'polite');
    this._el.style.cssText = `
      position: fixed; pointer-events: none; opacity: 0;
      padding: 6px 10px; background: rgba(13,18,31,0.95);
      color: #e5e7eb; font-size: 12px; border-radius: 4px;
      border: 1px solid #2a2a3e; max-width: 260px; z-index: 1000;
      transition: opacity 120ms ease;
      visibility: hidden;
    `;
    this._root.appendChild(this._el);
    this._visible = false;
  }

  get isVisible() { return this._visible; }

  show(text, screenX, screenY, opts = {}) {
    this._el.textContent = text;
    this._el.dataset.variant = opts.variant || 'default';
    const rootRect = this._root.getBoundingClientRect();
    // Measure tooltip size (force reflow with hidden state)
    this._el.style.opacity = '0';
    this._el.style.visibility = 'hidden';
    this._el.style.left = '0px';
    this._el.style.top = '0px';
    const { width: w, height: h } = this._el.getBoundingClientRect();

    let x = screenX + TOOLTIP_OFFSET;
    let y = screenY + TOOLTIP_OFFSET;
    if (x + w > rootRect.right)  x = screenX - TOOLTIP_OFFSET - w;
    if (y + h > rootRect.bottom) y = screenY - TOOLTIP_OFFSET - h;
    x = Math.max(rootRect.left, x);
    y = Math.max(rootRect.top, y);

    this._el.style.left = `${x}px`;
    this._el.style.top = `${y}px`;
    this._el.style.opacity = '1';
    this._el.style.visibility = 'visible';
    this._visible = true;
  }

  hide() {
    this._el.style.opacity = '0';
    this._el.style.visibility = 'hidden';
    this._visible = false;
  }

  dispose() {
    this._el.remove();
  }
}
