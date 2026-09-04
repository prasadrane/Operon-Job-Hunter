/**
 * Office 3D — Status Orbs
 * Floating indicator orbs for each agent in the 5-stage pipeline.
 * Depends on global THREE namespace and window._sceneRef (the main scene).
 */

function createStatusOrbs(agentsMap) {
  const orbs = {}; // key -> { mesh, material }

  for (const [key, agent] of Object.entries(agentsMap)) {
    const orbGeo = new THREE.SphereGeometry(0.15, 8, 8);
    const orbMat = new THREE.MeshBasicMaterial({
      color: agent.config.color, transparent: true, opacity: 0.7,
      blending: THREE.AdditiveBlending
    });
    const orb = new THREE.Mesh(orbGeo, orbMat);
    orb.position.set(agent.group.position.x, agent.group.position.y + 3, agent.group.position.z);

    if (window._sceneRef) window._sceneRef.add(orb);

    orbs[key] = { mesh: orb, material: orbMat };
  }

  return orbs;
}

function updateOrbs(orbsData, agentsMap, time) {
  for (const [key, agent] of Object.entries(agentsMap)) {
    if (!orbsData[key]) continue;
    const orb = orbsData[key].mesh;
    const isActive = agent.status === 'active';
    orbsData[key].material.opacity = isActive ? 0.7 : 0.2;
    orb.visible = true;
    orb.position.y = agent.group.position.y + 2.8 + Math.sin(time * 2 + key.charCodeAt(0)) * 0.15;
  }

  // Hide orphan orbs
  for (const key of Object.keys(orbsData)) {
    if (!agentsMap[key]) orbsData[key].mesh.visible = false;
  }
}
