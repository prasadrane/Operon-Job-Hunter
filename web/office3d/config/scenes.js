const SCENES = {
  ROOMS: {
    EXECUTIVE_SUITE: { platformY: 1.5, elevation: 9, stagePos: [0, 0, -16], glowColor: '#f59e0b', deskPos: [0, 2.1, -16] },
    WAR_ROOM: { centerX: 0, centerZ: 0, radius: 4.2, plasmaHeight: 6, arcDistance: 16 },
    LOUNGE_AREA: { counterZ: 16, counterWidth: 8, sofaPositions: [[-7,0],[7,0]], lampX: -8, sideTables: [-3.5, 3.5] },
    DISCOVERY_WING: { xPos: -14, agentCount: 5, deskSpacing: 6, zRange: [-12, 12] },
    TAILORING_WING: { xPos: 14, agentCount: 4, deskSpacing: 6, zRange: [-12, 12] },
    CENTER_CORRIDOR: { width: 12, length: 42 },
  },

  CAMERA_PRESETS: {
    boss: { pos: [0, 3, -16], dist: 12 },
    discovery: { pos: [-14, 2, 0], dist: 22 },
    intelligence: { pos: [14, 2, 0], dist: 22 },
    warroom: { pos: [0, 2, 0], dist: 16 },
    lounge: { pos: [0, 2, 16], dist: 18 },
  },

  ZONE_COLORS: {
    discovery: '#3b82f6',
    tailoring: '#a78bfa',
    warRoom: '#06b6d4',
    lounge: '#10b981',
    executive: '#f59e0b',
    border: '#38bdf8',
  },

  LAYOUT: {
    floorSize: [44, 42],
    ceilingHeight: 14,
    pillarPositions: [
      [-21.5, 20.5], [21.5, 20.5], [-21.5, -20.5], [21.5, -20.5],
      [0, -20.5], [0, 20.5], [-21.5, 0], [21.5, 0]
    ],
    neonRingRadii: [5, 15, 25],
    gridLines: 44,
  },

  ANIMATION: {
    defaultSpeedMult: 1.0,
    reducedMotionSpeedMult: 0.5,
    dustCount: 200,
    steamCount: 30,
    fpsUpdateIntervalMs: 1000,
  },
};

// Camera preset keys for keyboard shortcuts
const CAMERA_KEYS = ['1', '2', '3', '4', '5'];
const CAMERA_LABELS = ['BOSS', 'DISCOVERY', 'INTELLIGENCE', 'WAR ROOM', 'LOUNGE'];
