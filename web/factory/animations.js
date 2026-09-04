import { ART_STYLE, ANIM_STATES } from './art-style.js';

/**
 * Controls animation state, frame advancement, and crossfade transitions
 */
export class AnimationController {
  constructor() {
    this.currentState = ANIM_STATES.IDLE;
    this.previousState = null;
    this.currentFrame = 0;
    this.frameTimer = 0;
    this.isCrossfading = false;
    this.crossfadeProgress = 0;
    this.crossfadeDuration = ART_STYLE.CROSSFADE_DURATION;

    // Check for reduced motion preference
    if (typeof window !== 'undefined' && window.matchMedia) {
      this.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

      // Listen for changes
      window.matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', (e) => {
        this.reducedMotion = e.matches;
      });
    } else {
      this.reducedMotion = false;
    }
    /** @type {import('./motion-gate.js').MotionGate|null} */
    this._motionGate = null;
  }

  /** Attach MotionGate as authoritative reduced-motion source. */
  setMotionGate(gate) {
    this._motionGate = gate;
    if (gate) {
      gate.on('change', (v) => { this.reducedMotion = v; });
      this.reducedMotion = gate.reduced;
    }
  }

  /** Whether this controller should skip animation this frame. */
  get skipAnimation() {
    return this._motionGate ? this._motionGate.reduced : this.reducedMotion;
  }

  /**
   * Play animation state with crossfade
   * @param {string} state - Animation state to play
   */
  play(state) {
    if (state === this.currentState && !this.isCrossfading) {
      return; // already playing this state
    }

    // Start crossfade
    this.previousState = this.currentState;
    this.currentState = state;
    this.isCrossfading = true;
    this.crossfadeProgress = 0;
    this.currentFrame = 0; // reset frame for new state
  }

  /**
   * Update animation based on elapsed time
   * @param {number} deltaTime - Time since last update in milliseconds
   */
  update(deltaTime) {
    // Skip animation if reduced motion is preferred (gate or local fallback)
    if (this.skipAnimation) {
      return;
    }

    // Update crossfade
    if (this.isCrossfading) {
      this.crossfadeProgress += deltaTime / this.crossfadeDuration;
      if (this.crossfadeProgress >= 1) {
        this.isCrossfading = false;
        this.crossfadeProgress = 1;
        this.previousState = null;
      }
    }

    // Advance frames based on current state FPS
    const fps = this.getFPSForState(this.currentState);
    const frameDuration = 1000 / fps;

    this.frameTimer += deltaTime;
    if (this.frameTimer >= frameDuration) {
      this.currentFrame = (this.currentFrame + 1) % 8; // 8 frames per state
      this.frameTimer = 0;
    }
  }

  /**
   * Get FPS for animation state
   * @param {string} state - Animation state
   * @returns {number} FPS for that state
   */
  getFPSForState(state) {
    const fpsMap = {
      [ANIM_STATES.IDLE]: ART_STYLE.FPS_IDLE,
      [ANIM_STATES.WALK]: ART_STYLE.FPS_WALK,
      [ANIM_STATES.WORK]: ART_STYLE.FPS_WORK,
      [ANIM_STATES.DISTRESSED]: ART_STYLE.FPS_DISTRESSED,
    };

    return fpsMap[state] || ART_STYLE.FPS_IDLE;
  }

  /**
   * Get current frame data for rendering
   * @returns {Object} { state, frame, previousState, crossfadeProgress }
   */
  getFrameData() {
    return {
      state: this.currentState,
      frame: this.currentFrame,
      previousState: this.previousState,
      crossfadeProgress: this.isCrossfading ? this.crossfadeProgress : 1,
    };
  }
}

/**
 * Legacy AnimationManager (kept for backward compatibility)
 * @deprecated Use AnimationController instead
 */
export class AnimationManager {
  constructor(entities) {
    this.entities = entities;
    this.controllers = new Map();
  }

  /**
   * Get or create animation controller for an entity
   * @param {string} entityId - Entity identifier
   * @returns {AnimationController} Animation controller
   */
  getController(entityId) {
    if (!this.controllers.has(entityId)) {
      this.controllers.set(entityId, new AnimationController());
    }
    return this.controllers.get(entityId);
  }

  /**
   * Update all animation controllers
   * @param {number} deltaTime - Time since last frame in ms
   */
  update(deltaTime) {
    for (const controller of this.controllers.values()) {
      controller.update(deltaTime);
    }
  }
}
