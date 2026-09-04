/**
 * KeyboardNavigator — focusable registry + tab order + keyboard shortcuts.
 *
 * Tab order default: agents → jobs → zones → errors → controls.
 * Shortcuts (plan §Task 24):
 *   Tab / Shift+Tab      navigate focusables
 *   Enter | Space        open detail panel for focused item
 *   Esc                  close panel & return focus to trigger
 *   E                    focus latest error
 *   R                    retry focused error (emits 'factory:request-retry')
 *   L                    view logs for focused item
 *   ?                    toggle shortcut reference modal
 *   1–5                  zoom-to-preset zone
 *   0                    reset camera
 *
 * Emits:
 *   - 'factory:open-detail'      { kind, data, trigger: 'keyboard' }
 *   - 'factory:close-panel'
 *   - 'factory:focus-entity'     { id, kind }
 *   - 'factory:request-retry'    { errorId }
 *   - 'factory:view-logs'        { id, kind }
 *   - 'factory:toggle-shortcuts'
 *   - 'factory:zoom-zone'        { zoneIndex }
 */
export class KeyboardNavigator {
  constructor({ camera, entities, overlay, panels } = {}) {
    this._camera = camera;
    this._entities = entities;
    this._overlay = overlay;
    this._panels = panels;
    /** @type {Map<string, Object>} id → item */
    this._items = new Map();
    this._order = ['agent', 'job', 'zone', 'error', 'control'];
    this._sorted = [];
    this._idx = -1;
    /** @type {Array<Object>} trigger stack for Esc return-focus */
    this._triggerStack = [];
    this._onKey = this._onKey.bind(this);
  }

  register(item) {
    this._items.set(item.id, item);
    this._resort();
  }
  unregister(id) {
    this._items.delete(id);
    this._resort();
  }

  setTabOrder(kinds) {
    this._order = kinds;
    this._resort();
  }

  focusNext() {
    if (!this._sorted.length) return;
    this._idx = (this._idx + 1) % this._sorted.length;
    this._sorted[this._idx].focus();
  }
  focusPrevious() {
    if (!this._sorted.length) return;
    this._idx = (this._idx - 1 + this._sorted.length) % this._sorted.length;
    this._sorted[this._idx].focus();
  }
  focusById(id) {
    const item = this._items.get(id);
    if (item) { item.focus(); this._idx = this._sorted.indexOf(item); }
  }
  focusLatestError() {
    const errors = this._sorted.filter(i => i.kind === 'error');
    const newest = errors.find(e => e.newest) || errors[0];
    if (newest) { newest.focus(); this._idx = this._sorted.indexOf(newest); }
  }

  /** Push trigger onto return-focus stack when panel opens. */
  _onPanelOpen(triggerItem) {
    this._triggerStack.push(triggerItem);
  }
  /** Close panel and return focus to most recent trigger. */
  _closePanel() {
    const t = this._triggerStack.pop();
    if (t) t.focus();
    window.dispatchEvent(new CustomEvent('factory:close-panel'));
  }

  attach()  { window.addEventListener('keydown', this._onKey); }
  detach()  { window.removeEventListener('keydown', this._onKey); }

  _onKey(e) {
    if (e.key === 'Tab') {
      if (this._sorted.length) {
        e.preventDefault();
        e.shiftKey ? this.focusPrevious() : this.focusNext();
      }
      return;
    }
    if (e.key === 'Escape') { this._closePanel(); return; }
    if (e.key === 'Enter' || e.key === ' ') {
      const item = this._sorted[this._idx];
      if (item) {
        e.preventDefault();
        this._onPanelOpen(item);
        window.dispatchEvent(new CustomEvent('factory:open-detail', {
          detail: { kind: item.kind, data: item.data || { id: item.id }, trigger: 'keyboard' },
        }));
      }
      return;
    }
    const k = e.key.toLowerCase();
    if (k === 'e') { this.focusLatestError(); return; }
    if (k === '?') { window.dispatchEvent(new CustomEvent('factory:toggle-shortcuts')); return; }
    if (k === '0') { this._camera?.reset(); return; }
    if (['1','2','3','4','5'].includes(k)) {
      window.dispatchEvent(new CustomEvent('factory:zoom-zone', { detail: { zoneIndex: parseInt(k, 10) - 1 } }));
      return;
    }
    if (k === 'r') {
      const item = this._sorted[this._idx];
      if (item && item.kind === 'error') {
        window.dispatchEvent(new CustomEvent('factory:request-retry', { detail: { errorId: item.id } }));
      }
      return;
    }
    if (k === 'l') {
      const item = this._sorted[this._idx];
      if (item) window.dispatchEvent(new CustomEvent('factory:view-logs', { detail: { id: item.id, kind: item.kind } }));
      return;
    }
  }

  _resort() {
    const rank = Object.fromEntries(this._order.map((k, i) => [k, i]));
    this._sorted = Array.from(this._items.values())
      .sort((a, b) => (rank[a.kind] ?? 99) - (rank[b.kind] ?? 99) || a.order - b.order);
    this._idx = -1;
  }
}

/**
 * ConfirmationModal — wraps native <dialog>, focus-trapped.
 * Used for state-changing recovery actions (Retry / Modify / Mark Manual).
 */
export class ConfirmationModal {
  constructor() {
    this._dialog = document.createElement('dialog');
    this._dialog.setAttribute('aria-modal', 'true');
    this._dialog.setAttribute('role', 'dialog');
    this._dialog.innerHTML = `
      <form method="dialog" style="display:flex;flex-direction:column;gap:12px;padding:16px;background:#0d121f;color:#f3f4f6;border:1px solid #2a2a3e;border-radius:6px;">
        <h3 data-role="title" style="margin:0;font-size:16px;color:#f3f4f6;"></h3>
        <p data-role="body" style="margin:0;font-size:14px;color:#d1d5db;"></p>
        <div style="display:flex;gap:8px;justify-content:flex-end;">
          <button data-role="cancel" value="cancel" style="padding:8px 14px;background:transparent;color:#d1d5db;border:1px solid #2a2a3e;border-radius:4px;cursor:pointer;">Cancel</button>
          <button data-role="confirm" value="confirm" autofocus
            style="padding:8px 14px;background:#3b82f6;color:#fff;border:0;border-radius:4px;cursor:pointer;">Confirm</button>
        </div>
      </form>
    `;
    document.body.appendChild(this._dialog);
  }

  confirm({ title, body, confirmLabel = 'Confirm', cancelLabel = 'Cancel' }) {
    this._dialog.querySelector('[data-role="title"]').textContent = title;
    this._dialog.querySelector('[data-role="body"]').textContent = body;
    this._dialog.querySelector('[data-role="confirm"]').textContent = confirmLabel;
    this._dialog.querySelector('[data-role="cancel"]').textContent = cancelLabel;
    return new Promise((resolve) => {
      this._dialog.addEventListener('close', () => {
        resolve(this._dialog.returnValue === 'confirm');
      }, { once: true });
      this._dialog.showModal();
    });
  }

  dispose() { this._dialog.remove(); }
}
