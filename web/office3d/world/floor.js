function buildFloor(scene) {
  const result = []; // collection of created objects

  // 1. Reflective dark floor — MeshPhysicalMaterial for clearcoat
  const floorGeo = new THREE.PlaneGeometry(44, 42);
  const floorMat = new THREE.MeshPhysicalMaterial({
    color: 0x0a0f1d, roughness: 0.35, metalness: 0.6,
    clearcoat: 0.4, clearcoatRoughness: 0.2,
  });
  const floor = new THREE.Mesh(floorGeo, floorMat);
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  scene.add(floor);
  result.push(floor);

  // 2. Grid lines fading toward edges
  for (let i = 0; i < 44; i++) {
    const x = -22 + i;
    const distFromCenter = Math.abs(i - 22) / 22;
    const opacity = Math.max(0.08, 0.3 * (1 - distFromCenter));
    // X-lines
    const xLine = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(x, 0.01, -21), new THREE.Vector3(x, 0.01, 21)]),
      new THREE.LineBasicMaterial({ color: 0x1e3a8a, transparent: true, opacity })
    );
    scene.add(xLine); result.push(xLine);
    // Z-lines
    const zLine = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-22, 0.01, x), new THREE.Vector3(22, 0.01, x)]),
      new THREE.LineBasicMaterial({ color: 0x1e3a8a, transparent: true, opacity })
    );
    scene.add(zLine); result.push(zLine);
  }

  // 3. Neon accent rings radiating outward
  [5, 15, 25].forEach(r => {
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(r, r + 0.04, 64),
      new THREE.MeshBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.3 })
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.02;
    scene.add(ring); result.push(ring);
  });

  // 4. War room raised platform
  const wrPlatform = new THREE.Mesh(
    new THREE.CylinderGeometry(5, 5, 0.15, 32),
    new THREE.MeshStandardMaterial({ color: 0x0c1324, roughness: 0.5, metalness: 0.4 })
  );
  wrPlatform.position.set(0, 0.075, 0);
  wrPlatform.receiveShadow = true;
  scene.add(wrPlatform); result.push(wrPlatform);

  // 5. Lounge area rug
  const loungeRug = new THREE.Mesh(
    new THREE.PlaneGeometry(10, 6),
    new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.9 })
  );
  loungeRug.rotation.x = -Math.PI / 2;
  loungeRug.position.set(0, 0.015, 16);
  scene.add(loungeRug); result.push(loungeRug);

  // 6. Edge glow particles (100 points on perimeter circle)
  const epCount = 100, epGeo = new THREE.BufferGeometry(), epPos = new Float32Array(epCount * 3);
  for (let i = 0; i < epCount; i++) {
    const angle = Math.random() * Math.PI * 2, radius = 20 + Math.random() * 2;
    epPos[i*3] = Math.cos(angle)*radius; epPos[i*3+1] = 0.05; epPos[i*3+2] = Math.sin(angle)*radius;
  }
  epGeo.setAttribute('position', new THREE.BufferAttribute(epPos, 3));
  const edgeParticles = new THREE.Points(epGeo,
    new THREE.PointsMaterial({ size: 0.04, color: 0x38bdf8, transparent: true, opacity: 0.2, blending: THREE.AdditiveBlending, depthWrite: false }));
  scene.add(edgeParticles); result.push(edgeParticles);

  // 7. Hazard stripe markings near lounge entrance
  for (let i = 0; i < 5; i++) {
    const s = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.01, 0.4),
      new THREE.MeshBasicMaterial({ color: 0xf59e0b, transparent: true, opacity: 0.12 }));
    s.position.set(-4+i*2, 0.02, 12.5);
    scene.add(s); result.push(s);
  }

  // 8. Boss suite floor glow
  const bossGlow = new THREE.Mesh(
    new THREE.PlaneGeometry(14, 7),
    new THREE.MeshBasicMaterial({ color: 0xf59e0b, transparent: true, opacity: 0.05 })
  );
  bossGlow.rotation.x = -Math.PI / 2;
  bossGlow.position.set(0, 0.016, -16);
  scene.add(bossGlow); result.push(bossGlow);

  return result;
}
