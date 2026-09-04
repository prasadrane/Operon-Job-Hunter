const MIN_HIT = 44; // WCAG 2.5.5 minimum touch target size

/**
 * A11yOverlay — DOM layer of invisible hit-areas synced to PixiJS entity positions.
 *
 * One `<button tabindex="0">` per interactive entity, positioned via CSS absolute
 * at the screen-projected coords × camera transform. Size clamped to ≥ 44×44.
 *
 * On focus of any hit-area, dispatches 'factory:focus-entity' { id, kind } so
 * renderer can draw a selection ring.
 */
export class A11yOverlay {
  constructor(canvasEl, camera) {
    this._canvas = canvasEl;
    this._camera = camera;
    this._root = document.createElement('div');
    this._root.id = 'a11y-overlay';
    this._root.style.cssText = 'position:absolute;inset:0;pointer-events:none;';
    canvasEl.parentElement.style.position = 'relative';
    canvasEl.parentElement.appendChild(this._root);

    /** @type {Map<string, { item: Object, btn: HTMLButtonElement }>} */
    this._nodes = new Map();
    this._onFocus = this._onFocus.bind(this);
    this._root.addEventListener('focus', this._onFocus, true);
  }

  sync(hitTargets) {
    const incoming = new Set(hitTargets.map(t => t.id));
    // Remove stale
    for (const [id, rec] of this._nodes) {
      if (!incoming.has(id)) { rec.btn.remove(); this._nodes.delete(id); }
    }
    // Upsert
    for (const t of hitTargets) {
      const s = this._camera.worldToScreen(t.worldX, t.worldY);
      const w = Math.max(MIN_HIT, t.width * this._camera.scale);
      const h = Math.max(MIN_HIT, t.height * this._camera.scale);
      let rec = this._nodes.get(t.id);
      if (!rec) {
        const btn = document.createElement('button');
        btn.tabIndex = 0;
        btn.dataset.kind = t.kind;
        btn.dataset.id = t.id;
        btn.style.cssText = `
          position:absolute; pointer-events: auto; background: transparent;
          border: 2px solid transparent; border-radius: 4px; cursor: pointer;
          padding: 0; outline: none;
        `;
        btn.setAttribute('aria-label', t.ariaLabel || `${t.kind} ${t.id}`);
        btn.addEventListener('focus', () => btn.classList.add('a11y-focus'));
        btn.addEventListener('blur',  () => btn.classList.remove('a11y-focus'));
        this._root.appendChild(btn);
        rec = { item: t, btn };
        this._nodes.set(t.id, rec);
      }
      rec.item = t;
      // Center min-inflated hit area over the sprite's actual projected position.
      rec.btn.style.left = `${s.x - (w - t.width * this._camera.scale) / 2}px`;
      rec.btn.style.top  = `${s.y - (h - t.height * this._camera.scale) / 2}px`;
      rec.btn.style.width  = `${w}px`;
      rec.btn.style.height = `${h}px`;
    }
  }

  _onFocus(e) {
    const btn = e.target;
    if (btn.dataset && btn.dataset.id) {
      window.dispatchEvent(new CustomEvent('factory:focus-entity', {
        detail: { id: btn.dataset.id, kind: btn.dataset.kind },
      }));
    }
  }

  dispose() {
    this._root.remove();
  }
}
