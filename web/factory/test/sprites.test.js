import { describe, it, expect, beforeEach } from 'vitest';
import { SpriteSheetLoader } from '../sprites.js';
import { ART_STYLE } from '../art-style.js';

describe('SpriteSheetLoader', () => {
  let loader;

  beforeEach(() => {
    loader = new SpriteSheetLoader();
  });

  it('should extract frames from sprite sheet', () => {
    // Mock sprite sheet (4 rows × 8 cols = 32 frames)
    const sheet = {
      width: ART_STYLE.SHEET_COLS * ART_STYLE.FRAME_WIDTH, // 256px
      height: ART_STYLE.SHEET_ROWS * ART_STYLE.FRAME_HEIGHT, // 128px
    };

    const frames = loader.extractFrames(sheet);

    expect(frames).toHaveLength(32);
    expect(frames[0]).toEqual({
      x: 0,
      y: 0,
      width: 32,
      height: 32,
    });
    expect(frames[7]).toEqual({
      x: 7 * 32, // 224px
      y: 0,
      width: 32,
      height: 32,
    });
  });

  it('should get frames by state and direction', () => {
    const sheet = { width: 256, height: 128 };
    const frames = loader.extractFrames(sheet);

    // Row 0 = idle (8 frames)
    const idleFrames = loader.getFramesByState(frames, 'idle');
    expect(idleFrames).toHaveLength(8);

    // Row 1 = walk (8 frames, but only NE/SE rendered)
    const walkFrames = loader.getFramesByState(frames, 'walk');
    expect(walkFrames).toHaveLength(8);
  });
});
