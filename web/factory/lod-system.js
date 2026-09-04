/**
 * Zoom-dependent LOD (Level of Detail) system
 * Manages rendering tier selection, crossfade transitions, viewport culling
 */
export class LODSystem {
  constructor() {
    this.currentTier = 'full';
    this.previousTier = null;
    this.isTransitioning = false;
    this.transitionProgress = 0;
    this.transitionDuration = 200; // 200ms crossfade
    this.transitionTimer = 0;
  }

  /**
   * Get LOD tier for given zoom level
   * @param {number} zoom - Camera zoom (0.25–2.0)
   * @returns {string} 'top-down' | 'simplified' | 'standard' | 'full'
   */
  getTier(zoom) {
    if (zoom < 0.5) return 'top-down';
    if (zoom <= 0.75) return 'simplified';
    if (zoom <= 1.0) return 'standard';
    return 'full';
  }

  /**
   * Set camera zoom and trigger tier transition if changed
   * @param {number} zoom - Camera zoom level
   */
  setZoom(zoom) {
    const newTier = this.getTier(zoom);

    if (newTier !== this.currentTier) {
      this.previousTier = this.currentTier;
      this.currentTier = newTier;
      this.isTransitioning = true;
      this.transitionProgress = 0;
      this.transitionTimer = 0;
    }
  }

  /**
   * Update crossfade transition
   * @param {number} deltaTime - Time since last frame in ms
   */
  update(deltaTime) {
    if (this.isTransitioning) {
      this.transitionTimer += deltaTime;
      this.transitionProgress = Math.min(1, this.transitionTimer / this.transitionDuration);

      if (this.transitionProgress >= 1) {
        this.isTransitioning = false;
        this.previousTier = null;
      }
    }
  }

  /**
   * Check if entity should be rendered (viewport culling)
   * @param {Object} entity - Entity { x, y, width, height }
   * @param {Object} viewport - Viewport { x, y, width, height }
   * @param {number} tileWidth - Tile width for buffer (default 48px)
   * @returns {boolean} True if entity should render
   */
  shouldRender(entity, viewport, tileWidth = 48) {
    const buffer = tileWidth; // 1 tile buffer

    const entityLeft = entity.x;
    const entityRight = entity.x + entity.width;
    const entityTop = entity.y;
    const entityBottom = entity.y + entity.height;

    const viewportLeft = viewport.x - buffer;
    const viewportRight = viewport.x + viewport.width + buffer;
    const viewportTop = viewport.y - buffer;
    const viewportBottom = viewport.y + viewport.height + buffer;

    return !(
      entityRight < viewportLeft ||
      entityLeft > viewportRight ||
      entityBottom < viewportTop ||
      entityTop > viewportBottom
    );
  }

  /**
   * Get rendering config for current tier
   * @returns {Object} { tier, showParticles, showAnimations, showTooltips, spriteDetail }
   */
  getRenderConfig() {
    const configs = {
      'top-down': {
        showParticles: false,
        showAnimations: false,
        showTooltips: false,
        spriteDetail: 'none', // zone color fills only
        drawSprites: false,
      },
      'simplified': {
        showParticles: false,
        showAnimations: false,
        showTooltips: false,
        spriteDetail: 'dots', // agent dots, no animations
        drawSprites: true,
      },
      'standard': {
        showParticles: false,
        showAnimations: true,
        showTooltips: false,
        spriteDetail: '4-dir', // 4-dir walk
        drawSprites: true,
      },
      'full': {
        showParticles: true,
        showAnimations: true,
        showTooltips: true,
        spriteDetail: '4-dir', // full detail
        drawSprites: true,
      },
    };

    return configs[this.currentTier] || configs['full'];
  }

  /**
   * Get alpha for crossfade (previous tier fades out, current fades in)
   * @param {string} tier - Tier to get alpha for
   * @returns {number} Alpha (0–1)
   */
  getTierAlpha(tier) {
    if (!this.isTransitioning) {
      return tier === this.currentTier ? 1 : 0;
    }

    if (tier === this.currentTier) {
      return this.transitionProgress; // fade in
    }

    if (tier === this.previousTier) {
      return 1 - this.transitionProgress; // fade out
    }

    return 0;
  }
}
