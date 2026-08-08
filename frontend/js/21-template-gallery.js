/**
 * Agentic OS — Template Gallery
 * Full CRUD: browse, preview, insert into chat, scaffold to Studio, create/edit/delete custom templates.
 */

(function() {
  'use strict';

  var allTemplates = [];
  var templateCategory = 'all';
  var _tmplSort = 'name';
  var CUSTOM_TEMPLATES_KEY = 'agentic_os_custom_templates';

  // ── Custom Template Storage ────────────────────────────────────
  function getCustomTemplates() {
    try {
      var s = _safeLS.get(CUSTOM_TEMPLATES_KEY);
      if (s) { var p = JSON.parse(s); if (Array.isArray(p)) return p; }
    } catch(e) {}
    return [];
  }

  function saveCustomTemplates(templates) {
    try { _safeLS.set(CUSTOM_TEMPLATES_KEY, JSON.stringify(templates)); } catch(e) {}
  }

  // ── Render Template Gallery ────────────────────────────────────
  async function renderTemplates() {
    var pane = document.getElementById('pane-templates');
    if (!pane) return;
    pane.innerHTML = '<div style="background:linear-gradient(135deg,var(--bg-1),var(--bg-0));border-bottom:1px solid var(--border);padding:20px 24px">'
      + '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">'
      + '<div>'
      + '<h2 style="font-size:22px;font-weight:900;margin-bottom:4px">🎨 Template Gallery</h2>'
      + '<p style="color:var(--text-2);font-size:13px">Production-ready templates. Insert into chat or scaffold into Studio.</p>'
      + '</div>'
      + '<div style="display:flex;gap:8px;flex-wrap:wrap">'
      // MISSING FEATURE: POST /api/templates/scaffold-custom existed and worked
      // (it snapshots the current preview/index.html into preview/templates/)
      // but no button anywhere in the UI ever called it — the only way to keep
      // a design was the localStorage-only "New Template", which stores a
      // prompt, not your actual code, and is lost if the browser is cleared.
      + '<button data-act-click="saveWorkAsTemplate()" class="btn btn-ghost btn-sm" style="padding:6px 14px;font-weight:700" title="Snapshot what you currently have in Studio as a reusable template file">💾 Save Current Work</button>'
      + '<button data-act-click="showCreateTemplateForm()" class="btn btn-primary btn-sm" style="padding:6px 14px;font-weight:700">＋ New Template</button>'
      + '</div>'
      + '</div>'
      + '<div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap" id="tmpl-cats"></div>'
      + '</div>'
      + '<div class="u-769fed37">'
      + '<div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;align-items:center">'
      + '<input id="tmpl-search" placeholder="Search templates…" data-act-input="filterTemplates()" '
      + 'style="flex:1;max-width:300px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;color:var(--text-0);font-size:13px;outline:none">'
      + '<select id="tmpl-sort" data-act-change="tmplChangeSort($value)" '
      + 'style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 10px;color:var(--text-0);font-size:12px;outline:none">'
      + '<option value="name">A-Z</option>'
      + '<option value="category">By Category</option>'
      + '</select>'
      + '<span id="tmpl-count" style="font-size:11px;color:var(--text-3)"></span>'
      + '</div>'
      + '<div id="tmpl-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px">'
      + '<div style="color:var(--text-2);grid-column:1/-1">Loading templates…</div>'
      + '</div>'
      + '</div>';

    try {
      var r = await fetch('/api/templates');
      if (!r.ok) throw new Error('Templates API: HTTP ' + r.status);
      var data = await r.json();
      var builtIn = data.templates || data || [];

      // Load custom templates
      var custom = getCustomTemplates();
      custom.forEach(function(t) { t._custom = true; });

      // MISSING FEATURE: snapshots created by "Save Current Work" were written
      // to preview/templates/ but were write-only — nothing listed them, so the
      // only way back to your own saved design was to guess its slugged URL.
      // They now appear in the gallery as a "saved" category with restore and
      // delete actions.
      var saved = [];
      try {
        var sr = await fetch('/api/templates/saved');
        if (sr.ok) {
          var sd = await sr.json();
          saved = (sd.saved || []).map(function(s) {
            return {
              id: 'saved:' + s.filename,
              name: s.name,
              category: 'saved',
              emoji: '💾',
              description: 'Your saved snapshot — ' + Math.max(1, Math.round(s.bytes / 1024)) + ' KB, ' +
                           new Date(s.saved_at).toLocaleString(),
              tags: ['saved'],
              file_count: 1,
              _saved: true,
              _filename: s.filename,
              _url: s.url
            };
          });
        }
      } catch (e) { /* saved snapshots are optional — never block the gallery */ }

      allTemplates = builtIn.concat(custom).concat(saved);

      // Category pills
      var cats = {};
      allTemplates.forEach(function(t) {
        var c = t.category || 'custom';
        if (!cats[c]) cats[c] = { id: c, label: c.charAt(0).toUpperCase() + c.slice(1), count: 0 };
        cats[c].count++;
      });
      var catList = Object.values(cats);

      var catEl = document.getElementById('tmpl-cats');
      if (catEl) {
        var html = '<span class="bp-btn ' + (templateCategory === 'all' ? 'active' : '') + '" data-act-click="filterTemplates(\'all\')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">All (' + allTemplates.length + ')</span>';
        catList.forEach(function(c) {
          html += '<span class="bp-btn ' + (templateCategory === c.id ? 'active' : '') + '" data-act-click="filterTemplates(\'' + c.id + '\')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">' + escHtml(c.label) + ' (' + c.count + ')</span>';
        });
        catEl.innerHTML = html;
      }
      renderTemplateGrid();
    } catch(ex) {
      var g = document.getElementById('tmpl-grid');
      if (g) g.innerHTML = '<div style="color:var(--danger);grid-column:1/-1">' + escHtml(humanError(ex, {action:'load your templates', dataSafe:true})) + '<br><button class="btn-sm u-8a77e5a3" data-act-click="renderTemplates()" >↻ Retry</button></div>';
    }
  }

  function filterTemplates(cat) {
    if (cat !== undefined) templateCategory = cat;
    document.querySelectorAll('#tmpl-cats .bp-btn').forEach(function(el) {
      var label = el.textContent.trim();
      if (cat === 'all') { el.classList.toggle('active', label.startsWith('All')); }
      else if (cat !== undefined) {
        var onclick = el.getAttribute('onclick') || '';
        el.classList.toggle('active', onclick.includes("'" + cat + "'"));
      }
    });
    var q = (document.getElementById('tmpl-search')?.value || '').toLowerCase().trim();
    renderTemplateGrid(q);
  }

  function tmplChangeSort(sort) {
    _tmplSort = sort;
    filterTemplates();
  }

  function renderTemplateGrid(q) {
    q = q || (document.getElementById('tmpl-search')?.value || '').toLowerCase().trim();
    var grid = document.getElementById('tmpl-grid');
    if (!grid) return;

    var filtered = allTemplates.slice();
    if (templateCategory !== 'all') filtered = filtered.filter(function(t) { return (t.category || 'custom') === templateCategory; });
    if (q) filtered = filtered.filter(function(t) {
      return (t.name || '').toLowerCase().includes(q) ||
        (t.description || '').toLowerCase().includes(q) ||
        (t.tags || []).some(function(tag) { return tag.toLowerCase().includes(q); });
    });

    if (_tmplSort === 'category') {
      filtered.sort(function(a, b) { return (a.category || '').localeCompare(b.category || '') || (a.name || '').localeCompare(b.name || ''); });
    } else {
      filtered.sort(function(a, b) { return (a.name || '').localeCompare(b.name || ''); });
    }

    var cnt = document.getElementById('tmpl-count');
    if (cnt) cnt.textContent = filtered.length + ' template' + (filtered.length !== 1 ? 's' : '');

    if (!filtered.length) {
      grid.innerHTML = '<div style="color:var(--text-3);grid-column:1/-1;text-align:center;padding:40px">No templates match "' + escHtml(q) + '"</div>';
      return;
    }

    grid.innerHTML = '';
    filtered.forEach(function(t) {
      grid.appendChild(renderTemplateCard(t));
    });
  }

  // ── Render Single Template Card ────────────────────────────────
  function renderTemplateCard(t) {
    var card = document.createElement('div');
    card.style.cssText = 'background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);overflow:hidden;transition:transform .15s,border-color .15s;cursor:default';
    card.addEventListener('mouseenter', function() { card.style.transform = 'translateY(-2px)'; card.style.borderColor = 'var(--border-hi)'; });
    card.addEventListener('mouseleave', function() { card.style.transform = ''; card.style.borderColor = ''; });

    // Preview strip
    var preview = document.createElement('div');
    preview.style.cssText = 'height:80px;background:linear-gradient(135deg,' + (t.preview_color || '#5b8af8') + '22,' + (t.preview_color || '#5b8af8') + '08);display:flex;align-items:center;justify-content:center;border-bottom:1px solid var(--border)';
    preview.innerHTML = '<span style="font-size:40px">' + (t.emoji || '📄') + '</span>';
    card.appendChild(preview);

    var body = document.createElement('div');
    body.style.cssText = 'padding:14px';

    // Title row
    var titleRow = document.createElement('div');
    titleRow.style.cssText = 'display:flex;align-items:center;gap:6px;margin-bottom:6px';
    var title = document.createElement('span');
    title.style.cssText = 'font-weight:800;font-size:14px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
    title.textContent = t.name;
    title.title = t.name;
    titleRow.appendChild(title);
    var catTag = document.createElement('span');
    catTag.className = 'tag';
    catTag.style.cssText = 'flex-shrink:0;font-size:10px';
    catTag.textContent = t.category || 'custom';
    titleRow.appendChild(catTag);
    if (t._custom) {
      var customTag = document.createElement('span');
      customTag.className = 'tag';
      customTag.style.cssText = 'flex-shrink:0;font-size:10px;background:var(--accent-glow);color:var(--accent-text);border-color:var(--accent-text)';
      customTag.textContent = 'custom';
      titleRow.appendChild(customTag);
    }
    body.appendChild(titleRow);

    // Description
    var desc = document.createElement('p');
    desc.style.cssText = 'font-size:12px;color:var(--text-2);line-height:1.5;margin-bottom:10px;min-height:36px';
    desc.textContent = t.description || '';
    body.appendChild(desc);

    // Tags
    var tagsDiv = document.createElement('div');
    tagsDiv.style.cssText = 'display:flex;flex-wrap:wrap;gap:4px;margin-bottom:12px';
    (t.tags || []).slice(0, 3).forEach(function(tag) {
      var tagSpan = document.createElement('span');
      tagSpan.style.cssText = 'font-size:10px;padding:2px 7px;border-radius:99px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-3)';
      tagSpan.textContent = tag;
      tagsDiv.appendChild(tagSpan);
    });
    if ((t.file_count || 0) > 1) {
      var fileSpan = document.createElement('span');
      fileSpan.style.cssText = 'font-size:10px;padding:2px 7px;border-radius:99px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-3)';
      fileSpan.textContent = t.file_count + ' files';
      tagsDiv.appendChild(fileSpan);
    }
    body.appendChild(tagsDiv);

    // Action buttons
    var actions = document.createElement('div');
    actions.style.cssText = 'display:flex;gap:6px';

    // Saved snapshots get their own actions: restore into Studio, or delete.
    // They are your own files, not a starter, so "Chat"/"Scaffold" don't apply.
    if (t._saved) {
      var restoreBtn = document.createElement('button');
      restoreBtn.className = 'btn btn-primary btn-sm';
      restoreBtn.style.cssText = 'flex:1;font-size:11px';
      restoreBtn.textContent = '↩ Restore';
      restoreBtn.title = 'Load this snapshot back into Studio';
      restoreBtn.addEventListener('click', function() { restoreSavedTemplate(t._filename, t.name); });
      actions.appendChild(restoreBtn);

      var openBtn = document.createElement('button');
      openBtn.className = 'btn btn-ghost btn-sm';
      openBtn.style.cssText = 'font-size:11px;padding:4px 8px';
      openBtn.textContent = '👁';
      openBtn.title = 'Open snapshot in a new tab';
      openBtn.addEventListener('click', function() { window.open(t._url, '_blank', 'noopener'); });
      actions.appendChild(openBtn);

      var delSavedBtn = document.createElement('button');
      delSavedBtn.className = 'btn btn-ghost btn-sm';
      delSavedBtn.style.cssText = 'font-size:11px;padding:4px 8px;color:var(--danger)';
      delSavedBtn.textContent = '🗑';
      delSavedBtn.title = 'Delete this snapshot';
      delSavedBtn.addEventListener('click', function() { deleteSavedTemplate(t._filename, t.name); });
      actions.appendChild(delSavedBtn);

      body.appendChild(actions);
      card.appendChild(body);
      return card;
    }

    // Insert into Chat
    var chatBtn = document.createElement('button');
    chatBtn.className = 'btn btn-ghost btn-sm';
    chatBtn.style.cssText = 'flex:1;font-size:11px';
    chatBtn.textContent = '💬 Chat';
    chatBtn.title = 'Insert template prompt into chat input';
    chatBtn.addEventListener('click', function() { insertTemplateIntoChat(t); });
    actions.appendChild(chatBtn);

    // Preview (read-only, no writes to disk) — only meaningful for built-in
    // templates that actually ship HTML files; custom templates are just a
    // saved chat prompt with no file content to preview.
    if (!t._custom && (t.file_count || 0) > 0) {
      var previewBtn = document.createElement('button');
      previewBtn.className = 'btn btn-ghost btn-sm';
      previewBtn.style.cssText = 'font-size:11px;padding:4px 8px';
      previewBtn.textContent = '👁';
      previewBtn.title = 'Preview (read-only — does not touch your Studio files)';
      previewBtn.addEventListener('click', function() { previewTemplate(t.id); });
      actions.appendChild(previewBtn);
    }

    // Scaffold to Studio
    var studioBtn = document.createElement('button');
    studioBtn.className = 'btn btn-primary btn-sm';
    studioBtn.style.cssText = 'flex:1;font-size:11px';
    studioBtn.textContent = '⚡ Studio';
    studioBtn.title = 'Scaffold project files into Studio editor';
    studioBtn.addEventListener('click', function() { scaffoldTemplate(t.id, false, t.name); });
    actions.appendChild(studioBtn);

    // Edit/Delete for custom templates
    if (t._custom) {
      var editBtn = document.createElement('button');
      editBtn.className = 'btn btn-ghost btn-sm';
      editBtn.style.cssText = 'font-size:11px;padding:4px 8px';
      editBtn.textContent = '✏️';
      editBtn.title = 'Edit template';
      editBtn.addEventListener('click', function() { showEditTemplateForm(t); });
      actions.appendChild(editBtn);

      var delBtn = document.createElement('button');
      delBtn.className = 'btn btn-ghost btn-sm';
      delBtn.style.cssText = 'font-size:11px;padding:4px 8px;color:var(--danger)';
      delBtn.textContent = '🗑';
      delBtn.title = 'Delete template';
      delBtn.addEventListener('click', function() { deleteCustomTemplate(t.id); });
      actions.appendChild(delBtn);
    }

    body.appendChild(actions);
    card.appendChild(body);
    return card;
  }

  // ── Save current Studio work as a reusable template file ───────
  // Wires up POST /api/templates/scaffold-custom, which shipped working but
  // unreachable. Unlike "＋ New Template" (a localStorage prompt entry), this
  // persists the actual HTML you have open, server-side, so it survives a
  // browser reset and can be reopened from preview/templates/.
  async function saveWorkAsTemplate() {
    var name = await gmPrompt('Save current work as template',
      'Name this snapshot of your current Studio preview:', '');
    if (!name || !name.trim()) return;
    try {
      var r = await fetch('/api/templates/scaffold-custom', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim() })
      });
      var j = await r.json().catch(function() { return null; });
      if (!r.ok || !j || !j.ok) {
        toast('❌ Could not save: ' + ((j && j.error) || 'HTTP ' + r.status), 'err', 3500);
        return;
      }
      toast('💾 Saved as "' + j.name + '"', 'ok', 3000);
      // Re-render so the new snapshot appears in the gallery immediately.
      renderTemplates();
    } catch (ex) {
      toast('❌ Save failed: ' + ex.message, 'err', 3000);
    }
  }

  // ── Saved snapshot actions ─────────────────────────────────────
  async function restoreSavedTemplate(filename, displayName) {
    var ok = await gmConfirm('Restore saved snapshot?',
      'This replaces <strong>preview/index.html</strong> with “' + escHtml(displayName) + '”.<br><br>' +
      'Your current file is backed up to Studio\u2019s version history first, so this can be undone.');
    if (!ok) return;
    try {
      var r = await fetch('/api/templates/saved/' + encodeURIComponent(filename) + '/restore', { method: 'POST' });
      var j = await r.json().catch(function() { return null; });
      if (!r.ok || !j || !j.ok) {
        toast('❌ Restore failed: ' + ((j && j.error) || 'HTTP ' + r.status), 'err', 3500);
        return;
      }
      toast('↩ Restored “' + displayName + '” — opening Studio…', 'ok', 3000);
      if (typeof studioLoadFileTree === 'function') studioLoadFileTree();
      if (typeof studioReloadPreview === 'function') studioReloadPreview();
      setTimeout(function() { if (typeof nav === 'function') nav('studio'); }, 600);
    } catch (ex) {
      toast('❌ Restore error: ' + ex.message, 'err', 3000);
    }
  }

  async function deleteSavedTemplate(filename, displayName) {
    var ok = await gmConfirm('Delete saved snapshot?',
      'Permanently delete “' + escHtml(displayName) + '”? This cannot be undone.');
    if (!ok) return;
    try {
      var r = await fetch('/api/templates/saved/' + encodeURIComponent(filename), { method: 'DELETE' });
      var j = await r.json().catch(function() { return null; });
      if (!r.ok || !j || !j.ok) {
        toast('❌ Delete failed: ' + ((j && j.error) || 'HTTP ' + r.status), 'err', 3500);
        return;
      }
      toast('🗑 Deleted “' + displayName + '”', 'ok', 2000);
      renderTemplates();
    } catch (ex) {
      toast('❌ Delete error: ' + ex.message, 'err', 3000);
    }
  }

  // ── Insert Template into Chat ──────────────────────────────────
  function insertTemplateIntoChat(t) {
    var prompt = t.prompt || t.description || ('Build a ' + t.name);
    var input = document.getElementById('chat-input');
    if (!input) {
      toast('❌ Chat input not found', 'err', 2000);
      return;
    }
    input.value = prompt;
    input.focus();
    // Trigger auto-resize
    if (typeof autoResizeInput === 'function') autoResizeInput(input);
    // Switch to chat pane
    if (typeof nav === 'function') nav('chat');
    // Hide empty state
    var empty = document.getElementById('chat-empty');
    if (empty) empty.style.display = 'none';
    toast('💬 Template inserted into chat — customize and send!', 'ok', 2000);
  }

  // ── Scaffold Template to Studio ────────────────────────────────
  async function scaffoldTemplate(templateId, silent, projectName) {
    if (!allTemplates.length) {
      try {
        var r = await fetch('/api/templates');
        if (r.ok) {
          var d = await r.json();
          allTemplates = d.templates || d || [];
        }
      } catch(e) {}
    }
    var t = allTemplates.find(function(x) { return x.id === templateId; });
    if (!silent) toast('⚡ Scaffolding ' + (t?.name || templateId) + '…', 'ok', 2000);

    // BUG FIX (data loss): scaffolding overwrote whatever was in preview/ with
    // no warning. If you had unsaved work open in Studio it was destroyed and
    // unrecoverable. The backend now refuses to clobber existing files unless
    // overwrite:true is passed, so ask first and name exactly what is at risk.
    async function postScaffold(overwrite) {
      return fetch('/api/templates/' + encodeURIComponent(templateId) + '/scaffold', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_name: projectName || (t?.name || templateId),
          overwrite: !!overwrite
        })
      });
    }

    try {
      var r = await postScaffold(false);
      var j = await r.json().catch(function() { return null; });

      if (j && j.needs_confirmation) {
        var files = (j.conflicts || []).join(', ');
        var proceed = await gmConfirm(
          'Replace existing files?',
          'Scaffolding <strong>' + escHtml(j.template || templateId) + '</strong> will replace ' +
          (j.conflicts || []).length + ' file(s) already in your workspace:<br><br>' +
          '<code class="u-72126da2">' + escHtml(files) + '</code><br><br>' +
          'A backup is saved to Studio\u2019s version history first, so this can be undone.'
        );
        if (!proceed) { toast('Scaffold cancelled — nothing changed', 'ok', 2000); return; }
        r = await postScaffold(true);
        j = await r.json().catch(function() { return null; });
      }

      if (!r.ok && !(j && j.ok)) {
        toast('❌ Scaffold failed: ' + ((j && j.error) || 'HTTP ' + r.status), 'err', 3000);
        return;
      }
      if (j && j.ok) {
        if (!silent) {
          var extra = (j.replaced && j.replaced.length)
            ? ' (' + j.replaced.length + ' file(s) backed up)'
            : '';
          toast('✅ ' + (j.template || 'Template') + ' ready' + extra + ' — opening Studio…', 'ok', 3000);
        }
        if (typeof studioLoadFileTree === 'function') studioLoadFileTree();
        if (typeof studioReloadPreview === 'function') studioReloadPreview();
        if (!silent) setTimeout(function() { if (typeof nav === 'function') nav('studio'); }, 600);
      } else {
        toast('❌ Scaffold failed: ' + ((j && j.error) || 'Unknown'), 'err', 3000);
      }
    } catch(ex) {
      toast('❌ Scaffold error: ' + ex.message, 'err', 3000);
    }
  }

  // ── Preview Template (non-destructive) ─────────────────────────
  // BUG FIX / MISSING FEATURE: this function existed and was exposed on
  // `window.previewTemplate` but was never wired to any button anywhere in
  // the UI — completely unreachable dead code. Its old implementation also
  // wasn't really a "preview" at all: it silently scaffolded the template
  // into preview/ (overwriting whatever the user currently had open in
  // Studio) and then navigated there, i.e. functionally identical to the
  // "⚡ Studio" button already on every card. Rewritten as a genuine
  // non-destructive preview: renders the template's raw HTML in a sandboxed
  // iframe via srcdoc, using the read-only GET /api/templates/{id}/preview
  // endpoint — no writes to preview/ or Studio's file tree at all. Wired to
  // a new "👁 Preview" button on every card.
  async function previewTemplate(templateId) {
    try {
      var r = await fetch('/api/templates/' + encodeURIComponent(templateId) + '/preview');
      if (!r.ok) { toast('❌ Preview failed: HTTP ' + r.status, 'err', 2000); return; }
      var j = await r.json();
      if (!j.ok) { toast('❌ Preview failed: ' + (j.error || 'Unknown'), 'err', 2000); return; }
      showTemplatePreviewModal(j.template || templateId, j.content || '', templateId, j);
    } catch(ex) {
      toast('❌ Preview error: ' + ex.message, 'err', 2000);
    }
  }

  function showTemplatePreviewModal(name, html, templateId, meta) {
    // Backend/multi-file templates ship no HTML, so there is nothing to render
    // in an iframe. The endpoint flags those with renderable:false and returns
    // the primary source file instead — show it as code rather than failing.
    meta = meta || {};
    var renderable = meta.renderable !== false;
    var existing = document.getElementById('tmpl-preview-modal');
    if (existing) existing.remove();
    var overlay = document.createElement('div');
    overlay.id = 'tmpl-preview-modal';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:9999;display:flex;align-items:center;justify-content:center;padding:24px';
    overlay.innerHTML =
      '<div style="background:var(--bg-1);border:1px solid var(--border);border-radius:16px;width:100%;max-width:1000px;height:85vh;display:flex;flex-direction:column;overflow:hidden">' +
        '<div style="display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid var(--border);flex-shrink:0">' +
          '<span style="font-weight:800;font-size:14px">👁 ' + escHtml(name) +
            (renderable ? ' — read-only preview (nothing written to disk)'
                        : ' — ' + escHtml(meta.filename || 'source') +
                          (meta.file_count ? ' (' + meta.file_count + ' files)' : '')) + '</span>' +
          '<div style="display:flex;gap:8px">' +
            '<button class="btn btn-primary btn-sm" id="tmpl-preview-scaffold-btn">⚡ Scaffold into Studio</button>' +
            '<button class="btn btn-ghost btn-sm" id="tmpl-preview-close-btn">✕ Close</button>' +
          '</div>' +
        '</div>' +
        // `allow-same-origin` is required here because several templates
        // (e.g. todo-app, notes-app) use localStorage for their in-page
        // demo state — without it, `srcdoc` content runs in a unique opaque
        // origin and any localStorage access throws a SecurityError,
        // breaking the very features being previewed. Matches the sandbox
        // flags already used by Studio's own preview iframes in index.html.
        (renderable
          ? '<iframe id="tmpl-preview-iframe" sandbox="allow-scripts allow-same-origin allow-forms allow-popups" style="flex:1;border:none;background:#fff"></iframe>'
          : '<pre id="tmpl-preview-code" style="flex:1;margin:0;overflow:auto;padding:16px;background:var(--bg-0);color:var(--text-1);font-family:ui-monospace,monospace;font-size:12.5px;line-height:1.6;white-space:pre-wrap"></pre>') +
      '</div>';
    document.body.appendChild(overlay);
    if (renderable) {
      var frame = document.getElementById('tmpl-preview-iframe');
      if (frame) frame.srcdoc = html;
    } else {
      var codeEl = document.getElementById('tmpl-preview-code');
      // textContent, never innerHTML — template source must never execute here.
      if (codeEl) codeEl.textContent = html;
    }
    document.getElementById('tmpl-preview-close-btn').onclick = function() { overlay.remove(); };
    document.getElementById('tmpl-preview-scaffold-btn').onclick = function() {
      overlay.remove();
      scaffoldTemplate(templateId, false, name);
    };
    overlay.addEventListener('click', function(e) { if (e.target === overlay) overlay.remove(); });
  }

  // ── Create Custom Template (uses gmPrompt for Tauri compat) ──
  window.showCreateTemplateForm = async function() {
    var name = await gmPrompt('Template name:', 'My Template');
    if (!name || !name.trim()) return;
    var description = await gmPrompt('Description:', 'What does this template build?');
    var category = await gmPrompt('Category:', 'custom');
    var promptText = await gmPrompt('Chat prompt:', 'Build a ' + name.trim());
    var emoji = await gmPrompt('Emoji icon:', '📄');

    var id = 'custom-' + Date.now();
    var newTemplate = {
      id: id,
      name: name.trim(),
      category: (category || 'custom').trim().toLowerCase(),
      emoji: emoji || '📄',
      description: (description || '').trim(),
      tags: ['custom'],
      preview_color: '#6366f1',
      prompt: (promptText || 'Build a ' + name.trim()).trim(),
      _custom: true,
    };

    var customs = getCustomTemplates();
    customs.push(newTemplate);
    saveCustomTemplates(customs);
    toast('✅ Template "' + name.trim() + '" created!', 'ok', 2000);
    renderTemplates();
  };

  // ── Edit Custom Template (uses gmPrompt for Tauri compat) ─────
  window.showEditTemplateForm = async function(t) {
    var name = await gmPrompt('Template name:', t.name || '');
    if (name === null) return;
    var description = await gmPrompt('Description:', t.description || '');
    if (description === null) return;
    var category = await gmPrompt('Category:', t.category || 'custom');
    if (category === null) return;
    var promptText = await gmPrompt('Chat prompt:', t.prompt || '');
    if (promptText === null) return;
    var emoji = await gmPrompt('Emoji icon:', t.emoji || '📄');
    if (emoji === null) return;

    var customs = getCustomTemplates();
    var idx = customs.findIndex(function(c) { return c.id === t.id; });
    if (idx === -1) { toast('❌ Template not found', 'err', 2000); return; }

    customs[idx].name = name.trim() || customs[idx].name;
    customs[idx].description = description.trim();
    customs[idx].category = (category || 'custom').trim().toLowerCase();
    customs[idx].prompt = (promptText || '').trim();
    customs[idx].emoji = emoji || '📄';

    saveCustomTemplates(customs);
    toast('✅ Template updated!', 'ok', 1500);
    renderTemplates();
  };

  // ── Delete Custom Template ─────────────────────────────────────
  async function deleteCustomTemplate(id) {
    // BUG FIX (Tauri compat): this used the native confirm() dialog, which
    // is explicitly unsupported in the Tauri WebKit webview per project
    // standards (only gmPrompt/gmConfirm/gmDanger — the custom in-app modal
    // system — are safe to use for confirmations; everything else in this
    // file already correctly uses gmPrompt). Switched to gmDanger to match.
    if (!(await gmDanger('Delete Template', 'Delete this template? This cannot be undone.', 'Delete'))) return;
    var customs = getCustomTemplates().filter(function(t) { return t.id !== id; });
    saveCustomTemplates(customs);
    toast('🗑 Template deleted', 'ok', 1500);
    renderTemplates();
  }

  // ── Expose to global scope ─────────────────────────────────────
  window.renderTemplates = renderTemplates;
  window.filterTemplates = filterTemplates;
  window.tmplChangeSort = tmplChangeSort;
  window.scaffoldTemplate = scaffoldTemplate;
  window.saveWorkAsTemplate = saveWorkAsTemplate;
  window.restoreSavedTemplate = restoreSavedTemplate;
  window.deleteSavedTemplate = deleteSavedTemplate;
  window.previewTemplate = previewTemplate;

  // Add to command palette
  if (typeof PALETTE_CMDS !== 'undefined') {
    PALETTE_CMDS.push(
      { icon: '🎨', label: 'Template Gallery', desc: 'Browse & use templates', action: function() { nav('templates'); } },
    );
  }

})();
