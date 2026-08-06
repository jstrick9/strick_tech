// Agent Identity — Extracted from 06-sprint-features.js
(function(S, nav, toast, escHtml, fetch, document) {
async function renderAgentIdentity() {
  const pane = document.getElementById('pane-agent-identity');
  if (!pane) return;

  const [list, sysStats] = await Promise.all([
    fetch('/api/agent-identity').then(r=>r.ok?r.json():{identities:[],count:0}).catch(()=>({identities:[],count:0})),
    fetch('/api/agent-identity/system/stats').then(r=>r.ok?r.json():{}).catch(()=>({})),
  ]);

  const authColor = {minimal:'var(--text-3)',standard:'var(--success)',elevated:'var(--warning)',admin:'var(--danger)'};
  const authIcon  = {minimal:'🔵',standard:'🟢',elevated:'🟡',admin:'🔴'};

  pane.innerHTML = `
  <div style="padding:20px;max-width:1100px;margin:0 auto">
    <div class="section-head" style="margin-bottom:20px">
      <div>
        <h2 style="margin:0 0 4px">🪪 Agent Identity & Zero-Trust</h2>
        <p style="margin:0;color:var(--text-2);font-size:13px">Cryptographic identity per agent · JIT access tokens · Least-privilege permissions · Zero-trust verification</p>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn" data-act-click="identityProvisionAll()">⚡ Provision All Agents</button>
        <button class="btn-sm" data-act-click="renderAgentIdentity()">↻ Refresh</button>
      </div>
    </div>

    <!-- System stats -->
    <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:20px">
      ${[
        ['🪪','Total Identities',sysStats.total_identities||0,'var(--accent)'],
        ['✅','Active',sysStats.active_identities||0,'var(--success)'],
        ['🎫','Active JIT Tokens',sysStats.active_jit_tokens||0,'var(--warning)'],
        ['🔑','Permissions',sysStats.total_permissions||0,'#7aa2f7'],
        ['🛡️','Zero-Trust',sysStats.zero_trust_active?'ON':'OFF',sysStats.zero_trust_active?'var(--success)':'var(--danger)'],
      ].map(([icon,label,val,col])=>`
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:12px;text-align:center">
          <div class="u-4ff818ff">${icon}</div>
          <div style="font-size:9px;color:var(--text-3);text-transform:uppercase;letter-spacing:.5px">${label}</div>
          <div style="font-size:18px;font-weight:700;color:${col}">${val}</div>
        </div>`).join('')}
    </div>

    <!-- Zero-trust explainer -->
    <div style="background:rgba(122,162,247,0.08);border:1px solid var(--accent);border-radius:10px;padding:14px 18px;margin-bottom:18px">
      <div style="font-size:12px;font-weight:700;color:var(--accent-text);margin-bottom:6px">🔐 Zero-Trust Architecture Active</div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;font-size:11px;color:var(--text-2)">
        <div>🪪 <strong>Unique cryptographic identity</strong> per agent — no shared service accounts</div>
        <div>⏱️ <strong>JIT tokens expire</strong> automatically — no persistent long-lived credentials</div>
        <div>🎯 <strong>Least-privilege</strong> — agents only get permissions for their current task</div>
      </div>
    </div>

    <!-- Add identity form -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:18px">
      <div style="font-size:12px;font-weight:700;margin-bottom:10px">➕ Provision New Agent Identity</div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end">
        <div>
          <div style="font-size:11px;color:var(--text-3);margin-bottom:4px">Agent ID</div>
          <input id="id-new-agent-id" placeholder="e.g. my-agent" style="background:var(--bg-3);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:12px;color:var(--text-0);width:140px">
        </div>
        <div>
          <div style="font-size:11px;color:var(--text-3);margin-bottom:4px">Display Name</div>
          <input id="id-new-name" placeholder="My Agent" style="background:var(--bg-3);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:12px;color:var(--text-0);width:140px">
        </div>
        <div>
          <div style="font-size:11px;color:var(--text-3);margin-bottom:4px">Authority Level</div>
          <select id="id-new-authority" style="background:var(--bg-3);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:12px;color:var(--text-0)">
            <option value="minimal">Minimal (read-only)</option>
            <option value="standard" selected>Standard</option>
            <option value="elevated">Elevated</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <button class="btn" data-act-click="identityProvisionOne()">🔑 Provision</button>
      </div>
    </div>

    <!-- Identity cards -->
    <div style="font-size:12px;font-weight:700;margin-bottom:10px;color:var(--text-0)">🪪 Agent Identities (${list.count||0})</div>
    ${list.count===0 ? `
      <div style="background:var(--bg-2);border:2px dashed var(--border);border-radius:12px;padding:40px;text-align:center">
        <div style="font-size:32px;margin-bottom:10px">🪪</div>
        <div style="font-weight:700;margin-bottom:6px">No identities provisioned yet</div>
        <div style="color:var(--text-3);font-size:12px;margin-bottom:14px">Click "Provision All Agents" to generate cryptographic keypairs for all 8 default agents</div>
        <button class="btn" data-act-click="identityProvisionAll()">⚡ Provision All Agents Now</button>
      </div>` : `
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px" id="identity-cards">
      ${(list.identities||[]).map(id=>renderIdentityCard(id)).join('')}
    </div>`}

    <!-- Authority level legend -->
    <div style="margin-top:20px;background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:14px">
      <div style="font-size:12px;font-weight:700;margin-bottom:10px">🔑 Authority Level Reference</div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;font-size:11px">
        ${[
          ['🔵','Minimal','Read memory, basic tool use only','var(--text-3)'],
          ['🟢','Standard','+ Write tasks, read files, web search, run code','var(--success)'],
          ['🟡','Elevated','+ Write files, delete tasks, webhooks, manage agents','var(--warning)'],
          ['🔴','Admin','+ Delete files, deploy, manage policies, system config','var(--danger)'],
        ].map(([icon,level,perms,col])=>`
          <div style="background:var(--bg-3);border-radius:8px;padding:10px;border-left:3px solid ${col}">
            <div style="font-weight:700;margin-bottom:4px">${icon} ${level}</div>
            <div style="color:var(--text-2)">${perms}</div>
          </div>`).join('')}
      </div>
    </div>
  </div>`;
}

function renderIdentityCard(id) {
  const authColor = {minimal:'var(--text-3)',standard:'var(--success)',elevated:'var(--warning)',admin:'var(--danger)'};
  const authIcon  = {minimal:'🔵',standard:'🟢',elevated:'🟡',admin:'🔴'};
  return `
  <div class="u-534c2d64">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
      <div style="width:36px;height:36px;border-radius:50%;background:${(authColor[id.authority_level]||'var(--accent)')}22;display:flex;align-items:center;justify-content:center;font-size:18px">
        ${authIcon[id.authority_level]||'🤖'}
      </div>
      <div class="u-97445a8d">
        <div style="font-weight:700;font-size:13px">${escHtml(id.display_name||id.agent_id)}</div>
        <div style="font-size:10px;color:var(--text-3)">${escHtml(id.agent_id)} · v${id.key_version}</div>
      </div>
      <span style="font-size:10px;padding:2px 7px;border-radius:4px;font-weight:700;background:${(authColor[id.authority_level]||'var(--accent)')}22;color:${authColor[id.authority_level]||'var(--accent)'}">
        ${escHtml(id.authority_level||'standard')}
      </span>
    </div>

    <div style="font-size:11px;color:var(--text-3);margin-bottom:8px">
      🎫 Active tokens: <strong style="color:var(--text-1)">${id.active_tokens||0}</strong>
      &nbsp;·&nbsp; 🔑 Permissions: <strong style="color:var(--text-1)">${id.permission_count||0}</strong>
    </div>

    <div style="font-size:10px;color:var(--text-3);margin-bottom:12px;word-break:break-all;background:var(--bg-3);border-radius:6px;padding:6px 8px;font-family:monospace">
      ${(id.public_key||'').slice(0,60)}…
    </div>

    <div style="display:flex;gap:6px;flex-wrap:wrap">
      <button class="btn-sm" data-act-click="identityIssueToken(${JSON.stringify(id.agent_id)})">🎫 Issue Token</button>
      <button class="btn-sm" data-act-click="identityViewPerms(${JSON.stringify(id.agent_id)})">🔑 Permissions</button>
      <button class="btn-sm" data-act-click="identityViewAudit(${JSON.stringify(id.agent_id)})">📋 Audit</button>
      <button class="btn-sm" data-act-click="identityRotateKeys(${JSON.stringify(id.agent_id)})" style="color:var(--warning);border-color:var(--warning)">🔄 Rotate Keys</button>
    </div>

    <div style="margin-top:8px;font-size:10px;color:var(--text-3)">
      Created: ${new Date(id.created_at).toLocaleDateString()} · Last seen: ${new Date(id.last_seen_at).toLocaleDateString()}
    </div>
  </div>`;
}

async function identityProvisionAll() {
  showToast('⚡ Provisioning identities for all agents…');
  const r = await fetch('/api/agent-identity/provision-all', {method:'POST'}).catch(()=>null);
  if (!r||!r.ok) { showToast('⚠️ Provision failed'); return; }
  const d = await r.json();
  showToast(`🪪 ${d.new} new identities provisioned (${d.existing} already existed)`);
  renderAgentIdentity();
}

async function identityProvisionOne() {
  const agentId   = document.getElementById('id-new-agent-id')?.value?.trim();
  const name      = document.getElementById('id-new-name')?.value?.trim();
  const authority = document.getElementById('id-new-authority')?.value;
  if (!agentId) { showToast('⚠️ Agent ID required'); return; }
  const r = await fetch('/api/agent-identity/provision', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({agent_id:agentId,display_name:name||agentId,authority_level:authority})
  }).catch(()=>null);
  if (!r||!r.ok) { showToast('⚠️ Provision failed'); return; }
  const d = await r.json();
  showToast(`🪪 Identity provisioned: ${d.identity?.agent_id}`);
  renderAgentIdentity();
}

async function identityIssueToken(agentId) {
  const taskId = await gmPrompt(`Issue JIT Token for ${agentId}`, 'Task ID (or leave blank):') || '';
  if (taskId === null) return;
  const r = await fetch(`/api/agent-identity/${encodeURIComponent(agentId)}/issue-token`, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({task_id:taskId, ttl_seconds:3600, scope:['read_memory','write_tasks']})
  }).catch(()=>null);
  if (!r||!r.ok) { showToast('⚠️ Token issue failed'); return; }
  const d = await r.json();
  if (!d.ok) { showToast('⚠️ ' + (d.error||'Failed')); return; }
  await gmAlert(`🎫 JIT Token Issued`,
    `Token ID: ${d.token_id}\nAgent: ${agentId}\nTask: ${d.task_id||'(none)'}\nExpires in: 1 hour\nScope: ${(d.scope||[]).join(', ')||'all'}\n\nCopy this token ID — it cannot be retrieved again.\nPresent it with API calls to prove agent identity.`);
  renderAgentIdentity();
}

async function identityViewPerms(agentId) {
  const r = await fetch(`/api/agent-identity/${encodeURIComponent(agentId)}/permissions`).catch(()=>null);
  if (!r||!r.ok) { showToast('Could not load permissions'); return; }
  const d = await r.json();
  const perms = (d.permissions||[]).map(p=>`• ${p.action} on ${p.resource}`).join('\n');
  await gmAlert(`🔑 Permissions: ${agentId}`, perms||'No permissions granted');
}

async function identityViewAudit(agentId) {
  const r = await fetch(`/api/agent-identity/${encodeURIComponent(agentId)}/audit?limit=20`).catch(()=>null);
  if (!r||!r.ok) { showToast('Could not load audit'); return; }
  const d = await r.json();
  const events = (d.events||[]).map(e=>`${new Date(e.created_at).toLocaleTimeString()} — ${e.event_type}: ${e.detail||''}`).join('\n');
  await gmAlert(`📋 Identity Audit: ${agentId}`, events||'No events yet');
}

async function identityRotateKeys(agentId) {
  const ok = await gmDanger('Rotate Keys', `Rotating keys for ${agentId} will:\n\n• Generate new RSA keypair\n• Revoke ALL existing JIT tokens\n• Require re-issuance of any active tokens\n\nProceed?`);
  if (!ok) return;
  const r = await fetch(`/api/agent-identity/${encodeURIComponent(agentId)}/rotate-keys`, {method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).catch(()=>null);
  if (!r||!r.ok) { showToast('⚠️ Key rotation failed'); return; }
  const d = await r.json();
  showToast(`🔄 Keys rotated — ${d.tokens_revoked} tokens revoked`);
  renderAgentIdentity();
}


// ══════════════════════════════════════════════════════════════════
//  PATCH MASTER NAV — Sprint 18 panes
// ══════════════════════════════════════════════════════════════════
// ══════════════════════════════════════════════════════════════════
//  SPRINT B — SUPERVISOR AGENT
// ══════════════════════════════════════════════════════════════════


// ══════════════════════════════════════════════════════════════════
//  TASK DAG VISUALIZER — Complete Implementation
//  Replaces old renderSupervisor + all supervisor* functions
// ══════════════════════════════════════════════════════════════════

window.renderAgentIdentity = renderAgentIdentity;
})(S, nav, toast, escHtml, fetch, document);
