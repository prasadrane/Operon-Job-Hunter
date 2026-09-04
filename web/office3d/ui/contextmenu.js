function createContextMenu(container) {
  const menu = document.createElement('div');
  menu.id = 'o3d-context-menu';
  menu.className = 'absolute z-50 bg-[#0d1322]/95 backdrop-blur-md rounded-lg border border-white/10 shadow-xl text-xs overflow-hidden hidden';
  container.appendChild(menu);

  // Close on outside click
  document.addEventListener('click', () => hide());

  return { menu };
}

function showContextMenu(ctxMenu, eventClientX, eventClientY, agentKey, agentsMap) {
  if (!ctxMenu.menu || !agentsMap[agentKey]) return;

  const agent = agentsMap[agentKey];
  ctxMenu.menu.classList.remove('hidden');
  ctxMenu.menu.style.left = eventClientX + 'px';
  ctxMenu.menu.style.top = eventClientY + 'px';

  ctxMenu.menu.innerHTML = `
    <button class="ctx-action w-full text-left px-3 py-2 hover:bg-white/5 text-slate-200" data-action="inspect">🔍 Inspect ${agent.config.name}</button>
    <button class="ctx-action w-full text-left px-3 py-2 hover:bg-white/5 text-slate-200" data-action="message">💬 Message Agent</button>
    <button class="ctx-action w-full text-left px-3 py-2 hover:bg-white/5 text-slate-200" data-action="assign">📋 Assign Task</button>
    <button class="ctx-action w-full text-left px-3 py-2 hover:bg-white/5 text-slate-200" data-action="focus">🎥 Focus Camera</button>
    <button class="ctx-action w-full text-left px-3 py-2 hover:bg-white/5 text-slate-200" data-action="wake">${agent.status === 'active' ? '💤 Sleep' : '⚡ Wake'} Agent</button>
  `;

  // Action handlers
  ctxMenu.menu.querySelectorAll('.ctx-action').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const action = btn.dataset.action;

      window._ctxDispatch?.(action, agentKey, agent);

      hide();
    });
  });
}

function hide() {
  const menu = document.getElementById('o3d-context-menu');
  if (menu) { menu.classList.add('hidden'); }
}
