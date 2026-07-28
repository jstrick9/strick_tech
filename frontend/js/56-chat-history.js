/**
 * Agentic OS — Enhanced Chat History Management
 * Industry-leading chat history with context menus, inline rename,
 * custom folders, date grouping, and polished UX.
 * Inspired by: Cursor, Open WebUI, ChatGPT, Claude
 */

(function() {
  'use strict';

  // ── Custom Folder Storage ──────────────────────────────────────
  const FOLDER_KEY = 'agentic_os_custom_folders';
  const DEFAULT_FOLDERS = ['General', 'Engineering', 'Research', 'Ideas'];

  function getCustomFolders() {
    try {
      const saved = _safeLS.get(FOLDER_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch(e) {}
    return [...DEFAULT_FOLDERS];
  }

  function saveCustomFolders(folders) {
    try { _safeLS.set(FOLDER_KEY, JSON.stringify(folders)); } catch(e) {}
    refreshFolderPills();
  }

  function getAllFolders() {
    return getCustomFolders();
  }

  // ── Context Menu (robust: delegated events, module-level state) ─
  let _ctxMenu = null;
  let _currentItems = [];   // module-level — no closures needed
  let _ctxMenuInitialized = false;

  function createContextMenu() {
    if (_ctxMenu) _ctxMenu.remove();
    _ctxMenu = document.createElement('div');
    _ctxMenu.id = 'chat-ctx-menu';
    _ctxMenu.style.cssText = [
      'position:fixed',
      'z-index:20000',
      'min-width:200px',
      'max-width:280px',
      'background:var(--bg-2)',
      'border:1px solid var(--border-hi)',
      'border-radius:12px',
      'padding:6px',
      'box-shadow:0 16px 48px rgba(0,0,0,.65)',
      'backdrop-filter:blur(16px)',
      'display:none',
    ].join(';');
    document.body.appendChild(_ctxMenu);

    // ── Delegated click handler (attached ONCE on the container) ──
    // This fires for every click INSIDE the menu. We find the closest
    // .ctx-item ancestor, read its data-idx, and call the handler.
    _ctxMenu.addEventListener('click', function(e) {
      var itemEl = e.target.closest('.ctx-item');
      if (!itemEl) return;
      e.preventDefault();
      e.stopPropagation();
      var idx = parseInt(itemEl.dataset.idx, 10);
      if (isNaN(idx) || idx < 0 || idx >= _currentItems.length) return;
      var handler = _currentItems[idx] && _currentItems[idx].handler;
      // Hide FIRST, then run handler (so modal can appear on top)
      hideContextMenu();
      if (typeof handler === 'function') {
        try { handler(); } catch(err) { console.warn('[ctx] handler error:', err); }
      }
    });

    // ── Close on mousedown OUTSIDE the menu ─────────────────────
    // Using mousedown (not click + capture) so it fires BEFORE any
    // click handlers on menu items. We check contains() to avoid
    // closing when the user clicks INSIDE the menu.
    if (!_ctxMenuInitialized) {
      document.addEventListener('mousedown', function(e) {
        if (_ctxMenu && _ctxMenu.style.display !== 'none' && !_ctxMenu.contains(e.target)) {
          hideContextMenu();
        }
      });
      // Also close on right-click outside (opening a new context menu elsewhere)
      document.addEventListener('contextmenu', function(e) {
        if (_ctxMenu && _ctxMenu.style.display !== 'none' && !_ctxMenu.contains(e.target)) {
          hideContextMenu();
        }
      });
      // Close on Escape
      document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') hideContextMenu();
      });
      _ctxMenuInitialized = true;
    }
  }

  function showContextMenu(x, y, items) {
    if (!_ctxMenu) createContextMenu();
    // Store items at module level — no closures needed
    _currentItems = items || [];

    // Build HTML
    var html = '';
    for (var i = 0; i < _currentItems.length; i++) {
      var item = _currentItems[i];
      if (item.separator) {
        html += '<div style="height:1px;background:var(--border);margin:4px 8px"></div>';
        continue;
      }
      var dangerStyle = item.danger ? 'color:var(--danger)' : '';
      var icon = item.icon || '';
      var shortcut = item.shortcut
        ? '<span style="font-size:10px;color:var(--text-3);font-family:monospace">' + item.shortcut + '</span>'
        : '';
      html += '<div class="ctx-item" data-idx="' + i + '" style="'
        + 'display:flex;align-items:center;gap:10px;padding:8px 12px;cursor:pointer;'
        + 'border-radius:8px;font-size:12.5px;color:var(--text-1);transition:background .1s;'
        + dangerStyle + '">'
        + '<span style="font-size:14px;width:18px;text-align:center;flex-shrink:0">' + icon + '</span>'
        + '<span style="flex:1">' + (item.label || '') + '</span>'
        + shortcut
        + '</div>';
    }
    _ctxMenu.innerHTML = html;

    // Add hover styles via delegated handlers (only once per render)
    var ctxItems = _ctxMenu.querySelectorAll('.ctx-item');
    for (var j = 0; j < ctxItems.length; j++) {
      (function(el) {
        var isDanger = el.style.color === 'var(--danger)';
        el.addEventListener('mouseenter', function() {
          el.style.background = 'var(--bg-3)';
          el.style.color = 'var(--text-0)';
        });
        el.addEventListener('mouseleave', function() {
          el.style.background = '';
          el.style.color = isDanger ? 'var(--danger)' : 'var(--text-1)';
        });
      })(ctxItems[j]);
    }

    // Position
    _ctxMenu.style.display = 'block';
    var rect = _ctxMenu.getBoundingClientRect();
    var maxX = window.innerWidth - rect.width - 8;
    var maxY = window.innerHeight - rect.height - 8;
    _ctxMenu.style.left = Math.max(0, Math.min(x, maxX)) + 'px';
    _ctxMenu.style.top = Math.max(0, Math.min(y, maxY)) + 'px';
  }

  function hideContextMenu() {
    if (_ctxMenu) _ctxMenu.style.display = 'none';
  }

  // ── Date Grouping ──────────────────────────────────────────────
  function getDateGroup(dateStr) {
    if (!dateStr) return 'Older';
    var d = new Date(dateStr);
    if (isNaN(d.getTime())) return 'Older';
    var now = new Date();
    var todayStr = now.toISOString().slice(0, 10);
    var dateStr2 = d.toISOString().slice(0, 10);
    if (dateStr2 === todayStr) return 'Today';
    var yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    if (dateStr2 === yesterday.toISOString().slice(0, 10)) return 'Yesterday';
    var weekAgo = new Date(now);
    weekAgo.setDate(weekAgo.getDate() - 7);
    if (d >= weekAgo) return 'Previous 7 Days';
    var monthAgo = new Date(now);
    monthAgo.setMonth(monthAgo.getMonth() - 1);
    if (d >= monthAgo) return 'Previous 30 Days';
    return 'Older';
  }

  // ── Enhanced loadChatSessions ──────────────────────────────────
  window.loadChatSessions = async function(q) {
    q = String(q || '').trim();
    if (q !== window._chatLastQuery) {
      window._chatLastQuery = q;
      window._chatCurrentPage = 1;
    }
    var el = document.getElementById('chat-sessions-list');
    if (!el) return;

    try {
      var r = await fetch('/api/sessions?limit=200&q=' + encodeURIComponent(q));
      var data = await r.json();
      var sessions = data.sessions || [];

      syncFoldersFromSessions(sessions);

      if (!sessions.length) {
        el.innerHTML = renderEmptyState();
        var startBtn = document.getElementById('btn-start-first');
        if (startBtn) startBtn.addEventListener('click', function() { window.startNewChatSession(); });
        return;
      }

      // Apply folder filter
      var folderFilter = window._activeChatFolder || 'All';
      if (folderFilter !== 'All') {
        sessions = sessions.filter(function(s) {
          var folder = (s.description && s.description !== 'All') ? s.description : 'General';
          return folder === folderFilter;
        });
      }

      // Update folder sort options
      var optFAZ = document.getElementById('opt-sort-folder-az');
      var optFZA = document.getElementById('opt-sort-folder-za');
      if (optFAZ && optFZA) {
        var showFolderSort = (folderFilter === 'All');
        optFAZ.style.display = showFolderSort ? '' : 'none';
        optFZA.style.display = showFolderSort ? '' : 'none';
        if (!showFolderSort && (window._chatSortOrder === 'folder_az' || window._chatSortOrder === 'folder_za')) {
          window._chatSortOrder = 'newest';
          var sortSel = document.getElementById('chat-sort-select');
          if (sortSel) sortSel.value = 'newest';
        }
      }

      // Sort (pinned first)
      sessions.sort(function(a, b) {
        if (a.pinned !== b.pinned) return b.pinned - a.pinned;
        var order = window._chatSortOrder || 'newest';
        var timeA = new Date(a.updated_at || a.created_at || 0).getTime();
        var timeB = new Date(b.updated_at || b.created_at || 0).getTime();
        if (order === 'oldest') return timeA - timeB;
        if (order === 'az') return (a.name || 'Chat').localeCompare(b.name || 'Chat');
        if (order === 'za') return (b.name || 'Chat').localeCompare(a.name || 'Chat');
        if (order === 'folder_az') return (a.description || 'General').localeCompare(b.description || 'General') || (a.name || '').localeCompare(b.name || '');
        if (order === 'folder_za') return (b.description || 'General').localeCompare(a.description || 'General') || (b.name || '').localeCompare(a.name || '');
        return timeB - timeA;
      });

      // Paginate
      var pageSize = window._chatPageSize || 5;
      var totalSessions = sessions.length;
      var totalPages = Math.max(1, Math.ceil(totalSessions / pageSize));
      if (window._chatCurrentPage > totalPages) window._chatCurrentPage = totalPages;
      var curPage = window._chatCurrentPage || 1;
      var startIdx = (curPage - 1) * pageSize;
      var pageSessions = sessions.slice(startIdx, startIdx + pageSize);

      updatePaginationUI(totalSessions, curPage, totalPages);

      if (!pageSessions.length) {
        el.innerHTML = renderEmptyPageState(totalSessions);
        var hereBtn = document.getElementById('btn-start-here');
        if (hereBtn) hereBtn.addEventListener('click', function() { window.startNewChatSession(); });
        return;
      }

      // Render with date grouping
      var sortOrder = window._chatSortOrder || 'newest';
      var useDateGroups = (sortOrder === 'newest' || sortOrder === 'oldest') && folderFilter === 'All';
      el.innerHTML = '';

      if (useDateGroups) {
        var groups = {};
        pageSessions.forEach(function(s) {
          var group = getDateGroup(s.updated_at || s.created_at);
          if (!groups[group]) groups[group] = [];
          groups[group].push(s);
        });
        ['Today', 'Yesterday', 'Previous 7 Days', 'Previous 30 Days', 'Older'].forEach(function(groupName) {
          var items = groups[groupName];
          if (!items || !items.length) return;
          var header = document.createElement('div');
          header.style.cssText = 'font-size:10.5px;font-weight:700;color:var(--text-3);padding:8px 4px 4px;letter-spacing:.04em;text-transform:uppercase';
          header.textContent = groupName;
          el.appendChild(header);
          items.forEach(function(s) { el.appendChild(renderSessionItem(s)); });
        });
      } else {
        pageSessions.forEach(function(s) { el.appendChild(renderSessionItem(s)); });
      }
    } catch(e) {
      console.warn('Failed to load chat sessions:', e);
      el.innerHTML = '<div style="color:var(--danger);font-size:12px;text-align:center;padding:20px">Failed to load chats</div>';
    }
  };

  // ── Render Empty State ─────────────────────────────────────────
  function renderEmptyState() {
    return '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:32px 16px;text-align:center">'
      + '<div style="font-size:36px;margin-bottom:12px;opacity:.6">💬</div>'
      + '<div style="font-size:13px;font-weight:700;color:var(--text-1);margin-bottom:4px">No conversations yet</div>'
      + '<div style="font-size:11.5px;color:var(--text-3);margin-bottom:16px">Start a chat to see your history here</div>'
      + '<button id="btn-start-first" class="btn-3d btn-primary btn-sm" style="padding:6px 16px;font-weight:700">＋ Start First Chat</button>'
      + '</div>';
  }

  function renderEmptyPageState(total) {
    return '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px 16px;text-align:center">'
      + '<div style="font-size:12px;color:var(--text-3);margin-bottom:12px">' + (total === 0 ? 'No saved conversations yet.' : 'No chats on this page.') + '</div>'
      + '<button id="btn-start-here" class="btn-3d btn-primary btn-sm" style="padding:6px 16px;font-weight:700">＋ New Chat</button>'
      + '</div>';
  }

  // ── Update Pagination UI ───────────────────────────────────────
  function updatePaginationUI(total, curPage, totalPages) {
    var pagEl = document.getElementById('chat-sessions-pagination');
    if (!pagEl) return;
    pagEl.style.display = total > 0 ? 'flex' : 'none';
    var ind = document.getElementById('chat-page-indicator');
    if (ind) ind.textContent = 'Page ' + curPage + ' of ' + totalPages + ' (' + total + ' total)';
    var prevBtn = document.getElementById('chat-page-prev');
    var nextBtn = document.getElementById('chat-page-next');
    if (prevBtn) prevBtn.disabled = (curPage <= 1);
    if (nextBtn) nextBtn.disabled = (curPage >= totalPages);
  }

  // ── Render Single Session Item ─────────────────────────────────
  function renderSessionItem(s) {
    var isCurrent = (s.id === (window.S && window.S.sessionId));
    var folder = (s.description && s.description !== 'All') ? s.description : 'General';
    var folderIcon = getFolderIcon(folder);
    var snameSafe = (s.name || 'Chat').slice(0, 256);
    var timeAgo = formatTimeAgo(s.updated_at || s.created_at);

    var itemDiv = document.createElement('div');
    itemDiv.className = 'chat-session-item' + (isCurrent ? ' active' : '');
    itemDiv.dataset.sessionId = s.id;
    itemDiv.style.cssText = 'display:flex;flex-direction:column;gap:3px;padding:10px 10px 8px;'
      + 'border-radius:10px;cursor:pointer;transition:all .15s;'
      + 'background:' + (isCurrent ? 'var(--accent-glow)' : 'transparent') + ';'
      + 'border:1px solid ' + (isCurrent ? 'var(--accent)' : 'transparent');

    // Hover effects
    itemDiv.addEventListener('mouseenter', function() {
      if (!isCurrent) { itemDiv.style.background = 'var(--bg-3)'; itemDiv.style.borderColor = 'var(--border)'; }
      var actions = itemDiv.querySelector('.session-actions');
      if (actions) actions.style.opacity = '1';
    });
    itemDiv.addEventListener('mouseleave', function() {
      if (!isCurrent) { itemDiv.style.background = 'transparent'; itemDiv.style.borderColor = 'transparent'; }
      var actions = itemDiv.querySelector('.session-actions');
      if (actions) actions.style.opacity = '0';
    });

    // Click to load
    itemDiv.addEventListener('click', function(e) {
      if (e.target.closest('.session-actions') || e.target.closest('.inline-edit-input')) return;
      window.loadChatSession(s.id);
    });

    // Right-click context menu
    itemDiv.addEventListener('contextmenu', function(e) {
      e.preventDefault();
      e.stopPropagation();
      showSessionContextMenu(e.clientX, e.clientY, s);
    });

    // ── Top row ──
    var topRow = document.createElement('div');
    topRow.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:4px;min-height:22px';

    var titleWrap = document.createElement('div');
    titleWrap.style.cssText = 'flex:1;min-width:0;display:flex;align-items:center;gap:4px';

    if (s.pinned) {
      var pin = document.createElement('span');
      pin.style.cssText = 'font-size:11px;flex-shrink:0';
      pin.textContent = '📌';
      titleWrap.appendChild(pin);
    }

    var titleSpan = document.createElement('span');
    titleSpan.className = 'session-title';
    titleSpan.style.cssText = 'font-size:12.5px;font-weight:' + (isCurrent ? '800' : '600')
      + ';color:var(--text-0);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;min-width:0';
    titleSpan.textContent = snameSafe;
    titleSpan.title = snameSafe;

    titleSpan.addEventListener('dblclick', function(e) {
      e.preventDefault();
      e.stopPropagation();
      startInlineRename(itemDiv, s, titleSpan);
    });

    titleWrap.appendChild(titleSpan);
    topRow.appendChild(titleWrap);

    // Action buttons (hover)
    var btnGroup = document.createElement('div');
    btnGroup.className = 'session-actions';
    btnGroup.style.cssText = 'display:flex;gap:2px;align-items:center;flex-shrink:0;opacity:0;transition:opacity .12s';

    // ⋯ button
    var moreBtn = document.createElement('button');
    moreBtn.title = 'More actions';
    moreBtn.style.cssText = 'background:none;border:none;color:var(--text-3);font-size:13px;cursor:pointer;padding:2px 4px;border-radius:4px;line-height:1;transition:all .1s';
    moreBtn.textContent = '⋯';
    moreBtn.addEventListener('mouseenter', function() { moreBtn.style.background = 'var(--bg-4)'; moreBtn.style.color = 'var(--text-0)'; });
    moreBtn.addEventListener('mouseleave', function() { moreBtn.style.background = 'none'; moreBtn.style.color = 'var(--text-3)'; });
    moreBtn.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      showSessionContextMenu(e.clientX, e.clientY, s);
    });
    btnGroup.appendChild(moreBtn);

    // ✕ delete button — visual toggle: first click → "Confirm?", second → delete
    var delBtn = document.createElement('button');
    delBtn.title = 'Delete chat';
    delBtn.style.cssText = 'background:none;border:none;color:var(--text-3);font-size:12px;cursor:pointer;padding:2px 4px;border-radius:4px;line-height:1;transition:all .1s';
    delBtn.innerHTML = '✕';
    var delConfirming = false;
    var delResetTimer = null;
    delBtn.addEventListener('mouseenter', function() {
      if (!delConfirming) { delBtn.style.background = 'rgba(232,82,82,.15)'; delBtn.style.color = 'var(--danger)'; }
    });
    delBtn.addEventListener('mouseleave', function() {
      if (!delConfirming) { delBtn.style.background = 'none'; delBtn.style.color = 'var(--text-3)'; }
    });
    delBtn.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      if (!delConfirming) {
        // First click: show confirm state
        delConfirming = true;
        delBtn.innerHTML = 'Confirm?';
        delBtn.style.background = 'var(--danger)';
        delBtn.style.color = '#fff';
        delBtn.title = 'Click again to confirm deletion';
        // Auto-reset after 3 seconds
        clearTimeout(delResetTimer);
        delResetTimer = setTimeout(function() {
          delConfirming = false;
          delBtn.innerHTML = '✕';
          delBtn.style.background = 'none';
          delBtn.style.color = 'var(--text-3)';
          delBtn.title = 'Delete chat';
        }, 3000);
      } else {
        // Second click: actually delete
        clearTimeout(delResetTimer);
        fetch('/api/sessions/' + encodeURIComponent(s.id), { method: 'DELETE' })
          .then(function(r) { return r.json(); })
          .then(function(j) {
            if (j.ok) {
              toast('🗑 Chat deleted', 'ok', 1500);
              if (window.S && window.S.sessionId === s.id && typeof window.startNewChatSession === 'function') window.startNewChatSession();
              window.loadChatSessions();
            } else {
              toast('❌ Delete failed: ' + (j.error || 'Unknown'), 'err', 2500);
              delConfirming = false;
              delBtn.innerHTML = '✕';
              delBtn.style.background = 'none';
              delBtn.style.color = 'var(--text-3)';
            }
          })
          .catch(function(err) {
            toast('❌ Delete error: ' + err.message, 'err', 2500);
            delConfirming = false;
            delBtn.innerHTML = '✕';
            delBtn.style.background = 'none';
            delBtn.style.color = 'var(--text-3)';
          });
      }
    });
    btnGroup.appendChild(delBtn);

    // 📋 Export MD button
    var expMdBtn = document.createElement('button');
    expMdBtn.title = 'Export as Markdown';
    expMdBtn.style.cssText = 'background:none;border:none;color:var(--text-3);font-size:11px;cursor:pointer;padding:2px 4px;border-radius:4px;line-height:1;transition:all .1s';
    expMdBtn.textContent = '📋';
    expMdBtn.addEventListener('mouseenter', function() { expMdBtn.style.background = 'var(--bg-4)'; expMdBtn.style.color = 'var(--text-0)'; });
    expMdBtn.addEventListener('mouseleave', function() { expMdBtn.style.background = 'none'; expMdBtn.style.color = 'var(--text-3)'; });
    expMdBtn.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      downloadExport(s.id, 'markdown');
    });
    btnGroup.appendChild(expMdBtn);

    // 📄 Export JSON button
    var expJsonBtn = document.createElement('button');
    expJsonBtn.title = 'Export as JSON';
    expJsonBtn.style.cssText = 'background:none;border:none;color:var(--text-3);font-size:11px;cursor:pointer;padding:2px 4px;border-radius:4px;line-height:1;transition:all .1s';
    expJsonBtn.textContent = '📄';
    expJsonBtn.addEventListener('mouseenter', function() { expJsonBtn.style.background = 'var(--bg-4)'; expJsonBtn.style.color = 'var(--text-0)'; });
    expJsonBtn.addEventListener('mouseleave', function() { expJsonBtn.style.background = 'none'; expJsonBtn.style.color = 'var(--text-3)'; });
    expJsonBtn.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      downloadExport(s.id, 'json');
    });
    btnGroup.appendChild(expJsonBtn);

    topRow.appendChild(btnGroup);
    itemDiv.appendChild(topRow);

    // ── Bottom row ──
    var bottomRow = document.createElement('div');
    bottomRow.style.cssText = 'display:flex;align-items:center;justify-content:space-between;font-size:10.5px;color:var(--text-3);padding-left:2px';

    var folderBadge = document.createElement('span');
    folderBadge.className = 'session-folder-badge';
    folderBadge.style.cssText = 'display:inline-flex;align-items:center;gap:3px;background:var(--bg-2);padding:1px 6px;border-radius:4px;border:1px solid var(--border);cursor:pointer;transition:all .1s';
    folderBadge.textContent = folderIcon + ' ' + folder;
    folderBadge.title = 'Click to change folder';
    folderBadge.addEventListener('mouseenter', function() { folderBadge.style.borderColor = 'var(--accent)'; });
    folderBadge.addEventListener('mouseleave', function() { folderBadge.style.borderColor = 'var(--border)'; });
    folderBadge.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      showFolderPicker(e.clientX, e.clientY, s);
    });
    bottomRow.appendChild(folderBadge);

    var metaSpan = document.createElement('span');
    metaSpan.style.cssText = 'display:flex;align-items:center;gap:6px';
    metaSpan.innerHTML = '<span>' + (s.message_count || 0) + ' msgs</span><span>·</span><span>' + timeAgo + '</span>';
    bottomRow.appendChild(metaSpan);

    itemDiv.appendChild(bottomRow);
    return itemDiv;
  }

  // ── Inline Rename ──────────────────────────────────────────────
  function startInlineRename(itemDiv, session, titleSpan) {
    var currentName = (session.name || 'Chat').slice(0, 256);
    var input = document.createElement('input');
    input.type = 'text';
    input.value = currentName;
    input.className = 'inline-edit-input';
    input.style.cssText = 'flex:1;min-width:0;background:var(--bg-0);border:1px solid var(--accent);border-radius:4px;padding:2px 6px;font-size:12.5px;font-weight:600;color:var(--text-0);outline:none;font-family:inherit';

    titleSpan.replaceWith(input);
    input.focus();
    input.select();

    var finished = false;
    function finishRename(save) {
      if (finished) return;
      finished = true;
      if (save && input.value.trim() && input.value.trim() !== currentName) {
        fetch('/api/sessions/' + encodeURIComponent(session.id), {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: input.value.trim() })
        }).then(function(r) { return r.json(); }).then(function(j) {
          if (j.ok) {
            toast('✏️ Chat renamed', 'ok', 1200);
            if (window.S && window.S.sessionId === session.id) window.S.sessionName = input.value.trim();
            window.loadChatSessions();
            return;
          }
          revert();
        }).catch(function() { revert(); });
      } else {
        revert();
      }
    }
    function revert() {
      titleSpan.textContent = currentName;
      if (input.parentNode) input.replaceWith(titleSpan);
    }

    input.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') { e.preventDefault(); finishRename(true); }
      if (e.key === 'Escape') { e.preventDefault(); finishRename(false); }
    });
    input.addEventListener('blur', function() { finishRename(true); });
  }

  // ── Session Context Menu ───────────────────────────────────────
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
      { icon: '🗑', label: 'Delete', danger: true, shortcut: 'Del', handler: function() {
        // Two-click confirmation: first click shows confirm, second deletes
        var confirmItems = [
          { icon: '⚠️', label: 'Confirm Delete?', danger: true, handler: function() {
            fetch('/api/sessions/' + encodeURIComponent(session.id), { method: 'DELETE' })
              .then(function(r) { return r.json(); })
              .then(function(j) {
                if (j.ok) {
                  toast('🗑 Chat deleted', 'ok', 1500);
                  if (window.S && window.S.sessionId === session.id && typeof window.startNewChatSession === 'function') window.startNewChatSession();
                  window.loadChatSessions();
                } else {
                  toast('❌ Delete failed: ' + (j.error || 'Unknown'), 'err', 2500);
                }
              }).catch(function(e) { toast('❌ Delete error: ' + e.message, 'err', 2500); });
          }},
          { icon: '✕', label: 'Cancel', handler: function() {} },
        ];
        showContextMenu(Math.round(window.innerWidth / 2 - 120), Math.round(window.innerHeight / 2 - 50), confirmItems);
      }},
    ];
    showContextMenu(x, y, items);
  }

  // ── Folder Picker ──────────────────────────────────────────────
  function showFolderPicker(x, y, session) {
    var folders = getAllFolders();
    var currentFolder = (session.description && session.description !== 'All') ? session.description : 'General';
    var items = folders.map(function(f) {
      return { icon: f === currentFolder ? '✓' : getFolderIcon(f), label: f, handler: function() { moveSessionToFolder(session, f); } };
    });
    items.push({ separator: true });
    items.push({ icon: '➕', label: 'Create New Folder…', handler: function() { createNewFolder(session); } });
    showContextMenu(x, y, items);
  }

  function showFolderPickerMenu(session) {
    var folders = getAllFolders();
    var currentFolder = (session.description && session.description !== 'All') ? session.description : 'General';
    var items = [];
    for (var i = 0; i < folders.length; i++) {
      (function(f) {
        items.push({
          icon: f === currentFolder ? '✓' : getFolderIcon(f),
          label: f,
          handler: function() { moveSessionToFolder(session, f); }
        });
      })(folders[i]);
    }
    items.push({ separator: true });
    items.push({ icon: '➕', label: 'Create New Folder…', handler: function() {
      var name = prompt('New folder name:');
      if (name && name.trim()) {
        var fldrs = getCustomFolders();
        if (fldrs.indexOf(name.trim()) === -1) { fldrs.push(name.trim()); saveCustomFolders(fldrs); }
        moveSessionToFolder(session, name.trim());
      }
    }});
    // Show at center of viewport
    showContextMenu(Math.round(window.innerWidth / 2 - 120), Math.round(window.innerHeight / 2 - 100), items);
  }

  function showFolderPickerAtCenter(session) {
    var folders = getAllFolders();
    var currentFolder = (session.description && session.description !== 'All') ? session.description : 'General';
    var folderList = folders.map(function(f) {
      return (f === currentFolder ? '✓ ' : '') + getFolderIcon(f) + ' ' + f;
    }).join('\n');

    if (typeof window.gmPrompt === 'function') {
      window.gmPrompt('Move to Folder', 'Current: ' + currentFolder + '\n\nAvailable folders:\n' + folderList + '\n\nType a folder name:', currentFolder).then(function(newFolder) {
        if (newFolder !== null && newFolder.trim()) {
          moveSessionToFolder(session, newFolder.trim());
        }
      });
    }
  }

  function moveSessionToFolder(session, folder) {
    fetch('/api/sessions/' + encodeURIComponent(session.id), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description: folder })
    }).then(function(r) { return r.json(); }).then(function(j) {
      if (j.ok) {
        var folders = getCustomFolders();
        if (folders.indexOf(folder) === -1) { folders.push(folder); saveCustomFolders(folders); }
        toast('📁 Moved to ' + folder, 'ok', 1200);
        if (window.S && window.S.sessionId === session.id) window.S.sessionFolder = folder;
        window.loadChatSessions();
      }
    }).catch(function() { toast('❌ Move failed', 'err', 2000); });
  }

  function createNewFolder(session) {
    if (typeof window.gmPrompt !== 'function') return;
    window.gmPrompt('Create New Folder', 'Enter a name for the new folder:', '').then(function(name) {
      if (!name || !name.trim()) return;
      var folderName = name.trim();
      var folders = getCustomFolders();
      if (folders.indexOf(folderName) === -1) { folders.push(folderName); saveCustomFolders(folders); toast('📁 Folder "' + folderName + '" created', 'ok', 1500); }
      if (session) moveSessionToFolder(session, folderName);
    });
  }

  // ── Fork Quick ─────────────────────────────────────────────────
  function forkSessionQuick(session) {
    var name = '⎇ Fork: ' + (session.name || 'Chat').slice(0, 80);
    var originalFolder = (session.description && session.description !== 'All') ? session.description : 'General';
    fetch('/api/sessions/' + encodeURIComponent(session.id) + '/branch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name })
    }).then(function(r) { return r.json(); }).then(function(d) {
      if (!d.ok) { toast('❌ Fork failed', 'err', 2000); return; }
      // Preserve original folder — backend sets description to "Branched from..."
      return fetch('/api/sessions/' + encodeURIComponent(d.id), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: originalFolder })
      }).then(function() {
        toast('⎇ Forked: ' + d.name + ' (' + d.messages_copied + ' msgs)', 'ok', 2500);
        window.loadChatSessions();
      });
    }).catch(function() { toast('❌ Fork failed', 'err', 2000); });
  }

  // ── Sync Folders from Sessions ─────────────────────────────────
  function syncFoldersFromSessions(sessions) {
    var existing = getCustomFolders();
    var changed = false;
    sessions.forEach(function(s) {
      var desc = (s.description || '').trim();
      if (desc && desc !== 'All' && existing.indexOf(desc) === -1) { existing.push(desc); changed = true; }
    });
    if (changed) saveCustomFolders(existing);
  }

  // ── Refresh Folder Pills ───────────────────────────────────────
  window.refreshFolderPills = function() {
    var container = document.getElementById('chat-folder-pills');
    if (!container) return;
    var folders = getAllFolders();
    var activeFolder = window._activeChatFolder || 'All';
    container.innerHTML = '';

    // "All" pill
    var allBtn = document.createElement('button');
    allBtn.type = 'button';
    allBtn.className = 'tag';
    allBtn.textContent = 'All Chats';
    allBtn.style.cssText = folderPillStyle(activeFolder === 'All');
    allBtn.addEventListener('click', function() { window.selectChatFolder('All'); });
    container.appendChild(allBtn);

    // Folder pills
    folders.forEach(function(f) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'tag';
      btn.textContent = getFolderIcon(f) + ' ' + f;
      btn.style.cssText = folderPillStyle(activeFolder === f);
      btn.addEventListener('click', function() { window.selectChatFolder(f); });
      btn.addEventListener('contextmenu', function(e) { e.preventDefault(); showFolderManageMenu(e.clientX, e.clientY, f); });
      container.appendChild(btn);
    });

    // "New Folder" button
    var newBtn = document.createElement('button');
    newBtn.type = 'button';
    newBtn.className = 'tag';
    newBtn.innerHTML = '＋';
    newBtn.title = 'Create new folder';
    newBtn.style.cssText = 'cursor:pointer;font-weight:700;font-size:12px;padding:3px 8px;border-radius:6px;background:var(--bg-2);color:var(--text-2);border:1px dashed var(--border);flex-shrink:0;transition:all .1s';
    newBtn.addEventListener('mouseenter', function() { newBtn.style.borderColor = 'var(--accent)'; newBtn.style.color = 'var(--accent)'; });
    newBtn.addEventListener('mouseleave', function() { newBtn.style.borderColor = 'var(--border)'; newBtn.style.color = 'var(--text-2)'; });
    newBtn.addEventListener('click', function() {
      if (typeof window.gmPrompt !== 'function') return;
      window.gmPrompt('Create New Folder', 'Enter a folder name:', '').then(function(name) {
        if (name && name.trim()) {
          var fldrs = getCustomFolders();
          if (fldrs.indexOf(name.trim()) === -1) { fldrs.push(name.trim()); saveCustomFolders(fldrs); toast('📁 Folder "' + name.trim() + '" created!', 'ok', 1500); }
        }
      });
    });
    container.appendChild(newBtn);
  };

  function folderPillStyle(isActive) {
    return 'cursor:pointer;font-weight:' + (isActive ? '700' : '600') + ';font-size:11px;'
      + 'padding:3px 8px;border-radius:6px;flex-shrink:0;'
      + 'background:' + (isActive ? 'var(--accent)' : 'var(--bg-2)') + ';'
      + 'color:' + (isActive ? '#fff' : 'var(--text-1)') + ';'
      + 'border:1px solid ' + (isActive ? 'var(--accent)' : 'var(--border)') + ';'
      + 'transition:all .12s';
  }

  // ── Folder Management Menu ─────────────────────────────────────
  function showFolderManageMenu(x, y, folderName) {
    var items = [
      { icon: '✏️', label: 'Rename "' + folderName + '"', handler: function() { renameFolder(folderName); } },
      { separator: true },
      { icon: '🗑', label: 'Delete Folder', danger: true, handler: function() { deleteFolder(folderName); } },
    ];
    showContextMenu(x, y, items);
  }

  function renameFolder(oldName) {
    if (typeof window.gmPrompt !== 'function') return;
    window.gmPrompt('Rename Folder', 'Rename "' + oldName + '" to:', oldName).then(function(newName) {
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
        toast('📁 Folder renamed to "' + newName.trim() + '"', 'ok', 1500);
        if (window._activeChatFolder === oldName) window._activeChatFolder = newName.trim();
        window.loadChatSessions();
      }).catch(function() { toast('❌ Rename failed', 'err', 2000); });
    });
  }

  function deleteFolder(folderName) {
    if (DEFAULT_FOLDERS.indexOf(folderName) !== -1) { toast('⚠️ Cannot delete default folders', 'warn', 2000); return; }
    if (typeof window.gmConfirm !== 'function') return;
    window.gmConfirm('Delete Folder', 'Delete "' + folderName + '"? Sessions will be moved to General.').then(function(ok) {
      if (!ok) return;
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
        if (window._activeChatFolder === folderName) window._activeChatFolder = 'All';
        toast('🗑 Folder "' + folderName + '" deleted', 'ok', 1500);
        window.loadChatSessions();
      });
    });
  }

  // ── Direct Export Download (no dependency on window.exportSession) ──
  function downloadExport(sessionId, fmt) {
    var label = fmt === 'json' ? 'JSON' : 'Markdown';
    toast('📋 Downloading ' + label + '…', 'ok', 2000);
    var url = '/api/sessions/' + encodeURIComponent(sessionId) + '/export?fmt=' + fmt;
    // window.open with _blank: server returns Content-Disposition: attachment
    // which forces download in both browser and Tauri webview
    window.open(url, '_blank');
  }

  // ── Helpers ────────────────────────────────────────────────────
  function getFolderIcon(folder) {
    var icons = { 'General': '📁', 'Engineering': '⚙️', 'Research': '🔬', 'Ideas': '💡', 'Work': '💼', 'Personal': '🏠', 'Projects': '🎯', 'Archive': '📦' };
    return icons[folder] || '📂';
  }

  function formatTimeAgo(dateStr) {
    if (!dateStr) return '';
    var d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr.slice(5, 16);
    var diff = Date.now() - d.getTime();
    var mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return mins + 'm ago';
    var hours = Math.floor(diff / 3600000);
    if (hours < 24) return hours + 'h ago';
    var days = Math.floor(diff / 86400000);
    if (days < 7) return days + 'd ago';
    return dateStr.slice(5, 16);
  }

  // ── Override selectChatFolder ──────────────────────────────────
  window.selectChatFolder = function(folder) {
    window._activeChatFolder = folder;
    window._chatCurrentPage = 1;
    window.refreshFolderPills();
    window.loadChatSessions();
  };

  // ── CSS ────────────────────────────────────────────────────────
  (function() {
    var s = document.createElement('style');
    s.textContent = [
      '.chat-session-item:hover { background: var(--bg-3) !important; }',
      '#chat-ctx-menu .ctx-item:hover { background: var(--bg-3); }',
      '.inline-edit-input:focus { border-color: var(--accent) !important; box-shadow: 0 0 0 2px var(--accent-glow) !important; }',
      '.chat-session-item:hover .session-actions { opacity: 1 !important; }',
      '.session-folder-badge:hover { border-color: var(--accent) !important; background: var(--bg-3) !important; }',
      '#chat-folder-pills button { transition: all .12s ease; }',
      '#chat-folder-pills button:hover { border-color: var(--accent) !important; }',
    ].join('\n');
    document.head.appendChild(s);
  })();

  // ── Init ───────────────────────────────────────────────────────
  function init() {
    createContextMenu();
    setTimeout(function() { window.refreshFolderPills(); }, 500);
    // Load chat history on first visit to the chat pane
    setTimeout(function() {
      if (typeof window.loadChatSessions === 'function') window.loadChatSessions();
    }, 800);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.showContextMenu = showContextMenu;
  window.hideContextMenu = hideContextMenu;

})();
