// Agentic OS — GitHub Panel
// Extracted from 01-app-core.js for modularity
// ── GitHub Panel ──────────────────────────────────────────────────
let ghStatus = null, ghSelectedRepo = '';

async function renderGitHub() {
  const pane = document.getElementById('pane-github');
  pane.innerHTML = `<div class="section-head">
    <div><h2>🐙 GitHub Integration</h2><p>Bidirectional sync, branch management, PRs, Pages deploy — all from Agentic OS</p></div>
    <button onclick="renderGitHub()" class="btn btn-ghost btn-sm">⟳ Refresh</button>
  </div>
  <div id="gh-body"><div style="color:var(--text-2);font-size:13px">Loading…</div></div>`;

  try {
    const r = await fetch('/api/github/status');
    if (!r.ok) throw new Error('GitHub status API error ' + r.status);
    ghStatus = await r.json();
    renderGitHubBody(ghStatus);
  } catch(e) {
    document.getElementById('gh-body').innerHTML = `<div style="color:var(--red)">Error: ${escHtml(e.message)}</div>`;
  }
}

function renderGitHubBody(s) {
  const el = document.getElementById('gh-body');
  if (!s.connected) {
    el.innerHTML = `
    <div class="settings-card">
      <h3>🔑 Connect GitHub</h3>
      <p>A GitHub token unlocks: repo create, push/pull code, branch management, PRs, and GitHub Pages deploy.</p>
      <div style="background:var(--bg-1);border-radius:var(--radius-sm);padding:14px;font-size:13px;line-height:1.9;margin-bottom:16px">
        ${(s.setup?.steps||[]).map(step => `<div>${escHtml(step)}</div>`).join('')}
        <a href="${s.setup?.token_url||'https://github.com/settings/tokens'}" target="_blank" style="color:var(--accent);display:block;margin-top:8px;font-weight:700">→ Generate Token on GitHub ↗</a>
      </div>
      <div class="key-input-row">
        <input id="gh-token-input" type="password" class="key-input" placeholder="ghp_…" autocomplete="off">
        <button onclick="saveGHToken()" class="btn btn-primary">Save Token</button>
      </div>
      <div style="font-size:11.5px;color:var(--text-2);margin-top:6px">Scopes needed: <code>repo, workflow, read:user</code></div>
    </div>`;
    return;
  }

  const u = s.user || {};
  el.innerHTML = `
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
    <!-- User card -->
    <div class="settings-card">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
        <img src="${u.avatar_url||''}" style="width:48px;height:48px;border-radius:50%;border:2px solid var(--border)">
        <div>
          <div style="font-weight:800;font-size:15px">${escHtml(u.name||u.login||'')}</div>
          <a href="${u.html_url||''}" target="_blank" style="font-size:12px;color:var(--accent)">@${escHtml(u.login||'')}</a>
          <div style="font-size:11px;color:var(--text-2)">${u.public_repos||0} repos · ${escHtml(u.plan||'free')} plan</div>
        </div>
        <span class="tag green" style="margin-left:auto">✅ Connected</span>
      </div>

      <!-- Quick actions -->
      <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Quick Actions</div>
      <div style="display:flex;flex-direction:column;gap:6px">
        <button onclick="createGHRepo()" class="btn btn-primary btn-sm" style="text-align:left">📦 Create New Repository</button>
        <button onclick="showGHPush()" class="btn btn-ghost btn-sm" style="text-align:left">⬆ Push preview/ to GitHub</button>
        <button onclick="showGHPull()" class="btn btn-ghost btn-sm" style="text-align:left">⬇ Pull from GitHub → preview/</button>
        <button onclick="showGHPages()" class="btn btn-ghost btn-sm" style="text-align:left">🌐 Deploy to GitHub Pages</button>
        <button onclick="showGHPR()" class="btn btn-ghost btn-sm" style="text-align:left">🔀 Create Pull Request</button>
      </div>
    </div>

    <!-- Repo selector + recent repos -->
    <div class="settings-card">
      <div style="font-weight:700;margin-bottom:10px">📂 Your Repositories</div>
      <div style="display:flex;gap:6px;margin-bottom:10px">
        <input id="gh-repo-input" placeholder="owner/repo-name" value="${escHtml(ghSelectedRepo)}"
          style="flex:1;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 10px;color:var(--text-0);font-size:12.5px;outline:none;font-family:monospace">
        <button onclick="ghSelectRepo()" class="btn btn-primary btn-sm">Select</button>
      </div>
      ${ghSelectedRepo ? `<div style="background:var(--accent-glow);border:1px solid var(--accent);border-radius:var(--radius-sm);padding:8px 12px;font-size:12.5px;margin-bottom:10px">
        Selected: <strong>${escHtml(ghSelectedRepo)}</strong>
        <a href="https://github.com/${escHtml(ghSelectedRepo)}" target="_blank" style="color:var(--accent);margin-left:8px">↗</a>
      </div>` : ''}
      <div style="font-size:11px;font-weight:700;color:var(--text-2);margin-bottom:6px">Recent Repos</div>
      <div style="display:flex;flex-direction:column;gap:4px;max-height:220px;overflow-y:auto">
        ${(s.recent_repos||[]).map(r => `
          <div onclick="ghSetRepo('${escHtml(r.full_name)}')"
               style="display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:var(--radius-sm);cursor:pointer;transition:var(--transition)"
               onmouseover="this.style.background='var(--bg-3)'" onmouseout="this.style.background=''">
            <span style="font-size:12px">${r.private?'🔒':'📂'}</span>
            <div style="flex:1;min-width:0">
              <div style="font-size:12.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escHtml(r.name)}</div>
              <div style="font-size:10.5px;color:var(--text-3)">${r.default_branch} · ${r.updated_at}</div>
            </div>
          </div>`).join('')}
      </div>
    </div>
  </div>

  <!-- Action result area -->
  <div id="gh-action-result" style="margin-top:16px"></div>`;
}

function ghSetRepo(fullName) {
  ghSelectedRepo = fullName;
  const inp = document.getElementById('gh-repo-input');
  if (inp) inp.value = fullName;
  toast(`📂 Selected: ${fullName}`, 'ok', 1500);
}

function ghSelectRepo() {
  const inp = document.getElementById('gh-repo-input');
  ghSelectedRepo = (inp?.value || '').trim();
  if (ghSelectedRepo) toast(`📂 Using: ${ghSelectedRepo}`, 'ok', 1500);
}

async function saveGHToken() {
  const token = document.getElementById('gh-token-input')?.value.trim();
  if (!token) { toast('Enter your GitHub token', 'warn'); return; }
  try {
    const r = await fetch('/api/secrets/set', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({key:'GITHUB_TOKEN', value:token, scope:'global'})
    });
    if (!r.ok) { toast('Server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast('🐙 GitHub token saved! Reload to activate.', 'ok', 4000); }
    else toast('Failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('Save failed: ' + ex.message, 'err'); }
}

async function createGHRepo() {
  const name = await gmPrompt('Create GitHub Repository', 'Repository name (e.g. my-awesome-app)', 'agentic-os-project');
  if (!name) return;
  const priv = await gmConfirm('Repository visibility', 'Make this repository private?');
  const res  = document.getElementById('gh-action-result');
  if (res) res.innerHTML = `<div style="color:var(--text-2);font-size:13px">Creating repository…</div>`;
  try {
    const r = await fetch('/api/github/repos/create', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({name, private: priv, description:'Built with Agentic OS'})
    });
    if (!r.ok) { if (res) res.innerHTML = `<div style="color:var(--red)">Server error ${r.status}</div>`; return; }
    const j = await r.json();
    if (j.ok) {
    ghSelectedRepo = j.repo;
    if (res) res.innerHTML = `<div class="settings-card">
      <h3>✅ Repository Created!</h3>
      <p><a href="${j.url}" target="_blank" style="color:var(--accent)">${j.repo} ↗</a></p>
      <div style="font-size:12.5px;color:var(--text-2)">Clone URL: <code style="font-size:11px">${escHtml(j.clone_url)}</code></div>
      <button onclick="showGHPush()" class="btn btn-primary btn-sm" style="margin-top:10px">⬆ Push code now</button>
    </div>`;
    toast(`📦 Repository created: ${j.repo}`, 'ok', 4000);
  } else {
    if (res) res.innerHTML = `<div style="color:var(--red)">${escHtml(j.error||'')}</div>`;
    toast('Failed: ' + (j.error||''), 'err');
  }
  } catch(ex) { if (res) res.innerHTML = `<div style="color:var(--red)">${escHtml(ex.message)}</div>`; toast('Error: ' + ex.message, 'err'); }
}

async function showGHPush() {
  const repo = ghSelectedRepo || await gmPrompt('Push to GitHub', 'Repository (e.g. username/my-repo)', '');
  if (!repo) return;
  ghSelectedRepo = repo;
  const msg = await gmPrompt('Commit message', 'What changed?', `Agentic OS push ${new Date().toISOString().slice(0,10)}`);
  if (msg === null) return;
  const res = document.getElementById('gh-action-result');
  if (res) res.innerHTML = `<div style="color:var(--text-2)">Pushing ${escHtml(repo)}…</div>`;
  try {
    const r = await fetch('/api/github/push', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({repo, message: msg||'Agentic OS push', branch:'main'})
    });
    if (!r.ok) { if (res) res.innerHTML = `<div style="color:var(--red)">Server error ${r.status}</div>`; return; }
    const j = await r.json();
    if (j.ok) {
    if (res) res.innerHTML = `<div class="settings-card">
      <h3>✅ Pushed to GitHub!</h3>
      <p>${j.files_pushed} files pushed to <a href="${j.url}" target="_blank" style="color:var(--accent)">${escHtml(j.repo)} ↗</a></p>
      ${j.errors?.length ? `<div style="color:var(--yellow);font-size:12px">⚠ ${j.errors.length} errors: ${escHtml(j.errors.join(', '))}</div>` : ''}
    </div>`;
    toast(`⬆ Pushed ${j.files_pushed} files to GitHub`, 'ok', 4000);
  } else {
      toast('Push failed: ' + (j.error||''), 'err');
    }
  } catch(ex) { if (res) res.innerHTML = `<div style="color:var(--red)">${escHtml(ex.message)}</div>`; toast('Push error: ' + ex.message, 'err'); }
}

async function showGHPull() {
  const repo = ghSelectedRepo || await gmPrompt('Pull from GitHub', 'Repository (username/repo)', '');
  if (!repo) return;
  ghSelectedRepo = repo;
  const res = document.getElementById('gh-action-result');
  if (res) res.innerHTML = `<div style="color:var(--text-2)">Pulling from ${escHtml(repo)}…</div>`;
  try {
    const r = await fetch('/api/github/pull', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({repo, branch:'main'})
    });
    if (!r.ok) {
      if (res) res.innerHTML = `<div style="color:var(--red)">Server error ${r.status}</div>`;
      return;
    }
    const j = await r.json();
    if (j.ok) {
      if (res) res.innerHTML = `<div class="settings-card">
        <h3>⬇ Pulled from GitHub!</h3>
        <p>${j.files_pulled} files pulled from <strong>${escHtml(repo)}</strong> (${escHtml(j.branch||'main')})</p>
        <div style="font-size:12px;color:var(--text-2);margin-top:6px">Files are now in preview/</div>
        <button onclick="studioLoadFileTree?.()" class="btn btn-ghost btn-sm" style="margin-top:8px">📂 Refresh File Tree</button>
      </div>`;
      toast(`⬇ Pulled ${j.files_pulled} files from GitHub`, 'ok', 3000);
      studioLoadFileTree?.();
    } else {
      if (res) res.innerHTML = `<div style="color:var(--red)">${escHtml(j.error||'Pull failed')}</div>`;
      toast('Pull failed: ' + (j.error||''), 'err');
    }
  } catch(ex) {
    if (res) res.innerHTML = `<div style="color:var(--red)">${escHtml(ex.message)}</div>`;
    toast('Pull error: ' + ex.message, 'err');
  }
}

async function showGHPages() {
  const repo = ghSelectedRepo || await gmPrompt('Deploy to GitHub Pages', 'Repository (username/repo)', '');
  if (!repo) return;
  ghSelectedRepo = repo;
  toast('🌐 Deploying to GitHub Pages…', 'ok', 2000);
  const res = document.getElementById('gh-action-result');
  try {
    const r = await fetch('/api/github/pages/deploy', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({repo})
    });
    if (!r.ok) { if (res) res.innerHTML = `<div style="color:var(--red)">Server error ${r.status}</div>`; return; }
    const j = await r.json();
    if (j.ok) {
    if (res) res.innerHTML = `<div class="settings-card">
      <h3>🌐 Deployed to GitHub Pages!</h3>
      <a href="${j.url}" target="_blank" style="color:var(--accent);font-size:15px;font-weight:700">${j.url} ↗</a>
      <div style="font-size:12px;color:var(--text-2);margin-top:6px">${j.tip}</div>
    </div>`;
    toast(`🌐 GitHub Pages live: ${j.url}`, 'ok', 6000);
  } else {
      if (res) res.innerHTML = `<div style="color:var(--red)">${escHtml(j.error||'Pages deploy failed')}</div>`;
      toast('Pages deploy failed: ' + (j.error||''), 'err');
    }
  } catch(ex) { if (res) res.innerHTML = `<div style="color:var(--red)">${escHtml(ex.message)}</div>`; toast('Pages error: ' + ex.message, 'err'); }
}

async function showGHPR() {
  const repo = ghSelectedRepo || await gmPrompt('Create Pull Request', 'Repository (owner/repo)', '');
  if (!repo) return;
  if (!repo.includes('/')) { toast('Repository must be owner/repo format', 'warn'); return; }
  const [owner, repoName] = repo.split('/', 2);
  if (!owner || !repoName) { toast('Invalid repository format (use owner/repo)', 'warn'); return; }
  const head  = await gmPrompt('Head branch (source)', 'Branch with your changes', 'feature/my-feature');
  if (!head) return;
  const title = await gmPrompt('PR Title', 'What does this PR do?', 'Agentic OS changes');
  if (!title) return;
  try {
    const r = await fetch(`/api/github/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repoName)}/pulls`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({head, title, base:'main', body:'Automated PR from Agentic OS'})
    });
    if (!r.ok) { toast('Server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) {
      toast(`🔀 PR #${j.number} created!`, 'ok', 4000);
      window.open(j.url, '_blank');
    } else toast('PR failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('PR error: ' + ex.message, 'err'); }
}

