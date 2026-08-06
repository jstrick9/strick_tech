// Agentic OS — Swarm & DAG
// Extracted from 01-app-core.js for modularity
// ── Swarm & Live Directed Acyclic Graph (`DAG`) Canvas (`Phase 3`) ──
window._swarmViewMode = 'dag';

window.toggleSwarmViewMode = function() {
  window._swarmViewMode = (window._swarmViewMode === 'dag') ? 'grid' : 'dag';
  const dagEl = document.getElementById('swarm-dag-container');
  const gridEl = document.getElementById('sw-runs');
  const btn = document.getElementById('sw-view-toggle-btn');
  if (window._swarmViewMode === 'dag') {
    if (dagEl) dagEl.style.display = 'flex';
    if (gridEl) gridEl.style.display = 'none';
    if (btn) btn.innerHTML = '⚡ Switch to Grid View';
  } else {
    if (dagEl) dagEl.style.display = 'none';
    if (gridEl) gridEl.style.display = 'grid';
    if (btn) btn.innerHTML = '🕸️ Switch to DAG View';
  }
};

window.renderSwarmDAG = function(runs = [], winner = '', isRunning = false, activeAgents = [], prompt = '') {
  const dagHost = document.getElementById('swarm-dag-host');
  if (!dagHost) return;
  const agentMap = {};
  runs.forEach(r => { agentMap[r.agent] = r; });
  // BUG FIX: node click handlers used to be built as inline
  // onclick="...openInspectionDrawer({...})..." strings with agent name/role
  // text run only through escHtml() (HTML-entity escaping) but NOT
  // JS-string-escaping. Any agent name/role containing an apostrophe (e.g.
  // "O'Brien's Brain") broke the single-quoted JS string literal embedded in
  // the onclick attribute, throwing `Uncaught SyntaxError: Unexpected
  // identifier` on click and never opening the inspection drawer at all —
  // reproduced live by renaming the built-in "brain" agent to include an
  // apostrophe and clicking its DAG node. Fixed by keying each node's real
  // (unescaped) inspection-drawer payload in this side-table and wiring
  // real addEventListener click handlers after the HTML is inserted,
  // eliminating string-escaping entirely for this data path.
  const nodeInspectionData = {};

  const levels = [
    { title: 'Level 1: Orchestration & Task Decomposition', nodes: ['orchestrator'] },
    { title: 'Level 2: Architecture & Synthesis', nodes: ['brain', 'design_decomposer', 'builder'] },
    { title: 'Level 3: Verification & Red Teaming', nodes: ['visual_tester', 'functional_tester', 'test_creator'] },
    { title: 'Level 4: Consensus & Fusion Hub', nodes: ['judge_consensus'] }
  ];

  dagHost.innerHTML = `
    <div style="position:relative;width:100%;display:flex;flex-direction:column;gap:16px">
      ${levels.map((lvl, lIdx) => `
        <div style="display:flex;flex-direction:column;gap:6px">
          <div style="font-size:10.5px;font-weight:800;color:var(--text-3);text-transform:uppercase;letter-spacing:0.8px">${lvl.title}</div>
          <div style="display:flex;gap:12px;flex-wrap:wrap;justify-content:center">
            ${lvl.nodes.map(nid => {
              if (nid === 'judge_consensus') {
                const hasWinner = Boolean(winner);
                return `
                <div class="card-elevated ${hasWinner ? 'surface-z4' : 'surface-z2'}" style="flex:1;min-width:240px;border:${hasWinner ? '2px solid var(--accent)' : '1px solid var(--border)'};background:${hasWinner ? 'var(--accent-glow)' : 'var(--bg-1)'}">
                  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
                    <span class="u-1444c6ea">⚖️</span>
                    <span style="font-weight:800;font-size:13px;color:var(--text-0)">Judge Consensus Hub</span>
                    <span class="badge ${hasWinner ? 'badge-success' : 'badge-default'}">${hasWinner ? '✅ CONSENSUS REACHED' : 'AWAITING BRANCHES'}</span>
                  </div>
                  <div style="font-size:12px;color:var(--text-2);line-height:1.5">
                    ${hasWinner ? `Synthesized output from multi-agent fanout. Winner: <strong style="color:var(--text-0)">${escHtml(winner)}</strong> (${Math.round((runs[0]?.score || 0.96)*100)}% confidence).` : 'Evaluates candidate outputs and synthesizes top-2 recommendations.'}
                  </div>
                </div>`;
              }
              const isSelected = activeAgents.includes(nid);
              const runData = agentMap[nid];
              const nodeAgent = (S.agents || []).find(a => a.id === nid) || { name: nid, avatar: '🤖', role: 'Specialist Agent' };
              const statusStr = isRunning ? '● Computing...' : (runData ? `✅ ${runData.latency_ms}ms · ${runData.tokens}t` : (isSelected ? '⏳ Queued' : '○ Bypassed'));
              nodeInspectionData[nid] = {
                id: nid,
                title: `${nodeAgent.name} Workstation Node`,
                icon: nodeAgent.avatar || '🤖',
                tier: 'PRO',
                summary: `Role: ${nodeAgent.role || 'Specialist'}. ${runData ? 'Execution Output: ' + (runData.output || '') : 'Node in standby.'}`,
              };
              return `
              <div class="card-elevated ${runData ? 'surface-z3' : 'surface-z1'}" style="flex:1;min-width:170px;border:${runData?.agent === winner ? '2px solid #10b981' : (isRunning && isSelected ? '1px solid var(--accent)' : '1px solid var(--border)')};transition:all .15s;cursor:pointer"
                data-swarm-node-id="${escHtml(nid)}">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
                  <div style="display:flex;align-items:center;gap:6px">
                    <span class="u-4ff818ff">${nodeAgent.avatar||'🤖'}</span>
                    <span style="font-weight:800;font-size:12.5px;color:var(--text-0)">${escHtml(nodeAgent.name)}</span>
                  </div>
                  <span style="font-size:10px;padding:2px 6px;border-radius:4px;background:${runData ? 'rgba(16,185,129,0.15)' : (isRunning && isSelected ? 'var(--accent-glow)' : 'var(--bg-3)')};color:${runData ? '#10b981' : (isRunning && isSelected ? 'var(--accent)' : 'var(--text-3)')};font-weight:700">
                    ${statusStr}
                  </span>
                </div>
                <div style="font-size:11px;color:var(--text-2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                  ${runData ? escHtml((runData.output||'').slice(0, 70)) : escHtml(nodeAgent.role||'Ready')}
                </div>
              </div>`;
            }).join('')}
          </div>
        </div>
        ${lIdx < levels.length - 1 ? `<div style="text-align:center;color:var(--accent-text);font-size:14px;opacity:0.6;margin:-4px 0">↓ Conduit Data Stream</div>` : ''}
      `).join('')}
    </div>`;

  dagHost.querySelectorAll('[data-swarm-node-id]').forEach(el => {
    el.addEventListener('click', () => {
      const nid = el.dataset.swarmNodeId;
      const doc = nodeInspectionData[nid];
      if (doc && typeof openInspectionDrawer === 'function') openInspectionDrawer(doc);
    });
  });
};

function renderSwarm() {
  const pane = document.getElementById('pane-swarm');
  pane.innerHTML = `
    <div class="section-head">
      <div><h2>🌀 Multi-Agent Swarm & DAG Visualizer</h2><p>Fan-out across 7 specialist roles • Directed Acyclic Graph (DAG) consensus • fusion of top candidates</p></div>
      <div style="display:flex;gap:8px">
        <button data-act-click="toggleSwarmViewMode()" class="btn-3d btn-ghost btn-sm" id="sw-view-toggle-btn">⚡ Switch to Grid View</button>
        <button data-act-click="loadSwarmHistory()" class="btn-3d btn-ghost btn-sm">📜 History</button>
        <button data-act-click="toggleSplitWorkspace(true,'swarm')" class="btn-3d btn-ghost btn-sm">🗂️ Secondary Dock</button>
      </div>
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
          <button data-act-click="runSwarm()" class="btn btn-primary" style="width:100%;margin-top:12px" id="sw-run-btn">🚀 Run Swarm</button>
          <div id="sw-status" style="font-size:12px;color:var(--text-2);margin-top:8px;min-height:18px"></div>
        </div>
      </div>
      <div style="overflow-y:auto;max-height:calc(100vh - 160px);display:flex;flex-direction:column">
        <div id="swarm-dag-container" class="card-elevated surface-z2" style="margin-bottom:16px;min-height:380px;display:flex;flex-direction:column">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--border)">
            <span style="font-weight:800;font-size:13px;color:var(--accent-text)">🕸️ Directed Acyclic Graph (DAG) Network</span>
            <span class="badge badge-accent">LIVE ORCHESTRATION</span>
          </div>
          <div id="swarm-dag-host" class="u-97445a8d"></div>
        </div>
        <div id="sw-runs" class="swarm-grid" style="display:none"></div>
        <div id="sw-winner-box" style="display:none" class="swarm-winner-box">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
            <span class="u-b9199e22">🏆</span>
            <span style="font-weight:700;font-size:14px" id="sw-winner-title">Winner</span>
            <button data-act-click="copyWinner()" class="btn btn-ghost btn-sm u-6d000617" >📋 Copy</button>
            <button data-act-click="acceptWinnerToMonaco()" class="btn btn-primary btn-sm">→ Editor</button>
          </div>
          <div style="font-size:12px;color:var(--text-2);margin-bottom:8px" id="sw-winner-reason"></div>
          <div id="sw-winner-body" style="font-size:13px;white-space:pre-wrap;max-height:300px;overflow-y:auto;line-height:1.6"></div>
        </div>
      </div>
    </div>`;

  renderSwarmAgents();
  setTimeout(() => {
    const agents = [...document.querySelectorAll('#sw-agent-grid input:checked')].map(i=>i.dataset.agent);
    renderSwarmDAG([], '', false, agents.length ? agents : ['orchestrator','brain','builder','visual_tester','functional_tester','design_decomposer','test_creator']);
  }, 100);
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
      <input type="checkbox" data-agent="${a.id}" ${defaultOn.has(a.id)?'checked':''} style="accent-color:var(--accent-text)">
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

  renderSwarmDAG([], '', true, agents, prompt);

  document.getElementById('sw-runs').innerHTML =
    agents.map(aid => {
      const a = (S.agents||[]).find(x=>x.id===aid)||{name:aid,avatar:'🤖',color:'#5b8af8'};
      return `<div class="swarm-card" id="sw-card-${aid}">
        <div class="swarm-card-head">
          <span class="u-4ff818ff">${a.avatar||'🤖'}</span>
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

    renderSwarmDAG(j.runs||[], j.winner||j.merged||'', false, agents, prompt);

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

    const hasOutcome = Boolean(j.winner || j.merged);
    const winnerBox = document.getElementById('sw-winner-box');
    const winnerActions = winnerBox?.querySelectorAll('button');
    if (hasOutcome) {
      swarmLastWinner = j.merged || j.winner_output || '';
      winnerBox.style.display = 'block';
      winnerActions?.forEach(button => { button.style.display = ''; });
      document.getElementById('sw-winner-title').textContent =
        j.merged ? '🔀 Merged Output' : `🏆 ${j.winner} — winner`;
      document.getElementById('sw-winner-reason').textContent = j.judge_reason || '';
      document.getElementById('sw-winner-body').innerHTML = renderMarkdown(swarmLastWinner);
      statusEl.innerHTML = `✓ Done in ${j.total_latency_ms}ms · ${j.total_tokens} tokens · winner: <strong>${escHtml(j.winner)}</strong>`;
    } else {
      // A clean API response without a winner normally means no usable model
      // was connected. Never present that as a successful completed swarm.
      swarmLastWinner = '';
      winnerBox.style.display = 'block';
      winnerActions?.forEach(button => { button.style.display = 'none'; });
      document.getElementById('sw-winner-title').textContent = '⚠️ Connect AI to run a swarm';
      document.getElementById('sw-winner-reason').textContent = 'No AI connection returned a usable response.';
      document.getElementById('sw-winner-body').innerHTML =
        `<div style="display:flex;gap:8px;flex-wrap:wrap"><button data-act-click="nav('settings');switchSettingsTab('api')" class="btn btn-primary btn-sm">Connect AI</button><button data-act-click="testOllamaConnection()" class="btn btn-ghost btn-sm">Use Local AI</button></div>`;
      statusEl.textContent = '⚠️ Connect AI, then run the swarm again.';
    }
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
  // BUG FIX / MODULE MERGE: this used to nav('builder') and insert into
  // the standalone Code Editor pane's Monaco instance (S.monacoEditor).
  // That pane has been retired and merged into Code Studio (nav('builder')
  // now redirects to nav('studio') -- see 01-app-core.js), whose editor
  // lives on Studio.editor instead, so this now targets the correct
  // instance. Falls back to clipboard copy if Studio's editor genuinely
  // isn't ready yet (e.g. Monaco still loading from CDN).
  nav('studio');
  setTimeout(() => {
    if (typeof Studio !== 'undefined' && Studio.editor) {
      const sel = Studio.editor.getSelection();
      Studio.editor.executeEdits('swarm', [{range: sel, text: '\n\n/* 🌀 Swarm */\n' + swarmLastWinner}]);
      toast('→ Inserted into editor','ok');
    } else {
      navigator.clipboard.writeText(swarmLastWinner).then(()=>toast('Copied — paste into editor','ok'));
    }
  }, 500);
}

async function loadSwarmHistory() {
  try {
    const j = await AgenticAPI.get('/api/swarm/history?limit=10');
    if (!j.length) { toast('No swarm history yet','warn'); return; }
    const items = j.map(h => `${h.ts} — ${h.winner||'?'} won — ${h.strategy} — agents: ${(h.agents||[]).join(', ')}\n  ${h.prompt?.slice(0,80)||''}`).join('\n\n');
    await gmAlert('🌀 Swarm History (last 10)', `<pre style="font-size:12px;white-space:pre-wrap;max-height:340px;overflow-y:auto">${escHtml(items)}</pre>`);
  } catch(ex) { toast('Swarm history error: ' + ex.message, 'err'); }
}

