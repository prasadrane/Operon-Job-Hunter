import { FactoryRenderer } from './renderer.js';
import { StateManager } from './state.js';
import { SSEBridge } from './sync.js';
import { EntityManager } from './entities.js';
import { AnimationManager } from './animations.js';
import { InteractionManager } from './interaction.js';
import { CameraController } from './camera.js';
import { TooltipManager } from './tooltip.js';
import { KeyboardNavigator, ConfirmationModal } from './keyboard.js';
import { A11yOverlay } from './a11y-overlay.js';
import { MotionGate } from './motion-gate.js';
import { PanelManager } from './panel-manager.js';
import { Router } from './router.js';
import { EmptyStateOverlay } from './empty-state.js';
import { StandupOverlay } from './standup-overlay.js';
import { renderAgentPanel } from './panels/agent-panel.js';
import { renderJobPanel } from './panels/job-panel.js';
import { renderZonePanel } from './panels/zone-panel.js';
import { renderErrorPanel } from './panels/error-panel.js';
import { Canvas2DFallback } from './canvas2d-fallback.js';

export function initFactory(options = {}) {
  if (window.factory) return window.factory;
  if (typeof PIXI === 'undefined') {
    console.warn('PixiJS runtime not available; skipping factory initialization.');
    return null;
  }

  const placeholder = document.getElementById('factory-canvas');
  if (!placeholder && !options.force) {
    return null;
  }

  const container = placeholder?.parentElement || document.body;
  const isBody = container === document.body;
  const width = isBody ? window.innerWidth : (container.clientWidth || window.innerWidth);
  const height = isBody ? window.innerHeight : (container.clientHeight || 650);

  // Canvas2D fallback
  const fallback = new Canvas2DFallback();
  fallback.setupVisibilityListener();
  const renderConfig = fallback.getRenderConfig();

  // Initialize PixiJS application for 2D Platformer
  const app = new PIXI.Application({
    width: width,
    height: height,
    backgroundColor: 0x07090e,
    antialias: true,
    resolution: window.devicePixelRatio || 1,
  });
  app.canvas = app.view;
  if (placeholder) {
    app.view.id = 'factory-canvas';
    app.view.className = 'w-full block rounded-2xl';
    placeholder.replaceWith(app.view);
  }

  // Initialize managers
  const state = new StateManager();
  const renderer = new FactoryRenderer(app);
  const entities = new EntityManager(app, state, renderer);
  const animations = new AnimationManager(entities);

  // Camera controller — owns pan/zoom
  const camera = new CameraController({ screen: app.screen });
  renderer.setCamera(camera);

  // Center 2D platformer view comfortably across all 5 tiers (scale 0.88 fits 100% of plant)
  camera.setZoom(0.88);
  camera.panTo(0, 250);

  // Motion gate
  const motionGate = new MotionGate();
  camera.setMotionGate(motionGate);
  animations.setMotionGate?.(motionGate);

  // Tooltip
  const tooltip = new TooltipManager(document.body);
  const interaction = new InteractionManager(app, entities, state, camera, tooltip, motionGate);

  // A11y overlay + keyboard navigator
  const overlay = new A11yOverlay(app.canvas, camera);
  const keyboard = new KeyboardNavigator({ camera, entities, overlay });
  keyboard.attach();
  const confirmModal = new ConfirmationModal();

  // Sync overlay hit targets
  app.ticker.add(() => {
    if (typeof entities.getHitTargets === 'function') {
      overlay.sync(entities.getHitTargets());
    }
  });

  // Wire retry confirmation flow
  window.addEventListener('factory:request-retry', async (e) => {
    const ok = await confirmModal.confirm({
      title: 'Retry stage?',
      body: `Retry job for error ${e.detail.errorId}. Estimated cost: $0.04, ~30s.`,
      confirmLabel: 'Confirm Retry',
    });
    if (ok) window.dispatchEvent(new CustomEvent('factory:confirm-retry', { detail: e.detail }));
  });

  // Panel & overlay managers
  const panelRoot = document.getElementById('panel-root');
  const overlayRoot = document.getElementById('overlay-root');
  const panels = new PanelManager(panelRoot);
  const router = new Router();
  const emptyState = new EmptyStateOverlay(overlayRoot);
  const standup = new StandupOverlay(overlayRoot);

  // Restore URL state on load
  router.applyUrl((params) => {
    if (params.zoom) renderer.setZoom(parseFloat(params.zoom));
    if (params.focus) entities.focusOn(params.focus);
    if (params.mode) state.setMode(params.mode);
  });

  // Panel open helpers
  function openAgentPanel(agentId) {
    const agent = state.agentStates.get(agentId) || { id: agentId, name: agentId, role: 'Subagent' };
    const panel = renderAgentPanel(agent, () => panels.close());
    panels.open(panel, document.activeElement);
    router.pushUpdate({ focus: agentId });
  }

  function openJobPanel(jobId) {
    const allJobs = [
      ...(state.jobQueue?.discovered || []),
      ...(state.jobQueue?.evaluation || []),
      ...(state.jobQueue?.tailored || []),
      ...(state.jobQueue?.applied || []),
    ];
    const job = allJobs.find(j => j.id === jobId) || { id: jobId, company: 'Job', title: 'Details' };
    const panel = renderJobPanel(job, () => panels.close());
    panels.open(panel, document.activeElement);
    router.pushUpdate({ job: jobId });
  }

  function openZonePanel(zoneName) {
    const zone = state.getZones?.()[zoneName] || { name: zoneName, stage: 1, queue: [] };
    const panel = renderZonePanel(zone, () => panels.close(), (jid) => openJobPanel(jid));
    panels.open(panel, document.activeElement);
  }

  function openErrorPanel(errorData) {
    const panel = renderErrorPanel(errorData, () => panels.close());
    panels.open(panel, document.activeElement);
  }

  // Wire click to open detail panel
  window.addEventListener('factory:open-detail', (e) => {
    const { kind, data } = e.detail || {};
    if (kind === 'agent' && data) {
      openAgentPanel(data.id || data.name);
    } else if (kind === 'job' && data) {
      openJobPanel(data.id);
    } else if (kind === 'zone' && data) {
      openZonePanel(data.name || data.id);
    }
  });

  // Connect SSE
  const sync = new SSEBridge(state, entities);
  sync.connect('/api/v2/factory/stream');

  // Update camera each frame
  app.ticker.add((dt) => {
    if (fallback.shouldPauseRendering()) return;
    const deltaMs = dt * 16.67;
    camera.update(deltaMs);
    renderer.update(deltaMs);
    entities.update(deltaMs);
  });

  // Handle window resize
  const resizeHandler = () => {
    const p = app.view?.parentElement || document.body;
    const w = p === document.body ? window.innerWidth : (p.clientWidth || window.innerWidth);
    const h = p === document.body ? window.innerHeight : (p.clientHeight || 650);
    if (w > 0 && h > 0) {
      app.renderer.resize(w, h);
      renderer.resize();
    }
  };
  window.addEventListener('resize', resizeHandler);

  const factoryObj = {
    app,
    state,
    renderer,
    entities,
    animations,
    interaction,
    sync,
    camera,
    tooltip,
    keyboard,
    overlay,
    confirmModal,
    motionGate,
    panels,
    router,
    emptyState,
    standup,
    fallback,
    renderConfig,
    openAgentPanel,
    openJobPanel,
    openZonePanel,
    openErrorPanel,
    resize: resizeHandler,
  };

  window.factory = factoryObj;
  return factoryObj;
}

// Auto-run if canvas is already present on load
if (typeof document !== 'undefined' && document.getElementById('factory-canvas')) {
  initFactory();
}
