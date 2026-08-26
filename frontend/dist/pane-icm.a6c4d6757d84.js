
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
            ${['folders', 'describe', 'templates', 'routing', 'audit', 'log'].map((t) => `
              <button type="button" id="icm-tab-${t}" data-act-click="icmwsTab(${arg(t)})"
                style="padding:10px 0;background:none;border:none;border-bottom:2px solid transparent;
                       color:var(--text-2);font-weight:600;font-size:13.5px;cursor:pointer;text-transform:capitalize">
                ${t === 'folders' ? '📁 Folders' : t === 'describe' ? '💬 Describe your work'
                  : t === 'templates' ? '📐 Templates'
                  : t === 'routing' ? '🎯 Routing'
                  : t === 'audit' ? '🔍 Audit a folder' : '📜 Route log'}
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
['folders', 'describe', 'templates', 'routing', 'audit', 'log'].forEach((t) => {
const b = document.getElementById('icm-tab-' + t);
if (!b) return;
const on = t === tab;
b.style.borderBottom = on ? '2px solid var(--accent)' : '2px solid transparent';
b.style.color = on ? 'var(--text-0)' : 'var(--text-2)';
});
if (tab === 'folders') renderFolders();
else if (tab === 'describe') renderDescribe();
else if (tab === 'templates') renderIcmTemplates();
else if (tab === 'routing') renderRouting();
else if (tab === 'audit') renderAudit();
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
        <div style="display:flex;gap:10px;justify-content:center;margin-top:16px">
          <button type="button" class="btn" data-act-click="icmwsTab('describe')">
            Describe your work</button>
          <button type="button" class="btn" data-act-click="icmwsNewWorkspace()">
            Set up stages manually</button>
        </div></div>`;
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
        ${esc(((w.stages || []).length ? 'stage' : unitNoun(w.form || 'pipeline')).toUpperCase())}S</div>
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
          ${w.entry_stage
            ? `Entry stage resolved: <b>${esc(w.entry_stage)}</b><br>
               <span style="opacity:0.8">${esc(w.entry_reason || '')}</span>`
            : 'This form has no stage sequence &mdash; open the shelf you need.'}
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
async function renderIcmTemplates() {
const body = document.getElementById('icm-body');
if (!body) return;
body.innerHTML = '<div style="padding:22px;color:var(--text-2);font-size:13px">Loading…</div>';
let list = [];
try {
list = (await api('/api/icm/templates')).templates || [];
} catch (e) {
body.innerHTML = `<div style="padding:22px;color:var(--danger);font-size:13px">${esc(e.message)}</div>`;
return;
}
body.innerHTML = `
      <div style="flex:1;overflow-y:auto;padding:22px 26px">
        <div style="max-width:900px">
          <div style="font-weight:700;font-size:15px">Templates</div>
          <div style="font-size:12.5px;color:var(--text-2);margin:6px 0 16px">
            A template is the <b>method</b> — the contracts, the routing and the reference
            material — with the run data stripped out. Starting a new piece of work copies
            one rather than beginning from a blank page.
          </div>
          <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px">
            ${list.map((t) => `
              <div style="border:1px solid var(--border-0);border-radius:10px;padding:14px">
                <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                  <div style="font-weight:600;font-size:13.5px">${esc(t.name)}</div>
                  ${t.builtin ? '<span style="font-size:9.5px;font-weight:800;color:var(--text-2)">STARTER</span>' : ''}
                </div>
                <div style="font-size:12px;color:var(--text-2);margin-top:5px;min-height:32px">
                  ${esc(t.description || '')}</div>
                <div style="font-size:11.5px;color:var(--text-2);margin-top:6px">
                  ${esc(String(t.form || '').replace('_', ' '))}${(t.stages || []).length
                    ? ' · ' + esc(String(t.stages.length)) + ' stages' : ''}
                </div>
                <div style="display:flex;gap:6px;margin-top:11px;flex-wrap:wrap">
                  <button type="button" class="btn-sm" data-act-click="icmwsUseTemplate(${arg(t.template_id)})">Use this</button>
                  ${t.builtin ? ''
                    : `<button type="button" class="btn-sm" data-act-click="icmwsDeleteTemplate(${arg(t.template_id)})">Delete</button>`}
                </div>
              </div>`).join('')}
          </div>

          <div style="margin-top:26px;padding-top:18px;border-top:1px solid var(--border-0)">
            <div style="font-weight:700;font-size:14px">Extract a template from a workspace</div>
            <div style="font-size:12.5px;color:var(--text-2);margin:5px 0 10px">
              Keeps the stage contracts and reference material; drops every output file.
              Your workspace is not modified.
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
              <select id="icm-tpl-src"
                style="padding:9px 11px;background:var(--bg-1);color:var(--text-0);
                       border:1px solid var(--border-0);border-radius:7px;font-size:13px">
                ${wsList.map((w) => `<option value="${esc(w.workspace_id)}">${esc(w.name)}</option>`).join('')}
              </select>
              <input id="icm-tpl-name" type="text" placeholder="template name"
                style="width:190px;padding:9px 11px;background:var(--bg-1);color:var(--text-0);
                       border:1px solid var(--border-0);border-radius:7px;font-size:13px">
              <button type="button" class="btn" data-act-click="icmwsExtractTemplate()">Extract</button>
            </div>
            <div id="icm-tpl-note" style="font-size:12.5px;color:var(--text-2);margin-top:10px"></div>
          </div>
        </div>
      </div>`;
}
async function icmwsUseTemplate(templateId) {
const name = window.prompt('Name for the new workspace');
if (!name || !name.trim()) return;
try {
const d = await api('/api/icm/templates/' + encodeURIComponent(templateId) + '/instantiate', {
method: 'POST',
headers: {'Content-Type': 'application/json'},
body: JSON.stringify({workspace_id: name.trim(), name: name.trim()}),
});
await loadWorkspaces();
currentWs = d.workspace.workspace_id;
currentFile = '';
icmwsTab('folders');
} catch (e) {
window.alert('Could not create it: ' + e.message);
}
}
async function icmwsDeleteTemplate(templateId) {
if (!window.confirm('Delete the template ' + templateId + '? Workspaces made from it are unaffected.')) return;
try {
await api('/api/icm/templates/' + encodeURIComponent(templateId), {method: 'DELETE'});
renderIcmTemplates();
} catch (e) {
window.alert(e.message);
}
}
async function icmwsExtractTemplate() {
const src = document.getElementById('icm-tpl-src');
const nameEl = document.getElementById('icm-tpl-name');
const note = document.getElementById('icm-tpl-note');
if (!src || !src.value) return;
const name = ((nameEl || {}).value || '').trim();
if (!name) { if (note) note.textContent = 'Give the template a name first.'; return; }
if (note) note.textContent = 'Extracting…';
try {
const d = await api('/api/icm/templates/extract', {
method: 'POST',
headers: {'Content-Type': 'application/json'},
body: JSON.stringify({
workspace_id: src.value,
name: name,
template_id: name.toLowerCase().replace(/[^a-z0-9]+/g, '-')
.replace(/^-+|-+$/g, '').slice(0, 48),
}),
});
const dropped = (d.dropped_instance_files || []).length;
const msg = `Extracted ${d.copied} method files`
+ (dropped ? `, left ${dropped} output file${dropped === 1 ? '' : 's'} behind.` : '.');
await renderIcmTemplates();
const fresh = document.getElementById('icm-tpl-note');
if (fresh) fresh.textContent = msg;
} catch (e) {
if (note) note.textContent = 'Could not extract: ' + e.message;
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
let lastAnalysis = null;
let _forms = [];
function unitNoun(formId) {
const f = (_forms || []).find((x) => x.id === formId);
return (f && f.unit_noun) || 'stage';
}
async function loadForms() {
if (_forms.length) return;
try { _forms = (await api('/api/icm/forms')).forms || []; } catch (e) { _forms = []; }
}
const SAMPLE = "Every week I put out a newsletter. First I go through the "
+ "week's links and pull out the three or four worth writing about. Then I "
+ "draft the issue in my own voice \u2014 it always has to sound conversational. "
+ "I always read it out loud and check the links before it goes out. "
+ "Finally I schedule it for Tuesday morning.";
async function renderDescribe() {
const body = document.getElementById('icm-body');
if (!body) return;
await loadForms();
body.innerHTML = `
      <div style="flex:1;overflow-y:auto;padding:22px 26px">
        <div style="max-width:860px">
          <div style="font-weight:700;font-size:15px">Describe your work</div>
          <div style="font-size:12.5px;color:var(--text-2);margin:6px 0 14px">
            In your own words, walk through one run start to finish. Where do you stop and
            check something? What has to stay the same every time? You do not need to know
            anything about the methodology &mdash; the shape you already work in gets named
            back to you, and you can correct it before anything is created.
          </div>
          <textarea id="icm-desc" spellcheck="false" placeholder="${esc(SAMPLE)}"
            style="width:100%;min-height:170px;background:var(--bg-1);color:var(--text-0);
                   border:1px solid var(--border-0);border-radius:10px;padding:14px;
                   font-size:13.5px;line-height:1.6;resize:vertical"></textarea>
          <div style="display:flex;gap:8px;margin-top:10px;align-items:center">
            <button type="button" class="btn" data-act-click="icmwsAnalyse()">Find the structure</button>
            <button type="button" class="btn-sm" data-act-click="icmwsSample()">Use the example</button>
          </div>
          <div id="icm-desc-out" style="margin-top:18px"></div>
        </div>
      </div>`;
}
function icmwsSample() {
const ta = document.getElementById('icm-desc');
if (ta) { ta.value = SAMPLE; icmwsAnalyse(); }
}
async function icmwsAnalyse() {
const ta = document.getElementById('icm-desc');
const out = document.getElementById('icm-desc-out');
if (!ta || !out) return;
if (!ta.value.trim()) { out.innerHTML = ''; return; }
out.innerHTML = '<div style="color:var(--text-2);font-size:13px">Reading\u2026</div>';
try {
const a = await api('/api/icm/describe', {
method: 'POST',
headers: {'Content-Type': 'application/json'},
body: JSON.stringify({text: ta.value}),
});
lastAnalysis = a;
if (!a.recommend_workspace) {
out.innerHTML = `
          <div style="border:1px solid var(--warning);border-radius:10px;padding:14px 16px">
            <div style="font-weight:700;font-size:13.5px;color:var(--warning)">
              A workspace may be more than this needs</div>
            <div style="font-size:13px;margin-top:6px;line-height:1.5">${esc(a.advice)}</div>
            ${(a.follow_up || []).length ? `<div style="margin-top:10px;font-size:12.5px;color:var(--text-2)">
              ${a.follow_up.map((q) => '&bull; ' + esc(q)).join('<br>')}</div>` : ''}
          </div>`;
return;
}
out.innerHTML = `
        <div style="border:1px solid var(--border-0);border-radius:10px;padding:16px 18px">
          <div style="font-weight:700;font-size:14px">${esc(a.form.label)}</div>
          <div style="font-size:12.5px;color:var(--text-2);margin-top:4px">
            ${esc(a.form.why)}${a.form.confident ? '' : ' (low confidence &mdash; change it if this is wrong)'}
          </div>
          <div style="margin-top:10px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">
            <span style="font-size:12px;color:var(--text-2)">Repeating unit:</span>
            <select id="icm-form-pick"
              style="padding:7px 10px;background:var(--bg-1);color:var(--text-0);
                     border:1px solid var(--border-0);border-radius:6px;font-size:12.5px">
              ${(_forms || []).map((f) => `<option value="${esc(f.id)}"
                ${f.id === a.form.form ? 'selected' : ''}>${esc(f.label)} &mdash; ${esc(f.unit)}</option>`).join('')}
            </select>
          </div>

          <div id="icm-unit-label" style="margin-top:16px;font-size:11px;font-weight:800;letter-spacing:0.5px;color:var(--text-2)">
            ${esc(unitNoun(a.form.form).toUpperCase())}S &mdash; edit these before creating</div>
          <div id="icm-stage-rows" style="margin-top:8px">
            ${a.stages.map((s, i) => `
              <div style="display:flex;gap:10px;align-items:center;padding:6px 0">
                <span style="font-size:11.5px;color:var(--text-2);min-width:24px">
                  ${String(i + 1).padStart(2, '0')}</span>
                <input type="text" class="icm-stage-in" value="${esc(s.name)}"
                  style="width:170px;padding:7px 10px;background:var(--bg-1);color:var(--text-0);
                         border:1px solid var(--border-0);border-radius:6px;font-size:12.5px">
                <span style="flex:1;font-size:12px;color:var(--text-2);overflow:hidden;
                             text-overflow:ellipsis;white-space:nowrap" title="${esc(s.said)}">
                  ${esc(s.why)} &mdash; &ldquo;${esc(s.said)}&rdquo;</span>
              </div>`).join('')}
          </div>

          ${(a.human_gates || []).length ? `
            <div style="margin-top:14px;font-size:11px;font-weight:800;letter-spacing:0.5px;color:var(--text-2)">
              HUMAN CHECKS</div>
            ${a.human_gates.map((g) => `<div style="font-size:12.5px;padding:3px 0">
              &ldquo;${esc(g.said)}&rdquo;
              <span style="color:var(--text-2)">&rarr; ${esc(g.becomes)}</span></div>`).join('')}` : ''}

          ${(a.factory || []).length ? `
            <div style="margin-top:14px;font-size:11px;font-weight:800;letter-spacing:0.5px;color:var(--text-2)">
              STAYS THE SAME EVERY RUN</div>
            ${a.factory.map((f) => `<div style="font-size:12.5px;padding:3px 0">
              &ldquo;${esc(f.said)}&rdquo;
              <span style="color:var(--text-2)">&rarr; ${esc(f.becomes)}</span></div>`).join('')}` : ''}

          <div style="display:flex;gap:10px;align-items:center;margin-top:18px;flex-wrap:wrap">
            <input id="icm-desc-name" type="text" placeholder="workspace name"
              style="width:200px;padding:9px 11px;background:var(--bg-1);color:var(--text-0);
                     border:1px solid var(--border-0);border-radius:7px;font-size:13px">
            <button type="button" class="btn" data-act-click="icmwsCreateFromDesc()">Create workspace</button>
            <span style="font-size:12px;color:var(--text-2)">Nothing has been created yet.</span>
          </div>
          ${(a.follow_up || []).length ? `
            <div style="margin-top:12px;font-size:12px;color:var(--text-2)">
              Worth answering: ${a.follow_up.map((q) => esc(q)).join(' &middot; ')}</div>` : ''}
          <div id="icm-desc-created" style="margin-top:10px"></div>
        </div>`;
const pick = document.getElementById('icm-form-pick');
if (pick) {
pick.addEventListener('change', () => {
const lbl = document.getElementById('icm-unit-label');
if (lbl) {
lbl.textContent = unitNoun(pick.value).toUpperCase() + 'S — edit these before creating';
}
});
}
} catch (e) {
out.innerHTML = `<div style="color:var(--danger);font-size:13px">${esc(e.message)}</div>`;
}
}
async function icmwsCreateFromDesc() {
const ta = document.getElementById('icm-desc');
const nameEl = document.getElementById('icm-desc-name');
const out = document.getElementById('icm-desc-created');
if (!ta || !out || !lastAnalysis) return;
const name = ((nameEl || {}).value || '').trim();
if (!name) { out.innerHTML = '<div style="color:var(--warning);font-size:13px">Give it a name first.</div>'; return; }
const stages = Array.from(document.querySelectorAll('.icm-stage-in'))
.map((el) => el.value.trim()).filter(Boolean);
out.innerHTML = '<div style="color:var(--text-2);font-size:13px">Creating\u2026</div>';
try {
const d = await api('/api/icm/describe/create', {
method: 'POST',
headers: {'Content-Type': 'application/json'},
body: JSON.stringify({
text: ta.value, name: name, stages: stages,
form: ((document.getElementById('icm-form-pick') || {}).value) || undefined,
}),
});
const wf = d.workspace.form || 'pipeline';
const noun = unitNoun(wf);
const built = ['stages', 'records', 'layers', 'pipelines', 'teams', 'objects']
.map((k) => (d.workspace[k] || []).length)
.reduce((a, n) => (a || n), 0);
out.innerHTML = `<div style="font-size:13px">
        Created <b>${esc(d.workspace.name)}</b> &mdash; ${esc(String(built))}
        ${esc(noun)}${built === 1 ? '' : 's'}.
        <button type="button" class="btn-sm" style="margin-left:8px"
          data-act-click="icmwsTab('folders')">Open it</button></div>`;
await loadWorkspaces();
currentWs = d.workspace.workspace_id;
} catch (e) {
out.innerHTML = `<div style="color:var(--danger);font-size:13px">${esc(e.message)}</div>`;
}
}
let auditPlan = null;
function renderAudit() {
const body = document.getElementById('icm-body');
if (!body) return;
body.innerHTML = `
      <div style="flex:1;overflow-y:auto;padding:22px 26px">
        <div style="max-width:900px">
          <div style="font-weight:700;font-size:15px">Audit an existing folder</div>
          <div style="font-size:12.5px;color:var(--text-2);margin:6px 0 16px">
            Point this at a folder you already have. It reads every file, sorts each one by
            role, and shows you a migration map — then waits for your yes. Nothing moves
            until you approve, and nothing is ever deleted.
          </div>
          <div style="display:flex;gap:8px">
            <input id="icm-audit-path" type="text" value="." placeholder="folder path"
              style="flex:1;padding:11px 13px;background:var(--bg-1);color:var(--text-0);
                     border:1px solid var(--border-0);border-radius:8px;font-size:13px">
            <button type="button" class="btn" data-act-click="icmwsSystemMap()">Map it</button>
            <button type="button" class="btn" data-act-click="icmwsPlan()">Plan migration</button>
          </div>
          <div id="icm-audit-out" style="margin-top:18px"></div>
        </div>
      </div>`;
}
function pathVal() {
return ((document.getElementById('icm-audit-path') || {}).value || '.').trim() || '.';
}
const ROLE_COLOURS = {
catalog: 'var(--accent-text)', contract: 'var(--accent-text)',
factory: 'var(--text-0)', product: 'var(--text-2)', dead: 'var(--warning)',
};
async function icmwsSystemMap() {
const out = document.getElementById('icm-audit-out');
if (!out) return;
out.innerHTML = '<div style="color:var(--text-2);font-size:13px">Walking the tree…</div>';
try {
const d = await api('/api/icm/restructure/system-map?limit=30&path='
+ encodeURIComponent(pathVal()));
out.innerHTML = `
        <div style="font-weight:700;font-size:14px">System map — ${esc(String(d.file_count))} files</div>
        <div style="font-size:12px;color:var(--text-2);margin:4px 0 12px">
          Index cards, not a 40-page report. "Hits" is first-order only: what a change here
          touches next, not everything downstream.
          ${d.truncated ? ' <b>Tree was large; scan was capped.</b>' : ''}
        </div>
        ${(d.cards || []).map((c) => `
          <div style="border:1px solid var(--border-0);border-radius:10px;padding:12px 14px;margin-bottom:10px">
            <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
              <div style="font-weight:700;font-size:13.5px">${esc(c.noun)}</div>
              <span style="font-size:10.5px;font-weight:800;letter-spacing:0.5px;
                color:${c.universe === 'live' ? 'var(--accent-text)' : 'var(--warning)'}">
                ${esc(String(c.universe).toUpperCase())}</span>
              <span style="font-size:11.5px;color:var(--text-2)">${esc(String(c.files))} files</span>
              ${c.ghost ? `<span style="font-size:11.5px;color:var(--warning)">
                  ${esc(String(c.ghost))} ghost</span>` : ''}
              ${c.leftover ? `<span style="font-size:11.5px;color:var(--text-2)">
                  ${esc(String(c.leftover))} leftover</span>` : ''}
            </div>
            <div style="font-size:12px;color:var(--text-2);margin-top:6px">
              Roles: ${esc(Object.entries(c.roles || {}).map((e) => e[0] + ' ' + e[1]).join(', '))}
            </div>
            <div style="font-size:12px;margin-top:5px">
              <b>If you change this it hits:</b>
              ${(c.hits || []).length ? esc(c.hits.join(', '))
                : '<span style="color:var(--text-2)">nothing else first-order</span>'}
            </div>
          </div>`).join('')}`;
} catch (e) {
out.innerHTML = `<div style="color:var(--danger);font-size:13px">${esc(e.message)}</div>`;
}
}
async function icmwsPlan() {
const out = document.getElementById('icm-audit-out');
if (!out) return;
out.innerHTML = '<div style="color:var(--text-2);font-size:13px">Classifying…</div>';
try {
const d = await api('/api/icm/restructure/plan', {
method: 'POST',
headers: {'Content-Type': 'application/json'},
body: JSON.stringify({path: pathVal()}),
});
auditPlan = d.plan;
const p = auditPlan;
out.innerHTML = `
        <div style="font-weight:700;font-size:14px">Migration plan — ${esc(String(p.file_count))} files</div>
        <div style="font-size:12px;color:var(--text-2);margin:4px 0 10px">
          Plan <code>${esc(p.plan_id)}</code>. Read it before approving.
          Files are <b>copied</b> into <code>_icm-restructured/</code>; the originals stay put.
        </div>
        <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:12px">
          ${Object.entries(p.by_role || {}).map((e) => `
            <div><span style="font-weight:700;color:${ROLE_COLOURS[e[0]] || 'var(--text-0)'}">
              ${esc(String(e[1]))}</span>
              <span style="font-size:12px;color:var(--text-2)"> ${esc(e[0])}</span></div>`).join('')}
        </div>
        <div style="max-height:340px;overflow-y:auto;border:1px solid var(--border-0);border-radius:8px">
          ${(p.moves || []).slice(0, 300).map((m) => `
            <div style="display:flex;gap:10px;padding:7px 12px;border-bottom:1px solid var(--border-0);font-size:12px">
              <span style="min-width:64px;font-weight:700;color:${ROLE_COLOURS[m.role] || 'var(--text-0)'}">
                ${esc(m.role)}</span>
              <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
                title="${esc(m.why)}">${esc(m.from)}</span>
              <span style="color:var(--text-2)">→</span>
              <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(m.to)}</span>
            </div>`).join('')}
        </div>
        <div style="display:flex;align-items:center;gap:12px;margin-top:14px">
          <button type="button" class="btn" data-act-click="icmwsApply()">
            Approve and copy ${esc(String((p.moves || []).length))} files</button>
          <span style="font-size:12px;color:var(--text-2)">Nothing has been written yet.</span>
        </div>
        <div id="icm-apply-out" style="margin-top:12px"></div>`;
} catch (e) {
out.innerHTML = `<div style="color:var(--danger);font-size:13px">${esc(e.message)}</div>`;
}
}
async function icmwsApply() {
const out = document.getElementById('icm-apply-out');
if (!out || !auditPlan) return;
if (!window.confirm(
'Copy ' + (auditPlan.moves || []).length + ' files into _icm-restructured/?\n\n'
+ 'Your original files are not moved, changed or deleted.')) return;
out.innerHTML = '<div style="color:var(--text-2);font-size:13px">Copying…</div>';
try {
const d = await api('/api/icm/restructure/apply', {
method: 'POST',
headers: {'Content-Type': 'application/json'},
body: JSON.stringify({plan_id: auditPlan.plan_id, approved: true}),
});
out.innerHTML = `<div style="font-size:13px">
        Copied <b>${esc(String(d.copied))}</b> files to <code>${esc(d.destination)}</code>.
        ${(d.skipped || []).length ? ' Skipped ' + esc(String(d.skipped.length)) + '.' : ''}
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
window.icmwsAnalyse = icmwsAnalyse;
window.icmwsSample = icmwsSample;
window.icmwsCreateFromDesc = icmwsCreateFromDesc;
window.icmwsUseTemplate = icmwsUseTemplate;
window.icmwsDeleteTemplate = icmwsDeleteTemplate;
window.icmwsExtractTemplate = icmwsExtractTemplate;
window.icmwsSystemMap = icmwsSystemMap;
window.icmwsPlan = icmwsPlan;
window.icmwsApply = icmwsApply;
window.PANE_RENDERERS = window.PANE_RENDERERS || {};
window.PANE_RENDERERS['icm'] = renderWorkspacesIcmPane;
})();
