// Agentic OS — Deploy Panel
// Extracted from 01-app-core.js for modularity.
//
// NOTE: an earlier session added a SECOND, more complete renderDeploy()
// implementation directly into 01-app-core.js (6 providers: Vercel,
// Netlify, Railway, Render, Fly.io, GitHub Pages) instead of updating this
// file. Because 01-app-core.js loads synchronously and this file loads
// `defer`, this file's plain `function renderDeploy(){...}` declaration
// ALWAYS executed after and silently overwrote `window.renderDeploy`,
// meaning the richer 6-provider UI was 100% dead code — every user only
// ever saw this file's older 2-provider (Vercel/Netlify) card grid, even
// though the backend (`backend/routers/deploy.py`) has fully working
// endpoints for all 6 providers plus a GitHub Pages shortcut the whole
// time. Consolidated here as the single canonical implementation with all
// 6 providers, and the dead duplicate was deleted from 01-app-core.js.
// ── Deploy Panel ──────────────────────────────────────────────────
async function renderDeploy() {
  const pane = document.getElementById('pane-deploy');
  if (!pane) return;
  let statusData = {};
  try {
    const r = await fetch('/api/deploy/status');
    statusData = await r.json();
  } catch(e) {}

  const p = statusData.providers || {};
  // `id` is always one of 6 hardcoded literal strings passed at the 6
  // providerCard(...) call sites below, never dynamic/user-controlled data,
  // so a single-quoted literal + escHtml() is safe here (this session's
  // established safe pattern for hardcoded/short-alphabet values) — this
  // replaces a `doDeploy(${JSON.stringify(id)})` that was broken
  // UNCONDITIONALLY (not just on inputs containing quotes): JSON.stringify()
  // always wraps its output in literal double quotes, which collide with
  // the onclick attribute's own double-quote delimiters and corrupt the
  // HTML, throwing "Uncaught SyntaxError: Unexpected end of input" on
  // click — reproduced live on every single deploy button in this pane,
  // confirmed pre-existing (not introduced by this pass's provider-card
  // consolidation).
  const providerCard = (id, name, icon, ready, token_key, docs_url, hint) => {
    const btnLabel = ready ? `🚀 Deploy to ${name}` : `⚙️ Setup ${name}`;
    return `<div style="background:var(--bg-2);border:1px solid ${ready?'var(--accent)':'var(--border)'};border-radius:var(--radius-lg);padding:20px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <span style="font-size:24px">${icon}</span>
        <div>
          <div style="font-weight:700;font-size:15px">${name}</div>
          <div style="font-size:11.5px;color:var(--text-2)">${hint}</div>
        </div>
        <span class="tag ${ready?'green':''}" style="margin-left:auto">${ready?'Ready':'Setup needed'}</span>
      </div>
      ${!ready ? `<div style="background:var(--bg-1);border-radius:var(--radius-sm);padding:10px;font-size:12px;margin-bottom:10px;color:var(--text-2)">
        Save <code style="background:var(--bg-0);padding:1px 5px;border-radius:3px">${token_key}</code> via the 🔐 Vault tab (takes effect immediately), or add it to your .env file (requires an app restart).
        <a href="${safeUrl(docs_url)}" target="_blank" style="color:var(--accent);display:block;margin-top:4px">→ Get token</a>
      </div>` : ''}
      <button onclick="doDeploy('${escHtml(id)}')" class="btn ${ready?'btn-primary':'btn-ghost'}" style="width:100%" id="deploy-btn-${id}">${btnLabel}</button>
      <div id="deploy-result-${id}" style="margin-top:10px;display:none"></div>
    </div>`;
  };

  pane.innerHTML = `<div class="section-head">
    <div><h2>🚀 Deploy</h2><p>One-click deploy to 6 platforms, GitHub Pages, or share via Cloudflare Tunnel</p></div>
    <button onclick="renderDeploy()" class="btn btn-ghost btn-sm">⟳ Refresh</button>
  </div>
  <div style="margin-bottom:16px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px 14px;font-size:13px;color:var(--text-2)">
    📁 <strong>${statusData.preview_files||0} files</strong> ready in <code style="background:var(--bg-0);padding:1px 5px;border-radius:3px">preview/</code>
    ${statusData.preview_files ? '' : ' — <a href="#" onclick="nav(\'studio\');return false" style="color:var(--accent)">Build something first</a>'}
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;margin-bottom:24px">
    ${providerCard('vercel',       'Vercel',       '▲',  p.vercel?.ready,       'VERCEL_TOKEN',   'https://vercel.com/account/tokens',                      'Best for Next.js, React, static sites')}
    ${providerCard('netlify',      'Netlify',      '◈',  p.netlify?.ready,      'NETLIFY_TOKEN',  'https://app.netlify.com/user/applications',              'Great for static sites, auto HTTPS')}
    ${providerCard('railway',      'Railway',      '🚂', p.railway?.ready,      'RAILWAY_TOKEN',  'https://railway.app/account/tokens',                     'Full-stack apps with a database')}
    ${providerCard('render',       'Render',       '🎨', p.render?.ready,      'RENDER_API_KEY', 'https://dashboard.render.com/u/account/api-keys',        'Free tier, auto-deploy from GitHub')}
    ${providerCard('flyio',        'Fly.io',       '🪰', p.flyio?.ready,       'flyctl CLI',     'https://fly.io/docs/hands-on/install-flyctl/',           'Global edge, Docker-based')}
    ${providerCard('github-pages', 'GitHub Pages', '🌐', p.github_pages?.ready,'GITHUB_TOKEN',   'https://github.com/settings/tokens',                     'Free static hosting via GitHub')}
  </div>
  <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:20px;margin-bottom:16px">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
      <span style="font-size:24px">☁️</span>
      <div><div style="font-weight:700">Cloudflare Tunnel</div>
      <div style="font-size:12px;color:var(--text-2)">Share localhost:8787 publicly via HTTPS — no signup needed</div></div>
      <span class="tag ${p.cloudflare?.ready?'green':''}" style="margin-left:auto">
        ${p.cloudflare?.ready?'cloudflared installed':'Not installed'}
      </span>
    </div>
    <button onclick="startTunnel()" class="btn btn-ghost" style="width:100%" id="tunnel-btn">🌐 Start Public Tunnel</button>
    <div id="tunnel-result" style="margin-top:10px;display:none"></div>
  </div>
  <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:20px">
    <div style="font-weight:700;margin-bottom:12px">📋 Deploy History</div>
    <div id="deploy-history">Loading…</div>
  </div>`;
  loadDeployHistory();
}

async function doDeploy(provider) {
  const btn = document.getElementById(`deploy-btn-${provider}`);
  const res = document.getElementById(`deploy-result-${provider}`);
  if (!btn || !res) return;
  const providerLabel = provider.split('-').map(w => w.charAt(0).toUpperCase()+w.slice(1)).join(' ');
  btn.disabled = true; btn.textContent = `⏳ Deploying to ${providerLabel}…`;
  res.style.display = 'block';
  res.innerHTML = '<div style="color:var(--text-2);font-size:13px">Deploying…</div>';
  try {
    const r = await fetch(`/api/deploy/${encodeURIComponent(provider)}`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({})
    });
    if (!r.ok) throw new Error(`Server error ${r.status}`);
    const j = await r.json();
    if (j.ok && j.no_action) {
      // Some providers (Render) have no zip-upload/drag-drop deploy API —
      // the backend can only confirm the API key is valid and point the
      // user at a one-time manual GitHub-connect step. Showing the same
      // "✅ Deployed!" success message as a real deploy here would be
      // misleading (nothing was actually deployed), so render an honest
      // "key confirmed, action needed" state instead.
      res.innerHTML = `<div style="color:var(--accent);font-weight:700">🔑 API key confirmed</div>
        <div style="font-size:12px;color:var(--text-2);margin-top:4px">${escHtml(j.tip||'')}</div>`;
      toast(`🔑 ${providerLabel} key confirmed — manual GitHub connect still required`, 'ok', 5000);
    } else if (j.ok) {
      const urlLink = j.url ? `<a href="${safeUrl(j.url)}" target="_blank" style="color:var(--accent);font-size:13px;display:block;margin-top:4px">${j.url}</a>` : '';
      const output  = j.output ? `<div style="font-size:11px;color:var(--text-2);margin-top:4px;font-family:monospace;white-space:pre-wrap">${escHtml(j.output.slice(0,200))}</div>` : '';
      res.innerHTML = `<div style="color:var(--green);font-weight:700">✅ Deployed!</div>
        ${urlLink}
        ${output}
        <div style="font-size:11px;color:var(--text-2);margin-top:4px">${escHtml(j.tip||'')}</div>`;
      toast(`🚀 Deployed to ${providerLabel}!`, 'ok', 5000);
    } else {
      const setup = j.setup ? '<div style="font-size:11.5px;color:var(--text-2);margin-top:6px">' + (j.setup||[]).map(s=>escHtml(s)).join('<br>') + '</div>' : '';
      const alt = j.alternative ? `<div style="font-size:11px;color:var(--accent);margin-top:6px">${escHtml(j.alternative)}</div>` : '';
      res.innerHTML = `<div style="color:var(--yellow)">⚠️ ${escHtml(j.error||'Setup required')}</div>${setup}${alt}`;
      toast(`⚠️ ${providerLabel} setup needed`, 'warn', 3000);
    }
  } catch(e) {
    res.innerHTML = `<div style="color:var(--red)">Error: ${escHtml(e.message)}</div>`;
    toast(`⚠️ Deploy error: ${e.message}`, 'err');
  } finally {
    btn.disabled = false;
    btn.textContent = `🚀 Deploy to ${providerLabel}`;
  }
}

async function startTunnel() {
  const btn = document.getElementById('tunnel-btn');
  const res = document.getElementById('tunnel-result');
  btn.disabled = true; btn.textContent = '⏳ Starting tunnel…';
  res.style.display = 'block';
  res.innerHTML = '<div style="color:var(--text-2);font-size:13px">Connecting to Cloudflare…</div>';
  try {
    const r = await fetch('/api/deploy/tunnel', {method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    if (!r.ok) throw new Error(`Server error ${r.status}`);
    const j = await r.json();
    if (j.ok) {
      res.innerHTML = `<div style="color:var(--green);font-weight:700">✅ Tunnel active!</div>
        <a href="${safeUrl(j.url)}" target="_blank" style="color:var(--accent);font-size:14px;display:block;margin-top:4px;font-weight:700">${j.url}</a>
        <div style="font-size:11.5px;color:var(--text-2);margin-top:4px">${escHtml(j.note||'')}</div>
        ${j.qr?`<img src="${j.qr}" style="margin-top:10px;border-radius:8px;width:120px">`:''} 
        <button onclick="stopTunnel()" class="btn btn-ghost btn-sm" style="margin-top:8px;color:var(--danger)">⛔ Stop Tunnel</button>`;
      toast(j.already_active ? '🌐 Tunnel already running — reusing it' : '🌐 Tunnel started — share the URL!', 'ok', 6000);
    } else {
      const installs = j.install ? Object.entries(j.install).map(([k,v])=>`<div><strong>${k}:</strong> <code style="font-size:11px">${escHtml(v)}</code></div>`).join('') : '';
      const then_ = j.then ? `<div style="margin-top:6px;color:var(--text-2);font-size:12px">${escHtml(j.then)}</div>` : '';
      res.innerHTML = `<div style="color:var(--yellow)">⚠️ ${escHtml(j.error||'')}</div>${installs}${then_}`;
    }
  } catch(e) {
    res.innerHTML = `<div style="color:var(--red)">Error: ${escHtml(e.message)}</div>`;
  } finally {
    btn.disabled = false; btn.textContent = '🌐 Start Public Tunnel';
  }
}

async function stopTunnel() {
  try {
    const r = await fetch('/api/deploy/tunnel/stop', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    const j = await r.json();
    if (j.ok) {
      const res = document.getElementById('tunnel-result');
      if (res) res.innerHTML = '<div style="color:var(--text-2)">Tunnel stopped.</div>';
      toast('⛔ Tunnel stopped', 'ok', 2000);
    } else {
      toast('Stop failed: ' + (j.error||''), 'err');
    }
  } catch(ex) { toast('Error stopping tunnel: ' + ex.message, 'err'); }
}

async function loadDeployHistory() {
  try {
    const j = await AgenticAPI.get('/api/deploy/history');
    const el = document.getElementById('deploy-history');
    if (!el) return;
    if (!j.length) { el.innerHTML = '<div style="color:var(--text-3);font-size:13px">No deploys yet.</div>'; return; }
    el.innerHTML = j.slice(0,10).map(d =>
      `<div style="display:flex;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);font-size:12.5px">
        <span style="color:var(--green)">🚀</span>
        <span style="flex:1;color:var(--text-1)">${escHtml((d.content||'').slice(0,80))}</span>
        <span style="color:var(--text-3)">${(d.created_at||'').slice(0,10)}</span>
      </div>`
    ).join('');
  } catch(e) {
    const el = document.getElementById('deploy-history');
    if (el) el.innerHTML = '<div style="color:var(--text-3);font-size:13px">Could not load history.</div>';
  }
}
