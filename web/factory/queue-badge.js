import { ART_STYLE } from './art-style.js';

/**
 * Queue count badge showing number of jobs waiting in zone
 * Circular badge with zone color, pulses when new job enters
 */
export class QueueBadge {
  /**
   * @param {string} zone - Zone name ('discovery', 'evaluation', etc.)
   */
  constructor(zone) {
    this.zone = zone;
    this.count = 0;
    this.color = this.getZoneColor(zone);
    this.scale = 1.0;
    this.pulseScale = 1.0;
    this.isPulsing = false;
    this.pulseTimer = 0;
    this.pulseDuration = 500; // 500ms pulse
  }

  /**
   * Get color for zone
   * @param {string} zone - Zone name
   * @returns {string} Hex color
   */
  getZoneColor(zone) {
    const zoneColors = {
      'discovery': '#3b82f6', // blue
      'evaluation': '#10b981', // green
      'tailoring': '#f59e0b', // yellow
      'submission': '#ef4444', // red
      'lifecycle': '#8b5cf6', // purple
    };
    return zoneColors[zone] || '#6b7280'; // gray default
  }

  /**
   * Set queue count (auto-pulses if count increased)
   * @param {number} count - Number of jobs in queue
   */
  setCount(count) {
    const previousCount = this.count;
    this.count = count;

    // Auto-pulse if count increased
    if (count > previousCount) {
      this.pulse();
    }
  }

  /**
   * Trigger pulse animation
   */
  pulse() {
    this.isPulsing = true;
    this.pulseTimer = 0;
    this.pulseScale = 1.3; // start at 130% size
  }

  /**
   * Update pulse animation
   * @param {number} deltaTime - Time since last frame in ms
   */
  update(deltaTime) {
    if (this.isPulsing) {
      this.pulseTimer += deltaTime;
      const progress = this.pulseTimer / this.pulseDuration;

      if (progress >= 1) {
        this.isPulsing = false;
        this.pulseScale = 1.0;
      } else {
        // Ease out: scale from 1.3 → 1.0
        this.pulseScale = 1.0 + 0.3 * (1 - progress);
      }
    }
  }

  /**
   * Get render data for PixiJS
   * @returns {Object} { zone, count, color, scale }
   */
  getRenderData() {
    return {
      zone: this.zone,
      count: this.count,
      color: this.color,
      scale: this.isPulsing ? this.pulseScale : 1.0,
    };
  }
}
