import { DIRECTIONS } from './art-style.js';

/**
 * Individual agent sprite with 4-dir+flip animation
 */
export class AgentSprite {
  constructor() {
    this.direction = DIRECTIONS.SE; // default facing
    this.isFlipped = false;
    this.currentState = 'idle';
    this.currentFrame = 0;
  }

  /**
   * Set direction with horizontal flip for opposite directions
   * 4-dir+flip convention: NE/SE are base, NW/SW are flipped
   * @param {string} dir - Direction (NE, SE, SW, NW)
   */
  setDirection(dir) {
    // NW is flip of NE, SW is flip of SE
    if (dir === DIRECTIONS.NW) {
      this.direction = DIRECTIONS.NE;
      this.isFlipped = true;
    } else if (dir === DIRECTIONS.SW) {
      this.direction = DIRECTIONS.SE;
      this.isFlipped = true;
    } else {
      this.direction = dir;
      this.isFlipped = false;
    }
  }

  /**
   * Set animation frame index (0-7)
   * @param {number} frameIndex - Frame index
   */
  setFrame(frameIndex) {
    this.currentFrame = frameIndex % 8; // wrap around
  }

  /**
   * Set animation state
   * @param {string} state - Animation state ('idle', 'walk', 'work', 'distressed')
   */
  setState(state) {
    this.currentState = state;
    this.currentFrame = 0; // reset to first frame
  }
}
