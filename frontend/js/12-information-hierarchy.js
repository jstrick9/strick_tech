/*
 * Agentic OS — Information Hierarchy Engine (frontend/js/12-information-hierarchy.js)
 * Implements Strick Tech's 2-Tier Architecture (Universal Context + IVREN Project Deltas).
 */
(function() {
  'use strict';

  let currentHierarchyTab = 'tier1';
  let currentTier1File = 'about_me';
  let currentTier2Project = null;
  let currentIvrenSection = 'instructions';
  let tier1Cache = {};
  let tier2Cache = {};

  async function renderHierarchyPane() {
    try {
      const r = await fetch('/api/hierarchy/status');
      const data = await r.json();
      if (data.ok) {
        const pcountEl = document.getElementById('h-project-count');
        if (pcountEl) pcountEl.textContent = data.project_count || 0;
        
        // Populate project list if Tier 2 projects exist
        if (data.projects && data.projects.length > 0) {
          renderProjectList(data.projects);
          if (!currentTier2Project) {
            currentTier2Project = data.projects[0].project_id;
          }
        }
      }
      if (currentHierarchyTab === 'tier1') {
        await loadTier1File(currentTier1File);
      } else {
        await loadIvrenSection(currentTier2Project, currentIvrenSection);
      }
    } catch(err) {
      console.warn('Render Hierarchy Pane error:', err);
      if (window.showPaneError) window.showPaneError('hierarchy', err);
    }
  }

  window.switchHierarchyTab = function(tab) {
    currentHierarchyTab = tab;
    // MODULE MERGE: extended from a 2-way (tier1/tier2) toggle to a 3-way
    // toggle to also drive the folded-in "AI Guidelines" (Steering Files)
    // tab. Kept the same explicit per-button style-toggle pattern already
    // used here rather than a generic loop, to minimize the diff against
    // the existing working tier1/tier2 logic.
    const tabs = { tier1: 'h-tab-tier1', tier2: 'h-tab-tier2', guidelines: 'h-tab-guidelines' };
    const views = { tier1: 'h-view-tier1', tier2: 'h-view-tier2', guidelines: 'h-view-guidelines' };
    Object.keys(tabs).forEach(key => {
      const btn = document.getElementById(tabs[key]);
      if (!btn) return;
      const active = key === tab;
      btn.classList.toggle('active', active);
      btn.style.borderBottom = active ? '2px solid var(--accent)' : '2px solid transparent';
      btn.style.color = active ? 'var(--text-0)' : 'var(--text-2)';
    });
    Object.keys(views).forEach(key => {
      const view = document.getElementById(views[key]);
      if (!view) return;
      view.style.display = key === tab ? (key === 'guidelines' ? 'block' : 'flex') : 'none';
    });

    if (tab === 'tier1') {
      loadTier1File(currentTier1File);
    } else if (tab === 'tier2') {
      loadIvrenSection(currentTier2Project, currentIvrenSection);
    } else if (tab === 'guidelines') {
      renderGuidelinesTab();
    }
  };

  window.selectTier1File = async function(fileKey) {
    currentTier1File = fileKey;
    document.querySelectorAll('.t1-file-item').forEach(el => {
      el.style.background = 'transparent';
      el.style.border = '1px solid transparent';
    });
    const activeEl = document.getElementById('t1-item-' + fileKey);
    if (activeEl) {
      activeEl.style.background = 'rgba(91,138,248,.1)';
      activeEl.style.border = '1px solid var(--border-hi)';
    }
    await loadTier1File(fileKey);
  };

  async function loadTier1File(fileKey) {
    const titleMap = {
      'about_me': 'about_me.md (Who I am & My Mission)',
      'about_my_business': 'about_my_business.md (Company, ICP & Unique Value)',
      'about_my_voice': 'about_my_voice.md (Tone, Words to Love/Avoid — Highest Leverage)',
      'about_my_offers': 'about_my_offers.md (Core Products, Pricing & Deliverables)'
    };
    const titleEl = document.getElementById('t1-editor-title');
    if (titleEl) titleEl.textContent = 'Editing: ' + (titleMap[fileKey] || fileKey + '.md');

    try {
      const r = await fetch('/api/hierarchy/tier1');
      const data = await r.json();
      if (data.ok) {
        tier1Cache = data;
        const textarea = document.getElementById('t1-editor-textarea');
        if (textarea) textarea.value = data[fileKey] || '';
        if (typeof updateLiveHierarchySplitPreview === 'function') updateLiveHierarchySplitPreview();
      }
    } catch(err) {
      console.warn('Load Tier1 error:', err);
    }
  }

  window.saveCurrentTier1File = async function() {
    const textarea = document.getElementById('t1-editor-textarea');
    if (!textarea) return;
    const content = textarea.value;
    const payload = {};
    payload[currentTier1File] = content;

    try {
      const r = await fetch('/api/hierarchy/tier1', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await r.json();
      if (data.ok) {
        if (window.toast) toast('✅ Saved ' + currentTier1File + '.md to Universal Context!', 'ok', 3000);
        tier1Cache[currentTier1File] = content;
      } else {
        if (window.toast) toast('Error saving file: ' + data.detail, 'err');
      }
    } catch(err) {
      if (window.toast) toast('Network error saving file', 'err');
    }
  };

  function renderProjectList(projects) {
    const listEl = document.getElementById('t2-project-list');
    if (!listEl) return;
    // `pid` went into onclick="selectTier2Project(${jsArg(pid)})" unescaped. The
    // server now rejects ids outside [a-z0-9_], so a quote can no longer reach
    // here — but building an inline handler from data is the pattern that has
    // already caused breakage elsewhere in this codebase, so use delegation.
    listEl.innerHTML = projects.map(p => {
      const pid = p.project_id || p.name;
      const name = p.meta?.name || pid;
      const isSelected = currentTier2Project === pid;
      return `<div data-h-project="${escHtml(pid)}" style="padding:9px 12px;border-radius:var(--radius-sm);cursor:pointer;background:${isSelected ? 'rgba(91,138,248,.1)' : 'transparent'};border:1px solid ${isSelected ? 'var(--border-hi)' : 'transparent'};font-size:13px;font-weight:${isSelected ? 700 : 500};display:flex;align-items:center;justify-content:space-between;gap:8px">
        <span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">📁 ${escHtml(name)}</span>
        <button type="button" data-h-delete="${escHtml(pid)}" title="Delete this project hierarchy"
                style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:12px;padding:0 2px;flex-shrink:0">🗑</button>
      </div>`;
    }).join('');
    wireProjectListEvents(listEl);
  }

  function wireProjectListEvents(listEl) {
    if (listEl.dataset.wired) return;
    listEl.dataset.wired = '1';
    listEl.addEventListener('click', async (e) => {
      const del = e.target.closest('[data-h-delete]');
      if (del) {
        e.stopPropagation();
        const pid = del.dataset.hDelete;
        const confirmFn = window.gmDanger || (async (t, m) => window.confirm(m));
        if (!(await confirmFn('Delete Project Hierarchy',
              `Delete "${pid}" and all five IVREN files? This cannot be undone.`))) return;
        try {
          const r = await fetch('/api/hierarchy/projects/' + encodeURIComponent(pid), {method:'DELETE'});
          if (!r.ok) {
            let detail = '';
            try { detail = (await r.json()).detail || ''; } catch (err) { /* non-JSON */ }
            window.toast?.('Delete failed: ' + (detail || 'HTTP ' + r.status), 'err');
            return;
          }
          window.toast?.('🗑 Deleted ' + pid, 'ok');
          if (currentTier2Project === pid) currentTier2Project = null;
          renderHierarchyPane();
        } catch (ex) { window.toast?.('Delete error: ' + ex?.message, 'err'); }
        return;
      }
      const item = e.target.closest('[data-h-project]');
      if (item) selectTier2Project(item.dataset.hProject);
    });
  }

  window.selectTier2Project = async function(pid) {
    currentTier2Project = pid;
    document.querySelectorAll('#t2-project-list > div').forEach(el => {
      el.style.background = 'transparent';
      el.style.border = '1px solid transparent';
      el.style.fontWeight = '500';
    });
    const activeEl = document.querySelector(`[data-h-project="${CSS.escape(pid)}"]`);
    if (activeEl) {
      activeEl.style.background = 'rgba(91,138,248,.1)';
      activeEl.style.border = '1px solid var(--border-hi)';
      activeEl.style.fontWeight = '700';
    }
    await loadIvrenSection(pid, currentIvrenSection);
  };

  window.switchIvrenSection = async function(sec) {
    currentIvrenSection = sec;
    document.querySelectorAll('.ivren-tab').forEach(el => {
      el.style.borderBottom = '2px solid transparent';
      el.style.color = 'var(--text-2)';
    });
    const activeTab = document.getElementById('ivren-tab-' + sec);
    if (activeTab) {
      activeTab.style.borderBottom = '2px solid var(--accent)';
      activeTab.style.color = 'var(--text-0)';
    }

    const appendBar = document.getElementById('t2-notes-append-bar');
    if (appendBar) appendBar.style.display = sec === 'notes' ? 'flex' : 'none';

    await loadIvrenSection(currentTier2Project, sec);
  };

  async function loadIvrenSection(pid, sec) {
    if (!pid) {
      const textarea = document.getElementById('t2-ivren-textarea');
      if (textarea) textarea.value = '# No Project Selected\nClick "+ New Project Hierarchy" to get started.';
      return;
    }
    const titleEl = document.getElementById('t2-project-title');
    if (titleEl) titleEl.textContent = pid.replace(/_/g, ' ').toUpperCase() + ' — ' + sec.toUpperCase();

    try {
      const r = await fetch('/api/hierarchy/projects/' + encodeURIComponent(pid));
      const data = await r.json();
      if (data.ok && data.ivren) {
        tier2Cache[pid] = data.ivren;
        const textarea = document.getElementById('t2-ivren-textarea');
        if (textarea) textarea.value = data.ivren[sec] || '';
        if (typeof updateLiveHierarchySplitPreview === 'function') updateLiveHierarchySplitPreview();
      }
    } catch(err) {
      console.warn('Load IVREN error:', err);
    }
  }

  window.saveCurrentIvrenSection = async function() {
    if (!currentTier2Project) return;
    const textarea = document.getElementById('t2-ivren-textarea');
    if (!textarea) return;
    const content = textarea.value;
    const payload = {};
    payload[currentIvrenSection] = content;

    try {
      const r = await fetch('/api/hierarchy/projects/' + encodeURIComponent(currentTier2Project) + '/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await r.json();
      if (data.ok) {
        if (window.toast) toast('✅ Saved IVREN section: ' + currentIvrenSection + ' for project ' + currentTier2Project, 'ok', 3000);
      } else {
        if (window.toast) toast('Error saving section: ' + data.detail, 'err');
      }
    } catch(err) {
      if (window.toast) toast('Network error saving IVREN section', 'err');
    }
  };

  window.appendNoteToCurrentProject = async function() {
    if (!currentTier2Project) return;
    const inputEl = document.getElementById('t2-notes-input');
    if (!inputEl || !inputEl.value.trim()) return;
    const noteText = inputEl.value.trim();

    try {
      const r = await fetch('/api/hierarchy/projects/' + encodeURIComponent(currentTier2Project) + '/notes/append', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note: noteText, author: 'user' })
      });
      const data = await r.json();
      if (data.ok) {
        inputEl.value = '';
        if (window.toast) toast('📈 Compounding Feedback Note Logged!', 'ok', 3000);
        await loadIvrenSection(currentTier2Project, 'notes');
      }
    } catch(err) {
      if (window.toast) toast('Error appending feedback note', 'err');
    }
  };

  // ── AI Guidelines Tab (merged from the former standalone Steering pane) ─────
  // Reuses the existing, working /api/steering/* backend (backend/routers/
  // steering.py) unchanged — only the presentation layer moved. This keeps
  // the merge low-risk: no DB schema changes, no endpoint changes, just a
  // new home for the same UI inside the Hierarchy pane's third tab.
  async function renderGuidelinesTab() {
    const host = document.getElementById('h-view-guidelines');
    if (!host) return;

    const [files, compiled, patterns] = await Promise.all([
      fetch('/api/steering').then(r=>r.ok?r.json().catch(()=>null):null).catch(()=>null),
      fetch('/api/steering/compiled').then(r=>r.ok?r.json().catch(()=>null):null).catch(()=>null),
      fetch('/api/steering/learned/patterns').then(r=>r.ok?r.json().catch(()=>null):null).catch(()=>null),
    ]);
    const filesData    = files    || { files: [] };
    const compiledData = compiled || { context: '', length: 0 };
    const patternsData = patterns || { patterns: [] };

    host.innerHTML = `
    <div style="max-width:900px;margin:0 auto">
      <div class="section-head" style="margin-bottom:16px">
        <div>
          <h2 style="font-size:18px;margin:0 0 4px">🧭 AI Guidelines — Coding & Project Rules</h2>
          <p style="color:var(--text-2);font-size:13px;margin:0">Freeform rules injected into every AI prompt alongside your Tier 1/2 context above — like Kiro steering, Cursor .cursorrules, or Windsurf Memories.</p>
        </div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-sm" data-act-click="steerNew()">＋ New Rule File</button>
          <button class="btn-sm btn-ghost" data-act-click="steerLearnFromChat()">🧠 Auto-Learn</button>
          <button class="btn-sm btn-ghost" data-act-click="steerPromotePatterns()">⬆ Promote Patterns</button>
        </div>
      </div>

      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;margin-bottom:16px;overflow:hidden">
        <div style="padding:10px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px">
          <span style="font-weight:700;font-size:13px">📡 Compiled Guidelines Context</span>
          <span style="font-size:11px;color:var(--text-3)">
            ${compiledData.llm_chars||compiledData.length||0} chars injected into every prompt
            ${compiledData.truncated_for_llm?'<span style="color:var(--warning)">⚠️ truncated</span>':''}
          </span>
          <span style="margin-left:auto;font-size:11px;${(compiledData.length||0)>0?'color:var(--success)':'color:var(--text-3)'}">
            ${(compiledData.length||0)>0?'✅ Active':'⚠️ No rule files enabled'}
          </span>
        </div>
        <div style="padding:12px 16px;max-height:120px;overflow-y:auto;font-family:monospace;font-size:11px;color:var(--text-2);white-space:pre-wrap">${escHtml((compiledData.context||'').slice(0,800))}${(compiledData.length||0)>800?'…':''}</div>
      </div>

      <div style="font-size:13px;font-weight:700;margin-bottom:10px">Rule Files (${(filesData.files||[]).length})</div>
      <div id="steer-file-list">
        ${(filesData.files||[]).map(f=>`
          <div class="steer-card" data-file-id="${escHtml(f.id)}">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
              <button class="steer-toggle ${f.enabled?'on':''}" title="${f.enabled?'Enabled':'Disabled'}"></button>
              <strong style="color:var(--text-0)">${escHtml(f.title)}</strong>
              <span class="steer-cat">${escHtml(f.category||'general')}</span>
              ${f.auto_learned?'<span class="steer-auto-badge">Auto-learned</span>':''}
              <div style="margin-left:auto;display:flex;gap:5px">
                <button class="btn-sm steer-edit-btn">✏</button>
                <button class="btn-sm steer-delete-btn" style="color:var(--danger)">🗑</button>
              </div>
            </div>
            <div style="font-size:11px;color:var(--text-2);font-family:monospace;line-height:1.6;max-height:80px;overflow:hidden">${escHtml((f.content||'').slice(0,300))}${(f.content||'').length>300?'…':''}</div>
          </div>
        `).join('') || '<div style="color:var(--text-3);padding:16px;text-align:center">No rule files yet. Create one or click Auto-Learn.</div>'}
      </div>

      ${(patternsData.patterns||[]).length ? `
      <div style="margin-top:20px;font-size:13px;font-weight:700;margin-bottom:10px">🧠 Learned Patterns (${patternsData.count||0})</div>
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;overflow:hidden">
        ${(patternsData.patterns||[]).slice(0,10).map(p=>`
          <div style="display:flex;align-items:center;gap:8px;padding:8px 14px;border-bottom:1px solid var(--border);font-size:12px">
            <span style="color:var(--text-3);width:140px;flex-shrink:0">${escHtml(p.pattern_key||'')}</span>
            <span style="color:var(--text-1);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml((p.pattern_val||'').slice(0,80))}</span>
            <span style="color:var(--accent);font-weight:700;width:40px;text-align:right">${Math.round((p.confidence||0)*100)}%</span>
            <span style="color:var(--text-3);font-size:10px;width:50px">×${p.occurrences||1}</span>
            ${p.promoted?'<span style="font-size:10px;color:var(--success)">✅</span>':''}
          </div>
        `).join('')}
      </div>` : ''}
    </div>`;

    // BUG FIX (quote-collision, same class already fixed elsewhere in this
    // codebase for Swarm/Chat/Memory): the toggle/edit/delete buttons above
    // used to be built as inline onclick="steerToggle(${JSON.stringify(f.id)},this)"
    // strings. JSON.stringify() wraps its output in double quotes, which
    // collide with the onclick attribute's own double quotes — the browser's
    // HTML attribute parser truncates the handler at the first unescaped
    // quote it sees. Reproduced live: clicking a rule file's toggle button
    // threw `Uncaught SyntaxError: Failed to execute 'click' on
    // 'HTMLElement': Unexpected end of input` and never actually flipped
    // the enabled state. Since steering file ids are user-influenced
    // strings (derived from a user-typed title), this was a real,
    // reachable bug, not just a theoretical one. Fixed by reading the id
    // from a `data-file-id` attribute and wiring real addEventListener
    // handlers instead of serializing it into the attribute string.
    host.querySelectorAll('.steer-card').forEach(card => {
      const fileId = card.dataset.fileId;
      card.querySelector('.steer-toggle')?.addEventListener('click', (e) => steerToggle(fileId, e.currentTarget));
      card.querySelector('.steer-edit-btn')?.addEventListener('click', () => steerEdit(fileId));
      card.querySelector('.steer-delete-btn')?.addEventListener('click', () => steerDelete(fileId));
    });
  }
  // Exposed so the compiled-context preview / other panes can re-render this
  // tab specifically (mirrors window.renderHierarchyPane for tier1/tier2).
  window.renderGuidelinesTab = renderGuidelinesTab;

  window.steerNew = async function() {
    const title = await gmPrompt('Rule file title:', 'My Convention');
    if (!title) return;
    const cat   = await gmPrompt('Category (stack|style|architecture|context|custom):', 'custom');
    const overlay = document.createElement('div');
    overlay.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    overlay.innerHTML=`
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:14px;width:600px;max-height:80vh;display:flex;flex-direction:column;padding:20px;gap:12px">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <h3 style="margin:0">New Rule File: ${escHtml(title)}</h3>
          <button onclick="this.closest('[style*=\\"fixed\\"]').remove()" style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
        </div>
        <textarea id="steer-new-content" rows="15" style="flex:1;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:12px;font-family:monospace;padding:10px;resize:none" placeholder="# ${escHtml(title)}\n\nWrite your project rules and conventions here..."></textarea>
        <div style="display:flex;gap:8px;justify-content:flex-end">
          <button class="btn-sm" onclick="this.closest('[style*=\\"fixed\\"]').remove()">Cancel</button>
          <button class="btn" data-title="${escHtml(title)}" data-cat="${escHtml(cat||'custom')}" data-act-click="steerSaveNew($data.title,$data.cat,$this)">💾 Save</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
  };

  window.steerSaveNew = async function(title, cat, btn) {
    const content = document.getElementById('steer-new-content')?.value||'';
    if (!content.trim()) { gmAlert('Add some content first'); return; }
    try {
      await fetch('/api/steering',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({title,category:cat,content,enabled:true})});
      btn.closest('[style*="fixed"]').remove();
      renderGuidelinesTab();
      if (window.toast) toast('✅ Rule file saved', 'ok');
    } catch(ex) { gmAlert('Save failed: '+ex.message); }
  };

  window.steerToggle = async function(fileId, btn) {
    try {
      const r = await fetch(`/api/steering/${encodeURIComponent(fileId)}/toggle`,{method:'POST'});
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const d = await r.json();
      if (!d.ok) throw new Error(d.error||'Toggle failed');
      renderGuidelinesTab();
    } catch(ex) {
      if (window.toast) toast('⚠️ Toggle failed: ' + ex.message, 'err', 3000);
    }
  };

  window.steerEdit = async function(fileId) {
    const r = await fetch(`/api/steering/${encodeURIComponent(fileId)}`);
    const f = await r.json();
    const overlay = document.createElement('div');
    overlay.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    overlay.innerHTML=`
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:14px;width:700px;max-height:85vh;display:flex;flex-direction:column;padding:20px;gap:12px">
        <div style="display:flex;align-items:center;gap:8px">
          <h3 style="margin:0;flex:1">✏ ${escHtml(f.title||fileId)}</h3>
          <button class="steer-modal-close-btn" style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
        </div>
        <textarea id="steer-edit-ta" rows="18" style="flex:1;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:12px;font-family:monospace;padding:10px;resize:none">${escHtml(f.content||'')}</textarea>
        <div style="display:flex;gap:8px;justify-content:flex-end">
          <button class="btn-sm steer-modal-cancel-btn">Cancel</button>
          <button class="btn steer-modal-save-btn">💾 Save</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    // BUG FIX: same quote-collision class as the file-card buttons above —
    // `fileId` is a user-influenced string (derived from a user-typed rule
    // title), so serializing it via JSON.stringify() straight into an
    // onclick="..." attribute could truncate/break the handler for any id
    // containing a double quote. Wired via addEventListener + closure over
    // the real `fileId` variable instead.
    overlay.querySelector('.steer-modal-close-btn')?.addEventListener('click', () => overlay.remove());
    overlay.querySelector('.steer-modal-cancel-btn')?.addEventListener('click', () => overlay.remove());
    overlay.querySelector('.steer-modal-save-btn')?.addEventListener('click', (e) => steerSaveEdit(fileId, e.currentTarget));
  };

  window.steerSaveEdit = async function(fileId, btn) {
    const ta = document.getElementById('steer-edit-ta');
    const c  = ta?.value ?? '';
    try {
      btn.textContent = '⏳ Saving…';
      btn.disabled = true;
      const r = await fetch(`/api/steering/${encodeURIComponent(fileId)}`, {
        method:'PUT', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({content: c})
      });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      btn.closest('[style*="fixed"]').remove();
      renderGuidelinesTab();
      if (window.toast) toast('✅ Rule file saved', 'ok');
    } catch(ex) {
      btn.textContent = '💾 Save';
      btn.disabled = false;
      gmAlert('Save failed: ' + ex.message);
    }
  };

  window.steerDelete = async function(fileId) {
    if (!(await gmDanger('Delete Rule File', 'This rule will no longer be injected into prompts.', 'Delete'))) return;
    try {
      const r = await fetch(`/api/steering/${encodeURIComponent(fileId)}`,{method:'DELETE'});
      const d = await r.json();
      if (window.toast) toast(d.deleted !== false ? '🗑 Rule file deleted' : '⚠️ File not found', d.deleted !== false ? 'ok' : 'err', 2000);
    } catch(ex) { if (window.toast) toast('⚠️ Delete failed', 'err', 2000); }
    renderGuidelinesTab();
  };

  window.steerLearnFromChat = async function() {
    if (window.toast) toast('🧠 Learning from your chat history…', 'ok');
    try {
      const r = await fetch('/api/steering/learn/from-chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({limit:100})});
      const d = await r.json();
      if (d.ok) {
        gmAlert(`✅ Learned ${d.stored_patterns} patterns from your chat history!\n\nClick "Promote Patterns" to create a rule file.`);
        renderGuidelinesTab();
      } else {
        gmAlert(d.error||'Nothing to learn yet. Chat more first!');
      }
    } catch(ex) { gmAlert('Learn failed: '+ex.message); }
  };

  window.steerPromotePatterns = async function() {
    try {
      const r = await fetch('/api/steering/learn/promote',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({min_confidence:0.5})});
      const d = await r.json();
      if (d.ok) {
        gmAlert(`✅ Promoted ${d.patterns_promoted} patterns into a new rule file!\n\n"${d.file_id}" is now active.`);
        renderGuidelinesTab();
      } else {
        gmAlert(d.error||'No patterns ready to promote yet. Run Auto-Learn first.');
      }
    } catch(ex) { gmAlert('Promote failed: '+ex.message); }
  };

  // ── Modals & Wizards ────────────────────────────────────────────────────────
  window.openHierarchyInterview = function() {
    let modal = document.getElementById('hierarchy-interview-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'hierarchy-interview-modal';
      modal.className = 'modal-back';
      modal.style.cssText = 'position:fixed;inset:0;background:rgba(4,6,14,.85);z-index:11000;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(6px)';
      modal.innerHTML = `
        <div class="modal" style="background:var(--bg-1);border:1px solid var(--border-hi);border-radius:16px;width:100%;max-width:640px;max-height:90vh;overflow-y:auto;padding:28px;box-shadow:0 32px 80px rgba(0,0,0,.7)">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
            <div style="font-size:18px;font-weight:800;display:flex;align-items:center;gap:8px">
              <span>🤖</span> AI Interview: Build Universal Context in 2 Minutes
            </div>
            <button data-hide="id:hierarchy-interview-modal" style="background:none;border:none;color:var(--text-2);font-size:20px;cursor:pointer">×</button>
          </div>
          <div style="font-size:13px;color:var(--text-2);line-height:1.6;margin-bottom:20px">
            Answer these 4 master questions once. We'll automatically structure your 4 Tier 1 Markdown files (<code style="color:var(--accent)">about_me</code>, <code style="color:var(--accent)">about_my_business</code>, <code style="color:var(--accent)">about_my_voice</code>, <code style="color:var(--accent)">about_my_offers</code>).
          </div>
          <div style="display:flex;flex-direction:column;gap:16px">
            <div>
              <label style="font-size:12.5px;font-weight:700;display:block;margin-bottom:6px;color:var(--text-0)">1. Who are you & what is your mission? (The 1-line dinner party intro)</label>
              <textarea id="inv-q1" placeholder="e.g. I am Joshua Strickland, founder of Strick Tech. I build the Agentic OS Platform across Free, Pro, and Enterprise editions to empower autonomous multi-agent engineering workflows..." style="width:100%;height:64px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;color:var(--text-0);font-size:13px;resize:none"></textarea>
            </div>
            <div>
              <label style="font-size:12.5px;font-weight:700;display:block;margin-bottom:6px;color:var(--text-0)">2. What does your business do & who is your Ideal Customer Profile (ICP)?</label>
              <textarea id="inv-q2" placeholder="e.g. We sell Agentic OS Studio to technical founders, dev shops, and enterprise leaders who want local-first agent orchestration..." style="width:100%;height:64px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;color:var(--text-0);font-size:13px;resize:none"></textarea>
            </div>
            <div>
              <label style="font-size:12.5px;font-weight:700;display:block;margin-bottom:6px;color:var(--text-0)">3. How do you like things written? Tone, Words to LOVE & Words to AVOID (Highest Leverage)</label>
              <textarea id="inv-q3" placeholder="e.g. Crisp, punchy, high-signal. Use bullet points and exact code. LOVE: high-leverage, compounding, robust. AVOID: delve, synergy, game-changer..." style="width:100%;height:64px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;color:var(--text-0);font-size:13px;resize:none"></textarea>
            </div>
            <div>
              <label style="font-size:12.5px;font-weight:700;display:block;margin-bottom:6px;color:var(--text-0)">4. What are your current offers, pricing & packages?</label>
              <textarea id="inv-q4" placeholder="e.g. Agentic OS Open Source (Free local app), Pro Pack ($49/mo), and Enterprise Governance Tower ($2,500 setup)..." style="width:100%;height:64px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;color:var(--text-0);font-size:13px;resize:none"></textarea>
            </div>
          </div>
          <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:24px">
            <button data-hide="id:hierarchy-interview-modal" class="btn btn-ghost">Cancel</button>
            <button data-act-click="submitHierarchyInterview()" class="btn btn-primary">⚡ Generate 4 Tier 1 Context Files</button>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
    }
    modal.style.display = 'flex';
  };

  window.submitHierarchyInterview = async function() {
    const q1 = document.getElementById('inv-q1')?.value || 'AI Builder';
    const q2 = document.getElementById('inv-q2')?.value || 'Agentic OS Platform';
    const q3 = document.getElementById('inv-q3')?.value || 'Clear, punchy, actionable';
    const q4 = document.getElementById('inv-q4')?.value || 'Open Source & Pro Edition';

    try {
      const r = await fetch('/api/hierarchy/tier1/interview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name_and_role: q1,
          business_and_icp: q2,
          voice_and_words: q3,
          offers_and_pricing: q4
        })
      });
      const data = await r.json();
      if (data.ok) {
        document.getElementById('hierarchy-interview-modal').style.display = 'none';
        if (window.toast) toast('⚡ Universal Context generated & saved across all 4 files!', 'ok', 4000);
        await renderHierarchyPane();
      }
    } catch(err) {
      if (window.toast) toast('Error submitting interview', 'err');
    }
  };

  window.openNewProjectIvrenModal = function() {
    let modal = document.getElementById('hierarchy-new-project-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'hierarchy-new-project-modal';
      modal.className = 'modal-back';
      modal.style.cssText = 'position:fixed;inset:0;background:rgba(4,6,14,.85);z-index:11000;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(6px)';
      modal.innerHTML = `
        <div class="modal" style="background:var(--bg-1);border:1px solid var(--border-hi);border-radius:16px;width:100%;max-width:480px;padding:28px;box-shadow:0 32px 80px rgba(0,0,0,.7)">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
            <div style="font-size:18px;font-weight:800;display:flex;align-items:center;gap:8px">
              <span>📁</span> Create Tier 2 Project Hierarchy (IVREN)
            </div>
            <button data-hide="id:hierarchy-new-project-modal" style="background:none;border:none;color:var(--text-2);font-size:20px;cursor:pointer">×</button>
          </div>
          <div style="font-size:12.5px;color:var(--text-2);margin-bottom:18px">
            Every project gets the exact same 5 compounding subfolders: <strong style="color:var(--text-0)">I</strong>nstructions, <strong style="color:var(--text-0)">V</strong>oice, <strong style="color:var(--text-0)">R</strong>eferences, <strong style="color:var(--text-0)">E</strong>xamples, and <strong style="color:var(--text-0)">N</strong>otes.
          </div>
          <div style="display:flex;flex-direction:column;gap:12px">
            <div>
              <label style="font-size:12px;font-weight:700;display:block;margin-bottom:4px;color:var(--text-0)">Project ID (URL-friendly)</label>
              <input id="np-id" placeholder="e.g. newsletter, client_work, youtube" style="width:100%;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;color:var(--text-0);font-size:13px">
            </div>
            <div>
              <label style="font-size:12px;font-weight:700;display:block;margin-bottom:4px;color:var(--text-0)">Display Name</label>
              <input id="np-name" placeholder="e.g. Weekly AI Newsletter" style="width:100%;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;color:var(--text-0);font-size:13px">
            </div>
            <div>
              <label style="font-size:12px;font-weight:700;display:block;margin-bottom:4px;color:var(--text-0)">Target Audience</label>
              <input id="np-audience" placeholder="e.g. AI builders and product managers" style="width:100%;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;color:var(--text-0);font-size:13px">
            </div>
            <div>
              <label style="font-size:12px;font-weight:700;display:block;margin-bottom:4px;color:var(--text-0)">Brief Description</label>
              <input id="np-desc" placeholder="e.g. Weekly high-signal deep dives" style="width:100%;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;color:var(--text-0);font-size:13px">
            </div>
          </div>
          <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:20px">
            <button data-hide="id:hierarchy-new-project-modal" class="btn btn-ghost">Cancel</button>
            <button data-act-click="submitNewProjectIvren()" class="btn btn-primary">✨ Create IVREN Folders</button>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
    }
    modal.style.display = 'flex';
  };

  window.submitNewProjectIvren = async function() {
    const pid = document.getElementById('np-id')?.value.trim();
    const name = document.getElementById('np-name')?.value.trim() || pid;
    const audience = document.getElementById('np-audience')?.value.trim() || 'General audience';
    const desc = document.getElementById('np-desc')?.value.trim() || 'Specialized project hierarchy';

    if (!pid) {
      if (window.toast) toast('Please enter a Project ID', 'err');
      return;
    }

    try {
      const r = await fetch('/api/hierarchy/projects/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: pid, name: name, audience: audience, description: desc })
      });
      const data = await r.json();
      if (data.ok) {
        document.getElementById('hierarchy-new-project-modal').style.display = 'none';
        if (window.toast) toast('🎉 Project ' + pid + ' IVREN Hierarchy created!', 'ok', 3500);
        currentTier2Project = pid;
        switchHierarchyTab('tier2');
        await renderHierarchyPane();
      }
    } catch(err) {
      if (window.toast) toast('Error creating project hierarchy', 'err');
    }
  };

  let isHierarchySplitOpen = false;
  let hierarchySplitTimeout = null;

  window.toggleHierarchySplitPreview = function() {
    isHierarchySplitOpen = !isHierarchySplitOpen;
    const splitPanel = document.getElementById('h-live-split-panel');
    const toggleBtn = document.getElementById('h-split-toggle-btn');
    if (splitPanel) {
      splitPanel.style.display = isHierarchySplitOpen ? 'flex' : 'none';
    }
    if (toggleBtn) {
      toggleBtn.classList.toggle('btn-primary', isHierarchySplitOpen);
      toggleBtn.classList.toggle('btn-ghost', !isHierarchySplitOpen);
    }
    if (isHierarchySplitOpen) {
      updateLiveHierarchySplitPreview();
    }
  };

  function updateLiveHierarchySplitPreview() {
    if (!isHierarchySplitOpen) return;
    if (hierarchySplitTimeout) clearTimeout(hierarchySplitTimeout);
    hierarchySplitTimeout = setTimeout(async () => {
      try {
        const url = '/api/hierarchy/compiled-context' + (currentTier2Project && currentHierarchyTab === 'tier2' ? '?project_id=' + encodeURIComponent(currentTier2Project) : '');
        const r = await fetch(url);
        const data = await r.json();
        if (data.ok) {
          const textarea = document.getElementById('h-live-split-textarea');
          const stats = document.getElementById('h-live-split-stats');
          if (textarea) textarea.value = data.compiled_context || '';
          if (stats) stats.textContent = `📊 ${data.char_count} chars (~${data.estimated_tokens} tokens)`;
        }
      } catch(err) {}
    }, 250);
  }

  // Bind live typing inside editors
  setTimeout(() => {
    const t1Text = document.getElementById('t1-editor-textarea');
    const t2Text = document.getElementById('t2-ivren-textarea');
    if (t1Text) t1Text.addEventListener('input', updateLiveHierarchySplitPreview);
    if (t2Text) t2Text.addEventListener('input', updateLiveHierarchySplitPreview);
  }, 500);

  window.previewCompiledContext = async function() {
    let modal = document.getElementById('hierarchy-preview-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'hierarchy-preview-modal';
      modal.className = 'modal-back';
      modal.style.cssText = 'position:fixed;inset:0;background:rgba(4,6,14,.85);z-index:11000;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(6px)';
      modal.innerHTML = `
        <div class="modal" style="background:var(--bg-1);border:1px solid var(--border-hi);border-radius:16px;width:100%;max-width:760px;max-height:88vh;display:flex;flex-direction:column;padding:24px;box-shadow:0 32px 80px rgba(0,0,0,.7)">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;flex-shrink:0">
            <div style="font-size:17px;font-weight:800;display:flex;align-items:center;gap:8px">
              <span>📜</span> Live XML System Prompt Injection Preview
            </div>
            <button data-hide="id:hierarchy-preview-modal" style="background:none;border:none;color:var(--text-2);font-size:20px;cursor:pointer">×</button>
          </div>
          <div style="font-size:12.5px;color:var(--text-2);margin-bottom:12px;flex-shrink:0">
            This exact XML/Markdown context is automatically injected into every Agentic OS chat, swarm query, and specialized agent session:
          </div>
          <textarea id="preview-compiled-textarea" readonly style="flex:1;min-height:360px;width:100%;background:var(--bg-0);border:1px solid var(--border);border-radius:var(--radius-sm);padding:14px;color:var(--text-0);font-family:monospace;font-size:12px;line-height:1.5;resize:none;outline:none"></textarea>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-top:16px;flex-shrink:0">
            <span id="preview-compiled-stats" style="font-size:11.5px;color:var(--text-3);font-weight:600"></span>
            <button data-hide="id:hierarchy-preview-modal" class="btn btn-primary">Close Preview</button>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
    }
    modal.style.display = 'flex';

    try {
      const url = '/api/hierarchy/compiled-context' + (currentTier2Project && currentHierarchyTab === 'tier2' ? '?project_id=' + encodeURIComponent(currentTier2Project) : '');
      const r = await fetch(url);
      const data = await r.json();
      if (data.ok) {
        document.getElementById('preview-compiled-textarea').value = data.compiled_context || '';
        document.getElementById('preview-compiled-stats').textContent = `📊 Character Count: ${data.char_count} (~${data.estimated_tokens} tokens)`;
      }
    } catch(err) {
      document.getElementById('preview-compiled-textarea').value = 'Error fetching compiled context.';
    }
  };

  // Register with window.PANE_RENDERERS and globally
  if (typeof window.PANE_RENDERERS === 'undefined') window.PANE_RENDERERS = {};
  window.PANE_RENDERERS['hierarchy'] = renderHierarchyPane;
  window.renderHierarchy = renderHierarchyPane;
  window.renderHierarchyPane = renderHierarchyPane;

  // Register command in PALETTE_CMDS if available
  setTimeout(() => {
    if (typeof PALETTE_CMDS !== 'undefined') {
      PALETTE_CMDS.unshift({
        icon: '🧭',
        label: 'Information Hierarchy',
        desc: 'Universal Business Context + Project IVREN',
        action: () => nav('hierarchy')
      });
    }
  }, 300);

  console.debug('%c✅ Information Hierarchy Engine (Universal Context + IVREN) loaded', 'color:#a78bfa;font-weight:bold');
})();
