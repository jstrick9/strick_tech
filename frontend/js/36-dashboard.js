// Agentic OS — Dashboard
// Extracted from 01-app-core.js for modularity
// ── Dashboard ─────────────────────────────────────────────────────
let dashData = null;
let _dashRefreshTimer = null;

async function renderDashboard() {
  const pane = document.getElementById('pane-dashboard');
  if (!pane) return;
  pane.innerHTML = `
    <div class="section-head">
      <div>
        <h2>📊 Dashboard</h2>
        <p>Real-time analytics — cost, tasks, memory, agents, swarm, E2E</p>
        <!-- BUG FIX: renderConnectionReadiness() has always written to both
             'chat-connection-status' and 'mission-connection-status', but the
             latter element existed nowhere in the app, so the Launchpad half of
             that call was a permanent no-op and users only saw AI-connection
             state from inside Chat. Rendered here so the dashboard surfaces it
             too. -->
        <button type="button" id="mission-connection-status" class="connection-status checking"
                data-act-click="nav('settings');switchSettingsTab('api')"
                title="Check or change your AI connection">Checking AI connection…</button>
      </div>
      <div style="display:flex;gap:6px;align-items:center">
        <select id="dash-days" data-act-change="renderDashboard()" style="background:var(--bg-3);border:1px solid var(--border);border-radius:6px;color:var(--text-1);font-size:12px;padding:4px 8px">
          <option value="7">7 days</option>
          <option value="30" selected>30 days</option>
          <option value="90">90 days</option>
        </select>
        <button data-act-click="exportDashboardCSV()" class="btn-sm" title="Export CSV">⬇ CSV</button>
        <button data-act-click="renderDashboard()" class="btn btn-ghost btn-sm">⟳ Refresh</button>
      </div>
    </div>
    <div id="dash-body" style="color:var(--text-2);font-size:13px">Loading…</div>`;

  const days = document.getElementById('dash-days')?.value || '30';
  try {
    const r = await fetch(`/api/analytics/dashboard?days=${days}`);
    if (!r.ok) {
      const el = document.getElementById('dash-body');
      if (el) el.innerHTML = `<div style="color:var(--danger)">Failed to load analytics (HTTP ${r.status})<br><button class="btn-sm" data-act-click="renderDashboard()" style="margin-top:6px">↻ Retry</button></div>`;
      return;
    }
    dashData = await r.json();
    renderDashBody(dashData);
  } catch(ex) {
    const el = document.getElementById('dash-body');
    if (el) el.innerHTML = `<div style="color:var(--danger)">Failed to load: ${escHtml(ex?.message||String(ex))}<br><button class="btn-sm" data-act-click="renderDashboard()" style="margin-top:6px">↻ Retry</button></div>`;
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
