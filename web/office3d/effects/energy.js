function createEnergyEffects(scene) {
  const result = {};

  // Energy arcs — CatmullRomCurve3 tubes from war room toward boss suite
  function makeArc(offsetX) {
    const pts = [];
    for (let t = 0; t <= 1; t += 0.05) {
      pts.push(new THREE.Vector3(
        (t-0.5)*2*offsetX,
        Math.sin(t*Math.PI)*0.8+0.5,
        (1-t)*(-16)
      ));
    }
    return new THREE.Mesh(
      new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 20, 0.02, 6, false),
      new THREE.MeshBasicMaterial({ color: 0xf59e0b, transparent: true, opacity: 0.15 })
    );
  }

  result.arc1 = makeArc(1); scene.add(result.arc1);
  result.arc2 = makeArc(-1); scene.add(result.arc2);

  // Boss projection beam — translucent cone rising from desk
  result.projBeam = new THREE.Mesh(
    new THREE.CylinderGeometry(0.5, 0.8, 2.5, 16, 1, true),
    new THREE.MeshBasicMaterial({
      color: 0xfbbf24, transparent: true, opacity: 0.05, side: THREE.DoubleSide, blending: THREE.AdditiveBlending
    })
  );
  result.projBeam.position.set(0, 3.4, -16); scene.add(result.projBeam);

  // Plasma column outer cone glow
  result.plasmaCone = new THREE.Mesh(
    new THREE.ConeGeometry(1.2, 6, 16, 1, true),
    new THREE.MeshBasicMaterial({
      color: 0x38bdf8, transparent: true, opacity: 0.03, side: THREE.DoubleSide, blending: THREE.AdditiveBlending
    })
  );
  result.plasmaCone.position.set(0, 4.5, 0); result.plasmaCone.rotation.x = Math.PI; // points downward
  scene.add(result.plasmaCone);

  return result;
}

function animateEnergy(effects, clock, reducedMotion) {
  const time = clock.getElapsedTime();
  const sm = reducedMotion ? 0.5 : 1.0;

  // Arc pulse
  if (effects.arc1 && effects.arc1.material) {
    effects.arc1.material.opacity = 0.1 + Math.sin(time*4)*0.08;
  }
  if (effects.arc2 && effects.arc2.material) {
    effects.arc2.material.opacity = 0.1 + Math.sin(time*4+1)*0.08;
  }

  // Projection beam flicker
  if (effects.projBeam) effects.projBeam.material.opacity = 0.04 + Math.sin(time*1.5)*0.02;

  // Plasma cone wobble
  if (effects.plasmaCone) {
    effects.plasmaCone.scale.x = 1 + Math.sin(time*3)*0.15;
    effects.plasmaCone.scale.z = effects.plasmaCone.scale.x;
  }
}
