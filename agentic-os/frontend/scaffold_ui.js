/* Scaffold UI — Next.js / SvelteKit / Expo — v4.5 */
(function(){
  function addButtons(){
    const box = document.querySelector('.builder-left div[style*="padding:10px"]');
    if(!box || box.dataset.suv) return;
    box.dataset.suv="1";
    const html = `
      <div class="mini" style="margin-bottom:7px;margin-top:10px;color:#c9b6ff">Framework templates — v4.5</div>
      <button class="device-btn" style="width:100%;margin-bottom:5px;background:#1a1f3a;color:#c9d8ff" onclick="scaffoldFw('nextjs saas')">
        ▲ Next.js 14 — SaaS
      </button>
      <button class="device-btn" style="width:100%;margin-bottom:5px;background:#1a1f3a;color:#ffb86e" onclick="scaffoldFw('sveltekit app')">
        ⚡ SvelteKit
      </button>
      <button class="device-btn" style="width:100%;margin-bottom:5px;background:#1a1f3a;color:#c084fc" onclick="scaffoldFw('expo native app')">
        📱 Expo — full
      </button>
      <button class="device-btn" style="width:100%;margin-bottom:8px;background:#14231b;color:#9ece6a" onclick="scaffoldFw('web app')">
        🌐 Web — multi-file
      </button>
      <div style="font-size:10.5px;color:#6b7ca5;line-height:1.45">
        Next.js → 17 files: app/, components/, lib/, api/<br>
        SvelteKit → 9 files: src/routes/<br>
        Expo → screens/, components/, hooks/<br>
        All: Tailwind + shadcn • RAG ready • E2E green
      </div>
    `;
    // insert before "+ New file" button
    const newFileBtn = box.querySelector('button[onclick="newFile()"]');
    if(newFileBtn){
      const div = document.createElement('div');
      div.innerHTML = html;
      newFileBtn.parentNode.insertBefore(div, newFileBtn);
    } else {
      box.insertAdjacentHTML('beforeend', html);
    }
  }
  window.scaffoldFw = async function(prompt){
    if(typeof addConsole==='function') addConsole('› scaffold '+prompt+' — v4.5 multi-file …');
    try{
      const r = await fetch('/api/preview/scaffold', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({prompt})
      });
      const j = await r.json();
      if(j.ok){
        if(typeof addChat==='function'){
          addChat(`✅ ${j.framework||'project'} scaffolded — v4.5

${j.count||j.files?.length||'?'} files created:
${(j.files||[]).slice(0,12).map(f=>' • '+f).join('\n')}
${(j.files||[]).length>12 ? ' … +' + ((j.files||[]).length-12) + ' more' : ''}

Preview: ${j.preview_url}
→ Open Monaco tabs left to edit
→ Live Preview right updates HMR
→ Git time-travel saves every version
→ E2E → Deploy → Ship

Next: Cmd+K refactor • /api/agent/edit • Swarm to improve`, 'agent');
        }
        // refresh file tree
        if(typeof loadFileTree==='function') setTimeout(loadFileTree, 400);
        // open first files in Monaco
        setTimeout(async ()=>{
          const files = j.files || [];
          // try open key files
          const priority = [
            'app/page.tsx','app/layout.tsx',
            'src/routes/+page.svelte',
            'mobile/screens/HomeScreen.tsx',
            'components/hero.tsx',
            'index.html','app.js'
          ];
          for(const p of priority){
            if(files.includes(p) && window.openFile){
              try{ await window.openFile(p); }catch(e){}
              break;
            }
          }
          // also refresh preview iframe
          const ifr=document.getElementById('previewFrame');
          if(ifr && j.preview_url) { ifr.src = j.preview_url + '?t=' + Date.now(); }
        }, 600);
      } else {
        alert('Scaffold failed: '+(j.error||'unknown'));
      }
    }catch(e){
      alert('Scaffold error: '+e);
      console.error(e);
    }
  };
  // try inject repeatedly
  let t=0;
  const iv=setInterval(()=>{
    t++;
    addButtons();
    if(document.querySelector('[onclick*="scaffoldFw"]') || t>40) clearInterval(iv);
  },500);
  console.log('[ScaffoldUI] v4.5 ready — Next.js / SvelteKit / Expo');
})();
