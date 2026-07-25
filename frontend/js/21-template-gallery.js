// Agentic OS — Template Gallery
// Extracted from 01-app-core.js for modularity
// ── Template Gallery state ──────────────────────────────────────────────────────
let allTemplates    = [];
let templateCategory = 'all';
let _tmplSort       = 'name';

async function renderTemplates() {
  const pane = document.getElementById('pane-templates');
  if (!pane) return;
  pane.innerHTML = `
    <div style="background:linear-gradient(135deg,var(--bg-1),var(--bg-0));border-bottom:1px solid var(--border);padding:20px 24px">
      <h2 style="font-size:22px;font-weight:900;margin-bottom:4px">🎨 Template Gallery</h2>
      <p style="color:var(--text-2);font-size:13px">14 production-ready templates. One click to scaffold into preview.</p>
      <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap" id="tmpl-cats"></div>
    </div>
    <div style="padding:20px">
      <div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;align-items:center">
        <input id="tmpl-search" placeholder="Search templates…" oninput="filterTemplates()"
               style="flex:1;max-width:300px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;color:var(--text-0);font-size:13px;outline:none">
        <select id="tmpl-sort" onchange="tmplChangeSort(this.value)"
                style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 10px;color:var(--text-0);font-size:12px;outline:none">
          <option value="name">A-Z</option>
          <option value="category">By Category</option>
        </select>
        <span id="tmpl-count" style="font-size:11px;color:var(--text-3)"></span>
      </div>
      <div id="tmpl-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px">
        <div style="color:var(--text-2);grid-column:1/-1">Loading templates…</div>
      </div>
    </div>`;

  try {
    const [tr, cr] = await Promise.all([
      fetch('/api/templates'),
      fetch('/api/templates/categories'),
    ]);
    if (!tr.ok) throw new Error('Templates API error: HTTP '+tr.status);
    if (!cr.ok) throw new Error('Categories API error: HTTP '+cr.status);

    const listData = await tr.json();
    const cats     = await cr.json();
    allTemplates   = listData.templates || listData || [];

    // Category pills
    const catEl = document.getElementById('tmpl-cats');
    if (catEl) {
      catEl.innerHTML = [
        `<span class="bp-btn ${templateCategory==='all'?'active':''}" onclick="filterTemplates('all')">All (${allTemplates.length})</span>`,
        ...cats.map(c => `<span class="bp-btn ${templateCategory===c.id?'active':''}" onclick="filterTemplates(${JSON.stringify(c.id)})">${escHtml(c.label)} (${c.count})</span>`)
      ].join('');
    }
    renderTemplateGrid();

  } catch(ex) {
    const g = document.getElementById('tmpl-grid');
    if (g) g.innerHTML = `<div style="color:var(--danger);grid-column:1/-1">Failed to load templates: ${escHtml(ex?.message||String(ex))}<br><button class="btn-sm" onclick="renderTemplates()" style="margin-top:8px">↻ Retry</button></div>`;
  }
}

function filterTemplates(cat) {
  if (cat !== undefined) templateCategory = cat;
  // Update pill active state
  document.querySelectorAll('#tmpl-cats .bp-btn').forEach(el => {
    const label = el.textContent.trim();
    if (cat === 'all') {
      el.classList.toggle('active', label.startsWith('All'));
    } else if (cat !== undefined) {
      // Match by exact category id embedded in onclick
      const onclick = el.getAttribute('onclick') || '';
      el.classList.toggle('active', onclick.includes(JSON.stringify(cat)));
    }
  });
  const q = document.getElementById('tmpl-search')?.value?.toLowerCase()?.trim() || '';
  renderTemplateGrid(q);
}

function tmplChangeSort(sort) {
  _tmplSort = sort;
  filterTemplates();
}

function renderTemplateGrid(q) {
  q = q || (document.getElementById('tmpl-search')?.value?.toLowerCase()?.trim() || '');
  const grid = document.getElementById('tmpl-grid');
  if (!grid) return;

  let filtered = allTemplates.slice();
  if (templateCategory !== 'all') filtered = filtered.filter(t => t.category === templateCategory);
  if (q) filtered = filtered.filter(t =>
    t.name.toLowerCase().includes(q) ||
    t.description.toLowerCase().includes(q) ||
    (t.tags||[]).some(tag => tag.toLowerCase().includes(q))
  );

  // Sort
  if (_tmplSort === 'category') {
    filtered.sort((a,b) => (a.category||'').localeCompare(b.category||'') || (a.name||'').localeCompare(b.name||''));
  } else {
    filtered.sort((a,b) => (a.name||'').localeCompare(b.name||''));
  }

  // Update count
  const cnt = document.getElementById('tmpl-count');
  if (cnt) cnt.textContent = `${filtered.length} template${filtered.length!==1?'s':''}`;

  if (!filtered.length) {
    grid.innerHTML = `<div style="color:var(--text-3);grid-column:1/-1;text-align:center;padding:40px">No templates match "${escHtml(q)}"</div>`;
    return;
  }

  grid.innerHTML = filtered.map(t => `
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);overflow:hidden;transition:transform .15s,border-color .15s;cursor:default"
         onmouseover="this.style.transform='translateY(-2px)';this.style.borderColor='var(--border-hi)'"
         onmouseout="this.style.transform='';this.style.borderColor='var(--border)'">
      <!-- Preview strip with emoji -->
      <div style="height:80px;background:linear-gradient(135deg,${escHtml(t.preview_color||'#5b8af8')}22,${escHtml(t.preview_color||'#5b8af8')}08);display:flex;align-items:center;justify-content:center;border-bottom:1px solid var(--border)">
        <span style="font-size:40px" role="img" aria-label="${escHtml(t.name)}">${t.emoji||'📄'}</span>
      </div>
      <div style="padding:14px">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
          <span style="font-weight:800;font-size:14px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escHtml(t.name)}">${escHtml(t.name)}</span>
          <span class="tag" style="flex-shrink:0;font-size:10px">${escHtml(t.category||'')}</span>
        </div>
        <p style="font-size:12px;color:var(--text-2);line-height:1.5;margin-bottom:10px;min-height:36px">${escHtml(t.description||'')}</p>
        <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:12px">
          ${(t.tags||[]).slice(0,3).map(tag => `<span style="font-size:10px;padding:2px 7px;border-radius:99px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-3)">${escHtml(tag)}</span>`).join('')}
          ${(t.file_count||0)>1?`<span style="font-size:10px;padding:2px 7px;border-radius:99px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-3)">${t.file_count} files</span>`:''}
        </div>
        <div style="display:flex;gap:6px">
          <button onclick="previewTemplate(${JSON.stringify(t.id)})" class="btn btn-ghost btn-sm" style="flex:1" title="Preview in Studio">👁 Preview</button>
          <button onclick="scaffoldTemplateDialog(${JSON.stringify(t.id)},${JSON.stringify(t.name)})" class="btn btn-primary btn-sm" style="flex:1" title="Scaffold this template">⚡ Use</button>
        </div>
      </div>
    </div>`).join('');
}

async function previewTemplate(templateId) {
  try {
    // Fetch preview HTML from backend
    const r = await fetch(`/api/templates/${encodeURIComponent(templateId)}/preview`);
    if (!r.ok) { showToast('Preview failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (!j.ok) { showToast('Preview failed: '+(j.error||'Unknown')); return; }

    // Scaffold silently then open Studio
    await scaffoldTemplate(templateId, true);
    setTimeout(() => nav('studio'), 400);
    showToast('👁 Preview loaded in Studio');
  } catch(ex) {
    showToast('Preview error: '+ex?.message);
  }
}

async function scaffoldTemplateDialog(templateId, templateName) {
  const projectName = await gmPrompt(
    `Scaffold "${templateName}"`,
    'Project name (optional — leave blank to use template name)',
    templateName
  );
  if (projectName === null) return; // User cancelled
  await scaffoldTemplate(templateId, false, (projectName||'').trim());
}

async function scaffoldTemplate(templateId, silent, projectName) {
  // If allTemplates not loaded yet, load it
  if (!allTemplates.length) {
    try {
      const r = await fetch('/api/templates');
      if (r.ok) {
        const d = await r.json();
        allTemplates = d.templates || d || [];
      }
    } catch(e) {}
  }
  const t = allTemplates.find(x => x.id === templateId);
  if (!silent) showToast(`⚡ Scaffolding ${t?.name||templateId}…`);

  try {
    const r = await fetch(`/api/templates/${encodeURIComponent(templateId)}/scaffold`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({project_name: projectName || (t?.name || templateId)})
    });
    if (!r.ok) {
      showToast('Scaffold failed: HTTP '+r.status);
      return;
    }
    const j = await r.json();
    if (j.ok) {
      if (!silent) showToast(`✅ ${j.template} ready — opening Studio…`);
      studioLoadFileTree?.();
      studioReloadPreview?.();
      if (!silent) setTimeout(() => nav('studio'), 600);
    } else {
      showToast('Scaffold failed: '+(j.error||'Unknown error'));
    }
  } catch(ex) {
    showToast('Scaffold error: '+ex?.message);
  }
}

// Add templates to command palette
if (typeof PALETTE_CMDS !== 'undefined') {
  PALETTE_CMDS.push(
    {icon:'🎨', label:'Template Gallery',     desc:'20+ starter templates', action:()=>nav('templates')},
    {icon:'🚀', label:'SaaS Landing Page',    desc:'Scaffold SaaS template', action:()=>scaffoldTemplate('saas-landing')},
    {icon:'📊', label:'Admin Dashboard',      desc:'Scaffold dashboard',     action:()=>scaffoldTemplate('admin-dashboard')},
    {icon:'✅', label:'Todo App',             desc:'Scaffold kanban todo',   action:()=>scaffoldTemplate('todo-app')},
    {icon:'🎨', label:'Developer Portfolio',  desc:'Scaffold portfolio',     action:()=>scaffoldTemplate('portfolio')},
    {icon:'💬', label:'Chat App',             desc:'Scaffold chat UI',       action:()=>scaffoldTemplate('chat-app')},
    {icon:'🗂',  label:'Sessions',            desc:'View chat history',      action:()=>toggleSessionsPanel()},
    {icon:'＋', label:'New Chat Session',     desc:'Start fresh conversation',action:()=>newSession()},
  );
}

// ═══════════════════════════════════════════════════════════════
//  STUDIO POWER FEATURES
// ═══════════════════════════════════════════════════════════════

