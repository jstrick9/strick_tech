// Agentic OS — Terminal
// Extracted from 01-app-core.js for modularity
// ── Terminal State ───────────────────────────────────────────────
const Terminal = { active:'main', history:{'main':[]}, histIdx:{'main':0}, running:false, reader:null, _runId:null };

async function renderTerminal() {
  const pane = document.getElementById('pane-terminal');
  if (!pane) return;
  // FIX 11: preserve output across pane switches — only render once
  if (pane.querySelector('#term-output')) {
    document.getElementById('term-input')?.focus();
    return;
  }
  let env = {};
  try { const r = await fetch('/api/terminal/env'); env = await r.json(); } catch(e) {}
  const QUICK_COMMANDS = ['ls -la','git status','git log --oneline -5','npm install','npm run dev','npm run build','pip install -r requirements.txt','node --version','python3 --version'];
  pane.innerHTML = `
    <div class="terminal-tabs" id="term-tabs">
      <div class="terminal-tab active" data-sess="main">main</div>
      <div class="terminal-tab" id="term-new-session-btn" style="padding:6px 10px;color:var(--text-3)">＋</div>
    </div>
    <div class="terminal-toolbar" id="term-toolbar">
      ${QUICK_COMMANDS.map((c, idx)=>
        `<button type="button" class="term-btn" data-quick-cmd-idx="${idx}">${escHtml(c)}</button>`).join('')}
      <button type="button" class="term-btn" id="term-kill-btn" style="margin-left:auto;color:var(--danger);display:none" title="Kill running process (Ctrl+C)">■ Kill</button>
      <button type="button" class="term-btn" id="term-clear-btn" style="color:var(--text-3)">Clear</button>
    </div>
    <div class="terminal-container">
      <div class="terminal-output" id="term-output">
        <span class="system">Agentic OS Terminal — ${env.cwd||'/preview'}</span>
        ${env.node?'<span class="system" style="display:block">node '+env.node+'</span>':''}
        ${env.python?'<span class="system" style="display:block">python '+env.python+'</span>':''}
        <span class="system" style="display:block;margin-top:4px">Type a command or click above ↑</span><br>
      </div>
      <div class="terminal-input-row">
        <span class="terminal-prompt">❯</span>
        <input class="terminal-input" id="term-input" placeholder="Enter command…" autocomplete="off" spellcheck="false">
      </div>
    </div>`;
  // BUG FIX (quote-collision, total breakage of the quick-command
  // toolbar): this used to be
  // onclick="termRun(${JSON.stringify(c)})" for every toolbar button.
  // JSON.stringify() ALWAYS wraps its output in literal double quotes,
  // which ALWAYS collide with the onclick attribute's own double-quote
  // delimiters -- this broke EVERY toolbar quick-command button
  // (ls -la, git status, npm install, etc.), not just ones with special
  // characters, since the wrapping quotes themselves are the problem.
  // Reproduced live: clicking any single toolbar button threw "Uncaught
  // SyntaxError: Failed to execute 'click' on 'HTMLElement': Unexpected
  // end of input". Fixed via data-quick-cmd-idx + a delegated listener
  // looking up the real command string from the QUICK_COMMANDS array.
  document.getElementById('term-toolbar')?.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-quick-cmd-idx]');
    if (btn) termRun(QUICK_COMMANDS[Number(btn.dataset.quickCmdIdx)]);
  });
  document.getElementById('term-new-session-btn')?.addEventListener('click', termNewSession);
  document.getElementById('term-kill-btn')?.addEventListener('click', termKill);
  document.getElementById('term-clear-btn')?.addEventListener('click', termClear);
  const input = document.getElementById('term-input');
  if (input) { input.focus(); input.addEventListener('keydown', termKeyDown); input.addEventListener('input', termShowSuggestions); }
  try { const r=await fetch('/api/terminal/history'); const h=await r.json(); Terminal.history['main']=(h||[]).map(x=>x.command||'').reverse(); Terminal.histIdx['main']=Terminal.history['main'].length; } catch(e){}
}
async function termRun(cmd) { const i=document.getElementById('term-input'); if(i) i.value=cmd; await termExecute(cmd); }
async function termExecute(cmd) {
  if (!cmd.trim()) return;
  // FIX 10: prevent concurrent runs
  if (Terminal.running) { termAppend('<span class="stderr">⚠ A command is already running — wait or press ■ Kill</span>'); return; }
  Terminal.running = true;
  const killBtn = document.getElementById('term-kill-btn');
  if (killBtn) killBtn.style.display = '';
  if (!Terminal.history[Terminal.active]) Terminal.history[Terminal.active]=[];
  Terminal.history[Terminal.active].push(cmd);
  Terminal.histIdx[Terminal.active] = Terminal.history[Terminal.active].length;
  const input = document.getElementById('term-input');
  if (input) input.value = '';
  termAppend(`<span class="cmd">❯ ${escHtml(cmd)}</span>`);
  try {
    const resp = await fetch('/api/terminal/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command:cmd,session_id:Terminal.active})});
    // FIX 5: null guard + resp.ok check (FIX 12)
    if (!resp.ok) {
      // The endpoint now returns 400/403 with an explanatory body (blocked
      // command, empty command) instead of burying the reason in an SSE frame.
      let detail = '';
      try { detail = (await resp.json()).error || ''; } catch (e) { /* non-JSON body */ }
      termAppend(`<span class="stderr">${escHtml(detail || 'Server error: HTTP ' + resp.status)}</span><br>`);
      return;
    }
    if (!resp.body) { termAppend(`<span class="stderr">No response body — check server</span>`); return; }
    const reader = resp.body.getReader(); const decoder = new TextDecoder();
    Terminal.reader = reader;
    while(true) {
      const {done,value} = await reader.read(); if(done) break;
      for (const line of decoder.decode(value,{stream:true}).split('\n')) {
        if(!line.startsWith('data:')) continue;
        try {
          const ev=JSON.parse(line.slice(5).trim());
          if(ev.type==='start'&&ev.run_id){Terminal._runId=ev.run_id;}  // FIX 6: capture run_id
          else if(ev.type==='stdout') termAppend(`<span class="stdout">${escHtml(ev.data)}</span>`);
          else if(ev.type==='error') termAppend(`<span class="stderr">${escHtml(ev.data)}</span>`);
          else if(ev.type==='exit') { const c=ev.exit_code===0?'var(--success)':'var(--danger)'; termAppend(`<span style="color:${c};font-size:11px">Exit: ${ev.exit_code} (${ev.duration_ms||0}ms)</span><br>`); }
        } catch(e){}
      }
    }
  } catch(e) { termAppend(`<span class="stderr">Error: ${escHtml(e.message)}</span>`); }
  finally {
    Terminal.running=false; Terminal.reader=null; Terminal._runId=null;
    const kb=document.getElementById('term-kill-btn'); if(kb) kb.style.display='none';
  }
}
// `innerHTML +=` re-serialises and re-parses the ENTIRE output buffer on every
// single line. A command producing thousands of lines degrades quadratically
// and locks the tab. insertAdjacentHTML appends without touching what is
// already rendered, and a line cap keeps the DOM bounded on long runs.
const TERM_MAX_LINES = 5000;
function termAppend(h) {
  const o = document.getElementById('term-output');
  if (!o) return;
  o.insertAdjacentHTML('beforeend', h);
  while (o.childNodes.length > TERM_MAX_LINES) o.removeChild(o.firstChild);
  o.scrollTop = o.scrollHeight;
}
function termClear() { const o=document.getElementById('term-output'); if(o) o.innerHTML=''; }
async function termKill() {
  // FIX 6+7: Kill running process via API + abort reader
  if (Terminal._runId) {
    try { await fetch(`/api/terminal/kill/${encodeURIComponent(Terminal._runId)}`,{method:'POST'}); } catch(e){}
  }
  if (Terminal.reader) { try { await Terminal.reader.cancel(); } catch(e){} Terminal.reader=null; }
  Terminal.running=false; Terminal._runId=null;
  termAppend('<span class="stderr">^C — process killed</span>');
  const kb=document.getElementById('term-kill-btn'); if(kb) kb.style.display='none';
}
function termKeyDown(e) {
  const input=document.getElementById('term-input');
  const sess=Terminal.active; const hist=Terminal.history[sess]||[];
  if(e.key==='Enter'){e.preventDefault();const cmd=input.value.trim();if(cmd)termExecute(cmd);}
  else if(e.key==='ArrowUp'){e.preventDefault();if(!Terminal.histIdx[sess]&&Terminal.histIdx[sess]!==0)Terminal.histIdx[sess]=hist.length;if(Terminal.histIdx[sess]>0){Terminal.histIdx[sess]--;input.value=hist[Terminal.histIdx[sess]]||'';}}
  else if(e.key==='ArrowDown'){e.preventDefault();if(Terminal.histIdx[sess]<hist.length-1){Terminal.histIdx[sess]++;input.value=hist[Terminal.histIdx[sess]]||'';}else{Terminal.histIdx[sess]=hist.length;input.value='';}}
  else if(e.key==='Tab'){e.preventDefault();const p=input.value;const m=['ls ','git ','npm ','npx ','python3 '].find(c=>c.startsWith(p));if(m)input.value=m;}
  else if(e.key==='l'&&(e.ctrlKey||e.metaKey)){e.preventDefault();termClear();}
  else if(e.key==='c'&&e.ctrlKey&&Terminal.running){e.preventDefault();termKill();}  // FIX 7: Ctrl+C kills
}
async function termShowSuggestions() {
  const input=document.getElementById('term-input'); if(!input) return;
  const q=input.value; if(q.length<2){document.getElementById('term-suggestions')?.remove();return;}
  try {
    const r=await fetch(`/api/terminal/suggestions?q=${encodeURIComponent(q)}`); const suggs=await r.json();
    let dd=document.getElementById('term-suggestions');
    if(!dd){dd=document.createElement('div');dd.id='term-suggestions';dd.style.cssText='position:fixed;background:var(--bg-2);border:1px solid var(--border-hi);border-radius:var(--radius-sm);z-index:9999;max-width:400px;box-shadow:var(--shadow-lg);font-family:monospace;font-size:12px';document.body.appendChild(dd);}
    const rect=input.getBoundingClientRect(); dd.style.bottom=(window.innerHeight-rect.top+4)+'px'; dd.style.left=rect.left+'px';
    if(!suggs.length){dd.remove();return;}
    const top6 = suggs.slice(0,6);
    // BUG FIX (quote-collision, total breakage of autocomplete):
    // this used to be onclick="document.getElementById('term-input')
    // .value=${JSON.stringify(s.cmd)};..." for every suggestion row.
    // Same root cause as the toolbar bug above -- JSON.stringify() always
    // wraps its output in literal double quotes, which always collide
    // with the onclick attribute's own delimiters, breaking every single
    // suggestion regardless of its content. Reproduced live: clicking any
    // autocomplete suggestion (even a plain one like "git status") threw
    // "Uncaught SyntaxError: ...Unexpected end of input" and never filled
    // the input. Fixed via data-sugg-idx + a delegated listener on the
    // dropdown container looking up the real command from `top6`.
    dd.innerHTML=top6.map((s,idx)=>`<div data-sugg-idx="${idx}" style="padding:7px 12px;cursor:pointer;display:flex;gap:10px;border-bottom:1px solid var(--border)" onmouseover="this.style.background='var(--bg-3)'" onmouseout="this.style.background=''"><span style="color:var(--accent);flex:1">${escHtml(s.cmd)}</span><span style="color:var(--text-3)">${escHtml(s.desc)}</span></div>`).join('');
    dd.addEventListener('click', (e) => {
      const row = e.target.closest('[data-sugg-idx]');
      if (!row) return;
      const cmd = top6[Number(row.dataset.suggIdx)]?.cmd;
      if (cmd !== undefined) document.getElementById('term-input').value = cmd;
      dd?.remove();
      document.getElementById('term-input')?.focus();
    });
    document.addEventListener('click',()=>dd?.remove(),{once:true});
  } catch(e){}
}
function termNewSession(){const id='s'+Date.now().toString(36);
  // FIX H: init history + histIdx for new session
  if(!Terminal.history[id]) Terminal.history[id]=[];
  Terminal.histIdx[id]=0;
  Terminal.active=id;const tabs=document.getElementById('term-tabs');if(tabs){const t=document.createElement('div');t.className='terminal-tab active';t.dataset.sess=id;t.textContent=id.slice(-4);t.onclick=()=>{Terminal.active=id;document.querySelectorAll('.terminal-tab').forEach(x=>x.classList.toggle('active',x.dataset.sess===id));termClear();};tabs.insertBefore(t,tabs.lastElementChild);}document.querySelectorAll('.terminal-tab').forEach(x=>x.classList.toggle('active',x.dataset.sess===id));termClear();}

// ══════════════════════════════════════════════════════════════════════════════
//  SECRETS VAULT — Encrypted key/value store with Fernet AES-256
//  NOTE: this backs a SEPARATE pane (pane-secrets / 'secrets' nav item),
//  not the Terminal pane -- it lives in this file only for code
//  organization. Out of scope for this Terminal review pass; queued for
//  its own individual review later per the no-batching instruction. Spot
//  -checked while here: vaultReveal/vaultEdit/vaultDelete/vaultShowAdd's
//  onclick="...('${escHtml(item.key)}')" pattern is NOT an active
//  quote-collision bug today because backend/routers/secrets.py's
//  set_secret() validates key format server-side
//  (^[A-Z][A-Z0-9_]{0,127}$ -- uppercase letters/digits/underscores
//  only), so no stored key can ever contain a quote character. Still
//  worth revisiting for consistency with the data-*/addEventListener
//  pattern used elsewhere in this app when this pane gets its own pass.
// ══════════════════════════════════════════════════════════════════════════════
async function renderSecretsVault() {
  const pane = document.getElementById('pane-secrets');
  if (!pane) return;
  pane.innerHTML = '<div style="padding:24px;color:var(--text-2)">Loading vault…</div>';
  let data = {};
  try {
    const r = await fetch('/api/secrets/list');
    data = await r.json();
  } catch(e) {
    pane.innerHTML = `<div style="padding:24px">${pageHeader({title:'🔐 Secrets Vault',subtitle:'Failed to load vault'})}</div>`;
    return;
  }
  const items = data.items || [];
  const encrypted = data.encrypted;
  const engine = data.engine || 'Unknown';
  const warning = data.warning;

  pane.innerHTML = `
    ${pageHeader({
      title:'🔐 Secrets Vault',
      subtitle:'Encrypted credentials injected into every agent run — never in git',
      actions:[{label:'＋ Add Secret',action:'vaultShowAdd()',primary:true},{label:'🔄 Refresh',action:'renderSecretsVault()'}]
    })}
    <div class="page-content">

    <!-- Encryption status banner -->
    <div style="display:flex;align-items:center;gap:12px;padding:12px 16px;border-radius:var(--radius-lg);margin-bottom:20px;background:${encrypted?'rgba(61,186,122,.08)':'rgba(232,162,55,.08)'};border:1px solid ${encrypted?'rgba(61,186,122,.3)':'rgba(232,162,55,.3)'}">
      <span style="font-size:22px">${encrypted?'🔒':'⚠️'}</span>
      <div style="flex:1">
        <div style="font-weight:700;color:${encrypted?'var(--success)':'var(--warning)'}">
          ${encrypted?'AES-256 Fernet Encryption Active':'Encryption Not Available'}
        </div>
        <div style="font-size:11.5px;color:var(--text-2);margin-top:2px">${escHtml(engine)}</div>
        ${warning?`<div style="font-size:11px;color:var(--warning);margin-top:4px">${escHtml(warning)}</div>`:''}
      </div>
      <div style="font-size:11px;color:var(--text-3);text-align:right">
        Key file: <code style="font-size:10px">${escHtml(data.vault_path||'')}</code>
      </div>
    </div>

    <!-- Add secret form (hidden by default) -->
    <div id="vault-add-form" style="display:none;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:18px;margin-bottom:20px">
      <div style="font-weight:700;margin-bottom:14px;font-size:14px">Add / Update Secret</div>
      <div style="display:grid;grid-template-columns:1fr 2fr;gap:10px;margin-bottom:10px">
        <div>
          <label style="font-size:11px;color:var(--text-3);text-transform:uppercase;display:block;margin-bottom:4px">Key Name</label>
          <input id="vault-key-input" class="vault-input" placeholder="OPENROUTER_API_KEY" autocomplete="off" spellcheck="false"
            oninput="this.value=this.value.toUpperCase().replace(/[^A-Z0-9_]/g,'')">
        </div>
        <div>
          <label style="font-size:11px;color:var(--text-3);text-transform:uppercase;display:block;margin-bottom:4px">Value</label>
          <input id="vault-value-input" class="vault-input" type="password" placeholder="sk-or-v1-…" autocomplete="new-password">
        </div>
      </div>
      <div style="display:flex;gap:10px;align-items:center;margin-bottom:10px">
        <div style="flex:1">
          <label style="font-size:11px;color:var(--text-3);text-transform:uppercase;display:block;margin-bottom:4px">Scope</label>
          <select id="vault-scope-select" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 10px;color:var(--text-0);font-size:13px;outline:none">
            <option value="global">global — all agents</option>
            <option value="agent">agent — specific agent</option>
          </select>
        </div>
        <div style="flex:1">
          <label style="font-size:11px;color:var(--text-3);text-transform:uppercase;display:block;margin-bottom:4px">Agent (if scoped)</label>
          <input id="vault-agent-input" class="vault-input" placeholder="builder, reviewer, …">
        </div>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-primary" onclick="vaultSave()">💾 Save to Vault</button>
        <button class="btn btn-ghost" onclick="vaultHideAdd()">Cancel</button>
        <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-2);margin-left:auto;cursor:pointer">
          <input type="checkbox" id="vault-show-value" onchange="document.getElementById('vault-value-input').type=this.checked?'text':'password'">
          Show value
        </label>
      </div>
    </div>

    <!-- Secrets list -->
    <div style="font-weight:700;font-size:13px;margin-bottom:10px;color:var(--text-1)">
      ${items.length} secret${items.length!==1?'s':''} stored
    </div>

    ${items.length===0 ? `
      ${emptyState({icon:'🔐',title:'No secrets yet',body:'Add your API keys and credentials. They are encrypted at rest and injected into every agent run.',
        actions:[{label:'＋ Add First Secret',action:'vaultShowAdd()',primary:true}]})}
    ` : `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);overflow:hidden">
        <div style="display:grid;grid-template-columns:1fr 80px 80px 120px 130px;padding:8px 14px;background:var(--bg-3);font-size:10px;font-weight:700;color:var(--text-3);text-transform:uppercase;gap:8px">
          <div>Key</div><div>Scope</div><div>Length</div><div>Updated</div><div>Actions</div>
        </div>
        ${items.map(item=>`
          <div class="vault-row" style="display:grid;grid-template-columns:1fr 80px 80px 120px 130px;gap:8px">
            <div style="display:flex;align-items:center;gap:8px;min-width:0">
              <span class="vault-key">${escHtml(item.key)}</span>
              ${encrypted?'<span class="vault-enc-badge">🔒</span>':''}
            </div>
            <div><span class="vault-scope">${escHtml(item.scope||'global')}</span></div>
            <div style="color:var(--text-3);font-size:11px">${item.length||0} chars</div>
            <div style="color:var(--text-3);font-size:11px;white-space:nowrap">${escHtml((item.updated_at||'').slice(0,16))}</div>
            <div style="display:flex;gap:5px">
              <button class="btn btn-ghost btn-sm" onclick="vaultReveal('${escHtml(item.key)}')" title="Reveal value">👁</button>
              <button class="btn btn-ghost btn-sm" onclick="vaultEdit('${escHtml(item.key)}')" title="Update value">✏️</button>
              <button class="btn btn-sm" onclick="vaultDelete('${escHtml(item.key)}')" style="color:var(--danger)" title="Delete">🗑</button>
            </div>
          </div>
        `).join('')}
      </div>
    `}

    <!-- Quick-add common keys -->
    <div style="margin-top:20px">
      ${helpPanel({title:'Common API Keys',body:'Click a key name to pre-fill the form.',steps:[]})}
      <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px">
        ${['OPENROUTER_API_KEY','GITHUB_TOKEN','VERCEL_TOKEN','NETLIFY_TOKEN','SUPABASE_URL','SUPABASE_ANON_KEY','STRIPE_SECRET_KEY','ANTHROPIC_API_KEY','OPENAI_API_KEY'].map(k=>
          `<button class="btn btn-ghost btn-sm" onclick="vaultShowAdd('${k}')">${escHtml(k)}</button>`
        ).join('')}
      </div>
    </div>

    </div>`;
}

function vaultShowAdd(prefillKey='') {
  const form = document.getElementById('vault-add-form');
  if (form) {
    form.style.display = 'block';
    if (prefillKey) {
      const ki = document.getElementById('vault-key-input');
      if (ki) { ki.value = prefillKey; }
    }
    document.getElementById('vault-value-input')?.focus();
    form.scrollIntoView({behavior:'smooth',block:'nearest'});
  }
}

function vaultHideAdd() {
  const form = document.getElementById('vault-add-form');
  if (form) {
    form.style.display = 'none';
    const ki = document.getElementById('vault-key-input');
    const vi = document.getElementById('vault-value-input');
    if (ki) ki.value = '';
    if (vi) vi.value = '';
  }
}

async function vaultSave() {
  const key   = (document.getElementById('vault-key-input')?.value||'').trim().toUpperCase();
  const value = document.getElementById('vault-value-input')?.value||'';
  const scope = document.getElementById('vault-scope-select')?.value||'global';
  const agent = (document.getElementById('vault-agent-input')?.value||'').trim();
  if (!key) { showToast('Key name is required','err'); return; }
  if (!value) { showToast('Value is required','err'); return; }
  try {
    const r = await fetch('/api/secrets/set',{
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({key, value, scope, agent})
    });
    const j = await r.json();
    if (j.ok) {
      showToast(`✅ ${key} saved to vault (${j.encrypted?'AES-256':'base64'})`, 'ok', 3000);
      vaultHideAdd();
      renderSecretsVault();
    } else {
      showToast('⚠️ ' + (j.error||'Save failed'), 'err');
    }
  } catch(ex) { showToast('⚠️ ' + ex.message, 'err'); }
}

async function vaultReveal(key) {
  try {
    const r = await fetch(`/api/secrets/get?key=${encodeURIComponent(key)}&reveal=true`);
    const j = await r.json();
    if (j.ok && j.value !== undefined) {
      await gmAlert(`🔐 ${escHtml(key)}`,
        `<div style="font-family:monospace;background:var(--bg-0);padding:12px;border-radius:8px;word-break:break-all;font-size:13px;color:var(--success)">${escHtml(j.value)}</div>
         <div style="font-size:11px;color:var(--text-3);margin-top:8px">This value is encrypted at rest. Copy it now.</div>`);
    } else {
      showToast('⚠️ Could not reveal: ' + (j.error||'unknown'), 'err');
    }
  } catch(ex) { showToast('⚠️ ' + ex.message, 'err'); }
}

async function vaultEdit(key) {
  const newVal = await gmPrompt(`Update value for ${key}:`, '');
  if (newVal === null) return;
  if (!newVal.trim()) { showToast('Value cannot be empty', 'err'); return; }
  try {
    const r = await fetch('/api/secrets/set',{
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({key, value:newVal})
    });
    const j = await r.json();
    if (j.ok) {
      showToast(`✅ ${key} updated`, 'ok', 2000);
      renderSecretsVault();
    } else {
      showToast('⚠️ ' + (j.error||'Update failed'), 'err');
    }
  } catch(ex) { showToast('⚠️ ' + ex.message, 'err'); }
}

async function vaultDelete(key) {
  if (!(await gmDanger('Delete Secret', `Permanently delete "${key}" from the vault? This cannot be undone.`, 'Delete'))) return;
  try {
    const r = await fetch(`/api/secrets/${encodeURIComponent(key)}`, {method:'DELETE'});
    const j = await r.json();
    if (j.ok) {
      showToast(`🗑 ${key} deleted from vault`, 'ok', 2000);
      renderSecretsVault();
    } else {
      showToast('⚠️ ' + (j.error||'Delete failed'), 'err');
    }
  } catch(ex) { showToast('⚠️ ' + ex.message, 'err'); }
}


