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
      + '<button onclick="showCreateTemplateForm()" class="btn btn-primary btn-sm" style="padding:6px 14px;font-weight:700">＋ New Template</button>'
      + '</div>'
      + '<div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap" id="tmpl-cats"></div>'
      + '</div>'
      + '<div style="padding:20px">'
      + '<div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;align-items:center">'
      + '<input id="tmpl-search" placeholder="Search templates…" oninput="filterTemplates()" '
      + 'style="flex:1;max-width:300px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;color:var(--text-0);font-size:13px;outline:none">'
      + '<select id="tmpl-sort" onchange="tmplChangeSort(this.value)" '
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

      allTemplates = builtIn.concat(custom);

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
        var html = '<span class="bp-btn ' + (templateCategory === 'all' ? 'active' : '') + '" onclick="filterTemplates(\'all\')">All (' + allTemplates.length + ')</span>';
        catList.forEach(function(c) {
          html += '<span class="bp-btn ' + (templateCategory === c.id ? 'active' : '') + '" onclick="filterTemplates(\'' + c.id + '\')">' + escHtml(c.label) + ' (' + c.count + ')</span>';
        });
        catEl.innerHTML = html;
      }
      renderTemplateGrid();
    } catch(ex) {
      var g = document.getElementById('tmpl-grid');
      if (g) g.innerHTML = '<div style="color:var(--danger);grid-column:1/-1">Failed to load templates: ' + escHtml(ex.message) + '<br><button class="btn-sm" onclick="renderTemplates()" style="margin-top:8px">↻ Retry</button></div>';
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
      customTag.style.cssText = 'flex-shrink:0;font-size:10px;background:var(--accent-glow);color:var(--accent);border-color:var(--accent)';
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

    // Insert into Chat
    var chatBtn = document.createElement('button');
    chatBtn.className = 'btn btn-ghost btn-sm';
    chatBtn.style.cssText = 'flex:1;font-size:11px';
    chatBtn.textContent = '💬 Chat';
    chatBtn.title = 'Insert template prompt into chat input';
    chatBtn.addEventListener('click', function() { insertTemplateIntoChat(t); });
    actions.appendChild(chatBtn);

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

    try {
      var r = await fetch('/api/templates/' + encodeURIComponent(templateId) + '/scaffold', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_name: projectName || (t?.name || templateId) })
      });
      if (!r.ok) {
        toast('❌ Scaffold failed: HTTP ' + r.status, 'err', 3000);
        return;
      }
      var j = await r.json();
      if (j.ok) {
        if (!silent) toast('✅ ' + (j.template || 'Template') + ' ready — opening Studio…', 'ok', 3000);
        if (typeof studioLoadFileTree === 'function') studioLoadFileTree();
        if (typeof studioReloadPreview === 'function') studioReloadPreview();
        if (!silent) setTimeout(function() { if (typeof nav === 'function') nav('studio'); }, 600);
      } else {
        toast('❌ Scaffold failed: ' + (j.error || 'Unknown'), 'err', 3000);
      }
    } catch(ex) {
      toast('❌ Scaffold error: ' + ex.message, 'err', 3000);
    }
  }

  // ── Preview Template ───────────────────────────────────────────
  async function previewTemplate(templateId) {
    try {
      var r = await fetch('/api/templates/' + encodeURIComponent(templateId) + '/preview');
      if (!r.ok) { toast('❌ Preview failed: HTTP ' + r.status, 'err', 2000); return; }
      var j = await r.json();
      if (!j.ok) { toast('❌ Preview failed: ' + (j.error || 'Unknown'), 'err', 2000); return; }
      // Scaffold silently then open Studio
      await scaffoldTemplate(templateId, true);
      setTimeout(function() { if (typeof nav === 'function') nav('studio'); }, 400);
      toast('👁 Preview loaded in Studio', 'ok', 2000);
    } catch(ex) {
      toast('❌ Preview error: ' + ex.message, 'err', 2000);
    }
  }

  // ── Create Custom Template ─────────────────────────────────────
  window.showCreateTemplateForm = function() {
    var name = prompt('Template name:');
    if (!name || !name.trim()) return;
    var description = prompt('Description (what does this template build?):', '');
    var category = prompt('Category (e.g. apps, saas, portfolio, marketing):', 'custom');
    var promptText = prompt('Chat prompt (what gets inserted into chat input):', 'Build a ' + name.trim());
    var emoji = prompt('Emoji icon:', '📄');

    if (!name.trim()) return;

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

  // ── Edit Custom Template ───────────────────────────────────────
  window.showEditTemplateForm = function(t) {
    var name = prompt('Template name:', t.name || '');
    if (name === null) return;
    var description = prompt('Description:', t.description || '');
    if (description === null) return;
    var category = prompt('Category:', t.category || 'custom');
    if (category === null) return;
    var promptText = prompt('Chat prompt:', t.prompt || '');
    if (promptText === null) return;
    var emoji = prompt('Emoji icon:', t.emoji || '📄');
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
  function deleteCustomTemplate(id) {
    if (!confirm('Delete this template? This cannot be undone.')) return;
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
  window.previewTemplate = previewTemplate;

  // Add to command palette
  if (typeof PALETTE_CMDS !== 'undefined') {
    PALETTE_CMDS.push(
      { icon: '🎨', label: 'Template Gallery', desc: 'Browse & use templates', action: function() { nav('templates'); } },
    );
  }

})();
