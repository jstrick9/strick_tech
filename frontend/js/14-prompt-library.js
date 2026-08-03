// Agentic OS — Prompt Library
// Extracted from 01-app-core.js for modularity
//
// BUG FIX (quote-collision crash): the category filter buttons and every
// action button on a prompt card (Use/Edit/Duplicate/Favorite/Delete)
// interpolated `JSON.stringify(...)` directly into a double-quoted HTML
// attribute, e.g. onclick="usePrompt(${JSON.stringify(p.id)},
// ${JSON.stringify(p.content)})". JSON.stringify() performs no
// HTML-entity escaping, so the double quotes it wraps a string in collide
// with the onclick attribute's own double-quote delimiters, corrupting
// the HTML. Since prompt `content` is long, free-form, user-authored
// text, this was near-guaranteed to break on real-world prompts (e.g.
// "write a function that returns "hello world""). Reproduced live:
// created a prompt with content containing a double-quote and clicking
// its "→ Use" button threw
// "Uncaught SyntaxError: Failed to execute 'click' on 'HTMLElement':
// Unexpected end of input" and did nothing.
// Fixed by switching every dynamically-generated onclick attribute in
// the prompt grid and category filter to `data-*` attributes wired via
// delegated `addEventListener` calls in wirePromptGridEvents()/
// wireCategoryFilterEvents(), looked up by prompt id / category id
// against the already-loaded `promptsData` array rather than ever
// re-serializing prompt content into an HTML attribute. Static onclick
// attributes with no interpolated user data (New Prompt/Export/Import/
// search input/sort select/Favorites toggle/modal Cancel+Save) are left
// as-is since they cannot collide.
//
// Also replaced every `showToast(...)` call in this file's Prompt
// Library section with `toast(...)` per this codebase's standing rule
// (`showToast` is a legacy compatibility alias for old code only).
// ── Prompt Library state ─────────────────────────────────────────────────────
let promptsData    = [];
let promptCategory = 'all';
let promptFavOnly  = false;
let editingPromptId = null;
let _promptSort    = 'updated';

// The API returns real status codes with an explanatory body; showing only
// the status number threw away the reason (e.g. which category was invalid).
async function promptError(r, fallback) {
  let body = {};
  try { body = await r.json(); } catch (e) { /* non-JSON error body */ }
  let msg = body.error || body.detail || fallback || ('HTTP ' + r.status);
  if (Array.isArray(body.valid_categories)) msg += ` (valid: ${body.valid_categories.join(', ')})`;
  if (body.hint) msg += ` — ${body.hint}`;
  return msg;
}

async function renderPrompts() {
  const pane = document.getElementById('pane-prompts');
  if (!pane) return;
  pane.innerHTML = '<div style="padding:20px;color:var(--text-2)">Loading…</div>';
  try {
    const [pr, cr, ar] = await Promise.all([
      fetch('/api/prompts'),
      fetch('/api/prompts/categories'),
      fetch('/api/prompts/agents'),
    ]);
    if (!pr.ok) throw new Error('Prompts API error: HTTP '+pr.status);
    if (!cr.ok) throw new Error('Categories API error: HTTP '+cr.status);
    const listData = await pr.json();
    const catData  = await cr.json();
    // Non-fatal: without it the picker just falls back to "any agent".
    const agents   = ar.ok ? await ar.json() : {agents: []};
    promptsData = listData.prompts || listData || [];  // handle both wrapped and raw
    const cats  = catData.categories || catData || [];

    pane.innerHTML = `
      ${pageHeader?.({title:'💬 Prompt Library',subtitle:'Save, organize, and reuse your best AI prompts',actions:[
        {label:'＋ New Prompt',action:'openNewPromptModal()',primary:true},
        {label:'⬇ Export',action:'exportPrompts()'},
        {label:'⬆ Import',action:'importPrompts()'},
      ]})||'<div style="padding:20px"><h2>💬 Prompt Library</h2></div>'}
      <div class="page-content">
      <div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;align-items:center">
        <input id="prompt-search" placeholder="Search prompts…" oninput="filterPrompts()"
               style="flex:1;max-width:280px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 12px;color:var(--text-0);font-size:13px;outline:none">
        <select id="prompt-sort" onchange="changePromptSort(this.value)"
                style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 10px;color:var(--text-0);font-size:12px;outline:none">
          <option value="updated">Recently updated</option>
          <option value="used">Most used</option>
          <option value="title">A-Z</option>
        </select>
        <button onclick="toggleFavs()" class="btn ${promptFavOnly?'btn-primary':'btn-ghost'} btn-sm" id="fav-btn">⭐ Favorites</button>
        <div style="display:flex;gap:4px;flex-wrap:wrap" id="prompt-cat-filter">
          <button type="button" data-prompt-cat="all" class="term-btn" id="pcat-all"
                  style="${promptCategory==='all'?'border-color:var(--accent);color:var(--accent-hi)':''}">All (${promptsData.length})</button>
          ${cats.map(c=>`<button type="button" data-prompt-cat="${escHtml(c.id)}" class="term-btn" id="pcat-${escHtml(c.id)}"
            title="${c.builtin===false?'Custom category':'Built-in category'}"
            style="${promptCategory===c.id?'border-color:var(--accent);color:var(--accent-hi)':''}">${escHtml(c.label||c.id)} (${c.count})</button>`).join('')}
          <button type="button" data-prompt-action="new-category" class="term-btn"
                  title="Create a custom category">＋ Category</button>
        </div>
      </div>
      <div id="prompt-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:10px">${renderPromptCards()}</div>
      </div>
      <!-- Prompt modal -->
      <div id="prompt-modal" style="display:none;position:fixed;inset:0;background:rgba(4,6,14,.85);z-index:9000;align-items:center;justify-content:center;backdrop-filter:blur(8px)" onclick="if(event.target===this)closePromptModal()">
        <div style="background:var(--bg-2);border:1px solid var(--border-hi);border-radius:var(--radius-xl);padding:22px;width:100%;max-width:560px;box-shadow:var(--shadow-lg);max-height:90vh;overflow-y:auto">
          <h2 style="font-size:17px;font-weight:800;margin-bottom:14px" id="pm-modal-title">New Prompt</h2>
          <div class="form-group"><label class="form-label">Title *</label><input id="pm-title" class="input" placeholder="e.g. Security code review"></div>
          <div class="form-group"><label class="form-label">Prompt *</label><textarea id="pm-content" class="input" style="min-height:120px;font-family:monospace;font-size:12px" placeholder="The full prompt text… Use {placeholder} for variables."></textarea></div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px">
            <div class="form-group" style="margin:0"><label class="form-label">Category</label>
              <select id="pm-category" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 10px;color:var(--text-0);font-size:13px;outline:none">
                <!-- Was a hardcoded list of the 12 built-ins, so a custom
                     category could never be selected even once it existed. -->
                ${cats.map(c=>`<option value="${escHtml(c.id)}">${escHtml(c.label||c.id)}</option>`).join('')}
              </select>
            </div>
            <div class="form-group" style="margin:0"><label class="form-label">Tags</label>
              <input id="pm-tags" class="input" placeholder="security, api…">
            </div>
          </div>
          <div class="form-group"><label class="form-label">Agent (optional)</label>
            <!-- Was a free-text input, which let a prompt be pinned to an agent
                 that doesn't exist — the ?agent_id= filter then never matched it
                 and the prompt was unreachable. A picker makes that impossible. -->
            <select id="pm-agent" class="input">
              <option value="">— Any agent —</option>
              ${(agents.agents || []).map(a =>
                `<option value="${escHtml(a.id)}">${escHtml(a.name)}${a.count ? ` (${a.count})` : ''}</option>`
              ).join('')}
            </select>
          </div>
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin-bottom:14px;font-size:13px">
            <input type="checkbox" id="pm-fav" style="accent-color:var(--accent)"> Mark as favorite
          </label>
          <div style="display:flex;gap:8px;justify-content:flex-end">
            <button onclick="closePromptModal()" class="btn btn-ghost">Cancel</button>
            <button onclick="savePrompt()" class="btn btn-primary" id="pm-save-btn">Save</button>
          </div>
        </div>
      </div>`;

    wireCategoryFilterEvents();
    wirePromptGridEvents();

  } catch(ex) {
    pane.innerHTML = `<div style="padding:20px;color:var(--danger)">Error loading prompts: ${escHtml(ex?.message||String(ex))}<br>
      <button class="btn-sm" onclick="renderPrompts()" style="margin-top:8px">↻ Retry</button></div>`;
  }
}

// Category filter chips: delegated click handling looked up by the
// category id stored in data-prompt-cat, instead of the old
// onclick="setPromptCat(${JSON.stringify(c.id)})" pattern.
function wireCategoryFilterEvents() {
  const filterBar = document.getElementById('prompt-cat-filter');
  if (!filterBar) return;
  filterBar.addEventListener('click', (e) => {
    if (e.target.closest('[data-prompt-action="new-category"]')) { createCategory(); return; }
    const btn = e.target.closest('[data-prompt-cat]');
    if (btn) setPromptCat(btn.dataset.promptCat);
  });
}

async function createCategory() {
  const name = (window.prompt('New category name (e.g. "Marketing Copy"):') || '').trim();
  if (!name) return;
  try {
    const r = await fetch('/api/prompts/categories', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({name})
    });
    if (!r.ok) { toast('Could not create category: '+await promptError(r), 'err'); return; }
    const j = await r.json();
    toast(`✅ Category "${j.label}" created`, 'ok');
    renderPrompts();
  } catch (ex) { toast('Category error: '+ex?.message, 'err'); }
}

// Prompt card action buttons (Use/Edit/Duplicate/Favorite/Delete):
// delegated click handling looked up by prompt id against the
// already-loaded promptsData array, instead of the old
// onclick="usePrompt(${JSON.stringify(p.id)},${JSON.stringify(p.content)})"
// pattern that corrupted the HTML on any prompt whose content contained a
// double-quote (see file header note for the full bug writeup and live
// repro). Re-wired every time renderPromptCards() replaces #prompt-grid's
// innerHTML (renderPrompts() initial render, and every filterPrompts()
// call from search/category/favorites-toggle/sort), since the listener
// is attached to the stable #prompt-grid container itself (event
// delegation), not to the individual card buttons that get replaced.
function wirePromptGridEvents() {
  const grid = document.getElementById('prompt-grid');
  if (!grid || grid.dataset.wired) return;
  grid.dataset.wired = '1';
  grid.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-prompt-action]');
    if (!btn) return;
    const pid = btn.dataset.promptId;
    const p = promptsData.find(x => x.id === pid);
    switch (btn.dataset.promptAction) {
      case 'use':        if (p) usePrompt(pid, p.content); break;
      case 'edit':       editPrompt(pid); break;
      case 'duplicate':  duplicatePrompt(pid); break;
      case 'history':    showPromptHistory(pid); break;
      case 'favorite':   toggleFavorite(pid, p?.is_favorite ? 1 : 0); break;
      case 'delete':     deletePrompt(pid); break;
      case 'create-first': openNewPromptModal(); break;
    }
  });
}

function renderPromptCards() {
  let filtered = promptsData.slice();
  if (promptCategory !== 'all') filtered = filtered.filter(p => p.category === promptCategory);
  if (promptFavOnly)             filtered = filtered.filter(p => p.is_favorite);
  const q = (document.getElementById('prompt-search')?.value || '').toLowerCase().trim();
  if (q) filtered = filtered.filter(p =>
    p.title.toLowerCase().includes(q) ||
    p.content.toLowerCase().includes(q) ||
    (p.tags||'').toLowerCase().includes(q)
  );
  if (!filtered.length) return `<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--text-3)">
    No prompts found${q?' matching "'+escHtml(q)+'"':''}.
    ${!promptsData.length?'<br><button type="button" class="btn btn-primary btn-sm" data-prompt-action="create-first" style="margin-top:8px">＋ Create First Prompt</button>':''}
  </div>`;

  return filtered.map(p => `
    <div class="prompt-card ${p.is_favorite?'favorite':''}" style="position:relative">
      <div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:8px">
        <div style="flex:1;min-width:0">
          <div style="font-weight:700;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${escHtml(p.title)}">${escHtml(p.title)}</div>
          <div style="display:flex;gap:4px;margin-top:3px;flex-wrap:wrap">
            <span style="font-size:10px;padding:1px 7px;border-radius:99px;background:var(--bg-3);color:var(--text-2)">${escHtml(p.category||'general')}</span>
            ${(p.tags||'').split(',').filter(t=>t.trim()).slice(0,2).map(t=>`<span style="font-size:10px;padding:1px 7px;border-radius:99px;background:var(--bg-3);color:var(--text-3)">${escHtml(t.trim())}</span>`).join('')}
            ${p.agent_id?`<span style="font-size:10px;padding:1px 7px;border-radius:99px;background:var(--bg-3);color:var(--accent)">🤖 ${escHtml(p.agent_id)}</span>`:''}
            ${(() => { const v = promptVariables(p.content); return v.length
              ? `<span style="font-size:10px;padding:1px 7px;border-radius:99px;background:var(--bg-3);color:var(--warning)"
                       title="Fills in when you click Use: ${escHtml(v.join(', '))}">⚙ ${v.length} var${v.length>1?'s':''}</span>`
              : ''; })()}
          </div>
        </div>
        ${p.is_favorite?'<span style="font-size:12px;flex-shrink:0">⭐</span>':''}
        <span style="font-size:10.5px;color:var(--text-3);flex-shrink:0">${p.use_count||0}×</span>
      </div>
      <p style="font-size:12px;color:var(--text-2);line-height:1.5;margin-bottom:10px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical">${escHtml(p.content)}</p>
      <div style="display:flex;gap:5px;flex-wrap:wrap">
        <button type="button" data-prompt-action="use" data-prompt-id="${escHtml(p.id)}" class="btn btn-primary btn-sm" style="flex:1" title="Load in chat">→ Use</button>
        <button type="button" data-prompt-action="edit" data-prompt-id="${escHtml(p.id)}" class="btn btn-ghost btn-sm" title="Edit">✏️</button>
        <button type="button" data-prompt-action="duplicate" data-prompt-id="${escHtml(p.id)}" class="btn btn-ghost btn-sm" title="Duplicate">⧉</button>
        <button type="button" data-prompt-action="history" data-prompt-id="${escHtml(p.id)}" class="btn btn-ghost btn-sm" title="Version history">🕘</button>
        <button type="button" data-prompt-action="favorite" data-prompt-id="${escHtml(p.id)}" class="btn btn-ghost btn-sm" title="${p.is_favorite?'Remove from favorites':'Add to favorites'}">${p.is_favorite?'⭐':'☆'}</button>
        <button type="button" data-prompt-action="delete" data-prompt-id="${escHtml(p.id)}" style="background:none;border:none;color:var(--danger);cursor:pointer;font-size:13px;padding:3px 6px" title="Delete">🗑</button>
      </div>
    </div>`).join('');
}

function filterPrompts() {
  const g = document.getElementById('prompt-grid');
  if (g) g.innerHTML = renderPromptCards();
}

function setPromptCat(cat) {
  promptCategory = cat;
  document.querySelectorAll('[id^="pcat-"]').forEach(b => {
    const active = b.id === 'pcat-'+cat;
    b.style.borderColor = active ? 'var(--accent)' : '';
    b.style.color       = active ? 'var(--accent-hi)' : '';
  });
  filterPrompts();
}

function toggleFavs() {
  promptFavOnly = !promptFavOnly;
  const b = document.getElementById('fav-btn');
  if (b) b.className = `btn ${promptFavOnly?'btn-primary':'btn-ghost'} btn-sm`;
  filterPrompts();
}

function changePromptSort(sort) {
  _promptSort = sort;
  // Re-sort promptsData locally
  const sortFns = {
    updated: (a,b) => (b.updated_at||'').localeCompare(a.updated_at||''),
    used:    (a,b) => (b.use_count||0) - (a.use_count||0),
    title:   (a,b) => (a.title||'').localeCompare(b.title||''),
  };
  promptsData.sort(sortFns[sort] || sortFns.updated);
  filterPrompts();
}

function openNewPromptModal(prefill) {
  prefill = prefill || '';
  editingPromptId = null;
  const modalTitle = document.getElementById('pm-modal-title');
  const titleEl    = document.getElementById('pm-title');
  const contentEl  = document.getElementById('pm-content');
  const catEl      = document.getElementById('pm-category');
  const tagsEl     = document.getElementById('pm-tags');
  const agentEl    = document.getElementById('pm-agent');
  const favEl      = document.getElementById('pm-fav');
  const saveBtnEl  = document.getElementById('pm-save-btn');
  if (modalTitle) modalTitle.textContent = 'New Prompt';
  if (titleEl)    titleEl.value    = '';
  if (contentEl)  contentEl.value  = prefill;
  if (catEl)      catEl.value      = 'general';
  if (tagsEl)     tagsEl.value     = '';
  if (agentEl)    agentEl.value    = '';
  if (favEl)      favEl.checked    = false;
  if (saveBtnEl)  saveBtnEl.textContent = 'Save';
  const modal = document.getElementById('prompt-modal');
  if (modal) modal.style.display = 'flex';
  setTimeout(() => titleEl?.focus(), 50);
}

function closePromptModal() {
  const modal = document.getElementById('prompt-modal');
  if (modal) modal.style.display = 'none';
  editingPromptId = null;
}

async function savePrompt() {
  const title    = document.getElementById('pm-title')?.value?.trim();
  const content  = document.getElementById('pm-content')?.value?.trim();
  if (!title || !content) { toast('⚠️ Title and content are required', 'warn'); return; }

  const payload = {
    title,
    content,
    category:    document.getElementById('pm-category')?.value  || 'general',
    tags:        document.getElementById('pm-tags')?.value       || '',
    agent_id:    document.getElementById('pm-agent')?.value      || '',
    is_favorite: document.getElementById('pm-fav')?.checked ? 1 : 0,
  };

  const url    = editingPromptId ? `/api/prompts/${editingPromptId}` : '/api/prompts';
  const method = editingPromptId ? 'PATCH' : 'POST';

  try {
    const r = await fetch(url, {method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (!r.ok) { toast('Save failed: '+await promptError(r), 'err'); return; }
    const j = await r.json();
    if (j.ok) {
      toast(editingPromptId ? '✅ Prompt updated' : '✅ Prompt saved', 'ok');
      closePromptModal();
      renderPrompts();
    } else {
      toast('Save failed: '+(j.error||'Unknown error'), 'err');
    }
  } catch(ex) {
    toast('Save error: '+ex?.message, 'err');
  }
}

function editPrompt(pid) {
  const p = promptsData.find(x => x.id === pid);
  if (!p) { toast('Prompt not found', 'err'); return; }
  editingPromptId = pid;
  const modalTitle = document.getElementById('pm-modal-title');
  const titleEl    = document.getElementById('pm-title');
  const contentEl  = document.getElementById('pm-content');
  const catEl      = document.getElementById('pm-category');
  const tagsEl     = document.getElementById('pm-tags');
  const agentEl    = document.getElementById('pm-agent');
  const favEl      = document.getElementById('pm-fav');
  const saveBtnEl  = document.getElementById('pm-save-btn');
  if (modalTitle) modalTitle.textContent = 'Edit Prompt';
  if (titleEl)    titleEl.value    = p.title    || '';
  if (contentEl)  contentEl.value  = p.content  || '';
  if (catEl)      catEl.value      = p.category || 'general';
  if (tagsEl)     tagsEl.value     = p.tags     || '';
  if (agentEl) {
    // A prompt saved before validation may point at an agent that no longer
    // exists. Setting <select>.value to a missing option silently selects
    // nothing, which would look like the pin had been cleared — show it.
    if (p.agent_id && !Array.from(agentEl.options).some(o => o.value === p.agent_id)) {
      const opt = document.createElement('option');
      opt.value = p.agent_id;
      opt.textContent = `${p.agent_id} (no longer exists)`;
      agentEl.appendChild(opt);
    }
    agentEl.value = p.agent_id || '';
  }
  if (favEl)      favEl.checked    = !!p.is_favorite;
  if (saveBtnEl)  saveBtnEl.textContent = 'Update';
  const modal = document.getElementById('prompt-modal');
  if (modal) modal.style.display = 'flex';
  setTimeout(() => titleEl?.focus(), 50);
}

async function deletePrompt(pid) {
  const p = promptsData.find(x => x.id === pid);
  const name = p?.title || pid;
  if (!(await gmDanger('Delete Prompt', `Remove "${name}" from your library?`))) return;
  try {
    const r = await fetch(`/api/prompts/${encodeURIComponent(pid)}`, {method:'DELETE'});
    if (!r.ok) { toast('Delete failed: '+await promptError(r), 'err'); return; }
    const j = await r.json();
    if (j.ok) {
      promptsData = promptsData.filter(p => p.id !== pid);
      toast('🗑 Prompt deleted', 'ok');
      filterPrompts();
    } else {
      toast('Delete failed: '+(j.error||'Unknown'), 'err');
    }
  } catch(ex) {
    toast('Delete error: '+ex?.message, 'err');
  }
}

async function toggleFavorite(pid, current) {
  try {
    const r = await fetch(`/api/prompts/${encodeURIComponent(pid)}`, {
      method:'PATCH', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({is_favorite: current ? 0 : 1})
    });
    if (!r.ok) { toast('Favorite toggle failed: '+await promptError(r), 'err'); return; }
    const d = await r.json();
    if (d.ok) {
      const p = promptsData.find(x => x.id === pid);
      if (p) p.is_favorite = current ? 0 : 1;
      filterPrompts();
      toast(current ? '☆ Removed from favorites' : '⭐ Added to favorites', 'ok');
    } else {
      toast('Toggle failed: '+(d.error||'Unknown'), 'err');
    }
  } catch(ex) {
    toast('Favorite error: '+ex?.message, 'err');
  }
}

// The editor tells users to "Use {placeholder} for variables", but nothing
// ever substituted them — the literal braces were sent to the model. Ask for
// the values, render server-side, then load the finished text into chat.
function promptVariables(content) {
  const names = [];
  const re = /(?<!\{)\{([a-zA-Z][a-zA-Z0-9_ -]{0,48})\}(?!\})/g;
  let m;
  while ((m = re.exec(content || '')) !== null) {
    const name = m[1].trim();
    if (name && !names.includes(name)) names.push(name);
  }
  return names;
}

function askForVariables(title, names) {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    overlay.innerHTML = `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:14px;max-width:460px;width:100%;padding:20px">
        <h3 style="margin:0 0 4px;color:var(--text-0);font-size:15px">Fill in variables</h3>
        <div style="font-size:11.5px;color:var(--text-3);margin-bottom:14px">${escHtml(title)}</div>
        ${names.map((n, i) => `
          <div class="form-group">
            <label class="form-label">${escHtml(n)}</label>
            <input class="input pv-input" data-var-name="${escHtml(n)}"${i === 0 ? ' autofocus' : ''}
                   placeholder="Value for {${escHtml(n)}}">
          </div>`).join('')}
        <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:14px">
          <button type="button" class="btn btn-ghost btn-sm" data-pv="cancel">Cancel</button>
          <button type="button" class="btn btn-ghost btn-sm" data-pv="skip" title="Send with the placeholders left in">Use as-is</button>
          <button type="button" class="btn btn-primary btn-sm" data-pv="ok">→ Use prompt</button>
        </div>
      </div>`;
    const finish = (result) => { overlay.remove(); resolve(result); };
    overlay.addEventListener('click', (e) => {
      const act = e.target.closest('[data-pv]')?.dataset.pv;
      if (act === 'cancel' || e.target === overlay) return finish(null);
      if (act === 'skip') return finish({});
      if (act === 'ok') {
        const values = {};
        overlay.querySelectorAll('.pv-input').forEach(el => { values[el.dataset.varName] = el.value; });
        finish(values);
      }
    });
    overlay.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') finish(null);
      if (e.key === 'Enter' && e.target.classList.contains('pv-input')) {
        overlay.querySelector('[data-pv="ok"]')?.click();
      }
    });
    document.body.appendChild(overlay);
    setTimeout(() => overlay.querySelector('.pv-input')?.focus(), 30);
  });
}

async function usePrompt(pid, content) {
  const names = promptVariables(content);
  if (names.length) {
    const values = await askForVariables(
      promptsData.find(x => x.id === pid)?.title || 'Prompt', names);
    if (values === null) return;  // cancelled
    try {
      const r = await fetch(`/api/prompts/${encodeURIComponent(pid)}/render`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({values})
      });
      if (r.ok) {
        const j = await r.json();
        content = j.rendered ?? content;
        if (j.missing?.length) toast(`⚠️ Left unfilled: ${j.missing.join(', ')}`, 'warn');
      } else {
        toast('Render failed: '+await promptError(r), 'err');
      }
    } catch (ex) { toast('Render error: '+ex?.message, 'err'); }
    const pLocal = promptsData.find(x => x.id === pid);
    if (pLocal) pLocal.use_count = (pLocal.use_count||0) + 1;
  } else {
    try {
      fetch(`/api/prompts/${encodeURIComponent(pid)}/use`, {method:'POST'}).catch(()=>{});
      const p = promptsData.find(x => x.id === pid);
      if (p) p.use_count = (p.use_count||0) + 1;
    } catch(e) {}
  }
  nav('chat');
  setTimeout(() => {
    const inp = document.getElementById('chat-input');
    if (inp) {
      inp.value = content;
      inp.focus();
      if (typeof autoResizeInput === 'function') autoResizeInput(inp);
      const emptyEl = document.getElementById('chat-empty');
      if (emptyEl) emptyEl.style.display = 'none';
    }
  }, 200);
  toast('✅ Prompt loaded in chat', 'ok');
}

async function duplicatePrompt(pid) {
  try {
    const r = await fetch(`/api/prompts/${encodeURIComponent(pid)}/duplicate`, {method:'POST'});
    if (!r.ok) { toast('Duplicate failed: '+await promptError(r), 'err'); return; }
    const j = await r.json();
    if (j.ok) {
      toast('⧉ Prompt duplicated: '+escHtml(j.title||''), 'ok');
      renderPrompts();
    } else {
      toast('Duplicate failed: '+(j.error||'Unknown'), 'err');
    }
  } catch(ex) {
    toast('Duplicate error: '+ex?.message, 'err');
  }
}

async function exportPrompts() {
  try {
    const r = await fetch('/api/prompts/export');
    if (!r.ok) { toast('Export failed: '+await promptError(r), 'err'); return; }
    const d = await r.json();
    const blob = new Blob([JSON.stringify(d.prompts, null, 2)], {type:'application/json'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `prompts-export-${new Date().toISOString().slice(0,10)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
    toast(`✅ Exported ${d.count} prompts`, 'ok');
  } catch(ex) {
    toast('Export error: '+ex?.message, 'err');
  }
}

async function importPrompts() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.json';
  input.onchange = async () => {
    const file = input.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const prompts = Array.isArray(data) ? data : (data.prompts || []);
      if (!prompts.length) { toast('No prompts found in file', 'warn'); return; }
      const r = await fetch('/api/prompts/import', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({prompts})
      });
      if (!r.ok) { toast('Import failed: '+await promptError(r), 'err'); return; }
      const j = await r.json();
      if (j.ok) {
        toast(`✅ Imported ${j.imported}${j.replaced ? ', replaced '+j.replaced : ''} (${j.skipped} skipped)`, 'ok');
        renderPrompts();
      } else {
        toast('Import failed: '+(j.error||'Unknown'), 'err');
      }
    } catch(ex) {
      toast('Import parse error: '+ex?.message, 'err');
    }
  };
  input.click();
}

// Save current chat input as a prompt
window.saveCurrentAsPrompt = async function() {
  const content = document.getElementById('chat-input')?.value?.trim();
  if (!content) { toast('⚠️ Type a prompt first', 'warn'); return; }
  const title = await gmPrompt('Save Prompt', 'Name for this prompt', content.slice(0,50)+(content.length>50?'…':''));
  if (!title || !title.trim()) return;
  try {
    const r = await fetch('/api/prompts', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({title:title.trim(), content, category:'general'})
    });
    if (!r.ok) { toast('Save failed: '+await promptError(r), 'err'); return; }
    const j = await r.json();
    if (j.ok) toast('✅ Saved to Prompt Library', 'ok');
    else toast('Save failed: '+(j.error||'Unknown'), 'err');
  } catch(ex) {
    toast('Save error: '+ex?.message, 'err');
  }
};

(function addSavePromptBtn() {
  const t = document.querySelector('.chat-tools');
  if (!t || document.getElementById('save-prompt-btn')) { setTimeout(addSavePromptBtn, 700); return; }
  const b = document.createElement('button');
  b.id        = 'save-prompt-btn';
  b.className = 'chat-tool';
  b.title     = 'Save current input as a reusable prompt';
  b.textContent = '💾 Save Prompt';
  b.onclick   = saveCurrentAsPrompt;
  t.appendChild(b);
})();

// ══════════════════════════════════════════════════════
//  CODE SEARCH
// ══════════════════════════════════════════════════════
async function renderCodeSearch(){
  const pane=document.getElementById('pane-codesearch');if(!pane)return;
  pane.innerHTML=`
    ${pageHeader?.({title:'🔍 Code Search',subtitle:'Instant search across all project files'})||'<div style="padding:20px"><h2>🔍 Code Search</h2></div>'}
    <div class="page-content">
    <div style="display:flex;gap:8px;margin-bottom:14px">
      <input id="cs-input" class="input" placeholder="Search code, functions, variables, text…" style="flex:1;font-size:14px;height:42px" onkeydown="if(event.key==='Enter')runCodeSearch()" autocomplete="off">
      <button onclick="runCodeSearch()" class="btn btn-primary" id="cs-btn" style="height:42px">🔍 Search</button>
    </div>
    <div id="cs-results" style="color:var(--text-3);text-align:center;padding:40px;font-size:13px">Type to search across all project files</div>
    </div>`;
  document.getElementById('cs-input')?.focus();
}

async function runCodeSearch(){
  const q=document.getElementById('cs-input')?.value?.trim();if(!q)return;
  const btn=document.getElementById('cs-btn');const res=document.getElementById('cs-results');
  btn.disabled=true;btn.textContent='⏳…';res.innerHTML='<div style="color:var(--text-2);padding:12px">Searching…</div>';
  try {
    const r=await fetch(`/api/project/search?q=${encodeURIComponent(q)}&limit=30&context_lines=2`);
    const j=await r.json();const results=j.results||[];
    if(!results.length){res.innerHTML=`<div style="text-align:center;padding:40px;color:var(--text-3)"><div style="font-size:24px;margin-bottom:8px">🔍</div><div>No results for "${escHtml(q)}"</div></div>`;return;}
    const byFile={};results.forEach(r=>{if(!byFile[r.file])byFile[r.file]=[];byFile[r.file].push(r);});
    res.innerHTML=`<div style="margin-bottom:12px;font-size:13px;color:var(--text-1);font-weight:600">${j.total} match${j.total!==1?'es':''} in ${Object.keys(byFile).length} file${Object.keys(byFile).length!==1?'s':''}${j.summary?` — ${escHtml(j.summary)}`:''}
    </div>${Object.entries(byFile).map(([file,hits])=>`
      <div style="margin-bottom:10px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);overflow:hidden">
        <div style="padding:7px 12px;background:var(--bg-3);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;cursor:pointer" onclick="studioOpenFile?.('${escHtml(file)}');nav('studio')">
          <span style="font-size:11.5px;font-family:monospace;color:var(--accent);font-weight:600">${escHtml(file)}</span>
          <span style="font-size:10.5px;color:var(--text-3);margin-left:auto">${hits.length} match${hits.length!==1?'es':''} · open →</span>
        </div>
        ${hits.map(hit=>{
          // FIX 10: render surrounding context lines, not just the match line
          const ctx = hit.context || [hit.match];
          const matchIdx = ctx.indexOf(hit.match);
          const ctxHtml = ctx.map((l,ci)=>{
            const isMatch = ci === matchIdx || l === hit.match;
            return `<div style="display:flex;gap:6px;${isMatch?'background:rgba(91,138,248,.08);':''}padding:1px 0">
              <span style="color:var(--text-3);font-size:10px;min-width:32px;text-align:right;user-select:none">${(hit.line - matchIdx + ci)}</span>
              <span style="font-family:monospace;font-size:12px;color:${isMatch?'var(--text-0)':'var(--text-3)'};white-space:pre-wrap">${escHtml(l)}</span>
            </div>`;
          }).join('');
          return `<div style="padding:6px 12px;border-bottom:1px solid var(--border);cursor:pointer;transition:var(--transition)" onclick="studioOpenFile?.('${escHtml(file)}');nav('studio')" onmouseover="this.style.background='var(--bg-3)'" onmouseout="this.style.background=''">
            ${ctxHtml}
          </div>`;
        }).join('')}
      </div>`).join('')}`;
  }catch(e){res.innerHTML=`<div style="color:var(--danger);padding:12px">Error: ${escHtml(e.message)}</div>`;}
  finally{btn.disabled=false;btn.textContent='🔍 Search';}
}
window.renderCodeSearch = renderCodeSearch;
window.runCodeSearch = runCodeSearch;

// ══════════════════════════════════════════════════════
//  AI CODE REVIEWER
// ══════════════════════════════════════════════════════
let reviewOpen=false;

async function reviewCurrentFile(){
  const filepath=Studio?.currentFile||S?.currentFile;
  if(!filepath){toast('Open a file in Studio first','warn');return;}
  let overlay=document.getElementById('review-overlay');
  if(!overlay){
    overlay=document.createElement('div');overlay.id='review-overlay';overlay.className='review-overlay';
    overlay.innerHTML=`<div style="padding:10px 12px;border-bottom:1px solid var(--border);background:var(--bg-2);display:flex;align-items:center;gap:8px;flex-shrink:0">
      <span style="font-weight:700;font-size:13px">🔍 Code Review</span>
      <span id="review-score" style="font-size:11px;color:var(--text-2)"></span>
      <div style="margin-left:auto;display:flex;gap:5px">
        <button onclick="reviewCurrentFile()" class="btn btn-ghost btn-sm">⟳</button>
        <button onclick="toggleReviewOverlay()" style="background:none;border:none;color:var(--text-2);cursor:pointer;font-size:16px">×</button>
      </div>
    </div>
    <div id="review-summary" style="padding:9px 12px;font-size:12.5px;color:var(--text-2);border-bottom:1px solid var(--border);flex-shrink:0"></div>
    <div id="review-issues" style="flex:1;overflow-y:auto;padding:4px"></div>`;
    document.getElementById('shell')?.appendChild(overlay);
  }
  overlay.classList.add('open');reviewOpen=true;
  const scoreEl=document.getElementById('review-score');const sumEl=document.getElementById('review-summary');const issuesEl=document.getElementById('review-issues');
  if(scoreEl)scoreEl.textContent='Analyzing…';
  if(sumEl)sumEl.innerHTML='<div style="color:var(--text-2)">AI reviewing…</div>';
  toast(`🔍 Reviewing ${filepath}…`,'ok',2000);
  try {
    const r=await fetch('/api/project/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filepath})});
    const j=await r.json();
    const sc=j.score||75;const sc_color=sc>=80?'var(--success)':sc>=60?'var(--warning)':'var(--danger)';
    if(scoreEl)scoreEl.innerHTML=`<span style="color:${sc_color};font-weight:700">${sc}/100</span>`;
    if(sumEl)sumEl.innerHTML=`<div style="margin-bottom:5px">${escHtml(j.summary||'Review complete')}</div>${(j.highlights||[]).slice(0,2).map(h=>`<div style="color:var(--success);font-size:11.5px">✓ ${escHtml(h)}</div>`).join('')}`;
    const issues=j.issues||[];
    if(issuesEl)issuesEl.innerHTML=!issues.length?'<div style="text-align:center;padding:20px;color:var(--success)">✅ No issues!</div>':issues.map(i=>`
      <div class="review-issue">
        <span class="review-issue-sev ${i.severity||'info'}"></span>
        <div style="flex:1;min-width:0">
          <div style="font-size:12px;font-weight:600">Line ${i.line||'?'} — ${escHtml(i.message||'')}</div>
          ${i.fix?`<div style="font-size:11.5px;color:var(--text-2)">Fix: ${escHtml(i.fix)}</div>`:''}
        </div>
      </div>`).join('');
    toast(`✅ Review: ${sc}/100 — ${issues.length} issue${issues.length!==1?'s':''}`,'ok',3000);
  }catch(e){if(sumEl)sumEl.innerHTML=`<div style="color:var(--danger)">Error: ${escHtml(e.message)}</div>`;}
}

function toggleReviewOverlay(){
  reviewOpen=!reviewOpen;
  document.getElementById('review-overlay')?.classList.toggle('open',reviewOpen);
}

(function addReviewBtn(){
  const t=document.querySelector('.studio-toolbar');if(!t||document.getElementById('review-btn')){setTimeout(addReviewBtn,900);return;}
  const b=document.createElement('button');b.id='review-btn';b.className='btn btn-ghost btn-sm';b.title='AI code review (⌘⇧R)';b.textContent='🔍 Review';b.onclick=reviewCurrentFile;t.appendChild(b);
})();

// ══════════════════════════════════════════════════════
//  SHARE APP
// ══════════════════════════════════════════════════════
async function shareProject(){
  toast('🌐 Getting share URL…','ok',2000);
  const r=await fetch('/api/project/share',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target:'web'})});
  const j=await r.json();
  if(j.ok){
    const url=j.public_url||j.lan_url;
    await gmAlert('🌐 Share Your App',`
      <div style="margin-bottom:10px;font-size:13px">${j.is_public?'<span style="color:var(--success)">✅ Public URL (anyone can access)</span>':'<span style="color:var(--warning)">⚠️ LAN only (same Wi-Fi)</span>'}</div>
      <code style="display:block;background:var(--bg-0);padding:10px;border-radius:6px;font-size:12px;word-break:break-all;margin-bottom:10px">${url}</code>
      ${j.qr_url?`<div style="text-align:center;margin-bottom:10px"><img src="${j.qr_url}" style="width:130px;height:130px;border-radius:8px"></div>`:''}
      <div style="font-size:12px;color:var(--text-2)">${j.tip}</div>`);
    navigator.clipboard.writeText(url).then(()=>toast('📋 URL copied!','ok',1500));
  }else toast('Share failed','err');
}

(function addShareBtn(){
  const a=document.getElementById('topbar-actions');if(!a||document.getElementById('share-btn')){setTimeout(addShareBtn,700);return;}
  const b=document.createElement('button');
  b.id='share-btn';
  b.className='btn-3d btn-sm';
  b.title='Share App URL (⌘U)';
  b.innerHTML='<span style="font-size:14px">📤</span> <span class="btn-text" style="font-size:12px;font-weight:700">Share App</span>';
  b.style.cssText='background:rgba(168,85,247,0.15);border:1px solid rgba(168,85,247,0.4);color:#d8b4fe;padding:5px 12px;border-radius:8px;cursor:pointer;display:flex;align-items:center;gap:5px';
  b.onclick=shareProject;
  a.insertBefore(b,a.firstChild);
})();

// ══════════════════════════════════════════════════════
//  SPLIT-SCREEN DUAL-PANE WORKSPACE ENGINE (`Phase 2`)
// ══════════════════════════════════════════════════════
window.toggleSplitWorkspace = function(forceOpen, initialPane) {
  const rightSlot = document.getElementById('content-right');
  const splitter = document.getElementById('workspace-splitter');
  const btn = document.getElementById('split-toggle-btn');
  const content = document.getElementById('content');
  if (!rightSlot || !splitter || !content) return;
  
  let open = (typeof forceOpen === 'boolean') ? forceOpen : rightSlot.style.display === 'none';
  if (open) {
    rightSlot.style.display = 'flex';
    splitter.style.display = 'block';
    content.style.flex = '1';
    content.style.width = '';
    if (btn) {
      btn.style.borderColor = 'var(--accent)';
      btn.style.background = 'var(--accent-glow)';
    }
    const paneToRender = initialPane || document.getElementById('split-pane-select')?.value || 'studio';
    renderSplitPane(paneToRender);
    try { try { _safeLS.set('agentic_os_split_active', 'true'); } catch {} } catch(e) {}
    toast('🗂️ Dual-pane split view active', 'ok', 2000);
  } else {
    rightSlot.style.display = 'none';
    splitter.style.display = 'none';
    content.style.flex = '1';
    content.style.width = '';
    if (btn) {
      btn.style.borderColor = 'var(--border-hi)';
      btn.style.background = 'var(--bg-2)';
    }
    try { try { _safeLS.set('agentic_os_split_active', 'false'); } catch {} } catch(e) {}
    toast('✕ Split view closed', 'ok', 1500);
  }
};

window.renderSplitPane = async function(paneId) {
  const slot = document.getElementById('pane-right-slot');
  if (!slot || !paneId) return;
  const sel = document.getElementById('split-pane-select');
  if (sel && sel.value !== paneId) sel.value = paneId;
  
  slot.innerHTML = `<div style="padding:24px;color:var(--text-2)">⚡ Initializing ${escHtml(paneId)} secondary workstation...</div>`;
  
  if (paneId === 'studio') {
    slot.innerHTML = `
      <div style="display:flex;flex-direction:column;height:100%;gap:12px">
        <div style="display:flex;justify-content:space-between;align-items:center;background:var(--bg-1);padding:10px 14px;border-radius:10px;border:1px solid var(--border)">
          <span style="font-weight:800;color:var(--accent)">⚡ Studio Code Buffer (Secondary Dock)</span>
          <button class="btn-3d btn-sm" onclick="nav('studio')" style="padding:4px 10px;font-size:11px">Open Full Studio ↗</button>
        </div>
        <div id="secondary-monaco-container" style="flex:1;min-height:320px;background:#04060f;border:1px solid var(--border-hi);border-radius:12px;padding:14px;font-family:monospace;font-size:12.5px;color:#a7f3d0;overflow:auto">
// Strick Tech Studio — Secondary Editor Dock
// Synchronized with primary workspace AST Code Graph

function initSecondaryBuffer() {
  console.debug("Secondary editor buffer loaded and ready.");
  return { status: "ready", mode: "live-sync", port: 8787 };
}

// Press ⌘S to save edits or run unit test suite
        </div>
      </div>`;
  } else if (paneId === 'browser') {
    if (typeof window.renderBrowserAgent === 'function') {
      await window.renderBrowserAgent();
      const orig = document.getElementById('pane-browser');
      if (orig && orig.innerHTML) slot.innerHTML = orig.innerHTML;
    }
  } else {
    const orig = document.getElementById('pane-' + paneId);
    const renderer = window.MASTER_PANE_REGISTRY[paneId];
    if (renderer) {
      try { await renderer(); } catch(e) {}
      if (orig && orig.innerHTML) {
        slot.innerHTML = orig.innerHTML;
      } else {
        slot.innerHTML = `<div style="padding:24px;color:var(--text-1)">Workstation ${escHtml(paneId)} active in primary slot.</div>`;
      }
    }
  }
};

window.setSplitRatio = function(leftRatio) {
  const content = document.getElementById('content');
  const rightSlot = document.getElementById('content-right');
  if (!content || !rightSlot) return;
  const mainWidth = document.getElementById('main')?.clientWidth || (window.innerWidth - 260);
  content.style.flex = 'none';
  content.style.width = Math.floor(mainWidth * leftRatio) + 'px';
  toast(`↔ Split ratio adjusted to Math.floor(leftRatio * 100)%`, 'ok', 1200);
};

window.swapSplitPanes = function() {
  const currentLeft = document.querySelector('.pane.active')?.id?.replace('pane-', '') || 'chat';
  const currentRight = document.getElementById('split-pane-select')?.value || 'studio';
  nav(currentRight);
  renderSplitPane(currentLeft);
  toast(`↔ Swapped: ${currentRight} primary, ${currentLeft} secondary`, 'ok', 2000);
};

window.setupSplitterResizer = function() {
  const splitter = document.getElementById('workspace-splitter');
  const content = document.getElementById('content');
  const main = document.getElementById('main');
  if (!splitter || !content || !main) return;
  let isResizing = false;
  
  splitter.addEventListener('mousedown', (e) => {
    isResizing = true;
    window._isSplitResizing = true;
    splitter.style.background = 'var(--accent)';
    document.body.style.cursor = 'col-resize';
    e.preventDefault();
  });
  
  document.addEventListener('mousemove', (e) => {
    if (!isResizing) return;
    const mainRect = main.getBoundingClientRect();
    let newWidth = e.clientX - mainRect.left;
    if (newWidth < 280) newWidth = 280;
    if (newWidth > mainRect.width - 280) newWidth = mainRect.width - 280;
    content.style.flex = 'none';
    content.style.width = newWidth + 'px';
  });
  
  document.addEventListener('mouseup', () => {
    if (isResizing) {
      isResizing = false;
      window._isSplitResizing = false;
      splitter.style.background = 'var(--border)';
      document.body.style.cursor = '';
    }
  });
  
  try {
    if (_safeLS.get('agentic_os_split_active') === 'true') {
      setTimeout(() => toggleSplitWorkspace(true), 600);
    }
  } catch(e) {}
};
setTimeout(() => window.setupSplitterResizer?.(), 500);

// ══════════════════════════════════════════════════════
//  STUDIO CONSOLE & TERMINAL DRAWER (`Phase 2`)
// ══════════════════════════════════════════════════════
window.switchStudioConsoleTab = function(tabId) {
  document.querySelectorAll('.studio-console-tab').forEach(el => {
    el.classList.remove('active');
    el.style.background = 'transparent';
    el.style.borderColor = 'var(--border)';
  });
  document.querySelectorAll('.studio-console-panel').forEach(el => el.style.display = 'none');
  const btn = document.getElementById('con-tab-' + tabId);
  const panel = document.getElementById('con-panel-' + tabId);
  if (btn) {
    btn.classList.add('active');
    btn.style.background = 'var(--accent-glow)';
    btn.style.borderColor = 'var(--accent)';
  }
  if (panel) panel.style.display = 'block';
};

window.toggleStudioConsoleDrawer = function() {
  const drawer = document.getElementById('studio-console-drawer');
  const btn = document.getElementById('con-collapse-btn');
  if (!drawer) return;
  if (drawer.style.height === '36px' || drawer.style.height === '34px') {
    drawer.style.height = '170px';
    if (btn) btn.textContent = '▼ Collapse';
  } else if (drawer.style.height === '170px') {
    drawer.style.height = '280px';
    if (btn) btn.textContent = '▲ Maximize';
  } else {
    drawer.style.height = '36px';
    if (btn) { btn.textContent = '▲ Expand'; }
  }
};

window.clearStudioConsole = function() {
  ['build', 'lint', 'hmr'].forEach(t => {
    const el = document.getElementById('con-panel-' + t);
    if (el) el.innerHTML = `<div>[${t.toUpperCase()}] Console cleared.</div>`;
  });
  const cnt = document.getElementById('con-hmr-count');
  if (cnt) cnt.textContent = '0';
  toast('🗑 Studio console cleared', 'ok', 1200);
};

window.logStudioConsole = function(tab, msg, isError = false) {
  const panel = document.getElementById('con-panel-' + tab);
  if (!panel) return;
  const line = document.createElement('div');
  line.style.cssText = `margin-top:6px;color:${isError ? '#f87171' : (tab === 'build' ? '#a7f3d0' : '#7dd3fc')};border-bottom:1px solid rgba(255,255,255,0.05);padding-bottom:3px`;
  line.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
  panel.appendChild(line);
  panel.scrollTop = panel.scrollHeight;
  if (tab === 'hmr') {
    const cnt = document.getElementById('con-hmr-count');
    if (cnt) cnt.textContent = String((parseInt(cnt.textContent || '0', 10) || 0) + 1);
  }
};

window.runStudioConsoleLint = async function() {
  // BUG FIX: this used to POST with no body (so the backend silently linted
  // Agentic OS's OWN source instead of the user's file) and its catch block
  // logged "Syntax validation check green." even when the request FAILED —
  // so the button was incapable of ever reporting a problem with your code.
  // It now sends the open file's content and reports real results, including
  // per-error detail and genuine failures.
  const file = (window.Studio && window.Studio.currentFile) || '';
  const content = (window.Studio && window.Studio.editor && typeof window.Studio.editor.getValue === 'function')
    ? window.Studio.editor.getValue()
    : null;

  switchStudioConsoleTab('lint');
  if (!file || content === null) {
    logStudioConsole('lint', 'Open a file in Studio first — nothing to check.', true);
    return;
  }
  logStudioConsole('lint', `Checking syntax of ${file}…`);

  try {
    const d = await AgenticAPI.post('/api/studio/lint', { path: file, content });
    if (!d) {
      logStudioConsole('lint', 'Linter returned no response — check the server connection.', true);
      return;
    }
    logStudioConsole('lint', d.message || (d.ok ? 'Syntax OK.' : 'Syntax issues found.'), !d.ok);
    (d.errors || []).forEach((err) => logStudioConsole('lint', `  • ${err}`, true));
  } catch (e) {
    logStudioConsole('lint', `Lint request failed: ${e && e.message ? e.message : e}`, true);
  }
};

// Hook Studio auto-save into console log
const _origStudioSaveFile = window.studioSaveFile;
if (typeof _origStudioSaveFile === 'function') {
  window.studioSaveFile = async function() {
    await _origStudioSaveFile();
    if (typeof logStudioConsole === 'function') {
      logStudioConsole('build', `💾 File saved: ${window.Studio?.currentFile || 'index.html'} — HMR reload triggered`);
      logStudioConsole('hmr', `HMR reload dispatched for ${window.Studio?.currentFile || 'index.html'}`);
    }
  };
}

// ══════════════════════════════════════════════════════
//  UX POLISH — Keyboard shortcuts + improvements
// ══════════════════════════════════════════════════════
document.addEventListener('keydown',e=>{
  if((e.metaKey||e.ctrlKey)&&e.key==='p'&&!e.shiftKey){e.preventDefault();nav('codesearch');setTimeout(()=>document.getElementById('cs-input')?.focus(),200);}
  if((e.metaKey||e.ctrlKey)&&e.key==='r'&&e.shiftKey){e.preventDefault();reviewCurrentFile();}
  if((e.metaKey||e.ctrlKey)&&e.key==='u'){e.preventDefault();shareProject();}
  if((e.metaKey||e.ctrlKey)&&e.key==='\\'){e.preventDefault();toggleSplitWorkspace();}
});

// Auto-focus chat on startup
setTimeout(()=>{if(document.querySelector('.pane.active')?.id==='pane-chat')document.getElementById('chat-input')?.focus();},1200);

// Add to command palette
if(typeof PALETTE_CMDS!=='undefined'){
  PALETTE_CMDS.unshift(
    {icon:'💬',label:'Prompt Library',desc:'Save & reuse AI prompts (⌘L)',action:()=>nav('prompts')},
    {icon:'🔍',label:'Search Code',desc:'Find anything in project (⌘P)',action:()=>nav('codesearch')},
    {icon:'🌐',label:'Share App',desc:'Get public URL (⌘U)',action:()=>shareProject()},
    {icon:'🔍',label:'Review Code',desc:'AI code review (⌘⇧R)',action:()=>reviewCurrentFile()},
    {icon:'🗂️',label:'Split Workspace',desc:'Dual-pane docking view (⌘\\)',action:()=>toggleSplitWorkspace()},
    {icon:'🖥️',label:'Studio Console',desc:'Run linter and check HMR events',action:()=>{nav('studio');runStudioConsoleLint();}},
  );
}


// ── Version history ────────────────────────────────────────────────────────
// Editing used to overwrite in place with no history, so the phrasing that
// worked was simply gone once you changed it.
async function showPromptHistory(pid) {
  let data;
  try {
    const r = await fetch(`/api/prompts/${encodeURIComponent(pid)}/versions`);
    if (!r.ok) { toast('History failed: '+await promptError(r), 'err'); return; }
    data = await r.json();
  } catch (ex) { toast('History error: '+ex?.message, 'err'); return; }

  const p = promptsData.find(x => x.id === pid);
  const versions = data.versions || [];
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.78);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
  overlay.innerHTML = `
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:14px;max-width:640px;width:100%;max-height:80vh;overflow:auto;padding:20px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <h3 style="margin:0;color:var(--text-0);font-size:15px">🕘 Version history — ${escHtml(p?.title || pid)}</h3>
        <button type="button" class="btn btn-ghost btn-sm" data-ph="close">✕</button>
      </div>
      <div style="border:1px solid var(--border);border-radius:8px;padding:10px;margin-bottom:12px;background:var(--bg-1)">
        <div style="font-size:10px;color:var(--accent);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Current</div>
        <div style="font-size:12px;color:var(--text-1);white-space:pre-wrap;word-break:break-word">${escHtml((p?.content || '').slice(0, 400))}</div>
      </div>
      ${versions.length ? versions.map(v => `
        <div style="border:1px solid var(--border);border-radius:8px;padding:10px;margin-bottom:8px">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:4px">
            <span style="font-size:11px;color:var(--text-3)">v${v.version_no} · ${escHtml(v.reason || 'edit')} · ${escHtml((v.created_at || '').replace('T',' ').slice(0,16))}</span>
            <button type="button" class="btn btn-ghost btn-sm" data-ph="restore" data-v="${v.version_no}">↺ Restore</button>
          </div>
          <div style="font-size:12px;color:var(--text-2);white-space:pre-wrap;word-break:break-word">${escHtml((v.content || '').slice(0, 400))}</div>
        </div>`).join('')
      : '<div style="color:var(--text-3);font-size:12px;padding:14px;text-align:center">No previous versions yet — history starts from your next edit.</div>'}
    </div>`;
  overlay.addEventListener('click', async (e) => {
    const act = e.target.closest('[data-ph]')?.dataset.ph;
    if (act === 'close' || e.target === overlay) { overlay.remove(); return; }
    if (act === 'restore') {
      const v = e.target.closest('[data-ph="restore"]').dataset.v;
      try {
        const r = await fetch(`/api/prompts/${encodeURIComponent(pid)}/versions/${v}/restore`, {method:'POST'});
        if (!r.ok) { toast('Restore failed: '+await promptError(r), 'err'); return; }
        const j = await r.json();
        // Be explicit when a restore couldn't bring everything back verbatim.
        if (j.demoted_category) toast('⚠️ That version\'s category no longer exists — set to general', 'warn');
        if (j.dropped_agent)    toast('⚠️ That version\'s agent no longer exists — pin cleared', 'warn');
        toast(`↺ Restored to v${v}`, 'ok');
        overlay.remove();
        renderPrompts();
      } catch (ex) { toast('Restore error: '+ex?.message, 'err'); }
    }
  });
  document.body.appendChild(overlay);
}
window.showPromptHistory = showPromptHistory;
window.createCategory = createCategory;
