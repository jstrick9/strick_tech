
;/* 34-plugin-hub.js */
let hubCatalog = [];
let hubCollections = [];
let hubTab = 'discover';
let hubCategory = '';
let hubQuery = '';
async function renderPluginHub() {
const pane = document.getElementById('pane-plugins');
if (!pane) return;
pane.innerHTML = `<div class="section-head">
    <div>
      <h2>🧩 Plugin Hub</h2>
      <p>Add ready-made skills to your agents. One click to install — no configuration.</p>
    </div>
    <div style="display:flex;gap:8px">
      <button data-act-click="hubShowInstallCustom()" class="btn btn-ghost btn-sm">＋ Add custom</button>
    </div>
  </div>
  <div id="hub-stats" style="display:flex;gap:10px;margin-bottom:14px;flex-wrap:wrap"></div>
  <div style="display:flex;gap:8px;margin-bottom:14px;align-items:center;flex-wrap:wrap">
    <button data-act-click="hubSetTab('discover')" id="hub-tab-discover" class="btn btn-sm ${hubTab==='discover'?'btn-primary':'btn-ghost'}">✨ Discover</button>
    <button data-act-click="hubSetTab('installed')" id="hub-tab-installed" class="btn btn-sm ${hubTab==='installed'?'btn-primary':'btn-ghost'}">📥 Installed</button>
    <input id="hub-search" placeholder="Search plugins…" value="${escHtml(hubQuery)}"
           style="flex:1;min-width:180px;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 11px;color:var(--text-0);font-size:13px;outline:none">
  </div>
  <div id="hub-body"><div style="color:var(--text-2);padding:20px">Loading…</div></div>
  <div id="hub-drawer"></div>`;
const search = document.getElementById('hub-search');
if (search) {
let t = null;
search.addEventListener('input', e => {
hubQuery = e.target.value;
clearTimeout(t);
t = setTimeout(() => hubRenderBody(), 180);
});
}
await hubLoad();
}
async function hubLoad() {
try {
const [catR, colR, stR] = await Promise.all([
fetch('/api/hub/catalog'),
fetch('/api/hub/collections'),
fetch('/api/hub/stats'),
]);
if (!catR.ok) throw new Error('catalog ' + catR.status);
const cat = await catR.json();
hubCatalog = cat.items || [];
hubCollections = colR.ok ? (await colR.json()).collections || [] : [];
const stats = stR.ok ? await stR.json() : null;
hubRenderStats(stats);
hubRenderBody();
} catch (ex) {
const b = document.getElementById('hub-body');
if (b) b.innerHTML = `<div style="color:var(--red);padding:16px">Could not load the plugin hub: ${escHtml(ex.message)}</div>`;
}
}
function hubRenderStats(s) {
const el = document.getElementById('hub-stats');
if (!el || !s) return;
const chip = (label, value) =>
`<div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 14px">
       <div class="u-80b90e3a">${value}</div>
       <div style="font-size:11px;color:var(--text-2)">${escHtml(label)}</div>
     </div>`;
el.innerHTML =
chip('Plugins available', s.total_packs) +
chip('Installed', s.installed_packs) +
chip('Skills ready to use', s.installed_skills) +
chip('Categories', s.categories);
}
function hubSetTab(tab) {
hubTab = tab;
['discover', 'installed'].forEach(t => {
const b = document.getElementById('hub-tab-' + t);
if (b) b.className = 'btn btn-sm ' + (t === tab ? 'btn-primary' : 'btn-ghost');
});
hubRenderBody();
}
function hubFiltered() {
const q = hubQuery.trim().toLowerCase();
return hubCatalog.filter(p => {
if (hubTab === 'installed' && !p.installed) return false;
if (hubCategory && p.category !== hubCategory) return false;
if (!q) return true;
return (p.name + ' ' + p.description + ' ' + (p.tags || []).join(' ')).toLowerCase().includes(q);
});
}
function hubRenderBody() {
const el = document.getElementById('hub-body');
if (!el) return;
const items = hubFiltered();
const showCollections = hubTab === 'discover' && !hubQuery.trim() && !hubCategory && hubCollections.length;
const cats = [...new Set(hubCatalog.map(p => p.category))].filter(Boolean).sort();
const catBar = `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px">
      <span data-act-click="hubSetCategory('')" class="tag" style="cursor:pointer;padding:4px 11px;${!hubCategory?'background:var(--accent-glow);color:var(--accent-hi)':''}" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">All</span>
      ${cats.map(c => `<span data-act-click="hubSetCategory(${jsArg(c)})" class="tag" style="cursor:pointer;padding:4px 11px;${hubCategory===c?'background:var(--accent-glow);color:var(--accent-hi)':''}" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">${escHtml(c)}</span>`).join('')}
    </div>`;
el.innerHTML = `
    ${showCollections ? hubCollectionsHtml() : ''}
    ${catBar}
    ${items.length ? `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:14px">
      ${items.map(hubCardHtml).join('')}
    </div>` : `<div style="color:var(--text-3);padding:24px;text-align:center">
        ${hubTab === 'installed'
          ? 'No plugins installed yet. Switch to <b>Discover</b> and pick a starter collection.'
          : 'No plugins match that search.'}
      </div>`}`;
}
function hubSetCategory(c) {
hubCategory = c;
hubRenderBody();
}
function hubCollectionsHtml() {
return `<div class="u-49f14f8f">
    <div class="u-a848666e">Start here</div>
    <div style="font-size:12px;color:var(--text-2);margin-bottom:10px">Curated bundles — installs every plugin in the set.</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px">
      ${hubCollections.map(c => {
        const done = c.installed_count >= c.available && c.available > 0;
        return `<div style="background:var(--bg-2);border:1px solid ${c.recommended?'var(--accent)':'var(--border)'};border-radius:var(--radius-lg);padding:14px">
          <div class="u-881f70f9">${c.icon}</div>
          <div style="font-weight:700;margin-top:4px">${escHtml(c.name)}</div>
          <div style="font-size:12px;color:var(--text-2);line-height:1.45;margin:4px 0 10px;min-height:34px">${escHtml(c.description)}</div>
          <div style="font-size:11px;color:var(--text-3);margin-bottom:8px">${c.available} plugin(s) · ${c.skill_total} skills · ${c.installed_count} installed</div>
          <button ${done ? 'disabled' : ''} data-collection="${escHtml(c.id)}"
                  data-act-click="hubInstallCollection($data.collection)"
                  class="btn btn-sm ${done?'btn-ghost':'btn-primary'}" style="width:100%">
            ${done ? '✓ All installed' : 'Install set'}
          </button>
        </div>`;
      }).join('')}
    </div>
  </div>`;
}
function hubCardHtml(p) {
return `<div style="background:var(--bg-2);border:1px solid ${p.installed?'var(--accent)':'var(--border)'};border-radius:var(--radius-lg);padding:16px;display:flex;flex-direction:column">
    <div style="display:flex;align-items:flex-start;gap:10px;margin-bottom:8px">
      <span style="font-size:26px;line-height:1">${p.icon || '🧩'}</span>
      <div class="u-59eddc67">
        <div style="font-weight:700;font-size:14.5px;display:flex;align-items:center;gap:5px">
          ${escHtml(p.name)}
          ${p.verified ? '<span title="Verified publisher" style="color:var(--accent-text)">✓</span>' : ''}
        </div>
        <div style="font-size:11px;color:var(--text-3)">by ${escHtml(p.author)} · v${escHtml(p.version)}</div>
      </div>
      ${p.installed ? '<span class="tag green u-0d5be05f" >Installed</span>' : ''}
    </div>
    <p style="font-size:12.5px;color:var(--text-2);line-height:1.5;margin:0 0 10px;flex:1">${escHtml(p.description)}</p>
    <div style="display:flex;align-items:center;gap:6px;font-size:11px;color:var(--text-3);margin-bottom:10px">
      <span class="tag u-0d5be05f" >${escHtml(p.category)}</span>
      <span>${p.skill_count} skill${p.skill_count === 1 ? '' : 's'}</span>
    </div>
    <div style="display:flex;gap:6px">
      <button data-pack="${escHtml(p.id)}" data-act-click="hubShowDetail($data.pack)" class="btn btn-ghost btn-sm u-97445a8d" >Preview</button>
      ${p.installed
        ? `<button data-pack="${escHtml(p.id)}" data-act-click="hubUninstall($data.pack)" class="btn btn-ghost btn-sm">Remove</button>`
        : `<button data-pack="${escHtml(p.id)}" data-act-click="hubInstall($data.pack)" class="btn btn-primary btn-sm u-97445a8d" >Install</button>`}
    </div>
  </div>`;
}
async function hubShowDetail(packId) {
const drawer = document.getElementById('hub-drawer');
if (!drawer) return;
drawer.innerHTML = '<div style="padding:16px;color:var(--text-2)">Loading…</div>';
try {
const r = await fetch(`/api/hub/pack/${encodeURIComponent(packId)}`);
if (!r.ok) { toast('Could not load that plugin', 'err'); drawer.innerHTML = ''; return; }
const d = await r.json();
drawer.innerHTML = `<div data-act-click="hubCloseDetail($event)" id="hub-overlay"
        style="position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:900;display:flex;justify-content:flex-end">
      <div data-stop="1" style="width:min(560px,100%);height:100%;overflow-y:auto;background:var(--bg-1);border-left:1px solid var(--border);padding:22px">
        <div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:6px">
          <span style="font-size:34px">${d.icon || '🧩'}</span>
          <div class="u-97445a8d">
            <div style="font-size:19px;font-weight:800">${escHtml(d.name)}</div>
            <div style="font-size:12px;color:var(--text-3)">by ${escHtml(d.author)} · v${escHtml(d.version)} · ${escHtml(d.category)}</div>
          </div>
          <button data-act-click="hubCloseDetail()" class="btn btn-ghost btn-sm">✕</button>
        </div>
        <p style="font-size:13px;color:var(--text-1);line-height:1.6">${escHtml(d.description)}</p>
        <div style="margin:14px 0">
          ${d.installed
            ? `<button data-pack="${escHtml(d.id)}" data-act-click="hubUninstall($data.pack)" class="btn btn-ghost" style="width:100%">Remove plugin</button>`
            : `<button data-pack="${escHtml(d.id)}" data-act-click="hubInstall($data.pack)" class="btn btn-primary" style="width:100%">Install — adds ${d.skill_count} skill(s)</button>`}
        </div>
        <div style="font-weight:700;font-size:13px;margin:18px 0 8px">What you get</div>
        ${(d.skills || []).length ? (d.skills || []).map(s => `
          <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:12px;margin-bottom:8px">
            <div class="u-160b0675">${s.emoji || '⚡'} ${escHtml(s.name || s.id || '')}</div>
            ${s.description ? `<div style="font-size:12px;color:var(--text-2);margin-top:3px">${escHtml(s.description)}</div>` : ''}
            ${(s.inputs || []).length ? `<div style="font-size:11px;color:var(--text-3);margin-top:6px">Asks for: ${(s.inputs || []).map(i => escHtml(i.label || i.id)).join(', ')}</div>` : ''}
            ${s.prompt_template ? `<details class="u-8a77e5a3">
              <summary style="font-size:11px;color:var(--text-3);cursor:pointer">Show prompt</summary>
              <pre style="white-space:pre-wrap;font-size:11px;color:var(--text-2);background:var(--bg-0);padding:8px;border-radius:4px;margin-top:6px">${escHtml(s.prompt_template)}</pre>
            </details>` : ''}
          </div>`).join('')
          : '<div style="font-size:12px;color:var(--text-3)">This plugin lists no skills.</div>'}
      </div>
    </div>`;
} catch (ex) {
drawer.innerHTML = '';
toast('Error: ' + ex.message, 'err');
}
}
function hubCloseDetail(e) {
if (e && e.target && e.target.id !== 'hub-overlay') return;
const d = document.getElementById('hub-drawer');
if (d) d.innerHTML = '';
}
function hubWarnAfterInstall(name, warnings) {
const list = warnings || [];
if (!list.length) return;
gmAlert(
`⚠️ Installed with ${list.length} safety warning${list.length !== 1 ? 's' : ''}`,
`<div style="font-size:13px;margin-bottom:10px">
       <strong>${escHtml(name || 'This plugin')}</strong> was installed, but its content matched patterns
       that can steer an agent away from your instructions.
     </div>
     <ul style="font-size:12.5px;color:var(--text-2);padding-left:18px;margin:0 0 10px">
       ${list.map(w => `<li style="margin-bottom:4px">${escHtml(w)}</li>`).join('')}
     </ul>
     <div style="font-size:11.5px;color:var(--text-3)">
       Skill runs have no tool or file access, so this cannot execute anything — but the
       agent's answers may be affected. Remove the plugin if you did not expect this.
     </div>`
);
}
async function hubInstall(packId) {
try {
const r = await fetch(`/api/hub/install/${encodeURIComponent(packId)}`, { method: 'POST' });
const j = await r.json().catch(() => null);
if (!r.ok || !j || !j.ok) {
toast('Install failed: ' + ((j && j.error) || ('server error ' + r.status)), 'err');
return;
}
toast(j.warning_count
? `⚠️ Installed with ${j.warning_count} safety warning(s)`
: `✅ ${j.message}`, j.warning_count ? 'warn' : 'ok', j.warning_count ? 5000 : 3000);
hubCloseDetail();
await hubLoad();
if (typeof renderSkills === 'function') { try { renderSkills(); } catch (_) {} }
hubWarnAfterInstall(j.name, j.warnings);
} catch (ex) { toast('Install error: ' + ex.message, 'err'); }
}
async function hubUninstall(packId) {
const pack = hubCatalog.find(p => p.id === packId);
const ok = await gmConfirm('Remove plugin?', `Remove "${pack ? pack.name : packId}" and its skills?`);
if (!ok) return;
try {
const r = await fetch(`/api/hub/uninstall/${encodeURIComponent(packId)}`, { method: 'POST' });
const j = await r.json().catch(() => null);
if (!r.ok || !j || !j.ok) {
toast('Remove failed: ' + ((j && j.error) || ('server error ' + r.status)), 'err');
return;
}
toast('Plugin removed', 'ok', 2000);
hubCloseDetail();
await hubLoad();
} catch (ex) { toast('Remove error: ' + ex.message, 'err'); }
}
async function hubInstallCollection(id) {
toast('Installing set…', 'ok', 1500);
try {
const r = await fetch(`/api/hub/collections/${encodeURIComponent(id)}/install`, { method: 'POST' });
const j = await r.json().catch(() => null);
if (!j) { toast('Install failed: server error ' + r.status, 'err'); return; }
toast(j.ok ? `✅ ${j.message}` : `Partially installed — ${(j.failed || []).length} failed`, j.ok ? 'ok' : 'warn', 3500);
await hubLoad();
if (typeof renderSkills === 'function') { try { renderSkills(); } catch (_) {} }
hubWarnAfterInstall(j.collection, j.warnings);
} catch (ex) { toast('Install error: ' + ex.message, 'err'); }
}
async function hubShowInstallCustom() {
const url = await gmPrompt(
'Add a custom plugin',
'Paste a public URL to a plugin JSON file (GitHub raw links work).',
''
);
if (!url) return;
try {
const r = await fetch('/api/plugins/install/url', {
method: 'POST',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({ url }),
});
const j = await r.json().catch(() => null);
if (!r.ok || !j || !j.ok) {
if (j && j.unsafe && (j.problems || []).length) {
gmAlert('🛑 Plugin refused',
`<div style="font-size:13px;margin-bottom:10px">This plugin was <strong>not installed</strong>. Its templates do things a prompt template has no legitimate reason to do:</div>
           <ul style="font-size:12.5px;color:var(--danger);padding-left:18px;margin:0 0 10px">
             ${(j.problems || []).map(x => `<li style="margin-bottom:4px">${escHtml(x)}</li>`).join('')}
           </ul>
           <div style="font-size:11.5px;color:var(--text-3)">Only plain substitutions such as {topic} are allowed.</div>`);
toast('Plugin refused by the safety check', 'err', 4000);
return;
}
toast('Install failed: ' + ((j && j.error) || ('server error ' + r.status)), 'err', 4000);
return;
}
toast(j.warnings && j.warnings.length
? `⚠️ Installed with ${j.warnings.length} safety warning(s)`
: '✅ Plugin installed', (j.warnings || []).length ? 'warn' : 'ok', 3000);
await hubLoad();
hubWarnAfterInstall(j.plugin || j.name, j.warnings);
} catch (ex) { toast('Install error: ' + ex.message, 'err'); }
}
