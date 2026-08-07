// Agentic OS — Composer (Multi-file AI Agent)
// Extracted from 01-app-core.js for modularity
// ── Composer (Multi-file AI Agent) ────────────────────────────────
let composerRunning = false;

async function renderComposer() {
  const pane = document.getElementById('pane-composer');
  pane.innerHTML = `<div class="section-head">
    <div><h2>🪄 Composer</h2><p>Multi-file AI agent — one instruction builds your entire project. Screenshot → Code. Branch previews.</p></div>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
    <!-- Left: Input panels -->
    <div style="display:flex;flex-direction:column;gap:14px">

      <!-- Multi-file agent -->
      <div class="settings-card">
        <h3>🤖 Multi-File Agent</h3>
        <p>Like Cursor Composer — describe what to build, AI creates all needed files across your project.</p>
        <select id="comp-framework" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 10px;color:var(--text-0);font-size:13px;outline:none;margin-bottom:8px">
          <option value="web">🌐 Web (HTML/CSS/JS)</option>
          <option value="nextjs">⚛️ Next.js</option>
          <option value="sveltekit">🔥 SvelteKit</option>
          <option value="expo">📱 Expo React Native</option>
        </select>
        <textarea id="comp-instruction" data-draft="composer-instruction" placeholder="Build a SaaS dashboard with a sidebar nav, stats cards, a data table, and a dark mode toggle. Make it production-ready with Tailwind CSS." style="width:100%;min-height:100px;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;color:var(--text-0);font-size:13px;resize:none;outline:none;font-family:inherit;margin-bottom:10px"></textarea>
        <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px" id="comp-prompts">
          ${[
            'Dark mode landing page with hero, features, pricing',
            'Login + signup form with validation',
            'Dashboard with charts and sidebar',
            'Mobile-first portfolio site',
            'E-commerce product page with cart',
          ].map(p => `<button data-act-click="hSetFieldValue('comp-instruction',${jsArg(p)})" class="chat-tool u-11a50812" >${p.slice(0,30)}…</button>`).join('')}
        </div>
        <button data-act-click="runComposer()" class="btn btn-primary" style="width:100%" id="comp-run-btn">🪄 Build with AI</button>
        <div id="comp-status" style="font-size:12px;color:var(--text-2);margin-top:8px;min-height:18px"></div>
      </div>

      <!-- Screenshot to code -->
      <div class="settings-card">
        <h3>📷 Screenshot → Code</h3>
        <p>Paste a design screenshot and AI rebuilds it as working code. Like v0's image input.</p>
        <div id="screenshot-drop" style="border:2px dashed var(--border);border-radius:var(--radius-sm);padding:24px;text-align:center;cursor:pointer;transition:var(--transition);margin-bottom:10px" 
             data-prevent="1" data-hover="bc:var(--accent)" data-act-dragover="hNoop()" 
             data-act-dragleave="hSetBorder($this,'var(--border)')"
             data-act-drop="handleScreenshotDrop($event)"
             data-act-click="hClickElement('screenshot-file')">
          <div style="font-size:32px;margin-bottom:8px">🖼️</div>
          <div style="font-size:13px;color:var(--text-2)">Drop a screenshot here, or click to upload</div>
          <div style="font-size:11px;color:var(--text-3);margin-top:4px">PNG, JPG, WebP — any design or UI screenshot</div>
        </div>
        <input type="file" id="screenshot-file" accept="image/*" style="display:none" data-act-change="handleScreenshotFile($event)">
        <div id="screenshot-preview" style="display:none;margin-bottom:10px">
          <img id="screenshot-img" style="max-width:100%;max-height:200px;border-radius:var(--radius-sm);border:1px solid var(--border)" alt="Uploaded screenshot preview">
        </div>
        <div style="display:flex;gap:8px">
          <select id="s2c-framework" style="flex:1;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px;color:var(--text-0);font-size:12.5px;outline:none">
            <option value="web">Web (HTML)</option>
            <option value="react">React</option>
          </select>
          <button data-act-click="runScreenshotToCode()" class="btn btn-primary" id="s2c-btn" disabled>📷 Convert</button>
        </div>
        <div id="s2c-status" style="font-size:12px;color:var(--text-2);margin-top:6px"></div>
      </div>
    </div>

    <!-- Right: Results + Branch previews -->
    <div style="display:flex;flex-direction:column;gap:14px">
      <!-- Composer output -->
      <div id="comp-results" style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:16px;min-height:200px">
        <div style="color:var(--text-3);font-size:13px">Run the composer → file results appear here</div>
      </div>

      <!-- Branch previews -->
      <div class="settings-card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
          <h3 style="margin:0">🌿 Branch Previews</h3>
          <button data-act-click="createBranchPreview()" class="btn btn-primary btn-sm">+ Snapshot</button>
        </div>
        <p style="font-size:12.5px;color:var(--text-2)">Snapshot current state as a named preview URL. Share with clients before making changes.</p>
        <div id="branch-list" style="display:flex;flex-direction:column;gap:6px">Loading…</div>
      </div>
    </div>
  </div>`;

  loadBranchPreviews();
}

async function runComposer() {
  const instruction = document.getElementById('comp-instruction')?.value.trim();
  const framework   = document.getElementById('comp-framework')?.value || 'web';
  if (!instruction) { toast('Enter an instruction', 'warn'); return; }
  if (composerRunning) { toast('Composer is already running…', 'warn'); return; }

  composerRunning = true;
  const btn    = document.getElementById('comp-run-btn');
  const status = document.getElementById('comp-status');
  const results = document.getElementById('comp-results');
  btn.disabled = true; btn.textContent = '⏳ Building…';
  status.textContent = 'Planning…';
  results.innerHTML  = '';

  const fileCards = {};

  try {
    const resp = await fetch('/api/composer/run', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({instruction, framework, stream: true})
    });
    // FIX 7a: check HTTP status before reading body
    if (!resp.ok) { throw new Error(`Server error: HTTP ${resp.status}`); }
    // FIX 7b: null guard before calling getReader()
    if (!resp.body) { throw new Error('No response body — check server'); }
    const reader  = resp.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      const text = decoder.decode(value, {stream:true});
      for (const line of text.split('\n')) {
        if (!line.startsWith('data:')) continue;
        try {
          const ev = JSON.parse(line.slice(5).trim());

          if (ev.type === 'plan_ready' && ev.plan) {
            const plan = ev.plan;
            status.textContent = plan.summary || 'Building…';
            results.innerHTML = `<div style="font-size:12px;color:var(--text-2);margin-bottom:10px">📋 ${escHtml(plan.summary||'')}</div>`;
            (plan.files||[]).forEach(f => {
              const card = document.createElement('div');
              card.id   = `comp-file-${btoa(f.path).slice(0,8)}`;
              card.style.cssText = 'background:var(--bg-3);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;margin-bottom:6px;font-size:12px';
              card.innerHTML = `<span style="font-family:monospace">${escHtml(f.path)}</span> <span style="color:var(--text-3)">⏳</span>`;
              results.appendChild(card);
            });
          }

          if (ev.type === 'file_start') {
            const id = `comp-file-${btoa(ev.path).slice(0,8)}`;
            const existing = document.getElementById(id);
            if (existing) existing.innerHTML = `<span style="font-family:monospace;color:var(--yellow)">${escHtml(ev.path)}</span> <span style="color:var(--yellow)">⚡ writing…</span>`;
            status.textContent = `Writing ${ev.path}…`;
          }

          if (ev.type === 'file_done') {
            const id = `comp-file-${btoa(ev.path).slice(0,8)}`;
            const existing = document.getElementById(id);
            if (existing) existing.innerHTML = `<span style="font-family:monospace;color:var(--green)">${escHtml(ev.path)}</span> <span style="color:var(--green)">✅ ${ev.bytes}B</span>`;
          }

          // The backend now refuses paths that escape the project directory or
          // target protected filenames. Nothing rendered file_error, so a
          // refused file just stayed on "⏳" forever with no explanation.
          if (ev.type === 'file_error') {
            const id = `comp-file-${btoa(ev.path).slice(0,8)}`;
            const existing = document.getElementById(id);
            const msg = `<span style="font-family:monospace;color:var(--red)">${escHtml(ev.path)}</span> <span style="color:var(--red)">✕ ${escHtml(ev.error||'failed')}</span>`;
            if (existing) { existing.innerHTML = msg; }
            else { const d = document.createElement('div'); d.innerHTML = msg; results.appendChild(d); }
          }

          if (ev.type === 'done') {
            const written = ev.files_written || [];
            status.innerHTML = `✅ Done in ${ev.duration_ms}ms — ${written.length} files written`;
            if (written.length > 0) {
              results.innerHTML += `<div style="margin-top:10px;display:flex;gap:8px">
                <button data-act-click="nav('studio')" class="btn btn-primary btn-sm">🎬 View in Studio</button>
                <button data-act-click="createBranchPreview()" class="btn btn-ghost btn-sm">📸 Snapshot</button>
                <button data-act-click="showGHPush()" class="btn btn-ghost btn-sm">⬆ Push to GitHub</button>
              </div>`;
              // Reload studio file tree
              studioLoadFileTree?.();
              studioReloadPreview?.();
              toast(`🪄 Built ${written.length} files!`, 'ok', 4000);
            }
          }
        } catch(e) {}
      }
    }
  } catch(e) {
    status.textContent = '✗ ' + e.message;
    toast('Composer error: ' + e.message, 'err');
  } finally {
    composerRunning = false;
    btn.disabled = false; btn.textContent = '🪄 Build with AI';
  }
}

// Screenshot to code
let screenshotB64 = '';

function handleScreenshotDrop(e) {
  e.preventDefault();
  const file = e.dataTransfer.files[0];
  if (file) loadScreenshotFile(file);
}

function handleScreenshotFile(e) {
  const file = e.target.files[0];
  if (file) loadScreenshotFile(file);
}

function loadScreenshotFile(file) {
  const reader = new FileReader();
  reader.onload = e => {
    screenshotB64 = e.target.result;
    const prev = document.getElementById('screenshot-preview');
    const img  = document.getElementById('screenshot-img');
    const btn  = document.getElementById('s2c-btn');
    const drop = document.getElementById('screenshot-drop');
    if (prev) prev.style.display = 'block';
    if (img)  img.src = screenshotB64;
    if (btn)  btn.disabled = false;
    if (drop) drop.style.borderColor = 'var(--green)';
    toast('📷 Image loaded — click Convert', 'ok', 2000);
  };
  reader.readAsDataURL(file);
}

async function runScreenshotToCode() {
  if (!screenshotB64) { toast('Upload a screenshot first', 'warn'); return; }
  const fw  = document.getElementById('s2c-framework')?.value || 'web';
  const btn = document.getElementById('s2c-btn');
  const st  = document.getElementById('s2c-status');
  btn.disabled = true; btn.textContent = '⏳ Converting…';
  if (st) st.textContent = 'AI is analyzing your screenshot…';
  // FIX 8: try/catch for network failures
  try {
    const r = await fetch('/api/composer/screenshot-to-code', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({image_b64: screenshotB64.split(',')[1], framework: fw, filename:'index.html'})
    });
    if (!r.ok) {
      let detail = '';
      try { detail = (await r.json()).error || ''; } catch (e) { /* non-JSON body */ }
      throw new Error(detail || `HTTP ${r.status}`);
    }
    const j = await r.json();
    if (j.ok) {
      // preview_url went into an href unescaped; keep it same-origin.
      // Renamed from `safeUrl` — a local of that name SHADOWS the global
      // sanitiser in 01-app-core.js, so any later edit in this scope that
      // reached for safeUrl() would silently get a string instead of the
      // function. The value itself was already restricted to same-origin
      // paths by the regex; the hazard was the name.
      const previewPath = /^\/[^\s"'<>]*$/.test(j.preview_url || '') ? j.preview_url : '/preview/index.html';
      if (st) st.innerHTML = `✅ Converted! ${escHtml(String(j.tokens ?? 0))} tokens · <a href="${safeUrl(previewPath)}" target="_blank" rel="noopener" style="color:var(--accent-text)">Preview ↗</a>`;
      studioLoadFileTree?.();
      studioReloadPreview?.();
      toast('📷 Screenshot converted to code!', 'ok', 4000);
      nav('studio');
    } else {
      if (st) st.textContent = '✗ ' + (j.error||'Conversion failed — check your API key supports vision');
      toast(j.error || 'Conversion failed', 'err');
    }
  } catch(ex) {
    if (st) st.textContent = '✗ ' + ex.message;
    toast('Conversion error: ' + ex.message, 'err');
  } finally {
    btn.disabled = false; btn.textContent = '📷 Convert';
  }
}

// Branch previews
async function loadBranchPreviews() {
  try {
    const r = await fetch('/api/composer/preview/branches');
    const j = await r.json();
    const el = document.getElementById('branch-list');
    if (!el) return;
    if (!j.branches?.length) {
      el.innerHTML = '<div style="color:var(--text-3);font-size:12.5px">No snapshots yet. Click "+ Snapshot" to capture the current state.</div>';
      return;
    }
    el.innerHTML = j.branches.map(b => `
      <div style="background:var(--bg-3);border-radius:var(--radius-sm);padding:8px 12px;display:flex;align-items:center;gap:8px">
        <div class="u-59eddc67">
          <div style="font-size:12.5px;font-weight:600">${escHtml(b.title||b.name)}</div>
          <div style="font-size:11px;color:var(--text-3)">${b.files} files · ${(b.created_at||'').slice(0,16)}</div>
        </div>
        <a href="${safeUrl(b.url)}" target="_blank" class="btn btn-ghost btn-sm">View ↗</a>
        <button data-act-click="deleteBranchPreview(${jsArg(b.name)})" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:12px">🗑</button>
      </div>`).join('');
  } catch(e) {}
}

async function createBranchPreview() {
  const name = await gmPrompt('Create Preview Snapshot', 'Name this snapshot (e.g. v1-homepage, client-review)', `snapshot-${Date.now()}`);
  if (!name) return;
  const r = await fetch('/api/composer/preview/branch', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name, title: name})
  });
  const j = await r.json();
  if (j.ok) {
    toast(`📸 Snapshot created! ${j.files} files`, 'ok', 3000);
    loadBranchPreviews();
    await gmAlert('Branch Preview Created 🌿',
      `<div>Share this URL with clients for review:</div>
       <code style="display:block;background:var(--bg-0);padding:8px;border-radius:4px;margin:10px 0;font-size:12px">http://localhost:8787${j.url}</code>
       <div style="font-size:12px;color:var(--text-2)">The snapshot is frozen — changes to your project won't affect it.</div>`);
  } else toast('Snapshot failed: ' + (j.error||''), 'err');
}

async function deleteBranchPreview(name) {
  if (!(await gmDanger('Delete Snapshot', `Delete snapshot "${name}"?`))) return;
  await fetch(`/api/composer/preview/branches/${encodeURIComponent(name)}`, {method:'DELETE'});
  toast('Snapshot deleted', 'ok', 1500);
  loadBranchPreviews();
}

