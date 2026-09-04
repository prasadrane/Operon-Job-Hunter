/**
 * VRAM budget enforcement singleton
 * Warning threshold: 20MB
 * Hard cap: 32MB
 * Budget allocation:
 *   - Agent sprite sheets: 1 shared 1024x1024 atlas = 4MB
 *   - Zone ground textures: 1 shared 2048x2048 atlas = 5MB
 *   - UI elements + fonts: 2MB
 *   - Render targets: 1MB
 *   - Particle systems: 4MB (temporary)
 *   - Total: ~16MB
 */
export class AtlasBudgetTracker {
  constructor() {
    this.atlases = new Map(); // name → sizeMB
    this.warningThreshold = 20; // MB
    this.hardCap = 32; // MB
    this.warningMessage = '';
  }

  /**
   * Register atlas and track VRAM usage
   * @param {string} name - Atlas name (e.g., 'agents', 'zones')
   * @param {number} sizeMB - Atlas size in MB
   * @returns {boolean} True if registration succeeded
   */
  registerAtlas(name, sizeMB) {
    const newTotal = this.getTotalUsage() + sizeMB;

    if (newTotal > this.hardCap) {
      console.error(
        `VRAM hard cap exceeded: ${newTotal.toFixed(2)}MB > ${this.hardCap}MB. ` +
        `Cannot register atlas '${name}' (${sizeMB}MB).`
      );
      return false;
    }

    this.atlases.set(name, sizeMB);

    if (this.isWarning()) {
      this.warningMessage = `VRAM warning: ${this.getTotalUsage().toFixed(2)}MB > ${this.warningThreshold}MB threshold.`;
      console.warn(this.warningMessage);
    }

    return true;
  }

  /**
   * Check if allocation would exceed hard cap
   * @param {number} sizeMB - Size to allocate in MB
   * @returns {boolean} True if allocation is allowed
   */
  canAllocate(sizeMB) {
    const newTotal = this.getTotalUsage() + sizeMB;
    return newTotal <= this.hardCap;
  }

  /**
   * Get size of specific atlas
   * @param {string} name - Atlas name
   * @returns {number} Size in MB, or 0 if not found
   */
  getAtlasSize(name) {
    return this.atlases.get(name) || 0;
  }

  /**
   * Get total VRAM usage
   * @returns {number} Total MB used
   */
  getTotalUsage() {
    let total = 0;
    for (const size of this.atlases.values()) {
      total += size;
    }
    return total;
  }

  /**
   * Check if warning threshold exceeded
   * @returns {boolean} True if usage > 20MB
   */
  isWarning() {
    return this.getTotalUsage() >= this.warningThreshold;
  }

  /**
   * Get budget breakdown
   * @returns {Object} { atlasName: sizeMB, total: totalMB }
   */
  getUsage() {
    const breakdown = {};
    for (const [name, size] of this.atlases.entries()) {
      breakdown[name] = size;
    }
    breakdown.total = this.getTotalUsage();
    return breakdown;
  }

  /**
   * Pre-compute atlas size from dimensions (for CI)
   * @param {number} width - Atlas width in pixels
   * @param {number} height - Atlas height in pixels
   * @param {number} bytesPerPixel - Bytes per pixel (default 4 for RGBA)
   * @returns {number} Size in MB
   */
  static computeAtlasSizeMB(width, height, bytesPerPixel = 4) {
    const bytes = width * height * bytesPerPixel;
    return bytes / (1024 * 1024);
  }

  /**
   * Validate atlas fits in budget (for CI pre-compute)
   * @param {string} name - Atlas name
   * @param {number} width - Atlas width
   * @param {number} height - Atlas height
   * @returns {boolean} True if atlas fits
   */
  validateAtlas(name, width, height) {
    const sizeMB = AtlasBudgetTracker.computeAtlasSizeMB(width, height);
    return this.canAllocate(sizeMB);
  }
}
