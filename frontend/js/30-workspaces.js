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
              ?`<button onclick="exportCurrentZip()" class="btn btn-ghost btn-sm">📦 Export</button>`
              :`<button data-workspace-id="${escHtml(w.id)}" data-workspace-name="${escHtml(w.name)}" onclick="activateWorkspace(this.dataset.workspaceId, this.dataset.workspaceName)" class="btn btn-primary btn-sm">Switch →</button>
                <button data-workspace-id="${escHtml(w.id)}" onclick="exportWorkspace(this.dataset.workspaceId)" class="btn btn-ghost btn-sm">📦</button>
                <button data-workspace-id="${escHtml(w.id)}" data-workspace-name="${escHtml(w.name)}" onclick="deleteWorkspace(this.dataset.workspaceId, this.dataset.workspaceName)" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:11px">🗑</button>`}
          </div>
        </div>`).join('')}
        <div class="card card-interactive" onclick="createNewWorkspace()" style="display:flex;align-items:center;justify-content:center;min-height:120px;border-style:dashed;cursor:pointer">
          <div style="text-align:center;color:var(--text-3)"><div style="font-size:24px;margin-bottom:4px">＋</div><div style="font-size:12.5px">New Project</div></div>
        </div>
      </div>
      </div>`;
  } catch(e) { pane.innerHTML=`<div class="page-content">${emptyState({icon:'⚠️',title:'Error',body:e.message})}</div>`; }
}
async function activateWorkspace(wsId, name) {
  toast(`⚡ Switching to ${name}…`, 'ok', 2000);
  try {
    const r = await fetch(`/api/workspaces/${encodeURIComponent(wsId)}/activate`, {method:'POST'});
    if (!r.ok) { toast('Switch failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast(`✅ Switched to ${name}`, 'ok', 2000); studioLoadFileTree?.(); studioReloadPreview?.(); renderWorkspaces(); }
    else toast('Switch failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('Switch error: ' + ex.message, 'err'); }
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

