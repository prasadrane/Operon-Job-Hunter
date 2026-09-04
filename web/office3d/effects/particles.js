// 3D office ambient particles — dust motes, coffee steam, sleeping Zzz sprites.

function createParticles(scene) {
  const result = {};

  // Dust motes — 200 points drifting in spotlight zones near boss suite
  const dustCount = 200;
  const dustGeo = new THREE.BufferGeometry();
  const dustPos = new Float32Array(dustCount * 3);
  const dustCols = new Float32Array(dustCount * 3);
  for (let i = 0; i < dustCount; i++) {
    dustPos[i*3]     = (Math.random() - 0.5) * 8;
    dustPos[i*3 + 1] = 2 + Math.random() * 14;
    dustPos[i*3 + 2] = -18 + Math.random() * 10;
    const g = Math.random() > 0.5;
    dustCols[i*3]     = g ? 0.96 : 0.22;
    dustCols[i*3 + 1] = g ? 0.85 : 0.72;
    dustCols[i*3 + 2] = g ? 0.33 : 0.98;
  }
  dustGeo.setAttribute('position', new THREE.BufferAttribute(dustPos, 3));
  dustGeo.setAttribute('color',    new THREE.BufferAttribute(dustCols, 3));
  const dustMat = new THREE.PointsMaterial({
    size: 0.06, vertexColors: true, transparent: true, opacity: 0.35,
    blending: THREE.AdditiveBlending, depthWrite: false,
  });
  const dust = new THREE.Points(dustGeo, dustMat);
  scene.add(dust);
  result.dust = { mesh: dust, positions: dustPos };

  // Coffee steam wisps — 30 particles rising from lounge counter area
  const steamCount = 30;
  const steamGeo = new THREE.BufferGeometry();
  const steamPos = new Float32Array(steamCount * 3);
  for (let i = 0; i < steamCount; i++) {
    steamPos[i*3]     = (Math.random() - 0.5) * 3;
    steamPos[i*3 + 1] = 1.2 + Math.random() * 0.8;
    steamPos[i*3 + 2] = 15.8 + (Math.random() - 0.5) * 0.5;
  }
  steamGeo.setAttribute('position', new THREE.BufferAttribute(steamPos, 3));
  const steamMat = new THREE.PointsMaterial({
    size: 0.08, color: 0x10b981, transparent: true, opacity: 0.15,
    blending: THREE.AdditiveBlending, depthWrite: false,
  });
  const steam = new THREE.Points(steamGeo, steamMat);
  scene.add(steam);
  result.steam = { mesh: steam, positions: steamPos };

  // Zzz sprites above sleeping agents
  result.zzzSprites = [];

  return result;
}

function animateParticles(particles, clock, reducedMotion) {
  const time = clock.getElapsedTime();
  const speedMult = reducedMotion ? 0.5 : 1.0;

  // Animate dust drift
  if (particles.dust) {
    const pos = particles.dust.positions;
    for (let i = 0; i < pos.length; i += 3) {
      pos[i]     += Math.sin(time * 0.5 + i)     * 0.001 * speedMult;
      pos[i + 1] += Math.cos(time * 0.3 + i * 0.7) * 0.002 * speedMult;
      pos[i + 2] += Math.sin(time * 0.4 + i * 0.3) * 0.001 * speedMult;
      if (Math.abs(pos[i]) > 4) pos[i] *= -0.9;
      if (pos[i + 1] > 16 || pos[i + 1] < 2) pos[i + 1] = 2 + Math.random() * 14;
    }
    particles.dust.mesh.geometry.attributes.position.needsUpdate = true;
  }

  // Animate coffee steam rise
  if (particles.steam) {
    const pos = particles.steam.positions;
    for (let i = 0; i < pos.length; i += 3) {
      pos[i + 1] += 0.008 * speedMult;
      pos[i]     += Math.sin(time * 2 + i) * 0.001;
      if (pos[i + 1] > 2.2) {
        pos[i + 1] = 1.2;
        pos[i] = (Math.random() - 0.5) * 3;
      }
    }
    particles.steam.mesh.geometry.attributes.position.needsUpdate = true;
  }

  // Update Zzz sprites above sleeping agents (from window._zzzData set by animations.js)
  if (window._zzzData) {
    window._zzzData.forEach(({ key, agent }) => {
      if (!agent.group) return;
      let sprite = particles.zzzSprites.find(s => s.key === key);
      if (!sprite) {
        const canvas = document.createElement('canvas');
        canvas.width = 64;
        canvas.height = 64;
        const ctx = canvas.getContext('2d');
        ctx.font = 'bold 40px monospace';
        ctx.fillStyle = '#38bdf8';
        ctx.textAlign = 'center';
        ctx.fillText('Zzz...', 32, 40);
        const texture = new THREE.CanvasTexture(canvas);
        sprite = { key, material: new THREE.SpriteMaterial({ map: texture, transparent: true, opacity: 0 }), created: time };
        const sp = new THREE.Sprite(sprite.material);
        sceneAdd(sp);
        sprite.mesh = sp;
        particles.zzzSprites.push(sprite);
      }
      const isActive = agent.status !== 'sleeping';
      const targetOpacity = isActive ? 0 : 0.5 + Math.sin(time * 2 + key.charCodeAt(0)) * 0.2;
      sprite.material.opacity += (targetOpacity - sprite.material.opacity) * 0.05;
      if (sprite.mesh && agent.group) {
        sprite.mesh.position.set(
          agent.group.position.x,
          agent.group.position.y + 2.5,
          agent.group.position.z,
        );
      }
      if (isActive && sprite.created + 0.5 < time) {
        sceneRemove(sprite.mesh);
        sprite.mesh.material.dispose();
        particles.zzzSprites = particles.zzzSprites.filter(s => s.key !== key);
      }
    });
  }
}

function sceneAdd(obj) { if (window._sceneRef) window._sceneRef.add(obj); }
function sceneRemove(obj) { if (window._sceneRef) window._sceneRef.remove(obj); }
