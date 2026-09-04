function animateAgents(agents, clock, reducedMotion) {
  const delta = Math.min(clock.getDelta(), 0.05);
  const time = clock.getElapsedTime();
  const speedMult = reducedMotion ? 0.5 : 1.0;

  for (const agent of agents) {
    const grp = agent.group;

    // Breathing idle sway on torso
    const breathe = Math.sin(time * 1.5 + agent.breathPhase) * 0.015 * speedMult;
    if (grp.children[0]) grp.children[0].position.y = (agent._torsoBaseY || 1.05) + breathe;

    // Blink timer
    if (!agent.isBlinking && time > agent.nextBlinkTime) {
      agent.isBlinking = true;
      agent.blinkTimer = 0.15;
    }
    if (agent.isBlinking) {
      agent.blinkTimer -= delta;
      const h = agent.head || grp.children.find(c => c.position.y === 1.82);
      if (h) {
        const origY = h.scale.y;
        h.scale.y = Math.max(0.2, origY - delta * 2);
        if (agent.blinkTimer <= 0) {
          agent.isBlinking = false;
          agent.nextBlinkTime = time + 3 + Math.random() * 4;
          h.scale.y = 1;
        }
      }
    }

    // Walk toward targetPos
    const dist = grp.position.distanceTo(agent.targetPos);
    if (dist > 0.1) {
      const dir = new THREE.Vector3().subVectors(agent.targetPos, grp.position).normalize();
      grp.position.addScaledVector(dir, Math.min(dist, delta * 4.5));
      grp.lookAt(agent.targetPos.x, grp.position.y, agent.targetPos.z);

      // Walking swing
      const sw = 12 * speedMult;
      if (agent.leftLeg) agent.leftLeg.rotation.x = Math.sin(time * sw) * 0.5;
      if (agent.rightLeg) agent.rightLeg.rotation.x = -Math.sin(time * sw) * 0.5;
      if (agent.leftArmUpper) agent.leftArmUpper.rotation.x = -Math.sin(time * sw) * 0.4;
      if (agent.rightArmUpper) agent.rightArmUpper.rotation.x = Math.sin(time * sw) * 0.4;
      if (agent.leftForearm) agent.leftForearm.rotation.x = -Math.sin(time * sw * 0.8) * 0.3;
      if (agent.rightForearm) agent.rightForearm.rotation.x = Math.sin(time * sw * 0.8) * 0.3;

      // Footstep sparks
      if (Math.sin(time * sw) > 0.95) {
        const sg = new THREE.BufferGeometry();
        sg.setAttribute('position', new THREE.BufferAttribute(new Float32Array([grp.position.x + 0.1, 0.02, grp.position.z]), 3));
        const sp = new THREE.Points(sg, new THREE.PointsMaterial({ size: 0.03, color: agent.config.color, transparent: true, opacity: 0.6 }));
        window._sparkPool = window._sparkPool || [];
        sceneAdd(sp);
        setTimeout(() => {
          try { sceneRemove(sp); sp.geometry.dispose(); sp.material.dispose(); } catch (e) { }
        }, 200);
      }
    } else {
      // Reset all limbs
      [agent.leftLeg, agent.rightLeg, agent.leftArmUpper, agent.rightArmUpper, agent.leftForearm, agent.rightForearm].forEach(limb => {
        if (limb) limb.rotation.x = 0;
      });

      if (agent.status === 'standup') {
        grp.lookAt(0, grp.position.y, 0);
        if (agent.leftArmUpper) agent.leftArmUpper.rotation.x = 0.15;
        if (agent.rightArmUpper) agent.rightArmUpper.rotation.x = 0.15;
        if (agent.head) agent.head.rotation.y = Math.sin(time * 2 + (agent.key?.length || 0)) * 0.15;
      } else if (agent.status === 'active') {
        grp.lookAt(agent.config.deskPos.x, grp.position.y, agent.config.deskPos.z);
        const ta = 14 * speedMult;
        if (agent.leftArmUpper) {
          agent.leftArmUpper.rotation.x = 0.7 + Math.sin(time * ta) * 0.15;
          agent.leftArmUpper.rotation.z = Math.sin(time * ta) * 0.05;
        }
        if (agent.rightArmUpper) {
          agent.rightArmUpper.rotation.x = 0.7 + Math.cos(time * ta) * 0.15;
          agent.rightArmUpper.rotation.z = -Math.sin(time * ta) * 0.05;
        }
        if (agent.leftForearm) agent.leftForearm.rotation.x = -0.3 + Math.sin(time * ta) * 0.2;
        if (agent.rightForearm) agent.rightForearm.rotation.x = -0.3 + Math.cos(time * ta) * 0.2;
        if (agent.head) {
          const hw = new THREE.Vector3();
          agent.head.getWorldPosition(hw);
          agent.head.position.y = hw.y + Math.sin(time * 6) * 0.02;
        }
        // Finger wiggle
        grp.children.forEach(c => {
          if (c.userData.side === 'left' && c.userData.fingerIndex !== undefined) {
            c.position.y = 0.18 + Math.sin(time * 16 + c.userData.fingerIndex) * 0.01;
          }
          if (c.userData.side === 'right' && c.userData.fingerIndex !== undefined) {
            c.position.y = 0.18 + Math.cos(time * 16 + c.userData.fingerIndex) * 0.01;
          }
        });
      } else {
        // Sleeping
        if (agent.head) {
          const hw = new THREE.Vector3();
          agent.head.getWorldPosition(hw);
          agent.head.rotation.z = 0.15 + Math.sin(time * 0.8) * 0.05;
        }
        if (grp.children[0]) grp.children[0].scale.y = 1 + Math.sin(time * 0.8) * 0.03;
      }
    }
  }
}

// Helper to add to scene without importing — assumes THREE is global
function sceneAdd(obj) {
  if (window._sceneRef) window._sceneRef.add(obj);
}

function sceneRemove(obj) {
  if (window._sceneRef) window._sceneRef.remove(obj);
}
