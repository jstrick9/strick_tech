/* Environment Secrets Vault — v4.8 */
(function(){
  console.log('[Vault] loading Secrets Vault v4.8');
  function inject(){
    const tabs=document.querySelector('.tabs');
    if(!tabs) return false;
    if(document.querySelector('.tab[data-tab="vault"]')) return true;
    const b=document.createElement('div');
    b.className='tab';
    b.dataset.tab='vault';
    b.innerHTML='🔐 Vault';
    b.style.color='#fcd34d';
    b.style.fontWeight='700';
    tabs.appendChild(b);

    const center=document.querySelector('.center');
    if(center && !document.getElementById('pane-vault')){
      const pane=document.createElement('div');
      pane.id='pane-vault';
      pane.style.display='none';
      pane.style.height='100%';
      pane.style.overflow='auto';
      pane.style.background='#070812';
      pane.innerHTML=`
<div style="max-width:1180px;margin:0 auto;padding:20px">
  <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:16px">
    <div style="font-size:22px;font-weight:800;color:#fde68a">🔐 Environment Secrets Vault</div>
    <span style="font-size:11px;background:#2a1f08;color:#fcd34d;padding:3px 10px;border-radius:999px;border:1px solid #5a3a0f">Fernet AES-256</span>
    <span style="font-size:11px;background:#1a1328;color:#c9b6ff;padding:3px 10px;border-radius:999px;border:1px solid #3d2a66">per-agent scoping</span>
    <span style="font-size:11px;background:#13231b;color:#9ece6a;padding:3px 10px;border-radius:999px;border:1px solid #294a2b">never in Git</span>
    <span class="spacer"></span>
    <span id="vault-status" style="font-size:11px;color:#9aa7c7">checking…</span>
  </div>

  <div style="display:grid;grid-template-columns:360px 1fr 320px;gap:16px;align-items:start">
    <!-- left: add -->
    <div style="background:#0e1326;border:1px solid #24325a;border-radius:16px;padding:16px;position:sticky;top:12px">
      <div style="font-weight:700;color:#fde68a;margin-bottom:10px">Add secret</div>
      <label style="font-size:11px;color:#8fa0d7">KEY</label>
      <input id="vt-key" placeholder="OPENROUTER_API_KEY"
        style="width:100%;background:#0b1022;color:#ffeaa7;border:1px solid #334477;border-radius:10px;padding:9px 11px;font-family:ui-monospace,monospace;font-size:12.5px;margin-bottom:9px;outline:none;text-transform:uppercase" />
      <label style="font-size:11px;color:#8fa0d7">VALUE</label>
      <div style="position:relative">
        <input id="vt-val" type="password" placeholder="sk-or-••••••••"
          style="width:100%;background:#0b1022;color:#e8f5d8;border:1px solid #334477;border-radius:10px;padding:9px 38px 9px 11px;font-family:ui-monospace,monospace;font-size:12.5px;outline:none" />
        <button id="vt-eye" style="position:absolute;right:8px;top:7px;background:none;border:none;color:#7a88b6;cursor:pointer;font-size:14px">👁</button>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:9px">
        <div>
          <label style="font-size:11px;color:#8fa0d7">Scope</label>
          <select id="vt-scope" style="width:100%;background:#0b1022;color:#dbe6ff;border:1px solid #273560;border-radius:9px;padding:7px;font-size:12px">
            <option value="global">global</option>
            <option value="agent">agent-scoped</option>
            <option value="project">project</option>
            <option value="ci">ci/cd</option>
          </select>
        </div>
        <div>
          <label style="font-size:11px;color:#8fa0d7">Agent</label>
          <select id="vt-agent" style="width:100%;background:#0b1022;color:#dbe6ff;border:1px solid #273560;border-radius:9px;padding:7px;font-size:12px">
            <option value="">— any —</option>
            <option value="claude">claude</option>
            <option value="hermes">hermes</option>
            <option value="gemini">gemini</option>
            <option value="grok">grok</option>
            <option value="openclaw">openclaw</option>
            <option value="galaxy">galaxy</option>
            <option value="swarm">swarm</option>
            <option value="builder">builder</option>
          </select>
        </div>
      </div>
      <button class="btn" id="vt-save" style="width:100%;margin-top:12px;background:linear-gradient(90deg,#fcd34d,#f59e0b);color:#1a1200">🔐 Encrypt & Save to Vault</button>
      <div style="font-size:10.5px;color:#7b88a8;margin-top:9px;line-height:1.5">
        • Fernet AES-256 — key at <code>memory/.vault_key</code> (600)<br>
        • Never committed — excluded from Git time-travel<br>
        • Auto-injected to <code>os.environ</code> on boot<br>
        • Per-agent scoping — e.g. CLAUDE_API_KEY → agent=claude
      </div>
      <div style="margin-top:14px;border-top:1px dashed #223054;padding-top:12px">
        <div style="font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:#8a95c7;margin-bottom:8px">Quick presets</div>
        <div style="display:flex;flex-wrap:wrap;gap:5px" id="vt-presets"></div>
      </div>
    </div>

    <!-- center: list -->
    <div style="background:#0c1022;border:1px solid #1f2a4a;border-radius:16px;overflow:hidden;display:flex;flex-direction:column;min-height:520px">
      <div style="padding:12px 16px;border-bottom:1px solid #1d2745;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <b style="color:#fde68a">Vault keys</b>
        <span id="vt-count" style="font-size:11px;color:#8fa0d7">—</span>
        <span class="spacer"></span>
        <input id="vt-filter" placeholder="filter…" style="background:#0b1022;color:#dbe6ff;border:1px solid #263560;border-radius:8px;padding:5px 9px;font-size:11.5px;width:160px">
        <button class="btn-sm btn-ghost" id="vt-reload">⟳</button>
        <button class="btn-sm btn-ghost" id="vt-export">⬇ Export .env</button>
      </div>
      <div id="vt-list" style="flex:1;overflow:auto;padding:10px 14px">
        <div style="color:#7a88b8">Loading vault…</div>
      </div>
    </div>

    <!-- right: audit + tools -->
    <div style="display:flex;flex-direction:column;gap:14px">
      <div style="background:#0e1326;border:1px solid #26325a;border-radius:14px;padding:14px">
        <div style="font-weight:700;color:#ffe08a;font-size:13px;margin-bottom:8px">Vault status</div>
        <div id="vt-status-box" style="font-size:12px;color:#a9b8e8;line-height:1.7">
          Loading…
        </div>
      </div>

      <div style="background:#0e1326;border:1px solid #26325a;border-radius:14px;padding:14px">
        <div style="font-weight:700;color:#c9b6ff;font-size:13px;margin-bottom:8px">Import .env</div>
        <textarea id="vt-import-txt" placeholder="PASTE .env here…
OPENROUTER_API_KEY=sk-or-...
CLAUDE_API_KEY=...
VERCEL_TOKEN=...
GITHUB_TOKEN=..."
          style="width:100%;height:110px;background:#0b1022;color:#cfe8d8;border:1px solid #28365a;border-radius:9px;padding:8px;font-family:ui-monospace,monospace;font-size:11.5px;resize:vertical"></textarea>
        <button class="btn-sm btn-ghost" id="vt-import-btn" style="width:100%;margin-top:7px">⬆ Import → encrypt all</button>
        <div style="font-size:10.5px;color:#7a88a8;margin-top:6px">Bulk paste — auto-detects KEY=val lines — encrypts → vault — updates .env</div>
      </div>

      <div style="background:#0e1326;border:1px solid #26325a;border-radius:14px;padding:14px">
        <div style="font-weight:700;color:#e6d7a3;font-size:13px;margin-bottom:8px">Audit trail</div>
        <div id="vt-audit" style="font-size:11px;color:#8ea0c8;max-height:220px;overflow:auto;font-family:ui-monospace,monospace;line-height:1.5">
          loading…
        </div>
      </div>
    </div>
  </div>
</div>`;
      const ref = document.getElementById('pane-swarm') || document.querySelector('[id^="pane-"]');
      if(ref && ref.parentNode) ref.parentNode.appendChild(pane); else document.querySelector('.center').appendChild(pane);
    }
    hookVault();
    return true;
  }

  function hookVault(){
    document.querySelectorAll('.tab').forEach(tab=>{
      if(tab._vault) return; tab._vault=true;
      tab.addEventListener('click', ()=>{
        const t=tab.dataset.tab;
        document.querySelectorAll('[id^="pane-"]').forEach(p=>p.style.display='none');
        const el=document.getElementById('pane-'+t);
        if(el) el.style.display = t==='chat'?'flex':'block';
        if(t==='vault') refreshVault();
      });
    });
    const vt=document.querySelector('.tab[data-tab="vault"]');
    if(vt){ vt.addEventListener('click', ()=>{ document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active')); vt.classList.add('active'); }); }

    // bind once
    if(window.__vaultBound) return;
    window.__vaultBound=true;

    document.addEventListener('click', e=>{
      if(e.target && e.target.id==='vt-save') saveSecret();
      if(e.target && e.target.id==='vt-reload') refreshVault();
      if(e.target && e.target.id==='vt-export') exportEnv();
      if(e.target && e.target.id==='vt-import-btn') importEnv();
      if(e.target && e.target.id==='vt-eye'){
        const inp=document.getElementById('vt-val');
        if(inp){ inp.type = inp.type==='password' ? 'text' : 'password'; }
      }
    });
    document.addEventListener('input', e=>{
      if(e.target && e.target.id==='vt-filter') renderList();
    });
    document.addEventListener('keydown', e=>{
      if(e.target && e.target.id==='vt-val' && (e.metaKey||e.ctrlKey) && e.key==='Enter'){
        saveSecret();
      }
    });
  }

  let vaultData = {items:[]};

  async function refreshVault(){
    try{
      const r=await fetch('/api/secrets/list?masked=true');
      const j=await r.json();
      vaultData = j;
      const st=document.getElementById('vault-status');
      if(st) st.textContent = j.encrypted ? `🔐 Fernet • ${j.count} keys • ${j.engine}` : '⚠️ '+(j.warning||'fallback');
      renderList();
      renderStatusBox(j);
      loadAudit();
      renderPresets();
    }catch(e){
      console.error(e);
    }
  }

  function renderPresets(){
    const box=document.getElementById('vt-presets');
    if(!box || box.dataset.done) return;
    box.dataset.done='1';
    const presets=[
      'OPENROUTER_API_KEY','CLAUDE_API_KEY','GEMINI_API_KEY','GROK_API_KEY',
      'OPENAI_API_KEY','ANTHROPIC_API_KEY','VERCEL_TOKEN','GITHUB_TOKEN',
      'STRIPE_SECRET_KEY','SUPABASE_URL','SUPABASE_ANON_KEY','DATABASE_URL'
    ];
    box.innerHTML = presets.map(k=>`<button onclick="document.getElementById('vt-key').value='${k}';document.getElementById('vt-val').focus()" 
      style="font-size:10.5px;padding:3px 7px;border-radius:6px;background:#151d34;border:1px solid #223055;color:#9fb4ea;cursor:pointer">${k.split('_')[0]}</button>`).join(' ');
  }

  function renderList(){
    const el=document.getElementById('vt-list');
    const filterEl=document.getElementById('vt-filter');
    if(!el) return;
    const q=(filterEl?.value||'').toLowerCase();
    const items=(vaultData.items||[]).filter(it=> !q || it.key.toLowerCase().includes(q) || (it.agent||'').includes(q));
    document.getElementById('vt-count') && (document.getElementById('vt-count').textContent = `${items.length}/${vaultData.count||0} keys`);
    if(!items.length){
      el.innerHTML = `<div style="color:#7a88b8;padding:18px;text-align:center">
        Vault empty — add your first secret left →<br><br>
        <b style="color:#fcd34d">Recommended for Agentic OS:</b><br>
        <div style="margin-top:8px;font-family:ui-monospace,monospace;font-size:11px;color:#9fb0d8">
        OPENROUTER_API_KEY<br>
        CLAUDE_API_KEY<br>
        GEMINI_API_KEY<br>
        VERCEL_TOKEN<br>
        GITHUB_TOKEN
        </div>
        <div style="margin-top:10px;font-size:11px;color:#7a88b8">All → encrypted Fernet AES-256<br>Never in Git • per-agent scoping</div>
      </div>`;
      return;
    }
    el.innerHTML = items.map(it=>`
      <div style="background:#0f152c;border:1px solid #1f2a4a;border-radius:11px;padding:11px 12px;margin-bottom:8px">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
          <div>
            <b style="color:#ffe9a6;font-family:ui-monospace,monospace;font-size:12.5px">${it.key}</b>
            ${it.agent ? `<span style="font-size:10px;background:#221a3a;color:#c9b6f5;padding:1px 6px;border-radius:999px;margin-left:6px">${it.agent}</span>`:''}
            <span style="font-size:10px;color:#7a88a8;margin-left:6px">${it.scope||'global'}</span>
          </div>
          <div style="display:flex;gap:5px">
            <button onclick="vaultReveal('${it.key}')" style="font-size:11px;background:#1a2032;color:#b6c3e6;border:1px solid #263250;padding:3px 8px;border-radius:6px;cursor:pointer">👁 reveal</button>
            <button onclick="vaultCopy('${it.key}')" style="font-size:11px;background:#1a2032;color:#b6c3e6;border:1px solid #263250;padding:3px 8px;border-radius:6px;cursor:pointer">📋 copy</button>
            <button onclick="vaultDelete('${it.key}')" style="font-size:11px;background:#2a1215;color:#ff9a9a;border:1px solid #5a1a1a;padding:3px 8px;border-radius:6px;cursor:pointer">🗑</button>
          </div>
        </div>
        <div style="font-family:ui-monospace,monospace;font-size:11.5px;color:#9fb89a;margin-top:6px;word-break:break-all">${it.masked||'••••••••'}</div>
        <div style="font-size:10.5px;color:#6b7ca5;margin-top:4px">
          updated ${it.updated_at ? new Date(it.updated_at).toLocaleString() : '—'} • fp ${it.fingerprint||'—'} • ${it.length||'?'} chars
        </div>
      </div>
    `).join('');
  }

  function renderStatusBox(j){
    const box=document.getElementById('vt-status-box');
    if(!box) return;
    box.innerHTML = `
      <div>🔐 <b>${j.encrypted ? 'Fernet AES-256' : 'Base64 fallback'}</b></div>
      <div>📁 <code>${j.vault_path||'brain/secrets.vault'}</code></div>
      <div>🔑 ${j.count} keys stored</div>
      <div style="margin-top:6px;color:#9ece6a">✓ excluded from Git time-travel</div>
      <div style="color:#9ece6a">✓ auto-injected to os.environ on boot</div>
      <div style="color:#9ece6a">✓ per-agent scoping enabled</div>
      ${j.warning ? `<div style="color:#ff9e64;margin-top:6px">⚠️ ${j.warning}</div>` : ''}
      <div style="margin-top:8px;font-size:11px;color:#7a88b8">
        Use in agents:<br>
        <code>os.getenv("OPENROUTER_API_KEY")</code><br>
        auto-filled from vault.
      </div>
    `;
  }

  async function saveSecret(){
    const keyEl=document.getElementById('vt-key');
    const valEl=document.getElementById('vt-val');
    const scopeEl=document.getElementById('vt-scope');
    const agentEl=document.getElementById('vt-agent');
    const key=(keyEl?.value||'').trim().toUpperCase();
    const value=valEl?.value||'';
    if(!key){ alert('Enter KEY — e.g. OPENROUTER_API_KEY'); keyEl?.focus(); return; }
    if(!value){ alert('Enter secret value'); valEl?.focus(); return; }
    const btn=document.getElementById('vt-save');
    const orig=btn?.textContent;
    if(btn){ btn.textContent='⏳ Encrypting…'; btn.disabled=true; }
    try{
      const r=await fetch('/api/secrets/set',{
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          key, value,
          scope: scopeEl?.value || 'global',
          agent: agentEl?.value || ''
        })
      });
      const j=await r.json();
      if(j.ok){
        if(window.addConsole) addConsole(`🔐 Vault saved → ${key} • ${j.scope} • fp ${j.fingerprint}`);
        keyEl.value=''; valEl.value='';
        await refreshVault();
        if(typeof addChat==='function'){
          addChat(`🔐 Secret saved to Vault

**${key}**
• scope: ${j.scope}${j.agent ? ' • agent: '+j.agent : ''}
• fingerprint: \`${j.fingerprint}\`
• encrypted: Fernet AES-256
• path: \`brain/secrets.vault\`
• auto-injected → \`os.getenv("${key}")\`

✅ NOT in Git time-travel
✅ NOT in backup tar snapshots (add manually if needed)
✅ per-agent scoping active

Next: restart agent loop → env var available instantly (already injected).`, 'agent');
        }
      } else {
        alert('Save failed: '+(j.error||'unknown'));
      }
    }catch(e){ alert(e); }
    finally{ if(btn){ btn.textContent=orig; btn.disabled=false; } }
  }

  window.vaultReveal = async function(key){
    try{
      const r=await fetch('/api/secrets/get?key='+encodeURIComponent(key)+'&reveal=true');
      const j=await r.json();
      if(j.ok && j.revealed){
        // copy to clipboard, show 8s then clear clipboard? just alert
        await navigator.clipboard.writeText(j.value);
        alert(`🔓 ${key}\n\n${j.value.slice(0,120)}${j.value.length>120?'…':''}\n\n✓ Copied to clipboard\n\n(Audit logged: reveal)`);
      } else {
        alert(j.error||'failed');
      }
    }catch(e){ alert(e); }
  };
  window.vaultCopy = async function(key){
    // reveal then copy – same as reveal
    return window.vaultReveal(key);
  };
  window.vaultDelete = async function(key){
    if(!confirm(`Delete secret "${key}" from vault?\n\nThis cannot be undone (unless you have a backup).\n\nIt will also be removed from .env`)) return;
    try{
      const r=await fetch('/api/secrets/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key})});
      const j=await r.json();
      if(j.ok){ refreshVault(); if(window.addConsole) addConsole('🗑 vault deleted → '+key); }
      else alert(j.error||'delete failed');
    }catch(e){ alert(e); }
  };

  async function exportEnv(){
    try{
      const r=await fetch('/api/secrets/export?format=env');
      const txt=await r.text();
      // download
      const blob=new Blob([txt],{type:'text/plain'});
      const url=URL.createObjectURL(blob);
      const a=document.createElement('a'); a.href=url; a.download='.env.agentic-export'; a.click();
      URL.revokeObjectURL(url);
      alert('Exported '+(txt.split('\n').filter(l=>l.trim()&&!l.startsWith('#')).length)+' secrets → .env.agentic-export downloaded');
    }catch(e){ alert(e); }
  }

  async function importEnv(){
    const ta=document.getElementById('vt-import-txt');
    const txt=ta?.value.trim();
    if(!txt){ alert('Paste .env content first — left box under “Import .env”'); ta?.focus(); return; }
    const btn=document.getElementById('vt-import-btn');
    const orig=btn?.textContent;
    if(btn){ btn.textContent='⏳ Encrypting…'; btn.disabled=true; }
    try{
      const r=await fetch('/api/secrets/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({env_text:txt})});
      const j=await r.json();
      if(j.ok){
        alert(`✅ Imported ${j.imported} secrets → encrypted → vault`);
        ta.value='';
        refreshVault();
      } else alert('Import failed');
    }catch(e){ alert(e); }
    finally{ if(btn){ btn.textContent=orig; btn.disabled=false; } }
  }

  async function loadAudit(){
    try{
      const r=await fetch('/api/secrets/audit?limit=30');
      const j=await r.json();
      const el=document.getElementById('vt-audit');
      if(el){
        if(!j.length){ el.textContent='No audit events yet.'; return; }
        el.innerHTML = j.map(a=>`<div>[${a.ts}] <b style="color:#fcd34d">${a.action}</b> ${a.key_name} <span style="color:#7a88b8">${a.agent_scope||''}</span></div>`).join('');
      }
    }catch(e){}
  }

  // inject loop
  let tries=0;
  const iv=setInterval(()=>{
    tries++;
    if(inject() || tries>45) clearInterval(iv);
  },400);

  console.log('[Vault] Secrets Vault UI — v4.8 ready');
})();
