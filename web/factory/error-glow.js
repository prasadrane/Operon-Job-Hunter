import { ERROR_VIS } from './art-style.js';

/**
 * Per-entity visual error treatment.
 * Tier 1 (root cause): pulsing red glow + error-code badge
 * Tier 2 (direct downstream): static amber outline
 * Tier 3 (indirect): no visual change
 *
 * Respects prefers-reduced-motion: tier 1 pulse → static red outline.
 */
export class ErrorGlow {
  constructor() {
    this.tier = 0;           // 0 = no error, 1/2/3 = tier
    this.errorCode = '';     // e.g. 'ERR_TIMEOUT'
    this.isActive = false;

    // Pulse state (tier 1 only)
    this.pulseTimer = 0;
    this.glowAlpha = 0;

    // Outline state (tier 2 + reduced-motion fallback)
    this.outlineAlpha = 0;
    this.outlineColor = null;

    // Reduced motion
    this.reducedMotion = false;
    if (typeof window !== 'undefined' && window.matchMedia) {
      this.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      window.matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', (e) => {
        this.reducedMotion = e.matches;
      });
    }
  }

  /**
   * Set error tier and optional error code
   * @param {number} tier - 1 (root), 2 (downstream), 3 (indirect/no-op)
   * @param {string|null} errorCode - Error code string (e.g., 'ERR_TIMEOUT') or null
   */
  setTier(tier, errorCode) {
    this.tier = tier;
    this.errorCode = errorCode; // Preserve null/undefined as-is (bug fix from plan)
    this.isActive = tier === 1 || tier === 2;
    this.pulseTimer = 0;
    this.glowAlpha = 0;
    this.outlineAlpha = 0;
    this.outlineColor = null;

    if (tier === 2) {
      this.outlineColor = ERROR_VIS.TIER2_COLOR;
      this.outlineAlpha = 1.0;
    }

    // Reduced motion: tier 1 → static red outline
    if (tier === 1 && this.reducedMotion) {
      this.outlineColor = ERROR_VIS.TIER1_COLOR;
      this.outlineAlpha = 1.0;
    }
  }

  /**
   * Override reduced motion flag (for testing or manual toggle)
   * @param {boolean} enabled
   */
  setReducedMotion(enabled) {
    this.reducedMotion = enabled;
    // Re-apply tier with new preference
    if (this.tier === 1) {
      const code = this.errorCode;
      this.setTier(1, code);
    }
  }

  /**
   * Update pulse animation (tier 1 only, unless reduced motion)
   * @param {number} deltaTime - Time since last frame in ms
   */
  update(deltaTime) {
    if (!this.isActive) return;

    if (this.tier === 1 && !this.reducedMotion) {
      this.pulseTimer = (this.pulseTimer + deltaTime) % ERROR_VIS.TIER1_PULSE_CYCLE_MS;
      // Sine wave: 0→0.3→0 over 2000ms
      const phase = (this.pulseTimer / ERROR_VIS.TIER1_PULSE_CYCLE_MS) * Math.PI * 2;
      const normalized = (Math.sin(phase - Math.PI / 2) + 1) / 2; // 0→1→0
      this.glowAlpha = normalized * ERROR_VIS.TIER1_PULSE_ALPHA_MAX;
    }
  }

  /**
   * Clear error state
   */
  clear() {
    this.tier = 0;
    this.errorCode = '';
    this.isActive = false;
    this.pulseTimer = 0;
    this.glowAlpha = 0;
    this.outlineAlpha = 0;
    this.outlineColor = null;
  }

  /**
   * Get render data for PixiJS
   * @returns {Object} { tier, glowColor, glowAlpha, outlineColor, outlineAlpha, outlineWidth, showBadge, badgeText, badgePosition }
   */
  getRenderData() {
    const result = {
      tier: this.tier,
      glowColor: null,
      glowAlpha: 0,
      outlineColor: this.outlineColor,
      outlineAlpha: this.outlineAlpha,
      outlineWidth: this.outlineColor ? ERROR_VIS.TIER2_OUTLINE_WIDTH : 0,
      showBadge: false,
      badgeText: '',
      badgePosition: null,
    };

    if (this.tier === 1) {
      result.glowColor = ERROR_VIS.TIER1_COLOR;
      result.glowAlpha = this.glowAlpha;

      if (this.errorCode) {
        result.showBadge = true;
        result.badgeText = this.errorCode;
        result.badgePosition = {
          x: ERROR_VIS.BADGE_OFFSET_X,
          y: ERROR_VIS.BADGE_OFFSET_Y,
        };
      }
    }

    return result;
  }
}

// Re-export ERROR_VIS for test convenience
export { ERROR_VIS };
