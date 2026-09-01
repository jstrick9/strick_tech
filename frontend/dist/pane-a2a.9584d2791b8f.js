
;/* 52-a2a.js */
(function(S, nav, toast, escHtml, fetch, document) {
let _a2aTab        = 'network';
let _a2aAgents     = [];
let _a2aLocalAgents= [];
let _a2aTasks      = [];
let _a2aStats      = null;
let _a2aSelected   = null;
async function renderA2A() {
const pane = document.getElementById('pane-a2a');
if (!pane) return;
pane.innerHTML = `
  

  <div class="a2a-root">
    <!-- Sidebar -->
    <div class="a2a-sidebar">
      <div class="a2a-sidebar-title">A2A Network</div>
      <div class="a2a-nav active" id="a2a-nav-network" data-act-click="a2aSetTab('network')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
        <span class="a2a-nav-icon">🌐</span> Agent Network
      </div>
      <div class="a2a-nav" id="a2a-nav-tasks" data-act-click="a2aSetTab('tasks')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
        <span class="a2a-nav-icon">📋</span> Tasks
        <span class="a2a-badge" id="a2a-task-badge" style="display:none">0</span>
      </div>
      <div class="a2a-nav" id="a2a-nav-cards" data-act-click="a2aSetTab('cards')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
        <span class="a2a-nav-icon">🪪</span> Agent Cards
      </div>
      <div class="a2a-div"></div>
      <div class="a2a-nav" data-act-click="a2aOpenRegister()" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
        <span class="a2a-nav-icon">➕</span> Register Agent
      </div>
      <div class="a2a-nav" data-act-click="a2aOpenDelegate()" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
        <span class="a2a-nav-icon">📤</span> Delegate Task
      </div>
    </div>

    <!-- Main -->
    <div class="a2a-main">
      <div class="a2a-header">
        <span class="a2a-header-title" id="a2a-header-title">🌐 A2A Agent Network</span>
        <button class="a2a-btn" data-act-click="a2aRefresh()">↺ Refresh</button>
        <button class="a2a-btn primary" data-act-click="a2aOpenDelegate()">📤 Delegate Task</button>
      </div>
      <div class="a2a-content" id="a2a-content">
        <div style="color:var(--text-3);padding:20px">Loading…</div>
      </div>
    </div>
  </div>`;
await a2aRefresh();
}
async function a2aRefresh() {
const [agentsR, tasksR, statsR] = await Promise.all([
fetch('/api/a2a/agents').then(r=>r.ok?r.json():{agents:[],local_agents:[]}).catch(()=>({agents:[],local_agents:[]})),
fetch('/api/a2a/tasks?limit=50').then(r=>r.ok?r.json():{tasks:[]}).catch(()=>({tasks:[]})),
fetch('/api/a2a/stats').then(r=>r.ok?r.json():{}).catch(()=>({})),
]);
_a2aAgents      = agentsR.agents      || [];
_a2aLocalAgents = agentsR.local_agents|| [];
_a2aTasks       = tasksR.tasks        || [];
_a2aStats       = statsR;
const active = _a2aTasks.filter(t=>!['completed','failed','canceled'].includes(t.state)).length;
const badge  = document.getElementById('a2a-task-badge');
if (badge) { badge.textContent=active; badge.style.display=active>0?'inline-flex':'none'; }
a2aRenderTab();
}
function a2aSetTab(tab) {
_a2aTab = tab;
document.querySelectorAll('.a2a-nav[id^="a2a-nav-"]').forEach(el => {
el.classList.toggle('active', el.id === 'a2a-nav-' + tab);
});
const titles = {
network:'🌐 A2A Agent Network',
tasks:  '📋 A2A Tasks',
cards:  '🪪 Agent Cards (A2A v1.0)',
};
const h = document.getElementById('a2a-header-title');
if (h) h.textContent = titles[tab] || 'A2A Network';
a2aRenderTab();
}
function a2aRenderTab() {
const c = document.getElementById('a2a-content');
if (!c) return;
if (_a2aTab === 'network') a2aRenderNetwork(c);
if (_a2aTab === 'tasks')   a2aRenderTasks(c);
if (_a2aTab === 'cards')   a2aRenderCards(c);
}
function a2aRenderNetwork(container) {
const s = _a2aStats || {};
const trustColors = {local:'#3dba7a',verified:'#5b8af8',unverified:'#e8a237',blocked:'#e85252'};
const statusIcons = {active:'🟢',unverified:'🟡',unreachable:'🔴',blocked:'⛔'};
const stats = [
{val:s.registered_agents||0, lbl:'Registered', col:'var(--accent)'},
{val:s.active_agents||0,     lbl:'Active',     col:'var(--success)'},
{val:s.local_agents||0,      lbl:'Local',      col:'#3dba7a'},
{val:s.total_tasks||0,       lbl:'Tasks Run',  col:'#9d74f5'},
{val:s.inbound_calls||0,     lbl:'Inbound',    col:'var(--accent)'},
{val:s.outbound_calls||0,    lbl:'Outbound',   col:'var(--warning)'},
];
const allAgents = [..._a2aAgents];
const selectedAgent = _a2aSelected ? allAgents.find(a=>a.agent_id===_a2aSelected) : null;
container.innerHTML = `
    <!-- Stats -->
    <div class="a2a-stats-grid">
      ${stats.map(s=>`<div class="a2a-stat"><div class="a2a-stat-val" style="color:${s.col}">${s.val}</div><div class="a2a-stat-lbl">${s.lbl}</div></div>`).join('')}
    </div>

    <!-- Protocol explanation -->
    <div style="background:rgba(91,138,248,.06);border:1px solid rgba(91,138,248,.2);border-radius:10px;padding:12px 14px;margin-bottom:16px">
      <div style="font-size:12px;font-weight:700;color:var(--accent-text);margin-bottom:6px">🌐 A2A Protocol v1.0 — Agent-to-Agent</div>
      <div style="font-size:11px;color:var(--text-2);line-height:1.6">
        Every agent exposes a signed <strong>Agent Card</strong> at <code class="u-1b6531f7">/.well-known/agent.json</code> and a
        <strong>JSON-RPC 2.0 endpoint</strong> at <code class="u-1b6531f7">/a2a/{id}</code>.<br>
        External platforms (Google ADK, LangChain, Strick Tech Swarm Framework, Microsoft Agent Framework) can delegate tasks to this platform via <code>tasks/send</code> or stream updates via <code>tasks/sendSubscribe</code>.
      </div>
      <div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap">
        <a href="/.well-known/agent.json" target="_blank" class="a2a-btn">🪪 Platform Card</a>
        <a href="/a2a/orchestrator/card" target="_blank" class="a2a-btn">🎯 Orchestrator Card</a>
        <button class="a2a-btn" data-act-click="a2aSetTab('cards')">View All Cards →</button>
      </div>
    </div>

    <!-- Registered agents -->
    <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px">
      Registered Agents (${allAgents.length})
    </div>
    <div class="a2a-agent-grid">
      ${allAgents.map(ag => {
        const tc  = trustColors[ag.trust_level] || '#7a8aaa';
        const si  = statusIcons[ag.status] || '❓';
        const skills = ag.skills || [];
        const caps   = ag.capabilities || [];
        const isLocal= ag.trust_level === 'local';
        return `<div class="a2a-agent-card ${_a2aSelected===ag.agent_id?'selected':''}" data-act-click="a2aSelectAgent(${jsArg(ag.agent_id)})" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
          <div class="a2a-agent-head">
            <span class="a2a-agent-icon">${isLocal?'🏠':ag.status==='active'?'🌐':'🔌'}</span>
            <div class="a2a-agent-body">
              <div class="a2a-agent-name">${escHtml(ag.name)}</div>
              <div class="a2a-agent-url">${escHtml(ag.a2a_url)}</div>
            </div>
            <span class="a2a-trust-badge" style="background:${tc}22;color:${tc}">${si} ${ag.trust_level}</span>
          </div>
          <div style="font-size:11px;color:var(--text-2);margin-bottom:6px;line-height:1.4">${escHtml((ag.description||'').slice(0,80))}</div>
          <div class="a2a-skills">
            ${skills.slice(0,4).map(s=>`<span class="a2a-skill">${escHtml(typeof s==='object'?s.name:s)}</span>`).join('')}
            ${skills.length>4?`<span class="a2a-skill">+${skills.length-4} more</span>`:''}
          </div>
          ${caps.length?`<div class="a2a-caps">⚡ ${caps.slice(0,3).join(' · ')}</div>`:''}
          <div class="a2a-agent-actions">
            <button class="a2a-btn" data-act-click="a2aDelegateToAgent(${jsArg(ag.agent_id)})" data-stop="1">📤 Delegate</button>
            ${!isLocal?`<button class="a2a-btn" data-act-click="a2aVerifyAgent(${jsArg(ag.agent_id)})" data-stop="1">🔍 Verify</button>`:''}
            ${!isLocal?`<button class="a2a-btn" data-act-click="a2aDeleteAgent(${jsArg(ag.agent_id)})" data-stop="1" style="color:var(--danger)">🗑</button>`:''}
          </div>
        </div>`;
      }).join('')}
      <!-- Add remote agent card -->
      <div class="a2a-agent-card" data-act-click="a2aOpenRegister()" style="border-style:dashed;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px;min-height:160px;opacity:.7" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
        <div class="u-d137430a">➕</div>
        <div style="font-size:12px;font-weight:600;color:var(--text-1)">Register Remote Agent</div>
        <div style="font-size:10px;color:var(--text-3);margin-top:4px;text-align:center">Connect to any A2A-compatible platform</div>
      </div>
    </div>

    <!-- Local agents section -->
    ${_a2aLocalAgents.length ? `
    <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.05em;margin:16px 0 10px">
      Local Agents — Available via A2A (${_a2aLocalAgents.length})
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:6px">
      ${_a2aLocalAgents.map(a=>`
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:8px;padding:8px 12px;cursor:pointer;font-size:11px;transition:all .12s" data-act-click="a2aViewLocalCard(${jsArg(a.agent_id)})" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
          <span style="font-weight:600;color:var(--text-0)">${escHtml(a.name)}</span>
          <span style="color:var(--text-3);margin-left:6px">${escHtml((a.description||'').slice(0,30))}</span>
          <a href="/a2a/${encodeURIComponent(a.agent_id)}/card" target="_blank" style="color:var(--accent-text);font-size:10px;margin-left:8px" data-stop="1">🪪</a>
        </div>`).join('')}
    </div>` : ''}
  `;
}
async function a2aRenderTasks(container) {
container.innerHTML = `<div style="color:var(--text-3);padding:20px">Loading…</div>`;
const d = await fetch('/api/a2a/tasks?limit=50').then(r=>r.ok?r.json():{tasks:[]}).catch(()=>({tasks:[]}));
_a2aTasks = d.tasks || [];
const stateColors = {
submitted:'var(--text-3)',working:'var(--warning)',
'input-required':'#9d74f5',completed:'var(--success)',
failed:'var(--danger)',canceled:'var(--text-3)',
};
if (!_a2aTasks.length) {
container.innerHTML = `<div style="padding:40px;text-align:center;color:var(--text-3)">
      <div class="u-da61af79">📋</div>
      <div style="font-size:14px;font-weight:600;color:var(--text-1);margin-bottom:8px">No A2A Tasks Yet</div>
      <div style="font-size:12px;line-height:1.6">Tasks appear here when external agents delegate work to this platform, or when you delegate tasks to remote agents.</div>
      <button class="a2a-btn primary u-d6f2af6e" data-act-click="a2aOpenDelegate()" >📤 Send Your First Task</button>
    </div>`;
return;
}
container.innerHTML = `
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;flex-wrap:wrap">
      <strong style="font-size:13px;color:var(--text-0)">${_a2aTasks.length} tasks</strong>
      <span style="font-size:11px;color:var(--text-3)">(inbound + outbound)</span>
      <button class="a2a-btn u-6d000617" data-act-click="hRenderA2ATasks()" >↺</button>
    </div>
    <table class="a2a-task-table">
      <thead><tr>
        <th>Task ID</th><th>Direction</th><th>Agent</th><th>State</th><th>Progress</th><th>Created</th><th>Actions</th>
      </tr></thead>
      <tbody>
        ${_a2aTasks.map(t => {
          const sc = stateColors[t.state] || 'var(--text-3)';
          const isOutbound = t.direction === 'outbound';
          return `<tr data-act-click="a2aViewTask(${jsArg(t.task_id)})" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
            <td style="font-family:monospace;font-size:10px;color:var(--text-3)">${t.task_id.slice(0,18)}…</td>
            <td class="u-0d5be05f">${isOutbound?'📤 outbound':'📥 inbound'}</td>
            <td style="color:var(--accent-text);font-size:11px">${escHtml(isOutbound?t.target_agent_id:t.target_agent_id)}</td>
            <td><span class="a2a-state" style="background:${sc}22;color:${sc}">${t.state}</span></td>
            <td class="u-0d5be05f">${t.progress_pct||0}%</td>
            <td style="font-size:10px;color:var(--text-3)">${new Date(t.created_at).toLocaleString()}</td>
            <td data-stop="1">
              ${!['completed','failed','canceled'].includes(t.state) ?
                `<button class="a2a-btn" data-act-click="a2aCancelTask(${jsArg(t.task_id)})" style="font-size:10px;color:var(--danger)">✕</button>` : ''}
            </td>
          </tr>`;
        }).join('')}
      </tbody>
    </table>
  `;
}
async function a2aRenderCards(container) {
const localIds = ['orchestrator','researcher','builder','reviewer','creative','brain','memory'];
const base = window.location.origin;
container.innerHTML = `
    <div style="font-size:12px;color:var(--text-2);margin-bottom:14px;line-height:1.6">
      Each local agent exposes a signed <strong>A2A v1.0 Agent Card</strong> at two standard locations:
      <br>• <code class="u-1b6531f7">/a2a/{id}/.well-known/agent.json</code> (spec-compliant)
      <br>• <code class="u-1b6531f7">/a2a/{id}/card</code> (friendly alias)
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px;margin-bottom:16px">
      ${localIds.map(id => `
        <div class="a2a-detail-panel">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
            <div style="font-size:16px;font-weight:800;color:var(--text-0)">${id}</div>
            <span style="font-size:9px;padding:1px 7px;border-radius:4px;background:rgba(61,186,122,.15);color:#3dba7a">LOCAL</span>
            <div style="margin-left:auto;display:flex;gap:5px">
              <a href="/a2a/${id}/card" target="_blank" class="a2a-btn u-80d654f9" >🪪 View</a>
              <button class="a2a-btn" data-act-click="a2aShowCard(${jsArg(id)})">JSON</button>
            </div>
          </div>
          <div class="a2a-wk-url">${base}/a2a/${id}/.well-known/agent.json</div>
          <div style="font-size:10px;color:var(--text-3)">JSON-RPC endpoint: ${base}/a2a/${id}</div>
        </div>`).join('')}
    </div>
    <div class="a2a-detail-panel">
      <div class="a2a-detail-title">Platform Agent Card</div>
      <div class="a2a-wk-url">${base}/.well-known/agent.json</div>
      <div style="font-size:11px;color:var(--text-2);margin-bottom:8px">
        The platform-level card describes the full Agentic OS installation and lists all available agents.
        Any A2A-compatible platform (Google ADK, LangChain, Strick Tech Swarm Framework, Microsoft Agent Framework) can use this to discover and delegate tasks.
      </div>
      <a href="/.well-known/agent.json" target="_blank" class="a2a-btn primary" style="text-decoration:none;display:inline-flex">🪪 View Platform Card</a>
    </div>
  `;
}
async function a2aShowCard(agentId) {
const d = await fetch(`/a2a/${encodeURIComponent(agentId)}/card`)
.then(r=>r.ok?r.json():null).catch(()=>null);
if (!d) { showToast('⚠️ Could not load agent card'); return; }
const overlay = document.createElement('div');
overlay.className = 'a2a-modal-overlay';
overlay.innerHTML = `<div class="a2a-modal" style="max-width:720px;max-height:80vh;overflow-y:auto">
    <h3 style="margin:0 0 8px">🪪 A2A Agent Card — ${escHtml(agentId)}</h3>
    <p style="margin:0 0 10px;font-size:11px;color:var(--text-3)">Served at /a2a/${escHtml(agentId)}/.well-known/agent.json</p>
    <pre class="a2a-card-code">${escHtml(JSON.stringify(d, null, 2))}</pre>
    <div class="a2a-modal-row">
      <a href="/a2a/${encodeURIComponent(agentId)}/card" target="_blank" class="a2a-btn">Open in tab</a>
      <button class="a2a-btn" data-act-click="hCopyText(${jsArg(JSON.stringify(d,null,2))})">Copy JSON</button>
      <button class="a2a-btn primary" data-close="closest:.a2a-modal-overlay">Close</button>
    </div>
  </div>`;
overlay.onclick = e => { if(e.target===overlay) overlay.remove(); };
document.body.appendChild(overlay);
}
async function a2aViewLocalCard(agentId) {
_a2aTab = 'cards';
document.querySelectorAll('.a2a-nav[id^="a2a-nav-"]').forEach(el => el.classList.toggle('active', el.id==='a2a-nav-cards'));
await a2aRenderCards(document.getElementById('a2a-content'));
setTimeout(() => a2aShowCard(agentId), 100);
}
function a2aSelectAgent(agentId) {
_a2aSelected = agentId === _a2aSelected ? null : agentId;
a2aRenderNetwork(document.getElementById('a2a-content'));
}
function a2aDelegateToAgent(agentId) {
_a2aSelected = agentId;
a2aOpenDelegate(agentId);
}
function a2aOpenDelegate(preselectedId) {
const existing = document.getElementById('a2a-delegate-modal');
if (existing) { existing.remove(); return; }
const allRemote = [..._a2aAgents.filter(a=>a.trust_level!=='local'), ..._a2aLocalAgents];
const options   = allRemote.map(a=>
`<option value="${escHtml(a.agent_id)}" ${a.agent_id===preselectedId?'selected':''}>${escHtml(a.name||a.agent_id)}</option>`
).join('');
const overlay = document.createElement('div');
overlay.id = 'a2a-delegate-modal';
overlay.className = 'a2a-modal-overlay';
overlay.innerHTML = `<div class="a2a-modal">
    <h3>📤 Delegate Task via A2A</h3>
    <p>Send a task to a remote A2A-compatible agent. The task is submitted via JSON-RPC 2.0 tasks/send and the result is returned when complete.</p>
    <div class="a2a-form-group">
      <label class="a2a-form-label">Target Agent *</label>
      <select class="a2a-select" id="a2a-del-agent">${options}</select>
    </div>
    <div class="a2a-form-group">
      <label class="a2a-form-label">Task Message *</label>
      <textarea class="a2a-textarea" id="a2a-del-message" placeholder="Describe what you want the remote agent to do…&#10;&#10;Example: Research the top 5 agentic AI frameworks in 2026 and write a brief comparison."></textarea>
    </div>
    <div class="a2a-form-group">
      <label class="a2a-form-label">Session ID (optional)</label>
      <input class="a2a-input" id="a2a-del-session" placeholder="For grouping related tasks">
    </div>
    <div class="a2a-modal-row">
      <button class="a2a-btn" data-close="id:a2a-delegate-modal">Cancel</button>
      <button class="a2a-btn primary" data-act-click="a2aSubmitDelegate()">📤 Send Task</button>
    </div>
  </div>`;
overlay.onclick = e => { if(e.target===overlay) overlay.remove(); };
document.body.appendChild(overlay);
setTimeout(() => document.getElementById('a2a-del-message')?.focus(), 50);
}
async function a2aSubmitDelegate() {
const agentId = document.getElementById('a2a-del-agent')?.value?.trim();
const message = document.getElementById('a2a-del-message')?.value?.trim();
const session = document.getElementById('a2a-del-session')?.value?.trim() || '';
if (!agentId || !message) { showToast('⚠️ Select an agent and enter a message'); return; }
document.getElementById('a2a-delegate-modal')?.remove();
showToast(`📤 Delegating task to ${agentId}…`);
const isLocal = _a2aLocalAgents.some(a=>a.agent_id===agentId);
let result;
if (isLocal) {
const r = await fetch(`/a2a/${encodeURIComponent(agentId)}`, {
method:'POST', headers:{'Content-Type':'application/json'},
body: JSON.stringify({
jsonrpc:'2.0', id:'ui-1', method:'tasks/send',
params:{
message:{role:'user',parts:[{type:'text',text:message}]},
sessionId: session || undefined,
}
})
}).catch(()=>null);
result = r ? await r.json() : null;
if (result?.result) {
showToast(`✅ Task completed: ${result.result.status?.state}`);
} else {
showToast('⚠️ Task submission failed (local): ' + (result?.error?.message || 'Unknown error'));
}
} else {
const r = await fetch('/api/a2a/delegate', {
method:'POST', headers:{'Content-Type':'application/json'},
body: JSON.stringify({agent_id:agentId, message, session_id:session})
}).catch(()=>null);
result = r ? await r.json() : null;
if (result?.ok) {
showToast(`✅ Task delegated: ${result.task_id}`);
} else {
showToast('ℹ️ Task sent (remote may be demo): ' + (result?.note || result?.error || ''));
}
}
await a2aRefresh();
a2aSetTab('tasks');
}
function a2aOpenRegister() {
const existing = document.getElementById('a2a-register-modal');
if (existing) { existing.remove(); return; }
const overlay = document.createElement('div');
overlay.id = 'a2a-register-modal';
overlay.className = 'a2a-modal-overlay';
overlay.innerHTML = `<div class="a2a-modal">
    <h3>➕ Register Remote A2A Agent</h3>
    <p>Connect to any A2A v1.0 compatible agent. After registering, click Verify to fetch its Agent Card and capabilities.</p>
    <div class="a2a-form-group">
      <label class="a2a-form-label">Agent Name *</label>
      <input class="a2a-input" id="a2a-reg-name" placeholder="e.g. LangChain Research Agent">
    </div>
    <div class="a2a-form-group">
      <label class="a2a-form-label">A2A Endpoint URL *</label>
      <input class="a2a-input" id="a2a-reg-url" placeholder="https://example.com/a2a/agent">
    </div>
    <div class="a2a-form-group">
      <label class="a2a-form-label">Description</label>
      <input class="a2a-input" id="a2a-reg-desc" placeholder="What this agent does">
    </div>
    <div class="a2a-form-group">
      <label class="a2a-form-label">Authentication</label>
      <select class="a2a-select" id="a2a-reg-auth" data-act-change="a2aToggleAuthFields()">
        <option value="none">None (public)</option>
        <option value="bearer">Bearer Token</option>
        <option value="api_key">API Key</option>
      </select>
    </div>
    <div id="a2a-auth-fields" style="display:none">
      <div class="a2a-form-group">
        <label class="a2a-form-label">Token / Key</label>
        <input class="a2a-input" id="a2a-reg-token" type="password" placeholder="sk-…">
      </div>
    </div>
    <div class="a2a-modal-row">
      <button class="a2a-btn" data-close="id:a2a-register-modal">Cancel</button>
      <button class="a2a-btn primary" data-act-click="a2aSubmitRegister()">➕ Register</button>
    </div>
  </div>`;
overlay.onclick = e => { if(e.target===overlay) overlay.remove(); };
document.body.appendChild(overlay);
setTimeout(() => document.getElementById('a2a-reg-name')?.focus(), 50);
}
function a2aToggleAuthFields() {
const auth = document.getElementById('a2a-reg-auth')?.value;
const fields = document.getElementById('a2a-auth-fields');
if (fields) fields.style.display = auth !== 'none' ? 'block' : 'none';
}
async function a2aSubmitRegister() {
const name     = document.getElementById('a2a-reg-name')?.value?.trim();
const url      = document.getElementById('a2a-reg-url')?.value?.trim();
const desc     = document.getElementById('a2a-reg-desc')?.value?.trim() || '';
const authType = document.getElementById('a2a-reg-auth')?.value || 'none';
const token    = document.getElementById('a2a-reg-token')?.value?.trim() || '';
if (!name || !url) { showToast('⚠️ Name and URL required'); return; }
document.getElementById('a2a-register-modal')?.remove();
const authConfig = authType !== 'none' && token ? {token, key: token} : {};
const r = await fetch('/api/a2a/agents', {
method:'POST', headers:{'Content-Type':'application/json'},
body: JSON.stringify({name, a2a_url:url, description:desc, auth_type:authType, auth_config:authConfig})
}).catch(()=>null);
const d = r ? await r.json() : {};
if (d.ok) {
showToast(`✅ Registered: ${name}`);
await a2aRefresh();
a2aVerifyAgent(d.agent_id);
} else {
showToast('⚠️ Registration failed: '+(d.error||''));
}
}
async function a2aVerifyAgent(agentId) {
showToast(`🔍 Verifying ${agentId}…`);
const r = await fetch(`/api/a2a/agents/${encodeURIComponent(agentId)}/verify`, {method:'POST'}).catch(()=>null);
const d = r ? await r.json() : {};
if (d.ok) {
showToast(`✅ Verified: ${d.card_name||agentId} (${d.skills_count} skills)`);
} else {
showToast(`ℹ️ ${agentId}: ${d.status} — ${d.error||'could not reach agent card URL'}`);
}
await a2aRefresh();
}
async function a2aDeleteAgent(agentId) {
const ok = await gmDanger('Remove Agent', `Remove "${agentId}" from the A2A registry?`);
if (!ok) return;
await fetch(`/api/a2a/agents/${encodeURIComponent(agentId)}`, {method:'DELETE'});
showToast('🗑 Agent removed');
await a2aRefresh();
}
async function a2aViewTask(taskId) {
const d = await fetch(`/api/a2a/tasks/${encodeURIComponent(taskId)}`).then(r=>r.ok?r.json():null).catch(()=>null);
if (!d || !d.ok) { showToast('Could not load task'); return; }
const t   = d.task || {};
const a2a = d.a2a_response || {};
const sv  = d.supervisor_run;
const msgs = (t.messages||[]).map(m => `[${m.role}] ${(m.parts||[]).map(p=>p.text||'').join('')}`).join('\n');
const arts = (t.artifacts||[]).map(a => `${a.name}: ${(a.parts||[]).map(p=>p.text||'').join('').slice(0,200)}`).join('\n');
await gmAlert(`📋 A2A Task: ${taskId.slice(0,20)}`,
`State: ${t.state}  |  Direction: ${t.caller_agent_id==='local'?'Outbound (we sent)':'Inbound (received)'}
Target Agent: ${t.target_agent_id}
Progress: ${t.progress_pct||0}%  |  Session: ${t.session_id||'—'}
Created: ${t.created_at}

Messages:
${msgs.slice(0,500) || '(none)'}

Artifacts:
${arts.slice(0,500) || '(none)'}

${sv ? `Supervisor Run: ${sv.run_id} (${sv.status}) score=${sv.eval_score||'—'}` : ''}
${t.error_message ? `Error: ${t.error_message}` : ''}`);
}
async function a2aCancelTask(taskId) {
const ok = await gmDanger('Cancel Task', `Cancel A2A task ${taskId.slice(0,20)}?`);
if (!ok) return;
const r = await fetch(`/api/a2a/tasks/${encodeURIComponent(taskId)}/cancel`, {method:'POST'}).catch(()=>null);
const d = r ? await r.json() : {};
showToast(d.ok ? `✅ Task canceled` : '⚠️ '+(d.error||'Failed'));
await a2aRefresh();
a2aSetTab('tasks');
}
window.renderA2A = renderA2A;
window.a2aCancelTask = a2aCancelTask;
window.a2aDelegateToAgent = a2aDelegateToAgent;
window.a2aDeleteAgent = a2aDeleteAgent;
window.a2aOpenDelegate = a2aOpenDelegate;
window.a2aOpenRegister = a2aOpenRegister;
window.a2aRefresh = a2aRefresh;
window.a2aSelectAgent = a2aSelectAgent;
window.a2aSetTab = a2aSetTab;
window.a2aShowCard = a2aShowCard;
window.a2aSubmitDelegate = a2aSubmitDelegate;
window.a2aSubmitRegister = a2aSubmitRegister;
window.a2aToggleAuthFields = a2aToggleAuthFields;
window.a2aVerifyAgent = a2aVerifyAgent;
window.a2aViewLocalCard = a2aViewLocalCard;
window.a2aViewTask = a2aViewTask;
})(S, nav, toast, escHtml, fetch, document);
