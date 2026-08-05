// Agentic OS — Plugin Marketplace (quote-collision fixed with data-* + delegated listeners)
let pluginRegistry = [], pluginInstalled = new Set();

async function renderPlugins() {
  const pane = document.getElementById('pane-plugins');
  if (!pane) return;
  pane.innerHTML = `<div class="section-head">
    <div><h2>🧩 Plugin Marketplace</h2><p>Install skill packs, agent personas, and tool collections. One click to unlock new capabilities.</p></div>
    <div style="display:flex;gap:8px">
      <button data-act-click="showInstallFromUrl()" class="btn btn-ghost btn-sm">🔗 Install from URL</button>
      <button data-act-click="exportWorkspaceData()" class="btn btn-ghost btn-sm">📤 Export Workspace</button>
      <button data-act-click="showImportWorkspace()" class="btn btn-ghost btn-sm">📥 Import</button>
    </div>
  </div>
  <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap" id="plugin-cats"></div>
  <div id="plugin-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px">
    <div style="color:var(--text-2)">Loading marketplace…</div>
  </div>`;
  await loadPluginRegistry();
}

async function loadPluginRegistry() {
  try {
    const [regR, instR] = await Promise.all([
      fetch('/api/plugins/registry'), fetch('/api/plugins/installed')
    ]);
    if (!regR.ok) throw new Error('Registry API error ' + regR.status);
    if (!instR.ok) throw new Error('Installed API error ' + instR.status);
    const regData = await regR.json();
    const instData = await instR.json();
    pluginRegistry = Array.isArray(regData) ? regData : (Array.isArray(regData?.plugins) ? regData.plugins : []);
    const installed = Array.isArray(instData) ? instData : (Array.isArray(instData?.installed) ? instData.installed : []);
    pluginInstalled = new Set(installed.map(p => p.id));
    renderPluginGrid();
    renderPluginCats();
  } catch(e) { console.warn('Failed to load plugins:', e); toast('Failed to load plugins: ' + e.message, 'err'); }
}

function renderPluginCats() {
  const el = document.getElementById('plugin-cats');
  if (!el) return;
  const cats = [...new Set(pluginRegistry.map(p => p.category))];
  el.innerHTML = cats.map(c =>
    `<span class="tag" style="cursor:pointer;padding:5px 12px" data-plugin-cat="${escHtml(c)}">${escHtml(c)}</span>`
  ).join('');
  el.querySelectorAll('[data-plugin-cat]').forEach(btn => {
    btn.addEventListener('click', () => {
      const cat = btn.dataset.pluginCat;
      const filtered = cat ? pluginRegistry.filter(p => p.category === cat) : pluginRegistry;
      renderPluginGrid(filtered);
    });
  });
}

function renderPluginGrid(list = pluginRegistry) {
  const grid = document.getElementById('plugin-grid');
  if (!grid) return;
  grid.innerHTML = list.map(p => {
    const installed = pluginInstalled.has(p.id);
    return `<div style="background:var(--bg-2);border:1px solid ${installed?'var(--accent)':'var(--border)'};border-radius:var(--radius-lg);padding:18px;transition:var(--transition)"
         data-plugin-id="${escHtml(p.id)}"
         data-plugin-name="${escHtml(p.name)}"
         data-hover="bc:var(--border-hi)" data-hover-out="bc:${installed?'var(--accent)':'var(--border)'}">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <span style="font-size:28px">${p.emoji||'🧩'}</span>
        <div style="flex:1;min-width:0">
          <div style="font-weight:800;font-size:15px">${escHtml(p.name)}</div>
          <div style="font-size:11px;color:var(--text-2)">by ${escHtml(p.author||'Community')} · v${p.version||'1.0'}</div>
        </div>
        ${installed ? `<span class="tag green">Installed</span>` : ''}
      </div>
      <p style="font-size:12.5px;color:var(--text-2);line-height:1.5;margin-bottom:12px;min-height:36px">${escHtml(p.description||'')}</p>
      <div style="display:flex;align-items:center;justify-content:space-between">
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          <span class="tag">${p.category}</span>
          <span class="tag">${p.skill_count||p.skills?.length||0} skills</span>
        </div>
        ${installed
          ? `<button class="btn btn-ghost btn-sm btn-uninstall" data-uninstall-id="${escHtml(p.id)}" data-uninstall-name="${escHtml(p.name)}" style="color:var(--red)">Uninstall</button>`
          : `<button class="btn btn-primary btn-sm btn-install" data-install-id="${escHtml(p.id)}" id="install-btn-${escHtml(p.id)}">Install</button>`
        }
      </div>
    </div>`;
  }).join('') || '<div style="color:var(--text-3)">No plugins found.</div>';

  grid.querySelectorAll('.btn-install').forEach(btn => {
    btn.addEventListener('click', () => installPlugin(btn.dataset.installId));
  });
  grid.querySelectorAll('.btn-uninstall').forEach(btn => {
    btn.addEventListener('click', () => uninstallPlugin(btn.dataset.uninstallId, btn.dataset.uninstallName));
  });
}

async function installPlugin(pluginId) {
  const btn = document.getElementById(`install-btn-${pluginId}`);
  if (btn) { btn.disabled = true; btn.textContent = '⏳…'; }
  const r = await fetch(`/api/plugins/install/${encodeURIComponent(pluginId)}`, { method:'POST' });
  if (!r.ok) {
    toast('Install failed: server error ' + r.status, 'err');
    if (btn) { btn.disabled = false; btn.textContent = 'Install'; }
    return;
  }
  const j = await r.json();
  if (j.ok) {
    toast(`🧩 ${j.plugin} installed — ${j.skills_added} skills added to Skills Hub`, 'ok', 5000);
    loadPluginRegistry();
    fetch('/api/skills').then(r=>r.ok?r.json().catch(()=>{}):[]).then(s => { allSkills = s||[]; }).catch(()=>{});
  } else {
    toast(j.error || 'Install failed', j.installed ? 'warn' : 'err');
    if (btn) { btn.disabled = false; btn.textContent = 'Install'; }
  }
}

async function uninstallPlugin(pluginId, name) {
  if (!(await gmDanger('Uninstall Plugin', `Remove "${name}" and all its skills?`))) return;
  try {
    const r = await fetch(`/api/plugins/uninstall/${encodeURIComponent(pluginId)}`, { method:'DELETE' });
    if (!r.ok) { toast('Uninstall failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast('🗑 Plugin uninstalled', 'ok'); loadPluginRegistry(); }
    else toast('Uninstall failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('Uninstall error: ' + ex.message, 'err'); }
}

async function showInstallFromUrl() {
  const url = await gmPrompt('Install from URL', 'GitHub raw URL or any JSON plugin URL', 'https://raw.githubusercontent.com/…/plugin.json');
  if (!url) return;
  toast('⏳ Fetching plugin…', 'ok', 2000);
  try {
    const r = await fetch('/api/plugins/install/url', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ url })
    });
    if (!r.ok) { toast('Install failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast(`🧩 Plugin installed — ${j.skills_added} skills added`, 'ok', 4000); loadPluginRegistry(); }
    else toast('Error: ' + (j.error||''), 'err');
  } catch(ex) { toast('Install error: ' + ex.message, 'err'); }
}
window.renderPlugins = renderPlugins;
window.loadPluginRegistry = loadPluginRegistry;
window.installPlugin = installPlugin;
window.uninstallPlugin = uninstallPlugin;
window.renderPluginGrid = renderPluginGrid;
// `window.filterPlugins = filterPlugins` referenced a function that does not
// exist anywhere in the codebase, so this line threw ReferenceError on EVERY
// page load and aborted the rest of the module. Only function hoisting kept
// the exports below it working -- any `const`/`let` added after this point
// would have been silently missing. Nothing calls filterPlugins, so the dead
// export is removed rather than a stub invented for it.
// (Found by a real browser: jsdom never executed this file.)
window.showInstallFromUrl = showInstallFromUrl;

async function exportWorkspaceData() {
  toast('⏳ Exporting…', 'ok', 1500);
  const r = await fetch('/api/plugins/export');
  if (!r.ok) { toast('Export failed: server error ' + r.status, 'err'); return; }
  const j = await r.json();
  if (j.ok === false) { toast('Export failed: ' + (j.error||''), 'err'); return; }
  const blob = new Blob([JSON.stringify(j, null, 2)], { type: 'application/json' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = `agentic-os-workspace-${new Date().toISOString().slice(0,10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
  toast(`📤 Exported ${j.agents?.length} agents, ${j.skills?.length} skills, ${j.memories?.length} memories`, 'ok', 4000);
}

async function showImportWorkspace() {
  const json_str = await gmPrompt('Import Workspace', 'Paste your exported workspace JSON here', '', true);
  if (!json_str) return;
  try {
    const data = JSON.parse(json_str);
    const r = await fetch('/api/plugins/import', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ workspace: data })
    });
    if (!r.ok) { toast('Import failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) {
      const i = j.imported;
      toast(`📥 Imported: ${i.agents} agents, ${i.skills} skills, ${i.memories} memories`, 'ok', 5000);
      loadAgents();
    } else toast('Import failed', 'err');
  } catch(e) { toast('Invalid JSON: ' + e.message, 'err'); }
}
