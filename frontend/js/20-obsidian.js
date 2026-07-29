// Agentic OS — Obsidian Pane
// Extracted from 01-app-core.js for modularity
// ── Obsidian Pane ─────────────────────────────────────────────────
async function renderObsidian() {
  const pane = document.getElementById('pane-obsidian');
  if (!pane) return;
  pane.innerHTML = `<div class="section-head"><div><h2>🧿 Obsidian Vault</h2><p>Bi-directional sync with your Obsidian vault → Memory Galaxy</p></div></div>
    <div id="obs-body"><div style="color:var(--text-2);font-size:13px">Loading…</div></div>`;
  try {
    const r = await fetch('/api/obsidian/status');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const s = await r.json();
    renderObsidianBody(s);
  } catch(e) {
    const el = document.getElementById('obs-body');
    if (el) el.innerHTML = `<div style="color:var(--danger)">Error loading Obsidian status: ${escHtml(e?.message||String(e))}<br><button class="btn-sm" onclick="renderObsidian()" style="margin-top:8px">↻ Retry</button></div>`;
  }
}

function renderObsidianBody(s) {
  const el = document.getElementById('obs-body');
  if (!el) return;
  el.innerHTML = `<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
    <div>
      <div class="settings-card">
        <h3>${s.connected ? '✅ Vault Connected' : '🧠 Brain / Vault'}</h3>
        <p style="font-size:12px;color:var(--text-2);margin-bottom:8px">
          ${s.connected
            ? `Path: <code style="font-size:11px;background:var(--bg-0);padding:2px 6px;border-radius:4px">${escHtml(s.vault_path||'')}</code>`
            : 'Using built-in <strong>brain/</strong> folder. Set <code>OBSIDIAN_VAULT_PATH</code> in .env for full Obsidian.'}
        </p>
        <div style="font-size:12px;margin-bottom:10px;color:var(--text-2)">
          📁 ${s.note_count||0} notes · ${s.size_mb||0}MB
          ${s.note_dir ? `<div style="font-size:10px;color:var(--text-3)">Notes: ${escHtml(s.note_dir)}</div>` : ''}
        </div>
        ${!s.connected ? `<div style="background:var(--bg-1);border-radius:var(--radius-sm);padding:10px;font-size:11px;color:var(--text-2);margin-bottom:10px;line-height:1.7">
          Set <code>OBSIDIAN_VAULT_PATH=/path/to/MyVault</code> in .env and restart.
        </div>` : ''}
        <div style="display:flex;flex-direction:column;gap:7px">
          <button onclick="indexVault()" class="btn btn-primary" id="obs-index-btn">📥 Index Vault → Memory Galaxy</button>
          <button onclick="createDailyNote()" class="btn btn-ghost">📅 Create Daily Note</button>
          <button onclick="exportMemories()" class="btn btn-ghost">📤 Export Memories → Vault</button>
          <div style="display:flex;gap:6px">
            <button onclick="startVaultWatch()" class="btn btn-ghost" id="obs-watch-btn" style="flex:1">👁 Start Auto-Watch</button>
            <button onclick="stopVaultWatch()" class="btn-sm" title="Stop watcher" style="color:var(--danger)">■ Stop</button>
          </div>
        </div>
        <div id="obs-status" style="margin-top:10px;font-size:12px;color:var(--text-2)"></div>
      </div>
    </div>
    <div>
      <div class="settings-card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
          <h3 style="margin:0">📝 Notes <span id="obs-note-count" style="font-size:11px;color:var(--text-3);font-weight:400"></span></h3>
          <button class="btn-sm" onclick="loadObsidianNotes()">↻ Refresh</button>
        </div>
        <div style="display:flex;gap:6px;margin-bottom:8px">
          <input id="obs-search" placeholder="Search notes…" oninput="searchNotes()" style="flex:1;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 10px;color:var(--text-0);font-size:12px;outline:none">
        </div>
        <div id="obs-notes" style="max-height:260px;overflow-y:auto;display:flex;flex-direction:column;gap:2px">Loading…</div>
      </div>
      <div class="settings-card" style="margin-top:12px">
        <h3>✏️ Quick Note</h3>
        <input id="obs-note-title" placeholder="Note title…" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 10px;color:var(--text-0);font-size:13px;outline:none;margin-bottom:7px;box-sizing:border-box">
        <textarea id="obs-note-body" placeholder="Content (Markdown)…" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 10px;color:var(--text-0);font-size:12px;outline:none;resize:none;min-height:72px;font-family:monospace;box-sizing:border-box"></textarea>
        <button onclick="saveQuickNote()" class="btn btn-primary" style="width:100%;margin-top:7px">💾 Save Note</button>
      </div>
    </div>
  </div>`;
  loadObsidianNotes();
  obsCheckWatchStatus();
}

async function indexVault() {
  const st  = document.getElementById('obs-status');
  const btn = document.getElementById('obs-index-btn');
  if (st) st.textContent = '⏳ Indexing…';
  if (btn) { btn.disabled=true; btn.textContent='⏳ Indexing…'; }
  try {
    const r = await fetch('/api/obsidian/index', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{"max_notes":500}'});
    if (!r.ok) { if(st) st.textContent='✗ HTTP '+r.status; return; }
    const j = await r.json();
    if (j.ok) {
      if (st) st.innerHTML = `✅ Indexed <strong>${j.indexed}</strong> · Skipped ${j.skipped} · Errors ${j.errors}`;
      showToast(`🧿 Vault indexed: ${j.indexed} notes added to Memory Galaxy`);
      loadObsidianNotes();
    } else {
      if (st) st.textContent = '✗ '+(j.error||'failed');
      showToast('Index failed: '+(j.error||'Unknown'));
    }
  } catch(ex) {
    if (st) st.textContent = '✗ '+ex?.message;
    showToast('Index error: '+ex?.message);
  } finally {
    if (btn) { btn.disabled=false; btn.textContent='📥 Index Vault → Memory Galaxy'; }
  }
}

async function createDailyNote() {
  try {
    const r = await fetch('/api/obsidian/daily_note', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    if (!r.ok) { showToast('Daily note failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) { showToast(`📅 Daily note created: ${j.date}`); loadObsidianNotes(); }
    else showToast('Daily note failed: '+(j.error||'Unknown'));
  } catch(ex) { showToast('Daily note error: '+ex?.message); }
}

async function exportMemories() {
  try {
    const r = await fetch('/api/obsidian/export', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{"limit":50}'});
    if (!r.ok) { showToast('Export failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) { showToast(`📤 Exported ${j.memories} memories → ${j.filename}`); loadObsidianNotes(); }
    else showToast('Export failed: '+(j.error||'No memories'));
  } catch(ex) { showToast('Export error: '+ex?.message); }
}

async function startVaultWatch() {
  try {
    const r = await fetch('/api/obsidian/watch/start', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    if (!r.ok) { showToast('Watch failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) {
      showToast('👁 Vault watcher started');
      const btn = document.getElementById('obs-watch-btn');
      if (btn) { btn.textContent='✅ Watching'; btn.style.color='var(--success)'; }
    } else {
      const msg = j.install_cmd ? `${j.error||'Failed'} — Run: ${j.install_cmd}` : (j.error||'Failed');
      showToast('Watch: '+msg);
    }
  } catch(ex) { showToast('Watch error: '+ex?.message); }
}

async function stopVaultWatch() {
  try {
    const r = await fetch('/api/obsidian/watch/stop', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    if (!r.ok) { showToast('Stop failed: HTTP '+r.status); return; }
    const j = await r.json();
    showToast(j.ok ? '■ Watcher stopped' : 'Stop failed: '+(j.error||''));
    if (j.ok) {
      const btn = document.getElementById('obs-watch-btn');
      if (btn) { btn.textContent='👁 Start Auto-Watch'; btn.style.color=''; }
    }
  } catch(ex) { showToast('Stop error: '+ex?.message); }
}

async function obsCheckWatchStatus() {
  try {
    const r = await fetch('/api/obsidian/watch/status');
    if (!r.ok) return;
    const j = await r.json();
    const btn = document.getElementById('obs-watch-btn');
    if (btn) {
      btn.textContent = j.running ? '✅ Watching' : '👁 Start Auto-Watch';
      btn.style.color = j.running ? 'var(--success)' : '';
    }
  } catch(e) {}
}

async function loadObsidianNotes(q='') {
  const el  = document.getElementById('obs-notes');
  const cnt = document.getElementById('obs-note-count');
  if (!el) return;
  try {
    const r = await fetch(`/api/obsidian/notes?limit=50${q ? '&q='+encodeURIComponent(q) : ''}`);
    if (!r.ok) { el.innerHTML = `<div style="color:var(--danger);font-size:12px">Failed (HTTP ${r.status})</div>`; return; }
    const j = await r.json();
    if (cnt) cnt.textContent = `(${j.count||0})`;
    if (!(j.notes||[]).length) {
      el.innerHTML = `<div style="color:var(--text-3);font-size:12px;padding:8px">No notes${q?' matching "'+escHtml(q)+'"':''}</div>`;
      return;
    }
    el.innerHTML = j.notes.map(n => `
      <div style="display:flex;align-items:center;gap:7px;padding:5px 8px;border-radius:var(--radius-sm);cursor:pointer;transition:background .1s"
           onmouseover="this.style.background='var(--bg-3)'" onmouseout="this.style.background=''"
           onclick="viewNote(${JSON.stringify(n.path)})">
        <span style="font-size:12px">${n.folder==='Daily'?'📅':'📄'}</span>
        <div style="flex:1;min-width:0">
          <div style="font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escHtml(n.name)}</div>
          <div style="font-size:10px;color:var(--text-3)">${n.modified}${n.folder?' · '+escHtml(n.folder):''}</div>
        </div>
        <span style="font-size:10px;color:var(--text-3)">${Math.round(n.size/1024*10)/10}K</span>
        <button onclick="event.stopPropagation();obsDeleteNote(${JSON.stringify(n.path)})"
                style="background:none;border:none;color:var(--danger);cursor:pointer;font-size:11px;opacity:.5;padding:0 2px" title="Delete">🗑</button>
      </div>`).join('');
  } catch(ex) {
    el.innerHTML = `<div style="color:var(--danger);font-size:12px">Error: ${escHtml(ex?.message||String(ex))}</div>`;
  }
}

function searchNotes() {
  const q = document.getElementById('obs-search')?.value?.trim() || '';
  loadObsidianNotes(q);
}

async function viewNote(path) {
  try {
    const r = await fetch('/api/obsidian/note?path=' + encodeURIComponent(path));
    if (!r.ok) { showToast('Note not found: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) {
      const name = path.split('/').pop();
      const overlay = document.createElement('div');
      overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
      overlay.innerHTML = `
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:14px;max-width:680px;width:100%;max-height:82vh;display:flex;flex-direction:column">
          <div style="display:flex;align-items:center;padding:12px 16px;border-bottom:1px solid var(--border);gap:8px">
            <span style="font-weight:700;color:var(--text-0);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">📄 ${escHtml(name)}</span>
            <span style="font-size:10px;color:var(--text-3)">${j.size||0}B · ${j.modified||''}</span>
            <button onclick="this.closest('[style*=fixed]').remove()" style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
          </div>
          <div style="padding:14px 16px;overflow-y:auto;flex:1;font-size:12px;line-height:1.7;color:var(--text-1);white-space:pre-wrap;font-family:monospace">${escHtml((j.content||'').slice(0,6000))}${(j.content||'').length>6000?'\n\n[... truncated]':''}</div>
          <div style="padding:10px 16px;border-top:1px solid var(--border);display:flex;gap:7px;align-items:center">
            <button class="btn-sm" onclick="navigator.clipboard.writeText(${JSON.stringify(j.content||'')})">📋 Copy</button>
            <button class="btn-sm" style="color:var(--danger)" onclick="obsDeleteNote(${JSON.stringify(path)});this.closest('[style*=fixed]').remove()">🗑 Delete</button>
            <button class="btn-sm" style="margin-left:auto" onclick="this.closest('[style*=fixed]').remove()">Close</button>
          </div>
        </div>`;
      overlay.onclick = e => { if(e.target===overlay) overlay.remove(); };
      document.body.appendChild(overlay);
    } else {
      showToast('Could not read note: '+(j.error||'Unknown'));
    }
  } catch(ex) {
    showToast('View error: '+ex?.message);
  }
}

async function obsDeleteNote(path) {
  const ok = await gmDanger('Delete Note', `Delete "${escHtml(path.split('/').pop())}"? This cannot be undone.`);
  if (!ok) return;
  try {
    const r = await fetch('/api/obsidian/note', {
      method:'DELETE', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({path})
    });
    if (!r.ok) { showToast('Delete failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) { showToast('🗑 Note deleted'); loadObsidianNotes(); }
    else showToast('Delete failed: '+(j.error||'Unknown'));
  } catch(ex) { showToast('Delete error: '+ex?.message); }
}

async function saveQuickNote() {
  const titleEl = document.getElementById('obs-note-title');
  const bodyEl  = document.getElementById('obs-note-body');
  const title   = titleEl?.value?.trim();
  const body    = bodyEl?.value?.trim() || '';
  if (!title) { showToast('⚠️ Enter a note title'); return; }
  const content  = `# ${escHtml(title)}\n\n${body}`;
  const filename = title.replace(/[^\w\s-]/g,'').trim().replace(/\s+/g,'_') + '.md';
  try {
    const r = await fetch('/api/obsidian/note', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({path: filename, content})
    });
    if (!r.ok) { showToast('Save failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) {
      showToast(`📝 Note saved: ${title}`);
      if (titleEl) titleEl.value = '';
      if (bodyEl)  bodyEl.value  = '';
      loadObsidianNotes();
    } else {
      showToast('Save failed: '+(j.error||'Unknown'));
    }
  } catch(ex) { showToast('Save error: '+ex?.message); }
}
