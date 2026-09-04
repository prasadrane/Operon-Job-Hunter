import { ART_STYLE } from './art-style.js';

/**
 * Loads and manages sprite sheets for agents
 */
export class SpriteSheetLoader {
  /**
   * Extract all frames from a sprite sheet
   * @param {Object} sheet - Sprite sheet with width/height
   * @returns {Array} Array of frame objects {x, y, width, height}
   */
  extractFrames(sheet) {
    const frames = [];
    const { FRAME_WIDTH, FRAME_HEIGHT, SHEET_COLS, SHEET_ROWS } = ART_STYLE;

    for (let row = 0; row < SHEET_ROWS; row++) {
      for (let col = 0; col < SHEET_COLS; col++) {
        frames.push({
          x: col * FRAME_WIDTH,
          y: row * FRAME_HEIGHT,
          width: FRAME_WIDTH,
          height: FRAME_HEIGHT,
        });
      }
    }

    return frames;
  }

  /**
   * Get frames for a specific animation state
   * @param {Array} frames - All frames from extractFrames()
   * @param {string} state - Animation state ('idle', 'walk', 'work', 'distressed')
   * @returns {Array} Frames for that state (8 frames)
   */
  getFramesByState(frames, state) {
    const stateIndex = {
      'idle': 0,
      'walk': 1,
      'work': 2,
      'distressed': 3,
    }[state];

    if (stateIndex === undefined) {
      throw new Error(`Unknown animation state: ${state}`);
    }

    const startIdx = stateIndex * ART_STYLE.SHEET_COLS;
    return frames.slice(startIdx, startIdx + ART_STYLE.SHEET_COLS);
  }
}
