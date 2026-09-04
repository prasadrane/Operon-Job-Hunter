/**
 * Art style constants for factory visualization
 * Based on spec Section 6A: Art Style Guide
 */
export const ART_STYLE = {
  // Chibi proportions
  AGENT_HEIGHT: 32, // px (fits 48x24 tile)
  HEAD_TO_BODY_RATIO: 1/3,
  EYE_SIZE: 4, // px diameter
  PUPIL_SIZE: 2, // px diameter
  HAND_SIZE: 3, // px radius

  // Line weights
  LINE_OUTER: 2, // px (darkened base color)
  LINE_INNER: 1, // px (slightly lighter)

  // Sprite dimensions
  FRAME_WIDTH: 32, // px
  FRAME_HEIGHT: 32, // px
  SHEET_COLS: 8, // frames per row
  SHEET_ROWS: 4, // states (idle, walk, work, distressed)

  // Atlas dimensions
  ATLAS_WIDTH: 1024,
  ATLAS_HEIGHT: 1024,

  // Animation frame rates (fps)
  FPS_IDLE: 4,
  FPS_WALK: 10,
  FPS_WORK: 8,
  FPS_DISTRESSED: 6,

  // Status orb
  ORB_SIZE: 12, // px diameter
  ORB_FPS: 2,
  ORB_SCALE_MIN: 1.0,
  ORB_SCALE_MAX: 1.2,
  ORB_ALPHA_MIN: 0.7,
  ORB_ALPHA_MAX: 1.0,

  // Colors (OKLCH - will be converted to RGB)
  COLORS: {
    ACTIVE: '#10b981', // green
    SLEEPING: '#6b7280', // gray
    ERROR: '#ef4444', // red
    BUSY: '#f59e0b', // amber
  },

  // Transitions
  CROSSFADE_DURATION: 200, // ms
};

// Animation state names
export const ANIM_STATES = {
  IDLE: 'idle',
  WALK: 'walk',
  WORK: 'work',
  DISTRESSED: 'distressed',
};

// Error visualization constants (spec §8)
export const ERROR_VIS = {
  // Tier 1: Root cause
  TIER1_COLOR: '#ef4444',       // red glow
  TIER1_PULSE_CYCLE_MS: 2000,   // full 2s cycle
  TIER1_PULSE_ALPHA_MIN: 0.0,   // fully transparent at trough
  TIER1_PULSE_ALPHA_MAX: 0.30,  // 30% alpha per spec §6A
  TIER1_BADGE_BG: '#ef4444',
  TIER1_BADGE_TEXT: '#ffffff',

  // Tier 2: Direct downstream
  TIER2_COLOR: '#f59e0b',       // amber outline
  TIER2_OUTLINE_WIDTH: 2,       // px

  // Tier 3: Indirect (no visual change — no constants needed)
  TIER_NONE: 0,
  TIER_ROOT_CAUSE: 1,
  TIER_DIRECT_DOWNSTREAM: 2,
  TIER_INDIRECT: 3,

  // Error badge positioning (relative to agent sprite center)
  BADGE_OFFSET_X: 0,
  BADGE_OFFSET_Y: -24,          // above status orb
  BADGE_PADDING_X: 6,
  BADGE_PADDING_Y: 2,
  BADGE_FONT_SIZE: 10,
};

// Direction names
export const DIRECTIONS = {
  NE: 'ne', // northeast (up-right)
  SE: 'se', // southeast (down-right)
  SW: 'sw', // southwest (down-left)
  NW: 'nw', // northwest (up-left)
};
