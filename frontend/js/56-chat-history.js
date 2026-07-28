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

  // ── Context Menu ───────────────────────────────────────────────
  let _ctxMenu = null;

  function createContextMenu() {
    if (_ctxMenu) _ctxMenu.remove();
    _ctxMenu = document.createElement('div');
    _ctxMenu.id = 'chat-ctx-menu';
    _ctxMenu.style.cssText = `
      position:fixed; z-index:20000; min-width:200px; max-width:260px;
      background:var(--bg-2); border:1px solid var(--border-hi);
      border-radius:12px; padding:6px; box-shadow:0 16px 48px rgba(0,0,0,.65);
      animation:slideUp .12s ease; backdrop-filter:blur(16px);
      display:none;
    `;
    document.body.appendChild(_ctxMenu);
    // Close on click outside
    document.addEventListener('click', () => hideContextMenu(), { capture: true });
    document.addEventListener('contextmenu', (e) => {
      if (!_ctxMenu.contains(e.target)) hideContextMenu();
    }, { capture: true });
  }

  function showContextMenu(x, y, items) {
    if (!_ctxMenu) createContextMenu();
    _ctxMenu.innerHTML = items.map(item => {
      if (item.separator) return '<div style="height:1px;background:var(--border);margin:4px 8px"></div>';
      const danger = item.danger ? 'color:var(--danger)' : '';
      const icon = item.icon || '';
      return `<div class="ctx-item" data-action="${item.action || ''}" style="
        display:flex; align-items:center; gap:10px; padding:8px 12px; cursor:pointer;
        border-radius:8px; font-size:12.5px; color:var(--text-1); transition:all .1s;
        ${danger}
      " onmouseenter="this.style.background='var(--bg-3)';this.style.color='var(--text-0)'"
         onmouseleave="this.style.background='';this.style.color='${item.danger ? 'var(--danger)' : 'var(--text-1)'}'">
        <span style="font-size:14px;width:18px;text-align:center;flex-shrink:0">${icon}</span>
        <span style="flex:1">${item.label}</span>
        ${item.shortcut ? `<span style="font-size:10px;color:var(--text-3);font-family:monospace">${item.shortcut}</span>` : ''}
      </div>`;
    }).join('');

    // Attach click handlers
    _ctxMenu.querySelectorAll('.ctx-item').forEach((el, i) => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        hideContextMenu();
        if (items[i]?.handler) items[i].handler();
      });
    });

    // Position
    _ctxMenu.style.display = 'block';
    const rect = _ctxMenu.getBoundingClientRect();
    const maxX = window.innerWidth - rect.width - 8;
    const maxY = window.innerHeight - rect.height - 8;
    _ctxMenu.style.left = Math.min(x, maxX) + 'px';
    _ctxMenu.style.top = Math.min(y, maxY) + 'px';
  }

  function hideContextMenu() {
    if (_ctxMenu) _ctxMenu.style.display = 'none';
  }

  // ── Date Grouping ──────────────────────────────────────────────
  function getDateGroup(dateStr) {
    if (!dateStr) return 'Older';
    const now = new Date();
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return 'Older';
    
    const todayStr = now.toISOString().slice(0, 10);
    const dateStr2 = d.toISOString().slice(0, 10);
    if (dateStr2 === todayStr) return 'Today';
    
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    if (dateStr2 === yesterday.toISOString().slice(0, 10)) return 'Yesterday';
    
    const weekAgo = new Date(now);
    weekAgo.setDate(weekAgo.getDate() - 7);
    if (d >= weekAgo) return 'Previous 7 Days';
    
    const monthAgo = new Date(now);
    monthAgo.setMonth(monthAgo.getMonth() - 1);
    if (d >= monthAgo) return 'Previous 30 Days';
    
    return 'Older';
  }

  // ── Enhanced loadChatSessions ──────────────────────────────────
  const origLoadChatSessions = window.loadChatSessions;
  
  window.loadChatSessions = async function(q = '') {
    q = String(q || '').trim();
    if (q !== window._chatLastQuery) {
      window._chatLastQuery = q;
      window._chatCurrentPage = 1;
    }
    const el = document.getElementById('chat-sessions-list');
    if (!el) return;

    try {
      const r = await fetch(`/api/sessions?limit=200&q=${encodeURIComponent(q)}`);
      const data = await r.json();
      let sessions = data.sessions || [];

      // Sync custom folders from session descriptions
      syncFoldersFromSessions(sessions);

      if (!sessions.length) {
        el.innerHTML = renderEmptyState();
        const startBtn = document.getElementById('btn-start-first');
        if (startBtn) startBtn.addEventListener('click', () => window.startNewChatSession());
        return;
      }

      // Apply folder filter
      const folderFilter = window._activeChatFolder || 'All';
      if (folderFilter !== 'All') {
        sessions = sessions.filter(s => {
          const folder = (s.description && s.description !== 'All') ? s.description : 'General';
          return folder === folderFilter;
        });
      }

      // Update folder sort options visibility
      const optFAZ = document.getElementById('opt-sort-folder-az');
      const optFZA = document.getElementById('opt-sort-folder-za');
      if (optFAZ && optFZA) {
        const showFolderSort = (folderFilter === 'All');
        optFAZ.style.display = showFolderSort ? '' : 'none';
        optFZA.style.display = showFolderSort ? '' : 'none';
        if (!showFolderSort && (window._chatSortOrder === 'folder_az' || window._chatSortOrder === 'folder_za')) {
          window._chatSortOrder = 'newest';
          const sortSel = document.getElementById('chat-sort-select');
          if (sortSel) sortSel.value = 'newest';
        }
      }

      // Sort sessions (pinned first always)
      sessions.sort((a, b) => {
        if (a.pinned !== b.pinned) return b.pinned - a.pinned;
        const order = window._chatSortOrder || 'newest';
        const timeA = new Date(a.updated_at || a.created_at || 0).getTime();
        const timeB = new Date(b.updated_at || b.created_at || 0).getTime();
        if (order === 'oldest') return timeA - timeB;
        if (order === 'az') return (a.name || 'Chat').localeCompare(b.name || 'Chat');
        if (order === 'za') return (b.name || 'Chat').localeCompare(a.name || 'Chat');
        if (order === 'folder_az') return (a.description || 'General').localeCompare(b.description || 'General') || (a.name || '').localeCompare(b.name || '');
        if (order === 'folder_za') return (b.description || 'General').localeCompare(a.description || 'General') || (a.name || '').localeCompare(b.name || '');
        return timeB - timeA;
      });

      // Paginate
      const pageSize = window._chatPageSize || 5;
      const totalSessions = sessions.length;
      const totalPages = Math.max(1, Math.ceil(totalSessions / pageSize));
      if (window._chatCurrentPage > totalPages) window._chatCurrentPage = totalPages;
      const curPage = window._chatCurrentPage || 1;
      const startIdx = (curPage - 1) * pageSize;
      const pageSessions = sessions.slice(startIdx, startIdx + pageSize);

      // Update pagination UI
      updatePaginationUI(totalSessions, curPage, totalPages);

      if (!pageSessions.length) {
        el.innerHTML = renderEmptyPageState(totalSessions);
        const hereBtn = document.getElementById('btn-start-here');
        if (hereBtn) hereBtn.addEventListener('click', () => window.startNewChatSession());
        return;
      }

      // Render with date grouping (only when sorting by time and showing all folders)
      const sortOrder = window._chatSortOrder || 'newest';
      const useDateGroups = (sortOrder === 'newest' || sortOrder === 'oldest') && folderFilter === 'All';
      
      el.innerHTML = '';
      
      if (useDateGroups) {
        const groups = {};
        pageSessions.forEach(s => {
          const group = getDateGroup(s.updated_at || s.created_at);
          if (!groups[group]) groups[group] = [];
          groups[group].push(s);
        });
        
        const groupOrder = ['Today', 'Yesterday', 'Previous 7 Days', 'Previous 30 Days', 'Older'];
        groupOrder.forEach(groupName => {
          const items = groups[groupName];
          if (!items || !items.length) return;
          
          const header = document.createElement('div');
          header.style.cssText = 'font-size:10.5px;font-weight:700;color:var(--text-3);padding:8px 4px 4px;letter-spacing:.04em;text-transform:uppercase';
          header.textContent = groupName;
          el.appendChild(header);
          
          items.forEach(s => el.appendChild(renderSessionItem(s)));
        });
      } else {
        pageSessions.forEach(s => el.appendChild(renderSessionItem(s)));
      }
    } catch(e) {
      console.warn('Failed to load chat sessions:', e);
      el.innerHTML = '<div style="color:var(--danger);font-size:12px;text-align:center;padding:20px">Failed to load chats</div>';
    }
  };

  // ── Render Empty State ─────────────────────────────────────────
  function renderEmptyState() {
    return `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:32px 16px;text-align:center">
      <div style="font-size:36px;margin-bottom:12px;opacity:.6">💬</div>
      <div style="font-size:13px;font-weight:700;color:var(--text-1);margin-bottom:4px">No conversations yet</div>
      <div style="font-size:11.5px;color:var(--text-3);margin-bottom:16px">Start a chat to see your history here</div>
      <button id="btn-start-first" class="btn-3d btn-primary btn-sm" style="padding:6px 16px;font-weight:700">＋ Start First Chat</button>
    </div>`;
  }

  function renderEmptyPageState(total) {
    return `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px 16px;text-align:center">
      <div style="font-size:12px;color:var(--text-3);margin-bottom:12px">${total === 0 ? 'No saved conversations yet.' : 'No chats on this page.'}</div>
      <button id="btn-start-here" class="btn-3d btn-primary btn-sm" style="padding:6px 16px;font-weight:700">＋ New Chat</button>
    </div>`;
  }

  // ── Update Pagination UI ───────────────────────────────────────
  function updatePaginationUI(total, curPage, totalPages) {
    const pagEl = document.getElementById('chat-sessions-pagination');
    if (!pagEl) return;
    pagEl.style.display = total > 0 ? 'flex' : 'none';
    const ind = document.getElementById('chat-page-indicator');
    if (ind) ind.textContent = `Page ${curPage} of ${totalPages} (${total} total)`;
    const prevBtn = document.getElementById('chat-page-prev');
    const nextBtn = document.getElementById('chat-page-next');
    if (prevBtn) prevBtn.disabled = (curPage <= 1);
    if (nextBtn) nextBtn.disabled = (curPage >= totalPages);
  }

  // ── Render Single Session Item ─────────────────────────────────
  function renderSessionItem(s) {
    const isCurrent = (s.id === window.S?.sessionId);
    const folder = (s.description && s.description !== 'All') ? s.description : 'General';
    const folderIcon = getFolderIcon(folder);
    const snameSafe = (s.name || 'Chat').slice(0, 256);
    const timeAgo = formatTimeAgo(s.updated_at || s.created_at);

    const itemDiv = document.createElement('div');
    itemDiv.className = `chat-session-item ${isCurrent ? 'active' : ''}`;
    itemDiv.dataset.sessionId = s.id;
    itemDiv.style.cssText = `
      display:flex; flex-direction:column; gap:3px; padding:10px 10px 8px;
      border-radius:10px; cursor:pointer; transition:all .15s;
      background:${isCurrent ? 'var(--accent-glow)' : 'transparent'};
      border:1px solid ${isCurrent ? 'var(--accent)' : 'transparent'};
    `;
    
    // Hover effects
    itemDiv.addEventListener('mouseenter', () => {
      if (!isCurrent) {
        itemDiv.style.background = 'var(--bg-3)';
        itemDiv.style.borderColor = 'var(--border)';
      }
      // Show action buttons
      const actions = itemDiv.querySelector('.session-actions');
      if (actions) actions.style.opacity = '1';
    });
    itemDiv.addEventListener('mouseleave', () => {
      if (!isCurrent) {
        itemDiv.style.background = 'transparent';
        itemDiv.style.borderColor = 'transparent';
      }
      const actions = itemDiv.querySelector('.session-actions');
      if (actions) actions.style.opacity = '0';
    });

    // Click to load
    itemDiv.addEventListener('click', (e) => {
      if (e.target.closest('.session-actions') || e.target.closest('.inline-edit-input')) return;
      window.loadChatSession(s.id);
    });

    // Right-click context menu
    itemDiv.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      e.stopPropagation();
      showSessionContextMenu(e.clientX, e.clientY, s);
    });

    // ── Top row: title + actions ──
    const topRow = document.createElement('div');
    topRow.style.cssText = 'display:flex; align-items:center; justify-content:space-between; gap:4px; min-height:22px';

    // Title (editable on double-click)
    const titleWrap = document.createElement('div');
    titleWrap.style.cssText = 'flex:1; min-width:0; display:flex; align-items:center; gap:4px';
    
    if (s.pinned) {
      const pin = document.createElement('span');
      pin.style.cssText = 'font-size:11px;flex-shrink:0';
      pin.textContent = '📌';
      titleWrap.appendChild(pin);
    }
    
    const titleSpan = document.createElement('span');
    titleSpan.className = 'session-title';
    titleSpan.style.cssText = `
      font-size:12.5px; font-weight:${isCurrent ? '800' : '600'};
      color:var(--text-0); white-space:nowrap; overflow:hidden;
      text-overflow:ellipsis; flex:1; min-width:0;
    `;
    titleSpan.textContent = snameSafe;
    titleSpan.title = snameSafe;
    
    // Double-click to rename inline
    titleSpan.addEventListener('dblclick', (e) => {
      e.preventDefault();
      e.stopPropagation();
      startInlineRename(itemDiv, s, titleSpan);
    });
    
    titleWrap.appendChild(titleSpan);
    topRow.appendChild(titleWrap);

    // Action buttons (visible on hover)
    const btnGroup = document.createElement('div');
    btnGroup.className = 'session-actions';
    btnGroup.style.cssText = 'display:flex; gap:2px; align-items:center; flex-shrink:0; opacity:0; transition:opacity .12s';
    
    // More actions button (3 dots)
    const moreBtn = document.createElement('button');
    moreBtn.title = 'More actions';
    moreBtn.style.cssText = `
      background:none; border:none; color:var(--text-3); font-size:13px;
      cursor:pointer; padding:2px 4px; border-radius:4px; line-height:1;
      transition:all .1s;
    `;
    moreBtn.textContent = '⋯';
    moreBtn.addEventListener('mouseenter', () => { moreBtn.style.background = 'var(--bg-4)'; moreBtn.style.color = 'var(--text-0)'; });
    moreBtn.addEventListener('mouseleave', () => { moreBtn.style.background = 'none'; moreBtn.style.color = 'var(--text-3)'; });
    moreBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      showSessionContextMenu(e.clientX, e.clientY, s);
    });
    btnGroup.appendChild(moreBtn);

    // Delete button
    const delBtn = document.createElement('button');
    delBtn.title = 'Delete chat';
    delBtn.style.cssText = `
      background:none; border:none; color:var(--text-3); font-size:12px;
      cursor:pointer; padding:2px 4px; border-radius:4px; line-height:1;
      transition:all .1s;
    `;
    delBtn.innerHTML = '✕';
    delBtn.addEventListener('mouseenter', () => { delBtn.style.background = 'rgba(232,82,82,.15)'; delBtn.style.color = 'var(--danger)'; });
    delBtn.addEventListener('mouseleave', () => { delBtn.style.background = 'none'; delBtn.style.color = 'var(--text-3)'; });
    delBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      window.deleteChatSession(e, s.id);
    });
    btnGroup.appendChild(delBtn);

    topRow.appendChild(btnGroup);
    itemDiv.appendChild(topRow);

    // ── Bottom row: folder badge + meta ──
    const bottomRow = document.createElement('div');
    bottomRow.style.cssText = 'display:flex; align-items:center; justify-content:space-between; font-size:10.5px; color:var(--text-3); padding-left:2px';

    const folderBadge = document.createElement('span');
    folderBadge.className = 'session-folder-badge';
    folderBadge.style.cssText = `
      display:inline-flex; align-items:center; gap:3px;
      background:var(--bg-2); padding:1px 6px; border-radius:4px;
      border:1px solid var(--border); cursor:pointer;
      transition:all .1s;
    `;
    folderBadge.textContent = `${folderIcon} ${folder}`;
    folderBadge.title = 'Click to change folder';
    folderBadge.addEventListener('mouseenter', () => { folderBadge.style.borderColor = 'var(--accent)'; });
    folderBadge.addEventListener('mouseleave', () => { folderBadge.style.borderColor = 'var(--border)'; });
    folderBadge.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      showFolderPicker(e.clientX, e.clientY, s);
    });
    bottomRow.appendChild(folderBadge);

    const metaSpan = document.createElement('span');
    metaSpan.style.cssText = 'display:flex; align-items:center; gap:6px';
    metaSpan.innerHTML = `<span>${s.message_count || 0} msgs</span><span>·</span><span>${timeAgo}</span>`;
    bottomRow.appendChild(metaSpan);

    itemDiv.appendChild(bottomRow);
    return itemDiv;
  }

  // ── Inline Rename ──────────────────────────────────────────────
  function startInlineRename(itemDiv, session, titleSpan) {
    const currentName = (session.name || 'Chat').slice(0, 256);
    
    const input = document.createElement('input');
    input.type = 'text';
    input.value = currentName;
    input.className = 'inline-edit-input';
    input.style.cssText = `
      flex:1; min-width:0; background:var(--bg-0); border:1px solid var(--accent);
      border-radius:4px; padding:2px 6px; font-size:12.5px; font-weight:600;
      color:var(--text-0); outline:none; font-family:inherit;
    `;
    
    titleSpan.replaceWith(input);
    input.focus();
    input.select();

    const finishRename = async (save) => {
      if (save && input.value.trim() && input.value.trim() !== currentName) {
        try {
          const res = await fetch(`/api/sessions/${encodeURIComponent(session.id)}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: input.value.trim() })
          });
          const j = await res.json();
          if (j.ok) {
            toast('✏️ Chat renamed', 'ok', 1200);
            if (window.S?.sessionId === session.id) window.S.sessionName = input.value.trim();
            window.loadChatSessions();
            return;
          }
        } catch(e) {
          toast('❌ Rename failed', 'err', 2000);
        }
      }
      // Revert
      titleSpan.textContent = currentName;
      input.replaceWith(titleSpan);
    };

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); finishRename(true); }
      if (e.key === 'Escape') { e.preventDefault(); finishRename(false); }
    });
    input.addEventListener('blur', () => finishRename(true));
  }

  // ── Context Menu for Sessions ──────────────────────────────────
  function showSessionContextMenu(x, y, session) {
    const folder = (session.description && session.description !== 'All') ? session.description : 'General';
    
    const items = [
      { icon: '📂', label: 'Open Chat', handler: () => window.loadChatSession(session.id) },
      { separator: true },
      { icon: '✏️', label: 'Rename', shortcut: 'DblClick', handler: () => {
        const el = document.querySelector(`[data-session-id="${session.id}"] .session-title`);
        if (el) startInlineRename(el.closest('.chat-session-item'), session, el);
      }},
      { icon: '📁', label: `Move to Folder…`, handler: () => showFolderPickerAtCenter(session) },
      { icon: session.pinned ? '📌' : '📍', label: session.pinned ? 'Unpin' : 'Pin to Top', handler: () => window.pinChatSession(null, session.id, !session.pinned) },
      { separator: true },
      { icon: '⎇', label: 'Fork / Branch', handler: () => forkSessionQuick(session) },
      { icon: '📋', label: 'Export as Markdown', handler: () => window.exportSession?.(session.id) },
      { icon: '📄', label: 'Export as JSON', handler: () => window.exportSessionJSON?.(session.id) },
      { separator: true },
      { icon: '🗑', label: 'Delete', danger: true, shortcut: 'Del', handler: () => window.deleteChatSession(null, session.id) },
    ];
    
    showContextMenu(x, y, items);
  }

  // ── Folder Picker ──────────────────────────────────────────────
  function showFolderPicker(x, y, session) {
    const folders = getAllFolders();
    const currentFolder = (session.description && session.description !== 'All') ? session.description : 'General';
    
    const items = folders.map(f => ({
      icon: f === currentFolder ? '✓' : getFolderIcon(f),
      label: f,
      handler: () => moveSessionToFolder(session, f)
    }));
    
    items.push({ separator: true });
    items.push({
      icon: '➕', label: 'Create New Folder…',
      handler: () => createNewFolder(session)
    });
    
    showContextMenu(x, y, items);
  }

  function showFolderPickerAtCenter(session) {
    const folders = getAllFolders();
    const currentFolder = (session.description && session.description !== 'All') ? session.description : 'General';
    
    // Use the gmPrompt approach but with a better UX
    const folderList = folders.map(f => `${f === currentFolder ? '✓ ' : ''}${getFolderIcon(f)} ${f}`).join('\n');
    
    if (typeof window.gmPrompt === 'function') {
      window.gmPrompt('Move to Folder', `Current: ${currentFolder}\n\nAvailable folders:\n${folderList}\n\nType a folder name:`, currentFolder).then(newFolder => {
        if (newFolder !== null && newFolder.trim()) {
          moveSessionToFolder(session, newFolder.trim());
        }
      });
    }
  }

  async function moveSessionToFolder(session, folder) {
    try {
      const res = await fetch(`/api/sessions/${encodeURIComponent(session.id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: folder })
      });
      const j = await res.json();
      if (j.ok) {
        // Add folder to custom folders if new
        const folders = getCustomFolders();
        if (!folders.includes(folder)) {
          folders.push(folder);
          saveCustomFolders(folders);
        }
        toast(`📁 Moved to ${folder}`, 'ok', 1200);
        if (window.S?.sessionId === session.id) window.S.sessionFolder = folder;
        window.loadChatSessions();
      }
    } catch(e) {
      toast('❌ Move failed', 'err', 2000);
    }
  }

  async function createNewFolder(session) {
    if (typeof window.gmPrompt !== 'function') return;
    const name = await window.gmPrompt('Create New Folder', 'Enter a name for the new folder:', '');
    if (!name || !name.trim()) return;
    
    const folderName = name.trim();
    const folders = getCustomFolders();
    if (!folders.includes(folderName)) {
      folders.push(folderName);
      saveCustomFolders(folders);
      toast(`📁 Folder "${folderName}" created`, 'ok', 1500);
    }
    
    // Move the session to the new folder
    if (session) {
      await moveSessionToFolder(session, folderName);
    }
  }

  // ── Fork Quick ─────────────────────────────────────────────────
  async function forkSessionQuick(session) {
    const name = `⎇ Fork: ${(session.name || 'Chat').slice(0, 80)}`;
    try {
      const r = await fetch(`/api/sessions/${encodeURIComponent(session.id)}/branch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      });
      const d = await r.json();
      if (d.ok) {
        toast(`⎇ Forked: ${d.name} (${d.messages_copied} msgs)`, 'ok', 2500);
        window.loadChatSessions();
      }
    } catch(e) {
      toast('❌ Fork failed', 'err', 2000);
    }
  }

  // ── Sync Folders from Sessions ─────────────────────────────────
  function syncFoldersFromSessions(sessions) {
    const existing = getCustomFolders();
    let changed = false;
    sessions.forEach(s => {
      const desc = (s.description || '').trim();
      if (desc && desc !== 'All' && !existing.includes(desc)) {
        existing.push(desc);
        changed = true;
      }
    });
    if (changed) saveCustomFolders(existing);
  }

  // ── Refresh Folder Pills ───────────────────────────────────────
  window.refreshFolderPills = function() {
    const container = document.getElementById('chat-folder-pills');
    if (!container) return;
    
    const folders = getAllFolders();
    const activeFolder = window._activeChatFolder || 'All';
    
    container.innerHTML = '';
    
    // "All" pill
    const allBtn = document.createElement('button');
    allBtn.type = 'button';
    allBtn.className = 'tag';
    allBtn.textContent = 'All Chats';
    allBtn.style.cssText = folderPillStyle(activeFolder === 'All');
    allBtn.addEventListener('click', () => window.selectChatFolder('All'));
    container.appendChild(allBtn);
    
    // Folder pills
    folders.forEach(f => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'tag';
      btn.textContent = `${getFolderIcon(f)} ${f}`;
      btn.style.cssText = folderPillStyle(activeFolder === f);
      btn.addEventListener('click', () => window.selectChatFolder(f));
      
      // Right-click to manage folder
      btn.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        showFolderManageMenu(e.clientX, e.clientY, f, folders);
      });
      
      container.appendChild(btn);
    });
    
    // "New Folder" button
    const newBtn = document.createElement('button');
    newBtn.type = 'button';
    newBtn.className = 'tag';
    newBtn.innerHTML = '＋';
    newBtn.title = 'Create new folder';
    newBtn.style.cssText = `
      cursor:pointer; font-weight:700; font-size:12px; padding:3px 8px;
      border-radius:6px; background:var(--bg-2); color:var(--text-2);
      border:1px dashed var(--border); flex-shrink:0; transition:all .1s;
    `;
    newBtn.addEventListener('mouseenter', () => { newBtn.style.borderColor = 'var(--accent)'; newBtn.style.color = 'var(--accent)'; });
    newBtn.addEventListener('mouseleave', () => { newBtn.style.borderColor = 'var(--border)'; newBtn.style.color = 'var(--text-2)'; });
    newBtn.addEventListener('click', async () => {
      if (typeof window.gmPrompt !== 'function') return;
      const name = await window.gmPrompt('Create New Folder', 'Enter a folder name:', '');
      if (name && name.trim()) {
        const folders = getCustomFolders();
        if (!folders.includes(name.trim())) {
          folders.push(name.trim());
          saveCustomFolders(folders);
          toast(`📁 Folder "${name.trim()}" created!`, 'ok', 1500);
        }
      }
    });
    container.appendChild(newBtn);
  };

  function folderPillStyle(isActive) {
    return `
      cursor:pointer; font-weight:${isActive ? '700' : '600'}; font-size:11px;
      padding:3px 8px; border-radius:6px; flex-shrink:0;
      background:${isActive ? 'var(--accent)' : 'var(--bg-2)'};
      color:${isActive ? '#fff' : 'var(--text-1)'};
      border:1px solid ${isActive ? 'var(--accent)' : 'var(--border)'};
      transition:all .12s;
    `;
  }

  // ── Folder Management Menu ─────────────────────────────────────
  function showFolderManageMenu(x, y, folderName, allFolders) {
    const items = [
      { icon: '✏️', label: `Rename "${folderName}"`, handler: () => renameFolder(folderName) },
      { separator: true },
      { icon: '🗑', label: 'Delete Folder', danger: true, handler: () => deleteFolder(folderName, allFolders) },
    ];
    showContextMenu(x, y, items);
  }

  async function renameFolder(oldName) {
    if (typeof window.gmPrompt !== 'function') return;
    const newName = await window.gmPrompt('Rename Folder', `Rename "${oldName}" to:`, oldName);
    if (!newName || !newName.trim() || newName.trim() === oldName) return;
    
    const folders = getCustomFolders();
    const idx = folders.indexOf(oldName);
    if (idx >= 0) folders[idx] = newName.trim();
    else folders.push(newName.trim());
    saveCustomFolders(folders);
    
    // Update all sessions in this folder
    try {
      const r = await fetch('/api/sessions?limit=200');
      const d = await r.json();
      const sessions = (d.sessions || []).filter(s => (s.description || 'General') === oldName);
      for (const s of sessions) {
        await fetch(`/api/sessions/${encodeURIComponent(s.id)}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ description: newName.trim() })
        });
      }
      toast(`📁 Folder renamed to "${newName.trim()}"`, 'ok', 1500);
      if (window._activeChatFolder === oldName) window._activeChatFolder = newName.trim();
      window.loadChatSessions();
    } catch(e) {
      toast('❌ Rename failed', 'err', 2000);
    }
  }

  async function deleteFolder(folderName, allFolders) {
    if (DEFAULT_FOLDERS.includes(folderName)) {
      toast('⚠️ Cannot delete default folders', 'warn', 2000);
      return;
    }
    
    const ok = await window.gmConfirm('Delete Folder', `Delete "${folderName}"? Sessions will be moved to General.`);
    if (!ok) return;
    
    // Move sessions to General
    try {
      const r = await fetch('/api/sessions?limit=200');
      const d = await r.json();
      const sessions = (d.sessions || []).filter(s => (s.description || 'General') === folderName);
      for (const s of sessions) {
        await fetch(`/api/sessions/${encodeURIComponent(s.id)}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ description: 'General' })
        });
      }
    } catch(e) {}
    
    const folders = getCustomFolders().filter(f => f !== folderName);
    saveCustomFolders(folders);
    
    if (window._activeChatFolder === folderName) window._activeChatFolder = 'All';
    toast(`🗑 Folder "${folderName}" deleted`, 'ok', 1500);
    window.loadChatSessions();
  }

  // ── Helpers ────────────────────────────────────────────────────
  function getFolderIcon(folder) {
    const icons = {
      'General': '📁', 'Engineering': '⚙️', 'Research': '🔬',
      'Ideas': '💡', 'Work': '💼', 'Personal': '🏠',
      'Projects': '🎯', 'Archive': '📦'
    };
    return icons[folder] || '📂';
  }

  function formatTimeAgo(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr.slice(5, 16);
    
    const now = new Date();
    const diff = now - d;
    const mins = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);
    
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    if (hours < 24) return `${hours}h ago`;
    if (days < 7) return `${days}d ago`;
    return dateStr.slice(5, 16);
  }

  // ── Override selectChatFolder to also refresh pills ─────────────
  const origSelectFolder = window.selectChatFolder;
  window.selectChatFolder = function(folder) {
    window._activeChatFolder = folder;
    window._chatCurrentPage = 1;
    window.refreshFolderPills();
    window.loadChatSessions();
  };

  // ── Add CSS for the enhanced chat history ──────────────────────
  (function addEnhancedStyles() {
    const s = document.createElement('style');
    s.textContent = `
      /* Chat session item hover */
      .chat-session-item:hover {
        background: var(--bg-3) !important;
      }
      
      /* Context menu items */
      #chat-ctx-menu .ctx-item:hover {
        background: var(--bg-3);
      }
      
      /* Inline rename input */
      .inline-edit-input:focus {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 2px var(--accent-glow) !important;
      }
      
      /* Session actions fade in */
      .chat-session-item:hover .session-actions {
        opacity: 1 !important;
      }
      
      /* Folder badge hover */
      .session-folder-badge:hover {
        border-color: var(--accent) !important;
        background: var(--bg-3) !important;
      }
      
      /* Folder pills smooth transitions */
      #chat-folder-pills button {
        transition: all .12s ease;
      }
      #chat-folder-pills button:hover {
        border-color: var(--accent) !important;
      }
      
      /* Context menu animation */
      @keyframes ctxFadeIn {
        from { opacity: 0; transform: translateY(-4px); }
        to { opacity: 1; transform: translateY(0); }
      }
      #chat-ctx-menu {
        animation: ctxFadeIn .12s ease !important;
      }
    `;
    document.head.appendChild(s);
  })();

  // ── Init ───────────────────────────────────────────────────────
  // Wait for DOM to be ready, then enhance
  function init() {
    createContextMenu();
    // Override folder pills with dynamic ones
    setTimeout(() => {
      window.refreshFolderPills();
    }, 500);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Export key functions
  window.refreshFolderPills = window.refreshFolderPills;
  window.showContextMenu = showContextMenu;
  window.hideContextMenu = hideContextMenu;
  
})();
