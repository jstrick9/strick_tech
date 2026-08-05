// Agentic OS — Workspaces
// Extracted from 01-app-core.js for modularity
// ── Workspaces ─────────────────────────────────────────────────────
async function renderWorkspaces() {
  const pane = document.getElementById('pane-workspaces');
  pane.innerHTML = skeletonPage();
  try {
    const r = await fetch('/api/workspaces');
    if (!r.ok) throw new Error('Workspaces API error ' + r.status);
    const ws = await r.json();
    pane.innerHTML = `
      ${pageHeader({title:'📁 Workspaces', subtitle:'Separate projects — each has its own files, settings, and preview',
        actions:[{label:'Import GitHub',action:'importFromGitHub()'},{label:'Export ZIP',action:'exportCurrentZip()'},{label:'＋ New Project',action:'createNewWorkspace()',primary:true}]})}
      <div class="page-content">
      ${helpPanel({title:'Switch between multiple client projects',body:'Activating a workspace loads its files into Studio instantly. Your current work is auto-saved first.',steps:['Click a workspace card to activate','All files switch automatically','Edit, build, and deploy independently','Export any project as a ZIP']})}
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px">
        ${ws.map(w=>`<div class="card ${w.is_current?'':'card-interactive lift'}" style="${w.is_current?'border-color:var(--accent)':''}">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
            <div style="width:36px;height:36px;border-radius:8px;background:${w.color||'var(--accent)'}22;border:1px solid ${w.color||'var(--accent)'}44;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0">${w.emoji||'📁'}</div>
            <div style="flex:1;min-width:0"><div style="font-weight:700;font-size:13.5px">${escHtml(w.name)}</div>
            <div style="font-size:11px;color:var(--text-2)">${w.file_count||0} files · ${w.framework||'web'}</div></div>
            ${w.is_current?`<span class="badge badge-accent">Active</span>`:''}
          </div>
          <div style="display:flex;gap:6px;flex-wrap:wrap">
            ${w.is_current
              ?`<button data-act-click="exportCurrentZip()" class="btn btn-ghost btn-sm">📦 Export</button>`
              :`<button data-workspace-id="${escHtml(w.id)}" data-workspace-name="${escHtml(w.name)}" data-act-click="activateWorkspace($data.workspaceId,$data.workspaceName)" class="btn btn-primary btn-sm">Switch →</button>
                <button data-workspace-id="${escHtml(w.id)}" data-act-click="exportWorkspace($data.workspaceId)" class="btn btn-ghost btn-sm">📦</button>
                <button data-workspace-id="${escHtml(w.id)}" data-workspace-name="${escHtml(w.name)}" data-act-click="deleteWorkspace($data.workspaceId,$data.workspaceName)" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:11px">🗑</button>`}
          </div>
        </div>`).join('')}
        <div class="card card-interactive" data-act-click="createNewWorkspace()" style="display:flex;align-items:center;justify-content:center;min-height:120px;border-style:dashed;cursor:pointer" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
          <div style="text-align:center;color:var(--text-3)"><div style="font-size:24px;margin-bottom:4px">＋</div><div style="font-size:12.5px">New Project</div></div>
        </div>
      </div>

      <!-- Full app-data Backup / Restore. Wires up a previously-unreachable
           backend feature (backend/routers/workspace_export.py's
           /api/workspace/export, /import, /stats — a complete portable
           JSON archive of agents, chat history, memory, tasks, secrets,
           prompts, and skills) that was fully implemented and registered
           on the server but had ZERO frontend UI anywhere in the app.
           Distinct from the per-project ZIP export above, which only
           captures one workspace's preview/ files, not the shared
           app-wide SQLite database. -->
      <div class="card" style="margin-top:16px">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">
          <span style="font-size:20px">💾</span>
          <div style="font-weight:700;font-size:14px">Full Backup &amp; Restore</div>
        </div>
        <div style="font-size:12px;color:var(--text-2);margin-bottom:12px">Export your entire Agentic OS database — agents, chat history, memory, tasks, prompts, and skills — as one portable JSON file. Restore it here or on another machine.</div>
        <div id="ws-backup-stats" style="font-size:11.5px;color:var(--text-3);margin-bottom:12px">Loading stats…</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          <button data-act-click="exportFullBackup()" class="btn btn-primary btn-sm">💾 Export Full Backup</button>
          <label style="display:inline-flex;align-items:center;gap:5px;font-size:12px;cursor:pointer">
            <input type="checkbox" id="ws-backup-include-secrets">
            <span style="color:var(--text-2)">Include secrets (encrypted)</span>
          </label>
          <button data-act-click="importFullBackupDialog()" class="btn btn-ghost btn-sm">⬆ Restore from Backup</button>
        </div>
      </div>
      </div>`;
    loadBackupStats();
  } catch(e) { pane.innerHTML=`<div class="page-content">${emptyState({icon:'⚠️',title:'Error',body:e.message})}</div>`; }
}

async function loadBackupStats() {
  const el = document.getElementById('ws-backup-stats');
  if (!el) return;
  try {
    const r = await fetch('/api/workspace/stats');
    if (!r.ok) throw new Error('server error ' + r.status);
    const j = await r.json();
    if (!j.ok) throw new Error(j.error || 'stats failed');
    const s = j.stats;
    el.textContent = `${s.agents} agents · ${s.chat_log} messages · ${s.memory} memory entries · ${s.tasks} tasks · ${s.db_size_mb} MB database`;
  } catch(ex) {
    el.textContent = 'Could not load stats: ' + ex.message;
  }
}

async function exportFullBackup() {
  const includeSecrets = document.getElementById('ws-backup-include-secrets')?.checked || false;
  toast('💾 Preparing backup…', 'ok', 2000);
  try {
    const r = await fetch(`/api/workspace/export?include_secrets=${includeSecrets}`);
    if (!r.ok) { toast('Export failed: server error ' + r.status, 'err'); return; }
    const archive = await r.json();
    // Client-side JSON blob download — this data was already fetched via
    // GET, so a synchronous <a download> click right after (no further
    // await in between) is safe in the Tauri WebKit webview.
    const blob = new Blob([JSON.stringify(archive, null, 2)], {type:'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `agentic-os-backup-${new Date().toISOString().slice(0,10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast(`💾 Backup exported — ${archive.summary?.total_rows||0} rows across ${archive.summary?.tables_exported||0} tables`, 'ok', 4000);
  } catch(ex) { toast('Export error: ' + ex.message, 'err'); }
}

function importFullBackupDialog() {
  const input = document.createElement('input');
  input.type = 'file'; input.accept = '.json';
  input.onchange = async () => {
    const file = input.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const archive = JSON.parse(text);
      if (archive.format !== 'agentic-os-workspace') { toast('⚠️ Not a valid Agentic OS backup file', 'warn'); return; }
      if (!(await gmDanger('Restore from Backup', 'This will merge (upsert) the backup\'s data into your current database. Existing rows with matching IDs will be overwritten. Continue?', 'Restore'))) return;
      toast('⬆️ Restoring…', 'ok', 3000);
      const r = await fetch('/api/workspace/import', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: text
      });
      if (!r.ok) { toast('Restore failed: server error ' + r.status, 'err'); return; }
      const j = await r.json();
      if (j.ok) { toast(`✅ Restored ${j.total} rows`, 'ok', 4000); loadBackupStats(); }
      else toast('Restore failed: ' + (j.error||''), 'err');
    } catch(ex) { toast('⚠️ Parse error: ' + ex.message, 'err'); }
  };
  input.click();
}

// Guards against a double-click issuing two overlapping switches. The server
// now serialises activation anyway (a lock in workspaces.py), but the button
// staying live during an await is what generated the pair in the first place,
// and a second request that can only ever be a no-op should not be sent.
let _wsSwitching = false;

async function activateWorkspace(wsId, name) {
  if (_wsSwitching) return;
  _wsSwitching = true;
  document.querySelectorAll('[data-workspace-id]').forEach(b => { b.disabled = true; });
  toast(`⚡ Switching to ${name}…`, 'ok', 2000);
  try {
    const r = await fetch(`/api/workspaces/${encodeURIComponent(wsId)}/activate`, {method:'POST'});
    if (!r.ok) { toast('Switch failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast(`✅ Switched to ${name}`, 'ok', 2000); studioLoadFileTree?.(); studioReloadPreview?.(); renderWorkspaces(); }
    else toast('Switch failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('Switch error: ' + ex.message, 'err'); }
  finally {
    _wsSwitching = false;
    document.querySelectorAll('[data-workspace-id]').forEach(b => { b.disabled = false; });
  }
}
async function createNewWorkspace() {
  const name = await gmPrompt('New Project', 'Project name (e.g. Client A, My SaaS)','');
  if (!name) return;
  try {
    const r = await fetch('/api/workspaces', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({name, emoji:'📁'})});
    if (!r.ok) { toast('Create failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast(`✅ "${name}" created`, 'ok'); renderWorkspaces(); }
    else toast('Create failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('Create error: ' + ex.message, 'err'); }
}
async function exportCurrentZip() {
  const a = document.createElement('a'); a.href='/api/workspaces/export/current'; a.download='agentic-os-project.zip'; a.click();
  toast('📦 Download started', 'ok', 2000);
}
async function exportWorkspace(wsId) {
  const a = document.createElement('a'); a.href=`/api/workspaces/${wsId}/export`; a.download=`workspace-${wsId}.zip`; a.click();
}
async function deleteWorkspace(wsId, name) {
  if (!(await gmDanger('Delete Project', `Delete "${name}"? This cannot be undone.`,'Delete'))) return;
  try {
    const r = await fetch(`/api/workspaces/${encodeURIComponent(wsId)}`, {method:'DELETE'});
    if (!r.ok) { toast('Delete failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast('🗑 Deleted', 'ok'); renderWorkspaces(); }
    else toast('Delete failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('Delete error: ' + ex.message, 'err'); }
}
async function importFromGitHub() {
  const repo = await gmPrompt('Import from GitHub', 'e.g. username/my-repo','');
  if (!repo) return;
  if (!repo.includes('/')) { toast('Enter as username/repo-name', 'warn'); return; }
  toast('⬇️ Importing…', 'ok', 3000);
  try {
    const r = await fetch('/api/workspaces/import/github', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({repo, name: repo.split('/')[1]||repo})});
    if (!r.ok) { toast('Import failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast(`✅ Imported ${j.files_imported} files from ${repo}`, 'ok', 4000); renderWorkspaces(); }
    else toast('Import failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('Import error: ' + ex.message, 'err'); }
}

