import { ensurePanelStyles } from './panel-styles.js';

/**
 * Manages detail panel lifecycle: open, close, focus trap, Esc dismissal.
 * Only one panel open at a time.
 */
export class PanelManager {
  /**
   * @param {HTMLElement} rootEl - The #panel-root container
   */
  constructor(rootEl) {
    this.rootEl = rootEl;
    this._activePanel = null;
    this._triggerEl = null;
    this._onKeydown = this._handleKeydown.bind(this);
  }

  /**
   * Open a panel, replacing any existing one.
   * @param {HTMLElement} panelEl - Panel DOM element (role="dialog")
   * @param {HTMLElement} triggerEl - Element that triggered the open (for return-focus)
   */
  open(panelEl, triggerEl) {
    ensurePanelStyles();

    // Close existing panel if any
    if (this._activePanel) {
      this._closeSilent();
    }

    this._activePanel = panelEl;
    this._triggerEl = triggerEl || document.activeElement;

    this.rootEl.appendChild(panelEl);

    // Focus first focusable element inside panel
    const focusable = this._getFocusable(panelEl);
    if (focusable.length > 0) {
      requestAnimationFrame(() => focusable[0].focus());
    } else {
      panelEl.setAttribute('tabindex', '-1');
      panelEl.focus();
    }

    // Attach keyboard listeners
    document.addEventListener('keydown', this._onKeydown);
  }

  /**
   * Close the active panel and return focus to trigger.
   */
  close() {
    if (!this._activePanel) return;
    this._closeSilent();
    // Return focus to trigger
    if (this._triggerEl && typeof this._triggerEl.focus === 'function') {
      this._triggerEl.focus();
    }
    this._triggerEl = null;
  }

  /**
   * @returns {boolean} True if a panel is currently open
   */
  isOpen() {
    return this._activePanel !== null;
  }

  /**
   * @returns {HTMLElement|null} Currently active panel element
   */
  getActivePanel() {
    return this._activePanel;
  }

  _closeSilent() {
    if (!this._activePanel) return;
    this.rootEl.removeChild(this._activePanel);
    document.removeEventListener('keydown', this._onKeydown);
    this._activePanel = null;
  }

  _handleKeydown(e) {
    if (e.key === 'Escape') {
      e.preventDefault();
      this.close();
      return;
    }
    // Focus trap on Tab
    if (e.key === 'Tab' && this._activePanel) {
      const focusable = this._getFocusable(this._activePanel);
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  _getFocusable(container) {
    const selectors = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
    return Array.from(container.querySelectorAll(selectors)).filter(
      el => !el.disabled && el.offsetParent !== null
    );
  }
}
