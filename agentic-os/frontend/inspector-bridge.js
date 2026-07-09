/* Component Inspector Bridge — Mission Control side — v4.6 */
(function(){
  console.log('[InspectorBridge] loading…');
  let inspectOn = false;
  let lastPick = null;

  // UI: add Inspect toggle button to preview toolbar
  function injectToggle(){
    // try multiple places: preview-toolbar, editor-toolbar
    const toolbars = document.querySelectorAll('.preview-toolbar, .editor-toolbar');
    toolbars.forEach(tb=>{
      if(tb && !tb.querySelector('#inspectToggleBtn')){
        const btn = document.createElement('button');
        btn.id='inspectToggleBtn';
        btn.className='device-btn';
        btn.style.cssText='background:#221a3a;color:#c9b6f5;border-color:#3d2a66;font-weight:600';
        btn.textContent='⊕ Inspect';
        btn.title='Click-to-code — click element in Live Preview → jump to Monaco (Alt+Shift+I)';
        btn.onclick = toggleInspect;
        // insert first
        tb.insertBefore(btn, tb.firstChild);
        // add status pill
        const pill=document.createElement('span');
        pill.id='inspectStatus';
        pill.style.cssText='font-size:11px;color:#8a92aa;margin-left:8px';
        pill.textContent='off';
        btn.insertAdjacentElement('afterend', pill);
      }
    });
  }

  function toggleInspect(){
    inspectOn = !inspectOn;
    const btn=document.getElementById('inspectToggleBtn');
    if(btn){
      btn.textContent = inspectOn ? '✕ Inspect ON' : '⊕ Inspect';
      btn.style.background = inspectOn ? '#3a1a5a' : '#221a3a';
      btn.style.color = inspectOn ? '#f0d6ff' : '#c9b6f5';
    }
    const pill=document.getElementById('inspectStatus');
    if(pill){ pill.textContent = inspectOn ? 'click element in preview →' : 'off'; pill.style.color = inspectOn ? '#bb9af7' : '#8a92aa'; }
    // send to iframe
    sendToPreview({type:'agentic-inspect-enable', enabled: inspectOn});
    if(inspectOn && window.addConsole) addConsole('🔍 Inspect ON — click any element in Live Preview → Monaco jumps to source');
    else if(window.addConsole) addConsole('Inspect OFF');
  }

  function sendToPreview(msg){
    const ifr=document.getElementById('previewFrame');
    try{ ifr && ifr.contentWindow && ifr.contentWindow.postMessage(msg, '*'); }catch(e){}
  }

  // receive picks from iframe
  window.addEventListener('message', async (ev)=>{
    const d=ev.data||{};
    if(d.type==='agentic-inspect'){
      lastPick=d;
      console.log('[InspectorBridge] pick', d);
      // update UI
      const pill=document.getElementById('inspectStatus');
      if(pill) pill.textContent = `${d.tag}${d.id?'#'+d.id:''} → Monaco…`;
      // try to find in Monaco
      await jumpToSource(d);
      // auto turn off inspect after pick? keep on for rapid picking – leave on, user Esc to exit
      // optionally flash
      if(window.addConsole) addConsole(`🔍 ${d.tag}${d.id?'#'+d.id:''} → ${d.selector?.slice(0,70)}`);
    }
    if(d.type==='agentic-inspect-toggled'){
      inspectOn = !!d.enabled;
      const btn=document.getElementById('inspectToggleBtn');
      if(btn){
        btn.textContent = inspectOn ? '✕ Inspect ON' : '⊕ Inspect';
      }
      const pill=document.getElementById('inspectStatus');
      if(pill) pill.textContent = inspectOn ? 'click element in preview →' : 'off';
    }
    if(d.type==='agentic-inspect-ready'){
      // inspector loaded in iframe – auto enable if toggle is on
      if(inspectOn){
        setTimeout(()=> sendToPreview({type:'agentic-inspect-enable', enabled:true}), 120);
      }
    }
  });

  async function jumpToSource(pick){
    // strategy:
    // 1. try find by id -> search all open monaco files? simpler search current file
    // 2. search all project files via /api/preview/files + /api/preview/read
    // 3. fuzzy match tag+class+text
    try{
      // get file list
      const rf = await fetch('/api/preview/files').then(r=>r.json()).catch(()=>[]);
      const files = (rf||[]).map(f=>f.path).filter(p=>/\.(html|jsx|tsx|js|ts|vue|svelte)$/.test(p));
      // prioritize current active tab
      const activeTab = window.activeTab || (window.monacoEditor && window.monacoEditor.__agentic_path) || 'index.html';
      const ordered = [activeTab, ...files.filter(f=>f!==activeTab)].slice(0,18);
      let found=null;
      // build search needles
      const needles = [];
      if(pick.id) needles.push(`id="${pick.id}"`, `id='${pick.id}'`, `#${pick.id}`);
      if(pick.className){
        const c1 = String(pick.className).trim().split(/\s+/)[0];
        if(c1) needles.push(`class="${c1}`, `className="${c1}`, `.${c1}`, c1);
      }
      // text content – first 24 chars, escape
      const txt = (pick.text||'').trim().replace(/\s+/g,' ').slice(0,48);
      if(txt.length>3) needles.push(txt.slice(0,24));
      // tag with attributes
      needles.push(`<${pick.tag}`);
      // search
      for(const path of ordered){
        try{
          const res = await fetch('/api/preview/read?path='+encodeURIComponent(path));
          if(!res.ok) continue;
          const content = await res.text();
          let idx=-1, needleUsed='';
          for(const n of needles){
            if(!n) continue;
            idx = content.toLowerCase().indexOf(n.toLowerCase());
            if(idx>=0){ needleUsed=n; break; }
          }
          if(idx>=0){
            // compute line/col
            const before = content.slice(0, idx);
            const line = before.split('\n').length;
            const col = before.split('\n').pop().length + 1;
            found = {path, line, col, needle: needleUsed, index: idx};
            break;
          }
        }catch(e){}
      }
      if(found){
        // open in Monaco
        if(window.openFile){
          await window.openFile(found.path);
        } else {
          // fallback: switch to builder tab and try to set activeTab
          document.querySelector('.tab[data-tab="builder"]')?.click();
        }
        // after short delay, reveal position
        setTimeout(()=>{
          try{
            if(window.monacoEditor){
              const ed=window.monacoEditor;
              ed.revealLineInCenter(found.line);
              ed.setPosition({lineNumber: found.line, column: found.col});
              ed.focus();
              // add decoration flash
              const deco = ed.deltaDecorations([], [{
                range: new monaco.Range(found.line,1,found.line,1),
                options: { isWholeLine:true, className:'agentic-inspect-line', overviewRuler:{color:'#bb9af7',position: monaco.editor.OverviewRulerLane.Right} }
              }]);
              setTimeout(()=>{ try{ ed.deltaDecorations(deco, []); }catch(e){} }, 1800);
              // store path on editor for reverse mapping
              ed.__agentic_path = found.path;
            }
          }catch(e){ console.warn(e); }
        }, 220);
        // flash in preview (reverse highlight)
        sendToPreview({type:'agentic-inspect-flash', selector: pick.selector, text: txt});
        // chat ping
        if(typeof addChat==='function'){
          addChat(`🔍 Component Inspector\n\nClicked: \`${pick.tag}${pick.id?'#'+pick.id:''}\`\n→ \`${found.path}:${found.line}\`\nMatched: “${found.needle.slice(0,48)}”\n\nMonaco jumped — edit → HMR <1s\n\nReverse: click a line in Monaco → flashes in preview (Cmd+Shift+I)`, 'agent');
        }
        return true;
      } else {
        // not found – still open builder
        if(typeof addChat==='function'){
          addChat(`🔍 Inspect: <${pick.tag}${pick.id?' #'+pick.id:''}> — "${txt?.slice(0,60)}…"\n\nNo exact source match found in ${ordered.length} files.\n\nTried: ${needles.slice(0,4).join(', ')}\n\nTip: add data-agentic-id for perfect mapping, or use Cmd+K “add data-agentic-id” — Hermes will annotate.\n\nSelector: \`${pick.selector}\``, 'agent');
        }
        return false;
      }
    }catch(e){
      console.error('[InspectorBridge] jump failed', e);
      return false;
    }
  }

  // reverse: Monaco cursor → flash in preview
  function setupMonacoReverse(){
    let lastPos=0;
    setInterval(()=>{
      try{
        if(!window.monacoEditor || !inspectOn) return;
        const pos = window.monacoEditor.getPosition();
        if(!pos) return;
        const key = pos.lineNumber; // throttle per line change
        if(key===lastPos) return;
        lastPos=key;
        const model = window.monacoEditor.getModel();
        if(!model) return;
        const lineText = model.getLineContent(pos.lineNumber) || '';
        // extract likely text / tag
        // find >text< pattern
        let m = lineText.match(/>([^<]{3,60})</);
        let flashText = m ? m[1].trim() : '';
        if(!flashText){
          // try class / id
          const cm = lineText.match(/class(Name)?\s*=\s*["']([^"']+)["']/);
          if(cm) flashText = cm[2].split(' ')[0];
        }
        if(flashText && flashText.length>2){
          sendToPreview({type:'agentic-inspect-flash', text: flashText});
        }
      }catch(e){}
    }, 900);
  }

  // keyboard: Cmd+Shift+I toggle inspect
  document.addEventListener('keydown', (e)=>{
    if((e.metaKey||e.ctrlKey) && e.shiftKey && e.key.toLowerCase()==='i'){
      e.preventDefault();
      toggleInspect();
    }
    if(e.key==='Escape' && inspectOn){
      toggleInspect();
    }
  });

  // inject toggle button repeatedly until UI ready
  let tries=0;
  const iv=setInterval(()=>{
    tries++;
    injectToggle();
    if(document.getElementById('inspectToggleBtn') || tries>40){
      clearInterval(iv);
      setupMonacoReverse();
    }
  }, 600);

  // expose
  window.Inspector = { toggle: toggleInspect, on: ()=>{ if(!inspectOn) toggleInspect(); }, off: ()=>{ if(inspectOn) toggleInspect(); } };
  console.log('[InspectorBridge] ready — Cmd+Shift+I toggle — click-to-code active');
})();
