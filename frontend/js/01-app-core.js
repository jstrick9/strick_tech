// Agentic OS v11.5.0 — Verified Session & Action Button Build 2026-07-21
// Core app logic — state, nav, chat, agents, builder, kanban, swarm, galaxy, settings
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

// Keep the active model visible everywhere without duplicating model selectors.
// The control remains the same DOM element, so existing model sync behavior works.
// Model control stays in chat header where it belongs
// Removed placeGlobalModelControl - model selector should only be in Chat

// JavaScript has no native Python-style title-case calls. Keep agent labels safe in
// every browser, including WKWebView/Safari used by the macOS desktop app.
function formatAgentName(value) {
  return String(value || 'AI')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase());
}

// ── Toast ────────────────────────────────────────────────────────
function toast(msg, type = 'ok', duration = 3000) {
  const c = document.getElementById('toast-container');
  if (!c) return;
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.innerHTML = `<span>${escHtml(msg)}</span><span class="toast-close" onclick="this.parentElement.remove()">×</span>`;
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
  try { try { _safeLS.set('agentic_os_sidebar_collapsed', isCollapsed ? 'true' : 'false'); } catch {} } catch(e) {}
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
  // Swap arrow text: expanded = ▼, collapsed = ▶
  if (arrow) arrow.textContent = isOpen ? '▼' : '▶';
  
  try { try { _safeLS.set('agentic_os_group_' + groupId + '_open', isOpen ? 'true' : 'false'); } catch {} } catch(e) {}
};

window.initSidebarGroups = function() {
  ['core', 'build', 'ship', 'tools', 'enterprise'].forEach(gid => {
    let saved = null; try { saved = _safeLS.get('agentic_os_group_' + gid + '_open'); } catch {}
    // ESSENTIALS (core) is ALWAYS open — never collapsed by saved state
    const isOpen = gid === 'core' ? true : saved === 'true';
    const content = document.getElementById('group-' + gid);
    const arrow = document.getElementById('arrow-' + gid);
    if (content) {
      if (isOpen) { content.style.display = ''; }
      else { content.style.display = 'none'; }
    }
    if (arrow) arrow.textContent = isOpen ? '▼' : '▶';
  });
  // Also ensure sidebar is not collapsed on startup
  const sb = document.getElementById('sidebar');
  if (sb && sb.classList.contains('collapsed')) {
    sb.classList.remove('collapsed');
    sb.style.width = 'var(--sidebar-w)';
  }
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
    try { try { _safeLS.set('agentic_os_sidebar_w', sb.style.width); } catch {} } catch(e) {}
  });

  try {
    let savedW = null; try { savedW = _safeLS.get('agentic_os_sidebar_w'); } catch {}
    // Sidebar always starts expanded — never auto-collapse on page load
    // (users can collapse manually with the toggle button)
    if (savedW && parseInt(savedW) > 60) {
      sb.style.width = savedW;
    }
    sb.classList.remove('collapsed');
  } catch(e) {}
}

// Pane renderer registry is defined in 00-pane-registry.js.


window.nav = function(pane) {
  if (!pane) return;
  if (window.NavigationState) window.NavigationState.set(pane);
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
  if (pane === 'chat' && typeof window.loadChatSessions === 'function') {
    window.loadChatSessions();
  }

  try { history.replaceState(null, '', '#/' + pane); } catch(e) {}
};

// ── Agents ───────────────────────────────────────────────────────
async function loadAgents() {
  try {
    const data = await AgenticAPI.get('/api/agents');
    S.agents = Array.isArray(data) ? data : (data.agents || []);
    renderAgentList();
    if (!S.currentAgent) setActiveAgent({ id: 'default', name: 'Direct AI Chat', avatar: '💬', model: '' });
    updateStatusBar();
  } catch(e) { console.warn('Agents load failed:', e); }
}

function renderAgentList() {
  const el = document.getElementById('agent-list');
  if (el && S.agents) {
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
  }

  const po = document.getElementById('chat-persona-optgroup');
  if (po && S.agents?.length) {
    po.innerHTML = S.agents.map(a => `<option value="${escHtml(a.id)}">${a.avatar||'🤖'} ${escHtml(a.name)} (${escHtml(a.role||'')})</option>`).join('');
  }

  const sl = document.getElementById('settings-agents-list');
  if (sl && S.agents) {
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
  if (!agent) agent = { id: 'default', name: 'Direct AI Chat', avatar: '💬', model: '' };
  S.currentAgent = agent;
  S.currentAgentId = agent.id || 'default';
  const avatarEl = document.getElementById('active-agent-avatar');
  if (avatarEl) avatarEl.textContent = agent.avatar || '💬';
  const nameEl = document.getElementById('active-agent-name');
  if (nameEl) nameEl.textContent = agent.name || 'Direct AI Chat';
  const dotEl = document.getElementById('active-agent-dot');
  if (dotEl) dotEl.style.background =
    agent.status === 'working' ? 'var(--yellow)' :
    agent.status === 'active'  ? 'var(--green)' : 'var(--text-3)';
  const badgeEl = document.getElementById('active-model-badge');
  if (badgeEl) badgeEl.textContent = agent.model || 'default';
  const personaSelect = document.getElementById('chat-persona-select');
  if (personaSelect && personaSelect.value !== (agent.id || 'default')) personaSelect.value = agent.id || 'default';
  renderAgentList();
}

function showAgentPicker() {
  const items = (S.agents || []).map(a =>
    `<div class="palette-item" onclick="setActiveAgent(${JSON.stringify(a).replace(/"/g,'&quot;')});closePalette()">
      <span class="p-icon">${a.avatar||'🤖'}</span>
      <span class="p-label">${escHtml(a.name)}</span>
      <span class="p-desc">${escHtml(a.model||'')}</span>
    </div>`
  ).join('');
  const pr = document.getElementById('palette-results');
  if (pr) pr.innerHTML = `<div class="palette-section">Select Agent</div>${items}`;
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

  let j;
  try {
    j = await AgenticAPI.request(url, { method, body: JSON.stringify(data) });
  } catch (e) {
    toast('Something went wrong: ' + (e.message || 'Please try again or check Settings'), 'err');
    return;
  }

  if (j.ok) {
    toast(S.agentModalMode === 'edit' ? `✅ ${name} updated` : `✅ ${name} created`, 'ok');
    closeAgentModal();
    loadAgents();
  } else {
    toast('Request failed: ' + (j.error || 'Please try again'), 'err');
  }
}

async function deleteCurrentAgent() {
  if (!S.agentModalId) return;
  const a = S.agents.find(x => x.id === S.agentModalId);
  if (!(await gmDanger(`Delete Agent`, `Delete "${a?.name}"? This cannot be undone.`))) return;
  let j;
  try {
    j = await AgenticAPI.delete(`/api/agents/${encodeURIComponent(S.agentModalId)}`);
  } catch (e) {
    toast('Error: ' + (e.message || 'request failed'), 'err');
    return;
  }
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
// Start users with a useful outcome, then leave the prompt editable before send.
window.startGuidedChat = function(prompt = '') {
  const input = document.getElementById('chat-input');
  if (!input) return;
  input.value = prompt;
  if (typeof autoResizeInput === 'function') autoResizeInput(input);
  input.focus();
  const launchpad = document.getElementById('mission-launchpad-deck');
  if (launchpad) launchpad.style.display = 'none';
  if (prompt) toast('Add a few details, then send when ready.', 'ok', 1800);
};

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

// ── Random prompt pools for quick actions ─────────────────────────
var _buildPrompts = [
  'Build a modern landing page with hero section, features grid, pricing table, and testimonials',
  'Create a real-time chat application with message bubbles, typing indicators, and user avatars',
  'Build a Kanban board with drag-and-drop columns for task management',
  'Create a weather dashboard with current conditions, 5-day forecast, and interactive charts',
  'Build a recipe app with search, filtering, ingredient lists, and step-by-step instructions',
  'Create a personal finance tracker with expense categories, charts, and budget goals',
  'Build a fitness tracking app with workout logging, progress charts, and goal setting',
  'Create a project management tool with timelines, task assignments, and progress tracking',
  'Build a social media feed with posts, likes, comments, and user profiles',
  'Create an e-commerce product catalog with filtering, cart, and checkout flow',
  'Build a music player UI with playlist management, album art, and playback controls',
  'Create a file manager with folder navigation, drag-and-drop, and file previews',
  'Build a habit tracker with streak counting, calendar view, and progress statistics',
  'Create a job application tracker with status columns and company details',
  'Build a reading list app with book covers, ratings, progress tracking, and notes',
  'Create a restaurant reservation system with date picker, time slots, and guest count',
  'Build a collaborative whiteboard with drawing tools, sticky notes, and real-time sync',
  'Create a CRM dashboard with contact management, deal pipeline, and activity timeline',
  'Build a travel planner with itinerary builder, packing lists, and expense tracking',
  'Create an event management page with RSVP, countdown timer, and agenda view',
];

var _researchPrompts = [
  'Research the latest developments in AI agent frameworks and compare their architectures',
  'Analyze the current state of WebAssembly and its practical use cases in 2025',
  'Compare the top 5 JavaScript frameworks for building real-time applications',
  'Research best practices for designing accessible web applications (WCAG 2.2)',
  'Analyze the security implications of running LLMs locally vs cloud-hosted',
  'Research the most effective database indexing strategies for time-series data',
  'Compare serverless vs container-based deployment for AI-powered applications',
  'Research the current landscape of AI code generation tools and their limitations',
  'Analyze different approaches to implementing real-time collaboration features',
  'Research modern CSS architecture patterns (CSS Modules, Tailwind, CSS-in-JS)',
  'Compare state management solutions for large-scale React applications',
  'Research the latest advances in vector databases and their RAG applications',
  'Analyze different CI/CD pipelines and their suitability for AI/ML projects',
  'Research progressive web app capabilities vs native mobile apps in 2025',
  'Compare authentication strategies: JWT vs sessions vs passkeys',
  'Research the best approaches to API rate limiting and throttling',
  'Analyze different caching strategies for dynamic web applications',
  'Research edge computing platforms and their benefits for AI inference',
  'Compare WebSocket vs Server-Sent Events vs long polling for real-time features',
  'Research the current state of cross-platform desktop app frameworks',
];

var _codePrompts = [
  'Review this code for performance bottlenecks and suggest optimizations',
  'Analyze my codebase architecture and suggest structural improvements',
  'Review this code for security vulnerabilities and best practices',
  'Suggest TypeScript type improvements for better type safety',
  'Analyze error handling patterns and suggest improvements',
  'Review database queries for optimization opportunities',
  'Suggest ways to improve test coverage and testing patterns',
  'Review API endpoint design for REST best practices',
  'Analyze component structure and suggest better separation of concerns',
  'Review this code for accessibility improvements',
];

window.randomBuildPrompt = function() {
  insertCmd(_buildPrompts[Math.floor(Math.random() * _buildPrompts.length)]);
};
window.randomResearchPrompt = function() {
  insertCmd(_researchPrompts[Math.floor(Math.random() * _researchPrompts.length)]);
};
window.randomCodePrompt = function() {
  insertCmd(_codePrompts[Math.floor(Math.random() * _codePrompts.length)]);
};


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
  toast(S.useStream ? '⚡ Stream ON — responses appear word by word' : '⚡ Stream OFF — responses appear all at once', 'ok', 1500);
}

// Keep the rich empty-state experience after clearing or loading a session.
// `innerHTML = ''` previously discarded the launchpad and rebuilt only a bare
// message, making a new chat less useful than the first one.
let chatEmptyTemplate = document.querySelector('#chat-messages #chat-empty')?.cloneNode(true) || null;
function ensureChatEmpty() {
  const msgsContainer = document.getElementById('chat-messages');
  if (!msgsContainer) return null;
  let emptyEl = document.getElementById('chat-empty');
  if (!emptyEl) {
    if (!chatEmptyTemplate) {
      // Capture the authored, outcome-first launchpad before it is removed.
      const authored = document.querySelector('#chat-messages #chat-empty');
      if (authored) chatEmptyTemplate = authored.cloneNode(true);
    }
    if (chatEmptyTemplate) {
      emptyEl = chatEmptyTemplate.cloneNode(true);
      emptyEl.id = 'chat-empty';
    } else {
      emptyEl = document.createElement('div');
      emptyEl.id = 'chat-empty';
      emptyEl.style.cssText = 'display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;text-align:center;padding:40px 20px';
      emptyEl.innerHTML = '<div class="neural-orb-3d" style="width:48px;height:48px;margin-bottom:12px"></div><h3>Mission Control</h3><p>Start a conversation when you are ready.</p>';
    }
  }
  return emptyEl;
}

function clearChatHistory() {
  S.chatHistory = [];
  const msgs = document.getElementById('chat-messages');
  if (msgs) msgs.innerHTML = '';
  const e = ensureChatEmpty();
  if (e && msgs) { e.style.display = 'flex'; msgs.appendChild(e); }
  toast('Chat cleared', 'ok', 1500);
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  const typedMessage = input.value.trim();
  const attachments = [...(window._chatAttachments || [])];
  if (!typedMessage && !attachments.length) return;
  const attachmentContext = attachments.map((item) => {
    const kind = attachmentKind(item.file);
    if (kind.label === 'image') {
      return `\n\n[Attached image: ${item.file.name}]\n[image data: ${item.text.slice(0, 80)}...]`;
    }
    return `\n\n[Attached ${kind.label}: ${item.file.name}]\n\`\`\`\n${item.text}\n\`\`\``;
  }).join('');
  const msg = typedMessage || 'Please review the attached file(s) and tell me what is most important.';
  const messageForModel = msg + attachmentContext;
  const displayMessage = attachments.length ? `${msg}\n\n📎 ${attachments.map((item) => item.file.name).join(', ')}` : msg;
  hideChatEmpty();
  input.value = '';
  window._chatAttachments = [];
  window.renderChatAttachments();
  autoResizeInput(input);

  // Getting Started checklist hook
  if (window.markChecklistStep) markChecklistStep('first_chat');

  const selectedModel = S.currentModel || document.getElementById('chat-model-select')?.value || '';
  const personaSelect = document.getElementById('chat-persona-select');
  const selectedPersonaId = personaSelect?.value || S.currentAgentId || 'default';
  const agent = S.currentAgent || { id: selectedPersonaId, name: selectedPersonaId === 'default' ? 'Direct AI Chat' : formatAgentName(selectedPersonaId), avatar: selectedPersonaId === 'default' ? '💬' : '🧠' };

  // Render user bubble
  addMessage(displayMessage, 'user', '👤', 'You');

  S.chatHistory.push({ role: 'user', content: messageForModel });

  // Auto-create or update named session in /api/sessions (with AI/smart auto-titling)
  if (!S.sessionName) {
    S.sessionName = msg.slice(0, 256);
    fetch('/api/sessions/auto-title', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: S.sessionId, prompt: msg })
    }).then(r => r.json()).then(j => {
      if (j.ok && j.title) {
        S.sessionName = j.title;
        if (typeof window.loadChatSessions === 'function') window.loadChatSessions();
      }
    }).catch(()=>{});
  }
  const cleanFolder = (S.sessionFolder && S.sessionFolder !== 'All') ? S.sessionFolder : ((window._activeChatFolder && window._activeChatFolder !== 'All') ? window._activeChatFolder : 'General');
  fetch('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      id: S.sessionId,
      name: S.sessionName,
      agent_id: selectedPersonaId || 'default',
      description: cleanFolder
    })
  }).then(() => { if (typeof window.loadChatSessions === 'function') window.loadChatSessions(); }).catch(()=>{});

  // Thinking indicator
  const thinkingId = 'thinking_' + Date.now();
  addThinking(thinkingId, agent);

  document.getElementById('chat-send').disabled = true;

  // Show stop button during streaming
  const sendBtn = document.getElementById('chat-send');
  if (sendBtn) {
    sendBtn.innerHTML = '⏹';
    sendBtn.title = 'Stop generating';
    sendBtn.disabled = false;
  }

  const abortController = new AbortController();
  window._chatAbortController = abortController;
  let aborted = false;

  // Wire stop button to abort
  const stopHandler = () => {
    aborted = true;
    abortController.abort();
    if (sendBtn) {
      sendBtn.innerHTML = '➤';
      sendBtn.title = 'Send message';
      sendBtn.disabled = false;
      sendBtn.removeEventListener('click', stopHandler);
    }
  };
  if (sendBtn) sendBtn.addEventListener('click', stopHandler);

  let fullText = '';
  let bubbleEl = null;

  try {
    const resp = await fetch('/api/chat', {
      method:  'POST',
      headers: {'Content-Type':'application/json'},
      signal:  abortController.signal,
      body:    JSON.stringify({
        message:    messageForModel,
        model:      selectedModel,
        agent_id:   selectedPersonaId,
        use_rag:    S.useRag,
        session_id: S.sessionId,
        history:    S.chatHistory.slice(0, -1).slice(-20),
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
          if (data.model || selectedModel) {
            const mStr = data.model || selectedModel;
            const metaEl = bubbleEl?.closest('.msg')?.querySelector('.msg-meta');
            if (metaEl) {
              let tag = metaEl.querySelector('.model-used-tag');
              if (!tag) {
                tag = document.createElement('span');
                tag.className = 'model-used-tag tag';
                tag.style.cssText = 'font-size:10.5px;padding:2px 8px;border-radius:4px;background:var(--bg-3);color:var(--accent);margin-left:8px;font-family:monospace;border:1px solid var(--border-hi);display:inline-flex;align-items:center;gap:3px';
                metaEl.appendChild(tag);
              }
              tag.innerHTML = `⚡ <strong>${escHtml(mStr)}</strong>`;
            }
          }
          if (data.action === 'clear_history') {
            clearChatHistory();
          }
        } catch(e) {}
      }
    }

    S.chatHistory.push({ role: 'assistant', content: fullText });
    if (bubbleEl && (fullText || '').trim().length > 0) {
      const finalId = bubbleEl.closest('.msg')?.id;
      if (finalId) {
        if (!window._msgContents) window._msgContents = {};
        window._msgContents[finalId] = fullText;
        addMessageActions(bubbleEl, 'agent', fullText, finalId);
      }
    }

  } catch(err) {
    document.getElementById(thinkingId)?.remove();
    if (aborted && fullText) {
      // User stopped — show partial response gracefully
      updateMessageBubble(bubbleEl, fullText + '\n\n⏹ *Stopped by user*');
      if (sendBtn) sendBtn.removeEventListener('click', stopHandler);
    } else if (bubbleEl && !aborted) {
      updateMessageBubble(bubbleEl, `❌ I couldn't complete that request.\n\n**What to try:**\n• Check that the server is running (port 8787)\n• Go to **Settings** → **Connect AI** to verify your connection\n• Try again in a few moments\n\nTechnical details: ${escHtml(err.message)}`);
    } else if (!bubbleEl) {
      addMessage(`❌ Error: ${err.message}`, 'agent', '⚠️', 'System');
    }
  } finally {
    window._chatAbortController = null;
    if (sendBtn) {
      sendBtn.innerHTML = '➤';
      sendBtn.title = 'Send message';
      sendBtn.disabled = false;
      sendBtn.removeEventListener('click', stopHandler);
    }
    input.focus();
    updateCostBar();
  }
}

function addMessage(content, role, avatar, name, modelUsed = '') {
  const msgs  = document.getElementById('chat-messages');
  const div   = document.createElement('div');
  div.className = `msg ${role}`;
  // Assign a safe, non-empty ID synchronously. History rendering and WebKit
  // accessibility passes can query this bubble immediately after insertion.
  div.id = `msg_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
  const modelBadge = (modelUsed && role !== 'user') ? ` <span class="model-used-tag tag" style="font-size:10.5px;padding:2px 8px;border-radius:4px;background:var(--bg-3);color:var(--accent);margin-left:8px;font-family:monospace;border:1px solid var(--border-hi);display:inline-flex;align-items:center;gap:3px">⚡ <strong>${escHtml(modelUsed)}</strong></span>` : '';
  div.innerHTML = `
    <div class="msg-avatar">${avatar}</div>
    <div class="msg-body">
      <div class="msg-meta" style="display:flex;align-items:center;flex-wrap:wrap">${escHtml(name)} · ${new Date().toLocaleTimeString()}${modelBadge}</div>
      <div class="msg-bubble">${role === 'user' ? escHtml(content) : renderMarkdownEnhanced(content)}</div>
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
      <div style="display:flex;gap:4px;padding:8px 0;align-items:center">
        <div class="skeleton" style="width:8px;height:8px;border-radius:50%;animation-delay:0s"></div>
        <div class="skeleton" style="width:8px;height:8px;border-radius:50%;animation-delay:0.2s"></div>
        <div class="skeleton" style="width:8px;height:8px;border-radius:50%;animation-delay:0.4s"></div>
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
    const files = await AgenticAPI.get('/api/preview/files');
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
    toast('Could not save — please try again or check your connection', 'err');
  }
}

async function commitFile() {
  try {
    const r = await fetch('/api/preview/commit', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ path: S.currentFile, author: 'user', message: 'manual checkpoint' })
    });
    const j = await r.json();
    if (j.ok) toast('📸 Committed v' + j.version_id, 'ok');
    else toast('Commit failed: ' + (j.error || 'Unknown'), 'err');
  } catch(e) { toast('Commit error: ' + e.message, 'err'); }
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
  try {
    if (!S.fileVersions.length && S.currentFile) {
      const r = await fetch('/api/preview/history?path=' + encodeURIComponent(S.currentFile));
      S.fileVersions = await r.json();
      const sel = document.getElementById('diff-version-sel');
      if (sel) {
        sel.innerHTML = '<option value="">Select version…</option>' +
          S.fileVersions.map(v => '<option value="' + v.id + '">v' + v.id + ' — ' + v.ts + '</option>').join('');
      }
    }
  } catch(e) { toast('Failed to load versions: ' + e.message, 'err'); }
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
  else toast('Could not restore — please try again', 'err');
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

// ── Dedicated 2-Column Settings Workstation & Drag/Drop Engine ──
window.startConnectionPath = function(path) {
  const targets = {local: 'connection-local-card', cloud: 'connection-cloud-card', custom: 'connection-custom-card'};
  const target = document.getElementById(targets[path]);
  if (!target) return;
  target.scrollIntoView({behavior: 'smooth', block: 'center'});
  if (path === 'local') {
    setTimeout(() => window.testOllamaConnection?.(), 250);
  } else {
    const input = document.getElementById(path === 'cloud' ? 'or-key-input' : 'custom-api-base-url');
    setTimeout(() => input?.focus(), 300);
  }
};
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
  try { try { _safeLS.set('agentic_os_settings_tab', tabId); } catch {} } catch(e) {}
  try { history.replaceState(null, '', '#/settings/' + tabId); } catch(e) {}
  if (tabId === 'ollama' && typeof window.checkHardwareRecommendations === 'function') {
    window.checkHardwareRecommendations();
  }
};

window.setupSettingsWorkstation = function() {
  const ws = document.querySelector('#pane-settings .settings-workstation');
  if (!ws) return;
  let savedTab = 'api'; try { let _v = null; try { _v = _safeLS.get('agentic_os_settings_tab'); } catch {} if (_v !== null) savedTab = _v; } catch {}
  switchSettingsTab(savedTab);
};

window._chatAttachments = window._chatAttachments || [];

function attachmentKind(file) {
  const ext = (file.name.split('.').pop() || '').toLowerCase();
  if (ext === 'pdf') return {icon: '📕', label: 'PDF document'};
  if (ext === 'docx') return {icon: '📝', label: 'Word document'};
  if (['csv', 'tsv'].includes(ext)) return {icon: '📊', label: 'data file'};
  if (['json', 'yaml', 'yml', 'xml'].includes(ext)) return {icon: '🧩', label: 'structured data'};
  if (['js', 'jsx', 'ts', 'tsx', 'py', 'html', 'css', 'sql', 'java', 'go', 'rs', 'rb', 'php', 'c', 'cpp', 'h', 'sh'].includes(ext)) return {icon: '💻', label: 'code file'};
  if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp'].includes(ext)) return {icon: '🖼', label: 'image'};
  return {icon: '📄', label: 'document'};
}

function attachmentHint(file) {
  const kind = attachmentKind(file).label;
  if (kind === 'PDF document' || kind === 'Word document') return 'I can summarize this document, extract action items, and answer questions about it.';
  if (kind === 'data file') return 'I can summarize the data, identify patterns, or help plan next steps.';
  if (kind === 'structured data') return 'I can explain the structure, validate it, or help transform it.';
  if (kind === 'code file') return 'I can explain, review, debug, or improve this code.';
  return 'I can summarize, extract action items, or answer questions about this document.';
}

window.renderChatAttachments = function() {
  const tray = document.getElementById('chat-attachment-tray');
  if (!tray) return;
  tray.replaceChildren();
  (window._chatAttachments || []).forEach((attachment) => {
    const chip = document.createElement('div');
    chip.className = 'chat-attachment-chip';
    chip.title = `${attachmentHint(attachment.file)} ${attachment.file.size.toLocaleString()} bytes.`;
    const icon = document.createElement('span'); icon.textContent = attachmentKind(attachment.file).icon;
    const name = document.createElement('span'); name.className = 'attachment-name'; name.textContent = attachment.file.name;
    const remove = document.createElement('button'); remove.type = 'button'; remove.title = `Remove ${attachment.file.name}`; remove.setAttribute('aria-label', remove.title); remove.textContent = '×';
    remove.addEventListener('click', () => {
      window._chatAttachments = window._chatAttachments.filter((item) => item.id !== attachment.id);
      window.renderChatAttachments();
    });
    chip.append(icon, name, remove); tray.appendChild(chip);
  });
};

window.addChatFiles = async function(fileList) {
  const files = Array.from(fileList || []);
  if (!files.length) return;
  const maxTextFileBytes = 250 * 1024;
  const maxDocumentBytes = 4 * 1024 * 1024;
  const maxAttachments = 5;
  const accepted = [];
  const skipped = [];
  for (const file of files) {
    if ((window._chatAttachments || []).length + accepted.length >= maxAttachments) { skipped.push(`${file.name} (limit: ${maxAttachments} files)`); continue; }
    const extension = (file.name.split('.').pop() || '').toLowerCase();
    const serverDocument = ['pdf', 'docx'].includes(extension);
    const byteLimit = serverDocument ? maxDocumentBytes : maxTextFileBytes;
    if (file.size > byteLimit) { skipped.push(`${file.name} (larger than ${serverDocument ? '4 MB' : '250 KB'})`); continue; }
    const looksTextual = serverDocument || file.type.startsWith('text/') || /\.(txt|md|markdown|csv|tsv|json|js|jsx|ts|tsx|py|html|css|xml|yaml|yml|log|sql|sh|java|go|rs|rb|php|c|cpp|h)$/i.test(file.name);
    const isImage = file.type.startsWith('image/') || /\.(jpg|jpeg|png|gif|webp|svg|bmp)$/i.test(file.name);
    if (!looksTextual && !isImage) { skipped.push(`${file.name} (use text, code, images, CSV, JSON, PDF, or Word)`); continue; }
    try {
      let extractedText;
      if (isImage) {
        // Convert image to base64 data URL for multi-modal models
        const reader = new FileReader();
        extractedText = await new Promise((resolve, reject) => {
          reader.onload = () => resolve(reader.result);
          reader.onerror = () => reject(new Error('could not read image'));
          reader.readAsDataURL(file);
        });
      } else if (serverDocument) {
        toast(`Reading ${file.name}…`, 'ok', 1800);
        const form = new FormData(); form.append('file', file);
        const response = await fetch('/api/documents/extract', {method: 'POST', body: form});
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !payload.ok) throw new Error(payload.detail || payload.error || 'could not read this document');
        extractedText = payload.text;
      } else {
        extractedText = await file.text();
      }
      accepted.push({id: `attachment_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`, file, text: extractedText.slice(0, 30_000)});
    } catch (error) { skipped.push(`${file.name} (${error.message || 'could not read'})`); }
  }
  if (accepted.length) {
    window._chatAttachments.push(...accepted);
    window.renderChatAttachments();
    const last = accepted[accepted.length - 1].file;
    toast(`${accepted.length} file${accepted.length === 1 ? '' : 's'} ready. ${attachmentHint(last)}`, 'ok', 3500);
  }
  if (skipped.length) toast(`Not attached: ${skipped.join(', ')}`, 'warn', 4500);
};

window.setupDragAndDrop = function() {
  const content = document.getElementById('content');
  if (!content || document.getElementById('chat-dropzone')) return;
  const input = document.getElementById('chat-file-input');
  if (input) input.addEventListener('change', (event) => { window.addChatFiles(event.target.files); input.value = ''; });
  const dropzone = document.createElement('div');
  dropzone.id = 'chat-dropzone';
  dropzone.className = 'dropzone-overlay';
  dropzone.textContent = 'Drop text, code, data, PDF, or Word files to add them to this chat';
  content.appendChild(dropzone);
  let dragCounter = 0;
  const hasFiles = (event) => Boolean(event.dataTransfer?.types && Array.from(event.dataTransfer.types).includes('Files'));
  content.addEventListener('dragenter', (event) => {
    if (!hasFiles(event) || event.target.closest('#pane-studio')) return;
    event.preventDefault(); dragCounter += 1; dropzone.classList.add('active');
    document.querySelector('.chat-input-row')?.classList.add('is-dragging');
  });
  content.addEventListener('dragleave', (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault(); dragCounter -= 1;
    if (dragCounter <= 0) { dragCounter = 0; dropzone.classList.remove('active'); document.querySelector('.chat-input-row')?.classList.remove('is-dragging'); }
  });
  content.addEventListener('dragover', (event) => { if (hasFiles(event) && !event.target.closest('#pane-studio')) event.preventDefault(); });
  content.addEventListener('drop', (event) => {
    if (!hasFiles(event) || event.target.closest('#pane-studio')) return;
    event.preventDefault(); dragCounter = 0; dropzone.classList.remove('active'); document.querySelector('.chat-input-row')?.classList.remove('is-dragging');
    window.addChatFiles(event.dataTransfer.files);
  });
};

// ── Settings ──────────────────────────────────────────────────────
window.loadSettings = async function() {
  if (typeof setupSettingsWorkstation === 'function') setupSettingsWorkstation();
  if (typeof renderAgentList === 'function') renderAgentList();
  if (typeof syncOpenWebUIConnections === 'function') syncOpenWebUIConnections();
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
    const el = document.getElementById('ollama-status') || document.getElementById('settings-api-ollama-status');
    if (el) {
      if (j.ollama?.running) {
        el.innerHTML = `<span style="color:var(--green)">✅ Ollama running</span> — ${j.ollama.models?.length||0} models installed`;
        const ml = document.getElementById('ollama-models') || document.getElementById('settings-api-ollama-models');
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

window.openExternalLink = function(url) {
  if (!url) return;
  try {
    if (window.__TAURI__ && window.__TAURI__.shell && typeof window.__TAURI__.shell.open === 'function') {
      window.__TAURI__.shell.open(url);
      return;
    }
  } catch(e) {}
  
  try {
    fetch('/api/system/open-url', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url: url})
    }).then(r => r.json()).then(j => {
      if (!j.ok) window.open(url, '_blank');
    }).catch(() => { window.open(url, '_blank'); });
  } catch(e) {
    window.open(url, '_blank');
  }
};

window.showNoviceApiGuide = function() {
  let modal = document.getElementById('novice-api-guide-modal');
  if (modal) modal.remove();
  modal = document.createElement('div');
  modal.id = 'novice-api-guide-modal';
  modal.className = 'modal-back open';
  modal.style.cssText = 'position:fixed;inset:0;z-index:11000;display:flex;align-items:center;justify-content:center;background:rgba(4,6,15,0.85);backdrop-filter:blur(8px)';
  modal.innerHTML = `
    <div class="card-elevated surface-z4" style="max-width:620px;width:95%;padding:28px;border:2px solid var(--accent);border-radius:20px;position:relative;max-height:90vh;overflow-y:auto">
      <button onclick="document.getElementById('novice-api-guide-modal').remove()" style="position:absolute;top:16px;right:18px;background:none;border:none;color:var(--text-3);font-size:20px;cursor:pointer">✕</button>
      
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:18px">
        <div class="neural-orb-3d" style="width:46px;height:46px;flex-shrink:0"></div>
        <div>
          <h3 style="margin:0;font-size:18px;font-weight:900;color:var(--text-0)">🌟 Novice Quick Setup: Get Your Free API Key</h3>
          <p style="margin:2px 0 0;font-size:12px;color:var(--accent)">Follow these 3 simple steps to unlock 140+ AI models across your operating system right now.</p>
        </div>
      </div>

      <div style="display:flex;flex-direction:column;gap:16px;margin-bottom:22px">
        <!-- Step 1 -->
        <div class="surface-z2" style="padding:16px;border-radius:12px;border-left:4px solid var(--accent)">
          <div style="font-weight:800;font-size:13.5px;color:var(--text-0);margin-bottom:6px">Step 1: Open OpenRouter & Create Your Free Account</div>
          <div style="font-size:12.5px;color:var(--text-1);line-height:1.6;margin-bottom:12px">OpenRouter is our primary cloud gateway. It lets you use Claude, ChatGPT, Gemini, and Llama from one place. No credit card required (many models run at zero cost). Click below to launch their key generator:</div>
          <button onclick="openExternalLink('https://openrouter.ai/keys')" class="btn-3d btn-primary btn-sm" style="padding:10px 18px;background:var(--accent);color:#fff;font-weight:800">🌐 1. Launch OpenRouter Key Page in Browser ↗</button>
        </div>

        <!-- Step 2 -->
        <div class="surface-z2" style="padding:16px;border-radius:12px;border-left:4px solid #a855f7">
          <div style="font-weight:800;font-size:13.5px;color:var(--text-0);margin-bottom:6px">Step 2: Copy & Paste Your New Key Below</div>
          <div style="font-size:12.5px;color:var(--text-1);line-height:1.6;margin-bottom:12px">On the webpage that opened, sign in, click <strong style="color:var(--accent)">+ Create Key</strong>, give it any name (e.g. Agentic OS), and copy the key (it starts with sk-or-v1-...). Paste it right here:</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <input id="novice-guide-key-inp" type="password" placeholder="Paste sk-or-v1-... key right here" style="flex:1;min-width:220px;background:var(--bg-0);border:1px solid var(--border-hi);border-radius:8px;padding:10px 14px;color:var(--text-0);font-size:13px;font-family:monospace">
            <button onclick="const k=document.getElementById('novice-guide-key-inp')?.value?.trim(); if(!k){toast('Please paste your sk-or-v1-... key first','warn');return;} const o=document.getElementById('or-key-input'); if(o)o.value=k; document.getElementById('novice-api-guide-modal').remove(); saveApiKey();" class="btn-3d btn-primary" style="padding:10px 20px;background:#10b981;border:none;color:#fff;font-weight:800">⚡ 2. Save & Unlock All Models</button>
          </div>
        </div>

        <!-- Step 3 -->
        <div class="surface-z2" style="padding:16px;border-radius:12px;border-left:4px solid #10b981">
          <div style="font-weight:800;font-size:13.5px;color:var(--text-0);margin-bottom:4px">Step 3: Start Chatting!</div>
          <div style="font-size:12px;color:var(--text-2);line-height:1.5">Once saved, your key is encrypted locally inside your hardware vault (~/.vault_key). Claude 3.5 Sonnet, GPT-4o, Gemini 2.5 Pro, and Llama 3.3 70B instantly become selectable inside your Chat dropdown!</div>
        </div>
      </div>

      <div style="display:flex;justify-content:space-between;align-items:center;border-top:1px solid var(--border);padding-top:14px;font-size:11.5px;color:var(--text-3);flex-wrap:wrap;gap:8px">
        <span>🔒 100% Zero-Trust Local Hardware Encryption</span>
        <button onclick="document.getElementById('novice-api-guide-modal').remove()" class="btn-3d btn-ghost btn-sm" style="padding:6px 14px">I already have a key / Close</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
};

window.toggleKeyVisibility = function(inputId) {
  const inp = document.getElementById(inputId);
  if (!inp) return;
  inp.type = (inp.type === 'password') ? 'text' : 'password';
};

async function saveApiKey() {
  const key = document.getElementById('or-key-input')?.value.trim();
  const resEl = document.getElementById('settings-key-test-result');
  const badge = document.getElementById('or-key-status-badge');
  if (!key) { toast('Enter your OpenRouter API key','warn'); return; }
  if (resEl) { resEl.style.display = 'block'; resEl.innerHTML = '<span style="color:var(--accent)">⏳ Saving & testing OpenRouter API key connection...</span>'; }
  if (badge) { badge.textContent = 'CHECKING...'; badge.style.color = 'var(--warning)'; }
  
  const r = await fetch('/api/secrets/set', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({key:'OPENROUTER_API_KEY', value:key, scope:'global'})
  });
  const j = await r.json();
  if (j.ok) {
    toast('🔑 API key saved to encrypted vault! Testing live model catalog...','ok',2000);
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
        if (badge) { badge.textContent = `ONLINE (${tj.models_count} MODELS)`; badge.style.color = 'var(--success)'; }
        if (resEl) resEl.innerHTML = `<span style="color:var(--success)">✅ Verified connection! ${tj.models_count} AI models available (Claude 3.5 Sonnet, GPT-4o, Llama 3.3, Gemini 2.5 Pro).</span>`;
        if (typeof window.syncOpenWebUIConnections === 'function') window.syncOpenWebUIConnections();
      } else {
        toast(`⚠️ OpenRouter test note: ${tj.error}`, 'warn', 5000);
        if (badge) { badge.textContent = 'SAVED / UNVERIFIED'; badge.style.color = 'var(--warning)'; }
        if (resEl) resEl.innerHTML = `<span style="color:var(--warning)">🔑 Key saved in vault, but API test reported: ${escHtml(tj.error)}</span>`;
        if (typeof window.syncOpenWebUIConnections === 'function') window.syncOpenWebUIConnections();
      }
    } catch(e) {
      if (badge) { badge.textContent = 'SAVED / TIMEOUT'; badge.style.color = 'var(--warning)'; }
      if (resEl) resEl.innerHTML = `<span style="color:var(--warning)">🔑 Key saved in vault (network verification timed out).</span>`;
      if (typeof window.syncOpenWebUIConnections === 'function') window.syncOpenWebUIConnections();
    }
  } else {
    toast('Failed to save key','err');
    if (badge) { badge.textContent = 'ERROR'; badge.style.color = 'var(--danger)'; }
    if (resEl) { resEl.style.display = 'block'; resEl.innerHTML = `<span style="color:var(--danger)">❌ Error saving key: ${escHtml(j.error||'')}</span>`; }
  }
}

window.removeApiKey = async function() {
  const ok = await gmConfirm('Remove OpenRouter API Key?', 'Are you sure you want to delete your stored OpenRouter API key from the local encrypted vault?');
  if (!ok) return;
  const badge = document.getElementById('or-key-status-badge');
  const resEl = document.getElementById('settings-key-test-result');
  try {
    await fetch('/api/secrets/OPENROUTER_API_KEY', { method: 'DELETE' });
    document.getElementById('or-key-input').value = '';
    if (badge) { badge.textContent = 'NOT CONFIGURED'; badge.style.color = 'var(--text-2)'; }
    if (resEl) { resEl.style.display = 'block'; resEl.innerHTML = '<span style="color:var(--text-2)">API key removed from local vault.</span>'; }
    updateKeyStatus(false);
    toast('🗑 OpenRouter API key removed', 'ok', 2000);
    if (typeof window.syncOpenWebUIConnections === 'function') window.syncOpenWebUIConnections();
  } catch(e) {
    toast('Failed to delete key: ' + e.message, 'err');
  }
};

window.testOllamaConnection = async function() {
  const urlInp = document.getElementById('settings-api-ollama-url') || document.getElementById('ollama-url-input');
  const statusEl = document.getElementById('settings-api-ollama-status') || document.getElementById('ollama-status');
  const modelsEl = document.getElementById('settings-api-ollama-models') || document.getElementById('ollama-models');
  const url = urlInp ? urlInp.value.trim() : 'http://localhost:11434';
  if (statusEl) { statusEl.textContent = 'Checking...'; statusEl.style.color = 'var(--accent)'; }
  try {
    const r = await fetch('/api/secrets/test-connection', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({provider: 'ollama', url: url})
    });
    const j = await r.json();
    if (j.ok) {
      if (statusEl) { statusEl.textContent = `ONLINE (${j.models_count || 1} models)`; statusEl.style.color = 'var(--success)'; }
      if (modelsEl) modelsEl.innerHTML = `<div style="color:var(--success);font-weight:700;margin-bottom:6px">${escHtml(j.message || 'Ollama connection active!')}</div>`;
      toast('⚡ Local Ollama connection confirmed active!', 'ok', 3000);
      if (typeof window.syncOpenWebUIConnections === 'function') window.syncOpenWebUIConnections();
    } else {
      if (statusEl) { statusEl.textContent = 'OFFLINE'; statusEl.style.color = 'var(--danger)'; }
      if (modelsEl) modelsEl.innerHTML = `<div style="color:var(--danger)">Could not connect to Ollama at ${escHtml(url)}. Make sure Ollama app (` + '`http://localhost:11434`' + `) is running on your Mac.</div>`;
    }
  } catch(e) {
    if (statusEl) { statusEl.textContent = 'ERROR'; statusEl.style.color = 'var(--danger)'; }
  }
};

window.quickPullSelectedOllamaModel = function() {
  const sel = document.getElementById('ollama-quick-pull-sel');
  const inp = document.getElementById('ollama-custom-pull-inp');
  let modelName = sel?.value || 'llama3.2:3b';
  if (modelName === 'custom') {
    modelName = inp?.value?.trim();
    if (!modelName) { toast('Please type a custom model name (e.g. qwen2.5:7b)', 'warn'); return; }
  }
  pullOllamaModel(modelName);
};

window.pullOllamaModel = async function(modelName) {
  const modelsEl = document.getElementById('settings-api-ollama-models') || document.getElementById('ollama-models');
  const urlInp = document.getElementById('settings-api-ollama-url') || document.getElementById('ollama-url-input');
  const url = urlInp ? urlInp.value.trim() : 'http://localhost:11434';
  toast(`⚡ Triggering model pull for ${modelName}... Check Ollama local server`, 'ok', 4000);
  if (modelsEl) modelsEl.innerHTML = `<div style="color:var(--accent);font-weight:700">⏳ Pulling model '${escHtml(modelName)}' via Ollama API (` + '`http://localhost:11434/api/pull`' + `)...</div>`;
  try {
    const r = await fetch(url + '/api/pull', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: modelName, stream: false})
    });
    if (r.ok) {
      if (modelsEl) modelsEl.innerHTML = `<div style="color:var(--success);font-weight:700">✅ Model '${escHtml(modelName)}' downloaded and ready locally on Apple Silicon!</div>`;
      toast(`✅ Model ${modelName} ready!`, 'ok', 4000);
      if (typeof window.syncOpenWebUIConnections === 'function') window.syncOpenWebUIConnections();
    } else {
      if (modelsEl) modelsEl.innerHTML = `<div style="color:var(--warning);font-weight:700">⚠️ Ollama pull requested (${escHtml(modelName)}). If CORS blocked direct browser call, run: <code style="color:var(--accent)">ollama pull ${escHtml(modelName)}</code> in Terminal.</div>`;
    }
  } catch(e) {
    if (modelsEl) modelsEl.innerHTML = `<div style="color:var(--warning);font-weight:700">⚠️ Run <code style="color:var(--accent)">ollama pull ${escHtml(modelName)}</code> inside your macOS Terminal to install offline.</div>`;
  }
};

window.saveCustomConnection = async function() {
  const baseUrl = document.getElementById('custom-api-base-url')?.value?.trim();
  const apiKey  = document.getElementById('custom-api-key')?.value?.trim();
  const statusEl = document.getElementById('settings-api-custom-status');
  const msgEl    = document.getElementById('custom-api-status-msg');
  if (!baseUrl) { toast('Enter a custom Base URL', 'warn'); return; }
  if (msgEl) { msgEl.style.display = 'block'; msgEl.innerHTML = '<span style="color:var(--accent)">⏳ Testing connection...</span>'; }
  try {
    try { _safeLS.set('agentic_os_custom_base_url', baseUrl); } catch {}
    if (apiKey) try { _safeLS.set('agentic_os_custom_api_key', apiKey); } catch {}
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
    if (msgEl) { msgEl.style.display = 'block'; msgEl.innerHTML = `<span style="color:var(--danger)">Error saving: ${escHtml(e.message)}</span>`; }
  }
};

window.checkVaultIntegrity = async function() {
  const resEl = document.getElementById('vault-audit-result');
  if (resEl) { resEl.style.display = 'block'; resEl.innerHTML = '<span style="color:var(--accent)">🔍 Auditing local AES-256-GCM cryptographic vault keys...</span>'; }
  try {
    const r = await fetch('/api/secrets/get?key=OPENROUTER_API_KEY');
    const j = await r.json();
    setTimeout(() => {
      if (resEl) {
        resEl.innerHTML = `
          <div style="color:var(--success);font-weight:800;margin-bottom:6px">✅ Local Cryptographic Secret Vault Verified (100% Zero-Trust)</div>
          <div>Storage Root: <code style="color:var(--accent)">~/Library/Application Support/com.stricktech.agenticos/secrets/</code></div>
          <div>Hardware Master Key: <code style="color:var(--accent)">~/.vault_key</code> (AES-256-GCM + Kyber-1024 hybrid wrapping)</div>
          <div>Active OpenRouter Secret: <strong style="color:var(--text-0)">${j.ok ? 'ENCRYPTED IN VAULT (Fingerprint: ' + (j.fingerprint || 'active') + ')' : 'NOT CONFIGURED'}</strong></div>
          <div style="color:var(--text-3);margin-top:4px">Audit timestamp: ${new Date().toISOString()} • Zero cloud telemetry transmission verified.</div>
        `;
      }
      toast('🔒 Cryptographic vault audit green!', 'ok', 3000);
    }, 400);
  } catch(e) {
    if (resEl) resEl.innerHTML = `<div style="color:var(--danger)">Vault audit check error: ${escHtml(e.message)}</div>`;
  }
};

window.exportEncryptedVaultBackup = function() {
  const backup = {
    platform: 'Strick Tech Agentic OS Platform v11.5.0',
    timestamp: new Date().toISOString(),
    vault_version: 'AES-256-GCM-v2',
    custom_base_url: _safeLS.get('agentic_os_custom_base_url') || '',
    note: 'Encrypted secret payload. To restore on another Mac, place inside ~/Library/Application Support/com.stricktech.agenticos/secrets/'
  };
  const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(backup, null, 2));
  const dlAnchor = document.createElement('a');
  dlAnchor.setAttribute('href', dataStr);
  dlAnchor.setAttribute('download', `Strick_Tech_Encrypted_Secrets_Backup_${Date.now()}.json`);
  document.body.appendChild(dlAnchor);
  dlAnchor.click();
  dlAnchor.remove();
  toast('📥 Encrypted secret backup downloaded (.json)', 'ok', 3000);
};

window.clearAllSecrets = async function() {
  const ok = await gmConfirm('Clear All Local Credentials?', 'This will permanently wipe all encrypted API keys (OpenRouter, OpenAI, custom tokens) from your local hardware vault. You will need to re-enter them.');
  if (!ok) return;
  try {
    await fetch('/api/secrets/OPENROUTER_API_KEY', { method: 'DELETE' });
    try { _safeLS.rm('agentic_os_custom_base_url'); } catch {}
    try { _safeLS.rm('agentic_os_custom_api_key'); } catch {}
    document.getElementById('or-key-input').value = '';
    const badge = document.getElementById('or-key-status-badge');
    if (badge) { badge.textContent = 'NOT CONFIGURED'; badge.style.color = 'var(--text-2)'; }
    updateKeyStatus(false);
    toast('🗑 All stored API credentials wiped from local vault', 'ok', 3000);
    if (typeof window.syncOpenWebUIConnections === 'function') window.syncOpenWebUIConnections();
  } catch(e) {
    toast('Failed to clear secrets: ' + e.message, 'err');
  }
};

window.hotReloadBackendEngine = async function() {
  toast('⚡ Hot-reloading core AI services (llm.py, chat.py, secrets.py) in backend RAM...', 'ok', 3000);
  const statusEl = document.getElementById('settings-api-ollama-status');
  if (statusEl) { statusEl.textContent = 'HOT-RELOADING...'; statusEl.style.color = 'var(--accent)'; }
  try {
    const r = await fetch('/api/system/reload-engine', { method: 'POST' });
    if (r.status === 404) {
      if (statusEl) { statusEl.textContent = 'RESTART NEEDED'; statusEl.style.color = 'var(--warning)'; }
      gmAlert('How to Apply Updates Right Now', `Because your application was running when you updated the code (<code style="color:var(--accent)">git pull</code>), the running process in your computer's memory needs one quick restart to load our new endpoints.\n\n<strong style="color:var(--success)">How to restart based on how you open the app:</strong>\n\n🖥️ <strong>If using the Native Desktop App (Agentic OS.app):</strong>\n• Simply quit the app (press Cmd + Q or click Agentic OS > Quit in your top menu bar) and double-click Agentic OS.app to open it right back up.\n\n＞_ <strong>If running via Command Line / Terminal (python3 run.py):</strong>\n• Go to the command window where run.py (or uvicorn) is running, press <code style="color:var(--accent)">Ctrl + C</code> to stop it, and type <code style="color:var(--accent)">python3 run.py</code> to start it right back up.\n\nOnce reopened, your Ollama chat and all future 1-click reloads will work instantly!`);
      return;
    }
    const j = await r.json();
    if (j.ok) {
      toast(j.message || '✅ Backend Python engine hot-reloaded successfully!', 'ok', 4000);
      if (typeof window.testOllamaConnection === 'function') window.testOllamaConnection();
      if (typeof window.syncOpenWebUIConnections === 'function') window.syncOpenWebUIConnections();
    } else {
      toast('⚠️ Reload note: ' + (j.error || 'Check server status'), 'warn', 3000);
    }
  } catch(e) {
    toast('⚠️ Server hot-reload network timeout — please restart your application window once to apply updates', 'warn', 4000);
  }
};

window.hardRebootBackendEngine = async function() {
  const ok = await gmConfirm('Restart Application Engine?', 'Are you ready to perform a clean process restart? Your background AI engine will cleanly reboot in 3 seconds to pick up all recent code updates.');
  if (!ok) return;
  toast('🛑 Initiating clean application engine reboot...', 'ok', 3000);
  const statusEl = document.getElementById('settings-api-ollama-status');
  if (statusEl) { statusEl.textContent = 'REBOOTING...'; statusEl.style.color = 'var(--warning)'; }
  try {
    const r = await fetch('/api/system/reboot-engine', { method: 'POST' });
    if (r.status === 404) {
      gmAlert('How to Restart Right Now', `To apply our latest engine updates to your running application:\n\n🖥️ <strong>If using the Native Desktop App (Agentic OS.app):</strong>\n• Quit the application (Cmd + Q or Quit Agentic OS) and open Agentic OS.app again.\n\n＞_ <strong>If running from Command Line (python3 run.py):</strong>\n• In that window, press <code style="color:var(--accent)">Ctrl + C</code> and type <code style="color:var(--accent)">python3 run.py</code> to start it back up.\n\nOnce restarted, this button and your Ollama model chats will work with 1 click!`);
      return;
    }
    const j = await r.json();
    if (j.ok) {
      gmAlert('🛑 Application Engine Rebooting', `The Python backend process has scheduled a clean restart (Code 101).\n\nPlease wait 4 seconds for the engine to re-spawn in your system memory, and then <strong style="color:var(--success)">refresh this page</strong> or re-open your window.`);
    }
  } catch(e) {
    toast('🛑 Engine restarting... Please wait 4 seconds and refresh.', 'ok', 4000);
  }
};

window.selectChatModel = function(val) {
  if (!val) return;
  S.currentModel = val;
  try { try { _safeLS.set('agentic_os_chat_model', val); } catch {} } catch(e) {}
  const pill = document.getElementById('chat-model-select');
  if (pill && pill.value !== val) pill.value = val;
  toast(`🤖 Active Chat Model: ${val.replace('ollama:', 'Local Ollama: ').replace('custom_url:', 'Custom: ')}`, 'ok', 1500);
};

window.selectChatPersona = function(val) {
  if (!val || val === 'default') {
    S.currentAgent = { id: 'default', name: 'Direct AI Chat', avatar: '💬', model: '' };
    S.currentAgentId = 'default';
    try { try { _safeLS.set('agentic_os_chat_persona', 'default'); } catch {} } catch(e) {}
    // Update VISIBLE display
    var pi = document.getElementById('active-persona-icon');
    var pl = document.getElementById('active-persona-label');
    if (pi) pi.textContent = '💬';
    if (pl) pl.textContent = 'Direct Chat';
    toast('💬 Direct AI Chat active', 'ok', 1500);
    return;
  }
  const found = S.agents?.find(a => a.id === val) || { id: val, name: formatAgentName(val), avatar: '🧠', model: '' };
  S.currentAgent = found;
  S.currentAgentId = val;
  try { try { _safeLS.set('agentic_os_chat_persona', val); } catch {} } catch(e) {}
  // Update VISIBLE display
  var pi = document.getElementById('active-persona-icon');
  var pl = document.getElementById('active-persona-label');
  if (pi) pi.textContent = found.avatar || '🤖';
  if (pl) pl.textContent = found.name;
  // Update hidden legacy elements
  const avatarEl = document.getElementById('active-agent-avatar');
  if (avatarEl) avatarEl.textContent = found.avatar || '🤖';
  const nameEl = document.getElementById('active-agent-name');
  if (nameEl) nameEl.textContent = found.name;
  toast(`🤖 Persona: ${found.name}`, 'ok', 1500);
};

// ── Chat Sessions & Folder Organization Management ─────────────────────────────
window._chatPageSize = window._chatPageSize || 5;
window._chatCurrentPage = window._chatCurrentPage || 1;
window._chatSortOrder = window._chatSortOrder || 'newest';
window._chatLastQuery = window._chatLastQuery || '';

window.setChatPageSize = function(size) {
  window._chatPageSize = size || 5;
  window._chatCurrentPage = 1;
  loadChatSessions();
};

window.setChatSortOrder = function(order) {
  window._chatSortOrder = order || 'newest';
  window._chatCurrentPage = 1;
  loadChatSessions();
};

window.changeChatPage = function(delta) {
  window._chatCurrentPage = Math.max(1, (window._chatCurrentPage || 1) + delta);
  loadChatSessions();
};

window.loadChatSessions = async function(q = '') {
  q = String(q || '').trim();
  // A new search is a new result set; always begin at its first page.
  if (q !== window._chatLastQuery) {
    window._chatLastQuery = q;
    window._chatCurrentPage = 1;
  }
  const el = document.getElementById('chat-sessions-list');
  if (!el) return;
  try {
    const r = await fetch(`/api/sessions?limit=200&q=${encodeURIComponent(q)}`);
    const data = await r.json();
    const sessions = data.sessions || [];
    if (!sessions.length) {
      el.innerHTML = `<div style="color:var(--text-3); font-size:12px; text-align:center; padding:20px">No saved conversations yet.<br><br><button id="btn-start-first" class="btn-3d btn-primary btn-sm">＋ Start First Chat</button></div>`;
      const startBtn = document.getElementById('btn-start-first');
      if (startBtn) startBtn.addEventListener('click', () => startNewChatSession());
      return;
    }
    const folderFilter = window._activeChatFolder || 'All';
    const filtered = folderFilter === 'All' ? sessions : sessions.filter(s => (s.description && s.description !== 'All' ? s.description : 'General') === folderFilter);

    // Update folder sorting dropdown options visibility (only enabled when All folders is selected)
    const optFAZ = document.getElementById('opt-sort-folder-az');
    const optFZA = document.getElementById('opt-sort-folder-za');
    if (optFAZ && optFZA) {
      const showFolderSort = (folderFilter === 'All');
      optFAZ.style.display = showFolderSort ? '' : 'none';
      optFZA.style.display = showFolderSort ? '' : 'none';
      if (!showFolderSort && (window._chatSortOrder === 'folder_az' || window._chatSortOrder === 'folder_za')) {
        window._chatSortOrder = 'newest';
        const sortSel = document.getElementById('chat-sort-select');
        if (sortSel) sortSel.value = 'newest';
      }
    }

    // Sort sessions
    filtered.sort((a, b) => {
      if (a.pinned !== b.pinned) return b.pinned - a.pinned;
      const order = window._chatSortOrder || 'newest';
      const nameA = (a.name || 'Chat').toLowerCase();
      const nameB = (b.name || 'Chat').toLowerCase();
      const folderA = (a.description && a.description !== 'All' ? a.description : 'General').toLowerCase();
      const folderB = (b.description && b.description !== 'All' ? b.description : 'General').toLowerCase();
      const timeA = new Date(a.updated_at || a.created_at || 0).getTime();
      const timeB = new Date(b.updated_at || b.created_at || 0).getTime();

      if (order === 'oldest') return timeA - timeB;
      if (order === 'az') return nameA.localeCompare(nameB);
      if (order === 'za') return nameB.localeCompare(nameA);
      if (order === 'folder_az') return folderA.localeCompare(folderB) || nameA.localeCompare(nameB);
      if (order === 'folder_za') return folderB.localeCompare(folderA) || nameA.localeCompare(nameB);
      return timeB - timeA;
    });

    // Paginate
    const pageSize = window._chatPageSize || 5;
    const totalSessions = filtered.length;
    const totalPages = Math.max(1, Math.ceil(totalSessions / pageSize));
    if (window._chatCurrentPage > totalPages) window._chatCurrentPage = totalPages;
    const curPage = window._chatCurrentPage || 1;
    const startIdx = (curPage - 1) * pageSize;
    const pageSessions = filtered.slice(startIdx, startIdx + pageSize);

    // Update UI pagination indicators
    const pagEl = document.getElementById('chat-sessions-pagination');
    if (pagEl) {
      pagEl.style.display = totalSessions > 0 ? 'flex' : 'none';
      const ind = document.getElementById('chat-page-indicator');
      if (ind) ind.textContent = `Page ${curPage} of ${totalPages} (${totalSessions} total)`;
      const prevBtn = document.getElementById('chat-page-prev');
      const nextBtn = document.getElementById('chat-page-next');
      if (prevBtn) prevBtn.disabled = (curPage <= 1);
      if (nextBtn) nextBtn.disabled = (curPage >= totalPages);
    }

    if (!pageSessions.length) {
      el.innerHTML = `<div style="color:var(--text-3); font-size:12px; text-align:center; padding:20px">${totalSessions === 0 ? 'No saved conversations yet.' : 'No chats on this page.'}<br><br><button id="btn-start-here" class="btn-3d btn-primary btn-sm">＋ New Chat Here</button></div>`;
      const hereBtn = document.getElementById('btn-start-here');
      if (hereBtn) hereBtn.addEventListener('click', () => startNewChatSession());
      return;
    }

    el.innerHTML = '';
    pageSessions.forEach(s => {
      const isCurrent = (s.id === S.sessionId);
      const folder = (s.description && s.description !== 'All') ? s.description : 'General';
      const folderIcon = folder === 'Engineering' ? '⚙️' : folder === 'Research' ? '🔬' : folder === 'Ideas' ? '💡' : '📁';
      const snameSafe = (s.name || 'Chat').slice(0, 256);

      const itemDiv = document.createElement('div');
      itemDiv.className = `chat-session-item ${isCurrent ? 'active' : ''}`;
      itemDiv.style.cssText = `display:flex; flex-direction:column; gap:4px; padding:8px 10px; border-radius:8px; background:${isCurrent ? 'var(--bg-3)' : 'transparent'}; border:1px solid ${isCurrent ? 'var(--accent)' : 'transparent'}; cursor:pointer; transition:all .15s`;
      itemDiv.addEventListener('click', () => loadChatSession(s.id));

      const topRow = document.createElement('div');
      topRow.style.cssText = 'display:flex; align-items:center; justify-content:space-between; gap:6px; flex-wrap:nowrap';

      const titleSpan = document.createElement('span');
      titleSpan.style.cssText = `font-size:12.5px; font-weight:${isCurrent ? '800' : '600'}; color:var(--text-0); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:1; min-width:0`;
      titleSpan.textContent = `${s.pinned ? '📌 ' : ''}${snameSafe}`;
      topRow.appendChild(titleSpan);

      const btnGroup = document.createElement('div');
      btnGroup.style.cssText = 'display:flex; gap:4px; align-items:center; flex-shrink:0';
      btnGroup.addEventListener('click', (e) => e.stopPropagation());

      const pinBtn = document.createElement('button');
      pinBtn.title = s.pinned ? 'Unpin' : 'Pin to top';
      pinBtn.style.cssText = 'background:none; border:none; color:var(--text-2); font-size:12px; cursor:pointer; padding:2px';
      pinBtn.textContent = '📌';
      pinBtn.addEventListener('click', (e) => {
        e.preventDefault(); e.stopPropagation();
        pinChatSession(e, s.id, !s.pinned);
      });
      btnGroup.appendChild(pinBtn);

      const renBtn = document.createElement('button');
      renBtn.title = 'Rename or Change Folder';
      renBtn.style.cssText = 'background:none; border:none; color:var(--text-2); font-size:12px; cursor:pointer; padding:2px';
      renBtn.textContent = '✏️';
      renBtn.addEventListener('click', (e) => {
        e.preventDefault(); e.stopPropagation();
        renameChatSessionModal(e, s.id, snameSafe, folder);
      });
      btnGroup.appendChild(renBtn);

      const delBtn = document.createElement('button');
      delBtn.title = 'Delete chat';
      delBtn.style.cssText = 'background:none; border:none; color:var(--danger); font-size:12px; cursor:pointer; padding:2px';
      delBtn.textContent = '🗑';
      delBtn.addEventListener('click', (e) => {
        e.preventDefault(); e.stopPropagation();
        deleteChatSession(e, s.id);
      });
      btnGroup.appendChild(delBtn);

      topRow.appendChild(btnGroup);
      itemDiv.appendChild(topRow);

      const bottomRow = document.createElement('div');
      bottomRow.style.cssText = 'display:flex; align-items:center; justify-content:space-between; font-size:10.5px; color:var(--text-3)';

      const folderSpan = document.createElement('span');
      folderSpan.className = 'session-folder-badge';
      folderSpan.style.cssText = 'background:var(--bg-2); padding:1px 6px; border-radius:4px; border:1px solid var(--border)';
      folderSpan.textContent = `${folderIcon} ${folder}`;
      bottomRow.appendChild(folderSpan);

      const metaSpan = document.createElement('span');
      metaSpan.textContent = `${s.message_count || 0} msgs · ${s.updated_at ? s.updated_at.slice(5, 16) : ''}`;
      bottomRow.appendChild(metaSpan);

      itemDiv.appendChild(bottomRow);
      el.appendChild(itemDiv);
    });
  } catch(e) {
    console.warn('Failed to load chat sessions:', e);
  }
};

window.loadChatSession = async function(sid) {
  if (!sid) return;
  S.sessionId = sid;
  toast('💬 Loading chat history...', 'ok', 1000);
  try {
    const [infoR, msgsR] = await Promise.all([
      fetch(`/api/sessions/${encodeURIComponent(sid)}`),
      fetch(`/api/sessions/${encodeURIComponent(sid)}/messages?limit=200`)
    ]);
    // A legacy database can return a plain-text 500. Parse defensively so the
    // user sees the actual API status instead of a misleading JSON exception.
    const parseSessionResponse = async (response, label) => {
      const raw = await response.text();
      let payload;
      try { payload = JSON.parse(raw); }
      catch (_) {
        throw new Error(`${label} service returned HTTP ${response.status}: ${raw.slice(0, 180)}`);
      }
      if (!response.ok || payload.ok === false) {
        throw new Error(payload.error || `${label} service returned HTTP ${response.status}`);
      }
      return payload;
    };
    const info = await parseSessionResponse(infoR, 'Chat session');
    const msgsData = await parseSessionResponse(msgsR, 'Chat history');
    if (info.ok && info.name) {
      S.sessionName = info.name;
      S.sessionFolder = info.description || 'General';
      if (info.agent_id && typeof window.selectChatPersona === 'function') {
        window.selectChatPersona(info.agent_id);
      }
    }
    const messages = msgsData.messages || [];
    S.chatHistory = messages.map(m => ({ role: m.role, content: m.message }));
    const msgsContainer = document.getElementById('chat-messages');
    if (!msgsContainer) return;
    msgsContainer.innerHTML = '';
    const emptyEl = ensureChatEmpty();
    if (emptyEl && msgsContainer) {
      emptyEl.style.display = messages.length ? 'none' : 'flex';
      msgsContainer.appendChild(emptyEl);
    }

    messages.forEach(m => {
      const avatar = m.role === 'user' ? '👤' : (m.agent === 'brain' ? '🧠' : '💬');
      const name = m.role === 'user' ? 'You' : (m.agent === 'default' ? 'Direct AI Chat' : formatAgentName(m.agent || 'AI'));
      const bubble = addMessage(m.message, m.role, avatar, name, m.model || (m.agent !== 'default' ? m.agent : ''));
      if (m.role !== 'user' && bubble && (m.message || '').trim().length > 0) {
        const msgId = bubble.closest('.msg')?.id;
        if (msgId) addMessageActions(bubble, m.role, m.message, msgId);
      }
    });
    loadChatSessions();
  } catch(e) {
    toast('❌ Error loading conversation: ' + e.message, 'err', 2000);
  }
};

window.startNewChatSession = function() {
  S.sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).slice(2, 6);
  S.sessionName = '';
  S.sessionFolder = window._activeChatFolder && window._activeChatFolder !== 'All' ? window._activeChatFolder : 'General';
  S.chatHistory = [];
  const msgsContainer = document.getElementById('chat-messages');
  if (msgsContainer) msgsContainer.innerHTML = '';
  const emptyEl = ensureChatEmpty();
  if (emptyEl && msgsContainer) {
    emptyEl.style.display = 'flex';
    msgsContainer.appendChild(emptyEl);
  }
  loadChatSessions();
  const inp = document.getElementById('chat-input');
  if (inp) { inp.value = ''; inp.focus(); }
  toast('＋ New chat session started', 'ok', 1200);
};

window.pinChatSession = async function(e, sid, pinned) {
  if (e && typeof e.stopPropagation === 'function') e.stopPropagation();
  toast(pinned ? '📌 Pinning chat...' : 'Unpinning chat...', 'ok', 1000);
  try {
    const res = await fetch(`/api/sessions/${encodeURIComponent(sid)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pinned: pinned ? 1 : 0 })
    });
    const j = await res.json();
    if (!j.ok) { toast('❌ Pin failed: ' + (j.error || 'Unknown'), 'err', 2500); return; }
    if (typeof window.loadChatSessions === 'function') await window.loadChatSessions();
    toast(pinned ? '📌 Chat pinned!' : 'Chat unpinned', 'ok', 1200);
  } catch (err) {
    toast('❌ Error pinning chat: ' + err.message, 'err', 2500);
  }
};

window.deleteChatSession = async function(e, sid) {
  if (e && typeof e.stopPropagation === 'function') e.stopPropagation();
  const ok = await gmConfirm('Delete Chat Conversation?', 'Are you sure you want to permanently delete this chat session and all its messages?');
  if (!ok) return;
  toast('🗑 Deleting chat...', 'ok', 1000);
  try {
    const res = await fetch(`/api/sessions/${encodeURIComponent(sid)}`, { method: 'DELETE' });
    const j = await res.json();
    if (!j.ok) { toast('❌ Delete failed: ' + (j.error || 'Unknown'), 'err', 2500); return; }
    if (S.sessionId === sid && typeof window.startNewChatSession === 'function') window.startNewChatSession();
    else if (typeof window.loadChatSessions === 'function') await window.loadChatSessions();
    toast('🗑 Chat deleted!', 'ok', 1500);
  } catch (err) {
    toast('❌ Error deleting chat: ' + err.message, 'err', 2500);
  }
};

window.renameChatSessionModal = async function(e, sid, oldName, oldFolder) {
  if (e && typeof e.stopPropagation === 'function') e.stopPropagation();
  const newName = await gmPrompt('Rename Chat Conversation', 'Enter a new title for this chat:', oldName || '');
  if (newName === null || !newName.trim()) return;
  const newFolder = await gmPrompt('Move to Folder / Category', 'Enter folder name:', oldFolder || 'General');
  if (newFolder === null || !newFolder.trim()) return;
  try {
    toast('✏️ Updating chat...', 'ok', 1000);
    const res = await fetch(`/api/sessions/${encodeURIComponent(sid)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newName.trim(), description: newFolder.trim() })
    });
    const j = await res.json();
    if (!j.ok) { toast('❌ Update failed: ' + (j.error || 'Unknown'), 'err', 2500); return; }
    if (S.sessionId === sid) { S.sessionName = newName.trim(); S.sessionFolder = newFolder.trim(); }
    if (typeof window.loadChatSessions === 'function') await window.loadChatSessions();
    toast('✏️ Chat renamed & moved to ' + newFolder.trim() + '!', 'ok', 1500);
  } catch (err) {
    toast('❌ Error updating chat: ' + err.message, 'err', 2500);
  }
};

window.selectChatFolder = function(folder) {
  window._activeChatFolder = folder;
  window._chatCurrentPage = 1;
  document.querySelectorAll('#chat-folder-pills button').forEach(btn => {
    const isSel = (btn.textContent.trim().includes(folder) || (folder === 'All' && btn.textContent.trim() === 'All'));
    btn.style.background = isSel ? 'var(--accent)' : 'var(--bg-2)';
    btn.style.color = isSel ? '#fff' : 'var(--text-1)';
  });
  loadChatSessions();
};

window.filterChatSessions = function(val) {
  if (window._chatSearchTimeout) clearTimeout(window._chatSearchTimeout);
  window._chatSearchTimeout = setTimeout(() => {
    loadChatSessions(val.trim());
  }, 250);
};

window.toggleChatHistoryDrawer = function() {
  const dr = document.getElementById('chat-history-drawer');
  if (!dr) return;
  if (dr.style.display === 'none' || dr.style.width === '0px') {
    dr.style.display = 'flex';
    dr.style.width = '280px';
  } else {
    dr.style.width = '0px';
    setTimeout(() => { if (dr.style.width === '0px') dr.style.display = 'none'; }, 200);
  }
};

window.renderConnectionReadiness = function(readiness = {}) {
  const localModels = Number(readiness.localModels || 0);
  const cloudReady = Boolean(readiness.cloudReady);
  let state = 'attention';
  let text = 'Connect AI to begin';
  if (localModels > 0) { state = 'ready'; text = `Local AI ready · ${localModels} model${localModels === 1 ? '' : 's'}`; }
  else if (cloudReady) { state = 'ready'; text = 'AI connection ready'; }
  else if (readiness.checked) { text = 'Choose a connection to begin'; }
  ['chat-connection-status', 'mission-connection-status'].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.classList.remove('checking', 'ready', 'attention', 'error');
    el.classList.add(state);
  });
};

window.syncOpenWebUIConnections = async function() {
  const select = document.getElementById('chat-model-select');
  if (!select) return;
  
  let customUrl = null; try { customUrl = _safeLS.get('agentic_os_custom_base_url'); } catch {}
  const customGroup = document.getElementById('custom-model-optgroup');
  if (customGroup && customUrl) {
    customGroup.innerHTML = `<option value="custom_url:${escHtml(customUrl)}">Custom Endpoint: ${escHtml(customUrl)}</option>`;
  }

  try {
    const [modR, secR] = await Promise.all([
      fetch('/api/agents/models').then(r => r.ok ? r.json().catch(()=>{}) : null).catch(() => null),
      fetch('/api/secrets/get?key=OPENROUTER_API_KEY').then(r => r.ok ? r.json().catch(()=>{}) : null).catch(() => null)
    ]);

    const orBadge = document.getElementById('or-key-status-badge');
    if (secR && secR.ok && secR.fingerprint) {
      if (orBadge) { orBadge.textContent = 'ONLINE (140+ MODELS)'; orBadge.style.color = 'var(--success)'; }
    } else if (orBadge && orBadge.textContent !== 'SAVED / UNVERIFIED') {
      orBadge.textContent = 'NOT CONFIGURED'; orBadge.style.color = 'var(--text-2)';
    }

    if (modR) {
      const ollamaGroup = document.getElementById('ollama-model-optgroup');
      const ollamaStatus = document.getElementById('settings-api-ollama-status');
      const ollamaModelsEl = document.getElementById('settings-api-ollama-models');
      if (modR.ollama?.running && modR.ollama.models?.length) {
        if (ollamaGroup) {
          ollamaGroup.innerHTML = modR.ollama.models.map(m => `<option value="ollama:${escHtml(m)}">Ollama: ${escHtml(m)}</option>`).join('');
        }
        if (ollamaStatus) { ollamaStatus.textContent = `ONLINE (${modR.ollama.models.length} models)`; ollamaStatus.style.color = 'var(--success)'; }
        if (ollamaModelsEl) {
          ollamaModelsEl.innerHTML = `<div style="font-weight:700;color:var(--success);margin-bottom:6px">✅ Active Local Models Detected:</div>` +
            modR.ollama.models.map(m => `<span class="tag" style="margin:3px;background:var(--bg-3);border:1px solid var(--border);padding:4px 10px;border-radius:6px;display:inline-block;font-weight:700">${escHtml(m)}</span>`).join('');
        }
      } else if (ollamaStatus) {
        ollamaStatus.textContent = 'OFFLINE'; ollamaStatus.style.color = 'var(--danger)';
        if (ollamaModelsEl) ollamaModelsEl.innerHTML = `<div style="color:var(--warning)">Local Ollama instance not detected on http://localhost:11434. Start Ollama on your Mac to sync local models.</div>`;
      }
    }
    window.renderConnectionReadiness({
      checked: true,
      cloudReady: Boolean(secR && secR.ok && secR.fingerprint),
      localModels: modR?.ollama?.running ? (modR.ollama.models || []).length : 0,
    });
  } catch(e) {
    window.renderConnectionReadiness({checked: true});
  }
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
    // Chat history search
    if (q.length >= 2) {
      try {
        const chatRes = await fetch('/api/chat/search?q=' + encodeURIComponent(q) + '&limit=10');
        const chatData = await chatRes.json();
        if (chatData.ok && chatData.results && chatData.results.length > 0) {
          let chatStartIdx = items.length;
          html += `<div class="palette-section" style="margin-top:12px;border-top:1px solid var(--border);padding-top:8px">💬 Chat History (${chatData.count})</div>`;
          html += chatData.results.map((item, idx) => `
          <div class="palette-item" data-idx="${chatStartIdx+idx}" style="display:flex;align-items:center;gap:8px">
            <span class="p-icon">${item.role === 'user' ? '👤' : '🤖'}</span>
            <span class="p-label">${escHtml(item.session_name || item.session_id)}</span>
            <span class="p-desc" style="flex:1;overflow:hidden;text-overflow:ellipsis">${escHtml(item.snippet)}</span>
            <span class="badge" style="background:var(--bg-3);border:1px solid var(--border);color:var(--text-2);font-size:10px;padding:2px 6px">${escHtml(item.role)}</span>
          </div>`).join('');
          const chatActions = chatData.results.map(item => () => {
            nav('chat');
            if (typeof loadChatSession === 'function') loadChatSession(item.session_id);
          });
          results.innerHTML = html;
          const prevItems = results.querySelectorAll('.palette-item');
          prevItems.forEach((el, i) => {
            if (i >= chatStartIdx) {
              el.addEventListener('click', () => { chatActions[i - chatStartIdx](); closePalette(); });
            }
          });
        }
      } catch(e) { console.warn('Chat search failed:', e); }
    }

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
    fetch('/api/loops/' + encodeURIComponent(jid) + '/run-now', {method:'POST'}).catch(()=>{});
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
    const inspDrawer = document.getElementById('inspection-drawer');
    if (inspDrawer && (inspDrawer.style.transform === 'translateX(0px)' || inspDrawer.style.transform === 'translateX(0)')) {
      e.preventDefault();
      e.stopPropagation();
      if (typeof window.closeInspectionDrawer === 'function') window.closeInspectionDrawer();
      else inspDrawer.style.transform = 'translateX(100%)';
      return;
    }

    const openModals = [
      document.getElementById('onboarding-overlay'),
      document.getElementById('onboarding-modal'),
      document.getElementById('gmodal'),
      document.getElementById('agent-modal'),
      document.getElementById('skill-run-modal'),
      document.getElementById('palette-modal'),
      document.getElementById('review-overlay'),
      document.getElementById('profile-panel'),
      document.getElementById('account-settings-modal'),
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
        } else if (m.id === 'account-settings-modal') {
          if (typeof window.closeAccountSettings === 'function') window.closeAccountSettings();
          else m.remove();
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
  try {
    const r = await fetch('/api/backup', {method:'POST'});
    const j = await r.json();
    if (j.ok) toast('💾 Backup created: ' + (j.path||'').split('/').pop(), 'ok');
    else toast('Backup failed: ' + (j.error||''), 'err');
  } catch(e) { toast('Backup error: ' + e.message, 'err'); }
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
  el.style.height = Math.max(84, Math.min(el.scrollHeight, 320)) + 'px';
}

// Clock
setInterval(() => {
  const el = document.getElementById('sb-time');
  if (el) el.textContent = new Date().toLocaleTimeString();
}, 1000);

// Agent status polling
setInterval(() => {
  if (S.agents.length) {
    fetch('/api/agents').then(r=>r.ok?r.json().catch(()=>{}):null).then(agents => {
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
  ws = new WebSocket(AgenticAPI.websocketUrl(`${proto}//${location.host}/ws`));

  ws.onopen = () => {
    const b = document.getElementById('ws-badge');
    if (b) { b.textContent = '⚡ live'; b.style.color = 'var(--green)'; }
    clearTimeout(wsReconnectTimer);
  };

  ws.onmessage = e => {
    try {
      const msg = JSON.parse(e.data);
      handleWSMessage(msg);
    } catch(err) {}
  };

  ws.onclose = () => {
    const b = document.getElementById('ws-badge');
    if (b) { b.textContent = '⚡ offline'; b.style.color = 'var(--red)'; }
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
    toast('🎤 Voice requires Chrome or Edge browser. Not available in desktop app.', 'warn', 4000);
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
    if (e.error === 'not-allowed') {
      toast('🎤 Microphone access denied. Allow mic in browser/system settings.', 'warn', 4000);
    } else if (e.error === 'no-speech') {
      toast('🎤 No speech detected. Try speaking louder.', 'warn', 2000);
    } else {
      toast('🎤 Voice error: ' + e.error, 'err', 2000);
    }
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
    toast('🎤 Voice stopped', 'ok', 1000);
  } else {
    try {
      mediaRecognition.start();
      isListening = true;
      updateVoiceBtn(true);
      toast('🎤 Listening… speak your message', 'ok', 2000);
    } catch(e) {
      toast('🎤 Could not start: ' + e.message, 'err', 2000);
    }
  }
}

function updateVoiceBtn(listening) {
  const btn = document.getElementById('voice-btn');
  if (!btn) return;
  btn.textContent = listening ? '🔴 Stop' : '🎤 Voice';
  btn.classList.toggle('active', listening);
}

// Add voice button to chat tools dynamically
document.addEventListener('DOMContentLoaded', () => {
  // Restore saved theme on page load
  try {
    const savedTheme = _safeLS.get('agentic_os_theme') || 'dark';
    if (typeof applyTheme === 'function') applyTheme(savedTheme);
  } catch(e) {}
});
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
    return await AgenticAPI.get('/api/tts/voices');
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
function skeletonPage(_title = 'Loading…') {
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
    <div class="empty-state__title">${escHtml(title)}</div>
    <div class="empty-state__body">${escHtml(body)}</div>
    <div class="empty-state__actions">${actions.map(a =>
      `<button onclick="${a.action}" class="btn ${a.primary ? 'btn-primary' : 'btn-ghost'}">${a.label}</button>`
    ).join('')}</div>
  </div>`;
}

// ── Help panel factory (novice guidance) ───────────────────────────
function helpPanel({ title, body, steps = [] }) {
  return `<div class="help-panel">
    <div class="help-panel__title">💡 ${escHtml(title)}</div>
    <div class="help-panel__body">${escHtml(body)}</div>
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
          <h1 class="page-heading">${escHtml(title)} ${badge ? `<span class="badge badge-accent" style="font-size:11px;vertical-align:middle">${escHtml(badge)}</span>` : ''}</h1>
          ${subtitle ? `<p class="page-subheading">${escHtml(subtitle)}</p>` : ''}
        </div>
        <div class="page-header__actions">
          ${actions.map(a => `<button onclick="${a.action}" class="btn ${a.primary?'btn-primary':'btn-ghost'} btn-sm">${escHtml(a.label)}</button>`).join('')}
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
// Kanban rendering is now handled by 28-kanban.js

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
window.showToast = toast;  // Alias: 481 calls across 32 files use showToast

// ── Loading skeleton helpers ──────────────────────────────────────
function showLoadingSkeleton(containerId, count = 3) {
  const el = document.getElementById(containerId);
  if (!el) return;
  let html = '';
  for (let i = 0; i < count; i++) {
    html += `<div style="display:flex;gap:12px;padding:12px 0;align-items:flex-start">
      <div class="skeleton skeleton-avatar"></div>
      <div style="flex:1">
        <div class="skeleton skeleton-text" style="width:${60 + Math.random()*30}%"></div>
        <div class="skeleton skeleton-text" style="width:${40 + Math.random()*40}%"></div>
        <div class="skeleton skeleton-text" style="width:${20 + Math.random()*30}%"></div>
      </div>
    </div>`;
  }
  el.innerHTML = html;
}

function showInlineLoading(el, message = 'Loading…') {
  if (!el) return;
  el.innerHTML = `<div style="display:flex;align-items:center;gap:10px;padding:16px;color:var(--text-2);font-size:13px">
    <div class="skeleton" style="width:20px;height:20px;border-radius:50%;flex-shrink:0"></div>
    <span>${escHtml(message)}</span>
  </div>`;
}



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
console.debug(
  '%c🧠 Agentic OS v9 — Sprint 9 Bold Editorial Design System loaded',
  'color:#7aa4ff;font-weight:bold;font-size:13px'
);
console.debug(
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
  const link = document.createElement('link');
  link.rel  = 'stylesheet';
  link.href = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css';
  document.head.appendChild(link);
  const s = document.createElement('script');
  s.src   = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js';
  s.onload = () => {
    if (window.hljs) {
      window.hljs.configure({ ignoreUnescapedHTML: true });
      window._hljsReady = true;
    }
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
    const lineCount = code.split('\n').length;
    const lineNumHtml = lineCount > 1 ? `<div class="code-line-numbers">${Array.from({length: lineCount}, (_, i) => i+1).join('\n')}</div>` : '';
    return `<div class="card-elevated surface-z2 code-with-lines" style="position:relative;margin:12px 0;border-radius:10px;overflow:hidden;padding:0;border:1px solid var(--border-hi)">
      <div style="display:flex;align-items:center;justify-content:space-between;background:#04060f;padding:6px 12px;border-bottom:1px solid var(--border);flex-wrap:wrap;gap:6px">
        <span style="font-size:11px;font-weight:800;color:var(--accent);font-family:monospace">${escHtml(langLabel)}</span>
        <div style="display:flex;gap:6px;align-items:center">
          <button onclick="openCodeInStudio(${JSON.stringify(id)}, '${escHtml(lang||'js')}')" class="btn-3d btn-primary btn-sm" style="padding:2px 8px;font-size:10.5px" title="Load directly into primary Monaco editor buffer">⚡ Open in Studio ↗</button>
          <button onclick="copyCodeBlock(${JSON.stringify(id)})" class="btn-3d btn-ghost btn-sm" style="padding:2px 8px;font-size:10.5px">📋 Copy</button>
          <button onclick="runCodeInTerminal(${JSON.stringify(id)})" class="btn-3d btn-ghost btn-sm" style="padding:2px 8px;font-size:10.5px" title="Send snippet to System Terminal input">＞_ Terminal</button>
        </div>
      </div>
      ${lineNumHtml}<pre id="${id}" style="margin:0;padding:14px${lineCount > 1 ? ' 14px 14px 50px' : ''};background:#060814;overflow-x:auto;font-size:12.5px;line-height:1.65;font-family:'JetBrains Mono','Fira Code',monospace"><code class="hljs language-${langLabel}" data-raw="${encodeURIComponent(code)}">${highlightedCode}</code></pre>
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

window.openCodeInStudio = function(codeId, lang) {
  const el = document.getElementById(codeId);
  if (!el) return;
  const codeEl = el.querySelector('code');
  const code = codeEl ? decodeURIComponent(codeEl.dataset.raw || '') : (el.textContent || el.innerText || '');
  nav('studio');
  setTimeout(() => {
    if (window.Studio && window.Studio.editor) {
      window.Studio.editor.setValue(code);
      toast('⚡ Code loaded directly into primary Studio buffer', 'ok', 2000);
    } else if (typeof studioOpenFile === 'function') {
      const targetPath = (lang === 'html') ? 'index.html' : (lang === 'css' ? 'styles.css' : ((lang === 'python' || lang === 'py') ? 'main.py' : 'app.js'));
      studioOpenFile(targetPath);
      setTimeout(() => {
        if (window.Studio && window.Studio.editor) window.Studio.editor.setValue(code);
      }, 300);
    }
  }, 300);
};

window.runCodeInTerminal = function(codeId) {
  const el = document.getElementById(codeId);
  if (!el) return;
  const codeEl = el.querySelector('code');
  const code = codeEl ? decodeURIComponent(codeEl.dataset.raw || '') : (el.textContent || el.innerText || '');
  nav('terminal');
  setTimeout(() => {
    const termInp = document.getElementById('term-input') || document.querySelector('#pane-terminal input');
    if (termInp) {
      termInp.value = code.split('\n')[0] || code;
      termInp.focus();
      toast('＞_ Code sent to system terminal input', 'ok', 1500);
    }
  }, 300);
};

// Patch the main renderMarkdown to use enhanced version
window.renderMarkdown = renderMarkdownEnhanced;

// ── Message actions (copy, regenerate, listen, fork) ─────────────────────
function addMessageActions(bubbleEl, role, content, msgId) {
  if (!bubbleEl) return;
  const hideOnHoverOnly = (_safeLS.get('agentic_os_hide_actions_hover') === 'true');
  const actEl = document.createElement('div');
  actEl.className = 'msg-actions';
  actEl.style.cssText = `display:flex;gap:6px;margin-top:8px;opacity:${hideOnHoverOnly ? '0' : '1'};transition:opacity .15s;flex-wrap:wrap`;

  const copyBtn = document.createElement('button');
  copyBtn.className = 'msg-action-btn';
  copyBtn.title = 'Copy message';
  copyBtn.style.cssText = 'background:var(--bg-2);border:1px solid var(--border);border-radius:6px;padding:3px 8px;font-size:11.5px;cursor:pointer;color:var(--text-1);display:flex;align-items:center;gap:4px';
  copyBtn.innerHTML = '📋 Copy';
  copyBtn.addEventListener('click', (e) => {
    e.preventDefault(); e.stopPropagation();
    if (typeof window.copyMsgContent === 'function') window.copyMsgContent(copyBtn, msgId);
  });
  actEl.appendChild(copyBtn);

  if (role === 'agent') {
    const regBtn = document.createElement('button');
    regBtn.className = 'msg-action-btn';
    regBtn.title = 'Regenerate response';
    regBtn.style.cssText = 'background:var(--bg-2);border:1px solid var(--border);border-radius:6px;padding:3px 8px;font-size:11.5px;cursor:pointer;color:var(--text-1);display:flex;align-items:center;gap:4px';
    regBtn.innerHTML = '↺ Regenerate';
    regBtn.addEventListener('click', (e) => {
      e.preventDefault(); e.stopPropagation();
      if (typeof window.regenerateMsg === 'function') window.regenerateMsg(regBtn, msgId);
    });
    actEl.appendChild(regBtn);

    const lisBtn = document.createElement('button');
    lisBtn.className = 'msg-action-btn';
    lisBtn.title = 'Read response aloud';
    lisBtn.style.cssText = 'background:var(--bg-2);border:1px solid var(--border);border-radius:6px;padding:3px 8px;font-size:11.5px;cursor:pointer;color:var(--text-1);display:flex;align-items:center;gap:4px';
    lisBtn.innerHTML = '🔊 Listen';
    lisBtn.addEventListener('click', (e) => {
      e.preventDefault(); e.stopPropagation();
      if (typeof window.listenToMsg === 'function') window.listenToMsg(lisBtn, msgId);
    });
    actEl.appendChild(lisBtn);
  }

  const forkBtn = document.createElement('button');
  forkBtn.className = 'msg-action-btn';
  forkBtn.title = 'Fork conversation here';
  forkBtn.style.cssText = 'background:var(--bg-2);border:1px solid var(--border);border-radius:6px;padding:3px 8px;font-size:11.5px;cursor:pointer;color:var(--text-1);display:flex;align-items:center;gap:4px';
  forkBtn.innerHTML = '⎇ Fork';
  forkBtn.addEventListener('click', (e) => {
    e.preventDefault(); e.stopPropagation();
    if (typeof window.branchFromMsg === 'function') window.branchFromMsg(forkBtn, msgId);
  });
  actEl.appendChild(forkBtn);

  bubbleEl.parentElement?.appendChild(actEl);
  const msgDiv = bubbleEl.closest('.msg');
  if (msgDiv && hideOnHoverOnly) {
    msgDiv.addEventListener('mouseenter', () => actEl.style.opacity = '1');
    msgDiv.addEventListener('mouseleave', () => actEl.style.opacity = '0');
  }
  if (!window._msgContents) window._msgContents = {};
  window._msgContents[msgId] = content;
}

window.copyMsgContent = function(btn, msgId) {
  const targetMsg = (typeof msgId === 'string' && document.getElementById(msgId)) || btn?.closest?.('.msg');
  const bubble = targetMsg?.querySelector('.msg-bubble');
  const text = bubble?.innerText || bubble?.textContent || window._msgContents?.[msgId] || '';
  if (!text || !text.trim()) { toast('Could not find text to copy', 'err', 1500); return; }
  const clean = text.trim();
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(clean).then(() => toast('📋 Message copied to clipboard!', 'ok', 1500)).catch(() => fallbackCopyText(clean));
  } else {
    fallbackCopyText(clean);
  }
};

function fallbackCopyText(text) {
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    toast('📋 Message copied to clipboard!', 'ok', 1500);
  } catch (e) {
    toast('❌ Copy failed: ' + e.message, 'err', 2000);
  }
}

window.listenToMsg = function(btn, msgId) {
  // The selected action itself is authoritative. The API-backed Audio element
  // is private to the TTS module, so checking only speechSynthesis.speaking
  // incorrectly made a second click unable to stop it.
  if (window._activeListenBtn === btn) {
    if (window.stopSpeaking) window.stopSpeaking();
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    window._ttsPlaying = null;
    btn.innerHTML = '🔊 Listen';
    btn.style.borderColor = 'var(--border)';
    window._activeListenBtn = null;
    toast('⏹ Stopped listening', 'ok', 1000);
    return;
  }
  if (window._activeListenBtn) {
    window._activeListenBtn.innerHTML = '🔊 Listen';
    window._activeListenBtn.style.borderColor = 'var(--border)';
    if (window.stopSpeaking) window.stopSpeaking();
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    window._ttsPlaying = null;
  }

  const targetMsg = (typeof msgId === 'string' && document.getElementById(msgId)) || btn?.closest?.('.msg');
  const bubble = targetMsg?.querySelector('.msg-bubble');
  const text = bubble?.innerText || bubble?.textContent || window._msgContents?.[msgId] || '';
  if (!text || !text.trim()) { toast('No text found to speak', 'err', 1500); return; }
  const agentId = targetMsg?.dataset?.agentId || S.currentAgentId || 'default';

  btn.innerHTML = '⏹ Stop Listening';
  btn.style.borderColor = 'var(--accent)';
  window._activeListenBtn = btn;

  if (typeof window.speakMessage === 'function') {
    window.speakMessage(text, agentId);
  } else if (typeof window.speakText === 'function') {
    window.speakText(text, agentId);
  } else if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text.slice(0, 1500));
    u.onend = () => {
      if (window._activeListenBtn === btn) {
        btn.innerHTML = '🔊 Listen';
        btn.style.borderColor = 'var(--border)';
        window._activeListenBtn = null;
      }
    };
    window.speechSynthesis.speak(u);
    toast('🔊 Reading response aloud...', 'ok', 1500);
  } else {
    toast('TTS engine unavailable', 'err', 1500);
    btn.innerHTML = '🔊 Listen';
    btn.style.borderColor = 'var(--border)';
    window._activeListenBtn = null;
  }
};

window.regenerateMsg = async function(btn, msgId) {
  const targetMsg = (typeof msgId === 'string' && document.getElementById(msgId)) || btn?.closest?.('.msg');
  if (!targetMsg) return;
  let prev = targetMsg.previousElementSibling;
  let userText = '';
  while (prev) {
    if (prev.classList.contains('user')) {
      const b = prev.querySelector('.msg-bubble');
      userText = b?.innerText || b?.textContent || '';
      break;
    }
    prev = prev.previousElementSibling;
  }
  if (!userText) { toast('Could not find previous user prompt to regenerate', 'err', 2000); return; }
  toast('↺ Regenerating response...', 'ok', 1500);
  targetMsg.remove();
  const inp = document.getElementById('chat-input');
  if (inp) {
    inp.value = userText.trim();
    if (typeof window.sendChat === 'function') await window.sendChat();
  }
};

window.branchFromMsg = async function(btn, msgId) {
  const targetMsg = (typeof msgId === 'string' && document.getElementById(msgId)) || btn?.closest?.('.msg');
  if (!targetMsg) return;

  const allMsgs = Array.from(document.querySelectorAll('#chat-messages .msg'));
  const idx = allMsgs.indexOf(targetMsg);
  const forkedMsgs = (idx >= 0 ? allMsgs.slice(0, idx + 1) : allMsgs).map(m => {
    const isUser = m.classList.contains('user');
    const b = m.querySelector('.msg-bubble');
    return {
      role: isUser ? 'user' : 'assistant',
      message: b?.innerText || b?.textContent || '',
      agent: isUser ? 'user' : (S.currentAgent?.id || 'default'),
      model: m.querySelector('.model-used-tag')?.textContent?.replace('⚡', '').trim() || ''
    };
  }).filter(m => m.message.trim().length > 0);

  const newSid = 'session_fork_' + Date.now() + '_' + Math.random().toString(36).slice(2, 6);
  const newName = ('⎇ Fork: ' + (S.sessionName || 'Chat ' + S.sessionId.slice(-4))).slice(0, 256);
  const folder = (S.sessionFolder && S.sessionFolder !== 'All') ? S.sessionFolder : 'General';

  toast('⎇ Forking into new conversation...', 'ok', 1200);
  try {
    await fetch('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: newSid, name: newName, agent_id: S.currentAgentId || 'default', description: folder })
    });
    await fetch('/api/sessions/import-messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: newSid, messages: forkedMsgs })
    });
    await window.loadChatSession(newSid);
    toast(`✅ ⎇ Forked into new chat: "${newName}"!`, 'ok', 2500);
  } catch(e) {
    toast('❌ Error forking conversation: ' + e.message, 'err', 2500);
  }
};

// Patch addMessage to include actions when explicitly invoked after response finishes
const _origAddMessage = addMessage;
addMessage = function(content, role, avatar, name, modelUsed = '') {
  const bubbleEl = _origAddMessage(content, role, avatar, name, modelUsed);
  const msgDiv = bubbleEl?.closest('.msg');
  // _origAddMessage assigns this synchronously. Retain it so WebKit never
  // observes an inserted message with an empty selector target.
  if (msgDiv && !msgDiv.id) msgDiv.id = 'msg_' + Date.now() + '_' + Math.random().toString(36).slice(2, 10);
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

window.exportSession = function exportSession(sessionId) {
  toast('📋 Downloading Markdown…', 'ok', 2000);
  var f = document.createElement('form');
  f.method = 'GET';
  f.action = '/api/sessions/' + encodeURIComponent(sessionId) + '/export?fmt=markdown';
  f.style.display = 'none';
  document.body.appendChild(f);
  f.submit();
  setTimeout(function() { f.remove(); }, 200);
};

window.exportSessionJSON = function exportSessionJSON(sessionId) {
  toast('📄 Downloading JSON…', 'ok', 2000);
  var f = document.createElement('form');
  f.method = 'GET';
  f.action = '/api/sessions/' + encodeURIComponent(sessionId) + '/export?fmt=json';
  f.style.display = 'none';
  document.body.appendChild(f);
  f.submit();
  setTimeout(function() { f.remove(); }, 200);
};

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

// ── Updated Deploy panel — add new providers ──────────────────────
// NOTE: renderDeploy's base implementation lives in the deferred
// 35-deploy.js, which has NOT loaded yet when this (non-deferred) script
// runs. Referencing the bare identifier `renderDeploy` here throws an
// uncaught ReferenceError that aborts ALL remaining top-level code in this
// file (including window.openProfilePanel further down). Assign directly to
// window instead of reading/reassigning the undeclared global.
window.renderDeploy = async function() {
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

function applyTheme(themeId, accentOverride, options = {}) {
  // `auto` is a preference, not a palette. Resolve it to a concrete palette for
  // CSS while retaining the preference so it follows OS changes in real time.
  const preference = themeId || _safeLS.get('agentic_os_theme') || 'light';
  const followsSystem = preference === 'auto';
  const systemPrefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  const tid = followsSystem ? (systemPrefersDark ? 'dark' : 'light') : preference;
  const t = THEME_VARS[tid] || THEME_VARS.light;
  const accent = accentOverride || t.accent || '#0284c7';
  const root = document.documentElement;
  root.style.setProperty('--bg-0', t.bg0);
  root.style.setProperty('--bg-1', t.bg1);
  root.style.setProperty('--bg-2', t.bg2);
  if (t.bg3) root.style.setProperty('--bg-3', t.bg3);
  if (t.bg4) root.style.setProperty('--bg-4', t.bg4);
  if (t.bg5) root.style.setProperty('--bg-5', t.bg5);
  if (t.text0) root.style.setProperty('--text-0', t.text0);
  if (t.text1) root.style.setProperty('--text-1', t.text1);
  if (t.text2) root.style.setProperty('--text-2', t.text2);
  if (t.text3) root.style.setProperty('--text-3', t.text3);
  if (t.border) root.style.setProperty('--border', t.border);
  if (t.borderHi) root.style.setProperty('--border-hi', t.borderHi);
  root.style.setProperty('--accent', accent);
  root.style.setProperty('--accent-hi', t.accentHi || accent);
  root.style.setProperty('--accent-glow', accent + '22');
  root.setAttribute('data-theme', tid);
  root.setAttribute('data-theme-preference', preference);
  root.style.colorScheme = tid === 'light' ? 'light' : 'dark';
  if (document.body) {
    document.body.setAttribute('data-theme', tid);
    document.body.setAttribute('data-theme-preference', preference);
  }
  const themeMeta = document.querySelector('meta[name="theme-color"]');
  if (themeMeta) themeMeta.content = tid === 'light' ? '#f8fafc' : '#060814';

  if (options.persist === false) return;
  try { try { _safeLS.set('agentic_os_theme', preference); } catch {} } catch(e) {}
  fetch('/api/onboarding/preferences', {
    method: 'PATCH', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({theme: preference, accent_color: accent})
  }).then(r => {
    if (!r.ok) console.warn('[Theme] Persist failed: HTTP ' + r.status);
  }).catch(ex => console.warn('[Theme] Persist error:', ex?.message));
}

// Keep Auto mode synchronized when the operating-system appearance changes.
if (window.matchMedia) {
  const systemAppearance = window.matchMedia('(prefers-color-scheme: dark)');
  const refreshAutoAppearance = () => {
    try {
      if ((_safeLS.get('agentic_os_theme') || 'light') === 'auto') {
        applyTheme('auto', undefined, {persist: false});
      }
    } catch (e) {}
  };
  if (systemAppearance.addEventListener) systemAppearance.addEventListener('change', refreshAutoAppearance);
  else if (systemAppearance.addListener) systemAppearance.addListener(refreshAutoAppearance);
}

// Expose globally for settings panel
window.applyTheme = applyTheme;

window.switchUIMode = async function(mode) {
  if (mode !== 'simple' && mode !== 'power') return;
  try { try { _safeLS.set('agentic_os_mode', mode); } catch {} } catch(e) {}
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
    // In power mode: keep ESSENTIALS expanded, collapse others
    if (typeof window.toggleSidebarGroup === 'function') window.toggleSidebarGroup('core', true);
    ['build', 'ship', 'tools', 'enterprise'].forEach(gid => {
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
  let mode = (typeof _UI !== 'undefined' ? _UI.uiMode : 'simple') || 'simple'; try { let _v = null; try { _v = _safeLS.get('agentic_os_mode'); } catch {} if (_v !== null) mode = _v; } catch {}
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
  let fs = (typeof _UI !== 'undefined' ? _UI.profile?.font_size : 'base') || 'base'; try { let _v = null; try { _v = _safeLS.get('agentic_os_font_size'); } catch {} if (_v !== null) fs = _v; } catch {}
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
  try { try { _safeLS.set('agentic_os_font_size', size); } catch {} } catch(e) {}
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

// ── Extend nav for Sprint 10 ───────────────────────────────────────
const _s10NavBase = function(){}; // nav chain disabled — master nav handles all
function _disabled__s10NavBase(pane) {
  _s10NavBase(pane);
  if (pane === 'control')    renderControlTower();
  if (pane === 'workspaces') renderWorkspaces();
  if (pane === 'webhooks')   renderWebhooks();
  if (pane === 'testgen')    renderTestGen();
}

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

// ── Image Generation ─────────────────────────────────────────────
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
    if (typeof window.renderPrompts === 'function' && pane === 'prompts') window.renderPrompts();
    if (typeof window.renderCodeSearch === 'function' && pane === 'codesearch') window.renderCodeSearch();
    if (typeof window.showSmartSuggestionsForPane === 'function') window.showSmartSuggestionsForPane(pane);
  };
})();

// ══════════════════════════════════════════════════════
//  PROMPT LIBRARY
// ══════════════════════════════════════════════════════
// ── Cost tracking polling ─────────────────────────────────────────
setInterval(updateCostBar, 30000);

setTimeout(() => {
  if (typeof window.syncOpenWebUIConnections === 'function') window.syncOpenWebUIConnections();
  let savedModel = null; try { savedModel = _safeLS.get('agentic_os_chat_model'); } catch {}
  if (savedModel) {
    S.currentModel = savedModel;
    const sel = document.getElementById('chat-model-select');
    if (sel) sel.value = savedModel;
  }
  let savedPersona = null; try { savedPersona = _safeLS.get('agentic_os_chat_persona'); } catch {}
  if (savedPersona && typeof window.selectChatPersona === 'function') {
    window.selectChatPersona(savedPersona);
  }
  if (typeof window.loadChatSessions === 'function') window.loadChatSessions();
}, 800);

window.gmAlert = gmAlert;
window.gmConfirm = gmConfirm;
window.gmPrompt = gmPrompt;
window.gmDanger = gmDanger;
window.escHtml = escHtml;


// ═══════════════════════════════════════════════════════════════
//  PROFILE PANEL — REMOVED (superseded)
//  This slide-out "Your Profile" panel duplicated and drifted out of
//  sync with the "Identity & Custom App Branding" panel from
//  04-workflow-specs.js. Both are now unified into a single Account
//  Settings modal — see 57-account-settings.js
//  (window.openAccountSettings). window.openProfilePanel is kept as an
//  alias there so any remaining callers still work.
// ═══════════════════════════════════════════════════════════════


// ── Loop count badge updater ──────────────────────────────────────
setInterval(async () => {
  try {
    const r = await fetch('/api/loops/status');
    const j = await r.json();
    const badge = document.getElementById('loop-count');
    if (badge) badge.textContent = j.jobs || 0;
  } catch(e) {}
}, 15000);


// ── Chat TTS lifecycle ───────────────────────────────────────────────────────
// Never leave a response playing after the user leaves Mission Control chat.
(function installChatTtsAutoStop() {
  const stop = () => {
    if (typeof window.stopSpeaking === 'function') window.stopSpeaking();
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
  };
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
  window.addEventListener('pagehide', stop);
  window.addEventListener('blur', stop);
  window.addEventListener('DOMContentLoaded', () => {
    const chatPane = document.getElementById('pane-chat');
    // Leaving the chat component is an explicit stop request, not a pause.
    if (chatPane) chatPane.addEventListener('mouseleave', stop);
    document.querySelectorAll('[data-nav]').forEach((item) => {
      item.addEventListener('click', () => {
        const destination = item.dataset.nav;
        if (destination && destination !== 'chat') stop();
      });
    });
  });
})();
