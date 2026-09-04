import { describe, it, expect, beforeEach } from 'vitest';
import { BitmapTextManager } from '../bitmap-text-manager.js';

describe('BitmapTextManager', () => {
  let manager;

  beforeEach(() => {
    manager = new BitmapTextManager();
  });

  it('should initialize with empty font atlas', () => {
    expect(manager.fonts.size).toBe(0);
  });

  it('should load font atlas for given size', async () => {
    await manager.loadFont(14, '/fonts/roboto-14.fnt');
    expect(manager.fonts.has(14)).toBe(true);
  });

  it('should create BitmapText with correct size', async () => {
    await manager.loadFont(18, '/fonts/roboto-18.fnt');
    const text = manager.createText('Hello', 18);

    expect(text.text).toBe('Hello');
    expect(text.fontSize).toBe(18);
  });

  it('should fallback to 14px if size not available', async () => {
    await manager.loadFont(14, '/fonts/roboto-14.fnt');
    const text = manager.createText('Hello', 99); // 99px not loaded

    expect(text.fontSize).toBe(14);
  });

  it('should pool BitmapText instances by size', async () => {
    await manager.loadFont(14, '/fonts/roboto-14.fnt');

    const text1 = manager.createText('Hello', 14);
    const text2 = manager.createText('World', 14);

    const pool = manager.getTextPool(14);
    expect(pool).toHaveLength(2);
  });

  it('should return nearest size if exact size not loaded', async () => {
    await manager.loadFont(14, '/fonts/roboto-14.fnt');
    await manager.loadFont(18, '/fonts/roboto-18.fnt');
    await manager.loadFont(24, '/fonts/roboto-24.fnt');

    expect(manager.getNearestSize(16)).toBe(14);
    expect(manager.getNearestSize(20)).toBe(18);
    expect(manager.getNearestSize(30)).toBe(24);
  });
});
