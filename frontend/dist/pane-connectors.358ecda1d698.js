
;/* 51-connectors.js */
(function(S, nav, toast, escHtml, fetch, document) {
const CONNECTOR_CATEGORY_ICONS = {
communication:'💬', project_mgmt:'🎫', productivity:'📊',
};
async function renderConnectors() {
const pane = document.getElementById('pane-connectors');
if (!pane) return;
const [list, stats] = await Promise.all([
fetch('/api/connectors').then(r=>r.ok?r.json():{connectors:[]}).catch(()=>({connectors:[]})),
fetch('/api/connectors/stats/summary').then(r=>r.ok?r.json():{}).catch(()=>({})),
]);
const statusColor = {active:'var(--success)',unconfigured:'var(--warning)',disabled:'var(--danger)'};
const categories  = [...new Set((list.connectors||[]).map(c=>c.category))].sort();
pane.innerHTML = `
  <div class="u-8316cf9b">
    <div class="section-head u-49f14f8f" >
      <div>
        <h2 class="u-58d955e1">🔌 Enterprise Connectors</h2>
        <p style="margin:0;color:var(--text-2);font-size:13px">Connect agents to the systems businesses already use — Slack, Jira, Google Workspace, Email, GitHub, Salesforce, Notion and custom integrations</p>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn" data-act-click="connectorRegister()">+ Custom Connector</button>
        <button class="btn-sm" data-act-click="renderConnectors()">↻ Refresh</button>
      </div>
    </div>

    <!-- Stats -->
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:18px">
      ${[
        ['🔌','Total',stats.total_connectors||0,'var(--accent)'],
        ['✅','Active',stats.active_connectors||0,'var(--success)'],
        ['📞','Executions',stats.total_executions||0,'var(--text-2)'],
        ['📂','Categories',Object.keys(stats.by_category||{}).length,'#9d74f5'],
      ].map(([icon,label,val,col])=>`
        <div class="u-d4cbd628">
          <div class="u-4ff818ff">${icon}</div>
          <div style="font-size:9px;color:var(--text-3);text-transform:uppercase">${label}</div>
          <div style="font-size:18px;font-weight:700;color:${col}">${val}</div>
        </div>`).join('')}
    </div>

    <!-- Connector SDK callout -->
    <div style="background:rgba(158,206,106,0.08);border:1px solid var(--success);border-radius:10px;padding:14px 18px;margin-bottom:18px">
      <div style="font-size:12px;font-weight:700;color:var(--success);margin-bottom:4px">🛠️ Connector SDK</div>
      <div style="font-size:11px;color:var(--text-2)">Register any custom connector — define its capabilities, auth type, and credential schema. Your agents can then call it via <code class="u-1b6531f7">POST /api/connectors/{id}/execute</code> or through the MCP Gateway.</div>
    </div>

    <!-- Connector cards by category -->
    ${categories.map(cat=>`
    <div class="u-49f14f8f">
      <div style="font-size:12px;font-weight:700;margin-bottom:10px;color:var(--text-0)">
        ${CONNECTOR_CATEGORY_ICONS[cat]||'📦'} ${cat.replace('_',' ').replace(/\b\w/g,c=>c.toUpperCase())}
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px">
        ${(list.connectors||[]).filter(c=>c.category===cat).map(c=>renderConnectorCard(c, statusColor)).join('')}
      </div>
    </div>`).join('')}
  </div>`;
}
function renderConnectorCard(c, statusColor) {
const sCol = statusColor[c.status]||'var(--text-3)';
const caps = Array.isArray(c.capabilities) ? c.capabilities : [];
return `
  <div class="u-534c2d64">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
      <span class="u-81351bd1">${c.icon||'🔌'}</span>
      <div class="u-97445a8d">
        <div class="u-88697aec">${escHtml(c.name)}</div>
        <span style="font-size:10px;padding:1px 6px;border-radius:4px;font-weight:700;background:${sCol}22;color:${sCol}">${c.status}</span>
      </div>
      ${c.call_count>0?`<span style="font-size:10px;color:var(--text-3)">${c.call_count} calls</span>`:''}
    </div>

    <div style="font-size:11px;color:var(--text-2);margin-bottom:10px;line-height:1.5">${escHtml((c.description||'').slice(0,100))}</div>

    <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:10px">
      ${caps.slice(0,4).map(cap=>`<span style="font-size:10px;background:var(--bg-3);border-radius:4px;padding:2px 6px;color:var(--text-2)">${escHtml(cap)}</span>`).join('')}
      ${caps.length>4?`<span style="font-size:10px;color:var(--text-3)">+${caps.length-4} more</span>`:''}
    </div>

    <div style="display:flex;gap:6px;flex-wrap:wrap">
      ${c.status==='unconfigured'?`<button class="btn u-97445a8d" data-connector-id="${escHtml(c.connector_id)}" data-connector-name="${escHtml(c.name)}" data-connector-auth="${escHtml(c.auth_type)}" data-act-click="connectorConfigure($data.connectorId,$data.connectorName,$data.connectorAuth)" >⚙️ Configure</button>`:
        `<button class="btn-sm" data-connector-id="${escHtml(c.connector_id)}" data-connector-caps='${JSON.stringify(caps).replace(/\'/g, "&#39;")}' data-act-click="connectorExecute($data.connectorId,$data.connectorName,$json.connectorCaps)">▶ Execute</button>
         <button class="btn-sm" data-connector-id="${escHtml(c.connector_id)}" data-act-click="connectorHistory($data.connectorId)">📋 History</button>
         <button class="btn-sm" data-connector-id="${escHtml(c.connector_id)}" data-act-click="connectorTest($data.connectorId)">🧪 Test</button>`}
    </div>
  </div>`;
}
async function connectorConfigure(connId, name, authType) {
const hints = {api_key:'API key / token', basic:'username:password or email:token', oauth:'OAuth token', smtp:'SMTP credentials', none:'No credentials needed'};
const note = await gmPrompt(`Configure: ${name}`, `${hints[authType]||'Enter credentials'}\n\nPaste as JSON: {"key":"value"}`,'{}') || '';
if (note===null) return;
let creds = {};
try { creds = JSON.parse(note); } catch(e) { showToast('⚠️ Invalid JSON — use {"key":"value"} format'); return; }
const r = await fetch(`/api/connectors/${encodeURIComponent(connId)}/configure`,{
method:'PATCH', headers:{'Content-Type':'application/json'},
body: JSON.stringify({credentials:creds})
}).catch(()=>null);
const d = r ? await r.json() : {};
showToast(d.ok ? `✅ ${name} configured and active` : '⚠️ '+(d.error||'Failed'));
renderConnectors();
}
async function connectorExecute(connId, name, caps) {
const action = await gmPrompt(`Execute: ${name}`, `Action to run:\n${caps.map(c=>`• ${c}`).join('\n')}`, caps[0]||'') || '';
if (!action?.trim()) return;
const payloadStr = await gmPrompt('Payload (JSON):', '{"channel":"general","text":"Hello from Agentic OS!"}') || '{}';
let payload = {};
try { payload = JSON.parse(payloadStr); } catch(e) { showToast('⚠️ Invalid JSON payload'); return; }
showToast(`🔌 Executing ${name}.${action}…`);
const r = await fetch(`/api/connectors/${encodeURIComponent(connId)}/execute`,{
method:'POST', headers:{'Content-Type':'application/json'},
body: JSON.stringify({action, payload, agent_id:'user'})
}).catch(()=>null);
if (!r) { showToast('⚠️ Execution failed'); return; }
const d = await r.json();
await gmAlert(`🔌 ${name} — ${action}`,
`Status: ${d.ok?'✅ Success':'❌ Failed'}\nExec ID: ${d.exec_id||'?'}\nDuration: ${d.duration_ms||0}ms\n\n${d.ok ? JSON.stringify(d,null,2).slice(0,500) : 'Error: '+(d.error||'Unknown')}`);
renderConnectors();
}
async function connectorHistory(connId) {
const r = await fetch(`/api/connectors/${encodeURIComponent(connId)}/executions?limit=10`).catch(()=>null);
if (!r||!r.ok) { showToast('Could not load history'); return; }
const d = await r.json();
const lines = (d.executions||[]).map(e=>
`${new Date(e.created_at).toLocaleTimeString()} [${e.status}] ${e.action} (${e.duration_ms}ms)`
).join('\n');
await gmAlert('📋 Execution History', lines || 'No executions yet');
}
async function connectorTest(connId) {
const r = await fetch(`/api/connectors/${encodeURIComponent(connId)}/test`,{method:'POST'}).catch(()=>null);
if (!r) { showToast('⚠️ Test failed'); return; }
const d = await r.json();
showToast(d.configured ? `✅ ${d.name} is ready` : `⚠️ ${d.message}`);
}
async function connectorRegister() {
const name   = await gmPrompt('Custom Connector SDK', 'Connector name:');
if (!name?.trim()) return;
const cat    = await gmPrompt('Category:', 'custom') || 'custom';
const auth   = await gmPrompt('Auth type (none/api_key/basic/oauth):', 'api_key') || 'api_key';
const capsStr= await gmPrompt('Capabilities (comma-separated):', 'my_action') || '';
const caps   = capsStr.split(',').map(s=>s.trim()).filter(Boolean);
const r = await fetch('/api/connectors',{
method:'POST', headers:{'Content-Type':'application/json'},
body: JSON.stringify({name, category:cat, auth_type:auth, capabilities:caps})
}).catch(()=>null);
const d = r ? await r.json() : {};
showToast(d.ok ? `🔌 Connector registered: ${d.connector_id}` : '⚠️ '+(d.error||'Failed'));
if (d.ok) renderConnectors();
}
window.renderConnectors = renderConnectors;
window.connectorConfigure = connectorConfigure;
window.connectorExecute = connectorExecute;
window.connectorHistory = connectorHistory;
window.connectorRegister = connectorRegister;
window.connectorTest = connectorTest;
})(S, nav, toast, escHtml, fetch, document);
