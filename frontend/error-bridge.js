/* Error Bridge — Mission Control receives iframe errors — v4.5 */
(function(){
  console.log('[ErrorBridge] v4.5 active');
  let lastError=null;
  let errorCount=0;
  window.addEventListener('message', async (ev)=>{
    const d = ev.data||{};
    if(d.type==='agentic-error'){
      errorCount++;
      lastError=d;
      console.warn('[Agentic OS] preview error:', d.message);
      // update UI badge
      const badge = document.getElementById('errorBadge');
      if(badge){
        badge.textContent = '💥 '+errorCount;
        badge.style.display='inline-block';
        badge.style.background='#7f1d1d';
        badge.style.color='#fecaca';
      } else {
        // inject badge into topbar
        const topActions = document.querySelector('.top-actions');
        if(topActions && !document.getElementById('errorBadge')){
          const b=document.createElement('div');
          b.id='errorBadge';
          b.style.cssText='background:#7f1d1d;color:#fecaca;padding:3px 9px;border-radius:999px;font-size:11px;font-weight:700;cursor:pointer;border:1px solid #dc2626';
          b.textContent='💥 1';
          b.title='Live error — click to auto-heal';
          b.onclick=openErrorHeal;
          topActions.prepend(b);
        }
      }
      // show toast in console
      if(window.addConsole) addConsole('💥 Preview error: '+(d.message||'').slice(0,120)+' — @ '+ (d.filename||'').split('/').pop()+':'+d.lineno);
      // auto-open heal modal? only first time
      if(errorCount===1){
        setTimeout(()=>{ if(confirm('💥 Runtime error in Live Preview:\n\n'+(d.message||'').slice(0,180)+'\n\nOpen Auto-Heal?')) openErrorHeal(); }, 400);
      }
      // ping chat
      if(typeof addChat==='function'){
        addChat(`💥 **Live Error Overlay caught crash**

\`${(d.message||'').slice(0,140)}\`
${d.filename||''}:${d.lineno||'?'} 

→ Auto-heal ready:
• **Fix with Hermes** — 1-click — /api/agent/fix
• **Swarm Fix** — 4 agents parallel
• **Git rollback** — time-travel

Open Live Builder → preview shows red overlay → click “Fix with Hermes”

Or click top bar 💥 badge → auto-heal modal.`, 'agent');
      }
    }
    if(d.type==='agentic-heal-applied'){
      // HMR refresh preview
      const ifr=document.getElementById('previewFrame');
      if(ifr){ setTimeout(()=>{ ifr.src = ifr.src.split('?')[0] + '?healed=' + Date.now(); }, 600); }
      if(window.addConsole) addConsole('✅ Auto-heal applied → '+ (d.path||'') +' → HMR reload');
      // clear error badge after 3s
      setTimeout(()=>{
        const b=document.getElementById('errorBadge');
        if(b){ b.textContent='✓ healed'; b.style.background='#13231b'; b.style.color='#9ece6a'; setTimeout(()=>b.remove(), 2500); }
        errorCount=0;
      }, 1200);
    }
    if(d.type==='agentic-open-timetravel'){
      // open time-travel UI
      if(typeof showTab==='function') showTab('builder');
      setTimeout(()=>{
        const btn=document.querySelector('[onclick*="time"], #ttoggle, .tt-head button');
        if(btn) btn.click();
        alert('Git time-travel opened → pick last green version → Restore');
      }, 300);
    }
    if(d.type==='agentic-error-overlay-ready'){
      console.log('[ErrorBridge] overlay ready in', d.url);
    }
  });

  async function openErrorHeal(){
    if(!lastError){ alert('No recent error captured.\n\nTrigger an error in Live Preview first — or open the preview iframe directly to see red overlay.'); return; }
    const e = lastError;
    const proceed = confirm(`🤖 Hermes Auto-Heal

Error:
${e.message}

${e.filename}:${e.lineno}

Run /api/agent/fix now?
→ Yes = auto-patch + HMR
→ Cancel = open Monaco Cmd+K`);
    if(!proceed) return;
    try{
      // get current file content from Monaco if possible
      let code = '';
      let filepath = (e.filename||'').split('/').pop() || 'index.html';
      // try monaco
      if(window.monacoEditor){
        try{ code = window.monacoEditor.getValue(); filepath = window.activeTab || filepath; }catch(_){}
      }
      if(!code){
        // fetch from preview
        try{
          const url = e.filename && e.filename.includes('/preview/') ? new URL(e.filename).pathname : '/preview/index.html';
          const r = await fetch(url);
          if(r.ok) code = await r.text();
        }catch(_){}
      }
      const res = await fetch('/api/agent/fix', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          code: code.slice(0,18000),
          error: e.message,
          stack: e.stack||'',
          filepath,
          language: filepath.endsWith('.js')?'javascript': filepath.endsWith('.tsx')||filepath.endsWith('.ts')?'typescript':'html'
        })
      });
      const j = await res.json();
      if(!j.ok && !j.fixed){ alert('Fix failed: '+(j.error||'unknown')); return; }
      const ok = confirm(`Hermes Auto-Heal ready

${j.explanation}

--- diff preview ---
${(j.diff||'').slice(0,600)}

Apply patch + HMR now?`);
      if(!ok) return;
      const apply = await fetch('/api/agent/fix/apply', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({filepath: j.filepath||filepath, fixed: j.fixed, explanation: j.explanation})
      });
      const aj = await apply.json();
      if(aj.ok){
        alert('✅ Auto-heal applied!\n\n'+aj.path+'\n\nPreview will HMR reload…');
        // reload preview iframe
        const ifr=document.getElementById('previewFrame');
        if(ifr) ifr.src = ifr.src.split('?')[0] + '?healed=' + Date.now();
        // clear badge
        const b=document.getElementById('errorBadge');
        if(b) b.remove();
        errorCount=0;
      } else {
        alert('Apply failed: '+(aj.error||'unknown'));
      }
    }catch(err){
      alert('Auto-heal error: '+err);
    }
  }

  window.openErrorHeal = openErrorHeal;

  // inject error overlay script into preview iframe automatically
  function injectOverlayIntoIframe(){
    const ifr=document.getElementById('previewFrame');
    if(!ifr) return;
    try{
      const doc = ifr.contentDocument;
      if(doc && !doc.querySelector('script[data-agentic-error]')){
        const s = doc.createElement('script');
        s.src = '/static/error-overlay.js';
        s.setAttribute('data-agentic-error','1');
        (doc.head||doc.documentElement).appendChild(s);
        console.log('[ErrorBridge] injected error-overlay.js into preview iframe');
      }
    }catch(e){
      // cross-origin? preview is same origin /preview/*
      // ignore
    }
  }
  // try on load + every 3s + when tab switches to builder
  setInterval(injectOverlayIntoIframe, 3000);
  document.addEventListener('click', (ev)=>{
    const t = ev.target.closest && ev.target.closest('[data-tab="builder"]');
    if(t) setTimeout(injectOverlayIntoIframe, 900);
  });
  // also first run
  setTimeout(injectOverlayIntoIframe, 1500);

  console.log('[ErrorBridge] ready — listening for agentic-error postMessage');
})();
