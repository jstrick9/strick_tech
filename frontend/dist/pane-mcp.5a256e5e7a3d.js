
;/* 35-connect-hub.js */
let connectCatalog = [];
let connectFilter = 'all';
let connectQuery = '';
async function renderConnectHub() {
const pane = document.getElementById('pane-mcp');
if (!pane) return;
pane.innerHTML = `<div class="section-head">
    <div>
      <h2>🔌 Connect</h2>
      <p>Everything your agents can reach — built-in tools, connected apps, and tool servers.</p>
    </div>
  </div>
  <div id="connect-stats" style="display:flex;gap:10px;margin-bottom:14px;flex-wrap:wrap"></div>
  <div style="display:flex;gap:8px;margin-bottom:14px;align-items:center;flex-wrap:wrap">
    <button data-act-click="connectSetFilter('all')" id="cf-all" class="btn btn-sm btn-primary">All</button>
    <button data-act-click="connectSetFilter('setup')" id="cf-setup" class="btn btn-sm btn-ghost">⚙️ Needs setup</button>
    <button data-act-click="connectSetFilter('connector')" id="cf-connector" class="btn btn-sm btn-ghost">🔗 Apps</button>
    <button data-act-click="connectSetFilter('tool')" id="cf-tool" class="btn btn-sm btn-ghost">🔧 Tools</button>
    <button data-act-click="connectSetFilter('server')" id="cf-server" class="btn btn-sm btn-ghost">🚪 Servers</button>
    <input id="connect-search" placeholder="Search…" value="${escHtml(connectQuery)}"
      style="flex:1;min-width:160px;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 11px;color:var(--text-0);font-size:13px;outline:none">
  </div>
  <div id="connect-body"><div style="color:var(--text-2);padding:20px">Loading…</div></div>
  <div id="connect-drawer"></div>`;
const search = document.getElementById('connect-search');
if (search) {
let t = null;
search.addEventListener('input', e => {
connectQuery = e.target.value;
clearTimeout(t);
t = setTimeout(() => connectRenderBody(), 180);
});
}
await connectLoad();
}
async function connectLoad() {
try {
const [cR, sR] = await Promise.all([
fetch('/api/connect/catalog'),
fetch('/api/connect/stats'),
]);
if (!cR.ok) throw new Error('catalog ' + cR.status);
connectCatalog = (await cR.json()).items || [];
if (sR.ok) connectRenderStats(await sR.json());
connectRenderBody();
} catch (ex) {
const b = document.getElementById('connect-body');
if (b) b.innerHTML = `<div style="color:var(--red);padding:16px">Could not load: ${escHtml(ex.message)}</div>`;
}
}
function connectRenderStats(s) {
const el = document.getElementById('connect-stats');
if (!el) return;
const chip = (label, value, accent) =>
`<div style="background:var(--bg-2);border:1px solid ${accent||'var(--border)'};border-radius:var(--radius-sm);padding:8px 14px">
       <div class="u-80b90e3a">${value}</div>
       <div style="font-size:11px;color:var(--text-2)">${escHtml(label)}</div>
     </div>`;
el.innerHTML =
chip('Ready to use', s.ready, 'var(--accent)') +
chip('Needs setup', s.needs_setup, s.needs_setup ? 'var(--orange,#e0821c)' : null) +
chip('Built-in tools', s.tools) +
chip('Connected apps', s.connectors) +
chip('Tool servers', s.servers);
}
function connectSetFilter(f) {
connectFilter = f;
['all', 'setup', 'connector', 'tool', 'server'].forEach(k => {
const b = document.getElementById('cf-' + k);
if (b) b.className = 'btn btn-sm ' + (k === f ? 'btn-primary' : 'btn-ghost');
});
connectRenderBody();
}
function connectFiltered() {
const q = connectQuery.trim().toLowerCase();
return connectCatalog.filter(i => {
if (connectFilter === 'setup' && !i.needs_setup) return false;
if (['connector', 'tool', 'server'].includes(connectFilter) && i.kind !== connectFilter) return false;
if (!q) return true;
return (i.name + ' ' + i.description + ' ' + (i.actions || []).join(' ')).toLowerCase().includes(q);
});
}
function connectRenderBody() {
const el = document.getElementById('connect-body');
if (!el) return;
const items = connectFiltered();
const needsSetup = connectCatalog.filter(i => i.needs_setup);
const banner = (connectFilter === 'all' && needsSetup.length)
? `<div style="background:var(--bg-2);border:1px solid var(--orange,#e0821c);border-radius:var(--radius-lg);padding:12px 14px;margin-bottom:14px">
        <div class="u-88697aec">⚙️ ${needsSetup.length} app${needsSetup.length===1?'':'s'} need credentials</div>
        <div style="font-size:12px;color:var(--text-2);margin-top:3px">
          ${needsSetup.slice(0,6).map(i => escHtml(i.name)).join(' · ')}
        </div>
        <button data-act-click="connectSetFilter('setup')" class="btn btn-primary btn-sm" style="margin-top:9px">Set them up</button>
      </div>`
: '';
el.innerHTML = banner + (items.length
? `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:12px">
        ${items.map(connectCard).join('')}
      </div>`
: '<div style="color:var(--text-3);padding:24px;text-align:center">Nothing matches.</div>');
}
function connectCard(i) {
const badge = i.ready
? '<span class="tag green u-0d5be05f" >Ready</span>'
: '<span class="tag" style="font-size:10px;color:var(--orange,#e0821c)">Setup needed</span>';
return `<div style="background:var(--bg-2);border:1px solid ${i.ready?'var(--border)':'var(--orange,#e0821c)'};border-radius:var(--radius-lg);padding:14px;display:flex;flex-direction:column">
    <div style="display:flex;align-items:flex-start;gap:9px;margin-bottom:6px">
      <span style="font-size:22px;line-height:1">${i.icon || '🔧'}</span>
      <div class="u-59eddc67">
        <div style="font-weight:700;font-size:13.5px;word-break:break-word">${escHtml(i.name)}</div>
        <div style="font-size:10.5px;color:var(--text-3)">${escHtml(i.kind)} · ${escHtml(i.category)}</div>
      </div>
      ${badge}
    </div>
    <p style="font-size:12px;color:var(--text-2);line-height:1.45;margin:0 0 9px;flex:1">${escHtml(i.description || '')}</p>
    ${(i.actions || []).length ? `<div style="font-size:10.5px;color:var(--text-3);margin-bottom:9px">
      ${(i.actions||[]).slice(0,4).map(a=>`<span class="tag" style="font-size:9.5px">${escHtml(a)}</span>`).join(' ')}
      ${(i.actions||[]).length>4?`<span style="color:var(--text-3)"> +${i.actions.length-4}</span>`:''}
    </div>` : ''}
    <div style="display:flex;gap:6px">
      <button data-item="${escHtml(i.id)}" data-act-click="connectShowDetail($data.item)" class="btn btn-ghost btn-sm u-97445a8d" >Details</button>
      ${i.needs_setup
        ? `<button data-item="${escHtml(i.id)}" data-act-click="connectShowSetup($data.item)" class="btn btn-primary btn-sm u-97445a8d" >Set up</button>`
        : `<button data-item="${escHtml(i.id)}" data-act-click="connectTest($data.item)" class="btn btn-ghost btn-sm">Test</button>`}
    </div>
  </div>`;
}
async function connectShowDetail(id) {
const drawer = document.getElementById('connect-drawer');
if (!drawer) return;
try {
const r = await fetch(`/api/connect/item/${encodeURIComponent(id)}`);
if (!r.ok) { toast('Not found', 'err'); return; }
const d = await r.json();
drawer.innerHTML = `<div id="connect-overlay" data-act-click="connectClose($event)"
        style="position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:900;display:flex;justify-content:flex-end">
      <div data-stop="1" style="width:min(520px,100%);height:100%;overflow-y:auto;background:var(--bg-1);border-left:1px solid var(--border);padding:22px">
        <div style="display:flex;align-items:flex-start;gap:12px">
          <span style="font-size:32px">${d.icon || '🔧'}</span>
          <div class="u-97445a8d"><div class="u-80b90e3a">${escHtml(d.name)}</div>
            <div style="font-size:12px;color:var(--text-3)">${escHtml(d.kind)} · ${escHtml(d.category)} · ${d.ready?'ready':'needs setup'}</div></div>
          <button data-act-click="connectClose()" class="btn btn-ghost btn-sm">✕</button>
        </div>
        <p style="font-size:13px;color:var(--text-1);line-height:1.6;margin-top:10px">${escHtml(d.description||'')}</p>
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:11px;font-size:12.5px;margin:12px 0">
          ${escHtml(d.how_to_use || '')}
        </div>
        ${(d.actions||[]).length ? `<div style="font-weight:700;font-size:13px;margin:14px 0 6px">Available actions</div>
          <div>${(d.actions||[]).map(a=>`<span class="tag" style="margin:0 4px 4px 0;display:inline-block">${escHtml(a)}</span>`).join('')}</div>` : ''}
        ${d.setup ? connectSetupHtml(d.id, d.setup) : ''}
        <div style="margin-top:16px;display:flex;gap:8px">
          <button data-item="${escHtml(d.id)}" data-act-click="connectTest($data.item)" class="btn btn-ghost u-97445a8d" >Test connection</button>
        </div>
        <div id="connect-test-result" class="u-d2c171b1"></div>
      </div>
    </div>`;
} catch (ex) { toast('Error: ' + ex.message, 'err'); }
}
function connectSetupHtml(id, s) {
return `<div style="margin-top:16px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:13px">
    <div style="font-weight:700;font-size:13px;margin-bottom:6px">⚙️ Setup</div>
    ${(s.needs||[]).length ? `<div style="font-size:12px;color:var(--text-2)">You'll need: <b>${(s.needs||[]).map(escHtml).join(', ')}</b></div>` : ''}
    ${s.where ? `<div style="font-size:12px;color:var(--text-2);margin-top:5px">Where: ${escHtml(s.where)}</div>` : ''}
    ${s.scopes ? `<div style="font-size:12px;color:var(--text-2);margin-top:5px">Scopes: ${escHtml(s.scopes)}</div>` : ''}
    ${s.docs ? `<div style="font-size:12px;margin-top:6px"><a href="${safeUrl(s.docs)}" target="_blank" rel="noopener noreferrer" style="color:var(--accent-text)">Provider docs ↗</a></div>` : ''}
    ${(s.needs||[]).length ? `<button data-item="${escHtml(id)}" data-act-click="connectShowSetup($data.item)" class="btn btn-primary btn-sm" style="margin-top:10px;width:100%">Enter credentials</button>` : ''}
  </div>`;
}
async function connectShowSetup(id) {
try {
const r = await fetch(`/api/connect/setup/${encodeURIComponent(id)}`);
if (!r.ok) { toast('No setup guide for that item', 'warn'); return; }
const g = await r.json();
const needs = g.needs || [];
if (!needs.length) { toast('No credentials required', 'ok'); return; }
const creds = {};
for (const field of needs) {
const v = await gmPrompt(
`Set up ${id.replace('conn_', '')}`,
`${field}${g.where ? `\n\nFind it at: ${g.where}` : ''}`,
''
);
if (v === null) return;
if (!v) { toast('All fields are required', 'warn'); return; }
creds[field] = v;
}
const cr = await fetch(`/api/connectors/${encodeURIComponent(id)}/configure`, {
method: 'PATCH',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({ credentials: creds }),
});
const cj = await cr.json().catch(() => null);
if (!cr.ok || !cj || !cj.ok) {
toast('Setup failed: ' + ((cj && cj.error) || cr.status), 'err');
return;
}
toast('✅ Credentials saved — testing…', 'ok', 2000);
connectClose();
await connectLoad();
await connectTest(id);
} catch (ex) { toast('Setup error: ' + ex.message, 'err'); }
}
async function connectTest(id) {
const out = document.getElementById('connect-test-result');
if (out) out.innerHTML = '<div style="color:var(--text-2);font-size:12px">Testing…</div>';
try {
const r = await fetch(`/api/connect/test/${encodeURIComponent(id)}`, { method: 'POST' });
const j = await r.json().catch(() => null);
const ok = !!(j && j.ok);
const msg = j ? (typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail || {})) : 'no response';
if (out) {
out.innerHTML = `<div style="font-size:12px;color:${ok?'var(--green)':'var(--red)'}">
        ${ok ? '✅ Working' : '❌ Not working'} — ${escHtml(msg.slice(0, 300))}</div>`;
} else {
toast(ok ? '✅ Connection working' : '❌ Connection failed', ok ? 'ok' : 'err', 3000);
}
} catch (ex) {
if (out) out.innerHTML = `<div style="color:var(--red);font-size:12px">${escHtml(ex.message)}</div>`;
}
}
function connectClose(e) {
if (e && e.target && e.target.id !== 'connect-overlay') return;
const d = document.getElementById('connect-drawer');
if (d) d.innerHTML = '';
}

;/* 39-mcp-panel.js */
async function renderMCP() {
const pane = document.getElementById('pane-mcp');
if (!pane) return;
pane.innerHTML = `<div class="section-head">
    <div><h2>🔧 MCP Tool Router</h2><p>Model Context Protocol — call any tool directly or let an agent use them autonomously</p></div>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
    <div>
      <div class="settings-card">
        <h3>Direct Tool Call</h3>
        <p>Call any tool directly and inspect the result.</p>
        <label style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px">Tool</label>
        <select id="mcp-tool-sel" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px;color:var(--text-0);font-size:13px;margin:6px 0 10px;outline:none">
          <option value="">Loading tools…</option>
        </select>
        <label style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px">Args (JSON)</label>
        <textarea id="mcp-args" data-draft="mcp-args" placeholder='{"path": "index.html"}' style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px;color:var(--text-0);font-size:13px;resize:none;min-height:60px;outline:none;font-family:monospace;margin:6px 0 10px"></textarea>
        <button data-act-click="runMCPTool()" class="btn btn-primary" style="width:100%">▶ Call Tool</button>
        <div id="mcp-result" style="margin-top:12px;background:var(--bg-0);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;font-family:monospace;font-size:12px;color:var(--text-1);white-space:pre-wrap;max-height:300px;overflow-y:auto;display:none"></div>
      </div>
      <div class="settings-card">
        <h3>Agentic Run</h3>
        <p>Give an agent a task and let it autonomously use tools to complete it.</p>
        <textarea id="mcp-agent-prompt" data-draft="mcp-agent-prompt" placeholder="Research the latest React 19 features and write a summary to index.html" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px;color:var(--text-0);font-size:13px;resize:none;min-height:80px;outline:none;font-family:inherit;margin:6px 0 10px"></textarea>
        <div style="display:flex;gap:8px;margin-bottom:10px">
          <select id="mcp-agent-sel" style="flex:1;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px;color:var(--text-0);font-size:12.5px;outline:none">
            ${S.agents.map(a=>`<option value="${a.id}">${a.avatar||'🤖'} ${escHtml(a.name)}</option>`).join('')}
          </select>
          <input id="mcp-max-steps" type="number" value="5" min="1" max="10" style="width:70px;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px;color:var(--text-0);font-size:12.5px;outline:none" placeholder="Steps">
        </div>
        <button data-act-click="runAgentWithTools()" class="btn btn-primary" style="width:100%" id="mcp-agent-btn">🤖 Run Agent</button>
        <div id="mcp-agent-result" style="margin-top:12px;display:none"></div>
      </div>
    </div>
    <div>
      <div class="settings-card">
        <h3 id="mcp-tools-header">Available Tools</h3>
        <p>All tools available to agents via MCP.</p>
        <div id="mcp-tool-list" style="display:flex;flex-direction:column;gap:6px"></div>
      </div>
    </div>
  </div>`;
loadMCPTools();
}
async function loadMCPTools() {
try {
const r = await fetch('/api/mcp/tools');
if (!r.ok) throw new Error('Tools API error ' + r.status);
const j = await r.json();
const sel = document.getElementById('mcp-tool-sel');
const list = document.getElementById('mcp-tool-list');
const hdr = document.getElementById('mcp-tools-header');
if (hdr) hdr.textContent = `Available Tools (${j.count || j.tools?.length || 0})`;
if (sel) sel.innerHTML = j.tools.map(t => `<option value="${escHtml(t.name)}">${escHtml(t.name)}</option>`).join('');
if (list) list.innerHTML = j.tools.map(t => `
      <div style="display:flex;gap:10px;padding:7px 10px;background:var(--bg-3);border-radius:var(--radius-sm);cursor:pointer"
           data-act-click="hSetFieldValue('mcp-tool-sel',${jsArg(t.name)})">
        <code style="color:var(--accent-text);font-size:12px;min-width:140px">${t.name}</code>
        <span style="font-size:12px;color:var(--text-2)">${t.description}</span>
      </div>`).join('');
if (sel) sel.onchange = () => {
const tool = j.tools.find(t => t.name === sel.value);
if (tool) {
const exampleArgs = {};
(tool.args||[]).filter(a=>!a.endsWith('?')).forEach(a => exampleArgs[a] = '');
document.getElementById('mcp-args').value = JSON.stringify(exampleArgs, null, 2);
}
};
} catch(e) { toast('Failed to load MCP tools', 'err'); }
}
async function runMCPTool() {
const tool = document.getElementById('mcp-tool-sel')?.value;
if (!tool) { toast('Select a tool first', 'warn'); return; }
const argsStr = document.getElementById('mcp-args')?.value || '{}';
const resultEl = document.getElementById('mcp-result');
let args = {};
try { args = JSON.parse(argsStr); } catch(e) { toast('Invalid JSON args — check the format', 'err'); return; }
if (resultEl) { resultEl.style.display = 'block'; resultEl.textContent = 'Running…'; }
try {
const r = await fetch('/api/mcp/call', {
method:'POST', headers:{'Content-Type':'application/json'},
body: JSON.stringify({tool, args})
});
if (!r.ok) {
if (resultEl) resultEl.textContent = 'Server error ' + r.status;
toast('Tool call failed: server error ' + r.status, 'err');
return;
}
const j = await r.json();
if (resultEl) resultEl.textContent = JSON.stringify(j, null, 2);
if (j.ok) toast(`✅ ${tool} → ${j.duration_ms}ms`, 'ok', 2000);
else toast(`❌ ${j.error}`, 'err');
} catch(ex) {
if (resultEl) resultEl.textContent = 'Error: ' + ex.message;
toast('Tool call error: ' + ex.message, 'err');
}
}
async function runAgentWithTools() {
const prompt = document.getElementById('mcp-agent-prompt')?.value.trim();
const agentId = document.getElementById('mcp-agent-sel')?.value || 'builder';
const maxSteps = parseInt(document.getElementById('mcp-max-steps')?.value || '5');
if (!prompt) { toast('Enter a prompt', 'warn'); return; }
const btn = document.getElementById('mcp-agent-btn');
const resultEl = document.getElementById('mcp-agent-result');
btn.disabled = true; btn.textContent = '⏳ Running…';
resultEl.style.display = 'block';
resultEl.innerHTML = `<div style="color:var(--text-2);font-size:13px">Agent is working…</div>`;
try {
const r = await fetch('/api/mcp/agent/run', {
method:'POST', headers:{'Content-Type':'application/json'},
body: JSON.stringify({prompt, agent_id: agentId, max_steps: maxSteps})
});
if (!r.ok) {
resultEl.innerHTML = `<div style="color:var(--danger)">Server error ${r.status}</div>`;
btn.disabled = false; btn.textContent = '🤖 Run Agent';
return;
}
const j = await r.json();
resultEl.innerHTML = `
    <div style="margin-bottom:10px;font-size:13px;font-weight:700">${j.ok?'✅':'❌'} ${j.step_count} steps</div>
    ${(j.steps||[]).map((s,i) => `<div style="background:var(--bg-3);border-radius:var(--radius-sm);padding:8px;margin-bottom:6px;font-size:12px">
      <div style="font-weight:700;margin-bottom:3px">Step ${s.step}: <span style="color:var(--accent-text)">${s.type}</span>${s.tool?` → ${s.tool}`:''}</div>
      ${s.output?`<div style="color:var(--text-1);white-space:pre-wrap;max-height:80px;overflow:hidden">${escHtml((s.output||'').slice(0,200))}</div>`:''}
      ${s.error?`<div style="color:var(--red)">${escHtml(s.error)}</div>`:''}
    </div>`).join('')}
    ${j.final_answer?`<div style="background:var(--accent-glow);border:1px solid var(--accent);border-radius:var(--radius-sm);padding:10px;font-size:13px">
      <div style="font-weight:700;margin-bottom:5px">Final Answer</div>
      <div>${renderMarkdown(j.final_answer)}</div>
    </div>`:''}`;
btn.disabled = false; btn.textContent = '🤖 Run Agent';
if (j.ok) toast(`✅ Agent done in ${j.step_count} steps`, 'ok');
} catch(ex) {
resultEl.innerHTML = `<div style="color:var(--danger)">Error: ${escHtml(ex.message)}</div>`;
btn.disabled = false; btn.textContent = '🤖 Run Agent';
}
}
