// Agent Monitor — Extracted from 06-sprint-features.js
(function(S, nav, toast, escHtml, fetch, document) {
// ── State ─────────────────────────────────────────────────────────
// NOTE: this state/constants block was originally (incorrectly) left in the
// separate 52-a2a.js IIFE, which has its own private closure scope and
// cannot be seen from here. Moved here since it belongs to this module.
let _monitorPoll    = null;    // live poll timer
let _driftTab       = 'dashboard';  // dashboard | agents | alerts | history
let _driftSummary   = null;
let _driftSelected  = null;    // currently viewed agent_id
let _driftAlerts    = [];
let _driftHistory   = [];
let _driftLeaderboard = [];

// ── Constants ──────────────────────────────────────────────────────
const DRIFT_SEV_COLORS = {
  none:     { bg:'rgba(61,186,122,.12)',   border:'#3dba7a',  text:'#3dba7a',   label:'None'     },
  low:      { bg:'rgba(91,138,248,.12)',   border:'#5b8af8',  text:'#5b8af8',   label:'Low'      },
  medium:   { bg:'rgba(232,162,55,.12)',   border:'#e8a237',  text:'#e8a237',   label:'Medium'   },
  high:     { bg:'rgba(240,96,128,.15)',   border:'#f06080',  text:'#f06080',   label:'High'     },
  critical: { bg:'rgba(232,82,82,.15)',    border:'#e85252',  text:'#e85252',   label:'Critical' },
};
const DRIFT_TREND_ICONS = {
  stable:             '→',
  improving:          '↗',
  degrading:          '↘',
  volatile:           '↕',
  insufficient_data:  '?',
};
const DRIFT_TREND_COLORS = {
  stable:             'var(--text-3)',
  improving:          'var(--success)',
  degrading:          'var(--danger)',
  volatile:           'var(--warning)',
  insufficient_data:  'var(--text-3)',
};
const DRIFT_DIM_LABELS = {
  latency:    { label:'Latency',    icon:'⏱️', unit:'ms' },
  tokens:     { label:'Tokens',     icon:'🔤', unit:'/task' },
  cost:       { label:'Cost',       icon:'💰', unit:'/task' },
  error_rate: { label:'Error Rate', icon:'❌', unit:'%' },
  volume:     { label:'Volume',     icon:'📊', unit:'/hr' },
};
const DRIFT_ACTION_LABELS = {
  none:             { label:'No Action',         color:'var(--text-3)',  icon:'—' },
  alerted:          { label:'Alert Raised',      color:'var(--warning)', icon:'⚠️' },
  kill_recommended: { label:'Kill Recommended',  color:'var(--danger)',  icon:'🛑' },
};
const DRIFT_REC_LABELS = {
  monitor:       'Monitor',
  restart_agent: 'Restart Agent',
  kill_agent:    'Kill Agent',
  escalate:      'Escalate',
};

async function renderAgentMonitor() {
  const pane = document.getElementById('pane-agent-monitor');
  if (!pane) return;

  pane.innerHTML = `
  

  <div class="bdd-root">
    <!-- ── Sidebar ── -->
    <div class="bdd-sidebar">
      <div class="bdd-sidebar-title">Drift Detection</div>
      <div class="bdd-nav active" id="bdd-nav-dashboard" data-act-click="bddSetTab('dashboard')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
        <span class="bdd-nav-icon">📊</span> Dashboard
      </div>
      <div class="bdd-nav" id="bdd-nav-agents" data-act-click="bddSetTab('agents')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
        <span class="bdd-nav-icon">🤖</span> Agent Scores
      </div>
      <div class="bdd-nav" id="bdd-nav-alerts" data-act-click="bddSetTab('alerts')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
        <span class="bdd-nav-icon">⚠️</span> Alerts
        <span class="bdd-alert-badge" id="bdd-alert-count" style="display:none">0</span>
      </div>
      <div class="bdd-nav" id="bdd-nav-history" data-act-click="bddSetTab('history')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
        <span class="bdd-nav-icon">📈</span> History
      </div>
      <div class="bdd-sidebar-div"></div>
      <div class="bdd-nav" id="bdd-nav-monitor" data-act-click="bddSetTab('monitor')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
        <span class="bdd-nav-icon">📡</span> Live Monitor
      </div>
      <div class="bdd-sidebar-foot">
        <button class="bdd-detect-btn" data-act-click="bddDetectAll()">🔍 Run Detection</button>
      </div>
    </div>

    <!-- ── Main ── -->
    <div class="bdd-main">
      <div class="bdd-header">
        <span class="bdd-header-title" id="bdd-header-title">🧬 Behavior Drift Detection</span>
        <button class="bdd-header-btn" data-act-click="bddRefresh()">↺ Refresh</button>
        <button class="bdd-header-btn" data-act-click="bddBuildFingerprints()" title="Recompute baselines">🧬 Rebuild Baselines</button>
        <button class="bdd-header-btn" data-act-click="bddDetectAll()" style="background:var(--accent);border-color:var(--accent-text);color:var(--on-accent)">🔍 Detect All</button>
      </div>
      <div class="bdd-content" id="bdd-content">
        <div style="padding:40px;text-align:center;color:var(--text-3)">Loading…</div>
      </div>
    </div>
  </div>`;

  await bddRefresh();
  _startMonitorPoll();
}


// ── Data ────────────────────────────────────────────────────────────
async function bddRefresh() {
  const [sumR, alertsR, lbR] = await Promise.all([
    fetch('/api/drift/summary').then(r=>r.ok?r.json():{}).catch(()=>({})),
    fetch('/api/drift/alerts?limit=50').then(r=>r.ok?r.json():{alerts:[]}).catch(()=>({alerts:[]})),
    fetch('/api/drift/leaderboard').then(r=>r.ok?r.json():{leaderboard:[]}).catch(()=>({leaderboard:[]})),
  ]);
  _driftSummary     = sumR;
  _driftAlerts      = alertsR.alerts || [];
  _driftLeaderboard = lbR.leaderboard || [];

  // Update alert badge
  const unresolvedCount = _driftAlerts.filter(a=>!a.resolved).length;
  const badge = document.getElementById('bdd-alert-count');
  if (badge) {
    badge.textContent = unresolvedCount;
    badge.style.display = unresolvedCount > 0 ? 'inline-flex' : 'none';
  }

  bddRenderTab();
}


// ── Tab system ──────────────────────────────────────────────────────
function bddSetTab(tab) {
  _driftTab = tab;
  document.querySelectorAll('.bdd-nav').forEach(el => {
    el.classList.toggle('active', el.id === 'bdd-nav-' + tab);
  });
  const titles = {
    dashboard: '📊 Drift Detection Dashboard',
    agents:    '🤖 Agent Drift Scores',
    alerts:    '⚠️ Drift Alerts',
    history:   '📈 Drift History',
    monitor:   '📡 Live Agent Monitor',
  };
  const h = document.getElementById('bdd-header-title');
  if (h) h.textContent = titles[tab] || 'Behavior Drift Detection';
  bddRenderTab();
}

function bddRenderTab() {
  const c = document.getElementById('bdd-content');
  if (!c) return;
  if (_driftTab === 'dashboard') bddRenderDashboard(c);
  if (_driftTab === 'agents')    bddRenderAgents(c);
  if (_driftTab === 'alerts')    bddRenderAlerts(c);
  if (_driftTab === 'history')   bddRenderHistory(c);
  if (_driftTab === 'monitor')   bddRenderLiveMonitor(c);
}


// ── Dashboard ───────────────────────────────────────────────────────
function bddRenderDashboard(container) {
  const s   = _driftSummary || {};
  const lb  = _driftLeaderboard;
  const bySev = s.agents_by_severity || {};

  const critAgents  = lb.filter(a=>a.severity==='critical');
  const highAgents  = lb.filter(a=>a.severity==='high');
  const stableAgents= lb.filter(a=>['none','low'].includes(a.severity));
  const avgScore    = lb.length ? lb.reduce((s,a)=>s+a.drift_score,0)/lb.length : 0;

  const stats = [
    { val: lb.length,                              lbl:'Agents Tracked', col:'var(--accent)' },
    { val: (bySev.critical||0),                   lbl:'Critical',       col: bySev.critical>0?'var(--danger)':'var(--text-3)' },
    { val: (bySev.high||0),                       lbl:'High Drift',     col: bySev.high>0?'#f06080':'var(--text-3)' },
    { val: (bySev.medium||0),                     lbl:'Medium Drift',   col: bySev.medium>0?'var(--warning)':'var(--text-3)' },
    { val: s.alerts_unresolved||0,                 lbl:'Active Alerts',  col: s.alerts_unresolved>0?'var(--danger)':'var(--text-3)' },
    { val: avgScore.toFixed(1),                   lbl:'Avg Score',      col:'#9d74f5' },
  ];

  container.innerHTML = `
    <!-- Severity severity bar -->
    <div class="bdd-sev-bar" title="Distribution of agent drift severity">
      ${['critical','high','medium','low','none'].map(sev => {
        const cnt = bySev[sev]||0;
        const col = DRIFT_SEV_COLORS[sev]?.border||'var(--border)';
        return `<div class="bdd-sev-seg" style="background:${col};flex:${Math.max(cnt,0.5)}" title="${sev}: ${cnt}"></div>`;
      }).join('')}
    </div>

    <!-- Stats grid -->
    <div class="bdd-summary-grid">
      ${stats.map(s => `
        <div class="bdd-stat-card">
          <div class="bdd-stat-val" style="color:${s.col}">${s.val}</div>
          <div class="bdd-stat-lbl">${s.lbl}</div>
        </div>`).join('')}
    </div>

    <!-- Critical agents banner -->
    ${critAgents.length ? `
    <div style="background:rgba(232,82,82,.08);border:1px solid #e85252;border-radius:10px;padding:12px 14px;margin-bottom:14px">
      <div style="font-size:12px;font-weight:700;color:#e85252;margin-bottom:8px">🔴 Critical Drift — Immediate Action Required</div>
      ${critAgents.map(a => `
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;font-size:11px">
          <span style="font-weight:700;color:var(--text-0);min-width:90px">${escHtml(a.agent_id)}</span>
          <span style="color:#e85252;font-weight:800">${a.drift_score.toFixed(1)}/100</span>
          <span style="color:var(--text-3)">${escHtml((a.flags||[]).slice(0,3).join(', '))}</span>
          <div style="margin-left:auto;display:flex;gap:5px">
            <button class="bdd-alert-btn danger" data-act-click="bddKillAgent(${JSON.stringify(a.agent_id)})">🛑 Kill</button>
            <button class="bdd-alert-btn" data-act-click="bddViewAgent(${JSON.stringify(a.agent_id)})">🔍 Details</button>
          </div>
        </div>`).join('')}
    </div>` : ''}

    <!-- Leaderboard -->
    <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px">
      Drift Leaderboard — All Agents
    </div>
    <div class="bdd-leaderboard">
      ${lb.map(a => {
        const sc = DRIFT_SEV_COLORS[a.severity] || DRIFT_SEV_COLORS.none;
        const trendC = DRIFT_TREND_COLORS[a.trend] || 'var(--text-3)';
        const trendI = DRIFT_TREND_ICONS[a.trend]  || '?';
        const pct    = Math.min(a.drift_score, 100);
        const isSelected = _driftSelected === a.agent_id;
        return `<div class="bdd-lb-row ${isSelected?'selected':''}" data-act-click="bddViewAgent(${JSON.stringify(a.agent_id)})" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
          <span class="bdd-lb-agent">${escHtml(a.agent_id)}</span>
          <div class="bdd-lb-score-bar">
            <div class="bdd-lb-score-fill" style="width:${pct}%;background:${sc.border}"></div>
          </div>
          <span class="bdd-lb-score-num" style="color:${sc.border}">${a.drift_score.toFixed(1)}</span>
          <span class="bdd-lb-sev" style="background:${sc.bg};color:${sc.text}">${sc.label}</span>
          <span class="bdd-lb-trend" style="color:${trendC}" title="${a.trend}">${trendI}</span>
          <span class="bdd-lb-flags">${escHtml((a.flags||[]).join(', '))}</span>
          <div class="bdd-lb-action">
            ${a.action==='kill_recommended' ? `<span style="font-size:9px;font-weight:700;color:var(--danger)">KILL</span>` :
              a.action==='alerted'          ? `<span style="font-size:9px;font-weight:700;color:var(--warning)">ALERT</span>` : ''}
          </div>
        </div>`;
      }).join('')}
    </div>
  `;
}


// ── Agents tab ──────────────────────────────────────────────────────
function bddRenderAgents(container) {
  if (!_driftSelected) {
    // Show leaderboard, click to select agent for detail
    container.innerHTML = `
      <div style="font-size:12px;color:var(--text-3);margin-bottom:12px">
        Click an agent to see its full drift profile, dimension breakdown, and sparkline chart.
      </div>
      <div class="bdd-leaderboard">
        ${_driftLeaderboard.map(a => {
          const sc = DRIFT_SEV_COLORS[a.severity] || DRIFT_SEV_COLORS.none;
          const pct = Math.min(a.drift_score, 100);
          return `<div class="bdd-lb-row" data-act-click="bddViewAgent(${JSON.stringify(a.agent_id)})" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
            <div class="bdd-gauge" style="border-color:${sc.border};width:48px;height:48px">
              <span class="bdd-gauge-val" style="color:${sc.border};font-size:13px">${a.drift_score.toFixed(0)}</span>
              <span class="bdd-gauge-lbl" style="color:${sc.border};font-size:7px">${sc.label}</span>
            </div>
            <div style="flex:1;min-width:0">
              <div style="font-weight:700;font-size:13px;color:var(--text-0)">${escHtml(a.agent_id)}</div>
              <div style="font-size:10px;color:${DRIFT_TREND_COLORS[a.trend]||'var(--text-3)'}">
                ${DRIFT_TREND_ICONS[a.trend]||'?'} ${a.trend}
                ${a.flags?.length ? '· ' + escHtml(a.flags.slice(0,2).join(', ')) : ''}
              </div>
              <div class="bdd-lb-score-bar" style="margin-top:5px">
                <div class="bdd-lb-score-fill" style="width:${pct}%;background:${sc.border}"></div>
              </div>
            </div>
            <div style="display:flex;gap:5px">
              <button class="bdd-header-btn" data-act-click="bddDetectAgent(${JSON.stringify(a.agent_id)})" data-stop="1">🔍 Run</button>
            </div>
          </div>`;
        }).join('')}
      </div>`;
  } else {
    bddRenderAgentDetail(container, _driftSelected);
  }
}

async function bddRenderAgentDetail(container, agentId) {
  container.innerHTML = `<div style="color:var(--text-3);padding:20px">Loading ${escHtml(agentId)}…</div>`;

  const d = await fetch(`/api/drift/agent/${encodeURIComponent(agentId)}`)
    .then(r=>r.ok?r.json():null).catch(()=>null);
  if (!d || !d.ok) {
    container.innerHTML = `<div style="color:var(--danger);padding:20px">Failed to load agent: ${escHtml(agentId)}</div>`;
    return;
  }

  const ls   = d.latest_score || {};
  const fp   = d.fingerprint  || {};
  const hist = d.scores_24h   || [];
  const alts = d.active_alerts|| [];
  const sc   = DRIFT_SEV_COLORS[ls.severity||'none'];
  const dims = ls.dimensions   || {};

  // Build sparkline
  const sparklineHTML = bddBuildSparkline(hist);

  const dimRows = Object.entries(DRIFT_DIM_LABELS).map(([key, meta]) => {
    const dim = dims[key] || {};
    const z   = dim.zscore || 0;
    const barPct = Math.min(z * 20, 100);
    const barCol = z > 3 ? '#e85252' : z > 2 ? '#f06080' : z > 1 ? '#e8a237' : '#3dba7a';
    const curVal = key==='error_rate'
      ? `${((dim.current||0)*100).toFixed(1)}%`
      : key==='cost'
        ? `$${(dim.current||0).toFixed(5)}`
        : `${(dim.current||0).toFixed(0)}${meta.unit}`;
    const baseVal = key==='error_rate'
      ? `${((dim.baseline||0)*100).toFixed(1)}%`
      : key==='cost'
        ? `$${(dim.baseline||0).toFixed(5)}`
        : `${(dim.baseline||0).toFixed(0)}${meta.unit}`;
    return `<div class="bdd-dim-row">
      <span class="bdd-dim-icon">${meta.icon}</span>
      <span class="bdd-dim-label">${meta.label}</span>
      <div class="bdd-dim-bar-wrap">
        <div class="bdd-dim-bar-fill" style="width:${barPct}%;background:${barCol}"></div>
      </div>
      <span class="bdd-dim-zscore" style="color:${barCol}">${z.toFixed(1)}σ</span>
      <span class="bdd-dim-vals">${curVal} / ${baseVal}</span>
    </div>`;
  }).join('');

  container.innerHTML = `
    <!-- Back button -->
    <div style="margin-bottom:12px">
      <button class="bdd-header-btn" data-act-click="hResetDriftSelection()">← Back to All Agents</button>
    </div>

    <!-- Agent header -->
    <div style="display:flex;align-items:center;gap:14px;margin-bottom:16px;flex-wrap:wrap">
      <div class="bdd-gauge" style="border-color:${sc.border}">
        <span class="bdd-gauge-val" style="color:${sc.border}">${(ls.drift_score||0).toFixed(1)}</span>
        <span class="bdd-gauge-lbl" style="color:${sc.border}">${sc.label}</span>
      </div>
      <div style="flex:1">
        <div style="font-size:18px;font-weight:800;color:var(--text-0)">${escHtml(agentId)}</div>
        <div style="font-size:12px;color:${DRIFT_TREND_COLORS[ls.trend]||'var(--text-3)'}">
          ${DRIFT_TREND_ICONS[ls.trend]||''} ${ls.trend||'—'} &nbsp;
          <span style="color:var(--text-3)">${ls.computed_at ? 'Computed ' + new Date(ls.computed_at).toLocaleTimeString() : ''}</span>
        </div>
        <div style="font-size:11px;color:var(--text-2);margin-top:3px">${escHtml(ls.detail||'')}</div>
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        <button class="bdd-header-btn" data-act-click="bddDetectAgent(${JSON.stringify(agentId)})">🔍 Re-run Detection</button>
        <button class="bdd-header-btn" data-act-click="bddBuildFingerprint(${JSON.stringify(agentId)})">🧬 Rebuild Baseline</button>
        ${ls.severity==='critical' ? `<button class="bdd-header-btn" style="color:var(--danger);border-color:var(--danger)" data-act-click="bddKillAgent(${JSON.stringify(agentId)})">🛑 Kill Agent</button>` : ''}
      </div>
    </div>

    <!-- Active alerts for this agent -->
    ${alts.length ? `
    <div style="margin-bottom:14px">
      ${alts.map(a => `
        <div class="bdd-alert-card" style="border-color:${DRIFT_SEV_COLORS[a.severity]?.border||'var(--border)'}">
          <span class="bdd-alert-icon">${a.severity==='critical'?'🔴':'🟡'}</span>
          <div class="bdd-alert-body">
            <div class="bdd-alert-title">${escHtml(a.title)}</div>
            <div class="bdd-alert-desc">${escHtml(a.description)}</div>
          </div>
          <div class="bdd-alert-actions">
            <button class="bdd-alert-btn" data-act-click="bddResolveAlert(${JSON.stringify(a.alert_id)})">✓ Resolve</button>
          </div>
        </div>`).join('')}
    </div>` : ''}

    <div class="bdd-detail-layout">
      <!-- Dimensions -->
      <div class="bdd-detail-panel">
        <div class="bdd-panel-title">📊 Dimension Z-Scores &nbsp;<span style="font-weight:400;color:var(--text-3)">(current vs baseline)</span></div>
        ${dimRows}
        <div style="font-size:10px;color:var(--text-3);margin-top:8px">Z-score = standard deviations from baseline mean. >2σ = warning, >3σ = critical.</div>
      </div>

      <!-- Baseline fingerprint -->
      <div class="bdd-detail-panel">
        <div class="bdd-panel-title">🧬 Baseline Fingerprint <span style="font-weight:400;color:var(--text-3)">(7-day rolling)</span></div>
        ${fp ? `
        <div class="bdd-fp-grid">
          <div class="bdd-fp-item">
            <div class="bdd-fp-label">Latency Mean</div>
            <div class="bdd-fp-val">${fp.lat_mean?.toFixed(0)||'—'}ms</div>
            <div class="bdd-fp-sub">±${fp.lat_stddev?.toFixed(0)||'—'}ms std</div>
          </div>
          <div class="bdd-fp-item">
            <div class="bdd-fp-label">Latency P90</div>
            <div class="bdd-fp-val">${fp.lat_p90?.toFixed(0)||'—'}ms</div>
            <div class="bdd-fp-sub">P99: ${fp.lat_p99?.toFixed(0)||'—'}ms</div>
          </div>
          <div class="bdd-fp-item">
            <div class="bdd-fp-label">Tokens/task</div>
            <div class="bdd-fp-val">${fp.tok_mean?.toFixed(0)||'—'}</div>
            <div class="bdd-fp-sub">±${fp.tok_stddev?.toFixed(0)||'—'} std</div>
          </div>
          <div class="bdd-fp-item">
            <div class="bdd-fp-label">Cost/task</div>
            <div class="bdd-fp-val">$${fp.cost_mean?.toFixed(5)||'—'}</div>
            <div class="bdd-fp-sub">P90: $${fp.cost_p90?.toFixed(5)||'—'}</div>
          </div>
          <div class="bdd-fp-item">
            <div class="bdd-fp-label">Error Rate</div>
            <div class="bdd-fp-val">${((fp.error_rate_mean||0)*100).toFixed(1)}%</div>
            <div class="bdd-fp-sub">Baseline</div>
          </div>
          <div class="bdd-fp-item">
            <div class="bdd-fp-label">Tasks/hour</div>
            <div class="bdd-fp-val">${fp.tasks_per_hour?.toFixed(1)||'—'}</div>
            <div class="bdd-fp-sub">${fp.total_samples||0} samples</div>
          </div>
        </div>
        <div style="font-size:10px;color:var(--text-3);margin-top:8px">
          Computed ${fp.computed_at ? new Date(fp.computed_at).toLocaleString() : '—'}
        </div>` : '<div style="color:var(--text-3);font-size:12px">No fingerprint computed. Click "Rebuild Baseline".</div>'}
      </div>
    </div>

    <!-- Sparkline chart -->
    <div class="bdd-detail-panel" style="margin-top:14px">
      <div class="bdd-panel-title">📈 Drift Score — Last 24h</div>
      ${hist.length >= 2 ? `
        <div class="bdd-sparkline-wrap">
          <span class="bdd-sparkline-label">${hist.length} measurements</span>
          ${sparklineHTML}
        </div>` : `<div style="color:var(--text-3);font-size:12px">Insufficient history (${hist.length} measurements). Run detection over time to build the chart.</div>`}
    </div>
  `;
}

function bddBuildSparkline(hist) {
  if (hist.length < 2) return '';
  const W=560, H=60, padX=10, padY=8;
  const scores = hist.map(h=>h.drift_score);
  const minS   = Math.min(...scores, 0);
  const maxS   = Math.max(...scores, 10);
  const range  = maxS - minS || 1;

  const toX = (i) => padX + (i / (hist.length - 1)) * (W - padX*2);
  const toY = (s) => padY + (1 - (s - minS) / range) * (H - padY*2);

  const points = hist.map((h,i) => `${toX(i)},${toY(h.drift_score)}`).join(' ');
  const dots   = hist.map((h,i) => {
    const col = DRIFT_SEV_COLORS[h.severity||'none']?.border || '#3dba7a';
    const x = toX(i), y = toY(h.drift_score);
    const ts = new Date(h.computed_at).toLocaleTimeString();
    return `<circle cx="${x}" cy="${y}" r="3" fill="${col}" title="${h.drift_score.toFixed(1)} — ${h.severity} (${ts})"/>`;
  }).join('');

  // Reference lines at 25 (low), 45 (medium), 70 (high)
  const refLines = [
    { s:25, col:'#5b8af8', lbl:'Low'    },
    { s:45, col:'#e8a237', lbl:'Medium' },
    { s:70, col:'#f06080', lbl:'High'   },
  ].filter(r => r.s >= minS && r.s <= maxS).map(r => {
    const y = toY(r.s);
    return `<line x1="${padX}" y1="${y}" x2="${W-padX}" y2="${y}" stroke="${r.col}" stroke-width="0.5" stroke-dasharray="4,3" opacity="0.6"/>
      <text x="${W-padX+2}" y="${y+3}" font-size="8" fill="${r.col}">${r.lbl}</text>`;
  }).join('');

  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:${H}px">
    ${refLines}
    <polyline points="${points}" fill="none" stroke="#9d74f5" stroke-width="2"/>
    ${dots}
  </svg>`;
}


// ── Alerts tab ──────────────────────────────────────────────────────
function bddRenderAlerts(container) {
  const unresolved = _driftAlerts.filter(a => !a.resolved);
  const resolved   = _driftAlerts.filter(a =>  a.resolved);

  if (!unresolved.length && !resolved.length) {
    container.innerHTML = `<div class="bdd-empty">
      <div class="bdd-empty-icon">✅</div>
      <div class="bdd-empty-title">No Drift Alerts</div>
      <div class="bdd-empty-sub">All agents are within normal behavioral parameters. Run detection to check for new issues.</div>
    </div>`;
    return;
  }

  const renderCard = (a) => {
    const sc  = DRIFT_SEV_COLORS[a.severity] || DRIFT_SEV_COLORS.none;
    const rec = DRIFT_REC_LABELS[a.recommended_action] || a.recommended_action;
    const ackEl = a.acknowledged ? '<span style="font-size:10px;color:var(--success)">✓ Acknowledged</span>' : '';
    return `<div class="bdd-alert-card" style="border-color:${sc.border};${a.resolved?'opacity:.5':''}">
      <span class="bdd-alert-icon">${a.severity==='critical'?'🔴':a.severity==='high'?'🟠':a.severity==='medium'?'🟡':'🔵'}</span>
      <div class="bdd-alert-body">
        <div class="bdd-alert-title">${escHtml(a.title)}</div>
        <div class="bdd-alert-desc">${escHtml(a.description)}</div>
        <div class="bdd-alert-meta">
          <span class="bdd-lb-sev" style="background:${sc.bg};color:${sc.text}">${sc.label}</span>
          <span>Score: <strong>${a.drift_score?.toFixed(1)||'?'}</strong></span>
          <span>Action: <strong style="color:${a.recommended_action==='kill_agent'?'var(--danger)':a.recommended_action==='restart_agent'?'var(--warning)':'var(--text-1)'}">${rec}</strong></span>
          <span>${new Date(a.created_at).toLocaleString()}</span>
          ${ackEl}
        </div>
      </div>
      <div class="bdd-alert-actions">
        ${!a.resolved ? `
          ${!a.acknowledged ? `<button class="bdd-alert-btn" data-act-click="bddAckAlert(${JSON.stringify(a.alert_id)})">👁 Ack</button>` : ''}
          ${a.recommended_action==='kill_agent' ? `<button class="bdd-alert-btn danger" data-act-click="bddKillAgent(${JSON.stringify(a.agent_id)})">🛑 Kill</button>` : ''}
          <button class="bdd-alert-btn" data-act-click="bddViewAgent(${JSON.stringify(a.agent_id)})">🔍 Inspect</button>
          <button class="bdd-alert-btn" data-act-click="bddResolveAlert(${JSON.stringify(a.alert_id)})">✓ Resolve</button>
        ` : '<span style="font-size:10px;color:var(--success)">Resolved</span>'}
      </div>
    </div>`;
  };

  container.innerHTML = `
    ${unresolved.length ? `
    <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;margin-bottom:10px">
      Active Alerts (${unresolved.length})
    </div>
    ${unresolved.map(renderCard).join('')}` : ''}
    ${resolved.length ? `
    <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;margin:14px 0 10px">
      Resolved (${resolved.length})
    </div>
    ${resolved.slice(0,5).map(renderCard).join('')}` : ''}
  `;
}


// ── History tab ─────────────────────────────────────────────────────
async function bddRenderHistory(container) {
  container.innerHTML = `<div style="color:var(--text-3);padding:20px">Loading history…</div>`;
  const d = await fetch('/api/drift/history?hours=24&limit=200').then(r=>r.ok?r.json():{history:[]}).catch(()=>({history:[]}));
  const hist = d.history || [];

  if (!hist.length) {
    container.innerHTML = `<div class="bdd-empty">
      <div class="bdd-empty-icon">📈</div>
      <div class="bdd-empty-title">No History Yet</div>
      <div class="bdd-empty-sub">Run drift detection to populate the history timeline.</div>
    </div>`;
    return;
  }

  container.innerHTML = `
    <div style="font-size:11px;color:var(--text-3);margin-bottom:12px">Last 24 hours · ${hist.length} measurements across ${new Set(hist.map(h=>h.agent_id)).size} agents</div>
    <table class="bdd-hist-table">
      <thead><tr>
        <th>Time</th><th>Agent</th><th>Window</th><th>Score</th><th>Severity</th><th>Trend</th><th>Flags</th><th>Action</th>
      </tr></thead>
      <tbody>
        ${hist.map(h => {
          const sc = DRIFT_SEV_COLORS[h.severity||'none'];
          const tc = DRIFT_TREND_COLORS[h.trend||'stable'];
          return `<tr data-act-click="bddViewAgent(${JSON.stringify(h.agent_id)})" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
            <td style="color:var(--text-3);white-space:nowrap">${new Date(h.computed_at).toLocaleTimeString()}</td>
            <td style="font-weight:600;color:var(--accent-text)">${escHtml(h.agent_id)}</td>
            <td style="font-size:10px;color:var(--text-3)">${h.window_label||'1h'}</td>
            <td style="font-weight:800;color:${sc.border}">${(h.drift_score||0).toFixed(1)}</td>
            <td><span class="bdd-lb-sev" style="background:${sc.bg};color:${sc.text}">${sc.label}</span></td>
            <td style="color:${tc}">${DRIFT_TREND_ICONS[h.trend||'stable']||''} ${h.trend||''}</td>
            <td style="font-size:10px;color:var(--text-3)">${escHtml((h.flags||[]).join(', ').slice(0,40))}</td>
            <td style="font-size:10px">${h.action && h.action!=='none' ? `<span style="color:var(--warning)">${h.action}</span>` : '—'}</td>
          </tr>`;
        }).join('')}
      </tbody>
    </table>
  `;
}


// ── Live Monitor tab (old content, preserved) ────────────────────────
async function bddRenderLiveMonitor(container) {
  const [live, anomalies, summary] = await Promise.all([
    fetch('/api/agent-monitor/live').then(r=>r.ok?r.json():{agents:[],summary:{}}).catch(()=>({agents:[],summary:{}})),
    fetch('/api/agent-monitor/anomalies?limit=10').then(r=>r.ok?r.json():{anomalies:[]}).catch(()=>({anomalies:[]})),
    fetch('/api/agent-monitor/summary').then(r=>r.ok?r.json():{}).catch(()=>({})),
  ]);
  const statusColor={idle:'var(--text-3)',working:'var(--warning)',killed:'var(--danger)',paused:'var(--accent)'};
  const statusIcon ={idle:'💤',working:'⚡',killed:'💀',paused:'⏸️'};

  container.innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-bottom:16px">
      ${[['🤖','Total',summary.total_agents||0,'var(--text-2)'],['⚡','Active',summary.active_agents||0,'var(--warning)'],
         ['💤','Idle',(summary.total_agents||0)-(summary.active_agents||0)-(summary.killed_agents||0),'var(--text-3)'],
         ['💀','Killed',summary.killed_agents||0,'var(--danger)'],
         ['⚠️','Anomalies',summary.unresolved_anomalies||0,'var(--warning)'],
         ['💰','Cost',`$${((summary.session_summary||{}).session_cost||0).toFixed(4)}`,'#9ece6a']
        ].map(([i,l,v,c])=>`<div class="bdd-stat-card"><div class="bdd-stat-val" style="color:${c}">${i} ${v}</div><div class="bdd-stat-lbl">${l}</div></div>`).join('')}
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px">
      ${(live.agents||[]).map(a => renderAgentMonitorCard(a, statusColor, statusIcon)).join('')}
    </div>
  `;
}


// ── Actions ──────────────────────────────────────────────────────────
async function bddDetectAll() {
  showToast('🔍 Running drift detection for all agents…');
  try {
    const r = await fetch('/api/drift/detect', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    const d = await r.json();
    showToast(`✅ Detection complete: ${d.agents_flagged} flagged / ${d.agents_checked} checked`);
    await bddRefresh();
  } catch(e) { showToast('⚠️ Detection failed: '+e.message); }
}

async function bddDetectAgent(agentId) {
  showToast(`🔍 Running detection for ${agentId}…`);
  try {
    const r = await fetch(`/api/drift/detect/${encodeURIComponent(agentId)}`,
      {method:'POST',headers:{'Content-Type':'application/json'},body:'{"window":"1h"}'});
    const d = await r.json();
    if (d.ok) {
      showToast(`✅ ${agentId}: score=${d.drift_score?.toFixed(1)} (${d.severity})`);
      await bddRefresh();
      if (_driftSelected === agentId) bddRenderAgentDetail(document.getElementById('bdd-content'), agentId);
    } else { showToast('⚠️ '+d.error); }
  } catch(e) { showToast('⚠️ '+e.message); }
}

async function bddBuildFingerprints() {
  showToast('🧬 Rebuilding behavioral baselines for all agents…');
  try {
    const r = await fetch('/api/drift/fingerprint',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const d = await r.json();
    showToast(`✅ Baselines rebuilt: ${d.computed} agents`);
    await bddRefresh();
  } catch(e) { showToast('⚠️ '+e.message); }
}

async function bddBuildFingerprint(agentId) {
  showToast(`🧬 Rebuilding baseline for ${agentId}…`);
  try {
    const r = await fetch(`/api/drift/fingerprint/${encodeURIComponent(agentId)}`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const d = await r.json();
    if (d.ok) {
      showToast(`✅ Baseline rebuilt: ${d.total_samples} samples`);
      bddRenderAgentDetail(document.getElementById('bdd-content'), agentId);
    } else { showToast('⚠️ '+d.error); }
  } catch(e) { showToast('⚠️ '+e.message); }
}

async function bddViewAgent(agentId) {
  _driftSelected = agentId;
  bddSetTab('agents');
  bddRenderAgentDetail(document.getElementById('bdd-content'), agentId);
}

async function bddAckAlert(alertId) {
  await fetch(`/api/drift/alerts/${encodeURIComponent(alertId)}/acknowledge`,{method:'POST'});
  showToast('👁 Alert acknowledged');
  const hr = await fetch('/api/drift/alerts?limit=50').then(r=>r.ok?r.json():{alerts:[]});
  _driftAlerts = hr.alerts || [];
  bddRenderAlerts(document.getElementById('bdd-content'));
}

async function bddResolveAlert(alertId) {
  await fetch(`/api/drift/alerts/${encodeURIComponent(alertId)}/resolve`,{method:'POST'});
  showToast('✅ Alert resolved');
  const hr = await fetch('/api/drift/alerts?limit=50').then(r=>r.ok?r.json():{alerts:[]});
  _driftAlerts = hr.alerts || [];
  const cnt = document.getElementById('bdd-alert-count');
  const unres = _driftAlerts.filter(a=>!a.resolved).length;
  if (cnt) { cnt.textContent=unres; cnt.style.display=unres>0?'inline-flex':'none'; }
  bddRenderAlerts(document.getElementById('bdd-content'));
}

async function bddKillAgent(agentId) {
  const ok = await gmDanger('Kill Agent', `Immediately stop all tasks for agent "${agentId}"?\n\nThis is the recommended action for critical behavior drift.`);
  if (!ok) return;
  try {
    const r = await fetch(`/api/agent-monitor/kill/${encodeURIComponent(agentId)}`,
      {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason:'Critical behavior drift — auto-kill recommended'})});
    const d = await r.json();
    showToast(d.ok ? `🛑 Agent ${agentId} killed` : '⚠️ Kill failed');
    await bddRefresh();
  } catch(e) { showToast('⚠️ '+e.message); }
}


// ── Live poll ────────────────────────────────────────────────────────
function _startMonitorPoll() {
  if (_monitorPoll) clearInterval(_monitorPoll);
  _monitorPoll = setInterval(async() => {
    if (!document.getElementById('pane-agent-monitor')?.classList.contains('active')) {
      clearInterval(_monitorPoll); _monitorPoll = null; return;
    }
    // Only auto-refresh summary numbers, not full re-render
    const sr = await fetch('/api/drift/summary').then(r=>r.ok?r.json():{}).catch(()=>({}));
    _driftSummary = sr;
    const unres = sr.alerts_critical||0 + sr.alerts_high||0;
    const badge = document.getElementById('bdd-alert-count');
    if (badge && (sr.alerts_unresolved||0) > 0) {
      badge.textContent = sr.alerts_unresolved;
      badge.style.display = 'inline-flex';
    }
  }, 15000);  // every 15s — gentle, not aggressive
}


// ── Old compat aliases (referenced by nav patches) ───────────────────
function renderAgentMonitorCard(a, statusColor, statusIcon) {
  const sCol = (statusColor||{})[a.status]||'var(--text-3)';
  const hasAnomaly = a.anomaly_score > 0;
  return `<div style="background:var(--bg-2);border:1px solid ${hasAnomaly?'var(--danger)':a.status==='working'?'var(--warning)':'var(--border)'};border-radius:12px;padding:14px">
    ${hasAnomaly?'<div style="float:right">⚠️</div>':''}
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
      <div style="width:28px;height:28px;border-radius:50%;background:${a.color||'#7aa2f7'}33;display:flex;align-items:center;justify-content:center">${a.avatar||'🤖'}</div>
      <div><div style="font-weight:700;font-size:12px">${escHtml(a.name||a.agent_id)}</div>
        <div style="font-size:10px;color:${sCol}">${(statusIcon||{})[a.status]||''} ${a.status}</div></div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:10px;margin-bottom:8px">
      <div style="background:var(--bg-3);border-radius:5px;padding:4px 7px"><div style="color:var(--text-3)">Cost</div><div>$${(a.cost_session||0).toFixed(4)}</div></div>
      <div style="background:var(--bg-3);border-radius:5px;padding:4px 7px"><div style="color:var(--text-3)">Errors</div><div style="color:${a.errors_session>0?'var(--danger)':'var(--text-0)'}">${a.errors_session||0}</div></div>
    </div>
    <div style="display:flex;gap:5px">
      <button class="btn-sm" data-act-click="bddViewAgent(${JSON.stringify(a.agent_id||a.id)})" style="font-size:10px">📊 Drift</button>
      ${!a.is_killed ?
        `<button class="btn-sm" data-act-click="bddKillAgent(${JSON.stringify(a.agent_id||a.id)})" style="color:var(--danger);border-color:var(--danger);font-size:10px">🛑</button>` :
        `<button class="btn-sm" data-act-click="monitorReviveAgent(${JSON.stringify(a.agent_id||a.id)})" style="color:var(--success);font-size:10px">♻️</button>`}
    </div>
  </div>`;
}
async function monitorDetectAnomalies() { await bddDetectAll(); }
async function monitorSnapshotKPIs() {
  const r = await fetch('/api/agent-monitor/kpis/snapshot',{method:'POST'}).catch(()=>null);
  const d = r ? await r.json() : {};
  showToast(`📸 KPI snapshot: ${d.snapshotted||0} agents`);
}
async function monitorViewKPIs(id) { await bddViewAgent(id); }
async function monitorKillAgent(id) { await bddKillAgent(id); }
async function monitorReviveAgent(id) {
  const r = await fetch(`/api/agent-monitor/revive/${encodeURIComponent(id)}`,{method:'POST'}).catch(()=>null);
  const d = r ? await r.json() : {};
  showToast(d.ok ? `♻️ ${id} revived` : '⚠️ Revive failed');
  await bddRefresh();
}
async function monitorShadowTest(id) {
  const r = await fetch('/api/agent-monitor/shadow',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent_id:id,shadow_config:{}})}).catch(()=>null);
  const d = r ? await r.json() : {};
  showToast(d.ok ? `🔬 Shadow: ${d.test_id}` : '⚠️ Failed');
}
async function monitorResolveAnomaly(id) {
  await fetch(`/api/agent-monitor/anomalies/${encodeURIComponent(id)}/resolve`,{method:'POST'});
  showToast('✅ Resolved');
  await bddRefresh();
}



window.renderAgentMonitor = renderAgentMonitor;
})(S, nav, toast, escHtml, fetch, document);
