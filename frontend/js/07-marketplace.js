// Agentic OS v6.0 — Plugin marketplace, plugin SDK, multi-tab preview
// Extracted from index.html (block 7)


'use strict';

// ══════════════════════════════════════════════════════════════════
//  STEERING FILES — persistent project context in every prompt
// ══════════════════════════════════════════════════════════════════
async function renderSteering() {
  const pane = document.getElementById('pane-steering');
  if (!pane) return;

  const [files, compiled, patterns] = await Promise.all([
    fetch('/api/steering').then(r=>r.ok?r.json():null).catch(()=>({files:[]})),
    fetch('/api/steering/compiled').then(r=>r.ok?r.json():null).catch(()=>({context:'',length:0})),
    fetch('/api/steering/learned/patterns').then(r=>r.ok?r.json():null).catch(()=>({patterns:[]})),
  ]);

  pane.innerHTML = `
  

  <div style="padding:20px;max-width:900px;margin:0 auto">
    <div class="section-head">
      <div>
        <h2>🧭 Steering Files</h2>
        <p>Project rules &amp; context injected into every AI prompt — like Kiro steering + Cursor .cursorrules + Windsurf Memories</p>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn" onclick="steerNew()">＋ New File</button>
        <button class="btn-sm" onclick="steerLearnFromChat()">🧠 Auto-Learn</button>
        <button class="btn-sm" onclick="steerPromotePatterns()">⬆ Promote Patterns</button>
      </div>
    </div>

    <!-- Context preview -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;margin-bottom:16px;overflow:hidden">
      <div style="padding:10px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px">
        <span style="font-weight:700;font-size:13px">📡 Compiled Context</span>
        <span style="font-size:11px;color:var(--text-3)">
          ${compiled.llm_chars||compiled.length||0} chars injected into every prompt
          ${compiled.truncated_for_llm?'<span style="color:var(--warning)">⚠️ truncated</span>':''}
        </span>
        <span style="margin-left:auto;font-size:11px;${(compiled.length||0)>0?'color:var(--success)':'color:var(--text-3)'}">
          ${(compiled.length||0)>0?'✅ Active':'⚠️ No files enabled'}
        </span>
      </div>
      <div style="padding:12px 16px;max-height:120px;overflow-y:auto;font-family:monospace;font-size:11px;color:var(--text-2);white-space:pre-wrap">${escHtml((compiled.context||'').slice(0,800))}${(compiled.length||0)>800?'…':''}</div>
    </div>

    <!-- Steering files -->
    <div style="font-size:13px;font-weight:700;margin-bottom:10px">Steering Files (${(files.files||[]).length})</div>
    <div id="steer-file-list">
      ${(files.files||[]).map(f=>`
        <div class="steer-card">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
            <button class="steer-toggle ${f.enabled?'on':''}" onclick="steerToggle(${JSON.stringify(f.id)},this)" title="${f.enabled?'Enabled':'Disabled'}"></button>
            <strong style="color:var(--text-0)">${escHtml(f.title)}</strong>
            <span class="steer-cat">${escHtml(f.category||'general')}</span>
            ${f.auto_learned?'<span class="steer-auto-badge">Auto-learned</span>':''}
            <div style="margin-left:auto;display:flex;gap:5px">
              <button class="btn-sm" onclick="steerEdit(${JSON.stringify(f.id)})">✏</button>
              <button class="btn-sm" style="color:var(--danger)" onclick="steerDelete(${JSON.stringify(f.id)})">🗑</button>
            </div>
          </div>
          <div style="font-size:11px;color:var(--text-2);font-family:monospace;line-height:1.6;max-height:80px;overflow:hidden">${escHtml((f.content||'').slice(0,300))}${(f.content||'').length>300?'…':''}</div>
        </div>
      `).join('') || '<div style="color:var(--text-3);padding:16px;text-align:center">No steering files yet. Create one or click Auto-Learn.</div>'}
    </div>

    <!-- Learned patterns -->
    ${(patterns.patterns||[]).length ? `
    <div style="margin-top:20px;font-size:13px;font-weight:700;margin-bottom:10px">🧠 Learned Patterns (${patterns.count||0})</div>
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;overflow:hidden">
      ${(patterns.patterns||[]).slice(0,10).map(p=>`
        <div style="display:flex;align-items:center;gap:8px;padding:8px 14px;border-bottom:1px solid var(--border);font-size:12px">
          <span style="color:var(--text-3);width:140px;flex-shrink:0">${escHtml(p.pattern_key||'')}</span>
          <span style="color:var(--text-1);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml((p.pattern_val||'').slice(0,80))}</span>
          <span style="color:var(--accent);font-weight:700;width:40px;text-align:right">${Math.round((p.confidence||0)*100)}%</span>
          <span style="color:var(--text-3);font-size:10px;width:50px">×${p.occurrences||1}</span>
          ${p.promoted?'<span style="font-size:10px;color:var(--success)">✅</span>':''}
        </div>
      `).join('')}
    </div>` : ''}
  </div>`;
}

async function steerNew() {
  const title = await gmPrompt('Steering file title:', 'My Convention');
  if (!title) return;
  const cat   = await gmPrompt('Category (stack|style|architecture|context|custom):', 'custom');
  const overlay = document.createElement('div');
  overlay.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
  overlay.innerHTML=`
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:14px;width:600px;max-height:80vh;display:flex;flex-direction:column;padding:20px;gap:12px">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <h3 style="margin:0">New Steering File: ${escHtml(title)}</h3>
        <button onclick="this.closest('[style*=\"fixed\"]').remove()" style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
      </div>
      <textarea id="steer-new-content" rows="15" style="flex:1;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:12px;font-family:monospace;padding:10px;resize:none" placeholder="# ${title}\n\nWrite your project rules and conventions here..."></textarea>
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button class="btn-sm" onclick="this.closest('[style*=\"fixed\"]').remove()">Cancel</button>
        <button class="btn" data-title="${title.replace(/"/g,'&quot;')}" data-cat="${(cat||'custom').replace(/"/g,'&quot;')}" onclick="steerSaveNew(this.dataset.title,this.dataset.cat,this)">💾 Save</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
}

async function steerSaveNew(title, cat, btn) {
  const content = document.getElementById('steer-new-content')?.value||'';
  if (!content.trim()) { gmAlert('Add some content first'); return; }
  try {
    await fetch('/api/steering',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({title,category:cat,content,enabled:true})});
    btn.closest('[style*="fixed"]').remove();
    renderSteering();
    showToast('✅ Steering file saved');
  } catch(ex) { gmAlert('Save failed: '+ex.message); }
}

async function steerToggle(fileId, btn) {
  // FIX 9: try/catch for silent failure; FIX 9b: re-render compiled preview on change
  try {
    const r = await fetch(`/api/steering/${encodeURIComponent(fileId)}`/toggle`,{method:'POST'});
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const d = await r.json();
    if (!d.ok) throw new Error(d.error||'Toggle failed');
    btn.classList.toggle('on', d.enabled);
    btn.title = d.enabled ? 'Enabled' : 'Disabled';
    // Re-render compiled context bar to reflect new char count
    fetch('/api/steering/compiled').then(r=>r.ok?r.json():null).then(compiled => { if (!compiled) return;
      const bar = document.querySelector('#pane-steering [style*="Compiled Context"]');
      if (!bar) return;
      const charsEl = bar.querySelector('[style*="chars"]') || bar.parentElement?.querySelector('span[style*="color"]');
      // Simplest: just re-render the whole pane
      renderSteering();
    }).catch(()=>{});
  } catch(ex) {
    showToast('⚠️ Toggle failed: ' + ex.message, 'err', 3000);
    // Revert visual state
    btn.classList.toggle('on');
  }
}

async function steerEdit(fileId) {
  const r = await fetch(`/api/steering/${encodeURIComponent(fileId)}``);
  const f = await r.json();
  const overlay = document.createElement('div');
  overlay.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
  overlay.innerHTML=`
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:14px;width:700px;max-height:85vh;display:flex;flex-direction:column;padding:20px;gap:12px">
      <div style="display:flex;align-items:center;gap:8px">
        <h3 style="margin:0;flex:1">✏ ${escHtml(f.title||fileId)}</h3>
        <button onclick="this.closest('[style*=\"fixed\"]').remove()" style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
      </div>
      <textarea id="steer-edit-ta" rows="18" style="flex:1;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:12px;font-family:monospace;padding:10px;resize:none">${escHtml(f.content||'')}</textarea>
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button class="btn-sm" onclick="this.closest('[style*=\"fixed\"]').remove()">Cancel</button>
        <button class="btn" onclick="steerSaveEdit(${JSON.stringify(fileId)},this)">💾 Save</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
}

async function steerSaveEdit(fileId, btn) {
  // FIX 11: proper try/catch for edit save
  const ta = document.getElementById('steer-edit-ta');
  const c  = ta?.value ?? '';
  try {
    btn.textContent = '⏳ Saving…';
    btn.disabled = true;
    const r = await fetch(`/api/steering/${encodeURIComponent(fileId)}``, {
      method:'PUT', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({content: c})
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    btn.closest('[style*="fixed"]').remove();
    renderSteering();
    showToast('✅ Steering file saved');
  } catch(ex) {
    btn.textContent = '💾 Save';
    btn.disabled = false;
    gmAlert('Save failed: ' + ex.message);
  }
}

async function steerDelete(fileId) {
  // FIX 10: use gmDanger for destructive action + showToast feedback
  if (!(await gmDanger('Delete Steering File', 'This rule will no longer be injected into prompts.', 'Delete'))) return;
  try {
    const r = await fetch(`/api/steering/${encodeURIComponent(fileId)}``,{method:'DELETE'});
    const d = await r.json();
    showToast(d.deleted !== false ? '🗑 Steering file deleted' : '⚠️ File not found', d.deleted !== false ? 'ok' : 'err', 2000);
  } catch(ex) { showToast('⚠️ Delete failed', 'err', 2000); }
  renderSteering();
}

async function steerLearnFromChat() {
  showToast('🧠 Learning from your chat history…');
  try {
    const r = await fetch('/api/steering/learn/from-chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({limit:100})});
    const d = await r.json();
    if (d.ok) {
      gmAlert(`✅ Learned ${d.stored_patterns} patterns from your chat history!\n\nClick "Promote Patterns" to create a steering file.`);
      renderSteering();
    } else {
      gmAlert(d.error||'Nothing to learn yet. Chat more first!');
    }
  } catch(ex) { gmAlert('Learn failed: '+ex.message); }
}

async function steerPromotePatterns() {
  try {
    const r = await fetch('/api/steering/learn/promote',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({min_confidence:0.5})});
    const d = await r.json();
    if (d.ok) {
      gmAlert(`✅ Promoted ${d.patterns_promoted} patterns into a new steering file!\n\n"${d.file_id}" is now active.`);
      renderSteering();
    } else {
      gmAlert(d.error||'No patterns ready to promote yet. Run Auto-Learn first.');
    }
  } catch(ex) { gmAlert('Promote failed: '+ex.message); }
}


// ══════════════════════════════════════════════════════════════════
//  BUGBOT — AI PR / Code Reviewer
// ══════════════════════════════════════════════════════════════════
async function renderBugBot() {
  const pane = document.getElementById('pane-bugbot');
  if (!pane) return;

  const [reviews, stats] = await Promise.all([
    fetch('/api/bugbot/reviews?limit=10').then(r=>r.ok?r.json():null).catch(()=>({reviews:[]})),
    fetch('/api/bugbot/stats').then(r=>r.ok?r.json():null).catch(()=>({})),
  ]);

  pane.innerHTML = `
  

  <div style="padding:20px;max-width:1000px;margin:0 auto">
    <div class="section-head">
      <div>
        <h2>🐛 BugBot — AI Code Reviewer</h2>
        <p>Like Cursor BugBot — review diffs, files, and GitHub PRs with OWASP-aware AI analysis</p>
      </div>
    </div>

    <!-- Stats row -->
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px">
      ${[
        ['📋','Reviews',stats.total_reviews||0],
        ['📊','Avg Score',`${stats.avg_score||0}/100`],
        ['🐛','Issues Found',stats.total_issues_found||0],
        ['🚨','Critical',stats.by_severity?.critical||0],
      ].map(([icon,label,val])=>`
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:14px;text-align:center">
          <div style="font-size:22px">${icon}</div>
          <div style="font-size:10px;color:var(--text-3);text-transform:uppercase;letter-spacing:.5px">${label}</div>
          <div style="font-size:20px;font-weight:700;color:var(--text-0)">${val}</div>
        </div>`).join('')}
    </div>

    <!-- Review tabs -->
    <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap">
      <button class="btn" id="bb-tab-diff" onclick="bbShowTab('diff')" style="background:var(--accent);color:#fff">📄 Review Diff</button>
      <button class="btn-sm" id="bb-tab-git" onclick="bbShowTab('git')">🌿 Git Diff</button>
      <button class="btn-sm" id="bb-tab-file" onclick="bbShowTab('file')">📁 Review File</button>
      <button class="btn-sm" id="bb-tab-pr" onclick="bbShowTab('pr')">🐙 GitHub PR</button>
      <button class="btn-sm" id="bb-tab-history" onclick="bbShowTab('history')">📋 History</button>
    </div>

    <div id="bb-tab-content">
      <!-- Diff review (default) -->
      <div id="bb-pane-diff">
        <div style="margin-bottom:10px;font-size:12px;color:var(--text-2)">Paste a git diff or any code diff for AI review</div>
        <textarea id="bb-diff-input" rows="12" style="width:100%;background:var(--bg-2);border:1px solid var(--border);border-radius:10px;color:var(--text-0);font-size:12px;font-family:monospace;padding:12px;resize:vertical;box-sizing:border-box" placeholder="+++ b/auth.py
@@ -45,6 +45,12 @@
+async def login(username: str, password: str):
+    user = db.execute(f'SELECT * FROM users WHERE username={username}')
+    if user and user.password == password:
+        return {'token': secrets.token_hex(32)}"></textarea>
        <div style="display:flex;gap:8px;margin-top:8px">
          <input id="bb-review-title" placeholder="Review title (optional)" style="flex:1;background:var(--bg-2);border:1px solid var(--border);border-radius:7px;color:var(--text-0);font-size:12px;padding:6px 10px">
          <button class="btn" onclick="bbReviewDiff()">🔍 Review</button>
          <button class="btn-sm" onclick="bbReviewDiffStream()">⚡ Stream</button>
        </div>
      </div>
      <div id="bb-pane-git" style="display:none">
        <div style="font-size:12px;color:var(--text-2);margin-bottom:10px">Review your current local git changes</div>
        <div style="display:flex;gap:8px;margin-bottom:12px">
          <label style="font-size:12px;color:var(--text-1);display:flex;align-items:center;gap:5px">
            <input type="checkbox" id="bb-staged"> Staged only
          </label>
          <input id="bb-branch-ref" placeholder="branch (optional)" style="background:var(--bg-2);border:1px solid var(--border);border-radius:7px;color:var(--text-0);font-size:12px;padding:6px 10px">
          <button class="btn" onclick="bbReviewGit()">🌿 Review Git Diff</button>
        </div>
      </div>
      <div id="bb-pane-file" style="display:none">
        <div style="display:flex;gap:8px;margin-bottom:8px">
          <input id="bb-file-name" placeholder="filename.py" style="background:var(--bg-2);border:1px solid var(--border);border-radius:7px;color:var(--text-0);font-size:12px;padding:6px 10px;width:200px">
          <button class="btn-sm" onclick="bbLoadCurrentFile()">← Load current preview file</button>
        </div>
        <textarea id="bb-file-content" rows="12" style="width:100%;background:var(--bg-2);border:1px solid var(--border);border-radius:10px;color:var(--text-0);font-size:12px;font-family:monospace;padding:12px;resize:vertical;box-sizing:border-box" placeholder="Paste file content to review…"></textarea>
        <button class="btn" onclick="bbReviewFile()" style="margin-top:8px">📁 Review File</button>
      </div>
      <div id="bb-pane-pr" style="display:none">
        <div style="font-size:12px;color:var(--text-2);margin-bottom:10px">Review a GitHub Pull Request (requires GITHUB_TOKEN)</div>
        <input id="bb-pr-url" placeholder="https://github.com/owner/repo/pull/123" style="width:100%;background:var(--bg-2);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:13px;padding:8px 12px;box-sizing:border-box;margin-bottom:10px">
        <div style="display:flex;gap:8px">
          <label style="font-size:12px;color:var(--text-1);display:flex;align-items:center;gap:5px">
            <input type="checkbox" id="bb-post-comment"> Auto-post comment to PR
          </label>
          <button class="btn" onclick="bbReviewPR()">🐙 Review PR</button>
        </div>
      </div>
      <div id="bb-pane-history" style="display:none">
        ${(reviews.reviews||[]).map(r=>`
          <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:12px;margin-bottom:8px;display:flex;align-items:center;gap:10px;cursor:pointer" onclick="bbShowReview(${JSON.stringify(r.id)})">
            <div style="width:44px;height:44px;border-radius:50%;background:var(--bg-3);display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:700;color:${r.score>=80?'var(--success)':r.score>=60?'var(--warning)':'var(--danger)'}">
              ${r.score}
            </div>
            <div style="flex:1">
              <div style="font-weight:600;color:var(--text-0)">${escHtml(r.title||'Untitled')}</div>
              <div style="font-size:11px;color:var(--text-3)">${new Date(r.created_at).toLocaleString()}</div>
            </div>
            <span class="bb-severity-badge ${r.severity||'low'}">${r.severity||'low'}</span>
          </div>`).join('') || '<div style="color:var(--text-3);padding:20px;text-align:center">No reviews yet</div>'}
      </div>
    </div>

    <div id="bb-results" style="margin-top:16px"></div>
  </div>`;
}

function bbShowTab(tab) {
  // FIX 6: null-safe getElementById (pane may not exist during partial render)
  ['diff','git','file','pr','history'].forEach(t=>{
    const paneEl = document.getElementById(`bb-pane-${t}`);
    if (paneEl) paneEl.style.display = t===tab?'block':'none';
    const btn = document.getElementById(`bb-tab-${t}`);
    if (btn) { btn.style.background=t===tab?'var(--accent)':''; btn.style.color=t===tab?'#fff':''; }
  });
}

async function bbReviewDiff() {
  const diff  = document.getElementById('bb-diff-input')?.value||'';
  const title = document.getElementById('bb-review-title')?.value||'Review';
  if (!diff.trim()) { gmAlert('Paste a diff first'); return; }
  showToast('🔍 Reviewing diff…');
  try {
    const r = await fetch('/api/bugbot/review/diff',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({diff,title})});
    const d = await r.json();
    bbShowResults(d);
  } catch(ex) { gmAlert('Review failed: '+ex.message); }
}

async function bbReviewDiffStream() {
  const diff  = document.getElementById('bb-diff-input')?.value||'';
  const title = document.getElementById('bb-review-title')?.value||'Review';
  if (!diff.trim()) { gmAlert('Paste a diff first'); return; }
  const results = document.getElementById('bb-results');
  if (results) results.innerHTML = '<div style="color:var(--text-2);font-size:12px;padding:12px;background:var(--bg-2);border-radius:8px;font-family:monospace;white-space:pre-wrap" id="bb-stream-log">Analyzing…</div>';
  try {
    const resp = await fetch('/api/bugbot/review/diff/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({diff,title})});
    // FIX 4: null guard on resp.body before streaming
    if (!resp.ok || !resp.body) { gmAlert(`Stream review failed: HTTP ${resp.status}`); return; }
    const reader=resp.body.getReader(); const dec=new TextDecoder(); let buf='';
    while(true){const{done,value}=await reader.read();if(done)break;buf+=dec.decode(value,{stream:true});
      const parts=buf.split('\n\n');buf=parts.pop()||'';
      for(const part of parts){if(!part.startsWith('data:'))continue;
        try{const d=JSON.parse(part.slice(5).trim());
          if(d.type==='chunk'){const el=document.getElementById('bb-stream-log');if(el)el.textContent+=d.text||'';}
          else if(d.type==='done'){bbShowResults(d);}
        }catch(e){}}
    }
  } catch(ex) { gmAlert('Stream failed: '+ex.message); }
}

async function bbReviewGit() {
  const staged = document.getElementById('bb-staged')?.checked||false;
  const branch = document.getElementById('bb-branch-ref')?.value||'';
  showToast('🌿 Reviewing git diff…');
  try {
    const r = await fetch('/api/bugbot/review/git',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({staged,branch})});
    const d = await r.json();
    bbShowResults(d);
  } catch(ex) { gmAlert('Review failed: '+ex.message); }
}

async function bbReviewFile() {
  const content  = document.getElementById('bb-file-content')?.value||'';
  const filename = document.getElementById('bb-file-name')?.value||'file.py';
  if (!content.trim()) { gmAlert('Paste file content first'); return; }
  showToast('📁 Reviewing file…');
  try {
    const r = await fetch('/api/bugbot/review/file',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content,filename})});
    const d = await r.json();
    bbShowResults(d);
  } catch(ex) { gmAlert('Review failed: '+ex.message); }
}

async function bbReviewPR() {
  const pr_url     = document.getElementById('bb-pr-url')?.value||'';
  const auto_post  = document.getElementById('bb-post-comment')?.checked||false;
  if (!pr_url.includes('github.com')) { gmAlert('Enter a valid GitHub PR URL'); return; }
  showToast('🐙 Fetching and reviewing PR…');
  try {
    const r = await fetch('/api/bugbot/review/github-pr',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pr_url,auto_post_comment:auto_post})});
    const d = await r.json();
    bbShowResults(d);
  } catch(ex) { gmAlert('PR review failed: '+ex.message); }
}

function bbShowResults(d) {
  const el = document.getElementById('bb-results');
  if (!el) return;
  const issues  = d.issues||[];
  const score   = d.score||75;
  const sev     = d.severity||'low';
  const col     = score>=80?'var(--success)':score>=60?'var(--warning)':'var(--danger)';
  const bySev   = {};
  issues.forEach(i=>{ bySev[i.severity]=(bySev[i.severity]||0)+1; });

  el.innerHTML = `
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:14px;overflow:hidden">
      <div style="padding:16px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:16px">
        <div style="width:56px;height:56px;border-radius:50%;border:3px solid ${col};display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:800;color:${col}">${score}</div>
        <div>
          <div style="font-size:14px;font-weight:700;color:var(--text-0)">Code Quality Score</div>
          <div style="font-size:12px;color:var(--text-2);margin-top:2px">${escHtml(d.summary||'')}</div>
        </div>
        <div style="margin-left:auto;display:flex;gap:6px;flex-wrap:wrap">
          ${Object.entries(bySev).map(([s,c])=>`<span class="bb-severity-badge ${s}">${s}: ${c}</span>`).join('')}
        </div>
      </div>
      <div style="padding:16px">
        ${issues.length===0?'<div style="color:var(--success);text-align:center;padding:12px">✅ No issues found!</div>':
          issues.map(i=>`
            <div class="bb-issue-card ${i.severity||'low'}">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
                <span class="bb-severity-badge ${i.severity||'low'}">${i.severity||'low'}</span>
                <strong style="font-size:12px;color:var(--text-0)">${escHtml(i.name||i.description?.slice(0,50)||'Issue')}</strong>
                ${i.file?`<span style="font-size:10px;color:var(--text-3);margin-left:auto">${escHtml(i.file)}${i.line?':'+i.line:''}</span>`:''}
              </div>
              <div style="font-size:12px;color:var(--text-2)">${escHtml(i.description||'')}</div>
              ${i.fix?`<div style="font-size:11px;color:var(--accent);margin-top:4px;font-family:monospace">Fix: ${escHtml(i.fix)}</div>`:''}
            </div>`).join('')
        }
        ${(d.positives||[]).length?`<div style="margin-top:10px;padding:10px 12px;background:rgba(61,186,122,.08);border-radius:8px;border:1px solid var(--success)33"><strong style="color:var(--success);font-size:12px">✅ Positives:</strong>${(d.positives||[]).map(p=>`<div style="font-size:11px;color:var(--text-2);margin-top:2px">• ${escHtml(p)}</div>`).join('')}</div>`:''}
      </div>
    </div>`;
}

async function bbLoadCurrentFile() {
  const ta = document.getElementById('bb-file-content');
  const fn = document.getElementById('bb-file-name');
  try {
    const r = await fetch('/preview/index.html');
    const t = await r.text();
    if(ta) ta.value=t.slice(0,20000);
    if(fn) fn.value='index.html';
  } catch(ex) { gmAlert('Could not load file'); }
}

async function bbShowReview(reviewId) {
  // FIX 5: try/catch + resp.ok check + error feedback
  try {
    const r = await fetch(`/api/bugbot/reviews/${encodeURIComponent(reviewId)}`);
    if (!r.ok) { showToast(`⚠️ Could not load review (HTTP ${r.status})`); return; }
    const d = await r.json();
    if (d.ok === false) { showToast(`⚠️ ${d.error || 'Review not found'}`); return; }
    bbShowResults({...d, issues:d.issues||[], summary:''});
    bbShowTab('diff');
  } catch(ex) { showToast('⚠️ Failed to load review: ' + ex.message); }
}


// ══════════════════════════════════════════════════════════════════
//  PROJECT HEALTH DASHBOARD
// ══════════════════════════════════════════════════════════════════
async function renderHealth() {
  const pane = document.getElementById('pane-health');
  if (!pane) return;
  pane.innerHTML = '<div style="padding:20px;color:var(--text-2)">Computing project health…</div>';

  try {
    const h = await fetch('/api/ambient/health').then(r=>r.ok?r.json():null);
    const grade_color = h.grade==='A'?'var(--success)':h.grade==='B'?'var(--info)':h.grade==='C'?'var(--warning)':'var(--danger)';
    const dim_icons = {complexity:'🔥',security:'🔒',debt:'💳',docs:'📚',deps:'📦'};
    const dim_labels = {complexity:'Complexity',security:'Security',debt:'Tech Debt',docs:'Documentation',deps:'Dependencies'};

    pane.innerHTML = `
    <div style="padding:20px;max-width:900px;margin:0 auto">
      <div class="section-head">
        <div><h2>💊 Project Health</h2><p>Automated scoring across complexity, security, tech debt, documentation, and dependencies</p></div>
        <button class="btn-sm" onclick="renderHealth()">🔄 Refresh</button>
      </div>

      <!-- Overall score hero -->
      <div style="background:linear-gradient(135deg,var(--bg-2),var(--bg-3));border:1px solid var(--border);border-radius:16px;padding:24px;margin-bottom:20px;display:flex;align-items:center;gap:24px">
        <div style="width:100px;height:100px;border-radius:50%;border:5px solid ${grade_color};display:flex;flex-direction:column;align-items:center;justify-content:center;flex-shrink:0">
          <div style="font-size:32px;font-weight:800;color:${grade_color}">${h.overall||0}</div>
          <div style="font-size:14px;font-weight:700;color:${grade_color}">${h.grade||'?'}</div>
        </div>
        <div>
          <div style="font-size:20px;font-weight:700;color:var(--text-0);margin-bottom:6px">Overall Health: ${h.grade||'?'}</div>
          <div style="font-size:13px;color:var(--text-2);line-height:1.6">💡 Tip: <strong>${escHtml(h.tip||'')}</strong></div>
        </div>
      </div>

      <!-- Score bars -->
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px;margin-bottom:20px">
        ${Object.entries(h.scores||{}).map(([key,val])=>{
          const score = val;
          const col   = score>=80?'var(--success)':score>=60?'var(--warning)':'var(--danger)';
          const dets  = (h.details||{})[key]||[];
          return `
            <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
                <span style="font-size:20px">${dim_icons[key]||'📊'}</span>
                <span style="font-weight:600;color:var(--text-0)">${dim_labels[key]||key}</span>
                <span style="margin-left:auto;font-size:18px;font-weight:700;color:${col}">${score}</span>
              </div>
              <div style="height:6px;background:var(--bg-4);border-radius:3px;margin-bottom:10px">
                <div style="height:100%;width:${score}%;background:${col};border-radius:3px;transition:width .5s"></div>
              </div>
              ${dets.map(d=>`<div style="font-size:11px;color:var(--text-2);padding:2px 0">• ${escHtml(d)}</div>`).join('')}
            </div>`;
        }).join('')}
      </div>

      <!-- Quick actions -->
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px">
        <div style="font-size:13px;font-weight:700;margin-bottom:10px">⚡ Quick Fixes</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn-sm" onclick="nav('bugbot')">🐛 Run Code Review</button>
          <button class="btn-sm" onclick="bbRunSecurityScan()">🔒 Security Scan</button>
          <button class="btn-sm" onclick="bbRunDepAudit()">📦 Audit Dependencies</button>
          <button class="btn-sm" onclick="nav('codeindex');ciIndexNow()">🕸️ Index Codebase</button>
          <button class="btn-sm" onclick="nav('ambient');ambientScan()">🌊 Ambient Scan</button>
        </div>
      </div>

      <!-- History -->
      <div style="margin-top:16px" id="health-history"></div>
    </div>`;

    bbLoadHealthHistory();
  } catch(ex) {
    pane.innerHTML = `<div style="padding:20px;color:var(--danger)">Health check failed: ${ex.message}</div>`;
  }
}

async function bbLoadHealthHistory() {
  try {
    const r = await fetch('/api/ambient/health/history?limit=5');
    const d = await r.json();
    const el = document.getElementById('health-history');
    if (!el || !d.snapshots?.length) return;
    el.innerHTML = `
      <div style="font-size:13px;font-weight:700;margin-bottom:8px">📈 History</div>
      <div style="display:flex;gap:8px;overflow-x:auto;padding-bottom:4px">
        ${d.snapshots.map(s=>`
          <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:10px 14px;flex-shrink:0;text-align:center;min-width:80px">
            <div style="font-size:20px;font-weight:700;color:${s.overall_score>=80?'var(--success)':s.overall_score>=60?'var(--warning)':'var(--danger)'}">${s.overall_score}</div>
            <div style="font-size:10px;color:var(--text-3)">${new Date(s.created_at).toLocaleDateString()}</div>
          </div>`).join('')}
      </div>`;
  } catch(e) {}
}

async function bbRunSecurityScan() {
  nav('gitai'); setTimeout(()=>gitaiRunSecurity(), 400);
}
async function bbRunDepAudit() {
  nav('gitai'); setTimeout(()=>gitaiRunDepAudit(), 400);
}


// ══════════════════════════════════════════════════════════════════
//  GIT AI — Natural Language Git + Changelog + Deps + Security
// ══════════════════════════════════════════════════════════════════
async function renderGitAI() {
  const pane = document.getElementById('pane-gitai');
  if (!pane) return;

  let gitStatus = {};
  try { gitStatus = await fetch('/api/gitai/status').then(r=>r.ok?r.json():null); } catch(e) {}

  pane.innerHTML = `
  

  <div style="padding:20px;max-width:900px;margin:0 auto">
    <div class="section-head">
      <div><h2>🌿 Git AI</h2><p>Natural language git, AI changelogs, dependency audits, and security scanning</p></div>
    </div>

    <!-- Git status bar -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:12px 16px;margin-bottom:16px;display:flex;gap:16px;align-items:center;font-size:12px">
      <span>🌿 <strong style="color:var(--accent)">${escHtml(gitStatus.branch||'(no branch)')}</strong></span>
      <span style="color:var(--text-3)">|</span>
      <span>${gitStatus.changed_count||0} changed files</span>
      ${gitStatus.clean?'<span style="color:var(--success)">✅ Clean</span>':'<span style="color:var(--warning)">⚠️ Uncommitted changes</span>'}
      <button class="btn-sm" onclick="gitaiRefreshStatus()">↺</button>
    </div>

    <!-- Tabs -->
    <div style="display:flex;border-bottom:1px solid var(--border);margin-bottom:16px">
      <button class="gitai-tab active" id="gat-nl" onclick="gitaiTab('nl',this)">💬 Natural Language</button>
      <button class="gitai-tab" id="gat-commit" onclick="gitaiTab('commit',this)">✍ AI Commit</button>
      <button class="gitai-tab" id="gat-changelog" onclick="gitaiTab('changelog',this)">📋 Changelog</button>
      <button class="gitai-tab" id="gat-deps" onclick="gitaiTab('deps',this)">📦 Dep Audit</button>
      <button class="gitai-tab" id="gat-security" onclick="gitaiTab('security',this)">🔒 Security</button>
    </div>

    <!-- Natural Language Git -->
    <div id="gitai-pane-nl">
      <div style="font-size:12px;color:var(--text-2);margin-bottom:10px">Ask Git anything in plain English — like Cursor's natural language git interface</div>
      <div style="display:flex;gap:8px">
        <input id="gitai-nl-input" placeholder="e.g. 'show what changed in the last 5 commits' or 'create branch feature/payments'" style="flex:1;background:var(--bg-2);border:1px solid var(--border);border-radius:9px;color:var(--text-0);font-size:13px;padding:10px 14px" onkeydown="if(event.key==='Enter')gitaiNLRun()">
        <button class="btn" onclick="gitaiNLRun()">Ask</button>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px">
        ${['show last 10 commits','what changed today?','create branch feature/payments','stage all changes','show diff of HEAD~1','revert last commit'].map(s=>`<button class="btn-sm" onclick="document.getElementById('gitai-nl-input').value='${s}';gitaiNLRun()" style="font-size:11px">${s}</button>`).join('')}
      </div>
      <div id="gitai-nl-result"></div>
    </div>

    <!-- AI Commit -->
    <div id="gitai-pane-commit" style="display:none">
      <div style="font-size:12px;color:var(--text-2);margin-bottom:10px">Generate a semantic commit message from your staged/unstaged changes</div>
      <input id="gitai-commit-hint" placeholder="Optional hint (e.g. 'adding auth feature')" style="width:100%;background:var(--bg-2);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:12px;padding:8px 12px;box-sizing:border-box;margin-bottom:8px">
      <div style="display:flex;gap:8px">
        <button class="btn" onclick="gitaiGenerateCommit(false)">✍ Generate Message</button>
        <button class="btn-sm" onclick="gitaiGenerateCommit(true)">⚡ Generate &amp; Commit</button>
      </div>
      <div id="gitai-commit-result"></div>
    </div>

    <!-- Changelog -->
    <div id="gitai-pane-changelog" style="display:none">
      <div style="font-size:12px;color:var(--text-2);margin-bottom:10px">Auto-generate CHANGELOG.md from git history</div>
      <div style="display:flex;gap:8px;margin-bottom:8px;flex-wrap:wrap">
        <input id="gitai-cl-version" placeholder="New version (e.g. v2.0.0)" style="background:var(--bg-2);border:1px solid var(--border);border-radius:7px;color:var(--text-0);font-size:12px;padding:6px 10px;width:160px">
        <input id="gitai-cl-since" placeholder="Since (e.g. v1.0.0 or 2025-01-01)" style="background:var(--bg-2);border:1px solid var(--border);border-radius:7px;color:var(--text-0);font-size:12px;padding:6px 10px;flex:1">
        <button class="btn" onclick="gitaiChangelog()">📋 Generate Changelog</button>
      </div>
      <div id="gitai-cl-result"></div>
    </div>

    <!-- Dependencies -->
    <div id="gitai-pane-deps" style="display:none">
      <div style="font-size:12px;color:var(--text-2);margin-bottom:10px">Audit requirements.txt and package.json for outdated/vulnerable packages</div>
      <button class="btn" onclick="gitaiRunDepAudit()">📦 Audit Dependencies</button>
      <div id="gitai-deps-result"></div>
    </div>

    <!-- Security -->
    <div id="gitai-pane-security" style="display:none">
      <div style="font-size:12px;color:var(--text-2);margin-bottom:10px">OWASP Top 10 scanner across your codebase — finds SQL injection, XSS, hardcoded secrets, and more</div>
      <div style="display:flex;gap:8px;margin-bottom:10px">
        <select id="gitai-sec-target" style="background:var(--bg-2);border:1px solid var(--border);border-radius:7px;color:var(--text-0);font-size:12px;padding:6px 8px">
          <option value="all">All files</option>
          <option value="backend">Backend only</option>
          <option value="preview">Preview only</option>
        </select>
        <button class="btn" onclick="gitaiRunSecurity()">🔒 Run Security Scan</button>
      </div>
      <div id="gitai-sec-result"></div>
    </div>
  </div>`;
}

function gitaiTab(tab, el) {
  ['nl','commit','changelog','deps','security'].forEach(t=>{
    document.getElementById(`gitai-pane-${t}`).style.display=t===tab?'block':'none';
    document.getElementById(`gat-${t}`)?.classList.toggle('active',t===tab);
  });
}

async function gitaiNLRun() {
  const query = document.getElementById('gitai-nl-input')?.value||'';
  if (!query.trim()) return;
  const el = document.getElementById('gitai-nl-result');
  window._gitaiLastQuery = query;  // FIX 6: store query for onclick handler
  if (el) el.innerHTML='<div style="color:var(--text-2);padding:8px">Thinking…</div>';
  try {
    const r = await fetch('/api/gitai/nl-git',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query,dry_run:true})});
    const d = await r.json();
    if (!el) return;
    el.innerHTML=`
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:14px;margin-top:10px">
        <div style="font-size:12px;color:var(--text-0);font-weight:600;margin-bottom:8px">${escHtml(d.explanation||'')}</div>
        ${(d.commands||[]).map(c=>`<div class="gitai-cmd">${escHtml(c.cmd?.join(' ')||'')} ${c.safe?'':'⚠️ unsafe'}</div>`).join('<br>')}
        ${d.warnings?.length?`<div style="margin-top:8px;font-size:11px;color:var(--warning)">⚠️ ${d.warnings.join(' | ')}</div>`:''}
        <div style="margin-top:10px;display:flex;gap:6px">
          <button class="btn-sm" onclick="gitaiNLExecute(_gitaiLastQuery)" ${d.is_destructive?'style="color:var(--danger)"':''}>▶ Execute ${d.is_destructive?'(DESTRUCTIVE!)':''}</button>
        </div>
      </div>`;
  } catch(ex) { if(el)el.innerHTML=`<div style="color:var(--danger)">Error: ${ex.message}</div>`; }
}

async function gitaiNLExecute(query) {
  const ok = await gmConfirm(`Execute: "${query}"?`);
  if (!ok) return;
  try {
    const r = await fetch('/api/gitai/nl-git',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query,dry_run:false,allow_unsafe:false})});
    const d = await r.json();
    const el = document.getElementById('gitai-nl-result');
    if (el) el.innerHTML+=`<div class="gitai-result">${(d.results||[]).map(r=>`${r.cmd}\n${r.stdout||r.error||''}`).join('\n\n')}</div>`;
  } catch(ex) { gmAlert('Execute failed: '+ex.message); }
}

async function gitaiRefreshStatus() {
  // FIX 8: only update status bar — don't call renderGitAI() which wipes tab state
  try {
    const s = await fetch('/api/gitai/status').then(r=>r.ok?r.json():null);
    showToast('🌿 ' + (s.branch||'no branch') + ' · ' + (s.changed_count||0) + ' changes', 'ok', 2000);
    // Update status bar elements if they exist without full re-render
    const branchEl = document.querySelector('#pane-gitai [data-field="branch"]');
    const cleanEl  = document.querySelector('#pane-gitai [data-field="clean"]');
    if (!branchEl) { renderGitAI(); return; }  // fall back to full render if not found
  } catch(e) {}
}

async function gitaiGenerateCommit(autoCommit) {
  const hint = document.getElementById('gitai-commit-hint')?.value||'';
  const el   = document.getElementById('gitai-commit-result');
  if(el) el.innerHTML='<div style="color:var(--text-2);padding:8px">Generating commit message…</div>';
  try {
    window._gitaiLastCommitMsg = '';  // FIX 7: reset before fetch
    const r = await fetch('/api/gitai/commit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({auto_commit:autoCommit,hint})});
    const d = await r.json();
    window._gitaiLastCommitMsg = d.message||'';  // FIX 7: store for copy
    if(el) el.innerHTML=`
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:14px;margin-top:10px">
        <div style="font-size:13px;font-family:monospace;color:var(--text-0);padding:10px;background:var(--bg-3);border-radius:7px;margin-bottom:8px" id="gitai-commit-msg">${escHtml(d.message||'')}</div>
        ${d.committed?'<div style="color:var(--success)">✅ Committed!</div>':''}
        <button class="btn-sm" onclick="navigator.clipboard.writeText(window._gitaiLastCommitMsg||'').then(()=>showToast('📋 Copied','ok',1200))">📋 Copy</button>  <!-- FIX 7 -->
      </div>`;
  } catch(ex) { if(el)el.innerHTML=`<div style="color:var(--danger)">Error: ${ex.message}</div>`; }
}

async function gitaiChangelog() {
  const version = document.getElementById('gitai-cl-version')?.value||'';
  const since   = document.getElementById('gitai-cl-since')?.value||'';
  const el = document.getElementById('gitai-cl-result');
  if(el) el.innerHTML='<div style="color:var(--text-2);padding:8px">Generating changelog…</div>';
  try {
    const r = await fetch('/api/gitai/changelog',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({version,since,limit:50})});
    const d = await r.json();
    if(el) el.innerHTML=`
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:14px;margin-top:10px">
        <div style="font-size:12px;color:var(--success);margin-bottom:8px">✅ ${d.commits_used} commits → ${escHtml(d.changelog_path||'')}</div>
        <div style="font-size:11px;font-family:monospace;white-space:pre-wrap;color:var(--text-1);max-height:300px;overflow-y:auto">${escHtml(d.entry||'')}</div>
      </div>`;
  } catch(ex) { if(el)el.innerHTML=`<div style="color:var(--danger)">Error: ${ex.message}</div>`; }
}

async function gitaiRunDepAudit() {
  const el = document.getElementById('gitai-deps-result');
  if(el) el.innerHTML='<div style="color:var(--text-2);padding:8px">Auditing dependencies…</div>';
  try {
    const r = await fetch('/api/gitai/deps/audit');
    const d = await r.json();
    if(el) el.innerHTML=`
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:14px;margin-top:10px">
        <div style="font-size:12px;margin-bottom:10px"><strong>${d.packages_scanned||0}</strong> packages scanned · <strong>${d.issues_found||0}</strong> issues · <strong style="color:var(--danger)">${d.critical_count||0}</strong> critical</div>
        ${(d.findings||[]).map(f=>`
          <div style="padding:6px 0;border-top:1px solid var(--border);font-size:11px">
            <span class="bb-severity-badge ${f.severity||'low'}">${f.severity||'info'}</span>
            <strong style="color:var(--text-0);margin-left:6px">${escHtml(f.name||'')}</strong> ${escHtml(f.current_version||'')} → ${escHtml(f.latest_version||'?')}
            <div style="color:var(--text-2);margin-top:2px">${escHtml(f.description||'')}</div>
            ${f.recommendation?`<div style="color:var(--accent);font-family:monospace;font-size:10px">${escHtml(f.recommendation)}</div>`:''}
          </div>`).join('')||'<div style="color:var(--success)">✅ No issues found</div>'}
        ${d.upgrade_commands?.python?`<div style="margin-top:10px;font-family:monospace;font-size:10px;color:var(--text-3)">${escHtml(d.upgrade_commands.python)}</div>`:''}
      </div>`;
  } catch(ex) { if(el)el.innerHTML=`<div style="color:var(--danger)">Error: ${ex.message}</div>`; }
}

async function gitaiRunSecurity() {
  const target = document.getElementById('gitai-sec-target')?.value||'all';
  const el = document.getElementById('gitai-sec-result');
  if(el) el.innerHTML='<div style="color:var(--text-2);padding:8px">Scanning for OWASP vulnerabilities…</div>';
  try {
    const r = await fetch('/api/gitai/security/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target,max_files:80})});
    const d = await r.json();
    const col = d.security_score>=80?'var(--success)':d.security_score>=60?'var(--warning)':'var(--danger)';
    if(el) el.innerHTML=`
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:14px;margin-top:10px">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
          <div style="width:48px;height:48px;border-radius:50%;border:3px solid ${col};display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:700;color:${col}">${d.security_score||0}</div>
          <div>
            <div style="font-weight:700;color:var(--text-0)">Security Score: ${d.grade||'?'}</div>
            <div style="font-size:11px;color:var(--text-3)">${d.files_scanned||0} files · ${d.total_findings||0} findings</div>
          </div>
        </div>
        ${(d.vulnerabilities||[]).slice(0,20).map(v=>`
          <div class="bb-issue-card ${v.severity||'low'}">
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">
              <span class="bb-severity-badge ${v.severity}">${v.severity}</span>
              <strong style="font-size:11px">${escHtml(v.name||'')}</strong>
              <span style="font-size:10px;color:var(--text-3);margin-left:auto">${escHtml(v.file||'')}:${v.line||0}</span>
            </div>
            <div style="font-size:11px;color:var(--text-2)">${escHtml(v.description||'')}</div>
          </div>`).join('')||'<div style="color:var(--success)">✅ No security issues found</div>'}
      </div>`;
  } catch(ex) { if(el)el.innerHTML=`<div style="color:var(--danger)">Error: ${ex.message}</div>`; }
}


// ══════════════════════════════════════════════════════════════════
//  AMBIENT AGENT — always-on background suggestions
// ══════════════════════════════════════════════════════════════════
async function renderAmbient() {
  const pane = document.getElementById('pane-ambient');
  if (!pane) return;

  const [suggs, tasks] = await Promise.all([
    fetch('/api/ambient/suggestions?limit=30').then(r=>r.ok?r.json():null).catch(()=>({suggestions:[]})),
    fetch('/api/ambient/tasks?limit=10').then(r=>r.ok?r.json():null).catch(()=>({tasks:[]})),
  ]);

  const sev_icons = {high:'⚠️',medium:'⚡',info:'💡',critical:'🚨'};
  const cat_labels = {todo:'📌 TODO',security:'🔒 Security',complexity:'🔥 Complexity',error_handling:'⚠️ Error Handling',maintenance:'🔧 Maintenance'};

  pane.innerHTML = `
  

  <div style="padding:20px;max-width:900px;margin:0 auto">
    <div class="section-head">
      <div><h2>🌊 Ambient Agent</h2><p>Always-on background intelligence — proactive suggestions, background tasks, project scanning</p></div>
      <div style="display:flex;gap:8px">
        <button class="btn" onclick="ambientScan()">🔍 Run Scan</button>
        <button class="btn-sm" onclick="ambientNewTask()">＋ Background Task</button>
        <button class="btn-sm" style="color:var(--danger)" onclick="ambientClearAll()">🗑 Clear</button>
      </div>
    </div>

    <!-- Stats -->
    <div style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap">
      ${[
        ['⚠️',suggs.suggestions?.filter(s=>s.severity==='high').length||0,'High Priority'],
        ['⚡',suggs.suggestions?.filter(s=>s.severity==='medium').length||0,'Medium'],
        ['💡',suggs.suggestions?.filter(s=>s.severity==='info').length||0,'Info'],
        ['🔄',tasks.tasks?.filter(t=>t.status==='pending'||t.status==='running').length||0,'Running Tasks'],
      ].map(([icon,count,label])=>`
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:10px 16px;display:flex;align-items:center;gap:8px">
          <span style="font-size:18px">${icon}</span>
          <div><div style="font-size:18px;font-weight:700;color:var(--text-0)">${count}</div><div style="font-size:10px;color:var(--text-3)">${label}</div></div>
        </div>`).join('')}
    </div>

    <!-- Suggestions -->
    <div style="font-size:13px;font-weight:700;margin-bottom:8px">💡 Suggestions (${suggs.suggestions?.length||0})</div>
    <div id="amb-sugg-list">
      ${(suggs.suggestions||[]).map(s=>`
        <div class="amb-card" id="amb-s-${s.id}">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <span>${sev_icons[s.severity]||'ℹ️'}</span>
            <strong style="color:var(--text-0);font-size:12px">${escHtml(s.title||'')}</strong>
            <span class="amb-cat-pill">${cat_labels[s.category]||s.category||''}</span>
            <button onclick="ambientDismiss(${JSON.stringify(s.id)},this)" style="margin-left:auto;background:none;border:none;color:var(--text-3);cursor:pointer;font-size:11px">✕ Dismiss</button>
          </div>
          ${s.description?`<div style="font-size:11px;color:var(--text-2)">${escHtml(s.description)}</div>`:''}
          ${s.file_path?`<div style="font-size:10px;font-family:monospace;color:var(--text-3);margin-top:3px">${escHtml(s.file_path)}${s.line_no?':'+s.line_no:''}</div>`:''}
        </div>`).join('') || '<div style="color:var(--text-3);padding:20px;text-align:center">No suggestions yet. Click "Run Scan" to analyze your project.</div>'}
    </div>

    <!-- Background Tasks -->
    <div style="margin-top:20px;font-size:13px;font-weight:700;margin-bottom:8px">⚙️ Background Tasks (${tasks.tasks?.length||0})</div>
    <div>
      ${(tasks.tasks||[]).map(t=>`
        <div class="amb-card">
          <div style="display:flex;align-items:center;gap:8px">
            <span style="font-size:14px">${t.status==='done'?'✅':t.status==='failed'?'❌':'🔄'}</span>
            <div style="flex:1">
              <div style="font-weight:600;color:var(--text-0);font-size:12px">${escHtml(t.name||'')}</div>
              <div style="font-size:10px;color:var(--text-3)">${t.status} · ${new Date(t.created_at).toLocaleTimeString()}</div>
            </div>
            <button class="btn-sm" onclick="ambientShowTask(${JSON.stringify(t.id)})">View</button>
          </div>
          ${t.result&&t.status!=='pending'?`<div style="font-size:11px;color:var(--text-2);margin-top:6px;font-family:monospace">${escHtml((t.result||'').slice(0,120))}…</div>`:''}
        </div>`).join('') || '<div style="color:var(--text-3);padding:12px">No background tasks yet</div>'}
    </div>
  </div>`;
}

async function ambientScan() {
  showToast('🔍 Running ambient scan…');
  try {
    const r = await fetch('/api/ambient/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({deep:false})});
    if (!r.ok) { gmAlert('Scan failed: server error ' + r.status); return; }
    const d = await r.json();
    showToast(`✅ Found ${d.count||0} suggestions`);
    renderAmbient();
  } catch(ex) { gmAlert('Scan failed: '+ex.message); }
}

async function ambientDismiss(id, btn) {
  await fetch(`/api/ambient/suggestions/${encodeURIComponent(id)}/dismiss`,{method:'POST'}).catch(()=>{});
  document.getElementById(`amb-s-${id}`)?.remove();
}

async function ambientClearAll() {
  const ok = await gmDanger('Clear all suggestions? This cannot be undone.');
  if (!ok) return;
  await fetch('/api/ambient/suggestions/clear',{method:'DELETE'});
  renderAmbient();
}

async function ambientNewTask() {
  const name   = await gmPrompt('Task name:', 'Background Analysis');
  if (!name) return;
  const prompt = await gmPrompt('Task prompt:', 'Analyze the codebase and suggest 3 improvements');
  if (!prompt) return;
  try {
    const r = await fetch('/api/ambient/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,prompt})});
    if (!r.ok) { gmAlert('Task creation failed: server error ' + r.status); return; }
    const d = await r.json();
    if (d.ok === false) { gmAlert('Task creation failed: ' + (d.error||'unknown error')); return; }
    showToast(`🔄 Task "${name}" started`);
    setTimeout(renderAmbient, 2000);
  } catch(ex) { gmAlert('Task failed: '+ex.message); }
}

async function ambientShowTask(taskId) {
  try {
    const r = await fetch(`/api/ambient/tasks/${encodeURIComponent(taskId)}`);
    if (!r.ok) { gmAlert('Failed to load task: server error ' + r.status); return; }
    const d = await r.json();
    if (d.ok === false) { gmAlert('Task not found: ' + (d.error||'')); return; }
    gmAlert(`Task: ${d.name||'—'}\nStatus: ${d.status||'—'}\nAgent: ${d.agent_id||'—'}\n\nResult:\n${(d.result||'(pending…)').slice(0,500)}`);
  } catch(ex) { gmAlert('Failed to load task: ' + ex.message); }
}


// ══════════════════════════════════════════════════════════════════
//  PATCH MASTER NAV — Sprint 17 panes
// ══════════════════════════════════════════════════════════════════
(function patchNavSprint17() {
  const _base = window.nav || function(){};
  window.nav = function masterNav17(pane) {
    _base(pane);
    if (pane==='steering') renderSteering?.();
    if (pane==='bugbot')   renderBugBot?.();
    if (pane==='health')   renderHealth?.();
    if (pane==='gitai')    renderGitAI?.();
    if (pane==='ambient')  renderAmbient?.();
  };
  console.log('%c✅ Sprint 17: Steering, BugBot, Health, Git AI, Ambient loaded', 'color:#9d74f5;font-weight:bold');

  // Auto-run ambient scan every 30 min if pane is open
  setInterval(async () => {
    if (document.getElementById('pane-ambient')?.classList.contains('active')) {
      await fetch('/api/ambient/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).catch(()=>{});
    }
  }, 30 * 60 * 1000);
})();

// Keyboard shortcuts Sprint 17
document.addEventListener('keydown', e => {
  if (!e.metaKey && !e.ctrlKey || !e.shiftKey) return;
  if (e.key==='B') { e.preventDefault(); nav('bugbot'); }
  if (e.key==='N') { e.preventDefault(); nav('steering'); }
  if (e.key==='E') { e.preventDefault(); nav('health'); }
});

