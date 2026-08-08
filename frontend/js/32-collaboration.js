// Agentic OS — Collaboration
// Extracted from 01-app-core.js for modularity
// ── Collaboration ─────────────────────────────────────────────────
let collabWS = null, collabSessionId = null, collabPeerId = null;

async function startCollab() {
  // Create a new session
  const r = await fetch('/api/collab/sessions', { method:'POST' });
  const j = await r.json();
  if (!j.ok) { toast('Failed to create collab session', 'err'); return; }

  const url = `${location.origin}/?collab=${j.session_id}`;
  await gmAlert('🤝 Collaboration Session Created',
    `<div class="u-761d3add">Share this URL with collaborators:</div>
     <code style="background:var(--bg-0);padding:8px 12px;border-radius:var(--radius-sm);display:block;font-size:12px;word-break:break-all">${url}</code>
     <div style="margin-top:10px;font-size:12px;color:var(--text-2)">They'll see your cursor, navigation, and can chat in real-time.</div>`
  );

  joinCollabSession(j.session_id);
}

function joinCollabSession(sessionId) {
  if (collabWS) { collabWS.close(); }
  collabSessionId = sessionId;

  const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  collabWS = new WebSocket(AgenticAPI.websocketUrl(`${wsProto}//${location.host}/api/collab/sessions/${sessionId}/ws`));

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
fetch('/api/onboarding/preferences').then(r=>r.ok?r.json().catch(()=>{}):{}).then(p=>{
  if (!p) return;
  S.preferences = p;
  applyPreferences(p);
}).catch(()=>{});




// ═══════════════════════════════════════════════════════════════
//  SPRINT 10 — Control Tower, Workspaces, Webhooks, Test Gen,
//              Notification Center
// ═══════════════════════════════════════════════════════════════

