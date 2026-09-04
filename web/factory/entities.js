import { AgentCharacter } from './agent-character.js';
import { JobToken } from './job-token.js';
import { TIERS, TRACK_BOUNDS } from './renderer.js';

export const AGENT_PLATFORM_STATIONS = {
  // Tier 1: Discovery Wing (Y=60, L->R)
  scout_falcon:   { tier: 1, x: -300, y: 60,  name: 'Scout Falcon', role: 'Fast-Path ATS', zone: 'discovery' },
  scout_atlas:    { tier: 1, x: -150, y: 60,  name: 'Scout Atlas', role: 'Enterprise (Workday)', zone: 'discovery' },
  scout_titan:    { tier: 1, x: 0,    y: 60,  name: 'Scout Titan', role: 'Big Tech Harvester', zone: 'discovery' },
  scout_horizon:  { tier: 1, x: 150,  y: 60,  name: 'Scout Horizon', role: 'Market Sweeper', zone: 'discovery' },
  scout_aegis:    { tier: 1, x: 300,  y: 60,  name: 'Scout Aegis', role: 'Visa & H-1B Gate', zone: 'discovery' },

  // Tier 2: Evaluation Lab (Y=155, R->L)
  evaluator:      { tier: 2, x: 150,  y: 155, name: 'Judge Minerva', role: '7-Block Rubric Scorer', zone: 'evaluation' },
  factguard:      { tier: 2, x: -150, y: 155, name: 'FactGuard Sentry', role: 'Ground Truth Guard', zone: 'evaluation' },

  // Tier 3: Tailoring Workshop (Y=250, L->R)
  scribe:         { tier: 3, x: -150, y: 250, name: 'Scribe & Tailor', role: 'GraphRAG PDF Tailor', zone: 'tailoring' },
  ats_optimizer:  { tier: 3, x: 150,  y: 250, name: 'ATS Optimizer', role: 'Keyword Density', zone: 'tailoring' },

  // Tier 4: Submission Bay (Y=345, R->L)
  websurfer:      { tier: 4, x: 0,    y: 345, name: 'Cyber-Pilot', role: 'FastPath Submitter', zone: 'submission' },

  // Tier 5: Command HQ & Lifecycle (Y=440, L->R)
  commander_apex: { tier: 5, x: -120, y: 440, name: 'Commander Apex', role: 'Fleet Orchestrator', zone: 'lifecycle' },
  outreach:       { tier: 5, x: 120,  y: 440, name: 'Outreach Diplomat', role: 'Recruiter InMail', zone: 'lifecycle' },
};

export function normalizeAgentKey(rawKey) {
  if (!rawKey) return null;
  const k = String(rawKey).toLowerCase().replace(/[-]/g, '_').trim();
  if (k.includes('falcon')) return 'scout_falcon';
  if (k.includes('atlas')) return 'scout_atlas';
  if (k.includes('titan')) return 'scout_titan';
  if (k.includes('horizon')) return 'scout_horizon';
  if (k.includes('aegis')) return 'scout_aegis';
  if (k.includes('eval') || k.includes('judge') || k.includes('minerva')) return 'evaluator';
  if (k.includes('fact') || k.includes('sentinel')) return 'factguard';
  if (k.includes('scribe') || k.includes('tailor')) return 'scribe';
  if (k.includes('ats')) return 'ats_optimizer';
  if (k.includes('surf') || k.includes('pilot') || k.includes('submit')) return 'websurfer';
  if (k.includes('outreach') || k.includes('diplomat')) return 'outreach';
  if (k.includes('apex') || k.includes('command') || k.includes('boss')) return 'commander_apex';
  return k;
}

export class EntityManager {
  constructor(app, state, renderer = null) {
    this.app = app;
    this.state = state;
    this.renderer = renderer;

    this.entityContainer = new PIXI.Container();
    if (renderer?.lodLayers) {
      renderer.lodLayers['standard'].addChild(this.entityContainer);
      renderer.lodLayers['full'].addChild(this.entityContainer);
    } else {
      app.stage.addChild(this.entityContainer);
    }

    /** @type {Map<string, {container:PIXI.Container, character:AgentCharacter, worldX:number, worldY:number, data:Object}>} */
    this.agents = new Map();
    /** @type {Map<string, {container:PIXI.Container, token:JobToken, gfx:PIXI.Graphics, worldX:number, worldY:number, data:Object}>} */
    this.jobs = new Map();

    // Initialize all canonical stations with real character bodies
    for (const key of Object.keys(AGENT_PLATFORM_STATIONS)) {
      this._ensureAgent(key);
    }

    // React to state changes
    this._unsubs = [];
    this._unsubs.push(state.subscribe('state_sync', () => this._reconcile()));
    this._unsubs.push(state.subscribe('agent_update', ({ agentId }) => this._ensureAgent(agentId)));
  }

  setRenderer(renderer) {
    if (this.renderer === renderer) return;
    this.entityContainer.parent?.removeChild?.(this.entityContainer);
    this.renderer = renderer;
    if (renderer?.lodLayers) {
      renderer.lodLayers['standard'].addChild(this.entityContainer);
      renderer.lodLayers['full'].addChild(this.entityContainer);
    } else {
      this.app.stage.addChild(this.entityContainer);
    }
  }

  // ---------- Reconciliation ----------

  _reconcile() {
    const agentStates = this.state.agentStates ?? new Map();
    for (const [rawId, s] of agentStates.entries()) {
      const canonKey = normalizeAgentKey(rawId);
      if (canonKey) this._ensureAgent(canonKey, s);
    }

    const jq = this.state.jobQueue ?? { discovered: [], evaluation: [], tailored: [], applied: [] };
    const allJobs = [
      ...(jq.discovered || []).map((j) => ({ ...j, stage: 'discovery', tierIdx: 0 })),
      ...(jq.evaluation || []).map((j) => ({ ...j, stage: 'evaluation', tierIdx: 1 })),
      ...(jq.tailored || []).map((j) => ({ ...j, stage: 'tailoring', tierIdx: 2 })),
      ...(jq.applied || []).map((j) => ({ ...j, stage: 'submission', tierIdx: 3 })),
    ];

    for (let i = 0; i < allJobs.length; i++) {
      this._ensureJob(allJobs[i], i);
    }

    const validJobIds = new Set(allJobs.map((j) => j.id));
    for (const id of [...this.jobs.keys()]) {
      if (!validJobIds.has(id)) this._removeJob(id);
    }
  }

  // ---------- Agent rendering with Animated Character Bodies ----------

  _ensureAgent(rawId, customState = null) {
    const canonKey = normalizeAgentKey(rawId);
    if (!canonKey) return;

    const station = AGENT_PLATFORM_STATIONS[canonKey];
    if (!station) return;

    const s = customState || this.state.getAgentState(rawId) || this.state.getAgentState(canonKey) || {};
    const status = s.status || 'sleeping';

    if (this.agents.has(canonKey)) {
      const rec = this.agents.get(canonKey);
      rec.character.setStatus(status);
      rec.data = { ...station, ...s, id: canonKey, status };
      return;
    }

    const container = new PIXI.Container();
    container.x = station.x;
    container.y = station.y;

    const character = new AgentCharacter(canonKey);
    character.setStatus(status);
    container.addChild(character.root);

    // Agent Name Badge under platform
    const shortName = station.name.replace('Scout ', '').split(' ')[0];
    const nameTxt = new PIXI.Text(shortName, {
      fontFamily: 'JetBrains Mono, monospace',
      fontSize: 8,
      fontWeight: 'bold',
      fill: '#cbd5e1',
      align: 'center',
    });
    nameTxt.anchor.set(0.5, 0);
    nameTxt.x = 0;
    nameTxt.y = 8;
    container.addChild(nameTxt);

    this.entityContainer.addChild(container);
    this.agents.set(canonKey, {
      container,
      character,
      nameTxt,
      worldX: station.x,
      worldY: station.y,
      data: { ...station, ...s, id: canonKey, status },
    });
  }

  _removeAgent(agentId) {
    const canonKey = normalizeAgentKey(agentId);
    const rec = this.agents.get(canonKey);
    if (!rec) return;
    rec.container.destroy?.({ children: true });
    this.agents.delete(canonKey);
  }

  // ---------- Job Rendering ----------

  _ensureJob(job, index = 0) {
    const jobId = job.id;
    if (!jobId) return;

    if (this.jobs.has(jobId)) {
      const rec = this.jobs.get(jobId);
      rec.token.setJob(job);
      rec.data = { ...rec.data, ...job };
      return;
    }

    const tierIdx = Math.min(job.tierIdx ?? 0, 4);
    const tier = TIERS[tierIdx];

    // Place job tokens along the conveyor lane
    const isLTR = tier.dir === 1;
    const startX = isLTR ? TRACK_BOUNDS.minX + 30 : TRACK_BOUNDS.maxX - 30;
    const slotX = startX + (tier.dir * (((index % 5) * 55) + 20));
    const slotY = tier.y - 10;

    const container = new PIXI.Container();
    container.x = slotX;
    container.y = slotY;

    const gfx = this._drawJobToken(job);
    container.addChild(gfx);

    const token = new JobToken();
    token.setJob(job);

    this.entityContainer.addChild(container);
    this.jobs.set(jobId, {
      container,
      token,
      gfx,
      worldX: slotX,
      worldY: slotY,
      data: { ...job, id: jobId },
    });
  }

  _drawJobToken(job) {
    const g = new PIXI.Graphics();
    const score = job.fit_score || job.score || 0;
    const isHigh = score >= 75;
    const color = isHigh ? 0x10b981 : 0x38bdf8;

    // 2D Cartridge Disc
    g.lineStyle(1.5, color, 0.95);
    g.beginFill(0x07090e, 0.95);
    g.drawRoundedRect(-9, -5, 18, 10, 2.5);
    g.endFill();

    // Data Core
    g.beginFill(color, 0.9);
    g.drawRect(-6, -3, 12, 2.5);
    g.endFill();

    return g;
  }

  _removeJob(jobId) {
    const rec = this.jobs.get(jobId);
    if (!rec) return;
    rec.container.destroy?.({ children: true });
    this.jobs.delete(jobId);
  }

  update(deltaTime) {
    // Animate character bodies (idle breathing, typing arms, cape wave, laser eyes)
    for (const rec of this.agents.values()) {
      rec.character.update(deltaTime);
    }
    for (const [id, rec] of this.jobs.entries()) {
      rec.token.update(deltaTime);
      if (rec.token.isComplete?.()) this._removeJob(id);
    }
  }

  getHitTargets() {
    const out = [];
    for (const [id, rec] of this.agents) {
      out.push({
        id,
        kind: 'agent',
        data: rec.data || { id, name: id },
        worldX: rec.worldX - 20,
        worldY: rec.worldY - 34,
        width: 40,
        height: 46,
      });
    }
    for (const [id, rec] of this.jobs) {
      out.push({
        id,
        kind: 'job',
        data: rec.data || { id, company: 'Job' },
        worldX: rec.worldX - 10,
        worldY: rec.worldY - 6,
        width: 20,
        height: 12,
      });
    }
    return out;
  }
}
