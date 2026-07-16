// Agentic OS v6.0 — Execution replay, collaborative editor, marketplace CDN
// Extracted from index.html (block 8)


'use strict';

// ══════════════════════════════════════════════════════════════════
//  EXECUTION REPLAY — frame-by-frame workflow scrubber
// ══════════════════════════════════════════════════════════════════


// ══════════════════════════════════════════════════════════════════
//  TIME-TRAVEL DEBUGGER — Complete Implementation
//  Replaces old renderReplay + all rp* functions
// ══════════════════════════════════════════════════════════════════

// ── State ─────────────────────────────────────────────────────────
let _ttdRuns        = [];       // all loaded runs from API
let _ttdRun         = null;     // currently selected run {run, frames, node_lanes, duration_ms}
let _ttdWf          = null;     // workflow graph {nodes, edges}
let _ttdFrame       = 0;        // current frame index (0-based)
let _ttdPlaying     = false;
let _ttdPlayTimer   = null;
let _ttdZoom        = 1.0;
let _ttdPanX        = 0;
let _ttdPanY        = 0;
let _ttdPanning     = false;
let _ttdPanStart    = {x:0,y:0,px:0,py:0};
let _ttdDiffRunA    = null;
let _ttdDiffRunB    = null;
let _ttdView        = 'graph';  // 'graph' | 'timeline' | 'diff'
let _ttdSearchQ     = '';
let _ttdFilterWf    = '';
let _ttdNodePositions = {};     // auto-layout cache

// ── Render main pane ─────────────────────────────────────────────
async function renderReplay() {
  const pane = document.getElementById('pane-replay');
  if (!pane) return;

  pane.innerHTML = `
  

  <div class="ttd-root">
    <!-- ── Left sidebar ── -->
    <div class="ttd-sidebar">
      <div class="ttd-sidebar-head">
        <p class="ttd-sidebar-title">⏮ Run History</p>
        <input class="ttd-search" id="ttd-search" placeholder="🔍  Search runs…" oninput="ttdSearchRuns(this.value)">
        <select class="ttd-wf-filter" id="ttd-wf-filter" onchange="ttdFilterByWf(this.value)">
          <option value="">All workflows</option>
        </select>
      </div>
      <div class="ttd-run-list" id="ttd-run-list">
        <div style="color:var(--text-3);font-size:12px;padding:10px">Loading…</div>
      </div>
      <div class="ttd-sidebar-foot">
        <button class="ttd-toolbar-btn" style="flex:1;justify-content:center" onclick="ttdOpenDiffMode()">↔ Diff Runs</button>
        <button class="ttd-toolbar-btn" onclick="ttdLoadRuns()" title="Refresh">↺</button>
      </div>
    </div>

    <!-- ── Main panel ── -->
    <div class="ttd-main">
      <!-- Toolbar -->
      <div class="ttd-toolbar">
        <span class="ttd-run-title" id="ttd-run-title">Select a run to debug</span>
        <div class="ttd-view-tabs" id="ttd-view-tabs">
          <button class="ttd-tab active" id="ttd-tab-graph"    onclick="ttdSetView('graph')">Graph</button>
          <button class="ttd-tab"        id="ttd-tab-timeline" onclick="ttdSetView('timeline')">Timeline</button>
          <button class="ttd-tab"        id="ttd-tab-diff"     onclick="ttdSetView('diff')">Diff</button>
        </div>
        <button class="ttd-toolbar-btn" onclick="ttdFitView()" title="Fit graph to window">⊡ Fit</button>
        <button class="ttd-toolbar-btn" onclick="ttdToggleDetail()" id="ttd-detail-toggle">Detail ▶</button>
      </div>

      <!-- Viewport (graph + timeline + diff stacked) -->
      <div style="flex:1;display:flex;overflow:hidden;min-height:0;position:relative">

        <!-- Graph canvas -->
        <div class="ttd-canvas-wrap" id="ttd-canvas-wrap" style="display:block">
          <div class="ttd-canvas-inner" id="ttd-canvas-inner">
            <svg id="ttd-svg" style="position:absolute;inset:0;overflow:visible;pointer-events:none">
              <defs>
                <marker id="ttd-arrow-default" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                  <path d="M0,0 L0,6 L8,3 z" fill="rgba(255,255,255,.18)"/>
                </marker>
                <marker id="ttd-arrow-active" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                  <path d="M0,0 L0,6 L8,3 z" fill="#5b8af8"/>
                </marker>
                <marker id="ttd-arrow-done" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                  <path d="M0,0 L0,6 L8,3 z" fill="#3dba7a"/>
                </marker>
                <marker id="ttd-arrow-error" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                  <path d="M0,0 L0,6 L8,3 z" fill="#e85252"/>
                </marker>
                <filter id="ttd-glow">
                  <feGaussianBlur stdDeviation="3" result="blur"/>
                  <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
                </filter>
              </defs>
              <g id="ttd-edges-g"></g>
            </svg>
            <div id="ttd-nodes-g"></div>
          </div>

          <!-- Empty state (shown when no run selected) -->
          <div class="ttd-empty" id="ttd-empty">
            <div class="ttd-empty-icon">⏮️</div>
            <div class="ttd-empty-title">No Run Selected</div>
            <div class="ttd-empty-sub">
              Select a run from the sidebar to replay it frame-by-frame on the graph canvas,
              or run a workflow from the <strong style="color:var(--accent);cursor:pointer" onclick="nav('workflow')">Workflows</strong> pane first.
            </div>
          </div>

          <!-- Zoom controls -->
          <div class="ttd-zoom-controls" id="ttd-zoom-controls" style="display:none">
            <button class="ttd-zoom-btn" onclick="ttdZoom(1.2)" title="Zoom in">+</button>
            <div class="ttd-zoom-label" id="ttd-zoom-label">100%</div>
            <button class="ttd-zoom-btn" onclick="ttdZoom(1/1.2)" title="Zoom out">−</button>
          </div>

          <!-- Fit button -->
          <button class="ttd-fit-btn" id="ttd-fit-btn" onclick="ttdFitView()" style="display:none">⊡ Fit</button>

          <!-- Minimap -->
          <div class="ttd-minimap" id="ttd-minimap" style="display:none">
            <canvas id="ttd-minimap-canvas" width="120" height="80"></canvas>
          </div>

          <!-- KB hint -->
          <div class="ttd-kb-hint" id="ttd-kb-hint">← → Arrow keys to step · Space to play/pause</div>
        </div>

        <!-- Timeline lane view -->
        <div class="ttd-timeline-view" id="ttd-timeline-view">
          <div id="ttd-lane-content"></div>
        </div>

        <!-- Diff view -->
        <div class="ttd-diff-view" id="ttd-diff-view">
          <div id="ttd-diff-content">
            <div class="ttd-empty">
              <div class="ttd-empty-icon">↔</div>
              <div class="ttd-empty-title">Run Diff</div>
              <div class="ttd-empty-sub">Select two runs using the checkboxes in the sidebar, then click "Diff Runs".</div>
            </div>
          </div>
        </div>

        <!-- Detail panel -->
        <div class="ttd-detail collapsed" id="ttd-detail">
          <div class="ttd-detail-head">
            <h4 id="ttd-detail-node-name">Frame Detail</h4>
            <button onclick="ttdToggleDetail()" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:13px">✕</button>
          </div>
          <div class="ttd-detail-body" id="ttd-detail-body">
            <div style="color:var(--text-3);font-size:12px">Click a node to see its details.</div>
          </div>
        </div>
      </div>

      <!-- Playback controls -->
      <div class="ttd-controls" id="ttd-controls" style="display:none">
        <!-- Scrubber -->
        <div class="ttd-scrubber-wrap" id="ttd-scrubber" onclick="ttdScrubClick(event)" onmousemove="ttdScrubHover(event)">
          <div class="ttd-scrubber-track" id="ttd-scrub-track">
            <div class="ttd-frame-markers" id="ttd-frame-pips"></div>
            <div class="ttd-scrubber-fill" id="ttd-scrub-fill" style="width:0%"></div>
            <div class="ttd-scrubber-thumb" id="ttd-scrub-thumb" style="left:0%"></div>
          </div>
        </div>
        <!-- Buttons row -->
        <div class="ttd-ctrl-row">
          <button class="ttd-ctrl-btn" onclick="ttdGoFirst()"  title="First frame (Home)">⏮</button>
          <button class="ttd-ctrl-btn" onclick="ttdStepBack()" title="Previous frame (←)">◁</button>
          <button class="ttd-ctrl-btn" id="ttd-play-btn" onclick="ttdTogglePlay()" title="Play/Pause (Space)">▶</button>
          <button class="ttd-ctrl-btn" onclick="ttdStepFwd()"  title="Next frame (→)">▷</button>
          <button class="ttd-ctrl-btn" onclick="ttdGoLast()"   title="Last frame (End)">⏭</button>
          <select class="ttd-speed-select" id="ttd-speed" title="Playback speed">
            <option value="800">0.25×</option>
            <option value="400">0.5×</option>
            <option value="220" selected>1×</option>
            <option value="110">2×</option>
            <option value="50">4×</option>
          </select>
          <span class="ttd-frame-counter" id="ttd-frame-counter">Frame 0 / 0</span>
          <span class="ttd-frame-time" id="ttd-frame-time"></span>
          <button class="ttd-rerun-btn" id="ttd-rerun-btn" onclick="ttdRerunFrom()">↺ Re-run from here</button>
        </div>
      </div>
    </div>
  </div>`;

  // Init pan+zoom on canvas
  ttdInitCanvasInteraction();
  // Keyboard shortcuts
  ttdInitKeyboard();
  // Load runs
  await ttdLoadRuns();
  // Show kb hint briefly
  const hint = document.getElementById('ttd-kb-hint');
  if (hint) { hint.classList.add('visible'); setTimeout(() => hint.classList.remove('visible'), 3000); }
}

// ── Constants ────────────────────────────────────────────────────
const TTD_COLORS = {
  trigger:'#5b8af8', agent:'#9d74f5', condition:'#e8a237',
  transform:'#38c5d8', output:'#3dba7a', delay:'#7a8aaa',
  webhook:'#4cc98a', memory:'#c084fc', code:'#f08850', loop:'#f06080'
};
const TTD_ICONS = {
  trigger:'⚡', agent:'🤖', condition:'🔀', transform:'⚙️',
  output:'📤', delay:'⏱️', webhook:'🌐', memory:'🧠', code:'</>', loop:'🔁'
};

// ── Load & filter runs ───────────────────────────────────────────
async function ttdLoadRuns() {
  try {
    const r = await fetch('/api/replay/runs?limit=100');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const d = await r.json();
    _ttdRuns = d.runs || [];
    ttdPopulateWfFilter();
    ttdRenderRunList();
  } catch(e) {
    const list = document.getElementById('ttd-run-list');
    if (list) list.innerHTML = `<div style="color:var(--danger);font-size:12px;padding:10px">Failed to load runs: ${escHtml(e.message)}</div>`;
  }
}

function ttdPopulateWfFilter() {
  const sel = document.getElementById('ttd-wf-filter');
  if (!sel) return;
  const seen = new Map();
  _ttdRuns.forEach(r => { if (!seen.has(r.workflow_id)) seen.set(r.workflow_id, r.workflow_nm || r.workflow_id); });
  sel.innerHTML = '<option value="">All workflows</option>' +
    [...seen.entries()].map(([id, nm]) => `<option value="${escHtml(id)}">${escHtml(nm)}</option>`).join('');
}

function ttdSearchRuns(q) {
  _ttdSearchQ = q.toLowerCase();
  ttdRenderRunList();
}

function ttdFilterByWf(wfId) {
  _ttdFilterWf = wfId;
  ttdRenderRunList();
}

function ttdGetFilteredRuns() {
  return _ttdRuns.filter(r => {
    if (_ttdFilterWf && r.workflow_id !== _ttdFilterWf) return false;
    if (_ttdSearchQ) {
      const hay = ((r.workflow_nm || '') + ' ' + (r.id || '') + ' ' + (r.input || '')).toLowerCase();
      if (!hay.includes(_ttdSearchQ)) return false;
    }
    return true;
  });
}

function ttdRenderRunList() {
  const list = document.getElementById('ttd-run-list');
  if (!list) return;
  const runs = ttdGetFilteredRuns();
  if (!runs.length) {
    list.innerHTML = `<div style="color:var(--text-3);font-size:12px;padding:10px;line-height:1.7">
      ${_ttdRuns.length ? 'No runs match your filter.' : 'No runs yet. <strong style="color:var(--accent);cursor:pointer" onclick="nav(\'workflow\')">Run a workflow</strong> first.'}
    </div>`;
    return;
  }
  list.innerHTML = runs.map(run => {
    const isActive = _ttdRun?.run?.id === run.id;
    const isDiffA  = _ttdDiffRunA === run.id;
    const isDiffB  = _ttdDiffRunB === run.id;
    const diffLabel = isDiffA ? 'A' : (isDiffB ? 'B' : '');
    const ts = new Date(run.created_at).toLocaleString(undefined, {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
    return `<div class="ttd-run-card ${isActive?'active':''}" onclick="ttdSelectRun(${JSON.stringify(run.id)})">
      <div class="ttd-run-card-top">
        <input type="checkbox" class="ttd-diff-checkbox" title="Select for diff"
          onclick="event.stopPropagation();ttdToggleDiffSelect(${JSON.stringify(run.id)},this.checked)"
          ${isDiffA||isDiffB?'checked':''}>
        ${diffLabel ? `<span style="font-size:10px;font-weight:700;color:${isDiffA?'#3dba7a':'#9d74f5'}">${diffLabel}</span>` : ''}
        <span class="ttd-badge ${run.status}">${run.status}</span>
        <span class="ttd-run-ms">${(run.total_ms||0).toLocaleString()}ms</span>
      </div>
      <div class="ttd-run-name">${escHtml(run.workflow_nm || run.workflow_id)}</div>
      <div class="ttd-run-meta">${run.node_count||0} nodes · ${ts}</div>
      ${run.input ? `<div class="ttd-run-input">"${escHtml((run.input||'').slice(0,50))}"</div>` : ''}
    </div>`;
  }).join('');
}

// ── Select & load a run ──────────────────────────────────────────
async function ttdSelectRun(runId) {
  try {
    const [tlResp, rdResp] = await Promise.all([
      fetch(`/api/replay/runs/${encodeURIComponent(runId)}/timeline`),
      fetch(`/api/replay/runs/${encodeURIComponent(runId)}`),
    ]);
    if (!tlResp.ok || !rdResp.ok) { gmAlert('Failed to load run.'); return; }
    const [tl, rd] = await Promise.all([tlResp.json(), rdResp.json()]);
    if (tl.ok === false) { gmAlert('Run not found: ' + (tl.error||'')); return; }

    _ttdRun      = { ...tl, frames: rd.frames || [] };
    _ttdFrame    = 0;
    _ttdPlaying  = false;
    clearInterval(_ttdPlayTimer);

    // Load workflow graph
    const wfId = tl.run?.workflow_id;
    _ttdWf = null;
    if (wfId) {
      try {
        const wfR = await fetch(`/api/workflow/${encodeURIComponent(wfId)}`);
        _ttdWf = wfR.ok ? await wfR.json() : null;
      } catch(e) {}
    }
    // If no workflow file, reconstruct a minimal graph from frames
    if (!_ttdWf || !_ttdWf.nodes?.length) {
      _ttdWf = ttdReconstructGraph(_ttdRun.frames || []);
    }

    // Update UI
    document.getElementById('ttd-run-title').textContent =
      `${tl.run?.workflow_nm || 'Run'} · ${rd.frames?.length || 0} frames · ${(tl.duration_ms||0).toLocaleString()}ms`;
    document.getElementById('ttd-empty').style.display = 'none';
    document.getElementById('ttd-controls').style.display = 'block';
    document.getElementById('ttd-zoom-controls').style.display = 'flex';
    document.getElementById('ttd-fit-btn').style.display = 'block';
    document.getElementById('ttd-minimap').style.display = 'block';
    document.getElementById('ttd-play-btn').textContent = '▶';
    document.getElementById('ttd-play-btn').classList.remove('playing');

    ttdRenderRunList();
    ttdBuildGraph();
    ttdBuildTimeline();
    ttdGoFrame(0);
    ttdFitView();
  } catch(e) { console.error('ttdSelectRun', e); gmAlert('Error loading run: ' + e.message); }
}

// ── Reconstruct graph from frames (when workflow file is missing) ──
function ttdReconstructGraph(frames) {
  const nodeMap = new Map();
  const edges   = [];
  const seen    = new Set();
  frames.forEach(f => {
    if (!nodeMap.has(f.node_id)) {
      nodeMap.set(f.node_id, {
        id: f.node_id, type: f.node_type || 'agent',
        label: f.node_label || f.node_id, config: {}
      });
    }
  });
  // Auto-layout: arrange nodes horizontally in execution order
  const nodeIds = [...new Set(frames.filter(f=>f.event_type==='node_start').map(f=>f.node_id))];
  const COLS = Math.ceil(Math.sqrt(nodeIds.length));
  nodeIds.forEach((nid, i) => {
    const n = nodeMap.get(nid);
    n.x = (i % COLS) * 260 + 60;
    n.y = Math.floor(i / COLS) * 160 + 60;
  });
  // Build sequential edges from execution order
  for (let i = 0; i < nodeIds.length - 1; i++) {
    edges.push({ id: `e${i}`, from: nodeIds[i], to: nodeIds[i+1] });
  }
  return { nodes: [...nodeMap.values()], edges, reconstructed: true };
}

// ── Build graph canvas ───────────────────────────────────────────
function ttdBuildGraph() {
  if (!_ttdWf) return;
  const nodesG  = document.getElementById('ttd-nodes-g');
  const edgesG  = document.getElementById('ttd-edges-g');
  if (!nodesG || !edgesG) return;

  const nodes = _ttdWf.nodes || [];
  const edges = _ttdWf.edges || [];

  // Nodes
  nodesG.innerHTML = nodes.map(n => {
    const col = TTD_COLORS[n.type] || '#7a8aaa';
    const icon = TTD_ICONS[n.type] || '⬡';
    return `<div class="ttd-node n-pending" id="ttdn-${n.id}"
              style="left:${n.x||0}px;top:${n.y||0}px;border-color:${col}22"
              onclick="ttdClickNode(event,${JSON.stringify(n.id)})">
      <div class="ttd-node-hdr">
        <span class="ttd-node-icon">${icon}</span>
        <span class="ttd-node-label" title="${escHtml(n.label||n.type)}">${escHtml(n.label||n.type)}</span>
        <span class="ttd-node-type-tag" style="background:${col}22;color:${col}">${n.type}</span>
      </div>
      <div class="ttd-node-body" id="ttdnb-${n.id}">—</div>
      <div class="ttd-node-footer">
        <span class="ttd-node-dur" id="ttdnd-${n.id}"></span>
        <div class="ttd-node-bar"><div class="ttd-node-bar-fill" id="ttdnbar-${n.id}" style="width:0%"></div></div>
      </div>
    </div>`;
  }).join('');

  // Measure canvas bounds after nodes render
  setTimeout(() => {
    ttdDrawEdges(nodes, edges);
    ttdUpdateMinimap();
  }, 50);
}

function ttdDrawEdges(nodes, edges) {
  const edgesG = document.getElementById('ttd-edges-g');
  if (!edgesG) return;
  edgesG.innerHTML = '';

  const nodeW = 200, nodeH = 90; // approximate node size

  edges.forEach((e, i) => {
    const from = nodes.find(n => n.id === e.from);
    const to   = nodes.find(n => n.id === e.to);
    if (!from || !to) return;

    const x1 = (from.x||0) + nodeW;
    const y1 = (from.y||0) + nodeH/2;
    const x2 = (to.x||0);
    const y2 = (to.y||0) + nodeH/2;
    const cx = (x1 + x2) / 2;

    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    const d = `M${x1},${y1} C${cx},${y1} ${cx},${y2} ${x2},${y2}`;
    path.setAttribute('d', d);
    path.setAttribute('id', `ttde-${e.id || i}`);
    path.setAttribute('stroke', 'rgba(255,255,255,.12)');
    path.setAttribute('stroke-width', '1.5');
    path.setAttribute('fill', 'none');
    path.setAttribute('marker-end', 'url(#ttd-arrow-default)');
    edgesG.appendChild(path);

    // Edge label (yes/no for conditions)
    if (e.label) {
      const mid = { x: cx, y: (y1+y2)/2 };
      const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      txt.setAttribute('x', mid.x);
      txt.setAttribute('y', mid.y - 4);
      txt.setAttribute('text-anchor', 'middle');
      txt.setAttribute('class', 'ttd-edge-label');
      txt.textContent = e.label;
      edgesG.appendChild(txt);
    }
  });
}

// ── Frame navigation ─────────────────────────────────────────────
function ttdGoFrame(idx) {
  if (!_ttdRun) return;
  const frames = _ttdRun.frames || [];
  if (!frames.length) return;
  _ttdFrame = Math.max(0, Math.min(idx, frames.length - 1));

  // Scrubber
  const pct = frames.length > 1 ? (_ttdFrame / (frames.length - 1) * 100) : 0;
  const fill  = document.getElementById('ttd-scrub-fill');
  const thumb = document.getElementById('ttd-scrub-thumb');
  if (fill)  fill.style.width = pct + '%';
  if (thumb) thumb.style.left = pct + '%';

  // Counter
  const counter = document.getElementById('ttd-frame-counter');
  if (counter) counter.textContent = `Frame ${_ttdFrame + 1} / ${frames.length}`;

  // Time info
  const frame = frames[_ttdFrame];
  const timeEl = document.getElementById('ttd-frame-time');
  if (timeEl && frame) {
    const relMs = frame.rel_ms != null ? frame.rel_ms : 0;
    timeEl.textContent = `t+${relMs}ms`;
  }

  ttdApplyGraphState(_ttdFrame);
  ttdUpdateTimelineScrubber(_ttdFrame);
  if (_ttdView === 'graph' && frame) ttdShowNodeDetail(frame.node_id, _ttdFrame);
  ttdUpdateMinimap();
}

function ttdApplyGraphState(upToIdx) {
  if (!_ttdRun || !_ttdWf) return;
  const frames = _ttdRun.frames || [];
  const nodes  = _ttdWf.nodes || [];
  const edges  = _ttdWf.edges || [];

  // Reset all nodes
  nodes.forEach(n => {
    const el   = document.getElementById(`ttdn-${n.id}`);
    const body = document.getElementById(`ttdnb-${n.id}`);
    const dur  = document.getElementById(`ttdnd-${n.id}`);
    const bar  = document.getElementById(`ttdnbar-${n.id}`);
    if (el)   el.className = 'ttd-node n-pending';
    if (body) body.textContent = '—';
    if (dur)  dur.textContent = '';
    if (bar)  { bar.className = 'ttd-node-bar-fill'; bar.style.width = '0%'; }
  });

  // Reset all edges
  edges.forEach((e, i) => {
    const p = document.getElementById(`ttde-${e.id || i}`);
    if (p) {
      p.setAttribute('stroke', 'rgba(255,255,255,.12)');
      p.setAttribute('stroke-width', '1.5');
      p.setAttribute('marker-end', 'url(#ttd-arrow-default)');
    }
  });

  // Track node state as we replay
  const nodeStates = {}; // nid → {state, output, dur, error}
  const visitedEdges = new Set();
  let prevNid = null;

  for (let i = 0; i <= upToIdx && i < frames.length; i++) {
    const f = frames[i];
    if (!f) continue;
    const isLast = (i === upToIdx);

    if (f.event_type === 'node_start') {
      nodeStates[f.node_id] = { state: isLast ? 'active' : 'started', output: '', dur: 0, error: '' };
      // Highlight incoming edges as active
      if (isLast) {
        edges.forEach((e, ei) => {
          if (e.to === f.node_id) {
            const p = document.getElementById(`ttde-${e.id || ei}`);
            if (p) {
              p.setAttribute('stroke', '#5b8af8');
              p.setAttribute('stroke-width', '2');
              p.setAttribute('marker-end', 'url(#ttd-arrow-active)');
            }
          }
        });
      }
    } else if (f.event_type === 'node_output') {
      const hasErr = f.error && f.error.length > 0;
      nodeStates[f.node_id] = {
        state: isLast ? 'active' : (hasErr ? 'error' : 'done'),
        output: f.output || '',
        dur: f.duration_ms || 0,
        error: f.error || ''
      };
      // Mark edges out of this node as done
      if (!isLast) {
        edges.forEach((e, ei) => {
          if (e.from === f.node_id) {
            const p = document.getElementById(`ttde-${e.id || ei}`);
            if (p) {
              p.setAttribute('stroke', hasErr ? '#e85252' : '#3dba7a');
              p.setAttribute('stroke-width', hasErr ? '1.5' : '2');
              p.setAttribute('marker-end', hasErr ? 'url(#ttd-arrow-error)' : 'url(#ttd-arrow-done)');
            }
          }
        });
      }
    }
  }

  // Apply visual state to DOM nodes
  Object.entries(nodeStates).forEach(([nid, st]) => {
    const el   = document.getElementById(`ttdn-${nid}`);
    const body = document.getElementById(`ttdnb-${nid}`);
    const dur  = document.getElementById(`ttdnd-${nid}`);
    const bar  = document.getElementById(`ttdnbar-${nid}`);
    if (!el) return;

    const stateClass = { active:'n-active', done:'n-done', error:'n-error', started:'' }[st.state] || '';
    el.className = `ttd-node ${stateClass}`;

    if (body) {
      const txt = st.error ? `⚠️ ${st.error.slice(0,80)}` : (st.output.slice(0,90) + (st.output.length>90?'…':''));
      body.textContent = txt || '—';
      body.style.color = st.error ? 'var(--danger)' : 'var(--text-2)';
    }
    if (dur) dur.textContent = st.dur ? `${st.dur}ms` : '';
    if (bar) {
      bar.className = 'ttd-node-bar-fill ' + (st.state==='active'?'b-active': st.error?'b-error':'b-done');
      bar.style.width = st.state === 'pending' ? '0%' : '100%';
    }
  });

  // Scroll active node into view if it's off-screen
  const curFrame = frames[upToIdx];
  if (curFrame) {
    const activeEl = document.getElementById(`ttdn-${curFrame.node_id}`);
    if (activeEl) {
      // Don't auto-pan during play — let user control
      if (!_ttdPlaying) ttdScrollNodeIntoView(activeEl);
    }
  }
}

function ttdScrollNodeIntoView(el) {
  // Pan canvas so node is centered, respecting current zoom
  const wrap  = document.getElementById('ttd-canvas-wrap');
  const inner = document.getElementById('ttd-canvas-inner');
  if (!wrap || !inner) return;
  const wRect = wrap.getBoundingClientRect();
  const style = el.style;
  const nx    = parseFloat(style.left || el.offsetLeft);
  const ny    = parseFloat(style.top  || el.offsetTop);
  const nw    = el.offsetWidth || 180;
  const nh    = el.offsetHeight || 90;
  const targetX = wRect.width/2  - (nx + nw/2) * _ttdZoom;
  const targetY = wRect.height/2 - (ny + nh/2) * _ttdZoom;
  _ttdPanX = targetX;
  _ttdPanY = targetY;
  ttdApplyTransform();
}

// ── Node detail panel ────────────────────────────────────────────
function ttdClickNode(event, nodeId) {
  event.stopPropagation();
  // Deselect old
  document.querySelectorAll('.ttd-node.n-selected').forEach(el => el.classList.remove('n-selected'));
  const el = document.getElementById(`ttdn-${nodeId}`);
  if (el) el.classList.add('n-selected');
  ttdShowNodeDetail(nodeId, _ttdFrame);
  // Open detail panel if collapsed
  const detail = document.getElementById('ttd-detail');
  if (detail?.classList.contains('collapsed')) ttdToggleDetail();
}

function ttdShowNodeDetail(nodeId, upToIdx) {
  const body    = document.getElementById('ttd-detail-body');
  const nameEl  = document.getElementById('ttd-detail-node-name');
  if (!body || !_ttdRun) return;

  const frames = _ttdRun.frames || [];
  // Find last frame for this node up to current position
  let startFrame = null, outputFrame = null;
  for (let i = upToIdx; i >= 0; i--) {
    if (frames[i]?.node_id !== nodeId) continue;
    if (!outputFrame && frames[i].event_type === 'node_output') outputFrame = frames[i];
    if (!startFrame  && frames[i].event_type === 'node_start')  startFrame  = frames[i];
    if (startFrame && outputFrame) break;
  }

  const frame = outputFrame || startFrame;
  if (!frame) { body.innerHTML = '<div style="color:var(--text-3);font-size:12px">Not yet reached.</div>'; return; }

  if (nameEl) nameEl.textContent = frame.node_label || nodeId;

  const col   = TTD_COLORS[frame.node_type] || '#7a8aaa';
  const icon  = TTD_ICONS[frame.node_type]  || '⬡';
  const isErr = frame.error && frame.error.length > 0;

  let ctx = {};
  try { ctx = JSON.parse(frame.input_ctx || '{}'); } catch(e) {}

  const copyBtn = (text) =>
    `<button class="ttd-copy-btn" onclick="navigator.clipboard.writeText(${JSON.stringify(text)}).then(()=>showToast('Copied!'))">Copy</button>`;

  body.innerHTML = `
    <!-- Node identity -->
    <div class="ttd-detail-section">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
        <span style="font-size:20px">${icon}</span>
        <div>
          <div style="font-size:13px;font-weight:700;color:var(--text-0)">${escHtml(frame.node_label || nodeId)}</div>
          <div style="font-size:10px;color:${col};font-weight:600;text-transform:uppercase">${frame.node_type}</div>
        </div>
      </div>
    </div>

    <!-- Status -->
    <div class="ttd-detail-section">
      <div class="ttd-detail-section-label">Status</div>
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <span class="ttd-detail-badge ${isErr?'':''}${frame.event_type==='node_output'?(isErr?'':''):''}"
              style="background:${isErr?'rgba(232,82,82,.15)':frame.event_type==='node_output'?'rgba(61,186,122,.15)':'rgba(91,138,248,.15)'};
                     color:${isErr?'#e85252':frame.event_type==='node_output'?'#3dba7a':'#5b8af8'}">
          ${isErr ? '❌ Error' : frame.event_type === 'node_output' ? '✅ Complete' : '⏳ Running'}
        </span>
        ${frame.duration_ms ? `<span style="font-size:11px;color:var(--accent)">${frame.duration_ms}ms</span>` : ''}
        <span style="font-size:10px;color:var(--text-3)">Frame ${frame.frame_no}</span>
      </div>
    </div>

    <!-- Output -->
    ${frame.output ? `
    <div class="ttd-detail-section">
      <div class="ttd-detail-section-label">Output ${copyBtn(frame.output)}</div>
      <div class="ttd-detail-val">${escHtml(frame.output)}</div>
    </div>` : ''}

    <!-- Error -->
    ${isErr ? `
    <div class="ttd-detail-section">
      <div class="ttd-detail-section-label" style="color:var(--danger)">Error ${copyBtn(frame.error)}</div>
      <div class="ttd-detail-val v-error">${escHtml(frame.error)}</div>
    </div>` : ''}

    <!-- Context at entry -->
    ${ctx.prev_output ? `
    <div class="ttd-detail-section">
      <div class="ttd-detail-section-label">Context at entry ${copyBtn(ctx.prev_output)}</div>
      <div class="ttd-detail-val">${escHtml(ctx.prev_output.slice(0,500))}</div>
    </div>` : ''}

    <!-- Input prompt / config -->
    ${ctx.input ? `
    <div class="ttd-detail-section">
      <div class="ttd-detail-section-label">Original Input</div>
      <div class="ttd-detail-val">${escHtml(ctx.input.slice(0,300))}</div>
    </div>` : ''}

    <!-- Actions -->
    <div class="ttd-detail-section" style="margin-top:16px;display:flex;flex-direction:column;gap:6px">
      <button class="ttd-toolbar-btn" style="width:100%;justify-content:center"
        onclick="ttdRerunFromNode(${JSON.stringify(frame.node_id)},${frame.frame_no})">
        ↺ Re-run from this node
      </button>
    </div>
  `;
}

// ── Timeline view ─────────────────────────────────────────────────
function ttdBuildTimeline() {
  const view = document.getElementById('ttd-lane-content');
  if (!view || !_ttdRun) return;

  const frames     = _ttdRun.frames || [];
  const nodeLanes  = _ttdRun.node_lanes || {};
  const totalMs    = Math.max(_ttdRun.duration_ms || 1, 1);

  // Ruler ticks
  const ticks = [];
  const tickCount = 8;
  for (let i = 0; i <= tickCount; i++) {
    ticks.push(`<div class="ttd-ruler-tick" style="left:${i/tickCount*100}%">${Math.round(totalMs*i/tickCount)}ms</div>`);
  }

  const lanes = Object.entries(nodeLanes).map(([nid, nframes]) => {
    const nodeType  = nframes[0]?.node_type || 'agent';
    const nodeLabel = (nframes[0]?.node_label || nid).slice(0, 22);
    const col       = TTD_COLORS[nodeType] || '#7a8aaa';
    const outputs   = nframes.filter(f => f.event_type === 'node_output');

    const blocks = outputs.map(f => {
      const start = f.rel_ms ?? 0;
      const dur   = Math.max(f.duration_ms || 10, 1);
      const left  = (start / totalMs * 100).toFixed(2);
      const width = Math.max(dur / totalMs * 100, 0.4).toFixed(2);
      const isErr = f.error && f.error.length > 0;
      return `<div class="ttd-lane-block ${isErr?'lb-error':''}"
                style="left:${left}%;width:${width}%;background:${isErr?'#e85252':col};min-width:4px"
                title="${escHtml(nodeLabel)}: ${dur}ms${isErr?' — ERROR':''}"
                onclick="ttdGoToDbFrame(${f.id})">
        ${dur > 40 ? `${dur}ms` : ''}
      </div>`;
    }).join('');

    return `<div class="ttd-lane">
      <div class="ttd-lane-label" style="color:${col}" title="${escHtml(nodeLabel)}">${escHtml(nodeLabel)}</div>
      <div class="ttd-lane-track" id="ttdlane-${nid}">
        ${blocks || '<div style="color:var(--text-3);font-size:10px;padding:5px">no output</div>'}
        <div class="ttd-lane-scrubber" id="ttdscrub-${nid}"></div>
      </div>
    </div>`;
  }).join('');

  view.innerHTML = `
    <div class="ttd-timeline-header">
      <strong style="color:var(--text-0);font-size:13px">Execution Timeline</strong>
      <span style="font-size:11px;color:var(--text-3);margin-left:auto">Total: ${totalMs.toLocaleString()}ms · ${frames.length} frames</span>
    </div>
    <div class="ttd-timeline-ruler">${ticks.join('')}</div>
    ${lanes || '<div style="color:var(--text-3);padding:12px">No lane data</div>'}
  `;
}

function ttdUpdateTimelineScrubber(frameIdx) {
  if (!_ttdRun || _ttdView !== 'timeline') return;
  const frames   = _ttdRun.frames || [];
  const nodeLanes = _ttdRun.node_lanes || {};
  const totalMs  = Math.max(_ttdRun.duration_ms || 1, 1);
  const frame    = frames[frameIdx];
  if (!frame) return;
  const pct = ((frame.rel_ms ?? 0) / totalMs * 100).toFixed(2);
  Object.keys(nodeLanes).forEach(nid => {
    const s = document.getElementById(`ttdscrub-${nid}`);
    if (s) s.style.left = pct + '%';
  });
}

// ── Diff view ─────────────────────────────────────────────────────
function ttdToggleDiffSelect(runId, checked) {
  if (checked) {
    if (!_ttdDiffRunA) _ttdDiffRunA = runId;
    else if (!_ttdDiffRunB && _ttdDiffRunB !== runId) _ttdDiffRunB = runId;
    else { _ttdDiffRunA = runId; _ttdDiffRunB = null; }
  } else {
    if (_ttdDiffRunA === runId) _ttdDiffRunA = null;
    if (_ttdDiffRunB === runId) _ttdDiffRunB = null;
  }
  ttdRenderRunList();
}

async function ttdOpenDiffMode() {
  if (!_ttdDiffRunA || !_ttdDiffRunB) {
    gmAlert('Select exactly 2 runs using the checkboxes (☑) in the sidebar, then click Diff Runs.');
    return;
  }
  ttdSetView('diff');
  await ttdRunDiff(_ttdDiffRunA, _ttdDiffRunB);
}

async function ttdRunDiff(idA, idB) {
  const cont = document.getElementById('ttd-diff-content');
  if (!cont) return;
  cont.innerHTML = '<div style="color:var(--text-3);padding:20px;font-size:13px">Loading diff…</div>';
  try {
    const r = await fetch(`/api/replay/diff/${encodeURIComponent(idA)}/${encodeURIComponent(idB)}`);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const d = await r.json();
    const diffs  = d.diffs || [];
    const runA   = _ttdRuns.find(r => r.id === idA);
    const runB   = _ttdRuns.find(r => r.id === idB);

    const rows = diffs.map(df => {
      const cls  = df.only_in === 'both' ? (df.changed ? 'ttd-diff-changed' : '') :
                   df.only_in === 'a' ? 'ttd-diff-only-a' : 'ttd-diff-only-b';
      const badge = df.only_in !== 'both' ? `<span style="font-size:10px;color:${df.only_in==='a'?'#3dba7a':'#9d74f5'}">only in ${df.only_in.toUpperCase()}</span>` :
                    (df.changed ? '<span class="ttd-diff-changed-badge">⚠ Changed</span>' : '<span class="ttd-diff-same-badge">Same</span>');
      return `<tr class="${cls}">
        <td class="ttd-diff-node">${escHtml(df.node_label || df.node_id)}</td>
        <td>${badge}</td>
        <td class="ttd-diff-out">${df.a_output != null ? escHtml((df.a_output||'').slice(0,120)) : '<em style="color:var(--text-3)">—</em>'}
          ${df.a_duration != null ? `<div style="font-size:10px;color:var(--accent)">${df.a_duration}ms</div>` : ''}</td>
        <td class="ttd-diff-out">${df.b_output != null ? escHtml((df.b_output||'').slice(0,120)) : '<em style="color:var(--text-3)">—</em>'}
          ${df.b_duration != null ? `<div style="font-size:10px;color:var(--accent)">${df.b_duration}ms</div>` : ''}</td>
      </tr>`;
    }).join('');

    cont.innerHTML = `
      <div class="ttd-diff-header">
        <strong style="color:var(--text-0);font-size:13px">Run Diff</strong>
        <span class="ttd-badge" style="background:rgba(61,186,122,.15);color:#3dba7a">A: ${escHtml(runA?.workflow_nm||idA.slice(0,12))}</span>
        <span class="ttd-badge" style="background:rgba(157,116,245,.15);color:#9d74f5">B: ${escHtml(runB?.workflow_nm||idB.slice(0,12))}</span>
        <span style="font-size:11px;color:var(--text-3);margin-left:auto">${d.changed_count} of ${diffs.length} nodes changed</span>
      </div>
      <table class="ttd-diff-table">
        <thead><tr><th>Node</th><th>Status</th><th>Run A Output</th><th>Run B Output</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  } catch(e) {
    cont.innerHTML = `<div style="color:var(--danger);padding:20px">Diff failed: ${escHtml(e.message)}</div>`;
  }
}

// ── View switching ────────────────────────────────────────────────
function ttdSetView(view) {
  _ttdView = view;
  const canvasWrap  = document.getElementById('ttd-canvas-wrap');
  const timelineView = document.getElementById('ttd-timeline-view');
  const diffView    = document.getElementById('ttd-diff-view');
  const tabs = { graph:'ttd-tab-graph', timeline:'ttd-tab-timeline', diff:'ttd-tab-diff' };

  // Update tabs
  Object.entries(tabs).forEach(([v, id]) => {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('active', v === view);
  });

  if (view === 'graph') {
    if (canvasWrap)   canvasWrap.style.display = 'block';
    if (timelineView) timelineView.classList.remove('visible');
    if (diffView)     diffView.classList.remove('visible');
  } else if (view === 'timeline') {
    if (canvasWrap)   canvasWrap.style.display = 'none';
    if (timelineView) { timelineView.classList.add('visible'); ttdBuildTimeline(); }
    if (diffView)     diffView.classList.remove('visible');
  } else if (view === 'diff') {
    if (canvasWrap)   canvasWrap.style.display = 'none';
    if (timelineView) timelineView.classList.remove('visible');
    if (diffView)     diffView.classList.add('visible');
  }
}

// ── Detail panel toggle ──────────────────────────────────────────
function ttdToggleDetail() {
  const detail = document.getElementById('ttd-detail');
  const btn    = document.getElementById('ttd-detail-toggle');
  if (!detail) return;
  const collapsed = detail.classList.toggle('collapsed');
  if (btn) btn.textContent = collapsed ? 'Detail ▶' : 'Detail ✕';
}

// ── Playback ──────────────────────────────────────────────────────
function ttdTogglePlay() {
  if (_ttdPlaying) {
    _ttdPlaying = false;
    clearInterval(_ttdPlayTimer);
    const btn = document.getElementById('ttd-play-btn');
    if (btn) { btn.textContent = '▶'; btn.classList.remove('playing'); }
  } else {
    const frames = _ttdRun?.frames || [];
    if (_ttdFrame >= frames.length - 1) ttdGoFrame(0);
    _ttdPlaying = true;
    const btn = document.getElementById('ttd-play-btn');
    if (btn) { btn.textContent = '⏸'; btn.classList.add('playing'); }
    const speed = parseInt(document.getElementById('ttd-speed')?.value || '220');
    _ttdPlayTimer = setInterval(() => {
      const frms = _ttdRun?.frames || [];
      if (_ttdFrame >= frms.length - 1) {
        _ttdPlaying = false;
        clearInterval(_ttdPlayTimer);
        const b = document.getElementById('ttd-play-btn');
        if (b) { b.textContent = '▶'; b.classList.remove('playing'); }
        return;
      }
      ttdGoFrame(_ttdFrame + 1);
    }, speed);
  }
}

function ttdStepFwd()  { ttdGoFrame(_ttdFrame + 1); }
function ttdStepBack() { ttdGoFrame(_ttdFrame - 1); }
function ttdGoFirst()  { ttdGoFrame(0); }
function ttdGoLast()   { ttdGoFrame((_ttdRun?.frames?.length || 1) - 1); }

function ttdScrubClick(e) {
  const track = document.getElementById('ttd-scrub-track');
  if (!track) return;
  const rect = track.getBoundingClientRect();
  const pct  = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  const idx  = Math.round(pct * ((_ttdRun?.frames?.length || 1) - 1));
  ttdGoFrame(idx);
}

function ttdScrubHover(e) {
  // Could show tooltip — skip for performance
}

function ttdGoToDbFrame(dbId) {
  const frames = _ttdRun?.frames || [];
  const idx    = frames.findIndex(f => f.id === dbId);
  if (idx >= 0) { ttdSetView('graph'); ttdGoFrame(idx); }
}

// Build frame pips on scrubber
function ttdBuildScrubberPips() {
  const container = document.getElementById('ttd-frame-pips');
  if (!container || !_ttdRun) return;
  const frames = _ttdRun.frames || [];
  container.innerHTML = frames.map((f, i) => {
    const pct  = frames.length > 1 ? (i / (frames.length-1) * 100) : 0;
    const col  = f.error ? '#e85252' : (f.event_type==='node_output' ? (TTD_COLORS[f.node_type]||'#7a8aaa') : 'rgba(255,255,255,.2)');
    return `<div class="ttd-frame-pip" style="left:${pct.toFixed(2)}%;background:${col}"></div>`;
  }).join('');
}

// ── Re-run ────────────────────────────────────────────────────────
async function ttdRerunFrom() {
  if (!_ttdRun) return;
  const frame = _ttdRun.frames?.[_ttdFrame];
  if (!frame) return;
  await ttdRerunFromNode(frame.node_id, frame.frame_no);
}

async function ttdRerunFromNode(nodeId, frameNo) {
  const ok = await gmConfirm(`Re-run from "${nodeId}" (frame ${frameNo})?`);
  if (!ok) return;
  try {
    const runId = _ttdRun.run?.id;
    const resp  = await fetch(`/api/replay/runs/${encodeURIComponent(runId)}/rerun-from/${frameNo}`,
      { method:'POST', headers:{'Content-Type':'application/json'}, body:'{}' });
    if (!resp.ok) { gmAlert('Re-run failed: HTTP ' + resp.status); return; }
    // Stream the response
    const reader = resp.body.getReader();
    const dec    = new TextDecoder();
    let buf = '', done_ = false;
    while (!done_) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const evs = buf.split('\n\n'); buf = evs.pop() || '';
      for (const ev of evs) {
        if (!ev.startsWith('data:')) continue;
        try {
          const d = JSON.parse(ev.slice(5).trim());
          if (d.type === 'done') { done_ = true; break; }
        } catch(e) {}
      }
    }
    showToast('✅ Re-run complete!');
    await ttdLoadRuns();
    ttdRenderRunList();
  } catch(ex) { gmAlert('Re-run failed: ' + ex.message); }
}

// ── Zoom & Pan ────────────────────────────────────────────────────
function ttdApplyTransform() {
  const inner = document.getElementById('ttd-canvas-inner');
  if (inner) inner.style.transform = `translate(${_ttdPanX}px,${_ttdPanY}px) scale(${_ttdZoom})`;
  const label = document.getElementById('ttd-zoom-label');
  if (label) label.textContent = Math.round(_ttdZoom * 100) + '%';
}

function ttdZoom(factor) {
  const wrap = document.getElementById('ttd-canvas-wrap');
  if (!wrap) return;
  const wRect = wrap.getBoundingClientRect();
  const cx = wRect.width / 2, cy = wRect.height / 2;
  // Zoom toward center
  _ttdPanX = cx - (cx - _ttdPanX) * factor;
  _ttdPanY = cy - (cy - _ttdPanY) * factor;
  _ttdZoom = Math.max(0.2, Math.min(3, _ttdZoom * factor));
  ttdApplyTransform();
  ttdUpdateMinimap();
}

function ttdFitView() {
  if (!_ttdWf) return;
  const wrap = document.getElementById('ttd-canvas-wrap');
  if (!wrap) return;
  const nodes = _ttdWf.nodes || [];
  if (!nodes.length) return;
  const wRect = wrap.getBoundingClientRect();
  const pad   = 60;
  const NODE_W = 200, NODE_H = 90;

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  nodes.forEach(n => {
    minX = Math.min(minX, n.x || 0);
    minY = Math.min(minY, n.y || 0);
    maxX = Math.max(maxX, (n.x || 0) + NODE_W);
    maxY = Math.max(maxY, (n.y || 0) + NODE_H);
  });

  const contentW = maxX - minX + pad * 2;
  const contentH = maxY - minY + pad * 2;
  const scaleX   = wRect.width  / contentW;
  const scaleY   = wRect.height / contentH;
  _ttdZoom = Math.max(0.2, Math.min(2, Math.min(scaleX, scaleY)));
  _ttdPanX = (wRect.width  - (maxX + minX) * _ttdZoom) / 2;
  _ttdPanY = (wRect.height - (maxY + minY) * _ttdZoom) / 2;
  ttdApplyTransform();
  ttdUpdateMinimap();
}

function ttdInitCanvasInteraction() {
  const wrap = document.getElementById('ttd-canvas-wrap');
  if (!wrap) return;

  // Wheel zoom
  wrap.addEventListener('wheel', e => {
    e.preventDefault();
    const rect   = wrap.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    const factor = e.deltaY < 0 ? 1.12 : 1/1.12;
    _ttdPanX = mouseX - (mouseX - _ttdPanX) * factor;
    _ttdPanY = mouseY - (mouseY - _ttdPanY) * factor;
    _ttdZoom = Math.max(0.2, Math.min(3, _ttdZoom * factor));
    ttdApplyTransform();
    ttdUpdateMinimap();
  }, { passive: false });

  // Pan drag
  wrap.addEventListener('mousedown', e => {
    if (e.target.closest('.ttd-node,.ttd-zoom-controls,.ttd-fit-btn,.ttd-minimap')) return;
    _ttdPanning  = true;
    _ttdPanStart = { x: e.clientX, y: e.clientY, px: _ttdPanX, py: _ttdPanY };
    wrap.style.cursor = 'grabbing';
  });
  document.addEventListener('mousemove', e => {
    if (!_ttdPanning) return;
    _ttdPanX = _ttdPanStart.px + (e.clientX - _ttdPanStart.x);
    _ttdPanY = _ttdPanStart.py + (e.clientY - _ttdPanStart.y);
    ttdApplyTransform();
  });
  document.addEventListener('mouseup', () => {
    if (_ttdPanning) {
      _ttdPanning = false;
      const wrap2 = document.getElementById('ttd-canvas-wrap');
      if (wrap2) wrap2.style.cursor = '';
      ttdUpdateMinimap();
    }
  });
}

// ── Minimap ───────────────────────────────────────────────────────
function ttdUpdateMinimap() {
  const canvas = document.getElementById('ttd-minimap-canvas');
  if (!canvas || !_ttdWf) return;
  const ctx   = canvas.getContext('2d');
  const W     = 120, H = 80;
  const nodes = _ttdWf.nodes || [];
  const edges = _ttdWf.edges || [];
  ctx.clearRect(0, 0, W, H);

  if (!nodes.length) return;
  const NODE_W = 200, NODE_H = 90;
  const pad = 8;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  nodes.forEach(n => {
    minX = Math.min(minX, n.x||0); minY = Math.min(minY, n.y||0);
    maxX = Math.max(maxX, (n.x||0)+NODE_W); maxY = Math.max(maxY, (n.y||0)+NODE_H);
  });
  const scX = (W - pad*2) / Math.max(maxX - minX, 1);
  const scY = (H - pad*2) / Math.max(maxY - minY, 1);
  const sc  = Math.min(scX, scY);

  const toMX = (x) => pad + (x - minX) * sc;
  const toMY = (y) => pad + (y - minY) * sc;

  // Draw edges
  ctx.strokeStyle = 'rgba(255,255,255,.15)';
  ctx.lineWidth   = 0.8;
  edges.forEach(e => {
    const fn = nodes.find(n=>n.id===e.from);
    const tn = nodes.find(n=>n.id===e.to);
    if (!fn||!tn) return;
    ctx.beginPath();
    ctx.moveTo(toMX((fn.x||0)+NODE_W), toMY((fn.y||0)+NODE_H/2));
    ctx.lineTo(toMX(tn.x||0),          toMY((tn.y||0)+NODE_H/2));
    ctx.stroke();
  });

  // Draw nodes
  const frames = _ttdRun?.frames || [];
  const nodeStates = {};
  for (let i = 0; i <= _ttdFrame && i < frames.length; i++) {
    const f = frames[i];
    if (f.event_type === 'node_output') {
      nodeStates[f.node_id] = f.error ? 'error' : 'done';
    } else if (f.event_type === 'node_start') {
      nodeStates[f.node_id] = 'active';
    }
  }

  nodes.forEach(n => {
    const st = nodeStates[n.id];
    const col = TTD_COLORS[n.type] || '#7a8aaa';
    ctx.fillStyle = st === 'active' ? col : st === 'done' ? '#3dba7a' : st === 'error' ? '#e85252' : 'rgba(255,255,255,.06)';
    const mw = Math.max(NODE_W * sc, 4);
    const mh = Math.max(NODE_H * sc * 0.6, 3);
    const rx = toMX(n.x || 0);
    const ry = toMY(n.y || 0);
    ctx.beginPath();
    ctx.roundRect(rx, ry, mw, mh, 1.5);
    ctx.fill();
  });

  // Viewport rectangle
  const wrap = document.getElementById('ttd-canvas-wrap');
  if (wrap) {
    const wRect = wrap.getBoundingClientRect();
    const vLeft   = (-_ttdPanX / _ttdZoom - minX) * sc + pad;
    const vTop    = (-_ttdPanY / _ttdZoom - minY) * sc + pad;
    const vWidth  = (wRect.width  / _ttdZoom) * sc;
    const vHeight = (wRect.height / _ttdZoom) * sc;
    ctx.strokeStyle = 'rgba(91,138,248,.6)';
    ctx.lineWidth   = 1;
    ctx.strokeRect(vLeft, vTop, vWidth, vHeight);
  }
}

// ── Keyboard shortcuts ────────────────────────────────────────────
function ttdInitKeyboard() {
  document.addEventListener('keydown', ttdKeyHandler);
}

function ttdKeyHandler(e) {
  // Only active when replay pane is visible
  const pane = document.getElementById('pane-replay');
  if (!pane || pane.style.display === 'none' || !_ttdRun) return;
  // Don't steal keys from inputs
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;

  switch(e.key) {
    case 'ArrowRight': e.preventDefault(); ttdStepFwd();      break;
    case 'ArrowLeft':  e.preventDefault(); ttdStepBack();     break;
    case 'Home':       e.preventDefault(); ttdGoFirst();      break;
    case 'End':        e.preventDefault(); ttdGoLast();       break;
    case ' ':          e.preventDefault(); ttdTogglePlay();   break;
    case '+': case '=': ttdZoom(1.2);                         break;
    case '-':            ttdZoom(1/1.2);                       break;
    case 'f': case 'F':  ttdFitView();                         break;
  }
}

// ── Backward compat aliases (used by old nav patches) ─────────────
// Let old code that references rpLoadRuns / renderReplay still work
async function rpLoadRuns(wfId) { return ttdLoadRuns(); }



// ══════════════════════════════════════════════════════════════════
//  OT COLLABORATIVE EDITOR
// ══════════════════════════════════════════════════════════════════

let _ceDoc      = null;   // current doc {id, title, content, revision, peers}
let _ceDocs     = [];
let _ceWS       = null;
let _cePeerId   = null;
let _cePeers    = {};
let _ceRevision = 0;
let _cePendingOps = [];
let _ceBuffer   = '';     // local text buffer
let _ceTypingTimer = null;
let _ceCursorPos = 0;

async function renderCollabEdit() {
  const pane = document.getElementById('pane-collabedit');
  if (!pane) return;

  pane.innerHTML = `
  

  <div class="ce-layout">
    <div class="ce-sidebar">
      <div class="ce-sidebar-top">
        <h3>✍️ Collab Docs</h3>
        <button onclick="ceNewDoc()" style="width:100%;padding:6px;background:var(--accent);border:none;border-radius:7px;color:#fff;font-size:12px;font-weight:600;cursor:pointer">＋ New Document</button>
      </div>
      <div class="ce-doc-list" id="ce-doc-list">Loading…</div>
    </div>

    <div class="ce-main">
      <div class="ce-topbar">
        <input class="ce-title-input" id="ce-title" placeholder="Untitled Document" onblur="ceSaveTitle()" value="">
        <div id="ce-status-badge" style="font-size:11px;background:var(--bg-3);border:1px solid var(--border);border-radius:6px;padding:3px 8px;color:var(--text-2)">Not connected</div>
        <div class="ce-presence-bar" id="ce-presence"></div>
        <div style="display:flex;gap:5px;margin-left:4px">
          <button class="btn-sm" onclick="ceUndo()" title="Undo (⌘Z)">↩</button>
          <button class="btn-sm" onclick="ceRedo()" title="Redo (⌘⇧Z)">↪</button>
          <button class="btn-sm" onclick="ceToggleHistory()">History</button>
          <button class="btn-sm" onclick="ceToggleChat()">💬 Chat</button>
          <button class="btn-sm" onclick="ceSnapshot()">📷 Snap</button>
          <button class="btn-sm" onclick="ceShare()">🔗 Share</button>
        </div>
      </div>

      <div style="display:flex;flex:1;overflow:hidden">
        <div class="ce-editor-wrap" style="flex:1">
          <textarea class="ce-editor" id="ce-editor"
            placeholder="Start typing… collaborate in real-time with teammates."
            oninput="ceHandleInput()"
            onkeydown="ceHandleKeydown(event)"
            onselect="ceSendCursor()"
            onclick="ceSendCursor()"
          ></textarea>
          <div class="ce-cursors" id="ce-cursors"></div>
        </div>
        <div class="ce-history" id="ce-history">
          <div style="font-size:11px;font-weight:700;color:var(--text-3);text-transform:uppercase;margin-bottom:8px">Op History</div>
          <div id="ce-history-ops"></div>
        </div>
      </div>

      <div class="ce-chat" id="ce-chat">
        <div class="ce-chat-msgs" id="ce-chat-msgs"></div>
        <div class="ce-chat-input-row">
          <input class="ce-chat-input" id="ce-chat-input" placeholder="Message collaborators…"
                 onkeydown="if(event.key==='Enter'){ceSendChat();event.preventDefault()}">
          <button class="btn-sm" onclick="ceSendChat()">Send</button>
        </div>
      </div>

      <div class="ce-statusbar">
        <div class="ce-op-indicator" id="ce-sync-dot"></div>
        <span id="ce-sync-label">idle</span>
        <span>Rev: <strong id="ce-rev">0</strong></span>
        <span id="ce-peers-count">0 peers</span>
        <span style="margin-left:auto" id="ce-word-count">0 words</span>
      </div>
    </div>
  </div>`;

  await ceLoadDocs();

  // Keyboard shortcuts
  document.addEventListener('keydown', e => {
    if (!document.getElementById('pane-collabedit')?.classList.contains('active')) return;
    if ((e.metaKey||e.ctrlKey) && e.key==='z' && !e.shiftKey) { e.preventDefault(); ceUndo(); }
    if ((e.metaKey||e.ctrlKey) && (e.key==='y' || (e.key==='z'&&e.shiftKey))) { e.preventDefault(); ceRedo(); }
  });
}

async function ceLoadDocs() {
  try {
    const r = await fetch('/api/crdt/docs');
    const d = await r.json();
    _ceDocs = d.docs || [];
    const list = document.getElementById('ce-doc-list');
    if (!list) return;
    list.innerHTML = _ceDocs.map(doc => `
      <div class="ce-doc-item ${_ceDoc?.id===doc.id?'active':''}" onclick="ceSelectDoc(${JSON.stringify(doc.id)})">
        <div style="font-weight:600;color:var(--text-0)">${escHtml(doc.title||'Untitled')}</div>
        <div style="font-size:10px;color:var(--text-3)">${doc.size||0} chars · rev ${doc.revision}</div>
      </div>
    `).join('') || '<div style="color:var(--text-3);font-size:12px">No docs yet</div>';
  } catch(e) {}
}

async function ceNewDoc() {
  const title = await gmPrompt('Document title:', 'New Document');
  if (!title) return;
  try {
    const r = await fetch('/api/crdt/docs', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({title, content:''})
    });
    const d = await r.json();
    await ceLoadDocs();
    ceSelectDoc(d.doc?.id||'');
  } catch(e) {}
}

async function ceSelectDoc(docId) {
  if (!docId) return;
  // Disconnect existing WS
  if (_ceWS) { _ceWS.close(); _ceWS=null; }
  _cePeers = {}; _ceRevision = 0; _cePendingOps = [];

  try {
    const r = await fetch(`/api/crdt/docs/${encodeURIComponent(docId)}`);
    _ceDoc = await r.json();
  } catch(e) { return; }

  // Update UI
  const editor = document.getElementById('ce-editor');
  const title  = document.getElementById('ce-title');
  if (editor) { editor.value = _ceDoc.content || ''; _ceBuffer = _ceDoc.content || ''; }
  if (title)  title.value = _ceDoc.title || '';
  document.getElementById('ce-rev').textContent = _ceDoc.revision || 0;
  _ceRevision = _ceDoc.revision || 0;
  ceUpdateWordCount();
  ceLoadDocs();

  // Connect WebSocket
  ceConnectWS(docId);
}

function ceConnectWS(docId) {
  const name = localStorage.getItem('collab_name') || `User_${Math.random().toString(36).slice(2,6)}`;
  // FIX 4: use wss:// on HTTPS to avoid mixed-content errors
  const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${wsProto}//${location.host}/api/crdt/docs/${docId}/ws`;

  _ceWS = new WebSocket(wsUrl);
  const badge = document.getElementById('ce-status-badge');

  _ceWS.onopen = () => {
    if (badge) { badge.textContent='Connecting…'; badge.style.color='var(--warning)'; }
    _ceWS.send(JSON.stringify({type:'join', name}));
  };

  _ceWS.onmessage = ({data}) => {
    try {
      const msg = JSON.parse(data);

      if (msg.type === 'init') {
        _cePeerId   = msg.peer_id;
        _ceRevision = msg.doc.revision;
        _cePeers    = {};
        (msg.doc.peers||[]).forEach(p => { _cePeers[p.id]=p; });
        const editor = document.getElementById('ce-editor');
        if (editor && msg.doc.content !== undefined) {
          editor.value = msg.doc.content;
          _ceBuffer    = msg.doc.content;
        }
        if (badge) { badge.textContent='Live'; badge.style.color='var(--success)'; }
        ceUpdatePresence();
      }
      else if (msg.type === 'op') {
        // Apply remote op to our editor
        const editor = document.getElementById('ce-editor');
        if (!editor) return;
        const curPos = editor.selectionStart;
        const newText = ceApplyOpLocal(_ceBuffer, msg.op);
        _ceBuffer = newText;
        editor.value = newText;
        _ceRevision = msg.revision;
        document.getElementById('ce-rev').textContent = _ceRevision;
        ceUpdateWordCount();
        ceAddHistoryEntry(msg.peer_name||msg.peer_id, msg.op);
      }
      else if (msg.type === 'ack') {
        _ceRevision = msg.revision;
        document.getElementById('ce-rev').textContent = _ceRevision;
        const dot = document.getElementById('ce-sync-dot');
        if (dot) { dot.className='ce-op-indicator'; }
        document.getElementById('ce-sync-label').textContent = 'synced';
      }
      else if (msg.type === 'cursor') {
        if (_cePeers[msg.peer_id]) _cePeers[msg.peer_id].position = msg.position;
        ceRenderRemoteCursors();
      }
      else if (msg.type === 'peer_joined') {
        _cePeers[msg.peer_id] = {id:msg.peer_id, name:msg.name, color:msg.color};
        ceUpdatePresence();
      }
      else if (msg.type === 'peer_left') {
        delete _cePeers[msg.peer_id];
        ceUpdatePresence();
        ceRenderRemoteCursors();
      }
      else if (msg.type === 'chat') {
        ceAppendChatMsg(msg.name||msg.peer_id, msg.message, msg.peer_id===_cePeerId);
      }
      else if (msg.type === 'ping') {
        _ceWS.send(JSON.stringify({type:'pong'}));
      }
    } catch(e) {}
  };

  _ceWS.onclose = () => {
    if (badge) { badge.textContent='Disconnected'; badge.style.color='var(--danger)'; }
    // Reconnect after 3s
    setTimeout(() => { if (_ceDoc) ceConnectWS(_ceDoc.id); }, 3000);
  };

  _ceWS.onerror = () => {
    if (badge) { badge.textContent='Error'; badge.style.color='var(--danger)'; }
  };
}

function ceHandleInput() {
  const editor = document.getElementById('ce-editor');
  if (!editor) return;
  const newText = editor.value;
  const oldText = _ceBuffer;

  // Compute the op (simple diff)
  const op = ceComputeOp(oldText, newText);
  _ceBuffer = newText;
  ceUpdateWordCount();

  if (!op.length || !_ceWS || _ceWS.readyState!==WebSocket.OPEN) return;

  // Show syncing indicator
  const dot = document.getElementById('ce-sync-dot');
  if (dot) dot.className='ce-op-indicator syncing';
  document.getElementById('ce-sync-label').textContent='syncing…';

  // Debounce: send after 80ms quiet
  clearTimeout(_ceTypingTimer);
  _ceTypingTimer = setTimeout(() => {
    if (_ceWS?.readyState===WebSocket.OPEN) {
      _ceWS.send(JSON.stringify({type:'op', op, revision:_ceRevision}));
    }
  }, 80);
}

function ceHandleKeydown(e) {
  // Ctrl+Z / Cmd+Z handled globally above
  // Tab → insert 2 spaces
  if (e.key==='Tab') {
    e.preventDefault();
    const editor = document.getElementById('ce-editor');
    if (!editor) return;
    const start = editor.selectionStart;
    const end   = editor.selectionEnd;
    const val   = editor.value;
    editor.value = val.slice(0,start)+'  '+val.slice(end);
    editor.selectionStart = editor.selectionEnd = start+2;
    ceHandleInput();
  }
}

function ceComputeOp(oldText, newText) {
  // Simple Myers-like diff → OT ops
  // Find common prefix
  let prefixLen = 0;
  while (prefixLen < oldText.length && prefixLen < newText.length && oldText[prefixLen]===newText[prefixLen]) prefixLen++;
  // Find common suffix
  let oldSuffix=oldText.length, newSuffix=newText.length;
  while (oldSuffix>prefixLen && newSuffix>prefixLen && oldText[oldSuffix-1]===newText[newSuffix-1]) { oldSuffix--; newSuffix--; }

  const op = [];
  if (prefixLen > 0)                           op.push(prefixLen);         // retain prefix
  if (oldSuffix-prefixLen > 0)                 op.push(-(oldSuffix-prefixLen)); // delete middle
  if (newText.slice(prefixLen,newSuffix).length > 0) op.push(newText.slice(prefixLen,newSuffix)); // insert
  const tailLen = oldText.length-oldSuffix;
  if (tailLen > 0)                             op.push(tailLen);           // retain suffix

  return op.filter(c => c!==0 && c!=='');
}

function ceApplyOpLocal(text, op) {
  let result='', pos=0;
  for (const c of op) {
    if (typeof c==='number' && c>0) { result+=text.slice(pos,pos+c); pos+=c; }
    else if (typeof c==='string')   { result+=c; }
    else if (typeof c==='number' && c<0) { pos+=Math.abs(c); }
  }
  result+=text.slice(pos);
  return result;
}

function ceSendCursor() {
  if (!_ceWS || _ceWS.readyState!==WebSocket.OPEN) return;
  const editor = document.getElementById('ce-editor');
  if (!editor) return;
  _ceCursorPos = editor.selectionStart;
  _ceWS.send(JSON.stringify({
    type:'cursor',
    position:_ceCursorPos,
    selection:{from:editor.selectionStart,to:editor.selectionEnd}
  }));
}

function ceRenderRemoteCursors() {
  const container = document.getElementById('ce-cursors');
  const editor    = document.getElementById('ce-editor');
  if (!container||!editor) return;
  // Remote cursors: approximate position using character count
  container.innerHTML = Object.values(_cePeers)
    .filter(p => p.id!==_cePeerId && p.position!==undefined)
    .map(p => {
      // Approximate pixel position (very rough — textarea lineHeight)
      const pos = Math.min(p.position||0, (editor.value||'').length);
      const before = (editor.value||'').slice(0,pos);
      const lines  = before.split('\n');
      const lineNo = lines.length-1;
      const col    = lines[lines.length-1].length;
      const top    = 24 + lineNo * 23.8;  // 24px padding + lineHeight
      const left   = 32 + col * 8.4;      // 32px padding + charWidth

      return `
        <div class="ce-remote-cursor" id="rc-${p.id}" style="left:${left}px;top:${top}px;height:20px;--peer-color:${p.color||'#5b8af8'}">
          <div class="ce-cursor-label" style="background:${p.color||'#5b8af8'}">${escHtml((p.name||'?')[0])}</div>
        </div>
      `;
    }).join('');
}

function ceUpdatePresence() {
  const bar = document.getElementById('ce-presence');
  const cnt = document.getElementById('ce-peers-count');
  if (!bar) return;
  const peers = Object.values(_cePeers).filter(p=>p.id!==_cePeerId);
  bar.innerHTML = peers.map(p=>`
    <div class="ce-peer-avatar" title="${escHtml(p.name||p.id)}" style="background:${p.color||'#5b8af8'}">
      ${escHtml((p.name||'?')[0].toUpperCase())}
    </div>
  `).join('');
  if (cnt) cnt.textContent = `${peers.length} peer${peers.length===1?'':'s'}`;
}

function ceUpdateWordCount() {
  const editor = document.getElementById('ce-editor');
  const el     = document.getElementById('ce-word-count');
  if (!el||!editor) return;
  const words = editor.value.trim().split(/\s+/).filter(Boolean).length;
  el.textContent = `${words} words`;
}

function ceAddHistoryEntry(peerName, op) {
  const container = document.getElementById('ce-history-ops');
  if (!container) return;
  const el = document.createElement('div');
  el.className = 'ce-op-row';
  const opStr = op.map(c=>typeof c==='string'?`+${JSON.stringify(c.slice(0,20))}`:c).join(', ');
  el.innerHTML = `<span class="peer" style="color:var(--accent)">${escHtml(peerName)}</span>: ${escHtml(opStr.slice(0,60))}`;
  container.insertBefore(el, container.firstChild);
  if (container.children.length>50) container.lastChild?.remove();
}

function ceToggleHistory() {
  document.getElementById('ce-history')?.classList.toggle('open');
}

function ceToggleChat() {
  document.getElementById('ce-chat')?.classList.toggle('open');
}

function ceSendChat() {
  const input = document.getElementById('ce-chat-input');
  if (!input||!_ceWS||_ceWS.readyState!==WebSocket.OPEN) return;
  const msg = input.value.trim();
  if (!msg) return;
  _ceWS.send(JSON.stringify({type:'chat', message:msg}));
  ceAppendChatMsg('You', msg, true);
  input.value='';
}

function ceAppendChatMsg(name, msg, isSelf) {
  const container = document.getElementById('ce-chat-msgs');
  if (!container) return;
  const el = document.createElement('div');
  el.className='ce-chat-msg';
  el.innerHTML=`<span class="ce-chat-peer" style="color:${isSelf?'var(--accent)':'var(--success)'}">${escHtml(name)}:</span> ${escHtml(msg)}`;
  container.appendChild(el);
  container.scrollTop=container.scrollHeight;
}

async function ceUndo() {
  if (!_ceWS||_ceWS.readyState!==WebSocket.OPEN) return;
  _ceWS.send(JSON.stringify({type:'undo'}));
}
async function ceRedo() {
  if (!_ceWS||_ceWS.readyState!==WebSocket.OPEN) return;
  _ceWS.send(JSON.stringify({type:'redo'}));
}

async function ceSaveTitle() {
  // FIX 3: use dedicated title-update endpoint instead of DELETE+recreate
  // (DELETE destroys revision history — very destructive for a rename)
  if (!_ceDoc) return;
  const title = (document.getElementById('ce-title'))?.value||'';
  try {
    // First try PATCH if endpoint exists (PUT full update)
    const r = await fetch(`/api/crdt/docs/${encodeURIComponent(_ceDoc.id)}`, {
      method: 'PUT',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({title, content: _ceBuffer})
    });
    if (r.ok) {
      _ceDoc.title = title;
      showToast('✅ Title saved');
      ceLoadDocs();
      return;
    }
  } catch(e) {}
  // Fallback: only recreate if PUT fails (avoids history loss on happy path)
  try {
    await fetch(`/api/crdt/docs/${encodeURIComponent(_ceDoc.id)}`,{method:'DELETE'}).catch(()=>{});
    const r = await fetch('/api/crdt/docs',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id:_ceDoc.id,title,content:_ceBuffer})});
    const d = await r.json();
    if (d.ok) { _ceDoc = d.doc; showToast('✅ Title saved'); ceLoadDocs(); }
  } catch(e) {}
}

async function ceSnapshot() {
  if (!_ceDoc) return;
  // FIX 5: showToast instead of blocking gmAlert
  try {
    const r = await fetch(`/api/crdt/docs/${encodeURIComponent(_ceDoc.id)}/snapshot`,{method:'POST'});
    const d = await r.json();
    showToast(`📷 Snapshot saved at revision ${d.revision||_ceRevision}`);
  } catch(ex) { showToast('⚠️ Snapshot failed: ' + ex.message); }
}

function ceShare() {
  if (!_ceDoc) return;
  // FIX 6: showToast instead of blocking gmAlert
  const url = `${location.origin}/?ce_doc=${_ceDoc.id}`;
  if (navigator.clipboard) {
    navigator.clipboard.writeText(url)
      .then(() => showToast(`🔗 Collab link copied to clipboard!`))
      .catch(() => showToast(`🔗 Share link: ${url}`));
  } else {
    showToast(`🔗 Share: ${url}`);
  }
}

// Auto-open CE doc from URL
(function ceAutoOpen() {
  const params = new URLSearchParams(location.search);
  const docId  = params.get('ce_doc');
  if (docId) {
    setTimeout(() => { nav('collabedit'); setTimeout(() => ceSelectDoc(docId), 600); }, 1200);
  }
})();


// ══════════════════════════════════════════════════════════════════
//  PLUGIN MARKETPLACE UI
// ══════════════════════════════════════════════════════════════════

let _mktCategory  = '';
let _mktSort      = 'featured';
let _mktQuery     = '';
let _mktInstalled = {};

async function renderMarketplace() {
  const pane = document.getElementById('pane-marketplace');
  if (!pane) return;
  pane.innerHTML = `<div style="padding:20px;color:var(--text-2)">Loading marketplace…</div>`;

  try {
    const [stats, featured, cats, inst] = await Promise.all([
      fetch('/api/marketplace/stats/overview').then(r=>{ if(!r.ok) throw new Error('stats '+r.status); return r.json(); }),
      fetch('/api/marketplace/featured?limit=4').then(r=>{ if(!r.ok) throw new Error('featured '+r.status); return r.json(); }),
      fetch('/api/marketplace/categories').then(r=>{ if(!r.ok) throw new Error('cats '+r.status); return r.json(); }),
      fetch('/api/marketplace/installed/list').then(r=>{ if(!r.ok) return {installed:[],count:0}; return r.json(); }),
    ]);

    // Build installed map
    _mktInstalled = {};
    (inst.installed||[]).forEach((i) => { _mktInstalled[i.pack_id] = i.version; });

    pane.innerHTML = `
    

    <!-- Hero -->
    <div class="mkt-hero">
      <h1>🛒 Plugin Marketplace</h1>
      <p>Discover and install community plugin packs — skills, integrations, and AI tools</p>
      <div class="mkt-search-row">
        <input class="mkt-search" id="mkt-search" placeholder="Search plugins…"
               oninput="mktSearch(this.value)" value="">
        <button class="btn" onclick="mktSearch(document.getElementById('mkt-search').value)" style="flex-shrink:0">Search</button>
        <button class="btn-sm" onclick="nav('pluginsdk')" style="flex-shrink:0">🛠️ Publish Pack</button>
      </div>
      <div class="mkt-stats">
        <div class="mkt-stat"><strong>${stats.total_packs||0}</strong> packs</div>
        <div class="mkt-stat"><strong>${(stats.total_downloads||0).toLocaleString()}</strong> downloads</div>
        <div class="mkt-stat"><strong>${stats.categories||0}</strong> categories</div>
        <div class="mkt-stat"><strong>${stats.installed||0}</strong> installed</div>
      </div>
    </div>

    <div class="mkt-body">
      <!-- Sidebar filters -->
      <div class="mkt-filters">
        <h4>Categories</h4>
        <button class="mkt-cat-btn active" onclick="mktFilterCat('')" id="mkt-cat-all">
          🏠 All <span class="mkt-cat-count">${stats.total_packs||0}</span>
        </button>
        ${(cats.categories||[]).map((c) => `
          <button class="mkt-cat-btn" onclick="mktFilterCat('${c.category}')" id="mkt-cat-${c.category}">
            ${catIcon(c.category)} ${capitalize(c.category)}
            <span class="mkt-cat-count">${c.count}</span>
          </button>
        `).join('')}

        <h4 style="margin-top:16px">Sort By</h4>
        <select class="mkt-sort-select" style="width:100%" onchange="mktChangeSort(this.value)">
          <option value="featured" selected>⭐ Featured</option>
          <option value="downloads">⬇ Most Downloaded</option>
          <option value="rating">⭐ Top Rated</option>
          <option value="newest">🆕 Newest</option>
        </select>

        <h4 style="margin-top:16px">Manage</h4>
        <button class="btn-sm" style="width:100%;margin-bottom:6px" onclick="mktCheckUpdates()">🔄 Check Updates</button>
        <button class="btn-sm" style="width:100%;margin-bottom:6px" onclick="mktShowInstalled()">📦 Installed (${Object.keys(_mktInstalled).length})</button>
        <button class="btn-sm" style="width:100%" onclick="mktUploadPack()">⬆ Upload ZIP</button>
      </div>

      <!-- Main content -->
      <div class="mkt-main" id="mkt-main">
        <!-- Featured section -->
        <div id="mkt-featured-section">
          <div class="mkt-section-title">⭐ Featured Packs</div>
          <div class="mkt-featured" id="mkt-featured">
            ${(featured.packs||[]).map((p) =>mktCardHTML(p,true)).join('')}
          </div>
        </div>

        <div class="mkt-toolbar">
          <div class="mkt-section-title" style="margin:0">All Packs</div>
          <div style="margin-left:auto;font-size:11px;color:var(--text-3)" id="mkt-result-count"></div>
        </div>
        <div class="mkt-grid" id="mkt-grid">Loading…</div>
      </div>
    </div>`;

    await mktLoadPacks();
  } catch(e) {
    pane.innerHTML = `<div style="padding:20px;color:var(--danger)">Marketplace load failed: ${e?.message||String(e)}</div>`;
  }
}

function catIcon(cat) {
  return {'core':'🤖','developer':'💻','content':'✍️','analytics':'📊','research':'🔬',
          'devops':'🚀','ai':'🎯','business':'💼','utility':'🔧','user':'👤'}[cat]||'📦';
}
function capitalize(s) { return s.charAt(0).toUpperCase()+s.slice(1); }

function mktCardHTML(p, featured=false) {
  const isInstalled = !!_mktInstalled[p.id];
  const rating = p.rating || (p.rating_count ? Math.round(p.rating_sum/p.rating_count*10)/10 : 0);
  const stars   = '★'.repeat(Math.round(rating)) + '☆'.repeat(5-Math.round(rating));

  return `
    <div class="mkt-card">
      <div class="mkt-card-hdr">
        <span class="mkt-card-icon">${p.icon||'🔧'}</span>
        <div class="mkt-card-meta">
          <div class="mkt-card-name">${escHtml(p.name)}</div>
          <div class="mkt-card-author">${escHtml(p.author||'')} · v${p.latest_ver||'1.0.0'}</div>
        </div>
        <div class="mkt-card-badges">
          ${p.verified?'<span class="mkt-verified">✓ Verified</span>':''}
          ${featured&&p.featured?'<span class="mkt-featured-badge">⭐</span>':''}
        </div>
      </div>
      <div class="mkt-card-desc">${escHtml((p.description||'').slice(0,100))}${(p.description||'').length>100?'…':''}</div>
      <div class="mkt-card-tags">
        ${(p.tags_list||[]).slice(0,3).map((t) =>`<span class="mkt-tag">${escHtml(t)}</span>`).join('')}
        ${(p.skills||[]).length?`<span class="mkt-tag">${p.skills.length} skills</span>`:''}
      </div>
      <div class="mkt-card-footer">
        <span class="mkt-rating" title="${rating}/5">
          ${stars} <span style="color:var(--text-3)">${rating}</span>
        </span>
        <span class="mkt-dl">⬇ ${(p.downloads||0).toLocaleString()}</span>
        <button class="mkt-install-btn ${isInstalled?'installed':''}"
                onclick="mktInstallOrUninstall(${JSON.stringify(p.id)},${JSON.stringify(p.name)},${isInstalled})"
                id="mkt-btn-${p.id}">
          ${isInstalled?'✓ Installed':'Install'}
        </button>
      </div>
      <div style="display:flex;gap:5px;margin-top:2px">
        <button class="btn-sm" onclick="mktViewDetail(${JSON.stringify(p.id)})">Details</button>
        <button class="btn-sm" onclick="window.open('/api/marketplace/'+encodeURIComponent(${JSON.stringify(p.id)})+'/download','_blank')">⬇ ZIP</button>
      </div>
    </div>
  `;
}

async function mktLoadPacks(q='', category='', sort='featured') {
  const grid = document.getElementById('mkt-grid');
  if (!grid) return;
  grid.innerHTML = '<div style="color:var(--text-3);padding:12px">Loading…</div>';
  try {
    const params = new URLSearchParams({q,sort,limit:'48'});
    if (category) params.set('category',category);
    const r = await fetch(`/api/marketplace?${encodeURIComponent(params)}`);
    if (!r.ok) { grid.innerHTML = `<div style="color:var(--danger);padding:12px">Failed to load (HTTP ${r.status})</div>`; return; }
    const d = await r.json();
    const cnt = document.getElementById('mkt-result-count');
    if (cnt) cnt.textContent = `${d.total||0} result${d.total!==1?'s':''}`;
    grid.innerHTML = (d.packs||[]).map((p) =>mktCardHTML(p)).join('') ||
      '<div style="color:var(--text-3);padding:20px;text-align:center">No packs found matching your criteria</div>';
  } catch(e) {
    grid.innerHTML = `<div style="color:var(--danger);padding:12px">Failed to load: ${e?.message||String(e)}</div>`;
  }
}

function mktSearch(q) {
  _mktQuery = q;
  const feat = document.getElementById('mkt-featured-section');
  if (feat) feat.style.display = q ? 'none' : '';
  mktLoadPacks(q, _mktCategory, _mktSort);
}

function mktFilterCat(cat) {
  _mktCategory = cat;
  document.querySelectorAll('.mkt-cat-btn').forEach(el => el.classList.remove('active'));
  const btn = document.getElementById(`mkt-cat-${cat||'all'}`);
  if (btn) btn.classList.add('active');
  const feat = document.getElementById('mkt-featured-section');
  if (feat) feat.style.display = cat ? 'none' : '';
  mktLoadPacks(_mktQuery, cat, _mktSort);
}

function mktChangeSort(sort) {
  _mktSort = sort;
  mktLoadPacks(_mktQuery, _mktCategory, sort);
}

async function mktInstallOrUninstall(packId, packName, isInstalled) {
  if (isInstalled) {
    const ok = await gmDanger(`Uninstall "${packName}"?`, `Remove this pack and all its skills from your workspace?`);
    if (!ok) return;
    try {
      const r = await fetch(`/api/marketplace/${encodeURIComponent(packId)}/uninstall`,{method:'DELETE'});
      if (!r.ok) { gmAlert('Uninstall request failed: '+r.status); return; }
      const d = await r.json();
      if (d.ok) {
        delete _mktInstalled[packId];
        const btn = document.getElementById(`mkt-btn-${packId}`);
        if (btn) { btn.textContent='Install'; btn.classList.remove('installed'); }
        showToast(`🗑️ ${packName} uninstalled.`);
      } else {
        gmAlert('Uninstall failed: '+(d.error||'Unknown error'));
      }
    } catch(ex) {
      gmAlert('Uninstall error: '+ex?.message);
    }
  } else {
    const btn = document.getElementById(`mkt-btn-${packId}`);
    if (btn) { btn.textContent='Installing…'; btn.disabled=true; }
    try {
      const r = await fetch(`/api/marketplace/${encodeURIComponent(packId)}/install`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      if (!r.ok) { if (btn) { btn.textContent='Install'; btn.disabled=false; } gmAlert('Install request failed: '+r.status); return; }
      const d = await r.json();
      if (d.ok) {
        _mktInstalled[packId] = d.version || 'latest';
        if (btn) { btn.textContent='✓ Installed'; btn.classList.add('installed'); btn.disabled=false; }
        showToast(d.message||`✅ ${packName} installed!`);
      } else {
        if (btn) { btn.textContent='Install'; btn.disabled=false; }
        gmAlert('Install failed: '+(d.error||'Unknown error'));
      }
    } catch(ex) {
      if (btn) { btn.textContent='Install'; btn.disabled=false; }
      gmAlert('Install error: '+ex?.message);
    }
  }
}

async function mktViewDetail(packId) {
  try {
    const resp = await fetch(`/api/marketplace/${encodeURIComponent(packId)}`);
    if (!resp.ok) { gmAlert('Pack not found: '+resp.status); return; }
    const d = await resp.json();
    if (d.ok === false) { gmAlert('Pack not found: '+(d.error||packId)); return; }
    const skills  = (d.skills||[]).map((s) =>`<div style="padding:5px 0;border-top:1px solid var(--border);font-size:12px">
      <strong style="color:var(--text-0)">${s.icon||'⚡'} ${escHtml(s.name||s.id)}</strong>
      <div style="color:var(--text-2)">${escHtml((s.description||s.prompt||'').slice(0,80))}</div>
    </div>`).join('');
    const reviews = (d.reviews||[]).map((rv) =>`<div style="padding:6px 0;border-top:1px solid var(--border)">
      <div style="font-size:11px;font-weight:700">${'★'.repeat(rv.rating)}${'☆'.repeat(5-rv.rating)} ${escHtml(rv.reviewer||'Anon')}</div>
      <div style="font-size:12px;color:var(--text-2)">${escHtml(rv.review_text||'')}</div>
    </div>`).join('');
    const isInst = !!_mktInstalled[packId];

    const overlay = document.createElement('div');
    overlay.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    overlay.innerHTML=`
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:16px;max-width:560px;width:100%;max-height:80vh;overflow-y:auto;padding:24px">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
          <span style="font-size:36px">${d.icon||'🔧'}</span>
          <div>
            <h2 style="margin:0;color:var(--text-0)">${escHtml(d.name||packId)}</h2>
            <div style="color:var(--text-3);font-size:12px">by ${escHtml(d.author||'')} · v${d.latest_ver||'1.0.0'} · ${(d.downloads||0).toLocaleString()} downloads</div>
          </div>
          <button onclick="this.closest('[style*=\"fixed\"]').remove()" style="margin-left:auto;background:none;border:none;color:var(--text-3);font-size:20px;cursor:pointer">✕</button>
        </div>
        <p style="color:var(--text-2);font-size:13px;line-height:1.6">${escHtml(d.description||'')}</p>
        <div style="margin-bottom:16px">
          <h4 style="font-size:12px;color:var(--text-3);text-transform:uppercase">Skills (${(d.skills||[]).length})</h4>
          ${skills||'<div style="color:var(--text-3);font-size:12px">No skills listed</div>'}
        </div>
        ${reviews?`<div><h4 style="font-size:12px;color:var(--text-3);text-transform:uppercase">Reviews (${(d.reviews||[]).length})</h4>${reviews}</div>`:''}
        <div style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn" onclick="mktInstallOrUninstall(${JSON.stringify(packId)},${JSON.stringify(d.name||packId)},${isInst});this.closest('[style*=\'fixed\']').remove()">
            ${isInst?'✓ Installed (Uninstall)':'Install'}
          </button>
          <button class="btn-sm" onclick="mktLeaveReview(${JSON.stringify(packId)})">⭐ Review</button>
          <button class="btn-sm" onclick="window.open('/api/marketplace/'+encodeURIComponent(${JSON.stringify(packId)})+'/download','_blank')">⬇ Download ZIP</button>
        </div>
      </div>`;
    overlay.onclick = e => { if(e.target===overlay) overlay.remove(); };
    document.body.appendChild(overlay);
  } catch(ex) {
    gmAlert('Failed to load pack details: '+ex?.message);
  }
}

async function mktLeaveReview(packId) {
  const ratingStr = await gmPrompt('Rating (1-5 stars):', '5');
  if (ratingStr === null) return;
  const rating = parseInt(ratingStr||'5');
  if (isNaN(rating)||rating<1||rating>5) { gmAlert('Rating must be between 1 and 5'); return; }
  const text = await gmPrompt('Review (optional):', '');
  if (text === null) return;
  try {
    const r = await fetch(`/api/marketplace/${encodeURIComponent(packId)}/review`,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({rating,review:text,reviewer:'You'})});
    if (!r.ok) { gmAlert('Review submit failed: '+r.status); return; }
    const d = await r.json();
    if (d.ok) {
      gmAlert(`✅ Review submitted! New average: ${d.new_avg}⭐`);
    } else {
      gmAlert('Review error: '+(d.error||'Unknown error'));
    }
  } catch(ex) {
    gmAlert('Review submission failed: '+ex?.message);
  }
}

async function mktCheckUpdates() {
  try {
    const resp = await fetch('/api/marketplace/installed/check-updates');
    if (!resp.ok) { gmAlert('Failed to check updates: '+resp.status); return; }
    const r = await resp.json();
    if (!r.updates?.length) { gmAlert('✅ All installed packs are up to date!'); return; }
    const names = r.updates.map((u) =>`${u.name||u.pack_id}: ${u.installed_ver} → ${u.latest_ver}`).join('\n');
    const ok = await gmConfirm(`${r.count} update${r.count>1?'s':''} available:\n\n${names}\n\nUpdate all now?`);
    if (ok) {
      const ur = await fetch('/api/marketplace/installed/update-all',{method:'POST'});
      if (!ur.ok) { gmAlert('Update failed: '+ur.status); return; }
      const ud = await ur.json();
      gmAlert(`✅ Updated ${ud.count} pack${ud.count!==1?'s':''}!`);
      renderMarketplace();
    }
  } catch(ex) {
    gmAlert('Update check failed: '+ex?.message);
  }
}

async function mktShowInstalled() {
  try {
    const resp = await fetch('/api/marketplace/installed/list');
    if (!resp.ok) { gmAlert('Failed to load installed list: '+resp.status); return; }
    const d = await resp.json();
    const items = (d.installed||[]).map((i) =>`
      <div style="display:flex;align-items:center;gap:8px;padding:8px 0;border-top:1px solid var(--border);font-size:12px">
        <span style="font-size:18px">${i.icon||'🔧'}</span>
        <div style="flex:1">
          <strong style="color:var(--text-0)">${escHtml(i.name||i.pack_id)}</strong>
          <div style="color:var(--text-3)">v${i.version}</div>
        </div>
        <button class="btn-sm" style="color:var(--danger);border-color:var(--danger)"
                onclick="mktInstallOrUninstall(${JSON.stringify(i.pack_id)},${JSON.stringify(i.name||i.pack_id)},true)">Uninstall</button>
      </div>
    `).join('');
    const overlay = document.createElement('div');
    overlay.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    overlay.innerHTML=`<div style="background:var(--bg-2);border:1px solid var(--border);border-radius:16px;max-width:460px;width:100%;max-height:70vh;overflow-y:auto;padding:24px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <h3 style="margin:0;color:var(--text-0)">📦 Installed Packs (${d.count||0})</h3>
        <button onclick="this.closest('[style*=\"fixed\"]').remove()" style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
      </div>
      ${items||'<div style="color:var(--text-3)">No packs installed</div>'}
    </div>`;
    overlay.onclick = e => { if(e.target===overlay) overlay.remove(); };
    document.body.appendChild(overlay);
  } catch(ex) {
    gmAlert('Failed to show installed packs: '+ex?.message);
  }
}

function mktUploadPack() {
  const input = document.createElement('input');
  input.type='file'; input.accept='.zip';
  input.onchange = async () => {
    const file = input.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file',file);
    try {
      const r = await fetch('/api/marketplace/upload',{method:'POST',body:fd});
      if (!r.ok) { gmAlert('Upload failed (HTTP '+r.status+')'); return; }
      const d = await r.json();
      if (d.ok) { gmAlert(`✅ Pack uploaded: ${d.pack_id} v${d.version}`); renderMarketplace(); }
      else gmAlert('Upload failed: '+(d.error||'Unknown error'));
    } catch(ex) {
      gmAlert('Upload error: '+ex?.message);
    }
  };
  input.click();
}

// Simple toast helper (may already exist)
function showToast(msg, dur=3000) {
  let t = document.getElementById('_toast');
  if (!t) {
    t = document.createElement('div');
    t.id='_toast';
    t.style.cssText='position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--bg-2);border:1px solid var(--border);color:var(--text-0);padding:10px 20px;border-radius:10px;font-size:13px;z-index:99999;box-shadow:0 4px 20px rgba(0,0,0,.4);transition:opacity .3s;pointer-events:none';
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.style.opacity='1';
  clearTimeout((t)._timer);
  (t)._timer = setTimeout(()=>{ t?.style.opacity='0'; }, dur);
}


// ══════════════════════════════════════════════════════════════════
//  PATCH MASTER NAV — Sprint 15 panes
// ══════════════════════════════════════════════════════════════════
(function patchNavSprint15() {
  const _base = window.nav || function(){};
  window.nav = function masterNav15(pane) {
    _base(pane);
    if (pane==='replay')      renderReplay?.();
    if (pane==='collabedit')  renderCollabEdit?.();
    if (pane==='marketplace') renderMarketplace?.();
  };
  console.log('%c✅ Sprint 15 loaded: Replay, Collab OT Editor, Marketplace', 'color:#f0c060;font-weight:bold');
})();

// ── Keyboard shortcuts Sprint 15 ──────────────────────────────────
document.addEventListener('keydown', (e) => {
  if (!e.metaKey && !e.ctrlKey) return;
  // ⌘⇧M → Marketplace
  if (e.shiftKey && e.key==='M') { e.preventDefault(); nav('marketplace'); }
  // ⌘⇧R → Replay
  if (e.shiftKey && e.key==='R' && !(e.target)?.closest?.('#pane-chat')) {
    e.preventDefault(); nav('replay');
  }
});

