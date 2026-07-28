/**
 * Agentic OS — Enhanced Chat History Management
 * Folder tree view (like Windows Explorer / macOS Finder) + date view toggle.
 * Inspired by: Cursor, Open WebUI, ChatGPT, Claude
 */

(function() {
  'use strict';

  // ── State ─────────────────────────────────────────────────────
  var FOLDER_KEY = 'agentic_os_custom_folders';
  var DEFAULT_FOLDERS = ['General', 'Engineering', 'Research', 'Ideas'];
  var _currentView = 'folders';  // 'folders' or 'date'
  var _expandedFolders = {};      // which folders are expanded
  var _allSessions = [];          // cached session list

  function getCustomFolders() {
    try {
      var saved = _safeLS.get(FOLDER_KEY);
      if (saved) { var p = JSON.parse(saved); if (Array.isArray(p) && p.length) return p; }
    } catch(e) {}
    return DEFAULT_FOLDERS.slice();
  }

  function saveCustomFolders(folders) {
    try { _safeLS.set(FOLDER_KEY, JSON.stringify(folders)); } catch(e) {}
  }

  function getFolderIcon(folder) {
    var icons = { 'General':'📁','Engineering':'⚙️','Research':'🔬','Ideas':'💡','Work':'💼','Personal':'🏠','Projects':'🎯','Archive':'📦' };
    return icons[folder] || '📂';
  }

  function formatTimeAgo(dateStr) {
    if (!dateStr) return '';
    var d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr.slice(5, 16);
    var diff = Date.now() - d.getTime(), mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return mins + 'm ago';
    var hours = Math.floor(diff / 3600000);
    if (hours < 24) return hours + 'h ago';
    var days = Math.floor(diff / 86400000);
    if (days < 7) return days + 'd ago';
    return dateStr.slice(5, 16);
  }

  function getDateGroup(dateStr) {
    if (!dateStr) return 'Older';
    var d = new Date(dateStr);
    if (isNaN(d.getTime())) return 'Older';
    var now = new Date(), today = now.toISOString().slice(0,10), ds = d.toISOString().slice(0,10);
    if (ds === today) return 'Today';
    var y = new Date(now); y.setDate(y.getDate()-1);
    if (ds === y.toISOString().slice(0,10)) return 'Yesterday';
    var w = new Date(now); w.setDate(w.getDate()-7);
    if (d >= w) return 'Previous 7 Days';
    var m = new Date(now); m.setMonth(m.getMonth()-1);
    if (d >= m) return 'Previous 30 Days';
    return 'Older';
  }

  // ── View Switching ────────────────────────────────────────────
  window.switchChatView = function(view) {
    _currentView = view;
    var fb = document.getElementById('view-folders-btn');
    var db = document.getElementById('view-date-btn');
    var pag = document.getElementById('chat-sessions-pagination');
    if (fb) { fb.style.background = view === 'folders' ? 'var(--accent)' : 'transparent'; fb.style.color = view === 'folders' ? '#fff' : 'var(--text-2)'; }
    if (db) { db.style.background = view === 'date' ? 'var(--accent)' : 'transparent'; db.style.color = view === 'date' ? '#fff' : 'var(--text-2)'; }
    if (pag) pag.style.display = view === 'date' ? 'flex' : 'none';
    renderChatList();
  };

  // ── Main Load ─────────────────────────────────────────────────
  window.loadChatSessions = async function(q) {
    q = String(q || '').trim();
    var el = document.getElementById('chat-sessions-list');
    if (!el) return;
    try {
      var url = '/api/sessions?limit=200' + (q ? '&q=' + encodeURIComponent(q) : '');
      var r = await fetch(url);
      var data = await r.json();
      _allSessions = data.sessions || [];
      syncFoldersFromSessions(_allSessions);
      renderChatList();
    } catch(e) {
      console.warn('Failed to load sessions:', e);
      el.innerHTML = '<div style="color:var(--danger);font-size:12px;text-align:center;padding:20px">Failed to load</div>';
    }
  };

  // ── Render (dispatches to folder or date view) ────────────────
  function renderChatList() {
    var el = document.getElementById('chat-sessions-list');
    if (!el) return;
    if (!_allSessions.length) {
      el.innerHTML = '<div style="display:flex;flex-direction:column;align-items:center;padding:32px 16px;text-align:center">'
        + '<div style="font-size:36px;margin-bottom:12px;opacity:.6">💬</div>'
        + '<div style="font-size:13px;font-weight:700;color:var(--text-1);margin-bottom:4px">No conversations yet</div>'
        + '<div style="font-size:11.5px;color:var(--text-3);margin-bottom:16px">Start a chat to see your history</div>'
        + '<button onclick="startNewChatSession()" class="btn-3d btn-primary btn-sm" style="padding:6px 16px;font-weight:700">＋ Start First Chat</button>'
        + '</div>';
      return;
    }

    // Apply search filter
    var q = (document.getElementById('chat-sessions-search')?.value || '').trim().toLowerCase();
    var sessions = q ? _allSessions.filter(function(s) {
      return (s.name || '').toLowerCase().includes(q) || (s.description || '').toLowerCase().includes(q);
    }) : _allSessions;

    if (_currentView === 'date') {
      renderDateView(el, sessions);
    } else {
      renderFolderView(el, sessions);
    }
  }

  // ── Folder Tree View ──────────────────────────────────────────
  function renderFolderView(el, sessions) {
    el.innerHTML = '';

    // Group sessions by folder
    var folderMap = {};
    sessions.forEach(function(s) {
      var folder = (s.description && s.description !== 'All') ? s.description : 'General';
      if (!folderMap[folder]) folderMap[folder] = [];
      folderMap[folder].push(s);
    });

    var folders = getCustomFolders();
    // Add any folders from sessions that aren't in the custom list
    Object.keys(folderMap).forEach(function(f) {
      if (folders.indexOf(f) === -1) folders.push(f);
    });

    // Sort: folders with pinned items first, then by name
    folders.sort(function(a, b) {
      var aPinned = (folderMap[a] || []).some(function(s) { return s.pinned; });
      var bPinned = (folderMap[b] || []).some(function(s) { return s.pinned; });
      if (aPinned !== bPinned) return bPinned - aPinned;
      return a.localeCompare(b);
    });

    folders.forEach(function(folder) {
      var items = folderMap[folder] || [];
      // Sort within folder: pinned first, then newest
      items.sort(function(a, b) {
        if (a.pinned !== b.pinned) return b.pinned - a.pinned;
        return new Date(b.updated_at || b.created_at || 0) - new Date(a.updated_at || a.created_at || 0);
      });

      var isExpanded = _expandedFolders[folder] !== false; // default expanded

      // Folder header
      var folderDiv = document.createElement('div');
      folderDiv.style.cssText = 'margin-bottom:2px';

      var header = document.createElement('div');
      header.style.cssText = 'display:flex;align-items:center;gap:6px;padding:6px 8px;border-radius:6px;cursor:pointer;transition:background .1s;user-select:none';
      header.addEventListener('mouseenter', function() { header.style.background = 'var(--bg-3)'; });
      header.addEventListener('mouseleave', function() { header.style.background = ''; });
      header.addEventListener('click', function() {
        _expandedFolders[folder] = !_expandedFolders[folder];
        renderChatList();
      });

      // Arrow
      var arrow = document.createElement('span');
      arrow.style.cssText = 'font-size:9px;color:var(--text-3);width:12px;text-align:center;transition:transform .15s;flex-shrink:0';
      arrow.textContent = isExpanded ? '▼' : '▶';
      header.appendChild(arrow);

      // Folder icon
      var icon = document.createElement('span');
      icon.style.cssText = 'font-size:13px;flex-shrink:0';
      icon.textContent = getFolderIcon(folder);
      header.appendChild(icon);

      // Folder name
      var name = document.createElement('span');
      name.style.cssText = 'flex:1;font-size:12px;font-weight:700;color:var(--text-0);white-space:nowrap;overflow:hidden;text-overflow:ellipsis';
      name.textContent = folder;
      header.appendChild(name);

      // Count badge
      var count = document.createElement('span');
      count.style.cssText = 'font-size:10px;color:var(--text-3);background:var(--bg-3);padding:1px 5px;border-radius:4px;flex-shrink:0';
      count.textContent = items.length;
      header.appendChild(count);

      // Folder actions (visible on hover)
      var folderActions = document.createElement('div');
      folderActions.style.cssText = 'display:flex;gap:2px;flex-shrink:0;opacity:0;transition:opacity .12s';
      header.addEventListener('mouseenter', function() { folderActions.style.opacity = '1'; });
      header.addEventListener('mouseleave', function() { folderActions.style.opacity = '0'; });

      // Edit folder button
      var editBtn = document.createElement('button');
      editBtn.textContent = '✏️';
      editBtn.title = 'Rename folder';
      editBtn.style.cssText = 'background:none;border:none;cursor:pointer;font-size:11px;padding:1px 3px;border-radius:3px;color:var(--text-3);line-height:1';
      editBtn.addEventListener('click', function(e) { e.stopPropagation(); inlineRenameFolder(folder); });
      folderActions.appendChild(editBtn);

      // Delete folder button (not for defaults)
      if (DEFAULT_FOLDERS.indexOf(folder) === -1) {
        var delBtn = document.createElement('button');
        delBtn.textContent = '🗑';
        delBtn.title = 'Delete folder';
        delBtn.style.cssText = 'background:none;border:none;cursor:pointer;font-size:11px;padding:1px 3px;border-radius:3px;color:var(--text-3);line-height:1';
        delBtn.addEventListener('click', function(e) { e.stopPropagation(); confirmDeleteFolder(folder); });
        folderActions.appendChild(delBtn);
      }

      header.appendChild(folderActions);
      folderDiv.appendChild(header);

      // Chat items under folder
      if (isExpanded && items.length) {
        var chatList = document.createElement('div');
        chatList.style.cssText = 'padding-left:20px;display:flex;flex-direction:column;gap:1px';
        items.forEach(function(s) { chatList.appendChild(renderChatItem(s)); });
        folderDiv.appendChild(chatList);
      }

      el.appendChild(folderDiv);
    });
  }

  // ── Date View ─────────────────────────────────────────────────
  function renderDateView(el, sessions) {
    // Sort newest first
    sessions.sort(function(a, b) {
      if (a.pinned !== b.pinned) return b.pinned - a.pinned;
      return new Date(b.updated_at || b.created_at || 0) - new Date(a.updated_at || a.created_at || 0);
    });

    // Paginate
    var pageSize = window._chatPageSize || 5;
    var total = sessions.length;
    var totalPages = Math.max(1, Math.ceil(total / pageSize));
    if (window._chatCurrentPage > totalPages) window._chatCurrentPage = totalPages;
    var curPage = window._chatCurrentPage || 1;
    var startIdx = (curPage - 1) * pageSize;
    var page = sessions.slice(startIdx, startIdx + pageSize);

    updatePaginationUI(total, curPage, totalPages);

    el.innerHTML = '';
    if (!page.length) {
      el.innerHTML = '<div style="color:var(--text-3);font-size:12px;text-align:center;padding:20px">No chats on this page</div>';
      return;
    }

    var groups = {};
    page.forEach(function(s) {
      var g = getDateGroup(s.updated_at || s.created_at);
      if (!groups[g]) groups[g] = [];
      groups[g].push(s);
    });

    ['Today', 'Yesterday', 'Previous 7 Days', 'Previous 30 Days', 'Older'].forEach(function(gn) {
      var items = groups[gn];
      if (!items || !items.length) return;
      var header = document.createElement('div');
      header.style.cssText = 'font-size:10px;font-weight:700;color:var(--text-3);padding:8px 6px 4px;letter-spacing:.04em;text-transform:uppercase';
      header.textContent = gn;
      el.appendChild(header);
      items.forEach(function(s) { el.appendChild(renderChatItem(s)); });
    });
  }

  function updatePaginationUI(total, curPage, totalPages) {
    var pagEl = document.getElementById('chat-sessions-pagination');
    if (!pagEl) return;
    var ind = document.getElementById('chat-page-indicator');
    if (ind) ind.textContent = 'Page ' + curPage + ' of ' + totalPages + ' (' + total + ')';
    var prev = document.getElementById('chat-page-prev');
    var next = document.getElementById('chat-page-next');
    if (prev) prev.disabled = curPage <= 1;
    if (next) next.disabled = curPage >= totalPages;
  }

  // ── Render Single Chat Item ───────────────────────────────────
  function renderChatItem(s) {
    var isCurrent = (s.id === (window.S && window.S.sessionId));
    var sname = (s.name || 'Chat').slice(0, 256);
    var timeAgo = formatTimeAgo(s.updated_at || s.created_at);

    var div = document.createElement('div');
    div.className = 'chat-session-item' + (isCurrent ? ' active' : '');
    div.dataset.sessionId = s.id;
    div.style.cssText = 'display:flex;align-items:center;gap:6px;padding:6px 8px;border-radius:6px;cursor:pointer;transition:all .12s;'
      + 'background:' + (isCurrent ? 'var(--accent-glow)' : 'transparent') + ';'
      + 'border:1px solid ' + (isCurrent ? 'var(--accent)' : 'transparent');

    div.addEventListener('mouseenter', function() {
      if (!isCurrent) { div.style.background = 'var(--bg-3)'; div.style.borderColor = 'var(--border)'; }
      if (actionsDiv) actionsDiv.style.opacity = '1';
    });
    div.addEventListener('mouseleave', function() {
      if (!isCurrent) { div.style.background = 'transparent'; div.style.borderColor = 'transparent'; }
      if (actionsDiv) actionsDiv.style.opacity = '0';
    });
    div.addEventListener('click', function(e) {
      if (e.target.closest('.session-actions') || e.target.closest('.inline-edit-input')) return;
      window.loadChatSession(s.id);
    });
    div.addEventListener('contextmenu', function(e) {
      e.preventDefault(); e.stopPropagation();
      showSessionContextMenu(e.clientX, e.clientY, s);
    });

    // Pin indicator
    if (s.pinned) {
      var pin = document.createElement('span');
      pin.style.cssText = 'font-size:10px;flex-shrink:0';
      pin.textContent = '📌';
      div.appendChild(pin);
    }

    // Title
    var title = document.createElement('span');
    title.className = 'session-title';
    title.style.cssText = 'flex:1;font-size:12px;font-weight:' + (isCurrent ? '800' : '600') + ';color:var(--text-0);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0';
    title.textContent = sname;
    title.title = sname + ' (double-click to rename)';
    title.addEventListener('dblclick', function(e) {
      e.preventDefault(); e.stopPropagation();
      startInlineRename(div, s, title);
    });
    div.appendChild(title);

    // Time
    var time = document.createElement('span');
    time.style.cssText = 'font-size:10px;color:var(--text-3);flex-shrink:0;white-space:nowrap';
    time.textContent = timeAgo;
    div.appendChild(time);

    // Action buttons (hover)
    var actionsDiv = document.createElement('div');
    actionsDiv.className = 'session-actions';
    actionsDiv.style.cssText = 'display:flex;gap:1px;flex-shrink:0;opacity:0;transition:opacity .12s';

    var delBtn = document.createElement('button');
    delBtn.title = 'Delete';
    delBtn.style.cssText = 'background:none;border:none;color:var(--text-3);font-size:11px;cursor:pointer;padding:1px 3px;border-radius:3px;line-height:1';
    delBtn.textContent = '✕';
    var delConfirming = false, delTimer = null;
    delBtn.addEventListener('mouseenter', function() { if (!delConfirming) delBtn.style.color = 'var(--danger)'; });
    delBtn.addEventListener('mouseleave', function() { if (!delConfirming) delBtn.style.color = 'var(--text-3)'; });
    delBtn.addEventListener('click', function(e) {
      e.preventDefault(); e.stopPropagation();
      if (!delConfirming) {
        delConfirming = true;
        delBtn.textContent = 'Sure?';
        delBtn.style.color = 'var(--danger)';
        delTimer = setTimeout(function() { delConfirming = false; delBtn.textContent = '✕'; delBtn.style.color = 'var(--text-3)'; }, 3000);
      } else {
        clearTimeout(delTimer);
        fetch('/api/sessions/' + encodeURIComponent(s.id), { method: 'DELETE' })
          .then(function(r) { return r.json(); })
          .then(function(j) {
            if (j.ok) {
              toast('🗑 Deleted', 'ok', 1200);
              if (window.S && window.S.sessionId === s.id && window.startNewChatSession) window.startNewChatSession();
              window.loadChatSessions();
            }
          }).catch(function() { toast('❌ Delete failed', 'err', 2000); });
      }
    });
    actionsDiv.appendChild(delBtn);

    // More button
    var moreBtn = document.createElement('button');
    moreBtn.title = 'More';
    moreBtn.style.cssText = 'background:none;border:none;color:var(--text-3);font-size:12px;cursor:pointer;padding:1px 3px;border-radius:3px;line-height:1';
    moreBtn.textContent = '⋯';
    moreBtn.addEventListener('click', function(e) { e.preventDefault(); e.stopPropagation(); showSessionContextMenu(e.clientX, e.clientY, s); });
    actionsDiv.appendChild(moreBtn);

    div.appendChild(actionsDiv);
    return div;
  }

  // ── Inline Rename ─────────────────────────────────────────────
  function startInlineRename(itemDiv, session, titleSpan) {
    var currentName = (session.name || 'Chat').slice(0, 256);
    var input = document.createElement('input');
    input.type = 'text'; input.value = currentName; input.className = 'inline-edit-input';
    input.style.cssText = 'flex:1;min-width:0;background:var(--bg-0);border:1px solid var(--accent);border-radius:4px;padding:2px 6px;font-size:12px;font-weight:600;color:var(--text-0);outline:none;font-family:inherit';
    titleSpan.replaceWith(input); input.focus(); input.select();
    var finished = false;
    function finish(save) {
      if (finished) return; finished = true;
      if (save && input.value.trim() && input.value.trim() !== currentName) {
        fetch('/api/sessions/' + encodeURIComponent(session.id), {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: input.value.trim() })
        }).then(function(r) { return r.json(); }).then(function(j) {
          if (j.ok) { toast('✏️ Renamed', 'ok', 1200); if (window.S && window.S.sessionId === session.id) window.S.sessionName = input.value.trim(); window.loadChatSessions(); return; }
          revert();
        }).catch(function() { revert(); });
      } else { revert(); }
    }
    function revert() { titleSpan.textContent = currentName; if (input.parentNode) input.replaceWith(titleSpan); }
    input.addEventListener('keydown', function(e) { if (e.key === 'Enter') { e.preventDefault(); finish(true); } if (e.key === 'Escape') { e.preventDefault(); finish(false); } });
    input.addEventListener('blur', function() { finish(true); });
  }

  // ── Context Menu ──────────────────────────────────────────────
  var _ctxMenu = null, _currentItems = [], _ctxInit = false;

  function createContextMenu() {
    if (_ctxMenu) _ctxMenu.remove();
    _ctxMenu = document.createElement('div');
    _ctxMenu.id = 'chat-ctx-menu';
    _ctxMenu.style.cssText = 'position:fixed;z-index:20000;min-width:200px;max-width:280px;background:var(--bg-2);border:1px solid var(--border-hi);border-radius:12px;padding:6px;box-shadow:0 16px 48px rgba(0,0,0,.65);backdrop-filter:blur(16px);display:none';
    document.body.appendChild(_ctxMenu);

    _ctxMenu.addEventListener('click', function(e) {
      var itemEl = e.target.closest('.ctx-item');
      if (!itemEl) return;
      e.preventDefault(); e.stopPropagation();
      var idx = parseInt(itemEl.dataset.idx, 10);
      if (isNaN(idx) || idx < 0 || idx >= _currentItems.length) return;
      var handler = _currentItems[idx] && _currentItems[idx].handler;
      hideContextMenu();
      if (typeof handler === 'function') { try { handler(); } catch(err) { console.warn('[ctx]', err); } }
    });

    if (!_ctxInit) {
      document.addEventListener('mousedown', function(e) {
        if (_ctxMenu && _ctxMenu.style.display !== 'none' && !_ctxMenu.contains(e.target)) hideContextMenu();
      });
      document.addEventListener('contextmenu', function(e) {
        if (_ctxMenu && _ctxMenu.style.display !== 'none' && !_ctxMenu.contains(e.target)) hideContextMenu();
      });
      document.addEventListener('keydown', function(e) { if (e.key === 'Escape') hideContextMenu(); });
      _ctxInit = true;
    }
  }

  function showContextMenu(x, y, items) {
    if (!_ctxMenu) createContextMenu();
    _currentItems = items || [];
    var html = '';
    for (var i = 0; i < _currentItems.length; i++) {
      var item = _currentItems[i];
      if (item.separator) { html += '<div style="height:1px;background:var(--border);margin:4px 8px"></div>'; continue; }
      var ds = item.danger ? 'color:var(--danger)' : '';
      html += '<div class="ctx-item" data-idx="' + i + '" style="display:flex;align-items:center;gap:10px;padding:8px 12px;cursor:pointer;border-radius:8px;font-size:12.5px;color:var(--text-1);transition:background .1s;' + ds + '">'
        + '<span style="font-size:14px;width:18px;text-align:center;flex-shrink:0">' + (item.icon || '') + '</span>'
        + '<span style="flex:1">' + (item.label || '') + '</span>'
        + (item.shortcut ? '<span style="font-size:10px;color:var(--text-3);font-family:monospace">' + item.shortcut + '</span>' : '')
        + '</div>';
    }
    _ctxMenu.innerHTML = html;
    _ctxMenu.querySelectorAll('.ctx-item').forEach(function(el) {
      var isD = el.style.color === 'var(--danger)';
      el.addEventListener('mouseenter', function() { el.style.background = 'var(--bg-3)'; el.style.color = 'var(--text-0)'; });
      el.addEventListener('mouseleave', function() { el.style.background = ''; el.style.color = isD ? 'var(--danger)' : 'var(--text-1)'; });
    });
    _ctxMenu.style.display = 'block';
    var rect = _ctxMenu.getBoundingClientRect();
    _ctxMenu.style.left = Math.max(0, Math.min(x, window.innerWidth - rect.width - 8)) + 'px';
    _ctxMenu.style.top = Math.max(0, Math.min(y, window.innerHeight - rect.height - 8)) + 'px';
  }

  function hideContextMenu() { if (_ctxMenu) _ctxMenu.style.display = 'none'; }

  function showSessionContextMenu(x, y, session) {
    var items = [
      { icon: '📂', label: 'Open Chat', handler: function() { window.loadChatSession(session.id); } },
      { separator: true },
      { icon: '✏️', label: 'Rename', shortcut: 'DblClick', handler: function() {
        var el = document.querySelector('[data-session-id="' + session.id + '"] .session-title');
        if (el) startInlineRename(el.closest('.chat-session-item'), session, el);
      }},
      { icon: '📁', label: 'Move to Folder…', handler: function() { showFolderPickerMenu(session); } },
      { icon: session.pinned ? '📌' : '📍', label: session.pinned ? 'Unpin' : 'Pin to Top', handler: function() { window.pinChatSession(null, session.id, !session.pinned); } },
      { separator: true },
      { icon: '⎇', label: 'Fork / Branch', handler: function() { forkSessionQuick(session); } },
      { icon: '📋', label: 'Export as Markdown', handler: function() { downloadExport(session.id, 'markdown'); } },
      { icon: '📄', label: 'Export as JSON', handler: function() { downloadExport(session.id, 'json'); } },
      { separator: true },
      { icon: '🗑', label: 'Delete', danger: true, handler: function() {
        var confirmItems = [
          { icon: '⚠️', label: 'Confirm Delete?', danger: true, handler: function() {
            fetch('/api/sessions/' + encodeURIComponent(session.id), { method: 'DELETE' })
              .then(function(r) { return r.json(); })
              .then(function(j) {
                if (j.ok) { toast('🗑 Deleted', 'ok', 1200); if (window.S && window.S.sessionId === session.id && window.startNewChatSession) window.startNewChatSession(); window.loadChatSessions(); }
              });
          }},
          { icon: '✕', label: 'Cancel', handler: function() {} },
        ];
        showContextMenu(Math.round(window.innerWidth/2-120), Math.round(window.innerHeight/2-50), confirmItems);
      }},
    ];
    showContextMenu(x, y, items);
  }

  // ── Folder Picker Menu ────────────────────────────────────────
  function showFolderPickerMenu(session) {
    var folders = getCustomFolders();
    var current = (session.description && session.description !== 'All') ? session.description : 'General';
    var items = folders.map(function(f) {
      return { icon: f === current ? '✓' : getFolderIcon(f), label: f, handler: function() { moveSessionToFolder(session, f); } };
    });
    items.push({ separator: true });
    items.push({ icon: '➕', label: 'Create New Folder…', handler: function() {
      var name = prompt('New folder name:');
      if (name && name.trim()) {
        var fldrs = getCustomFolders();
        if (fldrs.indexOf(name.trim()) === -1) { fldrs.push(name.trim()); saveCustomFolders(fldrs); }
        moveSessionToFolder(session, name.trim());
      }
    }});
    showContextMenu(Math.round(window.innerWidth/2-120), Math.round(window.innerHeight/2-100), items);
  }

  function moveSessionToFolder(session, folder) {
    fetch('/api/sessions/' + encodeURIComponent(session.id), {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description: folder })
    }).then(function(r) { return r.json(); }).then(function(j) {
      if (j.ok) {
        var fldrs = getCustomFolders();
        if (fldrs.indexOf(folder) === -1) { fldrs.push(folder); saveCustomFolders(fldrs); }
        toast('📁 Moved to ' + folder, 'ok', 1200);
        if (window.S && window.S.sessionId === session.id) window.S.sessionFolder = folder;
        window.loadChatSessions();
      }
    }).catch(function() { toast('❌ Move failed', 'err', 2000); });
  }

  // ── Fork ──────────────────────────────────────────────────────
  function forkSessionQuick(session) {
    var name = '⎇ Fork: ' + (session.name || 'Chat').slice(0, 80);
    var origFolder = (session.description && session.description !== 'All') ? session.description : 'General';
    fetch('/api/sessions/' + encodeURIComponent(session.id) + '/branch', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name })
    }).then(function(r) { return r.json(); }).then(function(d) {
      if (!d.ok) { toast('❌ Fork failed', 'err', 2000); return; }
      return fetch('/api/sessions/' + encodeURIComponent(d.id), {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: origFolder })
      }).then(function() {
        toast('⎇ Forked: ' + d.name + ' (' + d.messages_copied + ' msgs)', 'ok', 2500);
        window.loadChatSessions();
      });
    }).catch(function() { toast('❌ Fork failed', 'err', 2000); });
  }

  // ── Export ─────────────────────────────────────────────────────
  function downloadExport(sessionId, fmt) {
    var label = fmt === 'json' ? 'JSON' : 'Markdown';
    var ext = fmt === 'json' ? '.json' : '.md';
    toast('📋 Downloading ' + label + '…', 'ok', 2000);
    var a = document.createElement('a');
    a.href = '/api/sessions/' + encodeURIComponent(sessionId) + '/export?fmt=' + fmt;
    a.download = 'export' + ext;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  // ── Folder Management ─────────────────────────────────────────
  function inlineRenameFolder(oldName) {
    var newName = prompt('Rename "' + oldName + '" to:', oldName);
    if (!newName || !newName.trim() || newName.trim() === oldName) return;
    var folders = getCustomFolders();
    var idx = folders.indexOf(oldName);
    if (idx >= 0) folders[idx] = newName.trim();
    else folders.push(newName.trim());
    saveCustomFolders(folders);
    // Update sessions
    fetch('/api/sessions?limit=200').then(function(r) { return r.json(); }).then(function(d) {
      var sessions = (d.sessions || []).filter(function(s) { return (s.description || 'General') === oldName; });
      return Promise.all(sessions.map(function(s) {
        return fetch('/api/sessions/' + encodeURIComponent(s.id), {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ description: newName.trim() })
        });
      }));
    }).then(function() {
      toast('📁 Renamed to "' + newName.trim() + '"', 'ok', 1500);
      window.loadChatSessions();
    }).catch(function() { toast('❌ Rename failed', 'err', 2000); });
  }

  function confirmDeleteFolder(folderName) {
    if (DEFAULT_FOLDERS.indexOf(folderName) !== -1) { toast('⚠️ Cannot delete default folders', 'warn', 2000); return; }
    if (!confirm('Delete "' + folderName + '"? Sessions will be moved to General.')) return;
    fetch('/api/sessions?limit=200').then(function(r) { return r.json(); }).then(function(d) {
      var sessions = (d.sessions || []).filter(function(s) { return (s.description || 'General') === folderName; });
      return Promise.all(sessions.map(function(s) {
        return fetch('/api/sessions/' + encodeURIComponent(s.id), {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ description: 'General' })
        });
      }));
    }).then(function() {
      var folders = getCustomFolders().filter(function(f) { return f !== folderName; });
      saveCustomFolders(folders);
      toast('🗑 Folder deleted', 'ok', 1500);
      window.loadChatSessions();
    });
  }

  function syncFoldersFromSessions(sessions) {
    var existing = getCustomFolders();
    var changed = false;
    sessions.forEach(function(s) {
      var desc = (s.description || '').trim();
      if (desc && desc !== 'All' && existing.indexOf(desc) === -1) { existing.push(desc); changed = true; }
    });
    if (changed) saveCustomFolders(existing);
  }

  // ── Wire up New Folder button ─────────────────────────────────
  function init() {
    createContextMenu();
    var newFolderBtn = document.getElementById('new-folder-btn');
    if (newFolderBtn) {
      newFolderBtn.addEventListener('click', function() {
        var name = prompt('New folder name:');
        if (name && name.trim()) {
          var folders = getCustomFolders();
          if (folders.indexOf(name.trim()) !== -1) { toast('⚠️ Folder already exists', 'warn', 1500); return; }
          folders.push(name.trim());
          saveCustomFolders(folders);
          toast('📁 Folder "' + name.trim() + '" created!', 'ok', 1500);
          window.loadChatSessions();
        }
      });
    }
    // Load sessions
    setTimeout(function() { if (typeof window.loadChatSessions === 'function') window.loadChatSessions(); }, 800);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  // Override selectChatFolder to filter in folder view
  window.selectChatFolder = function(folder) { window.loadChatSessions(); };
  window.filterChatSessions = function(val) {
    if (window._chatSearchTimeout) clearTimeout(window._chatSearchTimeout);
    window._chatSearchTimeout = setTimeout(function() { window.loadChatSessions(val.trim()); }, 250);
  };

})();
