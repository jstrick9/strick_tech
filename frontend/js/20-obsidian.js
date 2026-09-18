// Agentic OS — Obsidian Pane
// Extracted from 01-app-core.js for modularity
// ── Obsidian Pane ─────────────────────────────────────────────────
let _notesSearchTimer = null;
let _notesLoadSeq = 0;

async function renderObsidian() {
  const pane = document.getElementById('pane-obsidian');
  if (!pane) return;
  pane.innerHTML = `<div class="section-head"><div><h2>🧿 Obsidian Vault</h2><p>Bi-directional sync with your Obsidian vault → Memory Galaxy</p></div></div>
    <div id="obs-body">${stateFeedback.loadingElement('Loading…')}</div>`;
  try {
    const r = await fetch('/api/obsidian/status');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const s = await r.json();
    renderObsidianBody(s);
  } catch(e) {
    const el = document.getElementById('obs-body');
    if (el) el.innerHTML = stateFeedback.errorElement({ title: 'Couldn’t reach your Obsidian vault', message: humanError(e, {action:'check your Obsidian vault', dataSafe:true}), retry: 'renderObsidian()' });
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
          <button data-act-click="indexVault()" class="btn btn-primary" id="obs-index-btn">📥 Index Vault → Memory Galaxy</button>
          <button data-act-click="createDailyNote()" class="btn btn-ghost">📅 Create Daily Note</button>
          <button data-act-click="exportMemories()" class="btn btn-ghost">📤 Export Memories → Vault</button>
          <div style="display:flex;gap:6px">
            <button data-act-click="startVaultWatch()" class="btn btn-ghost u-97445a8d" id="obs-watch-btn" >👁 Start Auto-Watch</button>
            <button data-act-click="stopVaultWatch()" class="btn-sm" title="Stop watcher" style="color:var(--danger)">■ Stop</button>
          </div>
        </div>
        <div id="obs-status" style="margin-top:10px;font-size:12px;color:var(--text-2)"></div>
      </div>
    </div>
    <div>
      <div class="settings-card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
          <h3 class="u-11696618">📝 Notes <span id="obs-note-count" style="font-size:11px;color:var(--text-3);font-weight:400"></span></h3>
          <button class="btn-sm" data-act-click="loadObsidianNotes()">↻ Refresh</button>
        </div>
        <div style="display:flex;gap:6px;margin-bottom:8px">
          <input id="obs-search" placeholder="Search notes…" data-act-input="searchNotes()" style="flex:1;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 10px;color:var(--text-0);font-size:12px;outline:none">
        </div>
        <div id="obs-notes" style="max-height:260px;overflow-y:auto;display:flex;flex-direction:column;gap:2px">${stateFeedback.loadingElement('Loading…')}</div>
      </div>
      <div class="settings-card u-56f43562" >
        <h3>✏️ Quick Note</h3>
        <input id="obs-note-title" placeholder="Note title…" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 10px;color:var(--text-0);font-size:13px;outline:none;margin-bottom:7px;box-sizing:border-box">
        <textarea id="obs-note-body" placeholder="Content (Markdown)…" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 10px;color:var(--text-0);font-size:12px;outline:none;resize:none;min-height:72px;font-family:monospace;box-sizing:border-box"></textarea>
        <button data-act-click="saveQuickNote()" class="btn btn-primary" style="width:100%;margin-top:7px">💾 Save Note</button>
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
      showToast('Index failed: '+(j.error||'Unknown'), 'err');
    }
  } catch(ex) {
    if (st) st.textContent = '✗ '+ex?.message;
    showToast('Index error: '+ex?.message, 'err');
  } finally {
    if (btn) { btn.disabled=false; btn.textContent='📥 Index Vault → Memory Galaxy'; }
  }
}

async function createDailyNote() {
  try {
    const r = await fetch('/api/obsidian/daily_note', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    if (!r.ok) {
      // Surface the server's reason (e.g. the 409 "already exists" guard)
      // instead of a bare status code — and as an ERROR, not a green ✓.
      const j = await r.json().catch(() => ({}));
      showToast('📅 ' + (j.error || ('Daily note failed: HTTP ' + r.status)), 'err');
      return;
    }
    const j = await r.json();
    if (j.ok) { showToast(`📅 Daily note created: ${j.date}`); loadObsidianNotes(); }
    else showToast('📅 Daily note failed: '+(j.error||'Unknown'), 'err');
  } catch(ex) { showToast('📅 Daily note error: '+ex?.message, 'err'); }
}

async function exportMemories() {
  try {
    const r = await fetch('/api/obsidian/export', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{"limit":50}'});
    if (!r.ok) { showToast('Export failed: HTTP '+r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { showToast(`📤 Exported ${j.memories} memories → ${j.filename}`); loadObsidianNotes(); }
    else showToast('Export failed: '+(j.error||'No memories'), 'err');
  } catch(ex) { showToast('Export error: '+ex?.message, 'err'); }
}

async function startVaultWatch() {
  try {
    const r = await fetch('/api/obsidian/watch/start', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    if (!r.ok) { showToast('Watch failed: HTTP '+r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) {
      showToast('👁 Vault watcher started');
      const btn = document.getElementById('obs-watch-btn');
      if (btn) { btn.textContent='✅ Watching'; btn.style.color='var(--success)'; }
    } else {
      const msg = j.install_cmd ? `${j.error||'Failed'} — Run: ${j.install_cmd}` : (j.error||'Failed');
      showToast('Watch: '+msg, 'err');
    }
  } catch(ex) { showToast('Watch error: '+ex?.message, 'err'); }
}

async function stopVaultWatch() {
  try {
    const r = await fetch('/api/obsidian/watch/stop', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    if (!r.ok) { showToast('Stop failed: HTTP '+r.status, 'err'); return; }
    const j = await r.json();
    showToast(j.ok ? '■ Watcher stopped' : ('Stop failed: '+(j.error||'')), j.ok ? undefined : 'err');
    if (j.ok) {
      const btn = document.getElementById('obs-watch-btn');
      if (btn) { btn.textContent='👁 Start Auto-Watch'; btn.style.color=''; }
    }
  } catch(ex) { showToast('Stop error: '+ex?.message, 'err'); }
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
  // Stale-response guard: searchNotes fires this per query (and refreshes
  // fire it too), and responses can arrive out of order. Without the guard
  // a slow response for an OLD query overwrote the render of a newer one —
  // the list showed results that didn't match the search box (verified
  // live: box "zzz", list = full note list).
  const seq = ++_notesLoadSeq;
  try {
    const r = await fetch(`/api/obsidian/notes?limit=50${q ? '&q='+encodeURIComponent(q) : ''}`);
    if (!r.ok) { if (seq === _notesLoadSeq) el.innerHTML = `<div style="color:var(--danger);font-size:12px">Failed (HTTP ${r.status})</div>`; return; }
    const j = await r.json();
    if (seq !== _notesLoadSeq) return; // superseded by a newer query/refresh
    if (cnt) cnt.textContent = `(${j.count||0})`;
    if (!(j.notes||[]).length) {
      el.innerHTML = `<div style="color:var(--text-3);font-size:12px;padding:8px">No notes${q?' matching "'+escHtml(q)+'"':''}</div>`;
      return;
    }
    el.innerHTML = j.notes.map(n => `
      <div style="display:flex;align-items:center;gap:7px;padding:5px 8px;border-radius:var(--radius-sm);cursor:pointer;transition:background .1s"
           data-hover="bg:var(--bg-3)" data-hover-out="bg:"
           data-act-click="viewNote(${jsArg(n.path)})">
        <span class="u-6cb285c6">${n.folder==='Daily'?'📅':'📄'}</span>
        <div class="u-59eddc67">
          <div style="font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escHtml(n.name)}</div>
          <div style="font-size:10px;color:var(--text-3)">${n.modified}${n.folder?' · '+escHtml(n.folder):''}</div>
        </div>
        <span style="font-size:10px;color:var(--text-3)">${Math.round(n.size/1024*10)/10}K</span>
        <button data-act-click="obsDeleteNote(${jsArg(n.path)})" data-stop="1"
                style="background:none;border:none;color:var(--danger);cursor:pointer;font-size:12px;opacity:.55;padding:3px 4px;min-width:24px;min-height:24px;border-radius:5px" aria-label="Delete note" title="Delete">🗑</button>
      </div>`).join('');
  } catch(ex) {
    if (seq !== _notesLoadSeq) return; // a newer call already rendered
    el.innerHTML = `<div style="color:var(--danger);font-size:12px">Error: ${escHtml(ex?.message||String(ex))}</div>`;
  }
}

function searchNotes() {
  const q = document.getElementById('obs-search')?.value?.trim() || '';
  // Debounced: data-act-input fires on EVERY keystroke, and this used to
  // fetch immediately — "race" alone was 4 requests. 250ms matches
  // specSearch; loadObsidianNotes carries the stale-response guard.
  clearTimeout(_notesSearchTimer);
  _notesSearchTimer = setTimeout(() => loadObsidianNotes(q), 250);
}

async function viewNote(path) {
  try {
    const r = await fetch('/api/obsidian/note?path=' + encodeURIComponent(path));
    if (!r.ok) { showToast('Note not found: HTTP '+r.status, 'err'); return; }
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
            <button aria-label="Close" title="Close" data-close="closest:[style*=fixed]" style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
          </div>
          <div style="padding:14px 16px;overflow-y:auto;flex:1;font-size:12px;line-height:1.7;color:var(--text-1);white-space:pre-wrap;font-family:monospace">${escHtml((j.content||'').slice(0,6000))}${(j.content||'').length>6000?'\n\n[... truncated]':''}</div>
          <div id="obs-note-links" style="padding:6px 16px 0;font-size:11px;color:var(--text-2);line-height:1.5;max-height:56px;overflow-y:auto"></div>
          <div style="padding:10px 16px;border-top:1px solid var(--border);display:flex;gap:7px;align-items:center">
            <button class="btn-sm" data-act-click="navigator.clipboard.writeText(${jsArg(j.content||'')})">📋 Copy</button>
            <button class="btn-sm" style="color:var(--danger)" data-act-click="obsDeleteNote(${jsArg(path)})" data-close="closest:[style*=fixed]">🗑 Delete</button>
            <button class="btn-sm u-6d000617"  data-close="closest:[style*=fixed]">Close</button>
          </div>
        </div>`;
      overlay.onclick = e => { if(e.target===overlay) overlay.remove(); };
      document.body.appendChild(overlay);
      // The wiki-link graph (which notes link here, what this note links to)
      // was a fully-built backend endpoint with no surface anywhere in the
      // UI — users could never see it. Shown in the viewer, where it answers
      // "what references this note?" exactly when you're reading it.
      fetch('/api/obsidian/backlinks?note=' + encodeURIComponent(name.replace(/\.md$/, '')))
        .then(r => r.json())
        .then(b => {
          if (!b.ok) return;
          const box = overlay.querySelector('#obs-note-links');
          if (!box) return;
          const bl = (b.data && b.data.backlinks) || [];
          const lk = (b.data && b.data.links) || [];
          const fmt = (arr) => arr.slice(0, 15).map(x => escHtml(String(x))).join(', ') + (arr.length > 15 ? `, +${arr.length - 15} more` : '');
          if (bl.length) box.innerHTML += `<div style="margin-bottom:2px">← <strong>${bl.length}</strong> backlink${bl.length > 1 ? 's' : ''}: ${fmt(bl)}</div>`;
          if (lk.length) box.innerHTML += `<div>→ <strong>${lk.length}</strong> link${lk.length > 1 ? 's' : ''}: ${fmt(lk)}</div>`;
        })
        .catch(() => {});
    } else {
      showToast('Could not read note: '+(j.error||'Unknown'), 'err');
    }
  } catch(ex) {
    showToast('View error: '+ex?.message, 'err');
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
    if (!r.ok) { showToast('Delete failed: HTTP '+r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { showToast('🗑 Note deleted'); loadObsidianNotes(); }
    else showToast('Delete failed: '+(j.error||'Unknown'), 'err');
  } catch(ex) { showToast('Delete error: '+ex?.message, 'err'); }
}

async function saveQuickNote() {
  const titleEl = document.getElementById('obs-note-title');
  const bodyEl  = document.getElementById('obs-note-body');
  const title   = titleEl?.value?.trim();
  const body    = bodyEl?.value?.trim() || '';
  if (!title) { showToast('⚠️ Enter a note title', 'err'); return; }
  // An all-punctuation title ("!!!") slugifies to an empty stem, which used
  // to POST a junk hidden ".md" file into the vault (the backend rejects it
  // too now — this guard keeps the error friendly and client-side).
  const slug = title.replace(/[^\w\s-]/g,'').trim().replace(/\s+/g,'_');
  if (!slug) { showToast('⚠️ Title needs at least one letter or number', 'err'); return; }
  // Store the note as-typed. This used to escHtml() the title AND body into
  // the markdown file, so a note containing "&", "<", quotes or an emoji
  // sequence was permanently mangled on disk ("Tom & Jerry" →
  // "Tom &amp; Jerry") — and kept re-escaping if re-saved. Escaping belongs
  // to the DISPLAY path (viewNote), which already escapes when rendering.
  const content  = `# ${title}\n\n${body}`;
  const filename = slug + '.md';
  // overwrite:false first: the backend refuses to silently replace an
  // existing note (data-loss guard); a 409 asks the user before re-sending.
  const send = (overwrite) => fetch('/api/obsidian/note', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({path: filename, content, overwrite})
  });
  try {
    let r = await send(false);
    if (r.status === 409) {
      const replace = await gmDanger('Overwrite Note',
        `A note named "${escHtml(title)}" already exists. Replace its content? This cannot be undone.`, 'Overwrite');
      if (!replace) { showToast('Skipped — existing note kept'); return; }
      r = await send(true);
    }
    if (!r.ok) { showToast('Save failed: HTTP '+r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) {
      showToast(`📝 Note saved: ${title}`);
      if (titleEl) titleEl.value = '';
      if (bodyEl)  bodyEl.value  = '';
      loadObsidianNotes();
    } else {
      showToast('Save failed: '+(j.error||'Unknown'), 'err');
    }
  } catch(ex) { showToast('Save error: '+ex?.message, 'err'); }
}
