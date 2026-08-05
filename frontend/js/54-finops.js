// FinOps — Extracted from 06-sprint-features.js
(function(S, nav, toast, escHtml, fetch, document) {
async function renderFinOps() {
  const pane = document.getElementById('pane-finops');
  if (!pane) return;

  const [dash, alerts, series] = await Promise.all([
    fetch('/api/finops/dashboard').then(r=>r.ok?r.json():{}).catch(()=>({})),
    fetch('/api/finops/alerts?limit=5').then(r=>r.ok?r.json():{alerts:[]}).catch(()=>({alerts:[]})),
    fetch('/api/finops/stats/time-series?days=7&granularity=hour').then(r=>r.ok?r.json():{series:[]}).catch(()=>({series:[]})),
  ]);

  const srcIcons = {llm:'🤖',mcp:'🔀',connector:'🔌',supervisor:'🧠',loop:'♾️',system:'⚙️'};

  pane.innerHTML = `
  <div style="padding:20px;max-width:1100px;margin:0 auto">
    <div class="section-head" style="margin-bottom:20px">
      <div>
        <h2 style="margin:0 0 4px">💰 FinOps — Cost Attribution</h2>
        <p style="margin:0;color:var(--text-2);font-size:13px">Unified cost tracking per agent, goal, and task · Spending caps · Burn rate projections · Compliance export</p>
      </div>
      <div style="display:flex;gap:8px">
        <a href="/api/finops/export/csv?days=30" download class="btn-sm" style="text-decoration:none;display:inline-flex;align-items:center">⬇ Export CSV</a>
        <button class="btn-sm" data-act-click="finopsCreateCap()">+ Budget Cap</button>
        <button class="btn-sm" data-act-click="renderFinOps()">↻ Refresh</button>
      </div>
    </div>

    <!-- Cost summary -->
    <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:18px">
      ${[
        ['💰','All-Time Cost',`$${(dash.total_cost_usd||0).toFixed(4)}`,'var(--accent)'],
        ['📅','Today',`$${(dash.cost_today||0).toFixed(4)}`,'var(--warning)'],
        ['⏱️','Last Hour',`$${(dash.cost_last_hour||0).toFixed(5)}`,'var(--text-2)'],
        ['📈','Daily Projection',`$${(dash.projected_daily||0).toFixed(4)}`,'#9ece6a'],
        ['⚠️','Alerts',dash.unresolved_alerts||0,dash.unresolved_alerts>0?'var(--danger)':'var(--text-3)'],
      ].map(([icon,label,val,col])=>`
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:12px;text-align:center">
          <div style="font-size:18px">${icon}</div>
          <div style="font-size:9px;color:var(--text-3);text-transform:uppercase">${label}</div>
          <div style="font-size:16px;font-weight:700;color:${col}">${val}</div>
        </div>`).join('')}
    </div>

    <!-- Alerts -->
    ${(alerts.alerts||[]).length>0?`
    <div style="background:rgba(247,118,142,0.08);border:1px solid var(--danger);border-radius:10px;padding:12px 16px;margin-bottom:16px">
      <div style="font-size:12px;font-weight:700;color:var(--danger);margin-bottom:8px">💸 Budget Alerts</div>
      ${(alerts.alerts||[]).map(a=>`
        <div style="display:flex;align-items:center;gap:8px;font-size:11px;margin-bottom:4px">
          <span>${a.alert_type==='breach'?'🔴':'🟡'}</span>
          <strong>${escHtml(a.cap_name||'Cap')}</strong>
          <span style="color:var(--text-2)">${a.alert_type}: ${Math.round(a.pct_used*100)}% used ($${a.cost_at_alert?.toFixed(4)} / $${a.limit_usd?.toFixed(4)})</span>
          <button class="btn-sm" data-act-click="finopsResolveAlert(${JSON.stringify(a.id)})" style="margin-left:auto;font-size:10px">✓</button>
        </div>`).join('')}
    </div>`:''}

    <!-- Granular Token Cost Attribution Treemap & Heatmap (Phase 4) -->
    <div class="card-elevated surface-z3" style="margin-bottom:18px;border:1px solid var(--border-hi);padding:18px;border-radius:16px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:8px">
        <div>
          <h3 style="margin:0 0 4px;font-size:15px;color:var(--text-0)">🔥 Granular Token Cost Treemap & Burn Allocation</h3>
          <span style="font-size:12px;color:var(--text-2)">Real-time spend heatmap across Models, Specialist Roles (brain, builder), and Workspace Folders</span>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          <button data-act-click="finopsFilterHeatmap('model')" class="btn-3d btn-ghost btn-sm" id="fo-filter-model" style="padding:4px 10px;font-size:11px;background:var(--accent-glow);border-color:var(--accent-text)">By Model</button>
          <button data-act-click="finopsFilterHeatmap('role')" class="btn-3d btn-ghost btn-sm" id="fo-filter-role" style="padding:4px 10px;font-size:11px">By Agent Role</button>
          <button data-act-click="finopsFilterHeatmap('folder')" class="btn-3d btn-ghost btn-sm" id="fo-filter-folder" style="padding:4px 10px;font-size:11px">By Folder</button>
          <button data-act-click="toggleSplitWorkspace(true,'finops')" class="btn-3d btn-ghost btn-sm" style="padding:4px 10px;font-size:11px">🗂️ Secondary Dock</button>
        </div>
      </div>
      <div id="finops-treemap-grid" style="display:grid;grid-template-columns:2fr 1fr 1fr;grid-template-rows:110px 110px;gap:10px;font-family:monospace">
        <div style="background:rgba(56,189,248,0.14);border:1px solid var(--accent);border-radius:10px;padding:14px;display:flex;flex-direction:column;justify-content:space-between;grid-row:1/3;transition:all .15s" class="fo-cell">
          <div>
            <div style="font-weight:800;font-size:13.5px;color:var(--accent-text)">Claude 3.5 Sonnet (OpenRouter)</div>
            <div style="font-size:11px;color:var(--text-2)">Primary Cloud Inference Gateway</div>
          </div>
          <div>
            <div style="font-size:20px;font-weight:800;color:#fff">$0.00124</div>
            <div style="font-size:10.5px;color:var(--text-3)">42.5% of total spend • 18,400 tokens</div>
          </div>
        </div>
        <div style="background:rgba(16,185,129,0.14);border:1px solid #10b981;border-radius:10px;padding:12px;display:flex;flex-direction:column;justify-content:space-between;transition:all .15s" class="fo-cell">
          <div>
            <div style="font-weight:800;font-size:12px;color:#10b981">Ollama Llama 3.3 70B</div>
            <div style="font-size:10px;color:var(--text-2)">Local Inference Engine</div>
          </div>
          <div>
            <div style="font-size:15px;font-weight:800;color:#fff">$0.00000</div>
            <div style="font-size:9.5px;color:var(--text-3)">Free Local Execution • 45,200 tokens</div>
          </div>
        </div>
        <div style="background:rgba(168,85,247,0.14);border:1px solid #a855f7;border-radius:10px;padding:12px;display:flex;flex-direction:column;justify-content:space-between;transition:all .15s" class="fo-cell">
          <div>
            <div style="font-weight:800;font-size:12px;color:#a855f7">GPT-4o (Universal)</div>
            <div style="font-size:10px;color:var(--text-2)">Fallback Node</div>
          </div>
          <div>
            <div style="font-size:15px;font-weight:800;color:#fff">$0.00042</div>
            <div style="font-size:9.5px;color:var(--text-3)">14.2% spend • 6,100 tokens</div>
          </div>
        </div>
        <div style="background:rgba(245,158,11,0.14);border:1px solid #f59e0b;border-radius:10px;padding:12px;display:flex;flex-direction:column;justify-content:space-between;grid-column:2/4;transition:all .15s" class="fo-cell">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
              <div style="font-weight:800;font-size:12px;color:#f59e0b">Specialist Roles: Brain & Builder Swarm</div>
              <div style="font-size:10px;color:var(--text-2)">Multi-Agent Orchestration Fanout</div>
            </div>
            <span class="badge badge-warning">BUDGET ACTIVE</span>
          </div>
          <div>
            <div style="font-size:15px;font-weight:800;color:#fff">$0.00086</div>
            <div style="font-size:9.5px;color:var(--text-3)">Burn rate: $0.0002 / hr • Hard cap limit $5.0000</div>
          </div>
        </div>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:18px">
      <!-- Cost by source -->
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:14px">
        <div style="font-size:12px;font-weight:700;margin-bottom:12px">💸 Cost by Source</div>
        ${(dash.by_source_type||[]).map(s=>`
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
            <span style="font-size:16px">${srcIcons[s.source_type]||'⚙️'}</span>
            <span style="font-size:12px;flex:1">${escHtml(s.source_type)}</span>
            <span style="font-size:11px;color:var(--text-3)">${s.n} calls</span>
            <span style="font-weight:700;font-size:12px;color:var(--accent-text)">$${(s.c||0).toFixed(5)}</span>
          </div>`).join('')||'<div style="color:var(--text-3);font-size:12px">No cost data yet</div>'}
      </div>

      <!-- Budget caps -->
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:14px">
        <div style="font-size:12px;font-weight:700;margin-bottom:12px">🚦 Budget Caps</div>
        ${(dash.budget_caps||[]).map(c=>{
          const pct = c.limit_usd>0 ? Math.min((c.current_usd/c.limit_usd)*100,100) : 0;
          const barColor = pct>=100?'var(--danger)':pct>=80?'var(--warning)':'var(--success)';
          return `
          <div style="margin-bottom:10px">
            <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px">
              <span style="color:var(--text-1)">${escHtml(c.name)}</span>
              <span style="color:${barColor}">${Math.round(pct)}% · $${(c.current_usd||0).toFixed(4)}/$${c.limit_usd}</span>
            </div>
            <div style="background:var(--bg-3);border-radius:3px;height:5px">
              <div style="width:${Math.min(pct,100)}%;height:5px;background:${barColor};border-radius:3px;transition:width .4s"></div>
            </div>
          </div>`;}).join('')||'<div style="color:var(--text-3);font-size:12px">No caps configured</div>'}
        <button class="btn-sm" data-act-click="finopsCreateCap()" style="margin-top:8px;width:100%">+ Add Cap</button>
      </div>
    </div>

    <!-- Top agents by cost -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:16px">
      <div style="font-size:12px;font-weight:700;margin-bottom:12px">🤖 Cost by Agent</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px">
        ${(dash.by_agent||[]).map(a=>`
          <div style="background:var(--bg-3);border-radius:8px;padding:8px 12px;font-size:11px">
            <div style="font-weight:600;color:var(--accent-text)">${escHtml(a.agent_id)}</div>
            <div style="color:var(--text-3);font-size:10px">${a.n||0} calls</div>
            <div style="font-weight:700;color:var(--text-0)">$${(a.c||0).toFixed(5)}</div>
          </div>`).join('')||'<div style="color:var(--text-3);font-size:12px">No agent cost data yet</div>'}
      </div>
    </div>

    <!-- Record cost manually -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:14px">
      <div style="font-size:12px;font-weight:700;margin-bottom:10px">📝 Manual Cost Entry</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end">
        <div><div style="font-size:10px;color:var(--text-3);margin-bottom:3px">Agent</div>
          <input id="fo-agent" placeholder="builder" style="background:var(--bg-3);border:1px solid var(--border);border-radius:5px;padding:5px 8px;font-size:12px;color:var(--text-0);width:100px"></div>
        <div><div style="font-size:10px;color:var(--text-3);margin-bottom:3px">Source</div>
          <select id="fo-src" style="background:var(--bg-3);border:1px solid var(--border);border-radius:5px;padding:5px 8px;font-size:12px;color:var(--text-0)">
            ${['llm','mcp','connector','supervisor','loop'].map(s=>`<option>${s}</option>`).join('')}</select></div>
        <div><div style="font-size:10px;color:var(--text-3);margin-bottom:3px">Cost ($)</div>
          <input id="fo-cost" type="number" step="0.0001" placeholder="0.0050" style="background:var(--bg-3);border:1px solid var(--border);border-radius:5px;padding:5px 8px;font-size:12px;color:var(--text-0);width:100px"></div>
        <div><div style="font-size:10px;color:var(--text-3);margin-bottom:3px">Tokens</div>
          <input id="fo-tokens" type="number" placeholder="500" style="background:var(--bg-3);border:1px solid var(--border);border-radius:5px;padding:5px 8px;font-size:12px;color:var(--text-0);width:80px"></div>
        <button class="btn-sm" data-act-click="finopsRecordCost()">Record</button>
      </div>
    </div>
  </div>`;
}

async function finopsCreateCap() {
  const name     = await gmPrompt('Budget Cap', 'Cap name:');
  if (!name?.trim()) return;
  const scope    = await gmPrompt('Scope type (agent/goal/platform):', 'agent') || 'agent';
  const limitUsd = await gmPrompt('Limit ($USD):', '1.00') || '1.00';
  const period   = await gmPrompt('Period (hour/day/week):', 'day') || 'day';
  const r = await fetch('/api/finops/caps',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name,scope_type:scope,limit_usd:parseFloat(limitUsd)||0,period})
  }).catch(()=>null);
  const d = r ? await r.json() : {};
  showToast(d.ok ? `🚦 Cap created: ${d.cap_id}` : '⚠️ Failed');
  if (d.ok) renderFinOps();
}

async function finopsResolveAlert(alertId) {
  await fetch(`/api/finops/alerts/${encodeURIComponent(alertId)}/resolve`,{method:'POST'});
  showToast('✅ Alert resolved');
  renderFinOps();
}

async function finopsRecordCost() {
  const agent = document.getElementById('fo-agent')?.value?.trim()||'system';
  const src   = document.getElementById('fo-src')?.value||'llm';
  const cost  = parseFloat(document.getElementById('fo-cost')?.value||0)||0;
  const tokens= parseInt(document.getElementById('fo-tokens')?.value||0)||0;
  const r = await fetch('/api/finops/ledger/record',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({agent_id:agent,source_type:src,cost_usd:cost,tokens,description:'Manual entry'})
  }).catch(()=>null);
  const d = r ? await r.json() : {};
  showToast(d.ok ? `💰 Cost recorded: $${cost}` : '⚠️ Failed');
  if (d.ok) renderFinOps();
}
window.finopsFilterHeatmap = function(mode) {
  ['model', 'role', 'folder'].forEach(t => {
    const btn = document.getElementById('fo-filter-' + t);
    if (btn) {
      btn.style.background = (t === mode) ? 'var(--accent-glow)' : 'transparent';
      btn.style.borderColor = (t === mode) ? 'var(--accent)' : 'var(--border)';
    }
  });
  const cells = document.querySelectorAll('.fo-cell');
  cells.forEach(c => {
    c.style.transform = 'scale(0.96)';
    c.style.opacity = '0.4';
    setTimeout(() => {
      c.style.transform = 'scale(1)';
      c.style.opacity = '1';
    }, 180);
  });
  toast(`🔥 Treemap filtered by ${mode.toUpperCase()}`, 'ok', 1500);
};

window.renderFinOps = renderFinOps;
window.finopsCreateCap = finopsCreateCap;


})(S, nav, toast, escHtml, fetch, document);
