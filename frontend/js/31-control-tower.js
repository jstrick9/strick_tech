// Agentic OS — Control Tower
// Extracted from 01-app-core.js for modularity
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
        <button data-act-click="killAllRuns()" class="btn btn-danger btn-sm">🛑 Kill All</button>
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
              return `<div class="card card-interactive" data-act-click="showRunTrace(${jsArg(r.run_id)})" style="padding:9px 12px" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
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
                  ${r.status==='running'?`<button data-act-click="killRun(${jsArg(r.run_id)})" data-stop="1" class="btn btn-danger btn-sm">🛑</button>`:''}
                </div>
              </div>`;}).join('')}
          </div>
        </div>
        <div>
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
            <div style="font-weight:700">💰 Budget Guardrails</div>
            <button data-act-click="addBudgetRule()" class="btn btn-primary btn-sm">＋ Rule</button>
          </div>
          ${helpPanel({title:'Stop agents before costs run away',body:'Set limits per agent or globally. Warn or auto-stop when limit is hit.'})}
          <div style="display:flex;flex-direction:column;gap:5px">
            ${rules.length === 0 ? `<div style="color:var(--text-3);font-size:12px;text-align:center;padding:12px">No rules — agents run unlimited</div>` :
            rules.map(r=>`<div class="card" style="padding:9px 12px;display:flex;align-items:center;gap:10px">
              <div style="flex:1"><div style="font-size:12.5px;font-weight:600">${escHtml(r.name)}</div>
              <div style="font-size:11px;color:var(--text-2)">Max $${r.max_cost} · ${r.action}</div></div>
              <span class="badge ${r.enabled?'badge-success':'badge-default'}">${r.enabled?'On':'Off'}</span>
              <button data-act-click="deleteBudgetRule(${JSON.stringify(r.id)})" style="background:none;border:none;color:var(--text-3);cursor:pointer">🗑</button>
            </div>`).join('')}
          </div>
        </div>
      </div>
      </div>`;
  } catch(e) {
    pane.innerHTML = `<div class="page-content">${emptyState({icon:'⚠️',title:'Error',body:escHtml(e.message)})}</div>`;
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

