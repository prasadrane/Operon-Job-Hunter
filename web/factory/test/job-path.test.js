import { describe, it, expect } from 'vitest';
import { JobPath } from '../job-path.js';

describe('JobPath', () => {
  it('should calculate position along bezier curve', () => {
    const path = new JobPath(
      { x: 0, y: 0 },    // start
      { x: 50, y: -30 }, // control1
      { x: 100, y: -30 }, // control2
      { x: 150, y: 0 }   // end
    );

    // At t=0, should be at start
    const pos0 = path.calculatePosition(0);
    expect(pos0.x).toBe(0);
    expect(pos0.y).toBe(0);

    // At t=1, should be at end
    const pos1 = path.calculatePosition(1);
    expect(pos1.x).toBe(150);
    expect(pos1.y).toBe(0);

    // At t=0.5, should be somewhere in middle
    const posMid = path.calculatePosition(0.5);
    expect(posMid.x).toBeGreaterThan(0);
    expect(posMid.x).toBeLessThan(150);
  });

  it('should return 4 bezier control points', () => {
    const path = new JobPath(
      { x: 0, y: 0 },
      { x: 50, y: -30 },
      { x: 100, y: -30 },
      { x: 150, y: 0 }
    );

    const points = path.getBezierPoints();
    expect(points).toHaveLength(4);
    expect(points[0]).toEqual({ x: 0, y: 0 });
    expect(points[3]).toEqual({ x: 150, y: 0 });
  });
});
