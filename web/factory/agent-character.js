/**
 * 2D Retro Arcade / Platformer Character Body Renderer (Mario & Contra Style)
 * Renders procedural 2D platformer character bodies with animated limbs, heads, outfits, and gear.
 */

export const CHARACTER_DESIGNS = {
  scout_falcon: {
    skin: 0xfed7aa,
    hair: 0x1e293b,
    suit: 0x0284c7, // Sky Blue
    accent: 0xfacc15, // Yellow
    headgear: 'visor',
    visorColor: 0x38bdf8,
    cape: false,
    name: 'Falcon',
  },
  scout_atlas: {
    skin: 0xfde047,
    hair: 0x78350f,
    suit: 0xd97706, // Orange
    accent: 0xfef08a,
    headgear: 'hardhat',
    visorColor: 0xffedd5,
    cape: false,
    name: 'Atlas',
  },
  scout_titan: {
    skin: 0xfcd34d,
    hair: 0x0f172a,
    suit: 0x2563eb, // Royal Blue
    accent: 0x60a5fa,
    headgear: 'goggles',
    visorColor: 0x93c5fd,
    cape: false,
    name: 'Titan',
  },
  scout_horizon: {
    skin: 0xfbcfe8,
    hair: 0x475569,
    suit: 0x0891b2, // Cyan
    accent: 0x67e8f9,
    headgear: 'headset',
    visorColor: 0x22d3ee,
    cape: false,
    name: 'Horizon',
  },
  scout_aegis: {
    skin: 0xe2e8f0,
    hair: 0x334155,
    suit: 0x475569, // Steel Armor
    accent: 0x38bdf8,
    headgear: 'helmet',
    visorColor: 0x67e8f9,
    cape: false,
    name: 'Aegis',
  },
  evaluator: {
    skin: 0xfef08a,
    hair: 0xffffff, // White Judge Wig
    suit: 0xb45309, // Gold/Bronze Robes
    accent: 0xfef08a,
    headgear: 'judge_wig',
    visorColor: 0xfbbf24,
    cape: true,
    capeColor: 0x78350f,
    name: 'Minerva',
  },
  factguard: {
    skin: 0x94a3b8,
    hair: 0x0f172a,
    suit: 0x334155, // Sentry Droid
    accent: 0xef4444, // Red Sensor
    headgear: 'droid_dome',
    visorColor: 0xef4444,
    cape: false,
    name: 'FactGuard',
  },
  scribe: {
    skin: 0xfde68a,
    hair: 0x581c87,
    suit: 0x7c3aed, // Purple Robe
    accent: 0xd8b4fe,
    headgear: 'hood',
    visorColor: 0xc084fc,
    cape: true,
    capeColor: 0x4c1d95,
    name: 'Scribe',
  },
  ats_optimizer: {
    skin: 0xfef08a,
    hair: 0x1e293b,
    suit: 0x6d28d9, // Deep Violet
    accent: 0xa7f3d0, // Emerald target
    headgear: 'monocle',
    visorColor: 0x34d399,
    cape: false,
    name: 'ATS',
  },
  websurfer: {
    skin: 0xfcd34d,
    hair: 0xb91c1c, // Contra Red Bandana
    suit: 0x047857, // Commando Green
    accent: 0xef4444, // Red Warpaint/Bandana
    headgear: 'bandana',
    visorColor: 0x000000, // Sunglasses
    cape: false,
    name: 'Cyber-Pilot',
  },
  commander_apex: {
    skin: 0xfde047,
    hair: 0xd97706, // Golden Crown
    suit: 0xbe185d, // Royal Crimson
    accent: 0xfacc15, // Pure Gold
    headgear: 'crown',
    visorColor: 0xfde047,
    cape: true,
    capeColor: 0x831843,
    name: 'Apex',
  },
  outreach: {
    skin: 0xfde68a,
    hair: 0x0f172a,
    suit: 0x1e1b4b, // Diplomatic Suit
    accent: 0xf472b6, // Pink tie
    headgear: 'slick',
    visorColor: 0x38bdf8,
    cape: false,
    name: 'Outreach',
  },
};

export class AgentCharacter {
  constructor(agentId, designKey = null) {
    this.agentId = agentId;
    this.design = CHARACTER_DESIGNS[designKey || agentId] || CHARACTER_DESIGNS.scout_falcon;
    this.status = 'sleeping';
    this.animTime = Math.random() * 1000;

    this.root = new PIXI.Container();

    // Layers
    this.capeLayer = new PIXI.Graphics();
    this.bodyLayer = new PIXI.Graphics();
    this.headLayer = new PIXI.Graphics();
    this.limbsLayer = new PIXI.Graphics();
    this.consoleLayer = new PIXI.Graphics();
    this.effectsLayer = new PIXI.Graphics();

    this.root.addChild(this.capeLayer);
    this.root.addChild(this.bodyLayer);
    this.root.addChild(this.headLayer);
    this.root.addChild(this.limbsLayer);
    this.root.addChild(this.consoleLayer);
    this.root.addChild(this.effectsLayer);

    this.drawConsole();
    this.update(0);
  }

  setStatus(status) {
    this.status = status;
  }

  update(deltaTime) {
    this.animTime += deltaTime;
    const t = this.animTime;

    const isActive = this.status === 'active' || this.status === 'running';
    const isBusy = this.status === 'busy';
    const isError = this.status === 'error';

    // Animation speeds & offsets
    const bobSpeed = isActive ? 0.008 : isBusy ? 0.012 : 0.004;
    const bobY = Math.sin(t * bobSpeed) * (isActive ? 2 : 1);
    const typeCycle = (Math.sin(t * (isBusy ? 0.025 : 0.015)) > 0);

    const d = this.design;
    const charX = -8; // Character stands just behind the desk
    const charY = -8 + bobY;

    // 1. Cape (if character has one)
    this.capeLayer.clear();
    if (d.cape) {
      const capeWave = Math.sin(t * 0.006) * 3;
      this.capeLayer.beginFill(d.capeColor || 0x831843, 0.95);
      this.capeLayer.moveTo(charX - 5, charY - 14);
      this.capeLayer.lineTo(charX - 12 + capeWave, charY + 2);
      this.capeLayer.lineTo(charX + 3 + capeWave, charY + 2);
      this.capeLayer.lineTo(charX + 5, charY - 14);
      this.capeLayer.closePath();
      this.capeLayer.endFill();
    }

    // 2. Torso / Body (Tactical Jacket/Suit)
    this.bodyLayer.clear();
    // Legs & Boots
    this.bodyLayer.beginFill(0x0f172a, 1.0); // Dark Pants
    this.bodyLayer.drawRect(charX - 5, charY - 4, 4, 8); // Left Leg
    this.bodyLayer.drawRect(charX + 1, charY - 4, 4, 8); // Right Leg
    this.bodyLayer.beginFill(0x020617, 1.0); // Boots
    this.bodyLayer.drawRect(charX - 6, charY + 2, 5, 3);
    this.bodyLayer.drawRect(charX + 1, charY + 2, 5, 3);
    this.bodyLayer.endFill();

    // Torso Jacket
    this.bodyLayer.beginFill(d.suit, 1.0);
    this.bodyLayer.drawRoundedRect(charX - 6, charY - 15, 12, 12, 2);
    this.bodyLayer.endFill();

    // Belt & Accent Harness
    this.bodyLayer.beginFill(d.accent, 0.9);
    this.bodyLayer.drawRect(charX - 6, charY - 5, 12, 2); // Belt
    this.bodyLayer.drawRect(charX - 1, charY - 15, 2, 10); // Tie / Zipper
    this.bodyLayer.endFill();

    // 3. Head & Face
    this.headLayer.clear();
    const headY = charY - 24;

    // Face Skin
    this.headLayer.beginFill(d.skin, 1.0);
    this.headLayer.drawRoundedRect(charX - 5, headY, 10, 9, 2);
    this.headLayer.endFill();

    // Eyes / Visor
    if (d.headgear === 'visor') {
      // Cyber Visor
      this.headLayer.beginFill(d.visorColor, 0.95);
      this.headLayer.drawRect(charX - 5, headY + 2, 10, 3);
      this.headLayer.endFill();
    } else if (d.headgear === 'bandana') {
      // Contra Red Bandana
      this.headLayer.beginFill(0xef4444, 1.0);
      this.headLayer.drawRect(charX - 6, headY - 1, 12, 3);
      this.headLayer.drawRect(charX - 8, headY + 1, 3, 5); // Bandana tails
      this.headLayer.endFill();
      // Sunglasses
      this.headLayer.beginFill(0x000000, 1.0);
      this.headLayer.drawRect(charX - 4, headY + 2, 8, 3);
      this.headLayer.endFill();
    } else if (d.headgear === 'crown') {
      // Apex Gold Crown
      this.headLayer.beginFill(0xfacc15, 1.0);
      this.headLayer.moveTo(charX - 6, headY);
      this.headLayer.lineTo(charX - 6, headY - 5);
      this.headLayer.lineTo(charX - 3, headY - 2);
      this.headLayer.lineTo(charX, headY - 6);
      this.headLayer.lineTo(charX + 3, headY - 2);
      this.headLayer.lineTo(charX + 6, headY - 5);
      this.headLayer.lineTo(charX + 6, headY);
      this.headLayer.closePath();
      this.headLayer.endFill();
      // Crown Ruby Gem
      this.headLayer.beginFill(0xef4444, 1.0);
      this.headLayer.drawCircle(charX, headY - 2, 1.5);
      this.headLayer.endFill();
      // Eyes
      this.headLayer.beginFill(0x0f172a, 1.0);
      this.headLayer.drawCircle(charX - 2, headY + 3.5, 1);
      this.headLayer.drawCircle(charX + 2, headY + 3.5, 1);
      this.headLayer.endFill();
    } else if (d.headgear === 'judge_wig') {
      // Minerva White Wig
      this.headLayer.beginFill(0xffffff, 1.0);
      this.headLayer.drawRoundedRect(charX - 7, headY - 3, 14, 6, 3);
      this.headLayer.drawRect(charX - 7, headY + 2, 3, 7);
      this.headLayer.drawRect(charX + 4, headY + 2, 3, 7);
      this.headLayer.endFill();
      // Eyes
      this.headLayer.beginFill(0x0f172a, 1.0);
      this.headLayer.drawCircle(charX - 2, headY + 3.5, 1);
      this.headLayer.drawCircle(charX + 2, headY + 3.5, 1);
      this.headLayer.endFill();
    } else if (d.headgear === 'hardhat') {
      // Atlas Yellow Hardhat
      this.headLayer.beginFill(0xfacc15, 1.0);
      this.headLayer.drawRoundedRect(charX - 6, headY - 4, 12, 6, 2);
      this.headLayer.drawRect(charX - 8, headY + 1, 16, 2);
      this.headLayer.endFill();
      // Eyes
      this.headLayer.beginFill(0x0f172a, 1.0);
      this.headLayer.drawCircle(charX - 2, headY + 4, 1);
      this.headLayer.drawCircle(charX + 2, headY + 4, 1);
      this.headLayer.endFill();
    } else if (d.headgear === 'droid_dome') {
      // FactGuard Sentry Droid Dome
      this.headLayer.beginFill(0x334155, 1.0);
      this.headLayer.drawRoundedRect(charX - 6, headY - 3, 12, 11, 4);
      this.headLayer.endFill();
      // Red Scanning Eye (Pulsing)
      const eyeX = charX + Math.sin(t * 0.01) * 3;
      this.headLayer.beginFill(0xef4444, 1.0);
      this.headLayer.drawCircle(eyeX, headY + 3, 2);
      this.headLayer.endFill();
    } else {
      // Default Cyber Headset / Hair
      this.headLayer.beginFill(d.hair || 0x0f172a, 1.0);
      this.headLayer.drawRoundedRect(charX - 6, headY - 2, 12, 5, 2);
      this.headLayer.endFill();
      // Eyes
      this.headLayer.beginFill(0x0f172a, 1.0);
      this.headLayer.drawCircle(charX - 2, headY + 3.5, 1);
      this.headLayer.drawCircle(charX + 2, headY + 3.5, 1);
      this.headLayer.endFill();
    }

    // 4. Limbs / Arms (Animated typing on keyboard or pulling console levers)
    this.limbsLayer.clear();
    const deskEdgeX = 2;
    const deskEdgeY = charY - 9;

    this.limbsLayer.lineStyle(2.5, d.suit, 1.0);
    if (isActive || isBusy) {
      // Left Arm (typing)
      this.limbsLayer.moveTo(charX - 5, charY - 12);
      this.limbsLayer.lineTo(charX - 1, deskEdgeY + (typeCycle ? -2 : 1));
      this.limbsLayer.lineTo(deskEdgeX + 2, deskEdgeY + (typeCycle ? 1 : -2));

      // Right Arm (typing)
      this.limbsLayer.moveTo(charX + 5, charY - 12);
      this.limbsLayer.lineTo(charX + 2, deskEdgeY + (typeCycle ? 1 : -2));
      this.limbsLayer.lineTo(deskEdgeX + 5, deskEdgeY + (typeCycle ? -2 : 1));
    } else if (isError) {
      // Distressed arms on head
      this.limbsLayer.moveTo(charX - 5, charY - 12);
      this.limbsLayer.lineTo(charX - 8, headY + 2);
      this.limbsLayer.moveTo(charX + 5, charY - 12);
      this.limbsLayer.lineTo(charX + 8, headY + 2);
    } else {
      // Idle arms resting on console
      this.limbsLayer.moveTo(charX - 5, charY - 12);
      this.limbsLayer.lineTo(charX - 2, deskEdgeY);
      this.limbsLayer.lineTo(deskEdgeX + 2, deskEdgeY);
      this.limbsLayer.moveTo(charX + 5, charY - 12);
      this.limbsLayer.lineTo(charX + 2, deskEdgeY);
      this.limbsLayer.lineTo(deskEdgeX + 4, deskEdgeY);
    }

    // 5. Effects / Dynamic Status Light
    this.effectsLayer.clear();
    const statusColor = isError ? 0xef4444
                      : isBusy ? 0xf59e0b
                      : isActive ? 0x10b981
                      : 0x64748b;

    // Glowing Halo / Status Orb above head
    this.effectsLayer.beginFill(statusColor, isActive ? 0.95 : 0.6);
    this.effectsLayer.drawCircle(charX, headY - 10, 3.5);
    this.effectsLayer.endFill();

    if (isActive) {
      this.effectsLayer.lineStyle(1, statusColor, 0.4 + Math.sin(t * 0.01) * 0.3);
      this.effectsLayer.drawCircle(charX, headY - 10, 7);
    }
  }

  drawConsole() {
    const g = this.consoleLayer;
    g.clear();

    const deskX = 6;
    const deskY = -12;

    // 1. Arcade Terminal Stand & Desk
    g.lineStyle(1.5, 0x1e293b, 1.0);
    g.beginFill(0x090d16, 0.95);
    g.drawRoundedRect(deskX - 4, deskY + 6, 20, 10, 2); // Base
    g.drawRoundedRect(deskX - 6, deskY - 12, 24, 18, 3); // Main Console Housing
    g.endFill();

    // 2. CRT / Holographic Display Screen
    g.lineStyle(1, 0x0284c7, 0.8);
    g.beginFill(0x020617, 1.0);
    g.drawRect(deskX - 3, deskY - 9, 18, 12);
    g.endFill();

    // Screen scanlines / waveforms
    g.lineStyle(1, 0x38bdf8, 0.9);
    g.moveTo(deskX - 1, deskY - 3);
    g.lineTo(deskX + 3, deskY - 6);
    g.lineTo(deskX + 7, deskY - 1);
    g.lineTo(deskX + 11, deskY - 4);
    g.lineTo(deskX + 13, deskY - 3);

    // 3. Arcade Control Buttons & Joystick
    g.beginFill(0x10b981, 1.0);
    g.drawCircle(deskX + 2, deskY + 3, 1.5);
    g.beginFill(0xef4444, 1.0);
    g.drawCircle(deskX + 7, deskY + 3, 1.5);
    g.beginFill(0xf59e0b, 1.0);
    g.drawCircle(deskX + 12, deskY + 3, 1.5);
    g.endFill();
  }
}
