/**
 * sync.js — SSE subagent state bridge for Three.js agent movement and animation.
 *
 * Exported functions:
 *   updateAgentState(sceneRef, key, data, agentsMap, workstations, cameraControls)
 *   callStandup(agentsMap, dataRef)
 *   endStandup(dataRef)
 *   getStandupStatus(dataRef)
 */

/**
 * Update a single agent's visual state from SSE payload.
 * @param {THREE.Scene} sceneRef - Scene reference (reserved for raycasting if needed)
 * @param {string} key - Agent identifier matching a workstations entry
 * @param {object} data - SSE event payload: { status?, state_label?, current_task?, speech?, standup_active? }
 * @param {Map<string, object>} agentsMap - Map of agent objects keyed by their label
 * @param {Map<string, object>} workstations - Map of workstation descriptors keyed by same label
 * @param {any} cameraControls - Camera control instance (unused here, passed through for future use)
 */
function updateAgentState(sceneRef, key, data, agentsMap, workstations, cameraControls) {
  const agent = agentsMap[key];
  if (!agent || !agent.config) return;

  const cfg = agent.config;
  const ws = workstations[key];

  const rawStatus = (data.status || '').toLowerCase();
  const stateLabel = (data.state_label || '').toLowerCase();

  // --- Active vs sleeping ---
  const isSleeping =
    rawStatus === 'sleeping' ||
    rawStatus === 'dormant' ||
    rawStatus === 'standby' ||
    stateLabel.includes('sleep') ||
    stateLabel.includes('standby');

  const isActive = cfg.isBoss || (!isSleeping && (
    rawStatus === 'active' ||
    rawStatus === 'running' ||
    rawStatus === 'busy' ||
    Boolean(stateLabel)
  ));

  agent.status = isActive ? 'active' : 'sleeping';
  agent.currentTask = data.current_task !== undefined ? data.current_task : agent.currentTask;
  agent.speech = data.speech !== undefined ? data.speech : agent.speech;

  // --- Target position ---
  if (data.standup_active) {
    agent.targetPos = new THREE.Vector3(cfg.warRoomPos.x, cfg.warRoomPos.y, cfg.warRoomPos.z);
  } else if (isActive) {
    agent.targetPos = new THREE.Vector3(cfg.chairPos.x, cfg.chairPos.y, cfg.chairPos.z);
  } else {
    agent.targetPos = new THREE.Vector3(cfg.loungePos.x, cfg.loungePos.y, cfg.loungePos.z);
  }

  // --- Workstation monitor emissive glow ---
  if (ws && ws.monitors && Array.isArray(ws.monitors)) {
    for (let i = 0; i < ws.monitors.length; i++) {
      const mat = ws.monitors[i].material;
      if (mat) mat.emissiveIntensity = isActive ? 0.9 : 0.15;
    }
  }

  // --- Coffee mug visibility toggle on desk ---
  if (ws && ws.group && Array.isArray(ws.group.children)) {
    for (let i = 0; i < ws.group.children.length; i++) {
      const c = ws.group.children[i];
      if (c.userData && c.userData.isMug) c.visible = isActive;
    }
  }

  // --- Desk LED ring color pulse ---
  if (ws && ws.group && Array.isArray(ws.group.children)) {
    for (let i = 0; i < ws.group.children.length; i++) {
      const c = ws.group.children[i];
      if (c.geometry && c.geometry.type === 'TorusGeometry'
          && c.position.y > 0.8 && c.position.y < 1.0) {
        c.material.color.setHex(isActive ? cfg.color : 0x374151);
        if (c.material.opacity !== undefined) c.material.opacity = isActive ? 0.7 : 0.2;
      }
    }
  }
}

/**
 * Call standup — all agents move to the war-room table.
 * @param {Map<string, object>} agentsMap
 * @param {object} dataRef - Shared data object carrying _standupActive flag
 */
function callStandup(agentsMap, dataRef) {
  dataRef._standupActive = true;
  for (const agent of Object.values(agentsMap)) {
    if (agent.config) {
      agent.targetPos = new THREE.Vector3(
        agent.config.warRoomPos.x,
        agent.config.warRoomPos.y,
        agent.config.warRoomPos.z
      );
    }
  }
}

/**
 * End standup — clear the flag so agents disperse on the next update cycle.
 * @param {object} dataRef - Shared data object carrying _standupActive flag
 */
function endStandup(dataRef) {
  dataRef._standupActive = false;
}

/**
 * Query whether standup is currently active.
 * @param {object} dataRef
 * @returns {boolean}
 */
function getStandupStatus(dataRef) {
  return !!dataRef._standupActive;
}
