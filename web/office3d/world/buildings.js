function buildWorld(scene) {
  const result = [];

  // Frosted glass walls (left, right, back)
  const wallMat = new THREE.MeshPhysicalMaterial({
    color: 0x0f172a, transparent: true, opacity: 0.12, roughness: 0.9, metalness: 0,
    transmission: 0.8, clearcoat: 0.2, side: THREE.DoubleSide,
  });
  [-22, 22].forEach(x => {
    const w = new THREE.Mesh(new THREE.PlaneGeometry(0.5, 16), wallMat.clone());
    w.position.set(x, 5, 0); scene.add(w); result.push(w);
  });
  const bw = new THREE.Mesh(new THREE.PlaneGeometry(44, 16), wallMat.clone());
  bw.position.set(0, 5, -21); scene.add(bw); result.push(bw);

  // Ceiling light strips over wings
  const stripA = new THREE.MeshBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.5 });
  const stripB = new THREE.MeshBasicMaterial({ color: 0xa78bfa, transparent: true, opacity: 0.5 });
  for (let i = -1; i <= 1; i++) {
    const s1 = new THREE.Mesh(new THREE.BoxGeometry(0.15, 0.05, 14), stripA.clone());
    s1.position.set(-8 + i*3, 12, -6); scene.add(s1); result.push(s1);
  }
  for (let i = -1; i <= 1; i++) {
    const s2 = new THREE.Mesh(new THREE.BoxGeometry(0.15, 0.05, 14), stripB.clone());
    s2.position.set(8 + i*3, 12, -6); scene.add(s2); result.push(s2);
  }
  const centerStrip = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.05, 42), stripA.clone());
  centerStrip.position.set(0, 12, 2); scene.add(centerStrip); result.push(centerStrip);

  // 8 pillars with LED ring tops
  const pillarMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.7, metalness: 0.5 });
  const ledColors = [0x38bdf8, 0xa78bfa, 0x10b981];
  [[-21.5, 20.5], [21.5, 20.5], [-21.5, -20.5], [21.5, -20.5],
   [0, -20.5], [0, 20.5], [-21.5, 0], [21.5, 0]].forEach(([cx, cz], idx) => {
    const p = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.2, 14, 8), pillarMat.clone());
    p.position.set(cx, 7, cz); p.castShadow = true; scene.add(p); result.push(p);
    const lr = new THREE.Mesh(new THREE.TorusGeometry(0.3, 0.04, 8, 16),
      new THREE.MeshBasicMaterial({ color: ledColors[idx % 3] }));
    lr.position.set(cx, 13.5, cz); lr.rotation.x = Math.PI / 2;
    scene.add(lr); result.push(lr);
  });

  // Cyber pipe conduits along floor-wall edges
  const conduitMat = new THREE.MeshBasicMaterial({ color: 0x0284c7, transparent: true, opacity: 0.6 });
  [[[-21.8, 20], [-21.8, -20]], [[21.8, 20], [21.8, -20]], [[-21.8, -20], [21.8, -20]]].forEach(([s, e]) => {
    const dir = new THREE.Vector3(e[0], 0.1, e[1]).sub(new THREE.Vector3(s[0], 0.1, s[1]));
    const len = dir.length();
    const c = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, len, 6), conduitMat);
    c.position.set((s[0]+e[0])/2, 0.1, (s[1]+e[1])/2);
    c.rotation.z = Math.PI / 2; c.rotation.y = -Math.atan2(dir.x, dir.z);
    scene.add(c); result.push(c);
  });

  // Holographic door frames at executive entrance
  const frameMat = new THREE.MeshBasicMaterial({ color: 0xf59e0b, transparent: true, opacity: 0.4 });
  const corners = [[-2,-12],[-2,-10],[2,-10],[2,-12]];
  for (let i = 0; i < 4; i++) {
    const [sx,sz]=corners[i], [ex,ez]=corners[(i+1)%4];
    const mx=(sx+ex)/2, mz=(sz+ez)/2, len=Math.sqrt((ex-sx)**2+(ez-sz)**2);
    let edge;
    if (i%2===0) { edge = new THREE.Mesh(new THREE.BoxGeometry(len,0.06,0.06), frameMat); edge.position.set(mx,i===0?5:0,mz); }
    else { edge = new THREE.Mesh(new THREE.BoxGeometry(0.06,5,0.06), frameMat); edge.position.set(sx,2.5,sz); }
    scene.add(edge); result.push(edge);
  }

  // Cityscape silhouette in fog distance
  const bldgMat = new THREE.MeshBasicMaterial({ color: 0x0a0f1d });
  const winMat = new THREE.MeshBasicMaterial({ color: 0xfde047 });
  for (let i = 0; i < 60; i++) {
    const h = 2+Math.random()*8, w = 0.5+Math.random()*1.5, d = 0.5+Math.random()*1.5;
    const x = -40+Math.random()*80, z = -28-Math.random()*10;
    const b = new THREE.Mesh(new THREE.BoxGeometry(w,h,d), bldgMat);
    b.position.set(x, h/2-1, z); scene.add(b); result.push(b);
    if (Math.random() > 0.5) {
      const wg = new THREE.BoxGeometry(w*0.3, h*0.08, 0.02);
      for (let j = 0; j < Math.floor(Math.random()*4); j++) {
        const win = new THREE.Mesh(wg, winMat.clone());
        win.material.opacity = 0.1+Math.random()*0.3; win.material.transparent = true;
        win.position.copy(b.position); win.position.y+=(Math.random()-0.5)*h*0.6;
        win.position.x+=(Math.random()-0.5)*w*0.3; win.position.z+=d/2+0.01;
        scene.add(win); result.push(win);
      }
    }
  }

  // Ceiling truss beams
  const trussMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.6, metalness: 0.7 });
  for (let z = -18; z <= 18; z += 9) {
    const beam = new THREE.Mesh(new THREE.BoxGeometry(24, 0.15, 0.3), trussMat);
    beam.position.set(0, 13, z); scene.add(beam); result.push(beam);
  }

  return result;
}
