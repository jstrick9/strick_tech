
;/* 59-icm-workspaces.js */
(function () {
'use strict';
let wsList = [];
let currentWs = null;
let currentStage = '';
let currentFile = '';
let currentTab = 'folders';
let dirty = false;
const esc = (s) => String(s == null ? '' : s)
.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
function arg(v) {
return (window.jsArg ? window.jsArg(v) : JSON.stringify(v));
}
async function api(path, opts) {
const r = await fetch(path, opts);
let d = null;
try { d = await r.json(); } catch (e) { d = null; }
if (!r.ok || (d && d.ok === false)) {
const msg = (d && (d.detail || d.error)) || ('HTTP ' + r.status);
throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
}
return d || {};
}
async function renderWorkspacesIcmPane() {
const host = document.getElementById('pane-icm');
if (!host) return;
host.innerHTML = `
      <div style="flex:1;display:flex;flex-direction:column;min-height:0">
        <div style="padding:18px 24px 0;border-bottom:1px solid var(--border-0)">
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
            <div>
              <div style="font-size:18px;font-weight:700">🗂 Workspaces</div>
              <div style="font-size:12.5px;color:var(--text-2);margin-top:2px">
                Folder structure as agent architecture. The folder is the app.
              </div>
            </div>
            <div style="flex:1"></div>
            <button type="button" class="btn" data-act-click="icmwsNewWorkspace()">+ New workspace</button>
          </div>
          <div style="display:flex;gap:20px;margin-top:14px">
            ${['folders', 'routing', 'log'].map((t) => `
              <button type="button" id="icm-tab-${t}" data-act-click="icmwsTab(${arg(t)})"
                style="padding:10px 0;background:none;border:none;border-bottom:2px solid transparent;
                       color:var(--text-2);font-weight:600;font-size:13.5px;cursor:pointer;text-transform:capitalize">
                ${t === 'folders' ? '📁 Folders' : t === 'routing' ? '🎯 Routing' : '📜 Route log'}
              </button>`).join('')}
          </div>
        </div>
        <div id="icm-body" style="flex:1;overflow:hidden;display:flex;min-height:0"></div>
      </div>`;
await loadWorkspaces();
icmwsTab(currentTab);
}
async function loadWorkspaces() {
try {
const d = await api('/api/icm/routes');
wsList = d.routes || [];
if (currentWs && !wsList.some((w) => w.workspace_id === currentWs)) currentWs = null;
if (!currentWs && wsList.length) currentWs = wsList[0].workspace_id;
} catch (e) {
wsList = [];
console.warn('ICM workspaces load failed:', e);
}
}
function icmwsTab(tab) {
currentTab = tab;
['folders', 'routing', 'log'].forEach((t) => {
const b = document.getElementById('icm-tab-' + t);
if (!b) return;
const on = t === tab;
b.style.borderBottom = on ? '2px solid var(--accent)' : '2px solid transparent';
b.style.color = on ? 'var(--text-0)' : 'var(--text-2)';
});
if (tab === 'folders') renderFolders();
else if (tab === 'routing') renderRouting();
else renderLog();
}
function stageBar(w) {
if (!w.total_stages) return '';
const pct = Math.round((w.complete / w.total_stages) * 100);
return `<div style="height:4px;background:var(--bg-2);border-radius:2px;margin-top:6px;overflow:hidden">
        <div style="height:100%;width:${pct}%;background:var(--accent)"></div>
      </div>
      <div style="font-size:10.5px;color:var(--text-2);margin-top:3px">
        ${w.complete}/${w.total_stages} stages have output</div>`;
}
async function renderFolders() {
const body = document.getElementById('icm-body');
if (!body) return;
if (!wsList.length) {
body.innerHTML = `<div style="padding:48px;text-align:center;color:var(--text-2);margin:auto">
        <div style="font-size:34px">🗂</div>
        <div style="font-weight:600;color:var(--text-0);margin-top:10px">No workspaces yet</div>
        <div style="font-size:13px;margin-top:6px;max-width:420px">
          A workspace is numbered stage folders plus markdown contracts. One agent walks
          the right files at the right moment — no orchestration code.</div>
        <button type="button" class="btn" style="margin-top:16px" data-act-click="icmwsNewWorkspace()">
          Create your first workspace</button></div>`;
return;
}
body.innerHTML = `
      <div style="width:250px;border-right:1px solid var(--border-0);overflow-y:auto;padding:12px">
        ${wsList.map((w) => `
          <div role="button" tabindex="0" data-act-click="icmwsSelect(${arg(w.workspace_id)})"
            data-keys="Enter" data-self-click="1"
            style="padding:10px 12px;border-radius:8px;cursor:pointer;margin-bottom:6px;
                   background:${w.workspace_id === currentWs ? 'var(--bg-2)' : 'transparent'}">
            <div style="font-weight:600;font-size:13px">${esc(w.name)}</div>
            <div style="font-size:11px;color:var(--text-2)">${esc(w.description || w.workspace_id)}</div>
            ${stageBar(w)}
          </div>`).join('')}
      </div>
      <div id="icm-tree" style="width:290px;border-right:1px solid var(--border-0);overflow-y:auto;padding:12px"></div>
      <div id="icm-editor" style="flex:1;overflow-y:auto;padding:18px;min-width:0"></div>`;
await renderTree();
}
function icmwsSelect(id) {
currentWs = id;
currentFile = '';
renderFolders();
}
async function renderTree() {
const el = document.getElementById('icm-tree');
if (!el || !currentWs) return;
const w = wsList.find((x) => x.workspace_id === currentWs);
if (!w) return;
currentStage = w.entry_stage || '';
el.innerHTML = `
      <div style="font-size:10.5px;font-weight:800;letter-spacing:0.6px;color:var(--text-2);margin-bottom:8px">
        LAYERS</div>
      ${fileRow('IDENTITY.md', 'L0', 'Where am I?')}
      ${fileRow('CONTEXT.md', 'L1', 'Where do I go?')}
      ${fileRow('_config/conventions.md', 'L3', 'House rules')}
      <div style="font-size:10.5px;font-weight:800;letter-spacing:0.6px;color:var(--text-2);margin:14px 0 8px">
        STAGES</div>
      ${(w.stages || []).map((s) => {
        const entry = s === w.entry_stage;
        return `<div style="margin-bottom:8px">
          <div style="font-size:12px;font-weight:600;display:flex;align-items:center;gap:6px">
            ${esc(s)}
            ${entry ? '<span style="font-size:9.5px;background:var(--accent);color:var(--on-accent);padding:1px 6px;border-radius:8px">ENTRY</span>' : ''}
          </div>
          ${fileRow('stages/' + s + '/CONTEXT.md', 'L2', 'The stage contract')}
        </div>`;
      }).join('')}
      <div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--border-0)">
        <div style="font-size:11px;color:var(--text-2)">
          Entry stage resolved: <b>${esc(w.entry_stage || 'none')}</b><br>
          <span style="opacity:0.8">${esc(w.entry_reason || '')}</span>
        </div>
      </div>`;
}
function fileRow(path, layer, hint) {
const on = path === currentFile;
return `<div role="button" tabindex="0" data-act-click="icmwsOpen(${arg(path)})"
      data-keys="Enter" data-self-click="1"
      style="display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:6px;cursor:pointer;
             margin-left:${layer === 'L2' ? '12px' : '0'};
             background:${on ? 'var(--bg-2)' : 'transparent'}">
      <span style="font-size:9.5px;font-weight:800;color:var(--accent-text);min-width:18px">${esc(layer)}</span>
      <span style="font-size:12px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
        title="${esc(hint)}">${esc(path.split('/').pop())}</span>
    </div>`;
}
async function icmwsOpen(path) {
if (dirty && !window.confirm('Discard unsaved changes?')) return;
currentFile = path;
dirty = false;
renderTree();
const ed = document.getElementById('icm-editor');
if (!ed) return;
ed.innerHTML = '<div style="color:var(--text-2);font-size:13px">Loading…</div>';
try {
const d = await api('/api/icm/workspaces/' + encodeURIComponent(currentWs)
+ '/file?path=' + encodeURIComponent(path));
ed.innerHTML = `
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
          <div style="font-weight:700;font-size:14px">${esc(path)}</div>
          <div style="flex:1"></div>
          <span id="icm-save-state" style="font-size:11.5px;color:var(--text-2)"></span>
          <button type="button" class="btn" data-act-click="icmwsSave()">Save</button>
        </div>
        <div style="font-size:11.5px;color:var(--text-2);margin-bottom:8px">
          Every output is an edit surface — edit here and the next stage reads what you left.
        </div>
        <textarea id="icm-file-body" spellcheck="false"
          style="width:100%;min-height:460px;background:var(--bg-1);color:var(--text-0);
                 border:1px solid var(--border-0);border-radius:8px;padding:14px;
                 font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;
                 line-height:1.55;resize:vertical">${esc(d.content || '')}</textarea>`;
const ta = document.getElementById('icm-file-body');
if (ta) {
ta.addEventListener('input', () => {
dirty = true;
const s = document.getElementById('icm-save-state');
if (s) s.textContent = 'unsaved changes';
});
}
} catch (e) {
ed.innerHTML = `<div style="color:var(--danger);font-size:13px">Could not open ${esc(path)}: ${esc(e.message)}</div>`;
}
}
async function icmwsSave() {
const ta = document.getElementById('icm-file-body');
const s = document.getElementById('icm-save-state');
if (!ta || !currentWs || !currentFile) return;
if (s) s.textContent = 'saving…';
try {
await api('/api/icm/workspaces/' + encodeURIComponent(currentWs) + '/file', {
method: 'PUT',
headers: {'Content-Type': 'application/json'},
body: JSON.stringify({path: currentFile, content: ta.value}),
});
dirty = false;
if (s) s.textContent = 'saved';
await loadWorkspaces();
renderTree();
} catch (e) {
if (s) s.textContent = 'save failed: ' + e.message;
}
}
function renderRouting() {
const body = document.getElementById('icm-body');
if (!body) return;
body.innerHTML = `
      <div style="flex:1;overflow-y:auto;padding:22px 26px">
        <div style="max-width:860px">
          <div style="font-weight:700;font-size:15px">Where does a request start?</div>
          <div style="font-size:12.5px;color:var(--text-2);margin:6px 0 16px">
            Starting in the wrong folder is how ICM fails silently: the layered context never
            loads and the run still looks fine. Type a request to see exactly which workspace
            and stage it would enter, and why.
          </div>
          <div style="display:flex;gap:8px">
            <input id="icm-route-q" type="text" placeholder="e.g. write the weekly client report"
              style="flex:1;padding:11px 13px;background:var(--bg-1);color:var(--text-0);
                     border:1px solid var(--border-0);border-radius:8px;font-size:13px">
            <button type="button" class="btn" data-act-click="icmwsTestRoute()">Test</button>
          </div>
          <div id="icm-route-result" style="margin-top:16px"></div>
          <div style="margin-top:28px;font-weight:700;font-size:14px">Route table</div>
          <div style="font-size:12px;color:var(--text-2);margin:4px 0 10px">
            Declared in each workspace's <code>CONTEXT.md</code> under <code>## Routes</code>.
            Generated from the filesystem, never hand-maintained.
          </div>
          ${wsList.map((w) => `
            <div style="border:1px solid var(--border-0);border-radius:10px;padding:12px 14px;margin-bottom:10px">
              <div style="display:flex;align-items:center;gap:8px">
                <div style="font-weight:600;font-size:13px">${esc(w.name)}</div>
                <span style="font-size:11px;color:var(--text-2)">${esc(w.workspace_id)}</span>
              </div>
              <div style="margin-top:8px">
                ${(w.routes || []).length
                  ? w.routes.map((r) => `<span style="display:inline-block;font-size:11.5px;
                      background:var(--bg-2);border-radius:12px;padding:3px 10px;margin:0 6px 6px 0">${esc(r)}</span>`).join('')
                  : `<span style="font-size:12px;color:var(--warning)">
                       No routes declared — this workspace can only be reached by name or explicitly.</span>`}
              </div>
            </div>`).join('')}
        </div>
      </div>`;
const input = document.getElementById('icm-route-q');
if (input) {
input.addEventListener('keydown', (e) => { if (e.key === 'Enter') icmwsTestRoute(); });
}
}
async function icmwsTestRoute() {
const q = (document.getElementById('icm-route-q') || {}).value || '';
const out = document.getElementById('icm-route-result');
if (!out) return;
if (!q.trim()) { out.innerHTML = ''; return; }
out.innerHTML = '<div style="color:var(--text-2);font-size:13px">Resolving…</div>';
try {
const d = await api('/api/icm/route?q=' + encodeURIComponent(q));
const x = d.decision || {};
const colour = x.status === 'matched' ? 'var(--accent-text)'
: x.status === 'ambiguous' ? 'var(--warning)' : 'var(--text-2)';
out.innerHTML = `
        <div style="border:1px solid ${colour};border-radius:10px;padding:14px 16px">
          <div style="display:flex;align-items:center;gap:8px">
            <span style="font-size:10.5px;font-weight:800;letter-spacing:0.5px;color:${colour}">
              ${esc(String(x.status || '').toUpperCase())}</span>
            ${x.matched ? `<span style="font-weight:600;font-size:13.5px">
                ${esc(x.name)} → ${esc(x.stage)}</span>` : ''}
          </div>
          <div style="font-size:12.5px;color:var(--text-2);margin-top:6px">${esc(x.reason || '')}</div>
          ${x.stage_reason ? `<div style="font-size:12px;color:var(--text-2);margin-top:4px">
              Stage chosen because: ${esc(x.stage_reason)}</div>` : ''}
          ${(x.candidates || []).length ? `
            <div style="margin-top:12px;font-size:11px;font-weight:800;color:var(--text-2);letter-spacing:0.5px">
              SCORES</div>
            ${x.candidates.map((c) => `
              <div style="display:flex;gap:10px;font-size:12px;padding:3px 0">
                <span style="min-width:46px;font-weight:700">${esc(String(c.score))}</span>
                <span style="min-width:130px">${esc(c.workspace_id)}</span>
                <span style="color:var(--text-2);flex:1">${esc((c.evidence || []).join(', ') || '—')}</span>
              </div>`).join('')}` : ''}
        </div>`;
} catch (e) {
out.innerHTML = `<div style="color:var(--danger);font-size:13px">${esc(e.message)}</div>`;
}
}
async function renderLog() {
const body = document.getElementById('icm-body');
if (!body) return;
body.innerHTML = '<div style="padding:24px;color:var(--text-2);font-size:13px">Loading…</div>';
let rows = [];
try {
rows = (await api('/api/icm/route/log?limit=100')).decisions || [];
} catch (e) {  }
body.innerHTML = `
      <div style="flex:1;overflow-y:auto;padding:22px 26px">
        <div style="font-weight:700;font-size:15px">Route log</div>
        <div style="font-size:12.5px;color:var(--text-2);margin:6px 0 14px">
          Which folder each request actually started in. If routing is invisible, it is not fixed.
        </div>
        ${rows.length ? rows.map((r) => `
          <div style="display:flex;gap:12px;padding:9px 0;border-bottom:1px solid var(--border-0);font-size:12.5px">
            <span style="min-width:84px;color:var(--text-2)">
              ${esc(new Date((r.at || 0) * 1000).toLocaleTimeString())}</span>
            <span style="min-width:92px;font-weight:700;color:${
              r.status === 'matched' ? 'var(--accent-text)'
                : r.status === 'ambiguous' ? 'var(--warning)' : 'var(--text-2)'}">
              ${esc(r.status || '')}</span>
            <span style="min-width:150px">${esc(r.workspace_id || '—')}${r.stage ? ' / ' + esc(r.stage) : ''}</span>
            <span style="flex:1;color:var(--text-2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
              title="${esc(r.message || '')}">${esc(r.message || '')}</span>
            <span style="color:var(--text-2)">${esc(String(r.estimated_tokens || 0))} tok</span>
          </div>`).join('')
          : '<div style="color:var(--text-2);font-size:13px">No routing decisions recorded yet.</div>'}
      </div>`;
}
async function icmwsNewWorkspace() {
const name = window.prompt('Workspace name (e.g. "client reports")');
if (!name || !name.trim()) return;
const stagesRaw = window.prompt(
'Stages in order, comma separated.\n\nOne stage, one job — a stage that researches does not also write.',
'research, draft, review');
if (stagesRaw === null) return;
const stages = stagesRaw.split(',').map((s) => s.trim()).filter(Boolean);
if (!stages.length) return;
try {
const d = await api('/api/icm/workspaces', {
method: 'POST',
headers: {'Content-Type': 'application/json'},
body: JSON.stringify({name: name.trim(), description: '', stages: stages}),
});
currentWs = (d.workspace || {}).workspace_id || null;
currentFile = '';
await loadWorkspaces();
icmwsTab('folders');
} catch (e) {
window.alert('Could not create workspace: ' + e.message);
}
}
window.renderWorkspacesIcmPane = renderWorkspacesIcmPane;
window.icmwsTab = icmwsTab;
window.icmwsSelect = icmwsSelect;
window.icmwsOpen = icmwsOpen;
window.icmwsSave = icmwsSave;
window.icmwsTestRoute = icmwsTestRoute;
window.icmwsNewWorkspace = icmwsNewWorkspace;
window.PANE_RENDERERS = window.PANE_RENDERERS || {};
window.PANE_RENDERERS['icm'] = renderWorkspacesIcmPane;
})();
