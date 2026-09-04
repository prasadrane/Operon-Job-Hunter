function buildChambers(scene) {
  const result = { executive: null, warRoom: null, lounge: null, plasmaColumn: [], energyArcs: [], bossGlobe: null, bossCage: null };

  // === EXECUTIVE SUITE ===
  // Elevated stage platform with clearcoat
  const stage = new THREE.Mesh(
    new THREE.BoxGeometry(16, 1.5, 9),
    new THREE.MeshPhysicalMaterial({ color: 0x0f172a, roughness: 0.4, metalness: 0.6, clearcoat: 0.3 })
  );
  stage.position.set(0, 0.75, -16); stage.receiveShadow = true; stage.castShadow = true; scene.add(stage);
  result.executive = new THREE.Group(); result.executive.add(stage);

  // Gold neon edge trim
  const trim = new THREE.Mesh(new THREE.BoxGeometry(16.2, 0.1, 9.2), new THREE.MeshBasicMaterial({ color: 0xf59e0b }));
  trim.position.set(0, 1.5, -16); scene.add(trim); result.executive.add(trim);

  // Executive desk
  const desk = new THREE.Mesh(
    new THREE.BoxGeometry(6, 1.2, 2.5),
    new THREE.MeshPhysicalMaterial({ color: 0x1e1b4b, roughness: 0.3, metalness: 0.7, clearcoat: 0.5 })
  );
  desk.position.set(0, 2.1, -16); desk.castShadow = true; scene.add(desk); result.executive.add(desk);

  // Boss suit floor glow plane
  const bossGlow = new THREE.Mesh(new THREE.PlaneGeometry(14, 7),
    new THREE.MeshBasicMaterial({ color: 0xf59e0b, transparent: true, opacity: 0.05 }));
  bossGlow.rotation.x = -Math.PI/2; bossGlow.position.set(0, 1.51, -16); scene.add(bossGlow); result.executive.add(bossGlow);

  // 3 curved holographic screens using cylinder segment geometry
  result._bossScreens = [];
  for (let i = -1; i <= 1; i++) {
    const sg = new THREE.CylinderGeometry(1.5, 1.5, 0.9, 16, 1, true, -0.5, 1);
    const sm = new THREE.MeshStandardMaterial({ color: 0x0369a1, emissive: 0x38bdf8, emissiveIntensity: 0.8, roughness: 0.2, side: THREE.DoubleSide });
    const s = new THREE.Mesh(sg, sm);
    s.position.set(i*1.8, 3.1, -15.5-Math.abs(i)*0.2); s.rotation.y = -i*0.25; s.rotation.z = Math.PI/2;
    scene.add(s); result.executive.add(s);
    result._bossScreens.push(s);
  }

  // Projection beam cone from desk upward
  const projBeam = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.8, 2.5, 16, 1, true),
    new THREE.MeshBasicMaterial({ color: 0xfbbf24, transparent: true, opacity: 0.05, side: THREE.DoubleSide, blending: THREE.AdditiveBlending }));
  projBeam.position.set(0, 3.4, -16); scene.add(projBeam); result.executive.add(projBeam); result._projBeam = projBeam;

  // Crystal faceted strategy globe — Icosahedron wireframe + outer cage
  const globeGeo = new THREE.IcosahedronGeometry(0.7, 2);
  const globeEdges = new THREE.EdgesGeometry(globeGeo);
  result.bossGlobe = new THREE.LineSegments(globeEdges, new THREE.LineBasicMaterial({ color: 0xfbbf24, transparent: true, opacity: 0.6 }));
  result.bossGlobe.position.set(0, 3.8, -16); scene.add(result.bossGlobe); result.executive.add(result.bossGlobe);

  const cageGeo = new THREE.IcosahedronGeometry(0.9, 1);
  const cageEdges = new THREE.EdgesGeometry(cageGeo);
  result.bossCage = new THREE.LineSegments(cageEdges, new THREE.LineBasicMaterial({ color: 0xf59e0b, transparent: true, opacity: 0.15 }));
  result.bossCage.position.copy(result.bossGlobe.position); scene.add(result.bossCage); result.executive.add(result.bossCage);

  scene.add(result.executive);

  // === WAR ROOM ===
  result.warRoom = new THREE.Group();

  // Raised circular platform beneath table
  const wrPlatform = new THREE.Mesh(new THREE.CylinderGeometry(4.5, 4.5, 0.15, 32),
    new THREE.MeshStandardMaterial({ color: 0x0c1324, roughness: 0.5, metalness: 0.4 }));
  wrPlatform.position.set(0, 0.075, 0); wrPlatform.receiveShadow = true; scene.add(wrPlatform); result.warRoom.add(wrPlatform);

  // Frosted glass circular table
  const table = new THREE.Mesh(new THREE.CylinderGeometry(4.2, 4.2, 0.3, 32),
    new THREE.MeshPhysicalMaterial({ color: 0x0f172a, roughness: 0.1, metalness: 0.8, transparent: true, opacity: 0.9, clearcoat: 0.6 }));
  table.position.set(0, 0.9, 0); table.castShadow = true; table.receiveShadow = true; scene.add(table); result.warRoom.add(table);

  // Inner ring highlight on table surface
  const innerRing = new THREE.Mesh(new THREE.RingGeometry(1.5, 2.5, 32),
    new THREE.MeshBasicMaterial({ color: 0x06b6d4, transparent: true, opacity: 0.05, side: THREE.DoubleSide }));
  innerRing.rotation.x = -Math.PI/2; innerRing.position.set(0, 1.06, 0); scene.add(innerRing); result.warRoom.add(innerRing);

  // Glowing core
  const core = new THREE.Mesh(new THREE.CylinderGeometry(1.2, 1.2, 0.35, 24),
    new THREE.MeshBasicMaterial({ color: 0x06b6d4 }));
  core.position.set(0, 0.92, 0); scene.add(core); result.warRoom.add(core);

  // Plasma column — 20 stacked discs rising vertically
  result.plasmaColumn = [];
  for (let i = 0; i < 20; i++) {
    const disc = new THREE.Mesh(new THREE.CylinderGeometry(0.8+Math.random()*0.4, 0.8+Math.random()*0.4, 0.06, 12),
      new THREE.MeshBasicMaterial({ color: 0x06b6d4, transparent: true, opacity: 0.06+Math.random()*0.08, blending: THREE.AdditiveBlending }));
    disc.position.set(0, 1.2+i*0.3, 0); scene.add(disc); result.warRoom.add(disc);
    result.plasmaColumn.push(disc);
  }

  // Outer plasma glow cone
  result._plasmaCone = new THREE.Mesh(new THREE.ConeGeometry(1.2, 6, 16, 1, true),
    new THREE.MeshBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.03, side: THREE.DoubleSide, blending: THREE.AdditiveBlending }));
  result._plasmaCone.position.set(0, 4.5, 0); result._plasmaCone.rotation.x = Math.PI;
  scene.add(result._plasmaCone); result.warRoom.add(result._plasmaCone);

  // Floating UI panels beside table
  for (let p = -1; p <= 1; p += 2) {
    const panel = new THREE.Mesh(new THREE.PlaneGeometry(2, 1),
      new THREE.MeshBasicMaterial({ color: 0x06b6d4, transparent: true, opacity: 0.06, side: THREE.DoubleSide }));
    panel.position.set(p*5, 3, 0); panel.rotation.y = p*0.35; scene.add(panel); result.warRoom.add(panel);
  }

  // Energy arcs connecting war room to boss suite — two CatmullRomCurve3 tubes
  function buildArc(offsetX) {
    const pts = [];
    for (let t = 0; t <= 1; t += 0.05) {
      pts.push(new THREE.Vector3((t-0.5)*2*offsetX, Math.sin(t*Math.PI)*0.8+0.5, (1-t)*(-16)));
    }
    const curve = new THREE.CatmullRomCurve3(pts);
    return new THREE.Mesh(new THREE.TubeGeometry(curve, 20, 0.02, 6, false),
      new THREE.MeshBasicMaterial({ color: 0xf59e0b, transparent: true, opacity: 0.15 }));
  }
  result.energyArcs = [buildArc(1), buildArc(-1)];
  result.energyArcs.forEach(arc => { scene.add(arc); result.warRoom.add(arc); });

  // Rotating holographic rings
  result.holoRings = [];
  for (let r = 1; r <= 3; r++) {
    const ring = new THREE.Mesh(new THREE.RingGeometry(1.4*r, 1.45*r, 32),
      new THREE.MeshBasicMaterial({ color: r===2 ? 0x38bdf8 : 0x818cf8, side: THREE.DoubleSide, transparent: true, opacity: 0.7 }));
    ring.position.set(0, 1.3+r*0.4, 0); ring.rotation.x = Math.PI/2;
    scene.add(ring); result.warRoom.add(ring);
    result.holoRings.push({ mesh: ring, speed: 0.01*(r%2===0?1:-1) });
  }

  scene.add(result.warRoom);

  // === LOUNGE AREA ===
  result.lounge = new THREE.Group(); result.lounge.position.set(0, 0, 16);

  // Coffee counter with physical material
  const counter = new THREE.Mesh(new THREE.BoxGeometry(8, 1.1, 2),
    new THREE.MeshPhysicalMaterial({ color: 0x1e293b, roughness: 0.4, clearcoat: 0.3 }));
  counter.position.set(0, 0.55, 0); counter.castShadow = true; scene.add(counter); result.lounge.add(counter);

  // Coffee machine on counter top
  const coffeeMachine = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.7, 0.4),
    new THREE.MeshStandardMaterial({ color: 0x374151, metalness: 0.6 }));
  coffeeMachine.position.set(-2.5, 1.2, 0); scene.add(coffeeMachine); result.lounge.add(coffeeMachine);

  // Neon coffee sign
  const sign = new THREE.Mesh(new THREE.BoxGeometry(3, 0.4, 0.1), new THREE.MeshBasicMaterial({ color: 0x10b981 }));
  sign.position.set(0, 1.6, 0); scene.add(sign); result.lounge.add(sign);

  // Two sofas with armrests, back rests, legs
  for (let s = -1; s <= 1; s += 2) {
    const sofa = new THREE.Group();
    const seat = new THREE.Mesh(new THREE.BoxGeometry(4, 0.5, 1.4), new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.8 }));
    seat.position.y = 0.25; seat.castShadow = true; sofa.add(seat);
    const back = new THREE.Mesh(new THREE.BoxGeometry(4, 0.7, 0.15), new THREE.MeshStandardMaterial({ color: 0x1e293b }));
    back.position.set(0, 0.6, -0.65); sofa.add(back);
    [-1.9, 1.9].forEach(x => {
      const arm = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.4, 1.4), new THREE.MeshStandardMaterial({ color: 0x1e293b }));
      arm.position.set(x, 0.5, 0); sofa.add(arm);
    });
    [[-1.8,-0.5],[1.8,-0.5],[-1.8,0.5],[1.8,0.5]].forEach(([lx,lz]) => {
      const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.03,0.03,0.1,6), new THREE.MeshStandardMaterial({color:0x4b5563,metalness:0.5}));
      leg.position.set(lx,0.05,lz); sofa.add(leg);
    });
    sofa.position.set(s*7, 0, 0); scene.add(sofa); result.lounge.add(sofa);

    // Side table
    const stTop = new THREE.Mesh(new THREE.CylinderGeometry(0.3,0.3,0.05,12), new THREE.MeshStandardMaterial({color:0x4b5563,metalness:0.4}));
    stTop.position.set(s*3.5, 0.5, 0.8); scene.add(stTop); result.lounge.add(stTop);
    const stLeg = new THREE.Mesh(new THREE.CylinderGeometry(0.04,0.04,0.5,6), new THREE.MeshStandardMaterial({color:0x374151}));
    stLeg.position.set(s*3.5, 0.25, 0.8); scene.add(stLeg); result.lounge.add(stLeg);
  }

  // Floor lamp
  const lampPole = new THREE.Mesh(new THREE.CylinderGeometry(0.03,0.03,3,6), new THREE.MeshStandardMaterial({color:0x4b5563}));
  lampPole.position.set(-8, 1.5, 0); scene.add(lampPole); result.lounge.add(lampPole);
  const lampShade = new THREE.Mesh(new THREE.SphereGeometry(0.3,8,8,0,Math.PI*2,0,Math.PI/2),
    new THREE.MeshBasicMaterial({ color: 0xfde047, transparent: true, opacity: 0.6, side: THREE.DoubleSide }));
  lampShade.position.set(-8, 3, 0); scene.add(lampShade); result.lounge.add(lampShade);
  const lampLight = new THREE.PointLight(0xfde047, 0.5, 5);
  lampLight.position.set(-8, 2.8, 0); scene.add(lampLight); result.lounge.add(lampLight);

  scene.add(result.lounge);

  return result;
}
