/**
 * Canvas2D fallback for systems without WebGL
 * Restrictions:
 *   - No particles
 *   - Cap entities at 20 (down from 50)
 *   - Top-down projection (no isometric)
 *   - "Performance Mode" indicator
 */
export class Canvas2DFallback {
  constructor() {
    this.rendererMode = this.detectRendererMode();
    this.isTabVisible = true;
  }

  /**
   * Detect WebGL capability
   * @returns {string} 'webgl' | 'canvas2d'
   */
  detectRendererMode() {
    try {
      const canvas = document.createElement('canvas');
      const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
      return gl ? 'webgl' : 'canvas2d';
    } catch {
      return 'canvas2d';
    }
  }

  /**
   * Get current renderer mode (re-detects for testability)
   * @returns {string} 'webgl' | 'canvas2d'
   */
  getRendererMode() {
    this.rendererMode = this.detectRendererMode();
    return this.rendererMode;
  }

  /**
   * Get entity cap based on the current renderer mode
   * @returns {number} Max entities
   */
  getEntityCap() {
    return this.rendererMode === 'canvas2d' ? 20 : 50;
  }

  /**
   * Check if particles should be enabled
   * @returns {boolean}
   */
  shouldEnableParticles() {
    return this.rendererMode === 'webgl';
  }

  /**
   * Get projection mode
   * @returns {string} 'isometric' | 'top-down'
   */
  getProjection() {
    return this.rendererMode === 'canvas2d' ? 'top-down' : 'isometric';
  }

  /**
   * Handle visibility change event
   * @param {Event} event - visibilitychange event
   */
  handleVisibilityChange(event) {
    this.isTabVisible = !event.target.hidden;
  }

  /**
   * Check if rendering should be paused (tab hidden)
   * @returns {boolean}
   */
  shouldPauseRendering() {
    return !this.isTabVisible;
  }

  /**
   * Check if "Performance Mode" indicator should be shown
   * @returns {boolean}
   */
  shouldShowPerformanceIndicator() {
    return this.rendererMode === 'canvas2d';
  }

  /**
   * Setup visibility change listener
   */
  setupVisibilityListener() {
    document.addEventListener('visibilitychange', (event) => {
      this.handleVisibilityChange(event);
    });
  }

  /**
   * Get rendering config based on mode
   * @returns {Object}
   */
  getRenderConfig() {
    if (this.rendererMode === 'canvas2d') {
      return {
        mode: 'canvas2d',
        particles: false,
        entityCap: 20,
        projection: 'top-down',
        showPerformanceIndicator: true,
      };
    }

    return {
      mode: 'webgl',
      particles: true,
      entityCap: 50,
      projection: 'isometric',
      showPerformanceIndicator: false,
    };
  }
}
