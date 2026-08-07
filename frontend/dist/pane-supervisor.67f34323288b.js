
;/* 48-supervisor.js */
(function(S, nav, toast, escHtml, fetch, document) {
let _supervisorPollTimer = null;
let _dagRuns        = [];
let _dagActiveRun   = null;
let _dagZoom        = 1.0;
let _dagPanX        = 0;
let _dagPanY        = 0;
let _dagPanning     = false;
let _dagPanStart    = {x:0,y:0,px:0,py:0};
let _dagSelectedTask = null;
let _dagLiveTimer   = null;
let _dagAnimFrame   = null;
const DAG_AGENT_COLORS = {
researcher:   '#5b8af8',
builder:      '#3dba7a',
reviewer:     '#e8a237',
creative:     '#c084fc',
memory:       '#38c5d8',
brain:        '#9d74f5',
orchestrator: '#f06080',
};
const DAG_AGENT_ICONS = {
researcher:   '🔍',
builder:      '🔨',
reviewer:     '🔬',
creative:     '✍️',
memory:       '🧠',
brain:        '💡',
orchestrator: '🎯',
};
const DAG_STATUS_COLORS = {
pending:       'rgba(255,255,255,.15)',
running:       '#e8a237',
done:          '#3dba7a',
failed:        '#e85252',
killed:        '#7a8aaa',
awaiting_hitl: '#c084fc',
};
const DAG_STATUS_ICONS = {
decomposing:   '🧩', scheduled: '📋', running: '⚡',
synthesizing:  '🔀', done: '✅', failed: '❌', killed: '🛑',
pending:       '⏳', awaiting_hitl: '🛂',
};
const DAG_RUN_STATUS_COLOR = {
decomposing:'var(--warning)', scheduled:'var(--accent)', running:'#e8a237',
synthesizing:'#9d74f5', done:'var(--success)', failed:'var(--danger)', killed:'var(--text-3)',
};
async function renderSupervisor() {
const pane = document.getElementById('pane-supervisor');
if (!pane) return;
pane.innerHTML = `
  <div class="section-head" style="padding:16px 20px;border-bottom:1px solid var(--border);background:var(--bg-1);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">
    <div>
      <h2 style="margin:0 0 4px;font-size:20px;font-weight:900">◈ Supervisor & Multi-Node Edge Swarm Radar (Phase 5)</h2>
      <p style="margin:0;color:var(--text-2);font-size:12.5px">Autonomous goal DAG execution • Local LAN cluster grid • Distributed model sharding across Apple Silicon & edge nodes</p>
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button data-act-click="supervisorSwitchView('dag')" id="sup-btn-dag" class="btn-3d btn-primary btn-sm" style="padding:5px 12px">🧠 Supervisor DAGs</button>
      <button data-act-click="supervisorSwitchView('cluster')" id="sup-btn-cluster" class="btn-3d btn-ghost btn-sm" style="padding:5px 12px">📡 Multi-Node Edge Radar</button>
      <button data-act-click="toggleSplitWorkspace(true,'supervisor')" class="btn-3d btn-ghost btn-sm" style="padding:5px 12px">🗂️ Secondary Dock</button>
    </div>
  </div>

  <div id="sup-view-dag" style="display:block">
    <div class="dag-root">
      <!-- ── Sidebar ── -->
      <div class="dag-sidebar">
        <div class="dag-sidebar-head">
          <p class="dag-sidebar-title">🧠 Supervisor Runs</p>
          <div class="dag-stats-grid" id="dag-stats-grid">
            <div class="dag-stat"><div class="dag-stat-val" id="dag-stat-total" style="color:var(--accent-text)">—</div><div class="dag-stat-label">Total</div></div>
            <div class="dag-stat"><div class="dag-stat-val" id="dag-stat-done" style="color:var(--success)">—</div><div class="dag-stat-label">Done</div></div>
            <div class="dag-stat"><div class="dag-stat-val" id="dag-stat-score" style="color:#9d74f5">—</div><div class="dag-stat-label">Avg Score</div></div>
            <div class="dag-stat"><div class="dag-stat-val" id="dag-stat-tokens" style="color:var(--text-2)">—</div><div class="dag-stat-label">Tokens</div></div>
          </div>
        </div>
        <div class="dag-run-list" id="dag-run-list">
          <div style="color:var(--text-3);font-size:12px;padding:10px">Loading…</div>
        </div>
        <div class="dag-sidebar-foot">
          <button class="dag-launch-btn" data-act-click="dagOpenLaunch()">⚡ Launch New Goal</button>
        </div>
      </div>

      <!-- ── Main ── -->
      <div class="dag-main">
        <!-- Toolbar -->
        <div class="dag-toolbar">
          <span class="dag-toolbar-title" id="dag-run-title">Select a run to visualize its Task DAG</span>
          <div id="dag-live-indicator" style="display:none;align-items:center;gap:5px">
            <div class="dag-live-dot"></div>
            <span style="font-size:10px;color:var(--danger);font-weight:700">LIVE</span>
          </div>
          <button class="dag-toolbar-btn" id="dag-fit-btn" data-act-click="dagFitView()" style="display:none">⊡ Fit</button>
          <button class="dag-toolbar-btn" id="dag-detail-toggle" data-act-click="dagToggleDetail()" style="display:none">Detail ▶</button>
          <button class="dag-toolbar-btn danger" id="dag-kill-btn" data-act-click="dagKillActive()" style="display:none">🛑 Kill</button>
          <button class="dag-toolbar-btn" id="dag-delete-btn" data-act-click="dagDeleteActive()" style="display:none">🗑 Delete</button>
          <button class="dag-toolbar-btn" data-act-click="dagRefresh()" title="Refresh">↺</button>
        </div>

        <!-- Phase/wave banner -->
        <div class="dag-wave-bar" id="dag-wave-bar" style="display:none"></div>

        <!-- Phase status banner (for running runs) -->
        <div class="dag-phase-banner" id="dag-phase-banner" style="display:none">
          <span id="dag-phase-icon">⚡</span>
          <span id="dag-phase-text">Running…</span>
        </div>

        <!-- Viewport -->
        <div class="dag-viewport">
          <!-- Canvas -->
          <div class="dag-canvas-wrap" id="dag-canvas-wrap">
            <div class="dag-canvas-inner" id="dag-canvas-inner">
              <svg id="dag-svg" style="position:absolute;inset:0;overflow:visible;pointer-events:none">
                <defs>
                  <marker id="dag-arr-default" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                    <path d="M0,0 L0,6 L8,3 z" fill="rgba(255,255,255,.2)"/>
                  </marker>
                  <marker id="dag-arr-done" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                    <path d="M0,0 L0,6 L8,3 z" fill="#3dba7a"/>
                  </marker>
                  <marker id="dag-arr-active" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                    <path d="M0,0 L0,6 L8,3 z" fill="#e8a237"/>
                  </marker>
                  <marker id="dag-arr-error" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                    <path d="M0,0 L0,6 L8,3 z" fill="#e85252"/>
                  </marker>
                </defs>
                <g id="dag-edges-g"></g>
              </svg>
              <div id="dag-nodes-g"></div>
            </div>

            <!-- Empty state -->
            <div class="dag-empty" id="dag-empty">
              <div class="dag-empty-icon">🧠</div>
              <div class="dag-empty-title">No Run Selected</div>
              <div class="dag-empty-sub">
                Select a supervisor run from the sidebar to visualize its Task DAG — nodes light up in real time as the supervisor orchestrates specialist agents.
              </div>
              <button class="dag-launch-btn" data-act-click="dagOpenLaunch()" style="width:auto;padding:8px 20px;margin-top:16px">⚡ Launch Your First Goal</button>
            </div>

            <!-- Zoom controls -->
            <div class="dag-zoom-controls" id="dag-zoom-controls" style="display:none">
              <button class="dag-zoom-btn" data-act-click="dagZoom(1.2)" data-no-busy="1" title="Zoom in">+</button>
              <div class="dag-zoom-label" id="dag-zoom-label">100%</div>
              <button class="dag-zoom-btn" data-act-click="hZoomOut('dagZoom')" data-no-busy="1" title="Zoom out">−</button>
            </div>

            <!-- Minimap -->
            <div class="dag-minimap" id="dag-minimap" style="display:none">
              <canvas id="dag-minimap-canvas" width="130" height="80"></canvas>
            </div>
          </div>

          <!-- Detail panel -->
          <div class="dag-detail collapsed" id="dag-detail">
            <div class="dag-detail-head">
              <h4 id="dag-detail-title">Task Detail</h4>
              <button data-act-click="dagToggleDetail()" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:13px">✕</button>
            </div>
            <div class="dag-detail-body" id="dag-detail-body">
              <div style="color:var(--text-3);font-size:12px">Click a task node to see its details.</div>
            </div>
          </div>
        </div>

        <!-- Bottom: final output / eval bar (shown when done) -->
        <div id="dag-result-bar" style="display:none;flex-shrink:0;background:var(--bg-1);border-top:1px solid var(--border);padding:10px 14px">
          <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
            <span style="font-size:11px;font-weight:700;color:var(--text-2)">📊 Eval Score:</span>
            <span id="dag-eval-score" style="font-size:14px;font-weight:800;color:var(--success)"></span>
            <span id="dag-eval-notes" style="font-size:11px;color:var(--text-3);flex:1"></span>
            <button class="dag-toolbar-btn" data-act-click="dagShowFinalOutput()">📄 Final Output</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Multi-Node Edge Swarm Radar (Phase 5) -->
  <div id="sup-view-cluster" style="display:none;padding:20px;max-width:1100px;margin:0 auto;flex:1;overflow-y:auto">
    <div class="card-elevated surface-z3" style="margin-bottom:20px;border:1px solid var(--border-hi);padding:20px;border-radius:18px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:8px">
        <div>
          <h3 style="margin:0 0 4px;font-size:16px;color:var(--text-0)">📡 Local LAN Edge Cluster Radar & Compute Mesh</h3>
          <span style="font-size:12px;color:var(--text-2)">Zero-latency edge sharding across localized Apple Silicon & inference server nodes</span>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button data-act-click="clusterAddNode()" class="btn-3d btn-primary btn-sm u-6c51dbca" >＋ Add Edge Node</button>
          <button data-act-click="clusterScanLAN()" class="btn-3d btn-ghost btn-sm u-6c51dbca" >📡 Scan Local Network</button>
          <button data-act-click="clusterRebalanceLoad()" class="btn-3d btn-ghost btn-sm u-6c51dbca" >⚡ Rebalance Swarm Load</button>
        </div>
      </div>

      <!-- Radar Animation Grid -->
      <div style="display:grid;grid-template-columns:1fr 2fr;gap:20px;align-items:center;background:#04060f;border:1px solid var(--border-hi);border-radius:14px;padding:20px">
        <div style="position:relative;width:200px;height:200px;margin:0 auto;border-radius:50%;border:1px solid rgba(56,189,248,0.3);display:flex;align-items:center;justify-content:center;background:radial-gradient(circle, rgba(56,189,248,0.1) 0%, rgba(4,6,15,0.9) 80%)">
          <div style="position:absolute;width:140px;height:140px;border-radius:50%;border:1px dashed rgba(56,189,248,0.2)"></div>
          <div style="position:absolute;width:80px;height:80px;border-radius:50%;border:1px dashed rgba(56,189,248,0.2)"></div>
          <div style="width:12px;height:12px;border-radius:50%;background:var(--accent);box-shadow:0 0 16px var(--accent)"></div>
          <!-- Animated Radar Sweep -->
          <div style="position:absolute;top:50%;left:50%;width:100px;height:2px;background:linear-gradient(90deg, var(--accent), transparent);transform-origin:left center;animation:spin 3s linear infinite"></div>
          <!-- Node Dots -->
          <div style="position:absolute;top:35px;right:45px;width:8px;height:8px;border-radius:50%;background:#10b981;box-shadow:0 0 10px #10b981" title="Node 1 (Local Master)"></div>
          <div style="position:absolute;bottom:45px;left:40px;width:8px;height:8px;border-radius:50%;background:#a855f7;box-shadow:0 0 10px #a855f7" title="Node 2 (Edge Worker)"></div>
          <div style="position:absolute;top:50px;left:35px;width:8px;height:8px;border-radius:50%;background:#f59e0b;box-shadow:0 0 10px #f59e0b" title="Node 3 (GPU Inference Node)"></div>
        </div>

        <!-- Live node list — populated from GET /api/cluster/nodes by
             clusterRefresh(). This used to be three hardcoded <div>s naming
             invented laptop/GPU hardware with fake sub-millisecond latencies,
             shown regardless of what was actually registered. -->
        <div id="cluster-node-list" style="display:flex;flex-direction:column;gap:12px;font-family:monospace">
          <div style="color:var(--text-3);font-size:12px">Loading cluster nodes…</div>
        </div>
      </div>
    </div>
  </div>`;
dagInitCanvasInteraction();
dagInitKeyboard();
await dagRefresh();
}
window.supervisorSwitchView = function(view) {
const dagView = document.getElementById('sup-view-dag');
const clusterView = document.getElementById('sup-view-cluster');
const btnDag = document.getElementById('sup-btn-dag');
const btnCluster = document.getElementById('sup-btn-cluster');
if (view === 'dag') {
if (dagView) dagView.style.display = 'block';
if (clusterView) clusterView.style.display = 'none';
if (btnDag) { btnDag.className = 'btn-3d btn-primary btn-sm'; }
if (btnCluster) { btnCluster.className = 'btn-3d btn-ghost btn-sm'; }
} else {
if (dagView) dagView.style.display = 'none';
if (clusterView) clusterView.style.display = 'block';
if (btnDag) { btnDag.className = 'btn-3d btn-ghost btn-sm'; }
if (btnCluster) { btnCluster.className = 'btn-3d btn-primary btn-sm'; }
if (typeof window.clusterRefresh === 'function') window.clusterRefresh();
}
};
function clusterNodeCard(node) {
const online = (Date.now() / 1000 - (node.last_heartbeat || 0)) < 60;
const colour = node.role === 'master' ? '#10b981' : (online ? '#a855f7' : '#f59e0b');
const caps = node.capabilities || {};
const detail = [
caps.gpu,
caps.vram_gb ? `${caps.vram_gb}GB VRAM` : '',
(caps.models_loaded || []).join(', '),
].filter(Boolean).join(' • ');
const card = document.createElement('div');
card.className = 'card-elevated surface-z2';
card.style.cssText = `padding:12px;border-left:3px solid ${colour};border-radius:8px;display:flex;justify-content:space-between;align-items:center;gap:10px`;
const left = document.createElement('div');
left.style.cssText = 'min-width:0';
const title = document.createElement('div');
title.style.cssText = `color:${colour};font-weight:800;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis`;
title.textContent = `${node.name || node.node_id}${node.role === 'master' ? ' (master)' : ''}`;
const sub = document.createElement('div');
sub.style.cssText = 'color:var(--text-2);font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis';
sub.textContent = `${node.host_url || 'unknown host'}${detail ? ' • ' + detail : ''}`;
left.append(title, sub);
const badge = document.createElement('span');
badge.className = 'badge ' + (online ? 'badge-success' : 'badge-warning');
badge.style.flexShrink = '0';
badge.textContent = online ? (node.status || 'active').toUpperCase() : 'STALE';
card.append(left, badge);
return card;
}
window.clusterRefresh = async function() {
const list = document.getElementById('cluster-node-list');
if (!list) return;
try {
const r = await fetch('/api/cluster/nodes');
const d = await r.json();
const nodes = (d && d.nodes) || [];
list.replaceChildren();
if (!nodes.length) {
const empty = document.createElement('div');
empty.style.cssText = 'color:var(--text-3);font-size:12px';
empty.textContent = 'No nodes registered. Use “＋ Add Edge Node” to join one.';
list.appendChild(empty);
return;
}
nodes.forEach((n) => list.appendChild(clusterNodeCard(n)));
} catch (e) {
list.replaceChildren();
const err = document.createElement('div');
err.style.cssText = 'color:var(--danger);font-size:12px';
err.textContent = `Could not load cluster nodes: ${e && e.message ? e.message : e}`;
list.appendChild(err);
}
};
window.clusterAddNode = async function() {
const host = await gmPrompt('Add Edge Node', 'Enter the node\'s host URL (e.g. http://192.168.1.142:8787):', 'http://192.168.1.142:8787');
if (!host || !host.trim()) return;
const hostUrl = host.trim();
toast(`Registering ${hostUrl}…`, 'ok', 2000);
try {
const r = await fetch('/api/cluster/nodes/join', {
method: 'POST',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({ host_url: hostUrl, name: hostUrl.replace(/^https?:\/\//, '') }),
});
const d = await r.json();
if (!r.ok || !d.ok) throw new Error(d.detail || d.error || `HTTP ${r.status}`);
toast(`✅ Node registered: ${d.node_id}`, 'ok', 3000);
window.clusterRefresh();
} catch (e) {
toast(`❌ Could not register node: ${e && e.message ? e.message : e}`, 'err', 4000);
}
};
window.clusterScanLAN = async function() {
toast('Refreshing registered cluster nodes…', 'ok', 1500);
try {
const r = await fetch('/api/cluster/status');
const d = await r.json();
await window.clusterRefresh();
gmAlert(
'📡 Cluster Status',
`Cluster <code style="font-family:monospace">${escHtml(d.cluster_id || 'unknown')}</code><br><br>` +
`Registered nodes: <strong style="color:var(--accent-text)">${d.node_count ?? 0}</strong><br>` +
`Active (recent heartbeat): <strong>${d.active_nodes ?? 0}</strong><br>` +
`Total VRAM reported: <strong>${d.total_vram_gb ?? 0} GB</strong><br><br>` +
`<span style="color:var(--text-3)">Automatic subnet discovery isn't available — add nodes by URL with “＋ Add Edge Node”.</span>`
);
} catch (e) {
toast(`❌ Could not read cluster status: ${e && e.message ? e.message : e}`, 'err', 4000);
}
};
window.clusterRebalanceLoad = async function() {
toast('Dispatching a probe task to the cluster…', 'ok', 2000);
try {
const r = await fetch('/api/cluster/dispatch', {
method: 'POST',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({ task_prompt: 'Cluster rebalance probe' }),
});
const d = await r.json();
if (!r.ok || !d.ok) throw new Error(d.detail || d.error || `HTTP ${r.status}`);
toast(`✅ ${d.message || 'Task dispatched to ' + (d.dispatched_to_node || 'a node')}`, 'ok', 4000);
window.clusterRefresh();
} catch (e) {
toast(`❌ Dispatch failed: ${e && e.message ? e.message : e}`, 'err', 4000);
}
};
async function dagRefresh() {
const [statsR, runsR] = await Promise.all([
fetch('/api/supervisor/stats').then(r => r.ok ? r.json() : {}).catch(() => ({})),
fetch('/api/supervisor/runs?limit=50').then(r => r.ok ? r.json() : {runs:[]}).catch(() => ({runs:[]})),
]);
_dagRuns = runsR.runs || [];
dagUpdateStats(statsR);
dagRenderRunList();
if (!_dagActiveRun && _dagRuns.length > 0) {
const active = _dagRuns.find(r => ['decomposing','scheduled','running','synthesizing'].includes(r.status));
await dagSelectRun((active || _dagRuns[0]).run_id);
} else if (_dagActiveRun) {
await dagSelectRun(_dagActiveRun.run.run_id);
}
dagMaybePoll();
}
function dagUpdateStats(stats) {
const el = (id) => document.getElementById(id);
if (el('dag-stat-total'))  el('dag-stat-total').textContent  = stats.total_runs ?? '0';
if (el('dag-stat-done'))   el('dag-stat-done').textContent   = (stats.by_status || {}).done ?? '0';
if (el('dag-stat-score'))  el('dag-stat-score').textContent  = stats.avg_eval_score ? Math.round(stats.avg_eval_score * 100) + '%' : '—';
if (el('dag-stat-tokens')) el('dag-stat-tokens').textContent = ((stats.total_tokens || 0) / 1000).toFixed(1) + 'k';
}
function dagRenderRunList() {
const list = document.getElementById('dag-run-list');
if (!list) return;
if (!_dagRuns.length) {
list.innerHTML = `<div style="color:var(--text-3);font-size:12px;padding:12px;line-height:1.7">
      No runs yet.<br>Launch your first goal above.
    </div>`;
return;
}
list.innerHTML = _dagRuns.map(r => {
const isActive   = _dagActiveRun?.run?.run_id === r.run_id;
const isRunning  = ['decomposing','scheduled','running','synthesizing'].includes(r.status);
const col        = DAG_RUN_STATUS_COLOR[r.status] || 'var(--border)';
const icon       = DAG_STATUS_ICONS[r.status]     || '❓';
const progress   = r.task_count > 0 ? Math.round(r.done_count / r.task_count * 100) : 0;
const ts         = new Date(r.created_at).toLocaleString(undefined, {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
return `<div class="dag-run-card ${isActive?'active':''}" data-run-id="${escHtml(r.run_id)}">
      <div class="dag-run-card-top">
        <span class="dag-badge" style="background:${col}22;color:${col}">${icon} ${r.status}</span>
        ${isRunning ? '<div class="dag-live-dot u-6d000617" ></div>' : ''}
      </div>
      <div class="dag-run-name">${escHtml((r.goal_title || r.goal_text || '').slice(0, 55))}</div>
      <div class="dag-run-meta">${r.task_count} tasks · ${ts}${r.duration_ms?` · ${(r.duration_ms/1000).toFixed(1)}s`:''}</div>
      ${r.task_count > 0 ? `
      <div class="dag-progress-bar-wrap">
        <div class="dag-progress-track">
          <div class="dag-progress-fill" style="width:${progress}%;background:${col}"></div>
        </div>
      </div>` : ''}
    </div>`;
}).join('');
bindSupervisorDelegated();
}
async function dagSelectRun(runId) {
try {
const d = await fetch(`/api/supervisor/run/${encodeURIComponent(runId)}/dag`)
.then(r => r.ok ? r.json() : null);
if (!d || !d.ok) { toast('Could not load DAG'); return; }
_dagActiveRun = d;
_dagSelectedTask = null;
dagRenderRunList();
dagUpdateToolbar();
dagBuildGraph();
dagBuildWaveBar();
dagUpdatePhaseBanner();
dagFitView();
dagMaybePoll();
} catch(e) { console.error('dagSelectRun', e); toast('Error loading DAG: ' + e.message); }
}
function dagUpdateToolbar() {
const run = _dagActiveRun?.run;
if (!run) return;
const isRunning  = ['decomposing','scheduled','running','synthesizing'].includes(run.status);
const isTerminal = ['done','failed','killed'].includes(run.status);
const col        = DAG_RUN_STATUS_COLOR[run.status] || 'var(--text-3)';
const titleEl = document.getElementById('dag-run-title');
if (titleEl) {
titleEl.innerHTML = `<span class="dag-toolbar-pill" style="background:${col}22;color:${col}">${DAG_STATUS_ICONS[run.status]||''} ${run.status}</span>
    &nbsp;${escHtml((run.goal_title || run.goal_text || '').slice(0, 70))}
    <span style="font-size:10px;color:var(--text-3);margin-left:6px">${_dagActiveRun?.total_tasks || 0} tasks · ${_dagActiveRun?.wave_count || 0} waves</span>`;
}
const liveEl = document.getElementById('dag-live-indicator');
if (liveEl) liveEl.style.display = isRunning ? 'flex' : 'none';
const show = (id, show) => { const el = document.getElementById(id); if (el) el.style.display = show ? '' : 'none'; };
show('dag-fit-btn', true);
show('dag-detail-toggle', true);
show('dag-kill-btn', isRunning);
show('dag-delete-btn', isTerminal);
show('dag-zoom-controls', true);
show('dag-minimap', true);
const emptyEl = document.getElementById('dag-empty');
if (emptyEl) emptyEl.style.display = 'none';
const resultBar = document.getElementById('dag-result-bar');
if (resultBar) {
if (run.status === 'done' && run.eval_score) {
resultBar.style.display = 'block';
const scoreEl = document.getElementById('dag-eval-score');
const notesEl = document.getElementById('dag-eval-notes');
if (scoreEl) scoreEl.textContent = Math.round(run.eval_score * 100) + '%';
if (notesEl) notesEl.textContent = run.eval_notes || '';
} else {
resultBar.style.display = 'none';
}
}
}
function dagBuildWaveBar() {
const bar = document.getElementById('dag-wave-bar');
if (!bar || !_dagActiveRun) return;
const waves = _dagActiveRun.waves || [];
if (!waves.length) { bar.style.display = 'none'; return; }
bar.style.display = 'flex';
bar.innerHTML = `<span style="font-size:10px;color:var(--text-3);font-weight:700;margin-right:4px">Waves:</span>` +
waves.map((w, i) => `
      ${i > 0 ? '<span class="dag-wave-arrow">→</span>' : ''}
      <div class="dag-wave-pill ${w.status}">
        ${DAG_STATUS_ICONS[w.status] || '⬡'} Wave ${w.wave + 1}
        <span style="opacity:.7">(${w.count})</span>
      </div>
    `).join('');
}
function dagUpdatePhaseBanner() {
const banner  = document.getElementById('dag-phase-banner');
const iconEl  = document.getElementById('dag-phase-icon');
const textEl  = document.getElementById('dag-phase-text');
const run     = _dagActiveRun?.run;
if (!banner || !run) return;
const phaseMap = {
decomposing:  ['🧩', 'Brain is decomposing your goal into tasks…'],
scheduled:    ['📋', 'Tasks scheduled — preparing specialist agents…'],
running:      ['⚡', `Executing tasks — ${run.done_count || 0} of ${run.task_count || 0} complete`],
synthesizing: ['🔀', 'Orchestrator is synthesizing all task outputs…'],
};
const phase = phaseMap[run.status];
if (phase) {
banner.style.display = 'flex';
if (iconEl) iconEl.textContent = phase[0];
if (textEl) textEl.textContent = phase[1];
} else {
banner.style.display = 'none';
}
}
function dagBuildGraph() {
if (!_dagActiveRun) return;
const nodesG  = document.getElementById('dag-nodes-g');
const edgesG  = document.getElementById('dag-edges-g');
if (!nodesG || !edgesG) return;
const tasks = _dagActiveRun.tasks || [];
const edges = _dagActiveRun.edges || [];
nodesG.innerHTML = tasks.map(t => dagNodeHTML(t)).join('');
setTimeout(() => {
dagDrawEdges(tasks, edges);
dagUpdateMinimap();
}, 60);
}
function dagNodeHTML(t) {
const col    = DAG_AGENT_COLORS[t.agent_id] || '#7a8aaa';
const icon   = DAG_AGENT_ICONS[t.agent_id]  || '🤖';
const stIcon = DAG_STATUS_ICONS[t.status]   || '⏳';
const stCls  = { pending:'n-pending', running:'n-running', done:'n-done', failed:'n-failed', awaiting_hitl:'n-hitl' }[t.status] || 'n-pending';
const barCls = { pending:'b-pending', running:'b-running', done:'b-done', failed:'b-failed' }[t.status] || 'b-pending';
const durStr = t.duration_ms > 0 ? `${(t.duration_ms/1000).toFixed(1)}s` : '';
const preview = t.output ? t.output.slice(0, 90) + (t.output.length > 90 ? '…' : '') : (t.status === 'running' ? 'Running…' : '');
return `<div class="dag-node ${stCls} ${_dagSelectedTask===t.task_id?'n-selected':''}" id="dagn-${t.task_id}"
              style="left:${t.x||0}px;top:${t.y||0}px"
              data-act-click="dagClickTask($event,${jsArg(t.task_id)})">
    <div class="dag-node-hdr">
      <div class="dag-node-seq" style="background:${col}">${t.seq}</div>
      <span class="dag-node-label" title="${escHtml(t.title)}">${escHtml(t.title)}</span>
      <span class="dag-node-status-icon">${stIcon}</span>
    </div>
    <div class="dag-node-agent-row">
      <span class="dag-node-agent-tag" style="background:${col}22;color:${col}">${icon} ${t.agent_id}</span>
      ${durStr ? `<span class="dag-node-dur">${durStr}</span>` : ''}
    </div>
    ${preview ? `<div class="dag-node-preview">${escHtml(preview)}</div>` : ''}
    <div class="dag-node-bar">
      <div class="dag-node-bar-fill ${barCls}" id="dagnbar-${t.task_id}" style="background:${col};${t.status==='done'?'width:100%':''}"></div>
    </div>
  </div>`;
}
function dagDrawEdges(tasks, edges) {
const edgesG = document.getElementById('dag-edges-g');
if (!edgesG) return;
edgesG.innerHTML = '';
const taskMap = {};
tasks.forEach(t => { taskMap[t.task_id] = t; });
const NODE_W = 220, NODE_H = 110;
edges.forEach((e, i) => {
const src = taskMap[e.from_id];
const tgt = taskMap[e.to_id];
if (!src || !tgt) return;
const x1 = (src.x || 0) + NODE_W;
const y1 = (src.y || 0) + NODE_H / 2;
const x2 = (tgt.x || 0);
const y2 = (tgt.y || 0) + NODE_H / 2;
const cx = (x1 + x2) / 2;
const isDone   = e.done;
const isActive = e.active;
const isError  = e.error;
const stroke = isError  ? '#e85252'
: isDone   ? '#3dba7a'
: isActive ? '#e8a237'
: 'rgba(255,255,255,.12)';
const markerId = isError  ? 'dag-arr-error'
: isDone   ? 'dag-arr-done'
: isActive ? 'dag-arr-active'
: 'dag-arr-default';
const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
const d    = `M${x1},${y1} C${cx},${y1} ${cx},${y2} ${x2},${y2}`;
path.setAttribute('d', d);
path.setAttribute('id', `dage-${e.id}`);
path.setAttribute('stroke', stroke);
path.setAttribute('stroke-width', isDone || isActive ? '2' : '1.5');
path.setAttribute('fill', 'none');
path.setAttribute('marker-end', `url(#${markerId})`);
if (isActive && !isError) {
path.setAttribute('stroke-dasharray', '8 4');
path.classList.add('dag-edge-active');
}
edgesG.appendChild(path);
});
if (tasks.length) {
const maxX = Math.max(...tasks.map(t => (t.x || 0) + NODE_W + 80));
const maxY = Math.max(...tasks.map(t => (t.y || 0) + NODE_H + 80));
const svg  = document.getElementById('dag-svg');
if (svg) { svg.style.width = maxX + 'px'; svg.style.height = maxY + 'px'; }
}
}
function dagRefreshGraphState() {
if (!_dagActiveRun) return;
const tasks = _dagActiveRun.tasks || [];
const edges = _dagActiveRun.edges || [];
tasks.forEach(t => {
const el     = document.getElementById(`dagn-${t.task_id}`);
const barEl  = document.getElementById(`dagnbar-${t.task_id}`);
if (!el) return;
const stCls  = { pending:'n-pending', running:'n-running', done:'n-done', failed:'n-failed', awaiting_hitl:'n-hitl' }[t.status] || 'n-pending';
const barCls = { pending:'b-pending', running:'b-running', done:'b-done', failed:'b-failed' }[t.status] || 'b-pending';
const base = `dag-node ${stCls}`;
el.className = _dagSelectedTask === t.task_id ? base + ' n-selected' : base;
if (barEl) {
barEl.className = `dag-node-bar-fill ${barCls}`;
const col = DAG_AGENT_COLORS[t.agent_id] || '#7a8aaa';
barEl.style.background = col;
if (t.status === 'done') barEl.style.width = '100%';
}
const preview = el.querySelector('.dag-node-preview');
if (preview && t.output) preview.textContent = t.output.slice(0, 90) + (t.output.length > 90 ? '…' : '');
const iconEl = el.querySelector('.dag-node-status-icon');
if (iconEl) iconEl.textContent = DAG_STATUS_ICONS[t.status] || '⏳';
const agentRow = el.querySelector('.dag-node-dur');
if (agentRow && t.duration_ms > 0) agentRow.textContent = `${(t.duration_ms/1000).toFixed(1)}s`;
});
dagDrawEdges(tasks, edges);
dagUpdateMinimap();
}
function dagClickTask(e, taskId) {
e.stopPropagation();
_dagSelectedTask = taskId;
document.querySelectorAll('.dag-node.n-selected').forEach(n => n.classList.remove('n-selected'));
const el = document.getElementById(`dagn-${taskId}`);
if (el) el.classList.add('n-selected');
dagShowTaskDetail(taskId);
const detail = document.getElementById('dag-detail');
if (detail?.classList.contains('collapsed')) dagToggleDetail();
}
function dagShowTaskDetail(taskId) {
const body    = document.getElementById('dag-detail-body');
const titleEl = document.getElementById('dag-detail-title');
if (!body || !_dagActiveRun) return;
const task = (_dagActiveRun.tasks || []).find(t => t.task_id === taskId);
if (!task) return;
const col    = DAG_AGENT_COLORS[task.agent_id] || '#7a8aaa';
const icon   = DAG_AGENT_ICONS[task.agent_id]  || '🤖';
const stCol  = DAG_STATUS_COLORS[task.status]  || 'var(--text-3)';
const isErr  = task.status === 'failed';
const deps   = (task.depends_on || []).join(', ') || 'None (starts immediately)';
if (titleEl) titleEl.textContent = `Task #${task.seq} — ${task.title}`;
const copy = (txt) =>
`<button class="dag-copy-btn" data-act-click="hCopyText(${jsArg(txt)})">Copy</button>`;
body.innerHTML = `
    <!-- Header -->
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
      <div class="dag-node-seq" style="background:${col};width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:800;color:#fff;flex-shrink:0">${task.seq}</div>
      <div>
        <div style="font-size:13px;font-weight:700;color:var(--text-0)">${escHtml(task.title)}</div>
        <div style="font-size:11px;color:${col};font-weight:700">${icon} ${task.agent_id}</div>
      </div>
    </div>

    <!-- Status -->
    <div class="dag-detail-section">
      <div class="dag-detail-label">Status</div>
      <div style="display:flex;align-items:center;gap:8px">
        <span style="padding:3px 10px;border-radius:6px;font-size:11px;font-weight:700;background:${stCol}22;color:${stCol}">
          ${DAG_STATUS_ICONS[task.status] || ''} ${task.status}
        </span>
        ${task.duration_ms > 0 ? `<span style="font-size:11px;color:var(--accent-text)">${(task.duration_ms/1000).toFixed(2)}s</span>` : ''}
        ${task.tokens ? `<span style="font-size:10px;color:var(--text-3)">${task.tokens} tokens</span>` : ''}
      </div>
    </div>

    <!-- Description -->
    ${task.description ? `
    <div class="dag-detail-section">
      <div class="dag-detail-label">Description</div>
      <div class="dag-detail-val">${escHtml(task.description)}</div>
    </div>` : ''}

    <!-- Dependencies -->
    <div class="dag-detail-section">
      <div class="dag-detail-label">Depends On (seq)</div>
      <div class="dag-detail-val">${escHtml(deps)}</div>
    </div>

    <!-- Output -->
    ${task.output ? `
    <div class="dag-detail-section">
      <div class="dag-detail-label">Output ${copy(task.output)}</div>
      <div class="dag-detail-val ${isErr ? 'v-error' : ''}">${escHtml(task.output.slice(0, 1200))}</div>
    </div>` : (task.status === 'running' ? `
    <div class="dag-detail-section">
      <div class="dag-detail-label">Output</div>
      <div style="color:var(--warning);font-size:11px;animation:dag-blink 1s infinite">⚡ Agent running…</div>
    </div>` : '')}

    <!-- Timing -->
    <div class="dag-detail-section">
      <div class="dag-detail-label">Timing</div>
      <div style="font-size:11px;color:var(--text-2)">
        ${task.created_at   ? `Created:   ${new Date(task.created_at).toLocaleString()}<br>` : ''}
        ${task.started_at   ? `Started:   ${new Date(task.started_at).toLocaleString()}<br>` : ''}
        ${task.completed_at ? `Completed: ${new Date(task.completed_at).toLocaleString()}` : ''}
      </div>
    </div>

    <!-- Risk -->
    ${task.risk_level && task.risk_level !== 'low' ? `
    <div class="dag-detail-section">
      <div class="dag-detail-label">Risk Level</div>
      <span style="padding:2px 8px;border-radius:5px;font-size:11px;font-weight:700;background:rgba(232,82,82,.15);color:#e85252">
        ⚠️ ${task.risk_level}
      </span>
      ${task.hitl_required ? '<span style="font-size:11px;color:#c084fc;margin-left:6px">🛂 HITL required</span>' : ''}
    </div>` : ''}
  `;
}
function dagToggleDetail() {
const detail = document.getElementById('dag-detail');
const btn    = document.getElementById('dag-detail-toggle');
if (!detail) return;
const collapsed = detail.classList.toggle('collapsed');
if (btn) btn.textContent = collapsed ? 'Detail ▶' : 'Detail ✕';
}
function dagMaybePoll() {
const isActive = _dagActiveRun &&
['decomposing','scheduled','running','synthesizing'].includes(_dagActiveRun.run?.status);
if (_supervisorPollTimer) {
clearInterval(_supervisorPollTimer);
_supervisorPollTimer = null;
}
if (isActive) {
_supervisorPollTimer = setInterval(dagLivePoll, 2000);
}
}
async function dagLivePoll() {
if (!_dagActiveRun) return;
const pane = document.getElementById('pane-supervisor');
if (!pane) { clearInterval(_supervisorPollTimer); return; }
try {
const runId = _dagActiveRun.run.run_id;
const d = await fetch(`/api/supervisor/run/${encodeURIComponent(runId)}/dag`)
.then(r => r.ok ? r.json() : null);
if (!d || !d.ok) return;
const wasActive = ['decomposing','scheduled','running','synthesizing'].includes(_dagActiveRun.run?.status);
_dagActiveRun = d;
dagRefreshGraphState();
dagBuildWaveBar();
dagUpdatePhaseBanner();
dagUpdateToolbar();
if (_dagSelectedTask) dagShowTaskDetail(_dagSelectedTask);
const isNowActive = ['decomposing','scheduled','running','synthesizing'].includes(d.run?.status);
if (!isNowActive) {
clearInterval(_supervisorPollTimer);
_supervisorPollTimer = null;
const runsR = await fetch('/api/supervisor/runs?limit=50').then(r => r.ok ? r.json() : {runs:[]});
_dagRuns = runsR.runs || [];
dagRenderRunList();
}
} catch(e) {  }
}
function dagApplyTransform() {
const inner = document.getElementById('dag-canvas-inner');
if (inner) inner.style.transform = `translate(${_dagPanX}px,${_dagPanY}px) scale(${_dagZoom})`;
const label = document.getElementById('dag-zoom-label');
if (label) label.textContent = Math.round(_dagZoom * 100) + '%';
}
function dagZoom(factor) {
const wrap = document.getElementById('dag-canvas-wrap');
if (!wrap) return;
const rect = wrap.getBoundingClientRect();
const cx   = rect.width / 2, cy = rect.height / 2;
_dagPanX   = cx - (cx - _dagPanX) * factor;
_dagPanY   = cy - (cy - _dagPanY) * factor;
_dagZoom   = Math.max(0.2, Math.min(3, _dagZoom * factor));
dagApplyTransform();
dagUpdateMinimap();
}
function dagFitView() {
if (!_dagActiveRun?.tasks?.length) return;
const wrap = document.getElementById('dag-canvas-wrap');
if (!wrap) return;
const rect  = wrap.getBoundingClientRect();
const tasks = _dagActiveRun.tasks;
const pad   = 60;
const NODE_W = 220, NODE_H = 110;
let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
tasks.forEach(t => {
minX = Math.min(minX, t.x || 0);   minY = Math.min(minY, t.y || 0);
maxX = Math.max(maxX, (t.x||0)+NODE_W); maxY = Math.max(maxY, (t.y||0)+NODE_H);
});
const scX  = (rect.width  - pad*2) / Math.max(maxX - minX, 1);
const scY  = (rect.height - pad*2) / Math.max(maxY - minY, 1);
_dagZoom   = Math.max(0.2, Math.min(2, Math.min(scX, scY)));
_dagPanX   = (rect.width  - (maxX + minX) * _dagZoom) / 2;
_dagPanY   = (rect.height - (maxY + minY) * _dagZoom) / 2;
dagApplyTransform();
dagUpdateMinimap();
}
function dagInitCanvasInteraction() {
const wrap = document.getElementById('dag-canvas-wrap');
if (!wrap) return;
wrap.addEventListener('wheel', e => {
e.preventDefault();
const rect   = wrap.getBoundingClientRect();
const factor = e.deltaY < 0 ? 1.12 : 1/1.12;
const mx = e.clientX - rect.left, my = e.clientY - rect.top;
_dagPanX = mx - (mx - _dagPanX) * factor;
_dagPanY = my - (my - _dagPanY) * factor;
_dagZoom = Math.max(0.2, Math.min(3, _dagZoom * factor));
dagApplyTransform();
dagUpdateMinimap();
}, { passive: false });
wrap.addEventListener('mousedown', e => {
if (e.target.closest('.dag-node,.dag-zoom-controls,.dag-minimap')) return;
_dagPanning  = true;
_dagPanStart = { x: e.clientX, y: e.clientY, px: _dagPanX, py: _dagPanY };
wrap.style.cursor = 'grabbing';
});
document.addEventListener('mousemove', e => {
if (!_dagPanning) return;
_dagPanX = _dagPanStart.px + (e.clientX - _dagPanStart.x);
_dagPanY = _dagPanStart.py + (e.clientY - _dagPanStart.y);
dagApplyTransform();
});
document.addEventListener('mouseup', () => {
if (_dagPanning) {
_dagPanning = false;
const w2 = document.getElementById('dag-canvas-wrap');
if (w2) w2.style.cursor = '';
dagUpdateMinimap();
}
});
}
function dagUpdateMinimap() {
const canvas = document.getElementById('dag-minimap-canvas');
if (!canvas || !_dagActiveRun?.tasks?.length) return;
const ctx  = canvas.getContext('2d');
const W = 130, H = 80, pad = 8;
const tasks = _dagActiveRun.tasks || [];
const edges = _dagActiveRun.edges || [];
const NODE_W = 220, NODE_H = 110;
ctx.clearRect(0, 0, W, H);
let minX=Infinity, minY=Infinity, maxX=-Infinity, maxY=-Infinity;
tasks.forEach(t => {
minX=Math.min(minX,t.x||0); minY=Math.min(minY,t.y||0);
maxX=Math.max(maxX,(t.x||0)+NODE_W); maxY=Math.max(maxY,(t.y||0)+NODE_H);
});
const scX=(W-pad*2)/Math.max(maxX-minX,1);
const scY=(H-pad*2)/Math.max(maxY-minY,1);
const sc =Math.min(scX,scY);
const toX=(x)=>pad+(x-minX)*sc;
const toY=(y)=>pad+(y-minY)*sc;
const taskMap={};tasks.forEach(t=>taskMap[t.task_id]=t);
edges.forEach(e=>{
const s=taskMap[e.from_id], t=taskMap[e.to_id];
if(!s||!t)return;
ctx.strokeStyle=e.done?'#3dba7a':e.active?'#e8a237':'rgba(255,255,255,.15)';
ctx.lineWidth=0.8;
ctx.beginPath();
ctx.moveTo(toX((s.x||0)+NODE_W),toY((s.y||0)+NODE_H/2));
ctx.lineTo(toX(t.x||0),toY((t.y||0)+NODE_H/2));
ctx.stroke();
});
tasks.forEach(t=>{
const col=DAG_STATUS_COLORS[t.status]||'rgba(255,255,255,.1)';
ctx.fillStyle=col;
const mw=Math.max(NODE_W*sc,4), mh=Math.max(NODE_H*sc*0.55,3);
ctx.beginPath();
ctx.roundRect(toX(t.x||0),toY(t.y||0),mw,mh,1.5);
ctx.fill();
});
const wrap=document.getElementById('dag-canvas-wrap');
if(wrap){
const wRect=wrap.getBoundingClientRect();
ctx.strokeStyle='rgba(91,138,248,.6)';ctx.lineWidth=1;
ctx.strokeRect(
toX(-_dagPanX/_dagZoom),toY(-_dagPanY/_dagZoom),
(wRect.width/_dagZoom)*sc,(wRect.height/_dagZoom)*sc
);
}
}
function dagInitKeyboard() {
document.addEventListener('keydown', dagKeyHandler);
}
function dagKeyHandler(e) {
const pane = document.getElementById('pane-supervisor');
if (!pane) return;
if (e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA'||e.target.tagName==='SELECT') return;
if (e.key==='f'||e.key==='F') dagFitView();
if ((e.key==='+'||e.key==='=')&&!e.shiftKey) dagZoom(1.2);
if (e.key==='-') dagZoom(1/1.2);
}
function dagOpenLaunch() {
const existing = document.getElementById('dag-launch-modal');
if (existing) { existing.remove(); return; }
const examples = [
'Build a REST API for user authentication with JWT',
'Competitive analysis of the top 5 LLM providers in 2026',
'Write a marketing campaign for our new product launch',
'Audit this codebase and produce a security report',
'Research quantum error correction and write a technical summary',
];
const overlay = document.createElement('div');
overlay.id = 'dag-launch-modal';
overlay.className = 'dag-modal-overlay';
overlay.innerHTML = `
    <div class="dag-modal">
      <h3>⚡ Launch New Supervisor Goal</h3>
      <p>The Brain agent will decompose your goal into a task DAG, assign specialist agents, and execute waves in parallel. Watch the graph light up in real time.</p>
      <textarea id="dag-goal-ta" placeholder="Describe your goal in detail…&#10;&#10;Be specific about deliverables, constraints, and desired output format." rows="4"></textarea>
      <div class="dag-modal-examples">
        ${examples.map(ex => `<div class="dag-modal-example" data-act-click="hSetFieldValue('dag-goal-ta',${jsArg(ex)})" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">${escHtml(ex)}</div>`).join('')}
      </div>
      <div class="dag-modal-row">
        <button class="dag-toolbar-btn" data-close="id:dag-launch-modal">Cancel</button>
        <button class="dag-launch-btn" style="width:auto;padding:8px 20px" data-act-click="dagLaunchGoal()">⚡ Launch</button>
      </div>
    </div>`;
overlay.onclick = e => { if (e.target === overlay) overlay.remove(); };
document.body.appendChild(overlay);
setTimeout(() => document.getElementById('dag-goal-ta')?.focus(), 50);
}
async function dagLaunchGoal() {
const goal = document.getElementById('dag-goal-ta')?.value?.trim();
if (!goal) { toast('⚠️ Enter a goal first'); return; }
document.getElementById('dag-launch-modal')?.remove();
toast('⚡ Launching supervisor run…');
try {
const r = await fetch('/api/supervisor/run', {
method:'POST', headers:{'Content-Type':'application/json'},
body: JSON.stringify({ goal })
});
if (!r.ok) { toast('⚠️ Launch failed (HTTP ' + r.status + ')'); return; }
const d = await r.json();
if (!d.ok) { toast('⚠️ ' + (d.error || 'Launch failed')); return; }
toast(`🧠 Run started: ${d.run_id}`);
await dagRefresh();
await dagSelectRun(d.run_id);
} catch(e) { toast('⚠️ Launch error: ' + e.message); }
}
async function dagKillActive() {
if (!_dagActiveRun) return;
const runId = _dagActiveRun.run.run_id;
const ok    = await gmDanger('Kill Run', `Stop run ${runId}? All in-progress tasks will be abandoned.`);
if (!ok) return;
try {
const r = await fetch(`/api/supervisor/run/${encodeURIComponent(runId)}/kill`, {
method:'POST', headers:{'Content-Type':'application/json'},
body: JSON.stringify({reason:'User kill switch'})
});
const d = await r.json();
toast(d.ok ? `🛑 Run killed` : '⚠️ Kill failed: ' + (d.error || ''));
await dagRefresh();
} catch(e) { toast('⚠️ ' + e.message); }
}
async function dagDeleteActive() {
if (!_dagActiveRun) return;
const runId = _dagActiveRun.run.run_id;
const ok    = await gmDanger('Delete Run', `Delete run ${runId} and all task data?`);
if (!ok) return;
try {
const r = await fetch(`/api/supervisor/run/${encodeURIComponent(runId)}`, { method:'DELETE' });
const d = await r.json();
if (d.ok) {
toast('🗑 Run deleted');
_dagActiveRun = null;
_dagSelectedTask = null;
await dagRefresh();
} else {
toast('⚠️ Delete failed: ' + (d.error || ''));
}
} catch(e) { toast('⚠️ ' + e.message); }
}
async function dagShowFinalOutput() {
if (!_dagActiveRun) return;
const run = _dagActiveRun.run;
const out = run.final_output || '(no output)';
await gmAlert(`📄 Final Output — ${escHtml((run.goal_title||'').slice(0,60))}`,
`Score: ${run.eval_score ? Math.round(run.eval_score*100)+'%' : '—'}\n${run.eval_notes ? 'Notes: '+run.eval_notes+'\n' : ''}\n${out.slice(0,2000)}`);
}
async function supervisorLaunch() { dagOpenLaunch(); }
async function supervisorViewRun(runId) { await dagSelectRun(runId); }
async function supervisorKill(runId) {
if (_dagActiveRun?.run?.run_id !== runId) await dagSelectRun(runId);
await dagKillActive();
}
async function supervisorDelete(runId) {
if (_dagActiveRun?.run?.run_id !== runId) await dagSelectRun(runId);
await dagDeleteActive();
}
function renderSupervisorRunCard(r) { return ''; }
function bindSupervisorDelegated() {
document.getElementById('dag-run-list')?.addEventListener('click', e => {
const card = e.target.closest('.dag-run-card');
if (!card) return;
const runId = card.dataset.runId;
if (runId) dagSelectRun(runId);
});
}
window.renderSupervisor = renderSupervisor;
})(S, nav, toast, escHtml, fetch, document);
