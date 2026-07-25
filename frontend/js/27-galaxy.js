// Agentic OS — Galaxy
// Extracted from 01-app-core.js for modularity
// ── Galaxy ────────────────────────────────────────────────────────
let gxGraph = null, gxInited = false;
async function loadGalaxyLibrary(src) {
  // Monaco installs a global AMD `define`. The 3D libraries are browser UMD
  // bundles; when they see that AMD loader they issue an anonymous define call
  // and fail instead of exposing their browser global. Load them explicitly as
  // browser scripts, then restore Monaco immediately.
  const amdDefine = window.define;
  const amdRequire = window.require;
  try {
    window.define = undefined;
    window.require = undefined;
    await loadScript(src);
  } finally {
    window.define = amdDefine;
    window.require = amdRequire;
  }
}

async function initGalaxy() {
  if (gxInited) { refreshGalaxy(); gxLoadStats(); return; }
  gxInited = true;
  try {
    await loadGalaxyLibrary('https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js');
    await loadGalaxyLibrary('https://cdn.jsdelivr.net/npm/3d-force-graph@1.73.0/dist/3d-force-graph.min.js');
    setupGxGraph();
    refreshGalaxy();
    gxLoadStats();
  } catch (error) {
    gxInited = false;
    console.warn('Memory Galaxy could not initialize:', error);
    const stats = document.getElementById('gx-stats');
    if (stats) stats.textContent = 'Visualization unavailable — your saved memories are still available.';
  }
}

function setupGxGraph() {
  const el = document.getElementById('gx-graph');
  if (!el || !window.ForceGraph3D) return;
  gxGraph = ForceGraph3D()(el)
    .backgroundColor('#08090e')
    .nodeAutoColorBy('source')
    .nodeLabel(n => `${n.source} • ${n.label}`)
    .nodeVal('val')
    .linkDirectionalParticles(1)
    .linkDirectionalParticleWidth(1.2)
    .linkColor(() => 'rgba(91,138,248,.2)')
    .onNodeClick(n => {
      showGxNode(n);
      const d = 120, r = 1 + d / Math.hypot(n.x||1, n.y||1, n.z||1);
      gxGraph.cameraPosition({x:n.x*r,y:n.y*r,z:n.z*r}, n, 900);
    })
    .onNodeHover(n => { el.style.cursor = n ? 'pointer' : null; });
  new ResizeObserver(() => gxGraph && gxGraph.width(el.clientWidth).height(el.clientHeight)).observe(el);
}

async function refreshGalaxy() {
  const limit = document.getElementById('gx-limit')?.value || 250;
  const statsEl = document.getElementById('gx-stats');
  if (statsEl) statsEl.textContent = 'loading…';
  try {
    const r = await fetch('/api/memory/galaxy?limit=' + limit);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const data = await r.json();
    if (gxGraph) gxGraph.graphData(data);
    if (statsEl) statsEl.textContent =
      `${data.total_memories} memories · ${data.links.length} links · ${data.sources?.length||0} sources`;
  } catch(e) {
    if (statsEl) statsEl.textContent = 'Load failed — ' + (e?.message||String(e));
  }
}

function fitGalaxy() { if (gxGraph) gxGraph.zoomToFit(600, 60); }

function showGxNode(n) {
  const el = document.getElementById('gx-results');
  if (!el) return;
  const memId = n.mem_id || n.id;
  el.innerHTML = `<div class="gx-hit">
    <div class="gx-hit-source">${escHtml(n.source||'')} · mem #${memId}</div>
    <div class="gx-hit-text">${escHtml(n.label||'')}</div>
    <div style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap">
      <button onclick="navigator.clipboard.writeText(${JSON.stringify(n.label||'')})" class="btn btn-ghost btn-sm">📋 Copy</button>
      <button onclick="insertCmd('Tell me more about: '+${JSON.stringify((n.label||'').slice(0,60))});nav('chat')" class="btn btn-ghost btn-sm">💬 Chat</button>
      <button onclick="deleteGxNode(${JSON.stringify(memId)})" class="btn btn-ghost btn-sm" style="color:var(--danger)">🗑 Delete</button>
    </div>
  </div>`;
}

async function deleteGxNode(memId) {
  const ok = await gmDanger('Delete Memory', `Remove memory #${memId} permanently?`);
  if (!ok) return;
  try {
    const r = await fetch(`/api/memory/${encodeURIComponent(memId)}`, {method:'DELETE'});
    if (!r.ok) { gmAlert('Delete failed: HTTP '+r.status); return; }
    const d = await r.json();
    if (d.ok) {
      showToast('🗑 Memory deleted');
      document.getElementById('gx-results').innerHTML = '<div style="color:var(--text-3);font-size:12px;padding:12px">Memory deleted.</div>';
      refreshGalaxy();
    } else {
      gmAlert('Delete failed: '+(d.error||'Unknown'));
    }
  } catch(ex) {
    gmAlert('Delete error: '+ex?.message);
  }
}

window.gxAddMemory = async function() {
  const text = await gmPrompt('New Memory Content:', 'e.g. User prefers Python and Tailwind CSS over Bootstrap', '', true);
  if (!text) return;
  const source = await gmPrompt('Source / Category (e.g. user_prefs, project_rules, architecture):', 'user_prefs');
  if (!source) return;
  const tags = await gmPrompt('Tags (comma-separated, optional):', 'python, tailwind, ui');
  try {
    toast('⏳ Storing vector memory...', 'ok', 2000);
    const r = await fetch('/api/memory/add', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({content: text, source, tags: (tags||'').split(',').map(t=>t.trim()).filter(Boolean)})
    });
    const j = await r.json();
    if (j.ok || j.id) {
      toast('✅ Memory #' + (j.id || 'new') + ' stored & indexed!', 'ok', 3000);
      if (typeof refreshGalaxy === 'function') refreshGalaxy();
    } else {
      gmAlert('Error adding memory: ' + (j.error || 'Unknown error'));
    }
  } catch(e) {
    gmAlert('Network error adding memory: ' + e.message);
  }
};

async function doGxSearch() {
  const q = document.getElementById('gx-search')?.value?.trim();
  if (!q) return;
  const el = document.getElementById('gx-results');
  if (!el) return;
  el.innerHTML = '<div style="color:var(--text-2);font-size:12px;padding:12px">Searching…</div>';
  try {
    const r = await fetch(`/api/memory/search?q=${encodeURIComponent(q)}&mode=hybrid&limit=20`);
    if (!r.ok) { el.innerHTML = `<div style="color:var(--danger);font-size:12px;padding:12px">Search failed (HTTP ${r.status})</div>`; return; }
    const results = await r.json();
    if (!results.length) {
      el.innerHTML = '<div style="color:var(--text-3);font-size:12px;padding:12px">No memories found for that query.</div>';
      return;
    }
    el.innerHTML = results.map(m => `
      <div class="gx-hit">
        <div class="gx-hit-source">${escHtml(m.source||'')}${m.tags?' · '+escHtml(m.tags):''} · mem #${m.id}</div>
        <div class="gx-hit-text">${escHtml((m.content||'').slice(0,150))}</div>
        <div style="margin-top:4px;display:flex;gap:4px">
          <button data-memory-content="${escHtml((m.content||'').slice(0,60))}" class="btn btn-ghost btn-sm gx-chat-memory" style="font-size:10px">💬 Chat</button>
          <button data-memory-id="${escHtml(String(m.id))}" class="btn btn-ghost btn-sm gx-delete-memory" style="font-size:10px;color:var(--danger)">🗑</button>
        </div>
      </div>`).join('');
    el.querySelectorAll('.gx-chat-memory').forEach(button => button.addEventListener('click', () => {
      insertCmd('Tell me about: ' + (button.dataset.memoryContent || ''));
      nav('chat');
    }));
    el.querySelectorAll('.gx-delete-memory').forEach(button => button.addEventListener('click', () => {
      deleteGxNode(button.dataset.memoryId);
    }));
  } catch(e) {
    el.innerHTML = `<div style="color:var(--danger);font-size:12px;padding:12px">Error: ${escHtml(e?.message||String(e))}</div>`;
  }
}

async function ingestMemory() {
  const contentEl = document.getElementById('gx-ingest-text');
  const tagsEl    = document.getElementById('gx-ingest-tags');
  const content   = contentEl?.value?.trim();
  const tags      = tagsEl?.value?.trim() || '';
  if (!content) { showToast('⚠️ Enter memory content'); return; }
  try {
    const r = await fetch('/api/memory/add', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({source:'user', content, tags})
    });
    if (!r.ok) { showToast('❌ Memory add failed (HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) {
      showToast('🌌 Memory added (id: '+j.id+')');
      if (contentEl) contentEl.value = '';
      if (tagsEl)    tagsEl.value    = '';
      refreshGalaxy();
    } else {
      showToast('❌ Failed: '+(j.error||'Unknown error'));
    }
  } catch(ex) {
    showToast('❌ Error: '+ex?.message);
  }
}

async function gxLoadStats() {
  try {
    const d = await AgenticAPI.get('/api/memory/stats');
    const el = document.getElementById('gx-mem-stats');
    if (!el) return;
    el.innerHTML = `
      <span>💾 ${d.sqlite_memories||0} memories</span>
      <span>🔮 ${d.vectors_sqlite||0} vectors</span>
      <span title="${d.engine||''}">${d.status==='active'?'✅':'⚠️'} ${d.engine||'FTS5'}</span>`;
  } catch(e) {}
}

async function gxReindex() {
  showToast('🔄 Reindexing FTS…');
  try {
    const d = await AgenticAPI.post('/api/memory/reindex');
    if (d.ok) showToast(`✅ Reindexed ${d.total} memories`);
    else gmAlert('Reindex error: '+(d.error||'Unknown'));
  } catch(ex) {
    gmAlert('Reindex error: '+ex?.message);
  }
}

async function gxExport() {
  try {
    const r = await fetch('/api/memory/export?limit=10000');
    if (!r.ok) { gmAlert('Export failed: HTTP '+r.status); return; }
    const d = await r.json();
    const blob = new Blob([JSON.stringify(d.memories, null, 2)], {type:'application/json'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `memory-export-${new Date().toISOString().slice(0,10)}.json`;
    a.click();
    showToast(`✅ Exported ${d.count} memories`);
  } catch(ex) {
    gmAlert('Export error: '+ex?.message);
  }
}

async function gxImport() {
  const input = document.createElement('input');
  input.type = 'file'; input.accept = '.json';
  input.onchange = async () => {
    const file = input.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      // Accept either array or {memories:[...]}
      const memories = Array.isArray(data) ? data : (data.memories || []);
      if (!memories.length) { gmAlert('No memories found in file.'); return; }
      const r = await fetch('/api/memory/import', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({memories})
      });
      if (!r.ok) { gmAlert('Import failed: HTTP '+r.status); return; }
      const d = await r.json();
      if (d.ok) {
        showToast(`✅ Imported ${d.imported}, skipped ${d.skipped}`);
        refreshGalaxy();
        gxLoadStats();
      } else {
        gmAlert('Import error: '+(d.error||'Unknown'));
      }
    } catch(ex) {
      gmAlert('Import parse error: '+ex?.message);
    }
  };
  input.click();
}

