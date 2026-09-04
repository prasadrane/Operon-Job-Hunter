/**
 * BitmapText manager with MSDF font atlas
 * Replaces persistent PIXI.Text with PIXI.BitmapText for performance
 * Pre-rendered at 14/18/24px sizes
 */
export class BitmapTextManager {
  constructor() {
    this.fonts = new Map(); // size → font data
    this.textPool = new Map(); // size → BitmapText[]
    this.availableSizes = [14, 18, 24]; // pre-rendered sizes
  }

  /**
   * Load MSDF font atlas for given size
   * @param {number} size - Font size (14, 18, or 24)
   * @param {string} fontPath - Path to .fnt file
   */
  async loadFont(size, fontPath) {
    try {
      // In real implementation: PIXI.Assets.load(fontPath)
      // For now, mock the font data
      this.fonts.set(size, {
        path: fontPath,
        loaded: true,
      });

      if (!this.textPool.has(size)) {
        this.textPool.set(size, []);
      }
    } catch (error) {
      console.error(`Failed to load font size ${size}:`, error);
    }
  }

  /**
   * Load all pre-rendered font sizes
   */
  async loadAllFonts() {
    const fontPaths = {
      14: '/fonts/roboto-14.fnt',
      18: '/fonts/roboto-18.fnt',
      24: '/fonts/roboto-24.fnt',
    };

    const promises = Object.entries(fontPaths).map(([size, path]) =>
      this.loadFont(parseInt(size), path)
    );

    await Promise.all(promises);
  }

  /**
   * Create BitmapText with given text and size
   * @param {string} text - Text content
   * @param {number} size - Font size (falls back to nearest)
   * @returns {Object} BitmapText-like object { text, fontSize }
   */
  createText(text, size) {
    const actualSize = this.getNearestSize(size);

    // In real implementation: new PIXI.BitmapText(text, { fontName: ... })
    const bitmapText = {
      text,
      fontSize: actualSize,
      type: 'BitmapText',
    };

    // Add to pool
    if (!this.textPool.has(actualSize)) {
      this.textPool.set(actualSize, []);
    }
    this.textPool.get(actualSize).push(bitmapText);

    return bitmapText;
  }

  /**
   * Get nearest available font size
   * @param {number} size - Requested size
   * @returns {number} Nearest available size
   */
  getNearestSize(size) {
    // If exact size available, use it
    if (this.fonts.has(size)) {
      return size;
    }

    // Find nearest smaller size
    const available = Array.from(this.fonts.keys()).sort((a, b) => a - b);

    if (available.length === 0) {
      return 14; // default fallback
    }

    for (let i = available.length - 1; i >= 0; i--) {
      if (available[i] <= size) {
        return available[i];
      }
    }

    return available[0]; // smallest available
  }

  /**
   * Get text pool for given size
   * @param {number} size - Font size
   * @returns {Array} Array of BitmapText instances
   */
  getTextPool(size) {
    return this.textPool.get(size) || [];
  }

  /**
   * Create transient PIXI.Text (for tooltips <500ms)
   * @param {string} text - Text content
   * @param {Object} style - PixiJS text style
   * @returns {Object} Text-like object
   */
  createTransientText(text, style = {}) {
    // In real implementation: new PIXI.Text(text, style)
    return {
      text,
      type: 'Text',
      transient: true,
      style,
    };
  }
}
