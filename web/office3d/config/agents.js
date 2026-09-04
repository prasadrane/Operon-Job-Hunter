/**
 * CareerGraph AI — 3D Virtual Office Agent Configuration
 *
 * Single source of truth for all agent appearances, positions, colors,
 * and behavioral metadata in the 3D virtual office viewport.
 * Synced from SSE subagent stream keys: src/interface/api/subagent_state.py
 */

const AGENT_CONFIGS = {
  boss_apex: {
    id: "boss_apex",
    name: "Commander Apex",
    role: "Executive Orchestrator",
    color: 0xf59e0b,       // Amber/Gold
    suitColor: 0x1e1b4b,
    visorColor: 0xfde047,
    icon: "👑",
    deskPos: { x: 0, y: 1.5, z: -16 },
    chairPos: { x: 0, y: 1.5, z: -17.5 },
    warRoomPos: { x: 0, y: 0, z: -4.8 },
    loungePos: { x: 0, y: 0, z: 16 },
    isBoss: true,
    accessory: "crown",
  },
  scout_falcon: {
    id: "scout_falcon",
    name: "Scout Falcon",
    role: "Fast-Path ATS (GH / Lever / Ashby)",
    color: 0x3b82f6,       // Electric Blue
    suitColor: 0x172554,
    visorColor: 0x60a5fa,
    icon: "⚡",
    deskPos: { x: -14, y: 0, z: -12 },
    chairPos: { x: -14, y: 0, z: -13.5 },
    warRoomPos: { x: -4.5, y: 0, z: -2.5 },
    loungePos: { x: -8, y: 0, z: 15 },
    accessory: "magnifier",
  },
  scout_atlas: {
    id: "scout_atlas",
    name: "Scout Atlas",
    role: "Enterprise ATS (Workday / SmartRecruiters)",
    color: 0x6366f1,       // Indigo
    suitColor: 0x1e1b4b,
    visorColor: 0x818cf8,
    icon: "🏢",
    deskPos: { x: -14, y: 0, z: -6 },
    chairPos: { x: -14, y: 0, z: -7.5 },
    warRoomPos: { x: -4.8, y: 0, z: 0 },
    loungePos: { x: -6, y: 0, z: 16 },
    accessory: "magnifier",
  },
  scout_titan: {
    id: "scout_titan",
    name: "Scout Titan",
    role: "Big Tech Harvester (Amazon / MSFT / Google)",
    color: 0x06b6d4,       // Cyan
    suitColor: 0x083344,
    visorColor: 0x22d3ee,
    icon: "🌐",
    deskPos: { x: -14, y: 0, z: 0 },
    chairPos: { x: -14, y: 0, z: -1.5 },
    warRoomPos: { x: -4.2, y: 0, z: 2.5 },
    loungePos: { x: -4, y: 0, z: 15 },
    accessory: "magnifier",
  },
  scout_horizon: {
    id: "scout_horizon",
    name: "Scout Horizon",
    role: "Market Sweeper (EchoJobs / JobSpy)",
    color: 0x10b981,       // Emerald
    suitColor: 0x064e3b,
    visorColor: 0x34d399,
    icon: "📡",
    deskPos: { x: -14, y: 0, z: 6 },
    chairPos: { x: -14, y: 0, z: 4.5 },
    warRoomPos: { x: -2.5, y: 0, z: 4.2 },
    loungePos: { x: -2, y: 0, z: 16 },
    accessory: "magnifier",
  },
  scout_aegis: {
    id: "scout_aegis",
    name: "Scout Aegis",
    role: "Visa & Clearance Gatekeeper",
    color: 0xd97706,       // Bronze/Amber
    suitColor: 0x451a03,
    visorColor: 0xfbbf24,
    icon: "🛡️",
    deskPos: { x: -14, y: 0, z: 12 },
    chairPos: { x: -14, y: 0, z: 10.5 },
    warRoomPos: { x: 0, y: 0, z: 4.8 },
    loungePos: { x: 0, y: 0, z: 17 },
    accessory: "magnifier",
  },
  evaluator: {
    id: "evaluator",
    name: "Judge Minerva",
    role: "7-Block Rubric & Fit Scorer",
    color: 0xf59e0b,       // Gold
    suitColor: 0x451a03,
    visorColor: 0xfde68a,
    icon: "⚖️",
    deskPos: { x: 14, y: 0, z: -12 },
    chairPos: { x: 14, y: 0, z: -13.5 },
    warRoomPos: { x: 4.5, y: 0, z: -2.5 },
    loungePos: { x: 8, y: 0, z: 15 },
    accessory: "scales",
  },
  factguard: {
    id: "factguard",
    name: "FactGuard Sentry",
    role: "Anti-Hallucination Integrity",
    color: 0xef4444,       // Crimson/Shield
    suitColor: 0x450a0a,
    visorColor: 0xf87171,
    icon: "🛡️",
    deskPos: { x: 14, y: 0, z: -6 },
    chairPos: { x: 14, y: 0, z: -7.5 },
    warRoomPos: { x: 4.8, y: 0, z: 0 },
    loungePos: { x: 6, y: 0, z: 16 },
    accessory: "shield",
  },
  scribe: {
    id: "scribe",
    name: "Master Scribe",
    role: "GraphRAG Resume Compiler",
    color: 0x8b5cf6,       // Violet/Amethyst
    suitColor: 0x2e1065,
    visorColor: 0xa78bfa,
    icon: "📜",
    deskPos: { x: 14, y: 0, z: 0 },
    chairPos: { x: 14, y: 0, z: -1.5 },
    warRoomPos: { x: 4.2, y: 0, z: 2.5 },
    loungePos: { x: 4, y: 0, z: 15 },
    accessory: "stylus",
  },
  websurfer: {
    id: "websurfer",
    name: "Cyber-Pilot",
    role: "AXTree DOM Submitter",
    color: 0x14b8a6,       // Teal
    suitColor: 0x042f2e,
    visorColor: 0x2dd4bf,
    icon: "🚀",
    deskPos: { x: 14, y: 0, z: 6 },
    chairPos: { x: 14, y: 0, z: 4.5 },
    warRoomPos: { x: 2.5, y: 0, z: 4.2 },
    loungePos: { x: 2, y: 0, z: 16 },
    accessory: "rocket",
  },
  outreach: {
    id: "outreach",
    name: "Outreach Diplomat",
    role: "Recruiter Sourcing & InMail",
    color: 0xec4899,       // Pink/Magenta
    suitColor: 0x500724,
    visorColor: 0xf472b6,
    icon: "✉️",
    deskPos: { x: 14, y: 0, z: 12 },
    chairPos: { x: 14, y: 0, z: 10.5 },
    warRoomPos: { x: 1.5, y: 0, z: 4.6 },
    loungePos: { x: 5, y: 0, z: 17 },
    accessory: "envelope",
  },
  sentinel: {
    id: "sentinel",
    name: "Radar Sentinel",
    role: "Gmail Lifecycle & Interview Watcher",
    color: 0x0284c7,       // Sky Blue
    suitColor: 0x082f49,
    visorColor: 0x38bdf8,
    icon: "📊",
    deskPos: { x: 0, y: 0, z: 8 },
    chairPos: { x: 0, y: 0, z: 9.5 },
    warRoomPos: { x: 0, y: 0, z: 3.5 },
    loungePos: { x: -3, y: 0, z: 17 },
    accessory: "radar_dish",
  },
};

// Backwards-compat alias (sse uses "scout" → maps to scout_falcon)
AGENT_CONFIGS.scout = AGENT_CONFIGS.scout_falcon;

