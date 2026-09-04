const RECENT_VIEWS_KEY = 'factory_recent_views';
const MAX_RECENT = 5;
const TRACKED_PARAMS = ['zoom', 'pan_x', 'pan_y', 'focus', 'mode', 'filters', 'job'];

/**
 * URL router for factory visualization deep linking.
 * Uses history.pushState — no page reloads.
 */
export class Router {
  constructor() {
    this._onPopState = this._handlePopState.bind(this);
    window.addEventListener('popstate', this._onPopState);
  }

  /**
   * Get current params from URL.
   * @returns {Object} param key-value pairs
   */
  getParams() {
    const url = new URL(window.location.href);
    const params = {};
    for (const key of TRACKED_PARAMS) {
      const val = url.searchParams.get(key);
      if (val != null) params[key] = val;
    }
    return params;
  }

  /**
   * Push a partial update to URL params (merges with existing).
   * @param {Object} updates - Key-value pairs to set (null/undefined removes param)
   */
  pushUpdate(updates) {
    const url = new URL(window.location.href);
    for (const [key, val] of Object.entries(updates)) {
      if (val == null || val === '') {
        url.searchParams.delete(key);
      } else {
        url.searchParams.set(key, String(val));
      }
    }
    window.history.pushState(null, '', url.toString());
    this._saveRecentView(url.toString());
  }

  /**
   * Restore state from URL (called on initial load).
   * @param {Function} applyFn - Called with params object to apply state
   */
  applyUrl(applyFn) {
    const params = this.getParams();
    if (Object.keys(params).length > 0) {
      applyFn(params);
    }
  }

  /**
   * Copy current URL to clipboard.
   * @returns {string} The current URL
   */
  copyLink() {
    const url = window.location.href;
    navigator.clipboard.writeText(url).catch(() => {});
    return url;
  }

  /**
   * Get recent views from localStorage.
   * @returns {string[]} Array of URLs, most recent first
   */
  getRecentViews() {
    try {
      const raw = localStorage.getItem(RECENT_VIEWS_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  }

  destroy() {
    window.removeEventListener('popstate', this._onPopState);
  }

  _handlePopState() {
    // Dispatch custom event so state manager can react
    window.dispatchEvent(new CustomEvent('factory:urlchange', { detail: this.getParams() }));
  }

  _saveRecentView(url) {
    try {
      let views = this.getRecentViews();
      // Remove duplicate if exists
      views = views.filter(v => v !== url);
      views.unshift(url);
      if (views.length > MAX_RECENT) views = views.slice(0, MAX_RECENT);
      localStorage.setItem(RECENT_VIEWS_KEY, JSON.stringify(views));
    } catch {
      // localStorage may be unavailable
    }
  }
}
