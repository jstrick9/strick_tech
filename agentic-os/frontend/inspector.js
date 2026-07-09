/* Agentic OS — Component Inspector — click-to-code v4.6 */
(function(){
  if(window.__AGENTIC_INSPECTOR__) return;
  window.__AGENTIC_INSPECTOR__ = true;
  let enabled=false;
  let hoverEl=null;
  let overlay=null;

  function ensureOverlay(){
    if(overlay) return overlay;
    overlay=document.createElement('div');
    overlay.id='agentic-inspect-overlay';
    overlay.style.cssText='position:fixed;pointer-events:none;z-index:2147483646;border:2px solid #7aa2f7;background:rgba(122,162,247,0.08);border-radius:6px;transition:all 60ms;display:none;box-shadow:0 0 0 1px rgba(122,162,247,.35),0 0 24px rgba(122,162,247,.18)';
    document.documentElement.appendChild(overlay);
    // label
    const lab=document.createElement('div');
    lab.id='agentic-inspect-label';
    lab.style.cssText='position:fixed;pointer-events:none;z-index:2147483647;background:#1a2340;color:#dbe6ff;font:11px ui-monospace,monospace;padding:3px 7px;border-radius:6px;border:1px solid #3a4a7a;white-space:nowrap;display:none;max-width:420px;overflow:hidden;text-overflow:ellipsis';
    document.documentElement.appendChild(lab);
    overlay._lab=lab;
    return overlay;
  }

  function getSelector(el){
    if(!el || el===document.documentElement) return 'html';
    const parts=[];
    let cur=el;
    let depth=0;
    while(cur && cur.nodeType===1 && depth<5){
      let s = cur.tagName.toLowerCase();
      if(cur.id){ s+='#'+cur.id; parts.unshift(s); break; }
      // class first
      const cls = (cur.className||'').toString().trim().split(/\s+/).filter(c=>c && !c.startsWith('agentic')).slice(0,2).join('.');
      if(cls) s+='.'+cls;
      // nth
      if(cur.parentElement){
        const siblings=[...cur.parentElement.children].filter(ch=>ch.tagName===cur.tagName);
        if(siblings.length>1){
          s+=`:nth-of-type(${siblings.indexOf(cur)+1})`;
        }
      }
      parts.unshift(s);
      cur=cur.parentElement;
      depth++;
    }
    return parts.join(' > ');
  }

  function getXPath(el){
    if(el.id) return `//*[@id="${el.id}"]`;
    const parts=[];
    while(el && el.nodeType===1){
      let idx=1, sib=el.previousSibling;
      while(sib){ if(sib.nodeType===1 && sib.nodeName===el.nodeName) idx++; sib=sib.previousSibling; }
      parts.unshift(el.nodeName.toLowerCase() + '['+idx+']');
      el=el.parentNode;
    }
    return parts.length ? '/'+parts.join('/') : '';
  }

  function showHover(el){
    if(!enabled || !el || el===document.documentElement || el===document.body) { hideHover(); return; }
    // skip our own overlay
    if(el.id && el.id.startsWith('agentic-')) return;
    hoverEl=el;
    const ov=ensureOverlay();
    const r=el.getBoundingClientRect();
    ov.style.display='block';
    ov.style.left=(r.left-2+window.scrollX)+'px';
    ov.style.top=(r.top-2+window.scrollY)+'px';
    ov.style.width=(r.width+4)+'px';
    ov.style.height=(r.height+4)+'px';
    const lab=ov._lab;
    if(lab){
      const tag = el.tagName.toLowerCase();
      const id = el.id ? '#'+el.id : '';
      const cls = el.className ? '.'+String(el.className).trim().split(/\s+/).slice(0,2).join('.') : '';
      const txt = (el.textContent||'').trim().slice(0,42).replace(/\s+/g,' ');
      lab.textContent = `${tag}${id}${cls}  —  "${txt}"`;
      lab.style.display='block';
      // position label above element if space, else below
      let lx = r.left + window.scrollX;
      let ly = r.top + window.scrollY - 24;
      if(ly < window.scrollY + 4) ly = r.bottom + window.scrollY + 4;
      lab.style.left = Math.max(6, lx) + 'px';
      lab.style.top = ly + 'px';
    }
  }

  function hideHover(){
    if(overlay){ overlay.style.display='none'; if(overlay._lab) overlay._lab.style.display='none'; }
    hoverEl=null;
  }

  function pickElement(el, ev){
    if(!enabled) return;
    ev.preventDefault();
    ev.stopPropagation();
    // build payload
    const payload = {
      type: 'agentic-inspect',
      tag: el.tagName.toLowerCase(),
      id: el.id||'',
      className: String(el.className||''),
      text: (el.textContent||'').trim().slice(0,240),
      innerHTML: el.innerHTML ? el.innerHTML.slice(0,600) : '',
      selector: getSelector(el),
      xpath: getXPath(el),
      attributes: {},
      rect: el.getBoundingClientRect(),
      href: el.href || el.getAttribute && el.getAttribute('href') || '',
      src: el.src || '',
      dataAgentic: el.getAttribute && el.getAttribute('data-agentic-id') || ''
    };
    // collect data-* attributes
    try{
      [...el.attributes].forEach(a=>{
        if(a.name.startsWith('data-') || ['id','class','role','name','type','testid','data-testid','aria-label'].includes(a.name)){
          payload.attributes[a.name]=a.value;
        }
      });
    }catch(e){}
    // send to parent
    try{ window.parent && window.parent.postMessage(payload, '*'); }catch(e){}
    // flash
    const ov=ensureOverlay();
    ov.style.borderColor='#9ece6a';
    ov.style.background='rgba(158,206,106,0.10)';
    setTimeout(()=>{
      ov.style.borderColor='#7aa2f7';
      ov.style.background='rgba(122,162,247,0.08)';
    }, 320);
    // brief toast in iframe
    console.log('%c[Agentic Inspector] → sent to Monaco', 'color:#9ece6a', payload.selector);
  }

  // mouse move throttled
  let lastMove=0;
  document.addEventListener('mousemove', (e)=>{
    if(!enabled) return;
    const now=Date.now();
    if(now-lastMove < 45) return;
    lastMove=now;
    const el=document.elementFromPoint(e.clientX, e.clientY);
    if(el) showHover(el);
  }, true);

  document.addEventListener('mouseout', (e)=>{
    if(!enabled) return;
    // if leaving window
    if(!e.relatedTarget) hideHover();
  }, true);

  document.addEventListener('click', (e)=>{
    if(!enabled) return;
    const el=document.elementFromPoint(e.clientX, e.clientY);
    if(el) pickElement(el, e);
  }, true);

  // keyboard toggle: Alt+Shift+I
  document.addEventListener('keydown', (e)=>{
    if((e.altKey && e.shiftKey && e.key.toLowerCase()==='i') || (e.metaKey && e.shiftKey && e.key.toLowerCase()==='i')){
      e.preventDefault();
      setEnabled(!enabled);
      parent && parent.postMessage({type:'agentic-inspect-toggled', enabled}, '*');
    }
    if(e.key==='Escape' && enabled){
      setEnabled(false);
      parent && parent.postMessage({type:'agentic-inspect-toggled', enabled:false}, '*');
    }
  });

  function setEnabled(v){
    enabled=!!v;
    document.documentElement.style.cursor = enabled ? 'crosshair' : '';
    if(!enabled) hideHover();
    // badge
    let badge=document.getElementById('agentic-inspect-badge');
    if(enabled){
      if(!badge){
        badge=document.createElement('div');
        badge.id='agentic-inspect-badge';
        badge.textContent='🔍 Inspect ON — click element • Esc exit • Alt+Shift+I toggle';
        badge.style.cssText='position:fixed;top:10px;left:50%;transform:translateX(-50%);z-index:2147483647;background:#1a2340;color:#cfe0ff;font:12px system-ui,sans-serif;padding:7px 14px;border-radius:999px;border:1px solid #3a4a7a;box-shadow:0 8px 30px rgba(0,0,0,.4)';
        document.documentElement.appendChild(badge);
        setTimeout(()=>{ try{badge.remove()}catch(e){} }, 3200);
      }
    } else {
      if(badge) badge.remove();
    }
  }

  // listen parent messages
  window.addEventListener('message', (ev)=>{
    const d=ev.data||{};
    if(d.type==='agentic-inspect-enable'){
      setEnabled(!!d.enabled);
    }
    if(d.type==='agentic-inspect-flash'){
      // highlight a selector from Monaco side
      try{
        let el=null;
        if(d.selector){ el=document.querySelector(d.selector); }
        if(!el && d.text){
          // find by text content
          const walker=document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
          let n, found=null;
          const needle=d.text.trim().slice(0,42);
          while(n=walker.nextNode()){
            if(n.nodeValue && n.nodeValue.includes(needle)){
              found=n.parentElement; break;
            }
          }
          el=found;
        }
        if(el){
          showHover(el);
          el.scrollIntoView({behavior:'smooth', block:'center'});
          // flash 3 times
          let c=0;
          const iv=setInterval(()=>{
            const ov=document.getElementById('agentic-inspect-overlay');
            if(ov){ ov.style.opacity = ov.style.opacity==='0.35' ? '1' : '0.35'; }
            if(++c>5){ clearInterval(iv); setTimeout(hideHover, 700); }
          }, 140);
        }
      }catch(e){}
    }
    if(d.type==='agentic-inspect-ping'){
      // respond so parent knows inspector is loaded
      try{ window.parent.postMessage({type:'agentic-inspect-ready', url: location.href}, '*'); }catch(e){}
    }
  });

  // auto-enable if URL has ?inspect=1
  if(location.search.includes('inspect=1')) setTimeout(()=>setEnabled(true), 350);

  // signal ready
  setTimeout(()=>{
    try{ window.parent && window.parent.postMessage({type:'agentic-inspect-ready', url: location.href}, '*'); }catch(e){}
  }, 300);

  console.log('%c[Agentic Inspector] click-to-code ready — Alt+Shift+I toggle', 'color:#bb9af7;font-weight:bold');
  // expose
  window.__agenticInspector = { enable:()=>setEnabled(true), disable:()=>setEnabled(false), toggle:()=>setEnabled(!enabled) };
})();
