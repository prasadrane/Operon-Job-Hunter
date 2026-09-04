import { LODSystem } from './lod-system.js';

export const TIERS = [
  { id: 'discovery',  stage: 1, name: '1. DISCOVERY WING',     y: 60,  dir: 1,  color: 0x0284c7, neon: '#38bdf8', bg: 0x082f49 },
  { id: 'evaluation', stage: 2, name: '2. EVALUATION LAB',     y: 155, dir: -1, color: 0xd97706, neon: '#fbbf24', bg: 0x451a03 },
  { id: 'tailoring',  stage: 3, name: '3. TAILORING WORKSHOP', y: 250, dir: 1,  color: 0x7c3aed, neon: '#c084fc', bg: 0x2e1065 },
  { id: 'submission', stage: 4, name: '4. SUBMISSION BAY',     y: 345, dir: -1, color: 0x059669, neon: '#34d399', bg: 0x064e3b },
  { id: 'lifecycle',  stage: 5, name: '5. COMMAND & LIFECYCLE',y: 440, dir: 1,  color: 0xdb2777, neon: '#f472b6', bg: 0x500724 },
];

export const TRACK_BOUNDS = {
  minX: -400,
  maxX: 400,
  pipeRightX: 430,
  pipeLeftX: -430,
};

export class FactoryRenderer {
  constructor(app) {
    this.app = app;
    this.lod = new LODSystem();
    this.cameraZoom = 1.0;
    this.animTime = 0;

    // Camera container wraps all world-space content (pan/zoom applied here)
    this.cameraContainer = new PIXI.Container();
    this.app.stage.addChild(this.cameraContainer);

    // LOD layers
    this.lodLayers = {
      'top-down':   new PIXI.Container(),
      'simplified': new PIXI.Container(),
      'standard':   new PIXI.Container(),
      'full':       new PIXI.Container(),
    };
    for (const c of Object.values(this.lodLayers)) this.cameraContainer.addChild(c);

    // 2D Platformer Track Container
    this.trackContainer = new PIXI.Container();
    this.lodLayers['standard'].addChild(this.trackContainer);
    this.lodLayers['full'].addChild(this.trackContainer);

    // Animated Treads Graphic
    this.treadsGfx = new PIXI.Graphics();
    this.trackContainer.addChild(this.treadsGfx);

    // Static Track Architecture
    this.staticGfx = new PIXI.Graphics();
    this.trackContainer.addChild(this.staticGfx);

    // Labels Container
    this.labelsContainer = new PIXI.Container();
    this.lodLayers['standard'].addChild(this.labelsContainer);
    this.lodLayers['full'].addChild(this.labelsContainer);

    this.drawStaticTracks();
    this.drawStageBadges();

    this._camera = null;
    this._onLodChange = null;
    this._onChange = null;
  }

  setCamera(camera) {
    if (this._camera) {
      this._camera.off('lod-change', this._onLodChange);
      this._camera.off('change', this._onChange);
    }
    this._camera = camera;
    this._onLodChange = (e) => this._applyLod(e.level);
    this._onChange = () => this._applyCamera();
    this._camera.on('lod-change', this._onLodChange);
    this._camera.on('change', this._onChange);
    this._applyCamera();
  }

  drawStaticTracks() {
    const g = this.staticGfx;
    g.clear();

    const { minX, maxX, pipeRightX, pipeLeftX } = TRACK_BOUNDS;
    const trackW = maxX - minX;

    // 1. Background Structural Scaffolding Beams
    g.lineStyle(1, 0x1e293b, 0.35);
    for (let x = minX + 50; x <= maxX - 50; x += 150) {
      g.moveTo(x, 30);
      g.lineTo(x, 480);
    }

    // 2. Draw 5 Horizontal Conveyor Platforms
    for (let i = 0; i < TIERS.length; i++) {
      const tier = TIERS[i];
      const y = tier.y;

      // Heavy Industrial Understructure Girder
      g.lineStyle(2, 0x0f172a, 1.0);
      g.beginFill(0x0a0f1d, 0.95);
      g.drawRoundedRect(minX - 10, y + 5, trackW + 20, 14, 4);
      g.endFill();

      // Girder Rivet Details
      g.lineStyle(1, 0x334155, 0.5);
      for (let rx = minX; rx <= maxX; rx += 35) {
        g.drawCircle(rx, y + 12, 1.5);
      }

      // Conveyor Bed Surface
      g.lineStyle(1, tier.color, 0.7);
      g.beginFill(tier.bg, 0.85);
      g.drawRect(minX, y - 5, trackW, 10);
      g.endFill();

      // Top & Bottom Railings
      g.lineStyle(1.5, 0x475569, 0.85);
      g.moveTo(minX, y - 5);
      g.lineTo(maxX, y - 5);
      g.moveTo(minX, y + 5);
      g.lineTo(maxX, y + 5);

      // Intake chute at Top Left (Tier 1)
      if (i === 0) {
        g.lineStyle(2, 0x0284c7, 0.95);
        g.beginFill(0x0369a1, 0.85);
        g.drawRoundedRect(minX - 28, y - 20, 28, 26, 4);
        g.endFill();
      }
    }

    // 3. Draw 4 Serpentine U-Turn Transport Tubes
    // Tube 1: Tier 1 Right -> Tier 2 Right (Down)
    this._drawPipe(g, maxX, TIERS[0].y, pipeRightX, TIERS[1].y, maxX, 0x0284c7, 0xd97706);

    // Tube 2: Tier 2 Left -> Tier 3 Left (Down)
    this._drawPipe(g, minX, TIERS[1].y, pipeLeftX, TIERS[2].y, minX, 0xd97706, 0x7c3aed);

    // Tube 3: Tier 3 Right -> Tier 4 Right (Down)
    this._drawPipe(g, maxX, TIERS[2].y, pipeRightX, TIERS[3].y, maxX, 0x7c3aed, 0x059669);

    // Tube 4: Tier 4 Left -> Tier 5 Left (Down)
    this._drawPipe(g, minX, TIERS[3].y, pipeLeftX, TIERS[4].y, minX, 0x059669, 0xdb2777);
  }

  _drawPipe(g, x1, y1, bendX, y2, x2, color1, color2) {
    // Outer shadow pipe
    g.lineStyle(12, 0x07090e, 0.95);
    g.moveTo(x1, y1);
    g.bezierCurveTo(bendX, y1, bendX, y2, x2, y2);

    // Neon Glass Transport Tube
    g.lineStyle(7, color1, 0.8);
    g.moveTo(x1, y1);
    g.bezierCurveTo(bendX, y1, bendX, y2, x2, y2);

    // Inner Light Core
    g.lineStyle(2.5, 0xffffff, 0.9);
    g.moveTo(x1, y1);
    g.bezierCurveTo(bendX, y1, bendX, y2, x2, y2);
  }

  drawStageBadges() {
    this.labelsContainer.removeChildren();

    for (const tier of TIERS) {
      const isLTR = tier.dir === 1;
      const badgeX = isLTR ? TRACK_BOUNDS.minX + 75 : TRACK_BOUNDS.maxX - 75;

      const g = new PIXI.Graphics();
      g.lineStyle(1, tier.color, 0.8);
      g.beginFill(0x07090e, 0.92);
      g.drawRoundedRect(-65, -8, 130, 16, 4);
      g.endFill();
      g.x = badgeX;
      g.y = tier.y - 18;

      const txt = new PIXI.Text(tier.name, {
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 8,
        fontWeight: 'bold',
        fill: tier.neon,
        align: 'center',
      });
      txt.anchor.set(0.5);
      g.addChild(txt);

      // Flow direction arrow
      const arrowTxt = new PIXI.Text(isLTR ? '▶▶' : '◀◀', {
        fontFamily: 'monospace',
        fontSize: 6.5,
        fontWeight: 'bold',
        fill: tier.neon,
      });
      arrowTxt.anchor.set(0.5);
      arrowTxt.x = isLTR ? 52 : -52;
      arrowTxt.y = 0;
      g.addChild(arrowTxt);

      this.labelsContainer.addChild(g);
    }
  }

  drawAnimatedTreads(timeMs) {
    const g = this.treadsGfx;
    g.clear();

    const { minX, maxX } = TRACK_BOUNDS;
    const speed = 0.04;

    for (let i = 0; i < TIERS.length; i++) {
      const tier = TIERS[i];
      const y = tier.y;
      const dir = tier.dir;
      const offset = ((timeMs * speed * dir) % 18 + 18) % 18;

      g.lineStyle(1.2, 0x64748b, 0.65);
      for (let x = minX + offset; x < maxX; x += 18) {
        g.moveTo(x, y - 3);
        g.lineTo(x + (dir * 2.5), y + 3);
      }
    }
  }

  setZoom(zoom) {
    this.cameraZoom = Math.max(0.25, Math.min(2.0, zoom));
    this.cameraContainer.scale.set(this.cameraZoom);
    this.lod.setZoom(this.cameraZoom);
  }

  update(deltaTime) {
    this.animTime += deltaTime;
    this.drawAnimatedTreads(this.animTime);
    this.lod.update(deltaTime);
  }

  getViewport() {
    return {
      x: -this.cameraContainer.x / this.cameraZoom,
      y: -this.cameraContainer.y / this.cameraZoom,
      width: this.app.screen.width / this.cameraZoom,
      height: this.app.screen.height / this.cameraZoom,
    };
  }

  shouldRenderEntity(entity) {
    return this.lod.shouldRender(entity, this.getViewport(), 48);
  }

  resize() {
    if (this._camera) {
      this._applyCamera();
    }
  }

  _applyCamera() {
    if (!this._camera) return;
    this._camera.applyTo(this.cameraContainer);
  }

  _applyLod(level) {
    for (const [name, layer] of Object.entries(this.lodLayers)) {
      layer.visible = (name === level);
    }
  }
}
