/**
 * Agentic OS — Chat History Management
 * Folder tree view with icon selection, resizer, no default folders.
 */

(function() {
  'use strict';

  var FOLDER_KEY = 'agentic_os_custom_folders';
  var FOLDER_ICONS_KEY = 'agentic_os_folder_icons';
  var _currentView = 'folders';
  var _expandedFolders = {};
  var _allSessions = [];

  var ICON_OPTIONS = ['📁','📂','⚙️','🔧','🔬','💡','💼','🏠','🎯','📦','🚀','🎨','📊','🧪','🧠','💻','🌐','📝','🎮','🎵','📚','🛒','🏥','🎓','✈️','🏋️','🍳','🎬','📸','🌿','⭐','❤️','🔥','💎','🌟','🦄','🐉','🦊','🐱','🐶'];

  function getCustomFolders() {
    try { var s = _safeLS.get(FOLDER_KEY); if (s) { var p = JSON.parse(s); if (Array.isArray(p)) return p; } } catch(e) {}
    return [];
  }
  function saveCustomFolders(folders) { try { _safeLS.set(FOLDER_KEY, JSON.stringify(folders)); } catch(e) {} }

  function getFolderIcons() {
    try { var s = _safeLS.get(FOLDER_ICONS_KEY); if (s) return JSON.parse(s); } catch(e) {}
    return {};
  }
  function saveFolderIcons(icons) { try { _safeLS.set(FOLDER_ICONS_KEY, JSON.stringify(icons)); } catch(e) {} }

  function getFolderIcon(folder) {
    var icons = getFolderIcons();
    return icons[folder] || '📂';
  }

  function formatTimeAgo(dateStr) {
    if (!dateStr) return '';
    var d = new Date(dateStr); if (isNaN(d.getTime())) return dateStr.slice(5,16);
    var diff = Date.now()-d.getTime(), mins = Math.floor(diff/60000);
    if (mins<1) return 'just now'; if (mins<60) return mins+'m ago';
    var h=Math.floor(diff/3600000); if(h<24) return h+'h ago';
    var dy=Math.floor(diff/86400000); if(dy<7) return dy+'d ago';
    return dateStr.slice(5,16);
  }
  function getDateGroup(ds) {
    if(!ds) return 'Older'; var d=new Date(ds); if(isNaN(d.getTime())) return 'Older';
    var now=new Date(),t=now.toISOString().slice(0,10),ds2=d.toISOString().slice(0,10);
    if(ds2===t) return 'Today'; var y=new Date(now); y.setDate(y.getDate()-1);
    if(ds2===y.toISOString().slice(0,10)) return 'Yesterday';
    var w=new Date(now); w.setDate(w.getDate()-7); if(d>=w) return 'Previous 7 Days';
    var m=new Date(now); m.setMonth(m.getMonth()-1); if(d>=m) return 'Previous 30 Days';
    return 'Older';
  }

  // ── Toggle History Drawer ─────────────────────────────────────
  window.toggleChatHistoryDrawer = function() {
    var dr = document.getElementById('chat-history-drawer');
    var btn = document.getElementById('history-toggle-btn');
    var resizer = document.getElementById('chat-drawer-resizer');
    if (!dr) return;
    var isHidden = dr.style.display === 'none' || dr.style.width === '0px';
    if (isHidden) {
      dr.style.display = 'flex';
      dr.style.width = '280px';
      if (resizer) resizer.style.display = '';
      if (btn) btn.textContent = '📁 Hide History';
    } else {
      dr.style.display = 'none';
      if (resizer) resizer.style.display = 'none';
      if (btn) btn.textContent = '📁 Show History';
    }
  };

  // ── Drawer Resizer ────────────────────────────────────────────
  function initDrawerResizer() {
    var resizer = document.getElementById('chat-drawer-resizer');
    var drawer = document.getElementById('chat-history-drawer');
    if (!resizer || !drawer) return;

    var isResizing = false, startX = 0, startW = 0;

    resizer.addEventListener('mousedown', function(e) {
      isResizing = true;
      startX = e.clientX;
      startW = drawer.getBoundingClientRect().width;
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      resizer.style.background = 'var(--accent)';
    });

    document.addEventListener('mousemove', function(e) {
      if (!isResizing) return;
      var newW = startW + (e.clientX - startX);
      if (newW < 60) { drawer.style.display = 'none'; resizer.style.display = 'none'; }
      else { drawer.style.display = 'flex'; resizer.style.display = ''; drawer.style.width = Math.min(Math.max(newW, 180), 500) + 'px'; }
    });

    document.addEventListener('mouseup', function() {
      if (!isResizing) return;
      isResizing = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      resizer.style.background = '';
      // Update button text based on drawer state
      var btn = document.getElementById('history-toggle-btn');
      if (btn) {
        if (drawer.style.display === 'none') btn.textContent = '📁 Show History';
        else btn.textContent = '📁 Hide History';
      }
    });

    // Hover effect on resizer
    resizer.addEventListener('mouseenter', function() { if (!isResizing) resizer.style.background = 'var(--border-hi)'; });
    resizer.addEventListener('mouseleave', function() { if (!isResizing) resizer.style.background = ''; });
  }

  // ── View Switching ────────────────────────────────────────────
  window.switchChatView = function(view) {
    _currentView = view;
    var fb = document.getElementById('view-folders-btn');
    var db = document.getElementById('view-date-btn');
    var pag = document.getElementById('chat-sessions-pagination');
    if(fb){fb.style.background=view==='folders'?'var(--accent)':'transparent';fb.style.color=view==='folders'?'#fff':'var(--text-2)';}
    if(db){db.style.background=view==='date'?'var(--accent)':'transparent';db.style.color=view==='date'?'#fff':'var(--text-2)';}
    if(pag) pag.style.display = view==='date'?'flex':'none';
    renderChatList();
  };

  // ── Main Load ─────────────────────────────────────────────────
  window.loadChatSessions = async function(q) {
    q = String(q||'').trim();
    var el = document.getElementById('chat-sessions-list');
    if (!el) return;
    try {
      var url = '/api/sessions?limit=200' + (q ? '&q='+encodeURIComponent(q) : '');
      var r = await fetch(url); var data = await r.json();
      _allSessions = data.sessions || [];
      syncFoldersFromSessions(_allSessions);
      renderChatList();
    } catch(e) { console.warn('loadChatSessions error:', e); }
  };

  function renderChatList() {
    var el = document.getElementById('chat-sessions-list');
    if (!el) return;
    if (!_allSessions.length) {
      el.innerHTML = '<div style="display:flex;flex-direction:column;align-items:center;padding:32px 16px;text-align:center">'
        + '<div style="font-size:36px;margin-bottom:12px;opacity:.6">💬</div>'
        + '<div style="font-size:13px;font-weight:700;color:var(--text-1);margin-bottom:4px">No conversations yet</div>'
        + '<div style="font-size:11.5px;color:var(--text-3)">Start a chat to see history here</div></div>';
      return;
    }
    var q = (document.getElementById('chat-sessions-search')?.value||'').trim().toLowerCase();
    var sessions = q ? _allSessions.filter(function(s){return(s.name||'').toLowerCase().includes(q)||(s.description||'').toLowerCase().includes(q);}) : _allSessions;
    if (_currentView === 'date') renderDateView(el, sessions);
    else renderFolderView(el, sessions);
  }

  // ── Folder Tree View ──────────────────────────────────────────
  function renderFolderView(el, sessions) {
    el.innerHTML = '';
    var folderMap = {};
    sessions.forEach(function(s) {
      var f = (s.description && s.description !== 'All' && s.description.trim()) ? s.description.trim() : 'Uncategorized';
      if (!folderMap[f]) folderMap[f] = [];
      folderMap[f].push(s);
    });

    var customFolders = getCustomFolders();
    // Build folder list: custom folders first, then auto-detected from sessions
    var allFolders = [];
    customFolders.forEach(function(f) { if (allFolders.indexOf(f) === -1) allFolders.push(f); });
    Object.keys(folderMap).forEach(function(f) { if (allFolders.indexOf(f) === -1) allFolders.push(f); });

    if (!allFolders.length && !sessions.length) {
      el.innerHTML = '<div style="display:flex;flex-direction:column;align-items:center;padding:32px 16px;text-align:center">'
        + '<div style="font-size:36px;margin-bottom:12px;opacity:.6">📁</div>'
        + '<div style="font-size:13px;font-weight:700;color:var(--text-1);margin-bottom:4px">No folders yet</div>'
        + '<div style="font-size:11.5px;color:var(--text-3);margin-bottom:16px">Click ＋📁 to create your first folder</div></div>';
      return;
    }

    allFolders.forEach(function(folder) {
      var items = folderMap[folder] || [];
      items.sort(function(a,b) { if(a.pinned!==b.pinned) return b.pinned-a.pinned; return new Date(b.updated_at||b.created_at||0)-new Date(a.updated_at||a.created_at||0); });
      var isExpanded = _expandedFolders[folder] !== false;

      var folderDiv = document.createElement('div');
      folderDiv.style.cssText = 'margin-bottom:2px';

      var header = document.createElement('div');
      header.style.cssText = 'display:flex;align-items:center;gap:6px;padding:6px 8px;border-radius:6px;cursor:pointer;transition:background .1s;user-select:none';
      header.addEventListener('mouseenter', function(){header.style.background='var(--bg-3)';});
      header.addEventListener('mouseleave', function(){header.style.background='';});
      header.addEventListener('click', function(){_expandedFolders[folder]=!_expandedFolders[folder];renderChatList();});

      var arrow = document.createElement('span');
      arrow.style.cssText = 'font-size:9px;color:var(--text-3);width:12px;text-align:center;flex-shrink:0';
      arrow.textContent = isExpanded ? '▼' : '▶';
      header.appendChild(arrow);

      var icon = document.createElement('span');
      icon.style.cssText = 'font-size:13px;flex-shrink:0;cursor:pointer';
      icon.textContent = getFolderIcon(folder);
      icon.title = 'Click to change icon';
      icon.addEventListener('click', function(e) { e.stopPropagation(); showIconPicker(e.clientX, e.clientY, folder); });
      header.appendChild(icon);

      var name = document.createElement('span');
      name.style.cssText = 'flex:1;font-size:12px;font-weight:700;color:var(--text-0);white-space:nowrap;overflow:hidden;text-overflow:ellipsis';
      name.textContent = folder;
      name.title = 'Double-click to rename';
      name.addEventListener('dblclick', function(e) { e.stopPropagation(); startFolderRename(folder, name); });
      header.appendChild(name);

      var count = document.createElement('span');
      count.style.cssText = 'font-size:10px;color:var(--text-3);background:var(--bg-3);padding:1px 5px;border-radius:4px;flex-shrink:0';
      count.textContent = items.length;
      header.appendChild(count);

      // Folder actions on hover
      var fActions = document.createElement('div');
      fActions.style.cssText = 'display:flex;gap:2px;flex-shrink:0;opacity:0;transition:opacity .12s';
      header.addEventListener('mouseenter', function(){fActions.style.opacity='1';});
      header.addEventListener('mouseleave', function(){fActions.style.opacity='0';});

      var editBtn = document.createElement('button');
      editBtn.textContent = '✏️'; editBtn.title = 'Rename';
      editBtn.style.cssText = 'background:none;border:none;cursor:pointer;font-size:11px;padding:1px 3px;border-radius:3px;color:var(--text-3);line-height:1';
      editBtn.addEventListener('click', function(e){e.stopPropagation();startFolderRename(folder,name);});
      fActions.appendChild(editBtn);

      if (folder !== 'Uncategorized') {
        var delBtn = document.createElement('button');
        delBtn.textContent = '🗑'; delBtn.title = 'Delete folder (moves chats to Uncategorized)';
        delBtn.style.cssText = 'background:none;border:none;cursor:pointer;font-size:11px;padding:1px 3px;border-radius:3px;color:var(--text-3);line-height:1';
        delBtn.addEventListener('click', function(e){e.stopPropagation();deleteFolder(folder);});
        fActions.appendChild(delBtn);
      }

      header.appendChild(fActions);
      folderDiv.appendChild(header);

      if (isExpanded && items.length) {
        var chatList = document.createElement('div');
        chatList.style.cssText = 'padding-left:20px;display:flex;flex-direction:column;gap:1px';
        items.forEach(function(s){chatList.appendChild(renderChatItem(s));});
        folderDiv.appendChild(chatList);
      }
      el.appendChild(folderDiv);
    });
  }

  // ── Date View ─────────────────────────────────────────────────
  function renderDateView(el, sessions) {
    sessions.sort(function(a,b){if(a.pinned!==b.pinned) return b.pinned-a.pinned; return new Date(b.updated_at||b.created_at||0)-new Date(a.updated_at||a.created_at||0);});
    var pageSize=window._chatPageSize||5, total=sessions.length, totalPages=Math.max(1,Math.ceil(total/pageSize));
    if(window._chatCurrentPage>totalPages) window._chatCurrentPage=totalPages;
    var cur=window._chatCurrentPage||1, start=(cur-1)*pageSize, page=sessions.slice(start,start+pageSize);
    updatePaginationUI(total,cur,totalPages);
    el.innerHTML = '';
    if(!page.length){el.innerHTML='<div style="color:var(--text-3);font-size:12px;text-align:center;padding:20px">No chats</div>';return;}
    var groups={};
    page.forEach(function(s){var g=getDateGroup(s.updated_at||s.created_at);if(!groups[g])groups[g]=[];groups[g].push(s);});
    ['Today','Yesterday','Previous 7 Days','Previous 30 Days','Older'].forEach(function(gn){
      var items=groups[gn]; if(!items||!items.length) return;
      var h=document.createElement('div');h.style.cssText='font-size:10px;font-weight:700;color:var(--text-3);padding:8px 6px 4px;letter-spacing:.04em;text-transform:uppercase';h.textContent=gn;el.appendChild(h);
      items.forEach(function(s){el.appendChild(renderChatItem(s));});
    });
  }

  function updatePaginationUI(total,cur,totalPages){
    var pagEl=document.getElementById('chat-sessions-pagination'); if(!pagEl) return;
    var ind=document.getElementById('chat-page-indicator'); if(ind) ind.textContent='Page '+cur+' of '+totalPages+' ('+total+')';
    var prev=document.getElementById('chat-page-prev'),next=document.getElementById('chat-page-next');
    if(prev) prev.disabled=cur<=1; if(next) next.disabled=cur>=totalPages;
  }

  // ── Chat Item ─────────────────────────────────────────────────
  function renderChatItem(s) {
    var isCurrent = (s.id === (window.S && window.S.sessionId));
    var sname = (s.name || 'Chat').slice(0,256);
    var timeAgo = formatTimeAgo(s.updated_at || s.created_at);

    var div = document.createElement('div');
    div.className = 'chat-session-item' + (isCurrent ? ' active' : '');
    div.dataset.sessionId = s.id;
    div.style.cssText = 'display:flex;align-items:center;gap:6px;padding:6px 8px;border-radius:6px;cursor:pointer;transition:all .12s;background:'+(isCurrent?'var(--accent-glow)':'transparent')+';border:1px solid '+(isCurrent?'var(--accent)':'transparent');
    var actionsDiv;
    div.addEventListener('mouseenter', function(){if(!isCurrent){div.style.background='var(--bg-3)';div.style.borderColor='var(--border)';}if(actionsDiv)actionsDiv.style.opacity='1';});
    div.addEventListener('mouseleave', function(){if(!isCurrent){div.style.background='transparent';div.style.borderColor='transparent';}if(actionsDiv)actionsDiv.style.opacity='0';});
    div.addEventListener('click', function(e){if(e.target.closest('.session-actions'))return;window.loadChatSession(s.id);});
    div.addEventListener('contextmenu', function(e){e.preventDefault();e.stopPropagation();showSessionCtx(e.clientX,e.clientY,s);});

    if(s.pinned){var p=document.createElement('span');p.style.cssText='font-size:10px;flex-shrink:0';p.textContent='📌';div.appendChild(p);}

    var title=document.createElement('span');title.className='session-title';
    title.style.cssText='flex:1;font-size:12px;font-weight:'+(isCurrent?'800':'600')+';color:var(--text-0);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0';
    title.textContent=sname;title.title=sname+' (double-click to rename)';
    title.addEventListener('dblclick',function(e){e.preventDefault();e.stopPropagation();startInlineRename(div,s,title);});
    div.appendChild(title);

    var time=document.createElement('span');time.style.cssText='font-size:10px;color:var(--text-3);flex-shrink:0;white-space:nowrap';time.textContent=timeAgo;div.appendChild(time);

    actionsDiv=document.createElement('div');actionsDiv.className='session-actions';actionsDiv.style.cssText='display:flex;gap:1px;flex-shrink:0;opacity:0;transition:opacity .12s';

    var delBtn=document.createElement('button');delBtn.title='Delete';delBtn.style.cssText='background:none;border:none;color:var(--text-3);font-size:11px;cursor:pointer;padding:1px 3px;border-radius:3px;line-height:1';delBtn.textContent='✕';
    var delC=false,delT=null;
    delBtn.addEventListener('mouseenter',function(){if(!delC)delBtn.style.color='var(--danger)';});
    delBtn.addEventListener('mouseleave',function(){if(!delC)delBtn.style.color='var(--text-3)';});
    delBtn.addEventListener('click',function(e){
      e.preventDefault();e.stopPropagation();
      if(!delC){delC=true;delBtn.textContent='Sure?';delBtn.style.color='var(--danger)';delT=setTimeout(function(){delC=false;delBtn.textContent='✕';delBtn.style.color='var(--text-3)';},3000);}
      else{clearTimeout(delT);fetch('/api/sessions/'+encodeURIComponent(s.id),{method:'DELETE'}).then(function(r){return r.json();}).then(function(j){if(j.ok){toast('🗑 Deleted','ok',1200);if(window.S&&window.S.sessionId===s.id&&window.startNewChatSession)window.startNewChatSession();window.loadChatSessions();}}).catch(function(){toast('❌ Failed','err',2000);});}
    });
    actionsDiv.appendChild(delBtn);

    var moreBtn=document.createElement('button');moreBtn.title='More';moreBtn.style.cssText='background:none;border:none;color:var(--text-3);font-size:12px;cursor:pointer;padding:1px 3px;border-radius:3px;line-height:1';moreBtn.textContent='⋯';
    moreBtn.addEventListener('click',function(e){e.preventDefault();e.stopPropagation();showSessionCtx(e.clientX,e.clientY,s);});
    actionsDiv.appendChild(moreBtn);
    div.appendChild(actionsDiv);
    return div;
  }

  // ── Inline Rename ─────────────────────────────────────────────
  function startInlineRename(itemDiv, session, titleSpan) {
    var cur = (session.name||'Chat').slice(0,256);
    var inp = document.createElement('input'); inp.type='text'; inp.value=cur; inp.className='inline-edit-input';
    inp.style.cssText='flex:1;min-width:0;background:var(--bg-0);border:1px solid var(--accent);border-radius:4px;padding:2px 6px;font-size:12px;font-weight:600;color:var(--text-0);outline:none;font-family:inherit';
    titleSpan.replaceWith(inp); inp.focus(); inp.select();
    var done=false;
    function finish(save){
      if(done)return;done=true;
      if(save&&inp.value.trim()&&inp.value.trim()!==cur){
        fetch('/api/sessions/'+encodeURIComponent(session.id),{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:inp.value.trim()})})
        .then(function(r){return r.json();}).then(function(j){if(j.ok){toast('✏️ Renamed','ok',1200);window.loadChatSessions();return;}revert();}).catch(function(){revert();});
      }else revert();
    }
    function revert(){titleSpan.textContent=cur;if(inp.parentNode)inp.replaceWith(titleSpan);}
    inp.addEventListener('keydown',function(e){if(e.key==='Enter'){e.preventDefault();finish(true);}if(e.key==='Escape'){e.preventDefault();finish(false);}});
    inp.addEventListener('blur',function(){finish(true);});
  }

  // ── Folder Rename (inline) ────────────────────────────────────
  function startFolderRename(oldName, nameSpan) {
    var inp = document.createElement('input');
    inp.type = 'text'; inp.value = oldName;
    inp.style.cssText = 'flex:1;min-width:0;background:var(--bg-0);border:1px solid var(--accent);border-radius:4px;padding:2px 6px;font-size:12px;font-weight:700;color:var(--text-0);outline:none;font-family:inherit';
    nameSpan.replaceWith(inp); inp.focus(); inp.select();
    var done = false;
    function finish(save) {
      if (done) return; done = true;
      var newName = inp.value.trim();
      if (save && newName && newName !== oldName) {
        var folders = getCustomFolders();
        var idx = folders.indexOf(oldName);
        if (idx >= 0) folders[idx] = newName; else folders.push(newName);
        saveCustomFolders(folders);
        var icons = getFolderIcons();
        if (icons[oldName]) { icons[newName] = icons[oldName]; delete icons[oldName]; saveFolderIcons(icons); }
        fetch('/api/sessions?limit=200').then(function(r){return r.json();}).then(function(d){
          var toUpdate = (d.sessions||[]).filter(function(s){return(s.description||'')===oldName;});
          return Promise.all(toUpdate.map(function(s){
            return fetch('/api/sessions/'+encodeURIComponent(s.id),{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({description:newName})});
          }));
        }).then(function(){toast('📁 Renamed to "'+newName+'"','ok',1500);window.loadChatSessions();}).catch(function(){toast('❌ Rename failed','err',2000);revert();});
      } else revert();
    }
    function revert() { nameSpan.textContent = oldName; if (inp.parentNode) inp.replaceWith(nameSpan); }
    inp.addEventListener('keydown', function(e){if(e.key==='Enter'){e.preventDefault();finish(true);}if(e.key==='Escape'){e.preventDefault();finish(false);}});
    inp.addEventListener('blur', function(){finish(true);});
  }

  // ── Icon Picker ───────────────────────────────────────────────
  function showIconPicker(x, y, folder) {
    var icons = getFolderIcons();
    var currentIcon = icons[folder] || '📂';
    var items = ICON_OPTIONS.map(function(ic) {
      return { icon: ic === currentIcon ? '✓' : ic, label: ic === currentIcon ? ic + ' (current)' : '', handler: function() {
        icons[folder] = ic; saveFolderIcons(icons);
        toast('🎨 Icon updated', 'ok', 1000); renderChatList();
      }};
    });
    showContextMenu(x, y, items);
  }

  // ── Delete Folder ─────────────────────────────────────────────
  function deleteFolder(folderName) {
    var confirmItems = [
      { icon: '⚠️', label: 'Delete "' + folderName + '"?', danger: true, handler: function() {
        fetch('/api/sessions?limit=200').then(function(r){return r.json();}).then(function(d){
          var toUpdate = (d.sessions||[]).filter(function(s){return(s.description||'')===folderName;});
          return Promise.all(toUpdate.map(function(s){
            return fetch('/api/sessions/'+encodeURIComponent(s.id),{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({description:''})});
          }));
        }).then(function(){
          var folders = getCustomFolders().filter(function(f){return f!==folderName;});
          saveCustomFolders(folders);
          var icons = getFolderIcons(); delete icons[folderName]; saveFolderIcons(icons);
          toast('🗑 Folder deleted','ok',1500); window.loadChatSessions();
        });
      }},
      { icon: '✕', label: 'Cancel', handler: function() {} },
    ];
    showContextMenu(Math.round(window.innerWidth/2-120), Math.round(window.innerHeight/2-50), confirmItems);
  }

  // ── Context Menu ──────────────────────────────────────────────
  var _ctxMenu=null, _currentItems=[], _ctxInit=false;

  function createContextMenu() {
    if(_ctxMenu) _ctxMenu.remove();
    _ctxMenu = document.createElement('div');
    _ctxMenu.id = 'chat-ctx-menu';
    _ctxMenu.style.cssText = 'position:fixed;z-index:20000;min-width:200px;max-width:280px;background:var(--bg-2);border:1px solid var(--border-hi);border-radius:12px;padding:6px;box-shadow:0 16px 48px rgba(0,0,0,.65);backdrop-filter:blur(16px);display:none';
    document.body.appendChild(_ctxMenu);
    _ctxMenu.addEventListener('click', function(e){
      var el=e.target.closest('.ctx-item'); if(!el) return;
      e.preventDefault();e.stopPropagation();
      var idx=parseInt(el.dataset.idx,10);
      if(isNaN(idx)||idx<0||idx>=_currentItems.length) return;
      var handler=_currentItems[idx]&&_currentItems[idx].handler;
      hideContextMenu();
      if(typeof handler==='function'){try{handler();}catch(err){console.warn('[ctx]',err);}}
    });
    if(!_ctxInit){
      document.addEventListener('mousedown',function(e){if(_ctxMenu&&_ctxMenu.style.display!=='none'&&!_ctxMenu.contains(e.target))hideContextMenu();});
      document.addEventListener('contextmenu',function(e){if(_ctxMenu&&_ctxMenu.style.display!=='none'&&!_ctxMenu.contains(e.target))hideContextMenu();});
      document.addEventListener('keydown',function(e){if(e.key==='Escape')hideContextMenu();});
      _ctxInit=true;
    }
  }

  function showContextMenu(x,y,items){
    if(!_ctxMenu) createContextMenu();
    _currentItems=items||[];
    var html='';
    for(var i=0;i<_currentItems.length;i++){
      var item=_currentItems[i];
      if(item.separator){html+='<div style="height:1px;background:var(--border);margin:4px 8px"></div>';continue;}
      var ds=item.danger?'color:var(--danger)':'';
      html+='<div class="ctx-item" data-idx="'+i+'" style="display:flex;align-items:center;gap:10px;padding:8px 12px;cursor:pointer;border-radius:8px;font-size:12.5px;color:var(--text-1);transition:background .1s;'+ds+'">'
        +'<span style="font-size:14px;width:18px;text-align:center;flex-shrink:0">'+(item.icon||'')+'</span>'
        +'<span style="flex:1">'+(item.label||'')+'</span>'
        +(item.shortcut?'<span style="font-size:10px;color:var(--text-3);font-family:monospace">'+item.shortcut+'</span>':'')
        +'</div>';
    }
    _ctxMenu.innerHTML=html;
    _ctxMenu.querySelectorAll('.ctx-item').forEach(function(el){
      var isD=el.style.color==='var(--danger)';
      el.addEventListener('mouseenter',function(){el.style.background='var(--bg-3)';el.style.color='var(--text-0)';});
      el.addEventListener('mouseleave',function(){el.style.background='';el.style.color=isD?'var(--danger)':'var(--text-1)';});
    });
    _ctxMenu.style.display='block';
    var rect=_ctxMenu.getBoundingClientRect();
    _ctxMenu.style.left=Math.max(0,Math.min(x,window.innerWidth-rect.width-8))+'px';
    _ctxMenu.style.top=Math.max(0,Math.min(y,window.innerHeight-rect.height-8))+'px';
  }

  function hideContextMenu(){if(_ctxMenu) _ctxMenu.style.display='none';}

  // ── Session Context Menu ──────────────────────────────────────
  function showSessionCtx(x,y,session){
    var items=[
      {icon:'📂',label:'Open Chat',handler:function(){window.loadChatSession(session.id);}},
      {separator:true},
      {icon:'✏️',label:'Rename',shortcut:'DblClick',handler:function(){var el=document.querySelector('[data-session-id="'+session.id+'"] .session-title');if(el)startInlineRename(el.closest('.chat-session-item'),session,el);}},
      {icon:'📁',label:'Move to Folder…',handler:function(){showFolderPickerMenu(session);}},
      {icon:session.pinned?'📌':'📍',label:session.pinned?'Unpin':'Pin to Top',handler:function(){window.pinChatSession(null,session.id,!session.pinned);}},
      {separator:true},
      {icon:'⎇',label:'Fork / Branch',handler:function(){forkSessionQuick(session);}},
      {icon:'📋',label:'Export as Markdown',handler:function(){downloadExport(session.id,'markdown');}},
      {icon:'📄',label:'Export as JSON',handler:function(){downloadExport(session.id,'json');}},
      {separator:true},
      {icon:'🗑',label:'Delete',danger:true,handler:function(){
        showContextMenu(Math.round(window.innerWidth/2-120),Math.round(window.innerHeight/2-50),[
          {icon:'⚠️',label:'Confirm Delete?',danger:true,handler:function(){
            fetch('/api/sessions/'+encodeURIComponent(session.id),{method:'DELETE'}).then(function(r){return r.json();}).then(function(j){
              if(j.ok){toast('🗑 Deleted','ok',1200);if(window.S&&window.S.sessionId===session.id&&window.startNewChatSession)window.startNewChatSession();window.loadChatSessions();}
            });
          }},
          {icon:'✕',label:'Cancel',handler:function(){}},
        ]);
      }},
    ];
    showContextMenu(x,y,items);
  }

  // ── Folder Picker ─────────────────────────────────────────────
  function showFolderPickerMenu(session){
    var folders=getCustomFolders();
    var cur=(session.description&&session.description!=='All'&&session.description.trim())?session.description.trim():'Uncategorized';
    var items=folders.map(function(f){return{icon:f===cur?'✓':getFolderIcon(f),label:f,handler:function(){moveSessionToFolder(session,f);}};});
    items.push({separator:true});
    items.push({icon:'➕',label:'Create New Folder…',handler:function(){showNewFolderForm(session);}});
    showContextMenu(Math.round(window.innerWidth/2-120),Math.round(window.innerHeight/2-100),items);
  }

  function moveSessionToFolder(session,folder){
    fetch('/api/sessions/'+encodeURIComponent(session.id),{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({description:folder})})
    .then(function(r){return r.json();}).then(function(j){
      if(j.ok){var f=getCustomFolders();if(f.indexOf(folder)===-1){f.push(folder);saveCustomFolders(f);}toast('📁 Moved to '+folder,'ok',1200);window.loadChatSessions();}
    }).catch(function(){toast('❌ Failed','err',2000);});
  }

  // ── New Folder Form (inline) ──────────────────────────────────
  function showNewFolderForm(session) {
    if (!_ctxMenu) createContextMenu();
    var selectedIcon = '📁';
    _ctxMenu.innerHTML = '<div style="padding:8px">'
      + '<div style="font-size:12px;font-weight:700;color:var(--text-0);margin-bottom:8px">New Folder</div>'
      + '<input id="ctx-new-folder-name" type="text" placeholder="Folder name" style="width:100%;background:var(--bg-0);border:1px solid var(--border);border-radius:6px;padding:6px 10px;color:var(--text-0);font-size:12px;outline:none;font-family:inherit;margin-bottom:8px">'
      + '<div style="font-size:11px;color:var(--text-3);margin-bottom:6px">Choose an icon:</div>'
      + '<div id="ctx-icon-grid" style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:10px">'
      + ICON_OPTIONS.map(function(ic,i){
        return '<button type="button" class="ctx-icon-btn" data-icon="'+ic+'" style="background:'+(ic==='📁'?'var(--accent-glow)':'var(--bg-3)')+';border:1px solid '+(ic==='📁'?'var(--accent)':'var(--border)')+';border-radius:6px;padding:4px 6px;cursor:pointer;font-size:14px;transition:all .1s">'+ic+'</button>';
      }).join('')
      + '</div>'
      + '<button id="ctx-create-folder-btn" type="button" style="width:100%;padding:6px 12px;background:var(--accent);color:#fff;border:none;border-radius:6px;font-size:12px;font-weight:700;cursor:pointer">Create Folder</button>'
      + '</div>';
    _ctxMenu.style.display = 'block';
    _ctxMenu.style.left = Math.round(window.innerWidth/2-120)+'px';
    _ctxMenu.style.top = Math.round(window.innerHeight/2-150)+'px';

    var nameInput = document.getElementById('ctx-new-folder-name');
    if (nameInput) nameInput.focus();

    _ctxMenu.querySelectorAll('.ctx-icon-btn').forEach(function(btn) {
      btn.addEventListener('click', function() {
        _ctxMenu.querySelectorAll('.ctx-icon-btn').forEach(function(b){b.style.background='var(--bg-3)';b.style.borderColor='var(--border)';});
        btn.style.background = 'var(--accent-glow)'; btn.style.borderColor = 'var(--accent)';
        selectedIcon = btn.dataset.icon;
      });
    });

    var createBtn = document.getElementById('ctx-create-folder-btn');
    if (createBtn) {
      createBtn.addEventListener('click', function() {
        var name = nameInput ? nameInput.value.trim() : '';
        if (!name) { toast('⚠️ Enter a folder name', 'warn', 1500); return; }
        var folders = getCustomFolders();
        if (folders.indexOf(name) !== -1) { toast('⚠️ Folder already exists', 'warn', 1500); return; }
        folders.push(name); saveCustomFolders(folders);
        var icons = getFolderIcons(); icons[name] = selectedIcon; saveFolderIcons(icons);
        toast('📁 Folder "' + name + '" created!', 'ok', 1500);
        hideContextMenu();
        if (session) moveSessionToFolder(session, name);
        else window.loadChatSessions();
      });
    }

    if (nameInput) {
      nameInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); var btn = document.getElementById('ctx-create-folder-btn'); if (btn) btn.click(); }
        if (e.key === 'Escape') { hideContextMenu(); }
      });
    }
  }

  // ── Fork ──────────────────────────────────────────────────────
  function forkSessionQuick(session){
    var name='⎇ Fork: '+(session.name||'Chat').slice(0,80);
    var origFolder=(session.description&&session.description!=='All'&&session.description.trim())?session.description.trim():'';
    fetch('/api/sessions/'+encodeURIComponent(session.id)+'/branch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})})
    .then(function(r){return r.json();}).then(function(d){
      if(!d.ok){toast('❌ Fork failed','err',2000);return;}
      return fetch('/api/sessions/'+encodeURIComponent(d.id),{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({description:origFolder})})
      .then(function(){toast('⎇ Forked: '+d.name+' ('+d.messages_copied+' msgs)','ok',2500);window.loadChatSessions();});
    }).catch(function(){toast('❌ Fork failed','err',2000);});
  }

  // ── Export ─────────────────────────────────────────────────────
  function downloadExport(sessionId,fmt){
    var label=fmt==='json'?'JSON':'Markdown';
    toast('📋 Downloading '+label+'…','ok',2000);
    var a=document.createElement('a');
    a.href='/api/sessions/'+encodeURIComponent(sessionId)+'/export?fmt='+fmt;
    a.download='export'+(fmt==='json'?'.json':'.md');
    document.body.appendChild(a);a.click();a.remove();
  }

  function syncFoldersFromSessions(sessions){
    var existing=getCustomFolders();var changed=false;
    sessions.forEach(function(s){var d=(s.description||'').trim();if(d&&d!=='All'&&d!=='Uncategorized'&&existing.indexOf(d)===-1){/* auto-detected folders show in tree but not saved as custom */}});
  }

  // ── Init ──────────────────────────────────────────────────────
  function init() {
    createContextMenu();
    initDrawerResizer();

    var newFolderBtn = document.getElementById('new-folder-btn');
    if (newFolderBtn) {
      newFolderBtn.addEventListener('click', function(e) {
        e.preventDefault();
        showNewFolderForm(null);
      });
    }

    var settingsBtn = document.getElementById('folder-settings-btn');
    if (settingsBtn) {
      settingsBtn.addEventListener('click', function(e) {
        e.preventDefault();
        showFolderSettingsMenu(e.clientX, e.clientY);
      });
    }

    setTimeout(function() { if (typeof window.loadChatSessions === 'function') window.loadChatSessions(); }, 800);
  }

  // ── Folder Settings Menu ───────────────────────────────────────
  function showFolderSettingsMenu(x, y) {
    var folders = getCustomFolders();
    var items = [
      { icon: '➕', label: 'Create New Folder', handler: function() { showNewFolderForm(null); } },
    ];
    if (folders.length) {
      items.push({ separator: true });
      folders.forEach(function(f) {
        items.push({
          icon: getFolderIcon(f),
          label: f,
          handler: function() {
            var subItems = [
              { icon: '✏️', label: 'Rename "' + f + '"', handler: function() {
                var newName = window.prompt('Rename "' + f + '" to:', f);
                if (newName && newName.trim() && newName.trim() !== f) {
                  var fldrs = getCustomFolders(); var idx = fldrs.indexOf(f);
                  if (idx >= 0) fldrs[idx] = newName.trim(); saveCustomFolders(fldrs);
                  var icons = getFolderIcons(); if (icons[f]) { icons[newName.trim()] = icons[f]; delete icons[f]; saveFolderIcons(icons); }
                  fetch('/api/sessions?limit=200').then(function(r){return r.json();}).then(function(d){
                    var toUpdate = (d.sessions||[]).filter(function(s){return(s.description||'')===f;});
                    return Promise.all(toUpdate.map(function(s){
                      return fetch('/api/sessions/'+encodeURIComponent(s.id),{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({description:newName.trim()})});
                    }));
                  }).then(function(){toast('📁 Renamed','ok',1500);window.loadChatSessions();});
                }
              }},
              { icon: '🎨', label: 'Change Icon', handler: function() { showIconPicker(Math.round(window.innerWidth/2), Math.round(window.innerHeight/2), f); } },
              { separator: true },
              { icon: '🗑', label: 'Delete Folder', danger: true, handler: function() { deleteFolder(f); } },
            ];
            showContextMenu(x, y, subItems);
          }
        });
      });
    }
    showContextMenu(x, y, items);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  window.selectChatFolder = function() { window.loadChatSessions(); };
  window.filterChatSessions = function(val) {
    if (window._chatSearchTimeout) clearTimeout(window._chatSearchTimeout);
    window._chatSearchTimeout = setTimeout(function(){window.loadChatSessions(val.trim());},250);
  };

})();
