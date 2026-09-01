// MCP Gateway — Extracted from 06-sprint-features.js
(function(S, nav, toast, escHtml, fetch, document) {
// NOTE: this state/constants block was originally (incorrectly) left in
// the separate 49-goals.js IIFE, which has its own private closure scope
// and cannot be seen from here. Moved here since it belongs to this module.
// ══════════════════════════════════════════════════════════════════
//  SPRINT C — MCP GATEWAY
// ══════════════════════════════════════════════════════════════════


// ══════════════════════════════════════════════════════════════════
//  POLICY RULE BUILDER — Complete Implementation
//  Replaces old renderMCPGateway + all mcg* functions
// ══════════════════════════════════════════════════════════════════

// ── State ─────────────────────────────────────────────────────────
let _prbPolicies   = [];    // all loaded policies
let _prbServers    = [];    // all MCP servers
let _prbTemplates  = [];    // policy templates
let _prbFilter     = { action: '', search: '', server: '' };
let _prbSelected   = null;  // currently editing policy_id
let _prbTab        = 'rules';  // 'rules' | 'builder' | 'simulator' | 'conflicts' | 'servers'
let _prbConflicts  = null;  // cached conflict data
let _prbSimResult  = null;  // last simulation result
let _prbSelIds     = new Set(); // selected policy IDs for bulk ops

// ── Constants ─────────────────────────────────────────────────────
const PRB_ACTION_COLORS = {
  allow:        { bg: 'rgba(61,186,122,.15)',  border: '#3dba7a',  text: '#3dba7a',  icon: '✅' },
  deny:         { bg: 'rgba(232,82,82,.15)',   border: '#e85252',  text: '#e85252',  icon: '🚫' },
  require_hitl: { bg: 'rgba(232,162,55,.15)', border: '#e8a237',  text: '#e8a237',  icon: '🛂' },
};
const PRB_CATEGORY_COLORS = {
  Security:          '#e85252',
  'Agent Scoping':   '#5b8af8',
  Governance:        '#e8a237',
  'Privileged Access': '#3dba7a',
  'Data Protection': '#9d74f5',
};
const PRB_AGENTS = [
  {id:'*',        label:'All Agents (*)'},
  {id:'researcher', label:'🔍 Researcher'},
  {id:'builder',    label:'🔨 Builder'},
  {id:'reviewer',   label:'🔬 Reviewer'},
  {id:'creative',   label:'✍️  Creative'},
  {id:'brain',      label:'💡 Brain'},
  {id:'orchestrator',label:'🎯 Orchestrator'},
  {id:'memory',     label:'🧠 Memory'},
  {id:'user',       label:'👤 User'},
  {id:'guest',      label:'👻 Guest'},
];
const PRB_CONFLICT_SEVERITY = {
  error:   { icon:'❌', color:'#e85252', label:'Conflict' },
  warning: { icon:'⚠️',  color:'#e8a237', label:'Warning' },
  info:    { icon:'ℹ️',  color:'#5b8af8', label:'Info' },
};

async function renderMCPGateway() {
  const pane = document.getElementById('pane-mcp-gateway');
  if (!pane) return;

  pane.innerHTML = `
  

  <div class="prb-root">
    <!-- ── Sidebar ── -->
    <div class="prb-sidebar">
      <div class="prb-sidebar-head">
        <p class="prb-sidebar-title">📋 Policy Rules</p>
        <div class="prb-stats-row" id="prb-stats-row">
          <div class="prb-stat"><div class="prb-stat-val" id="prb-stat-total" style="color:var(--accent-text)">—</div><div class="prb-stat-lbl">Total</div></div>
          <div class="prb-stat"><div class="prb-stat-val" id="prb-stat-active" style="color:var(--success)">—</div><div class="prb-stat-lbl">Active</div></div>
          <div class="prb-stat"><div class="prb-stat-val" id="prb-stat-deny" style="color:var(--danger)">—</div><div class="prb-stat-lbl">Deny</div></div>
        </div>
        <input class="prb-search" id="prb-search" placeholder="🔍 Search rules…" data-act-input="prbSearchChange($value)">
        <div class="prb-filter-row">
          <select class="prb-filter-sel" id="prb-filter-action" data-act-change="prbFilterChange()">
            <option value="">All actions</option>
            <option value="allow">✅ Allow</option>
            <option value="deny">🚫 Deny</option>
            <option value="require_hitl">🛂 Require HITL</option>
          </select>
          <select class="prb-filter-sel" id="prb-filter-server" data-act-change="prbFilterChange()">
            <option value="">All servers</option>
          </select>
        </div>
      </div>
      <div class="prb-policy-list" id="prb-policy-list">
        <div style="color:var(--text-3);font-size:12px;padding:8px">Loading…</div>
      </div>
      <div class="prb-sidebar-foot">
        <div class="prb-bulk-row">
          <button class="prb-bulk-btn" data-act-click="prbBulkAction('enable')"  title="Enable selected">✓ Enable</button>
          <button class="prb-bulk-btn" data-act-click="prbBulkAction('disable')" title="Disable selected">○ Disable</button>
          <button class="prb-bulk-btn" data-act-click="prbBulkAction('delete')"  title="Delete selected" style="color:var(--danger)">🗑</button>
        </div>
        <button class="prb-new-btn" data-act-click="prbNewRule()">+ New Policy Rule</button>
      </div>
    </div>

    <!-- ── Main ── -->
    <div class="prb-main">
      <div class="prb-toolbar">
        <span class="prb-toolbar-title" id="prb-toolbar-title">Policy Rule Builder</span>
        <button style="padding:4px 10px;border-radius:6px;font-size:11px;background:var(--bg-2);border:1px solid var(--border);color:var(--text-1);cursor:pointer" data-act-click="prbRefresh()">↺ Refresh</button>
        <button style="padding:4px 10px;border-radius:6px;font-size:11px;background:var(--bg-2);border:1px solid var(--border);color:var(--text-1);cursor:pointer" data-act-click="mcgTestCall()">🧪 Test Call</button>
      </div>
      <div class="prb-tab-bar">
        <div class="prb-tab active" id="prb-tab-rules"     data-act-click="prbSetTab('rules')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">📋 Rules</div>
        <div class="prb-tab"        id="prb-tab-builder"   data-act-click="prbSetTab('builder')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">⚙️ Builder</div>
        <div class="prb-tab"        id="prb-tab-simulator" data-act-click="prbSetTab('simulator')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">🧪 Simulator</div>
        <div class="prb-tab"        id="prb-tab-conflicts" data-act-click="prbSetTab('conflicts')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">⚠️ Conflicts<span class="prb-tab-badge" id="prb-conflict-badge" style="display:none">0</span></div>
        <div class="prb-tab"        id="prb-tab-servers"   data-act-click="prbSetTab('servers')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">🖥️ Servers</div>
      </div>
      <div class="prb-content" id="prb-content">
        <div style="padding:40px;text-align:center;color:var(--text-3)">Loading…</div>
      </div>
    </div>
  </div>`;

  await prbRefresh();
}


// ── Load data ──────────────────────────────────────────────────────
async function prbRefresh() {
  const [statsR, polR, srvR, tplR] = await Promise.all([
    fetch('/api/mcp-gateway/stats').then(r=>r.ok?r.json():{}).catch(()=>({})),
    fetch('/api/mcp-gateway/policies').then(r=>r.ok?r.json():{policies:[]}).catch(()=>({policies:[]})),
    fetch('/api/mcp-gateway/servers').then(r=>r.ok?r.json():{servers:[]}).catch(()=>({servers:[]})),
    fetch('/api/mcp-gateway/policies/templates').then(r=>r.ok?r.json():{templates:[]}).catch(()=>({templates:[]})),
  ]);
  _prbPolicies  = polR.policies  || [];
  _prbServers   = srvR.servers   || [];
  _prbTemplates = tplR.templates || [];

  // Update stats
  const st = (id, v) => { const e=document.getElementById(id); if(e) e.textContent=v; };
  st('prb-stat-total',  statsR.active_policies ?? _prbPolicies.filter(p=>p.enabled).length);
  st('prb-stat-active', _prbPolicies.filter(p=>p.enabled).length);
  st('prb-stat-deny',   _prbPolicies.filter(p=>p.action==='deny'&&p.enabled).length);

  // Populate server filter
  const srvSel = document.getElementById('prb-filter-server');
  if (srvSel) {
    const existing = srvSel.value;
    srvSel.innerHTML = '<option value="">All servers</option>' +
      _prbServers.filter(s=>s.server_id.startsWith('srv_filesystem')||s.server_id.startsWith('srv_')).slice(0,10)
        .map(s=>`<option value="${escHtml(s.server_id)}">${escHtml(s.name)}</option>`).join('');
    srvSel.value = existing;
  }

  prbRenderList();
  prbRenderTab();

  // Check conflicts in background
  fetch('/api/mcp-gateway/policies/conflicts').then(r=>r.ok?r.json():null).then(d => {
    if (!d) return;
    _prbConflicts = d;
    const badge = document.getElementById('prb-conflict-badge');
    if (badge) {
      const count = d.conflict_count || 0;
      badge.textContent = count;
      badge.style.display = count > 0 ? 'inline-flex' : 'none';
    }
  }).catch(()=>{});
}

function prbGetFilteredPolicies() {
  return _prbPolicies.filter(p => {
    if (_prbFilter.action && p.action !== _prbFilter.action) return false;
    if (_prbFilter.server && !p.server_id.includes(_prbFilter.server)) return false;
    if (_prbFilter.search) {
      const q = _prbFilter.search.toLowerCase();
      const hay = (p.name + ' ' + p.agent_id + ' ' + p.server_id + ' ' + p.tool_pattern).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function prbSearchChange(q) { _prbFilter.search = q; prbRenderList(); prbRenderTab(); }
function prbFilterChange() {
  _prbFilter.action = document.getElementById('prb-filter-action')?.value || '';
  _prbFilter.server = document.getElementById('prb-filter-server')?.value || '';
  prbRenderList(); prbRenderTab();
}

function prbRenderList() {
  const list = document.getElementById('prb-policy-list');
  if (!list) return;
  const pols = prbGetFilteredPolicies();
  if (!pols.length) {
    list.innerHTML = `<div style="color:var(--text-3);font-size:12px;padding:10px;line-height:1.6">No rules match.</div>`;
    return;
  }
  list.innerHTML = pols.map(p => {
    const ac = PRB_ACTION_COLORS[p.action] || PRB_ACTION_COLORS.allow;
    const isSelected = _prbSelected === p.policy_id;
    const isChecked  = _prbSelIds.has(p.policy_id);
    return `<div class="prb-policy-item ${!p.enabled?'disabled':''} ${isSelected?'selected':''}" data-policy-id="${escHtml(p.policy_id)}" style="border-left-color:${p.enabled?ac.border:'var(--text-3)'}">
      <input type="checkbox" class="prb-policy-check" ${isChecked?'checked':''} data-act-click="prbToggleSelect(${jsArg(p.policy_id)},$checked)" data-stop="1">
      <div class="prb-policy-item-body">
        <div class="prb-policy-item-name">${escHtml(p.name)}</div>
        <div class="prb-policy-item-meta">
          P:${p.priority} · ${escHtml(p.agent_id.slice(0,12))} · ${escHtml(p.tool_pattern.slice(0,14))}
        </div>
      </div>
      <span class="prb-policy-action-badge" style="background:${ac.bg};color:${ac.text}">${ac.icon}</span>
    </div>`;
  }).join('');
}


// ── Tab rendering ──────────────────────────────────────────────────
function prbSetTab(tab) {
  _prbTab = tab;
  document.querySelectorAll('.prb-tab').forEach(el => {
    const t = el.id.replace('prb-tab-','');
    el.classList.toggle('active', t === tab);
  });
  prbRenderTab();
}

function prbRenderTab() {
  const content = document.getElementById('prb-content');
  if (!content) return;
  if (_prbTab === 'rules')     prbRenderRulesTab(content);
  if (_prbTab === 'builder')   prbRenderBuilderTab(content);
  if (_prbTab === 'simulator') prbRenderSimulatorTab(content);
  if (_prbTab === 'conflicts') prbRenderConflictsTab(content);
  if (_prbTab === 'servers')   prbRenderServersTab(content);
}


// ── Rules table tab ────────────────────────────────────────────────
function prbRenderRulesTab(container) {
  const pols = prbGetFilteredPolicies();
  if (!pols.length) {
    container.innerHTML = `<div style="padding:40px;text-align:center;color:var(--text-3)">
      <div style="font-size:36px;margin-bottom:12px">📋</div>
      <div style="font-size:14px;font-weight:600;color:var(--text-1);margin-bottom:8px">No Rules Found</div>
      <div style="font-size:12px;line-height:1.6">No policies match your current filters.<br>Create a new rule or clear your search.</div>
    </div>`;
    return;
  }
  container.innerHTML = `<table class="prb-rules-table">
    <thead><tr>
      <th style="width:28px"><input type="checkbox" id="prb-select-all" data-act-click="prbSelectAll($checked)" class="u-f1722f0d"></th>
      <th>Priority</th>
      <th>Action</th>
      <th>Rule Name</th>
      <th>Agent</th>
      <th>Server</th>
      <th>Tool Pattern</th>
      <th>Status</th>
      <th>Actions</th>
    </tr></thead>
    <tbody>
      ${pols.map(p => {
        const ac = PRB_ACTION_COLORS[p.action] || PRB_ACTION_COLORS.allow;
        const isSelected = _prbSelected === p.policy_id;
        const isChecked  = _prbSelIds.has(p.policy_id);
        const hasConditions = p.conditions && p.conditions !== '{}' && p.conditions !== '';
        return `<tr class="${!p.enabled?'disabled':''} ${isSelected?'selected':''}" data-policy-id="${escHtml(p.policy_id)}">
          <td data-stop="1"><input type="checkbox" ${isChecked?'checked':''} data-policy-id="${escHtml(p.policy_id)}" data-act-click="prbToggleSelect($data.policyId,$checked)" class="u-f1722f0d"></td>
          <td><span class="prb-priority-badge">${p.priority}</span></td>
          <td><span class="prb-action-chip" style="background:${ac.bg};color:${ac.text}">${ac.icon} ${p.action}</span></td>
          <td style="font-weight:600;color:var(--text-0);max-width:180px">
            ${escHtml(p.name)}
            ${hasConditions ? '<span title="Has conditions" style="margin-left:4px;font-size:10px">⏰</span>' : ''}
          </td>
          <td><span class="prb-code">${escHtml(p.agent_id)}</span></td>
          <td><span class="prb-code u-fb2957a3" >${escHtml(p.server_id.replace('srv_',''))}</span></td>
          <td><span class="prb-code">${escHtml(p.tool_pattern)}</span></td>
          <td data-stop="1">
            <span class="prb-toggle" data-policy-id="${escHtml(p.policy_id)}" data-policy-enabled="${p.enabled}" data-act-click="hTogglePolicyEnabled($data.policyId,$data.policyEnabled)" title="${p.enabled?'Click to disable':'Click to enable'}" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
              ${p.enabled ? '🟢' : '⚫'}
            </span>
          </td>
          <td data-stop="1">
            <div class="prb-row-actions">
              <button class="prb-row-btn" data-policy-id="${escHtml(p.policy_id)}" data-act-click="prbEditPolicy($data.policyId)" title="Edit">✏️</button>
              <button class="prb-row-btn" data-policy-id="${escHtml(p.policy_id)}" data-act-click="prbSimulateFromRow($data.policyId)" title="Simulate">🧪</button>
              ${!p.policy_id.startsWith('pol_allow_builtin') ? `<button class="prb-row-btn danger" data-policy-id="${escHtml(p.policy_id)}" data-policy-name="${escHtml(p.name)}" data-act-click="prbDeletePolicy($data.policyId,$data.policyName)" title="Delete">🗑</button>` : ''}
            </div>
          </td>
        </tr>`;
      }).join('')}
    </tbody>
  </table>
  <div style="padding:8px 12px;font-size:11px;color:var(--text-3);border-top:1px solid var(--border)">
    ${pols.length} rules shown${_prbPolicies.length !== pols.length ? ` (${_prbPolicies.length} total)` : ''}
    ${_prbSelIds.size ? ` · <strong style="color:var(--accent-text)">${_prbSelIds.size} selected</strong>` : ''}
  </div>`;
}


// ── Builder tab ─────────────────────────────────────────────────────
function prbRenderBuilderTab(container) {
  const editing = _prbSelected ? _prbPolicies.find(p=>p.policy_id===_prbSelected) : null;

  container.innerHTML = `
  <div class="prb-builder">
    <h3>${editing ? '✏️ Edit Policy Rule' : '⚙️ Build New Policy Rule'}</h3>
    <p class="prb-builder-sub">
      Define who can do what with which tools. Rules are evaluated in <strong>priority order</strong> (lower number = higher precedence). The first matching rule wins.
    </p>

    <!-- Templates (only when creating new) -->
    ${!editing ? `
    <div style="margin-bottom:18px">
      <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px">
        🚀 Start from Template
      </div>
      <div class="prb-templates">
        ${_prbTemplates.map(t => {
          const ac = PRB_ACTION_COLORS[t.action] || PRB_ACTION_COLORS.allow;
          const catCol = PRB_CATEGORY_COLORS[t.category] || 'var(--text-3)';
          return `<div class="prb-tpl-card" data-template-id="${escHtml(t.id||t.name)}" data-act-click="prbApplyTemplateById($data.templateId)" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
            <div class="prb-tpl-icon">${t.icon}</div>
            <div class="prb-tpl-name">${escHtml(t.name)}</div>
            <div class="prb-tpl-desc">${escHtml(t.description)}</div>
            <span class="prb-tpl-cat" style="background:${catCol}22;color:${catCol}">${escHtml(t.category)}</span>
            <span class="prb-tpl-action" style="background:${ac.bg};color:${ac.text}">${ac.icon} ${t.action}</span>
          </div>`;
        }).join('')}
      </div>
      <div style="font-size:11px;color:var(--text-3);margin:10px 0 14px;text-align:center">— or build from scratch below —</div>
    </div>` : ''}

    <!-- Form -->
    <div class="prb-form-grid">
      <div class="prb-form-group full">
        <label class="prb-form-label">Rule Name <span class="required">*</span></label>
        <input class="prb-input" id="prb-f-name" placeholder="e.g. Block file delete in production" value="${escHtml(editing?.name||'')}">
      </div>

      <div class="prb-form-group full">
        <label class="prb-form-label">Description</label>
        <input class="prb-input" id="prb-f-desc" placeholder="What this rule does and why" value="${escHtml(editing?.description||'')}">
      </div>
    </div>

    <!-- Action selector -->
    <div class="prb-form-group u-87c136df" >
      <label class="prb-form-label">Action <span class="required">*</span></label>
      <div class="prb-action-row" id="prb-action-row">
        ${Object.entries(PRB_ACTION_COLORS).map(([action, ac]) => {
          const labels = { allow:['✅','Allow','Permit this tool call to proceed'], deny:['🚫','Deny','Block this call entirely — returns error'], require_hitl:['🛂','Require HITL','Pause and require human approval before proceeding'] };
          const [icon, label, desc] = labels[action];
          const isSelected = (editing?.action || 'allow') === action;
          return `<div class="prb-action-opt ${isSelected?'selected-'+action:''}" id="prb-aopt-${action}" data-action="${escHtml(action)}" data-act-click="prbSelectAction($data.action)" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
            <div class="prb-action-icon">${icon}</div>
            <div class="prb-action-label" style="color:${ac.text}">${label}</div>
            <div class="prb-action-desc">${desc}</div>
          </div>`;
        }).join('')}
      </div>
      <input type="hidden" id="prb-f-action" value="${editing?.action||'allow'}">
    </div>

    <div class="prb-form-grid">
      <!-- Agent -->
      <div class="prb-form-group">
        <label class="prb-form-label">Agent ID</label>
        <select class="prb-select" id="prb-f-agent" data-act-change="prbUpdatePreview()">
          ${PRB_AGENTS.map(a=>`<option value="${a.id}" ${(editing?.agent_id||'*')===a.id?'selected':''}>${escHtml(a.label)}</option>`).join('')}
          <option value="custom_">Custom…</option>
        </select>
        <input class="prb-input" id="prb-f-agent-custom" placeholder="agent_id,another_id" style="display:none;margin-top:4px" value="">
        <div class="prb-form-hint">Use comma-separated IDs for multiple agents, or * for all</div>
      </div>

      <!-- Server -->
      <div class="prb-form-group">
        <label class="prb-form-label">Server / Resource</label>
        <select class="prb-select" id="prb-f-server" data-act-change="prbUpdatePreview()">
          <option value="*">All Servers (*)</option>
          ${_prbServers.slice(0,10).map(s=>`<option value="${s.server_id}" ${(editing?.server_id||'*')===s.server_id?'selected':''}>${escHtml(s.name)}</option>`).join('')}
        </select>
        <div class="prb-form-hint">Which MCP server this rule applies to</div>
      </div>

      <!-- Tool pattern -->
      <div class="prb-form-group">
        <label class="prb-form-label">Tool Pattern</label>
        <input class="prb-input" id="prb-f-tool" placeholder="* or fs.delete or http.*"
          value="${escHtml(editing?.tool_pattern||'*')}" data-act-input="prbUpdatePreview()">
        <div class="prb-form-hint">Glob pattern: * = all, fs.* = all fs tools, fs.delete = exact</div>
      </div>

      <!-- Priority -->
      <div class="prb-form-group">
        <label class="prb-form-label">Priority</label>
        <div class="prb-priority-wrap">
          <input type="range" class="prb-priority-slider" id="prb-f-priority" min="1" max="200"
            value="${editing?.priority||100}" data-act-input="hPriorityInput($value)">
          <span class="prb-priority-val" id="prb-f-priority-val">${editing?.priority||100}</span>
        </div>
        <div class="prb-form-hint">Lower = higher precedence (1 = first evaluated)</div>
      </div>
    </div>

    <!-- Conditions -->
    <div class="prb-form-group u-87c136df" >
      <label class="prb-form-label">
        Conditions (optional)
        <span style="font-size:10px;font-weight:400;color:var(--text-3);margin-left:6px">⏰ Time-based activation</span>
      </label>
      <div class="prb-conditions">
        <div class="prb-condition-item">
          <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:12px;color:var(--text-1)">
            <input type="checkbox" id="prb-cond-time-enabled" class="u-f1722f0d" data-act-change="prbToggleTimeCondition()">
            Active only during time window
          </label>
        </div>
        <div id="prb-cond-time-fields" style="display:none;margin-left:20px;margin-top:8px;display:flex;gap:12px;align-items:center">
          <label style="font-size:11px;color:var(--text-2)">From:</label>
          <input type="number" id="prb-cond-start-hour" min="0" max="23" value="9" class="prb-input" style="width:64px;padding:4px 6px">
          <label style="font-size:11px;color:var(--text-2)">To:</label>
          <input type="number" id="prb-cond-end-hour" min="1" max="24" value="17" class="prb-input" style="width:64px;padding:4px 6px">
          <span style="font-size:10px;color:var(--text-3)">(24h)</span>
        </div>
        <div class="prb-condition-item u-8a77e5a3" >
          <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:12px;color:var(--text-1)">
            <input type="checkbox" id="prb-cond-days-enabled" class="u-f1722f0d" data-act-change="prbToggleDaysCondition()">
            Active only on specific days
          </label>
        </div>
        <div id="prb-cond-days-fields" style="display:none;margin-left:20px;margin-top:6px;display:flex;gap:6px;flex-wrap:wrap">
          ${['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map((d,i)=>
            `<label style="display:flex;align-items:center;gap:3px;font-size:11px;cursor:pointer">
              <input type="checkbox" class="prb-day-check u-f1722f0d" value="${i}" checked >${d}
            </label>`).join('')}
        </div>
      </div>
    </div>

    <!-- Live preview -->
    <div id="prb-preview" class="prb-preview">${prbBuildPreviewText('allow','*','*','*',100,'{}')}</div>

    <!-- Submit row -->
    <div style="display:flex;gap:8px;margin-top:16px;flex-wrap:wrap">
      <button class="prb-new-btn" style="flex:1;padding:10px" data-edit-id="${escHtml(editing?.policy_id||'')}" data-act-click="prbSubmitRule($data.editId)">
        ${editing ? '💾 Save Changes' : '✅ Create Rule'}
      </button>
      ${editing ? `<button style="padding:10px 16px;border-radius:7px;background:var(--bg-2);border:1px solid var(--border);color:var(--text-1);cursor:pointer;font-size:12px" data-act-click="prbClearEdit()">✕ Cancel</button>` : ''}
    </div>
  </div>`;

  // Attach agent select handler
  const agentSel = document.getElementById('prb-f-agent');
  if (agentSel) {
    agentSel.addEventListener('change', () => {
      const custom = document.getElementById('prb-f-agent-custom');
      if (agentSel.value === 'custom_') {
        if (custom) custom.style.display = 'block';
      } else {
        if (custom) custom.style.display = 'none';
      }
      prbUpdatePreview();
    });
  }

  // If editing, restore conditions
  if (editing?.conditions) {
    try {
      const conds = JSON.parse(editing.conditions);
      if (conds.start_hour !== undefined) {
        const cb = document.getElementById('prb-cond-time-enabled');
        if (cb) { cb.checked = true; prbToggleTimeCondition(); }
        const sh = document.getElementById('prb-cond-start-hour');
        const eh = document.getElementById('prb-cond-end-hour');
        if (sh) sh.value = conds.start_hour;
        if (eh) eh.value = conds.end_hour;
      }
      if (conds.days_of_week) {
        const cb = document.getElementById('prb-cond-days-enabled');
        if (cb) { cb.checked = true; prbToggleDaysCondition(); }
        document.querySelectorAll('.prb-day-check').forEach(el => {
          el.checked = conds.days_of_week.includes(parseInt(el.value));
        });
      }
    } catch(e) {}
  }

  prbUpdatePreview();
}

function prbSelectAction(action) {
  document.getElementById('prb-f-action').value = action;
  document.querySelectorAll('.prb-action-opt').forEach(el => {
    el.className = 'prb-action-opt' + (el.id === 'prb-aopt-'+action ? ' selected-'+action : '');
  });
  prbUpdatePreview();
}

function prbToggleTimeCondition() {
  const cb = document.getElementById('prb-cond-time-enabled');
  const fields = document.getElementById('prb-cond-time-fields');
  if (fields) fields.style.display = cb?.checked ? 'flex' : 'none';
  prbUpdatePreview();
}

function prbToggleDaysCondition() {
  const cb = document.getElementById('prb-cond-days-enabled');
  const fields = document.getElementById('prb-cond-days-fields');
  if (fields) fields.style.display = cb?.checked ? 'flex' : 'none';
  prbUpdatePreview();
}

function prbBuildConditionsObject() {
  const conds = {};
  const timeCb = document.getElementById('prb-cond-time-enabled');
  if (timeCb?.checked) {
    conds.start_hour = parseInt(document.getElementById('prb-cond-start-hour')?.value || '9');
    conds.end_hour   = parseInt(document.getElementById('prb-cond-end-hour')?.value   || '17');
  }
  const daysCb = document.getElementById('prb-cond-days-enabled');
  if (daysCb?.checked) {
    conds.days_of_week = [...document.querySelectorAll('.prb-day-check:checked')].map(el=>parseInt(el.value));
  }
  return Object.keys(conds).length ? conds : {};
}

function prbBuildPreviewText(action, agentId, serverId, toolPat, priority, conditionsStr) {
  let cond = '';
  try {
    const c = JSON.parse(conditionsStr);
    if (c.start_hour !== undefined) cond += `\n  when: ${c.start_hour}:00–${c.end_hour}:00`;
    if (c.days_of_week) cond += `\n  days: ${c.days_of_week.map(d=>['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][d]).join(',')}`;
  } catch(e) {}
  return `policy {
  action:   ${action}  # ${PRB_ACTION_COLORS[action]?.icon || ''} ${action === 'allow' ? 'permit call' : action === 'deny' ? 'block call' : 'pause for human review'}
  agent:    ${agentId}
  server:   ${serverId}
  tool:     ${toolPat}
  priority: ${priority}${cond}
}`;
}

function prbUpdatePreview() {
  const preview = document.getElementById('prb-preview');
  if (!preview) return;
  const agentSel = document.getElementById('prb-f-agent');
  const agentId  = agentSel?.value === 'custom_'
    ? (document.getElementById('prb-f-agent-custom')?.value || '*')
    : (agentSel?.value || '*');
  const conds = prbBuildConditionsObject();
  preview.textContent = prbBuildPreviewText(
    document.getElementById('prb-f-action')?.value || 'allow',
    agentId,
    document.getElementById('prb-f-server')?.value || '*',
    document.getElementById('prb-f-tool')?.value   || '*',
    document.getElementById('prb-f-priority')?.value || '100',
    JSON.stringify(conds),
  );
}

function prbApplyTemplate(tpl) {
  const n = document.getElementById('prb-f-name');    if (n) n.value = tpl.name;
  const d = document.getElementById('prb-f-desc');    if (d) d.value = tpl.description;
  const s = document.getElementById('prb-f-server');  if (s) s.value = tpl.server_id;
  const t = document.getElementById('prb-f-tool');    if (t) t.value = tpl.tool_pattern;
  const p = document.getElementById('prb-f-priority');if (p) p.value = tpl.priority;
  const pv = document.getElementById('prb-f-priority-val'); if (pv) pv.textContent = tpl.priority;
  // Agent
  const agentSel = document.getElementById('prb-f-agent');
  if (agentSel) {
    const found = [...agentSel.options].some(o => { if(o.value===tpl.agent_id){o.selected=true;return true;} return false; });
    if (!found) { agentSel.value = '*'; }
  }
  prbSelectAction(tpl.action);
  prbUpdatePreview();
  toast(`📋 Template applied: ${tpl.name}`);
}

async function prbSubmitRule(editingId) {
  const agentSel = document.getElementById('prb-f-agent');
  const agentId  = agentSel?.value === 'custom_'
    ? (document.getElementById('prb-f-agent-custom')?.value?.trim() || '*')
    : (agentSel?.value || '*');
  const name     = document.getElementById('prb-f-name')?.value?.trim();
  const desc     = document.getElementById('prb-f-desc')?.value?.trim()   || '';
  const action   = document.getElementById('prb-f-action')?.value         || 'allow';
  const server   = document.getElementById('prb-f-server')?.value         || '*';
  const tool     = document.getElementById('prb-f-tool')?.value?.trim()   || '*';
  const priority = parseInt(document.getElementById('prb-f-priority')?.value || '100');
  const conditions = prbBuildConditionsObject();

  if (!name) { toast('⚠️ Rule name is required'); return; }

  const body = { name, description: desc, action, agent_id: agentId,
                 server_id: server, tool_pattern: tool, priority, conditions };

  try {
    let r, d;
    if (editingId) {
      r = await fetch(`/api/mcp-gateway/policies/${encodeURIComponent(editingId)}`, {
        method: 'PATCH', headers: {'Content-Type':'application/json'},
        body: JSON.stringify(body)
      });
    } else {
      r = await fetch('/api/mcp-gateway/policies', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify(body)
      });
    }
    d = await r.json();
    if (d.ok) {
      toast(editingId ? `✅ Rule updated` : `✅ Rule created: ${d.policy_id}`);
      _prbSelected = null;
      await prbRefresh();
      prbSetTab('rules');
    } else {
      toast('⚠️ ' + (d.error || 'Failed'));
    }
  } catch(e) { toast('⚠️ ' + e.message); }
}

function prbClearEdit() {
  _prbSelected = null;
  prbRenderBuilderTab(document.getElementById('prb-content'));
}


// ── Simulator tab ──────────────────────────────────────────────────
function prbRenderSimulatorTab(container) {
  const res = _prbSimResult;
  const decAC = res ? (PRB_ACTION_COLORS[res.decision] || PRB_ACTION_COLORS.allow) : null;

  container.innerHTML = `
  <div class="prb-sim">
    <h3>🧪 Policy Simulator</h3>
    <p style="font-size:12px;color:var(--text-3);margin:0 0 16px;line-height:1.5">
      Test your policy rules dry-run — no tool call is executed. See exactly which rule fires and why.
    </p>

    <div class="prb-sim-form">
      <div class="prb-sim-row">
        <div>
          <label style="font-size:11px;font-weight:700;color:var(--text-2);display:block;margin-bottom:4px">Agent ID</label>
          <select class="prb-select" id="sim-agent">
            ${PRB_AGENTS.map(a=>`<option value="${a.id}">${escHtml(a.label)}</option>`).join('')}
          </select>
        </div>
        <div>
          <label style="font-size:11px;font-weight:700;color:var(--text-2);display:block;margin-bottom:4px">Server</label>
          <select class="prb-select" id="sim-server">
            ${_prbServers.slice(0,10).map(s=>`<option value="${s.server_id}">${escHtml(s.name)}</option>`).join('')}
          </select>
        </div>
        <div>
          <label style="font-size:11px;font-weight:700;color:var(--text-2);display:block;margin-bottom:4px">Tool Name</label>
          <input class="prb-input" id="sim-tool" placeholder="fs.delete" value="fs.list">
        </div>
        <button class="prb-sim-btn" data-act-click="prbRunSimulation()">▶ Simulate</button>
      </div>
      <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
        <span style="font-size:10px;color:var(--text-3)">Quick test:</span>
        ${[
          ['researcher','srv_web_search','search.web'],
          ['builder','srv_filesystem','fs.delete'],
          ['*','srv_http','http.post'],
          ['orchestrator','srv_connectors','slack.message'],
        ].map(([a,s,t])=>`<button data-quick="${escHtml(a)}|${escHtml(s)}|${escHtml(t)}" data-act-click="prbQuickSimFromData($data.quick)" style="font-size:10px;padding:2px 8px;border-radius:4px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-2);cursor:pointer">${a} → ${t}</button>`).join('')}
      </div>
    </div>

    ${res ? `
    <div class="prb-sim-result">
      <!-- Decision hero -->
      <div class="prb-sim-decision" style="background:${decAC.bg};border:1px solid ${decAC.border}">
        <span class="prb-sim-decision-icon">${decAC.icon}</span>
        <div>
          <div class="prb-sim-decision-label" style="color:${decAC.text}">${res.decision.toUpperCase()}</div>
          <div class="prb-sim-decision-policy">Matched: <strong>${escHtml(res.matched_policy)}</strong></div>
          <div style="font-size:11px;color:var(--text-3)">
            ${escHtml(res.agent_id)} → ${escHtml(res.server_id)} → ${escHtml(res.tool_name)}
            · ${res.policies_checked} rules evaluated
          </div>
        </div>
      </div>

      <!-- Trace table -->
      <div style="font-size:11px;font-weight:700;color:var(--text-2);margin-bottom:8px">Evaluation Trace (${res.trace.length} rules)</div>
      <table class="prb-trace-table">
        <thead><tr><th>P</th><th>Rule</th><th>Agent</th><th>Server</th><th>Tool</th><th>When</th><th>Match?</th><th>Action</th></tr></thead>
        <tbody>
          ${res.trace.map(t => {
            const isWinner = t.winner;
            const ac = PRB_ACTION_COLORS[t.action] || PRB_ACTION_COLORS.allow;
            return `<tr class="${isWinner?'prb-trace-winner':''} u-eed0f8fb" ${isWinner?'':''}>
              <td style="color:var(--text-3)">${t.priority||'—'}</td>
              <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escHtml(t.name)}">${isWinner?'🏆 ':''} ${escHtml(t.name)}</td>
              <td class="${t.agent_match?'prb-match-yes':'prb-match-no'}">${t.agent_match?'✓':'✗'} <span class="u-0d5be05f">${escHtml((t.agent_id||'').slice(0,12))}</span></td>
              <td class="${t.server_match?'prb-match-yes':'prb-match-no'}">${t.server_match?'✓':'✗'} <span class="u-0d5be05f">${escHtml((t.server_id||'').replace('srv_','').slice(0,12))}</span></td>
              <td class="${t.tool_match?'prb-match-yes':'prb-match-no'}">${t.tool_match?'✓':'✗'} <span class="u-0d5be05f">${escHtml((t.tool_pattern||'').slice(0,12))}</span></td>
              <td class="${t.condition_match===false?'prb-match-no':'prb-match-yes'}" title="${escHtml(t.condition_reason||t.conditions||'always')}">${t.condition_match===false?`✗ <span class="u-0d5be05f">${escHtml(t.condition_reason||'condition')}</span>`:'✓ <span class="u-0d5be05f">always</span>'}</td>
              <td>${t.matched ? '<span class="prb-match-yes">✓ MATCH</span>' : '<span class="prb-match-no">✗</span>'}</td>
              <td><span class="prb-action-chip" style="background:${ac.bg};color:${ac.text}">${ac.icon} ${t.action||'—'}</span></td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
    </div>` : '<div style="color:var(--text-3);font-size:12px;text-align:center;padding:24px">Run a simulation above to see the evaluation trace.</div>'}
  </div>`;
}

async function prbRunSimulation() {
  const agent  = document.getElementById('sim-agent')?.value  || 'researcher';
  const server = document.getElementById('sim-server')?.value || 'srv_filesystem';
  const tool   = document.getElementById('sim-tool')?.value?.trim() || 'fs.list';
  if (!tool) { toast('⚠️ Tool name required'); return; }

  try {
    const r = await fetch('/api/mcp-gateway/policies/simulate', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ agent_id: agent, server_id: server, tool_name: tool })
    });
    _prbSimResult = await r.json();
    prbRenderSimulatorTab(document.getElementById('prb-content'));
  } catch(e) { toast('⚠️ Simulation failed: ' + e.message); }
}

function prbQuickSim(agent, server, tool) {
  const agEl = document.getElementById('sim-agent');
  const svEl = document.getElementById('sim-server');
  const tlEl = document.getElementById('sim-tool');
  if (agEl) agEl.value = agent;
  if (svEl) svEl.value = server;
  if (tlEl) tlEl.value = tool;
  prbRunSimulation();
}

function prbSimulateFromRow(polId) {
  if (typeof polId === 'string') {
    const pol = _prbPolicies.find(p => p.policy_id === polId);
    if (!pol) return;
    const agentSel = document.getElementById('sim-agent');
    const svEl = document.getElementById('sim-server');
    const tlEl = document.getElementById('sim-tool');
    if (agentSel) agentSel.value = pol.agent_id || '*';
    if (svEl) { [...svEl.options].some(o => { if (o.value === pol.server_id) { o.selected = true; return true; } return false; }); }
    if (tlEl) tlEl.value = pol.tool_pattern || '*';
  }
  _prbTab = 'simulator';
  document.querySelectorAll('.prb-tab').forEach(el => el.classList.toggle('active', el.id === 'prb-tab-simulator'));
  const content = document.getElementById('prb-content');
  prbRenderSimulatorTab(content);
  // Pre-fill
  const agEl = document.getElementById('sim-agent');
  const svEl = document.getElementById('sim-server');
  const tlEl = document.getElementById('sim-tool');
  if (agEl) agEl.value = pol.agent_id === '*' ? '*' : pol.agent_id.split(',')[0];
  if (svEl) {
    const parts = pol.server_id.split(',');
    const found = [...(svEl.options||[])].some(o => { if(o.value===parts[0]){o.selected=true;return true;} return false; });
  }
  if (tlEl) {
    // Replace wildcard with concrete example
    tlEl.value = pol.tool_pattern.replace('*','list');
  }
}


// ── Conflicts tab ─────────────────────────────────────────────────
function prbRenderConflictsTab(container) {
  if (!_prbConflicts) {
    container.innerHTML = `<div style="padding:20px;text-align:center;color:var(--text-3)">Loading conflict analysis…</div>`;
    fetch('/api/mcp-gateway/policies/conflicts').then(r=>r.ok?r.json():null).then(d=>{
      if (d) { _prbConflicts=d; prbRenderConflictsTab(container); }
    }).catch(()=>{});
    return;
  }

  const { conflicts=[], conflict_count=0, warning_count=0, total=0 } = _prbConflicts;

  if (!total) {
    container.innerHTML = `<div style="padding:40px;text-align:center;color:var(--text-3)">
      <div style="font-size:36px;margin-bottom:12px">✅</div>
      <div style="font-size:14px;font-weight:600;color:var(--text-1);margin-bottom:6px">No Conflicts Detected</div>
      <div class="u-6cb285c6">All ${_prbPolicies.length} policy rules are consistent. Good governance!</div>
    </div>`;
    return;
  }

  container.innerHTML = `
  <div class="prb-conflicts">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap">
      <h3 style="margin:0;font-size:15px;font-weight:700;color:var(--text-0)">⚠️ Policy Conflicts</h3>
      ${conflict_count ? `<span style="padding:3px 10px;border-radius:5px;font-size:11px;font-weight:700;background:rgba(232,82,82,.15);color:#e85252">${conflict_count} conflicts</span>` : ''}
      ${warning_count  ? `<span style="padding:3px 10px;border-radius:5px;font-size:11px;font-weight:700;background:rgba(232,162,55,.15);color:#e8a237">${warning_count} warnings</span>` : ''}
      <button data-act-click="hResetConflicts()" style="margin-left:auto;font-size:11px;padding:4px 10px;border-radius:5px;background:var(--bg-2);border:1px solid var(--border);color:var(--text-1);cursor:pointer">↺ Re-analyze</button>
    </div>
    <div style="font-size:12px;color:var(--text-3);margin-bottom:16px">
      Showing ${Math.min(total, 50)} of ${total} issues. Conflicts are evaluated against the first ${_prbPolicies.length} active rules.
    </div>
    ${conflicts.slice(0,50).map(c => {
      const sev = PRB_CONFLICT_SEVERITY[c.severity] || PRB_CONFLICT_SEVERITY.info;
      return `<div class="prb-conflict-card" style="border-left-color:${sev.color}">
        <div class="prb-conflict-head">
          <span class="u-1444c6ea">${sev.icon}</span>
          <span class="prb-conflict-type" style="background:${sev.color}22;color:${sev.color}">${sev.label}</span>
          <span style="font-size:11px;font-weight:700;color:var(--text-0)">${c.type.charAt(0).toUpperCase()+c.type.slice(1)}</span>
        </div>
        <div class="prb-conflict-desc">${escHtml(c.description)}</div>
        <div class="prb-conflict-policies">
          <div class="prb-conflict-pol">
            <span style="font-size:10px;color:var(--text-3)">Rule A: </span>
            <strong>${escHtml(c.policy_a?.name||'')}</strong>
            ${c.policy_a?.action ? `<span class="prb-action-chip" style="background:${PRB_ACTION_COLORS[c.policy_a.action]?.bg};color:${PRB_ACTION_COLORS[c.policy_a.action]?.text};margin-left:4px">${PRB_ACTION_COLORS[c.policy_a.action]?.icon} ${c.policy_a.action}</span>` : ''}
            <span style="font-size:9px;color:var(--text-3);margin-left:4px">P:${c.policy_a?.priority||'?'}</span>
          </div>
          <div class="prb-conflict-pol">
            <span style="font-size:10px;color:var(--text-3)">Rule B: </span>
            <strong>${escHtml(c.policy_b?.name||'')}</strong>
            ${c.policy_b?.action ? `<span class="prb-action-chip" style="background:${PRB_ACTION_COLORS[c.policy_b.action]?.bg};color:${PRB_ACTION_COLORS[c.policy_b.action]?.text};margin-left:4px">${PRB_ACTION_COLORS[c.policy_b.action]?.icon} ${c.policy_b.action}</span>` : ''}
            <span style="font-size:9px;color:var(--text-3);margin-left:4px">P:${c.policy_b?.priority||'?'}</span>
          </div>
          ${c.winner ? `<div class="prb-conflict-pol" style="border-color:var(--success)"><span style="font-size:10px;color:var(--success)">Winner: ${escHtml(c.winner.name)}</span></div>` : ''}
          ${c.policy_a ? `<button data-policy-id="${escHtml(c.policy_a?.id||'')}" data-act-click="prbEditPolicy($data.policyId)" style="font-size:10px;padding:2px 8px;border-radius:4px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-2);cursor:pointer">✏️ Edit A</button>` : ''}
          ${c.policy_b ? `<button data-policy-id="${escHtml(c.policy_b?.id||'')}" data-act-click="prbEditPolicy($data.policyId)" style="font-size:10px;padding:2px 8px;border-radius:4px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-2);cursor:pointer">✏️ Edit B</button>` : ''}
        </div>
      </div>`;
    }).join('')}
  </div>`;
}


// ── Servers tab ────────────────────────────────────────────────────
function prbRenderServersTab(container) {
  const builtins = _prbServers.filter(s => s.server_type === 'builtin' || s.server_type === 'connector');
  const custom   = _prbServers.filter(s => s.server_type === 'external');

  container.innerHTML = `
  <div class="u-287f770e">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
      <h3 style="margin:0;font-size:14px;font-weight:700;color:var(--text-0)">🖥️ MCP Servers</h3>
      <button data-act-click="prbRegisterServer()" style="padding:4px 12px;border-radius:6px;font-size:11px;background:var(--accent);border:none;color:var(--on-accent);cursor:pointer;margin-left:auto">+ Register Server</button>
    </div>
    <div class="prb-servers">
      ${_prbServers.map(s => {
        let tools = [];
        try { tools = JSON.parse(s.tools_schema||'[]'); } catch(e) {}
        const isActive = s.status === 'active';
        return `<div class="prb-server-card" style="border-color:${isActive?'var(--border)':'rgba(232,82,82,.3)'}">
          <div class="prb-server-head">
            <div class="prb-server-status" style="background:${isActive?'#3dba7a':'#e85252'}"></div>
            <div class="prb-server-name">${escHtml(s.name)}</div>
            <span class="prb-server-type">${s.server_type}</span>
          </div>
          <div class="prb-server-desc">${escHtml(s.description||'')}</div>
          <div class="prb-server-limits">
            ⏱️ ${s.rate_limit_rpm}/min &nbsp; 📊 ${s.rate_limit_day}/day
          </div>
          ${tools.length ? `<div class="prb-server-tools">
            Tools: ${tools.slice(0,4).map(t=>`<span class="prb-code">${escHtml(t.name||t)}</span>`).join(' ')}${tools.length>4?` +${tools.length-4}`:''}</div>` : ''}
          <div class="prb-server-actions">
            ${isActive
              ? `<button data-server-id="${escHtml(s.server_id)}" data-disable="true" data-act-click="prbToggleServer($data.serverId,true)" style="font-size:10px;padding:3px 8px;border-radius:5px;background:rgba(232,82,82,.12);border:1px solid rgba(232,82,82,.3);color:#e85252;cursor:pointer">🔴 Disable</button>`
              : `<button data-server-id="${escHtml(s.server_id)}" data-disable="false" data-act-click="prbToggleServer($data.serverId,false)" style="font-size:10px;padding:3px 8px;border-radius:5px;background:rgba(61,186,122,.12);border:1px solid rgba(61,186,122,.3);color:#3dba7a;cursor:pointer">🟢 Enable</button>`}
            <button data-server-id="${escHtml(s.server_id)}" data-server-name="${escHtml(s.name)}" data-act-click="prbAddPolicyForServer($data.serverId,$data.serverName)" style="font-size:10px;padding:3px 8px;border-radius:5px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-2);cursor:pointer">+ Add Rule</button>
          </div>
        </div>`;
      }).join('')}
    </div>
  </div>`;
}


// ── CRUD helpers ───────────────────────────────────────────────────
function prbSelectPolicy(polId) {
  _prbSelected = polId;
  prbRenderList();
  if (_prbTab === 'rules') {
    // Highlight row only
    document.querySelectorAll('.prb-rules-table tr').forEach(tr => tr.classList.remove('selected'));
  }
}

function prbEditPolicy(polId) {
  _prbSelected = polId;
  prbSetTab('builder');
}

async function prbToggleEnabled(polId, currentEnabled) {
  const r = await fetch(`/api/mcp-gateway/policies/${encodeURIComponent(polId)}/toggle`, {method:'PATCH'}).catch(()=>null);
  const d = r ? await r.json() : {};
  toast(d.ok ? `📋 Rule ${d.enabled?'enabled':'disabled'}` : '⚠️ Failed');
  await prbRefresh();
}

async function prbDeletePolicy(polId, name) {
  const ok = await gmDanger('Delete Rule', `Delete policy rule "${name}"? This cannot be undone.`);
  if (!ok) return;
  const r = await fetch(`/api/mcp-gateway/policies/${encodeURIComponent(polId)}`, {method:'DELETE'}).catch(()=>null);
  const d = r ? await r.json() : {};
  toast(d.ok ? '🗑 Rule deleted' : '⚠️ ' + (d.error||'Failed'));
  if (d.ok) { if(_prbSelected===polId) _prbSelected=null; await prbRefresh(); }
}

function prbToggleSelect(polId, checked) {
  if (checked) _prbSelIds.add(polId);
  else         _prbSelIds.delete(polId);
  prbRenderList();
}

function prbSelectAll(checked) {
  const pols = prbGetFilteredPolicies();
  pols.forEach(p => { if(checked) _prbSelIds.add(p.policy_id); else _prbSelIds.delete(p.policy_id); });
  prbRenderList();
  prbRenderTab();
}

async function prbBulkAction(action) {
  if (_prbSelIds.size === 0) { toast('⚠️ Select rules first (use checkboxes)'); return; }
  const count = _prbSelIds.size;
  if (action === 'delete') {
    const ok = await gmDanger('Bulk Delete', `Delete ${count} selected rule${count>1?'s':''}? This cannot be undone.`);
    if (!ok) return;
  }
  const r = await fetch('/api/mcp-gateway/policies/bulk', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ action, policy_ids: [..._prbSelIds] })
  }).catch(()=>null);
  const d = r ? await r.json() : {};
  toast(d.ok ? `${action==='enable'?'✓':action==='disable'?'○':'🗑'} ${d.affected} rule${d.affected!==1?'s':''} ${action}d` : '⚠️ '+(d.error||'Failed'));
  _prbSelIds.clear();
  if (d.ok) await prbRefresh();
}

function prbNewRule() {
  _prbSelected = null;
  prbSetTab('builder');
}

async function prbToggleServer(serverId, disable) {
  const ok = await gmDanger(`${disable?'Disable':'Enable'} Server`,
    `${disable?'Disable':'Enable'} server "${serverId}"? ${disable?'All tool calls to this server will be blocked.':''}`);
  if (!ok) return;
  const r = await fetch(`/api/mcp-gateway/servers/${encodeURIComponent(serverId)}/toggle`, {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({disable})
  }).catch(()=>null);
  const d = r ? await r.json() : {};
  toast(d.ok ? `${disable?'🔴 Disabled':'🟢 Enabled'}: ${serverId}` : '⚠️ '+(d.error||'Failed'));
  if (d.ok) await prbRefresh();
}

async function prbRegisterServer() {
  const name     = await gmPrompt('Register MCP Server', 'Server name:');
  if (!name?.trim()) return;
  const endpoint = await gmPrompt('Endpoint URL:', 'https://my-mcp-server.example.com') || '';
  const desc     = await gmPrompt('Description:', '') || '';
  const r = await fetch('/api/mcp-gateway/servers', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name, endpoint, description:desc, server_type:'external'})
  }).catch(()=>null);
  const d = r ? await r.json() : {};
  toast(d.ok ? `🖥️ Registered: ${d.server_id}` : '⚠️ '+(d.error||'Failed'));
  if (d.ok) await prbRefresh();
}

function prbAddPolicyForServer(serverId, serverName) {
  _prbSelected = null;
  prbSetTab('builder');
  setTimeout(() => {
    const svEl = document.getElementById('prb-f-server');
    if (svEl) {
      [...svEl.options].forEach(o => { o.selected = o.value === serverId; });
    }
    const nameEl = document.getElementById('prb-f-name');
    if (nameEl && !nameEl.value) nameEl.value = `Rule for ${serverName}`;
    prbUpdatePreview();
  }, 100);
}


// ── Old compat aliases (used by tests and other code) ────────────
async function renderMCPGatewayLegacy() { return renderMCPGateway(); }
async function mcgTestCall() {
  const tool = await gmPrompt('Test MCP Gateway Call', 'Tool name (e.g. fs.list, search.web):') || '';
  if (!tool.trim()) return;
  const argsStr = await gmPrompt('Args (JSON):', '{"path":"./"}') || '{}';
  let args = {};
  try { args = JSON.parse(argsStr); } catch(e) { toast('⚠️ Invalid JSON args'); return; }
  toast('📞 Calling via MCP Gateway…');
  const r = await fetch('/api/mcp-gateway/call', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({server_id:'srv_filesystem', tool, args, agent_id:'user'})
  }).catch(()=>null);
  if (!r) { toast('⚠️ Call failed'); return; }
  const d = await r.json();
  await gmAlert(`🔀 Gateway Result: ${tool}`,
    `Call ID: ${d.call_id||'?'}\nPolicy: ${d.policy_decision||'?'}\nDuration: ${d.gateway_duration_ms||0}ms\nStatus: ${d.ok?'✅ OK':'❌ Failed'}\n\nResult:\n${JSON.stringify(d.result||d.error||d,null,2).slice(0,600)}`);
  await prbRefresh();
}
async function mcgToggleServer(sId,dis) { await prbToggleServer(sId,dis); }
async function mcgViewAgentCard(id, isAgent=false) {
  if (!isAgent) return;
  const d = await fetch(`/api/mcp-gateway/agent-card/${encodeURIComponent(id)}`).then(r=>r.ok?r.json():{}).catch(()=>({}));
  const card = d.agent_card||{};
  await gmAlert(`🪪 A2A Agent Card: ${id}`,
    `Agent ID: ${card.agent_id}\nName: ${card.name}\nRole: ${card.role}\nAuthority: ${card.authority_level}\nPublic Key: ${(card.public_key||'not provisioned').slice(0,40)}…\n\nCapabilities:\n${(card.capabilities||[]).slice(0,10).map(c=>`  • ${c}`).join('\n')}\n\nProtocols: ${(card.protocols||[]).join(', ')}\nEndpoint: ${card.endpoint}\nCard Hash: ${card.card_hash||''}\nA2A v1.0 ✅`);
}
async function mcgRegisterServer() { await prbRegisterServer(); }
async function mcgCreatePolicy()   { prbNewRule(); }
async function mcgTogglePolicy(id) { await prbToggleEnabled(id, true); }
async function mcgDeletePolicy(id) {
  const pol = _prbPolicies.find(p=>p.policy_id===id);
  await prbDeletePolicy(id, pol?.name||id);
}



// ══════════════════════════════════════════════════════════════════
//  SPRINT C — ENTERPRISE CONNECTORS
// ══════════════════════════════════════════════════════════════════

const CONNECTOR_CATEGORY_ICONS = {
  communication:'💬', project_mgmt:'🎫', productivity:'📊',
};
window.renderMCPGateway = renderMCPGateway;

// Every data-act-click handler must be reachable from window: the delegated
// dispatcher resolves names by plain property lookup and silently warns
// "[delegate] unknown function" otherwise. Only renderMCPGateway was exported,
// so 17 of this pane's 21 handlers were dead -- all five tabs, the simulator,
// the rule builder, delete, bulk actions and the server kill-switch. The pane
// rendered correctly and did nothing.
window.mcgTestCall = mcgTestCall;
window.prbAddPolicyForServer = prbAddPolicyForServer;
window.prbBulkAction = prbBulkAction;
window.prbClearEdit = prbClearEdit;
window.prbDeletePolicy = prbDeletePolicy;
window.prbEditPolicy = prbEditPolicy;
window.prbNewRule = prbNewRule;
window.prbRefresh = prbRefresh;
window.prbRegisterServer = prbRegisterServer;
window.prbRunSimulation = prbRunSimulation;
window.prbSelectAction = prbSelectAction;
window.prbSelectAll = prbSelectAll;
window.prbSetTab = prbSetTab;
window.prbSimulateFromRow = prbSimulateFromRow;
window.prbSubmitRule = prbSubmitRule;
window.prbToggleSelect = prbToggleSelect;
window.prbToggleServer = prbToggleServer;

// ── Delegated-handler exports ─────────────────────────────────────────────
// These are referenced by data-act-* attributes in this pane. The
// delegated dispatcher resolves handler names by property lookup on
// window, and this file is IIFE-wrapped, so without these assignments
// every one of them silently no-ops.
window.prbFilterChange = prbFilterChange;
window.prbSearchChange = prbSearchChange;
window.prbToggleDaysCondition = prbToggleDaysCondition;
window.prbToggleTimeCondition = prbToggleTimeCondition;
window.prbUpdatePreview = prbUpdatePreview;
})(S, nav, toast, escHtml, fetch, document);

function prbQuickSimFromData(dataStr) {
  const [a, s, t] = dataStr.split('|');
  prbQuickSim(a, s, t);
}
function prbApplyTemplateById(id) {
  const tpl = _prbTemplates.find(t => t.id === id || t.name === id);
  if (tpl) prbApplyTemplate(tpl);
}
window.prbQuickSimFromData = prbQuickSimFromData;
window.prbApplyTemplateById = prbApplyTemplateById;

