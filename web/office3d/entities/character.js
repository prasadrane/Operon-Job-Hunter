class ProceduralCharacterFactory {
  static create(cfg) {
    const grp = new THREE.Group();
    grp.name = 'agent_' + cfg.id;

    // Torso layered jacket (suitColor)
    const torso = new THREE.Mesh(new THREE.BoxGeometry(0.75, 0.95, 0.48),
      new THREE.MeshStandardMaterial({ color: cfg.suitColor, roughness: 0.6 }));
    torso.position.y = 1.05; torso.castShadow = true; grp.add(torso);

    // Shirt panel line down center
    const shirtLine = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.85, 0.01),
      new THREE.MeshStandardMaterial({ color: cfg.color, transparent: true, opacity: 0.2 }));
    shirtLine.position.set(0, 1.05, 0.24); grp.add(shirtLine);

    // Lanyard with gold ID badge
    const lanyard = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.3, 0.01),
      new THREE.MeshBasicMaterial({ color: cfg.visorColor, transparent: true, opacity: 0.5 }));
    lanyard.position.set(0.15, 1.35, 0.24); grp.add(lanyard);
    const badge = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.1, 0.005),
      new THREE.MeshStandardMaterial({ color: 0xfbbf24 }));
    badge.position.set(0.15, 1.2, 0.25); grp.add(badge);

    // Shoulder pads
    [-0.42, 0.42].forEach(x => {
      const p = new THREE.Mesh(new THREE.BoxGeometry(0.15, 0.08, 0.2),
        new THREE.MeshStandardMaterial({ color: cfg.suitColor, roughness: 0.5 }));
      p.position.set(x, 1.52, 0); grp.add(p);
    });

    // Belt detail at waist
    const belt = new THREE.Mesh(new THREE.BoxGeometry(0.72, 0.06, 0.46),
      new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.5, metalness: 0.6 }));
    belt.position.set(0, 0.58, 0); grp.add(belt);

    // Capsule head — scaled sphere
    const hg = new THREE.SphereGeometry(0.32, 16, 16);
    hg.scale(1, 1.15, 0.95);
    const head = new THREE.Mesh(hg, new THREE.MeshStandardMaterial({ color: 0xfde047, roughness: 0.4 }));
    head.position.y = 1.82; head.castShadow = true; grp.add(head);

    // Cyber visor wrapping temples
    const visor = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.16, 0.28),
      new THREE.MeshStandardMaterial({ color: cfg.visorColor, emissive: cfg.visorColor, emissiveIntensity: 0.7 }));
    visor.position.set(0, 1.85, 0.25); grp.add(visor);

    // Visor temple wings
    [-0.26, 0.26].forEach(vx => {
      const w = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.08, 0.2),
        new THREE.MeshStandardMaterial({ color: cfg.visorColor, emissive: cfg.visorColor, emissiveIntensity: 0.4 }));
      w.position.set(vx, 1.85, 0.15); grp.add(w);
    });

    // Earpiece comm units
    [-0.35, 0.35].forEach(ex => {
      const ep = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.12, 8),
        new THREE.MeshStandardMaterial({ color: 0x374151 }));
      ep.rotation.z = Math.PI/2; ep.position.set(ex, 1.8, 0); grp.add(ep);
    });

    // Upper arms
    const armMat = new THREE.MeshStandardMaterial({ color: cfg.suitColor });
    const lau = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.65, 0.2), armMat.clone());
    lau.position.set(-0.5, 1.1, 0); grp.add(lau);
    const rau = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.65, 0.2), armMat.clone());
    rau.position.set(0.5, 1.1, 0); grp.add(rau);

    // Forearms
    const laf = new THREE.Mesh(new THREE.BoxGeometry(0.17, 0.5, 0.17), armMat.clone());
    laf.position.set(-0.5, 0.55, 0); grp.add(laf);
    const raf = new THREE.Mesh(new THREE.BoxGeometry(0.17, 0.5, 0.17), armMat.clone());
    raf.position.set(0.5, 0.55, 0); grp.add(raf);

    // Palms
    const palmMat = new THREE.MeshStandardMaterial({ color: cfg.suitColor });
    [-0.5, 0.5].forEach(x => {
      const palm = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.1, 0.08), palmMat);
      palm.position.set(x, 0.25, 0); grp.add(palm);
    });

    // Fingers — 3 per hand
    const fingerGeo = new THREE.BoxGeometry(0.04, 0.1, 0.04);
    const fingerMat = new THREE.MeshStandardMaterial({ color: 0xfde047 });
    [-0.58, -0.48, -0.38].forEach((fx, fi) => {
      const f = new THREE.Mesh(fingerGeo, fingerMat);
      f.position.set(fx, 0.18, 0); f.userData.fingerIndex = fi; f.userData.side = 'left';
      grp.add(f);
    });
    [-0.42, -0.52, -0.62].forEach((fx, fi) => {
      const f = new THREE.Mesh(fingerGeo, fingerMat);
      f.position.set(fx, 0.18, 0); f.userData.fingerIndex = fi; f.userData.side = 'right';
      grp.add(f);
    });

    // Legs
    const legMat = new THREE.MeshStandardMaterial({ color: 0x0f172a });
    const ll = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.75, 0.24), legMat.clone());
    ll.position.set(-0.2, 0.375, 0); grp.add(ll);
    const rl = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.75, 0.24), legMat.clone());
    rl.position.set(0.2, 0.375, 0); grp.add(rl);

    // Boots matching suit color
    const bootMat = new THREE.MeshStandardMaterial({ color: cfg.suitColor, roughness: 0.4, metalness: 0.3 });
    [-0.2, 0.2].forEach(x => {
      const boot = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.12, 0.32), bootMat);
      boot.position.set(x, 0.06, 0.03); grp.add(boot);
    });

    // Accessory per role
    const accMap = {
      magnifier: () => {
        const arc = new THREE.Mesh(new THREE.TorusGeometry(0.12, 0.015, 6, 12, Math.PI*1.5),
          new THREE.MeshStandardMaterial({ color: cfg.color, metalness: 0.5 }));
        arc.position.set(0.55, 0.8, 0.3); return arc;
      },
      scales: () => {
        const s = new THREE.Mesh(new THREE.TorusGeometry(0.1, 0.01, 6, 12),
          new THREE.MeshBasicMaterial({ color: 0xf59e0b }));
        s.position.set(0, 2.2, 0); return s;
      },
      shield: () => {
        const sh = new THREE.Mesh(new THREE.CircleGeometry(0.08, 6),
          new THREE.MeshBasicMaterial({ color: 0xef4444 }));
        sh.position.set(0, 1.05, 0.25); return sh;
      },
      stylus: () => {
        const pen = new THREE.Mesh(new THREE.CylinderGeometry(0.01, 0.01, 0.25, 4),
          new THREE.MeshStandardMaterial({ color: cfg.color, metalness: 0.4 }));
        pen.position.set(0.55, 0.6, 0.3); return pen;
      },
      rocket: () => {
        const r = new THREE.Mesh(new THREE.ConeGeometry(0.04, 0.15, 6),
          new THREE.MeshBasicMaterial({ color: cfg.color }));
        r.position.set(-0.55, 0.6, 0.3); r.rotation.z = 0.3; return r;
      },
      envelope: () => {
        const e = new THREE.Mesh(new THREE.PlaneGeometry(0.12, 0.08),
          new THREE.MeshBasicMaterial({ color: cfg.color }));
        e.position.set(0.5, 0.7, 0.3); return e;
      },
      radar_dish: () => {
        const d = new THREE.Mesh(new THREE.RingGeometry(0.08, 0.12, 12, 1, 0, Math.PI),
          new THREE.MeshBasicMaterial({ color: cfg.visorColor, side: THREE.DoubleSide }));
        d.position.set(-0.5, 0.7, 0.25); return d;
      },
      crown: () => {
        const c = new THREE.Mesh(new THREE.TorusGeometry(0.15, 0.03, 8, 16),
          new THREE.MeshBasicMaterial({ color: 0xf59e0b }));
        c.position.set(0, 2.05, 0); c.rotation.x = Math.PI/2; return c;
      },
    };
    if (cfg.accessory && accMap[cfg.accessory]) {
      const acc = accMap[cfg.accessory]();
      grp.add(acc);
    }

    // Return refs for animation modules to grab specific meshes by key
    const childrenByY = {};
    grp.children.forEach(c => {
      if (c.position.y === 1.82) childrenByY.head = c;
      if (c.position.y === 1.05 && c.geometry?.parameters?.width > 0.5) childrenByY.torso = c;
      if (c.position.x === -0.5 && c.position.y === 1.1) childrenByY.leftArmUpper = c;
      if (c.position.x === 0.5 && c.position.y === 1.1) childrenByY.rightArmUpper = c;
      if (c.position.x === -0.5 && c.position.y < 1 && c.geometry?.parameters?.height > 0.45) childrenByY.leftForearm = c;
      if (c.position.x === 0.5 && c.position.y < 1 && c.geometry?.parameters?.height > 0.45) childrenByY.rightForearm = c;
      if (c.position.x === -0.2 && c.position.z === 0) childrenByY.leftLeg = c;
      if (c.position.x === 0.2 && c.position.z === 0) childrenByY.rightLeg = c;
    });

    return { group: grp, ...childrenByY, config: cfg };
  }
}
