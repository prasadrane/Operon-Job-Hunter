/**
 * CareerGraph AI — 3D Virtual Office Engine (Modular Wire Layer)
 *
 * Thin conductor: wires all subsystem modules together into a single
 * VirtualOffice3D class. No Three.js logic lives here — all rendering,
 * animation, particle, UI, and data-sync code is delegated to sibling
 * modules under web/office3d/*.
 *
 * HTML consumers load each .js file via <script> tags in dependency order:
 *   <script src="config/agents.js"></script>     ← AGENT_CONFIGS global
 *   <script src="config/scenes.js"></script>     ← SCENES + CAMERA_KEYS globals
 *   <script src="system/renderer.js"></script>
 *   <script src="system/lighting.js"></script>
 *   <script src="system/postprocess.js"></script>
 *   <script src="world/floor.js"></script>
 *   <script src="world/buildings.js"></script>
 *   <script src="world/chambers.js"></script>
 *   <script src="entities/character.js"></script>
 *   <script src="entities/animations.js"></script>
 *   <script src="entities/orbs.js"></script>
 *   <script src="effects/particles.js"></script>
 *   <script src="effects/energy.js"></script>
 *   <script src="ui/billboards.js"></script>
 *   <script src="ui/contextmenu.js"></script>
 *   <script src="data/sync.js"></script>
 *   <script src="index.js"></script>             ← exports VirtualOffice3D globally
 */

// ─── Global references used by individual modules ──────────────────
window._sceneRef = null;       // Three.js Scene for add/remove helpers
window._sparkPool = [];        // Shared footstep spark particle pool
window._zzzData = [];          // Sleeping agent data for Zzz sprite creation
window._ctxDispatch = null;    // Context-menu action callback set from app.js

class VirtualOffice3D {
  constructor(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    this.container = container;
    this.clock = new THREE.Clock();

    // Visual preference flags (toggled by user buttons)
    this.highContrast = false;
    this.reducedMotion = false;
    this.minimapVisible = false;
    this.autoRotate = false;
    this.isStandupActive = false;

    // Camera state
    this.currentCameraView = 'isometric';
    this.hoveredAgent = null;
    this.selectedAgent = null;

    // Performance tracking
    this.frameCount = 0;
    this.lastFpsTime = 0;
    this.fps = 60;
    this.tabVisible = true;
    this.needsResize = true;

    // ─── Initialize system layer ────────────────────────
    const renderer = createRenderer(containerId);
    window.renderer = renderer;
    this.renderer = renderer;
    this.camera = createCamera(renderer);
    this.controls = setupControls(this.camera, renderer);

    // Create scene AFTER renderer so post-processing can reference it
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x07090e);
    this.scene.fog = new THREE.FogExp2(0x07090e, 0.012);

    // Set _sceneRef before any build call needs it
    window._sceneRef = this.scene;

    // Post-processing (needs scene + camera)
    const w = container.clientWidth || 1000;
    const h = container.clientHeight || 580;
    const { composer, bloomPass } = setupPostProcessing(this.scene, renderer, this.camera, w, h);
    this.composer = composer;
    this.bloomPass = bloomPass;

    // Lighting
    this.lights = createLighting(this.scene, { AGENT_CONFIGS });

    // World building
    this.floorObjects = buildFloor(this.scene);
    this.buildingObjects = buildWorld(this.scene);
    this.chambers = buildChambers(this.scene);

    // Entities — instantiate characters per agent config
    this.agents = {};
    this.workstations = {};

    for (const [key, cfg] of Object.entries(AGENT_CONFIGS)) {
      const char = ProceduralCharacterFactory.create(cfg);

      // Initial position: boss stays at desk, others at chair position
      const startPos = cfg.isBoss ? cfg.deskPos : cfg.chairPos;
      char.group.position.set(startPos.x, startPos.y, startPos.z);
      if (!cfg.isBoss && !char.group.rotation) {
        char.group.rotation.y = cfg.chairPos.z > cfg.deskPos.z ? 0 : Math.PI;
      }

      this.scene.add(char.group);

      this.agents[key] = {
        ...char,                                    // meshes refs from factory
        config: cfg,
        status: cfg.isBoss ? 'active' : 'sleeping',
        currentTask: cfg.isBoss ? 'Supervising team' : 'In Standby',
        speech: cfg.isBoss ? 'Team assembled!' : 'Zzz...',
        targetPos: new THREE.Vector3(startPos.x, startPos.y, startPos.z),
        breathPhase: Math.random() * Math.PI * 2,
        nextBlinkTime: Math.random() * 5 + 2,
        isBlinking: false,
        blinkTimer: 0,
        _torsoBaseY: 1.05,                          // base Y for breathing offset
      };

      // Track workstation monitors per agent (non-boss agents have desks)
      if (!cfg.isBoss) {
        this.workstations[key] = {
          group: null,                            // filled below
          monitors: [],
          config: cfg,
        };
      }
    }

    // Status orbs above each agent
    this.statusOrbs = createStatusOrbs(this.agents);

    // Particle systems
    this.particles = createParticles(this.scene);

    // Energy effects
    this.energyEffects = createEnergyEffects(this.scene);

    // UI overlays
    this.billboard = initBillboards();
    this.ctxMenu = createContextMenu(container);

    // Data sync bridge (standup state container)
    this._standupData = { _standupActive: false };

    // ─── Event listeners ────────────────────────────────
    window.addEventListener('resize', () => { this.needsResize = true; });
    document.addEventListener('visibilitychange', () => {
      this.tabVisible = !document.hidden;
      if (this.tabVisible) this.clock.getDelta();
    });

    // Raycaster for click/hover on canvases
    this.raycaster = new THREE.Raycaster();
    this.mouse = new THREE.Vector2();
    this.renderer.domElement.addEventListener('click', (e) => this.onCanvasClick(e));
    this.renderer.domElement.addEventListener('mousemove', (e) => this.onCanvasHover(e));
    this.renderer.domElement.addEventListener('contextmenu', (e) => { e.preventDefault(); this.showContextMenu(e); });
    this.renderer.domElement.addEventListener('dblclick', (e) => this.onDoubleClick(e));
    document.addEventListener('keydown', (e) => this.onKeyDown(e));
    document.addEventListener('click', () => hide());

    // ─── Start render loop ─────────────────────────────
    this.animate();
  }

  // ─── Interaction handlers ────────────────────────────

  updateAgentState(key, data) {
    updateAgentState(
      this.scene, key, data, this.agents, this.workstations, this.controls
    );
  }

  callStandup() {
    this._standupData._standupActive = true;
    for (const agent of Object.values(this.agents)) {
      agent.targetPos = new THREE.Vector3(agent.config.warRoomPos.x, 0, agent.config.warRoomPos.z);
    }
    this.focusCameraOn(0, 4, 0, 18);
  }

  endStandup() {
    this._standupData._standupActive = false;
    for (const [key, agent] of Object.entries(this.agents)) {
      this.updateAgentState(key, { status: agent.status });
    }
  }

  focusCameraOn(x, y, z, distance = 22) {
    if (!this.controls) return;
    const target = new THREE.Vector3(x, y, z);
    const offset = new THREE.Vector3(0, distance * 0.7, distance * 0.9);
    this.controls.target.copy(target);
    this.camera.position.copy(target).add(offset);

    // Update mode indicator label
    const labels = ['BOSS', 'DISCOVERY', 'INTELLIGENCE', 'WAR ROOM', 'LOUNGE'];
    const idx = ['1','2','3','4','5'].indexOf(String([x===0&&y<=4&&z===-16?1:0,x===-14?2:0,x===14?3:0,z===0&&x===0?4:0,z>=14?5:0].filter(v=>v)[0]-1));
    const el = document.getElementById('cam-mode-indicator-3d');
    if (el) el.textContent = this.currentCameraView.toUpperCase();
  }

  // Called by app.js when the tab becomes visible to ensure correct canvas size
  onResize() {
    if (!this.container || !this.renderer || !this.camera) return;
    const w = this.container.clientWidth || 1000;
    const h = this.container.clientHeight || 580;
    this.renderer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    if (this.composer) {
      this.composer.setSize(w, h);
    }
  }

  onCanvasClick(event) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    this.raycaster.setFromCamera(this.mouse, this.camera);
    const hits = this.raycaster.intersectObjects(this.scene.children, true);

    let hitAgent = null;
    if (hits.length > 0) {
      let obj = hits[0].object;
      while (obj.parent && obj.parent !== this.scene) {
        if (obj.name && obj.name.startsWith('agent_')) {
          hitAgent = obj.name.replace('agent_', '');
          break;
        }
        obj = obj.parent;
      }
    }

    if (hitAgent) this.onAgentSelected(hitAgent);
  }

  onCanvasHover(event) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    this.raycaster.setFromCamera(this.mouse, this.camera);
    const hits = this.raycaster.intersectObjects(this.scene.children, true);

    let foundAgent = null;
    if (hits.length > 0) {
      let obj = hits[0].object;
      while (obj.parent && obj.parent !== this.scene) {
        if (obj.name && obj.name.startsWith('agent_')) {
          foundAgent = obj.name.replace('agent_', '');
          break;
        }
        obj = obj.parent;
      }
    }

    if (foundAgent !== this.hoveredAgent) {
      const oldTip = document.getElementById('o3d-tooltip');
      if (oldTip) oldTip.remove();
      this.hoveredAgent = foundAgent;

      if (foundAgent && this.agents[foundAgent]) {
        const a = this.agents[foundAgent];
        showHoverTooltip(this.billboard, event.clientX, event.clientY, {
          name: a.config.name, color: a.config.color, role: a.config.role,
          statusText: a.status === 'active' ? '⚡ Working' : '💤 Standby'
        });
      }

      this.renderer.domElement.style.cursor = foundAgent ? 'pointer' : 'grab';
    }
  }

  onDoubleClick(event) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    this.raycaster.setFromCamera(this.mouse, this.camera);
    const hits = this.raycaster.intersectObjects(this.scene.children, true);

    let foundAgent = null;
    if (hits.length > 0) {
      let obj = hits[0].object;
      while (obj.parent && obj.parent !== this.scene) {
        if (obj.name && obj.name.startsWith('agent_')) {
          foundAgent = obj.name.replace('agent_', '');
          break;
        }
        obj = obj.parent;
      }
    }

    if (foundAgent && this.agents[foundAgent]) {
      this.selectedAgent = foundAgent;
      const a = this.agents[foundAgent];
      this.focusCameraOn(a.group.position.x, a.group.position.y + 1, a.group.position.z, 8);
    }
  }

  showContextMenu(event) {
    if (this.contextMenuClosed) return;

    const rect = this.renderer.domElement.getBoundingClientRect();
    this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    this.raycaster.setFromCamera(this.mouse, this.camera);
    const hits = this.raycaster.intersectObjects(this.scene.children, true);

    let hitAgent = null;
    if (hits.length > 0) {
      let obj = hits[0].object;
      while (obj.parent && obj.parent !== this.scene) {
        if (obj.name && obj.name.startsWith('agent_')) {
          hitAgent = obj.name.replace('agent_', '');
          break;
        }
        obj = obj.parent;
      }
    }

    if (hitAgent) {
      showContextMenu(this.ctxMenu, event.clientX, event.clientY, hitAgent, this.agents);
    }
  }

  onKeyDown(event) {
    const presets = {
      '1': [0, 3, -16, 12],
      '2': [-14, 2, 0, 22],
      '3': [14, 2, 0, 22],
      '4': [0, 2, 0, 16],
      '5': [0, 2, 16, 18],
    };

    if (presets[event.key]) {
      const args = presets[event.key];
      this.focusCameraOn(args[0], args[1], args[2], args[3]);
      this.currentCameraView = CAMERA_LABELS[['1','2','3','4','5'].indexOf(event.key)] || '';
      const el = document.getElementById('cam-mode-indicator-3d');
      if (el) el.textContent = this.currentCameraView.toUpperCase();
    }

    if (event.key === 'r' || event.key === 'R') {
      this.autoRotate = !this.autoRotate;
      if (this.controls) this.controls.autoRotate = this.autoRotate;
    }

    if (event.key === 'Escape') {
      this.selectedAgent = null;
      hide();
    }

    if (event.key === 'm' || event.key === 'M') {
      this.minimapVisible = !this.minimapVisible;
      const mc = document.getElementById('minimap-3d-container');
      if (mc) mc.classList.toggle('hidden', !this.minimapVisible);
    }
  }

  onAgentSelected(agentKey) {
    this.selectedAgent = agentKey;
    const a = this.agents[agentKey];
    if (a) {
      this.focusCameraOn(a.group.position.x, a.group.position.y + 1, a.group.position.z, 12);
      if (window.Toast) Toast.info(`Focused on ${a.config.name} (${a.config.role})`);
    }
  }

  // ─── Animation loop ──────────────────────────────────

  animate() {
    requestAnimationFrame(() => this.animate());

    if (!this.tabVisible) return;

    const delta = Math.min(this.clock.getDelta(), 0.05);
    const time = this.clock.getElapsedTime();
    const speedMult = this.reducedMotion ? 0.5 : 1.0;

    // FPS counter every second
    this.frameCount++;
    if (time - this.lastFpsTime >= 1) {
      this.fps = this.frameCount;
      this.frameCount = 0;
      this.lastFpsTime = time;
      const fpsEl = document.getElementById('perf-counter-3d');
      if (fpsEl && !fpsEl.classList.contains('hidden')) {
        fpsEl.textContent = `${this.fps} FPS`;
      }
    }

    // Debounced resize
    if (this.needsResize) {
      this.needsResize = false;
      if (window.renderer) {
        const w = this.container.clientWidth;
        const h = this.container.clientHeight || 580;
        window.renderer.setSize(w, h);
        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
      }
    }

    // Bloom intensity based on contrast mode
    if (this.bloomPass) {
      this.bloomPass.strength = this.highContrast ? 1.4 : 0.9;
    }

    // Holographic ring rotation
    if (this.chambers.holoRings) {
      this.chambers.holoRings.forEach(r => {
        r.mesh.rotation.z += r.speed * speedMult;
        r.mesh.material.opacity = 0.5 + Math.sin(time * 3 + r.mesh.position.z) * 0.2;
      });
    }

    // Boss globe rotation
    if (this.chambers.bossGlobe) {
      this.chambers.bossGlobe.rotation.y += 0.015 * speedMult;
      this.chambers.bossGlobe.rotation.x = Math.sin(time * 0.5) * 0.1;
    }
    if (this.chambers.bossCage) {
      this.chambers.bossCage.rotation.y -= 0.008 * speedMult;
      this.chambers.bossCage.rotation.z = Math.sin(time * 0.3) * 0.05;
    }

    // Boss screens shimmer
    if (this.chambers._bossScreens) {
      this.chambers._bossScreens.forEach((screen, i) => {
        screen.material.emissiveIntensity = 0.7 + Math.sin(time * 2 + i) * 0.15;
      });
    }

    // Energy arcs pulse
    if (this.energyEffects.arc1) this.energyEffects.arc1.material.opacity = 0.1 + Math.sin(time * 4) * 0.08;
    if (this.energyEffects.arc2) this.energyEffects.arc2.material.opacity = 0.1 + Math.sin(time * 4 + 1) * 0.08;

    // Projection beam flicker
    if (this.energyEffects.projBeam) this.energyEffects.projBeam.material.opacity = 0.04 + Math.sin(time * 1.5) * 0.02;

    // Plasma column animation
    if (this.chambers.plasmaColumn) {
      this.chambers.plasmaColumn.forEach((disc, i) => {
        disc.position.y += 0.02 * speedMult;
        if (disc.position.y > 8) disc.position.y = 1.2;
        disc.material.opacity = 0.06 + Math.sin(time * 5 + i * 0.5) * 0.04;
        disc.scale.x = 1 + Math.sin(time * 3 + i) * 0.15;
        disc.scale.z = disc.scale.x;
      });
    }

    // Dust particles drift
    if (this.particles.dust) {
      const pos = this.particles.dust.positions;
      for (let i = 0; i < pos.length; i += 3) {
        pos[i] += Math.sin(time*0.5+i) * 0.001 * speedMult;
        pos[i+1] += Math.cos(time*0.3+i*0.7) * 0.002 * speedMult;
        pos[i+2] += Math.sin(time*0.4+i*0.3) * 0.001 * speedMult;
        if (Math.abs(pos[i]) > 4) pos[i] *= -0.9;
        if (pos[i+1] > 16 || pos[i+1] < 2) pos[i+1] = 2 + Math.random()*14;
      }
      this.particles.dust.mesh.geometry.attributes.position.needsUpdate = true;
    }

    // Coffee steam rise
    if (this.particles.steam) {
      const pos = this.particles.steam.positions;
      for (let i = 0; i < pos.length; i += 3) {
        pos[i+1] += 0.008 * speedMult;
        pos[i] += Math.sin(time*2+i) * 0.001;
        if (pos[i+1] > 2.2) { pos[i+1] = 1.2; pos[i] = (Math.random()-0.5)*3; }
      }
      this.particles.steam.mesh.geometry.attributes.position.needsUpdate = true;
    }

    // Animate characters
    animateAgents(Object.values(this.agents), this.clock, this.reducedMotion);

    // Update status orbs
    updateOrbs(this.statusOrbs, this.agents, time);

    // Particles Zzz sprites
    if (window._zzzData) {
      animateParticles(this.particles, this.clock, this.reducedMotion);
    }

    // Controls auto-rotate
    if (this.controls) {
      this.controls.autoRotate = this.autoRotate;
      this.controls.autoRotateSpeed = this.autoRotate ? 0.8 : 0;
      this.controls.update();
    }

    // Render with post-processing or direct
    if (this.composer) {
      this.composer.render();
    } else {
      window.renderer.render(this.scene, this.camera);
    }

    // Mini-map render
    if (this.minimapVisible) {
      const canvas = document.getElementById('minimap-3d');
      if (canvas) renderMiniMap(canvas, this.agents, this.controls);
    }
  }
}

// Attach globally like the original
window.VirtualOffice3D = VirtualOffice3D;
