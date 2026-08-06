// HITL — Extracted from 06-sprint-features.js
(function(S, nav, toast, escHtml, fetch, document, window) {
async function renderHITL() {
  const pane = document.getElementById('pane-hitl');
  if (!pane) return;

  const [queue, stats, audit] = await Promise.all([
    fetch('/api/hitl/queue').then(r=>r.ok?r.json():null).catch(()=>({interrupts:[]})),
    fetch('/api/hitl/stats').then(r=>r.ok?r.json():null).catch(()=>({})),
    fetch('/api/hitl/audit?limit=10').then(r=>r.ok?r.json():null).catch(()=>({audit:[]})),
  ]);

  const riskColors = {low:'var(--success)',medium:'var(--warning)',high:'var(--danger)',critical:'#ff4444'};

  pane.innerHTML = `
  <div style="padding:20px;max-width:900px;margin:0 auto">
    <div class="section-head">
      <div>
        <h2>🛡️ Human-in-the-Loop</h2>
        <p>Confidence gates, interruption protocols, safe undo — agents pause for human approval before risky actions</p>
      </div>
      <button class="btn-sm" data-act-click="hitlTestInterrupt()">🧪 Test Interrupt</button>
    </div>

    <!-- Stats -->
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px">
      ${[
        ['⏳','Pending',stats.pending||0,'var(--warning)'],
        ['✅','Approved',stats.approved||0,'var(--success)'],
        ['❌','Rejected',stats.rejected||0,'var(--danger)'],
        ['📊','Approval Rate',`${stats.approval_rate||0}%`,'var(--accent)'],
      ].map(([icon,label,val,col])=>`
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:14px;text-align:center">
          <div class="u-881f70f9">${icon}</div>
          <div style="font-size:10px;color:var(--text-3);text-transform:uppercase">${label}</div>
          <div style="font-size:20px;font-weight:700;color:${col}">${val}</div>
        </div>`).join('')}
    </div>

    <!-- Pending queue with Side-by-Side Diff Verification (Phase 4) -->
    <div style="font-size:13px;font-weight:700;margin-bottom:10px">⏳ Pending Approval & Diff Verification (${(queue.interrupts||[]).length})</div>
    <div id="hitl-queue">
      ${(queue.interrupts||[]).map(item=>`
        <div class="card-elevated surface-z3" style="border:2px solid ${(item.confidence < 0.85) ? '#ff4444' : (riskColors[item.risk_level]||'var(--border)')};border-radius:14px;padding:18px;margin-bottom:14px;position:relative;box-shadow:${(item.confidence < 0.85) ? '0 0 28px rgba(255,68,68,0.22)' : 'var(--shadow)'}">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;flex-wrap:wrap;gap:8px">
            <div style="display:flex;align-items:center;gap:8px">
              <span style="font-size:11px;padding:3px 8px;border-radius:4px;font-weight:800;background:${riskColors[item.risk_level]||'var(--text-3)'}22;color:${riskColors[item.risk_level]||'var(--text-3)'};text-transform:uppercase">${item.risk_level||'high'}</span>
              <strong style="color:var(--text-0);font-size:14px">${escHtml(item.action_type||'Protected State Modification')}</strong>
            </div>
            <div style="display:flex;align-items:center;gap:8px">
              <span class="badge ${(item.confidence < 0.85) ? 'badge-danger' : 'badge-warning'}">${Math.round((item.confidence||0.65)*100)}% Confidence ${(item.confidence < 0.85) ? '⚠️ < 85% INTERRUPT' : 'GATED'}</span>
              <span style="font-size:11px;color:var(--text-3);font-family:monospace">${new Date(item.created_at).toLocaleTimeString()}</span>
            </div>
          </div>
          <div style="font-size:13px;color:var(--text-1);margin-bottom:14px;line-height:1.6">${escHtml(item.action_summary||'Autonomous agent requested execution of protected operational state mutation.')}</div>
          
          <!-- Side-by-Side Diff Verification -->
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;background:#04060f;border:1px solid var(--border-hi);border-radius:10px;padding:12px;font-family:monospace;font-size:11.5px;max-height:260px;overflow-y:auto">
            <div style="border-right:1px solid var(--border);padding-right:10px">
              <div style="color:#f87171;font-weight:700;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px">--- Current Baseline / Safe State</div>
              <pre style="margin:0;color:#cbd5e1;white-space:pre-wrap">${escHtml(item.baseline_state || (item.action_details && item.action_details.old_text) || "// Current operational baseline prior to action execution.\n// System integrity verified and state intact.\n\nfunction verifyBaseline() {\n  return { status: 'stable', writeProtected: true };\n}")}</pre>
            </div>
            <div style="padding-left:4px">
              <div style="color:#34d399;font-weight:700;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px">+++ Proposed Agent Execution Diff</div>
              <pre style="margin:0;color:#a7f3d0;white-space:pre-wrap">${escHtml(item.proposed_state || (item.action_details && item.action_details.new_text) || item.action_summary || "+ Executing autonomous state modification / code mutation.\n\nfunction updateTargetState() {\n  return { status: 'modified', newVersion: 'v11.2' };\n}")}</pre>
            </div>
          </div>

          <div style="display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap">
            <div style="display:flex;gap:8px">
              <button class="btn-3d btn-primary btn-sm" data-act-click="hitlDecide(${JSON.stringify(item.id)},'approve')" style="background:var(--success);border:none;color:#fff;padding:6px 14px">✅ Approve & Continue</button>
              <button class="btn-3d btn-ghost btn-sm u-6c51dbca" data-act-click="hitlModify(${JSON.stringify(item.id)})" >✏ Modify Parameters</button>
              <button class="btn-3d btn-danger btn-sm u-6c51dbca" data-act-click="hitlDecide(${JSON.stringify(item.id)},'reject')" >🛑 Abort & Revert</button>
            </div>
            <button data-act-click="toggleSplitWorkspace(true,'hitl')" class="btn-3d btn-ghost btn-sm" style="padding:4px 10px;font-size:11px">🗂️ Secondary Dock</button>
          </div>
        </div>`).join('') || '<div style="color:var(--text-3);padding:24px;text-align:center;background:var(--surface-z1);border-radius:12px;border:1px dashed var(--border)">No pending interruptions — autonomous agents operating safely within set confidence thresholds.</div>'}
    </div>

    <!-- Confidence threshold settings -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px;margin-top:16px">
      <div style="font-size:13px;font-weight:700;margin-bottom:12px">⚙️ Confidence Thresholds</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:12px">
        ${[['Low Risk','Auto-approve if ≥70%','var(--success)'],['Medium Risk','Interrupt if <85%','var(--warning)'],['High Risk','Always interrupt','var(--danger)'],['Critical','Always + dual confirm','#ff4444']].map(([level,desc,col])=>`
          <div style="background:var(--bg-3);border-radius:8px;padding:10px;border-left:3px solid ${col}">
            <div style="font-weight:600;color:var(--text-0)">${level}</div>
            <div style="color:var(--text-2);font-size:11px">${desc}</div>
          </div>`).join('')}
      </div>
    </div>

    <!-- Sprint A: Delegation Profiles -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px;margin-top:16px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
        <div style="font-size:13px;font-weight:700">🎛️ Delegation Profiles</div>
        <button class="btn-sm" data-act-click="hitlSaveDelegation()">💾 Save Profile</button>
      </div>
      <p style="font-size:11px;color:var(--text-3);margin:0 0 12px">Configure which action classes agents can perform autonomously vs. which always require your approval.</p>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:12px">
        ${[
          ['💸','Financial Transactions','stripe_charge,financial_transaction,ap2_payment','Always approve'],
          ['📧','External Communications','send_email,send_message,post_to_social','Always approve'],
          ['🗂️','File Deletions','delete_file,rm_rf','Always approve'],
          ['🚀','Production Deployments','deploy_to_production,push_to_main','Always approve'],
          ['📝','File Writes','write_file,update_file','Auto if ≥80% confidence'],
          ['🔍','Read & Search','read_file,web_search,read_memory','Always auto-approve'],
        ].map(([icon,label,actions,defaultVal])=>`
          <div style="background:var(--bg-3);border-radius:8px;padding:10px;display:flex;align-items:center;gap:8px">
            <span class="u-1444c6ea">${icon}</span>
            <div class="u-97445a8d">
              <div style="font-weight:600">${label}</div>
              <div style="font-size:10px;color:var(--text-3)">${defaultVal}</div>
            </div>
            <select class="hitl-deleg-sel" data-actions="${actions}" style="font-size:11px;background:var(--bg-2);border:1px solid var(--border);border-radius:5px;padding:3px 6px;color:var(--text-0)">
              <option value="auto">Auto-approve</option>
              <option value="auto_high" ${defaultVal.includes('80')? 'selected':''}>Auto if ≥80%</option>
              <option value="interrupt" ${defaultVal.includes('Always approve')? 'selected':''}>Always interrupt</option>
            </select>
          </div>`).join('')}
      </div>
    </div>

    <!-- Sprint A: Timeout Configuration -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px;margin-top:16px">
      <div style="font-size:13px;font-weight:700;margin-bottom:10px">⏱️ Approval Timeout Handling</div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;font-size:12px">
        <div style="background:var(--bg-3);border-radius:8px;padding:10px">
          <div style="font-weight:600;margin-bottom:4px">Default Timeout</div>
          <div style="display:flex;align-items:center;gap:6px">
            <input type="number" id="hitl-timeout" value="300" min="30" max="1800" style="width:70px;background:var(--bg-2);border:1px solid var(--border);border-radius:5px;padding:3px 6px;color:var(--text-0);font-size:12px">
            <span style="color:var(--text-3)">seconds</span>
          </div>
        </div>
        <div style="background:var(--bg-3);border-radius:8px;padding:10px">
          <div style="font-weight:600;margin-bottom:4px">On Timeout</div>
          <select id="hitl-timeout-action" style="font-size:11px;background:var(--bg-2);border:1px solid var(--border);border-radius:5px;padding:3px 6px;color:var(--text-0);width:100%">
            <option value="pause">Pause agent (safe default)</option>
            <option value="reject">Auto-reject action</option>
            <option value="escalate">Escalate to admin</option>
          </select>
        </div>
        <div style="background:var(--bg-3);border-radius:8px;padding:10px">
          <div style="font-weight:600;margin-bottom:4px">Notification</div>
          <div style="font-size:11px;color:var(--text-2)">
            🔔 Browser notification sent<br>
            📋 HITL queue badge shown<br>
            ⚡ WebSocket real-time push
          </div>
        </div>
      </div>
    </div>

    <!-- Audit log -->
    <div style="margin-top:16px;font-size:13px;font-weight:700;margin-bottom:8px">📋 Recent Decisions</div>
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;overflow:hidden">
      ${(audit.audit||[]).map(a=>`
        <div style="display:flex;align-items:center;gap:8px;padding:8px 14px;border-bottom:1px solid var(--border);font-size:12px">
          <span style="font-size:14px">${a.decision==='approve'?'✅':a.decision==='reject'?'❌':a.decision==='modify'?'✏️':'⚙️'}</span>
          <span style="font-weight:600">${escHtml(a.action_type||'action')}</span>
          <span style="color:var(--text-3)">${escHtml(a.action_summary||'')?.slice(0,60)}</span>
          <span style="margin-left:auto;color:var(--text-3)">${new Date(a.created_at).toLocaleTimeString()}</span>
        </div>`).join('') || '<div style="color:var(--text-3);padding:12px;text-align:center">No decisions yet</div>'}
    </div>

    <!-- Sprint A: Link to full audit log -->
    <div style="margin-top:12px;text-align:center">
      <button class="btn-sm" data-act-click="nav('audit-log')" style="color:var(--accent-text);border-color:var(--accent-text)">🔏 View Full Immutable Audit Log →</button>
    </div>
  </div>`;

  // Poll for new interrupts every 5s — FIX 4: re-render cards, not just box-shadow
  let _hitlLastCount = (queue.interrupts||[]).length;
  (function pollHITL() {
    if (!document.getElementById('pane-hitl')?.classList.contains('active')) return;
    setTimeout(async () => {
      try {
        const r = await fetch('/api/hitl/queue');
        const d = await r.json();
        const newCount = (d.interrupts||[]).length;
        if (newCount !== _hitlLastCount) {
          _hitlLastCount = newCount;
          renderHITL();  // full re-render when queue changes
          return;        // renderHITL restarts its own poll
        }
      } catch(e) {}
      pollHITL();
    }, 5000);
  })();
}

async function hitlDecide(id, decision) {
  const note = decision==='reject' ? await gmPrompt('Reason for rejection:','') : '';
  try {
    await fetch(`/api/hitl/interrupt/${encodeURIComponent(id)}/decide`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({decision,note,reviewer:'user'})});
    const _decLabel = decision==='approve'?'✅ Approved':decision==='modify'?'✏️ Modified':'❌ Rejected';
    showToast(`${_decLabel}: ${id}`);
    renderHITL();
  } catch(ex) { gmAlert('Decision failed: '+ex.message); }
}

async function hitlModify(id) {
  // FIX 3: send modified_action_data to the decide endpoint
  const mod = await gmPrompt('Modified action (JSON):','{}');
  if (mod === null) return;  // user cancelled
  let data = {};
  try { data = JSON.parse(mod||'{}'); } catch(e) { showToast('⚠️ Invalid JSON — using empty data'); }
  const note = await gmPrompt('Note (optional):','') || '';
  try {
    await fetch(`/api/hitl/interrupt/${encodeURIComponent(id)}/decide`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({decision:'modify', note, reviewer:'user', modified_action_data: data})
    });
    showToast('✏️ Modified & approved: ' + id);
    renderHITL();
  } catch(ex) { gmAlert('Modify failed: ' + ex.message); }
}
window.renderHITL = renderHITL;
window.hitlDecide = hitlDecide;
window.hitlModify = hitlModify;

async function hitlTestInterrupt() {
  const r = await fetch('/api/hitl/interrupt',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    action_type:'AST_MUTATION_CRITICAL',
    action_summary:'Autonomous agent requested execution of AST mutation on index.html with confidence < 85%',
    risk_level:'critical',
    confidence:0.72,
    agent_id:'builder',
    baseline_state: "// Current operational baseline index.html\n<div id=\"app-header\">\n  <h1>Strick Tech Agentic OS v11.0</h1>\n  <span class=\"badge\">Production Stable</span>\n</div>\n// All unit tests 100% green verified.",
    proposed_state: "// Proposed autonomous mutation index.html\n<div id=\"app-header\" class=\"header-redesigned\">\n  <h1>Strick Tech Agentic OS v11.2</h1>\n  <span class=\"badge badge-live\">Experimental Core Engine</span>\n  <button onclick=\"initExperimentalEngine()\">⚡ Launch</button>\n</div>\n// Note: Requires HITL approval gate."
  })});
  const d = await r.json();
  showToast(`🛡️ Test interrupt created: ${d.interrupt_id||'auto_approved'}`);
  renderHITL();
}

// Sprint A: Delegation profile save
function hitlSaveDelegation() {
  const sels = document.querySelectorAll('.hitl-deleg-sel');
  const profile = {};
  sels.forEach(s=>{ profile[s.dataset.actions] = s.value; });
  _safeLS.set('hitl_delegation_profile', JSON.stringify(profile));
  const timeout = document.getElementById('hitl-timeout')?.value || '300';
  const timeoutAction = document.getElementById('hitl-timeout-action')?.value || 'pause';
  try { _safeLS.set('hitl_timeout', timeout); } catch {}
  try { _safeLS.set('hitl_timeout_action', timeoutAction); } catch {}
  showToast('🎛️ Delegation profile saved');
  // Log to audit chain
  fetch('/api/audit-log/append',{
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      agent_id:'system', agent_name:'User',
      action_type:'delegation_profile_updated',
      action_detail:`Updated delegation profile with ${Object.keys(profile).length} rules`,
      reasoning:'User updated HITL delegation configuration',
      authority:'user', risk_level:'low', outcome:'success',
      metadata:{profile, timeout, timeout_action:timeoutAction}
    })
  }).catch(()=>{});
}


})(S, nav, toast, escHtml, fetch, document, window);
