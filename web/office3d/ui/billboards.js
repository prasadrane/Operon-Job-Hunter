// Hover tooltip — shows agent name/role/status when mouse enters agent mesh range
function initBillboards() {
  // Creates a persistent HTML overlay div that follows cursor
  const tip = document.createElement('div');
  tip.id = 'o3d-tooltip';
  tip.className = 'fixed pointer-events-none z-50 bg-[#0d1322]/90 backdrop-blur-sm rounded-lg border border-white/10 px-3 py-1.5 text-xs shadow-xl hidden';
  tip.style.left = '0px'; tip.style.top = '0px';
  document.body.appendChild(tip);

  return { tip };
}

function showHoverTooltip(billboardData, eventClientX, eventClientY) {
  if (!billboardData.tip) return;
  billboardData.tip.classList.remove('hidden');
  billboardData.tip.style.left = (eventClientX + 12) + 'px';
  billboardData.tip.style.top = (eventClientY - 30) + 'px';
  billboardData.tip.innerHTML = `
    <span style="color:#${billboardData.color.toString(16).padStart(6,'0')}">${billboardData.name}</span>
    — ${billboardData.role}<br>
    <span class="text-slate-400 text-[10px]">${billboardData.statusText}</span>
  `;
}

function hideHoverTooltip(billboardData) {
  if (!billboardData.tip) return;
  const old = document.getElementById('o3d-tooltip');
  if (old) old.remove();
  billboardData.tip = null;
}

// Mini-map canvas renderer for top-down office view
function renderMiniMap(canvas, agents, cameraControls) {
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  ctx.clearRect(0, 0, 128, 96);
  ctx.fillStyle = '#07090e'; ctx.fillRect(0, 0, 128, 96);

  // Grid lines
  ctx.strokeStyle = 'rgba(255,255,255,0.05)'; ctx.lineWidth = 0.5;
  for (let x = 0; x < 128; x += 16) { ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,96); ctx.stroke(); }
  for (let y = 0; y < 96; y += 16) { ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(128,y); ctx.stroke(); }

  // Zone color fills
  ctx.fillStyle = 'rgba(245,158,11,0.15)'; ctx.fillRect(52,4,24,24);        // boss zone
  ctx.fillStyle = 'rgba(6,182,212,0.15)'; ctx.fillRect(52,38,24,24);         // war room
  ctx.fillStyle = 'rgba(26,94,59,0.15)'; ctx.fillRect(52,68,24,24);          // lounge

  // Agent dots — position scaled to mini-map space
  const scale = 1.6, ox = 64, oz = 48;
  for (const [key, agent] of Object.entries(agents || {})) {
    const ax = ox + agent.group.position.x * scale;
    const az = oz + agent.group.position.z * scale;
    const color = '#' + (agent.config?.color || 0x3b82f6).toString(16).padStart(6, '0');
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(ax, az, agent.status === 'active' ? 3 : 2, 0, Math.PI*2);
    ctx.fill();
  }

  // Camera viewport indicator rectangle
  if (cameraControls) {
    const camX = 64 + cameraControls.getObject().position.x * scale * 0.5;
    const camZ = 48 + cameraControls.getObject().position.z * scale * 0.5;
    ctx.strokeStyle = '#38bdf8'; ctx.lineWidth = 1;
    ctx.strokeRect(camX - 4, camZ - 4, 8, 8);
  }
}
