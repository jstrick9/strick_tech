// Leaderboard — Extracted from 06-sprint-features.js
(function(S, nav, toast, escHtml, fetch, document) {
async function renderLeaderboard() {
  const pane = document.getElementById('pane-leaderboard');
  if (!pane) return;

  const [lb, gov, discovered] = await Promise.all([
    fetch('/api/agent-leaderboard?days=30').then(r=>{ if(!r.ok) throw new Error(r.status); return r.json(); }).catch(()=>({leaderboard:[]})),
    fetch('/api/agent-leaderboard/governance/summary').then(r=>{ if(!r.ok) throw new Error(r.status); return r.json(); }).catch(()=>({})),
    fetch('/api/agent-leaderboard/discover').then(r=>{ if(!r.ok) throw new Error(r.status); return r.json(); }).catch(()=>({agents:[]})),
  ]);

  pane.innerHTML = `
  <div style="padding:20px;max-width:1000px;margin:0 auto">
    <div class="section-head">
      <div>
        <h2>🏆 Agent Leaderboard</h2>
        <p>Rank agents by success rate, speed, and cost. Like Arthur AI's governance dashboard — discover and govern all agents.</p>
      </div>
      <button class="btn-sm" data-act-click="lbSeedData()">🎲 Seed Test Data</button>
    </div>

    <!-- Governance summary -->
    <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:20px">
      ${[
        ['🤖',gov.active_agents||0,'Active Agents'],
        ['📋',gov.active_policies||0,'Policies'],
        ['⏳',gov.pending_approvals||0,'Pending HITL'],
        ['📞',gov.calls_24h||0,'Calls (24h)'],
        ['❌',`${gov.error_rate_7d||0}%`,'Error Rate'],
      ].map(([icon,val,label])=>`
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:12px;text-align:center">
          <div style="font-size:18px">${icon}</div>
          <div style="font-size:18px;font-weight:700;color:var(--text-0)">${val}</div>
          <div style="font-size:10px;color:var(--text-3)">${label}</div>
        </div>`).join('')}
    </div>

    <!-- Tabs -->
    <div style="display:flex;gap:8px;margin-bottom:14px">
      <button class="btn" data-act-click="lbShowTab('leaderboard',$this)" style="background:var(--accent);color:var(--on-accent)">🏆 Leaderboard</button>
      <button class="btn-sm" data-act-click="lbShowTab('discover',$this)">🔍 Discover</button>
      <button class="btn-sm" data-act-click="lbShowTab('policies',$this)">📋 Policies</button>
    </div>

    <!-- Leaderboard tab -->
    <div id="lb-tab-leaderboard">
      <div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;align-items:center">
        <label style="font-size:11px;color:var(--text-3)">Days:</label>
        <select id="lb-days-select" data-act-change="lbChangeDays($value)" style="background:var(--bg-3);border:1px solid var(--border);border-radius:6px;color:var(--text-1);font-size:11px;padding:3px 8px">
          <option value="7">7d</option><option value="30" selected>30d</option><option value="90">90d</option><option value="365">1y</option>
        </select>
        <label style="font-size:11px;color:var(--text-3)">Task:</label>
        <select id="lb-task-select" data-act-change="lbChangeDays()" style="background:var(--bg-3);border:1px solid var(--border);border-radius:6px;color:var(--text-1);font-size:11px;padding:3px 8px">
          <option value="">All tasks</option>
          <option value="code">Code</option><option value="research">Research</option>
          <option value="chat">Chat</option><option value="analysis">Analysis</option>
        </select>
        <button class="btn-sm" data-act-click="lbExport()" style="margin-left:auto">⬇ Export</button>
      </div>
      <div id="lb-table-container">
      ${(lb.leaderboard||[]).length ? `
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;overflow:hidden">
          <div style="display:grid;grid-template-columns:30px 40px 1fr 85px 70px 80px 70px 60px;padding:8px 14px;background:var(--bg-3);font-size:11px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:.4px">
            <div>#</div><div></div><div>Name</div><div>Success%</div><div>Calls</div><div>Avg Lat</div><div>Cost</div><div>Rating</div>
          </div>
          ${(lb.leaderboard||[]).map((a, i) => {
            const medal = i===0?'🥇':i===1?'🥈':i===2?'🥉':'';
            const col   = a.success_rate>=90?'var(--success)':a.success_rate>=70?'var(--warning)':'var(--danger)';
            const rating = a.avg_rating ? '★'.repeat(Math.round(a.avg_rating)) : '—';
            return `
              <div style="display:grid;grid-template-columns:30px 40px 1fr 85px 70px 80px 70px 60px;padding:10px 14px;border-top:1px solid var(--border);align-items:center;cursor:pointer;transition:background .1s"
                   data-hover="bg:var(--bg-3)" data-hover-out="bg:"
                   data-act-click="lbViewAgent(${JSON.stringify(a.agent_id)})">
                <div style="font-weight:700;color:var(--text-3);font-size:12px">${medal||('#'+(i+1))}</div>
                <div style="font-size:20px">${a.avatar||'🤖'}</div>
                <div>
                  <div style="font-weight:600;color:var(--text-0);font-size:13px">${escHtml(a.name||a.agent_id)}</div>
                  <div style="font-size:10px;color:var(--text-3)">${escHtml(a.agent_id)}</div>
                </div>
                <div style="font-weight:700;color:${col};font-size:13px">${a.success_rate||0}%</div>
                <div style="color:var(--text-2);font-size:12px">${a.total_calls||0}</div>
                <div style="color:var(--text-2);font-size:12px">${Math.round(a.avg_latency||0)}ms</div>
                <div style="color:var(--text-2);font-size:12px">$${(a.total_cost||0).toFixed(4)}</div>
                <div style="color:var(--warning);font-size:11px">${rating}</div>
              </div>`;
          }).join('')}
        </div>
      ` : `
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:40px;text-align:center;color:var(--text-3)">
          <div style="font-size:40px;margin-bottom:12px">🏆</div>
          <div style="font-size:15px;font-weight:600;margin-bottom:8px">No performance data yet</div>
          <div style="font-size:13px;max-width:340px;margin:0 auto">Use your agents and performance data will appear here. Click "Seed Test Data" to demo.</div>
        </div>`}
      </div>
    </div>

    <!-- Discover tab -->
    <div id="lb-tab-discover" style="display:none">
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;overflow:hidden">
        ${(discovered.agents||[]).length ? (discovered.agents||[]).map((a) =>`
          <div style="display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid var(--border);cursor:pointer"
               data-hover="bg:var(--bg-3)" data-hover-out="bg:"
               data-act-click="lbViewAgent(${JSON.stringify(a.id||a.agent_id)})">
            <span style="font-size:22px">${a.avatar||'🤖'}</span>
            <div style="flex:1;min-width:0">
              <div style="font-weight:600;color:var(--text-0);font-size:13px">${escHtml(a.name||a.id)}</div>
              <div style="font-size:11px;color:var(--text-3)">${a.total_calls||0} calls · ${a.success_rate||0}% success · Last: ${(a.last_active||'never').slice(0,16)}</div>
            </div>
            <div style="display:flex;gap:5px;align-items:center;flex-shrink:0">
              <span style="font-size:11px;padding:2px 7px;border-radius:4px;${a.status==='active'?'background:rgba(61,186,122,.15);color:var(--success)':'background:var(--bg-3);color:var(--text-3)'}">${a.status||'idle'}</span>
              ${a.has_loop?'<span style="font-size:10px;background:rgba(232,162,55,.15);color:var(--warning);padding:1px 6px;border-radius:3px">🔁 Loop</span>':''}
              <span style="font-size:10px;padding:2px 6px;border-radius:3px;${a.risk_level==='high'?'background:rgba(232,82,82,.15);color:var(--danger)':a.risk_level==='medium'?'background:rgba(232,162,55,.15);color:var(--warning)':'background:rgba(61,186,122,.15);color:var(--success)'}">
                ${a.risk_level||'low'} risk
              </span>
              <span style="font-size:10px;color:var(--text-3)">${a.policy_count||0} policies</span>
            </div>
          </div>`).join('') : '<div style="color:var(--text-3);padding:20px;text-align:center">No agents found</div>'}
      </div>
    </div>

    <!-- Policies tab -->
    <div id="lb-tab-policies" style="display:none">
      <div style="margin-bottom:10px;display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap">
        <input id="lb-policy-filter" placeholder="Filter by agent…" data-act-input="lbFilterPolicies($value)"
               style="flex:1;min-width:120px;max-width:200px;background:var(--bg-3);border:1px solid var(--border);border-radius:6px;color:var(--text-0);font-size:12px;padding:5px 8px">
        <button class="btn-sm" data-act-click="lbAddPolicy()">＋ Add Policy</button>
      </div>
      <div id="lb-policies-list">Loading…</div>
    </div>
  </div>`;

  lbLoadPolicies();
}

function lbShowTab(tab, btn) {
  ['leaderboard','discover','policies'].forEach(t=>{
    const el=document.getElementById(`lb-tab-${t}`);
    if(el) el.style.display=t===tab?'block':'none';
  });
  document.querySelectorAll('#pane-leaderboard .btn,#pane-leaderboard .btn-sm').forEach(b=>{
    b.style.background=''; b.style.color='';
  });
  if(btn){btn.style.background='var(--accent)';btn.style.color='#fff';}
  if(tab==='policies') lbLoadPolicies();
}

let _lbAllPolicies = [];

async function lbLoadPolicies() {
  const el = document.getElementById('lb-policies-list');
  if (!el) return;
  el.innerHTML = '<div style="color:var(--text-3);font-size:12px;padding:12px">Loading…</div>';
  try {
    const r = await fetch('/api/agent-leaderboard/policies');
    if (!r.ok) { el.innerHTML = `<div style="color:var(--danger);padding:12px">Failed (HTTP ${r.status})</div>`; return; }
    const d = await r.json();
    _lbAllPolicies = d.policies || [];
    lbRenderPolicies(_lbAllPolicies);
  } catch(ex) {
    el.innerHTML = `<div style="color:var(--danger);padding:12px">Error: ${escHtml(ex?.message||String(ex))}</div>`;
  }
}

function lbFilterPolicies(q) {
  const filtered = q ? _lbAllPolicies.filter(p =>
    (p.agent_id||'').toLowerCase().includes(q.toLowerCase()) ||
    (p.policy_type||'').toLowerCase().includes(q.toLowerCase()) ||
    (p.policy_rule||'').toLowerCase().includes(q.toLowerCase())
  ) : _lbAllPolicies;
  lbRenderPolicies(filtered);
}

function lbRenderPolicies(policies) {
  const el = document.getElementById('lb-policies-list');
  if (!el) return;
  el.innerHTML = `
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;overflow:hidden">
      ${policies.length ? policies.map((p) =>`
        <div style="display:flex;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid var(--border);font-size:12px">
          <span style="background:var(--bg-3);padding:1px 6px;border-radius:4px;font-family:monospace;color:var(--accent-text);flex-shrink:0">${escHtml(p.agent_id||'*')}</span>
          <span style="font-weight:600;color:var(--text-1);flex-shrink:0">${escHtml(p.policy_type||'')}</span>
          <span style="color:var(--text-2);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml(p.policy_rule||'')}</span>
          <button data-act-click="lbTogglePolicy(${JSON.stringify(p.id)},${p.enabled?0:1})" style="background:none;border:none;cursor:pointer;font-size:14px" title="${p.enabled?'Disable':'Enable'} policy">${p.enabled?'✅':'❌'}</button>
          <button data-act-click="lbDeletePolicy(${JSON.stringify(p.id)})" style="background:none;border:none;color:var(--danger);cursor:pointer;font-size:14px" title="Delete policy">🗑</button>
        </div>`).join('') : '<div style="color:var(--text-3);padding:16px;text-align:center">No policies configured</div>'}
    </div>`;
}

async function lbTogglePolicy(policyId, newEnabled) {
  try {
    const r = await fetch(`/api/agent-leaderboard/policies/${encodeURIComponent(policyId)}`, {
      method:'PUT', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({enabled: !!newEnabled})
    });
    if (!r.ok) { showToast('Toggle failed: HTTP '+r.status); return; }
    lbLoadPolicies();
  } catch(ex) {
    showToast('Toggle error: '+ex?.message);
  }
}

async function lbDeletePolicy(policyId) {
  const ok = await gmDanger('Delete Policy', 'Remove this governance policy permanently?');
  if (!ok) return;
  try {
    const r = await fetch(`/api/agent-leaderboard/policies/${encodeURIComponent(policyId)}`, {method:'DELETE'});
    if (!r.ok) { showToast('Delete failed: HTTP '+r.status); return; }
    const d = await r.json();
    if (d.ok) { showToast('🗑 Policy deleted'); lbLoadPolicies(); }
    else showToast('Delete failed: '+(d.error||'Unknown'));
  } catch(ex) {
    showToast('Delete error: '+ex?.message);
  }
}

async function lbAddPolicy() {
  const agent_id = await gmPrompt('Agent ID (* for all agents):', '*');
  if (agent_id === null) return;
  const policy_type = await gmPrompt('Policy type (rate_limit|cost_cap|no_pii|no_secrets|custom):', 'custom');
  if (policy_type === null) return;
  const policy_rule = await gmPrompt('Rule description:', '');
  if (!policy_rule) return;
  try {
    const r = await fetch('/api/agent-leaderboard/policies', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({agent_id: agent_id||'*', policy_type: policy_type||'custom', policy_rule})
    });
    if (!r.ok) { showToast('Create policy failed: HTTP '+r.status); return; }
    const d = await r.json();
    if (d.ok) { showToast('✅ Policy added'); lbLoadPolicies(); }
    else showToast('Failed: '+(d.error||'Unknown'));
  } catch(ex) {
    showToast('Error: '+ex?.message);
  }
}

async function lbChangeDays(days) {
  const d = days || document.getElementById('lb-days-select')?.value || '30';
  const task = document.getElementById('lb-task-select')?.value || '';
  const container = document.getElementById('lb-table-container');
  if (!container) return;
  container.innerHTML = '<div style="color:var(--text-3);padding:12px">Loading…</div>';
  try {
    const params = new URLSearchParams({days: d, limit:'20'});
    if (task) params.set('task_type', task);
    const r = await fetch(`/api/agent-leaderboard?${encodeURIComponent(params)}`);
    if (!r.ok) { container.innerHTML = `<div style="color:var(--danger)">Failed (HTTP ${r.status})</div>`; return; }
    const lb = await r.json();
    if (!(lb.leaderboard||[]).length) {
      container.innerHTML = '<div style="color:var(--text-3);padding:20px;text-align:center">No data for selected period/task</div>';
      return;
    }
    container.innerHTML = `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;overflow:hidden">
        <div style="display:grid;grid-template-columns:30px 40px 1fr 85px 70px 80px 70px 60px;padding:8px 14px;background:var(--bg-3);font-size:11px;font-weight:700;color:var(--text-3);text-transform:uppercase">
          <div>#</div><div></div><div>Name</div><div>Success%</div><div>Calls</div><div>Avg Lat</div><div>Cost</div><div>Rating</div>
        </div>
        ${lb.leaderboard.map((a, i) => {
          const medal = i===0?'🥇':i===1?'🥈':i===2?'🥉':'';
          const col   = a.success_rate>=90?'var(--success)':a.success_rate>=70?'var(--warning)':'var(--danger)';
          const rating = a.avg_rating ? '★'.repeat(Math.min(5,Math.round(a.avg_rating))) : '—';
          return `<div style="display:grid;grid-template-columns:30px 40px 1fr 85px 70px 80px 70px 60px;padding:10px 14px;border-top:1px solid var(--border);align-items:center;cursor:pointer;transition:background .1s"
                       data-hover="bg:var(--bg-3)" data-hover-out="bg:"
                       data-act-click="lbViewAgent(${JSON.stringify(a.agent_id)})">
            <div style="font-weight:700;color:var(--text-3);font-size:12px">${medal||('#'+(i+1))}</div>
            <div style="font-size:20px">${a.avatar||'🤖'}</div>
            <div>
              <div style="font-weight:600;color:var(--text-0);font-size:13px">${escHtml(a.name||a.agent_id)}</div>
              <div style="font-size:10px;color:var(--text-3)">${escHtml(a.agent_id)}</div>
            </div>
            <div style="font-weight:700;color:${col};font-size:13px">${a.success_rate||0}%</div>
            <div style="color:var(--text-2);font-size:12px">${a.total_calls||0}</div>
            <div style="color:var(--text-2);font-size:12px">${Math.round(a.avg_latency||0)}ms</div>
            <div style="color:var(--text-2);font-size:12px">$${(a.total_cost||0).toFixed(4)}</div>
            <div style="color:var(--warning);font-size:11px">${rating}</div>
          </div>`;
        }).join('')}
      </div>`;
  } catch(ex) {
    if(container) container.innerHTML = `<div style="color:var(--danger)">Error: ${escHtml(ex?.message||String(ex))}</div>`;
  }
}

async function lbViewAgent(agentId) {
  try {
    const r = await fetch(`/api/agent-leaderboard/agent/${encodeURIComponent(agentId)}`);
    if (!r.ok) { gmAlert('Failed to load agent stats: HTTP '+r.status); return; }
    const d = await r.json();
    const s = d.summary || {};
    const byType = (d.by_type||[]).map(t =>
      `<div style="display:flex;justify-content:space-between;font-size:12px;padding:3px 0">
        <span style="color:var(--text-2)">${escHtml(t.task_type||'')}</span>
        <span><strong>${t.calls||0}</strong> calls · <span style="color:${(t.success_rate||0)>=80?'var(--success)':'var(--danger)'}">${t.success_rate||0}%</span></span>
      </div>`
    ).join('');
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    overlay.innerHTML = `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:16px;max-width:500px;width:100%;max-height:80vh;overflow-y:auto;padding:24px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
          <h3 style="margin:0;color:var(--text-0)">📊 ${escHtml(agentId)} Stats</h3>
          <button data-close="closest:[style*=fixed]" style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px">
          ${[
            ['Total Calls', s.total||0],
            ['Success Rate', (s.success_rate||0)+'%'],
            ['Avg Latency', Math.round(s.avg_latency||0)+'ms'],
            ['Total Tokens', (s.tokens||0).toLocaleString()],
            ['Total Cost', '$'+(s.cost||0).toFixed(6)],
            ['Avg Rating', s.avg_rating||'—'],
          ].map(([l,v]) => `<div style="background:var(--bg-3);border-radius:8px;padding:10px;text-align:center">
            <div style="font-size:16px;font-weight:700;color:var(--text-0)">${v}</div>
            <div style="font-size:10px;color:var(--text-3)">${l}</div>
          </div>`).join('')}
        </div>
        ${byType ? `<div><h4 style="font-size:11px;color:var(--text-3);text-transform:uppercase;margin:0 0 8px">By Task Type</h4>${byType}</div>` : ''}
        <div style="margin-top:16px;display:flex;gap:8px">
          <button class="btn-sm" data-act-click="lbRateAgent(${JSON.stringify(agentId)})">⭐ Rate</button>
          <button class="btn-sm" style="color:var(--danger);border-color:var(--danger)" data-act-click="lbClearAgent(${JSON.stringify(agentId)})" data-close="closest:[style*=fixed]">🗑 Clear Data</button>
        </div>
      </div>`;
    overlay.onclick = e => { if(e.target===overlay) overlay.remove(); };
    document.body.appendChild(overlay);
  } catch(ex) {
    gmAlert('Error loading agent: '+ex?.message);
  }
}

async function lbRateAgent(agentId) {
  const ratingStr = await gmPrompt('Rate this agent (1-5 stars):', '5');
  if (ratingStr === null) return;
  const rating = Math.min(5, Math.max(1, parseInt(ratingStr||'5')));
  if (isNaN(rating)) { gmAlert('Enter a number 1-5'); return; }
  try {
    const r = await fetch('/api/agent-leaderboard/rate', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({agent_id: agentId, rating})
    });
    if (!r.ok) { showToast('Rate failed: HTTP '+r.status); return; }
    showToast(`✅ Rated ${agentId}: ${rating}⭐`);
  } catch(ex) {
    showToast('Rate error: '+ex?.message);
  }
}

async function lbClearAgent(agentId) {
  const ok = await gmDanger('Clear Performance Data', `Delete all performance records for "${agentId}"?`);
  if (!ok) return;
  try {
    const r = await fetch(`/api/agent-leaderboard/performance/${encodeURIComponent(agentId)}`, {method:'DELETE'});
    if (!r.ok) { showToast('Clear failed: HTTP '+r.status); return; }
    const d = await r.json();
    showToast(`🗑 Cleared ${d.deleted||0} records for ${agentId}`);
    renderLeaderboard();
  } catch(ex) {
    showToast('Clear error: '+ex?.message);
  }
}

async function lbExport() {
  try {
    const days = document.getElementById('lb-days-select')?.value || '30';
    const r = await fetch(`/api/agent-leaderboard?days=${days}&limit=100`);
    if (!r.ok) { showToast('Export failed: HTTP '+r.status); return; }
    const d = await r.json();
    const blob = new Blob([JSON.stringify(d.leaderboard, null, 2)], {type:'application/json'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `agent-leaderboard-${new Date().toISOString().slice(0,10)}.json`;
    a.click();
    showToast('✅ Leaderboard exported');
  } catch(ex) {
    showToast('Export error: '+ex?.message);
  }
}

async function lbSeedData() {
  const agents = ['builder','researcher','orchestrator','memory','swarm'];
  const tasks  = ['code','research','chat','analysis','general'];
  let count = 0;
  for (const aid of agents) {
    for (let i = 0; i < Math.floor(Math.random()*10+5); i++) {
      try {
        await fetch('/api/agent-leaderboard/record', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({
            agent_id:   aid,
            task_type:  tasks[Math.floor(Math.random()*tasks.length)],
            success:    Math.random() > 0.15,
            tokens:     Math.floor(Math.random()*1000)+100,
            cost_usd:   Math.random()*0.01,
            latency_ms: Math.floor(Math.random()*3000)+200,
          })
        });
        count++;
      } catch(e) {}
    }
  }
  showToast(`✅ Seeded ${count} performance records`);
  renderLeaderboard();
}


// ══════════════════════════════════════════════════════════════════
// ══════════════════════════════════════════════════════════════════
//  SPRINT A — IMMUTABLE AUDIT LOG
// ══════════════════════════════════════════════════════════════════


// ══════════════════════════════════════════════════════════════════
//  COMPLIANCE REPORT CENTER — Complete Implementation
//  Covers: Audit Log + Compliance Report Generator + Report History
// ══════════════════════════════════════════════════════════════════

// ── State ──────────────────────────────────────────────────────────
window.renderLeaderboard = renderLeaderboard;
})(S, nav, toast, escHtml, fetch, document);
