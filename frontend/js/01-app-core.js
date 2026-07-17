// Agentic OS v6.0 — Core app logic — state, nav, chat, agents, builder, kanban, swarm, galaxy, settings
// Extracted from index.html (block 0)


// ═══════════════════════════════════════════════════════════════
//  AGENTIC OS v6.0 — MISSION CONTROL CORE
// ═══════════════════════════════════════════════════════════════

// ── State ───────────────────────────────────────────────────────
var currentAgent = null, monacoEditor = null, diffEditor = null, agentModalId = null, studioMonacoLoaded = false;
const S = window.S || {
  agents: [], currentAgent: null,
  chatHistory: [],
  sessionId: 'session_' + Date.now(),
  useRag: true,
  useStream: true,
  currentFile: 'index.html',
  fileVersions: [], monacoEditor: null, diffEditor: null, gxGraph: null,
  paletteFocusIdx: 0,
  agentModalMode: 'create', agentModalId: null,
  selectedAvatar: '🤖',
  selectedColor: '#5b8af8',
};
window.S = S;

// ── Toast ────────────────────────────────────────────────────────
function toast(msg, type = 'ok', duration = 3000) {
  const c = document.getElementById('toast-container');
  if (!c) return;
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.innerHTML = `<span>${msg}</span><span class="toast-close" onclick="this.parentElement.remove()">×</span>`;
  c.appendChild(t);
  if (typeof requestAnimationFrame === 'function') requestAnimationFrame(() => t.classList.add('show'));
  else setTimeout(() => t.classList.add('show'), 16);
  setTimeout(() => { t.classList.remove('show'); setTimeout(() => t.remove(), 250); }, duration);
}

// ── Navigation & Sidebar Architecture ─────────────────────────────
window.toggleSidebar = function() {
  const sb = document.getElementById('sidebar');
  const btn = document.getElementById('sidebar-toggle-btn');
  if (!sb) return;
  const isCollapsed = sb.classList.toggle('collapsed');
  if (isCollapsed) {
    let currentW = parseInt(sb.style.width || '260', 10);
    if (isNaN(currentW) || currentW <= 60) currentW = 260;
    sb.dataset.savedWidth = currentW + 'px';
    sb.style.width = '56px';
    if (btn) btn.innerHTML = '▶';
  } else {
    let restoreW = parseInt(sb.dataset.savedWidth || '260', 10);
    if (isNaN(restoreW) || restoreW <= 60) restoreW = 260;
    sb.style.width = restoreW + 'px';
    if (btn) btn.innerHTML = '◀';
  }
  try { localStorage.setItem('agentic_os_sidebar_collapsed', isCollapsed ? 'true' : 'false'); } catch(e) {}
};

window.toggleSidebarGroup = function(groupId, forceOpen) {
  const content = document.getElementById('group-' + groupId);
  const arrow = document.getElementById('arrow-' + groupId);
  if (!content) return;
  
  let isOpen;
  if (typeof forceOpen === 'boolean') {
    isOpen = forceOpen;
  } else {
    isOpen = content.style.display === 'none';
  }
  
  content.style.display = isOpen ? '' : 'none';
  if (arrow) arrow.style.transform = isOpen ? 'rotate(90deg)' : 'rotate(0deg)';
  
  try { localStorage.setItem('agentic_os_group_' + groupId + '_open', isOpen ? 'true' : 'false'); } catch(e) {}
};

window.initSidebarGroups = function() {
  ['core', 'build', 'ship', 'tools', 'enterprise'].forEach(gid => {
    const saved = localStorage.getItem('agentic_os_group_' + gid + '_open');
    const isOpen = saved === 'true';
    const content = document.getElementById('group-' + gid);
    const arrow = document.getElementById('arrow-' + gid);
    if (content) content.style.display = isOpen ? '' : 'none';
    if (arrow) arrow.style.transform = isOpen ? 'rotate(90deg)' : 'rotate(0deg)';
  });
};

window.PANE_TO_GROUP = {
  'chat':'core', 'studio':'core', 'templates':'core', 'swarm':'core', 'galaxy':'core', 'hierarchy':'core', 'kanban':'core', 'settings':'core',
  'builder':'build', 'composer':'build', 'pipeline':'build', 'skills':'build', 'loops':'build', 'mcp':'build', 'fusion':'build', 'arena':'build', 'plugins':'build', 'terminal':'build', 'secrets':'build', 'finetune':'build',
  'github':'ship', 'deploy':'ship', 'dbstudio':'ship', 'dashboard':'ship', 'system':'ship', 'workspaces':'ship', 'control':'ship', 'supervisor':'ship', 'goals':'ship',
  'workflow':'tools', 'specs':'tools', 'steering':'tools', 'bugbot':'tools', 'gitai':'tools', 'marketplace':'tools', 'replay':'tools', 'collabedit':'tools', 'ambient':'tools', 'hitl':'tools', 'connectors':'tools', 'mcp-gateway':'tools', 'a2a':'tools', 'agent-identity':'tools',
  'audit-log':'enterprise', 'leaderboard':'enterprise', 'agent-monitor':'enterprise', 'finops':'enterprise', 'eval-framework':'enterprise', 'docs':'enterprise', 'websearch':'enterprise', 'browser':'enterprise', 'knowledge-graph':'enterprise', 'rag':'enterprise', 'hooks':'enterprise', 'codeindex':'enterprise', 'observability':'enterprise', 'evals':'enterprise', 'health':'enterprise', 'integrations':'enterprise', 'imagegen':'enterprise', 'prompts':'enterprise', 'codesearch':'enterprise', 'obsidian':'enterprise', 'pluginsdk':'enterprise', 'multitab':'enterprise', 'profiler':'enterprise', 'webhooks':'enterprise', 'testgen':'enterprise', 'pqc':'enterprise'
};

function setupSidebarResizer() {
  const resizer = document.getElementById('sidebar-resizer');
  const sb = document.getElementById('sidebar');
  if (!resizer || !sb) return;
  let isResizing = false;
  
  resizer.addEventListener('mousedown', (e) => {
    isResizing = true;
    sb.classList.add('resizing');
    resizer.classList.add('resizing');
    if (document.body) document.body.style.cursor = 'col-resize';
  });
  
  window.addEventListener('mousemove', (e) => {
    if (!isResizing) return;
    let newW = e.clientX;
    if (newW < 60) newW = 56;
    if (newW > 600) newW = 600;
    sb.style.width = newW + 'px';
    if (newW <= 56) sb.classList.add('collapsed');
    else sb.classList.remove('collapsed');
  });
  
  window.addEventListener('mouseup', () => {
    if (!isResizing) return;
    isResizing = false;
    sb.classList.remove('resizing');
    resizer.classList.remove('resizing');
    if (document.body) document.body.style.cursor = '';
    try { localStorage.setItem('agentic_os_sidebar_w', sb.style.width); } catch(e) {}
  });

  try {
    const savedW = localStorage.getItem('agentic_os_sidebar_w');
    const savedCol = localStorage.getItem('agentic_os_sidebar_collapsed') === 'true';
    if (savedCol) {
      sb.classList.add('collapsed');
      sb.style.width = '56px';
    } else if (savedW) {
      sb.style.width = savedW;
    }
  } catch(e) {}
}

window.MASTER_PANE_REGISTRY = {
  'chat':           () => {},
  'studio':         () => typeof window.initStudio === 'function' && window.initStudio(),
  'builder':        () => typeof window.initBuilder === 'function' && window.initBuilder(),
  'templates':      () => typeof window.renderTemplates === 'function' && window.renderTemplates(),
  'composer':       () => typeof window.renderComposer === 'function' && window.renderComposer(),
  'kanban':         () => typeof window.renderKanban === 'function' && window.renderKanban(),
  'swarm':          () => typeof window.renderSwarm === 'function' && window.renderSwarm(),
  'galaxy':         () => typeof window.initGalaxy === 'function' && window.initGalaxy(),
  'hierarchy':      () => typeof window.renderHierarchy === 'function' && window.renderHierarchy(),
  'settings':       () => typeof window.loadSettings === 'function' && window.loadSettings(),
  'dashboard':      () => typeof window.renderDashboard === 'function' && window.renderDashboard(),
  'skills':         () => typeof window.renderSkills === 'function' && window.renderSkills(),
  'deploy':         () => typeof window.renderDeploy === 'function' && window.renderDeploy(),
  'pipeline':       () => typeof window.renderPipeline === 'function' && window.renderPipeline(),
  'obsidian':       () => typeof window.renderObsidian === 'function' && window.renderObsidian(),
  'system':         () => typeof window.renderSystem === 'function' && window.renderSystem(),
  'workspaces':     () => typeof window.renderWorkspaces === 'function' && window.renderWorkspaces(),
  'mcp':            () => typeof window.renderMCP === 'function' && window.renderMCP(),
  'loops':          () => typeof window.renderLoops === 'function' && window.renderLoops(),
  'github':         () => typeof window.renderGitHub === 'function' && window.renderGitHub(),
  'dbstudio':       () => typeof window.renderDBStudio === 'function' && window.renderDBStudio(),
  'plugins':        () => typeof window.renderPlugins === 'function' && window.renderPlugins(),
  'control':        () => typeof window.renderControlTower === 'function' && window.renderControlTower(),
  'webhooks':       () => typeof window.renderWebhooks === 'function' && window.renderWebhooks(),
  'testgen':        () => typeof window.renderTestGen === 'function' && window.renderTestGen(),
  'terminal':       () => typeof window.renderTerminal === 'function' && window.renderTerminal(),
  'secrets':        () => typeof window.renderSecretsVault === 'function' && window.renderSecretsVault(),
  'integrations':   () => typeof window.renderIntegrations === 'function' && window.renderIntegrations(),
  'imagegen':       () => typeof window.renderImageGen === 'function' && window.renderImageGen(),
  'prompts':        () => typeof window.renderPrompts === 'function' && window.renderPrompts(),
  'codesearch':     () => typeof window.renderCodeSearch === 'function' && window.renderCodeSearch(),
  'workflow':       () => typeof window.renderWorkflow === 'function' && window.renderWorkflow(),
  'profiler':       () => typeof window.renderProfiler === 'function' && window.renderProfiler(),
  'pluginsdk':      () => typeof window.renderPluginSDK === 'function' && window.renderPluginSDK(),
  'multitab':       () => typeof window.renderMultitab === 'function' && window.renderMultitab(),
  'specs':          () => typeof window.renderSpecs === 'function' && window.renderSpecs(),
  'hooks':          () => typeof window.renderHooks === 'function' && window.renderHooks(),
  'codeindex':      () => typeof window.renderCodeIndex === 'function' && window.renderCodeIndex(),
  'arena':          () => typeof window.renderArena === 'function' && window.renderArena(),
  'steering':       () => typeof window.renderSteering === 'function' && window.renderSteering(),
  'bugbot':         () => typeof window.renderBugBot === 'function' && window.renderBugBot(),
  'health':         () => typeof window.renderHealth === 'function' && window.renderHealth(),
  'gitai':          () => typeof window.renderGitAI === 'function' && window.renderGitAI(),
  'ambient':        () => typeof window.renderAmbient === 'function' && window.renderAmbient(),
  'fusion':         () => typeof window.renderFusion === 'function' && window.renderFusion(),
  'hitl':           () => typeof window.renderHITL === 'function' && window.renderHITL(),
  'browser':        () => typeof window.renderBrowserAgent === 'function' && window.renderBrowserAgent(),
  'websearch':      () => typeof window.renderWebSearch === 'function' && window.renderWebSearch(),
  'leaderboard':    () => typeof window.renderLeaderboard === 'function' && window.renderLeaderboard(),
  'audit-log':      () => typeof window.renderAuditLog === 'function' && window.renderAuditLog(),
  'agent-identity': () => typeof window.renderAgentIdentity === 'function' && window.renderAgentIdentity(),
  'supervisor':     () => typeof window.renderSupervisor === 'function' && window.renderSupervisor(),
  'goals':          () => typeof window.renderGoals === 'function' && window.renderGoals(),
  'mcp-gateway':    () => typeof window.renderMCPGateway === 'function' && window.renderMCPGateway(),
  'connectors':     () => typeof window.renderConnectors === 'function' && window.renderConnectors(),
  'a2a':            () => typeof window.renderA2A === 'function' && window.renderA2A(),
  'agent-monitor':  () => typeof window.renderAgentMonitor === 'function' && window.renderAgentMonitor(),
  'finops':         () => typeof window.renderFinOps === 'function' && window.renderFinOps(),
  'eval-framework': () => typeof window.renderEvalFramework === 'function' && window.renderEvalFramework(),
  'docs':           () => typeof window.renderDocs === 'function' && window.renderDocs(),
  'evals':          () => typeof window.renderEvals === 'function' && window.renderEvals(),
  'observability':  () => typeof window.renderObservability === 'function' && window.renderObservability(),
  'knowledge-graph':() => typeof window.renderKnowledgeGraph === 'function' && window.renderKnowledgeGraph(),
  'rag':            () => typeof window.renderRAG === 'function' && window.renderRAG(),
  'replay':         () => typeof window.renderReplay === 'function' && window.renderReplay(),
  'collabedit':     () => typeof window.renderCollabEdit === 'function' && window.renderCollabEdit(),
  'marketplace':    () => typeof window.renderMarketplace === 'function' && window.renderMarketplace(),
  'pqc':            () => typeof window.renderPQCVault === 'function' && window.renderPQCVault(),
  'finetune':       () => typeof window.renderFinetuneWorkstation === 'function' && window.renderFinetuneWorkstation(),
};

window.nav = function(pane) {
  if (!pane) return;
  document.querySelectorAll('.pane').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  
  let el = document.getElementById('pane-' + pane);
  if (!el) {
    el = document.createElement('div');
    el.className = 'pane';
    el.id = 'pane-' + pane;
    el.style.cssText = 'overflow:auto;padding:20px;background:var(--bg-0);flex:1';
    el.innerHTML = `<div style="flex:1;display:flex;flex-direction:column"><div style="padding:24px;color:var(--text-2)">⚡ Initializing ${escHtml(pane)} component...</div></div>`;
    const content = document.getElementById('content');
    if (content) content.appendChild(el);
  }
  el.classList.add('active');
  
  const navEl = document.querySelector(`[data-nav="${pane}"]`);
  if (navEl) navEl.classList.add('active');

  const gid = window.PANE_TO_GROUP?.[pane];
  if (gid && typeof window.toggleSidebarGroup === 'function') {
    window.toggleSidebarGroup(gid, true);
  }

  const renderer = window.MASTER_PANE_REGISTRY[pane];
  if (renderer) {
    try { renderer(); } catch(e) { console.warn('Master renderer error for ' + pane + ':', e); }
  }

  if (typeof window.showSmartSuggestionsForPane === 'function') {
    try { window.showSmartSuggestionsForPane(pane); } catch(e) {}
  }

  try { history.replaceState(null, '', '#/' + pane); } catch(e) {}
};

// ── Agents ───────────────────────────────────────────────────────
async function loadAgents() {
  try {
    const r = await fetch('/api/agents');
    const data = await r.json();
    S.agents = Array.isArray(data) ? data : (data.agents || []);
    renderAgentList();
    if (!S.currentAgent && S.agents.length) setActiveAgent(S.agents[0]);
    updateStatusBar();
  } catch(e) { console.warn('Agents load failed:', e); }
}

function renderAgentList() {
  const el = document.getElementById('agent-list');
  if (!el) return;
  el.innerHTML = S.agents.map(a => `
    <div class="agent-row ${S.currentAgent?.id === a.id ? 'active-agent' : ''}"
         onclick="setActiveAgent(${JSON.stringify(a).replace(/"/g,'&quot;')})"
         ondblclick="openAgentModal(${JSON.stringify(a.id)})">
      <div class="agent-avatar" style="background:${a.color}22;border:1px solid ${a.color}44">
        <span>${a.avatar || '🤖'}</span>
      </div>
      <div class="agent-info">
        <div class="agent-name">${escHtml(a.name)}</div>
        <div class="agent-role">${escHtml(a.role || a.model || '')}</div>
      </div>
      <div class="agent-status ${a.status || 'idle'}"></div>
    </div>
  `).join('');

  // also update settings agents list
  const sl = document.getElementById('settings-agents-list');
  if (sl) {
    sl.innerHTML = S.agents.map(a => `
      <div style="display:flex;align-items:center;gap:10px;background:var(--bg-3);border-radius:var(--radius-sm);padding:8px 12px;">
        <span style="font-size:18px">${a.avatar||'🤖'}</span>
        <div style="flex:1">
          <div style="font-weight:600;font-size:13px">${escHtml(a.name)}</div>
          <div style="font-size:11px;color:var(--text-2)">${escHtml(a.role||'')} • ${a.model||'default'}</div>
        </div>
        <button onclick="openAgentModal(${JSON.stringify(a.id)})" class="btn btn-ghost btn-sm">Edit</button>
      </div>
    `).join('');
  }
}

function setActiveAgent(agent) {
  S.currentAgent = agent;
  document.getElementById('active-agent-avatar').textContent = agent.avatar || '🤖';
  document.getElementById('active-agent-name').textContent = agent.name;
  document.getElementById('active-agent-dot').style.background =
    agent.status === 'working' ? 'var(--yellow)' :
    agent.status === 'active'  ? 'var(--green)' : 'var(--text-3)';
  document.getElementById('active-model-badge').textContent = agent.model || 'default';
  renderAgentList();
}

function showAgentPicker() {
  const items = S.agents.map(a =>
    `<div class="palette-item" onclick="setActiveAgent(${JSON.stringify(a).replace(/"/g,'&quot;')});closePalette()">
      <span class="p-icon">${a.avatar||'🤖'}</span>
      <span class="p-label">${escHtml(a.name)}</span>
      <span class="p-desc">${escHtml(a.model||'')}</span>
    </div>`
  ).join('');
  document.getElementById('palette-results').innerHTML =
    `<div class="palette-section">Select Agent</div>${items}`;
  openPalette();
}

// ── Agent Modal ───────────────────────────────────────────────────
function openAgentModal(agentId = null) {
  S.agentModalMode  = agentId ? 'edit' : 'create';
  S.agentModalId    = agentId;
  S.selectedAvatar  = '🤖';
  S.selectedColor   = '#5b8af8';

  const modal = document.getElementById('agent-modal');
  modal.style.display = 'flex';

  document.getElementById('agent-modal-title').textContent =
    agentId ? '✏️ Edit Agent' : '🤖 Create Agent';
  document.getElementById('am-save-btn').textContent =
    agentId ? 'Save Changes' : 'Create Agent';

  const delBtn = document.getElementById('am-delete-btn');
  delBtn.style.display = agentId ? 'inline-flex' : 'none';

  if (agentId) {
    const a = S.agents.find(x => x.id === agentId);
    if (a) {
      document.getElementById('am-name').value    = a.name || '';
      document.getElementById('am-role').value    = a.role || '';
      document.getElementById('am-model').value   = a.model || 'claude';
      document.getElementById('am-provider').value = a.provider || 'openrouter';
      document.getElementById('am-system').value  = a.system_prompt || '';
      S.selectedAvatar = a.avatar || '🤖';
      S.selectedColor  = a.color  || '#5b8af8';
    }
  } else {
    ['am-name','am-role','am-system'].forEach(id => document.getElementById(id).value = '');
    document.getElementById('am-model').value    = 'claude';
    document.getElementById('am-provider').value = 'openrouter';
  }

  // update pickers
  document.querySelectorAll('.avatar-opt').forEach(el => {
    el.classList.toggle('selected', el.dataset.avatar === S.selectedAvatar);
  });
  document.querySelectorAll('.color-swatch').forEach(el => {
    el.classList.toggle('selected', el.dataset.color === S.selectedColor);
  });
}

function closeAgentModal() {
  document.getElementById('agent-modal').style.display = 'none';
}

async function saveAgent() {
  const name = document.getElementById('am-name').value.trim();
  if (!name) { toast('Name is required', 'err'); return; }

  const data = {
    name,
    role:          document.getElementById('am-role').value.trim(),
    model:         document.getElementById('am-model').value,
    provider:      document.getElementById('am-provider').value,
    avatar:        S.selectedAvatar,
    color:         S.selectedColor,
    system_prompt: document.getElementById('am-system').value.trim(),
  };

  const url    = S.agentModalMode === 'edit' ? `/api/agents/${S.agentModalId}` : '/api/agents';
  const method = S.agentModalMode === 'edit' ? 'PATCH' : 'POST';

  const r = await fetch(url, { method, headers: {'Content-Type':'application/json'}, body: JSON.stringify(data) });
  const j = await r.json();

  if (j.ok) {
    toast(S.agentModalMode === 'edit' ? `✅ ${name} updated` : `✅ ${name} created`, 'ok');
    closeAgentModal();
    loadAgents();
  } else {
    toast('Error: ' + (j.error || 'unknown'), 'err');
  }
}

async function deleteCurrentAgent() {
  if (!S.agentModalId) return;
  const a = S.agents.find(x => x.id === S.agentModalId);
  if (!(await gmDanger(`Delete Agent`, `Delete "${a?.name}"? This cannot be undone.`))) return;
  const r = await fetch(`/api/agents/${encodeURIComponent(S.agentModalId)}`, { method: 'DELETE' });
  const j = await r.json();
  if (j.ok) {
    toast(`🗑 Agent deleted`, 'ok');
    closeAgentModal();
    loadAgents();
  } else {
    toast('Error: ' + (j.error || 'unknown'), 'err');
  }
}

// Avatar + color pickers
document.addEventListener('click', e => {
  if (e.target.closest('.avatar-opt')) {
    const el = e.target.closest('.avatar-opt');
    document.querySelectorAll('.avatar-opt').forEach(x => x.classList.remove('selected'));
    el.classList.add('selected');
    S.selectedAvatar = el.dataset.avatar;
  }
  if (e.target.closest('.color-swatch')) {
    const el = e.target.closest('.color-swatch');
    document.querySelectorAll('.color-swatch').forEach(x => x.classList.remove('selected'));
    el.classList.add('selected');
    S.selectedColor = el.dataset.color;
  }
});

// ── Chat ─────────────────────────────────────────────────────────
function insertCmd(cmd) {
  if (typeof nav === 'function') nav('chat');
  setTimeout(() => {
    const el = document.getElementById('chat-input');
    if (el) {
      el.value = cmd;
      el.focus();
      hideChatEmpty();
    }
  }, 20);
}
window.insertCmd = insertCmd;

function hideChatEmpty() {
  const e = document.getElementById('chat-empty');
  if (e) e.style.display = 'none';
}

function toggleRag() {
  S.useRag = !S.useRag;
  document.getElementById('rag-btn').classList.toggle('active', S.useRag);
  toast(S.useRag ? '🌌 RAG ON' : 'RAG OFF', 'ok', 1500);
}

function toggleStream() {
  S.useStream = !S.useStream;
  document.getElementById('stream-btn').classList.toggle('active', S.useStream);
}

function clearChatHistory() {
  S.chatHistory = [];
  document.getElementById('chat-messages').innerHTML = '';
  const e = document.getElementById('chat-empty');
  if (e) e.style.display = 'flex';
  toast('Chat cleared', 'ok', 1500);
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  const msg   = input.value.trim();
  if (!msg) return;
  hideChatEmpty();
  input.value = '';
  autoResizeInput(input);

  // Getting Started checklist hook
  if (window.markChecklistStep) markChecklistStep('first_chat');

  const agent = S.currentAgent || { id: 'brain', name: 'Brain', avatar: '🧠' };

  // Render user bubble
  addMessage(msg, 'user', '👤', 'You');

  S.chatHistory.push({ role: 'user', content: msg });

  // Thinking indicator
  const thinkingId = 'thinking_' + Date.now();
  addThinking(thinkingId, agent);

  document.getElementById('chat-send').disabled = true;

  let fullText = '';
  let bubbleEl = null;

  try {
    const resp = await fetch('/api/chat', {
      method:  'POST',
      headers: {'Content-Type':'application/json'},
      body:    JSON.stringify({
        message:    msg,
        agent_id:   agent.id,
        session_id: S.sessionId,
        history:    S.chatHistory.slice(-20),
      }),
    });

    // Remove thinking
    document.getElementById(thinkingId)?.remove();

    // Stream response
    bubbleEl = addMessage('', 'agent', agent.avatar || '🤖', agent.name);

    const reader  = resp.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const text  = decoder.decode(value, { stream: true });
      const lines = text.split('\n');
      for (const line of lines) {
        if (!line.startsWith('data:')) continue;
        try {
          const data = JSON.parse(line.slice(5).trim());
          if (data.delta) {
            fullText += data.delta;
            updateMessageBubble(bubbleEl, fullText);
          }
          if (data.action === 'clear_history') {
            clearChatHistory();
          }
        } catch(e) {}
      }
    }

    S.chatHistory.push({ role: 'assistant', content: fullText });

  } catch(err) {
    document.getElementById(thinkingId)?.remove();
    if (bubbleEl) {
      updateMessageBubble(bubbleEl, `❌ Error: ${err.message}\n\nMake sure Agentic OS backend is running.`);
    } else {
      addMessage(`❌ Error: ${err.message}`, 'agent', '⚠️', 'System');
    }
  } finally {
    document.getElementById('chat-send').disabled = false;
    input.focus();
    updateCostBar();
  }
}

function addMessage(content, role, avatar, name) {
  const msgs  = document.getElementById('chat-messages');
  const div   = document.createElement('div');
  div.className = `msg ${role}`;
  div.innerHTML = `
    <div class="msg-avatar">${avatar}</div>
    <div class="msg-body">
      <div class="msg-meta">${escHtml(name)} · ${new Date().toLocaleTimeString()}</div>
      <div class="msg-bubble">${role === 'user' ? escHtml(content) : renderMarkdown(content)}</div>
    </div>`;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  return div.querySelector('.msg-bubble');
}

function addThinking(id, agent) {
  const msgs = document.getElementById('chat-messages');
  const div  = document.createElement('div');
  div.id = id;
  div.className = 'msg agent';
  div.innerHTML = `
    <div class="msg-avatar">${agent.avatar || '🤖'}</div>
    <div class="msg-body">
      <div class="msg-meta">${escHtml(agent.name)} · thinking…</div>
      <div class="typing-indicator">
        <div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>
      </div>
    </div>`;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function updateMessageBubble(el, text) {
  if (!el) return;
  el.innerHTML = renderMarkdown(text);
  el.closest('.msg')?.parentElement?.scrollTo({ top: el.closest('.msg')?.parentElement?.scrollHeight, behavior: 'smooth' });
}

function renderMarkdown(text) {
  if (!text) return '';
  let t = escHtml(text);
  // code blocks
  t = t.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) =>
    `<pre><code class="lang-${lang}">${code}</code></pre>`);
  // inline code
  t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
  // bold
  t = t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // italic
  t = t.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // headers
  t = t.replace(/^### (.+)$/gm, '<h3 style="font-size:14px;font-weight:700;margin:8px 0 4px">$1</h3>');
  t = t.replace(/^## (.+)$/gm,  '<h2 style="font-size:15px;font-weight:800;margin:10px 0 5px">$1</h2>');
  t = t.replace(/^# (.+)$/gm,   '<h1 style="font-size:17px;font-weight:900;margin:12px 0 6px">$1</h1>');
  // lists
  t = t.replace(/^[-•] (.+)$/gm, '<div style="padding-left:12px">• $1</div>');
  t = t.replace(/^\d+\. (.+)$/gm, (m, p) => `<div style="padding-left:12px">${m}</div>`);
  // line breaks
  t = t.replace(/\n/g, '<br>');
  return t;
}

// ── Builder ───────────────────────────────────────────────────────
let monacoLoaded = false;
function initBuilder() {
  loadFileTree();
  if (!monacoLoaded) loadMonaco();
}

function loadMonaco() {
  if (window.monaco) { setupMonaco(); return; }
  const script = document.createElement('script');
  script.src = 'https://cdn.jsdelivr.net/npm/monaco-editor@0.47.0/min/vs/loader.js';
  script.onload = () => {
    require.config({ paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.47.0/min/vs' }});
    require(['vs/editor/editor.main'], setupMonaco);
  };
  document.head.appendChild(script);
}

function setupMonaco() {
  monacoLoaded = true;
  monaco.editor.defineTheme('agentic', {
    base: 'vs-dark',
    inherit: true,
    rules: [
      { token: '', foreground: 'c9d1d9', background: '08090e' },
      { token: 'comment', foreground: '6b7ca5', fontStyle: 'italic' },
      { token: 'keyword', foreground: '7aa4ff' },
      { token: 'string', foreground: '9ece6a' },
      { token: 'number', foreground: 'f08850' },
    ],
    colors: {
      'editor.background': '#08090e',
      'editor.foreground': '#c9d1d9',
      'editorLineNumber.foreground': '#3d4868',
      'editorCursor.foreground': '#5b8af8',
      'editor.selectionBackground': '#1a2e5088',
      'editorIndentGuide.background': '#1a1f35',
      'editorLineNumber.activeForeground': '#7a8aaa',
    }
  });
  S.monacoEditor = monaco.editor.create(document.getElementById('monaco-host'), {
    theme: 'agentic',
    fontSize: 14,
    fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', ui-monospace, monospace",
    fontLigatures: true,
    lineHeight: 22,
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    wordWrap: 'on',
    padding: { top: 16 },
    automaticLayout: true,
    smoothScrolling: true,
    cursorBlinking: 'smooth',
    renderLineHighlight: 'line',
  });
  if (S.monacoEditor && typeof S.monacoEditor.onDidChangeCursorPosition === 'function') {
    S.monacoEditor.onDidChangeCursorPosition(e => {
      const p = e.position;
      const cur = document.getElementById('ed-cursor');
      if (cur) cur.textContent = `Ln ${p.lineNumber}, Col ${p.column}`;
    });
  }
  if (S.monacoEditor && typeof S.monacoEditor.addCommand === 'function' && window.monaco?.KeyMod && window.monaco?.KeyCode) {
    S.monacoEditor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, saveFile);
  }
  openFile(S.currentFile);
}

async function loadFileTree() {
  try {
    const r = await fetch('/api/preview/files');
    const files = await r.json();
    const el = document.getElementById('file-tree');
    if (!el) return;
    if (!files.length) {
      el.innerHTML = `<div style="color:var(--text-3);font-size:12px;padding:16px;text-align:center">
        No files yet. Scaffold a project →</div>`;
      return;
    }
    el.innerHTML = files.map(f => {
      const ext = f.path.split('.').pop() || 'txt';
      const name = f.path.split('/').pop();
      return `<div class="file-row ${f.path===S.currentFile?'active':''}" onclick="openFile('${f.path}')">
        <span class="file-ext">${ext}</span>
        <span style="flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${f.path}">${name}</span>
        <span style="font-size:10px;color:var(--text-3)">${formatBytes(f.size)}</span>
      </div>`;
    }).join('') + `<div class="new-file-btn" onclick="openNewFileModal()">＋ New file</div>`;
  } catch(e) { console.warn('File tree failed:', e); }
}

async function openFile(path) {
  if (!path || typeof path !== 'string') return;
  S.currentFile = path;
  const edFile = document.getElementById('ed-file'); if (edFile) edFile.textContent = path;
  if (!S.monacoEditor) return;
  try {
    const r    = await fetch('/api/preview/read?path=' + encodeURIComponent(path));
    const text = await r.text();
    const ext  = path.split('.').pop();
    const lang = {html:'html',css:'css',js:'javascript',jsx:'javascript',
                  ts:'typescript',tsx:'typescript',json:'json',md:'markdown',
                  py:'python',svelte:'html'}[ext] || 'plaintext';
    const model = monaco.editor.createModel(text, lang);
    S.monacoEditor.setModel(model);
    document.getElementById('ed-lang').textContent = lang;
    // load version count
    const hr = await fetch('/api/preview/history?path=' + encodeURIComponent(path));
    const hist = await hr.json();
    document.getElementById('ed-versions').textContent = `${hist.length} versions`;
    S.fileVersions = hist;
    // update diff dropdown
    const sel = document.getElementById('diff-version-sel');
    if (sel) {
      sel.innerHTML = '<option value="">Select version…</option>' +
        hist.map(v => `<option value="${v.id}">v${v.id} — ${v.ts} — ${v.author}</option>`).join('');
    }
    // highlight in file tree
    document.querySelectorAll('.file-row').forEach(r =>
      r.classList.toggle('active', r.textContent.trim().startsWith(path.split('/').pop())));
  } catch(e) { console.warn('openFile error:', e); }
}

async function saveFile() {
  if (!S.monacoEditor) { toast('Editor not loaded', 'warn'); return; }
  const content = S.monacoEditor.getValue();
  const r = await fetch('/api/preview/save', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ path: S.currentFile, content, author: 'user', message: 'save' })
  });
  const j = await r.json();
  if (j.ok) {
    toast(`💾 Saved — ${j.versions} versions`, 'ok', 1500);
    document.getElementById('ed-versions').textContent = `${j.versions} versions`;
  } else {
    toast('Save failed', 'err');
  }
}

async function commitFile() {
  const r = await fetch('/api/preview/commit', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ path: S.currentFile, author: 'user', message: 'manual checkpoint' })
  });
  const j = await r.json();
  if (j.ok) toast(`📸 Committed v${j.version_id}`, 'ok');
}

function switchBuilderTab(tab) {
  document.querySelectorAll('.builder-tab').forEach(t => t.classList.toggle('active', t.dataset.btab === tab));
  ['editor','preview','diff'].forEach(t => {
    const el = document.getElementById('btab-' + t);
    if (el) el.style.display = t === tab ? 'flex' : 'none';
  });
  if (tab === 'preview') reloadPreview();
  if (tab === 'diff') loadDiffVersions();
}

function reloadPreview() {
  const frame = document.getElementById('preview-frame');
  const src   = document.getElementById('preview-target')?.value || '/preview/index.html';
  frame.src   = src + '?t=' + Date.now();
}

function openPreviewBlank() {
  const src = document.getElementById('preview-target')?.value || '/preview/index.html';
  window.open(src, '_blank');
}

async function loadDiffVersions() {
  if (!S.fileVersions.length && S.currentFile) {
    const r = await fetch('/api/preview/history?path=' + encodeURIComponent(S.currentFile));
    S.fileVersions = await r.json();
    const sel = document.getElementById('diff-version-sel');
    if (sel) {
      sel.innerHTML = '<option value="">Select version…</option>' +
        S.fileVersions.map(v => `<option value="${v.id}">v${v.id} — ${v.ts}</option>`).join('');
    }
  }
}

async function loadDiff() {
  const vid = document.getElementById('diff-version-sel')?.value;
  if (!vid) { toast('Select a version first', 'warn'); return; }
  if (!window.monaco) { toast('Monaco not loaded', 'warn'); return; }

  const [verR, curR] = await Promise.all([
    fetch('/api/preview/version?id=' + vid),
    fetch('/api/preview/read?path=' + encodeURIComponent(S.currentFile))
  ]);
  const ver = await verR.json();
  const cur = await curR.text();

  const host = document.getElementById('diff-host');
  if (S.diffEditor) { S.diffEditor.dispose(); S.diffEditor = null; }
  S.diffEditor = monaco.editor.createDiffEditor(host, {
    theme: 'agentic', readOnly: true, automaticLayout: true, renderSideBySide: true,
  });
  S.diffEditor.setModel({
    original: monaco.editor.createModel(ver.content || '', 'html'),
    modified: monaco.editor.createModel(cur, 'html'),
  });
}

async function restoreVersion() {
  const vid = document.getElementById('diff-version-sel')?.value;
  if (!vid) { toast('Select a version first', 'warn'); return; }
  if (!(await gmDanger('Restore Version', 'Overwrite current file with this version? This cannot be undone.', 'Restore'))) return;
  const r = await fetch('/api/preview/restore', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ version_id: parseInt(vid) })
  });
  const j = await r.json();
  if (j.ok) { toast('↶ Restored!', 'ok'); openFile(S.currentFile); switchBuilderTab('editor'); }
  else toast('Restore failed', 'err');
}

async function openNewFileModal() {
  const name = await gmPrompt('New File', 'e.g. about.html, styles.css');
  if (!name) return;
  fetch('/api/preview/new', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ path: name, content: '' })
  }).then(r => r.json()).then(j => {
    if (j.ok) { toast(`✅ Created ${name}`, 'ok'); loadFileTree(); openFile(name); }
    else toast('Error: ' + (j.error || ''), 'err');
  });
}

async function runScaffold() {
  const fw     = document.getElementById('scaffold-fw').value;
  const prompt = document.getElementById('scaffold-prompt').value.trim() || fw;
  toast('⚡ Scaffolding ' + fw + '…', 'ok');
  const r = await fetch('/api/preview/scaffold', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ framework: fw, prompt })
  });
  const j = await r.json();
  if (j.ok) {
    toast(`✅ ${j.message}`, 'ok', 4000);
    loadFileTree();
    if (j.files?.length) openFile(j.files[0]);
  } else {
    toast('Scaffold failed', 'err');
  }
}

// ── Kanban ────────────────────────────────────────────────────────
async function renderKanban() {
  const pane = document.getElementById('pane-kanban');
  pane.innerHTML = `<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-shrink:0">
    <div><div style="font-size:17px;font-weight:800">📋 Kanban</div><div style="font-size:13px;color:var(--text-2)">Drag tasks to update status</div></div>
    <button onclick="openNewTaskModal()" class="btn btn-primary btn-sm">＋ Task</button>
  </div>
  <div id="kb-board" style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;flex:1;overflow:hidden"></div>`;

  try {
    const r    = await fetch('/api/kanban');
    const data = await r.json();
    const COLS = [
      {id:'todo',    label:'📋 To Do',   color:'#5b8af8'},
      {id:'doing',   label:'⚡ Doing',   color:'#f0c060'},
      {id:'blocked', label:'⛔ Blocked', color:'#f06080'},
      {id:'done',    label:'✅ Done',    color:'#4cc98a'},
    ];
    document.getElementById('kb-board').innerHTML = COLS.map(col => `
      <div class="kb-col" data-col="${col.id}" ondragover="event.preventDefault()" ondrop="kbDrop(event,'${col.id}')">
        <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 12px;border-bottom:1px solid var(--border);font-weight:700;font-size:13px">
          <span>${col.label}</span>
          <span style="font-size:11px;background:var(--bg-3);padding:1px 7px;border-radius:99px;color:var(--text-2)">${(data[col.id]||[]).length}</span>
        </div>
        <div class="kb-drop" id="kbcol-${col.id}" style="padding:10px;min-height:200px;overflow-y:auto;max-height:calc(100vh - 300px)">
          ${(data[col.id]||[]).map(t => kbCard(t)).join('')}
        </div>
      </div>`).join('');
  } catch(e) {
    document.getElementById('kb-board').innerHTML = `<div style="color:var(--text-2);padding:20px">Failed to load Kanban</div>`;
  }
}

function kbCard(t) {
  const priColor = {high:'#f06080',medium:'#f0c060',low:'#7a8aaa'}[t.priority]||'#7a8aaa';
  return `<div class="kb-card" draggable="true" data-id="${t.id}"
    ondragstart="kbDragStart(event,${t.id})" style="margin-bottom:10px;cursor:grab">
    <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;font-size:11px;color:var(--text-2)">
      <span style="width:7px;height:7px;border-radius:50%;background:${priColor};flex-shrink:0"></span>
      <span style="background:var(--bg-3);padding:1px 7px;border-radius:99px;font-size:10.5px">${t.agent||'—'}</span>
      <span style="margin-left:auto;color:var(--text-3);font-size:10px">${t.layer||''}</span>
    </div>
    <div style="font-weight:600;font-size:13px;margin-bottom:6px">${escHtml(t.title)}</div>
    ${t.description ? `<div style="font-size:11.5px;color:var(--text-2);margin-bottom:6px;max-height:36px;overflow:hidden">${escHtml(t.description)}</div>` : ''}
    <div style="display:flex;gap:6px;opacity:0.7">
      <button onclick="deleteTask(${JSON.stringify(t.id)})" style="font-size:10px;background:none;border:none;color:var(--red);cursor:pointer">🗑</button>
    </div>
  </div>`;
}

let kbDragging = null;
function kbDragStart(e, id) { kbDragging = id; e.dataTransfer.effectAllowed = 'move'; }
async function kbDrop(e, status) {
  e.preventDefault();
  if (!kbDragging) return;
  await fetch(`/api/tasks/${encodeURIComponent(kbDragging)}`, {
    method:'PATCH', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({status})
  });
  kbDragging = null;
  renderKanban();
}

async function deleteTask(id) {
  if (!(await gmDanger('Delete Task', 'This task will be permanently removed.'))) return;
  await fetch(`/api/tasks/${encodeURIComponent(id)}`, {method:'DELETE'});
  toast('🗑 Task deleted','ok',1500);
  renderKanban();
}

async function openNewTaskModal() {
  const title = await gmPrompt('New Task', 'What needs to be done?');
  if (!title) return;
  const agent = await gmPrompt('Assign to agent', 'e.g. builder, brain, researcher', 'builder') || 'builder';
  fetch('/api/tasks', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({title, agent, status:'todo', priority:'medium'})
  }).then(r=>r.ok?r.json():null).then(j => {
    if (j?.ok) { toast('✅ Task created','ok'); renderKanban(); }
  }).catch(()=>{});
}

// ── Swarm ─────────────────────────────────────────────────────────
function renderSwarm() {
  const pane = document.getElementById('pane-swarm');
  pane.innerHTML = `
    <div class="section-head">
      <div><h2>🌀 Multi-Agent Swarm</h2><p>Fan-out to multiple agents in parallel • judge picks best • optionally merges top-2</p></div>
      <button onclick="loadSwarmHistory()" class="btn btn-ghost btn-sm">📜 History</button>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;flex:1">
      <div>
        <div class="settings-card">
          <h3>Swarm Prompt</h3>
          <textarea id="sw-prompt" placeholder="Write a marketing copy for an AI SaaS that helps solo founders…"
            style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);
            padding:10px;color:var(--text-0);font-size:13px;resize:none;min-height:80px;outline:none;font-family:inherit;margin-top:8px"></textarea>
          <div style="margin-top:12px">
            <div style="font-size:11px;font-weight:700;color:var(--text-2);margin-bottom:8px;text-transform:uppercase;letter-spacing:.5px">Agents</div>
            <div id="sw-agent-grid" style="display:flex;flex-wrap:wrap;gap:8px"></div>
          </div>
          <div style="margin-top:12px">
            <div style="font-size:11px;font-weight:700;color:var(--text-2);margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px">Strategy</div>
            <select id="sw-strategy" style="background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 10px;color:var(--text-0);font-size:13px;outline:none">
              <option value="judge">Judge — pick best (fast)</option>
              <option value="merge">Merge — fuse top 2</option>
              <option value="fanout">Fan-out — show all</option>
            </select>
          </div>
          <button onclick="runSwarm()" class="btn btn-primary" style="width:100%;margin-top:12px" id="sw-run-btn">🚀 Run Swarm</button>
          <div id="sw-status" style="font-size:12px;color:var(--text-2);margin-top:8px;min-height:18px"></div>
        </div>
      </div>
      <div style="overflow-y:auto;max-height:calc(100vh - 160px)">
        <div id="sw-runs" class="swarm-grid"></div>
        <div id="sw-winner-box" style="display:none" class="swarm-winner-box">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
            <span style="font-size:20px">🏆</span>
            <span style="font-weight:700;font-size:14px" id="sw-winner-title">Winner</span>
            <button onclick="copyWinner()" class="btn btn-ghost btn-sm" style="margin-left:auto">📋 Copy</button>
            <button onclick="acceptWinnerToMonaco()" class="btn btn-primary btn-sm">→ Editor</button>
          </div>
          <div style="font-size:12px;color:var(--text-2);margin-bottom:8px" id="sw-winner-reason"></div>
          <div id="sw-winner-body" style="font-size:13px;white-space:pre-wrap;max-height:300px;overflow-y:auto;line-height:1.6"></div>
        </div>
      </div>
    </div>`;

  renderSwarmAgents();
}

async function renderSwarmAgents() {
  const grid = document.getElementById('sw-agent-grid');
  if (!grid) return;
  const defaultOn = new Set(['orchestrator','brain','builder','visual_tester','functional_tester','design_decomposer','test_creator']);
  let agents = S.agents;
  try {
    const r = await fetch('/api/swarm/agents');
    if (r.ok) {
      const data = await r.json();
      if (Array.isArray(data)) agents = data;
      else if (Array.isArray(data.agents)) agents = data.agents;
    }
  } catch(e) { /* fall back to cached S.agents */ }
  if (!Array.isArray(agents)) agents = Array.isArray(S.agents) ? S.agents : [];
  grid.innerHTML = agents.map(a => `
    <label style="display:flex;align-items:center;gap:6px;background:var(--bg-3);border-radius:var(--radius-sm);
      padding:6px 10px;cursor:pointer;border:1px solid var(--border);font-size:12px;transition:var(--transition)"
      title="${escHtml(a.role||a.description||'')}">
      <input type="checkbox" data-agent="${a.id}" ${defaultOn.has(a.id)?'checked':''} style="accent-color:var(--accent)">
      <span>${a.avatar||'🤖'}</span><span>${escHtml(a.name)}</span>
    </label>`).join('');
}

let swarmLastWinner = '';
async function runSwarm() {
  const prompt = (document.getElementById('sw-prompt')?.value||'').trim();
  if (!prompt) { toast('Enter a prompt','warn'); return; }
  const agents = [...document.querySelectorAll('#sw-agent-grid input:checked')].map(i=>i.dataset.agent);
  if (agents.length < 2) { toast('Select at least 2 agents','warn'); return; }
  const strategy = document.getElementById('sw-strategy')?.value || 'judge';

  const btn = document.getElementById('sw-run-btn');
  const statusEl = document.getElementById('sw-status');
  btn.disabled = true; btn.textContent = '⏳ Swarming…';
  statusEl.textContent = `Fanning out to ${agents.join(', ')}…`;

  document.getElementById('sw-runs').innerHTML =
    agents.map(aid => {
      const a = S.agents.find(x=>x.id===aid)||{name:aid,avatar:'🤖',color:'#5b8af8'};
      return `<div class="swarm-card" id="sw-card-${aid}">
        <div class="swarm-card-head">
          <span style="font-size:18px">${a.avatar||'🤖'}</span>
          <span style="font-weight:700">${escHtml(a.name)}</span>
          <span style="margin-left:auto;font-size:11px;color:var(--text-2)" id="sw-meta-${aid}">running…</span>
        </div>
        <div class="swarm-card-body" id="sw-body-${aid}">
          <div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>
        </div>
      </div>`;
    }).join('');
  document.getElementById('sw-winner-box').style.display = 'none';

  try {
    const r = await fetch('/api/swarm/run', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({prompt, agents, strategy})
    });
    if (!r.ok) throw new Error('Server error ' + r.status);
    const j = await r.json();
    if (!j.ok) throw new Error(j.error||'swarm failed');

    (j.runs||[]).forEach(run => {
      const bodyEl = document.getElementById(`sw-body-${run.agent}`);
      const metaEl = document.getElementById(`sw-meta-${run.agent}`);
      if (bodyEl) bodyEl.innerHTML = renderMarkdown(run.output||'(empty)');
      const scoreStr = run.score != null ? ` · ${Math.round(run.score*100)}%` : '';
      if (metaEl) metaEl.textContent = `${run.latency_ms}ms · ${run.tokens}t${scoreStr}`;
      if (run.agent === j.winner) {
        const card = document.getElementById(`sw-card-${run.agent}`);
        if (card) { card.classList.add('winner'); }
      }
    });

    if (j.winner || j.merged) {
      swarmLastWinner = j.merged || j.winner_output || '';
      document.getElementById('sw-winner-box').style.display = 'block';
      document.getElementById('sw-winner-title').textContent =
        j.merged ? '🔀 Merged Output' : `🏆 ${j.winner} — winner`;
      document.getElementById('sw-winner-reason').textContent = j.judge_reason || '';
      document.getElementById('sw-winner-body').innerHTML = renderMarkdown(swarmLastWinner);
    }

    statusEl.innerHTML = `✓ Done in ${j.total_latency_ms}ms · ${j.total_tokens} tokens · winner: <strong>${j.winner||'—'}</strong>`;
  } catch(e) {
    statusEl.textContent = '✗ ' + e.message;
    toast('Swarm error: ' + e.message,'err');
  } finally {
    btn.disabled = false; btn.textContent = '🚀 Run Swarm';
  }
}

function copyWinner() {
  navigator.clipboard.writeText(swarmLastWinner)
    .then(()=>toast('📋 Copied!','ok',1500))
    .catch(()=>toast('Copy failed — clipboard not available','err'));
}

function acceptWinnerToMonaco() {
  if (!swarmLastWinner) { toast('No winner yet','warn'); return; }
  nav('builder');
  setTimeout(() => {
    if (S.monacoEditor) {
      const sel = S.monacoEditor.getSelection();
      S.monacoEditor.executeEdits('swarm', [{range: sel, text: '\n\n/* 🌀 Swarm */\n' + swarmLastWinner}]);
      toast('→ Inserted into editor','ok');
    } else {
      navigator.clipboard.writeText(swarmLastWinner).then(()=>toast('Copied — paste into editor','ok'));
    }
  }, 400);
}

async function loadSwarmHistory() {
  try {
    const r = await fetch('/api/swarm/history?limit=10');
    if (!r.ok) { toast('Failed to load history: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (!j.length) { toast('No swarm history yet','warn'); return; }
    const items = j.map(h => `${h.ts} — ${h.winner||'?'} won — ${h.strategy} — agents: ${(h.agents||[]).join(', ')}\n  ${h.prompt?.slice(0,80)||''}`).join('\n\n');
    await gmAlert('🌀 Swarm History (last 10)', `<pre style="font-size:12px;white-space:pre-wrap;max-height:340px;overflow-y:auto">${escHtml(items)}</pre>`);
  } catch(ex) { toast('Swarm history error: ' + ex.message, 'err'); }
}

// ── Galaxy ────────────────────────────────────────────────────────
let gxGraph = null, gxInited = false;
async function initGalaxy() {
  if (gxInited) { refreshGalaxy(); gxLoadStats(); return; }
  gxInited = true;
  // load 3D force graph
  await loadScript('https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js');
  await loadScript('https://cdn.jsdelivr.net/npm/3d-force-graph@1.73.0/dist/3d-force-graph.min.js');
  setupGxGraph();
  refreshGalaxy();
  gxLoadStats();
}

function setupGxGraph() {
  const el = document.getElementById('gx-graph');
  if (!el || !window.ForceGraph3D) return;
  gxGraph = ForceGraph3D()(el)
    .backgroundColor('#08090e')
    .nodeAutoColorBy('source')
    .nodeLabel(n => `${n.source} • ${n.label}`)
    .nodeVal('val')
    .linkDirectionalParticles(1)
    .linkDirectionalParticleWidth(1.2)
    .linkColor(() => 'rgba(91,138,248,.2)')
    .onNodeClick(n => {
      showGxNode(n);
      const d = 120, r = 1 + d / Math.hypot(n.x||1, n.y||1, n.z||1);
      gxGraph.cameraPosition({x:n.x*r,y:n.y*r,z:n.z*r}, n, 900);
    })
    .onNodeHover(n => { el.style.cursor = n ? 'pointer' : null; });
  new ResizeObserver(() => gxGraph && gxGraph.width(el.clientWidth).height(el.clientHeight)).observe(el);
}

async function refreshGalaxy() {
  const limit = document.getElementById('gx-limit')?.value || 250;
  const statsEl = document.getElementById('gx-stats');
  if (statsEl) statsEl.textContent = 'loading…';
  try {
    const r = await fetch('/api/memory/galaxy?limit=' + limit);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const data = await r.json();
    if (gxGraph) gxGraph.graphData(data);
    if (statsEl) statsEl.textContent =
      `${data.total_memories} memories · ${data.links.length} links · ${data.sources?.length||0} sources`;
  } catch(e) {
    if (statsEl) statsEl.textContent = 'Load failed — ' + (e?.message||String(e));
  }
}

function fitGalaxy() { if (gxGraph) gxGraph.zoomToFit(600, 60); }

function showGxNode(n) {
  const el = document.getElementById('gx-results');
  if (!el) return;
  const memId = n.mem_id || n.id;
  el.innerHTML = `<div class="gx-hit">
    <div class="gx-hit-source">${escHtml(n.source||'')} · mem #${memId}</div>
    <div class="gx-hit-text">${escHtml(n.label||'')}</div>
    <div style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap">
      <button onclick="navigator.clipboard.writeText(${JSON.stringify(n.label||'')})" class="btn btn-ghost btn-sm">📋 Copy</button>
      <button onclick="insertCmd('Tell me more about: '+${JSON.stringify((n.label||'').slice(0,60))});nav('chat')" class="btn btn-ghost btn-sm">💬 Chat</button>
      <button onclick="deleteGxNode(${JSON.stringify(memId)})" class="btn btn-ghost btn-sm" style="color:var(--danger)">🗑 Delete</button>
    </div>
  </div>`;
}

async function deleteGxNode(memId) {
  const ok = await gmDanger('Delete Memory', `Remove memory #${memId} permanently?`);
  if (!ok) return;
  try {
    const r = await fetch(`/api/memory/${encodeURIComponent(memId)}`, {method:'DELETE'});
    if (!r.ok) { gmAlert('Delete failed: HTTP '+r.status); return; }
    const d = await r.json();
    if (d.ok) {
      showToast('🗑 Memory deleted');
      document.getElementById('gx-results').innerHTML = '<div style="color:var(--text-3);font-size:12px;padding:12px">Memory deleted.</div>';
      refreshGalaxy();
    } else {
      gmAlert('Delete failed: '+(d.error||'Unknown'));
    }
  } catch(ex) {
    gmAlert('Delete error: '+ex?.message);
  }
}

window.gxAddMemory = async function() {
  const text = await gmPrompt('New Memory Content:', 'e.g. User prefers Python and Tailwind CSS over Bootstrap', '', true);
  if (!text) return;
  const source = await gmPrompt('Source / Category (e.g. user_prefs, project_rules, architecture):', 'user_prefs');
  if (!source) return;
  const tags = await gmPrompt('Tags (comma-separated, optional):', 'python, tailwind, ui');
  try {
    toast('⏳ Storing vector memory...', 'ok', 2000);
    const r = await fetch('/api/memory/add', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({content: text, source, tags: (tags||'').split(',').map(t=>t.trim()).filter(Boolean)})
    });
    const j = await r.json();
    if (j.ok || j.id) {
      toast('✅ Memory #' + (j.id || 'new') + ' stored & indexed!', 'ok', 3000);
      if (typeof refreshGalaxy === 'function') refreshGalaxy();
    } else {
      gmAlert('Error adding memory: ' + (j.error || 'Unknown error'));
    }
  } catch(e) {
    gmAlert('Network error adding memory: ' + e.message);
  }
};

async function doGxSearch() {
  const q = document.getElementById('gx-search')?.value?.trim();
  if (!q) return;
  const el = document.getElementById('gx-results');
  if (!el) return;
  el.innerHTML = '<div style="color:var(--text-2);font-size:12px;padding:12px">Searching…</div>';
  try {
    const r = await fetch(`/api/memory/search?q=${encodeURIComponent(q)}&mode=hybrid&limit=20`);
    if (!r.ok) { el.innerHTML = `<div style="color:var(--danger);font-size:12px;padding:12px">Search failed (HTTP ${r.status})</div>`; return; }
    const results = await r.json();
    if (!results.length) {
      el.innerHTML = '<div style="color:var(--text-3);font-size:12px;padding:12px">No memories found for that query.</div>';
      return;
    }
    el.innerHTML = results.map(m => `
      <div class="gx-hit">
        <div class="gx-hit-source">${escHtml(m.source||'')}${m.tags?' · '+escHtml(m.tags):''} · mem #${m.id}</div>
        <div class="gx-hit-text">${escHtml((m.content||'').slice(0,150))}</div>
        <div style="margin-top:4px;display:flex;gap:4px">
          <button onclick="insertCmd('Tell me about: '+${JSON.stringify((m.content||'').slice(0,60))});nav('chat')" class="btn btn-ghost btn-sm" style="font-size:10px">💬 Chat</button>
          <button onclick="deleteGxNode(${JSON.stringify(m.id)})" class="btn btn-ghost btn-sm" style="font-size:10px;color:var(--danger)">🗑</button>
        </div>
      </div>`).join('');
  } catch(e) {
    el.innerHTML = `<div style="color:var(--danger);font-size:12px;padding:12px">Error: ${e?.message||String(e)}</div>`;
  }
}

async function ingestMemory() {
  const contentEl = document.getElementById('gx-ingest-text');
  const tagsEl    = document.getElementById('gx-ingest-tags');
  const content   = contentEl?.value?.trim();
  const tags      = tagsEl?.value?.trim() || '';
  if (!content) { showToast('⚠️ Enter memory content'); return; }
  try {
    const r = await fetch('/api/memory/add', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({source:'user', content, tags})
    });
    if (!r.ok) { showToast('❌ Memory add failed (HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) {
      showToast('🌌 Memory added (id: '+j.id+')');
      if (contentEl) contentEl.value = '';
      if (tagsEl)    tagsEl.value    = '';
      refreshGalaxy();
    } else {
      showToast('❌ Failed: '+(j.error||'Unknown error'));
    }
  } catch(ex) {
    showToast('❌ Error: '+ex?.message);
  }
}

async function gxLoadStats() {
  try {
    const r = await fetch('/api/memory/stats');
    if (!r.ok) return;
    const d = await r.json();
    const el = document.getElementById('gx-mem-stats');
    if (!el) return;
    el.innerHTML = `
      <span>💾 ${d.sqlite_memories||0} memories</span>
      <span>🔮 ${d.vectors_sqlite||0} vectors</span>
      <span title="${d.engine||''}">${d.status==='active'?'✅':'⚠️'} ${d.engine||'FTS5'}</span>`;
  } catch(e) {}
}

async function gxReindex() {
  showToast('🔄 Reindexing FTS…');
  try {
    const r = await fetch('/api/memory/reindex', {method:'POST'});
    if (!r.ok) { gmAlert('Reindex failed: HTTP '+r.status); return; }
    const d = await r.json();
    if (d.ok) showToast(`✅ Reindexed ${d.total} memories`);
    else gmAlert('Reindex error: '+(d.error||'Unknown'));
  } catch(ex) {
    gmAlert('Reindex error: '+ex?.message);
  }
}

async function gxExport() {
  try {
    const r = await fetch('/api/memory/export?limit=10000');
    if (!r.ok) { gmAlert('Export failed: HTTP '+r.status); return; }
    const d = await r.json();
    const blob = new Blob([JSON.stringify(d.memories, null, 2)], {type:'application/json'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `memory-export-${new Date().toISOString().slice(0,10)}.json`;
    a.click();
    showToast(`✅ Exported ${d.count} memories`);
  } catch(ex) {
    gmAlert('Export error: '+ex?.message);
  }
}

async function gxImport() {
  const input = document.createElement('input');
  input.type = 'file'; input.accept = '.json';
  input.onchange = async () => {
    const file = input.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      // Accept either array or {memories:[...]}
      const memories = Array.isArray(data) ? data : (data.memories || []);
      if (!memories.length) { gmAlert('No memories found in file.'); return; }
      const r = await fetch('/api/memory/import', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({memories})
      });
      if (!r.ok) { gmAlert('Import failed: HTTP '+r.status); return; }
      const d = await r.json();
      if (d.ok) {
        showToast(`✅ Imported ${d.imported}, skipped ${d.skipped}`);
        refreshGalaxy();
        gxLoadStats();
      } else {
        gmAlert('Import error: '+(d.error||'Unknown'));
      }
    } catch(ex) {
      gmAlert('Import parse error: '+ex?.message);
    }
  };
  input.click();
}

// ── Dedicated 2-Column Settings Workstation & Drag/Drop Engine ──
window.switchSettingsTab = function(tabId) {
  if (tabId === 'theme') tabId = 'appearance';
  document.querySelectorAll('.settings-nav-item').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.settings-tab-pane').forEach(el => el.classList.remove('active'));
  let navBtn = document.getElementById('settings-nav-' + tabId);
  let pane = document.getElementById('settings-tab-' + tabId);
  if (!navBtn && tabId === 'appearance') navBtn = document.getElementById('settings-nav-theme');
  if (!pane && tabId === 'appearance') pane = document.getElementById('settings-tab-theme');
  if (navBtn) navBtn.classList.add('active');
  if (pane) pane.classList.add('active');
  try { localStorage.setItem('agentic_os_settings_tab', tabId); } catch(e) {}
  try { history.replaceState(null, '', '#/settings/' + tabId); } catch(e) {}
  if (tabId === 'ollama' && typeof window.checkHardwareRecommendations === 'function') {
    window.checkHardwareRecommendations();
  }
};

window.setupSettingsWorkstation = function() {
  const ws = document.querySelector('#pane-settings .settings-workstation');
  if (!ws) return;
  const savedTab = localStorage.getItem('agentic_os_settings_tab') || 'api';
  switchSettingsTab(savedTab);
};

window.setupDragAndDrop = function() {
  const content = document.getElementById('content');
  if (!content || document.getElementById('chat-dropzone')) return;
  const dropzone = document.createElement('div');
  dropzone.id = 'chat-dropzone';
  dropzone.className = 'dropzone-overlay';
  dropzone.innerHTML = '<div>⚡ Drop files here to attach to AI Context & Studio (~/Library/Application Support/com.stricktech.agenticos/workspaces/)</div>';
  content.appendChild(dropzone);

  let dragCounter = 0;
  content.addEventListener('dragenter', e => {
    e.preventDefault(); dragCounter++;
    dropzone.classList.add('active');
  });
  content.addEventListener('dragleave', e => {
    e.preventDefault(); dragCounter--;
    if (dragCounter <= 0) { dragCounter = 0; dropzone.classList.remove('active'); }
  });
  content.addEventListener('dragover', e => e.preventDefault());
  content.addEventListener('drop', async e => {
    e.preventDefault(); dragCounter = 0; dropzone.classList.remove('active');
    const files = e.dataTransfer?.files;
    if (!files || !files.length) return;
    toast(`⚡ Uploading ${files.length} file(s) into workspace...`, 'ok', 3000);
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const reader = new FileReader();
      reader.onload = async (evt) => {
        const text = evt.target?.result || '';
        if (document.getElementById('chat-input')) {
          const inp = document.getElementById('chat-input');
          inp.value += `\n[Attached File: ${file.name}]\n\`\`\`\n${text.slice(0, 2000)}\n\`\`\`\n`;
        }
      };
      reader.readAsText(file);
    }
  });
};

// ── Settings ──────────────────────────────────────────────────────
window.loadSettings = async function() {
  if (typeof setupSettingsWorkstation === 'function') setupSettingsWorkstation();
  if (typeof renderAgentList === 'function') renderAgentList();
  try {
    const pr = await fetch('/api/onboarding/preferences');
    if (pr.ok) {
      const p = await pr.json();
      const keyInp = document.getElementById('or-key-input');
      if (keyInp && p.workspace_name) keyInp.placeholder = `Current workspace: ${p.workspace_name}`;
    }
  } catch(e) {}
  try {
    const r = await fetch('/api/agents/models');
    const j = await r.json();
    const el = document.getElementById('ollama-status');
    if (el) {
      if (j.ollama?.running) {
        el.innerHTML = `<span style="color:var(--green)">✅ Ollama running</span> — ${j.ollama.models?.length||0} models installed`;
        const ml = document.getElementById('ollama-models');
        if (ml) ml.innerHTML = j.ollama.models?.map(m =>
          `<span class="tag" style="margin:2px">${m}</span>`).join('') || '';
      } else {
        el.innerHTML = `<span style="color:var(--red)">❌ Ollama not running</span> — see setup below`;
      }
    }
  } catch(e) {}
  const info = document.getElementById('system-info');
  if (info) info.innerHTML = `<div>Port: 8787 · Memory: SQLite FTS5 · Build: ${new Date().toLocaleDateString()}</div>`;
  if (typeof updateSettingsModeButtons === 'function') updateSettingsModeButtons();
};

window.lpSaveVerifyKey = async function() {
  const keyInp = document.getElementById('lp-api-key');
  const statusEl = document.getElementById('lp-key-status');
  if (!keyInp || !keyInp.value.trim()) {
    if (statusEl) statusEl.innerHTML = '<span style="color:var(--danger)">⚠️ Please paste your OpenRouter API key first.</span>';
    return;
  }
  const key = keyInp.value.trim();
  if (statusEl) statusEl.innerHTML = '<span style="color:var(--accent)">⏳ Saving & verifying live connection to OpenRouter...</span>';
  try {
    const r = await fetch('/api/secrets/set', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({key: 'OPENROUTER_API_KEY', value: key, scope: 'global'})
    });
    const j = await r.json();
    if (j.ok) {
      const tr = await fetch('/api/secrets/test-connection', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({provider: 'openrouter', key: key})
      });
      const tj = await tr.json();
      if (tj.ok) {
        if (statusEl) statusEl.innerHTML = `<span style="color:var(--success)">✅ Verified & active! ${tj.models_count || 180}+ models ready (Claude 3.5 Sonnet, GPT-4o, Llama 3.3).</span>`;
        if (typeof updateKeyStatus === 'function') updateKeyStatus(true);
        keyInp.value = '';
      } else {
        if (statusEl) statusEl.innerHTML = `<span style="color:var(--warning)">🔑 Key saved, but verification reported: ${escHtml(tj.error || 'Check permissions')}</span>`;
      }
    } else {
      if (statusEl) statusEl.innerHTML = `<span style="color:var(--danger)">❌ Failed to save key: ${escHtml(j.error || '')}</span>`;
    }
  } catch(e) {
    if (statusEl) statusEl.innerHTML = `<span style="color:var(--danger)">❌ Network error: ${escHtml(e?.message || '')}</span>`;
  }
};

async function saveApiKey() {
  const key = document.getElementById('or-key-input')?.value.trim();
  const resEl = document.getElementById('settings-key-test-result');
  if (!key) { toast('Enter your OpenRouter API key','warn'); return; }
  if (resEl) { resEl.style.display = 'block'; resEl.innerHTML = '<span style="color:var(--accent)">⏳ Saving & testing OpenRouter API key connection...</span>'; }
  const r = await fetch('/api/secrets/set', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({key:'OPENROUTER_API_KEY', value:key, scope:'global'})
  });
  const j = await r.json();
  if (j.ok) {
    toast('🔑 API key saved! Testing live connection...','ok',2000);
    updateKeyStatus(true);
    document.getElementById('or-key-input').value = '';
    if (window.markChecklistStep) markChecklistStep('api_key');
    try {
      const tr = await fetch('/api/secrets/test-connection', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({provider: 'openrouter', key: key})
      });
      const tj = await tr.json();
      if (tj.ok) {
        toast(`✅ OpenRouter verified! ${tj.models_count} models unlocked.`, 'ok', 5000);
        if (resEl) resEl.innerHTML = `<span style="color:var(--success)">✅ Verified connection! ${tj.models_count} AI models available (Claude 3.5 Sonnet, GPT-4o, Llama 3.3, Gemini).</span>`;
      } else {
        toast(`⚠️ OpenRouter test note: ${tj.error}`, 'warn', 5000);
        if (resEl) resEl.innerHTML = `<span style="color:var(--warning)">🔑 Key saved in vault, but API test reported: ${escHtml(tj.error)}</span>`;
      }
    } catch(e) {
      if (resEl) resEl.innerHTML = `<span style="color:var(--warning)">🔑 Key saved in vault (network verification timed out).</span>`;
    }
  } else {
    toast('Failed to save key','err');
    if (resEl) { resEl.style.display = 'block'; resEl.innerHTML = `<span style="color:var(--danger)">❌ Error saving key: ${escHtml(j.error||'')}</span>`; }
  }
}

window.testOllamaConnection = async function() {
  const urlInp = document.getElementById('ollama-url-input');
  const statusEl = document.getElementById('ollama-status');
  const modelsEl = document.getElementById('ollama-models') || document.getElementById('settings-api-ollama-models');
  const url = urlInp ? urlInp.value.trim() : 'http://localhost:11434';
  if (statusEl) statusEl.innerHTML = '<span style="color:var(--accent)">Testing…</span>';
  try {
    const r = await fetch('/api/secrets/test-connection', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({provider: 'ollama', url: url})
    });
    const j = await r.json();
    if (j.ok) {
      if (statusEl) statusEl.innerHTML = '<span style="color:var(--success)">✅ Online</span>';
      if (modelsEl) modelsEl.innerHTML = `<div style="margin-top:6px;color:var(--success);font-weight:700">${escHtml(j.message)}</div>`;
      toast('⚡ Local Ollama connection confirmed active!', 'ok', 3000);
      if (typeof window.syncOpenWebUIConnections === 'function') window.syncOpenWebUIConnections();
    } else {
      if (statusEl) statusEl.innerHTML = '<span style="color:var(--danger)">❌ Offline</span>';
      if (modelsEl) modelsEl.innerHTML = `<div style="margin-top:6px;color:var(--danger)">Could not connect to Ollama at ${escHtml(url)}. Make sure Ollama app is running.</div>`;
    }
  } catch(e) {
    if (statusEl) statusEl.innerHTML = '<span style="color:var(--danger)">❌ Error</span>';
  }
};

window.pullOllamaModel = async function(modelName) {
  const modelsEl = document.getElementById('ollama-models') || document.getElementById('settings-api-ollama-models');
  const urlInp = document.getElementById('ollama-url-input') || document.getElementById('settings-api-ollama-url');
  const url = urlInp ? urlInp.value.trim() : 'http://localhost:11434';
  toast(`⚡ Triggering model pull for ${modelName}... Check Ollama local server`, 'ok', 4000);
  if (modelsEl) modelsEl.innerHTML = `<div style="margin-top:6px;color:var(--accent);font-weight:700">⏳ Pulling model '${modelName}' via Ollama API...</div>`;
  try {
    const r = await fetch(url + '/api/pull', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: modelName, stream: false})
    });
    if (r.ok) {
      if (modelsEl) modelsEl.innerHTML = `<div style="margin-top:6px;color:var(--success);font-weight:700">✅ Model '${modelName}' downloaded and ready locally!</div>`;
      toast(`✅ Model ${modelName} ready!`, 'ok', 4000);
      if (typeof window.syncOpenWebUIConnections === 'function') window.syncOpenWebUIConnections();
    } else {
      if (modelsEl) modelsEl.innerHTML = `<div style="margin-top:6px;color:var(--warning);font-weight:700">⚠️ Ollama pull requested (${modelName}). If CORS blocked direct browser call, run: 'ollama pull ${modelName}' in Terminal.</div>`;
    }
  } catch(e) {
    if (modelsEl) modelsEl.innerHTML = `<div style="margin-top:6px;color:var(--warning);font-weight:700">⚠️ Run 'ollama pull ${modelName}' inside your macOS Terminal to install offline.</div>`;
  }
};

window.saveCustomConnection = async function() {
  const baseUrl = document.getElementById('custom-api-base-url')?.value?.trim();
  const apiKey  = document.getElementById('custom-api-key')?.value?.trim();
  const statusEl = document.getElementById('settings-api-custom-status');
  const msgEl    = document.getElementById('custom-api-status-msg');
  if (!baseUrl) { toast('Enter a custom Base URL', 'warn'); return; }
  if (msgEl) msgEl.innerHTML = '<span style="color:var(--accent)">⏳ Testing connection...</span>';
  try {
    localStorage.setItem('agentic_os_custom_base_url', baseUrl);
    if (apiKey) localStorage.setItem('agentic_os_custom_api_key', apiKey);
    const r = await fetch(baseUrl + '/models', {
      headers: apiKey ? {'Authorization': 'Bearer ' + apiKey} : {}
    }).catch(() => null);
    if (r && r.ok) {
      const d = await r.json();
      const count = d.data?.length || 1;
      if (statusEl) { statusEl.textContent = `ONLINE (${count} models)`; statusEl.style.color = 'var(--success)'; }
      if (msgEl) msgEl.innerHTML = `<span style="color:var(--success)">✅ Connected to ${escHtml(baseUrl)} — ${count} model(s) discovered!</span>`;
      toast(`✅ Custom connection verified! (${count} models)`, 'ok', 3000);
      if (typeof window.syncOpenWebUIConnections === 'function') window.syncOpenWebUIConnections();
    } else {
      if (statusEl) { statusEl.textContent = 'SAVED / OFFLINE'; statusEl.style.color = 'var(--warning)'; }
      if (msgEl) msgEl.innerHTML = `<span style="color:var(--warning)">🔗 Endpoint saved to local storage. (Could not fetch models directly: check server or CORS)</span>`;
      if (typeof window.syncOpenWebUIConnections === 'function') window.syncOpenWebUIConnections();
    }
  } catch(e) {
    if (msgEl) msgEl.innerHTML = `<span style="color:var(--danger)">Error saving: ${escHtml(e.message)}</span>`;
  }
};

window.syncOpenWebUIConnections = async function() {
  const select = document.getElementById('chat-model-select');
  if (!select) return;
  
  const customUrl = localStorage.getItem('agentic_os_custom_base_url');
  const customGroup = document.getElementById('custom-model-optgroup');
  if (customGroup && customUrl) {
    customGroup.innerHTML = `<option value="custom_url:${escHtml(customUrl)}">Custom: ${escHtml(customUrl)}</option>`;
  }

  try {
    const r = await fetch('/api/agents/models');
    if (r.ok) {
      const j = await r.json();
      const ollamaGroup = document.getElementById('ollama-model-optgroup');
      const ollamaStatus = document.getElementById('settings-api-ollama-status');
      const ollamaModelsEl = document.getElementById('settings-api-ollama-models');
      if (j.ollama?.running && j.ollama.models?.length) {
        if (ollamaGroup) {
          ollamaGroup.innerHTML = j.ollama.models.map(m => `<option value="ollama:${escHtml(m)}">Ollama: ${escHtml(m)}</option>`).join('');
        }
        if (ollamaStatus) { ollamaStatus.textContent = `ONLINE (${j.ollama.models.length} models)`; ollamaStatus.style.color = 'var(--success)'; }
        if (ollamaModelsEl) {
          ollamaModelsEl.innerHTML = `<div style="font-weight:700;color:var(--success);margin-bottom:6px">Installed Local Models:</div>` +
            j.ollama.models.map(m => `<span class="tag" style="margin:3px;background:var(--bg-3);border:1px solid var(--border);padding:3px 8px;border-radius:6px;display:inline-block">${escHtml(m)}</span>`).join('');
        }
      } else if (ollamaStatus) {
        ollamaStatus.textContent = 'OFFLINE'; ollamaStatus.style.color = 'var(--danger)';
      }
    }
  } catch(e) {}
};

// ── Command Palette ───────────────────────────────────────────────
const PALETTE_CMDS = [
  {icon:'✨', label:'Chat',           desc:'Open chat & multi-agent swarm', action:()=>nav('chat')},
  {icon:'⚡', label:'Builder',        desc:'Code editor + preview studio',  action:()=>nav('builder')},
  {icon:'📋', label:'Kanban',         desc:'Task board',                    action:()=>nav('kanban')},
  {icon:'🌀', label:'Swarm',          desc:'Multi-agent orchestration',     action:()=>nav('swarm')},
  {icon:'🌌', label:'Memory Galaxy',  desc:'3D vector memory graph',        action:()=>nav('galaxy')},
  {icon:'⚙', label:'Settings Hub',   desc:'API keys, models, themes',      action:()=>nav('settings')},
  {icon:'🛡', label:'New Agent',      desc:'Create specialist AI persona',  action:()=>openAgentModal()},
  {icon:'💾', label:'Backup DB',      desc:'Snapshot database to vault',    action:()=>doBackup()},
  {icon:'/',  label:'/help',          desc:'Show slash commands',           action:()=>{nav('chat');insertCmd('/help')}},
  {icon:'/',  label:'/goal',          desc:'Plan a goal',         action:()=>{nav('chat');insertCmd('/goal ')}},
  {icon:'/',  label:'/research',      desc:'Deep research',       action:()=>{nav('chat');insertCmd('/research ')}},
  {icon:'/',  label:'/code',          desc:'Build something',     action:()=>{nav('chat');insertCmd('/code ')}},
  {icon:'/',  label:'/memory',        desc:'Search memory',       action:()=>{nav('chat');insertCmd('/memory ')}},
];

function openPalette() {
  const modal = document.getElementById('palette-modal');
  if (!modal) return;
  modal.classList.add('open');
  const inp = document.getElementById('palette-input');
  if (inp) inp.value = '';
  filterPalette();
  setTimeout(() => document.getElementById('palette-input')?.focus(), 50);
}

function closePalette() {
  const modal = document.getElementById('palette-modal');
  if (modal) modal.classList.remove('open');
}
window.openPalette = openPalette;
window.closePalette = closePalette;

async function filterPalette() {
  const q = document.getElementById('palette-input').value.trim().toLowerCase();
  const results = document.getElementById('palette-results');
  
  const allCommands = [...PALETTE_CMDS];
  if (window.MASTER_PANE_REGISTRY) {
    Object.keys(window.MASTER_PANE_REGISTRY).forEach(pk => {
      if (!allCommands.some(c => c.label.toLowerCase() === pk.toLowerCase() || (c.desc && c.desc.toLowerCase().includes(`nav('${pk}')`)))) {
        allCommands.push({
          icon: '⚡',
          label: 'Open ' + pk.toUpperCase().replace(/-/g, ' '),
          desc: 'Switch directly to the ' + pk + ' workspace component',
          action: () => window.nav(pk)
        });
      }
    });
  }
  if (S.agents && S.agents.length) {
    S.agents.forEach(a => {
      allCommands.push({
        icon: a.avatar || '🤖',
        label: 'Agent: ' + a.name,
        desc: a.role || a.model || 'Specialist AI Agent',
        action: () => { if (typeof setActiveAgent === 'function') setActiveAgent(a); window.nav('chat'); }
      });
    });
  }

  const items = allCommands.filter(c =>
    !q || c.label.toLowerCase().includes(q) || c.desc.toLowerCase().includes(q));
  S.paletteFocusIdx = 0;
  let html = [
    `<div class="palette-section">Quick Commands</div>`,
    ...items.map((c, i) => `
      <div class="palette-item ${i===0?'focused':''}" data-idx="${i}">
        <span class="p-icon">${c.icon}</span>
        <span class="p-label">${escHtml(c.label)}</span>
        <span class="p-desc">${escHtml(c.desc)}</span>
      </div>`),
  ].join('');
  results.innerHTML = html;
  results.querySelectorAll('.palette-item').forEach((el, i) => {
    el.addEventListener('click', () => { items[i]?.action(); closePalette(); });
  });

  if (q.length > 0) {
    try {
      const res = await fetch('/api/search/global?q=' + encodeURIComponent(q));
      const data = await res.json();
      if (data.ok && data.results && data.results.length > 0) {
        let globalItems = data.results;
        let startIdx = items.length;
        html += `<div class="palette-section" style="margin-top:12px;border-top:1px solid var(--border);padding-top:8px">Global Search Matches (${data.count})</div>`;
        html += globalItems.map((item, idx) => {
          let pill = '';
          if (item.action?.startsWith('loop-run:')) pill = `<span class="badge" style="background:rgba(234,179,8,.2);color:#fbbf24;border:1px solid rgba(234,179,8,.4);padding:2px 7px;font-size:10px;font-weight:800;border-radius:6px;margin-left:auto;white-space:nowrap">⚡ Run Now</span>`;
          else if (item.action?.startsWith('memory-insert:')) pill = `<span class="badge" style="background:rgba(91,138,248,.2);color:#7aa4ff;border:1px solid rgba(91,138,248,.4);padding:2px 7px;font-size:10px;font-weight:800;border-radius:6px;margin-left:auto;white-space:nowrap">📋 Insert to Prompt</span>`;
          else if (item.action?.startsWith('mcp-tool:')) pill = `<span class="badge" style="background:rgba(168,85,247,.2);color:#c084fc;border:1px solid rgba(168,85,247,.4);padding:2px 7px;font-size:10px;font-weight:800;border-radius:6px;margin-left:auto;white-space:nowrap">🔧 Run Tool</span>`;
          return `
          <div class="palette-item ${startIdx+idx===0?'focused':''}" data-idx="${startIdx+idx}" style="display:flex;align-items:center;gap:8px">
            <span class="p-icon">${item.icon || '🔍'}</span>
            <span class="p-label">${escHtml(item.title)}</span>
            <span class="p-desc" style="flex:1;overflow:hidden;text-overflow:ellipsis">${escHtml(item.category + ' — ' + item.description)}</span>
            ${pill}
          </div>`;
        }).join('');
        results.innerHTML = html;
        const allActions = [...items.map(c => c.action), ...globalItems.map(g => () => handleGlobalItemClick(g.action))];
        results.querySelectorAll('.palette-item').forEach((el, i) => {
          el.addEventListener('click', () => { if (allActions[i]) allActions[i](); closePalette(); });
        });
      }
    } catch(e) { console.warn('Global search fetch failed:', e); }
  }
}

function handleGlobalItemClick(actionStr) {
  if (!actionStr) return;
  if (actionStr.startsWith('pane:')) { nav(actionStr.slice(5)); }
  else if (actionStr.startsWith('loop-run:')) {
    const jid = actionStr.slice(9);
    fetch('/api/loops/' + encodeURIComponent(jid) + '/run-now', {method:'POST'});
    if (window.toast) toast('⚡ Triggered autonomous loop ' + jid + ' right now!', 'ok', 3000);
  }
  else if (actionStr.startsWith('memory-insert:')) {
    const txt = actionStr.slice(14);
    const msgBox = document.getElementById('msgInput');
    if (msgBox) {
      msgBox.value = (msgBox.value ? msgBox.value + '\n\n' : '') + txt;
      msgBox.focus();
    }
    nav('chat');
    if (window.toast) toast('📋 Inserted memory snippet into chat prompt!', 'ok', 2500);
  }
  else if (actionStr.startsWith('mcp-tool:')) {
    nav('mcp');
    if (window.toast) toast('🔧 Switched to MCP Tools router to configure ' + actionStr.slice(9), 'ok', 2500);
  }
  else if (actionStr.startsWith('agent:')) { nav('agents'); }
  else if (actionStr.startsWith('prompt:')) { nav('prompts'); }
  else if (actionStr.startsWith('marketplace:')) { nav('marketplace'); }
  else if (actionStr.startsWith('skill:')) { nav('marketplace'); }
  else { nav('chat'); }
}

function paletteKey(e) {
  const items = document.querySelectorAll('.palette-item');
  if (e.key === 'ArrowDown') { S.paletteFocusIdx = Math.min(S.paletteFocusIdx+1, items.length-1); }
  if (e.key === 'ArrowUp')   { S.paletteFocusIdx = Math.max(S.paletteFocusIdx-1, 0); }
  if (e.key === 'Enter') { items[S.paletteFocusIdx]?.click(); return; }
  if (e.key === 'Escape') { closePalette(); return; }
  items.forEach((el,i) => el.classList.toggle('focused', i === S.paletteFocusIdx));
  items[S.paletteFocusIdx]?.scrollIntoView({block:'nearest'});
}

// Keyboard shortcuts & Master Global Escape Interceptor
document.addEventListener('keydown', function masterEscapeHandler(e) {
  if (e.key === 'Escape' || e.key === 'Esc') {
    const openModals = [
      document.getElementById('onboarding-overlay'),
      document.getElementById('onboarding-modal'),
      document.getElementById('gmodal'),
      document.getElementById('agent-modal'),
      document.getElementById('skill-run-modal'),
      document.getElementById('palette-modal'),
      document.getElementById('review-overlay'),
      document.getElementById('profile-panel'),
      document.getElementById('shortcuts-modal'),
      document.getElementById('ctx-help-overlay'),
      document.querySelector('.modal-back[style*="flex"]'),
      document.querySelector('.modal-back[style*="block"]')
    ].filter(m => m && (m.classList.contains('open') || m.style.display !== 'none' || m.style.opacity === '1'));

    if (openModals.length > 0) {
      e.preventDefault();
      e.stopPropagation();
      openModals.forEach(m => {
        if (m.id === 'onboarding-overlay' || m.id === 'onboarding-modal') {
          if (typeof window.closeOnboardingModal === 'function') window.closeOnboardingModal();
          else m.style.display = 'none';
        } else if (m.id === 'gmodal') {
          if (typeof _gm_cancel === 'function') _gm_cancel();
          else m.style.display = 'none';
        } else if (m.id === 'agent-modal') {
          if (typeof closeAgentModal === 'function') closeAgentModal();
          else m.style.display = 'none';
        } else if (m.id === 'skill-run-modal') {
          if (typeof closeSkillModal === 'function') closeSkillModal();
          else m.style.display = 'none';
        } else if (m.id === 'palette-modal') {
          if (typeof closePalette === 'function') closePalette();
          else m.classList.remove('open');
        } else if (m.id === 'review-overlay') {
          if (typeof toggleReviewOverlay === 'function') toggleReviewOverlay();
          else m.classList.remove('open');
        } else if (m.id === 'profile-panel' || m.id === 'ctx-help-overlay') {
          m.remove();
        } else {
          m.style.display = 'none';
        }
      });
      if (typeof toast === 'function') toast('✕ Modal closed', 'ok', 1200);
      return;
    }
  }
  if ((e.metaKey||e.ctrlKey) && e.key === 'k') { e.preventDefault(); openPalette(); }
  if ((e.metaKey||e.ctrlKey) && (e.key === '\\' || e.code === 'Backslash')) { e.preventDefault(); toggleSidebar(); }
  if ((e.metaKey||e.ctrlKey) && e.key === 'p' && !e.shiftKey) { e.preventDefault(); openPalette(); }
}, { capture: true });

// ── Status / misc ─────────────────────────────────────────────────
async function updateCostBar() {
  try {
    const r = await fetch('/api/cost');
    const j = await r.json();
    document.getElementById('sb-cost').textContent = `$${(j.total_cost_usd||0).toFixed(4)}`;
  } catch(e) {}
}

async function updateStatusBar() {
  const el = document.getElementById('sb-agents');
  if (el) el.textContent = `${S.agents.length} agents`;
  try {
    const r = await fetch('/api/memory/stats');
    if (!r.ok) return;
    const j = await r.json();
    const memEl = document.getElementById('sb-mem');
    if (memEl) memEl.textContent = `${j.sqlite_memories||0} memories`;
  } catch(e) {}
}

function updateKeyStatus(hasKey) {
  const dot   = document.getElementById('key-dot');
  const label = document.getElementById('key-label');
  const sbKey = document.getElementById('sb-key');
  if (hasKey) {
    dot.className  = 'key-dot ok';
    label.textContent = 'API key set';
    if (sbKey) sbKey.textContent = '🔑 Key set';
  } else {
    dot.className  = 'key-dot';
    label.textContent = 'No API key';
    if (sbKey) sbKey.textContent = '🔑 No key';
  }
  // Update chat empty state banner
  const banner = document.getElementById('chat-key-banner');
  if (banner) banner.style.display = hasKey ? 'none' : 'block';
}

async function checkKeyStatus() {
  try {
    const r = await fetch('/api/secrets/get?key=OPENROUTER_API_KEY');
    const j = await r.json();
    updateKeyStatus(j.ok && j.fingerprint);
  } catch(e) {}
}

async function doBackup() {
  const r = await fetch('/api/backup', {method:'POST'});
  const j = await r.json();
  if (j.ok) toast(`💾 Backup created: ${j.path?.split('/').pop()}`, 'ok');
  else toast('Backup failed: ' + (j.error||''), 'err');
}

// ── Helpers ───────────────────────────────────────────────────────
function escHtml(s) {
  return (s||'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function formatBytes(b) {
  if (b < 1024) return b + 'B';
  if (b < 1024*1024) return (b/1024).toFixed(1) + 'K';
  return (b/1024/1024).toFixed(1) + 'M';
}

function loadScript(src) {
  return new Promise((res, rej) => {
    if (document.querySelector(`script[src="${src}"]`)) { res(); return; }
    const s = document.createElement('script');
    s.src = src; s.onload = res; s.onerror = rej;
    document.head.appendChild(s);
  });
}

// Chat textarea auto-resize
const chatInput = document.getElementById('chat-input');
if (chatInput) {
  chatInput.addEventListener('input', () => autoResizeInput(chatInput));
  chatInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
  });
}

function autoResizeInput(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 160) + 'px';
}

// Clock
setInterval(() => {
  const el = document.getElementById('sb-time');
  if (el) el.textContent = new Date().toLocaleTimeString();
}, 1000);

// Agent status polling
setInterval(() => {
  if (S.agents.length) {
    fetch('/api/agents').then(r=>r.ok?r.json():null).then(agents => {
      if (!agents) return;
      S.agents = agents;
      renderAgentList();
      if (S.currentAgent) {
        const updated = agents.find(a => a.id === S.currentAgent.id);
        if (updated) setActiveAgent(updated);
      }
    }).catch(()=>{});
  }
}, 8000);

// ── Init ──────────────────────────────────────────────────────────
async function init() {
  await loadAgents();
  await checkKeyStatus();
  updateCostBar();
  updateStatusBar();
  // init rag/stream toggles
  document.getElementById('rag-btn')?.classList.toggle('active', S.useRag);
  document.getElementById('stream-btn')?.classList.toggle('active', S.useStream);
  setTimeout(() => { if (typeof checkOnboarding === 'function') checkOnboarding(); }, 800);
}

init();

// ═══════════════════════════════════════════════════════════════
//  SPRINT 2 — WebSocket, MCP, Loops, E2E, Voice
// ═══════════════════════════════════════════════════════════════

// ── WebSocket real-time ───────────────────────────────────────────
let ws = null, wsReconnectTimer = null;

function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${proto}//${location.host}/ws`);

  ws.onopen = () => {
    document.getElementById('ws-badge').textContent = '⚡ live';
    document.getElementById('ws-badge').style.color = 'var(--green)';
    clearTimeout(wsReconnectTimer);
  };

  ws.onmessage = e => {
    try {
      const msg = JSON.parse(e.data);
      handleWSMessage(msg);
    } catch(err) {}
  };

  ws.onclose = () => {
    document.getElementById('ws-badge').textContent = '⚡ offline';
    document.getElementById('ws-badge').style.color = 'var(--red)';
    wsReconnectTimer = setTimeout(connectWS, 4000);
  };

  ws.onerror = () => ws.close();
}

function handleWSMessage(msg) {
  if (msg.type === 'agent_status' || msg.type === 'agent_status_update') {
    if (msg.agents) {
      msg.agents.forEach(a => {
        const existing = S.agents.find(x => x.id === a.id);
        if (existing) existing.status = a.status;
      });
      renderAgentList();
    } else if (msg.agent_id) {
      const a = S.agents.find(x => x.id === msg.agent_id);
      if (a) { a.status = msg.status; renderAgentList(); }
    }
  }
  if (msg.type === 'memory_stats' || msg.type === 'init') {
    if (msg.sqlite_memories !== undefined)
      document.getElementById('sb-mem').textContent = `${msg.sqlite_memories} memories`;
  }
  if (msg.type === 'task_update') {
    if (document.getElementById('pane-kanban')?.classList.contains('active')) renderKanban();
  }
  if (msg.type === 'toast') {
    toast(msg.message, msg.kind || 'ok');
  }
  if (msg.type === 'memory_added') {
    document.getElementById('sb-mem').textContent =
      `${(parseInt(document.getElementById('sb-mem').textContent)||0)+1} memories`;
  }
}

connectWS();

// ── MCP Tool Panel ────────────────────────────────────────────────
async function renderMCP() {
  const pane = document.getElementById('pane-mcp');
  if (!pane) return;
  pane.innerHTML = `<div class="section-head">
    <div><h2>🔧 MCP Tool Router</h2><p>Model Context Protocol — call any tool directly or let an agent use them autonomously</p></div>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
    <div>
      <div class="settings-card">
        <h3>Direct Tool Call</h3>
        <p>Call any tool directly and inspect the result.</p>
        <label style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px">Tool</label>
        <select id="mcp-tool-sel" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px;color:var(--text-0);font-size:13px;margin:6px 0 10px;outline:none">
          <option value="">Loading tools…</option>
        </select>
        <label style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px">Args (JSON)</label>
        <textarea id="mcp-args" placeholder='{"path": "index.html"}' style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px;color:var(--text-0);font-size:13px;resize:none;min-height:60px;outline:none;font-family:monospace;margin:6px 0 10px"></textarea>
        <button onclick="runMCPTool()" class="btn btn-primary" style="width:100%">▶ Call Tool</button>
        <div id="mcp-result" style="margin-top:12px;background:var(--bg-0);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;font-family:monospace;font-size:12px;color:var(--text-1);white-space:pre-wrap;max-height:300px;overflow-y:auto;display:none"></div>
      </div>
      <div class="settings-card">
        <h3>Agentic Run</h3>
        <p>Give an agent a task and let it autonomously use tools to complete it.</p>
        <textarea id="mcp-agent-prompt" placeholder="Research the latest React 19 features and write a summary to index.html" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px;color:var(--text-0);font-size:13px;resize:none;min-height:80px;outline:none;font-family:inherit;margin:6px 0 10px"></textarea>
        <div style="display:flex;gap:8px;margin-bottom:10px">
          <select id="mcp-agent-sel" style="flex:1;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px;color:var(--text-0);font-size:12.5px;outline:none">
            ${S.agents.map(a=>`<option value="${a.id}">${a.avatar||'🤖'} ${escHtml(a.name)}</option>`).join('')}
          </select>
          <input id="mcp-max-steps" type="number" value="5" min="1" max="10" style="width:70px;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px;color:var(--text-0);font-size:12.5px;outline:none" placeholder="Steps">
        </div>
        <button onclick="runAgentWithTools()" class="btn btn-primary" style="width:100%" id="mcp-agent-btn">🤖 Run Agent</button>
        <div id="mcp-agent-result" style="margin-top:12px;display:none"></div>
      </div>
    </div>
    <div>
      <div class="settings-card">
        <h3 id="mcp-tools-header">Available Tools</h3>
        <p>All tools available to agents via MCP.</p>
        <div id="mcp-tool-list" style="display:flex;flex-direction:column;gap:6px"></div>
      </div>
    </div>
  </div>`;
  loadMCPTools();
}

async function loadMCPTools() {
  try {
    const r = await fetch('/api/mcp/tools');
    if (!r.ok) throw new Error('Tools API error ' + r.status);
    const j = await r.json();
    const sel = document.getElementById('mcp-tool-sel');
    const list = document.getElementById('mcp-tool-list');
    // Update header with live count
    const hdr = document.getElementById('mcp-tools-header');
    if (hdr) hdr.textContent = `Available Tools (${j.count || j.tools?.length || 0})`;
    if (sel) sel.innerHTML = j.tools.map(t => `<option value="${t.name}">${t.name}</option>`).join('');
    if (list) list.innerHTML = j.tools.map(t => `
      <div style="display:flex;gap:10px;padding:7px 10px;background:var(--bg-3);border-radius:var(--radius-sm);cursor:pointer"
           onclick="document.getElementById('mcp-tool-sel').value='${t.name}'">
        <code style="color:var(--accent);font-size:12px;min-width:140px">${t.name}</code>
        <span style="font-size:12px;color:var(--text-2)">${t.description}</span>
      </div>`).join('');
    // auto-fill args hint on select change
    if (sel) sel.onchange = () => {
      const tool = j.tools.find(t => t.name === sel.value);
      if (tool) {
        const exampleArgs = {};
        (tool.args||[]).filter(a=>!a.endsWith('?')).forEach(a => exampleArgs[a] = '');
        document.getElementById('mcp-args').value = JSON.stringify(exampleArgs, null, 2);
      }
    };
  } catch(e) { toast('Failed to load MCP tools', 'err'); }
}

async function runMCPTool() {
  const tool = document.getElementById('mcp-tool-sel')?.value;
  if (!tool) { toast('Select a tool first', 'warn'); return; }
  const argsStr = document.getElementById('mcp-args')?.value || '{}';
  const resultEl = document.getElementById('mcp-result');
  let args = {};
  try { args = JSON.parse(argsStr); } catch(e) { toast('Invalid JSON args — check the format', 'err'); return; }
  if (resultEl) { resultEl.style.display = 'block'; resultEl.textContent = 'Running…'; }
  try {
    const r = await fetch('/api/mcp/call', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({tool, args})
    });
    if (!r.ok) {
      if (resultEl) resultEl.textContent = 'Server error ' + r.status;
      toast('Tool call failed: server error ' + r.status, 'err');
      return;
    }
    const j = await r.json();
    if (resultEl) resultEl.textContent = JSON.stringify(j, null, 2);
    if (j.ok) toast(`✅ ${tool} → ${j.duration_ms}ms`, 'ok', 2000);
    else toast(`❌ ${j.error}`, 'err');
  } catch(ex) {
    if (resultEl) resultEl.textContent = 'Error: ' + ex.message;
    toast('Tool call error: ' + ex.message, 'err');
  }
}

async function runAgentWithTools() {
  const prompt = document.getElementById('mcp-agent-prompt')?.value.trim();
  const agentId = document.getElementById('mcp-agent-sel')?.value || 'builder';
  const maxSteps = parseInt(document.getElementById('mcp-max-steps')?.value || '5');
  if (!prompt) { toast('Enter a prompt', 'warn'); return; }
  const btn = document.getElementById('mcp-agent-btn');
  const resultEl = document.getElementById('mcp-agent-result');
  btn.disabled = true; btn.textContent = '⏳ Running…';
  resultEl.style.display = 'block';
  resultEl.innerHTML = `<div style="color:var(--text-2);font-size:13px">Agent is working…</div>`;
  try {
  const r = await fetch('/api/mcp/agent/run', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({prompt, agent_id: agentId, max_steps: maxSteps})
  });
  if (!r.ok) {
    resultEl.innerHTML = `<div style="color:var(--danger)">Server error ${r.status}</div>`;
    btn.disabled = false; btn.textContent = '🤖 Run Agent';
    return;
  }
  const j = await r.json();
  resultEl.innerHTML = `
    <div style="margin-bottom:10px;font-size:13px;font-weight:700">${j.ok?'✅':'❌'} ${j.step_count} steps</div>
    ${(j.steps||[]).map((s,i) => `<div style="background:var(--bg-3);border-radius:var(--radius-sm);padding:8px;margin-bottom:6px;font-size:12px">
      <div style="font-weight:700;margin-bottom:3px">Step ${s.step}: <span style="color:var(--accent)">${s.type}</span>${s.tool?` → ${s.tool}`:''}</div>
      ${s.output?`<div style="color:var(--text-1);white-space:pre-wrap;max-height:80px;overflow:hidden">${escHtml((s.output||'').slice(0,200))}</div>`:''}
      ${s.error?`<div style="color:var(--red)">${escHtml(s.error)}</div>`:''}
    </div>`).join('')}
    ${j.final_answer?`<div style="background:var(--accent-glow);border:1px solid var(--accent);border-radius:var(--radius-sm);padding:10px;font-size:13px">
      <div style="font-weight:700;margin-bottom:5px">Final Answer</div>
      <div>${renderMarkdown(j.final_answer)}</div>
    </div>`:''}`;
  btn.disabled = false; btn.textContent = '🤖 Run Agent';
  if (j.ok) toast(`✅ Agent done in ${j.step_count} steps`, 'ok');
  } catch(ex) {
    resultEl.innerHTML = `<div style="color:var(--danger)">Error: ${escHtml(ex.message)}</div>`;
    btn.disabled = false; btn.textContent = '🤖 Run Agent';
  }
}

// ── Loops Panel ───────────────────────────────────────────────────
async function renderLoops() {
  const pane = document.getElementById('pane-loops');
  pane.innerHTML = `<div class="section-head">
    <div><h2>♾️ Autonomous Loops</h2><p>Schedule agents to run repeatedly. They wake on a timer, continue working, and commit results.</p></div>
    <button onclick="refreshLoops()" class="btn btn-ghost btn-sm">⟳ Refresh</button>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
    <div class="settings-card">
      <h3>Create Loop</h3>
      <p>Define a recurring autonomous task.</p>
      <label style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px">Goal / Prompt</label>
      <textarea id="loop-prompt" placeholder="/goal Monitor the preview app for errors and auto-fix them every 15 minutes" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px;color:var(--text-0);font-size:13px;resize:none;min-height:80px;outline:none;font-family:inherit;margin:6px 0 10px"></textarea>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
        <div>
          <label style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px;display:block;margin-bottom:4px">Agent</label>
          <select id="loop-agent" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px;color:var(--text-0);font-size:12.5px;outline:none">
            ${S.agents.map(a=>`<option value="${a.id}">${a.avatar||'🤖'} ${escHtml(a.name)}</option>`).join('')}
          </select>
        </div>
        <div>
          <label style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px;display:block;margin-bottom:4px">Every (minutes)</label>
          <input id="loop-interval" type="number" value="15" min="1" max="1440" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px;color:var(--text-0);font-size:12.5px;outline:none">
        </div>
      </div>
      <button onclick="createLoop()" class="btn btn-primary" style="width:100%">♾️ Start Loop</button>
    </div>
    <div>
      <div class="settings-card">
        <h3>Running Loops</h3>
        <div id="loop-list" style="display:flex;flex-direction:column;gap:8px">
          <div style="color:var(--text-3);font-size:13px">Loading…</div>
        </div>
      </div>
      <div class="settings-card" style="margin-top:12px">
        <h3>Built-in Auto-Jobs</h3>
        <p style="font-size:12px;color:var(--text-2)">These run automatically in the background.</p>
        <div style="display:flex;flex-direction:column;gap:6px;font-size:12px">
          ${[
            ['Memory FTS reindex','Every 30 min','memory'],
            ['Daily standup journal','8:00 AM daily','brain'],
            ['Cost digest log','Every 6 hours','brain'],
            ['Agent status cleanup','Every 5 min','system'],
          ].map(([name,sched,agent])=>`
          <div style="display:flex;align-items:center;gap:8px;padding:6px 10px;background:var(--bg-3);border-radius:var(--radius-sm)">
            <span style="color:var(--green)">●</span>
            <span style="flex:1;font-weight:600">${name}</span>
            <span style="color:var(--text-2)">${sched}</span>
            <span class="tag">${agent}</span>
          </div>`).join('')}
        </div>
      </div>
    </div>
  </div>`;
  refreshLoops();
}

async function refreshLoops() {
  try {
    const r = await fetch('/api/loops');
    const loops = await r.json();
    const el = document.getElementById('loop-list');
    // update count badge
    const badge = document.getElementById('loop-count');
    if (badge) badge.textContent = loops.length;
    if (!el) return;
    if (!loops.length) {
      el.innerHTML = '<div style="color:var(--text-3);font-size:13px">No loops running. Create one ←</div>';
      return;
    }
    el.innerHTML = loops.map(l => `
      <div style="background:var(--bg-3);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
          <span style="color:var(--green);font-size:10px">●</span>
          <span style="font-weight:700;font-size:12.5px;flex:1">${escHtml(l.id)}</span>
          <span class="tag">${l.interval_minutes}min</span>
          <button onclick="pauseLoop(${JSON.stringify(l.id)})" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:11px" title="Pause">${l.status==='paused'?'▶ Resume':'⏸ Pause'}</button>
          <button onclick="stopLoop(${JSON.stringify(l.id)})" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:11px">Stop</button>
        </div>
        <div style="font-size:12px;color:var(--text-2);margin-bottom:3px">${escHtml((l.prompt||'').slice(0,100))}</div>
        <div style="font-size:11px;color:var(--text-3)">Runs: ${l.run_count||0} · Next: ${l.next_run?new Date(l.next_run).toLocaleTimeString():'—'}${l.status==='paused'?' · <span style="color:var(--warning)">PAUSED</span>':''}</div>
      </div>`).join('');
  } catch(e) { }
}

async function createLoop() {
  const prompt = document.getElementById('loop-prompt')?.value.trim();
  const agent_id = document.getElementById('loop-agent')?.value || 'builder';
  const interval = parseInt(document.getElementById('loop-interval')?.value || '15');
  if (!prompt) { toast('Enter a goal/prompt', 'warn'); return; }
  try {
    const r = await fetch('/api/loops', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({prompt, agent_id, interval_minutes: interval})
    });
    if (!r.ok) { toast('Server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) {
      toast(`♾️ Loop started: ${j.job_id}`, 'ok');
      document.getElementById('loop-prompt').value = '';
      refreshLoops();
    } else {
      toast('Error: ' + (j.error||'unknown'), 'err');
    }
  } catch(ex) { toast('Network error: ' + ex.message, 'err'); }
}

async function pauseLoop(jobId) {
  const loop = document.querySelector(`[data-loop-id="${jobId}"]`);
  // Determine current state by checking list
  try {
    const r = await fetch('/api/loops');
    if (!r.ok) return;
    const loops = await r.json();
    const l = loops.find(x => x.id === jobId);
    const isPaused = l && l.status === 'paused';
    const endpoint = isPaused ? 'resume' : 'pause';
    const resp = await fetch(`/api/loops/${encodeURIComponent(jobId)}/${encodeURIComponent(endpoint)}`, {method:'POST'});
    if (!resp.ok) { toast('Server error ' + resp.status, 'err'); return; }
    const d = await resp.json();
    if (d.ok) { toast(isPaused ? '▶ Loop resumed' : '⏸ Loop paused', 'ok', 1500); refreshLoops(); }
    else toast('Error: ' + (d.error||''), 'err');
  } catch(ex) { toast('Error: ' + ex.message, 'err'); }
}

async function stopLoop(jobId) {
  const ok = await gmDanger(`Stop loop "${jobId}"? This cannot be undone.`);(`Stop loop "${jobId}"? This cannot be undone.`);
  if (!ok) return;
  try {
    const r = await fetch(`/api/loops/${encodeURIComponent(jobId)}`, {method:'DELETE'});
    if (!r.ok) { toast('Server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast('Loop stopped', 'ok', 1500); refreshLoops(); }
    else toast('Error: ' + (j.error||''), 'err');
  } catch(ex) { toast('Network error: ' + ex.message, 'err'); }
}

// ── Extend nav() to handle Sprint 2+3 panes ───────────────────────
const _origNav = nav;
nav = function(pane) {
  _origNav(pane);
  if (pane === 'mcp')       renderMCP();
  if (pane === 'loops')     renderLoops();
  if (pane === 'dashboard') renderDashboard();
  if (pane === 'skills')    renderSkills();
  if (pane === 'deploy')    renderDeploy();
};

// ── Voice agent (Web Speech API) ──────────────────────────────────
let mediaRecognition = null;
let isListening = false;

function initVoice() {
  if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
    toast('Voice not supported in this browser. Use Chrome or Edge.', 'warn', 4000);
    return null;
  }
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  mediaRecognition = new SR();
  mediaRecognition.continuous    = false;
  mediaRecognition.interimResults = true;
  mediaRecognition.lang          = 'en-US';
  mediaRecognition.onresult = e => {
    const transcript = Array.from(e.results).map(r => r[0].transcript).join('');
    document.getElementById('chat-input').value = transcript;
    autoResizeInput(document.getElementById('chat-input'));
    if (e.results[0].isFinal) {
      isListening = false;
      updateVoiceBtn(false);
      sendChat();
    }
  };
  mediaRecognition.onerror = e => {
    toast('Voice error: ' + e.error, 'err', 2000);
    isListening = false;
    updateVoiceBtn(false);
  };
  mediaRecognition.onend = () => { isListening = false; updateVoiceBtn(false); };
  return mediaRecognition;
}

function toggleVoice() {
  if (!mediaRecognition) mediaRecognition = initVoice();
  if (!mediaRecognition) return;
  if (isListening) {
    mediaRecognition.stop();
    isListening = false;
    updateVoiceBtn(false);
  } else {
    mediaRecognition.start();
    isListening = true;
    updateVoiceBtn(true);
    toast('🎤 Listening… speak your message', 'ok', 2000);
  }
}

function updateVoiceBtn(listening) {
  const btn = document.getElementById('voice-btn');
  if (!btn) return;
  btn.textContent = listening ? '🔴 Stop' : '🎤 Voice';
  btn.classList.toggle('active', listening);
}

// Add voice button to chat tools dynamically
document.addEventListener('DOMContentLoaded', () => {});
(function addVoiceBtn() {
  const tools = document.querySelector('.chat-tools');
  if (!tools) { setTimeout(addVoiceBtn, 500); return; }
  const btn = document.createElement('button');
  btn.className = 'chat-tool';
  btn.id = 'voice-btn';
  btn.textContent = '🎤 Voice';
  btn.title = 'Voice input — speak your message';
  btn.onclick = toggleVoice;
  tools.appendChild(btn);
})();

// ── E2E Auto-fix (wired to builder pane) ──────────────────────────
async function runE2E(target = 'web') {
  // FIX A: delegate to runE2EFull (old implementation called wrong /api/mcp endpoint)
  return runE2EFull(target);
}
// Add E2E button to builder tabs area
(function addE2EBtn() {
  const tabsRow = document.querySelector('.builder-tabs');
  if (!tabsRow) { setTimeout(addE2EBtn, 600); return; }
  if (document.getElementById('e2e-btn')) return;
  const btn = document.createElement('button');
  btn.id = 'e2e-btn';
  btn.className = 'btn btn-ghost btn-sm';
  btn.style.margin = '5px';
  btn.textContent = '🧪 E2E';
  btn.title = 'Run E2E auto-fix loop';
  btn.onclick = () => runE2E('web');
  tabsRow.appendChild(btn);
})();

// ═══════════════════════════════════════════════════════════════
//  SPRINT 3 — Dashboard, Skills, Deploy, E2E, TTS
// ═══════════════════════════════════════════════════════════════

// ── Dashboard ─────────────────────────────────────────────────────
let dashData = null;
let _dashRefreshTimer = null;

async function renderDashboard() {
  const pane = document.getElementById('pane-dashboard');
  if (!pane) return;
  pane.innerHTML = `
    <div class="section-head">
      <div><h2>📊 Dashboard</h2><p>Real-time analytics — cost, tasks, memory, agents, swarm, E2E</p></div>
      <div style="display:flex;gap:6px;align-items:center">
        <select id="dash-days" onchange="renderDashboard()" style="background:var(--bg-3);border:1px solid var(--border);border-radius:6px;color:var(--text-1);font-size:12px;padding:4px 8px">
          <option value="7">7 days</option>
          <option value="30" selected>30 days</option>
          <option value="90">90 days</option>
        </select>
        <button onclick="exportDashboardCSV()" class="btn-sm" title="Export CSV">⬇ CSV</button>
        <button onclick="renderDashboard()" class="btn btn-ghost btn-sm">⟳ Refresh</button>
      </div>
    </div>
    <div id="dash-body" style="color:var(--text-2);font-size:13px">Loading…</div>`;

  const days = document.getElementById('dash-days')?.value || '30';
  try {
    const r = await fetch(`/api/analytics/dashboard?days=${days}`);
    if (!r.ok) {
      const el = document.getElementById('dash-body');
      if (el) el.innerHTML = `<div style="color:var(--danger)">Failed to load analytics (HTTP ${r.status})<br><button class="btn-sm" onclick="renderDashboard()" style="margin-top:6px">↻ Retry</button></div>`;
      return;
    }
    dashData = await r.json();
    renderDashBody(dashData);
  } catch(ex) {
    const el = document.getElementById('dash-body');
    if (el) el.innerHTML = `<div style="color:var(--danger)">Failed to load: ${ex?.message||String(ex)}<br><button class="btn-sm" onclick="renderDashboard()" style="margin-top:6px">↻ Retry</button></div>`;
  }
  // Auto-refresh every 30s
  clearTimeout(_dashRefreshTimer);
  _dashRefreshTimer = setTimeout(() => {
    const db = document.getElementById('dash-body');
    if (db && db.closest('[style*="display:none"]') === null) renderDashboard();
  }, 30000);
}

async function exportDashboardCSV() {
  try {
    const days = document.getElementById('dash-days')?.value || '30';
    const r = await fetch(`/api/analytics/export?fmt=csv&days=${days}`);
    if (!r.ok) { showToast('Export failed: HTTP '+r.status); return; }
    const text = await r.text();
    const blob = new Blob([text], {type:'text/csv'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `analytics-${days}d.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
    showToast('✅ Dashboard exported as CSV');
  } catch(ex) { showToast('Export error: '+ex?.message); }
}

function renderDashBody(d) {
  const el = document.getElementById('dash-body');
  if (!el) return;
  if (!d || !d.kpis) {
    el.innerHTML = '<div style="color:var(--danger)">Invalid dashboard data received</div>';
    return;
  }
  const k = d.kpis;

  const kpiCard = (icon, label, value, sub, color) => {
    color = color || 'var(--text-0)';
    return `<div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:16px">
      <div style="font-size:11px;color:var(--text-2);font-weight:700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">${icon} ${label}</div>
      <div style="font-size:26px;font-weight:800;color:${color};line-height:1">${value}</div>
      ${sub?`<div style="font-size:11px;color:var(--text-2);margin-top:4px">${sub}</div>`:''}
    </div>`;
  };

  const bar = (label, val, max, color) => {
    color = color || 'var(--accent)';
    const pct = max ? Math.min(100, Math.round(val / max * 100)) : 0;
    return `<div style="margin-bottom:8px">
      <div style="display:flex;justify-content:space-between;font-size:11.5px;margin-bottom:3px">
        <span style="color:var(--text-1)">${escHtml(String(label))}</span>
        <span style="color:var(--text-2)">${val}</span>
      </div>
      <div style="height:6px;background:var(--bg-3);border-radius:99px;overflow:hidden">
        <div style="width:${pct}%;height:100%;background:${color};border-radius:99px;transition:width .4s ease"></div>
      </div></div>`;
  };

  const agents = d.agents || [];
  const maxMsgs = agents.length ? Math.max(...agents.map(a => a.messages||0), 1) : 1;
  const costByAgent = d.cost?.by_agent || [];
  const maxCost = costByAgent.length ? Math.max(...costByAgent.map(a => a.cost||0), 0.0001) : 0.0001;

  el.innerHTML = `
  <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(155px,1fr));gap:12px;margin-bottom:24px">
    ${kpiCard('💰','Total Cost','$'+(k.total_cost_usd||0).toFixed(4),'Saved $'+(k.saved_vs_saas_usd||0)+' vs SaaS','var(--success)')}
    ${kpiCard('🔤','Tokens Used',(k.total_tokens||0).toLocaleString(),(k.total_messages||0)+' messages')}
    ${kpiCard('🧠','Memories',(k.total_memories||0).toLocaleString(),'in Memory Galaxy','var(--purple)')}
    ${kpiCard('📋','Tasks',(k.total_tasks||0),(k.completion_rate||0)+'% complete','var(--warning)')}
    ${kpiCard('✅','Done Tasks',(k.done_tasks||0),'of '+(k.total_tasks||0)+' total','var(--success)')}
    ${kpiCard('🌀','Swarm Runs',(k.swarm_runs||0),'multi-agent fan-outs','var(--orange)')}
    ${kpiCard('🧪','E2E Runs',(k.e2e_runs||0),(k.e2e_pass_rate||0)+'% pass rate','var(--teal)')}
    ${kpiCard('📁','File Versions',(k.file_versions||0),(k.versions_today||0)+' today','var(--accent)')}
  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:16px">
      <div style="font-weight:700;margin-bottom:12px;font-size:13px">🤖 Agent Activity</div>
      ${agents.length ? agents.slice(0,8).map(a => bar((a.avatar||'🤖')+' '+(a.name||a.id||'?'), a.messages||0, maxMsgs, a.color||'var(--accent)')).join('') : '<div style="color:var(--text-3);font-size:12px">No agent activity yet</div>'}
    </div>
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:16px">
      <div style="font-weight:700;margin-bottom:12px;font-size:13px">📋 Task Status</div>
      ${[['todo','To Do','var(--accent)'],['doing','Doing','var(--warning)'],['blocked','Blocked','var(--danger)'],['done','Done','var(--success)']].map(([s,l,c]) => bar(l, (d.tasks?.by_status||{})[s]||0, k.total_tasks||1, c)).join('')}
      <div style="margin-top:12px;font-weight:700;margin-bottom:8px;font-size:12px;color:var(--text-2)">By Agent</div>
      ${(d.tasks?.by_agent||[]).slice(0,5).map(a => bar(escHtml(a.agent||'?'), a.done||0, a.total||1, 'var(--success)')).join('')}
    </div>
  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:16px">
      <div style="font-weight:700;margin-bottom:12px;font-size:13px">🌌 Memory Sources</div>
      ${(d.memory?.by_source||[]).length ? (d.memory.by_source||[]).slice(0,8).map(s => bar(s.source||'?', s.count||0, d.memory?.total||1, 'var(--purple)')).join('') : '<div style="color:var(--text-3);font-size:12px">No memory data yet</div>'}
    </div>
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:16px">
      <div style="font-weight:700;margin-bottom:10px;font-size:13px">🧪 E2E &amp; Cost</div>
      ${bar('E2E Pass Rate', (d.e2e?.pass_count||0)+'/'+(d.e2e?.total_runs||0), Math.max(d.e2e?.total_runs||1,1), 'var(--success)')}
      <div style="margin-top:10px;font-size:12px;font-weight:700;color:var(--text-2);margin-bottom:6px">💰 Cost by Agent</div>
      ${costByAgent.slice(0,4).map(a => bar(escHtml(a.agent||'?'), '$'+(a.cost||0).toFixed(4), maxCost, 'var(--warning)')).join('') || '<div style="color:var(--text-3);font-size:12px">No cost data yet</div>'}
    </div>
  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:16px">
      <div style="font-weight:700;margin-bottom:10px;font-size:13px">🌀 Swarm Wins</div>
      ${(d.swarm?.wins_by_agent||[]).length ? (d.swarm.wins_by_agent||[]).map(w => `<div style="display:flex;justify-content:space-between;font-size:12.5px;padding:4px 0;border-bottom:1px solid var(--border)"><span>${escHtml(w.winner||'?')}</span><span style="color:var(--warning);font-weight:700">${w.wins} wins</span></div>`).join('') : '<div style="color:var(--text-3);font-size:12px">Run a swarm to see winners here</div>'}
    </div>
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:16px">
      <div style="font-weight:700;margin-bottom:8px;font-size:13px">⚡ Recent Activity</div>
      ${(d.activity?.recent||[]).slice(0,8).map(a => `<div style="font-size:11.5px;padding:3px 0;color:var(--text-2);border-bottom:1px solid var(--border)"><span style="color:var(--accent)">${escHtml(a.action||'')}</span>${a.detail?` · ${escHtml((a.detail||'').slice(0,40))}`:''}<span style="float:right;color:var(--text-3)">${(a.ts||'').slice(11,16)}</span></div>`).join('') || '<div style="color:var(--text-3);font-size:12px">No recent activity</div>'}
    </div>
  </div>`;
}
// ── Skills Hub ────────────────────────────────────────────────────
let allSkills = [], activeSkill = null, skillCategory = 'all';

async function renderSkills() {
  const pane = document.getElementById('pane-skills');
  if (!pane) return;
  pane.innerHTML = `<div class="section-head">
    <div><h2>⚡ Skills Hub</h2><p>12 pre-built AI skills + create your own. Run any skill with one click.</p></div>
    <button onclick="openCreateSkill()" class="btn btn-primary btn-sm">＋ New Skill</button>
  </div>
  <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px" id="skill-cats"></div>
  <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px" id="skill-grid"></div>
  <!-- Run modal -->
  <div id="skill-run-modal" style="display:none;position:fixed;inset:0;background:rgba(4,6,14,.85);z-index:9000;align-items:center;justify-content:center;backdrop-filter:blur(6px)" onclick="if(event.target===this)closeSkillModal()">
    <div style="background:var(--bg-2);border:1px solid var(--border-hi);border-radius:var(--radius-lg);width:100%;max-width:600px;padding:24px;max-height:85vh;overflow-y:auto">
      <h2 id="srm-title" style="font-size:18px;font-weight:800;margin-bottom:6px"></h2>
      <p id="srm-desc" style="font-size:13px;color:var(--text-2);margin-bottom:18px"></p>
      <div id="srm-inputs" style="margin-bottom:16px"></div>
      <div style="display:flex;gap:8px;margin-bottom:16px">
        <button onclick="execSkill()" class="btn btn-primary" style="flex:1" id="srm-run">▶ Run Skill</button>
        <button onclick="closeSkillModal()" class="btn btn-ghost">Cancel</button>
      </div>
      <div id="srm-result" style="display:none;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:14px;font-size:13px;line-height:1.6;max-height:400px;overflow-y:auto"></div>
    </div>
  </div>`;

  await loadSkills();
}

async function loadSkills() {
  try {
    const [sData, cData] = await Promise.all([
      fetch('/api/skills').then(r=>r.ok?r.json():{skills:[]}).catch(()=>({skills:[]})),
      fetch('/api/skills/categories').then(r=>r.ok?r.json():{categories:[]}).catch(()=>({categories:[]}))
    ]);
    allSkills = Array.isArray(sData) ? sData : (Array.isArray(sData?.skills) ? sData.skills : []);
    const cats = Array.isArray(cData) ? cData : (Array.isArray(cData?.categories) ? cData.categories : []);
    // Render category pills
    const catEl = document.getElementById('skill-cats');
    if (catEl) catEl.innerHTML =
      `<span class="tag ${skillCategory==='all'?'blue':''}" data-cat="all" style="cursor:pointer;padding:5px 12px" onclick="filterSkills('all')">All (${allSkills.length})</span>` +
      cats.map(c => `<span class="tag ${skillCategory===c.id?'blue':''}" data-cat="${c.id}" style="cursor:pointer;padding:5px 12px" onclick="filterSkills('${escHtml(c.id)}')">${escHtml(c.id)} (${c.count})</span>`).join('');
    renderSkillGrid();
  } catch(e) { console.warn('Failed to load skills:', e); toast('Loaded offline skills', 'ok'); }
}

function filterSkills(cat) {
  skillCategory = cat;
  document.querySelectorAll('#skill-cats .tag').forEach(el => {
    const elCat = el.dataset.cat || (el.textContent.startsWith('All') ? 'all' : '');
    el.classList.toggle('blue', elCat === cat);
  });
  renderSkillGrid();
}

function renderSkillGrid() {
  const grid = document.getElementById('skill-grid');
  if (!grid) return;
  const filtered = skillCategory === 'all' ? allSkills : allSkills.filter(s => s.category === skillCategory);
  grid.innerHTML = filtered.map(s => `
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:16px;cursor:pointer;transition:var(--transition)"
         onmouseover="this.style.borderColor='var(--border-hi)'" onmouseout="this.style.borderColor='var(--border)'"
         onclick="openSkillModal(${JSON.stringify(s.id)})">
      <div style="font-size:24px;margin-bottom:8px">${s.emoji||'⚡'}</div>
      <div style="font-weight:700;font-size:14px;margin-bottom:4px">${escHtml(s.name)}</div>
      <div style="font-size:12px;color:var(--text-2);margin-bottom:10px;min-height:32px">${escHtml(s.description||'')}</div>
      <div style="display:flex;align-items:center;justify-content:space-between">
        <span class="tag">${s.category||'general'}</span>
        <span style="font-size:11px;color:var(--text-2)">🤖 ${s.agent||'brain'}</span>
      </div>
    </div>`).join('');
}

function openSkillModal(skillId) {
  activeSkill = allSkills.find(s => s.id === skillId);
  if (!activeSkill) return;
  document.getElementById('srm-title').textContent = `${activeSkill.emoji||'⚡'} ${activeSkill.name}`;
  document.getElementById('srm-desc').textContent  = activeSkill.description || '';
  // Build inputs
  const inputsEl = document.getElementById('srm-inputs');
  inputsEl.innerHTML = (activeSkill.inputs||[]).map(inp => `
    <div style="margin-bottom:12px">
      <label style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px;display:block;margin-bottom:5px">
        ${escHtml(inp.label)}${inp.required?` <span style="color:var(--red)">*</span>`:''}
      </label>
      ${inp.type === 'textarea'
        ? `<textarea id="si-${inp.id}" placeholder="${escHtml(inp.label)}…" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px;color:var(--text-0);font-size:13px;resize:vertical;min-height:80px;outline:none;font-family:inherit"></textarea>`
        : inp.type === 'select'
        ? `<select id="si-${inp.id}" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px;color:var(--text-0);font-size:13px;outline:none">
             ${(inp.options||[]).map(o=>`<option value="${o}">${o}</option>`).join('')}
           </select>`
        : `<input id="si-${inp.id}" type="text" placeholder="${escHtml(inp.label)}…" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px;color:var(--text-0);font-size:13px;outline:none">`
      }
    </div>`).join('') || '<div style="color:var(--text-2);font-size:13px">No inputs required — click Run to execute.</div>';
  document.getElementById('srm-result').style.display = 'none';
  document.getElementById('skill-run-modal').style.display = 'flex';
}

function closeSkillModal() {
  document.getElementById('skill-run-modal').style.display = 'none';
  activeSkill = null;
}

async function execSkill() {
  if (!activeSkill) return;
  // Collect inputs
  const inputs = {};
  (activeSkill.inputs||[]).forEach(inp => {
    const el = document.getElementById('si-' + inp.id);
    if (el) inputs[inp.id] = el.value;
  });
  // Validate required
  const missing = (activeSkill.inputs||[]).filter(i => i.required && !inputs[i.id]?.trim());
  if (missing.length) { toast('Required: ' + missing.map(m=>m.label).join(', '), 'warn'); return; }

  const btn = document.getElementById('srm-run');
  btn.disabled = true; btn.textContent = '⏳ Running…';
  const resEl = document.getElementById('srm-result');
  resEl.style.display = 'block';
  resEl.innerHTML = `<div style="color:var(--text-2)">Running ${activeSkill.name}…</div>`;

  try {
    const r = await fetch('/api/skills/run', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ skill_id: activeSkill.id, inputs })
    });
    if (!r.ok) throw new Error('Server error ' + r.status);
    const j = await r.json();
    resEl.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
        <span style="color:${j.ok?'var(--green)':'var(--red)'};">${j.ok?'✅':'❌'}</span>
        <span style="font-size:12px;color:var(--text-2)">${escHtml(j.agent||'')} · ${j.latency_ms||0}ms · ${j.tokens||0} tokens · $${(j.cost||0).toFixed(5)}</span>
        <button onclick="speakText(${JSON.stringify((j.output||'').slice(0,1000)).replace(/'/g,'&#39;')}, '${j.agent||'default'}')" class="btn btn-ghost btn-sm" style="margin-left:auto">🔊 Listen</button>
      </div>
      <div style="white-space:pre-wrap;line-height:1.6">${renderMarkdown(j.output||'(empty)')}</div>`;
    if (j.ok) toast(`✅ ${activeSkill.name} complete · ${j.latency_ms}ms`, 'ok', 3000);
    else toast('Skill error: ' + (j.error||'check output'), 'err');
  } catch(e) {
    resEl.innerHTML = `<div style="color:var(--red)">Error: ${e.message}</div>`;
    toast('Skill failed', 'err');
  } finally {
    btn.disabled = false; btn.textContent = '▶ Run Skill';
  }
}

async function openCreateSkill() {
  const name = await gmPrompt('New Skill', 'Skill name (e.g. "LinkedIn Post Writer")');
  if (!name) return;
  const prompt_tmpl = await gmPrompt('Prompt Template', 'Use {placeholder} for inputs\ne.g. "Write a {tone} email about {topic}"', '', true);
  if (prompt_tmpl === null) return;
  const agent = await gmPrompt('Agent', 'e.g. brain, builder, researcher', 'brain') || 'brain';
  try {
    const r = await fetch('/api/skills', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ name, prompt_template: prompt_tmpl||'{prompt}', agent, category: 'custom', emoji: '⚡',
        inputs: [{id:'prompt',label:'Your input',type:'textarea',required:true}] })
    });
    if (!r.ok) { toast('Server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast(`✅ Skill "${name}" created`, 'ok'); loadSkills(); }
    else toast('Error: ' + (j.error||'unknown error'), 'err');
  } catch(ex) { toast('Failed to create skill: ' + ex.message, 'err'); }
}
window.renderSkills = renderSkills;
window.loadSkills = loadSkills;
window.filterSkills = filterSkills;
window.renderSkillGrid = renderSkillGrid;
window.openSkillModal = openSkillModal;
window.closeSkillModal = closeSkillModal;
window.execSkill = execSkill;
window.openCreateSkill = openCreateSkill;

// ── Deploy Panel ──────────────────────────────────────────────────
async function renderDeploy() {
  const pane = document.getElementById('pane-deploy');
  let statusData = {};
  try {
    const r = await fetch('/api/deploy/status');
    statusData = await r.json();
  } catch(e) {}

  const providerCard = (id, name, icon, ready, token_key, docs_url, hint) => {
    const btnLabel = ready ? `🚀 Deploy to ${name}` : `⚙️ Setup ${name}`;
    return `<div style="background:var(--bg-2);border:1px solid ${ready?'var(--accent)':'var(--border)'};border-radius:var(--radius-lg);padding:20px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <span style="font-size:24px">${icon}</span>
        <div>
          <div style="font-weight:700;font-size:15px">${name}</div>
          <div style="font-size:11.5px;color:var(--text-2)">${hint}</div>
        </div>
        <span class="tag ${ready?'green':''}" style="margin-left:auto">${ready?'Ready':'Setup needed'}</span>
      </div>
      ${!ready ? `<div style="background:var(--bg-1);border-radius:var(--radius-sm);padding:10px;font-size:12px;margin-bottom:10px;color:var(--text-2)">
        Add <code style="background:var(--bg-0);padding:1px 5px;border-radius:3px">${token_key}</code> to your .env or 🔐 Vault, then restart.
        <a href="${docs_url}" target="_blank" style="color:var(--accent);display:block;margin-top:4px">→ Get token</a>
      </div>` : ''}
      <button onclick="doDeploy(${JSON.stringify(id)})" class="btn ${ready?'btn-primary':'btn-ghost'}" style="width:100%" id="deploy-btn-${id}">${btnLabel}</button>
      <div id="deploy-result-${id}" style="margin-top:10px;display:none"></div>
    </div>`;
  };

  pane.innerHTML = `<div class="section-head">
    <div><h2>🚀 Deploy</h2><p>One-click deploy to Vercel, Netlify, or share via Cloudflare Tunnel</p></div>
    <button onclick="renderDeploy()" class="btn btn-ghost btn-sm">⟳ Refresh</button>
  </div>
  <div style="margin-bottom:16px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px 14px;font-size:13px;color:var(--text-2)">
    📁 <strong>${statusData.preview_files||0} files</strong> ready in <code style="background:var(--bg-0);padding:1px 5px;border-radius:3px">preview/</code>
    ${statusData.preview_files ? '' : ' — <a href="#" onclick="nav(\'builder\');return false" style="color:var(--accent)">Scaffold a project first</a>'}
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;margin-bottom:24px">
    ${providerCard('vercel','Vercel','▲',statusData.providers?.vercel?.ready,'VERCEL_TOKEN','https://vercel.com/account/tokens','Best for Next.js, React, static sites')}
    ${providerCard('netlify','Netlify','◈',statusData.providers?.netlify?.ready,'NETLIFY_TOKEN','https://app.netlify.com/user/applications','Great for static sites, auto HTTPS')}
  </div>
  <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:20px;margin-bottom:16px">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
      <span style="font-size:24px">☁️</span>
      <div><div style="font-weight:700">Cloudflare Tunnel</div>
      <div style="font-size:12px;color:var(--text-2)">Share localhost:8787 publicly via HTTPS — no signup needed</div></div>
      <span class="tag ${statusData.providers?.cloudflare?.ready?'green':''}" style="margin-left:auto">
        ${statusData.providers?.cloudflare?.ready?'cloudflared installed':'Not installed'}
      </span>
    </div>
    <button onclick="startTunnel()" class="btn btn-ghost" style="width:100%" id="tunnel-btn">🌐 Start Public Tunnel</button>
    <div id="tunnel-result" style="margin-top:10px;display:none"></div>
  </div>
  <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:20px">
    <div style="font-weight:700;margin-bottom:12px">📋 Deploy History</div>
    <div id="deploy-history">Loading…</div>
  </div>`;
  loadDeployHistory();
}

async function doDeploy(provider) {
  const btn = document.getElementById(`deploy-btn-${provider}`);
  const res = document.getElementById(`deploy-result-${provider}`);
  btn.disabled = true; btn.textContent = `⏳ Deploying to ${provider}…`;
  res.style.display = 'block';
  res.innerHTML = '<div style="color:var(--text-2);font-size:13px">Deploying…</div>';
  try {
    const r = await fetch(`/api/deploy/${encodeURIComponent(provider)}`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({})
    });
    if (!r.ok) throw new Error(`Server error ${r.status}`);
    const j = await r.json();
    if (j.ok) {
      const urlLink = j.url ? `<a href="${j.url}" target="_blank" style="color:var(--accent);font-size:13px;display:block;margin-top:4px">${j.url}</a>` : '';
      const output  = j.output ? `<div style="font-size:11px;color:var(--text-2);margin-top:4px;font-family:monospace;white-space:pre-wrap">${escHtml(j.output.slice(0,200))}</div>` : '';
      res.innerHTML = `<div style="color:var(--green);font-weight:700">✅ Deployed!</div>
        ${urlLink}
        ${output}
        <div style="font-size:11px;color:var(--text-2);margin-top:4px">${escHtml(j.tip||'')}</div>`;
      toast(`🚀 Deployed to ${provider}!`, 'ok', 5000);
    } else {
      const setup = j.setup ? '<div style="font-size:11.5px;color:var(--text-2);margin-top:6px">' + (j.setup||[]).map(s=>escHtml(s)).join('<br>') + '</div>' : '';
      const alt = j.alternative ? `<div style="font-size:11px;color:var(--accent);margin-top:6px">${escHtml(j.alternative)}</div>` : '';
      res.innerHTML = `<div style="color:var(--yellow)">⚠️ ${escHtml(j.error||'Setup required')}</div>${setup}${alt}`;
    }
  } catch(e) {
    res.innerHTML = `<div style="color:var(--red)">Error: ${escHtml(e.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = `🚀 Deploy to ${provider.charAt(0).toUpperCase()+provider.slice(1)}`;
  }
}

async function startTunnel() {
  const btn = document.getElementById('tunnel-btn');
  const res = document.getElementById('tunnel-result');
  btn.disabled = true; btn.textContent = '⏳ Starting tunnel…';
  res.style.display = 'block';
  res.innerHTML = '<div style="color:var(--text-2);font-size:13px">Connecting to Cloudflare…</div>';
  try {
    const r = await fetch('/api/deploy/tunnel', {method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    if (!r.ok) throw new Error(`Server error ${r.status}`);
    const j = await r.json();
    if (j.ok) {
      res.innerHTML = `<div style="color:var(--green);font-weight:700">✅ Tunnel active!</div>
        <a href="${j.url}" target="_blank" style="color:var(--accent);font-size:14px;display:block;margin-top:4px;font-weight:700">${j.url}</a>
        <div style="font-size:11.5px;color:var(--text-2);margin-top:4px">${escHtml(j.note||'')}</div>
        ${j.qr?`<img src="${j.qr}" style="margin-top:10px;border-radius:8px;width:120px">`:''} 
        <button onclick="stopTunnel()" class="btn btn-ghost btn-sm" style="margin-top:8px;color:var(--danger)">⛔ Stop Tunnel</button>`;
      toast('🌐 Tunnel started — share the URL!', 'ok', 6000);
    } else {
      const installs = j.install ? Object.entries(j.install).map(([k,v])=>`<div><strong>${k}:</strong> <code style="font-size:11px">${escHtml(v)}</code></div>`).join('') : '';
      const then_ = j.then ? `<div style="margin-top:6px;color:var(--text-2);font-size:12px">${escHtml(j.then)}</div>` : '';
      res.innerHTML = `<div style="color:var(--yellow)">⚠️ ${escHtml(j.error||'')}</div>${installs}${then_}`;
    }
  } catch(e) {
    res.innerHTML = `<div style="color:var(--red)">Error: ${escHtml(e.message)}</div>`;
  } finally {
    btn.disabled = false; btn.textContent = '🌐 Start Public Tunnel';
  }
}

async function stopTunnel() {
  try {
    const r = await fetch('/api/deploy/tunnel/stop', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    const j = await r.json();
    if (j.ok) {
      const res = document.getElementById('tunnel-result');
      if (res) res.innerHTML = '<div style="color:var(--text-2)">Tunnel stopped.</div>';
      toast('⛔ Tunnel stopped', 'ok', 2000);
    } else {
      toast('Stop failed: ' + (j.error||''), 'err');
    }
  } catch(ex) { toast('Error stopping tunnel: ' + ex.message, 'err'); }
}

async function loadDeployHistory() {
  try {
    const r = await fetch('/api/deploy/history');
    const j = await r.json();
    const el = document.getElementById('deploy-history');
    if (!el) return;
    if (!j.length) { el.innerHTML = '<div style="color:var(--text-3);font-size:13px">No deploys yet.</div>'; return; }
    el.innerHTML = j.slice(0,10).map(d =>
      `<div style="display:flex;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);font-size:12.5px">
        <span style="color:var(--green)">🚀</span>
        <span style="flex:1;color:var(--text-1)">${escHtml((d.content||'').slice(0,80))}</span>
        <span style="color:var(--text-3)">${(d.created_at||'').slice(0,10)}</span>
      </div>`
    ).join('');
  } catch(e) {
    const el = document.getElementById('deploy-history');
    if (el) el.innerHTML = '<div style="color:var(--text-3);font-size:13px">Could not load history.</div>';
  }
}

// ── TTS — speak any text ─────────────────────────────────────────
let ttsAudio = null;
let _ttsVolume = 1.0;  // 0.0 – 1.0

async function speakText(text, agentId = 'default') {
  if (!text || !text.trim()) return;

  // Stop any current playback
  stopSpeaking();

  try {
    const url = `/api/tts/speak?text=${encodeURIComponent(text.slice(0, 900))}&agent_id=${encodeURIComponent(agentId)}`;
    ttsAudio = new Audio(url);
    ttsAudio.volume = _ttsVolume;

    ttsAudio.onerror = () => {
      showToast('🔇 TTS unavailable — install edge-tts: pip install edge-tts');
      ttsAudio = null;
    };
    ttsAudio.onended = () => { ttsAudio = null; };

    await ttsAudio.play();
    showToast('🔊 Speaking…');
  } catch(ex) {
    showToast('TTS error: ' + (ex?.message || String(ex)));
    ttsAudio = null;
  }
}

function stopSpeaking() {
  if (ttsAudio) {
    ttsAudio.pause();
    ttsAudio.src = '';
    ttsAudio = null;
  }
}

function setTTSVolume(vol) {
  _ttsVolume = Math.max(0, Math.min(1, parseFloat(vol) || 1.0));
  if (ttsAudio) ttsAudio.volume = _ttsVolume;
}

// Auto-speak last agent message if voice mode is on
let voiceModeOn = false;
function toggleVoiceMode() {
  voiceModeOn = !voiceModeOn;
  const btn = document.getElementById('voice-mode-btn');
  if (btn) {
    btn.textContent = voiceModeOn ? '🔊 Voice' : '🔇 Voice';
    btn.classList.toggle('active', voiceModeOn);
  }
  showToast(voiceModeOn ? '🔊 Voice mode ON — agents will speak' : '🔇 Voice mode OFF');
}

// Patch updateMessageBubble to auto-TTS when voice mode on
const _origUpdateBubble = typeof updateMessageBubble !== 'undefined' ? updateMessageBubble : function(){};
updateMessageBubble = function(el, text) {
  _origUpdateBubble(el, text);
  if (voiceModeOn && text && text.length > 20) {
    // Debounce: only speak when streaming appears complete
    clearTimeout(window._ttsDebounce);
    window._ttsDebounce = setTimeout(() => {
      const agent = S?.currentAgent;
      speakText(text.slice(0, 700), agent?.id || 'default');
    }, 900);
  }
};

// Expose TTS status check
async function checkTTSStatus() {
  try {
    const r = await fetch('/api/tts/status');
    if (!r.ok) return null;
    return await r.json();
  } catch(e) { return null; }
}

// Load voice settings for agent voice picker
async function loadTTSVoices() {
  try {
    const r = await fetch('/api/tts/voices');
    if (!r.ok) return null;
    return await r.json();
  } catch(e) { return null; }
}

// Add voice mode + stop button to chat tools
(function addVoiceModeBtn() {
  const tools = document.querySelector('.chat-tools');
  if (!tools) { setTimeout(addVoiceModeBtn, 600); return; }
  if (document.getElementById('voice-mode-btn')) return;

  const btn = document.createElement('button');
  btn.className = 'chat-tool';
  btn.id        = 'voice-mode-btn';
  btn.textContent = '🔇 Voice';
  btn.title     = 'Voice mode — agents speak their replies';
  btn.onclick   = () => {
    voiceModeOn = !voiceModeOn;
    btn.textContent = voiceModeOn ? '🔊 Voice' : '🔇 Voice';
    btn.classList.toggle('active', voiceModeOn);
    if (!voiceModeOn) stopSpeaking();
    showToast(voiceModeOn ? '🔊 Agents will now speak' : '🔇 Voice mode off');
  };
  tools.appendChild(btn);

  // Stop button
  const stopBtn = document.createElement('button');
  stopBtn.className = 'chat-tool';
  stopBtn.id        = 'tts-stop-btn';
  stopBtn.textContent = '⏹';
  stopBtn.title     = 'Stop speaking';
  stopBtn.onclick   = stopSpeaking;
  tools.appendChild(stopBtn);
})();

// ── E2E in builder pane ───────────────────────────────────────────
async function runE2EFull(target = 'web') {
  const btn = document.getElementById('e2e-btn');
  if (btn) { btn.disabled = true; btn.textContent = '🧪 Running…'; }
  toast('🧪 Running E2E checks…', 'ok', 2000);
  try {
    const r = await fetch('/api/e2e/run', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ target })
    });
    const j = await r.json();
    const passed = j.passed, total = j.total, score = j.score;
    const color  = score >= 0.8 ? 'var(--green)' : score >= 0.5 ? 'var(--yellow)' : 'var(--red)';
    toast(`🧪 E2E: ${passed}/${total} passed (${Math.round(score*100)}%) via ${j.engine}`,
          score >= 0.8 ? 'ok' : 'warn', 5000);
    // Show trace in builder if pane active
    showE2ETrace(j);
    return j;
  } catch(e) {
    toast('E2E error: ' + e.message, 'err');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '🧪 E2E'; }
  }
}

function showE2ETrace(run) {
  const steps = run.trace_steps || [];
  if (!steps.length) return;
  const passed = run.passed, total = run.total;
  const scoreColor = run.score >= 0.8 ? 'var(--green)' : run.score >= 0.5 ? 'var(--yellow)' : 'var(--red)';
  const summary = steps.map(s => {
    const icon = s.status === 'pass' ? '✅' : s.status === 'warn' ? '⚠️' : s.status === 'skip' ? '⏭' : '❌';
    return `<div style="display:flex;align-items:center;gap:8px;padding:5px 8px;border-radius:6px;font-size:12px;${s.status!=='pass'?'background:var(--bg-3)':''}">
      <span>${icon}</span><span style="flex:1">${escHtml(s.step||s.step_name||'')}</span>
      <span style="color:var(--text-3)">${s.duration_ms||0}ms</span>
      ${s.error?`<span style="color:var(--red);font-size:10.5px">${escHtml((s.error||'').slice(0,60))}</span>`:''}
    </div>`;
  }).join('');

  // FIX B: show screenshots from Playwright steps when available
  const screenshots = steps
    .filter(s => s.screenshot_b64)
    .slice(0, 3)
    .map(s => `<img src="data:image/png;base64,${s.screenshot_b64}"
      title="${escHtml(s.step||s.step_name||'')}"
      style="width:100%;border-radius:6px;margin-top:6px;border:1px solid var(--border)"
      onerror="this.style.display='none'">`)
    .join('');

  // Show as a toast-like overlay in builder
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;bottom:60px;right:20px;width:360px;max-height:80vh;overflow-y:auto;background:var(--bg-2);border:1px solid var(--border-hi);border-radius:var(--radius-lg);padding:14px;z-index:8000;box-shadow:0 20px 60px rgba(0,0,0,.6)';
  overlay.innerHTML = `<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
    <span style="font-size:15px;font-weight:800">🧪 E2E Trace</span>
    <span style="color:${scoreColor};font-weight:700;margin-left:auto">${passed}/${total} · ${run.engine||'heuristic'}</span>
    <button onclick="this.parentElement.parentElement.remove()" style="background:none;border:none;color:var(--text-2);cursor:pointer;font-size:16px">×</button>
  </div>
  ${summary}
  ${screenshots}
  ${run.score < 0.8 ? '<button onclick="runAutofix(\'' + (run.target||'web') + '\')" class="btn btn-primary btn-sm" style="width:100%;margin-top:8px">🔧 Auto-fix</button>' : ''}`;
  document.body.appendChild(overlay);
  setTimeout(() => overlay.remove(), 15000);
}

async function runAutofix(target = 'web') {
  toast('🔧 Auto-fix loop starting…', 'ok', 2000);
  const r = await fetch('/api/e2e/autofix', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ target, max_iters: 3 })
  });
  const j = await r.json();
  const final = Math.round((j.final_score||0)*100);
  toast(`🔧 Auto-fix: ${j.status} · ${final}% pass rate · ${j.iterations?.length||0} iters`,
        j.ok ? 'ok' : 'warn', 5000);
  if (j.ok) {
    // Reload the current file in editor
    if (S.currentFile) openFile(S.currentFile);
  }
}

// Swap E2E button to use full runner
(function patchE2EBtn() {
  const btn = document.getElementById('e2e-btn');
  if (btn) { btn.onclick = () => runE2EFull('web'); return; }
  setTimeout(patchE2EBtn, 800);
})();

// ═══════════════════════════════════════════════════════════════
//  SPRINT 4 — Pipeline, Obsidian, System, Modal, HMR, Git
// ═══════════════════════════════════════════════════════════════

// ── Global Modal system (replaces all alert/confirm/prompt) ───────
let _gm_resolve = null;

function _gm_show({ title='', body='', input=false, textarea=false, placeholder='', buttons=[], value='' }) {
  return new Promise(resolve => {
    _gm_resolve = resolve;
    document.getElementById('gm-title').textContent = title;
    document.getElementById('gm-body').innerHTML    = body;
    const wrap  = document.getElementById('gm-input-wrap');
    const inp   = document.getElementById('gm-input');
    const ta    = document.getElementById('gm-textarea');
    wrap.style.display = (input||textarea) ? 'block' : 'none';
    inp.style.display  = input   ? 'block' : 'none';
    ta.style.display   = textarea? 'block' : 'none';
    if (input)    { inp.placeholder = placeholder; inp.value = value; }
    if (textarea) { ta.placeholder  = placeholder; ta.value  = value; }

    const btns = document.getElementById('gm-btns');
    btns.innerHTML = buttons.map((b,i) =>
      `<button class="btn ${b.primary?'btn-primary':b.danger?'btn-danger':'btn-ghost'}" onclick="_gm_click('${b.id||i}')">${b.label}</button>`
    ).join('');

    document.getElementById('gmodal').style.display = 'flex';
    setTimeout(() => (input ? inp : ta).focus?.(), 50);
    if (input) {
      inp.onkeydown = e => { if (e.key==='Enter') _gm_click('ok'); if (e.key==='Escape') _gm_cancel(); };
    }
  });
}
function _gm_click(id) {
  const val = document.getElementById('gm-input').value || document.getElementById('gm-textarea').value;
  document.getElementById('gmodal').style.display = 'none';
  _gm_resolve?.({ id, value: val });
  _gm_resolve = null;
}
function _gm_cancel() {
  document.getElementById('gmodal').style.display = 'none';
  _gm_resolve?.({ id: 'cancel', value: '' });
  _gm_resolve = null;
}

// Convenience wrappers
async function gmAlert(title, body='') {
  await _gm_show({ title, body, buttons:[{id:'ok',label:'OK',primary:true}] });
}
async function gmConfirm(title, body='') {
  const r = await _gm_show({ title, body, buttons:[{id:'cancel',label:'Cancel'},{id:'ok',label:'Confirm',primary:true}] });
  return r.id === 'ok';
}
async function gmPrompt(title, placeholder='', value='', textarea=false) {
  const r = await _gm_show({ title, input:!textarea, textarea, placeholder, value,
    buttons:[{id:'cancel',label:'Cancel'},{id:'ok',label:'OK',primary:true}] });
  return r.id === 'ok' ? r.value : null;
}
async function gmDanger(title, body, confirmLabel='Delete') {
  const r = await _gm_show({ title, body, buttons:[{id:'cancel',label:'Cancel'},{id:'ok',label:confirmLabel,danger:true}] });
  return r.id === 'ok';
}

// ── Extend nav() for Sprint 4 ──────────────────────────────────────
const _s3Nav = nav;
nav = function(pane) {
  _s3Nav(pane);
  if (pane === 'pipeline') renderPipeline();
  if (pane === 'obsidian') renderObsidian();
  if (pane === 'system')   renderSystem();
};

// ── Pipeline Pane ─────────────────────────────────────────────────
async function renderPipeline() {
  const pane = document.getElementById('pane-pipeline');
  let templates = [];
  try { const r = await fetch('/api/pipeline/templates'); const d = await r.json(); templates = Array.isArray(d) ? d : (Array.isArray(d.templates) ? d.templates : []); } catch(e){}

  pane.innerHTML = `<div class="section-head">
    <div><h2>🏛️ Pipeline</h2><p>Autonomous multi-stage: Goal → Research → Code → Review → Ship</p></div>
    <button onclick="loadPipelineHistory()" class="btn btn-ghost btn-sm">📋 History</button>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
    <div>
      <div class="settings-card">
        <h3>Goal</h3>
        <textarea id="pipe-goal" placeholder="Build a SaaS landing page with hero, pricing, and CTA sections using Tailwind CSS"
          style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;color:var(--text-0);font-size:13px;resize:none;min-height:90px;outline:none;font-family:inherit;margin-bottom:10px"></textarea>
        <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Stages</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px" id="pipe-stages">
          ${['goal','research','code','review','ship'].map(s => `
            <label style="display:flex;align-items:center;gap:5px;background:var(--bg-3);border-radius:var(--radius-sm);padding:5px 10px;cursor:pointer;font-size:12px;border:1px solid var(--border)">
              <input type="checkbox" data-stage="${s}" checked style="accent-color:var(--accent)">${s}
            </label>`).join('')}
        </div>
        <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Templates</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px">
          ${templates.map(t => `<button onclick="document.getElementById('pipe-goal').value=${JSON.stringify(t.goal)}" class="btn btn-ghost btn-sm">${t.label}</button>`).join('')}
        </div>
        <button onclick="runPipeline()" class="btn btn-primary" style="width:100%" id="pipe-run-btn">🏛️ Run Pipeline</button>
        <div id="pipe-status" style="font-size:12px;color:var(--text-2);margin-top:8px;min-height:18px"></div>
      </div>
    </div>
    <div id="pipe-results" style="overflow-y:auto;max-height:calc(100vh - 160px)">
      <div style="color:var(--text-3);font-size:13px;text-align:center;padding:40px">
        Run a pipeline → stage results appear here live
      </div>
    </div>
  </div>`;
}

async function runPipeline() {
  const goal = document.getElementById('pipe-goal')?.value.trim();
  if (!goal) { toast('Enter a goal first', 'warn'); return; }
  const stages = [...document.querySelectorAll('#pipe-stages input:checked')].map(i => i.dataset.stage);
  if (!stages.length) { toast('Select at least one stage', 'warn'); return; }

  const btn    = document.getElementById('pipe-run-btn');
  const status = document.getElementById('pipe-status');
  const results = document.getElementById('pipe-results');
  btn.disabled = true; btn.textContent = '⏳ Running pipeline…';
  status.textContent = 'Starting…';

  // Render skeleton
  results.innerHTML = stages.map(s => `
    <div id="pipe-card-${s}" class="settings-card" style="margin-bottom:12px;opacity:.5">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
        <span style="font-size:16px">${{goal:'🏛️',research:'🔭',code:'⚡',review:'🔨',ship:'🚀'}[s]||'⚙️'}</span>
        <span style="font-weight:700;text-transform:uppercase;font-size:12px">${s}</span>
        <span id="pipe-badge-${s}" class="tag" style="margin-left:auto">waiting</span>
      </div>
      <div id="pipe-out-${s}" style="font-size:12.5px;color:var(--text-2);line-height:1.6">…</div>
    </div>`).join('');

  try {
    const resp = await fetch('/api/pipeline/run', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ goal, stages, stream: true }),
    });
    if (!resp.ok) { throw new Error('Server error ' + resp.status); }
    if (!resp.body) { throw new Error('No response body (SSE not supported)'); }

    const reader  = resp.body.getReader();
    const decoder = new TextDecoder();
    let totalTokens = 0, totalCost = 0;
    let sseBuffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      sseBuffer += decoder.decode(value, { stream: true });
      // Process complete SSE messages (terminated by double newline)
      const messages = sseBuffer.split('\n\n');
      sseBuffer = messages.pop() || '';   // keep incomplete tail
      for (const msg of messages) {
        for (const line of msg.split('\n')) {
          if (!line.startsWith('data:')) continue;
          try {
            const ev = JSON.parse(line.slice(5).trim());
            if (ev.type === 'stage_start') {
              const badge = document.getElementById(`pipe-badge-${ev.stage}`);
              const card  = document.getElementById(`pipe-card-${ev.stage}`);
              if (badge) badge.textContent = 'running…';
              if (badge) badge.style.color = 'var(--yellow)';
              if (card)  card.style.opacity = '1';
              status.textContent = `Running ${ev.stage}…`;
            }
            if (ev.type === 'stage_done') {
              const badge = document.getElementById(`pipe-badge-${ev.stage}`);
              const out   = document.getElementById(`pipe-out-${ev.stage}`);
              if (badge) { badge.textContent = `✅ ${ev.result?.latency_ms||0}ms · ${ev.result?.tokens||0}t`; badge.style.color = 'var(--green)'; }
              if (out)   out.innerHTML = renderMarkdown(ev.result?.output || '(empty)');
              totalTokens += ev.result?.tokens || 0;
              totalCost   += ev.result?.cost   || 0;
            }
            if (ev.type === 'stage_error') {
              const badge = document.getElementById(`pipe-badge-${ev.stage}`);
              const out   = document.getElementById(`pipe-out-${ev.stage}`);
              if (badge) { badge.textContent = '❌ error'; badge.style.color = 'var(--red)'; }
              if (out)   out.textContent = ev.error || 'Stage failed';
            }
            if (ev.type === 'complete') {
              status.innerHTML = `✅ Done · ${ev.duration_ms}ms · ${totalTokens} tokens · $${totalCost.toFixed(5)}`;
              toast(`🏛️ Pipeline complete — ${stages.length} stages`, 'ok', 4000);
            }
          } catch(e) {}
        }
      }
    }
  } catch(e) {
    status.textContent = '✗ ' + e.message;
    toast('Pipeline error: ' + e.message, 'err');
  } finally {
    btn.disabled = false; btn.textContent = '🏛️ Run Pipeline';
  }
}

async function loadPipelineHistory() {
  try {
    const r = await fetch('/api/pipeline/history?limit=20');
    if (!r.ok) { gmAlert('Failed to load history: server error ' + r.status); return; }
    const j = await r.json();
    if (!j.length) { await gmAlert('Pipeline History', 'No pipeline runs yet.'); return; }
    const lines = j.map((h,i) => `${i+1}. [${h.ts}] ${(h.detail||'').slice(0,80)}`).join('\n');
    await gmAlert('📋 Pipeline History', `<pre style="font-size:12px;white-space:pre-wrap">${escHtml(lines)}</pre>`);
  } catch(ex) { gmAlert('Pipeline history error: ' + ex.message); }
}

// ── Obsidian Pane ─────────────────────────────────────────────────
async function renderObsidian() {
  const pane = document.getElementById('pane-obsidian');
  if (!pane) return;
  pane.innerHTML = `<div class="section-head"><div><h2>🧿 Obsidian Vault</h2><p>Bi-directional sync with your Obsidian vault → Memory Galaxy</p></div></div>
    <div id="obs-body"><div style="color:var(--text-2);font-size:13px">Loading…</div></div>`;
  try {
    const r = await fetch('/api/obsidian/status');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const s = await r.json();
    renderObsidianBody(s);
  } catch(e) {
    const el = document.getElementById('obs-body');
    if (el) el.innerHTML = `<div style="color:var(--danger)">Error loading Obsidian status: ${escHtml(e?.message||String(e))}<br><button class="btn-sm" onclick="renderObsidian()" style="margin-top:8px">↻ Retry</button></div>`;
  }
}

function renderObsidianBody(s) {
  const el = document.getElementById('obs-body');
  if (!el) return;
  el.innerHTML = `<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
    <div>
      <div class="settings-card">
        <h3>${s.connected ? '✅ Vault Connected' : '🧠 Brain / Vault'}</h3>
        <p style="font-size:12px;color:var(--text-2);margin-bottom:8px">
          ${s.connected
            ? `Path: <code style="font-size:11px;background:var(--bg-0);padding:2px 6px;border-radius:4px">${escHtml(s.vault_path||'')}</code>`
            : 'Using built-in <strong>brain/</strong> folder. Set <code>OBSIDIAN_VAULT_PATH</code> in .env for full Obsidian.'}
        </p>
        <div style="font-size:12px;margin-bottom:10px;color:var(--text-2)">
          📁 ${s.note_count||0} notes · ${s.size_mb||0}MB
          ${s.note_dir ? `<div style="font-size:10px;color:var(--text-3)">Notes: ${escHtml(s.note_dir)}</div>` : ''}
        </div>
        ${!s.connected ? `<div style="background:var(--bg-1);border-radius:var(--radius-sm);padding:10px;font-size:11px;color:var(--text-2);margin-bottom:10px;line-height:1.7">
          Set <code>OBSIDIAN_VAULT_PATH=/path/to/MyVault</code> in .env and restart.
        </div>` : ''}
        <div style="display:flex;flex-direction:column;gap:7px">
          <button onclick="indexVault()" class="btn btn-primary" id="obs-index-btn">📥 Index Vault → Memory Galaxy</button>
          <button onclick="createDailyNote()" class="btn btn-ghost">📅 Create Daily Note</button>
          <button onclick="exportMemories()" class="btn btn-ghost">📤 Export Memories → Vault</button>
          <div style="display:flex;gap:6px">
            <button onclick="startVaultWatch()" class="btn btn-ghost" id="obs-watch-btn" style="flex:1">👁 Start Auto-Watch</button>
            <button onclick="stopVaultWatch()" class="btn-sm" title="Stop watcher" style="color:var(--danger)">■ Stop</button>
          </div>
        </div>
        <div id="obs-status" style="margin-top:10px;font-size:12px;color:var(--text-2)"></div>
      </div>
    </div>
    <div>
      <div class="settings-card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
          <h3 style="margin:0">📝 Notes <span id="obs-note-count" style="font-size:11px;color:var(--text-3);font-weight:400"></span></h3>
          <button class="btn-sm" onclick="loadObsidianNotes()">↻ Refresh</button>
        </div>
        <div style="display:flex;gap:6px;margin-bottom:8px">
          <input id="obs-search" placeholder="Search notes…" oninput="searchNotes()" style="flex:1;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 10px;color:var(--text-0);font-size:12px;outline:none">
        </div>
        <div id="obs-notes" style="max-height:260px;overflow-y:auto;display:flex;flex-direction:column;gap:2px">Loading…</div>
      </div>
      <div class="settings-card" style="margin-top:12px">
        <h3>✏️ Quick Note</h3>
        <input id="obs-note-title" placeholder="Note title…" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 10px;color:var(--text-0);font-size:13px;outline:none;margin-bottom:7px;box-sizing:border-box">
        <textarea id="obs-note-body" placeholder="Content (Markdown)…" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 10px;color:var(--text-0);font-size:12px;outline:none;resize:none;min-height:72px;font-family:monospace;box-sizing:border-box"></textarea>
        <button onclick="saveQuickNote()" class="btn btn-primary" style="width:100%;margin-top:7px">💾 Save Note</button>
      </div>
    </div>
  </div>`;
  loadObsidianNotes();
  obsCheckWatchStatus();
}

async function indexVault() {
  const st  = document.getElementById('obs-status');
  const btn = document.getElementById('obs-index-btn');
  if (st) st.textContent = '⏳ Indexing…';
  if (btn) { btn.disabled=true; btn.textContent='⏳ Indexing…'; }
  try {
    const r = await fetch('/api/obsidian/index', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{"max_notes":500}'});
    if (!r.ok) { if(st) st.textContent='✗ HTTP '+r.status; return; }
    const j = await r.json();
    if (j.ok) {
      if (st) st.innerHTML = `✅ Indexed <strong>${j.indexed}</strong> · Skipped ${j.skipped} · Errors ${j.errors}`;
      showToast(`🧿 Vault indexed: ${j.indexed} notes added to Memory Galaxy`);
      loadObsidianNotes();
    } else {
      if (st) st.textContent = '✗ '+(j.error||'failed');
      showToast('Index failed: '+(j.error||'Unknown'));
    }
  } catch(ex) {
    if (st) st.textContent = '✗ '+ex?.message;
    showToast('Index error: '+ex?.message);
  } finally {
    if (btn) { btn.disabled=false; btn.textContent='📥 Index Vault → Memory Galaxy'; }
  }
}

async function createDailyNote() {
  try {
    const r = await fetch('/api/obsidian/daily_note', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    if (!r.ok) { showToast('Daily note failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) { showToast(`📅 Daily note created: ${j.date}`); loadObsidianNotes(); }
    else showToast('Daily note failed: '+(j.error||'Unknown'));
  } catch(ex) { showToast('Daily note error: '+ex?.message); }
}

async function exportMemories() {
  try {
    const r = await fetch('/api/obsidian/export', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{"limit":50}'});
    if (!r.ok) { showToast('Export failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) { showToast(`📤 Exported ${j.memories} memories → ${j.filename}`); loadObsidianNotes(); }
    else showToast('Export failed: '+(j.error||'No memories'));
  } catch(ex) { showToast('Export error: '+ex?.message); }
}

async function startVaultWatch() {
  try {
    const r = await fetch('/api/obsidian/watch/start', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    if (!r.ok) { showToast('Watch failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) {
      showToast('👁 Vault watcher started');
      const btn = document.getElementById('obs-watch-btn');
      if (btn) { btn.textContent='✅ Watching'; btn.style.color='var(--success)'; }
    } else {
      const msg = j.install_cmd ? `${j.error||'Failed'} — Run: ${j.install_cmd}` : (j.error||'Failed');
      showToast('Watch: '+msg);
    }
  } catch(ex) { showToast('Watch error: '+ex?.message); }
}

async function stopVaultWatch() {
  try {
    const r = await fetch('/api/obsidian/watch/stop', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    if (!r.ok) { showToast('Stop failed: HTTP '+r.status); return; }
    const j = await r.json();
    showToast(j.ok ? '■ Watcher stopped' : 'Stop failed: '+(j.error||''));
    if (j.ok) {
      const btn = document.getElementById('obs-watch-btn');
      if (btn) { btn.textContent='👁 Start Auto-Watch'; btn.style.color=''; }
    }
  } catch(ex) { showToast('Stop error: '+ex?.message); }
}

async function obsCheckWatchStatus() {
  try {
    const r = await fetch('/api/obsidian/watch/status');
    if (!r.ok) return;
    const j = await r.json();
    const btn = document.getElementById('obs-watch-btn');
    if (btn) {
      btn.textContent = j.running ? '✅ Watching' : '👁 Start Auto-Watch';
      btn.style.color = j.running ? 'var(--success)' : '';
    }
  } catch(e) {}
}

async function loadObsidianNotes(q='') {
  const el  = document.getElementById('obs-notes');
  const cnt = document.getElementById('obs-note-count');
  if (!el) return;
  try {
    const r = await fetch(`/api/obsidian/notes?limit=50${q ? '&q='+encodeURIComponent(q) : ''}`);
    if (!r.ok) { el.innerHTML = `<div style="color:var(--danger);font-size:12px">Failed (HTTP ${r.status})</div>`; return; }
    const j = await r.json();
    if (cnt) cnt.textContent = `(${j.count||0})`;
    if (!(j.notes||[]).length) {
      el.innerHTML = `<div style="color:var(--text-3);font-size:12px;padding:8px">No notes${q?' matching "'+escHtml(q)+'"':''}</div>`;
      return;
    }
    el.innerHTML = j.notes.map(n => `
      <div style="display:flex;align-items:center;gap:7px;padding:5px 8px;border-radius:var(--radius-sm);cursor:pointer;transition:background .1s"
           onmouseover="this.style.background='var(--bg-3)'" onmouseout="this.style.background=''"
           onclick="viewNote(${JSON.stringify(n.path)})">
        <span style="font-size:12px">${n.folder==='Daily'?'📅':'📄'}</span>
        <div style="flex:1;min-width:0">
          <div style="font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escHtml(n.name)}</div>
          <div style="font-size:10px;color:var(--text-3)">${n.modified}${n.folder?' · '+escHtml(n.folder):''}</div>
        </div>
        <span style="font-size:10px;color:var(--text-3)">${Math.round(n.size/1024*10)/10}K</span>
        <button onclick="event.stopPropagation();obsDeleteNote(${JSON.stringify(n.path)})"
                style="background:none;border:none;color:var(--danger);cursor:pointer;font-size:11px;opacity:.5;padding:0 2px" title="Delete">🗑</button>
      </div>`).join('');
  } catch(ex) {
    el.innerHTML = `<div style="color:var(--danger);font-size:12px">Error: ${escHtml(ex?.message||String(ex))}</div>`;
  }
}

function searchNotes() {
  const q = document.getElementById('obs-search')?.value?.trim() || '';
  loadObsidianNotes(q);
}

async function viewNote(path) {
  try {
    const r = await fetch('/api/obsidian/note?path=' + encodeURIComponent(path));
    if (!r.ok) { showToast('Note not found: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) {
      const name = path.split('/').pop();
      const overlay = document.createElement('div');
      overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
      overlay.innerHTML = `
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:14px;max-width:680px;width:100%;max-height:82vh;display:flex;flex-direction:column">
          <div style="display:flex;align-items:center;padding:12px 16px;border-bottom:1px solid var(--border);gap:8px">
            <span style="font-weight:700;color:var(--text-0);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">📄 ${escHtml(name)}</span>
            <span style="font-size:10px;color:var(--text-3)">${j.size||0}B · ${j.modified||''}</span>
            <button onclick="this.closest('[style*=fixed]').remove()" style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
          </div>
          <div style="padding:14px 16px;overflow-y:auto;flex:1;font-size:12px;line-height:1.7;color:var(--text-1);white-space:pre-wrap;font-family:monospace">${escHtml((j.content||'').slice(0,6000))}${(j.content||'').length>6000?'\n\n[... truncated]':''}</div>
          <div style="padding:10px 16px;border-top:1px solid var(--border);display:flex;gap:7px;align-items:center">
            <button class="btn-sm" onclick="navigator.clipboard.writeText(${JSON.stringify(j.content||'')})">📋 Copy</button>
            <button class="btn-sm" style="color:var(--danger)" onclick="obsDeleteNote(${JSON.stringify(path)});this.closest('[style*=fixed]').remove()">🗑 Delete</button>
            <button class="btn-sm" style="margin-left:auto" onclick="this.closest('[style*=fixed]').remove()">Close</button>
          </div>
        </div>`;
      overlay.onclick = e => { if(e.target===overlay) overlay.remove(); };
      document.body.appendChild(overlay);
    } else {
      showToast('Could not read note: '+(j.error||'Unknown'));
    }
  } catch(ex) {
    showToast('View error: '+ex?.message);
  }
}

async function obsDeleteNote(path) {
  const ok = await gmDanger('Delete Note', `Delete "${escHtml(path.split('/').pop())}"? This cannot be undone.`);
  if (!ok) return;
  try {
    const r = await fetch('/api/obsidian/note', {
      method:'DELETE', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({path})
    });
    if (!r.ok) { showToast('Delete failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) { showToast('🗑 Note deleted'); loadObsidianNotes(); }
    else showToast('Delete failed: '+(j.error||'Unknown'));
  } catch(ex) { showToast('Delete error: '+ex?.message); }
}

async function saveQuickNote() {
  const titleEl = document.getElementById('obs-note-title');
  const bodyEl  = document.getElementById('obs-note-body');
  const title   = titleEl?.value?.trim();
  const body    = bodyEl?.value?.trim() || '';
  if (!title) { showToast('⚠️ Enter a note title'); return; }
  const content  = `# ${title}\n\n${body}`;
  const filename = title.replace(/[^\w\s-]/g,'').trim().replace(/\s+/g,'_') + '.md';
  try {
    const r = await fetch('/api/obsidian/note', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({path: filename, content})
    });
    if (!r.ok) { showToast('Save failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) {
      showToast(`📝 Note saved: ${title}`);
      if (titleEl) titleEl.value = '';
      if (bodyEl)  bodyEl.value  = '';
      loadObsidianNotes();
    } else {
      showToast('Save failed: '+(j.error||'Unknown'));
    }
  } catch(ex) { showToast('Save error: '+ex?.message); }
}
// ── System Monitor Pane ────────────────────────────────────────────
let sysRefreshTimer = null;
async function renderSystem() {
  const pane = document.getElementById('pane-system');
  pane.innerHTML = `<div class="section-head">
    <div><h2>💻 System Monitor</h2><p>CPU · RAM · Disk · Processes · Git · HMR</p></div>
    <div style="display:flex;gap:8px">
      <button onclick="refreshSystem()" class="btn btn-ghost btn-sm">⟳ Refresh</button>
      <button onclick="doGitCommit()" class="btn btn-primary btn-sm">📦 Git Commit</button>
    </div>
  </div>
  <div id="sys-body"><div style="color:var(--text-2);font-size:13px">Loading…</div></div>`;
  refreshSystem();
  clearInterval(sysRefreshTimer);
  sysRefreshTimer = setInterval(refreshSystem, 10000);
}

async function refreshSystem() {
  try {
    const [hr, mr, gr] = await Promise.all([
      fetch('/api/system/health'), fetch('/api/system/metrics'), fetch('/api/system/git')
    ]);
    if (!hr.ok) throw new Error('Health API error ' + hr.status);
    if (!mr.ok) throw new Error('Metrics API error ' + mr.status);
    const h = await hr.json();
    const m = await mr.json();
    const g = gr.ok ? await gr.json() : {ok: false, error: 'Git API error ' + gr.status};
    renderSystemBody(h, m, g);
  } catch(e) {
    const el = document.getElementById('sys-body');
    if (el) el.innerHTML = `<div style="color:var(--red)">Error: ${escHtml(e.message)}</div>`;
  }
}

function renderSystemBody(h, m, g) {
  const el = document.getElementById('sys-body');
  if (!el) return;
  const sys  = h.system || {};
  const disk = h.disk   || {};
  const db   = h.database || {};

  const meter = (label, pct, color='var(--accent)') =>
    `<div style="margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px">
        <span style="color:var(--text-1)">${label}</span>
        <span style="font-weight:700;color:${color}">${pct}%</span>
      </div>
      <div style="height:8px;background:var(--bg-3);border-radius:99px;overflow:hidden">
        <div style="width:${Math.min(pct,100)}%;height:100%;background:${color};border-radius:99px;transition:width .6s ease"></div>
      </div></div>`;

  el.innerHTML = `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-bottom:20px">
    ${[
      ['💻 CPU', sys.cpu_pct||m.cpu_pct||0, '%', sys.cpu_count ? sys.cpu_count+' cores' : ''],
      ['🧠 RAM', sys.ram_pct||m.ram_pct||0, '%', `${sys.ram_used_mb||m.ram_used_mb||0}/${sys.ram_total_mb||m.ram_total_mb||0} MB`],
      ['💾 Disk', disk.pct||0, '%', `${disk.used_gb||0}/${disk.total_gb||0} GB`],
      ['🗄 DB', 0, '', `${db.counts?.memory||0} memories · ${db.counts?.tasks||0} tasks`],
      ['🔴 Process', sys.process_ram_mb||0, 'MB RAM', `PID ${sys.pid||h.database?.pid||'?'}`],
      ['⚡ HMR', 0, '', `${h.processes?.length||0} processes tracked`],
    ].map(([label,val,unit,sub]) => `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:14px">
        <div style="font-size:11px;color:var(--text-2);font-weight:700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">${label}</div>
        <div style="font-size:22px;font-weight:800;color:var(--text-0)">${val}${unit}</div>
        <div style="font-size:11px;color:var(--text-3);margin-top:2px">${sub}</div>
      </div>`).join('')}
  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
    <div class="settings-card">
      <h3>📊 Resource Usage</h3>
      ${meter('CPU', Math.round(sys.cpu_pct||m.cpu_pct||0), (sys.cpu_pct||0)>80?'var(--red)':(sys.cpu_pct||0)>50?'var(--yellow)':'var(--green)')}
      ${meter('RAM', Math.round(sys.ram_pct||m.ram_pct||0), (sys.ram_pct||0)>85?'var(--red)':(sys.ram_pct||0)>60?'var(--yellow)':'var(--accent)')}
      ${meter('Disk', Math.round(disk.pct||0), (disk.pct||0)>90?'var(--red)':'var(--teal)')}
      <div style="font-size:11.5px;color:var(--text-2);margin-top:8px">
        DB: <strong>${disk.db_mb||0}MB</strong> · Platform: <strong>${sys.platform||'?'}</strong> · Python: <strong>${sys.python||'?'}</strong>
      </div>
    </div>
    <div class="settings-card">
      <h3>🗂 Git Status</h3>
      ${g.ok ? `
        <div style="margin-bottom:8px">
          <span class="tag ${g.dirty?'yellow':'green'}">${g.dirty?'Modified':'Clean'}</span>
          <span class="tag blue" style="margin-left:6px">⎇ ${escHtml(g.branch||'')}</span>
        </div>
        ${g.unstaged?.length ? `<div style="font-size:12px;color:var(--yellow);margin-bottom:4px">Modified: ${g.unstaged.slice(0,3).map(f=>escHtml(f)).join(', ')}</div>` : ''}
        ${g.untracked?.length ? `<div style="font-size:12px;color:var(--text-2);margin-bottom:8px">Untracked: ${g.untracked.slice(0,3).map(f=>escHtml(f)).join(', ')}</div>` : ''}
        <div style="font-size:11.5px;font-weight:700;color:var(--text-2);margin-bottom:6px">Recent commits</div>
        ${(g.recent_commits||[]).slice(0,4).map(c => `
          <div style="display:flex;gap:8px;padding:4px 0;border-bottom:1px solid var(--border);font-size:11.5px">
            <code style="color:var(--accent);font-size:10.5px">${c.hash}</code>
            <span style="flex:1;color:var(--text-1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escHtml(c.message)}</span>
            <span style="color:var(--text-3)">${c.date}</span>
          </div>`).join('')}
        <button onclick="doGitCommit()" class="btn btn-primary btn-sm" style="width:100%;margin-top:10px">📦 Commit preview/</button>`
      : `<div style="color:var(--text-2);font-size:13px">${escHtml(g.error||'Git not available')}</div>
         <div style="font-size:12px;color:var(--text-3);margin-top:4px">${escHtml(g.tip||'')}</div>`}
    </div>
  </div>

  ${(h.processes||[]).length ? `
  <div class="settings-card" style="margin-top:16px">
    <h3>⚙️ Key Processes</h3>
    <div style="display:flex;flex-direction:column;gap:4px">
      ${(h.processes||[]).map(p => `
        <div style="display:flex;gap:10px;font-size:12.5px;padding:5px 0;border-bottom:1px solid var(--border)">
          <span style="color:var(--text-3);font-family:monospace">${p.pid}</span>
          <span style="flex:1;font-weight:600">${escHtml(p.name)}</span>
          <span class="tag ${p.status==='running'?'green':''}">${p.status}</span>
          <span style="color:var(--text-2)">${p.ram_mb}MB</span>
        </div>`).join('')}
    </div>
  </div>` : ''}`;
}

async function doGitCommit() {
  const message = await gmPrompt('Git Commit', 'Commit message…', 'Agentic OS checkpoint');
  if (!message) return;
  try {
    const r = await fetch('/api/system/git/commit', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ message })
    });
    if (!r.ok) { toast('Git commit failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) toast(`📦 Committed: ${j.hash||''} "${message}"`, 'ok', 4000);
    else toast('Git error: ' + (j.error||''), 'err');
    refreshSystem();
  } catch(ex) { toast('Git commit error: ' + ex.message, 'err'); }
}

// ── HMR — auto-reload preview when files change ────────────────────
let hmrSource = null;

function startHMR() {
  if (hmrSource && typeof hmrSource.close === 'function') hmrSource.close();
  if (typeof window.EventSource === 'undefined') return;
  hmrSource = new EventSource('/api/system/hmr');
  hmrSource.onmessage = e => {
    try {
      const ev = JSON.parse(e.data);
      if (ev.type === 'file_changed') {
        // Reload preview iframe silently
        const frame = document.getElementById('preview-frame');
        if (frame && document.getElementById('pane-builder')?.classList.contains('active')) {
          const src = frame.src.split('?')[0];
          frame.src = src + '?t=' + Date.now();
        }
        // Flash status indicator
        const sb = document.getElementById('sb-version');
        if (sb) {
          const orig = sb.textContent;
          sb.textContent = `⚡ HMR: ${ev.path || 'file'} changed`;
          sb.style.color = 'var(--yellow)';
          setTimeout(() => { sb.textContent = orig; sb.style.color = ''; }, 2000);
        }
      }
    } catch(err) {}
  };
  hmrSource.onerror = () => {
    setTimeout(startHMR, 5000); // auto-reconnect
  };
}

startHMR();

// ── Replace all prompt()/confirm() calls with gm equivalents ──────
// openNewFileModal
window.openNewFileModal = async function() {
  const name = await gmPrompt('New File', 'e.g. about.html, styles.css, component.jsx');
  if (!name) return;
  const r = await fetch('/api/preview/new', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ path: name, content: '' })
  });
  const j = await r.json();
  if (j.ok) { toast(`✅ Created ${name}`, 'ok'); loadFileTree(); openFile(name); }
  else toast('Error: ' + (j.error || ''), 'err');
};

// openNewTaskModal
window.openNewTaskModal = async function() {
  const title = await gmPrompt('New Task', 'Describe the task…');
  if (!title) return;
  const agent = await gmPrompt('Assign to agent', 'e.g. builder, brain, researcher', 'builder');
  if (agent === null) return;
  const r = await fetch('/api/tasks', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ title, agent: agent||'builder', status:'todo', priority:'medium' })
  });
  const j = await r.json();
  if (j.ok) { toast('✅ Task created', 'ok'); renderKanban(); }
};

// deleteTask
window.deleteTask = async function(id) {
  const ok = await gmDanger('Delete Task', 'This cannot be undone.', 'Delete');
  if (!ok) return;
  await fetch(`/api/tasks/${encodeURIComponent(id)}`, { method: 'DELETE' });
  toast('🗑 Task deleted', 'ok', 1500);
  renderKanban();
};

// openCreateSkill
window.openCreateSkill = async function() {
  const name = await gmPrompt('New Skill', 'Skill name (e.g. "LinkedIn Post Writer")');
  if (!name) return;
  const prompt_tmpl = await gmPrompt('Prompt Template', 'Use {placeholder} for inputs. e.g. "Write a {tone} post about {topic}"', '', true);
  if (prompt_tmpl === null) return;
  const agent = await gmPrompt('Agent ID', 'e.g. brain, builder, researcher', 'brain');
  if (agent === null) return;
  const r = await fetch('/api/skills', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      name, prompt_template: prompt_tmpl||'{prompt}',
      agent: agent||'brain', category: 'custom', emoji: '⚡',
      inputs: [{ id:'prompt', label:'Your input', type:'textarea', required:true }]
    })
  });
  const j = await r.json();
  if (j.ok) { toast(`✅ Skill "${name}" created`, 'ok'); loadSkills(); }
  else toast('Error: ' + (j.error||''), 'err');
};

// loadSwarmHistory (was alert)
window.loadSwarmHistory = async function() {
  const r = await fetch('/api/swarm/history?limit=10');
  const j = await r.json();
  if (!j.length) { toast('No swarm history yet', 'warn', 2000); return; }
  const lines = j.map((h,i) => `${i+1}. [${h.ts}] ${h.winner||'?'} won (${h.strategy})\n   ${(h.prompt||'').slice(0,80)}`).join('\n\n');
  await gmAlert('🌀 Swarm History (last 10)', `<pre style="font-size:12px;white-space:pre-wrap;max-height:300px;overflow-y:auto">${escHtml(lines)}</pre>`);
};

// ── Update requirements.txt with new deps ─────────────────────────
// ── Statusbar: add system metrics ────────────────────────────────
async function updateSystemMetrics() {
  try {
    const r = await fetch('/api/system/metrics');
    if (!r.ok) return;  // silently ignore on server error
    const m = await r.json();
    const el = document.getElementById('sb-version');
    if (el) el.title = `CPU: ${m.cpu_pct}% · RAM: ${m.ram_pct}% (${m.ram_used_mb}MB)`;
  } catch(e) {}
}
setInterval(updateSystemMetrics, 15000);

// ═══════════════════════════════════════════════════════════════
//  SPRINT 9 — BOLD EDITORIAL UX: Skeleton Loaders, Empty States,
//  Help Panels, ARIA, Missing Renderers, Micro-interactions,
//  Animated Counters, Contextual Guidance
// ═══════════════════════════════════════════════════════════════

// ── Skeleton loader factory ────────────────────────────────────────
function skeletonCard(rows = 2) {
  return `<div class="skeleton skeleton-card" style="height:80px;margin-bottom:12px"></div>`.repeat(rows);
}
function skeletonList(rows = 4) {
  return Array.from({length: rows}, (_,i) => `
    <div style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border)">
      <div class="skeleton" style="width:32px;height:32px;border-radius:50%;flex-shrink:0"></div>
      <div style="flex:1">
        <div class="skeleton skeleton-text" style="width:${60+i*8}%"></div>
        <div class="skeleton skeleton-text" style="width:${35+i*5}%;height:10px"></div>
      </div>
    </div>`).join('');
}
function skeletonStats(n = 4) {
  return `<div style="display:grid;grid-template-columns:repeat(${n},1fr);gap:12px">` +
    Array.from({length:n}, () =>
      `<div class="skeleton" style="height:90px;border-radius:var(--radius-lg)"></div>`).join('') + '</div>';
}
function skeletonPage(title = 'Loading…') {
  return `
    <div style="padding:0">
      <div class="page-header">
        <div class="skeleton skeleton-title" style="width:200px;height:28px;margin-bottom:8px"></div>
        <div class="skeleton skeleton-text" style="width:300px;height:14px"></div>
      </div>
      <div class="page-content">
        ${skeletonStats(4)}
        <div style="margin-top:20px">${skeletonList(5)}</div>
      </div>
    </div>`;
}

// ── Empty state factory ────────────────────────────────────────────
function emptyState({ icon, title, body, actions = [] }) {
  return `<div class="empty-state">
    <div class="empty-state__icon">${icon}</div>
    <div class="empty-state__title">${title}</div>
    <div class="empty-state__body">${body}</div>
    <div class="empty-state__actions">${actions.map(a =>
      `<button onclick="${a.action}" class="btn ${a.primary ? 'btn-primary' : 'btn-ghost'}">${a.label}</button>`
    ).join('')}</div>
  </div>`;
}

// ── Help panel factory (novice guidance) ───────────────────────────
function helpPanel({ title, body, steps = [] }) {
  return `<div class="help-panel">
    <div class="help-panel__title">💡 ${title}</div>
    <div class="help-panel__body">${body}</div>
    ${steps.length ? `<div class="help-panel__steps">${steps.map((s,i) =>
      `<div class="help-panel__step"><div class="help-panel__step-num">${i+1}</div><span>${s}</span></div>`
    ).join('')}</div>` : ''}
  </div>`;
}

// ── Animated number counter ────────────────────────────────────────
function animateCounter(el, target, duration = 800, prefix = '', suffix = '') {
  if (!el) return;
  const start    = 0;
  const startTime = performance.now();
  const update   = (now) => {
    const elapsed = now - startTime;
    const progress = Math.min(elapsed / duration, 1);
    // Ease out cubic
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = Math.floor(start + (target - start) * eased);
    el.textContent = prefix + current.toLocaleString() + suffix;
    if (progress < 1) requestAnimationFrame(update);
    else el.textContent = prefix + target.toLocaleString() + suffix;
  };
  requestAnimationFrame(update);
}

// ── Page header factory ────────────────────────────────────────────
function pageHeader({ title, subtitle = '', actions = [], badge = '' }) {
  return `
    <div class="page-header">
      <div class="page-header__top">
        <div>
          <h1 class="page-heading">${title} ${badge ? `<span class="badge badge-accent" style="font-size:11px;vertical-align:middle">${badge}</span>` : ''}</h1>
          ${subtitle ? `<p class="page-subheading">${subtitle}</p>` : ''}
        </div>
        <div class="page-header__actions">
          ${actions.map(a => `<button onclick="${a.action}" class="btn ${a.primary?'btn-primary':'btn-ghost'} btn-sm">${a.label}</button>`).join('')}
        </div>
      </div>
    </div>`;
}

// ── Missing pane renderers ─────────────────────────────────────────
// These panes had no renderX() function — filling them all now

// renderGalaxy (Memory Galaxy)
async function renderGalaxy() {
  const pane = document.getElementById('pane-galaxy');
  if (!pane) return;
  // Galaxy has its own complex init — just ensure it's initialized
  if (typeof initGalaxy === 'function') {
    initGalaxy();
  }
}

// renderSettings
async function renderSettings() {
  const pane = document.getElementById('pane-settings');
  if (!pane) return;
  if (typeof loadSettings === 'function') await loadSettings();
}

// renderBuilder
async function renderBuilder() {
  const pane = document.getElementById('pane-builder');
  if (!pane) return;
  if (typeof initBuilder === 'function') initBuilder();
}

// renderGithub (was renderGitHub)
async function renderGithub() {
  if (typeof renderGitHub === 'function') await renderGitHub();
}

// renderDbstudio (was renderDBStudio)  
async function renderDbstudio() {
  if (typeof renderDBStudio === 'function') await renderDBStudio();
}

// renderMcp (was renderMCP)
async function renderMcp() {
  if (typeof renderMCP === 'function') await renderMCP();
}

// Extend nav to call all renderers consistently
const _s9NavBase = function(){}; // nav chain disabled — master nav handles all
function _disabled__s9NavBase(pane) {
  _s9NavBase(pane);
  // Ensure renderers are called for all panes
  const map = {
    galaxy:   renderGalaxy,
    settings: renderSettings,
    builder:  renderBuilder,
    github:   renderGithub,
    dbstudio: renderDbstudio,
    mcp:      renderMcp,
    chat:     () => {},
    studio:   () => typeof initStudio==='function' && initStudio(),
  };
  if (map[pane]) {
    try { map[pane](); } catch(e) { console.warn('render error:', pane, e); }
  }
}

// ── Enhanced dashboard with animated counters ──────────────────────
const _origRenderDashBody = typeof renderDashBody === 'function' ? renderDashBody : null;
renderDashBody = function(d) {
  if (_origRenderDashBody) _origRenderDashBody(d);
  // Animate all stat values after render
  setTimeout(() => {
    const k = d?.kpis || {};
    const animItems = [
      ['total_cost_usd',    k.total_cost_usd,     '$', ''],
      ['total_tokens',      k.total_tokens,        '', ''],
      ['total_memories',    k.total_memories,      '', ''],
      ['total_tasks',       k.total_tasks,         '', ''],
      ['done_tasks',        k.done_tasks,           '', ''],
    ];
    document.querySelectorAll('#pane-dashboard .stat-card__value, #pane-dashboard [style*="font-size:26px"]').forEach((el, i) => {
      const item = animItems[i];
      if (item) {
        const target = typeof item[1] === 'number' ? item[1] : parseFloat(item[1]) || 0;
        animateCounter(el, target, 800 + i * 100, item[2], item[3]);
      }
    });
  }, 200);
};

// ── Enhanced chat empty state ──────────────────────────────────────
(function upgradeChatEmptyState() {
  const el = document.getElementById('chat-empty');
  if (!el) { setTimeout(upgradeChatEmptyState, 400); return; }
  el.innerHTML = `
    <div style="text-align:center;max-width:440px;padding:24px">
      <div style="font-size:52px;margin-bottom:16px;opacity:.8">🧠</div>
      <h2 style="font-size:22px;font-weight:900;letter-spacing:-.025em;color:var(--text-0);margin-bottom:8px">
        Mission Control
      </h2>
      <p style="font-size:14px;color:var(--text-2);line-height:1.7;margin-bottom:20px">
        Your local-first AI operating system. Chat with specialist agents, build apps, run multi-agent swarms, manage your Memory Galaxy, and deploy — all from here.
      </p>

      <!-- Quick start for novices -->
      <div style="background:rgba(91,138,248,.06);border:1px solid rgba(91,138,248,.15);border-radius:16px;padding:16px;margin-bottom:20px;text-align:left">
        <div style="font-size:11px;font-weight:700;color:var(--accent-hi);letter-spacing:.06em;text-transform:uppercase;margin-bottom:10px">💡 Quick start</div>
        <div style="display:flex;flex-direction:column;gap:8px">
          ${[
            ['💬', 'Just chat', 'Ask anything — "explain async/await in Python"'],
            ['🎬', 'Build an app', 'Go to Studio → pick a template → customize'],
            ['🌀', 'Run a swarm', 'Multiple AI agents work in parallel on one problem'],
            ['⚡', 'Run a skill', 'SEO audit, email sequence, code review — one click'],
          ].map(([icon, label, desc]) =>
            `<div style="display:flex;gap:10px;align-items:flex-start">
              <span style="font-size:16px;flex-shrink:0">${icon}</span>
              <div><div style="font-size:12.5px;font-weight:600;color:var(--text-0)">${label}</div>
              <div style="font-size:11.5px;color:var(--text-2)">${desc}</div></div>
            </div>`
          ).join('')}
        </div>
      </div>

      <!-- Command chips -->
      <div style="display:flex;flex-wrap:wrap;gap:7px;justify-content:center;margin-bottom:16px">
        ${[
          ['/help', 'Show all commands'],
          ['/goal build a SaaS landing page', 'Plan a goal'],
          ['/research latest React 19 features', 'Deep research'],
          ['/code write a dark mode toggle hook', 'Write code'],
          ['/swarm compare RAG approaches', 'Run swarm'],
        ].map(([cmd, hint]) =>
          `<button onclick="insertCmd('${cmd.replace(/'/g,"&#39;")}')" class="cmd-chip" title="${hint}">${cmd.length > 30 ? cmd.slice(0,28)+'…' : cmd}</button>`
        ).join('')}
      </div>

      <!-- Agent selector -->
      <div style="font-size:11px;color:var(--text-3);margin-bottom:8px">Active agent</div>
      <div style="display:flex;gap:6px;justify-content:center;flex-wrap:wrap" id="quick-agent-select">
        ${S.agents.slice(0,6).map(a =>
          `<button onclick="setActiveAgent(${JSON.stringify(a).replace(/"/g,'&quot;')});document.getElementById('chat-empty').style.display='none'"
            style="display:flex;align-items:center;gap:6px;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;padding:6px 10px;cursor:pointer;transition:var(--transition);font-size:12px;color:var(--text-1)"
            onmouseover="this.style.borderColor='var(--accent)';this.style.color='var(--text-0)'"
            onmouseout="this.style.borderColor='var(--border)';this.style.color='var(--text-1)'">
            <span>${a.avatar||'🤖'}</span><span>${escHtml(a.name)}</span>
          </button>`
        ).join('')}
      </div>
    </div>`;
})();

// ── Pane loading pattern — wrap all async renders ─────────────────
function withSkeleton(paneId, asyncFn) {
  return async function() {
    const pane = document.getElementById('pane-' + paneId);
    if (!pane) return;
    // Show skeleton immediately
    const prevContent = pane.innerHTML;
    pane.innerHTML = `<div style="flex:1;overflow:hidden">${skeletonPage()}</div>`;
    try {
      await asyncFn();
    } catch(e) {
      pane.innerHTML = `<div style="flex:1">${pageHeader({title:'Error'})}<div class="page-content">
        ${emptyState({icon:'⚠️', title:'Something went wrong', body: escHtml(e.message || 'Unknown error'),
          actions:[{label:'Retry', action:`nav('${paneId}')`, primary:true}]})}
      </div></div>`;
    }
  };
}

// Wrap key renderers with skeleton
const wrappedRenders = {
  dashboard: typeof renderDashboard === 'function' ? renderDashboard : null,
  skills:    typeof renderSkills    === 'function' ? renderSkills    : null,
  plugins:   typeof renderPlugins   === 'function' ? renderPlugins   : null,
  templates: typeof renderTemplates === 'function' ? renderTemplates : null,
  obsidian:  typeof renderObsidian  === 'function' ? renderObsidian  : null,
  system:    typeof renderSystem    === 'function' ? renderSystem    : null,
  deploy:    typeof renderDeploy    === 'function' ? renderDeploy    : null,
  pipeline:  typeof renderPipeline  === 'function' ? renderPipeline  : null,
  composer:  typeof renderComposer  === 'function' ? renderComposer  : null,
};
// Don't wrap with skeleton — they handle their own loading
// Just ensure they exist
Object.entries(wrappedRenders).forEach(([key, fn]) => {
  if (fn && !window[`render${key.charAt(0).toUpperCase()+key.slice(1)}`]) {
    window[`render${key.charAt(0).toUpperCase()+key.slice(1)}`] = fn;
  }
});

// ── Micro-interactions ─────────────────────────────────────────────

window.initDeepLinkRouter = function() {
  const hash = location.hash || '';
  if (hash && hash.startsWith('#/')) {
    const parts = hash.slice(2).split('/');
    const pane = parts[0];
    const subTab = parts[1];
    if (pane && window.MASTER_PANE_REGISTRY && window.MASTER_PANE_REGISTRY.hasOwnProperty(pane)) {
      setTimeout(() => {
        window.nav(pane);
        if (pane === 'settings' && subTab && typeof window.switchSettingsTab === 'function') {
          window.switchSettingsTab(subTab);
        } else if (pane === 'hierarchy' && subTab && typeof window.switchIvrenSection === 'function') {
          window.switchIvrenSection(subTab);
        }
      }, 100);
    }
  }
  window.addEventListener('hashchange', () => {
    const h = location.hash || '';
    if (h && h.startsWith('#/')) {
      const parts = h.slice(2).split('/');
      const p = parts[0];
      const sub = parts[1];
      if (p && window.MASTER_PANE_REGISTRY && window.MASTER_PANE_REGISTRY.hasOwnProperty(p)) {
        window.nav(p);
        if (p === 'settings' && sub && typeof window.switchSettingsTab === 'function') {
          window.switchSettingsTab(sub);
        }
      }
    }
  });
};

// Add lift class to all cards dynamically and initialize UI controllers
(function addLiftToCards() {
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.swarm-card,.plugin-card,.template-card').forEach(el => {
      el.classList.add('lift');
    });
    try { if (typeof initSidebarGroups === 'function') initSidebarGroups(); } catch(e) {}
    try { if (typeof setupSidebarResizer === 'function') setupSidebarResizer(); } catch(e) {}
    try { if (typeof setupSettingsWorkstation === 'function') setupSettingsWorkstation(); } catch(e) {}
    try { if (typeof setupDragAndDrop === 'function') setupDragAndDrop(); } catch(e) {}
    try { if (typeof window.initDeepLinkRouter === 'function') window.initDeepLinkRouter(); } catch(e) {}
  });
})();

// Button press scale effect (all buttons system-wide)
document.addEventListener('mousedown', e => {
  const btn = e.target.closest('.btn,.nav-item,.card-interactive');
  if (btn) {
    btn.style.transition = 'transform 80ms ease';
    btn.style.transform  = 'scale(0.97)';
  }
}, {passive: true});
document.addEventListener('mouseup', e => {
  const btn = e.target.closest('.btn,.nav-item,.card-interactive');
  if (btn) {
    btn.style.transition = 'transform 200ms ease';
    btn.style.transform  = '';
  }
}, {passive: true});

// Nav item hover — subtle slide indicator
document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('mouseenter', () => {
    if (!item.classList.contains('active')) {
      item.style.paddingLeft = '14px';
    }
  });
  item.addEventListener('mouseleave', () => {
    if (!item.classList.contains('active')) {
      item.style.paddingLeft = '';
    }
  });
});

// ── Contextual help tooltips ───────────────────────────────────────
(function addContextualHelp() {
  // Add help badges to key features for novices
  const helpItems = [
    ['#active-agent-pill',       'Click to switch which AI agent responds to you'],
    ['#rag-btn',                 'RAG = Retrieval Augmented Generation. Grounds AI responses in your Memory Galaxy'],
    ['#stream-btn',              'Stream = see AI responses token-by-token as they generate'],
    ['#hmr-badge',               'HMR = Hot Module Reload. Preview auto-updates when you save files'],
    ['#studio-resizer',          'Drag to resize editor vs preview split'],
    ['.palette-btn, #palette-btn', '⌘K opens the command palette — search everything'],
  ];

  helpItems.forEach(([selector, tip]) => {
    const el = document.querySelector(selector);
    if (el && !el.dataset.tooltip) el.dataset.tooltip = tip;
  });
})();

// ── ARIA improvements ──────────────────────────────────────────────
(function addARIA() {
  // Navigation
  const sidebar = document.getElementById('sidebar');
  if (sidebar) sidebar.setAttribute('role', 'navigation');
  if (sidebar) sidebar.setAttribute('aria-label', 'Main navigation');

  // Nav items
  document.querySelectorAll('.nav-item').forEach(item => {
    if (!item.getAttribute('role')) item.setAttribute('role', 'menuitem');
    const label = item.querySelector('.label')?.textContent;
    if (label && !item.getAttribute('aria-label')) item.setAttribute('aria-label', label);
  });

  // Buttons that only have icons
  document.querySelectorAll('.icon-btn,.topbar-btn').forEach(btn => {
    if (!btn.getAttribute('aria-label') && btn.title) {
      btn.setAttribute('aria-label', btn.title);
    }
  });

  // Chat input
  const chatInput = document.getElementById('chat-input');
  if (chatInput) {
    chatInput.setAttribute('aria-label', 'Message to AI agent');
    chatInput.setAttribute('role', 'textbox');
    chatInput.setAttribute('aria-multiline', 'true');
  }

  // Main landmark
  const content = document.getElementById('content');
  if (content) content.setAttribute('role', 'main');

  // Status bar
  const statusbar = document.getElementById('statusbar');
  if (statusbar) statusbar.setAttribute('aria-label', 'Application status');
})();

// ── First-run help overlay (novice) ───────────────────────────────
(function firstRunHelpOverlay() {
  // Show a dismissible guided tip on first visit (per session)
  if (sessionStorage.getItem('aos-welcomed')) return;
  sessionStorage.setItem('aos-welcomed', '1');

  // Delay to let everything load
  setTimeout(() => {
    const prefs = S.preferences || {};
    if (prefs.onboarding_complete) return; // They did onboarding

    const banner = document.createElement('div');
    banner.id    = 'welcome-banner';
    banner.style.cssText = `
      position:fixed;bottom:56px;left:50%;transform:translateX(-50%);
      background:linear-gradient(135deg,rgba(18,20,42,.98),rgba(13,15,26,.98));
      border:1px solid rgba(91,138,248,.3);border-radius:16px;padding:14px 18px;
      box-shadow:0 16px 48px rgba(0,0,0,.6);z-index:8000;
      display:flex;align-items:center;gap:14px;max-width:520px;width:calc(100% - 32px);
      animation:slideUp 300ms cubic-bezier(0.34,1.56,0.64,1);
    `;
    banner.innerHTML = `
      <span style="font-size:28px;flex-shrink:0">👋</span>
      <div style="flex:1;min-width:0">
        <div style="font-weight:700;font-size:13.5px;color:var(--text-0);margin-bottom:3px">Welcome to Agentic OS!</div>
        <div style="font-size:12px;color:var(--text-2);line-height:1.5">Press <kbd style="background:var(--bg-4);border:1px solid var(--border);border-radius:4px;padding:1px 6px;font-size:10px">⌘K</kbd> anytime to search, or start typing in the chat below.</div>
      </div>
      <div style="display:flex;gap:8px;flex-shrink:0">
        <button onclick="nav('templates');document.getElementById('welcome-banner')?.remove()" class="btn btn-primary btn-sm">🎨 Templates</button>
        <button onclick="document.getElementById('welcome-banner')?.remove()" style="background:none;border:none;color:var(--text-2);cursor:pointer;font-size:18px;padding:0 4px">×</button>
      </div>`;
    document.body.appendChild(banner);
    setTimeout(() => banner?.remove(), 12000);
  }, 2000);
})();

// ── Section head upgrade (replace hardcoded patterns) ─────────────
// Override the old section-head div pattern with the new page-header
const _origRenderKanban = typeof renderKanban === 'function' ? renderKanban : null;
if (_origRenderKanban) {
  renderKanban = async function() {
    const pane = document.getElementById('pane-kanban');
    if (pane) {
      pane.innerHTML = `
        ${pageHeader({
          title: '📋 Kanban',
          subtitle: 'Drag tasks between columns to update status',
          actions: [{label: '＋ Task', action: "openNewTaskModal()", primary: true}]
        })}
        <div class="page-content" style="padding:0">
          <div style="padding:16px">${skeletonStats(4)}</div>
        </div>`;
    }
    await _origRenderKanban();
  };
}

// ── Upgrade topbar elements ────────────────────────────────────────
(function upgradeTopbar() {
  const keyStatus = document.getElementById('key-status');
  if (keyStatus) {
    keyStatus.setAttribute('aria-label', 'API key status');
    keyStatus.setAttribute('role', 'button');
  }
  // Add keyboard shortcut hint to palette button
  const paletteBtn = document.getElementById('palette-btn');
  if (paletteBtn) {
    paletteBtn.setAttribute('aria-label', 'Open command palette (⌘K)');
    paletteBtn.setAttribute('role', 'button');
  }
})();

// ── Smooth nav transitions ─────────────────────────────────────────
const _s9FinalNav = nav;
nav = function(pane) {
  // Update active state with smooth indicator
  document.querySelectorAll('.nav-item').forEach(el => {
    const isActive = el.dataset.nav === pane;
    el.classList.toggle('active', isActive);
    if (isActive) {
      el.setAttribute('aria-current', 'page');
    } else {
      el.removeAttribute('aria-current');
    }
  });
  _s9FinalNav(pane);
  // Update document title
  const names = {
    chat:'Chat', studio:'Studio', builder:'Editor', kanban:'Kanban',
    swarm:'Swarm', galaxy:'Memory Galaxy', dashboard:'Dashboard',
    skills:'Skills', deploy:'Deploy', templates:'Templates',
    github:'GitHub', dbstudio:'Database', composer:'Composer',
    plugins:'Plugins', obsidian:'Obsidian', system:'System',
    settings:'Settings', mcp:'MCP Tools', loops:'Loops', pipeline:'Pipeline',
  };
  document.title = `Agentic OS — ${names[pane] || pane}`;
};

// ── Status bar enhancements ────────────────────────────────────────
(function enhanceStatusBar() {
  const sb = document.getElementById('sb-version');
  if (sb) {
    sb.style.cursor = 'pointer';
    sb.title = 'Agentic OS v6.0 — Click for system info';
    sb.addEventListener('click', () => nav('system'));
  }

  // Add online/offline indicator
  const offlineHandler = () => {
    const dot = document.querySelector('.sb-dot');
    if (dot) { dot.style.background = 'var(--red)'; dot.title = 'Offline'; }
    toast('⚠️ You are offline — local features still work', 'warn', 4000);
  };
  const onlineHandler = () => {
    const dot = document.querySelector('.sb-dot');
    if (dot) { dot.style.background = 'var(--success)'; dot.title = 'Online'; }
  };
  window.addEventListener('offline', offlineHandler);
  window.addEventListener('online', onlineHandler);
})();

// ── Enhanced toast with icons ──────────────────────────────────────
const _origToast = toast;
toast = function(msg, type = 'ok', duration = 3000) {
  const icons = { ok: '✅', err: '❌', warn: '⚠️' };
  const icon  = icons[type] || '';
  // Prepend icon if not already there
  const displayMsg = (msg.startsWith('✅') || msg.startsWith('❌') || msg.startsWith('⚠️')) 
    ? msg : (icon ? icon + ' ' + msg : msg);
  return _origToast(displayMsg, type, duration);
};
window.toast = toast;

// ── Add missing CSS vars for backward compat ──────────────────────
// Some code uses --bg-base, --success etc — ensure they're set
const rootStyle = document.documentElement.style;
const computedRoot = getComputedStyle(document.documentElement);
if (!computedRoot.getPropertyValue('--success').trim()) {
  document.documentElement.style.setProperty('--success', '#3dba7a');
  document.documentElement.style.setProperty('--danger',  '#e85252');
  document.documentElement.style.setProperty('--warning', '#e8a237');
}

// ── Global keyboard shortcut improvements ─────────────────────────
document.addEventListener('keydown', e => {
  // ⌘/ → focus chat input from anywhere
  if ((e.metaKey || e.ctrlKey) && e.key === '/') {
    e.preventDefault();
    nav('chat');
    setTimeout(() => document.getElementById('chat-input')?.focus(), 100);
  }
  // ⌘1-6 → quick nav
  if ((e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey) {
    const navMap = {'1':'chat','2':'studio','3':'templates','4':'kanban','5':'swarm','6':'deploy'};
    if (navMap[e.key]) {
      e.preventDefault();
      nav(navMap[e.key]);
    }
  }
});

// ── Report console (for Sprint 9 QA) ─────────────────────────────
console.log(
  '%c🧠 Agentic OS v9 — Sprint 9 Bold Editorial Design System loaded',
  'color:#7aa4ff;font-weight:bold;font-size:13px'
);
console.log(
  '%c  Design system: type scale, spacing scale, skeleton loaders, empty states, ARIA ✅',
  'color:#3dba7a;font-size:11px'
);

// ═══════════════════════════════════════════════════════════════
//  SPRINT 8 — Chat Overhaul, Templates, Sidebar, Studio Power
// ═══════════════════════════════════════════════════════════════

// ── Extend nav for Sprint 8 ────────────────────────────────────────
const _s8NavBase = function(){}; // nav chain disabled — master nav handles all
function _disabled__s8NavBase(pane) {
  _s8NavBase(pane);
  if (pane === 'templates') renderTemplates();
}

// ═══════════════════════════════════════════════════════════════
//  CHAT OVERHAUL — Syntax highlighting, Copy buttons,
//  Regenerate, @mentions, Persistent sessions
// ═══════════════════════════════════════════════════════════════

// ── Load highlight.js for syntax highlighting ──────────────────────
(function loadHLJS() {
  // Load highlight.js CSS
  const link = document.createElement('link');
  link.rel  = 'stylesheet';
  link.href = 'https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/styles/github-dark.min.css';
  document.head.appendChild(link);
  // Load highlight.js script
  const s = document.createElement('script');
  s.src   = 'https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/lib/core.min.js';
  s.onload = () => {
    // Load common languages
    const langs = ['javascript','typescript','python','bash','json','html','css','sql','rust','go','java','cpp'];
    let loaded = 0;
    langs.forEach(lang => {
      const ls = document.createElement('script');
      ls.src   = `https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/lib/languages/${lang}.min.js`;
      ls.onload = () => {
        loaded++;
        if (loaded === langs.length) {
          window.hljs.configure({ ignoreUnescapedHTML: true });
          window._hljsReady = true;
        }
      };
      document.head.appendChild(ls);
    });
  };
  document.head.appendChild(s);
})();

// ── Enhanced markdown renderer with syntax highlighting + copy ─────
function renderMarkdownEnhanced(text) {
  if (!text) return '';
  let t = text;

  // Code blocks with syntax highlighting and copy button
  t = t.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const escaped = code.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    const langLabel = lang || 'code';
    const highlightedCode = (window._hljsReady && lang && window.hljs.getLanguage(lang))
      ? window.hljs.highlight(code, { language: lang }).value
      : escaped;
    const id = 'cb_' + Math.random().toString(36).slice(2,8);
    return `<div style="position:relative;margin:10px 0;border-radius:8px;overflow:hidden;border:1px solid var(--border)">
      <div style="display:flex;align-items:center;justify-content:space-between;background:#0a0d18;padding:6px 12px;border-bottom:1px solid var(--border)">
        <span style="font-size:10.5px;color:var(--text-3);font-family:monospace">${escHtml(langLabel)}</span>
        <button onclick="copyCodeBlock(${JSON.stringify(id)})" style="background:none;border:1px solid var(--border);border-radius:5px;color:var(--text-2);padding:2px 8px;cursor:pointer;font-size:10.5px;transition:var(--transition)" onmouseover="this.style.color='var(--text-0)'" onmouseout="this.style.color='var(--text-2)'">📋 Copy</button>
      </div>
      <pre id="${id}" style="margin:0;padding:14px;background:#08090e;overflow-x:auto;font-size:12.5px;line-height:1.65;font-family:'JetBrains Mono','Fira Code',monospace"><code class="hljs language-${langLabel}" data-raw="${encodeURIComponent(code)}">${highlightedCode}</code></pre>
    </div>`;
  });

  // Inline code
  t = t.replace(/`([^`\n]+)`/g, '<code style="background:var(--bg-0);border:1px solid var(--border);border-radius:4px;padding:1px 5px;font-size:12px;font-family:monospace">$1</code>');
  // Bold and italic
  t = t.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  t = t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  t = t.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // Headers
  t = t.replace(/^### (.+)$/gm, '<h3 style="font-size:14px;font-weight:700;margin:10px 0 5px;color:var(--text-0)">$1</h3>');
  t = t.replace(/^## (.+)$/gm,  '<h2 style="font-size:15px;font-weight:800;margin:12px 0 6px;color:var(--text-0)">$1</h2>');
  t = t.replace(/^# (.+)$/gm,   '<h1 style="font-size:18px;font-weight:900;margin:14px 0 8px;color:var(--text-0)">$1</h1>');
  // Blockquote
  t = t.replace(/^> (.+)$/gm, '<blockquote style="border-left:3px solid var(--accent);margin:6px 0;padding:4px 12px;color:var(--text-2);font-style:italic">$1</blockquote>');
  // Lists
  t = t.replace(/^[\s]*[-•*] (.+)$/gm, '<div style="padding:2px 0 2px 16px;display:flex;gap:6px"><span style="color:var(--accent);flex-shrink:0">•</span><span>$1</span></div>');
  t = t.replace(/^[\s]*(\d+)\. (.+)$/gm, '<div style="padding:2px 0 2px 16px;display:flex;gap:6px"><span style="color:var(--accent);flex-shrink:0">$1.</span><span>$2</span></div>');
  // Horizontal rule
  t = t.replace(/^---+$/gm, '<hr style="border:none;border-top:1px solid var(--border);margin:12px 0">');
  // Links
  t = t.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" style="color:var(--accent);text-decoration:underline">$1</a>');
  // Line breaks
  t = t.replace(/\n\n/g, '</p><p style="margin-bottom:8px">');
  t = t.replace(/\n/g, '<br>');
  return '<p style="margin-bottom:8px">' + t + '</p>';
}

function copyCodeBlock(id) {
  const el   = document.getElementById(id);
  if (!el) return;
  const code = el.querySelector('code');
  const raw  = code ? decodeURIComponent(code.dataset.raw || '') : el.textContent;
  navigator.clipboard.writeText(raw).then(() => toast('📋 Code copied!', 'ok', 1500));
}

// Patch the main renderMarkdown to use enhanced version
window.renderMarkdown = renderMarkdownEnhanced;

// ── Message actions (copy, regenerate, branch) ─────────────────────
function addMessageActions(bubbleEl, role, content, msgId) {
  if (!bubbleEl) return;
  const actEl = document.createElement('div');
  actEl.className = 'msg-actions';
  actEl.style.cssText = 'display:flex;gap:4px;margin-top:6px;opacity:0;transition:opacity .15s';
  actEl.innerHTML = `
    <button onclick="copyMsgContent(${JSON.stringify(msgId)})" class="msg-action-btn" title="Copy message">📋</button>
    ${role === 'agent' ? `
    <button onclick="regenerateMsg(${JSON.stringify(msgId)})" class="msg-action-btn" title="Regenerate response">↺</button>
    <button onclick="speakText(window._msgContents?.[msgId]||'', (S.currentAgent||{}).id||'brain')" class="msg-action-btn" title="Listen">🔊</button>
    ` : ''}
    <button onclick="branchFromMsg(${JSON.stringify(msgId)})" class="msg-action-btn" title="Fork conversation here">⎇</button>
  `;
  bubbleEl.parentElement?.appendChild(actEl);
  // Show on hover
  const msgDiv = bubbleEl.closest('.msg');
  if (msgDiv) {
    msgDiv.addEventListener('mouseenter', () => actEl.style.opacity = '1');
    msgDiv.addEventListener('mouseleave', () => actEl.style.opacity = '0');
  }
  // Store content for later
  if (!window._msgContents) window._msgContents = {};
  window._msgContents[msgId] = content;
}

function copyMsgContent(msgId) {
  const content = window._msgContents?.[msgId] || '';
  navigator.clipboard.writeText(content).then(() => toast('📋 Copied', 'ok', 1200));
}

async function regenerateMsg(msgId) {
  // Find the user message just before this agent message
  const msgs = document.querySelectorAll('.msg');
  let userMsg = '';
  for (const m of msgs) {
    if (m.id === msgId) break;
    if (m.classList.contains('user')) {
      userMsg = m.querySelector('.msg-bubble')?.textContent || '';
    }
  }
  if (userMsg) {
    toast('↺ Regenerating…', 'ok', 1500);
    document.getElementById(msgId)?.closest('.msg')?.remove();
    // Re-send last user message
    const fakeInput = document.getElementById('chat-input');
    if (fakeInput) { fakeInput.value = userMsg; }
    await sendChat();
  }
}

function branchFromMsg(msgId) {
  toast('⎇ Branch conversation — session fork coming soon', 'ok', 3000);
}

// Patch addMessage to include actions
const _origAddMessage = addMessage;
addMessage = function(content, role, avatar, name) {
  const bubbleEl = _origAddMessage(content, role, avatar, name);
  const msgId = 'msg_' + Date.now() + '_' + Math.random().toString(36).slice(2,5);
  const msgDiv = bubbleEl?.closest('.msg');
  if (msgDiv) msgDiv.id = msgId;
  if (bubbleEl && role !== 'user') setTimeout(() => addMessageActions(bubbleEl, role, content, msgId), 100);
  return bubbleEl;
};

// Patch updateMessageBubble to add actions when done streaming
const _origUpdateBubble2 = window.updateMessageBubble || updateMessageBubble;
updateMessageBubble = function(el, text) {
  if (!el) return;
  el.innerHTML = renderMarkdownEnhanced(text);
  el.closest('.msg')?.parentElement?.scrollTo({ top: el.closest('.msg')?.parentElement?.scrollHeight, behavior: 'smooth' });
  // Store for copy/speak
  const msgId = el.closest('.msg')?.id;
  if (msgId) {
    if (!window._msgContents) window._msgContents = {};
    window._msgContents[msgId] = text;
  }
  if (window._hljsReady) {
    el.querySelectorAll('code[class*="hljs"]').forEach(block => {
      if (!block.dataset.highlighted) window.hljs.highlightElement(block);
    });
  }
};
window.updateMessageBubble = updateMessageBubble;

// Add CSS for message actions
(function addMsgActionCSS() {
  const s = document.createElement('style');
  s.textContent = `
    .msg-action-btn {
      background:var(--bg-3);border:1px solid var(--border);border-radius:6px;
      padding:3px 8px;cursor:pointer;color:var(--text-2);font-size:12px;
      transition:var(--transition);
    }
    .msg-action-btn:hover{background:var(--bg-4);color:var(--text-0)}
    .msg-bubble p{margin-bottom:6px}
    .msg-bubble h1,.msg-bubble h2,.msg-bubble h3{margin-top:12px}
  `;
  document.head.appendChild(s);
})();

// ── @mention system ────────────────────────────────────────────────
let mentionDropdownVisible = false;
let mentionQuery = '';

function initAtMentions() {
  const input = document.getElementById('chat-input');
  if (!input || input._atMentionsBound) return;
  input._atMentionsBound = true;

  input.addEventListener('input', e => {
    const val    = input.value;
    const cursor = input.selectionStart;
    const before = val.slice(0, cursor);
    const atIdx  = before.lastIndexOf('@');

    if (atIdx >= 0 && !before.slice(atIdx + 1).includes(' ')) {
      mentionQuery = before.slice(atIdx + 1).toLowerCase();
      showMentionDropdown(mentionQuery, atIdx);
    } else {
      hideMentionDropdown();
    }
  });

  input.addEventListener('keydown', e => {
    if (!mentionDropdownVisible) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter' || e.key === 'Escape') {
      e.preventDefault();
      const items = document.querySelectorAll('.mention-item');
      const focused = document.querySelector('.mention-item.focused');
      if (e.key === 'Escape') { hideMentionDropdown(); return; }
      if (e.key === 'Enter' && focused) { focused.click(); return; }
      if (items.length === 0) return;
      const idx = [...items].indexOf(focused);
      const next = e.key === 'ArrowDown'
        ? items[Math.min(idx + 1, items.length - 1)]
        : items[Math.max(idx - 1, 0)];
      items.forEach(i => i.classList.remove('focused'));
      next?.classList.add('focused');
    }
  });
}

function showMentionDropdown(query, atIdx) {
  let dd = document.getElementById('mention-dropdown');
  if (!dd) {
    dd = document.createElement('div');
    dd.id = 'mention-dropdown';
    dd.style.cssText = 'position:fixed;z-index:9999;background:var(--bg-2);border:1px solid var(--border-hi);border-radius:var(--radius);box-shadow:0 12px 40px rgba(0,0,0,.6);min-width:220px;max-height:200px;overflow-y:auto';
    document.body.appendChild(dd);
  }

  // Position near input
  const inp   = document.getElementById('chat-input');
  const rect  = inp.getBoundingClientRect();
  dd.style.bottom = (window.innerHeight - rect.top + 8) + 'px';
  dd.style.left   = rect.left + 'px';

  // Build items: agents + files
  const agentMatches  = S.agents.filter(a => !query || a.name.toLowerCase().startsWith(query) || a.id.toLowerCase().startsWith(query));
  const fileMatches   = [];  // Could populate from /api/preview/files

  if (!agentMatches.length) { hideMentionDropdown(); return; }

  dd.innerHTML = [
    '<div style="padding:5px 10px;font-size:10px;font-weight:700;color:var(--text-3);text-transform:uppercase">Agents</div>',
    ...agentMatches.slice(0, 6).map(a =>
      `<div class="mention-item" onclick="selectMention('@${a.name}')" style="display:flex;align-items:center;gap:10px;padding:8px 12px;cursor:pointer;transition:var(--transition)" onmouseover="this.style.background='var(--bg-3)'" onmouseout="this.style.background=''">
        <span style="font-size:16px">${a.avatar||'🤖'}</span>
        <div><div style="font-size:13px;font-weight:600">${escHtml(a.name)}</div><div style="font-size:10.5px;color:var(--text-3)">${escHtml(a.role||'')}</div></div>
      </div>`),
  ].join('');

  // Focus first
  dd.querySelector('.mention-item')?.classList.add('focused');
  mentionDropdownVisible = true;
}

function hideMentionDropdown() {
  const dd = document.getElementById('mention-dropdown');
  if (dd) dd.remove();
  mentionDropdownVisible = false;
}

function selectMention(mention) {
  const input  = document.getElementById('chat-input');
  const val    = input.value;
  const cursor = input.selectionStart;
  const before = val.slice(0, cursor);
  const atIdx  = before.lastIndexOf('@');
  const after  = val.slice(cursor);
  input.value  = before.slice(0, atIdx) + mention + ' ' + after;
  input.focus();
  hideMentionDropdown();

  // If @AgentName, switch active agent
  const agentName = mention.slice(1).toLowerCase();
  const matched   = S.agents.find(a => a.name.toLowerCase() === agentName || a.id === agentName);
  if (matched) {
    setActiveAgent(matched);
    toast(`🤖 Switched to ${matched.name}`, 'ok', 1500);
  }
}

// Init @mentions when DOM ready
setTimeout(initAtMentions, 1000);
// Also re-init when nav changes
document.addEventListener('click', () => setTimeout(initAtMentions, 100));

// ── Persistent Sessions ────────────────────────────────────────────
// ── Chat Sessions ─────────────────────────────────────────────────
let currentSessionId = S.sessionId;
let _sessions = [];   // cached session list (renamed from 'sessions' to avoid global pollution)

async function loadSessionsList() {
  try {
    const r = await fetch('/api/sessions?limit=50');
    if (!r.ok) { console.warn('[Sessions] load failed:', r.status); return; }
    const d = await r.json();
    _sessions = d.sessions || [];
    renderSessionsList();
  } catch(ex) {
    console.warn('[Sessions] loadSessionsList error:', ex);
  }
}

function renderSessionsList() {
  const el = document.getElementById('sessions-sidebar');
  if (!el) return;
  if (!_sessions.length) {
    el.innerHTML = '<div style="color:var(--text-3);font-size:12px;padding:12px;text-align:center">No sessions yet</div>';
    return;
  }
  el.innerHTML = _sessions.slice(0, 50).map(s => `
    <div onclick="switchSession(${JSON.stringify(s.id)})"
         style="padding:7px 10px;border-radius:var(--radius-sm);cursor:pointer;transition:background .1s;border:1px solid ${s.id===currentSessionId?'var(--accent)':'transparent'};background:${s.id===currentSessionId?'var(--accent-glow)':''}"
         onmouseover="this.style.background='var(--bg-3)'" onmouseout="this.style.background='${s.id===currentSessionId?'var(--accent-glow)':''}'"
         class="session-item">
      <div style="display:flex;align-items:center;gap:5px;margin-bottom:2px">
        ${s.pinned?'<span style="font-size:10px">📌</span>':''}
        <span style="font-size:11px;flex:1;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--text-0)">${escHtml(s.name||'Untitled')}</span>
        <div style="display:flex;gap:2px;flex-shrink:0">
          <button onclick="event.stopPropagation();pinSession(${JSON.stringify(s.id)},${s.pinned?0:1})"
                  style="background:none;border:none;cursor:pointer;font-size:11px;opacity:.5" title="${s.pinned?'Unpin':'Pin'}">${s.pinned?'📌':'📍'}</button>
          <button onclick="event.stopPropagation();renameSession(${JSON.stringify(s.id)})"
                  style="background:none;border:none;cursor:pointer;font-size:11px;opacity:.5" title="Rename">✏️</button>
          <button onclick="event.stopPropagation();branchSession(${JSON.stringify(s.id)})"
                  style="background:none;border:none;cursor:pointer;font-size:11px;opacity:.5" title="Branch">⎇</button>
          <button onclick="event.stopPropagation();exportSession(${JSON.stringify(s.id)})"
                  style="background:none;border:none;cursor:pointer;font-size:11px;opacity:.5" title="Export">⬇</button>
          <button onclick="event.stopPropagation();deleteSession(${JSON.stringify(s.id)})"
                  style="background:none;border:none;cursor:pointer;font-size:11px;opacity:.5;color:var(--danger)" title="Delete">🗑</button>
        </div>
      </div>
      <div style="font-size:10px;color:var(--text-3);display:flex;gap:6px">
        <span>${escHtml(s.agent_id||'brain')}</span>
        <span>${s.message_count||0} msgs</span>
        <span>${(s.updated_at||'').slice(5,16)}</span>
      </div>
    </div>`).join('');
}

async function switchSession(sessionId) {
  try {
    const r = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/messages`);
    if (!r.ok) { showToast('Failed to load session: HTTP '+r.status); return; }
    const d = await r.json();
    if (d.ok === false) { showToast('Session not found: '+(d.error||'')); return; }

    currentSessionId = sessionId;
    S.sessionId      = sessionId;
    S.chatHistory    = [];

    const msgs = d.messages || [];
    const chatEl = document.getElementById('chat-messages');
    if (chatEl) chatEl.innerHTML = '';
    const emptyEl = document.getElementById('chat-empty');
    if (emptyEl) emptyEl.style.display = msgs.length ? 'none' : 'flex';

    msgs.forEach(m => {
      if (m.role === 'user') {
        addMessage(m.message, 'user', '👤', 'You');
        S.chatHistory.push({role: 'user', content: m.message});
      } else {
        addMessage(m.message, 'agent', S.currentAgent?.avatar || '🤖', m.agent || 'Agent');
        S.chatHistory.push({role: 'assistant', content: m.message});
      }
    });

    renderSessionsList();
    showToast(`📂 Loaded: ${(_sessions.find(s=>s.id===sessionId)||{}).name||sessionId}`);
    toggleSessionsPanel(); // close panel after switching
  } catch(ex) {
    showToast('Session load error: '+ex?.message);
  }
}

async function newSession(name) {
  try {
    const sessionName = name || `Chat ${new Date().toLocaleTimeString()}`;
    const r = await fetch('/api/sessions', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: sessionName, agent_id: S.currentAgent?.id || 'brain'})
    });
    if (!r.ok) { showToast('Failed to create session: HTTP '+r.status); return; }
    const j = await r.json();
    if (!j.ok) { showToast('Create failed: '+(j.error||'Unknown')); return; }
    currentSessionId = j.id;
    S.sessionId      = j.id;
    S.chatHistory    = [];
    if (typeof clearChatHistory === 'function') clearChatHistory();
    else {
      const chatEl = document.getElementById('chat-messages');
      if (chatEl) chatEl.innerHTML = '';
    }
    await loadSessionsList();
    showToast(`✅ New session: ${j.name}`);
  } catch(ex) {
    showToast('New session error: '+ex?.message);
  }
}

async function renameSession(sessionId) {
  const s = _sessions.find(s => s.id === sessionId);
  const name = await gmPrompt('Rename session:', s?.name || '');
  if (!name || !name.trim()) return;
  try {
    const r = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'PATCH', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: name.trim()})
    });
    if (!r.ok) { showToast('Rename failed: HTTP '+r.status); return; }
    const d = await r.json();
    if (!d.ok) { showToast('Rename failed: '+(d.error||'Unknown')); return; }
    showToast('✅ Renamed');
    loadSessionsList();
  } catch(ex) {
    showToast('Rename error: '+ex?.message);
  }
}

async function pinSession(sessionId, pinState) {
  try {
    const r = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'PATCH', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({pinned: !!pinState})
    });
    if (!r.ok) { showToast('Pin failed: HTTP '+r.status); return; }
    showToast(pinState ? '📌 Pinned' : '📍 Unpinned');
    loadSessionsList();
  } catch(ex) {
    showToast('Pin error: '+ex?.message);
  }
}

async function deleteSession(sessionId) {
  const s = _sessions.find(s => s.id === sessionId);
  const name = s?.name || sessionId;
  if (!(await gmDanger('Delete Session', `Delete "${name}" and all its messages? This cannot be undone.`))) return;
  try {
    const r = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`, {method: 'DELETE'});
    if (!r.ok) { showToast('Delete failed: HTTP '+r.status); return; }
    const d = await r.json();
    if (!d.ok) { showToast('Delete failed: '+(d.error||'Unknown')); return; }
    if (sessionId === currentSessionId) {
      const chatEl = document.getElementById('chat-messages');
      if (chatEl) chatEl.innerHTML = '';
      currentSessionId = S.sessionId = 'session_' + Date.now();
    }
    showToast('🗑 Session deleted');
    loadSessionsList();
  } catch(ex) {
    showToast('Delete error: '+ex?.message);
  }
}

async function exportSession(sessionId) {
  try {
    const r = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/export?fmt=markdown`);
    if (!r.ok) { showToast('Export failed: HTTP '+r.status); return; }
    const md = await r.text();
    const blob = new Blob([md], {type: 'text/markdown'});
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `chat-export-${sessionId.slice(0,8)}.md`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('📄 Exported as Markdown');
  } catch(ex) {
    showToast('Export error: '+ex?.message);
  }
}

async function exportSessionJSON(sessionId) {
  try {
    const r = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/export?fmt=json`);
    if (!r.ok) { showToast('Export failed: HTTP '+r.status); return; }
    const d = await r.json();
    const blob = new Blob([JSON.stringify(d, null, 2)], {type: 'application/json'});
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `session-${sessionId.slice(0,8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('📋 Exported as JSON');
  } catch(ex) {
    showToast('Export error: '+ex?.message);
  }
}

async function branchSession(sessionId) {
  const name = await gmPrompt('Branch name:', 'Branched conversation');
  if (!name) return;
  try {
    const r = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/branch`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: name.trim()})
    });
    if (!r.ok) { showToast('Branch failed: HTTP '+r.status); return; }
    const d = await r.json();
    if (!d.ok) { showToast('Branch failed: '+(d.error||'Unknown')); return; }
    showToast(`⎇ Branched → ${d.name} (${d.messages_copied} msgs)`);
    loadSessionsList();
  } catch(ex) {
    showToast('Branch error: '+ex?.message);
  }
}

async function searchSessions(q) {
  if (!q) { loadSessionsList(); return; }
  try {
    const r = await fetch('/api/sessions?q=' + encodeURIComponent(q));
    if (!r.ok) return;
    const d = await r.json();
    _sessions = d.sessions || [];
    renderSessionsList();
  } catch(ex) {
    console.warn('[Sessions] search error:', ex);
  }
}

// Patch sendChat to persist session after each message
(function patchSendChatForSessions() {
  const _orig = window.sendChat;
  if (typeof _orig !== 'function') {
    // Retry if sendChat not defined yet
    setTimeout(patchSendChatForSessions, 500);
    return;
  }
  window.sendChat = async function() {
    await _orig.apply(this, arguments);
    try {
      await fetch(`/api/sessions/${encodeURIComponent(currentSessionId)}/touch`, {method: 'POST'});
      loadSessionsList();
    } catch(e) {}
  };
})();

// Sessions panel injection
(function injectSessionsPanel() {
  const chatPane = document.getElementById('pane-chat');
  if (!chatPane) { setTimeout(injectSessionsPanel, 400); return; }
  if (document.getElementById('sessions-panel')) return;

  const header = chatPane.querySelector('.chat-header');
  if (!header) { setTimeout(injectSessionsPanel, 400); return; }

  // Sessions toggle button
  const btn = document.createElement('button');
  btn.className   = 'icon-btn';
  btn.title       = 'Session history (all chats)';
  btn.textContent = '🗂';
  btn.style.cssText = 'margin-right:4px';
  btn.onclick = toggleSessionsPanel;
  header.insertBefore(btn, header.firstChild);

  // New session button
  const newBtn = document.createElement('button');
  newBtn.className   = 'icon-btn';
  newBtn.title       = 'New chat session';
  newBtn.textContent = '＋';
  newBtn.onclick     = () => newSession();
  header.insertBefore(newBtn, header.firstChild);

  // Sessions panel
  const panel = document.createElement('div');
  panel.id = 'sessions-panel';
  panel.style.cssText = [
    'display:none;position:absolute;top:52px;left:0;width:280px;bottom:0',
    'background:var(--bg-1);border-right:1px solid var(--border);z-index:50',
    'flex-direction:column;overflow:hidden',
  ].join(';');
  panel.innerHTML = `
    <div style="padding:10px 12px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;flex-shrink:0">
      <span style="font-weight:700;font-size:13px">🗂 Sessions</span>
      <div style="display:flex;gap:5px">
        <button onclick="newSession()" class="btn btn-primary btn-sm" title="New session">＋ New</button>
        <button onclick="showSessionStats()" class="btn-sm" title="Session stats">📊</button>
        <button onclick="toggleSessionsPanel()" style="background:none;border:none;color:var(--text-2);cursor:pointer;font-size:16px" title="Close">×</button>
      </div>
    </div>
    <div style="padding:8px">
      <input id="session-search" placeholder="Search sessions…"
             oninput="filterSessions()"
             style="width:100%;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 10px;color:var(--text-0);font-size:12px;outline:none;box-sizing:border-box">
    </div>
    <div id="sessions-sidebar" style="flex:1;overflow-y:auto;padding:4px 8px"></div>`;
  chatPane.style.position = 'relative';
  chatPane.appendChild(panel);
  loadSessionsList();
})();

function toggleSessionsPanel() {
  const p = document.getElementById('sessions-panel');
  if (!p) return;
  const visible = p.style.display !== 'none';
  p.style.display = visible ? 'none' : 'flex';
  if (!visible) loadSessionsList();
}

function filterSessions() {
  const q = (document.getElementById('session-search')?.value || '').toLowerCase().trim();
  if (!q) {
    // Show all
    document.querySelectorAll('.session-item').forEach(el => { el.style.display = ''; });
    return;
  }
  document.querySelectorAll('.session-item').forEach(el => {
    el.style.display = el.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}

async function showSessionStats() {
  try {
    const r = await fetch('/api/sessions/stats/overview');
    if (!r.ok) { showToast('Stats failed: HTTP '+r.status); return; }
    const d = await r.json();
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    overlay.innerHTML = `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:16px;max-width:400px;width:100%;padding:20px">
        <div style="display:flex;justify-content:space-between;margin-bottom:14px">
          <h3 style="margin:0;color:var(--text-0)">📊 Session Stats</h3>
          <button onclick="this.closest('[style*=fixed]').remove()" style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px">
          ${[
            ['💬 Sessions', d.total_sessions],
            ['📨 Messages', d.total_messages.toLocaleString()],
            ['🔤 Tokens', (d.total_tokens||0).toLocaleString()],
            ['💰 Cost', '$'+(d.total_cost||0).toFixed(4)],
            ['📌 Pinned', d.pinned_count],
            ['🔥 Active Today', d.active_today],
          ].map(([l,v]) => `<div style="background:var(--bg-3);border-radius:8px;padding:10px;text-align:center">
            <div style="font-size:18px;font-weight:700;color:var(--text-0)">${v}</div>
            <div style="font-size:10px;color:var(--text-3)">${l}</div>
          </div>`).join('')}
        </div>
        ${d.by_agent?.length ? `<div style="font-size:11px;color:var(--text-2)">
          ${d.by_agent.map(a => `<div style="display:flex;justify-content:space-between;padding:3px 0">${escHtml(a.agent_id||'?')}<strong>${a.count}</strong></div>`).join('')}
        </div>` : ''}
      </div>`;
    overlay.onclick = e => { if(e.target===overlay) overlay.remove(); };
    document.body.appendChild(overlay);
  } catch(ex) {
    showToast('Stats error: '+ex?.message);
  }
}

// Init sessions on startup
setTimeout(loadSessionsList, 1500);



// ═══════════════════════════════════════════════════════════════
//  TEMPLATE GALLERY
// ═══════════════════════════════════════════════════════════════

// ── Template Gallery state ──────────────────────────────────────────────────────
let allTemplates    = [];
let templateCategory = 'all';
let _tmplSort       = 'name';

async function renderTemplates() {
  const pane = document.getElementById('pane-templates');
  if (!pane) return;
  pane.innerHTML = `
    <div style="background:linear-gradient(135deg,var(--bg-1),var(--bg-0));border-bottom:1px solid var(--border);padding:20px 24px">
      <h2 style="font-size:22px;font-weight:900;margin-bottom:4px">🎨 Template Gallery</h2>
      <p style="color:var(--text-2);font-size:13px">14 production-ready templates. One click to scaffold into preview.</p>
      <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap" id="tmpl-cats"></div>
    </div>
    <div style="padding:20px">
      <div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;align-items:center">
        <input id="tmpl-search" placeholder="Search templates…" oninput="filterTemplates()"
               style="flex:1;max-width:300px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;color:var(--text-0);font-size:13px;outline:none">
        <select id="tmpl-sort" onchange="tmplChangeSort(this.value)"
                style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 10px;color:var(--text-0);font-size:12px;outline:none">
          <option value="name">A-Z</option>
          <option value="category">By Category</option>
        </select>
        <span id="tmpl-count" style="font-size:11px;color:var(--text-3)"></span>
      </div>
      <div id="tmpl-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px">
        <div style="color:var(--text-2);grid-column:1/-1">Loading templates…</div>
      </div>
    </div>`;

  try {
    const [tr, cr] = await Promise.all([
      fetch('/api/templates'),
      fetch('/api/templates/categories'),
    ]);
    if (!tr.ok) throw new Error('Templates API error: HTTP '+tr.status);
    if (!cr.ok) throw new Error('Categories API error: HTTP '+cr.status);

    const listData = await tr.json();
    const cats     = await cr.json();
    allTemplates   = listData.templates || listData || [];

    // Category pills
    const catEl = document.getElementById('tmpl-cats');
    if (catEl) {
      catEl.innerHTML = [
        `<span class="bp-btn ${templateCategory==='all'?'active':''}" onclick="filterTemplates('all')">All (${allTemplates.length})</span>`,
        ...cats.map(c => `<span class="bp-btn ${templateCategory===c.id?'active':''}" onclick="filterTemplates(${JSON.stringify(c.id)})">${escHtml(c.label)} (${c.count})</span>`)
      ].join('');
    }
    renderTemplateGrid();

  } catch(ex) {
    const g = document.getElementById('tmpl-grid');
    if (g) g.innerHTML = `<div style="color:var(--danger);grid-column:1/-1">Failed to load templates: ${escHtml(ex?.message||String(ex))}<br><button class="btn-sm" onclick="renderTemplates()" style="margin-top:8px">↻ Retry</button></div>`;
  }
}

function filterTemplates(cat) {
  if (cat !== undefined) templateCategory = cat;
  // Update pill active state
  document.querySelectorAll('#tmpl-cats .bp-btn').forEach(el => {
    const label = el.textContent.trim();
    if (cat === 'all') {
      el.classList.toggle('active', label.startsWith('All'));
    } else if (cat !== undefined) {
      // Match by exact category id embedded in onclick
      const onclick = el.getAttribute('onclick') || '';
      el.classList.toggle('active', onclick.includes(JSON.stringify(cat)));
    }
  });
  const q = document.getElementById('tmpl-search')?.value?.toLowerCase()?.trim() || '';
  renderTemplateGrid(q);
}

function tmplChangeSort(sort) {
  _tmplSort = sort;
  filterTemplates();
}

function renderTemplateGrid(q) {
  q = q || (document.getElementById('tmpl-search')?.value?.toLowerCase()?.trim() || '');
  const grid = document.getElementById('tmpl-grid');
  if (!grid) return;

  let filtered = allTemplates.slice();
  if (templateCategory !== 'all') filtered = filtered.filter(t => t.category === templateCategory);
  if (q) filtered = filtered.filter(t =>
    t.name.toLowerCase().includes(q) ||
    t.description.toLowerCase().includes(q) ||
    (t.tags||[]).some(tag => tag.toLowerCase().includes(q))
  );

  // Sort
  if (_tmplSort === 'category') {
    filtered.sort((a,b) => (a.category||'').localeCompare(b.category||'') || (a.name||'').localeCompare(b.name||''));
  } else {
    filtered.sort((a,b) => (a.name||'').localeCompare(b.name||''));
  }

  // Update count
  const cnt = document.getElementById('tmpl-count');
  if (cnt) cnt.textContent = `${filtered.length} template${filtered.length!==1?'s':''}`;

  if (!filtered.length) {
    grid.innerHTML = `<div style="color:var(--text-3);grid-column:1/-1;text-align:center;padding:40px">No templates match "${escHtml(q)}"</div>`;
    return;
  }

  grid.innerHTML = filtered.map(t => `
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);overflow:hidden;transition:transform .15s,border-color .15s;cursor:default"
         onmouseover="this.style.transform='translateY(-2px)';this.style.borderColor='var(--border-hi)'"
         onmouseout="this.style.transform='';this.style.borderColor='var(--border)'">
      <!-- Preview strip with emoji -->
      <div style="height:80px;background:linear-gradient(135deg,${escHtml(t.preview_color||'#5b8af8')}22,${escHtml(t.preview_color||'#5b8af8')}08);display:flex;align-items:center;justify-content:center;border-bottom:1px solid var(--border)">
        <span style="font-size:40px" role="img" aria-label="${escHtml(t.name)}">${t.emoji||'📄'}</span>
      </div>
      <div style="padding:14px">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
          <span style="font-weight:800;font-size:14px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escHtml(t.name)}">${escHtml(t.name)}</span>
          <span class="tag" style="flex-shrink:0;font-size:10px">${escHtml(t.category||'')}</span>
        </div>
        <p style="font-size:12px;color:var(--text-2);line-height:1.5;margin-bottom:10px;min-height:36px">${escHtml(t.description||'')}</p>
        <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:12px">
          ${(t.tags||[]).slice(0,3).map(tag => `<span style="font-size:10px;padding:2px 7px;border-radius:99px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-3)">${escHtml(tag)}</span>`).join('')}
          ${(t.file_count||0)>1?`<span style="font-size:10px;padding:2px 7px;border-radius:99px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-3)">${t.file_count} files</span>`:''}
        </div>
        <div style="display:flex;gap:6px">
          <button onclick="previewTemplate(${JSON.stringify(t.id)})" class="btn btn-ghost btn-sm" style="flex:1" title="Preview in Studio">👁 Preview</button>
          <button onclick="scaffoldTemplateDialog(${JSON.stringify(t.id)},${JSON.stringify(t.name)})" class="btn btn-primary btn-sm" style="flex:1" title="Scaffold this template">⚡ Use</button>
        </div>
      </div>
    </div>`).join('');
}

async function previewTemplate(templateId) {
  try {
    // Fetch preview HTML from backend
    const r = await fetch(`/api/templates/${encodeURIComponent(templateId)}/preview`);
    if (!r.ok) { showToast('Preview failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (!j.ok) { showToast('Preview failed: '+(j.error||'Unknown')); return; }

    // Scaffold silently then open Studio
    await scaffoldTemplate(templateId, true);
    setTimeout(() => nav('studio'), 400);
    showToast('👁 Preview loaded in Studio');
  } catch(ex) {
    showToast('Preview error: '+ex?.message);
  }
}

async function scaffoldTemplateDialog(templateId, templateName) {
  const projectName = await gmPrompt(
    `Scaffold "${templateName}"`,
    'Project name (optional — leave blank to use template name)',
    templateName
  );
  if (projectName === null) return; // User cancelled
  await scaffoldTemplate(templateId, false, (projectName||'').trim());
}

async function scaffoldTemplate(templateId, silent, projectName) {
  // If allTemplates not loaded yet, load it
  if (!allTemplates.length) {
    try {
      const r = await fetch('/api/templates');
      if (r.ok) {
        const d = await r.json();
        allTemplates = d.templates || d || [];
      }
    } catch(e) {}
  }
  const t = allTemplates.find(x => x.id === templateId);
  if (!silent) showToast(`⚡ Scaffolding ${t?.name||templateId}…`);

  try {
    const r = await fetch(`/api/templates/${encodeURIComponent(templateId)}/scaffold`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({project_name: projectName || (t?.name || templateId)})
    });
    if (!r.ok) {
      showToast('Scaffold failed: HTTP '+r.status);
      return;
    }
    const j = await r.json();
    if (j.ok) {
      if (!silent) showToast(`✅ ${j.template} ready — opening Studio…`);
      studioLoadFileTree?.();
      studioReloadPreview?.();
      if (!silent) setTimeout(() => nav('studio'), 600);
    } else {
      showToast('Scaffold failed: '+(j.error||'Unknown error'));
    }
  } catch(ex) {
    showToast('Scaffold error: '+ex?.message);
  }
}

// Add templates to command palette
if (typeof PALETTE_CMDS !== 'undefined') {
  PALETTE_CMDS.push(
    {icon:'🎨', label:'Template Gallery',     desc:'20+ starter templates', action:()=>nav('templates')},
    {icon:'🚀', label:'SaaS Landing Page',    desc:'Scaffold SaaS template', action:()=>scaffoldTemplate('saas-landing')},
    {icon:'📊', label:'Admin Dashboard',      desc:'Scaffold dashboard',     action:()=>scaffoldTemplate('admin-dashboard')},
    {icon:'✅', label:'Todo App',             desc:'Scaffold kanban todo',   action:()=>scaffoldTemplate('todo-app')},
    {icon:'🎨', label:'Developer Portfolio',  desc:'Scaffold portfolio',     action:()=>scaffoldTemplate('portfolio')},
    {icon:'💬', label:'Chat App',             desc:'Scaffold chat UI',       action:()=>scaffoldTemplate('chat-app')},
    {icon:'🗂',  label:'Sessions',            desc:'View chat history',      action:()=>toggleSessionsPanel()},
    {icon:'＋', label:'New Chat Session',     desc:'Start fresh conversation',action:()=>newSession()},
  );
}

// ═══════════════════════════════════════════════════════════════
//  STUDIO POWER FEATURES
// ═══════════════════════════════════════════════════════════════

// ── Format on save (Prettier-like) ────────────────────────────────
async function studioFormatFile() {
  if (!Studio.editor) return;
  const content = Studio.editor.getValue();
  const ext     = Studio.currentFile.split('.').pop();

  // Use Monaco's built-in formatter if available
  if (window.monaco && Studio.editor) {
    try {
      await Studio.editor.getAction('editor.action.formatDocument')?.run();
      toast('✨ Formatted', 'ok', 1200);
      return;
    } catch(e) {}
  }

  // Fallback: AI format
  const r = await fetch('/api/agent/edit', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      instruction: `Format and prettify this ${ext} code. Fix indentation, spacing, and style. Return only the formatted code.`,
      code: content, language: ext, filepath: Studio.currentFile
    })
  });
  let formatted = '';
  const reader  = r.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    for (const line of decoder.decode(value, {stream:true}).split('\n')) {
      if (!line.startsWith('data:')) continue;
      try { const d = JSON.parse(line.slice(5).trim()); if (d.delta) formatted += d.delta; } catch(e) {}
    }
  }
  if (formatted.trim()) {
    Studio.editor.setValue(formatted.trim().replace(/^```\w*\n?/, '').replace(/\n?```$/, ''));
    toast('✨ Formatted with AI', 'ok', 1500);
  }
}

// Add format button to Studio toolbar
(function addFormatBtn() {
  const toolbar = document.querySelector('.studio-toolbar');
  if (!toolbar || document.getElementById('studio-format-btn')) { setTimeout(addFormatBtn, 800); return; }
  const btn = document.createElement('button');
  btn.id        = 'studio-format-btn';
  btn.className = 'btn btn-ghost btn-sm';
  btn.title     = 'Format file (⌥⇧F)';
  btn.textContent = '✨';
  btn.onclick   = studioFormatFile;
  toolbar.appendChild(btn);
})();

// Format shortcut: Alt+Shift+F
document.addEventListener('keydown', e => {
  if (e.altKey && e.shiftKey && e.key === 'F') {
    e.preventDefault();
    studioFormatFile();
  }
});

// ── Find & Replace panel in Studio ────────────────────────────────
let findReplaceOpen = false;

function toggleFindReplace() {
  if (!Studio.editor) { toast('Open a file first', 'warn'); return; }
  if (findReplaceOpen) {
    Studio.editor.getAction('editor.action.closeReplaceInEditor')?.run();
    findReplaceOpen = false;
  } else {
    Studio.editor.getAction('editor.action.startFindReplaceAction')?.run();
    findReplaceOpen = true;
  }
}

// Add find/replace button
(function addFindReplaceBtn() {
  const toolbar = document.querySelector('.studio-toolbar');
  if (!toolbar || document.getElementById('studio-find-btn')) { setTimeout(addFindReplaceBtn, 800); return; }
  const btn = document.createElement('button');
  btn.id        = 'studio-find-btn';
  btn.className = 'btn btn-ghost btn-sm';
  btn.title     = 'Find & Replace (⌘H)';
  btn.textContent = '🔍';
  btn.onclick   = toggleFindReplace;
  toolbar.appendChild(btn);
})();

// ── In-preview DevTools Console Panel ─────────────────────────────
let consoleMessages = [];
let consoleOpen     = false;

// Listen for console messages from preview iframe
window.addEventListener('message', e => {
  if (e.data?.type === 'preview_console') {
    const msg = { level: e.data.level, text: e.data.text, time: new Date().toLocaleTimeString() };
    consoleMessages.push(msg);
    if (consoleMessages.length > 200) consoleMessages.shift();
    updateConsolePanel();
    // Flash console badge
    const badge = document.getElementById('console-count-badge');
    if (badge) { badge.textContent = consoleMessages.length; badge.style.display = ''; }
  }
});

function toggleConsole() {
  consoleOpen = !consoleOpen;
  const panel = document.getElementById('studio-console-panel');
  if (panel) {
    panel.style.display = consoleOpen ? 'flex' : 'none';
    if (consoleOpen) updateConsolePanel();
  }
}

function updateConsolePanel() {
  const el = document.getElementById('console-messages');
  if (!el) return;
  el.innerHTML = consoleMessages.map(m => {
    const colors = { error:'var(--red)', warn:'var(--yellow)', log:'var(--text-1)', info:'var(--teal)' };
    const c = colors[m.level] || 'var(--text-1)';
    return `<div style="display:flex;gap:8px;padding:3px 10px;border-bottom:1px solid rgba(255,255,255,.04);font-size:11.5px;font-family:monospace">
      <span style="color:var(--text-3);flex-shrink:0">${m.time}</span>
      <span style="color:${c};flex:1;white-space:pre-wrap;word-break:break-all">${escHtml(m.text||'')}</span>
    </div>`;
  }).join('') || '<div style="color:var(--text-3);padding:16px;text-align:center;font-size:12px">No console output yet</div>';
  el.scrollTop = el.scrollHeight;
}

// Inject console bridge into preview iframe on load
(function initConsoleBridge() {
  const frame = document.getElementById('studio-preview-iframe');
  if (!frame) { setTimeout(initConsoleBridge, 500); return; }
  frame.addEventListener('load', () => {
    try {
      const doc = frame.contentDocument || frame.contentWindow?.document;
      if (!doc) return;
      const s = doc.createElement('script');
      s.textContent = `
        ['log','warn','error','info'].forEach(level => {
          const orig = console[level].bind(console);
          console[level] = function(...args) {
            orig(...args);
            try {
              const text = args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' ');
              parent.postMessage({type:'preview_console',level,text},'*');
            } catch(ex){}
          };
        });
        window.addEventListener('error', e => {
          parent.postMessage({type:'preview_console',level:'error',text:e.message+' ('+e.filename?.split('/').pop()+':'+e.lineno+')'},'*');
        });
      `;
      doc.head?.appendChild(s);
    } catch(ex) {}
  });
})();

// Add Console toggle button to preview toolbar
(function addConsoleBtn() {
  const toolbar = document.querySelector('.preview-toolbar');
  if (!toolbar || document.getElementById('console-toggle-btn')) { setTimeout(addConsoleBtn, 800); return; }

  // Console panel (above preview iframe)
  const frameWrap = document.getElementById('studio-frame-wrap');
  if (frameWrap) {
    const consolePanel = document.createElement('div');
    consolePanel.id    = 'studio-console-panel';
    consolePanel.style.cssText = 'display:none;flex-direction:column;height:180px;background:var(--bg-0);border-top:1px solid var(--border);flex-shrink:0';
    consolePanel.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;padding:5px 10px;border-bottom:1px solid var(--border);background:var(--bg-1);flex-shrink:0">
        <span style="font-size:11.5px;font-weight:700;color:var(--text-2)">Console</span>
        <span id="console-count-badge" style="display:none;background:var(--red);color:#fff;font-size:9px;padding:1px 5px;border-radius:99px">0</span>
        <button onclick="consoleMessages=[];updateConsolePanel()" style="margin-left:auto;background:none;border:none;color:var(--text-3);cursor:pointer;font-size:11px">Clear</button>
        <button onclick="toggleConsole()" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:14px">×</button>
      </div>
      <div id="console-messages" style="flex:1;overflow-y:auto"></div>`;
    frameWrap.parentElement?.insertBefore(consolePanel, frameWrap);
  }

  // Toggle button
  const btn = document.createElement('div');
  btn.id    = 'console-toggle-btn';
  btn.className = 'device-btn';
  btn.title    = 'Toggle DevTools console';
  btn.innerHTML = '🔧 Console <span id="console-count-badge" style="display:none;background:var(--red);color:#fff;font-size:9px;padding:1px 5px;border-radius:99px;margin-left:3px">0</span>';
  btn.onclick  = toggleConsole;
  toolbar.appendChild(btn);
})();

// ── Responsive ruler overlay ───────────────────────────────────────
(function addResponsiveRuler() {
  const frameWrap = document.getElementById('studio-frame-wrap');
  if (!frameWrap || document.getElementById('preview-ruler')) { setTimeout(addResponsiveRuler, 800); return; }

  const ruler = document.createElement('div');
  ruler.id    = 'preview-ruler';
  ruler.style.cssText = 'position:absolute;top:0;left:0;right:0;height:20px;background:var(--bg-1);border-bottom:1px solid var(--border);display:flex;align-items:center;font-size:9px;font-family:monospace;color:var(--text-3);pointer-events:none;z-index:5;overflow:hidden;display:none';
  const marks = [320,375,480,640,768,1024,1280,1440,1920];
  ruler.innerHTML = marks.map(w => `<span style="position:absolute;left:calc(${w}/1920*100%);border-left:1px solid var(--border);padding-left:2px">${w}</span>`).join('');
  frameWrap.style.position = 'relative';
  frameWrap.appendChild(ruler);
})();

// ═══════════════════════════════════════════════════════════════
//  SPRINT 7 — GitHub, Database Studio, Composer (Multi-file AI)
// ═══════════════════════════════════════════════════════════════

// ── Extend nav for Sprint 7 ────────────────────────────────────────
const _s7NavBase = function(){}; // nav chain disabled — master nav handles all
function _disabled__s7NavBase(pane) {
  _s7NavBase(pane);
  if (pane === 'github')   renderGitHub();
  if (pane === 'dbstudio') renderDBStudio();
  if (pane === 'composer') renderComposer();
}

// ── GitHub Panel ──────────────────────────────────────────────────
let ghStatus = null, ghSelectedRepo = '';

async function renderGitHub() {
  const pane = document.getElementById('pane-github');
  pane.innerHTML = `<div class="section-head">
    <div><h2>🐙 GitHub Integration</h2><p>Bidirectional sync, branch management, PRs, Pages deploy — all from Agentic OS</p></div>
    <button onclick="renderGitHub()" class="btn btn-ghost btn-sm">⟳ Refresh</button>
  </div>
  <div id="gh-body"><div style="color:var(--text-2);font-size:13px">Loading…</div></div>`;

  try {
    const r = await fetch('/api/github/status');
    if (!r.ok) throw new Error('GitHub status API error ' + r.status);
    ghStatus = await r.json();
    renderGitHubBody(ghStatus);
  } catch(e) {
    document.getElementById('gh-body').innerHTML = `<div style="color:var(--red)">Error: ${escHtml(e.message)}</div>`;
  }
}

function renderGitHubBody(s) {
  const el = document.getElementById('gh-body');
  if (!s.connected) {
    el.innerHTML = `
    <div class="settings-card">
      <h3>🔑 Connect GitHub</h3>
      <p>A GitHub token unlocks: repo create, push/pull code, branch management, PRs, and GitHub Pages deploy.</p>
      <div style="background:var(--bg-1);border-radius:var(--radius-sm);padding:14px;font-size:13px;line-height:1.9;margin-bottom:16px">
        ${(s.setup?.steps||[]).map(step => `<div>${escHtml(step)}</div>`).join('')}
        <a href="${s.setup?.token_url||'https://github.com/settings/tokens'}" target="_blank" style="color:var(--accent);display:block;margin-top:8px;font-weight:700">→ Generate Token on GitHub ↗</a>
      </div>
      <div class="key-input-row">
        <input id="gh-token-input" type="password" class="key-input" placeholder="ghp_…" autocomplete="off">
        <button onclick="saveGHToken()" class="btn btn-primary">Save Token</button>
      </div>
      <div style="font-size:11.5px;color:var(--text-2);margin-top:6px">Scopes needed: <code>repo, workflow, read:user</code></div>
    </div>`;
    return;
  }

  const u = s.user || {};
  el.innerHTML = `
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
    <!-- User card -->
    <div class="settings-card">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
        <img src="${u.avatar_url||''}" style="width:48px;height:48px;border-radius:50%;border:2px solid var(--border)">
        <div>
          <div style="font-weight:800;font-size:15px">${escHtml(u.name||u.login||'')}</div>
          <a href="${u.html_url||''}" target="_blank" style="font-size:12px;color:var(--accent)">@${escHtml(u.login||'')}</a>
          <div style="font-size:11px;color:var(--text-2)">${u.public_repos||0} repos · ${escHtml(u.plan||'free')} plan</div>
        </div>
        <span class="tag green" style="margin-left:auto">✅ Connected</span>
      </div>

      <!-- Quick actions -->
      <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Quick Actions</div>
      <div style="display:flex;flex-direction:column;gap:6px">
        <button onclick="createGHRepo()" class="btn btn-primary btn-sm" style="text-align:left">📦 Create New Repository</button>
        <button onclick="showGHPush()" class="btn btn-ghost btn-sm" style="text-align:left">⬆ Push preview/ to GitHub</button>
        <button onclick="showGHPull()" class="btn btn-ghost btn-sm" style="text-align:left">⬇ Pull from GitHub → preview/</button>
        <button onclick="showGHPages()" class="btn btn-ghost btn-sm" style="text-align:left">🌐 Deploy to GitHub Pages</button>
        <button onclick="showGHPR()" class="btn btn-ghost btn-sm" style="text-align:left">🔀 Create Pull Request</button>
      </div>
    </div>

    <!-- Repo selector + recent repos -->
    <div class="settings-card">
      <div style="font-weight:700;margin-bottom:10px">📂 Your Repositories</div>
      <div style="display:flex;gap:6px;margin-bottom:10px">
        <input id="gh-repo-input" placeholder="owner/repo-name" value="${escHtml(ghSelectedRepo)}"
          style="flex:1;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 10px;color:var(--text-0);font-size:12.5px;outline:none;font-family:monospace">
        <button onclick="ghSelectRepo()" class="btn btn-primary btn-sm">Select</button>
      </div>
      ${ghSelectedRepo ? `<div style="background:var(--accent-glow);border:1px solid var(--accent);border-radius:var(--radius-sm);padding:8px 12px;font-size:12.5px;margin-bottom:10px">
        Selected: <strong>${escHtml(ghSelectedRepo)}</strong>
        <a href="https://github.com/${escHtml(ghSelectedRepo)}" target="_blank" style="color:var(--accent);margin-left:8px">↗</a>
      </div>` : ''}
      <div style="font-size:11px;font-weight:700;color:var(--text-2);margin-bottom:6px">Recent Repos</div>
      <div style="display:flex;flex-direction:column;gap:4px;max-height:220px;overflow-y:auto">
        ${(s.recent_repos||[]).map(r => `
          <div onclick="ghSetRepo('${escHtml(r.full_name)}')"
               style="display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:var(--radius-sm);cursor:pointer;transition:var(--transition)"
               onmouseover="this.style.background='var(--bg-3)'" onmouseout="this.style.background=''">
            <span style="font-size:12px">${r.private?'🔒':'📂'}</span>
            <div style="flex:1;min-width:0">
              <div style="font-size:12.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escHtml(r.name)}</div>
              <div style="font-size:10.5px;color:var(--text-3)">${r.default_branch} · ${r.updated_at}</div>
            </div>
          </div>`).join('')}
      </div>
    </div>
  </div>

  <!-- Action result area -->
  <div id="gh-action-result" style="margin-top:16px"></div>`;
}

function ghSetRepo(fullName) {
  ghSelectedRepo = fullName;
  const inp = document.getElementById('gh-repo-input');
  if (inp) inp.value = fullName;
  toast(`📂 Selected: ${fullName}`, 'ok', 1500);
}

function ghSelectRepo() {
  const inp = document.getElementById('gh-repo-input');
  ghSelectedRepo = (inp?.value || '').trim();
  if (ghSelectedRepo) toast(`📂 Using: ${ghSelectedRepo}`, 'ok', 1500);
}

async function saveGHToken() {
  const token = document.getElementById('gh-token-input')?.value.trim();
  if (!token) { toast('Enter your GitHub token', 'warn'); return; }
  try {
    const r = await fetch('/api/secrets/set', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({key:'GITHUB_TOKEN', value:token, scope:'global'})
    });
    if (!r.ok) { toast('Server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast('🐙 GitHub token saved! Reload to activate.', 'ok', 4000); }
    else toast('Failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('Save failed: ' + ex.message, 'err'); }
}

async function createGHRepo() {
  const name = await gmPrompt('Create GitHub Repository', 'Repository name (e.g. my-awesome-app)', 'agentic-os-project');
  if (!name) return;
  const priv = await gmConfirm('Repository visibility', 'Make this repository private?');
  const res  = document.getElementById('gh-action-result');
  if (res) res.innerHTML = `<div style="color:var(--text-2);font-size:13px">Creating repository…</div>`;
  try {
    const r = await fetch('/api/github/repos/create', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({name, private: priv, description:'Built with Agentic OS'})
    });
    if (!r.ok) { if (res) res.innerHTML = `<div style="color:var(--red)">Server error ${r.status}</div>`; return; }
    const j = await r.json();
    if (j.ok) {
    ghSelectedRepo = j.repo;
    if (res) res.innerHTML = `<div class="settings-card">
      <h3>✅ Repository Created!</h3>
      <p><a href="${j.url}" target="_blank" style="color:var(--accent)">${j.repo} ↗</a></p>
      <div style="font-size:12.5px;color:var(--text-2)">Clone URL: <code style="font-size:11px">${escHtml(j.clone_url)}</code></div>
      <button onclick="showGHPush()" class="btn btn-primary btn-sm" style="margin-top:10px">⬆ Push code now</button>
    </div>`;
    toast(`📦 Repository created: ${j.repo}`, 'ok', 4000);
  } else {
    if (res) res.innerHTML = `<div style="color:var(--red)">${escHtml(j.error||'')}</div>`;
    toast('Failed: ' + (j.error||''), 'err');
  }
  } catch(ex) { if (res) res.innerHTML = `<div style="color:var(--red)">${escHtml(ex.message)}</div>`; toast('Error: ' + ex.message, 'err'); }
}

async function showGHPush() {
  const repo = ghSelectedRepo || await gmPrompt('Push to GitHub', 'Repository (e.g. username/my-repo)', '');
  if (!repo) return;
  ghSelectedRepo = repo;
  const msg = await gmPrompt('Commit message', 'What changed?', `Agentic OS push ${new Date().toISOString().slice(0,10)}`);
  if (msg === null) return;
  const res = document.getElementById('gh-action-result');
  if (res) res.innerHTML = `<div style="color:var(--text-2)">Pushing ${repo}…</div>`;
  try {
    const r = await fetch('/api/github/push', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({repo, message: msg||'Agentic OS push', branch:'main'})
    });
    if (!r.ok) { if (res) res.innerHTML = `<div style="color:var(--red)">Server error ${r.status}</div>`; return; }
    const j = await r.json();
    if (j.ok) {
    if (res) res.innerHTML = `<div class="settings-card">
      <h3>✅ Pushed to GitHub!</h3>
      <p>${j.files_pushed} files pushed to <a href="${j.url}" target="_blank" style="color:var(--accent)">${escHtml(j.repo)} ↗</a></p>
      ${j.errors?.length ? `<div style="color:var(--yellow);font-size:12px">⚠ ${j.errors.length} errors: ${escHtml(j.errors.join(', '))}</div>` : ''}
    </div>`;
    toast(`⬆ Pushed ${j.files_pushed} files to GitHub`, 'ok', 4000);
  } else {
      toast('Push failed: ' + (j.error||''), 'err');
    }
  } catch(ex) { if (res) res.innerHTML = `<div style="color:var(--red)">${escHtml(ex.message)}</div>`; toast('Push error: ' + ex.message, 'err'); }
}

async function showGHPull() {
  const repo = ghSelectedRepo || await gmPrompt('Pull from GitHub', 'Repository (username/repo)', '');
  if (!repo) return;
  ghSelectedRepo = repo;
  const res = document.getElementById('gh-action-result');
  if (res) res.innerHTML = `<div style="color:var(--text-2)">Pulling from ${escHtml(repo)}…</div>`;
  try {
    const r = await fetch('/api/github/pull', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({repo, branch:'main'})
    });
    if (!r.ok) {
      if (res) res.innerHTML = `<div style="color:var(--red)">Server error ${r.status}</div>`;
      return;
    }
    const j = await r.json();
    if (j.ok) {
      if (res) res.innerHTML = `<div class="settings-card">
        <h3>⬇ Pulled from GitHub!</h3>
        <p>${j.files_pulled} files pulled from <strong>${escHtml(repo)}</strong> (${escHtml(j.branch||'main')})</p>
        <div style="font-size:12px;color:var(--text-2);margin-top:6px">Files are now in preview/</div>
        <button onclick="studioLoadFileTree?.()" class="btn btn-ghost btn-sm" style="margin-top:8px">📂 Refresh File Tree</button>
      </div>`;
      toast(`⬇ Pulled ${j.files_pulled} files from GitHub`, 'ok', 3000);
      studioLoadFileTree?.();
    } else {
      if (res) res.innerHTML = `<div style="color:var(--red)">${escHtml(j.error||'Pull failed')}</div>`;
      toast('Pull failed: ' + (j.error||''), 'err');
    }
  } catch(ex) {
    if (res) res.innerHTML = `<div style="color:var(--red)">${escHtml(ex.message)}</div>`;
    toast('Pull error: ' + ex.message, 'err');
  }
}

async function showGHPages() {
  const repo = ghSelectedRepo || await gmPrompt('Deploy to GitHub Pages', 'Repository (username/repo)', '');
  if (!repo) return;
  ghSelectedRepo = repo;
  toast('🌐 Deploying to GitHub Pages…', 'ok', 2000);
  const res = document.getElementById('gh-action-result');
  try {
    const r = await fetch('/api/github/pages/deploy', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({repo})
    });
    if (!r.ok) { if (res) res.innerHTML = `<div style="color:var(--red)">Server error ${r.status}</div>`; return; }
    const j = await r.json();
    if (j.ok) {
    if (res) res.innerHTML = `<div class="settings-card">
      <h3>🌐 Deployed to GitHub Pages!</h3>
      <a href="${j.url}" target="_blank" style="color:var(--accent);font-size:15px;font-weight:700">${j.url} ↗</a>
      <div style="font-size:12px;color:var(--text-2);margin-top:6px">${j.tip}</div>
    </div>`;
    toast(`🌐 GitHub Pages live: ${j.url}`, 'ok', 6000);
  } else {
      if (res) res.innerHTML = `<div style="color:var(--red)">${escHtml(j.error||'Pages deploy failed')}</div>`;
      toast('Pages deploy failed: ' + (j.error||''), 'err');
    }
  } catch(ex) { if (res) res.innerHTML = `<div style="color:var(--red)">${escHtml(ex.message)}</div>`; toast('Pages error: ' + ex.message, 'err'); }
}

async function showGHPR() {
  const repo = ghSelectedRepo || await gmPrompt('Create Pull Request', 'Repository (owner/repo)', '');
  if (!repo) return;
  if (!repo.includes('/')) { toast('Repository must be owner/repo format', 'warn'); return; }
  const [owner, repoName] = repo.split('/', 2);
  if (!owner || !repoName) { toast('Invalid repository format (use owner/repo)', 'warn'); return; }
  const head  = await gmPrompt('Head branch (source)', 'Branch with your changes', 'feature/my-feature');
  if (!head) return;
  const title = await gmPrompt('PR Title', 'What does this PR do?', 'Agentic OS changes');
  if (!title) return;
  try {
    const r = await fetch(`/api/github/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repoName)}/pulls`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({head, title, base:'main', body:'Automated PR from Agentic OS'})
    });
    if (!r.ok) { toast('Server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) {
      toast(`🔀 PR #${j.number} created!`, 'ok', 4000);
      window.open(j.url, '_blank');
    } else toast('PR failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('PR error: ' + ex.message, 'err'); }
}

// ── Database Studio ────────────────────────────────────────────────
var dbActiveTable = '', dbActiveTab = 'sqlite';

async function renderDBStudio() {
  const pane = document.getElementById('pane-dbstudio');
  pane.innerHTML = `<div class="section-head">
    <div><h2>🗄️ Database Studio</h2><p>Visual table browser, SQL editor, and Supabase connect</p></div>
    <div style="display:flex;gap:8px">
      <button onclick="dbSetTab('sqlite')" class="btn ${dbActiveTab==='sqlite'?'btn-primary':'btn-ghost'} btn-sm" id="db-tab-sqlite">📦 SQLite (local)</button>
      <button onclick="dbSetTab('supabase')" class="btn ${dbActiveTab==='supabase'?'btn-primary':'btn-ghost'} btn-sm" id="db-tab-supabase">☁️ Supabase</button>
      <button onclick="dbSetTab('sql')" class="btn ${dbActiveTab==='sql'?'btn-primary':'btn-ghost'} btn-sm" id="db-tab-sql">💻 SQL Editor</button>
      <button onclick="dbSetTab('designer')" class="btn ${dbActiveTab==='designer'?'btn-primary':'btn-ghost'} btn-sm" id="db-tab-designer">🏗️ Schema Designer</button>
    </div>
  </div>
  <div id="db-body"></div>`;
  dbSetTab(dbActiveTab);
}

async function dbSetTab(tab) {
  dbActiveTab = tab;
  ['sqlite','supabase','sql','designer'].forEach(t => {
    const btn = document.getElementById('db-tab-' + t);
    if (btn) { btn.className = btn.className.replace('btn-primary','btn-ghost'); }
    if (t === tab && btn) { btn.className = btn.className.replace('btn-ghost','btn-primary'); }
  });
  const el = document.getElementById('db-body');
  if (!el) return;

  if (tab === 'sqlite') await renderSQLiteTab(el);
  else if (tab === 'supabase') await renderSupabaseTab(el);
  else if (tab === 'sql') renderSQLEditorTab(el);
  else if (tab === 'designer') renderSchemaDesignerTab(el);
}

async function renderSQLiteTab(el) {
  let tables = [];
  try {
    const r = await fetch('/api/db/sqlite/tables');
    if (!r.ok) throw new Error('Tables API error ' + r.status);
    const data = await r.json();
    tables = Array.isArray(data) ? data : (Array.isArray(data?.tables) ? data.tables : []);
  } catch(ex) {
    el.innerHTML = `<div style="color:var(--red);padding:16px">Error loading tables: ${escHtml(ex.message)}</div>`;
    return;
  }
  el.innerHTML = `<div style="display:grid;grid-template-columns:200px 1fr;gap:16px;height:calc(100vh - 200px)">
    <!-- Table list -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:10px;overflow-y:auto">
      <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Tables (${tables.length})</div>
      ${tables.map(t => `
        <div onclick="dbLoadTable(${JSON.stringify(t.name)})"
             style="padding:6px 8px;border-radius:var(--radius-sm);cursor:pointer;font-size:12.5px;margin-bottom:2px;${dbActiveTable===t.name?'background:var(--accent-glow);color:var(--accent-hi)':''}"
             onmouseover="this.style.background='var(--bg-3)'" onmouseout="this.style.background='${dbActiveTable===t.name?'var(--accent-glow)':''}'"
        >
          <div style="font-weight:600">${escHtml(t.name)}</div>
          <div style="font-size:10.5px;color:var(--text-3)">${t.row_count} rows</div>
        </div>`).join('')}
    </div>
    <!-- Table data -->
    <div id="db-table-data" style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);overflow:hidden;display:flex;flex-direction:column">
      <div style="color:var(--text-3);font-size:13px;padding:30px;text-align:center">
        ${tables.length ? 'Select a table →' : 'No tables found'}
      </div>
    </div>
  </div>`;
  if (dbActiveTable) dbLoadTable(dbActiveTable);
}

async function dbLoadTable(name) {
  dbActiveTable = name;
  const el = document.getElementById('db-table-data');
  if (!el) return;
  el.innerHTML = `<div style="color:var(--text-2);padding:12px">Loading ${name}…</div>`;
  try {
    const r    = await fetch(`/api/db/sqlite/table/${encodeURIComponent(name)}?limit=100`);
    if (!r.ok) { el.innerHTML = `<div style="color:var(--red);padding:12px">Server error ${r.status}</div>`; return; }
    const data = await r.json();
    if (!data.ok) { el.innerHTML = `<div style="color:var(--red);padding:12px">${escHtml(data.error||'error')}</div>`; return; }

    const { columns, rows, total } = data;
    el.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid var(--border);background:var(--bg-1);flex-shrink:0">
        <span style="font-weight:700;font-size:13px">${escHtml(name)}</span>
        <span style="font-size:11px;color:var(--text-2)">${total} rows · ${columns.length} columns</span>
        <div style="margin-left:auto;display:flex;gap:6px">
          <button onclick="dbInsertRow('${escHtml(name)}')" class="btn btn-primary btn-sm">+ Row</button>
          <button onclick="dbSetTab('sql')" class="btn btn-ghost btn-sm">SQL</button>
        </div>
      </div>
      <div style="overflow:auto;flex:1">
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead>
            <tr style="background:var(--bg-1);position:sticky;top:0;z-index:1">
              ${columns.map(c => `<th style="padding:7px 10px;text-align:left;border-bottom:1px solid var(--border);color:var(--text-2);font-weight:700;white-space:nowrap">${escHtml(c)}</th>`).join('')}
              <th style="padding:7px 10px;border-bottom:1px solid var(--border);width:40px"></th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(row => `
              <tr style="border-bottom:1px solid var(--border)" onmouseover="this.style.background='var(--bg-3)'" onmouseout="this.style.background=''">
                ${columns.map(c => `<td style="padding:6px 10px;color:var(--text-1);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escHtml(String(row[c]??''))}">${escHtml(String(row[c]??''))}</td>`).join('')}
                <td style="padding:6px 10px"><button onclick="dbDeleteRow(${JSON.stringify(name)},${JSON.stringify(String(row[columns[0]]??''))},${JSON.stringify(columns[0])})" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:12px">🗑</button></td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>
      ${rows.length === 0 ? '<div style="text-align:center;padding:20px;color:var(--text-3)">No rows</div>' : ''}`;
  } catch(e) {
    el.innerHTML = `<div style="color:var(--red);padding:12px">${e.message}</div>`;
  }
}

async function dbInsertRow(table) {
  // Get columns first
  try {
    const r    = await fetch(`/api/db/sqlite/table/${encodeURIComponent(table)}?limit=0`);
    if (!r.ok) { toast('Column fetch failed: server error ' + r.status, 'err'); return; }
    const data = await r.json();
    const cols = (data.columns||[]).filter(c => c !== 'id' && c !== 'created_at');
    if (!cols.length) { toast('Cannot determine columns', 'warn'); return; }

    const values = {};
    for (const col of cols.slice(0,5)) {
      const v = await gmPrompt(`Insert row`, `Value for "${col}"`, '');
      if (v === null) return;
      values[col] = v;
    }

    const r2 = await fetch(`/api/db/sqlite/table/${encodeURIComponent(table)}/insert`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({row: values})
    });
    if (!r2.ok) { toast('Insert failed: server error ' + r2.status, 'err'); return; }
    const j = await r2.json();
    if (j.ok) { toast('Row inserted ✅', 'ok', 1500); dbLoadTable(table); }
    else toast('Insert failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('Insert error: ' + ex.message, 'err'); }
}

async function dbDeleteRow(table, value, pk) {
  if (!(await gmDanger(`Delete row`, `Delete row where ${pk}="${value}"?`))) return;
  try {
    const r = await fetch(`/api/db/sqlite/table/${encodeURIComponent(table)}/row`, {
      method:'DELETE', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({pk_column: pk, pk_value: value})
    });
    if (!r.ok) { toast('Delete failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast('Row deleted', 'ok', 1500); dbLoadTable(table); }
    else toast('Delete failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('Delete error: ' + ex.message, 'err'); }
}

async function renderSupabaseTab(el) {
  let s = {connected: false, setup: {steps: [], url: ''}};
  try {
    const r = await fetch('/api/db/supabase/status');
    if (!r.ok) throw new Error('Supabase status error ' + r.status);
    s = await r.json();
  } catch(ex) {
    el.innerHTML = `<div style="color:var(--red);padding:16px">Error: ${escHtml(ex.message)}</div>`;
    return;
  }
  if (!s.connected) {
    el.innerHTML = `<div class="settings-card">
      <h3>☁️ Connect Supabase</h3>
      <p>PostgreSQL + Auth + Storage — the same stack Lovable uses.</p>
      <div style="background:var(--bg-1);border-radius:var(--radius-sm);padding:12px;font-size:13px;line-height:1.8;margin-bottom:14px">
        ${(s.setup?.steps||[]).map(s=>escHtml(s)).join('<br>')}
        <a href="${s.setup?.url||'https://supabase.com'}" target="_blank" style="color:var(--accent);display:block;margin-top:8px">→ Create Supabase project ↗</a>
      </div>
      <div style="display:flex;flex-direction:column;gap:8px">
        <div>
          <label style="font-size:11px;font-weight:700;color:var(--text-2);display:block;margin-bottom:4px">SUPABASE_URL</label>
          <input id="supa-url-input" placeholder="https://xxxx.supabase.co" class="key-input" style="width:100%">
        </div>
        <div>
          <label style="font-size:11px;font-weight:700;color:var(--text-2);display:block;margin-bottom:4px">SUPABASE_ANON_KEY</label>
          <input id="supa-key-input" type="password" placeholder="eyJhbGci…" class="key-input" style="width:100%">
        </div>
        <button onclick="saveSupabaseKeys()" class="btn btn-primary">Connect Supabase</button>
      </div>
    </div>`;
    return;
  }

  el.innerHTML = `<div class="settings-card">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px">
      <span style="font-size:24px">☁️</span>
      <div><div style="font-weight:800">Supabase Connected</div>
      <div style="font-size:12px;color:var(--accent)">${escHtml(s.url||'')}</div></div>
      <span class="tag green" style="margin-left:auto">✅ Connected</span>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
      <button onclick="supaGenerateSchema()" class="btn btn-primary">🤖 AI Schema Designer</button>
      <button onclick="window.open('${s.url?.replace('.supabase.co','')}.supabase.co/project/default/editor','_blank')" class="btn btn-ghost">SQL Editor ↗</button>
      <button onclick="window.open('${s.url?.replace('.supabase.co','')}.supabase.co/project/default/auth/users','_blank')" class="btn btn-ghost">Auth Users ↗</button>
      <button onclick="window.open('${s.url?.replace('.supabase.co','')}.supabase.co/project/default/storage/buckets','_blank')" class="btn btn-ghost">Storage ↗</button>
    </div>
  </div>`;
}

async function saveSupabaseKeys() {
  const url = document.getElementById('supa-url-input')?.value.trim();
  const key  = document.getElementById('supa-key-input')?.value.trim();
  if (!url || !key) { toast('Both URL and key required', 'warn'); return; }
  try {
    const r1 = await fetch('/api/secrets/set', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:'SUPABASE_URL',value:url,scope:'global'})});
    const r2 = await fetch('/api/secrets/set', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:'SUPABASE_ANON_KEY',value:key,scope:'global'})});
    if (!r1.ok || !r2.ok) { toast('Save failed: server error', 'err'); return; }
    toast('☁️ Supabase connected! Reload to activate.', 'ok', 4000);
  } catch(ex) { toast('Save failed: ' + ex.message, 'err'); }
}

async function supaGenerateSchema() {
  const desc = await gmPrompt('AI Schema Designer', 'Describe your app data model\ne.g. "SaaS with users, projects, tasks, and comments"', '', true);
  if (!desc) return;
  toast('🤖 Generating schema…', 'ok', 2000);
  try {
    const r = await fetch('/api/db/supabase/ai-setup', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({description: desc})
    });
    if (!r.ok) { toast('Schema generation failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) {
    await gmAlert('Generated Supabase Schema', `<div style="font-size:12px;font-family:monospace;white-space:pre-wrap;max-height:400px;overflow-y:auto;background:var(--bg-0);padding:10px;border-radius:6px">${escHtml(j.sql)}</div>
      <div style="margin-top:10px;font-size:12px;color:var(--text-2)">Copy this SQL and run it in your Supabase SQL Editor.</div>`);
    } else toast('Schema generation failed', 'err');
  } catch(ex) { toast('Schema error: ' + ex.message, 'err'); }
}

function renderSQLEditorTab(el) {
  el.innerHTML = `<div style="display:flex;flex-direction:column;gap:12px">
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:16px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
        <div style="font-weight:700">💻 SQL Editor</div>
        <div style="display:flex;gap:6px">
          <label style="display:flex;align-items:center;gap:5px;font-size:12px;cursor:pointer">
            <input type="checkbox" id="sql-allow-write" style="accent-color:var(--red)">
            <span style="color:var(--red)">Allow writes</span>
          </label>
          <button onclick="runSQL()" class="btn btn-primary btn-sm">▶ Run SQL</button>
        </div>
      </div>
      <textarea id="sql-editor" placeholder="SELECT * FROM agents LIMIT 10;" style="width:100%;min-height:120px;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;color:var(--text-0);font-size:13px;font-family:'JetBrains Mono',monospace;resize:vertical;outline:none"></textarea>
    </div>
    <div id="sql-results" style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:16px;min-height:100px">
      <div style="color:var(--text-3);font-size:13px">Run a query to see results</div>
    </div>
  </div>`;

  // Keyboard shortcut
  document.getElementById('sql-editor')?.addEventListener('keydown', e => {
    if ((e.ctrlKey||e.metaKey) && e.key==='Enter') { e.preventDefault(); runSQL(); }
  });
}

async function runSQL() {
  const sql         = document.getElementById('sql-editor')?.value.trim();
  const allowWrite  = document.getElementById('sql-allow-write')?.checked;
  if (!sql) return;
  const res = document.getElementById('sql-results');
  if (res) res.innerHTML = '<div style="color:var(--text-2)">Running…</div>';

  try {
    const r = await fetch('/api/db/sqlite/query', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({sql, allow_write: allowWrite})
    });
    if (!r.ok) { if (res) res.innerHTML = `<div style="color:var(--red)">Server error ${r.status}</div>`; return; }
    const j = await r.json();
    if (!j.ok) {
    res.innerHTML = `<div style="color:var(--red);font-size:13px">Error: ${escHtml(j.error||'')}</div>`;
    return;
  }
  if (j.type === 'write') {
    res.innerHTML = `<div style="color:var(--green)">✅ ${j.rows_affected} rows affected</div>`;
    return;
  }
  const cols = j.columns || [];
  const rows = j.rows || [];
  res.innerHTML = `<div style="font-size:12px;color:var(--text-2);margin-bottom:8px">${rows.length} rows returned</div>
    <div style="overflow:auto;max-height:300px">
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr>${cols.map(c=>`<th style="padding:5px 8px;text-align:left;border-bottom:1px solid var(--border);color:var(--text-2);font-weight:700">${escHtml(c)}</th>`).join('')}</tr></thead>
        <tbody>${rows.map(row=>`<tr style="border-bottom:1px solid var(--border)">${cols.map(c=>`<td style="padding:5px 8px;color:var(--text-1)">${escHtml(String(row[c]??''))}</td>`).join('')}</tr>`).join('')}</tbody>
      </table>
    </div>`;
  } catch(ex) { if (res) res.innerHTML = `<div style="color:var(--red)">Error: ${escHtml(ex.message)}</div>`; }
}

async function renderSchemaDesignerTab(el) {
  el.innerHTML = `<div class="settings-card">
    <h3>🏗️ AI Schema Designer</h3>
    <p>Describe your data model in plain English → AI generates the SQL CREATE TABLE statement.</p>
    <textarea id="schema-desc" placeholder="A blog platform with users, posts, categories, tags, and comments. Users can like posts. Posts have a publish status." style="width:100%;min-height:80px;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;color:var(--text-0);font-size:13px;resize:none;outline:none;font-family:inherit;margin-bottom:10px"></textarea>
    <div style="display:flex;gap:8px">
      <button onclick="generateSchema('sqlite')" class="btn btn-primary">Generate SQLite</button>
      <button onclick="generateSchema('supabase')" class="btn btn-ghost">Generate Supabase SQL</button>
    </div>
    <div id="schema-result" style="margin-top:14px"></div>
  </div>`;
}

async function generateSchema(type) {
  const desc = document.getElementById('schema-desc')?.value.trim();
  if (!desc) { toast('Describe your data model first', 'warn'); return; }
  const el = document.getElementById('schema-result');
  if (el) el.innerHTML = '<div style="color:var(--text-2)">Generating schema…</div>';
  const endpoint = type==='supabase' ? '/api/db/supabase/ai-setup' : '/api/db/sqlite/ai-schema';
  try {
    const r = await fetch(endpoint, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({description: desc})
    });
    if (!r.ok) { if (el) el.innerHTML = `<div style="color:var(--red)">Server error ${r.status}</div>`; return; }
    const j = await r.json();
    if (el && j.sql) {
    el.innerHTML = `<div style="position:relative">
      <pre style="background:var(--bg-0);border:1px solid var(--border);border-radius:var(--radius-sm);padding:12px;font-family:monospace;font-size:12px;white-space:pre-wrap;max-height:300px;overflow-y:auto">${escHtml(j.sql)}</pre>
      <div style="display:flex;gap:6px;margin-top:8px">
        <button onclick="navigator.clipboard.writeText(${JSON.stringify(j.sql)}).then(()=>toast('📋 Copied','ok',1500))" class="btn btn-ghost btn-sm">📋 Copy</button>
        ${type==='sqlite'?`<button onclick="runGeneratedSchema(${JSON.stringify(j.sql)})" class="btn btn-primary btn-sm">▶ Create Table</button>`:''}
      </div>
    </div>`;
    }
  } catch(ex) { if (el) el.innerHTML = `<div style="color:var(--red)">Error: ${escHtml(ex.message)}</div>`; }
}

async function runGeneratedSchema(sql) {
  try {
    const r = await fetch('/api/db/sqlite/table/create', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({sql})
    });
    if (!r.ok) { toast('Create failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast('✅ Table created!', 'ok'); dbSetTab('sqlite'); }
    else toast('Error: ' + (j.error||''), 'err');
  } catch(ex) { toast('Error: ' + ex.message, 'err'); }
}

// ── Composer (Multi-file AI Agent) ────────────────────────────────
let composerRunning = false;

async function renderComposer() {
  const pane = document.getElementById('pane-composer');
  pane.innerHTML = `<div class="section-head">
    <div><h2>🪄 Composer</h2><p>Multi-file AI agent — one instruction builds your entire project. Screenshot → Code. Branch previews.</p></div>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
    <!-- Left: Input panels -->
    <div style="display:flex;flex-direction:column;gap:14px">

      <!-- Multi-file agent -->
      <div class="settings-card">
        <h3>🤖 Multi-File Agent</h3>
        <p>Like Cursor Composer — describe what to build, AI creates all needed files across your project.</p>
        <select id="comp-framework" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 10px;color:var(--text-0);font-size:13px;outline:none;margin-bottom:8px">
          <option value="web">🌐 Web (HTML/CSS/JS)</option>
          <option value="nextjs">⚛️ Next.js</option>
          <option value="sveltekit">🔥 SvelteKit</option>
          <option value="expo">📱 Expo React Native</option>
        </select>
        <textarea id="comp-instruction" placeholder="Build a SaaS dashboard with a sidebar nav, stats cards, a data table, and a dark mode toggle. Make it production-ready with Tailwind CSS." style="width:100%;min-height:100px;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;color:var(--text-0);font-size:13px;resize:none;outline:none;font-family:inherit;margin-bottom:10px"></textarea>
        <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px" id="comp-prompts">
          ${[
            'Dark mode landing page with hero, features, pricing',
            'Login + signup form with validation',
            'Dashboard with charts and sidebar',
            'Mobile-first portfolio site',
            'E-commerce product page with cart',
          ].map(p => `<button onclick="document.getElementById('comp-instruction').value='${p}'" class="chat-tool" style="font-size:11px">${p.slice(0,30)}…</button>`).join('')}
        </div>
        <button onclick="runComposer()" class="btn btn-primary" style="width:100%" id="comp-run-btn">🪄 Build with AI</button>
        <div id="comp-status" style="font-size:12px;color:var(--text-2);margin-top:8px;min-height:18px"></div>
      </div>

      <!-- Screenshot to code -->
      <div class="settings-card">
        <h3>📷 Screenshot → Code</h3>
        <p>Paste a design screenshot and AI rebuilds it as working code. Like v0's image input.</p>
        <div id="screenshot-drop" style="border:2px dashed var(--border);border-radius:var(--radius-sm);padding:24px;text-align:center;cursor:pointer;transition:var(--transition);margin-bottom:10px" 
             ondragover="event.preventDefault();this.style.borderColor='var(--accent)'" 
             ondragleave="this.style.borderColor='var(--border)'"
             ondrop="handleScreenshotDrop(event)"
             onclick="document.getElementById('screenshot-file').click()">
          <div style="font-size:32px;margin-bottom:8px">🖼️</div>
          <div style="font-size:13px;color:var(--text-2)">Drop a screenshot here, or click to upload</div>
          <div style="font-size:11px;color:var(--text-3);margin-top:4px">PNG, JPG, WebP — any design or UI screenshot</div>
        </div>
        <input type="file" id="screenshot-file" accept="image/*" style="display:none" onchange="handleScreenshotFile(event)">
        <div id="screenshot-preview" style="display:none;margin-bottom:10px">
          <img id="screenshot-img" style="max-width:100%;max-height:200px;border-radius:var(--radius-sm);border:1px solid var(--border)">
        </div>
        <div style="display:flex;gap:8px">
          <select id="s2c-framework" style="flex:1;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px;color:var(--text-0);font-size:12.5px;outline:none">
            <option value="web">Web (HTML)</option>
            <option value="react">React</option>
          </select>
          <button onclick="runScreenshotToCode()" class="btn btn-primary" id="s2c-btn" disabled>📷 Convert</button>
        </div>
        <div id="s2c-status" style="font-size:12px;color:var(--text-2);margin-top:6px"></div>
      </div>
    </div>

    <!-- Right: Results + Branch previews -->
    <div style="display:flex;flex-direction:column;gap:14px">
      <!-- Composer output -->
      <div id="comp-results" style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:16px;min-height:200px">
        <div style="color:var(--text-3);font-size:13px">Run the composer → file results appear here</div>
      </div>

      <!-- Branch previews -->
      <div class="settings-card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
          <h3 style="margin:0">🌿 Branch Previews</h3>
          <button onclick="createBranchPreview()" class="btn btn-primary btn-sm">+ Snapshot</button>
        </div>
        <p style="font-size:12.5px;color:var(--text-2)">Snapshot current state as a named preview URL. Share with clients before making changes.</p>
        <div id="branch-list" style="display:flex;flex-direction:column;gap:6px">Loading…</div>
      </div>
    </div>
  </div>`;

  loadBranchPreviews();
}

async function runComposer() {
  const instruction = document.getElementById('comp-instruction')?.value.trim();
  const framework   = document.getElementById('comp-framework')?.value || 'web';
  if (!instruction) { toast('Enter an instruction', 'warn'); return; }
  if (composerRunning) { toast('Composer is already running…', 'warn'); return; }

  composerRunning = true;
  const btn    = document.getElementById('comp-run-btn');
  const status = document.getElementById('comp-status');
  const results = document.getElementById('comp-results');
  btn.disabled = true; btn.textContent = '⏳ Building…';
  status.textContent = 'Planning…';
  results.innerHTML  = '';

  const fileCards = {};

  try {
    const resp = await fetch('/api/composer/run', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({instruction, framework, stream: true})
    });
    // FIX 7a: check HTTP status before reading body
    if (!resp.ok) { throw new Error(`Server error: HTTP ${resp.status}`); }
    // FIX 7b: null guard before calling getReader()
    if (!resp.body) { throw new Error('No response body — check server'); }
    const reader  = resp.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      const text = decoder.decode(value, {stream:true});
      for (const line of text.split('\n')) {
        if (!line.startsWith('data:')) continue;
        try {
          const ev = JSON.parse(line.slice(5).trim());

          if (ev.type === 'plan_ready' && ev.plan) {
            const plan = ev.plan;
            status.textContent = plan.summary || 'Building…';
            results.innerHTML = `<div style="font-size:12px;color:var(--text-2);margin-bottom:10px">📋 ${escHtml(plan.summary||'')}</div>`;
            (plan.files||[]).forEach(f => {
              const card = document.createElement('div');
              card.id   = `comp-file-${btoa(f.path).slice(0,8)}`;
              card.style.cssText = 'background:var(--bg-3);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;margin-bottom:6px;font-size:12px';
              card.innerHTML = `<span style="font-family:monospace">${escHtml(f.path)}</span> <span style="color:var(--text-3)">⏳</span>`;
              results.appendChild(card);
            });
          }

          if (ev.type === 'file_start') {
            const id = `comp-file-${btoa(ev.path).slice(0,8)}`;
            const existing = document.getElementById(id);
            if (existing) existing.innerHTML = `<span style="font-family:monospace;color:var(--yellow)">${escHtml(ev.path)}</span> <span style="color:var(--yellow)">⚡ writing…</span>`;
            status.textContent = `Writing ${ev.path}…`;
          }

          if (ev.type === 'file_done') {
            const id = `comp-file-${btoa(ev.path).slice(0,8)}`;
            const existing = document.getElementById(id);
            if (existing) existing.innerHTML = `<span style="font-family:monospace;color:var(--green)">${escHtml(ev.path)}</span> <span style="color:var(--green)">✅ ${ev.bytes}B</span>`;
          }

          if (ev.type === 'done') {
            const written = ev.files_written || [];
            status.innerHTML = `✅ Done in ${ev.duration_ms}ms — ${written.length} files written`;
            if (written.length > 0) {
              results.innerHTML += `<div style="margin-top:10px;display:flex;gap:8px">
                <button onclick="nav('studio')" class="btn btn-primary btn-sm">🎬 View in Studio</button>
                <button onclick="createBranchPreview()" class="btn btn-ghost btn-sm">📸 Snapshot</button>
                <button onclick="showGHPush()" class="btn btn-ghost btn-sm">⬆ Push to GitHub</button>
              </div>`;
              // Reload studio file tree
              studioLoadFileTree?.();
              studioReloadPreview?.();
              toast(`🪄 Built ${written.length} files!`, 'ok', 4000);
            }
          }
        } catch(e) {}
      }
    }
  } catch(e) {
    status.textContent = '✗ ' + e.message;
    toast('Composer error: ' + e.message, 'err');
  } finally {
    composerRunning = false;
    btn.disabled = false; btn.textContent = '🪄 Build with AI';
  }
}

// Screenshot to code
let screenshotB64 = '';

function handleScreenshotDrop(e) {
  e.preventDefault();
  const file = e.dataTransfer.files[0];
  if (file) loadScreenshotFile(file);
}

function handleScreenshotFile(e) {
  const file = e.target.files[0];
  if (file) loadScreenshotFile(file);
}

function loadScreenshotFile(file) {
  const reader = new FileReader();
  reader.onload = e => {
    screenshotB64 = e.target.result;
    const prev = document.getElementById('screenshot-preview');
    const img  = document.getElementById('screenshot-img');
    const btn  = document.getElementById('s2c-btn');
    const drop = document.getElementById('screenshot-drop');
    if (prev) prev.style.display = 'block';
    if (img)  img.src = screenshotB64;
    if (btn)  btn.disabled = false;
    if (drop) drop.style.borderColor = 'var(--green)';
    toast('📷 Image loaded — click Convert', 'ok', 2000);
  };
  reader.readAsDataURL(file);
}

async function runScreenshotToCode() {
  if (!screenshotB64) { toast('Upload a screenshot first', 'warn'); return; }
  const fw  = document.getElementById('s2c-framework')?.value || 'web';
  const btn = document.getElementById('s2c-btn');
  const st  = document.getElementById('s2c-status');
  btn.disabled = true; btn.textContent = '⏳ Converting…';
  if (st) st.textContent = 'AI is analyzing your screenshot…';
  // FIX 8: try/catch for network failures
  try {
    const r = await fetch('/api/composer/screenshot-to-code', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({image_b64: screenshotB64.split(',')[1], framework: fw, filename:'index.html'})
    });
    if (!r.ok) { throw new Error(`HTTP ${r.status}`); }
    const j = await r.json();
    if (j.ok) {
      if (st) st.innerHTML = `✅ Converted! ${j.tokens} tokens · <a href="${j.preview_url}" target="_blank" style="color:var(--accent)">Preview ↗</a>`;
      studioLoadFileTree?.();
      studioReloadPreview?.();
      toast('📷 Screenshot converted to code!', 'ok', 4000);
      nav('studio');
    } else {
      if (st) st.textContent = '✗ ' + (j.error||'Conversion failed — check your API key supports vision');
      toast(j.error || 'Conversion failed', 'err');
    }
  } catch(ex) {
    if (st) st.textContent = '✗ ' + ex.message;
    toast('Conversion error: ' + ex.message, 'err');
  } finally {
    btn.disabled = false; btn.textContent = '📷 Convert';
  }
}

// Branch previews
async function loadBranchPreviews() {
  try {
    const r = await fetch('/api/composer/preview/branches');
    const j = await r.json();
    const el = document.getElementById('branch-list');
    if (!el) return;
    if (!j.branches?.length) {
      el.innerHTML = '<div style="color:var(--text-3);font-size:12.5px">No snapshots yet. Click "+ Snapshot" to capture the current state.</div>';
      return;
    }
    el.innerHTML = j.branches.map(b => `
      <div style="background:var(--bg-3);border-radius:var(--radius-sm);padding:8px 12px;display:flex;align-items:center;gap:8px">
        <div style="flex:1;min-width:0">
          <div style="font-size:12.5px;font-weight:600">${escHtml(b.title||b.name)}</div>
          <div style="font-size:11px;color:var(--text-3)">${b.files} files · ${(b.created_at||'').slice(0,16)}</div>
        </div>
        <a href="${b.url}" target="_blank" class="btn btn-ghost btn-sm">View ↗</a>
        <button onclick="deleteBranchPreview('${escHtml(b.name)}')" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:12px">🗑</button>
      </div>`).join('');
  } catch(e) {}
}

async function createBranchPreview() {
  const name = await gmPrompt('Create Preview Snapshot', 'Name this snapshot (e.g. v1-homepage, client-review)', `snapshot-${Date.now()}`);
  if (!name) return;
  const r = await fetch('/api/composer/preview/branch', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name, title: name})
  });
  const j = await r.json();
  if (j.ok) {
    toast(`📸 Snapshot created! ${j.files} files`, 'ok', 3000);
    loadBranchPreviews();
    await gmAlert('Branch Preview Created 🌿',
      `<div>Share this URL with clients for review:</div>
       <code style="display:block;background:var(--bg-0);padding:8px;border-radius:4px;margin:10px 0;font-size:12px">http://localhost:8787${j.url}</code>
       <div style="font-size:12px;color:var(--text-2)">The snapshot is frozen — changes to your project won't affect it.</div>`);
  } else toast('Snapshot failed: ' + (j.error||''), 'err');
}

async function deleteBranchPreview(name) {
  if (!(await gmDanger('Delete Snapshot', `Delete snapshot "${name}"?`))) return;
  await fetch(`/api/composer/preview/branches/${encodeURIComponent(name)}`, {method:'DELETE'});
  toast('Snapshot deleted', 'ok', 1500);
  loadBranchPreviews();
}

// ── Updated Deploy panel — add new providers ──────────────────────
const _origRenderDeploy = renderDeploy;
renderDeploy = async function() {
  const pane = document.getElementById('pane-deploy');
  if (!pane) return;
  let statusData = {};
  try { const r = await fetch('/api/deploy/status'); statusData = await r.json(); } catch(e) {}

  const p = statusData.providers || {};
  const provCard = (id, name, icon, ready, token_key, docs_url, hint) => {
    const btnLabel = ready ? `🚀 Deploy to ${name}` : `⚙️ Setup ${name}`;
    return `<div style="background:var(--bg-2);border:1px solid ${ready?'var(--accent)':'var(--border)'};border-radius:var(--radius-lg);padding:18px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <span style="font-size:22px">${icon}</span>
        <div><div style="font-weight:700;font-size:14px">${name}</div>
        <div style="font-size:11.5px;color:var(--text-2)">${hint}</div></div>
        <span class="tag ${ready?'green':''}" style="margin-left:auto">${ready?'Ready':'Setup'}</span>
      </div>
      ${!ready ? `<div style="font-size:12px;color:var(--text-2);margin-bottom:8px">
        Set <code>${token_key}</code> in .env or 🔐 Vault
        <a href="${docs_url}" target="_blank" style="color:var(--accent);display:block">Get token ↗</a>
      </div>` : ''}
      <button onclick="doDeploy(${JSON.stringify(id)})" class="btn ${ready?'btn-primary':'btn-ghost'} btn-sm" style="width:100%" id="deploy-btn-${id}">${btnLabel}</button>
      <div id="deploy-result-${id}" style="margin-top:8px;display:none"></div>
    </div>`;
  };

  pane.innerHTML = `<div class="section-head">
    <div><h2>🚀 Deploy</h2><p>One-click deploy to 6 platforms + GitHub Pages</p></div>
    <button onclick="renderDeploy()" class="btn btn-ghost btn-sm">⟳ Refresh</button>
  </div>
  <div style="margin-bottom:14px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px 14px;font-size:13px;color:var(--text-2)">
    📁 <strong>${statusData.preview_files||0} files</strong> ready in <code>preview/</code>
    ${statusData.preview_files?'':' — <a href="#" onclick="nav(\'studio\');return false" style="color:var(--accent)">Build something first</a>'}
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px;margin-bottom:20px">
    ${provCard('vercel',       'Vercel',         '▲', p.vercel?.ready,       'VERCEL_TOKEN',    'https://vercel.com/account/tokens',                    'Best for Next.js, React, static')}
    ${provCard('netlify',      'Netlify',        '◈', p.netlify?.ready,      'NETLIFY_TOKEN',   'https://app.netlify.com/user/applications',             'Auto HTTPS, CDN, forms')}
    ${provCard('railway',      'Railway',        '🚂', p.railway?.ready,     'RAILWAY_TOKEN',   'https://railway.app/account/tokens',                    'Full-stack with database')}
    ${provCard('render',       'Render',         '🎨', p.render?.ready,      'RENDER_API_KEY',  'https://dashboard.render.com/u/account/api-keys',       'Free tier, auto-deploy')}
    ${provCard('flyio',        'Fly.io',         '🪰', p.flyio?.ready,       'flyctl CLI',      'https://fly.io/docs/hands-on/install-flyctl/',          'Global edge, Docker')}
    ${provCard('github-pages', 'GitHub Pages',   '🌐', p.github_pages?.ready,'GITHUB_TOKEN',    'https://github.com/settings/tokens',                    'Free hosting for static sites')}
  </div>
  <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:18px;margin-bottom:14px">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
      <span style="font-size:22px">☁️</span>
      <div><div style="font-weight:700">Cloudflare Tunnel</div>
      <div style="font-size:12px;color:var(--text-2)">Free public HTTPS URL — share localhost with anyone</div></div>
      <span class="tag ${p.cloudflare?.ready?'green':''}" style="margin-left:auto">${p.cloudflare?.ready?'cloudflared installed':'Not installed'}</span>
    </div>
    <button onclick="startTunnel()" class="btn btn-ghost" style="width:100%">🌐 Start Public Tunnel</button>
    <div id="tunnel-result" style="margin-top:8px;display:none"></div>
  </div>
  <div class="settings-card">
    <div style="font-weight:700;margin-bottom:10px">📋 Deploy History</div>
    <div id="deploy-history">Loading…</div>
  </div>`;
  loadDeployHistory();
};

// Add GitHub/DB/Composer to command palette
if (typeof PALETTE_CMDS !== 'undefined') {
  PALETTE_CMDS.push(
    {icon:'🐙', label:'GitHub',           desc:'Push, pull, PRs, Pages',           action:()=>nav('github')},
    {icon:'🗄️', label:'Database Studio', desc:'SQLite browser + Supabase connect', action:()=>nav('dbstudio')},
    {icon:'🪄', label:'Composer',         desc:'Multi-file AI agent + Screenshot→Code', action:()=>nav('composer')},
    {icon:'🌿', label:'Branch Preview',   desc:'Snapshot current state for sharing', action:()=>{nav('composer');setTimeout(createBranchPreview,400)}},
    {icon:'🌐', label:'GitHub Pages',     desc:'Deploy to GitHub Pages',            action:()=>{nav('github');setTimeout(showGHPages,400)}},
  );
}

// ═══════════════════════════════════════════════════════════════
//  SPRINT 6 — Unified Studio: Chat + Editor + Live Preview
// ═══════════════════════════════════════════════════════════════

// ── Extend nav for Studio ──────────────────────────────────────────
const _s6NavBase = function(){}; // nav chain disabled — master nav handles all
function _disabled__s6NavBase(pane) {
  _s6NavBase(pane);
  if (pane === 'studio') initStudio();
}

// ── Studio State ───────────────────────────────────────────────────
const Studio = {
  editor:         null,     // Monaco editor instance
  diffEditor:     null,     // Monaco diff editor
  currentFile:    'index.html',
  currentDevice:  'desktop',
  zoom:           100, autoSaveTimer: null, diffPending: null,     // {original, modified, path}
  lastError:      null,
  sidebarOpen:    true,
  hmrConnected:   false,
  chatHistory:    [],
  previewSrc:     '/preview/index.html',
};

// ── Init ───────────────────────────────────────────────────────────

function initStudio() {
  studioLoadFileTree();
  if (!studioMonacoLoaded) studioLoadMonaco();
  initStudioResizer();
  initStudioHMR();
  initStudioErrorBridge();
  document.querySelectorAll('[data-nav]').forEach(el =>
    el.classList.toggle('active', el.dataset.nav === 'studio'));
}
window.initStudio = initStudio;

// ── Monaco in Studio ───────────────────────────────────────────────
function studioLoadMonaco() {
  if (window.monaco && studioMonacoLoaded) { studioSetupMonaco(); return; }
  if (window.monaco) { studioSetupMonaco(); return; }
  const host = document.getElementById('studio-monaco-host');
  const s = document.createElement('script');
  s.src = 'https://cdn.jsdelivr.net/npm/monaco-editor@0.47.0/min/vs/loader.js';
  s.onload = () => {
    require.config({ paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.47.0/min/vs' }});
    require(['vs/editor/editor.main'], studioSetupMonaco);
  };
  s.onerror = () => {
    if (host && !Studio.editor) {
      host.innerHTML = `<textarea id="studio-fallback-textarea" spellcheck="false" style="width:100%;height:100%;background:var(--bg-0);color:var(--text-0);font-family:monospace;font-size:13.5px;padding:14px;border:none;outline:none;resize:none;line-height:1.6"></textarea>`;
      const ta = document.getElementById('studio-fallback-textarea');
      Studio.editor = {
        getValue: () => ta ? ta.value : '',
        setValue: (v) => { if (ta) ta.value = v; },
        setModel: () => {},
        onDidChangeModelContent: (cb) => { if (ta) ta.addEventListener('input', cb); }
      };
      if (ta) {
        ta.addEventListener('input', () => {
          studioMarkAutosave('saving');
          clearTimeout(Studio.autoSaveTimer);
          Studio.autoSaveTimer = setTimeout(studioAutoSave, 600);
        });
      }
      studioOpenFile(Studio.currentFile);
      toast('⚡ Offline/Sandboxed fallback editor initialized', 'ok', 3000);
    }
  };
  document.head.appendChild(s);
}

function studioSetupMonaco() {
  studioMonacoLoaded = true;
  const host = document.getElementById('studio-monaco-host');
  if (!host || Studio.editor) return;

  // Reuse agentic theme definition if already done
  if (!window._agenticThemeDefined) {
    window._agenticThemeDefined = true;
    monaco.editor.defineTheme('agentic', {
      base: 'vs-dark', inherit: true,
      rules: [
        { token: '', foreground: 'c9d1d9', background: '08090e' },
        { token: 'comment', foreground: '6b7ca5', fontStyle: 'italic' },
        { token: 'keyword', foreground: '7aa4ff' },
        { token: 'string',  foreground: '9ece6a' },
        { token: 'number',  foreground: 'f08850' },
      ],
      colors: {
        'editor.background':              '#08090e',
        'editor.foreground':              '#c9d1d9',
        'editorLineNumber.foreground':    '#3d4868',
        'editorCursor.foreground':        '#5b8af8',
        'editor.selectionBackground':     '#1a2e5088',
        'editorIndentGuide.background1':  '#1a1f35',
        'editorLineNumber.activeForeground': '#7a8aaa',
      }
    });
  }

  Studio.editor = monaco.editor.create(host, {
    theme:                'agentic',
    fontSize:             14,
    fontFamily:           "'JetBrains Mono','Fira Code',ui-monospace,monospace",
    fontLigatures:        true,
    lineHeight:           22,
    minimap:              { enabled: false },
    scrollBeyondLastLine: false,
    wordWrap:             'on',
    padding:              { top: 12 },
    automaticLayout:      true,
    smoothScrolling:      true,
    cursorBlinking:       'smooth',
    renderLineHighlight:  'line',
    suggest:              { preview: true },
  });

  if (Studio.editor && typeof Studio.editor.onDidChangeCursorPosition === 'function') {
    Studio.editor.onDidChangeCursorPosition(e => {
      const p = e.position;
      const el = document.getElementById('studio-ed-cursor');
      if (el) el.textContent = `Ln ${p.lineNumber}, Col ${p.column}`;
    });
  }

  if (Studio.editor && typeof Studio.editor.onDidChangeModelContent === 'function') {
    Studio.editor.onDidChangeModelContent(() => {
      studioMarkAutosave('saving');
      clearTimeout(Studio.autoSaveTimer);
      Studio.autoSaveTimer = setTimeout(studioAutoSave, 600);
    });
  }

  if (Studio.editor && typeof Studio.editor.addCommand === 'function' && window.monaco?.KeyMod && window.monaco?.KeyCode) {
    Studio.editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, studioSaveFile);
  }

  // Open default file
  studioOpenFile(Studio.currentFile);
}

// ── File tree ──────────────────────────────────────────────────────
async function studioLoadFileTree() {
  try {
    const r = await fetch('/api/preview/files');
    const files = await r.json();
    const el = document.getElementById('studio-file-tree');
    if (!el) return;
    if (!files.length) {
      el.innerHTML = `<div style="color:var(--text-3);font-size:11.5px;padding:12px;text-align:center">
        No files yet — scaffold a project ↓</div>`;
      return;
    }
    el.innerHTML = files.map(f => {
      const name = f.path.split('/').pop();
      const ext  = name.split('.').pop() || 'txt';
      const extColors = {html:'#f08850',css:'#38c5d8',js:'#f0c060',jsx:'#5b8af8',
                         ts:'#5b8af8',tsx:'#5b8af8',json:'#9ece6a',md:'#bb9af7',py:'#f7768e'};
      const c = extColors[ext] || '#7a8aaa';
      return `<div class="file-row ${f.path===Studio.currentFile?'active':''}"
               onclick="studioOpenFile('${escHtml(f.path)}')" title="${escHtml(f.path)}">
        <span style="font-size:9px;font-weight:700;padding:1px 4px;border-radius:3px;background:${c}22;color:${c};flex-shrink:0">${ext}</span>
        <span style="flex:1;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escHtml(name)}</span>
        <span style="font-size:10px;color:var(--text-3)">${formatBytes(f.size)}</span>
      </div>`;
    }).join('') + `<div class="new-file-btn" onclick="openNewFileModal()">＋ New file</div>`;
  } catch(e) { console.warn('studioLoadFileTree error:', e); }
}

async function studioOpenFile(path) {
  Studio.currentFile = path;
  const nameEl = document.getElementById('studio-ed-file');
  if (nameEl) nameEl.textContent = path;
  if (!Studio.editor) return;
  try {
    const r = await fetch('/api/preview/read?path=' + encodeURIComponent(path));
    if (!r.ok) return;
    const text = await r.text();
    const ext = path.split('.').pop();
    const langMap = {html:'html',css:'css',js:'javascript',jsx:'javascript',ts:'typescript',tsx:'typescript',json:'json',md:'markdown',py:'python'};
    const lang = langMap[ext] || 'plaintext';
    if (window.monaco?.editor?.createModel) {
      const model = monaco.editor.createModel(text, lang);
      Studio.editor.setModel(model);
    } else if (typeof Studio.editor.setValue === 'function') {
      Studio.editor.setValue(text);
    }
    const langEl = document.getElementById('studio-ed-lang');
    if (langEl) langEl.textContent = lang;
    updateStudioScrubber(path);
    document.querySelectorAll('#studio-file-tree .file-row').forEach(el =>
      el.classList.toggle('active', el.getAttribute('onclick')?.includes(`'${path}'`)));
  } catch(e) { console.warn('studioOpenFile error:', e); }
}

// ── Save & Auto-save ───────────────────────────────────────────────
function studioMarkAutosave(state) {
  const dot = document.getElementById('autosave-dot');
  if (!dot) return;
  dot.className = 'autosave-dot ' + state;
  if (state === 'saved') setTimeout(() => { dot.className = 'autosave-dot'; }, 2000);
}

async function studioAutoSave() {
  // FIX 6: try/catch so autosave never silently dies on network failure
  if (!Studio.editor) return;
  try {
    const content = Studio.editor.getValue();
    const r = await fetch('/api/preview/save', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ path: Studio.currentFile, content, author: 'autosave', message: 'autosave' })
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const j = await r.json();
    if (j.ok) {
      studioMarkAutosave('saved');
      const el = document.getElementById('studio-ed-versions');
      if (el) el.textContent = `${j.versions} versions`;
    }
  } catch(e) {
    studioMarkAutosave('error');
    console.warn('studioAutoSave failed:', e.message);
    // Retry next edit cycle — do NOT suppress future saves
  }
}

async function studioSaveFile() {
  if (!Studio.editor) return;
  const content = Studio.editor.getValue();
  const r = await fetch('/api/preview/save', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ path: Studio.currentFile, content, author: 'user', message: 'save' })
  });
  const j = await r.json();
  if (j.ok) {
    toast(`💾 Saved — ${j.versions} versions`, 'ok', 1500);
    studioMarkAutosave('saved');
    studioReloadPreview(); // explicit refresh on manual save
  } else {
    toast('Save failed', 'err');
  }
}

async function studioCommit() {
  const r = await fetch('/api/preview/commit', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ path: Studio.currentFile, author:'user', message:'checkpoint' })
  });
  const j = await r.json();
  if (j.ok) {
    toast(`📸 Committed v${j.version_id}`, 'ok', 1500);
    updateStudioScrubber(Studio.currentFile);
  }
}

let studioHistoryCache = [];
let studioLiveContentCache = '';

async function updateStudioScrubber(filePath) {
  if (!filePath) return;
  try {
    const r = await fetch('/api/preview/history?path=' + encodeURIComponent(filePath));
    const hist = r.ok ? await r.json() : [];
    studioHistoryCache = hist || [];
    const el = document.getElementById('studio-ed-versions');
    if (el) el.textContent = `${studioHistoryCache.length} versions`;

    const slider = document.getElementById('studio-scrubber-slider');
    const label = document.getElementById('studio-scrubber-label');
    const resetBtn = document.getElementById('studio-scrubber-reset-btn');
    if (slider) {
      slider.max = studioHistoryCache.length;
      slider.value = 0;
    }
    if (label) label.textContent = 'Live Version';
    if (resetBtn) resetBtn.style.display = 'none';
  } catch(e) {}
}

async function scrubStudioCommit(valIdx) {
  const idx = parseInt(valIdx, 10);
  const label = document.getElementById('studio-scrubber-label');
  const resetBtn = document.getElementById('studio-scrubber-reset-btn');

  if (idx === 0) {
    resetStudioScrubber();
    return;
  }

  const ver = studioHistoryCache[idx - 1];
  if (!ver) return;

  if (label) label.textContent = `⏪ Rev ${ver.id} (${(ver.ts||'').slice(11,16)})`;
  if (resetBtn) resetBtn.style.display = 'inline-block';

  try {
    const r = await fetch('/api/preview/version?id=' + ver.id);
    const data = await r.json();
    if (data.ok || data.content !== undefined) {
      if (typeof Studio !== 'undefined' && Studio.editor) {
        if (idx === 1) studioLiveContentCache = Studio.editor.getValue();
        Studio.editor.setValue(data.content || '');
      }
    }
  } catch(e) {}
}

window.resetStudioScrubber = function() {
  const slider = document.getElementById('studio-scrubber-slider');
  const label = document.getElementById('studio-scrubber-label');
  const resetBtn = document.getElementById('studio-scrubber-reset-btn');
  if (slider) slider.value = 0;
  if (label) label.textContent = 'Live Version';
  if (resetBtn) resetBtn.style.display = 'none';

  if (typeof Studio !== 'undefined' && Studio.editor && studioLiveContentCache) {
    Studio.editor.setValue(studioLiveContentCache);
  } else if (typeof Studio !== 'undefined' && Studio.currentFile) {
    if (typeof studioLoadFile === 'function') studioLoadFile(Studio.currentFile);
  }
};

// ── Preview ────────────────────────────────────────────────────────
function studioPreviewUrl() {
  return Studio.previewSrc || '/preview/index.html';
}

function studioReloadPreview() {
  const frame = document.getElementById('studio-preview-iframe');
  if (!frame) return;
  const src = studioPreviewUrl();
  frame.src = src + '?t=' + Date.now();
  const urlBar = document.getElementById('studio-url-bar');
  if (urlBar) urlBar.textContent = `localhost:8787${src}`;
}

// ── Device picker ──────────────────────────────────────────────────
const DEVICE_CONFIG = {
  // FIX 5: replaced bare undefined `height` with null for desktop/full
  desktop: { width: null,    height: null, frame: false, label: 'Desktop' },
  tablet:  { width: 768,     height: 1024, frame: true,  label: 'Tablet' },
  mobile:  { width: 390,     height: 844,  frame: true,  label: 'iPhone 15 Pro' },
  full:    { width: '100%',  height: null, frame: false, label: 'Full Width' },
};

function studioSetDevice(device) {
  Studio.currentDevice = device;
  const cfg  = DEVICE_CONFIG[device];
  const wrap  = document.getElementById('studio-frame-wrap');
  const frame = document.getElementById('studio-preview-iframe');
  if (!wrap || !frame) return;

  // Update active button
  ['desktop','tablet','mobile','full'].forEach(d => {
    const btn = document.getElementById('dev-' + d);
    if (btn) btn.classList.toggle('active', d === device);
  });

  if (cfg.frame) {
    // Wrap in device frame
    wrap.classList.remove('fullscreen');
    wrap.style.background = 'repeating-linear-gradient(45deg,#0a0b10 0,#0a0b10 10px,#08090e 10px,#08090e 20px)';
    frame.className = 'preview-iframe';
    frame.style.width  = cfg.width  + 'px';
    frame.style.height = cfg.height + 'px';
    frame.style.borderRadius = device === 'mobile' ? '40px' : '16px';
    frame.style.boxShadow = device === 'mobile'
      ? '0 0 0 10px #1a1a2e, 0 0 0 12px #252538, 0 30px 80px rgba(0,0,0,.7)'
      : '0 0 0 8px #1a1a2e, 0 20px 60px rgba(0,0,0,.6)';
    if (device === 'mobile') {
      // Add notch overlay
      wrap.style.paddingTop = '40px';
    } else {
      wrap.style.paddingTop = '20px';
    }
  } else {
    // Full / desktop
    wrap.classList.add('fullscreen');
    wrap.style.background = '';
    wrap.style.paddingTop = '';
    frame.className = 'preview-iframe-fullscreen';
    frame.style.width       = '';
    frame.style.height      = '';
    frame.style.borderRadius = '';
    frame.style.boxShadow   = '';
  }

  toast(`📱 ${cfg.label}`, 'ok', 1000);
}

function studioSetBreakpoint(width) {
  const frame = document.getElementById('studio-preview-iframe');
  const wrap  = document.getElementById('studio-frame-wrap');
  if (!frame || !wrap) return;
  wrap.classList.remove('fullscreen');
  wrap.style.background = 'repeating-linear-gradient(45deg,#0a0b10 0,#0a0b10 10px,#08090e 10px,#08090e 20px)';
  frame.className = 'preview-iframe';
  frame.style.width  = width + 'px';
  frame.style.height = '800px';
  frame.style.borderRadius = '8px';
  frame.style.boxShadow = '0 8px 40px rgba(0,0,0,.6)';
  // Deselect all device buttons
  ['desktop','tablet','mobile','full'].forEach(d => {
    const btn = document.getElementById('dev-' + d);
    if (btn) btn.classList.remove('active');
  });
  // Highlight matching breakpoint btn
  document.querySelectorAll('.bp-btn').forEach(btn => {
    btn.classList.toggle('active', btn.textContent === String(width));
  });
  toast(`📏 ${width}px breakpoint`, 'ok', 1000);
}

// ── Zoom ───────────────────────────────────────────────────────────
function studioZoom(delta) {
  Studio.zoom = Math.max(25, Math.min(200, Studio.zoom + delta));
  const frame = document.getElementById('studio-preview-iframe');
  if (frame) {
    frame.style.transform = `scale(${Studio.zoom/100})`;
    frame.style.transformOrigin = 'top left';
    if (Studio.zoom !== 100) {
      frame.style.width  = (100 / Studio.zoom * 100) + '%';
      frame.style.height = (100 / Studio.zoom * 100) + '%';
    } else {
      frame.style.width  = '';
      frame.style.height = '';
    }
  }
  const lbl = document.getElementById('studio-zoom-label');
  if (lbl) lbl.textContent = Studio.zoom + '%';
}

// ── Screenshot ─────────────────────────────────────────────────────
function studioScreenshot() {
  const url = studioPreviewUrl();
  const a = document.createElement('a');
  a.href = url;
  a.target = '_blank';
  a.click();
  toast('📷 Opening preview for screenshot…', 'ok', 2000);
}

async function studioQR() {
  const r = await fetch('/api/tunnel/info');
  const j = await r.json();
  const qrUrl = j.qr_web || '';
  if (qrUrl) {
    await gmAlert('📲 QR Code — Scan on your phone',
      `<div style="text-align:center">
        <img src="${qrUrl}" style="width:180px;height:180px;border-radius:10px;margin-bottom:10px">
        <div style="font-size:12px;color:var(--text-2)">Make sure your phone is on the same Wi-Fi</div>
        <div style="font-size:11px;color:var(--accent);margin-top:4px">${j.urls?.web_preview||''}</div>
      </div>`);
  } else {
    toast('Could not get QR code', 'err');
  }
}

// ── HMR in Studio ──────────────────────────────────────────────────
let studioHmrSource = null;

function initStudioHMR() {
  if (studioHmrSource || typeof window.EventSource === 'undefined') return;
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  // Use SSE (same as main HMR)
  studioHmrSource = new EventSource('/api/system/hmr');
  studioHmrSource.onmessage = e => {
    try {
      const ev = JSON.parse(e.data);
      if (ev.type === 'file_changed') {
        Studio.hmrConnected = true;
        const badge = document.getElementById('hmr-badge');
        if (badge) { badge.textContent = '⚡ LIVE'; badge.className = 'hmr-badge'; }
        // Auto-reload preview iframe — but only if NOT currently showing diff
        if (document.getElementById('studio-diff-overlay')?.style.display === 'none' ||
            !document.getElementById('studio-diff-overlay')) {
          const frame = document.getElementById('studio-preview-iframe');
          if (frame) frame.src = studioPreviewUrl() + '?t=' + Date.now();
        }
        // Flash
        const urlBar = document.getElementById('studio-url-bar');
        if (urlBar) {
          urlBar.style.color = 'var(--green)';
          setTimeout(() => { urlBar.style.color = ''; }, 800);
        }
      }
    } catch(err) {}
  };
  studioHmrSource.onerror = () => {
    const badge = document.getElementById('hmr-badge');
    if (badge) { badge.textContent = '○ offline'; badge.className = 'hmr-badge off'; }
    setTimeout(initStudioHMR, 5000);
  };
}

// ── Error bridge (iframe → parent) ────────────────────────────────
function initStudioErrorBridge() {
  window.addEventListener('message', e => {
    if (e.data?.type === 'preview_error') {
      Studio.lastError = e.data.error;
      const bar  = document.getElementById('studio-error-bar');
      const text = document.getElementById('studio-error-text');
      if (bar && text) {
        text.textContent = `⚠️ ${(e.data.error || 'JS Error').slice(0, 80)}`;
        bar.style.display = 'flex';
        setTimeout(() => { if(bar) bar.style.display = 'none'; }, 8000);
      }
    }
  });
}

// Inject error bridge script into preview iframe after it loads
document.addEventListener('DOMContentLoaded', () => {});
(function patchStudioIframe() {
  const frame = document.getElementById('studio-preview-iframe');
  if (!frame) { setTimeout(patchStudioIframe, 500); return; }
  frame.addEventListener('load', () => {
    try {
      const doc = frame.contentDocument || frame.contentWindow?.document;
      if (!doc) return;
      const s = doc.createElement('script');
      s.textContent = `
        window.addEventListener('error', function(e) {
          try { parent.postMessage({type:'preview_error',error:e.message+' ('+e.filename?.split('/').pop()+':'+e.lineno+')'},'*'); } catch(ex){}
        });
        window.addEventListener('unhandledrejection', function(e) {
          try { parent.postMessage({type:'preview_error',error:'Unhandled promise rejection: '+(e.reason?.message||e.reason)},'*'); } catch(ex){}
        });
      `;
      doc.head?.appendChild(s);
    } catch(ex) {} // cross-origin, ignore
  });
})();

// ── AI Edit with Diff-first ────────────────────────────────────────
async function studioAIEdit() {
  const input = document.getElementById('studio-ai-input');
  const instruction = (input?.value || '').trim();
  if (!instruction) { input?.focus(); return; }
  input.value = '';

  // Add to studio chat
  addStudioMsg(instruction, 'user');
  const thinkingId = 'think_' + Date.now();
  addStudioMsg('⏳ Thinking…', 'agent', thinkingId);

  // Get current file content
  const currentContent = Studio.editor?.getValue() || '';
  const ext  = Studio.currentFile.split('.').pop();
  const lang = { html:'html',css:'css',js:'javascript',jsx:'javascript',
                 ts:'typescript',tsx:'typescript',py:'python' }[ext] || ext;

  try {
    // Call AI edit endpoint (streaming)
    const resp = await fetch('/api/agent/edit', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        instruction,
        code:     currentContent,
        language: lang,
        filepath: Studio.currentFile,
      })
    });

    // FIX 9: null guard on resp.body before calling getReader()
    if (!resp.body) {
      throw new Error('No response body — check network or server logs');
    }
    let fullText = '';
    const reader  = resp.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      const lines = decoder.decode(value, {stream:true}).split('\n');
      for (const line of lines) {
        if (!line.startsWith('data:')) continue;
        try {
          const data = JSON.parse(line.slice(5).trim());
          if (data.delta) fullText += data.delta;
        } catch(e) {}
      }
    }

    // Remove thinking message
    document.getElementById(thinkingId)?.remove();

    // Clean up code fences if AI returned them
    let proposed = fullText.trim();
    if (proposed.startsWith('```')) {
      proposed = proposed.split('\n').slice(1).join('\n');
      if (proposed.endsWith('```')) proposed = proposed.slice(0, -3).trimEnd();
    }

    if (!proposed || proposed.length < 20) {
      addStudioMsg('❌ AI returned empty response. Try rephrasing.', 'agent');
      return;
    }

    addStudioMsg(`✅ Proposed change ready — ${proposed.split('\n').length} lines. Review the diff and click Accept.`, 'agent');

    // Show diff overlay
    studioShowDiff(currentContent, proposed);

  } catch(e) {
    document.getElementById(thinkingId)?.remove();
    addStudioMsg(`❌ Error: ${e.message}`, 'agent');
    toast('AI edit failed: ' + e.message, 'err');
  }
}

function studioAIInput(text) {
  const input = document.getElementById('studio-ai-input');
  if (input) { input.value = text; input.focus(); }
}

async function studioAIFix() {
  const error = Studio.lastError || 'Fix any bugs in the code';
  const input = document.getElementById('studio-ai-input');
  if (input) input.value = `Fix this error: ${error}`;
  await studioAIEdit();
}

// ── Diff overlay ────────────────────────────────────────────────────
function studioShowDiff(original, modified) {
  Studio.diffPending = { original, modified, path: Studio.currentFile };

  const overlay = document.getElementById('studio-diff-overlay');
  const fileEl  = document.getElementById('diff-overlay-file');
  if (overlay) overlay.style.display = 'flex';
  if (fileEl)  fileEl.textContent = Studio.currentFile;

  // Create / update Monaco diff editor
  const host = document.getElementById('studio-diff-host');
  if (!host || !window.monaco) return;

  if (Studio.diffEditor) { Studio.diffEditor.dispose(); Studio.diffEditor = null; }
  Studio.diffEditor = monaco.editor.createDiffEditor(host, {
    theme:            'agentic',
    readOnly:         true,
    automaticLayout:  true,
    renderSideBySide: true,
    enableSplitViewResizing: true,
  });
  const ext  = Studio.currentFile.split('.').pop();
  const lang = {html:'html',css:'css',js:'javascript',jsx:'javascript',
                ts:'typescript',tsx:'typescript',py:'python'}[ext] || 'plaintext';
  Studio.diffEditor.setModel({
    original: monaco.editor.createModel(original, lang),
    modified: monaco.editor.createModel(modified, lang),
  });
}

async function studioAcceptDiff() {
  if (!Studio.diffPending) return;
  const { modified, path } = Studio.diffPending;

  // Apply to editor
  if (Studio.editor) {
    const model = Studio.editor.getModel();
    if (model) model.setValue(modified);
  }

  // Save immediately
  const r = await fetch('/api/preview/save', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ path, content: modified, author: 'ai-edit', message: 'AI accepted diff' })
  });
  const j = await r.json();

  // FIX 7: only close + toast on success; show error if save failed
  if (j.ok) {
    studioRejectDiff();
    toast('✅ Changes applied — preview updating…', 'ok', 2000);
    studioMarkAutosave('saved');
  } else {
    toast('⚠️ Save failed — diff kept open. Check console.', 'err', 4000);
    console.error('studioAcceptDiff save failed:', j);
  }
}

function studioRejectDiff() {
  const overlay = document.getElementById('studio-diff-overlay');
  if (overlay) overlay.style.display = 'none';
  if (Studio.diffEditor) { Studio.diffEditor.dispose(); Studio.diffEditor = null; }
  Studio.diffPending = null;
}

// ── Studio chat ────────────────────────────────────────────────────
function addStudioMsg(text, role, id = '') {
  const msgs = document.getElementById('studio-chat-msgs');
  if (!msgs) return;
  const div = document.createElement('div');
  div.className = `studio-msg ${role}`;
  if (id) div.id = id;
  div.textContent = text;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function clearStudioChat() {
  const msgs = document.getElementById('studio-chat-msgs');
  if (msgs) msgs.innerHTML = '<div class="studio-msg agent">👋 Describe a change and I\'ll update the code instantly.</div>';
}

// Studio AI input keydown
document.addEventListener('keydown', e => {
  const inp = document.getElementById('studio-ai-input');
  if (e.target === inp && e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    studioAIEdit();
  }
});

// ── Scaffold from Studio ────────────────────────────────────────────
async function studioScaffold() {
  // FIX 8: try/catch for network failures
  const fw     = document.getElementById('studio-scaffold-fw')?.value || 'web';
  const prompt = document.getElementById('studio-scaffold-prompt')?.value?.trim() || fw;
  toast(`⚡ Scaffolding ${fw}…`, 'ok', 2000);
  try {
    const r = await fetch('/api/preview/scaffold', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ framework: fw, prompt })
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const j = await r.json();
    if (j.ok) {
      toast(`✅ ${j.message}`, 'ok', 4000);
      studioLoadFileTree();
      if (j.files?.length) studioOpenFile(j.files[0]);
      studioReloadPreview();
      addStudioMsg(`✅ Scaffolded ${fw} project — ${j.files?.length || 0} files created`, 'agent');
    } else {
      toast('Scaffold failed: ' + (j.error || 'unknown'), 'err');
      addStudioMsg(`❌ Scaffold failed: ${j.error || 'unknown'}`, 'agent');
    }
  } catch(e) {
    toast('Scaffold error: ' + e.message, 'err');
    addStudioMsg(`❌ Scaffold error: ${e.message}`, 'agent');
  }
}

// ── Resizer (drag to resize editor/preview split) ─────────────────
function initStudioResizer() {
  const resizer = document.getElementById('studio-resizer');
  const edPane  = document.getElementById('studio-editor-panel');
  const pvPane  = document.getElementById('studio-preview-panel');
  if (!resizer || !edPane || !pvPane) return;

  let dragging = false, startX = 0, startW = 0;

  resizer.addEventListener('mousedown', e => {
    dragging = true;
    startX   = e.clientX;
    startW   = edPane.getBoundingClientRect().width;
    resizer.classList.add('dragging');
    document.body.style.cursor    = 'col-resize';
    document.body.style.userSelect = 'none';
  });

  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const delta   = e.clientX - startX;
    const newW    = Math.max(200, Math.min(startW + delta, window.innerWidth - 400));
    edPane.style.width = newW + 'px';
    edPane.style.flex  = 'none';
    // Let Monaco re-layout
    Studio.editor?.layout();
  });

  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    resizer.classList.remove('dragging');
    document.body.style.cursor    = '';
    document.body.style.userSelect = '';
    Studio.editor?.layout();
  });
}

// ── Sidebar toggle ─────────────────────────────────────────────────
function toggleStudioSidebar() {
  Studio.sidebarOpen = !Studio.sidebarOpen;
  const sb = document.getElementById('studio-sidebar');
  if (sb) sb.classList.toggle('collapsed', !Studio.sidebarOpen);
  setTimeout(() => Studio.editor?.layout(), 200);
}

// ── Update existing builder nav when navigating ────────────────────
// When Studio is opened, also expose its openFile globally so
// other parts of the app (HMR etc.) can redirect to Studio
window.studioOpenFileGlobal = studioOpenFile;

// ── Sync studio preview src based on scaffold type ─────────────────
const _origRunScaffold = typeof runScaffold !== 'undefined' ? runScaffold : null;

// When scaffold completes in old builder, also update Studio if open
async function studioSyncAfterScaffold(result) {
  if (!result?.ok) return;
  if (result.framework === 'expo') {
    Studio.previewSrc = '/preview/mobile/index.html';
  } else {
    Studio.previewSrc = '/preview/index.html';
  }
  studioReloadPreview();
  studioLoadFileTree();
}

// ── Keyboard shortcut: ⌘⇧P → open Studio ─────────────────────────
document.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 'P') {
    e.preventDefault();
    nav('studio');
  }
  // ⌘⇧E → open old editor
  if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 'E') {
    e.preventDefault();
    nav('builder');
  }
});

// Add Studio to palette
if (typeof PALETTE_CMDS !== 'undefined') {
  PALETTE_CMDS.unshift(
    {icon:'🎬', label:'Open Studio',       desc:'Chat + Editor + Live Preview (⌘⇧P)', action:()=>nav('studio')},
    {icon:'🖥️', label:'Preview: Desktop', desc:'Full desktop device', action:()=>{nav('studio');setTimeout(()=>studioSetDevice('desktop'),300)}},
    {icon:'📱', label:'Preview: Phone',   desc:'iPhone 15 Pro frame', action:()=>{nav('studio');setTimeout(()=>studioSetDevice('mobile'),300)}},
    {icon:'📋', label:'Preview: Tablet',  desc:'iPad breakpoint',     action:()=>{nav('studio');setTimeout(()=>studioSetDevice('tablet'),300)}},
  );
}

// Add Studio shortcut to shortcuts list
// (will appear when fetched from /api/onboarding/shortcuts next call)

// ── Cost tracking polling ─────────────────────────────────────────
setInterval(updateCostBar, 30000);

// ═══════════════════════════════════════════════════════════════
//  SPRINT 5 — Plugins, Onboarding, Collab, Preferences, Shortcuts
// ═══════════════════════════════════════════════════════════════

// ── Extend nav for Sprint 5 ────────────────────────────────────────
const _s4Nav = nav;
nav = function(pane) {
  _s4Nav(pane);
  if (pane === 'plugins') renderPlugins();
};

// ── Plugin Marketplace ────────────────────────────────────────────
let pluginRegistry = [], pluginInstalled = new Set();

async function renderPlugins() {
  const pane = document.getElementById('pane-plugins');
  if (!pane) return;
  pane.innerHTML = `<div class="section-head">
    <div><h2>🧩 Plugin Marketplace</h2><p>Install skill packs, agent personas, and tool collections. One click to unlock new capabilities.</p></div>
    <div style="display:flex;gap:8px">
      <button onclick="showInstallFromUrl()" class="btn btn-ghost btn-sm">🔗 Install from URL</button>
      <button onclick="exportWorkspaceData()" class="btn btn-ghost btn-sm">📤 Export Workspace</button>
      <button onclick="showImportWorkspace()" class="btn btn-ghost btn-sm">📥 Import</button>
    </div>
  </div>
  <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap" id="plugin-cats"></div>
  <div id="plugin-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px">
    <div style="color:var(--text-2)">Loading marketplace…</div>
  </div>`;
  await loadPluginRegistry();
}

async function loadPluginRegistry() {
  try {
    const [regR, instR] = await Promise.all([
      fetch('/api/plugins/registry'), fetch('/api/plugins/installed')
    ]);
    if (!regR.ok) throw new Error('Registry API error ' + regR.status);
    if (!instR.ok) throw new Error('Installed API error ' + instR.status);
    const regData = await regR.json();
    const instData = await instR.json();
    pluginRegistry = Array.isArray(regData) ? regData : (Array.isArray(regData?.plugins) ? regData.plugins : []);
    const installed = Array.isArray(instData) ? instData : (Array.isArray(instData?.installed) ? instData.installed : []);
    pluginInstalled = new Set(installed.map(p => p.id));
    renderPluginGrid();
    renderPluginCats();
  } catch(e) { console.warn('Failed to load plugins:', e); toast('Failed to load plugins: ' + e.message, 'err'); }
}

function renderPluginCats() {
  const el = document.getElementById('plugin-cats');
  if (!el) return;
  const cats = [...new Set(pluginRegistry.map(p => p.category))];
  el.innerHTML = cats.map(c =>
    `<span class="tag" style="cursor:pointer;padding:5px 12px" onclick="filterPlugins(${JSON.stringify(c)})">${escHtml(c)}</span>`
  ).join('');
}

function filterPlugins(cat) {
  const filtered = cat ? pluginRegistry.filter(p => p.category === cat) : pluginRegistry;
  renderPluginGrid(filtered);
}

function renderPluginGrid(list = pluginRegistry) {
  const grid = document.getElementById('plugin-grid');
  if (!grid) return;
  grid.innerHTML = list.map(p => {
    const installed = pluginInstalled.has(p.id);
    return `<div style="background:var(--bg-2);border:1px solid ${installed?'var(--accent)':'var(--border)'};border-radius:var(--radius-lg);padding:18px;transition:var(--transition)"
         onmouseover="this.style.borderColor='var(--border-hi)'" onmouseout="this.style.borderColor='${installed?'var(--accent)':'var(--border)'}'">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <span style="font-size:28px">${p.emoji||'🧩'}</span>
        <div style="flex:1;min-width:0">
          <div style="font-weight:800;font-size:15px">${escHtml(p.name)}</div>
          <div style="font-size:11px;color:var(--text-2)">by ${escHtml(p.author||'Community')} · v${p.version||'1.0'}</div>
        </div>
        ${installed ? `<span class="tag green">Installed</span>` : ''}
      </div>
      <p style="font-size:12.5px;color:var(--text-2);line-height:1.5;margin-bottom:12px;min-height:36px">${escHtml(p.description||'')}</p>
      <div style="display:flex;align-items:center;justify-content:space-between">
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          <span class="tag">${p.category}</span>
          <span class="tag">${p.skill_count||p.skills?.length||0} skills</span>
        </div>
        ${installed
          ? `<button onclick="uninstallPlugin(${JSON.stringify(p.id)},${JSON.stringify(p.name)})" class="btn btn-ghost btn-sm" style="color:var(--red)">Uninstall</button>`
          : `<button onclick="installPlugin(${JSON.stringify(p.id)})" class="btn btn-primary btn-sm" id="install-btn-${p.id}">Install</button>`
        }
      </div>
    </div>`;
  }).join('') || '<div style="color:var(--text-3)">No plugins found.</div>';
}

async function installPlugin(pluginId) {
  const btn = document.getElementById(`install-btn-${pluginId}`);
  if (btn) { btn.disabled = true; btn.textContent = '⏳…'; }
  const r = await fetch(`/api/plugins/install/${encodeURIComponent(pluginId)}`, { method:'POST' });
  if (!r.ok) {
    toast('Install failed: server error ' + r.status, 'err');
    if (btn) { btn.disabled = false; btn.textContent = 'Install'; }
    return;
  }
  const j = await r.json();
  if (j.ok) {
    toast(`🧩 ${j.plugin} installed — ${j.skills_added} skills added to Skills Hub`, 'ok', 5000);
    loadPluginRegistry();
    // refresh skills in background
    fetch('/api/skills').then(r=>r.ok?r.json():[]).then(s => { allSkills = s||[]; }).catch(()=>{});
  } else {
    toast(j.error || 'Install failed', j.installed ? 'warn' : 'err');
    if (btn) { btn.disabled = false; btn.textContent = 'Install'; }
  }
}

async function uninstallPlugin(pluginId, name) {
  if (!(await gmDanger('Uninstall Plugin', `Remove "${name}" and all its skills?`))) return;
  try {
    const r = await fetch(`/api/plugins/uninstall/${encodeURIComponent(pluginId)}`, { method:'DELETE' });
    if (!r.ok) { toast('Uninstall failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast('🗑 Plugin uninstalled', 'ok'); loadPluginRegistry(); }
    else toast('Uninstall failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('Uninstall error: ' + ex.message, 'err'); }
}

async function showInstallFromUrl() {
  const url = await gmPrompt('Install from URL', 'GitHub raw URL or any JSON plugin URL', 'https://raw.githubusercontent.com/…/plugin.json');
  if (!url) return;
  toast('⏳ Fetching plugin…', 'ok', 2000);
  try {
    const r = await fetch('/api/plugins/install/url', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ url })
    });
    if (!r.ok) { toast('Install failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast(`🧩 Plugin installed — ${j.skills_added} skills added`, 'ok', 4000); loadPluginRegistry(); }
    else toast('Error: ' + (j.error||''), 'err');
  } catch(ex) { toast('Install error: ' + ex.message, 'err'); }
}
window.renderPlugins = renderPlugins;
window.loadPluginRegistry = loadPluginRegistry;
window.installPlugin = installPlugin;
window.uninstallPlugin = uninstallPlugin;
window.renderPluginGrid = renderPluginGrid;
window.filterPlugins = filterPlugins;
window.showInstallFromUrl = showInstallFromUrl;

async function exportWorkspaceData() {
  toast('⏳ Exporting…', 'ok', 1500);
  const r = await fetch('/api/plugins/export');
  if (!r.ok) { toast('Export failed: server error ' + r.status, 'err'); return; }
  const j = await r.json();
  if (j.ok === false) { toast('Export failed: ' + (j.error||''), 'err'); return; }
  // Download as JSON file
  const blob = new Blob([JSON.stringify(j, null, 2)], { type: 'application/json' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = `agentic-os-workspace-${new Date().toISOString().slice(0,10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
  toast(`📤 Exported ${j.agents?.length} agents, ${j.skills?.length} skills, ${j.memories?.length} memories`, 'ok', 4000);
}

async function showImportWorkspace() {
  const json_str = await gmPrompt('Import Workspace', 'Paste your exported workspace JSON here', '', true);
  if (!json_str) return;
  try {
    const data = JSON.parse(json_str);
    const r = await fetch('/api/plugins/import', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ workspace: data })
    });
    if (!r.ok) { toast('Import failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) {
      const i = j.imported;
      toast(`📥 Imported: ${i.agents} agents, ${i.skills} skills, ${i.memories} memories`, 'ok', 5000);
      loadAgents();
    } else toast('Import failed', 'err');
  } catch(e) { toast('Invalid JSON: ' + e.message, 'err'); }
}

// ── Onboarding Wizard ─────────────────────────────────────────────
let obStep = 0, obSteps = [], obPrefs = {};

async function checkOnboarding() {
  try {
    if (localStorage.getItem('agentic_os_onboarded') === 'true' || window._onboardingDismissed) return;
    const r = await fetch('/api/onboarding/status');
    if (!r.ok) return;
    const s = await r.json();
    if (!s.complete) {
      const sr = await fetch('/api/onboarding/steps');
      if (!sr.ok) return;
      obSteps  = await sr.json();
      obPrefs  = {};
      obStep   = 0;
      showOnboarding();
    } else {
      // Load preferences and apply theme
      const pr = await fetch('/api/onboarding/preferences');
      if (!pr.ok) return;
      const p  = await pr.json();
      applyPreferences(p);
    }
  } catch(e) {
    console.warn('[Onboarding] checkOnboarding error:', e);
  }
}

function showOnboarding() {
  if (!obSteps.length) return;
  const step = obSteps[Math.min(obStep, obSteps.length-1)];
  const total = obSteps.length;

  document.getElementById('ob-icon').textContent    = ['🧠','🔑','🏠','🤖','📋','🎨','🚀'][obStep] || '⚙️';
  document.getElementById('ob-title').textContent   = step.title;
  document.getElementById('ob-subtitle').textContent = step.subtitle || '';
  document.getElementById('ob-body').textContent    = step.body;
  document.getElementById('ob-counter').textContent = `Step ${obStep+1} of ${total}`;

  // Progress dots
  document.getElementById('ob-dots').innerHTML = obSteps.map((_,i) =>
    `<div style="width:8px;height:8px;border-radius:50%;background:${i===obStep?'var(--accent)':i<obStep?'var(--green)':'var(--bg-4)'}"></div>`
  ).join('');

  // Input area
  const inputWrap = document.getElementById('ob-input-area');
  const inp       = document.getElementById('ob-input');
  const themeArea = document.getElementById('ob-theme-area');
  const agentsArea = document.getElementById('ob-agents-area');
  inputWrap.style.display  = 'none';
  themeArea.style.display  = 'none';
  agentsArea.style.display = 'none';

  if (step.id === 'api_key') {
    inputWrap.style.display = 'block';
    inp.type        = 'password';
    inp.placeholder = 'sk-or-v1-…';
    inp.value       = '';
  } else if (step.id === 'workspace') {
    inputWrap.style.display = 'block';
    inp.type        = 'text';
    inp.placeholder = 'e.g. My AI Agency, Solo Founder OS…';
    inp.value       = obPrefs.workspace_name || '';
    setTimeout(() => inp.focus(), 100);
  } else if (step.id === 'agents') {
    agentsArea.style.display = 'block';
    agentsArea.innerHTML = S.agents.slice(0,6).map(a =>
      `<div style="display:flex;align-items:center;gap:10px;padding:8px;background:var(--bg-3);border-radius:var(--radius-sm);margin-bottom:6px">
        <span style="font-size:20px">${a.avatar||'🤖'}</span>
        <div><div style="font-weight:600;font-size:13px">${escHtml(a.name)}</div>
        <div style="font-size:11px;color:var(--text-2)">${escHtml(a.role||'')}</div></div>
        <span class="tag" style="margin-left:auto">${a.model||'default'}</span>
      </div>`).join('');
  } else if (step.id === 'theme') {
    themeArea.style.display = 'flex';
    const themes = [
      {id:'dark',    name:'Dark',     bg:'#08090e', accent:'#5b8af8'},
      {id:'midnight',name:'Midnight', bg:'#050810', accent:'#9d74f5'},
      {id:'forest',  name:'Forest',   bg:'#0a100d', accent:'#4cc98a'},
      {id:'ember',   name:'Ember',    bg:'#100a08', accent:'#f08850'},
      {id:'ocean',   name:'Ocean',    bg:'#080d10', accent:'#38c5d8'},
    ];
    themeArea.innerHTML = themes.map(t => `
      <div onclick="selectObTheme(${JSON.stringify(t.id)},${JSON.stringify(t.accent)})"
           id="ob-theme-${t.id}"
           style="cursor:pointer;border-radius:10px;padding:10px 14px;border:2px solid ${obPrefs.theme===t.id?t.accent:'var(--border)'};background:${t.bg};text-align:center;transition:var(--transition)">
        <div style="width:32px;height:32px;border-radius:50%;background:${t.accent};margin:0 auto 6px"></div>
        <div style="font-size:12px;color:#ccc;font-weight:600">${t.name}</div>
      </div>`).join('');
  }

  // Back button
  document.getElementById('ob-back').style.display = obStep > 0 ? 'inline-flex' : 'none';
  // Skip button
  document.getElementById('ob-skip').style.display = step.skip ? 'inline-flex' : 'none';
  // Next button label
  const nextBtn = document.getElementById('ob-next');
  nextBtn.textContent = obStep === obSteps.length - 1 ? '🚀 Start Building' : 'Next →';

  document.getElementById('onboarding-modal').style.display = 'flex';
}

function selectObTheme(id, accent) {
  obPrefs.theme = id; obPrefs.accent_color = accent;
  document.querySelectorAll('[id^="ob-theme-"]').forEach(el => {
    el.style.borderColor = el.id.endsWith(id) ? accent : 'var(--border)';
  });
  applyTheme(id, accent);
}

async function obNext(skip = false) {
  const step = obSteps[obStep];
  if (!skip) {
    // Collect value
    const inp = document.getElementById('ob-input');
    if (inp) {
      if (step.id === 'api_key' && inp.value.trim()) {
        obPrefs.api_key = inp.value.trim();
      } else if (step.id === 'workspace' && inp.value.trim()) {
        obPrefs.workspace_name = inp.value.trim();
      }
    }
  }
  obStep++;
  if (obStep >= obSteps.length || skip === true) {
    // Complete immediately so modal always dismisses
    closeOnboardingModal();
    try {
      fetch('/api/onboarding/complete', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(obPrefs)
      }).then(r => r.json()).then(j => {
        applyPreferences(j.preferences || obPrefs);
        if (obPrefs.workspace_name) {
          const sbVer = document.getElementById('sb-version');
          if (sbVer) sbVer.textContent = `Agentic OS — ${obPrefs.workspace_name}`;
        }
      }).catch(()=>{});
    } catch(ex) {}
    showToast('🚀 Welcome to Agentic OS!');
  } else {
    showOnboarding();
  }
}

window.closeOnboardingModal = function() {
  const modal = document.getElementById('onboarding-modal');
  if (modal) {
    modal.style.display = 'none';
    if (modal.parentNode) modal.parentNode.removeChild(modal);
  }
  const overlay = document.getElementById('onboarding-overlay');
  if (overlay) {
    overlay.style.display = 'none';
    if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
  }
  try { localStorage.setItem('agentic_os_onboarded', 'true'); } catch(e) {}
  try { if (window.nav) nav('chat'); } catch(e) {}
};

window.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    if (document.getElementById('onboarding-modal') || document.getElementById('onboarding-overlay')) {
      window.closeOnboardingModal();
    }
  }
});

function obBack() {
  if (obStep > 0) { obStep--; showOnboarding(); }
}

// ── Preferences & Theme ───────────────────────────────────────────
function applyPreferences(prefs) {
  if (!prefs) return;
  if (prefs.theme)        applyTheme(prefs.theme, prefs.accent_color);
  if (prefs.font_size)    document.documentElement.style.fontSize = prefs.font_size + 'px';
  if (prefs.workspace_name) {
    const sb = document.getElementById('sb-version');
    if (sb && prefs.workspace_name) sb.textContent = `Agentic OS — ${prefs.workspace_name}`;
  }
}

const THEME_VARS = {
  light:    { bg0:'#f8fafc', bg1:'#ffffff', bg2:'#f1f5f9', bg3:'#e2e8f0', bg4:'#cbd5e1', bg5:'#94a3b8', text0:'#0f172a', text1:'#334155', text2:'#64748b', text3:'#94a3b8', border:'rgba(15,23,42,0.12)', borderHi:'rgba(15,23,42,0.22)', accent:'#0284c7', accentHi:'#0369a1' },
  dark:     { bg0:'#060814', bg1:'#0b0f22', bg2:'#111633', bg3:'#171d42', bg4:'#1f2654', bg5:'#28316b', text0:'#f8fafc', text1:'#cbd5e1', text2:'#8292b4', text3:'#47557a', border:'rgba(56,189,248,.14)', borderHi:'rgba(56,189,248,.28)', accent:'#38bdf8', accentHi:'#7dd3fc' },
  obsidian: { bg0:'#040408', bg1:'#06060d', bg2:'#090912', bg3:'#10101c', bg4:'#1a1a2e', bg5:'#252542', text0:'#ffffff', text1:'#cbd5e1', text2:'#7a8aaa', text3:'#47557a', border:'rgba(255,255,255,.1)', borderHi:'rgba(255,255,255,.2)', accent:'#38bdf8', accentHi:'#7dd3fc' },
  jet:      { bg0:'#000000', bg1:'#0a0a0a', bg2:'#121216', bg3:'#1a1a20', bg4:'#24242e', bg5:'#30303e', text0:'#ffffff', text1:'#e2e8f0', text2:'#94a3b8', text3:'#64748b', border:'rgba(255,255,255,.15)', borderHi:'rgba(255,255,255,.3)', accent:'#e11d48', accentHi:'#fb7185' },
  midnight: { bg0:'#050810', bg1:'#080b14', bg2:'#0f1220', bg3:'#161b30', bg4:'#202848', bg5:'#2d3764', text0:'#f8fafc', text1:'#c2ceec', text2:'#7a8aaa', text3:'#3a4468', border:'rgba(168,85,247,.16)', borderHi:'rgba(168,85,247,.3)', accent:'#a855f7', accentHi:'#c084fc' },
  forest:   { bg0:'#06100a', bg1:'#09160e', bg2:'#0e2216', bg3:'#14301f', bg4:'#1d452d', bg5:'#275e3d', text0:'#ecfdf5', text1:'#a7f3d0', text2:'#6ee7b7', text3:'#34d399', border:'rgba(16,185,129,.16)', borderHi:'rgba(16,185,129,.3)', accent:'#10b981', accentHi:'#34d399' },
};

function applyTheme(themeId, accentOverride) {
  const tid    = themeId || localStorage.getItem('agentic_os_theme') || 'light';
  const t      = THEME_VARS[tid] || THEME_VARS.light;
  const accent = accentOverride || t.accent || '#0284c7';
  const root   = document.documentElement;
  root.style.setProperty('--bg-0',       t.bg0);
  root.style.setProperty('--bg-1',       t.bg1);
  root.style.setProperty('--bg-2',       t.bg2);
  if (t.bg3) root.style.setProperty('--bg-3', t.bg3);
  if (t.bg4) root.style.setProperty('--bg-4', t.bg4);
  if (t.bg5) root.style.setProperty('--bg-5', t.bg5);
  if (t.text0) root.style.setProperty('--text-0', t.text0);
  if (t.text1) root.style.setProperty('--text-1', t.text1);
  if (t.text2) root.style.setProperty('--text-2', t.text2);
  if (t.text3) root.style.setProperty('--text-3', t.text3);
  if (t.border) root.style.setProperty('--border', t.border);
  if (t.borderHi) root.style.setProperty('--border-hi', t.borderHi);
  root.style.setProperty('--accent',     accent);
  root.style.setProperty('--accent-hi',  t.accentHi || accent);
  root.style.setProperty('--accent-glow', accent + '22');
  
  root.setAttribute('data-theme', tid);
  if (document.body) document.body.setAttribute('data-theme', tid);
  try { localStorage.setItem('agentic_os_theme', tid); } catch(e) {}

  // Persist (non-blocking, errors ignored since this is a background save)
  fetch('/api/onboarding/preferences', {
    method: 'PATCH', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({theme: tid, accent_color: accent})
  }).then(r => {
    if (!r.ok) console.warn('[Theme] Persist failed: HTTP ' + r.status);
  }).catch(ex => console.warn('[Theme] Persist error:', ex?.message));
}

// Expose globally for settings panel
window.applyTheme = applyTheme;

window.switchUIMode = async function(mode) {
  if (mode !== 'simple' && mode !== 'power') return;
  try { localStorage.setItem('agentic_os_mode', mode); } catch(e) {}
  if (typeof _UI !== 'undefined') _UI.uiMode = mode;
  if (window._UI) window._UI.uiMode = mode;
  document.documentElement.setAttribute('data-ui-mode', mode);
  
  if (typeof window.applyMode === 'function') window.applyMode(mode);
  if (typeof window.applyUIMode === 'function') window.applyUIMode(mode);
  if (typeof updateSettingsModeButtons === 'function') updateSettingsModeButtons();
  
  const advItems = document.querySelectorAll('.nav-item[data-tier="advanced"], .sidebar-group-label[data-tier="advanced"], [data-tier="advanced"]');
  advItems.forEach(el => { el.style.display = mode === 'power' ? '' : 'none'; });
  
  const agentsSection = document.querySelectorAll('.sidebar-section, #agent-list, .sidebar-add-agent');
  agentsSection.forEach(el => { el.style.display = mode === 'power' ? '' : 'none'; });

  if (mode === 'simple') {
    if (typeof window.toggleSidebarGroup === 'function') window.toggleSidebarGroup('core', true);
  } else {
    ['core', 'build', 'ship', 'tools', 'enterprise'].forEach(gid => {
      if (typeof window.toggleSidebarGroup === 'function') window.toggleSidebarGroup(gid, false);
    });
  }

  try {
    fetch('/api/profile', {
      method: 'PATCH', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ui_mode: mode})
    }).catch(()=>{});
  } catch(e) {}
};

// ── Settings Appearance helpers ────────────────────────────────────
window.updateSettingsModeButtons = function() {
  const mode = localStorage.getItem('agentic_os_mode') || (typeof _UI !== 'undefined' ? _UI.uiMode : 'simple') || 'simple';
  const simBtn = document.getElementById('settings-simple-btn');
  const pwrBtn = document.getElementById('settings-power-btn');
  if (simBtn) {
    simBtn.style.borderColor = mode === 'simple' ? 'var(--accent)' : 'var(--border)';
    simBtn.style.background  = mode === 'simple' ? 'rgba(91,138,248,.12)' : 'var(--bg-3)';
  }
  if (pwrBtn) {
    pwrBtn.style.borderColor = mode === 'power' ? 'var(--accent)' : 'var(--border)';
    pwrBtn.style.background  = mode === 'power' ? 'rgba(91,138,248,.12)' : 'var(--bg-3)';
  }
  const fs = localStorage.getItem('agentic_os_font_size') || (typeof _UI !== 'undefined' ? _UI.profile?.font_size : 'base') || 'base';
  ['sm','base','lg'].forEach(s => {
    const b = document.getElementById(`fs-${s}`);
    if (b) {
      b.style.background   = s === fs ? 'var(--accent)' : '';
      b.style.color        = s === fs ? '#fff' : '';
      b.style.borderColor  = s === fs ? 'var(--accent)' : '';
    }
  });
};

window.saveFontSize = async function(size) {
  const sizeMap = { sm: '13px', base: '14px', lg: '16px' };
  const zoomMap = { sm: '0.90', base: '1.0', lg: '1.12' };
  document.documentElement.style.fontSize = sizeMap[size] || '14px';
  document.documentElement.style.setProperty('--text-base', sizeMap[size] || '14px');
  if (document.body) document.body.style.zoom = zoomMap[size] || '1.0';
  try { localStorage.setItem('agentic_os_font_size', size); } catch(e) {}
  if (typeof _UI !== 'undefined') {
    if (!_UI.profile) _UI.profile = {};
    _UI.profile.font_size = size;
  }
  if (typeof updateSettingsModeButtons === 'function') updateSettingsModeButtons();
  toast(`✅ Typography scale set to ${size}`, 'ok', 2000);
  try {
    fetch('/api/profile', {
      method: 'PATCH', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({font_size: size})
    }).catch(()=>{});
  } catch(e) {}
};

// ── Keyboard Shortcuts Overlay ─────────────────────────────────────
async function showShortcuts() {
  const list = document.getElementById('shortcuts-list');
  if (list && !list.children.length) {
    try {
      const r = await fetch('/api/onboarding/shortcuts');
      if (!r.ok) { list.innerHTML = '<div style="color:var(--danger)">Failed to load shortcuts</div>'; }
      else {
        const shortcuts = await r.json();
        list.innerHTML = shortcuts.map(s =>
          `<div style="display:flex;align-items:center;justify-content:space-between;padding:7px 0;border-bottom:1px solid var(--border)">
            <span style="font-size:13px;color:var(--text-1)">${escHtml(s.label)}</span>
            <div style="display:flex;gap:4px">
              ${s.keys.map(k => `<kbd style="background:var(--bg-3);border:1px solid var(--border);border-radius:5px;padding:2px 7px;font-size:12px;font-family:monospace">${escHtml(k)}</kbd>`).join('')}
            </div>
          </div>`
        ).join('');
      }
    } catch(ex) {
      if (list) list.innerHTML = `<div style="color:var(--danger)">Error: ${escHtml(ex?.message||String(ex))}</div>`;
    }
  }
  document.getElementById('shortcuts-modal').style.display = 'flex';
}
window.showShortcuts = showShortcuts;
window.showKeyboardShortcuts = function() {
  const lp = document.getElementById('mission-launchpad-deck');
  if (lp) lp.style.display = 'block';
  showShortcuts();
};

// Add shortcuts button to topbar (done at end of init)

// ── Collaboration ─────────────────────────────────────────────────
let collabWS = null, collabSessionId = null, collabPeerId = null;

async function startCollab() {
  // Create a new session
  const r = await fetch('/api/collab/sessions', { method:'POST' });
  const j = await r.json();
  if (!j.ok) { toast('Failed to create collab session', 'err'); return; }

  const url = `${location.origin}/?collab=${j.session_id}`;
  await gmAlert('🤝 Collaboration Session Created',
    `<div style="margin-bottom:10px">Share this URL with collaborators:</div>
     <code style="background:var(--bg-0);padding:8px 12px;border-radius:var(--radius-sm);display:block;font-size:12px;word-break:break-all">${url}</code>
     <div style="margin-top:10px;font-size:12px;color:var(--text-2)">They'll see your cursor, navigation, and can chat in real-time.</div>`
  );

  joinCollabSession(j.session_id);
}

function joinCollabSession(sessionId) {
  if (collabWS) { collabWS.close(); }
  collabSessionId = sessionId;

  const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  collabWS = new WebSocket(`${wsProto}//${location.host}/api/collab/sessions/${sessionId}/ws`);

  collabWS.onopen = () => {
    const name = S.preferences?.workspace_name || 'User';
    collabWS.send(JSON.stringify({ type:'join', name, pane:'chat' }));
    document.getElementById('collab-bar').style.display = 'flex';
    document.getElementById('collab-info').textContent = `Session: ${sessionId}`;
    toast('🤝 Joined collab session', 'ok');
  };

  collabWS.onmessage = e => {
    try {
      const msg = JSON.parse(e.data);
      handleCollabMsg(msg);
    } catch(err) {}
  };

  collabWS.onclose = () => {
    document.getElementById('collab-bar').style.display = 'none';
    toast('Collab session ended', 'warn', 2000);
    collabWS = null;
  };
}

function handleCollabMsg(msg) {
  if (msg.type === 'peer_joined' || msg.type === 'peer_left') {
    const peers = msg.peers || [];
    document.getElementById('collab-peers').innerHTML = peers
      .filter(p => p.id !== collabPeerId)
      .map(p => `<span style="background:${p.color};color:#000;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:700">${escHtml(p.name)}</span>`)
      .join('');
    if (msg.type === 'peer_joined') toast(`👋 ${msg.name} joined`, 'ok', 2000);
    else toast(`👋 A collaborator left`, 'ok', 1500);
  }
  if (msg.type === 'joined') { collabPeerId = msg.peer_id; }
  if (msg.type === 'nav' && msg.pane) {
    // Show ghost indicator of where peer is navigating
    toast(`👁 ${msg.peer_id.slice(0,6)}… → ${msg.pane}`, 'ok', 1500);
  }
  if (msg.type === 'chat') {
    // Show peer chat as a message
    addMessage(msg.message, 'agent', '👤', msg.name + ' (collab)');
  }
}

function leaveCollab() {
  if (collabWS) collabWS.close();
  collabWS = null; collabSessionId = null;
  document.getElementById('collab-bar').style.display = 'none';
}

// Broadcast nav events to collab peers
const _s5origNav = nav;
nav = function(pane) {
  _s5origNav(pane);
  if (collabWS?.readyState === 1) {
    collabWS.send(JSON.stringify({ type:'nav', payload:{ pane } }));
  }
};

// Check for collab invite in URL
(function checkCollabInvite() {
  const params = new URLSearchParams(location.search);
  const sid = params.get('collab');
  if (sid) {
    setTimeout(() => {
      toast(`🤝 Joining collaboration session ${sid}…`, 'ok', 2000);
      joinCollabSession(sid);
    }, 1500);
  }
})();

// Add shortcuts button to topbar (Collab and Marketplace live in sidebar)
(function addTopbarBtns() {
  const actions = document.getElementById('topbar-actions');
  if (!actions) { setTimeout(addTopbarBtns, 400); return; }
  if (document.getElementById('shortcuts-btn')) return;

  // Shortcuts button
  const sb = document.createElement('button');
  sb.id = 'shortcuts-btn';
  sb.className = 'icon-btn';
  sb.title = 'Keyboard shortcuts';
  sb.textContent = '⌨️';
  sb.onclick = showShortcuts;
  actions.insertBefore(sb, actions.firstChild);
})();

// Add plugin + collab commands to palette
PALETTE_CMDS.push(
  {icon:'🧩', label:'Plugin Marketplace', desc:'Install skill packs', action:()=>nav('plugins')},
  {icon:'🤝', label:'Start Collaboration', desc:'Share session with others', action:()=>startCollab()},
  {icon:'⌨️', label:'Keyboard Shortcuts',  desc:'View all shortcuts', action:()=>showShortcuts()},
  {icon:'🎨', label:'Change Theme',        desc:'Switch dark theme variant', action:()=>nav('settings')},
  {icon:'📤', label:'Export Workspace',    desc:'Download agents, skills, memories', action:()=>exportWorkspaceData()},
  {icon:'🔄', label:'Run Onboarding',      desc:'Re-run setup wizard', action:async()=>{ await fetch('/api/onboarding/reset',{method:'POST'}); checkOnboarding(); }},
);

// Store preferences reference
S.preferences = {};
fetch('/api/onboarding/preferences').then(r=>r.ok?r.json():{}).then(p=>{
  if (!p) return;
  S.preferences = p;
  applyPreferences(p);
}).catch(()=>{});




// ═══════════════════════════════════════════════════════════════
//  SPRINT 10 — Control Tower, Workspaces, Webhooks, Test Gen,
//              Notification Center
// ═══════════════════════════════════════════════════════════════

// ── Extend nav for Sprint 10 ───────────────────────────────────────
const _s10NavBase = function(){}; // nav chain disabled — master nav handles all
function _disabled__s10NavBase(pane) {
  _s10NavBase(pane);
  if (pane === 'control')    renderControlTower();
  if (pane === 'workspaces') renderWorkspaces();
  if (pane === 'webhooks')   renderWebhooks();
  if (pane === 'testgen')    renderTestGen();
}

// ── Control Tower ──────────────────────────────────────────────────
var controlRefreshTimer = null;
async function renderControlTower() {
  const pane = document.getElementById('pane-control');
  pane.innerHTML = skeletonPage();
  clearInterval(controlRefreshTimer);
  await refreshControlTower();
  controlRefreshTimer = setInterval(refreshControlTower, 5000);
}
window.renderControlTower = renderControlTower;
window.refreshControlTower = refreshControlTower;

async function refreshControlTower() {
  const pane = document.getElementById('pane-control');
  if (!pane || !pane.classList.contains('active')) { clearInterval(controlRefreshTimer); return; }
  try {
    const [sr, rr, br, nr] = await Promise.all([
      fetch('/api/control/stats'), fetch('/api/control/runs?limit=20'),
      fetch('/api/control/budget-rules'), fetch('/api/control/notifications?limit=5'),
    ]);
    const [stats, runs, rules, nd] = await Promise.all([sr.json(), rr.json(), br.json(), nr.json()]);
    const active = runs.filter(r => r.status === 'running');
    pane.innerHTML = `
      ${pageHeader({title:'🎛️ Control Tower', subtitle:'Live agent traces · kill switch · budget guardrails', badge: active.length > 0 ? active.length + ' LIVE' : ''})}
      <div class="page-content">
      ${active.length > 0 ? `<div style="background:rgba(232,82,82,.08);border:1px solid rgba(232,82,82,.3);border-radius:var(--radius-lg);padding:14px 18px;margin-bottom:20px;display:flex;align-items:center;gap:14px">
        <span style="font-size:20px">🔴</span>
        <div style="flex:1"><div style="font-weight:700;color:#e85252">${active.length} agent${active.length>1?'s':''} running</div>
        <div style="font-size:11.5px;color:var(--text-2)">Total cost: $${active.reduce((a,r)=>a+(r.total_cost||0),0).toFixed(4)}</div></div>
        <button onclick="killAllRuns()" class="btn btn-danger btn-sm">🛑 Kill All</button>
      </div>` : ''}
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px;margin-bottom:20px">
        ${[['Total Runs',stats.total_runs||0],['Active',stats.active_runs||0],['Today Cost','$'+(stats.today_cost||0).toFixed(4)],['Total Cost','$'+(stats.total_cost||0).toFixed(4)],['Errors',stats.error_count||0],['Killed',stats.killed_count||0]].map(([l,v])=>`<div class="stat-card"><div class="stat-card__label">${l}</div><div class="stat-card__value" style="font-size:20px">${v}</div></div>`).join('')}
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">
        <div>
          <div style="font-weight:700;margin-bottom:10px">Agent Runs</div>
          <div style="display:flex;flex-direction:column;gap:5px">
            ${runs.length === 0 ? emptyState({icon:'📊',title:'No runs yet',body:'Agent runs appear here with full traces and cost breakdown.'}) :
            runs.slice(0,10).map(r=>{
              const sCol = {running:'var(--warning)',done:'var(--success)',error:'var(--danger)',killed:'var(--text-3)'}[r.status]||'var(--text-2)';
              return `<div class="card card-interactive" onclick="showRunTrace('${r.run_id}')" style="padding:9px 12px">
                <div style="display:flex;align-items:center;gap:9px">
                  <span style="color:${sCol};font-size:9px">●</span>
                  <div style="flex:1;min-width:0">
                    <div style="font-size:12.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escHtml(r.agent_name||r.agent_id||'?')}</div>
                    <div style="font-size:11px;color:var(--text-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escHtml((r.prompt||'').slice(0,50))}</div>
                  </div>
                  <div style="text-align:right;flex-shrink:0">
                    <div style="font-size:11px;color:${sCol};font-weight:700">${r.status}</div>
                    <div style="font-size:10px;color:var(--text-3)">$${(r.total_cost||0).toFixed(4)}</div>
                  </div>
                  ${r.status==='running'?`<button onclick="event.stopPropagation();killRun('${r.run_id}')" class="btn btn-danger btn-sm">🛑</button>`:''}
                </div>
              </div>`;}).join('')}
          </div>
        </div>
        <div>
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
            <div style="font-weight:700">💰 Budget Guardrails</div>
            <button onclick="addBudgetRule()" class="btn btn-primary btn-sm">＋ Rule</button>
          </div>
          ${helpPanel({title:'Stop agents before costs run away',body:'Set limits per agent or globally. Warn or auto-stop when limit is hit.'})}
          <div style="display:flex;flex-direction:column;gap:5px">
            ${rules.length === 0 ? `<div style="color:var(--text-3);font-size:12px;text-align:center;padding:12px">No rules — agents run unlimited</div>` :
            rules.map(r=>`<div class="card" style="padding:9px 12px;display:flex;align-items:center;gap:10px">
              <div style="flex:1"><div style="font-size:12.5px;font-weight:600">${escHtml(r.name)}</div>
              <div style="font-size:11px;color:var(--text-2)">Max $${r.max_cost} · ${r.action}</div></div>
              <span class="badge ${r.enabled?'badge-success':'badge-default'}">${r.enabled?'On':'Off'}</span>
              <button onclick="deleteBudgetRule(${JSON.stringify(r.id)})" style="background:none;border:none;color:var(--text-3);cursor:pointer">🗑</button>
            </div>`).join('')}
          </div>
        </div>
      </div>
      </div>`;
  } catch(e) {
    pane.innerHTML = `<div class="page-content">${emptyState({icon:'⚠️',title:'Error',body:e.message})}</div>`;
  }
}
async function showRunTrace(runId) {
  // FIX A: try/catch around fetch
  let run = {}, steps = [];
  try {
    const r = await fetch(`/api/control/runs/${encodeURIComponent(runId)}`);
    if (!r.ok) { showToast('⚠️ Could not load trace'); return; }
    const j = await r.json();
    run = j.run||{}; steps = j.steps||[];
  } catch(ex) { showToast('⚠️ Failed to load trace: ' + ex.message); return; }
  await gmAlert(`🔍 Trace — ${escHtml(run.agent_name||runId)}`,
    `<div style="max-height:420px;overflow-y:auto">
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">
        <span class="badge ${run.status==='done'?'badge-success':run.status==='error'?'badge-danger':'badge-warning'}">${run.status||'?'}</span>
        <span class="badge badge-default">$${(run.total_cost||0).toFixed(5)}</span>
        <span class="badge badge-default">${run.total_tokens||0} tokens</span>
        <span class="badge badge-default">${run.duration_ms||0}ms · ${steps.length} steps</span>
      </div>
      <div style="font-size:12px;color:var(--text-2);margin-bottom:10px">${escHtml((run.prompt||'').slice(0,200))}</div>
      ${steps.map((s,i)=>`<div style="border-left:2px solid ${s.status==='done'?'var(--success)':'var(--danger)'};padding:6px 12px;margin-bottom:5px;background:var(--bg-3);border-radius:0 6px 6px 0">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:3px">
          <span style="font-size:10px;color:var(--text-3)">${i+1}</span>
          <span style="font-size:12px;font-weight:600">${escHtml(s.name||s.step_type||'step')}</span>
          <span style="margin-left:auto;font-size:10px;color:var(--text-2)">$${(s.cost||0).toFixed(5)} · ${s.duration_ms||0}ms</span>
        </div>
        ${s.output_text?`<div style="font-size:11px;color:var(--text-1);max-height:50px;overflow:hidden">${escHtml((s.output_text||'').slice(0,150))}</div>`:''}
      </div>`).join('')}
    </div>`);
}
async function killRun(runId) {
  if (!(await gmDanger('Kill Run', `Stop run ${runId}?`, 'Kill'))) return;
  const r = await fetch(`/api/control/runs/${encodeURIComponent(runId)}/kill`, {method:'POST'});
  const j = await r.json();
  if (j.ok) { toast('🛑 Run killed', 'ok', 2000); refreshControlTower(); }
}
async function killAllRuns() {
  if (!(await gmDanger('Kill All Runs', 'Stop ALL running agents?', 'Kill All'))) return;
  const r = await fetch('/api/control/runs/kill-all', {method:'POST'});
  const j = await r.json();
  toast(`🛑 Killed ${j.killed} run(s)`, 'ok', 2000); refreshControlTower();
}
async function addBudgetRule() {
  // FIX 6: let user choose action (stop/warn) instead of hardcoding 'warn'
  const name = await gmPrompt('Rule Name', 'e.g. Global cost limit', 'Budget Alert');
  if (!name) return;
  const cost = await gmPrompt('Max cost (USD)', 'e.g. 1.00', '1.00');
  if (!cost) return;
  const agentId = await gmPrompt('Agent ID (* = all agents)', 'e.g. builder or * for all', '*') || '*';
  const action = await gmPrompt('Action when limit hit (stop / warn)', 'stop or warn', 'stop');
  const validAction = (action === 'warn') ? 'warn' : 'stop';
  await fetch('/api/control/budget-rules', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name, max_cost: parseFloat(cost)||1.0, agent_id: agentId, action: validAction})});
  showToast('✅ Budget rule created');
  refreshControlTower();
}
async function deleteBudgetRule(id) {
  if (!(await gmDanger('Delete Rule', 'Remove this guardrail?'))) return;
  await fetch(`/api/control/budget-rules/${encodeURIComponent(id)}`, {method:'DELETE'});
  toast('Rule deleted', 'ok', 1500); refreshControlTower();
}

// ── Workspaces ─────────────────────────────────────────────────────
async function renderWorkspaces() {
  const pane = document.getElementById('pane-workspaces');
  pane.innerHTML = skeletonPage();
  try {
    const r = await fetch('/api/workspaces');
    if (!r.ok) throw new Error('Workspaces API error ' + r.status);
    const ws = await r.json();
    pane.innerHTML = `
      ${pageHeader({title:'📁 Workspaces', subtitle:'Separate projects — each has its own files, settings, and preview',
        actions:[{label:'Import GitHub',action:'importFromGitHub()'},{label:'Export ZIP',action:'exportCurrentZip()'},{label:'＋ New Project',action:'createNewWorkspace()',primary:true}]})}
      <div class="page-content">
      ${helpPanel({title:'Switch between multiple client projects',body:'Activating a workspace loads its files into Studio instantly. Your current work is auto-saved first.',steps:['Click a workspace card to activate','All files switch automatically','Edit, build, and deploy independently','Export any project as a ZIP']})}
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px">
        ${ws.map(w=>`<div class="card ${w.is_current?'':'card-interactive lift'}" style="${w.is_current?'border-color:var(--accent)':''}">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
            <div style="width:36px;height:36px;border-radius:8px;background:${w.color||'var(--accent)'}22;border:1px solid ${w.color||'var(--accent)'}44;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0">${w.emoji||'📁'}</div>
            <div style="flex:1;min-width:0"><div style="font-weight:700;font-size:13.5px">${escHtml(w.name)}</div>
            <div style="font-size:11px;color:var(--text-2)">${w.file_count||0} files · ${w.framework||'web'}</div></div>
            ${w.is_current?`<span class="badge badge-accent">Active</span>`:''}
          </div>
          <div style="display:flex;gap:6px;flex-wrap:wrap">
            ${w.is_current
              ?`<button onclick="exportCurrentZip()" class="btn btn-ghost btn-sm">📦 Export</button>`
              :`<button onclick="activateWorkspace(${JSON.stringify(w.id)},${JSON.stringify(w.name)})" class="btn btn-primary btn-sm">Switch →</button>
                <button onclick="exportWorkspace(${JSON.stringify(w.id)})" class="btn btn-ghost btn-sm">📦</button>
                <button onclick="deleteWorkspace(${JSON.stringify(w.id)},${JSON.stringify(w.name)})" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:11px">🗑</button>`}
          </div>
        </div>`).join('')}
        <div class="card card-interactive" onclick="createNewWorkspace()" style="display:flex;align-items:center;justify-content:center;min-height:120px;border-style:dashed;cursor:pointer">
          <div style="text-align:center;color:var(--text-3)"><div style="font-size:24px;margin-bottom:4px">＋</div><div style="font-size:12.5px">New Project</div></div>
        </div>
      </div>
      </div>`;
  } catch(e) { pane.innerHTML=`<div class="page-content">${emptyState({icon:'⚠️',title:'Error',body:e.message})}</div>`; }
}
async function activateWorkspace(wsId, name) {
  toast(`⚡ Switching to ${name}…`, 'ok', 2000);
  try {
    const r = await fetch(`/api/workspaces/${encodeURIComponent(wsId)}/activate`, {method:'POST'});
    if (!r.ok) { toast('Switch failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast(`✅ Switched to ${name}`, 'ok', 2000); studioLoadFileTree?.(); studioReloadPreview?.(); renderWorkspaces(); }
    else toast('Switch failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('Switch error: ' + ex.message, 'err'); }
}
async function createNewWorkspace() {
  const name = await gmPrompt('New Project', 'Project name (e.g. Client A, My SaaS)','');
  if (!name) return;
  try {
    const r = await fetch('/api/workspaces', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({name, emoji:'📁'})});
    if (!r.ok) { toast('Create failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast(`✅ "${name}" created`, 'ok'); renderWorkspaces(); }
    else toast('Create failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('Create error: ' + ex.message, 'err'); }
}
async function exportCurrentZip() {
  const a = document.createElement('a'); a.href='/api/workspaces/export/current'; a.download='agentic-os-project.zip'; a.click();
  toast('📦 Download started', 'ok', 2000);
}
async function exportWorkspace(wsId) {
  const a = document.createElement('a'); a.href=`/api/workspaces/${wsId}/export`; a.download=`workspace-${wsId}.zip`; a.click();
}
async function deleteWorkspace(wsId, name) {
  if (!(await gmDanger('Delete Project', `Delete "${name}"? This cannot be undone.`,'Delete'))) return;
  try {
    const r = await fetch(`/api/workspaces/${encodeURIComponent(wsId)}`, {method:'DELETE'});
    if (!r.ok) { toast('Delete failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast('🗑 Deleted', 'ok'); renderWorkspaces(); }
    else toast('Delete failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('Delete error: ' + ex.message, 'err'); }
}
async function importFromGitHub() {
  const repo = await gmPrompt('Import from GitHub', 'e.g. username/my-repo','');
  if (!repo) return;
  if (!repo.includes('/')) { toast('Enter as username/repo-name', 'warn'); return; }
  toast('⬇️ Importing…', 'ok', 3000);
  try {
    const r = await fetch('/api/workspaces/import/github', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({repo, name: repo.split('/')[1]||repo})});
    if (!r.ok) { toast('Import failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast(`✅ Imported ${j.files_imported} files from ${repo}`, 'ok', 4000); renderWorkspaces(); }
    else toast('Import failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('Import error: ' + ex.message, 'err'); }
}

// ── Webhooks ───────────────────────────────────────────────────────
async function renderWebhooks() {
  const pane = document.getElementById('pane-webhooks');
  pane.innerHTML = skeletonPage();
  try {
    const [wr, tr] = await Promise.all([fetch('/api/webhooks'), fetch('/api/webhooks/templates')]);
    if (!wr.ok) throw new Error('Webhooks API error ' + wr.status);
    if (!tr.ok) throw new Error('Templates API error ' + tr.status);
    const [whs, tmpls] = await Promise.all([wr.json(), tr.json()]);
    pane.innerHTML = `
      ${pageHeader({title:'🌐 Webhooks', subtitle:'External events trigger agent runs — GitHub push, Stripe payment, form submit',
        actions:[{label:'＋ New Webhook', action:'createWebhook()', primary:true}]})}
      <div class="page-content">
      ${helpPanel({title:'Automate with webhooks',body:'Any service can trigger your agents. Get a unique URL, add it to GitHub/Stripe/Zapier.',steps:['Click + New Webhook','Copy the generated URL','Add it to your service','Agents run automatically on every event']})}
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">
        <div>
          <div style="font-weight:700;margin-bottom:10px">Your Webhooks</div>
          ${whs.length===0 ? emptyState({icon:'🌐',title:'No webhooks yet',body:'Create a webhook to trigger agents from external services.',actions:[{label:'Create Webhook',action:'createWebhook()',primary:true}]}) :
          whs.map(w=>`<div class="card" style="margin-bottom:8px">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
              <div style="flex:1;min-width:0"><div style="font-weight:600;font-size:13px">${escHtml(w.name)}</div>
              <div style="font-size:11px;color:var(--text-2)">Agent: ${w.agent_id} · ${w.trigger_count||0} triggers</div></div>
              <span class="badge ${w.enabled?'badge-success':'badge-default'}">${w.enabled?'Active':'Off'}</span>
            </div>
            <div style="background:var(--bg-1);border:1px solid var(--border);border-radius:6px;padding:5px 9px;font-size:11px;font-family:monospace;color:var(--accent);margin-bottom:8px;display:flex;align-items:center;gap:6px">
              <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">POST /api/webhooks/${w.id}/trigger</span>
              <button onclick="navigator.clipboard.writeText('http://localhost:8787/api/webhooks/' + encodeURIComponent('${w.id}') + '/trigger').then(()=>toast('📋 Copied','ok',1200))" style="background:none;border:none;color:var(--text-2);cursor:pointer">📋</button>
            </div>
            <div style="display:flex;gap:6px">
              <button onclick="testWebhook(${JSON.stringify(w.id)})" class="btn btn-ghost btn-sm">▶ Test</button>
              <button onclick="deleteWebhook(${JSON.stringify(w.id)})" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:11px;margin-left:auto">🗑</button>
            </div>
          </div>`).join('')}
        </div>
        <div>
          <div style="font-weight:700;margin-bottom:10px">🚀 Templates</div>
          ${tmpls.map(t=>`<div class="card card-interactive lift" onclick="installWebhookTemplate(${JSON.stringify(t.id)})" style="margin-bottom:8px;padding:11px">
            <div style="font-weight:600;font-size:12.5px;margin-bottom:2px">${escHtml(t.name)}</div>
            <div style="font-size:11.5px;color:var(--text-2);margin-bottom:4px">${escHtml(t.description)}</div>
            <div style="font-size:10.5px;color:var(--text-3)">${escHtml(t.setup)}</div>
          </div>`).join('')}
        </div>
      </div>
      </div>`;
  } catch(e) { pane.innerHTML=`<div class="page-content">${emptyState({icon:'⚠️',title:'Error',body:e.message})}</div>`; }
}
async function createWebhook() {
  const name = await gmPrompt('Webhook Name','e.g. GitHub Push Handler','');
  if (!name) return;
  const agentId = await gmPrompt('Agent','e.g. reviewer, brain','brain')||'brain';
  try {
    const r = await fetch('/api/webhooks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,agent_id:agentId})});
    if (!r.ok) { toast('Create failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) {
      await gmAlert('✅ Webhook Created!',`<div style="margin-bottom:8px">Endpoint:</div>
        <code style="display:block;background:var(--bg-0);padding:8px;border-radius:4px;font-size:12px;word-break:break-all">http://localhost:8787/api/webhooks/${j.id}/trigger</code>
        <div style="margin-top:8px;font-size:12px;color:var(--text-2)">Header: <code>X-Webhook-Secret: ${j.secret}</code></div>`);
      renderWebhooks();
    } else {
      toast('Create failed: ' + (j.error||'unknown error'), 'err');
    }
  } catch(ex) { toast('Create webhook error: ' + ex.message, 'err'); }
}
async function installWebhookTemplate(id) {
  try {
    const r = await fetch('/api/webhooks/templates');
    if (!r.ok) { toast('Failed to load templates: ' + r.status, 'err'); return; }
    const tmpls = await r.json();
    const t = tmpls.find(x=>x.id===id);
    if (!t) { toast('Template not found', 'err'); return; }
    const r2 = await fetch('/api/webhooks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:t.name,agent_id:t.agent_id,prompt_template:t.prompt_template})});
    if (!r2.ok) { toast('Create failed: server error ' + r2.status, 'err'); return; }
    const j = await r2.json();
    if (j.ok) { toast(`✅ ${t.name} created`, 'ok', 3000); renderWebhooks(); }
    else toast('Create failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('Template install error: ' + ex.message, 'err'); }
}
async function testWebhook(id) {
  toast('▶ Sending test event…', 'ok', 1500);
  try {
    const r = await fetch(`/api/webhooks/${encodeURIComponent(id)}/test`, {method:'POST'});
    if (!r.ok) { toast('Test failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) toast(`✅ Test sent — run ${j.run_id}`, 'ok', 3000);
    else toast('Test failed: '+(j.error||''), 'err');
  } catch(ex) { toast('Test error: ' + ex.message, 'err'); }
}
async function deleteWebhook(id) {
  if (!(await gmDanger('Delete Webhook','Remove this endpoint? This cannot be undone.'))) return;
  try {
    const r = await fetch(`/api/webhooks/${encodeURIComponent(id)}`,{method:'DELETE'});
    if (!r.ok) { toast('Delete failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast('Deleted','ok',1200); renderWebhooks(); }
    else toast('Delete failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('Delete error: ' + ex.message, 'err'); }
}

// ── Test Generator ─────────────────────────────────────────────────
let generatedTestCode = '';
async function renderTestGen() {
  const pane = document.getElementById('pane-testgen');
  pane.innerHTML = skeletonPage();
  try {
    const [fr, fwr] = await Promise.all([fetch('/api/preview/files'), fetch('/api/testgen/frameworks')]);
    const [files, fws] = await Promise.all([fr.json(), fwr.json()]);
    const codeFiles = files.filter(f=>/\.(js|jsx|ts|tsx|py)$/.test(f.path));
    pane.innerHTML = `
      ${pageHeader({title:'🧪 Test Generator', subtitle:'AI writes comprehensive test suites for any file',actions:[]})}
      <div class="page-content">
      ${helpPanel({title:"AI generates tests you'd spend hours writing",body:'Select a file, choose your framework, get a complete test suite with happy paths, edge cases, mocks, and error handling.',steps:['Select a code file','Choose test framework','Click Generate','Review and save']})}
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">
        <div class="card">
          <h3 style="margin-bottom:14px">Generate Tests</h3>
          <div class="form-group"><label class="form-label">Source File</label>
            <select id="tg-file" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 10px;color:var(--text-0);font-size:13px;outline:none">
              <option value="">Select a file…</option>
              ${codeFiles.map(f=>`<option value="${escHtml(f.path)}">${escHtml(f.path)}</option>`).join('')}
            </select>
          </div>
          <div class="form-group"><label class="form-label">Framework</label>
            <select id="tg-framework" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 10px;color:var(--text-0);font-size:13px;outline:none">
              ${fws.map(f=>`<option value="${f.id}">${f.id} — ${f.lang}</option>`).join('')}
            </select>
          </div>
          <button onclick="generateTests()" class="btn btn-primary" style="width:100%" id="tg-gen-btn">🧪 Generate</button>
          <div id="tg-status" style="font-size:12px;color:var(--text-2);margin-top:8px"></div>
        </div>
        <div class="card">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
            <h3>Generated Tests</h3>
            <button onclick="saveGeneratedTests()" class="btn btn-primary btn-sm" id="tg-save-btn" style="display:none">💾 Save</button>
          </div>
          <pre id="tg-result" style="background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;font-family:'JetBrains Mono',monospace;font-size:11px;min-height:180px;max-height:360px;overflow-y:auto;white-space:pre-wrap;color:var(--text-1)">Select a file and click Generate →</pre>
        </div>
      </div>
      </div>`;
  } catch(e) { pane.innerHTML=`<div class="page-content">${emptyState({icon:'⚠️',title:'Error',body:e.message})}</div>`; }
}
async function generateTests() {
  const filepath = document.getElementById('tg-file')?.value;
  const framework = document.getElementById('tg-framework')?.value||'jest';
  if (!filepath) { toast('Select a file first','warn'); return; }
  const btn = document.getElementById('tg-gen-btn');
  const st  = document.getElementById('tg-status');
  const res = document.getElementById('tg-result');
  const saveBtn = document.getElementById('tg-save-btn');
  btn.disabled=true; btn.textContent='⏳ Generating…';
  st.textContent=`Generating ${framework} tests…`;
  res.textContent=''; generatedTestCode='';
  try {
    const resp = await fetch('/api/testgen/generate',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({filepath,framework,stream:true})});
    // FIX 9: resp.ok check + resp.body null guard
    if (!resp.ok) { throw new Error(`Server error: HTTP ${resp.status}`); }
    if (!resp.body) { throw new Error('No response body — check server logs'); }
    const reader=resp.body.getReader(); const dec=new TextDecoder();
    while(true) {
      const {done,value}=await reader.read(); if(done) break;
      for(const line of dec.decode(value,{stream:true}).split('\n')) {
        if(!line.startsWith('data:')) continue;
        try { const d=JSON.parse(line.slice(5).trim()); if(d.delta){generatedTestCode+=d.delta;res.textContent=generatedTestCode;res.scrollTop=res.scrollHeight;} } catch(e) {}
      }
    }
    st.textContent=`✅ ${generatedTestCode.split('\n').length} lines generated`;
    if(saveBtn) saveBtn.style.display='';
  } catch(e) { st.textContent='✗ '+e.message; toast('Failed: '+e.message,'err'); }
  finally { btn.disabled=false; btn.textContent='🧪 Generate'; }
}
async function saveGeneratedTests() {
  const fp = document.getElementById('tg-file')?.value;
  const fw = document.getElementById('tg-framework')?.value||'jest';
  if(!generatedTestCode||!fp) return;
  const extMap={jest:'.test.js',vitest:'.test.ts',pytest:'_test.py',mocha:'.test.js',playwright:'.spec.ts'};
  const name = fp.replace(/\.[^.]+$/,'') + (extMap[fw]||'.test.js');
  const r = await fetch('/api/preview/save',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({path:name,content:generatedTestCode,author:'testgen',message:`${fw} tests`})});
  const j = await r.json();
  if(j.ok) { toast(`💾 Saved: ${name}`,'ok',2000); studioLoadFileTree?.(); }
  else toast('Save failed','err');
}

// ── Notification Center ────────────────────────────────────────────
let notifPanelOpen = false, unreadCount = 0;

function toggleNotifPanel() {
  notifPanelOpen = !notifPanelOpen;
  let panel = document.getElementById('notif-panel');
  if (!panel) { panel = createNotifPanel(); document.getElementById('shell').appendChild(panel); }
  panel.style.display = notifPanelOpen ? 'flex' : 'none';
  if (notifPanelOpen) refreshNotifications();
}
function createNotifPanel() {
  const p = document.createElement('div');
  p.id = 'notif-panel';
  p.style.cssText='position:fixed;top:52px;right:0;width:340px;height:calc(100vh - 52px);background:var(--bg-1);border-left:1px solid var(--border);z-index:8000;flex-direction:column;box-shadow:var(--shadow-lg);display:none';
  p.innerHTML=`<div style="display:flex;align-items:center;justify-content:space-between;padding:12px 14px;border-bottom:1px solid var(--border);flex-shrink:0">
    <div style="font-weight:700;font-size:14px">🔔 Notifications</div>
    <div style="display:flex;gap:6px">
      <button onclick="markAllNotifRead()" class="btn btn-ghost btn-sm">Mark all read</button>
      <button onclick="toggleNotifPanel()" style="background:none;border:none;color:var(--text-2);cursor:pointer;font-size:16px">×</button>
    </div>
  </div>
  <div id="notif-list" style="flex:1;overflow-y:auto;padding:6px"></div>`;
  document.addEventListener('click', e => {
    if(notifPanelOpen && !p.contains(e.target) && !document.getElementById('notif-bell-btn')?.contains(e.target))
      { notifPanelOpen=false; p.style.display='none'; }
  });
  return p;
}
async function refreshNotifications() {
  const el = document.getElementById('notif-list'); if(!el) return;
  try {
    let notifs = [], count = 0;
    try {
      const r0 = await fetch('/api/notifications/list?limit=30');
      const d0 = await r0.json();
      if (d0.ok) { notifs = d0.notifications || []; count = d0.unread_count || 0; }
    } catch(err) {
      const r = await fetch('/api/control/notifications?limit=30');
      const d = await r.json();
      notifs = d.notifications||[]; count = d.unread_count||0;
    }
    unreadCount = count;
    updateNotifBadge(unreadCount);
    if(!notifs.length) { el.innerHTML=`<div style="text-align:center;padding:32px 16px;color:var(--text-3)"><div style="font-size:24px;margin-bottom:6px">🔔</div><div style="font-size:12.5px">No notifications right now</div></div>`; return; }
    const icons={run_complete:'✅',budget_alert:'⚠️',error:'❌',deploy:'🚀',system:'ℹ️',info:'ℹ️',success:'✅',warning:'⚠️'};
    el.innerHTML=notifs.map(n=>{
      const unread = !n.read && !n.read_at;
      const title = n.title || '';
      const body = n.message || n.body || '';
      const timeStr = n.timestamp ? new Date(n.timestamp*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : (n.created_at||'').slice(5,16);
      
      let actionButtons = '';
      if (title.includes('HITL') || n.type === 'hitl_interrupt' || n.link === 'control') {
        actionButtons = `<div style="display:flex;gap:6px;margin-top:6px">
          <button onclick="handleNotifAction(event, 'approve-hitl', '${n.id}')" class="btn btn-primary btn-sm" style="padding:2px 8px;font-size:10px;background:var(--success);border:none;color:#fff">✅ Approve Now</button>
          <button onclick="handleNotifAction(event, 'reject-hitl', '${n.id}')" class="btn btn-ghost btn-sm" style="padding:2px 8px;font-size:10px;color:var(--danger)">❌ Reject</button>
        </div>`;
      } else if (title.includes('Vulnerability') || title.includes('Zero-Day') || n.link === 'bounty') {
        actionButtons = `<div style="display:flex;gap:6px;margin-top:6px">
          <button onclick="handleNotifAction(event, 'autopatch', '${n.id}')" class="btn btn-primary btn-sm" style="padding:2px 8px;font-size:10px">🛠️ Auto-Patch Now</button>
        </div>`;
      } else if (n.type === 'budget_alert' || title.includes('Budget')) {
        actionButtons = `<div style="display:flex;gap:6px;margin-top:6px">
          <button onclick="handleNotifAction(event, 'finops', '${n.id}')" class="btn btn-ghost btn-sm" style="padding:2px 8px;font-size:10px;color:var(--warning)">⚙️ Adjust Cap</button>
        </div>`;
      }

      return `<div onclick="markNotifRead(${JSON.stringify(n.id)}); if('${n.link||''}') nav('${n.link}'); toggleNotifPanel()" style="padding:10px 13px;border-bottom:1px solid var(--border);cursor:pointer;background:${unread?'rgba(91,138,248,.08)':''}">
        <div style="display:flex;gap:9px">
          <span style="font-size:15px;flex-shrink:0">${icons[n.type]||'🔔'}</span>
          <div style="flex:1;min-width:0">
            <div style="font-size:12.5px;font-weight:${unread?700:500};color:var(--text-0);margin-bottom:2px">${escHtml(title)}</div>
            <div style="font-size:11px;color:var(--text-2);line-height:1.5">${escHtml(body)}</div>
            ${actionButtons}
            <div style="font-size:10px;color:var(--text-3);margin-top:3px">${timeStr}</div>
          </div>
          ${unread?'<span style="width:7px;height:7px;border-radius:50%;background:var(--accent);flex-shrink:0;margin-top:4px"></span>':''}
        </div>
      </div>`;
    }).join('');
  } catch(e) { el.innerHTML=`<div style="color:var(--danger);padding:12px;font-size:12px">Error: ${e.message}</div>`; }
}
function updateNotifBadge(count) {
  const b=document.getElementById('notif-badge'); if(b) { b.style.display=count>0?'block':'none'; b.textContent=count>99?'99+':count; }
}
async function markNotifRead(id) {
  try { await fetch(`/api/notifications/mark-read/${encodeURIComponent(id)}`,{method:'POST'}); } catch(e){}
  try { await fetch(`/api/control/notifications/${encodeURIComponent(id)}/read`,{method:'PATCH'}); } catch(e){}
  refreshNotifications();
}
async function markAllNotifRead() {
  try { await fetch('/api/notifications/mark-all-read',{method:'POST'}); } catch(e){}
  try { await fetch('/api/control/notifications/read-all',{method:'POST'}); } catch(e){}
  refreshNotifications(); toast('✅ All read','ok',1200);
}

window.handleNotifAction = async function(evt, actionType, notifId) {
  if (evt) { evt.stopPropagation(); evt.preventDefault(); }
  if (actionType === 'approve-hitl' || actionType === 'reject-hitl') {
    const decision = actionType === 'approve-hitl' ? 'approve' : 'reject';
    try {
      await fetch(`/api/hitl/interrupt/${encodeURIComponent(notifId)}/decide`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({decision: decision, note: 'Actioned via Notification Center'})
      });
      toast(`HITL Interrupt ${decision.toUpperCase()}ED successfully`, 'ok', 2500);
    } catch(e) {}
  } else if (actionType === 'autopatch') {
    try {
      await fetch(`/api/security/bounty-hunter/scans/${encodeURIComponent(notifId)}/autopatch`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({vulnerability_id: notifId, apply_to_codebase: true})
      });
      toast('🛠️ Autonomously applied security patch!', 'ok', 3000);
    } catch(e) {}
  } else if (actionType === 'finops') {
    nav('finops');
  }
  markNotifRead(notifId);
};
setInterval(async()=>{
  try {
    let c = 0, firstNotif = null;
    try {
      const r0 = await fetch('/api/notifications/list?unread_only=true&limit=1');
      const d0 = await r0.json();
      if (d0.ok) { c = d0.unread_count || 0; firstNotif = d0.notifications?.[0]; }
    } catch(err) {
      const r = await fetch('/api/control/notifications?unread_only=true&limit=1');
      const d = await r.json(); c = d.unread_count||0; firstNotif = d.notifications?.[0];
    }
    if(c!==unreadCount){unreadCount=c;updateNotifBadge(c);
      if(c>0&&firstNotif&&'Notification'in window&&Notification.permission==='granted'){
        new Notification('Agentic OS',{body:firstNotif.title||firstNotif.message});
      }
    }
    if(notifPanelOpen) refreshNotifications();
  } catch(e){}
}, 15000);
setTimeout(()=>{ if('Notification'in window&&Notification.permission==='default') Notification.requestPermission(); }, 5000);

// Add to palette
if(typeof PALETTE_CMDS!=='undefined') PALETTE_CMDS.push(
  {icon:'🎛️',label:'Control Tower',desc:'Live traces, kill switch, budget rules',action:()=>nav('control')},
  {icon:'🛑',label:'Kill All Agents',desc:'Emergency stop',action:()=>killAllRuns()},
  {icon:'📁',label:'Workspaces',desc:'Switch projects, export ZIP',action:()=>nav('workspaces')},
  {icon:'📦',label:'Export ZIP',desc:'Download project',action:()=>exportCurrentZip()},
  {icon:'🌐',label:'Webhooks',desc:'External triggers',action:()=>nav('webhooks')},
  {icon:'🧪',label:'Generate Tests',desc:'AI test suites',action:()=>nav('testgen')},
  {icon:'🔔',label:'Notifications',desc:'View all alerts',action:()=>toggleNotifPanel()},
);

// ═══════════════════════════════════════════════════════════════
//  SPRINT 12 — Terminal, Image Gen, Integrations, Docs, UX
// ═══════════════════════════════════════════════════════════════

// ── Extend nav for Sprint 12 ────────────────────────────────────
(function() {
  const _s12NavBase = window.nav || function(){};
  window.nav = function(pane) {
    _s12NavBase(pane);
    if (pane === 'terminal')     renderTerminal?.();
    else { document.getElementById('term-suggestions')?.remove(); }  // FIX 13: cleanup suggestions on nav
    if (pane === 'secrets')       renderSecretsVault?.();
    if (pane === 'integrations') renderIntegrations?.();
    if (pane === 'imagegen')     renderImageGen?.();
  };
})();

// ── Terminal State ───────────────────────────────────────────────
const Terminal = { active:'main', history:{'main':[]}, histIdx:{'main':0}, running:false, reader:null, _runId:null };

async function renderTerminal() {
  const pane = document.getElementById('pane-terminal');
  if (!pane) return;
  // FIX 11: preserve output across pane switches — only render once
  if (pane.querySelector('#term-output')) {
    document.getElementById('term-input')?.focus();
    return;
  }
  let env = {};
  try { const r = await fetch('/api/terminal/env'); env = await r.json(); } catch(e) {}
  pane.innerHTML = `
    <div class="terminal-tabs" id="term-tabs">
      <div class="terminal-tab active" data-sess="main">main</div>
      <div class="terminal-tab" onclick="termNewSession()" style="padding:6px 10px;color:var(--text-3)">＋</div>
    </div>
    <div class="terminal-toolbar" id="term-toolbar">
      ${['ls -la','git status','git log --oneline -5','npm install','npm run dev','npm run build','pip install -r requirements.txt','node --version','python3 --version'].map(c=>
        `<button class="term-btn" onclick="termRun(${JSON.stringify(c)})">${c}</button>`).join('')}
      <button class="term-btn" id="term-kill-btn" onclick="termKill()" style="margin-left:auto;color:var(--danger);display:none" title="Kill running process (Ctrl+C)">■ Kill</button>
      <button class="term-btn" onclick="termClear()" style="color:var(--text-3)">Clear</button>
    </div>
    <div class="terminal-container">
      <div class="terminal-output" id="term-output">
        <span class="system">Agentic OS Terminal — ${env.cwd||'/preview'}</span>
        ${env.node?'<span class="system" style="display:block">node '+env.node+'</span>':''}
        ${env.python?'<span class="system" style="display:block">python '+env.python+'</span>':''}
        <span class="system" style="display:block;margin-top:4px">Type a command or click above ↑</span><br>
      </div>
      <div class="terminal-input-row">
        <span class="terminal-prompt">❯</span>
        <input class="terminal-input" id="term-input" placeholder="Enter command…" autocomplete="off" spellcheck="false">
      </div>
    </div>`;
  const input = document.getElementById('term-input');
  if (input) { input.focus(); input.addEventListener('keydown', termKeyDown); input.addEventListener('input', termShowSuggestions); }
  try { const r=await fetch('/api/terminal/history'); const h=await r.json(); Terminal.history['main']=(h||[]).map(x=>x.command||'').reverse(); Terminal.histIdx['main']=Terminal.history['main'].length; } catch(e){}
}
async function termRun(cmd) { const i=document.getElementById('term-input'); if(i) i.value=cmd; await termExecute(cmd); }
async function termExecute(cmd) {
  if (!cmd.trim()) return;
  // FIX 10: prevent concurrent runs
  if (Terminal.running) { termAppend('<span class="stderr">⚠ A command is already running — wait or press ■ Kill</span>'); return; }
  Terminal.running = true;
  const killBtn = document.getElementById('term-kill-btn');
  if (killBtn) killBtn.style.display = '';
  if (!Terminal.history[Terminal.active]) Terminal.history[Terminal.active]=[];
  Terminal.history[Terminal.active].push(cmd);
  Terminal.histIdx[Terminal.active] = Terminal.history[Terminal.active].length;
  const input = document.getElementById('term-input');
  if (input) input.value = '';
  termAppend(`<span class="cmd">❯ ${escHtml(cmd)}</span>`);
  try {
    const resp = await fetch('/api/terminal/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command:cmd,session_id:Terminal.active})});
    // FIX 5: null guard + resp.ok check (FIX 12)
    if (!resp.ok) { termAppend(`<span class="stderr">Server error: HTTP ${resp.status}</span>`); return; }
    if (!resp.body) { termAppend(`<span class="stderr">No response body — check server</span>`); return; }
    const reader = resp.body.getReader(); const decoder = new TextDecoder();
    Terminal.reader = reader;
    while(true) {
      const {done,value} = await reader.read(); if(done) break;
      for (const line of decoder.decode(value,{stream:true}).split('\n')) {
        if(!line.startsWith('data:')) continue;
        try {
          const ev=JSON.parse(line.slice(5).trim());
          if(ev.type==='start'&&ev.run_id){Terminal._runId=ev.run_id;}  // FIX 6: capture run_id
          else if(ev.type==='stdout') termAppend(`<span class="stdout">${escHtml(ev.data)}</span>`);
          else if(ev.type==='error') termAppend(`<span class="stderr">${escHtml(ev.data)}</span>`);
          else if(ev.type==='exit') { const c=ev.exit_code===0?'var(--success)':'var(--danger)'; termAppend(`<span style="color:${c};font-size:11px">Exit: ${ev.exit_code} (${ev.duration_ms||0}ms)</span><br>`); }
        } catch(e){}
      }
    }
  } catch(e) { termAppend(`<span class="stderr">Error: ${escHtml(e.message)}</span>`); }
  finally {
    Terminal.running=false; Terminal.reader=null; Terminal._runId=null;
    const kb=document.getElementById('term-kill-btn'); if(kb) kb.style.display='none';
  }
}
function termAppend(h) { const o=document.getElementById('term-output'); if(o){o.innerHTML+=h;o.scrollTop=o.scrollHeight;} }
function termClear() { const o=document.getElementById('term-output'); if(o) o.innerHTML=''; }
async function termKill() {
  // FIX 6+7: Kill running process via API + abort reader
  if (Terminal._runId) {
    try { await fetch(`/api/terminal/kill/${encodeURIComponent(Terminal._runId)}`,{method:'POST'}); } catch(e){}
  }
  if (Terminal.reader) { try { await Terminal.reader.cancel(); } catch(e){} Terminal.reader=null; }
  Terminal.running=false; Terminal._runId=null;
  termAppend('<span class="stderr">^C — process killed</span>');
  const kb=document.getElementById('term-kill-btn'); if(kb) kb.style.display='none';
}
function termKeyDown(e) {
  const input=document.getElementById('term-input');
  const sess=Terminal.active; const hist=Terminal.history[sess]||[];
  if(e.key==='Enter'){e.preventDefault();const cmd=input.value.trim();if(cmd)termExecute(cmd);}
  else if(e.key==='ArrowUp'){e.preventDefault();if(!Terminal.histIdx[sess]&&Terminal.histIdx[sess]!==0)Terminal.histIdx[sess]=hist.length;if(Terminal.histIdx[sess]>0){Terminal.histIdx[sess]--;input.value=hist[Terminal.histIdx[sess]]||'';}}
  else if(e.key==='ArrowDown'){e.preventDefault();if(Terminal.histIdx[sess]<hist.length-1){Terminal.histIdx[sess]++;input.value=hist[Terminal.histIdx[sess]]||'';}else{Terminal.histIdx[sess]=hist.length;input.value='';}}
  else if(e.key==='Tab'){e.preventDefault();const p=input.value;const m=['ls ','git ','npm ','npx ','python3 '].find(c=>c.startsWith(p));if(m)input.value=m;}
  else if(e.key==='l'&&(e.ctrlKey||e.metaKey)){e.preventDefault();termClear();}
  else if(e.key==='c'&&e.ctrlKey&&Terminal.running){e.preventDefault();termKill();}  // FIX 7: Ctrl+C kills
}
async function termShowSuggestions() {
  const input=document.getElementById('term-input'); if(!input) return;
  const q=input.value; if(q.length<2){document.getElementById('term-suggestions')?.remove();return;}
  try {
    const r=await fetch(`/api/terminal/suggestions?q=${encodeURIComponent(q)}`); const suggs=await r.json();
    let dd=document.getElementById('term-suggestions');
    if(!dd){dd=document.createElement('div');dd.id='term-suggestions';dd.style.cssText='position:fixed;background:var(--bg-2);border:1px solid var(--border-hi);border-radius:var(--radius-sm);z-index:9999;max-width:400px;box-shadow:var(--shadow-lg);font-family:monospace;font-size:12px';document.body.appendChild(dd);}
    const rect=input.getBoundingClientRect(); dd.style.bottom=(window.innerHeight-rect.top+4)+'px'; dd.style.left=rect.left+'px';
    if(!suggs.length){dd.remove();return;}
    dd.innerHTML=suggs.slice(0,6).map(s=>`<div onclick="document.getElementById('term-input').value=${JSON.stringify(s.cmd)};document.getElementById('term-suggestions')?.remove();document.getElementById('term-input').focus()" style="padding:7px 12px;cursor:pointer;display:flex;gap:10px;border-bottom:1px solid var(--border)" onmouseover="this.style.background='var(--bg-3)'" onmouseout="this.style.background=''"><span style="color:var(--accent);flex:1">${escHtml(s.cmd)}</span><span style="color:var(--text-3)">${escHtml(s.desc)}</span></div>`).join('');
    document.addEventListener('click',()=>dd?.remove(),{once:true});
  } catch(e){}
}
function termNewSession(){const id='s'+Date.now().toString(36);
  // FIX H: init history + histIdx for new session
  if(!Terminal.history[id]) Terminal.history[id]=[];
  Terminal.histIdx[id]=0;
  Terminal.active=id;const tabs=document.getElementById('term-tabs');if(tabs){const t=document.createElement('div');t.className='terminal-tab active';t.dataset.sess=id;t.textContent=id.slice(-4);t.onclick=()=>{Terminal.active=id;document.querySelectorAll('.terminal-tab').forEach(x=>x.classList.toggle('active',x.dataset.sess===id));termClear();};tabs.insertBefore(t,tabs.lastElementChild);}document.querySelectorAll('.terminal-tab').forEach(x=>x.classList.toggle('active',x.dataset.sess===id));termClear();}

// ══════════════════════════════════════════════════════════════════════════════
//  SECRETS VAULT — Encrypted key/value store with Fernet AES-256
// ══════════════════════════════════════════════════════════════════════════════
async function renderSecretsVault() {
  const pane = document.getElementById('pane-secrets');
  if (!pane) return;
  pane.innerHTML = '<div style="padding:24px;color:var(--text-2)">Loading vault…</div>';
  let data = {};
  try {
    const r = await fetch('/api/secrets/list');
    data = await r.json();
  } catch(e) {
    pane.innerHTML = `<div style="padding:24px">${pageHeader({title:'🔐 Secrets Vault',subtitle:'Failed to load vault'})}</div>`;
    return;
  }
  const items = data.items || [];
  const encrypted = data.encrypted;
  const engine = data.engine || 'Unknown';
  const warning = data.warning;

  pane.innerHTML = `
    ${pageHeader({
      title:'🔐 Secrets Vault',
      subtitle:'Encrypted credentials injected into every agent run — never in git',
      actions:[{label:'＋ Add Secret',action:'vaultShowAdd()',primary:true},{label:'🔄 Refresh',action:'renderSecretsVault()'}]
    })}
    <div class="page-content">

    <!-- Encryption status banner -->
    <div style="display:flex;align-items:center;gap:12px;padding:12px 16px;border-radius:var(--radius-lg);margin-bottom:20px;background:${encrypted?'rgba(61,186,122,.08)':'rgba(232,162,55,.08)'};border:1px solid ${encrypted?'rgba(61,186,122,.3)':'rgba(232,162,55,.3)'}">
      <span style="font-size:22px">${encrypted?'🔒':'⚠️'}</span>
      <div style="flex:1">
        <div style="font-weight:700;color:${encrypted?'var(--success)':'var(--warning)'}">
          ${encrypted?'AES-256 Fernet Encryption Active':'Encryption Not Available'}
        </div>
        <div style="font-size:11.5px;color:var(--text-2);margin-top:2px">${escHtml(engine)}</div>
        ${warning?`<div style="font-size:11px;color:var(--warning);margin-top:4px">${escHtml(warning)}</div>`:''}
      </div>
      <div style="font-size:11px;color:var(--text-3);text-align:right">
        Key file: <code style="font-size:10px">${escHtml(data.vault_path||'')}</code>
      </div>
    </div>

    <!-- Add secret form (hidden by default) -->
    <div id="vault-add-form" style="display:none;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:18px;margin-bottom:20px">
      <div style="font-weight:700;margin-bottom:14px;font-size:14px">Add / Update Secret</div>
      <div style="display:grid;grid-template-columns:1fr 2fr;gap:10px;margin-bottom:10px">
        <div>
          <label style="font-size:11px;color:var(--text-3);text-transform:uppercase;display:block;margin-bottom:4px">Key Name</label>
          <input id="vault-key-input" class="vault-input" placeholder="OPENROUTER_API_KEY" autocomplete="off" spellcheck="false"
            oninput="this.value=this.value.toUpperCase().replace(/[^A-Z0-9_]/g,'')">
        </div>
        <div>
          <label style="font-size:11px;color:var(--text-3);text-transform:uppercase;display:block;margin-bottom:4px">Value</label>
          <input id="vault-value-input" class="vault-input" type="password" placeholder="sk-or-v1-…" autocomplete="new-password">
        </div>
      </div>
      <div style="display:flex;gap:10px;align-items:center;margin-bottom:10px">
        <div style="flex:1">
          <label style="font-size:11px;color:var(--text-3);text-transform:uppercase;display:block;margin-bottom:4px">Scope</label>
          <select id="vault-scope-select" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 10px;color:var(--text-0);font-size:13px;outline:none">
            <option value="global">global — all agents</option>
            <option value="agent">agent — specific agent</option>
          </select>
        </div>
        <div style="flex:1">
          <label style="font-size:11px;color:var(--text-3);text-transform:uppercase;display:block;margin-bottom:4px">Agent (if scoped)</label>
          <input id="vault-agent-input" class="vault-input" placeholder="builder, reviewer, …">
        </div>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-primary" onclick="vaultSave()">💾 Save to Vault</button>
        <button class="btn btn-ghost" onclick="vaultHideAdd()">Cancel</button>
        <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-2);margin-left:auto;cursor:pointer">
          <input type="checkbox" id="vault-show-value" onchange="document.getElementById('vault-value-input').type=this.checked?'text':'password'">
          Show value
        </label>
      </div>
    </div>

    <!-- Secrets list -->
    <div style="font-weight:700;font-size:13px;margin-bottom:10px;color:var(--text-1)">
      ${items.length} secret${items.length!==1?'s':''} stored
    </div>

    ${items.length===0 ? `
      ${emptyState({icon:'🔐',title:'No secrets yet',body:'Add your API keys and credentials. They are encrypted at rest and injected into every agent run.',
        actions:[{label:'＋ Add First Secret',action:'vaultShowAdd()',primary:true}]})}
    ` : `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);overflow:hidden">
        <div style="display:grid;grid-template-columns:1fr 80px 80px 120px 130px;padding:8px 14px;background:var(--bg-3);font-size:10px;font-weight:700;color:var(--text-3);text-transform:uppercase;gap:8px">
          <div>Key</div><div>Scope</div><div>Length</div><div>Updated</div><div>Actions</div>
        </div>
        ${items.map(item=>`
          <div class="vault-row" style="display:grid;grid-template-columns:1fr 80px 80px 120px 130px;gap:8px">
            <div style="display:flex;align-items:center;gap:8px;min-width:0">
              <span class="vault-key">${escHtml(item.key)}</span>
              ${encrypted?'<span class="vault-enc-badge">🔒</span>':''}
            </div>
            <div><span class="vault-scope">${escHtml(item.scope||'global')}</span></div>
            <div style="color:var(--text-3);font-size:11px">${item.length||0} chars</div>
            <div style="color:var(--text-3);font-size:11px;white-space:nowrap">${escHtml((item.updated_at||'').slice(0,16))}</div>
            <div style="display:flex;gap:5px">
              <button class="btn btn-ghost btn-sm" onclick="vaultReveal('${escHtml(item.key)}')" title="Reveal value">👁</button>
              <button class="btn btn-ghost btn-sm" onclick="vaultEdit('${escHtml(item.key)}')" title="Update value">✏️</button>
              <button class="btn btn-sm" onclick="vaultDelete('${escHtml(item.key)}')" style="color:var(--danger)" title="Delete">🗑</button>
            </div>
          </div>
        `).join('')}
      </div>
    `}

    <!-- Quick-add common keys -->
    <div style="margin-top:20px">
      ${helpPanel({title:'Common API Keys',body:'Click a key name to pre-fill the form.',steps:[]})}
      <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px">
        ${['OPENROUTER_API_KEY','GITHUB_TOKEN','VERCEL_TOKEN','NETLIFY_TOKEN','SUPABASE_URL','SUPABASE_ANON_KEY','STRIPE_SECRET_KEY','ANTHROPIC_API_KEY','OPENAI_API_KEY'].map(k=>
          `<button class="btn btn-ghost btn-sm" onclick="vaultShowAdd('${k}')">${escHtml(k)}</button>`
        ).join('')}
      </div>
    </div>

    </div>`;
}

function vaultShowAdd(prefillKey='') {
  const form = document.getElementById('vault-add-form');
  if (form) {
    form.style.display = 'block';
    if (prefillKey) {
      const ki = document.getElementById('vault-key-input');
      if (ki) { ki.value = prefillKey; }
    }
    document.getElementById('vault-value-input')?.focus();
    form.scrollIntoView({behavior:'smooth',block:'nearest'});
  }
}

function vaultHideAdd() {
  const form = document.getElementById('vault-add-form');
  if (form) {
    form.style.display = 'none';
    const ki = document.getElementById('vault-key-input');
    const vi = document.getElementById('vault-value-input');
    if (ki) ki.value = '';
    if (vi) vi.value = '';
  }
}

async function vaultSave() {
  const key   = (document.getElementById('vault-key-input')?.value||'').trim().toUpperCase();
  const value = document.getElementById('vault-value-input')?.value||'';
  const scope = document.getElementById('vault-scope-select')?.value||'global';
  const agent = (document.getElementById('vault-agent-input')?.value||'').trim();
  if (!key) { showToast('Key name is required','err'); return; }
  if (!value) { showToast('Value is required','err'); return; }
  try {
    const r = await fetch('/api/secrets/set',{
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({key, value, scope, agent})
    });
    const j = await r.json();
    if (j.ok) {
      showToast(`✅ ${key} saved to vault (${j.encrypted?'AES-256':'base64'})`, 'ok', 3000);
      vaultHideAdd();
      renderSecretsVault();
    } else {
      showToast('⚠️ ' + (j.error||'Save failed'), 'err');
    }
  } catch(ex) { showToast('⚠️ ' + ex.message, 'err'); }
}

async function vaultReveal(key) {
  try {
    const r = await fetch(`/api/secrets/get?key=${encodeURIComponent(key)}&reveal=true`);
    const j = await r.json();
    if (j.ok && j.value !== undefined) {
      await gmAlert(`🔐 ${escHtml(key)}`,
        `<div style="font-family:monospace;background:var(--bg-0);padding:12px;border-radius:8px;word-break:break-all;font-size:13px;color:var(--success)">${escHtml(j.value)}</div>
         <div style="font-size:11px;color:var(--text-3);margin-top:8px">This value is encrypted at rest. Copy it now.</div>`);
    } else {
      showToast('⚠️ Could not reveal: ' + (j.error||'unknown'), 'err');
    }
  } catch(ex) { showToast('⚠️ ' + ex.message, 'err'); }
}

async function vaultEdit(key) {
  const newVal = await gmPrompt(`Update value for ${key}:`, '');
  if (newVal === null) return;
  if (!newVal.trim()) { showToast('Value cannot be empty', 'err'); return; }
  try {
    const r = await fetch('/api/secrets/set',{
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({key, value:newVal})
    });
    const j = await r.json();
    if (j.ok) {
      showToast(`✅ ${key} updated`, 'ok', 2000);
      renderSecretsVault();
    } else {
      showToast('⚠️ ' + (j.error||'Update failed'), 'err');
    }
  } catch(ex) { showToast('⚠️ ' + ex.message, 'err'); }
}

async function vaultDelete(key) {
  if (!(await gmDanger('Delete Secret', `Permanently delete "${key}" from the vault? This cannot be undone.`, 'Delete'))) return;
  try {
    const r = await fetch(`/api/secrets/${encodeURIComponent(key)}`, {method:'DELETE'});
    const j = await r.json();
    if (j.ok) {
      showToast(`🗑 ${key} deleted from vault`, 'ok', 2000);
      renderSecretsVault();
    } else {
      showToast('⚠️ ' + (j.error||'Delete failed'), 'err');
    }
  } catch(ex) { showToast('⚠️ ' + ex.message, 'err'); }
}


// ── Image Generation ─────────────────────────────────────────────
// ── Image Generation state ────────────────────────────────────────────────────
let selectedImageStyle = '';
let _imgLastPrompt     = '';

async function renderImageGen() {
  const pane = document.getElementById('pane-imagegen');
  if (!pane) return;
  pane.innerHTML = '<div style="padding:20px;color:var(--text-2)">Loading…</div>';
  try {
    const [sR, gR, mR] = await Promise.all([
      fetch('/api/imagegen/styles'),
      fetch('/api/imagegen/gallery'),
      fetch('/api/imagegen/models'),
    ]);
    if (!sR.ok) throw new Error('Styles load failed: HTTP '+sR.status);
    if (!gR.ok) throw new Error('Gallery load failed: HTTP '+gR.status);
    const styles  = await sR.json();
    const gallery = await gR.json();
    const models  = mR.ok ? await mR.json() : {models:[], api_key_set:false};

    pane.innerHTML = `
      ${pageHeader?.({title:'🎨 Image Generator', subtitle:'Generate AI images, import Figma designs, manage your asset library',
        actions:[{label:'⬆ Upload', action:'igUpload()', primary:false}]})||'<div style="padding:20px"><h2>🎨 Image Generator</h2></div>'}
      <div class="page-content">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:18px">
        <!-- Generate panel -->
        <div class="card">
          <h3 style="margin-bottom:10px">✨ Generate Image</h3>
          ${!models.api_key_set ? `<div style="background:rgba(232,162,55,.1);border:1px solid var(--warning);border-radius:8px;padding:8px 12px;font-size:11px;color:var(--warning);margin-bottom:10px">
            ⚠️ No API key — generating placeholders. Set <code>OPENROUTER_API_KEY</code> in Settings for real images.
          </div>` : ''}
          <textarea id="img-prompt" class="input" style="min-height:70px;margin-bottom:8px;font-size:13px" placeholder="A dark SaaS dashboard with charts, clean and modern…" oninput="_imgLastPrompt=this.value"></textarea>
          <div style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:8px" id="style-picker">
            ${styles.map(s=>`<button class="term-btn" id="style-${s.id}" onclick="selectImageStyle(${JSON.stringify(s.id)})" title="${escHtml(s.prompt)}">${escHtml(s.label)}</button>`).join('')}
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px">
            <select id="img-size" style="background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 10px;color:var(--text-0);font-size:12px;outline:none">
              <option value="256x256">256×256 (Fastest)</option>
              <option value="512x512">512×512 (Fast)</option>
              <option value="1024x1024" selected>1024×1024</option>
              <option value="1792x1024">1792×1024 (Wide)</option>
              <option value="1024x1792">1024×1792 (Tall)</option>
            </select>
            <input id="img-save-to" class="input" placeholder="Save as: hero.png" style="font-size:12px">
          </div>
          <div style="display:flex;gap:6px;margin-bottom:8px">
            <button onclick="generateImage()" class="btn btn-primary" style="flex:1" id="img-gen-btn">🎨 Generate</button>
            <button onclick="igEnhancePrompt()" class="btn-sm" title="AI-enhance the prompt">✨ Enhance</button>
            <button onclick="igVariations()" class="btn-sm" title="Generate 4 variations">⊞ Vary</button>
          </div>
          <div id="img-status" style="font-size:11px;color:var(--text-2);margin-top:4px;min-height:16px"></div>
          <div id="img-result" style="display:none;margin-top:10px">
            <img id="img-preview" style="max-width:100%;border-radius:var(--radius-sm);border:1px solid var(--border)">
            <div style="display:flex;gap:6px;margin-top:6px;flex-wrap:wrap">
              <button onclick="downloadImage()" class="btn btn-ghost btn-sm">⬇ Download</button>
              <button onclick="igSaveToGallery()" class="btn btn-ghost btn-sm">💾 Save to Gallery</button>
              <button onclick="insertImageIntoCode()" class="btn btn-ghost btn-sm">→ Insert</button>
            </div>
            <input type="hidden" id="img-url">
          </div>
        </div>

        <!-- Right column -->
        <div style="display:flex;flex-direction:column;gap:12px">
          <!-- Figma Import -->
          <div class="card">
            <h3 style="margin-bottom:8px">🔗 Figma Import</h3>
            <p style="font-size:11px;color:var(--text-2);margin-bottom:8px">AI reconstructs your Figma design as working code.</p>
            <input id="figma-url" class="input" placeholder="https://www.figma.com/design/…" style="margin-bottom:6px;font-size:12px">
            <div style="display:flex;gap:6px;margin-bottom:6px">
              <select id="figma-framework" style="flex:1;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 10px;color:var(--text-0);font-size:12px;outline:none">
                <option value="html">HTML + Tailwind</option>
                <option value="react">React + Tailwind</option>
                <option value="vue">Vue + Tailwind</option>
              </select>
              <button onclick="importFigma()" class="btn btn-primary btn-sm">🎯 Import</button>
            </div>
            <div id="figma-status" style="font-size:11px;color:var(--text-2);min-height:14px"></div>
          </div>

          <!-- Style Transfer -->
          <div class="card">
            <h3 style="margin-bottom:8px">🎨 Style Transfer</h3>
            <input id="st-prompt" class="input" placeholder="Describe your subject…" style="margin-bottom:6px;font-size:12px">
            <div style="display:flex;gap:6px">
              <select id="st-style" style="flex:1;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 10px;color:var(--text-0);font-size:12px;outline:none">
                ${['cinematic','anime','oil_painting','watercolor','neon_noir','minimal','fantasy','retro','sketch','pixel_art'].map(s=>`<option value="${s}">${s.replace(/_/g,' ')}</option>`).join('')}
              </select>
              <button onclick="igStyleTransfer()" class="btn btn-primary btn-sm">→ Apply</button>
            </div>
            <div id="st-status" style="font-size:11px;color:var(--text-2);margin-top:4px;min-height:14px"></div>
          </div>
        </div>
      </div>

      <!-- Asset Library -->
      <div class="card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
          <h3>🖼️ Asset Library <span style="font-size:11px;color:var(--text-3);font-weight:400">(${gallery.count} images)</span></h3>
          <div style="display:flex;gap:6px">
            <button onclick="renderImageGen()" class="btn-sm">↻ Refresh</button>
            <button onclick="igUpload()" class="btn-sm">⬆ Upload</button>
          </div>
        </div>
        ${gallery.images.length === 0
          ? '<div style="text-align:center;padding:20px;color:var(--text-3);font-size:12px">No images yet — generate or upload one above</div>'
          : `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(100px,1fr));gap:6px;max-height:220px;overflow-y:auto">
              ${gallery.images.map(img=>`
                <div style="aspect-ratio:1;border-radius:6px;overflow:hidden;border:1px solid var(--border);cursor:pointer;position:relative;group"
                     onclick="selectGalleryImage(${JSON.stringify(img.url)},${JSON.stringify(img.name)})" title="${escHtml(img.name)}">
                  <img src="${escHtml(img.url)}" style="width:100%;height:100%;object-fit:cover" loading="lazy">
                  <button onclick="event.stopPropagation();igDeleteImage(${JSON.stringify(img.name)})"
                          style="position:absolute;top:2px;right:2px;background:rgba(0,0,0,.6);border:none;border-radius:4px;color:#fff;font-size:10px;cursor:pointer;padding:1px 4px;display:none" class="ig-del-btn">🗑</button>
                </div>`).join('')}
            </div>`}
      </div>
      </div>`;

    // Add hover to show delete button
    setTimeout(() => {
      document.querySelectorAll('#pane-imagegen .ig-del-btn').forEach(btn => {
        const parent = btn.parentElement;
        parent.addEventListener('mouseenter', () => btn.style.display='block');
        parent.addEventListener('mouseleave', () => btn.style.display='none');
      });
    }, 100);

  } catch(ex) {
    pane.innerHTML = `<div style="padding:20px;color:var(--danger)">Error loading Image Gen: ${escHtml(ex?.message||String(ex))}<br>
      <button class="btn-sm" onclick="renderImageGen()" style="margin-top:8px">↻ Retry</button></div>`;
  }
}

function selectImageStyle(id) {
  selectedImageStyle = id;
  document.querySelectorAll('#style-picker .term-btn').forEach(b => {
    const active = b.id === `style-${id}`;
    b.style.borderColor = active ? 'var(--accent)' : '';
    b.style.color       = active ? 'var(--accent-hi)' : '';
  });
}

async function generateImage() {
  const prompt = document.getElementById('img-prompt')?.value?.trim();
  const size   = document.getElementById('img-size')?.value || '1024x1024';
  const saveTo = document.getElementById('img-save-to')?.value?.trim() || '';
  if (!prompt) { showToast('⚠️ Enter a prompt first'); return; }

  const btn = document.getElementById('img-gen-btn');
  const st  = document.getElementById('img-status');
  if (btn) { btn.disabled=true; btn.textContent='⏳ Generating…'; }
  if (st)  st.textContent = 'Creating image…';

  try {
    const r = await fetch('/api/imagegen/generate', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        prompt, size,
        style:   selectedImageStyle,
        save_to: saveTo ? `assets/images/${saveTo}` : '',
      })
    });
    if (!r.ok) { if(st) st.textContent='✗ HTTP '+r.status; return; }
    const j = await r.json();

    if (j.ok) {
      const res    = document.getElementById('img-result');
      const prev   = document.getElementById('img-preview');
      const urlEl  = document.getElementById('img-url');
      if (res) res.style.display = 'block';

      if (j.svg) {
        const blob = new Blob([j.svg], {type:'image/svg+xml'});
        const url  = URL.createObjectURL(blob);
        if (prev)  prev.src  = url;
        if (urlEl) urlEl.value = url;
        if (st) st.innerHTML = '⚠️ Placeholder — set <code>OPENROUTER_API_KEY</code> for real images';
      } else if (j.url || j.b64) {
        const src = j.url || `data:image/png;base64,${j.b64}`;
        if (prev)  prev.src   = src;
        if (urlEl) urlEl.value = src;
        if (st) st.textContent = `✅ ${j.saved_to ? 'Saved: '+j.saved_to : 'Generated!'}`;
        showToast('🎨 Image ready!');
      }
    } else {
      if (st) st.textContent = '✗ '+(j.error||'Generation failed');
      showToast('Image generation failed: '+(j.error||'Unknown'));
    }
  } catch(ex) {
    if (st) st.textContent = '✗ '+(ex?.message||String(ex));
    showToast('Image gen error: '+ex?.message);
  } finally {
    if (btn) { btn.disabled=false; btn.textContent='🎨 Generate'; }
  }
}

async function importFigma() {
  const url = document.getElementById('figma-url')?.value?.trim();
  const fw  = document.getElementById('figma-framework')?.value || 'html';
  if (!url) { showToast('⚠️ Enter a Figma URL'); return; }
  const st = document.getElementById('figma-status');
  if (st) st.textContent = 'Importing design…';
  try {
    const r = await fetch('/api/imagegen/figma/import', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({url, framework: fw})
    });
    if (!r.ok) { if(st) st.textContent='✗ HTTP '+r.status; return; }
    const j = await r.json();
    if (j.ok) {
      if (st) st.textContent = `✅ Imported → ${j.file}`;
      showToast(`🎯 Imported → ${j.file}`);
      studioLoadFileTree?.();
    } else {
      if (st) st.textContent = '✗ '+(j.error||'Import failed');
      showToast('Figma import failed: '+(j.error||'Unknown'));
    }
  } catch(ex) {
    if (st) st.textContent = '✗ '+ex?.message;
    showToast('Figma import error: '+ex?.message);
  }
}

async function igStyleTransfer() {
  const prompt  = document.getElementById('st-prompt')?.value?.trim();
  const styleId = document.getElementById('st-style')?.value || 'cinematic';
  if (!prompt) { showToast('⚠️ Enter a subject description'); return; }
  const st = document.getElementById('st-status');
  if (st) st.textContent = 'Applying style…';
  try {
    const r = await fetch('/api/imagegen/style-transfer', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({source_prompt: prompt, style: styleId})
    });
    if (!r.ok) { if(st) st.textContent='✗ HTTP '+r.status; return; }
    const j = await r.json();
    if (j.ok) {
      if (st) st.textContent = '✅ Style applied';
      // Display in main result area
      const prev  = document.getElementById('img-preview');
      const urlEl = document.getElementById('img-url');
      const res   = document.getElementById('img-result');
      if (j.svg) {
        const blob = new Blob([j.svg], {type:'image/svg+xml'});
        const url  = URL.createObjectURL(blob);
        if (prev)  prev.src   = url;
        if (urlEl) urlEl.value = url;
      } else if (j.url) {
        if (prev)  prev.src   = j.url;
        if (urlEl) urlEl.value = j.url;
      }
      if (res) res.style.display = 'block';
      showToast(`🎨 Style: ${styleId} applied`);
    } else {
      if (st) st.textContent = '✗ '+(j.error||'Failed');
    }
  } catch(ex) {
    if (st) st.textContent = '✗ '+ex?.message;
    showToast('Style transfer error: '+ex?.message);
  }
}

async function igEnhancePrompt() {
  const prompt = document.getElementById('img-prompt')?.value?.trim();
  if (!prompt) { showToast('⚠️ Enter a prompt to enhance'); return; }
  showToast('✨ Enhancing prompt…');
  try {
    const r = await fetch('/api/imagegen/enhance-prompt', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({prompt, style: selectedImageStyle})
    });
    if (!r.ok) { showToast('Enhance failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok && j.enhanced) {
      const inp = document.getElementById('img-prompt');
      if (inp) inp.value = j.enhanced;
      showToast('✨ Prompt enhanced!');
    } else {
      showToast('Enhance failed: '+(j.error||'Unknown'));
    }
  } catch(ex) {
    showToast('Enhance error: '+ex?.message);
  }
}

async function igVariations() {
  const prompt = document.getElementById('img-prompt')?.value?.trim();
  if (!prompt) { showToast('⚠️ Enter a prompt first'); return; }
  showToast('⊞ Generating 4 variations…');
  try {
    const r = await fetch('/api/imagegen/variations', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({prompt, count: 4, size: '512x512'})
    });
    if (!r.ok) { showToast('Variations failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (!j.ok) { showToast('Variations failed: '+(j.error||'Unknown')); return; }
    // Show variations in a modal
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    const variants = (j.variations||[]).map((v,i) => {
      const src = v.svg
        ? URL.createObjectURL(new Blob([v.svg], {type:'image/svg+xml'}))
        : (v.url || '');
      return `<div style="cursor:pointer;border:2px solid var(--border);border-radius:8px;overflow:hidden" onclick="igSelectVariation(${JSON.stringify(src)},this)">
        <img src="${escHtml(src)}" style="width:100%;height:140px;object-fit:cover">
        <div style="font-size:10px;color:var(--text-3);padding:4px 6px">${escHtml(v.modifier||'')}</div>
      </div>`;
    }).join('');
    overlay.innerHTML = `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:16px;max-width:520px;width:100%;padding:20px">
        <div style="display:flex;justify-content:space-between;margin-bottom:12px">
          <h3 style="margin:0;color:var(--text-0)">⊞ Variations (${j.count})</h3>
          <button onclick="this.closest('[style*=fixed]').remove()" style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px" id="var-grid">${variants}</div>
        <div style="display:flex;justify-content:flex-end">
          <button onclick="this.closest('[style*=fixed]').remove()" class="btn-sm">Close</button>
        </div>
      </div>`;
    overlay.onclick = e => { if(e.target===overlay) overlay.remove(); };
    document.body.appendChild(overlay);
    showToast(`✅ ${j.count} variations generated`);
  } catch(ex) {
    showToast('Variations error: '+ex?.message);
  }
}

function igSelectVariation(src, el) {
  const prev  = document.getElementById('img-preview');
  const urlEl = document.getElementById('img-url');
  const res   = document.getElementById('img-result');
  if (prev)  prev.src   = src;
  if (urlEl) urlEl.value = src;
  if (res)   res.style.display = 'block';
  document.querySelectorAll('#var-grid > div').forEach(d => d.style.borderColor = 'var(--border)');
  if (el) el.style.borderColor = 'var(--accent)';
  showToast('✅ Variation selected');
}

function downloadImage() {
  const u = document.getElementById('img-url')?.value;
  if (!u) { showToast('⚠️ No image to download'); return; }
  const prompt = document.getElementById('img-prompt')?.value?.trim() || 'image';
  const fname  = prompt.split(' ').slice(0,4).join('-').toLowerCase().replace(/[^a-z0-9-]/g,'') || 'image';
  const a = document.createElement('a');
  a.href = u;
  a.download = fname + (u.includes('svg') ? '.svg' : '.png');
  a.click();
  showToast('⬇ Downloading…');
}

async function igSaveToGallery() {
  const src = document.getElementById('img-url')?.value;
  const prompt = document.getElementById('img-prompt')?.value?.trim() || 'image';
  if (!src) { showToast('⚠️ No image to save'); return; }
  // If it's a blob URL (SVG placeholder), download and re-upload
  const fname = prompt.split(' ').slice(0,4).join('_').toLowerCase().replace(/[^a-z0-9_]/g,'') || 'image';
  try {
    const resp = await fetch(src);
    const blob = await resp.blob();
    const ext  = blob.type.includes('svg') ? '.svg' : '.png';
    const fd   = new FormData();
    fd.append('file', blob, fname + ext);
    const r = await fetch('/api/imagegen/gallery/upload', {method:'POST', body:fd});
    if (!r.ok) { showToast('Save failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) { showToast('💾 Saved to gallery: '+j.name); }
    else showToast('Save failed: '+(j.error||'Unknown'));
  } catch(ex) {
    showToast('Save error: '+ex?.message);
  }
}

async function igDeleteImage(filename) {
  const ok = await gmDanger('Delete Image', `Delete "${filename}" from gallery?`);
  if (!ok) return;
  try {
    const r = await fetch(`/api/imagegen/gallery/${encodeURIComponent(filename)}`, {method:'DELETE'});
    if (!r.ok) { showToast('Delete failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) { showToast('🗑 Deleted'); renderImageGen(); }
    else showToast('Delete failed: '+(j.error||'Unknown'));
  } catch(ex) {
    showToast('Delete error: '+ex?.message);
  }
}

function insertImageIntoCode() {
  const u = document.getElementById('img-url')?.value;
  if (!u) { showToast('⚠️ No image to insert'); return; }
  const alt = (document.getElementById('img-prompt')?.value||'AI Generated').slice(0,60);
  nav('studio');
  setTimeout(() => {
    const tag = `<img src="${u}" alt="${alt}" style="max-width:100%;border-radius:8px">`;
    if (window.Studio?.editor) {
      const sel = Studio.editor.getSelection();
      Studio.editor.executeEdits('img', [{range:sel, text:tag}]);
      showToast('→ Inserted into editor');
    } else {
      navigator.clipboard.writeText(tag).then(() => showToast('📋 Copied img tag'));
    }
  }, 500);
}

function selectGalleryImage(url, name) {
  const p = document.getElementById('img-preview');
  const u = document.getElementById('img-url');
  const r = document.getElementById('img-result');
  if (p) p.src  = url;
  if (u) u.value = url;
  if (r) r.style.display = 'block';
  showToast(`🖼️ ${name}`);
}

function igUpload() {
  const inp = document.createElement('input');
  inp.type   = 'file';
  inp.accept = 'image/*';
  inp.onchange = async () => {
    const file = inp.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    showToast('⬆ Uploading…');
    try {
      const r = await fetch('/api/imagegen/gallery/upload', {method:'POST', body:fd});
      if (!r.ok) { showToast('Upload failed: HTTP '+r.status); return; }
      const j = await r.json();
      if (j.ok) { showToast(`✅ Uploaded: ${j.name}`); renderImageGen(); }
      else showToast('Upload failed: '+(j.error||'Unknown'));
    } catch(ex) {
      showToast('Upload error: '+ex?.message);
    }
  };
  inp.click();
}


// ── Integrations + Docs + Rules ─────────────────────────────────
async function renderIntegrations() {
  const pane=document.getElementById('pane-integrations'); if(!pane)return;
  pane.innerHTML='<div style="padding:20px;color:var(--text-2)">Loading…</div>';
  try {
    const [iR,cR,dR,rR]=await Promise.all([
      fetch('/api/integrations'),
      fetch('/api/integrations/categories'),
      fetch('/api/integrations/docs/types'),
      fetch('/api/integrations/rules'),
    ]);
    if (!iR.ok||!cR.ok||!dR.ok||!rR.ok) throw new Error('Failed to load integrations data');
    const [ints,cats,docTypes,rules]=await Promise.all([iR.json(),cR.json(),dR.json(),rR.json()]);
  const catColors={payments:'#4cc98a',auth:'#5b8af8',backend:'#9d74f5',ai:'#e8a237',email:'#38c5d8',database:'#f08850',analytics:'#f06080'};
  pane.innerHTML=`
    ${pageHeader?.({title:'🔌 Integrations & Docs',subtitle:'Scaffold Stripe, Auth, Email. Generate docs. Set AI project rules.'})||'<div style="padding:20px"><h2>🔌 Integrations</h2></div>'}
    <div class="page-content">
    <div style="display:flex;gap:2px;background:var(--bg-2);border-radius:var(--radius-sm);padding:3px;margin-bottom:16px;width:fit-content">
      <button onclick="switchIntTab('ints')" id="inttab-ints" class="btn btn-primary btn-sm">🔌 Integrations</button>
      <button onclick="switchIntTab('docs')" id="inttab-docs" class="btn btn-ghost btn-sm">📖 Docs</button>
      <button onclick="switchIntTab('rules')" id="inttab-rules" class="btn btn-ghost btn-sm">📋 Rules</button>
    </div>
    <div id="int-tab-ints">
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center">
        <div style="display:flex;gap:5px;flex-wrap:wrap;flex:1">
          <button onclick="filterInts('all')" class="term-btn" id="intcat-all" style="border-color:var(--accent);color:var(--accent-hi)">All (${ints.length})</button>
          ${cats.map(c=>`<button onclick="filterInts(${JSON.stringify(c.id)})" class="term-btn" id="intcat-${c.id}">${escHtml(c.id)} (${c.count})</button>`).join('')}
        </div>
        <div style="display:flex;gap:6px;flex-shrink:0">
          <button class="btn-sm" onclick="intStripeWire()" title="Generate Stripe checkout page">💳 Stripe Wire</button>
          <button class="btn-sm" onclick="intAuthWire()" title="Generate auth login page">🔐 Auth Wire</button>
        </div>
      </div>
      <div id="ints-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:10px">
        ${ints.map(i=>`
          <div class="card card-interactive" id="int-card-${i.id}" data-category="${i.category}">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
              <span style="font-size:22px">${i.emoji}</span>
              <div><div style="font-weight:700;font-size:13px">${escHtml(i.name)}</div>
              <span style="font-size:10px;padding:2px 7px;border-radius:99px;background:${catColors[i.category]||'var(--bg-4)'}22;color:${catColors[i.category]||'var(--text-2)'}">${i.category}</span></div>
            </div>
            <p style="font-size:12px;color:var(--text-2);margin-bottom:8px;line-height:1.5;min-height:28px">${escHtml(i.description)}</p>
            <div style="display:flex;gap:5px;margin-bottom:8px;flex-wrap:wrap">${i.env_vars.slice(0,2).map(v=>`<code style="font-size:10px;background:var(--bg-0);padding:1px 5px;border-radius:3px;color:var(--text-2)">${v}</code>`).join('')}${i.env_vars.length>2?`<span style="font-size:10px;color:var(--text-3)">+${i.env_vars.length-2}</span>`:''}</div>
            <div style="display:flex;gap:5px"><button onclick="scaffoldIntegration(${JSON.stringify(i.id)})" class="btn btn-primary btn-sm" style="flex:1">⚡ Scaffold</button><a href="${escHtml(i.docs_url)}" target="_blank" class="btn btn-ghost btn-sm">Docs ↗</a></div>
            <div id="int-status-${i.id}" style="font-size:11px;color:var(--text-2);margin-top:5px;display:none"></div>
          </div>`).join('')}
      </div>
    </div>
    <div id="int-tab-docs" style="display:none">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
        <div class="card">
          <h3 style="margin-bottom:12px">Auto-generate documentation</h3>
          <div style="display:flex;flex-direction:column;gap:7px">
            ${docTypes.map(d=>`<div style="display:flex;align-items:center;justify-content:space-between;background:var(--bg-3);border-radius:var(--radius-sm);padding:9px 12px"><div><div style="font-size:13px;font-weight:600">${d.label}</div><div style="font-size:11.5px;color:var(--text-2)">${d.desc}</div></div><button onclick="generateDoc(${JSON.stringify(d.id)})" class="btn btn-primary btn-sm" id="docbtn-${d.id}">Generate</button></div>`).join('')}
          </div>
          <div id="doc-status" style="font-size:12px;color:var(--text-2);margin-top:10px"></div>
        </div>
        <div class="card"><h3 style="margin-bottom:8px">Preview</h3><div id="docs-preview" style="font-size:12px;color:var(--text-3)">Generate a doc to see it here</div></div>
      </div>
    </div>
    <div id="int-tab-rules" style="display:none">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
        <div class="card">
          <h3 style="margin-bottom:6px">📋 .agenticrules</h3>
          <p style="font-size:12px;color:var(--text-2);margin-bottom:10px">Like Cursor's .cursorrules — all AI agents read these rules before every response.</p>
          <textarea id="rules-editor" style="width:100%;min-height:280px;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;color:var(--text-0);font-size:12px;font-family:'JetBrains Mono',monospace;resize:vertical;outline:none;line-height:1.6">${escHtml(rules.content||'')}</textarea>
          <div style="display:flex;gap:8px;margin-top:8px"><button onclick="saveProjectRules()" class="btn btn-primary" style="flex:1">💾 Save</button><button onclick="loadDefaultRules()" class="btn btn-ghost btn-sm">Reset</button></div>
        </div>
        <div class="card">
          <h3 style="margin-bottom:10px">How rules work</h3>
          <p style="font-size:12.5px;color:var(--text-2);line-height:1.65;margin-bottom:12px">Rules enforce consistency across all AI agents in your workspace — tech stack, code style, behavior patterns.</p>
          <div style="font-size:12px">
            ${[['Tech Stack','- Framework: Next.js 15\n- CSS: Tailwind + shadcn'],['Code Style','- TypeScript always\n- async/await preferred'],['Behavior','- Complete code only\n- Add error handling']].map(([l,e])=>`<div style="margin-bottom:8px;background:var(--bg-3);border-radius:6px;padding:8px"><div style="font-weight:600;font-size:11px;color:var(--text-2);margin-bottom:3px">${l}</div><pre style="font-size:11px;color:var(--text-1);white-space:pre-wrap;font-family:monospace">${escHtml(e)}</pre></div>`).join('')}
          </div>
        </div>
      </div>
    </div>
    </div>`;
  } catch(e) {
    pane.innerHTML = '<div style="padding:20px;color:var(--error)">Error loading integrations: ' + escHtml(e?.message||'') + '</div>';
  }
}
let currentIntTab='ints';
function switchIntTab(tab){currentIntTab=tab;['ints','docs','rules'].forEach(t=>{const e=document.getElementById(`int-tab-${t}`);const b=document.getElementById(`inttab-${t}`);if(e)e.style.display=t===tab?'':'none';if(b)b.className=`btn ${t===tab?'btn-primary':'btn-ghost'} btn-sm`;});}
function filterInts(cat){document.querySelectorAll('#ints-grid .card').forEach(c=>{c.style.display=cat==='all'||c.dataset.category===cat?'':'none';});document.querySelectorAll('[id^="intcat-"]').forEach(b=>{b.style.borderColor=b.id===`intcat-${cat}`?'var(--accent)':'';b.style.color=b.id===`intcat-${cat}`?'var(--accent-hi)':'';})}
async function scaffoldIntegration(id){
  const btn=document.querySelector(`#int-card-${JSON.stringify(id).replace(/"/g,'')} .btn-primary`)||document.querySelector(`[onclick="scaffoldIntegration(${JSON.stringify(id)})"]`);
  const st=document.getElementById(`int-status-${id}`);
  if(btn){btn.disabled=true;btn.textContent='⏳…';}
  if(st){st.style.display='block';st.textContent='Scaffolding…';}
  try {
    const r=await fetch(`/api/integrations/${encodeURIComponent(id)}/scaffold`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({framework:'web'})});
    if(!r.ok){if(st)st.textContent='✗ HTTP '+r.status;showToast('Scaffold failed: HTTP '+r.status);return;}
    const j=await r.json();
    if(j.ok){
      if(st)st.innerHTML=`✅ ${j.files?.length||0} files · <span style="color:var(--text-3)">${escHtml((j.next_steps||[]).slice(0,1).join(''))}</span>`;
      showToast(`✅ ${escHtml(j.integration||id)} scaffolded`);
      studioLoadFileTree?.();
    } else {
      if(st)st.textContent='✗ '+(j.error||'Failed');
      showToast('Scaffold failed: '+(j.error||'Unknown error'));
    }
  } catch(ex) {
    if(st)st.textContent='✗ '+ex?.message;
    showToast('Scaffold error: '+ex?.message);
  }
  if(btn){btn.disabled=false;btn.textContent='⚡ Scaffold';}
}
async function generateDoc(type) {
  const btn  = document.getElementById(`docbtn-${type}`);
  const st   = document.getElementById('doc-status');
  const prev = document.getElementById('docs-preview');
  if (btn) { btn.disabled=true; btn.textContent='⏳…'; }
  if (st)  st.textContent = `Generating ${type}…`;
  try {
    const r = await fetch('/api/integrations/docs/generate', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({type})
    });
    if (!r.ok) { if(st) st.textContent='✗ HTTP '+r.status; return; }
    const j = await r.json();
    if (j.ok) {
      if (st)   st.textContent = `✅ ${escHtml(j.filename||type+'.md')} saved`;
      if (prev) prev.innerHTML = `
        <div style="font-weight:700;margin-bottom:6px">${escHtml(j.filename||'')}</div>
        <pre style="font-size:11px;white-space:pre-wrap;max-height:260px;overflow-y:auto;color:var(--text-1)">${escHtml((j.content||'').slice(0,1200))}</pre>`;
      showToast(`📄 ${j.filename} generated`);
      studioLoadFileTree?.();
    } else {
      if (st) st.textContent = '✗ '+(j.error||'Generation failed');
      showToast('Doc generation failed: '+(j.error||'Unknown'));
    }
  } catch(ex) {
    if (st) st.textContent = '✗ '+ex?.message;
    showToast('Doc error: '+ex?.message);
  }
  if (btn) { btn.disabled=false; btn.textContent='Generate'; }
}

async function saveProjectRules() {
  const c = document.getElementById('rules-editor')?.value || '';
  if (!c.trim()) { showToast('⚠️ Rules cannot be empty'); return; }
  try {
    const r = await fetch('/api/integrations/rules', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({content: c})
    });
    if (!r.ok) { showToast('Save failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) showToast('📋 Rules saved — agents will follow them');
    else showToast('Save failed: '+(j.error||'Unknown'));
  } catch(ex) {
    showToast('Save error: '+ex?.message);
  }
}

async function loadDefaultRules() {
  try {
    const r = await fetch('/api/integrations/rules');
    if (!r.ok) { showToast('Failed to load rules: HTTP '+r.status); return; }
    const j = await r.json();
    const e = document.getElementById('rules-editor');
    if (e && j.content) { e.value = j.content; showToast('📋 Rules loaded'); }
  } catch(ex) {
    showToast('Load error: '+ex?.message);
  }
}

async function intStripeWire() {
  const mode     = await gmPrompt('Stripe mode (payment|subscription):', 'payment');
  if (!mode) return;
  const product  = await gmPrompt('Product name:', 'Pro Plan');
  if (!product) return;
  const amtStr   = await gmPrompt('Amount in cents (e.g. 1999 for $19.99):', '1999');
  const amount   = parseInt(amtStr||'1999');
  showToast('⚡ Generating Stripe integration…');
  try {
    const r = await fetch('/api/integrations/stripe/wire', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({mode, product_name: product, amount_cents: amount, include_webhook: true})
    });
    if (!r.ok) { gmAlert('Stripe wire failed: HTTP '+r.status); return; }
    const d = await r.json();
    if (d.ok) {
      showToast(`✅ Stripe checkout generated → ${d.preview_url}`);
      studioLoadFileTree?.();
    } else {
      gmAlert('Stripe wire failed: '+(d.error||'Unknown'));
    }
  } catch(ex) {
    gmAlert('Stripe wire error: '+ex?.message);
  }
}

async function intAuthWire() {
  const provider = await gmPrompt('Auth provider (nextauth|clerk|supabase|firebase|auth0|magic):', 'clerk');
  if (!provider) return;
  showToast('⚡ Generating auth integration…');
  try {
    const r = await fetch('/api/integrations/auth/wire', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({provider, oauth_providers:['google','github']})
    });
    if (!r.ok) { gmAlert('Auth wire failed: HTTP '+r.status); return; }
    const d = await r.json();
    if (d.ok) {
      showToast(`✅ Auth page generated → ${d.preview_url}`);
      studioLoadFileTree?.();
    } else {
      gmAlert('Auth wire failed: '+(d.error||'Unknown'));
    }
  } catch(ex) {
    gmAlert('Auth wire error: '+ex?.message);
  }
}

// ── UX: First-run project type selector ─────────────────────────
(function addProjectTypeSelector() {
  setTimeout(() => {
    const el = document.getElementById('chat-empty');
    if (!el || el.dataset.projectTypes) return;
    el.dataset.projectTypes = '1';
    const types = document.createElement('div');
    types.style.cssText = 'margin-top:16px;width:100%;max-width:420px';
    types.innerHTML = `<div style="font-size:11px;color:var(--text-3);text-align:center;margin-bottom:8px;font-weight:600;letter-spacing:.05em;text-transform:uppercase">Quick start</div>
      <div style="display:flex;flex-wrap:wrap;gap:6px;justify-content:center">
        ${[['🚀','SaaS','/goal Build a SaaS landing page with hero, pricing, and CTA'],['📱','Mobile','/goal Build an Expo React Native app with navigation'],['🛒','Shop','/goal Build an e-commerce product page with cart'],['🎨','Portfolio','/goal Build a developer portfolio with projects section'],['📊','Dashboard','/goal Build an admin dashboard with charts'],['🤖','AI App','/goal Build an AI-powered app with chat interface']].map(([e,l,p])=>
          `<button onclick="setProjectType(${JSON.stringify(p)})" style="display:flex;align-items:center;gap:5px;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;padding:6px 10px;cursor:pointer;font-size:12px;color:var(--text-1);transition:var(--transition)" onmouseover="this.style.borderColor='var(--accent)'" onmouseout="this.style.borderColor='var(--border)'">${e} ${l}</button>`).join('')}
      </div>`;
    el.appendChild(types);
  }, 1500);
})();

function setProjectType(prompt) {
  const input = document.getElementById('chat-input');
  if (input) { input.value = prompt; input.focus(); const e=document.getElementById('chat-empty'); if(e)e.style.display='none'; autoResizeInput?.(input); }
}

// ── UX: Continue button on cut-off responses ─────────────────────
const _origUMB = window.updateMessageBubble;
window.updateMessageBubble = function(el, text) {
  if (_origUMB) _origUMB(el, text);
  const trimmed = (text||'').trim();
  if (trimmed.length > 300 && !trimmed.match(/[.!?`\]})>]$/) && !el.querySelector('.continue-btn')) {
    setTimeout(() => {
      const btn = document.createElement('button');
      btn.className = 'continue-btn';
      btn.textContent = '→ Continue';
      btn.style.cssText = 'display:block;margin-top:8px;font-size:11px;background:var(--accent-glow);border:1px solid var(--accent);color:var(--accent-hi);padding:4px 10px;border-radius:6px;cursor:pointer';
      btn.onclick = () => { btn.remove(); const i=document.getElementById('chat-input'); if(i){i.value='Please continue from where you left off.';sendChat?.();} };
      el?.appendChild(btn);
    }, 300);
  }
};

// ── Add Sprint 12 to command palette ────────────────────────────
if (typeof PALETTE_CMDS !== 'undefined') {
  PALETTE_CMDS.push(
    {icon:'💻', label:'Terminal',         desc:'Run shell commands',                action:()=>nav('terminal')},
    {icon:'🎨', label:'Image Generator',  desc:'Generate AI images',               action:()=>nav('imagegen')},
    {icon:'🔌', label:'Integrations',     desc:'Stripe, Auth, Email setup',        action:()=>nav('integrations')},
    {icon:'📋', label:'Project Rules',    desc:'.agenticrules — guide all agents', action:()=>{nav('integrations');setTimeout(()=>switchIntTab?.('rules'),300)}},
    {icon:'📖', label:'Generate README',  desc:'AI documentation writer',          action:()=>{nav('integrations');setTimeout(()=>{switchIntTab?.('docs');generateDoc?.('readme')},300)}},
    {icon:'💳', label:'Stripe Scaffold',  desc:'Add payments to project',          action:()=>scaffoldIntegration?.('stripe-payments')},
    {icon:'🔐', label:'Auth Scaffold',    desc:'Add authentication',               action:()=>scaffoldIntegration?.('auth-clerk')},
    {icon:'🔗', label:'Import Figma',     desc:'Figma URL → code',                action:()=>nav('imagegen')},
  );
}


// ═══════════════════════════════════════════════════════════════
//  SPRINT 13 — Prompt Library, Code Search, Smart Suggestions,
//              AI Code Reviewer, Project Memory, Share App, UX Polish
// ═══════════════════════════════════════════════════════════════

// ── Extend nav for Sprint 13 ────────────────────────────────────
(function() {
  const _s13 = window.nav || function(){};
  window.nav = function(pane) {
    _s13(pane);
    if (pane === 'prompts')    renderPrompts?.();
    if (pane === 'codesearch') renderCodeSearch?.();
    showSmartSuggestionsForPane?.(pane);
  };
})();

// ══════════════════════════════════════════════════════
//  PROMPT LIBRARY
// ══════════════════════════════════════════════════════
// ── Prompt Library state ─────────────────────────────────────────────────────
let promptsData    = [];
let promptCategory = 'all';
let promptFavOnly  = false;
let editingPromptId = null;
let _promptSort    = 'updated';

async function renderPrompts() {
  const pane = document.getElementById('pane-prompts');
  if (!pane) return;
  pane.innerHTML = '<div style="padding:20px;color:var(--text-2)">Loading…</div>';
  try {
    const [pr, cr] = await Promise.all([
      fetch('/api/prompts'),
      fetch('/api/prompts/categories'),
    ]);
    if (!pr.ok) throw new Error('Prompts API error: HTTP '+pr.status);
    if (!cr.ok) throw new Error('Categories API error: HTTP '+cr.status);
    const listData = await pr.json();
    const catData  = await cr.json();
    promptsData = listData.prompts || listData || [];  // handle both wrapped and raw
    const cats  = catData.categories || catData || [];

    pane.innerHTML = `
      ${pageHeader?.({title:'💬 Prompt Library',subtitle:'Save, organize, and reuse your best AI prompts',actions:[
        {label:'＋ New Prompt',action:'openNewPromptModal()',primary:true},
        {label:'⬇ Export',action:'exportPrompts()'},
        {label:'⬆ Import',action:'importPrompts()'},
      ]})||'<div style="padding:20px"><h2>💬 Prompt Library</h2></div>'}
      <div class="page-content">
      <div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;align-items:center">
        <input id="prompt-search" placeholder="Search prompts…" oninput="filterPrompts()"
               style="flex:1;max-width:280px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 12px;color:var(--text-0);font-size:13px;outline:none">
        <select id="prompt-sort" onchange="changePromptSort(this.value)"
                style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 10px;color:var(--text-0);font-size:12px;outline:none">
          <option value="updated">Recently updated</option>
          <option value="used">Most used</option>
          <option value="title">A-Z</option>
        </select>
        <button onclick="toggleFavs()" class="btn ${promptFavOnly?'btn-primary':'btn-ghost'} btn-sm" id="fav-btn">⭐ Favorites</button>
        <div style="display:flex;gap:4px;flex-wrap:wrap">
          <button onclick="setPromptCat('all')" class="term-btn" id="pcat-all"
                  style="${promptCategory==='all'?'border-color:var(--accent);color:var(--accent-hi)':''}">All (${promptsData.length})</button>
          ${cats.map(c=>`<button onclick="setPromptCat(${JSON.stringify(c.id)})" class="term-btn" id="pcat-${c.id}"
            style="${promptCategory===c.id?'border-color:var(--accent);color:var(--accent-hi)':''}">${escHtml(c.id)} (${c.count})</button>`).join('')}
        </div>
      </div>
      <div id="prompt-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:10px">${renderPromptCards()}</div>
      </div>
      <!-- Prompt modal -->
      <div id="prompt-modal" style="display:none;position:fixed;inset:0;background:rgba(4,6,14,.85);z-index:9000;align-items:center;justify-content:center;backdrop-filter:blur(8px)" onclick="if(event.target===this)closePromptModal()">
        <div style="background:var(--bg-2);border:1px solid var(--border-hi);border-radius:var(--radius-xl);padding:22px;width:100%;max-width:560px;box-shadow:var(--shadow-lg);max-height:90vh;overflow-y:auto">
          <h2 style="font-size:17px;font-weight:800;margin-bottom:14px" id="pm-modal-title">New Prompt</h2>
          <div class="form-group"><label class="form-label">Title *</label><input id="pm-title" class="input" placeholder="e.g. Security code review"></div>
          <div class="form-group"><label class="form-label">Prompt *</label><textarea id="pm-content" class="input" style="min-height:120px;font-family:monospace;font-size:12px" placeholder="The full prompt text… Use {placeholder} for variables."></textarea></div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px">
            <div class="form-group" style="margin:0"><label class="form-label">Category</label>
              <select id="pm-category" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 10px;color:var(--text-0);font-size:13px;outline:none">
                ${['general','build','review','testing','refactor','debug','docs','auth','seo','database','ux','quality'].map(c=>`<option value="${c}">${c}</option>`).join('')}
              </select>
            </div>
            <div class="form-group" style="margin:0"><label class="form-label">Tags</label>
              <input id="pm-tags" class="input" placeholder="security, api…">
            </div>
          </div>
          <div class="form-group"><label class="form-label">Agent (optional)</label>
            <input id="pm-agent" class="input" placeholder="e.g. brain, builder, researcher">
          </div>
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin-bottom:14px;font-size:13px">
            <input type="checkbox" id="pm-fav" style="accent-color:var(--accent)"> Mark as favorite
          </label>
          <div style="display:flex;gap:8px;justify-content:flex-end">
            <button onclick="closePromptModal()" class="btn btn-ghost">Cancel</button>
            <button onclick="savePrompt()" class="btn btn-primary" id="pm-save-btn">Save</button>
          </div>
        </div>
      </div>`;

  } catch(ex) {
    pane.innerHTML = `<div style="padding:20px;color:var(--danger)">Error loading prompts: ${escHtml(ex?.message||String(ex))}<br>
      <button class="btn-sm" onclick="renderPrompts()" style="margin-top:8px">↻ Retry</button></div>`;
  }
}

function renderPromptCards() {
  let filtered = promptsData.slice();
  if (promptCategory !== 'all') filtered = filtered.filter(p => p.category === promptCategory);
  if (promptFavOnly)             filtered = filtered.filter(p => p.is_favorite);
  const q = (document.getElementById('prompt-search')?.value || '').toLowerCase().trim();
  if (q) filtered = filtered.filter(p =>
    p.title.toLowerCase().includes(q) ||
    p.content.toLowerCase().includes(q) ||
    (p.tags||'').toLowerCase().includes(q)
  );
  if (!filtered.length) return `<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--text-3)">
    No prompts found${q?' matching "'+escHtml(q)+'"':''}.
    ${!promptsData.length?'<br><button class="btn btn-primary btn-sm" onclick="openNewPromptModal()" style="margin-top:8px">＋ Create First Prompt</button>':''}
  </div>`;

  return filtered.map(p => `
    <div class="prompt-card ${p.is_favorite?'favorite':''}" style="position:relative">
      <div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:8px">
        <div style="flex:1;min-width:0">
          <div style="font-weight:700;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${escHtml(p.title)}">${escHtml(p.title)}</div>
          <div style="display:flex;gap:4px;margin-top:3px;flex-wrap:wrap">
            <span style="font-size:10px;padding:1px 7px;border-radius:99px;background:var(--bg-3);color:var(--text-2)">${escHtml(p.category||'general')}</span>
            ${(p.tags||'').split(',').filter(t=>t.trim()).slice(0,2).map(t=>`<span style="font-size:10px;padding:1px 7px;border-radius:99px;background:var(--bg-3);color:var(--text-3)">${escHtml(t.trim())}</span>`).join('')}
            ${p.agent_id?`<span style="font-size:10px;padding:1px 7px;border-radius:99px;background:var(--bg-3);color:var(--accent)">🤖 ${escHtml(p.agent_id)}</span>`:''}
          </div>
        </div>
        ${p.is_favorite?'<span style="font-size:12px;flex-shrink:0">⭐</span>':''}
        <span style="font-size:10.5px;color:var(--text-3);flex-shrink:0">${p.use_count||0}×</span>
      </div>
      <p style="font-size:12px;color:var(--text-2);line-height:1.5;margin-bottom:10px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical">${escHtml(p.content)}</p>
      <div style="display:flex;gap:5px;flex-wrap:wrap">
        <button onclick="usePrompt(${JSON.stringify(p.id)},${JSON.stringify(p.content)})" class="btn btn-primary btn-sm" style="flex:1" title="Load in chat">→ Use</button>
        <button onclick="editPrompt(${JSON.stringify(p.id)})" class="btn btn-ghost btn-sm" title="Edit">✏️</button>
        <button onclick="duplicatePrompt(${JSON.stringify(p.id)})" class="btn btn-ghost btn-sm" title="Duplicate">⧉</button>
        <button onclick="toggleFavorite(${JSON.stringify(p.id)},${p.is_favorite?1:0})" class="btn btn-ghost btn-sm" title="${p.is_favorite?'Remove from favorites':'Add to favorites'}">${p.is_favorite?'⭐':'☆'}</button>
        <button onclick="deletePrompt(${JSON.stringify(p.id)})" style="background:none;border:none;color:var(--danger);cursor:pointer;font-size:13px;padding:3px 6px" title="Delete">🗑</button>
      </div>
    </div>`).join('');
}

function filterPrompts() {
  const g = document.getElementById('prompt-grid');
  if (g) g.innerHTML = renderPromptCards();
}

function setPromptCat(cat) {
  promptCategory = cat;
  document.querySelectorAll('[id^="pcat-"]').forEach(b => {
    const active = b.id === 'pcat-'+cat;
    b.style.borderColor = active ? 'var(--accent)' : '';
    b.style.color       = active ? 'var(--accent-hi)' : '';
  });
  filterPrompts();
}

function toggleFavs() {
  promptFavOnly = !promptFavOnly;
  const b = document.getElementById('fav-btn');
  if (b) b.className = `btn ${promptFavOnly?'btn-primary':'btn-ghost'} btn-sm`;
  filterPrompts();
}

function changePromptSort(sort) {
  _promptSort = sort;
  // Re-sort promptsData locally
  const sortFns = {
    updated: (a,b) => (b.updated_at||'').localeCompare(a.updated_at||''),
    used:    (a,b) => (b.use_count||0) - (a.use_count||0),
    title:   (a,b) => (a.title||'').localeCompare(b.title||''),
  };
  promptsData.sort(sortFns[sort] || sortFns.updated);
  filterPrompts();
}

function openNewPromptModal(prefill) {
  prefill = prefill || '';
  editingPromptId = null;
  const modalTitle = document.getElementById('pm-modal-title');
  const titleEl    = document.getElementById('pm-title');
  const contentEl  = document.getElementById('pm-content');
  const catEl      = document.getElementById('pm-category');
  const tagsEl     = document.getElementById('pm-tags');
  const agentEl    = document.getElementById('pm-agent');
  const favEl      = document.getElementById('pm-fav');
  const saveBtnEl  = document.getElementById('pm-save-btn');
  if (modalTitle) modalTitle.textContent = 'New Prompt';
  if (titleEl)    titleEl.value    = '';
  if (contentEl)  contentEl.value  = prefill;
  if (catEl)      catEl.value      = 'general';
  if (tagsEl)     tagsEl.value     = '';
  if (agentEl)    agentEl.value    = '';
  if (favEl)      favEl.checked    = false;
  if (saveBtnEl)  saveBtnEl.textContent = 'Save';
  const modal = document.getElementById('prompt-modal');
  if (modal) modal.style.display = 'flex';
  setTimeout(() => titleEl?.focus(), 50);
}

function closePromptModal() {
  const modal = document.getElementById('prompt-modal');
  if (modal) modal.style.display = 'none';
  editingPromptId = null;
}

async function savePrompt() {
  const title    = document.getElementById('pm-title')?.value?.trim();
  const content  = document.getElementById('pm-content')?.value?.trim();
  if (!title || !content) { showToast('⚠️ Title and content are required'); return; }

  const payload = {
    title,
    content,
    category:    document.getElementById('pm-category')?.value  || 'general',
    tags:        document.getElementById('pm-tags')?.value       || '',
    agent_id:    document.getElementById('pm-agent')?.value      || '',
    is_favorite: document.getElementById('pm-fav')?.checked ? 1 : 0,
  };

  const url    = editingPromptId ? `/api/prompts/${editingPromptId}` : '/api/prompts';
  const method = editingPromptId ? 'PATCH' : 'POST';

  try {
    const r = await fetch(url, {method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (!r.ok) { showToast('Save failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) {
      showToast(editingPromptId ? '✅ Prompt updated' : '✅ Prompt saved');
      closePromptModal();
      renderPrompts();
    } else {
      showToast('Save failed: '+(j.error||'Unknown error'));
    }
  } catch(ex) {
    showToast('Save error: '+ex?.message);
  }
}

function editPrompt(pid) {
  const p = promptsData.find(x => x.id === pid);
  if (!p) { showToast('Prompt not found'); return; }
  editingPromptId = pid;
  const modalTitle = document.getElementById('pm-modal-title');
  const titleEl    = document.getElementById('pm-title');
  const contentEl  = document.getElementById('pm-content');
  const catEl      = document.getElementById('pm-category');
  const tagsEl     = document.getElementById('pm-tags');
  const agentEl    = document.getElementById('pm-agent');
  const favEl      = document.getElementById('pm-fav');
  const saveBtnEl  = document.getElementById('pm-save-btn');
  if (modalTitle) modalTitle.textContent = 'Edit Prompt';
  if (titleEl)    titleEl.value    = p.title    || '';
  if (contentEl)  contentEl.value  = p.content  || '';
  if (catEl)      catEl.value      = p.category || 'general';
  if (tagsEl)     tagsEl.value     = p.tags     || '';
  if (agentEl)    agentEl.value    = p.agent_id || '';
  if (favEl)      favEl.checked    = !!p.is_favorite;
  if (saveBtnEl)  saveBtnEl.textContent = 'Update';
  const modal = document.getElementById('prompt-modal');
  if (modal) modal.style.display = 'flex';
  setTimeout(() => titleEl?.focus(), 50);
}

async function deletePrompt(pid) {
  const p = promptsData.find(x => x.id === pid);
  const name = p?.title || pid;
  if (!(await gmDanger('Delete Prompt', `Remove "${name}" from your library?`))) return;
  try {
    const r = await fetch(`/api/prompts/${encodeURIComponent(pid)}`, {method:'DELETE'});
    if (!r.ok) { showToast('Delete failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) {
      promptsData = promptsData.filter(p => p.id !== pid);
      showToast('🗑 Prompt deleted');
      filterPrompts();
    } else {
      showToast('Delete failed: '+(j.error||'Unknown'));
    }
  } catch(ex) {
    showToast('Delete error: '+ex?.message);
  }
}

async function toggleFavorite(pid, current) {
  try {
    const r = await fetch(`/api/prompts/${encodeURIComponent(pid)}`, {
      method:'PATCH', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({is_favorite: current ? 0 : 1})
    });
    if (!r.ok) { showToast('Favorite toggle failed: HTTP '+r.status); return; }
    const d = await r.json();
    if (d.ok) {
      const p = promptsData.find(x => x.id === pid);
      if (p) p.is_favorite = current ? 0 : 1;
      filterPrompts();
      showToast(current ? '☆ Removed from favorites' : '⭐ Added to favorites');
    } else {
      showToast('Toggle failed: '+(d.error||'Unknown'));
    }
  } catch(ex) {
    showToast('Favorite error: '+ex?.message);
  }
}

async function usePrompt(pid, content) {
  try {
    fetch(`/api/prompts/${encodeURIComponent(pid)}/use`, {method:'POST'}).catch(()=>{});
    // Update local use_count
    const p = promptsData.find(x => x.id === pid);
    if (p) p.use_count = (p.use_count||0) + 1;
  } catch(e) {}
  nav('chat');
  setTimeout(() => {
    const inp = document.getElementById('chat-input');
    if (inp) {
      inp.value = content;
      inp.focus();
      if (typeof autoResizeInput === 'function') autoResizeInput(inp);
      const emptyEl = document.getElementById('chat-empty');
      if (emptyEl) emptyEl.style.display = 'none';
    }
  }, 200);
  showToast('✅ Prompt loaded in chat');
}

async function duplicatePrompt(pid) {
  try {
    const r = await fetch(`/api/prompts/${encodeURIComponent(pid)}/duplicate`, {method:'POST'});
    if (!r.ok) { showToast('Duplicate failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) {
      showToast('⧉ Prompt duplicated: '+escHtml(j.title||''));
      renderPrompts();
    } else {
      showToast('Duplicate failed: '+(j.error||'Unknown'));
    }
  } catch(ex) {
    showToast('Duplicate error: '+ex?.message);
  }
}

async function exportPrompts() {
  try {
    const r = await fetch('/api/prompts/export');
    if (!r.ok) { showToast('Export failed: HTTP '+r.status); return; }
    const d = await r.json();
    const blob = new Blob([JSON.stringify(d.prompts, null, 2)], {type:'application/json'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `prompts-export-${new Date().toISOString().slice(0,10)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
    showToast(`✅ Exported ${d.count} prompts`);
  } catch(ex) {
    showToast('Export error: '+ex?.message);
  }
}

async function importPrompts() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.json';
  input.onchange = async () => {
    const file = input.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const prompts = Array.isArray(data) ? data : (data.prompts || []);
      if (!prompts.length) { showToast('No prompts found in file'); return; }
      const r = await fetch('/api/prompts/import', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({prompts})
      });
      if (!r.ok) { showToast('Import failed: HTTP '+r.status); return; }
      const j = await r.json();
      if (j.ok) {
        showToast(`✅ Imported ${j.imported} prompts (${j.skipped} skipped)`);
        renderPrompts();
      } else {
        showToast('Import failed: '+(j.error||'Unknown'));
      }
    } catch(ex) {
      showToast('Import parse error: '+ex?.message);
    }
  };
  input.click();
}

// Save current chat input as a prompt
window.saveCurrentAsPrompt = async function() {
  const content = document.getElementById('chat-input')?.value?.trim();
  if (!content) { showToast('⚠️ Type a prompt first'); return; }
  const title = await gmPrompt('Save Prompt', 'Name for this prompt', content.slice(0,50)+(content.length>50?'…':''));
  if (!title || !title.trim()) return;
  try {
    const r = await fetch('/api/prompts', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({title:title.trim(), content, category:'general'})
    });
    if (!r.ok) { showToast('Save failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) showToast('✅ Saved to Prompt Library');
    else showToast('Save failed: '+(j.error||'Unknown'));
  } catch(ex) {
    showToast('Save error: '+ex?.message);
  }
};

(function addSavePromptBtn() {
  const t = document.querySelector('.chat-tools');
  if (!t || document.getElementById('save-prompt-btn')) { setTimeout(addSavePromptBtn, 700); return; }
  const b = document.createElement('button');
  b.id        = 'save-prompt-btn';
  b.className = 'chat-tool';
  b.title     = 'Save current input as a reusable prompt';
  b.textContent = '💾 Save Prompt';
  b.onclick   = saveCurrentAsPrompt;
  t.appendChild(b);
})();

// ══════════════════════════════════════════════════════
//  CODE SEARCH
// ══════════════════════════════════════════════════════
async function renderCodeSearch(){
  const pane=document.getElementById('pane-codesearch');if(!pane)return;
  pane.innerHTML=`
    ${pageHeader?.({title:'🔍 Code Search',subtitle:'Instant search across all project files'})||'<div style="padding:20px"><h2>🔍 Code Search</h2></div>'}
    <div class="page-content">
    <div style="display:flex;gap:8px;margin-bottom:14px">
      <input id="cs-input" class="input" placeholder="Search code, functions, variables, text…" style="flex:1;font-size:14px;height:42px" onkeydown="if(event.key==='Enter')runCodeSearch()" autocomplete="off">
      <button onclick="runCodeSearch()" class="btn btn-primary" id="cs-btn" style="height:42px">🔍 Search</button>
    </div>
    <div id="cs-results" style="color:var(--text-3);text-align:center;padding:40px;font-size:13px">Type to search across all project files</div>
    </div>`;
  document.getElementById('cs-input')?.focus();
}

async function runCodeSearch(){
  const q=document.getElementById('cs-input')?.value?.trim();if(!q)return;
  const btn=document.getElementById('cs-btn');const res=document.getElementById('cs-results');
  btn.disabled=true;btn.textContent='⏳…';res.innerHTML='<div style="color:var(--text-2);padding:12px">Searching…</div>';
  try {
    const r=await fetch(`/api/project/search?q=${encodeURIComponent(q)}&limit=30&context_lines=2`);
    const j=await r.json();const results=j.results||[];
    if(!results.length){res.innerHTML=`<div style="text-align:center;padding:40px;color:var(--text-3)"><div style="font-size:24px;margin-bottom:8px">🔍</div><div>No results for "${escHtml(q)}"</div></div>`;return;}
    const byFile={};results.forEach(r=>{if(!byFile[r.file])byFile[r.file]=[];byFile[r.file].push(r);});
    res.innerHTML=`<div style="margin-bottom:12px;font-size:13px;color:var(--text-1);font-weight:600">${j.total} match${j.total!==1?'es':''} in ${Object.keys(byFile).length} file${Object.keys(byFile).length!==1?'s':''}${j.summary?` — ${escHtml(j.summary)}`:''}
    </div>${Object.entries(byFile).map(([file,hits])=>`
      <div style="margin-bottom:10px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);overflow:hidden">
        <div style="padding:7px 12px;background:var(--bg-3);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;cursor:pointer" onclick="studioOpenFile?.('${escHtml(file)}');nav('studio')">
          <span style="font-size:11.5px;font-family:monospace;color:var(--accent);font-weight:600">${escHtml(file)}</span>
          <span style="font-size:10.5px;color:var(--text-3);margin-left:auto">${hits.length} match${hits.length!==1?'es':''} · open →</span>
        </div>
        ${hits.map(hit=>{
          // FIX 10: render surrounding context lines, not just the match line
          const ctx = hit.context || [hit.match];
          const matchIdx = ctx.indexOf(hit.match);
          const ctxHtml = ctx.map((l,ci)=>{
            const isMatch = ci === matchIdx || l === hit.match;
            return `<div style="display:flex;gap:6px;${isMatch?'background:rgba(91,138,248,.08);':''}padding:1px 0">
              <span style="color:var(--text-3);font-size:10px;min-width:32px;text-align:right;user-select:none">${(hit.line - matchIdx + ci)}</span>
              <span style="font-family:monospace;font-size:12px;color:${isMatch?'var(--text-0)':'var(--text-3)'};white-space:pre-wrap">${escHtml(l)}</span>
            </div>`;
          }).join('');
          return `<div style="padding:6px 12px;border-bottom:1px solid var(--border);cursor:pointer;transition:var(--transition)" onclick="studioOpenFile?.('${escHtml(file)}');nav('studio')" onmouseover="this.style.background='var(--bg-3)'" onmouseout="this.style.background=''">
            ${ctxHtml}
          </div>`;
        }).join('')}
      </div>`).join('')}`;
  }catch(e){res.innerHTML=`<div style="color:var(--danger);padding:12px">Error: ${e.message}</div>`;}
  finally{btn.disabled=false;btn.textContent='🔍 Search';}
}
window.renderCodeSearch = renderCodeSearch;
window.runCodeSearch = runCodeSearch;

// ══════════════════════════════════════════════════════
//  SMART NEXT-ACTION SUGGESTIONS BAR
// ══════════════════════════════════════════════════════
function ensureSuggestionsBar(){
  if(document.getElementById('smart-suggestions'))return;
  const bar=document.createElement('div');
  bar.id='smart-suggestions';
  bar.style.cssText='position:relative;flex-shrink:0;background:var(--bg-1);border-top:1px solid var(--border);padding:6px 16px;z-index:10;display:none;flex-direction:column;gap:4px;box-shadow:0 -2px 8px rgba(0,0,0,0.1)';
  bar.innerHTML='<div class="suggestion-chips" id="suggestion-chips"><span class="suggestion-label">💡 Next:</span></div>';
  const content = document.getElementById('content');
  const statusbar = document.getElementById('statusbar');
  if (content && statusbar && content.contains(statusbar)) {
    content.insertBefore(bar, statusbar);
  } else if (content) {
    content.appendChild(bar);
  } else {
    document.getElementById('shell')?.appendChild(bar);
  }
}

function showSmartSuggestionsForPane(pane){
  try { if (localStorage.getItem('agentic_os_disable_hints') === 'true') return; } catch(e) {}
  ensureSuggestionsBar();
  const bar=document.getElementById('smart-suggestions');if(!bar)return;
  bar.style.display='flex';
  updateSuggestionChips(getDefaultSuggestions(pane));
}

function updateSuggestionChips(suggestions){
  const chips=document.getElementById('suggestion-chips');if(!chips||!suggestions?.length)return;
  chips.innerHTML=`<span class="suggestion-label">💡 Next:</span>`+
    suggestions.map(s=>`<button class="suggestion-chip btn-3d" onclick="${s.action||''}" title="${escHtml(s.reason||'')}">${s.icon||'⚡'} ${escHtml(s.label)}</button>`).join('')+
    `<div style="margin-left:auto;display:flex;align-items:center;gap:6px">
       <button onclick="localStorage.setItem('agentic_os_disable_hints','true');document.getElementById('smart-suggestions').style.display='none';toast('✕ Next hints turned off.')" class="btn-sm btn-ghost" style="padding:2px 8px;font-size:10px">🔕 Turn off hints</button>
       <button onclick="document.getElementById('smart-suggestions').style.display='none'" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:16px;padding:0 4px">×</button>
     </div>`;
}

function getDefaultSuggestions(pane){
  const map={
    chat:[{icon:'💬',label:'Save Prompt',action:'saveCurrentAsPrompt?.()',reason:'Reuse later'},{icon:'🌀',label:'Run Swarm',action:"nav('swarm')",reason:'Multiple AI opinions'},{icon:'🎬',label:'Build in Studio',action:"nav('studio')",reason:'Create it'}],
    studio:[{icon:'🧪',label:'Run Tests',action:"runE2EFull?.('web')",reason:'Verify changes'},{icon:'🐙',label:'Push to GitHub',action:'showGHPush?.()',reason:'Back up code'},{icon:'🚀',label:'Deploy',action:"nav('deploy')",reason:'Go live'}],
    kanban:[{icon:'🏛️',label:'Run Pipeline',action:"nav('pipeline')",reason:'Automate'},{icon:'📊',label:'Analytics',action:"nav('dashboard')",reason:'Track progress'},{icon:'♾️',label:'Create Loop',action:"nav('loops')",reason:'Schedule'}],
    deploy:[{icon:'🌐',label:'Share App',action:'shareProject?.()',reason:'Get public URL'},{icon:'🐙',label:'GitHub Pages',action:'showGHPages?.()',reason:'Free hosting'},{icon:'📊',label:'Monitor',action:"nav('dashboard')",reason:'Track usage'}],
    templates:[{icon:'🎬',label:'Open Studio',action:"nav('studio')",reason:'Customize'},{icon:'💳',label:'Add Stripe',action:"scaffoldIntegration?.('stripe-payments')",reason:'Monetize'},{icon:'🔐',label:'Add Auth',action:"scaffoldIntegration?.('auth-clerk')",reason:'User accounts'}],
    github:[{icon:'🚀',label:'Deploy Now',action:"nav('deploy')",reason:'Go live'},{icon:'📋',label:'Create PR',action:'showGHPR?.()',reason:'Code review'},{icon:'🌐',label:'GitHub Pages',action:'showGHPages?.()',reason:'Free hosting'}],
  };
  return map[pane]||[{icon:'💬',label:'Chat with AI',action:"nav('chat')",reason:'Get help'},{icon:'🎬',label:'Studio',action:"nav('studio')",reason:'Build'},{icon:'📊',label:'Dashboard',action:"nav('dashboard')",reason:'Analytics'}];
}

setTimeout(()=>showSmartSuggestionsForPane?.('chat'),3000);

// ══════════════════════════════════════════════════════
//  AI CODE REVIEWER
// ══════════════════════════════════════════════════════
let reviewOpen=false;

async function reviewCurrentFile(){
  const filepath=Studio?.currentFile||S?.currentFile;
  if(!filepath){toast('Open a file in Studio first','warn');return;}
  let overlay=document.getElementById('review-overlay');
  if(!overlay){
    overlay=document.createElement('div');overlay.id='review-overlay';overlay.className='review-overlay';
    overlay.innerHTML=`<div style="padding:10px 12px;border-bottom:1px solid var(--border);background:var(--bg-2);display:flex;align-items:center;gap:8px;flex-shrink:0">
      <span style="font-weight:700;font-size:13px">🔍 Code Review</span>
      <span id="review-score" style="font-size:11px;color:var(--text-2)"></span>
      <div style="margin-left:auto;display:flex;gap:5px">
        <button onclick="reviewCurrentFile()" class="btn btn-ghost btn-sm">⟳</button>
        <button onclick="toggleReviewOverlay()" style="background:none;border:none;color:var(--text-2);cursor:pointer;font-size:16px">×</button>
      </div>
    </div>
    <div id="review-summary" style="padding:9px 12px;font-size:12.5px;color:var(--text-2);border-bottom:1px solid var(--border);flex-shrink:0"></div>
    <div id="review-issues" style="flex:1;overflow-y:auto;padding:4px"></div>`;
    document.getElementById('shell')?.appendChild(overlay);
  }
  overlay.classList.add('open');reviewOpen=true;
  const scoreEl=document.getElementById('review-score');const sumEl=document.getElementById('review-summary');const issuesEl=document.getElementById('review-issues');
  if(scoreEl)scoreEl.textContent='Analyzing…';
  if(sumEl)sumEl.innerHTML='<div style="color:var(--text-2)">AI reviewing…</div>';
  toast(`🔍 Reviewing ${filepath}…`,'ok',2000);
  try {
    const r=await fetch('/api/project/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filepath})});
    const j=await r.json();
    const sc=j.score||75;const sc_color=sc>=80?'var(--success)':sc>=60?'var(--warning)':'var(--danger)';
    if(scoreEl)scoreEl.innerHTML=`<span style="color:${sc_color};font-weight:700">${sc}/100</span>`;
    if(sumEl)sumEl.innerHTML=`<div style="margin-bottom:5px">${escHtml(j.summary||'Review complete')}</div>${(j.highlights||[]).slice(0,2).map(h=>`<div style="color:var(--success);font-size:11.5px">✓ ${escHtml(h)}</div>`).join('')}`;
    const issues=j.issues||[];
    if(issuesEl)issuesEl.innerHTML=!issues.length?'<div style="text-align:center;padding:20px;color:var(--success)">✅ No issues!</div>':issues.map(i=>`
      <div class="review-issue">
        <span class="review-issue-sev ${i.severity||'info'}"></span>
        <div style="flex:1;min-width:0">
          <div style="font-size:12px;font-weight:600">Line ${i.line||'?'} — ${escHtml(i.message||'')}</div>
          ${i.fix?`<div style="font-size:11.5px;color:var(--text-2)">Fix: ${escHtml(i.fix)}</div>`:''}
        </div>
      </div>`).join('');
    toast(`✅ Review: ${sc}/100 — ${issues.length} issue${issues.length!==1?'s':''}`,'ok',3000);
  }catch(e){if(sumEl)sumEl.innerHTML=`<div style="color:var(--danger)">Error: ${e.message}</div>`;}
}

function toggleReviewOverlay(){
  reviewOpen=!reviewOpen;
  document.getElementById('review-overlay')?.classList.toggle('open',reviewOpen);
}

(function addReviewBtn(){
  const t=document.querySelector('.studio-toolbar');if(!t||document.getElementById('review-btn')){setTimeout(addReviewBtn,900);return;}
  const b=document.createElement('button');b.id='review-btn';b.className='btn btn-ghost btn-sm';b.title='AI code review (⌘⇧R)';b.textContent='🔍 Review';b.onclick=reviewCurrentFile;t.appendChild(b);
})();

// ══════════════════════════════════════════════════════
//  SHARE APP
// ══════════════════════════════════════════════════════
async function shareProject(){
  toast('🌐 Getting share URL…','ok',2000);
  const r=await fetch('/api/project/share',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target:'web'})});
  const j=await r.json();
  if(j.ok){
    const url=j.public_url||j.lan_url;
    await gmAlert('🌐 Share Your App',`
      <div style="margin-bottom:10px;font-size:13px">${j.is_public?'<span style="color:var(--success)">✅ Public URL (anyone can access)</span>':'<span style="color:var(--warning)">⚠️ LAN only (same Wi-Fi)</span>'}</div>
      <code style="display:block;background:var(--bg-0);padding:10px;border-radius:6px;font-size:12px;word-break:break-all;margin-bottom:10px">${url}</code>
      ${j.qr_url?`<div style="text-align:center;margin-bottom:10px"><img src="${j.qr_url}" style="width:130px;height:130px;border-radius:8px"></div>`:''}
      <div style="font-size:12px;color:var(--text-2)">${j.tip}</div>`);
    navigator.clipboard.writeText(url).then(()=>toast('📋 URL copied!','ok',1500));
  }else toast('Share failed','err');
}

(function addShareBtn(){
  const a=document.getElementById('topbar-actions');if(!a||document.getElementById('share-btn')){setTimeout(addShareBtn,700);return;}
  const b=document.createElement('button');
  b.id='share-btn';
  b.className='btn-3d btn-sm';
  b.title='Share App URL (⌘U)';
  b.innerHTML='<span style="font-size:14px">📤</span> <span class="btn-text" style="font-size:12px;font-weight:700">Share App</span>';
  b.style.cssText='background:rgba(168,85,247,0.15);border:1px solid rgba(168,85,247,0.4);color:#d8b4fe;padding:5px 12px;border-radius:8px;cursor:pointer;display:flex;align-items:center;gap:5px';
  b.onclick=shareProject;
  a.insertBefore(b,a.firstChild);
})();

// ══════════════════════════════════════════════════════
//  UX POLISH — Keyboard shortcuts + improvements
// ══════════════════════════════════════════════════════
document.addEventListener('keydown',e=>{
  if((e.metaKey||e.ctrlKey)&&e.key==='p'&&!e.shiftKey){e.preventDefault();nav('codesearch');setTimeout(()=>document.getElementById('cs-input')?.focus(),200);}
  if((e.metaKey||e.ctrlKey)&&e.key==='r'&&e.shiftKey){e.preventDefault();reviewCurrentFile();}
  if((e.metaKey||e.ctrlKey)&&e.key==='u'){e.preventDefault();shareProject();}
});

// Auto-focus chat on startup
setTimeout(()=>{if(document.querySelector('.pane.active')?.id==='pane-chat')document.getElementById('chat-input')?.focus();},1200);

// Add to command palette
if(typeof PALETTE_CMDS!=='undefined'){
  PALETTE_CMDS.unshift(
    {icon:'💬',label:'Prompt Library',desc:'Save & reuse AI prompts (⌘L)',action:()=>nav('prompts')},
    {icon:'🔍',label:'Search Code',desc:'Find anything in project (⌘P)',action:()=>nav('codesearch')},
    {icon:'🌐',label:'Share App',desc:'Get public URL (⌘U)',action:()=>shareProject()},
    {icon:'🔍',label:'Review Code',desc:'AI code review (⌘⇧R)',action:()=>reviewCurrentFile()},
  );
}

// ── Cost tracking polling ─────────────────────────────────────────
setInterval(updateCostBar, 30000);

window.gmAlert = gmAlert;
window.gmConfirm = gmConfirm;
window.escHtml = escHtml;

// ── Loop count badge updater ──────────────────────────────────────
setInterval(async () => {
  try {
    const r = await fetch('/api/loops/status');
    const j = await r.json();
    const badge = document.getElementById('loop-count');
    if (badge) badge.textContent = j.jobs || 0;
  } catch(e) {}
}, 15000);
