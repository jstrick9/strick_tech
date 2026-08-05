// Compliance Report — Extracted from 06-sprint-features.js
(function(S, nav, toast, escHtml, fetch, document) {
// NOTE: this state/constants block was originally (incorrectly) left in the
// separate 45-leaderboard.js IIFE, which has its own private closure scope
// and cannot be seen from here. Moved here since it belongs to this module.
let _crcTab          = 'dashboard';   // dashboard | generate | history | audit
let _crcReports      = [];
let _crcSummary      = null;
let _crcAuditEntries = [];
let _crcAuditTotal   = 0;
let _crcAuditFilter  = { risk:'', outcome:'', agent:'' };
let _crcGenerating   = false;
let _crcSelectedFw   = 'General';
let _crcSelectedFmt  = 'pdf';
let _crcScope        = {
  audit_chain: true, hitl: true, policies: true,
  agent_identity: true, connectors: true, cost: true, supervisor: true,
};

// ── Constants ───────────────────────────────────────────────────────
const CRC_FRAMEWORKS = [
  { id:'General',  name:'General Audit',  icon:'📋', desc:'Comprehensive governance review' },
  { id:'SOC2',     name:'SOC 2 Type II',  icon:'🛡️',  desc:'Security, Availability, Processing Integrity' },
  { id:'GDPR',     name:'GDPR',           icon:'🇪🇺', desc:'Art. 30 records, Art. 32 security measures' },
  { id:'HIPAA',    name:'HIPAA',          icon:'🏥', desc:'§164.312 technical safeguards & audit controls' },
  { id:'FINRA',    name:'FINRA',          icon:'📈', desc:'Rule 4370, Rule 17a-4 record retention' },
  { id:'ISO27001', name:'ISO/IEC 27001',  icon:'🔏', desc:'Annex A technology & organizational controls' },
];
const CRC_SECTIONS = [
  { key:'audit_chain',    label:'Audit Chain',      icon:'🔗' },
  { key:'hitl',           label:'HITL Approvals',   icon:'🛂' },
  { key:'policies',       label:'Policy Enforcement',icon:'📋' },
  { key:'agent_identity', label:'Agent Identity',   icon:'🪪' },
  { key:'connectors',     label:'Connector Calls',  icon:'🔌' },
  { key:'cost',           label:'Cost & Tokens',    icon:'💰' },
  { key:'supervisor',     label:'Supervisor Runs',  icon:'🧠' },
];
const CRC_RISK_COLORS = {
  low:'var(--success)', medium:'var(--warning)', high:'var(--danger)', critical:'#e85252'
};
const CRC_OUTCOME_ICONS = {
  success:'✅', failure:'❌', blocked:'🚫', pending:'⏳'
};

async function renderAuditLog() {
  const pane = document.getElementById('pane-audit-log');
  if (!pane) return;

  pane.innerHTML = `
  

  <div class="crc-root">
    <!-- Sidebar -->
    <div class="crc-sidebar">
      <div class="crc-sidebar-title">Compliance Center</div>
      <div class="crc-nav-item active" id="crc-nav-dashboard" data-act-click="crcSetTab('dashboard')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
        <span class="crc-nav-icon">📊</span> Dashboard
      </div>
      <div class="crc-nav-item" id="crc-nav-generate" data-act-click="crcSetTab('generate')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
        <span class="crc-nav-icon">📄</span> Generate Report
      </div>
      <div class="crc-nav-item" id="crc-nav-history" data-act-click="crcSetTab('history')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
        <span class="crc-nav-icon">🗂️</span> Report History
      </div>
      <div class="crc-sidebar-divider"></div>
      <div class="crc-nav-item" id="crc-nav-audit" data-act-click="crcSetTab('audit')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
        <span class="crc-nav-icon">🔏</span> Audit Chain
      </div>
      <div class="crc-sidebar-divider"></div>
      <div style="padding:8px;font-size:10px;color:var(--text-3)">
        Quick exports:
      </div>
      <a href="/api/audit-log/export/json?limit=5000" download style="text-decoration:none">
        <div class="crc-nav-item"><span class="crc-nav-icon">⬇</span> Export JSON</div>
      </a>
      <a href="/api/audit-log/export/csv?limit=5000" download style="text-decoration:none">
        <div class="crc-nav-item"><span class="crc-nav-icon">⬇</span> Export CSV</div>
      </a>
    </div>

    <!-- Main -->
    <div class="crc-main">
      <div class="crc-header">
        <span class="crc-header-title" id="crc-header-title">🔏 Compliance & Audit Center</span>
        <button class="crc-action-btn" data-act-click="crcRefresh()" title="Refresh">↺ Refresh</button>
      </div>
      <div class="crc-content" id="crc-content">
        <div style="padding:40px;text-align:center;color:var(--text-3)">Loading…</div>
      </div>
    </div>
  </div>`;

  await crcRefresh();
}


// ── Data loading ─────────────────────────────────────────────────────
async function crcRefresh() {
  const [summaryR, reportsR] = await Promise.all([
    fetch('/api/compliance/summary').then(r=>r.ok?r.json():{}).catch(()=>({})),
    fetch('/api/compliance/reports?limit=20').then(r=>r.ok?r.json():{reports:[]}).catch(()=>({reports:[]})),
  ]);
  _crcSummary = summaryR;
  _crcReports = reportsR.reports || [];
  crcRenderTab();
}


// ── Tab system ───────────────────────────────────────────────────────
function crcSetTab(tab) {
  _crcTab = tab;
  document.querySelectorAll('.crc-nav-item').forEach(el => {
    el.classList.toggle('active', el.id === 'crc-nav-' + tab);
  });
  const titles = {
    dashboard: '📊 Compliance Dashboard',
    generate:  '📄 Generate Compliance Report',
    history:   '🗂️ Report History',
    audit:     '🔏 Immutable Audit Chain',
  };
  const titleEl = document.getElementById('crc-header-title');
  if (titleEl) titleEl.textContent = titles[tab] || 'Compliance Center';
  crcRenderTab();
}

function crcRenderTab() {
  const content = document.getElementById('crc-content');
  if (!content) return;
  if (_crcTab === 'dashboard') crcRenderDashboard(content);
  if (_crcTab === 'generate')  crcRenderGenerator(content);
  if (_crcTab === 'history')   crcRenderHistory(content);
  if (_crcTab === 'audit')     crcRenderAuditChain(content);
}


// ── Dashboard tab ─────────────────────────────────────────────────
function crcRenderDashboard(container) {
  const s = _crcSummary || {};
  const chainOk = s.chain_integrity !== false;

  const stats = [
    { label:'Audit Entries',     val: (s.chain_entries||0).toLocaleString(),      color:'var(--accent)' },
    { label:'High Risk Actions', val: (s.high_risk_actions||0).toLocaleString(),  color: s.high_risk_actions > 0 ? 'var(--danger)' : 'var(--success)' },
    { label:'Failed Actions',    val: (s.failed_actions||0).toLocaleString(),      color: s.failed_actions > 0 ? 'var(--danger)' : 'var(--success)' },
    { label:'HITL Decisions',    val: (s.hitl_total||0).toLocaleString(),          color:'var(--warning)' },
    { label:'HITL Pending',      val: (s.hitl_pending||0).toLocaleString(),        color: s.hitl_pending > 0 ? 'var(--warning)' : 'var(--success)' },
    { label:'Calls Blocked',     val: (s.policy_blocked||0).toLocaleString(),      color: s.policy_blocked > 0 ? 'var(--warning)' : 'var(--success)' },
    { label:'Block Rate',        val: (s.block_rate_pct||0) + '%',                 color:'var(--warning)' },
    { label:'Active Agents',     val: (s.active_agents||0).toLocaleString(),       color:'var(--accent)' },
    { label:'Total Cost',        val: '$' + (s.total_cost_usd||0).toFixed(4),      color:'#9d74f5' },
    { label:'Reports Generated', val: (s.reports_generated||0).toLocaleString(),   color:'var(--accent)' },
  ];

  container.innerHTML = `
    <!-- Chain integrity banner -->
    <div class="crc-chain-banner" style="background:${chainOk?'rgba(61,186,122,.1)':'rgba(232,82,82,.1)'};border:1px solid ${chainOk?'var(--success)':'var(--danger)'}">
      <span class="crc-chain-icon">${chainOk?'🔗':'⚠️'}</span>
      <div>
        <div class="crc-chain-status" style="color:${chainOk?'var(--success)':'var(--danger)'}">${chainOk?'Chain Integrity Verified ✓':'Chain Integrity Issue Detected ⚠️'}</div>
        <div class="crc-chain-detail" style="color:var(--text-3)">${(s.chain_entries||0).toLocaleString()} entries verified · Last report: ${s.last_report_at ? new Date(s.last_report_at).toLocaleDateString() + ' (' + s.last_report_framework + ')' : 'None yet'}</div>
      </div>
      <button class="crc-action-btn" data-act-click="crcVerifyChain()" style="margin-left:auto">🔍 Verify Now</button>
    </div>

    <!-- Stats grid -->
    <div class="crc-summary-grid">
      ${stats.map(st => `
        <div class="crc-summary-card">
          <div class="crc-summary-val" style="color:${st.color}">${st.val}</div>
          <div class="crc-summary-label">${st.label}</div>
        </div>`).join('')}
    </div>

    <!-- Quick actions -->
    <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px">Quick Actions</div>
    <div class="crc-quick-actions">
      <button class="crc-action-btn primary" data-act-click="crcSetTab('generate')">📄 Generate PDF Report</button>
      <button class="crc-action-btn" data-act-click="crcQuickReport('pdf','SOC2')">🛡️ SOC2 Report</button>
      <button class="crc-action-btn" data-act-click="crcQuickReport('pdf','GDPR')">🇪🇺 GDPR Report</button>
      <button class="crc-action-btn" data-act-click="crcQuickReport('pdf','HIPAA')">🏥 HIPAA Report</button>
      <button class="crc-action-btn" data-act-click="crcQuickReport('json','General')">⬇ JSON Export</button>
      <button class="crc-action-btn" data-act-click="crcQuickReport('csv','General')">⬇ CSV Export</button>
      <button class="crc-action-btn" data-act-click="crcSetTab('audit')">🔏 View Audit Chain</button>
    </div>

    <!-- Framework cards -->
    <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px;margin-top:6px">Supported Compliance Frameworks</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:8px;margin-bottom:18px">
      ${CRC_FRAMEWORKS.map(fw => `
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:9px;padding:12px;cursor:pointer;transition:all .12s" data-act-click="crcSetFwAndGenerate(${JSON.stringify(fw.id)})" data-hover="bc:var(--accent)" data-hover-out="bc:var(--border)" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
          <div style="font-size:18px;margin-bottom:5px">${fw.icon}</div>
          <div style="font-size:12px;font-weight:700;color:var(--text-0);margin-bottom:2px">${fw.name}</div>
          <div style="font-size:10px;color:var(--text-3)">${fw.desc}</div>
        </div>`).join('')}
    </div>

    <!-- Recent reports -->
    ${_crcReports.length ? `
    <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px">Recent Reports</div>
    ${_crcReports.slice(0,3).map(r => crcReportCard(r)).join('')}
    <button class="crc-action-btn" data-act-click="crcSetTab('history')" style="margin-top:4px">View All Reports →</button>
    ` : ''}
  `;
}


// ── Report generator tab ──────────────────────────────────────────
function crcRenderGenerator(container) {
  const today = new Date().toISOString().slice(0,10);
  const thirtyDaysAgo = new Date(Date.now() - 30*24*3600*1000).toISOString().slice(0,10);

  container.innerHTML = `
    <div class="crc-gen-layout">
      <!-- Left: Framework + Format -->
      <div>
        <!-- Framework -->
        <div class="crc-gen-panel" style="margin-bottom:12px">
          <div class="crc-panel-title">⚖️ Compliance Framework</div>
          <div class="crc-fw-grid">
            ${CRC_FRAMEWORKS.map(fw => `
              <div class="crc-fw-card ${_crcSelectedFw===fw.id?'selected':''}" id="crc-fw-${fw.id}" data-act-click="crcSelectFw(${JSON.stringify(fw.id)})" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
                <div class="crc-fw-icon">${fw.icon}</div>
                <div class="crc-fw-name">${fw.name}</div>
                <div class="crc-fw-desc">${fw.desc}</div>
              </div>`).join('')}
          </div>
        </div>

        <!-- Format -->
        <div class="crc-gen-panel" style="margin-bottom:12px">
          <div class="crc-panel-title">📁 Output Format</div>
          <div class="crc-fmt-row">
            ${[['pdf','📄 PDF','Formatted, signable'],['json','{ } JSON','Machine-readable'],['csv','📊 CSV','Spreadsheet']].map(([id,label,desc]) => `
              <div class="crc-fmt-btn ${_crcSelectedFmt===id?'selected':''}" id="crc-fmt-${id}" data-act-click="crcSelectFmt(${JSON.stringify(id)})" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
                <div>${label}</div>
                <div style="font-size:9px;color:var(--text-3);margin-top:2px">${desc}</div>
              </div>`).join('')}
          </div>
        </div>

        <!-- Date range -->
        <div class="crc-gen-panel">
          <div class="crc-panel-title">📅 Date Range</div>
          <div class="crc-form-label" style="margin-bottom:5px">From</div>
          <div class="crc-date-row">
            <input class="crc-date-input" type="date" id="crc-date-from" value="${thirtyDaysAgo}">
            <input class="crc-date-input" type="date" id="crc-date-to"   value="${today}">
          </div>
          <div style="font-size:10px;color:var(--text-3);margin-top:5px">Leave both blank for all-time report</div>
        </div>
      </div>

      <!-- Right: Scope + Title + Generate -->
      <div>
        <!-- Title -->
        <div class="crc-gen-panel" style="margin-bottom:12px">
          <div class="crc-panel-title">✏️ Report Title</div>
          <input class="crc-title-input" id="crc-report-title" value="Compliance Audit — ${new Date().toLocaleDateString('en-US',{year:'numeric',month:'long'})}" placeholder="Report title…">
        </div>

        <!-- Scope -->
        <div class="crc-gen-panel" style="margin-bottom:12px">
          <div class="crc-panel-title">🔍 Included Sections</div>
          <div class="crc-scope-list" id="crc-scope-list">
            ${CRC_SECTIONS.map(s => `
              <div class="crc-scope-item" data-act-click="crcToggleScope(${JSON.stringify(s.key)})" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
                <input type="checkbox" class="crc-scope-check" id="crc-scope-${s.key}" ${_crcScope[s.key]?'checked':''} data-act-click="crcToggleScope(${JSON.stringify(s.key)})" data-stop="1">
                <span class="crc-scope-icon">${s.icon}</span>
                <span class="crc-scope-label">${s.label}</span>
              </div>`).join('')}
          </div>
          <div style="display:flex;gap:6px;margin-top:8px">
            <button data-act-click="crcSelectAllScope(true)" style="font-size:10px;padding:3px 8px;border-radius:4px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-2);cursor:pointer">Select All</button>
            <button data-act-click="crcSelectAllScope(false)" style="font-size:10px;padding:3px 8px;border-radius:4px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-2);cursor:pointer">Clear All</button>
          </div>
        </div>

        <!-- Preview -->
        <div class="crc-gen-panel" style="margin-bottom:12px">
          <div class="crc-panel-title">👁️ Report Preview</div>
          <div class="crc-preview-box" id="crc-preview-box">${crcBuildPreview()}</div>
        </div>

        <!-- Generate button -->
        <button class="crc-gen-btn" id="crc-gen-btn" data-act-click="crcGenerate()" ${_crcGenerating?'disabled':''}>
          ${_crcGenerating ? '<div class="crc-spinner"></div> Generating Report…' : '📄 Generate Compliance Report'}
        </button>
        ${_crcGenerating ? `<div class="crc-generating"><div class="crc-spinner"></div><span style="font-size:12px;color:var(--accent)">Building report — collecting audit chain, HITL records, policy data…</span></div>` : ''}
      </div>
    </div>
  `;
}

function crcSelectFw(fw) {
  _crcSelectedFw = fw;
  document.querySelectorAll('.crc-fw-card').forEach(el => el.classList.remove('selected'));
  document.getElementById('crc-fw-' + fw)?.classList.add('selected');
  crcUpdatePreview();
}

function crcSelectFmt(fmt) {
  _crcSelectedFmt = fmt;
  document.querySelectorAll('.crc-fmt-btn').forEach(el => el.classList.remove('selected'));
  document.getElementById('crc-fmt-' + fmt)?.classList.add('selected');
  crcUpdatePreview();
}

function crcToggleScope(key) {
  _crcScope[key] = !_crcScope[key];
  const cb = document.getElementById('crc-scope-' + key);
  if (cb) cb.checked = _crcScope[key];
  crcUpdatePreview();
}

function crcSelectAllScope(val) {
  CRC_SECTIONS.forEach(s => {
    _crcScope[s.key] = val;
    const cb = document.getElementById('crc-scope-' + s.key);
    if (cb) cb.checked = val;
  });
  crcUpdatePreview();
}

function crcUpdatePreview() {
  const box = document.getElementById('crc-preview-box');
  if (box) box.innerHTML = crcBuildPreview();
}

function crcBuildPreview() {
  const fw   = CRC_FRAMEWORKS.find(f=>f.id===_crcSelectedFw) || CRC_FRAMEWORKS[0];
  const secs = CRC_SECTIONS.filter(s=>_crcScope[s.key]);
  return `<strong>${fw.icon} ${fw.name} — ${_crcSelectedFmt.toUpperCase()}</strong><br>
Sections: ${secs.map(s=>s.icon+' '+s.label).join(', ')}<br>
Format: ${_crcSelectedFmt === 'pdf' ? 'PDF (formatted, printable)' : _crcSelectedFmt === 'json' ? 'JSON (machine-readable full export)' : 'CSV (spreadsheet-compatible)'}<br>
<em style="color:var(--text-3);font-size:10px">${fw.desc}</em>`;
}

async function crcGenerate() {
  if (_crcGenerating) return;
  const title   = document.getElementById('crc-report-title')?.value?.trim() || 'Compliance Report';
  const fromVal = document.getElementById('crc-date-from')?.value || '';
  const toVal   = document.getElementById('crc-date-to')?.value   || '';
  const dateFrom = fromVal ? fromVal + 'T00:00:00Z' : '';
  const dateTo   = toVal   ? toVal   + 'T23:59:59Z' : '';

  _crcGenerating = true;
  crcRenderGenerator(document.getElementById('crc-content'));

  try {
    const resp = await fetch('/api/compliance/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title, framework: _crcSelectedFw, format: _crcSelectedFmt,
        date_from: dateFrom, date_to: dateTo, scope: { ..._crcScope },
      })
    });

    if (!resp.ok) {
      const err = await resp.json().catch(()=>({error:'Unknown error'}));
      showToast('⚠️ Report failed: ' + (err.error||resp.status));
      return;
    }

    // Trigger download
    const blob = await resp.blob();
    const reportId = resp.headers.get('X-Report-Id') || 'report';
    const ext  = _crcSelectedFmt === 'pdf' ? 'pdf' : _crcSelectedFmt === 'json' ? 'json' : 'csv';
    const filename = `compliance_${_crcSelectedFw.toLowerCase()}_${Date.now()}.${ext}`;
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
    showToast(`✅ Report downloaded: ${filename}`);

    // Refresh history
    const histR = await fetch('/api/compliance/reports?limit=20').then(r=>r.ok?r.json():{reports:[]});
    _crcReports = histR.reports || [];
  } catch(e) {
    showToast('⚠️ Error: ' + e.message);
  } finally {
    _crcGenerating = false;
    crcRenderGenerator(document.getElementById('crc-content'));
  }
}

async function crcQuickReport(fmt, fw) {
  _crcSelectedFmt = fmt;
  _crcSelectedFw  = fw;
  _crcGenerating  = true;
  showToast(`📄 Generating ${fw} ${fmt.toUpperCase()} report…`);
  try {
    const resp = await fetch('/api/compliance/generate', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        title: `${fw} Compliance Report — ${new Date().toLocaleDateString()}`,
        framework: fw, format: fmt, scope: { ..._crcScope }
      })
    });
    if (!resp.ok) { showToast('⚠️ Report failed'); return; }
    const blob = await resp.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = `compliance_${fw.toLowerCase()}.${fmt}`; a.click();
    URL.revokeObjectURL(url);
    showToast(`✅ ${fw} report downloaded`);
    const hr = await fetch('/api/compliance/reports?limit=20').then(r=>r.ok?r.json():{reports:[]});
    _crcReports = hr.reports || [];
  } catch(e) { showToast('⚠️ ' + e.message); }
  finally { _crcGenerating = false; }
}

function crcSetFwAndGenerate(fw) {
  _crcSelectedFw = fw;
  crcSetTab('generate');
}


// ── History tab ─────────────────────────────────────────────────────
function crcRenderHistory(container) {
  if (!_crcReports.length) {
    container.innerHTML = `<div style="padding:40px;text-align:center;color:var(--text-3)">
      <div style="font-size:40px;margin-bottom:12px">📄</div>
      <div style="font-size:14px;font-weight:600;color:var(--text-1);margin-bottom:8px">No Reports Generated Yet</div>
      <div style="font-size:12px;line-height:1.6;margin-bottom:20px">Generate your first compliance report from the Generate tab.</div>
      <button class="crc-gen-btn" style="width:auto;padding:10px 24px" data-act-click="crcSetTab('generate')">📄 Generate First Report</button>
    </div>`;
    return;
  }
  container.innerHTML = `
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
      <strong style="font-size:13px;color:var(--text-0)">${_crcReports.length} Reports</strong>
      <button class="crc-action-btn" data-act-click="crcSetTab('generate')" style="margin-left:auto">+ New Report</button>
    </div>
    ${_crcReports.map(r => crcReportCard(r)).join('')}
  `;
}

function crcReportCard(r) {
  const fw  = CRC_FRAMEWORKS.find(f=>f.id===r.framework) || {icon:'📋',name:r.framework};
  const sum = r.summary || {};
  const statusColors = { done:'var(--success)', failed:'var(--danger)', generating:'var(--warning)', pending:'var(--text-3)' };
  const sc  = statusColors[r.status] || 'var(--text-3)';
  const sizeKB = r.file_size_bytes ? (r.file_size_bytes/1024).toFixed(1) + ' KB' : '—';
  return `<div class="crc-report-card">
    <div class="crc-report-icon">${fw.icon}</div>
    <div class="crc-report-body">
      <div class="crc-report-title">${escHtml(r.title||'Compliance Report')}</div>
      <div class="crc-report-meta">
        ${fw.name} · ${r.format?.toUpperCase()} · ${sizeKB} · ${new Date(r.created_at).toLocaleString()}
        ${r.date_from ? ` · ${r.date_from.slice(0,10)} → ${(r.date_to||'now').slice(0,10)}` : ''}
      </div>
      ${Object.keys(sum).length ? `
      <div class="crc-report-summary">
        ${sum.audit_total != null ? `<span class="crc-report-chip">📋 ${(sum.audit_total||0).toLocaleString()} entries</span>` : ''}
        ${sum.high_risk_count > 0 ? `<span class="crc-report-chip" style="color:var(--danger)">⚠️ ${sum.high_risk_count} high-risk</span>` : ''}
        ${sum.hitl_total > 0 ? `<span class="crc-report-chip">🛂 ${sum.hitl_total} HITL</span>` : ''}
        ${sum.policy_blocked > 0 ? `<span class="crc-report-chip">🚫 ${sum.policy_blocked} blocked</span>` : ''}
        ${sum.chain_ok === false ? `<span class="crc-report-chip" style="color:var(--danger)">⚠️ Chain issue</span>` : `<span class="crc-report-chip" style="color:var(--success)">🔗 Chain OK</span>`}
      </div>` : ''}
    </div>
    <div class="crc-report-actions">
      <span class="crc-status-badge" style="background:${sc}22;color:${sc}">${r.status}</span>
      ${r.status==='done' ? `<button class="crc-rep-btn" data-act-click="crcRegenReport(${JSON.stringify(r)})">↺ Re-run</button>` : ''}
      <button class="crc-rep-btn" style="color:var(--danger)" data-act-click="crcDeleteReport(${JSON.stringify(r.report_id)})">🗑</button>
    </div>
  </div>`;
}

async function crcRegenReport(r) {
  _crcSelectedFw  = r.framework || 'General';
  _crcSelectedFmt = r.format    || 'pdf';
  try {
    _crcScope = JSON.parse(r.scope || '{}');
  } catch(e) {}
  crcSetTab('generate');
  document.getElementById('crc-report-title').value = r.title || 'Compliance Report';
}

async function crcDeleteReport(reportId) {
  const ok = await gmDanger('Delete Report', `Delete report ${reportId}?`);
  if (!ok) return;
  await fetch(`/api/compliance/reports/${encodeURIComponent(reportId)}`, {method:'DELETE'});
  const hr = await fetch('/api/compliance/reports?limit=20').then(r=>r.ok?r.json():{reports:[]});
  _crcReports = hr.reports || [];
  crcRenderHistory(document.getElementById('crc-content'));
  showToast('🗑 Report deleted');
}


// ── Audit chain tab ──────────────────────────────────────────────────
async function crcRenderAuditChain(container) {
  container.innerHTML = `<div style="padding:20px;text-align:center;color:var(--text-3)">Loading audit chain…</div>`;

  let url = '/api/audit-log?limit=100';
  if (_crcAuditFilter.risk)    url += `&risk_level=${encodeURIComponent(_crcAuditFilter.risk)}`;
  if (_crcAuditFilter.outcome) url += `&outcome=${encodeURIComponent(_crcAuditFilter.outcome)}`;
  if (_crcAuditFilter.agent)   url += `&agent_id=${encodeURIComponent(_crcAuditFilter.agent)}`;

  const [entriesR, statsR, verifyR] = await Promise.all([
    fetch(url).then(r=>r.ok?r.json():{entries:[],total:0}).catch(()=>({entries:[],total:0})),
    fetch('/api/audit-log/stats').then(r=>r.ok?r.json():{}).catch(()=>({})),
    fetch('/api/audit-log/verify').then(r=>r.ok?r.json():{ok:true,verified:0}).catch(()=>({ok:true})),
  ]);

  _crcAuditEntries = entriesR.entries || [];
  _crcAuditTotal   = entriesR.total   || 0;

  const chainOk = verifyR.ok !== false;
  const chainTip = (statsR.chain_tip||'').slice(0,32) + '…';

  container.innerHTML = `
    <!-- Chain status -->
    <div style="background:${chainOk?'rgba(61,186,122,.1)':'rgba(232,82,82,.1)'};border:1px solid ${chainOk?'var(--success)':'var(--danger)'};border-radius:10px;padding:12px 14px;margin-bottom:14px;display:flex;align-items:center;gap:10px">
      <span style="font-size:20px">${chainOk?'🔗':'⚠️'}</span>
      <div>
        <div style="font-weight:700;font-size:13px;color:${chainOk?'var(--success)':'var(--danger)'}">${verifyR.message||'Chain status unknown'}</div>
        <div style="font-size:10px;color:var(--text-3)">Entries verified: ${(verifyR.verified||0).toLocaleString()} · Chain tip: <code style="font-size:9px">${chainTip}</code></div>
      </div>
      <div style="display:flex;gap:6px;margin-left:auto">
        <button class="crc-action-btn" data-act-click="crcVerifyChain()">🔍 Verify</button>
        <a href="/api/audit-log/export/json?limit=5000" download class="crc-action-btn" style="text-decoration:none">⬇ JSON</a>
        <a href="/api/audit-log/export/csv?limit=5000" download class="crc-action-btn" style="text-decoration:none">⬇ CSV</a>
        <button class="crc-action-btn primary" data-act-click="crcQuickReport('pdf','General')">📄 PDF Report</button>
      </div>
    </div>

    <!-- Filters -->
    <div class="crc-audit-filters">
      <span style="font-size:11px;font-weight:700;color:var(--text-2)">Filter:</span>
      <select class="crc-filter-sel" id="crc-audit-risk" data-act-change="crcAuditFilterChange()">
        <option value="">All Risk</option>
        <option value="low">Low</option>
        <option value="medium">Medium</option>
        <option value="high">High</option>
        <option value="critical">Critical</option>
      </select>
      <select class="crc-filter-sel" id="crc-audit-outcome" data-act-change="crcAuditFilterChange()">
        <option value="">All Outcomes</option>
        <option value="success">Success</option>
        <option value="failure">Failure</option>
        <option value="blocked">Blocked</option>
      </select>
      <input class="crc-filter-input" id="crc-audit-agent" placeholder="Filter by agent…" data-act-input="crcAuditFilterChange()">
      <span style="margin-left:auto;font-size:11px;color:var(--text-3)">Showing ${_crcAuditEntries.length} of ${_crcAuditTotal.toLocaleString()}</span>
    </div>

    <!-- Table -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;overflow:hidden">
      <table class="crc-audit-table">
        <thead><tr>
          <th>#</th><th>Outcome</th><th>Agent</th><th>Action Type</th>
          <th>Detail</th><th>Risk</th><th>Hash</th><th>Time</th>
        </tr></thead>
        <tbody>
          ${_crcAuditEntries.map(e => `
          <tr data-act-click="crcShowEntry(${JSON.stringify(e.entry_id)})" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
            <td style="font-family:monospace;color:var(--text-3)">${e.seq}</td>
            <td>${CRC_OUTCOME_ICONS[e.outcome]||'❓'} <span style="font-size:10px">${escHtml(e.outcome||'')}</span></td>
            <td style="color:var(--accent)">${escHtml((e.agent_name||e.agent_id||'').slice(0,16))}</td>
            <td style="font-size:10px">${escHtml((e.action_type||'').slice(0,20))}</td>
            <td style="font-size:10px;color:var(--text-2);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml((e.action_detail||'').slice(0,80))}</td>
            <td><span class="crc-risk-chip" style="background:${CRC_RISK_COLORS[e.risk_level]||'var(--text-3)'}22;color:${CRC_RISK_COLORS[e.risk_level]||'var(--text-3)'}">${e.risk_level||''}</span></td>
            <td><span class="crc-hash">${(e.entry_hash||'').slice(0,8)}…</span></td>
            <td style="font-size:10px;color:var(--text-3)">${new Date(e.created_at).toLocaleTimeString()}</td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>

    <!-- Chain explainer -->
    <div class="crc-chain-detail-box">
      <div style="font-size:11px;font-weight:700;color:var(--text-0);margin-bottom:8px">🔗 How the Hash Chain Works</div>
      <div style="font-size:11px;color:var(--text-2);line-height:1.7">
        Each entry stores a <code>prev_hash</code> (SHA-256 of the previous record) and an <code>entry_hash</code> (SHA-256 of all critical fields + prev_hash).
        Modifying any record breaks all subsequent hashes — tampering is immediately detectable.
        Every action generates a signed <strong>cryptographic receipt</strong> tied to the agent's identity keypair.
        Use <strong>Verify</strong> to confirm integrity, or generate a PDF report to include the verification certificate.
      </div>
    </div>
  `;
}

async function crcAuditFilterChange() {
  _crcAuditFilter.risk    = document.getElementById('crc-audit-risk')?.value    || '';
  _crcAuditFilter.outcome = document.getElementById('crc-audit-outcome')?.value || '';
  _crcAuditFilter.agent   = document.getElementById('crc-audit-agent')?.value   || '';
  await crcRenderAuditChain(document.getElementById('crc-content'));
}

async function crcVerifyChain() {
  const r = await fetch('/api/audit-log/verify').catch(()=>null);
  if (!r || !r.ok) { showToast('⚠️ Could not reach audit log'); return; }
  const d = await r.json();
  if (d.ok) {
    showToast(`🔗 Chain OK — ${d.verified} entries verified`);
  } else {
    await gmAlert('⚠️ Chain Integrity Issue',
      `Chain broken at seq=${d.broken_at}.\n\n${d.message}\n\nThis may indicate data tampering. Generate a compliance report immediately and contact your compliance officer.`);
  }
  if (_crcTab === 'audit') await crcRenderAuditChain(document.getElementById('crc-content'));
}

async function crcShowEntry(entryId) {
  const d = await fetch(`/api/audit-log/entry/${encodeURIComponent(entryId)}`).then(r=>r.ok?r.json():null).catch(()=>null);
  if (!d) { showToast('Could not load entry'); return; }
  const e = d.entry || {};
  const r = d.receipt || {};
  const meta = (() => { try { return JSON.stringify(JSON.parse(e.metadata||'{}'),null,2); } catch(x) { return e.metadata||''; } })();
  await gmAlert(`🔏 Audit Entry #${e.seq}`,
    `Agent: ${e.agent_name||e.agent_id}\nAction: ${e.action_type}\nOutcome: ${e.outcome}\nRisk: ${e.risk_level}\nAuthority: ${e.authority}\nTime: ${e.created_at}\n\nDetail:\n${e.action_detail}\n\nReasoning:\n${e.reasoning||'(none)'}\n\nMetadata:\n${meta}\n\nEntry Hash: ${e.entry_hash}\nPrev Hash:  ${e.prev_hash}\n\nReceipt ID: ${r.receipt_id||'none'}\nSignature: ${r.signature||'unsigned'}`);
}


// ── Compat aliases ────────────────────────────────────────────────────
function renderAuditEntryRows(entries) { return ''; } // replaced
async function auditVerifyChain() { await crcVerifyChain(); }
async function auditReload() { if (_crcTab==='audit') await crcRenderAuditChain(document.getElementById('crc-content')); }
async function auditAddTestEntry() {
  await fetch('/api/audit-log/append',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent_id:'user',agent_name:'User',action_type:'test_entry',action_detail:'Manual test audit entry from Compliance Center',authority:'user',risk_level:'low',outcome:'success'})});
  showToast('✅ Test audit entry added');
  if (_crcTab==='audit') await crcRenderAuditChain(document.getElementById('crc-content'));
}
async function auditShowEntry(id) { await crcShowEntry(id); }



// ══════════════════════════════════════════════════════════════════
window.renderAuditLog = renderAuditLog;
})(S, nav, toast, escHtml, fetch, document);
