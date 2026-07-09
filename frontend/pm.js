/* Package Manager UI — npm / pnpm inside OS — v4.7 */
(function(){
  console.log('[PM] loading Package Manager UI v4.7');
  let pmState = {manager:'npm', deps:[], devDeps:[], query:'', results:[]};

  function injectPM(){
    // find builder-left panel
    const left = document.querySelector('.builder-left');
    if(!left || document.getElementById('pm-panel')) return true;
    // create panel after file-tree
    const ft = document.getElementById('fileTree');
    if(!ft) return false;
    const panel = document.createElement('div');
    panel.id='pm-panel';
    panel.style.cssText='border-top:1px solid #1d2238;background:#0b0f1c;max-height:420px;display:flex;flex-direction:column';
    panel.innerHTML = `
      <div style="padding:10px 12px;border-bottom:1px solid #1d2238;display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap">
        <div>
          <div style="font-size:12px;font-weight:700;color:#c7d8ff">📦 Dependencies</div>
          <div style="font-size:10.5px;color:#7a88b6" id="pm-summary">loading…</div>
        </div>
        <div style="display:flex;gap:4px">
          <button class="device-btn" data-pm="npm" style="font-size:10px;padding:3px 7px">npm</button>
          <button class="device-btn" data-pm="pnpm" style="font-size:10px;padding:3px 7px">pnpm</button>
          <button class="device-btn" data-pm="yarn" style="font-size:10px;padding:3px 7px">yarn</button>
        </div>
      </div>
      <div style="padding:9px 12px;">
        <input id="pm-search" placeholder="Search npm — e.g. framer-motion, zod, stripe…"
          style="width:100%;background:#0f1430;color:#dbe6ff;border:1px solid #263560;border-radius:8px;padding:8px 10px;font-size:12.5px;outline:none" />
        <div id="pm-results" style="max-height:150px;overflow:auto;margin-top:8px;display:none;background:#0c1226;border:1px solid #1e2a4a;border-radius:9px"></div>
      </div>
      <div style="flex:1;overflow:auto;padding:0 12px 10px;min-height:120px">
        <div style="font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;color:#7a88b6;margin-bottom:6px">installed</div>
        <div id="pm-installed" style="font-size:12px;color:#b8c5e8">
          <div style="color:#6b7ca5">loading package.json…</div>
        </div>
      </div>
      <div style="padding:8px 12px;border-top:1px solid #1d2238;display:flex;gap:6px;flex-wrap:wrap;font-size:11px">
        <button class="btn-sm btn-ghost" id="pm-refresh" style="flex:1">⟳ Refresh</button>
        <button class="btn-sm btn-ghost" id="pm-open-pkg">📄 package.json</button>
      </div>
    `;
    // insert after file-tree (which is flex:1)
    // fileTree parent is builder-left flex column – append at bottom before scaffold box?
    // find scaffold box
    const scaffoldBox = left.querySelector('div[style*="padding:10px;border-top:1px solid #1d2238"]');
    if(scaffoldBox){
      scaffoldBox.parentNode.insertBefore(panel, scaffoldBox);
    } else {
      left.appendChild(panel);
    }
    bindPM();
    loadPM();
    return true;
  }

  function bindPM(){
    const searchEl=document.getElementById('pm-search');
    if(searchEl && !searchEl._bound){
      searchEl._bound=true;
      let t;
      searchEl.addEventListener('input', ()=>{
        clearTimeout(t);
        t=setTimeout(()=> doSearch(searchEl.value.trim()), 280);
      });
      searchEl.addEventListener('keydown', e=>{
        if(e.key==='Enter'){ e.preventDefault(); doSearch(searchEl.value.trim()); }
        if(e.key==='Escape'){ hideResults(); }
      });
      searchEl.addEventListener('focus', ()=>{
        if(pmState.results.length) showResults();
      });
    }
    document.getElementById('pm-refresh')?.addEventListener('click', loadPM);
    document.getElementById('pm-open-pkg')?.addEventListener('click', openPackageJson);
    // manager toggle
    document.querySelectorAll('#pm-panel [data-pm]').forEach(btn=>{
      btn.addEventListener('click', ()=>{
        document.querySelectorAll('#pm-panel [data-pm]').forEach(b=>b.classList.remove('active'));
        btn.classList.add('active');
        pmState.manager = btn.dataset.pm;
        const sum=document.getElementById('pm-summary');
        if(sum) sum.textContent = `${pmState.deps.length + pmState.devDeps.length} deps • ${pmState.manager}`;
      });
    });
    // default active npm
    const nbtn=document.querySelector('#pm-panel [data-pm="npm"]');
    if(nbtn) nbtn.classList.add('active');
    // click outside to close results
    document.addEventListener('click', (e)=>{
      const box=document.getElementById('pm-results');
      const input=document.getElementById('pm-search');
      if(box && !box.contains(e.target) && e.target!==input){
        // don't hide immediately if clicking install button? already handled
        // hideResults();
      }
    });
  }

  async function loadPM(){
    const listEl=document.getElementById('pm-installed');
    const sumEl=document.getElementById('pm-summary');
    if(listEl) listEl.innerHTML='<div style="color:#6b7ca5">loading…</div>';
    try{
      const r=await fetch('/api/pm/list');
      const j=await r.json();
      pmState.deps=j.dependencies||[];
      pmState.devDeps=j.devDependencies||[];
      pmState.pkgPath=j.path||'package.json';
      const total = pmState.deps.length + pmState.devDeps.length;
      if(sumEl) sumEl.textContent = `${total} deps • ${j.name||'app'}@${j.version||'0.1.0'} • ${pmState.manager}`;
      renderInstalled();
    }catch(e){
      if(listEl) listEl.innerHTML='<div style="color:#ff8a8a">failed to load package.json</div>';
    }
  }

  function renderInstalled(){
    const el=document.getElementById('pm-installed');
    if(!el) return;
    const all = [
      ...pmState.deps.map(d=>({...d, dev:false})),
      ...pmState.devDeps.map(d=>({...d, dev:true}))
    ];
    if(!all.length){
      el.innerHTML='<div style="color:#6b7ca5">No dependencies yet — search above to add.<br><small>Try: framer-motion, zod, stripe, prisma</small></div>';
      return;
    }
    el.innerHTML = all.map(d=>`
      <div style="display:flex;align-items:center;justify-content:space-between;padding:5px 8px;border-radius:7px;margin-bottom:4px;background:#0f152a;border:1px solid #1e2746;font-size:12px">
        <div style="min-width:0;flex:1">
          <b style="color:#dbe6ff">${d.name}</b>
          <span style="color:#7a88b8;margin-left:6px">${d.wanted||''}</span>
          ${d.dev ? '<span style="font-size:10px;color:#a48bff;margin-left:6px">dev</span>':''}
          <div style="font-size:10.5px;color:#5f6d95">${d.installed ? '✓ '+(d.installed_version||'installed') : '<span style="color:#e0af68">not installed — run '+pmState.manager+' install</span>'}</div>
        </div>
        <button onclick="pmRemove('${d.name.replace(/'/g,"\\'")}')" style="background:none;border:none;color:#7a88b8;cursor:pointer;font-size:16px;padding:2px 6px" title="remove">×</button>
      </div>
    `).join('') +
    `<div style="margin-top:8px;font-size:11px;color:#6b7ca5">
      <code>${pmState.manager} install</code> — run in terminal at <code>${(pmState.pkgPath||'').split('/').slice(-2).join('/')}</code>
    </div>`;
  }

  window.pmRemove = async function(name){
    if(!confirm(`Remove ${name} from package.json?`)) return;
    try{
      const r=await fetch('/api/pm/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});
      const j=await r.json();
      if(j.ok){ loadPM(); if(window.addConsole) addConsole(`🗑 removed ${name} from package.json`); }
      else alert('Remove failed');
    }catch(e){ alert(e); }
  };

  async function doSearch(q){
    const box=document.getElementById('pm-results');
    if(!q){
      hideResults(); return;
    }
    if(box){
      box.style.display='block';
      box.innerHTML='<div style="padding:10px;color:#8fa0c7;font-size:12px">Searching npm…</div>';
    }
    try{
      const r=await fetch('/api/pm/search?q='+encodeURIComponent(q)+'&size=12');
      const j=await r.json();
      pmState.results=j.results||[];
      renderResults();
    }catch(e){
      if(box) box.innerHTML='<div style="padding:10px;color:#ff8a8a">search failed</div>';
    }
  }

  function renderResults(){
    const box=document.getElementById('pm-results');
    if(!box) return;
    const res=pmState.results;
    if(!res.length){
      box.innerHTML='<div style="padding:10px;color:#7a88b8;font-size:12px">No results</div>';
      box.style.display='block';
      return;
    }
    box.style.display='block';
    box.innerHTML = res.map((p,i)=>`
      <div style="padding:9px 11px;border-bottom:1px solid #1a2448;display:flex;justify-content:space-between;gap:10px;align-items:flex-start">
        <div style="min-width:0;flex:1">
          <div><b style="color:#e0e8ff">${p.name}</b> <span style="color:#8fa0d7;font-size:11px">${p.version||''}</span>
            ${p.score ? `<span style="font-size:10px;color:#6b7ca5;margin-left:6px">score ${(p.score*100|0)}%</span>`:''}
          </div>
          <div style="font-size:11px;color:#9aa7c7;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${(p.description||'').slice(0,120)}</div>
        </div>
        <div style="display:flex;flex-direction:column;gap:4px;flex-shrink:0">
          <button onclick="pmInstall('${p.name.replace(/'/g,"\\'")}','${(p.version||'latest').replace(/'/g,"\\'")}',false)" 
            style="background:#7aa2f7;color:#081028;border:none;padding:4px 9px;border-radius:7px;font-size:11px;font-weight:700;cursor:pointer">+ add</button>
          <button onclick="pmInstall('${p.name.replace(/'/g,"\\'")}','${(p.version||'latest').replace(/'/g,"\\'")}',true)"
            style="background:#1a2032;color:#b6c3e6;border:1px solid #263250;padding:3px 9px;border-radius:7px;font-size:10.5px;cursor:pointer">dev</button>
        </div>
      </div>
    `).join('') +
    `<div style="padding:7px 11px;font-size:10.5px;color:#6b7ca5;text-align:center">results from ${res[0]?.score ? 'npm registry' : 'curated fallback'} — click + add → updates package.json</div>`;
  }

  function hideResults(){
    const box=document.getElementById('pm-results');
    if(box) box.style.display='none';
  }

  window.pmInstall = async function(name, version, dev){
    const btn = event?.target;
    const orig = btn ? btn.textContent : '';
    if(btn){ btn.textContent='…'; btn.disabled=true; }
    try{
      const r = await fetch('/api/pm/add', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({name, version, dev: !!dev, manager: pmState.manager})
      });
      const j = await r.json();
      if(j.ok){
        if(window.addConsole) addConsole(`📦 ${pmState.manager} add ${name}@${j.version} ${dev? '--save-dev':''} → package.json updated`);
        if(typeof addChat==='function'){
          addChat(`📦 Installed **${name}@${j.version}** ${dev?'(dev)':''}

• package.json updated → \`${j.package_json?.split('/').slice(-2).join('/')}\`
• ${j.previous ? `Upgraded from ${j.previous}` : 'New dependency'}
• Next: \`${pmState.manager} install\` in terminal
• Monaco HMR will pick up new imports after install

Tip: You can keep coding — import '${name}' — TypeScript will resolve after npm install.

— Agentic OS Package Manager`, 'agent');
        }
        hideResults();
        document.getElementById('pm-search').value='';
        await loadPM();
      } else {
        alert('Install failed: '+(j.error||'unknown'));
      }
    }catch(e){
      alert('pm error: '+e);
    }finally{
      if(btn){ btn.textContent=orig; btn.disabled=false; }
    }
  };

  async function openPackageJson(){
    // open package.json in Monaco
    // first try known paths
    const tryPaths = ['package.json','app/package.json','next-app/package.json','frontend/package.json'];
    for(const p of tryPaths){
      try{
        const r = await fetch('/api/preview/read?path='+encodeURIComponent(p));
        if(r.ok){
          if(window.openFile){
            await window.openFile(p);
          } else {
            // fallback: switch to builder and alert
            document.querySelector('.tab[data-tab="builder"]')?.click();
            setTimeout(()=> alert('Open left file tree → '+p), 400);
          }
          return;
        }
      }catch(e){}
    }
    // fallback: fetch pm/list path
    try{
      const r=await fetch('/api/pm/list'); const j=await r.json();
      alert('package.json at:\n'+(j.path||'./package.json')+'\n\nOpen via Monaco → File tree → '+(j.path?.split('/').pop()||'package.json'));
      if(window.openFile && j.path){
        // try convert absolute to rel
        const rel = (j.path||'').includes('preview') ? j.path.split('preview/').pop() : 'package.json';
        window.openFile(rel).catch(()=>{});
      }
    }catch(e){ alert('Could not open package.json — check /preview/package.json in Monaco file tree'); }
  }

  // inject loop
  let tries=0;
  const iv=setInterval(()=>{
    tries++;
    if(injectPM() || tries>50) clearInterval(iv);
  }, 500);

  // expose
  window.PM = { refresh: loadPM, search: doSearch };
  console.log('[PM] Package Manager UI injected — npm / pnpm inside OS');
})();
