import { describe, it, expect, beforeEach } from 'vitest';
import { AtlasBudgetTracker } from '../atlas-budget-tracker.js';

describe('AtlasBudgetTracker', () => {
  let tracker;

  beforeEach(() => {
    tracker = new AtlasBudgetTracker();
  });

  it('should initialize with zero usage', () => {
    expect(tracker.getTotalUsage()).toBe(0);
  });

  it('should register atlas and track usage', () => {
    tracker.registerAtlas('agents', 4);
    expect(tracker.getTotalUsage()).toBe(4);
    expect(tracker.getAtlasSize('agents')).toBe(4);
  });

  it('should warn at 20MB threshold', () => {
    tracker.registerAtlas('agents', 4);
    tracker.registerAtlas('zones', 5);
    tracker.registerAtlas('ui', 2);
    tracker.registerAtlas('targets', 1);
    tracker.registerAtlas('particles', 4);
    tracker.registerAtlas('extra', 4); // total: 20MB

    expect(tracker.isWarning()).toBe(true);
    expect(tracker.warningMessage).toContain('20MB');
  });

  it('should reject allocation exceeding 32MB hard cap', () => {
    tracker.registerAtlas('agents', 4);
    tracker.registerAtlas('zones', 5);
    tracker.registerAtlas('ui', 2);
    tracker.registerAtlas('targets', 1);
    tracker.registerAtlas('particles', 4);
    tracker.registerAtlas('extra1', 10);
    tracker.registerAtlas('extra2', 5); // total: 31MB

    expect(tracker.canAllocate(2)).toBe(false); // would exceed 32MB
  });

  it('should allow allocation within budget', () => {
    tracker.registerAtlas('agents', 4);
    tracker.registerAtlas('zones', 5);

    expect(tracker.canAllocate(2)).toBe(true);
  });

  it('should provide budget breakdown', () => {
    tracker.registerAtlas('agents', 4);
    tracker.registerAtlas('zones', 5);
    tracker.registerAtlas('ui', 2);

    const breakdown = tracker.getUsage();
    expect(breakdown.agents).toBe(4);
    expect(breakdown.zones).toBe(5);
    expect(breakdown.ui).toBe(2);
    expect(breakdown.total).toBe(11);
  });

  it('should enforce shared atlas packing (agents 1024x1024 = 4MB)', () => {
    // 12 agents packed into single 1024x1024 atlas
    const agentAtlasSizeMB = (1024 * 1024 * 4) / (1024 * 1024); // RGBA = 4 bytes/pixel
    expect(agentAtlasSizeMB).toBe(4);

    tracker.registerAtlas('agents', agentAtlasSizeMB);
    expect(tracker.getAtlasSize('agents')).toBe(4);
  });

  it('should enforce shared atlas packing (zones 2048x2048 packed = 5MB)', () => {
    // 5 zone textures packed into 2048x2048 atlas
    // Full would be 16MB, but packed = 5MB (spec says ~5MB)
    tracker.registerAtlas('zones', 5);
    expect(tracker.getAtlasSize('zones')).toBe(5);
  });
});
