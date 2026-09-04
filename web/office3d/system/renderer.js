/**
 * Three.js rendering infrastructure for Office 3D viewer.
 *
 * Exports:
 *   createRenderer(containerId)    – WebGLRenderer with tone-mapping & shadows
 *   createCamera(renderer)         – PerspectiveCamera @ 0,26,32
 *   setupControls(camera, domEl)   – OrbitControls damped + constrained
 *   wireRenderer(containerId)      – glues everything together; default export
 */


/* ------------------------------------------------------------------ */
/*  Renderer                                                           */
/* ------------------------------------------------------------------ */

/**
 * Create and return a configured WebGLRenderer.
 * Also attaches `needsResize` (boolean) as a custom flag on the instance
 * so the debounce / rAF path in {@link wireRenderer} can read it.
 */
function createRenderer(containerId) {
  const container = document.getElementById(containerId);
  if (!container) throw new Error(`Container #${containerId} not found`);

  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    powerPreference: 'high-performance',
  });

  // -- Appearance ---------------------------------------------------
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.3;
  renderer.outputEncoding = THREE.sRGBEncoding;

  // -- Shadows ------------------------------------------------------
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  // -- Custom state used by the render loop -------------------------
  renderer.needsResize = false;

  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

  // Handle hidden containers (0x0 dimensions) by using defaults
  const w = container.clientWidth || 1000;
  const h = container.clientHeight || 580;
  renderer.setSize(w, h);
  container.appendChild(renderer.domElement);

  return renderer;
}

/* ------------------------------------------------------------------ */
/*  Camera                                                             */
/* ------------------------------------------------------------------ */

/**
 * Create a PerspectiveCamera aimed at [0,1,0].
 */
function createCamera(renderer) {
  const container = renderer.domElement.parentElement;
  const aspect = container.clientWidth / container.clientHeight;

  const camera = new THREE.PerspectiveCamera(40, aspect, 0.5, 300);
  camera.position.set(0, 26, 32);
  camera.lookAt(new THREE.Vector3(0, 1, 0));

  return camera;
}

/* ------------------------------------------------------------------ */
/*  Controls                                                           */
/* ------------------------------------------------------------------ */

/**
 * Set up orbit controls with damping and angle constraints.
 */
function setupControls(camera, renderer) {
  const controls = new THREE.OrbitControls(camera, renderer.domElement);

  controls.enableDamping = true;
  controls.dampingFactor = 0.05;
  controls.rotateSpeed = 0.5;
  controls.zoomSpeed = 1.2;
  controls.maxPolarAngle = Math.PI / 2.15;
  controls.minDistance = 10;
  controls.maxDistance = 65;
  controls.target.set(0, 2, 0);

  controls.update();

  return controls;
}

/* ------------------------------------------------------------------ */
/*  Wire – glue everything into a live scene                           */
/* ------------------------------------------------------------------ */

/**
 * Assemble renderer → camera → controls → scene → animate loop.
 *
 * Also hooks:
 *   - debounced resize via rAF (writes renderer.needsResize)
 *   - page Visibility API  → freezes delta on tab-hidden
 *   - simple FPS counter  → frameCount every 1 second
 *
 * @param {string} containerId  – DOM element ID
 * @returns {{renderer: WebGLRenderer, camera: PerspectiveCamera, controls: OrbitControls}}
 */
function wireRenderer(containerId) {
  const renderer = createRenderer(containerId);
  const camera = createCamera(renderer);
  const controls = setupControls(camera, renderer);
  const scene = new THREE.Scene();
  const clock = new THREE.Clock();

  /* -- Tab visibility: pause time when hidden ------------------- */
  let tabVisible = true;
  document.addEventListener('visibilitychange', () => {
    tabVisible = !document.hidden;
    if (tabVisible) clock.getDelta();          // reset delta accumulator
  });

  /* -- Debounced resize via rAF --------------------------------- */
  let rafPending = false;

  window.addEventListener('resize', () => {
    renderer.needsResize = true;

    if (!rafPending) {
      rafPending = true;
      requestAnimationFrame(() => {
        rafPending = false;
        if (!renderer.needsResize) return;

        const container = renderer.domElement.parentElement;
        if (!container) return;

        const w = container.clientWidth;
        const h = container.clientHeight;

        renderer.setSize(w, h);
        camera.aspect = w / h;
        camera.updateProjectionMatrix();

        renderer.needsResize = false;
      });
    }
  });

  /* -- FPS tracking ----------------------------------------------- */
  let frameCount = 0;
  let fpsAccum = 0;
  let fpsValue = 0;

  /* -- Render loop ------------------------------------------------ */
  function animate() {
    requestAnimationFrame(animate);

    if (!tabVisible) return;

    const delta = clock.getDelta();

    // FPS counter – roll-over every 1 s wall-clock
    frameCount++;
    fpsAccum += delta;
    if (fpsAccum >= 1.0) {
      fpsValue = Math.round(frameCount / fpsAccum);
      frameCount = 0;
      fpsAccum = 0;
    }

    controls.update();
    renderer.render(scene, camera);
  }

  animate();

  return { renderer, camera, controls };
}
