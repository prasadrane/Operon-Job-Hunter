import { ART_STYLE } from './art-style.js';

/**
 * Status orb floating above agent's head
 * Pulses to indicate state changes
 */
export class StatusOrb {
  constructor() {
    this.status = 'sleeping';
    this.color = ART_STYLE.COLORS.SLEEPING;
    this.scale = ART_STYLE.ORB_SCALE_MIN;
    this.alpha = ART_STYLE.ORB_ALPHA_MAX;
    this.frameTimer = 0;
    this.currentFrame = 0;
    this.totalFrames = 4;
  }

  /**
   * Set orb status and update color
   * @param {string} status - 'active', 'sleeping', 'error', 'busy'
   */
  setStatus(status) {
    this.status = status;
    this.color = ART_STYLE.COLORS[status.toUpperCase()] || ART_STYLE.COLORS.SLEEPING;
  }

  /**
   * Update pulse animation
   * @param {number} deltaTime - Time since last update in ms
   */
  update(deltaTime) {
    const frameDuration = 1000 / ART_STYLE.ORB_FPS; // 500ms per frame at 2fps

    this.frameTimer += deltaTime;
    if (this.frameTimer >= frameDuration) {
      this.currentFrame = (this.currentFrame + 1) % this.totalFrames;
      this.frameTimer = 0;

      // Update scale and alpha based on frame
      // Frame 0: scale 1.0, alpha 1.0
      // Frame 1: scale 1.2, alpha 0.7
      // Frame 2: scale 1.0, alpha 1.0
      // Frame 3: scale 1.0, alpha 1.0

      if (this.currentFrame === 1) {
        this.scale = ART_STYLE.ORB_SCALE_MAX;
        this.alpha = ART_STYLE.ORB_ALPHA_MIN;
      } else {
        this.scale = ART_STYLE.ORB_SCALE_MIN;
        this.alpha = ART_STYLE.ORB_ALPHA_MAX;
      }
    }
  }

  /**
   * Get render data for PixiJS
   * @returns {Object} { color, scale, alpha }
   */
  getRenderData() {
    return {
      color: this.color,
      scale: this.scale,
      alpha: this.alpha,
    };
  }
}
