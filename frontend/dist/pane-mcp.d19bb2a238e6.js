
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
       <div style="font-size:18px;font-weight:800">${value}</div>
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
        <div style="font-weight:700;font-size:13px">⚙️ ${needsSetup.length} app${needsSetup.length===1?'':'s'} need credentials</div>
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
          <div class="u-97445a8d"><div style="font-size:18px;font-weight:800">${escHtml(d.name)}</div>
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
        <div id="connect-test-result" style="margin-top:10px"></div>
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
