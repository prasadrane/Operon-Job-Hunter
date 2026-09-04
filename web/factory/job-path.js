import { TIERS, TRACK_BOUNDS } from './renderer.js';

/**
 * 2D Serpentine Path Generator for Job Tokens (Mario/Contra Conveyor Assembly)
 */
export class JobPath {
  constructor(p0, p1, p2, p3) {
    this.p0 = p0;
    this.p1 = p1;
    this.p2 = p2;
    this.p3 = p3;
  }

  calculatePosition(t) {
    const u = 1 - t;
    const uu = u * u;
    const uuu = uu * u;
    const tt = t * t;
    const ttt = tt * t;

    const x = uuu * this.p0.x +
              3 * uu * t * this.p1.x +
              3 * u * tt * this.p2.x +
              ttt * this.p3.x;

    const y = uuu * this.p0.y +
              3 * uu * t * this.p1.y +
              3 * u * tt * this.p2.y +
              ttt * this.p3.y;

    return { x, y };
  }

  getBezierPoints() {
    return [this.p0, this.p1, this.p2, this.p3];
  }

  /**
   * Create path between two tiers (e.g. stage transition through U-turn tube)
   */
  static createBetweenTiers(fromTierIdx, toTierIdx) {
    const fromTier = TIERS[fromTierIdx] || TIERS[0];
    const toTier = TIERS[toTierIdx] || TIERS[Math.min(fromTierIdx + 1, TIERS.length - 1)];

    const isRightTurn = fromTier.dir === 1;
    const startX = isRightTurn ? TRACK_BOUNDS.maxX : TRACK_BOUNDS.minX;
    const bendX = isRightTurn ? TRACK_BOUNDS.pipeRightX : TRACK_BOUNDS.pipeLeftX;
    const endX = startX;

    const p0 = { x: startX, y: fromTier.y };
    const p1 = { x: bendX, y: fromTier.y };
    const p2 = { x: bendX, y: toTier.y };
    const p3 = { x: endX, y: toTier.y };

    return new JobPath(p0, p1, p2, p3);
  }

  /**
   * Backward-compatible helper for tests / generic zone arcs
   */
  static createBetweenZones(start, end, arcHeight = 20) {
    const midX = (start.x + end.x) / 2;
    const p1 = { x: midX - 30, y: start.y - arcHeight };
    const p2 = { x: midX + 30, y: end.y - arcHeight };
    return new JobPath(start, p1, p2, end);
  }
}
