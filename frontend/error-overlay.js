// Agentic OS — Live Error Overlay v4.5
// Include in preview pages: <script src="/static/error-overlay.js"></script>
// Or auto-injected by Mission Control
(function(){
  if(window.__AGENTIC_ERROR_OVERLAY__) return;
  window.__AGENTIC_ERROR_OVERLAY__ = true;
  const ID='agentic-error-overlay';
  function showOverlay(payload){
    let el=document.getElementById(ID);
    if(!el){
      el=document.createElement('div');
      el.id=ID;
      el.style.cssText='position:fixed;inset:0;z-index:2147483647;background:rgba(18,8,8,.94);color:#ffdddd;font-family:ui-monospace,Menlo,Consolas,monospace;display:flex;flex-direction:column;';
      document.documentElement.appendChild(el);
    }
    el.innerHTML = `
      <div style="background:#7f1d1d;padding:14px 18px;display:flex;align-items:center;gap:12px;border-bottom:2px solid #dc2626">
        <div style="font-size:22px">💥</div>
        <div>
          <div style="font-weight:800;font-size:15px;color:#fff">Runtime Error — Agentic OS Auto-Heal</div>
          <div style="font-size:12px;color:#fecaca">${(payload.message||'Unknown error').slice(0,180)}</div>
        </div>
        <div style="margin-left:auto;display:flex;gap:8px">
          <button id="agx-fix" style="background:#facc15;color:#422006;border:none;padding:8px 14px;border-radius:9px;font-weight:700;cursor:pointer;font-size:13px">🤖 Fix with Hermes</button>
          <button id="agx-dismiss" style="background:#27272a;color:#e4e4e7;border:1px solid #444;padding:8px 12px;border-radius:9px;cursor:pointer;font-size:12px">Dismiss</button>
          <button id="agx-reload" style="background:#18181b;color:#a1a1aa;border:1px solid #3f3f46;padding:8px 12px;border-radius:9px;cursor:pointer;font-size:12px">Reload</button>
        </div>
      </div>
      <div style="flex:1;overflow:auto;padding:16px 20px;display:grid;grid-template-columns:1fr 380px;gap:18px">
        <div>
          <div style="color:#fda4af;font-size:12px;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px">Stack trace</div>
          <pre style="background:#1a0b0b;border:1px solid #7f1d1d;border-radius:10px;padding:12px;white-space:pre-wrap;font-size:12px;color:#fecaca;max-height:46vh;overflow:auto">${escapeHtml(payload.stack||payload.message||'')}</pre>
          <div style="margin-top:12px;font-size:12px;color:#fca5a5">
            <b>File:</b> ${escapeHtml(payload.filename||'unknown')} 
            <b style="margin-left:12px">Line:</b> ${payload.lineno||'?'}:${payload.colno||''}
          </div>
          <div style="margin-top:14px;font-size:12px;color:#fcd34d">
            → Auto-heal will: analyze error → patch via Hermes → HMR reload → re-run E2E<br>
            → Or press ⌘K in Monaco to refactor manually
          </div>
        </div>
        <div>
          <div style="background:#1c0f0f;border:1px solid #7f1d1d;border-radius:12px;padding:13px">
            <div style="font-weight:700;color:#fff;margin-bottom:8px">Auto-Heal options</div>
            <button id="agx-fix2" style="width:100%;background:#facc15;color:#422006;border:none;padding:10px;border-radius:10px;font-weight:800;cursor:pointer;margin-bottom:8px">🤖 Fix with Hermes — 1 click</button>
            <button id="agx-swarmfix" style="width:100%;background:#2d1b4e;color:#d8b4fe;border:1px solid #5b21b6;padding:9px;border-radius:10px;cursor:pointer;margin-bottom:8px;font-weight:600">🌀 Swarm Fix — 4 agents</button>
            <button id="agx-rollback" style="width:100%;background:#1f2937;color:#d1d5db;border:1px solid #374151;padding:9px;border-radius:10px;cursor:pointer">🕰 Git rollback — last green</button>
            <div style="font-size:11px;color:#fca5a5;margin-top:10px;line-height:1.5">
              Tip: enable <code>OPENROUTER_API_KEY</code> in .env for LLM-powered auto-heal (qwen-coder free).<br>
              Fallback: local heuristic patches — const-ify, optional chaining, try/catch, stub missing fn.
            </div>
          </div>
          <div id="agx-heal-log" style="margin-top:12px;font-size:11.5px;color:#fed7aa;background:#1a0f0a;border:1px solid #7c2d12;border-radius:10px;padding:10px;min-height:54px;white-space:pre-wrap">Waiting…</div>
        </div>
      </div>
      <div style="background:#1a0b0b;border-top:1px solid #7f1d1d;padding:8px 18px;font-size:11px;color:#fca5a5;display:flex;gap:18px;flex-wrap:wrap">
        <span>Agentic OS v4.5 — Live Error Overlay</span>
        <span>• window.onerror + unhandledrejection</span>
        <span>• postMessage → Mission Control</span>
        <span>• /api/agent/fix → HMR</span>
      </div>
    `;
    el.querySelector('#agx-dismiss')?.addEventListener('click', ()=>{ el.remove(); });
    el.querySelector('#agx-reload')?.addEventListener('click', ()=> location.reload());
    const doFix = ()=> runHeal(payload);
    el.querySelector('#agx-fix')?.addEventListener('click', doFix);
    el.querySelector('#agx-fix2')?.addEventListener('click', doFix);
    el.querySelector('#agx-swarmfix')?.addEventListener('click', ()=> runHeal(payload, true));
    el.querySelector('#agx-rollback')?.addEventListener('click', ()=>{
      alert('Git rollback: open Monaco → 🕰 time-travel → pick last green version → Restore → HMR');
      // try postMessage to parent to open time-travel
      window.parent && window.parent.postMessage({type:'agentic-open-timetravel'}, '*');
    });
  }

  function escapeHtml(s){ return (s||'').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

  async function runHeal(payload, useSwarm){
    const logEl=document.getElementById('agx-heal-log');
    const setLog = t=>{ if(logEl) logEl.textContent=t; };
    setLog('🧠 Hermes analyzing…\n'+(payload.message||'').slice(0,180));
    try{
      // try to get current file source – best effort
      let code = '';
      try{
        // if page is preview served, try fetch self
        const r = await fetch(location.pathname + '?_heal_src=' + Date.now(), {cache:'no-store'});
        if(r.ok){ code = await r.text(); }
      }catch(e){}
      if(!code){
        // fallback: grab all inline scripts
        code = Array.from(document.querySelectorAll('script')).map(s=>s.textContent||'').join('\n\n// --- next script ---\n\n');
      }
      if(!code) code = '// source not accessible — sending error only\n';
      const body = {
        code: code.slice(0,18000),
        error: payload.message,
        stack: payload.stack||'',
        filepath: (payload.filename||location.pathname).split('/').pop() || 'index.html',
        language: 'javascript'
      };
      setLog('› POST /api/agent/fix …');
      const endpoint = useSwarm ? '/api/swarm/run' : '/api/agent/fix';
      let res, j;
      if(useSwarm){
        // swarm fix: use swarm with error prompt
        res = await fetch('/api/swarm/run', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({
            prompt: `Fix this runtime error:\n${payload.message}\n\nStack:\n${(payload.stack||'').slice(0,800)}\n\nFile: ${body.filepath}\n\nReturn ONLY the fixed code.`,
            agents: ['hermes','claude','gemini','grok'],
            strategy: 'judge'
          })
        });
        j = await res.json();
        if(j.ok && j.winner_output){
          // winner_output may be full file or patch – treat as fixed
          body.fixed_code = j.winner_output;
          setLog(`✓ Swarm winner: ${j.winner} — score ${j.winner_score}\nApplying…`);
          // continue to apply
          j.fixed = j.winner_output;
          j.explanation = `Swarm fix — ${j.winner} won — ${j.judge_reason}`;
        }
      } else {
        res = await fetch('/api/agent/fix', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify(body)
        });
        j = await res.json();
      }
      if(!j.ok && !j.fixed){ throw new Error(j.error||'fix failed'); }
      const fixed = j.fixed || j.winner_output || '';
      setLog(`✓ Fix ready — ${(j.explanation||'Hermes').slice(0,220)}\n\nDiff:\n${(j.diff||'').slice(0,600)}\n\n→ Applying HMR…`);
      // apply
      const applyRes = await fetch('/api/agent/fix/apply', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          filepath: body.filepath,
          fixed: fixed,
          explanation: j.explanation || 'auto-heal'
        })
      });
      const aj = await applyRes.json();
      if(aj.ok){
        setLog(`✅ Patched ${aj.path} — ${aj.bytes} bytes — HMR reloading…`);
        // notify parent
        window.parent && window.parent.postMessage({type:'agentic-heal-applied', path: aj.path}, '*');
        setTimeout(()=>{ location.reload(); }, 900);
      } else {
        throw new Error(aj.error||'apply failed');
      }
    }catch(e){
      setLog('✗ Auto-heal failed:\n'+e+'\n\nTry: Cmd+K in Monaco → “fix runtime error”\nOr: Git time-travel → rollback');
    }
  }

  function report(err, source, lineno, colno, errorObj){
    const payload = {
      message: err?.message || err || 'Script error',
      stack: err?.stack || (errorObj && errorObj.stack) || '',
      filename: source || location.href,
      lineno: lineno||0,
      colno: colno||0,
      userAgent: navigator.userAgent,
      url: location.href,
      time: Date.now()
    };
    // post to parent Mission Control
    try{ window.parent && window.parent.postMessage({type:'agentic-error', ...payload}, '*'); }catch(e){}
    // show overlay
    showOverlay(payload);
    // also console
    console.error('[Agentic OS Error Overlay]', payload);
    return false; // let default run too
  }

  window.addEventListener('error', (e)=>{
    report(e.message, e.filename, e.lineno, e.colno, e.error);
  });
  window.addEventListener('unhandledrejection', (e)=>{
    report(e.reason?.message || e.reason || 'Unhandled promise rejection', '', 0,0, e.reason);
  });
  // bridge console.error
  const _cerr = console.error;
  console.error = function(...args){
    try{
      const msg = args.map(a=> typeof a==='string'?a:(a?.message||JSON.stringify(a))).join(' ');
      if(/error|fail|exception|undefined|is not|reference/i.test(msg)){
        report(msg, location.href, 0,0, null);
      }
    }catch(e){}
    return _cerr.apply(console, args);
  };

  // signal ready
  try{ window.parent && window.parent.postMessage({type:'agentic-error-overlay-ready', url: location.href}, '*'); }catch(e){}
  console.log('%c[Agentic OS] Error Overlay active — v4.5','color:#ff9e64;font-weight:bold');
})();
