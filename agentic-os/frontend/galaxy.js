/* Memory Galaxy — Qdrant Vector RAG v4.2 */
(function(){
  console.log('[Galaxy] loading Memory Galaxy v4.2');
  // update top badges
  try{
    const brand = document.querySelector('.brand');
    if(brand){
      brand.innerHTML = '🧠 Agentic OS <span>Mission Control</span>'+
        ' <span class="badge">FREE BOARDROOM CLONE</span>'+
        ' <span class="badge2">v4.2 GALAXY</span>'+
        ' <span class="badge3">QDRANT RAG</span>'+
        ' <span class="badge4">VECTOR 384d</span>';
    }
  }catch(e){}
  // inject tab
  function inject(){
    const tabs = document.querySelector('.tabs');
    if(!tabs) return false;
    if(document.querySelector('.tab[data-tab="galaxy"]')) return true;
    const b=document.createElement('div');
    b.className='tab';
    b.dataset.tab='galaxy';
    b.innerHTML='🌌 Memory Galaxy';
    b.style.color='#c084fc';
    b.style.fontWeight='700';
    tabs.appendChild(b);
    // pane
    const center = document.querySelector('.center');
    if(center && !document.getElementById('pane-galaxy')){
      const pane=document.createElement('div');
      pane.id='pane-galaxy';
      pane.style.display='none';
      pane.style.height='100%';
      pane.style.overflow='hidden';
      pane.innerHTML = `
<div style="display:grid;grid-template-columns:300px 1fr 320px;height:100%;min-height:0;background:#070912">
  <!-- left -->
  <div style="border-right:1px solid #1d2238;background:#0c1020;overflow:auto;display:flex;flex-direction:column">
    <div style="padding:13px 14px;border-bottom:1px solid #1a2040">
      <div style="font-weight:800;font-size:15px;color:#e6d7ff">🌌 Memory Galaxy</div>
      <div style="font-size:11px;color:#9a8fc7;margin-top:3px">Qdrant • all-MiniLM-L6-v2 • 384d</div>
      <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">
        <span class="pill2" id="gx-stat-mem">0 memories</span>
        <span class="pill2" id="gx-stat-vec">0 vectors</span>
        <span class="pill2" id="gx-stat-qd">Qdrant …</span>
      </div>
    </div>
    <div style="padding:12px">
      <input id="gx-search" placeholder="semantic search… e.g. landing page headline SEO"
        style="width:100%;background:#0f1430;color:#d8e4ff;border:1px solid #273060;border-radius:10px;padding:10px 12px;font-size:13px;outline:none" />
      <div style="display:flex;gap:6px;margin-top:8px;font-size:11px;color:#8fa0d7">
        <label><input type="radio" name="gxmode" value="hybrid" checked> hybrid</label>
        <label><input type="radio" name="gxmode" value="vector"> vector</label>
        <label><input type="radio" name="gxmode" value="keyword"> keyword</label>
      </div>
      <div style="display:flex;gap:6px;margin-top:8px">
        <button class="btn-sm btn" id="gx-search-btn" style="flex:1">🔍 Search</button>
        <button class="btn-sm btn-ghost" id="gx-reindex">⟳ Reindex</button>
      </div>
    </div>
    <div style="padding:0 12px 8px;font-size:11px;color:#7d8ab8;text-transform:uppercase;letter-spacing:.08em">RAG Q&A</div>
    <div style="padding:0 12px 12px">
      <textarea id="gx-rag-q" placeholder="Ask your memories… e.g. 'find me that landing page headline from 3 weeks ago about SEO agency'"
        style="width:100%;height:70px;background:#0f1430;color:#dbe6ff;border:1px solid #273060;border-radius:10px;padding:9px;font-size:12.5px;resize:vertical"></textarea>
      <button class="btn-sm btn" id="gx-rag-btn" style="width:100%;margin-top:6px">✨ Ask Galaxy</button>
      <div id="gx-rag-out" style="margin-top:8px;background:#0d1328;border:1px solid #1f2a4a;border-radius:10px;padding:9px;font-size:12px;color:#c7d6ff;min-height:54px;white-space:pre-wrap">RAG answers appear here — hybrid vector+keyword, cites memories.</div>
    </div>
    <div style="border-top:1px solid #1a2040;margin-top:auto"></div>
    <div style="padding:12px">
      <div style="font-size:11px;color:#7d8ab8;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px">Ingest</div>
      <textarea id="gx-ingest-txt" placeholder="Paste note / vault excerpt / OMI transcript…"
        style="width:100%;height:64px;background:#0f1430;color:#dbe6ff;border:1px solid #273060;border-radius:9px;padding:8px;font-size:12px"></textarea>
      <div style="display:flex;gap:6px;margin-top:6px">
        <input id="gx-ingest-src" value="vault" style="flex:1;background:#0f1430;color:#cfe0ff;border:1px solid #273060;border-radius:8px;padding:6px 8px;font-size:11.5px" />
        <input id="gx-ingest-tags" placeholder="tags" style="width:100px;background:#0f1430;color:#cfe0ff;border:1px solid #273060;border-radius:8px;padding:6px 8px;font-size:11.5px" />
      </div>
      <button class="btn-sm btn-ghost" id="gx-ingest-btn" style="width:100%;margin-top:6px">+ Add to Galaxy</button>
    </div>
  </div>
  <!-- center 3D -->
  <div style="display:flex;flex-direction:column;min-width:0;background:#05070f;position:relative">
    <div style="padding:9px 14px;border-bottom:1px solid #1a2040;display:flex;align-items:center;gap:10px;font-size:12px;color:#aab8e8;flex-wrap:wrap">
      <b style="color:#e0d4ff">3D Memory Galaxy</b>
      <span style="opacity:.7">drag • zoom • click node</span>
      <span class="spacer"></span>
      <button class="device-btn" id="gx-refresh">⟳ Refresh graph</button>
      <button class="device-btn" id="gx-fit">⊡ Fit</button>
      <select id="gx-limit" style="background:#141d38;color:#cdd8ff;border:1px solid #273060;border-radius:7px;padding:4px 8px;font-size:11px">
        <option value="120">120 nodes</option>
        <option value="180" selected>180 nodes</option>
        <option value="300">300 nodes</option>
        <option value="500">500 nodes</option>
      </select>
    </div>
    <div id="gx-graph" style="flex:1;position:relative;background:radial-gradient(1200px 700px at 60% 40%, #0b1330 0%, #05070f 65%, #02040a 100%);overflow:hidden"></div>
    <div style="position:absolute;bottom:10px;left:14px;font-size:11px;color:#6d7aa8;background:rgba(8,12,28,.7);padding:5px 9px;border-radius:8px;border:1px solid #1b2345">
      <span id="gx-graph-stat">loading…</span>
    </div>
  </div>
  <!-- right detail -->
  <div style="border-left:1px solid #1d2238;background:#0c1020;overflow:auto;display:flex;flex-direction:column;min-width:0">
    <div style="padding:12px 14px;border-bottom:1px solid #1a2040">
      <div style="font-weight:700;color:#e2d8ff;font-size:13.5px">Selected Memory</div>
      <div id="gx-sel-meta" style="font-size:11px;color:#8a97c5;margin-top:3px">Click a star in the galaxy →</div>
    </div>
    <div id="gx-sel-body" style="padding:14px;font-size:13px;color:#c9d8ff;line-height:1.55;flex:1;overflow:auto">
      <div style="color:#7a88b8">No node selected.<br><br>🌌 Memory Galaxy visualizes your entire Shared Memory as a 3D force graph.<br><br>
      • <b style="color:#c084fc">Purple</b> = galaxy / vector<br>
      • Node size = content length<br>
      • Edges = same source / shared tags<br><br>
      Try:<br>
      1. Semantic search left →<br>
      2. Ask RAG Q&A<br>
      3. Click nodes → inspect<br>
      4. Ingest vault notes</div>
    </div>
    <div style="padding:12px;border-top:1px solid #1a2040">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#7b88b5;margin-bottom:7px">Top hits</div>
      <div id="gx-hits" style="max-height:260px;overflow:auto;font-size:12px"></div>
    </div>
  </div>
</div>`;
      // insert after other panes
      const ref = document.getElementById('pane-builder') || center.lastElementChild;
      if(ref && ref.parentNode) ref.parentNode.insertBefore(pane, ref.nextSibling);
      else center.appendChild(pane);
    }
    // hook tab clicks
    setTimeout(hookTabs, 80);
    return true;
  }

  function hookTabs(){
    document.querySelectorAll('.tab').forEach(tab=>{
      if(tab._gx) return;
      tab._gx=true;
      tab.addEventListener('click', ()=>{
        const t = tab.dataset.tab;
        document.querySelectorAll('[id^="pane-"]').forEach(p=> p.style.display='none');
        const el = document.getElementById('pane-'+t);
        if(el) el.style.display = (t==='chat'?'flex':'block');
        if(t==='galaxy'){
          initGalaxy();
        }
      });
    });
    // also keep original tab handler compatible – re-trigger
    const gxTab = document.querySelector('.tab[data-tab="galaxy"]');
    if(gxTab){
      gxTab.addEventListener('click', ()=>{
        document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
        gxTab.classList.add('active');
      });
    }
  }

  let graph, graphData, inited=false;
  async function initGalaxy(){
    if(!inited){
      // load 3d-force-graph if needed
      if(!window.ForceGraph3D){
        await loadScript('https://unpkg.com/three@0.160.0/build/three.min.js');
        await loadScript('https://unpkg.com/3d-force-graph@1.73.0/dist/3d-force-graph.min.js');
      }
      inited=true;
      setupGraph();
      bindUI();
      refreshStats();
      refreshGraph();
    }
  }

  function loadScript(src){
    return new Promise((res,rej)=>{
      const s=document.createElement('script');
      s.src=src; s.onload=res; s.onerror=rej;
      document.head.appendChild(s);
    });
  }

  function setupGraph(){
    const el = document.getElementById('gx-graph');
    if(!el || !window.ForceGraph3D) return;
    const width = el.clientWidth || 800;
    const height = el.clientHeight || 600;
    graph = ForceGraph3D()(el)
      .backgroundColor('#05070f')
      .nodeAutoColorBy('source')
      .nodeLabel(n => `${n.source} • ${n.label}`)
      .nodeVal('val')
      .linkDirectionalParticles(1)
      .linkDirectionalParticleWidth(1.2)
      .linkColor(()=> 'rgba(150,140,255,0.22)')
      .onNodeClick(node=>{
        showNode(node);
        // focus
        const distance = 120;
        const distRatio = 1 + distance/Math.hypot(node.x, node.y, node.z);
        graph.cameraPosition(
          { x: node.x * distRatio, y: node.y * distRatio, z: node.z * distRatio },
          node,
          900
        );
      })
      .onNodeHover(n=>{
        el.style.cursor = n ? 'pointer' : null;
      });
    // resize
    new ResizeObserver(()=>{ 
      if(graph) graph.width(el.clientWidth).height(el.clientHeight);
    }).observe(el);
  }

  async function refreshStats(){
    try{
      const r = await fetch('/api/memory/stats'); const j = await r.json();
      document.getElementById('gx-stat-mem').textContent = (j.sqlite_memories||0)+' memories';
      document.getElementById('gx-stat-vec').textContent = (j.vectors_sqlite||j.qdrant_points||0)+' vectors';
      document.getElementById('gx-stat-qd').textContent = (j.status==='active' ? 'Qdrant ✓' : 'fallback');
    }catch(e){}
  }

  async function refreshGraph(){
    const limitEl = document.getElementById('gx-limit');
    const limit = limitEl ? limitEl.value : 180;
    const statEl = document.getElementById('gx-graph-stat');
    if(statEl) statEl.textContent = 'loading galaxy…';
    try{
      const r = await fetch('/api/memory/galaxy?limit='+limit);
      const j = await r.json();
      graphData = j;
      if(graph){
        graph.graphData(j);
      }
      if(statEl) statEl.textContent = `${j.total_memories} stars • ${j.links.length} links • ${j.sources.length} sources`;
    }catch(e){
      if(statEl) statEl.textContent = 'graph load failed — '+e;
    }
  }

  function showNode(n){
    document.getElementById('gx-sel-meta').innerHTML =
      `<span style="color:${n.color}">${n.source}</span> • mem #${n.mem_id} • ${n.created_at||''}`;
    document.getElementById('gx-sel-body').innerHTML =
      `<div style="font-size:12px;color:#9fb0e8;margin-bottom:8px">${n.tags ? '🏷️ '+n.tags : ''}</div>`+
      `<div>${escapeHtml(n.label)} …</div>`+
      `<div style="margin-top:12px;display:flex;gap:7px">
        <button class="btn-sm btn-ghost" onclick="gxCopy(${n.mem_id})">📋 Copy</button>
        <button class="btn-sm btn-ghost" onclick="gxChatNode(${n.mem_id})">💬 Chat</button>
      </div>`;
    // load full content
    fetch('/api/memory/search?mode=keyword&limit=6&q=id:'+n.mem_id).catch(()=>{});
    // try get full via galaxy nodes? we already have label truncated – fetch full
    fetch('/api/memory/search?mode=keyword&limit=60').then(r=>r.json()).then(list=>{
      const full = list.find(x=>x.id==n.mem_id);
      if(full){
        document.getElementById('gx-sel-body').innerHTML =
          `<div style="font-size:11px;color:#8ea0d6;margin-bottom:6px">${full.source} • ${full.tags||''}</div>`+
          `<div style="white-space:pre-wrap">${escapeHtml(full.content||n.label)}</div>`+
          `<div style="margin-top:12px;display:flex;gap:7px">
            <button class="btn-sm btn-ghost" onclick="navigator.clipboard.writeText(\`${(full.content||'').replace(/`/g,'\\`').slice(0,1200)}\`)">📋 Copy</button>
            <button class="btn-sm btn-ghost" onclick="gxUseInChat(${n.mem_id})">→ Use in Chat</button>
          </div>`;
      }
    }).catch(()=>{});
  }

  function escapeHtml(s){ return (s||'').replace(/[&<>"']/g, c=> ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

  window.gxCopy = (id)=>{ alert('Copy mem #'+id+' — use right panel copy button'); };
  window.gxChatNode = (id)=>{ 
    const tab=document.querySelector('.tab[data-tab="chat"]'); if(tab) tab.click();
    const inp=document.getElementById('chatInput'); if(inp){ inp.value='Tell me about memory #'+id; inp.focus(); }
  };
  window.gxUseInChat = (id)=> gxChatNode(id);

  function bindUI(){
    document.getElementById('gx-search-btn')?.addEventListener('click', doSearch);
    document.getElementById('gx-search')?.addEventListener('keydown', e=>{ if(e.key==='Enter') doSearch(); });
    document.getElementById('gx-reindex')?.addEventListener('click', async ()=>{
      const btn = document.getElementById('gx-reindex'); if(btn){ btn.textContent='…indexing'; btn.disabled=true; }
      try{
        const r=await fetch('/api/memory/reindex',{method:'POST'});
        const j=await r.json();
        alert(`Reindexed ${j.vectorized}/${j.total} memories → ${j.model}`);
        refreshStats(); refreshGraph();
      }catch(e){ alert(e); }
      if(btn){ btn.textContent='⟳ Reindex'; btn.disabled=false; }
    });
    document.getElementById('gx-rag-btn')?.addEventListener('click', doRag);
    document.getElementById('gx-ingest-btn')?.addEventListener('click', doIngest);
    document.getElementById('gx-refresh')?.addEventListener('click', refreshGraph);
    document.getElementById('gx-fit')?.addEventListener('click', ()=>{ if(graph) graph.zoomToFit(600, 60); });
    document.getElementById('gx-limit')?.addEventListener('change', refreshGraph);
  }

  async function doSearch(){
    const q=document.getElementById('gx-search').value.trim();
    if(!q){ alert('Enter semantic query'); return; }
    const mode = document.querySelector('input[name="gxmode"]:checked')?.value || 'hybrid';
    const hitsEl=document.getElementById('gx-hits');
    if(hitsEl) hitsEl.innerHTML='searching…';
    try{
      const r=await fetch(`/api/memory/search?q=${encodeURIComponent(q)}&mode=${mode}&limit=18`);
      const j=await r.json();
      if(hitsEl){
        hitsEl.innerHTML = j.map((h,i)=>`
          <div class="memory-item" style="cursor:pointer" onclick="window._gxPick(${h.id})">
            <small style="color:#9bb0ff">${h.source||'mem'} · ${(h.score??0).toFixed(3)} ${h.keyword_hit?'🔑':''}</small><br>
            ${escapeHtml((h.content||'').slice(0,160))}${(h.content||'').length>160?'…':''}
          </div>`).join('') || '<div style="color:#7788b8">no hits</div>';
      }
      // highlight nodes in graph
      if(graph && graphData){
        const hitIds = new Set(j.map(x=>'m'+x.id));
        graph.nodeColor(n => hitIds.has(n.id) ? '#ffdb6e' : n.color);
        setTimeout(()=>{ if(graph) graph.nodeColor(n => n.color); }, 4200);
      }
      window._gxPick = (id)=>{
        const node = graphData?.nodes?.find(n=>n.mem_id==id);
        if(node) showNode(node);
      };
    }catch(e){
      if(hitsEl) hitsEl.textContent='error '+e;
    }
  }

  async function doRag(){
    const q=document.getElementById('gx-rag-q').value.trim();
    const out=document.getElementById('gx-rag-out');
    if(!q){ out.textContent='Enter a question first.'; return; }
    out.textContent='🧠 Galaxy RAG thinking…';
    try{
      const r=await fetch('/api/agent/rag',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q,top_k:6})});
      const j=await r.json();
      out.textContent = j.answer + `\n\n— ${j.model} • ${j.context_used} memories\n` + (j.hits||[]).map((h,i)=>`[${i+1}] ${h.source} · ${h.score}`).join('\n');
      // update hits panel
      const hitsEl=document.getElementById('gx-hits');
      if(hitsEl && j.hits){
        hitsEl.innerHTML = j.hits.map(h=>`<div class="memory-item"><small>${h.source} · ${h.score}</small><br>${escapeHtml((h.content||'').slice(0,140))}…</div>`).join('');
      }
    }catch(e){ out.textContent='RAG error: '+e; }
  }

  async function doIngest(){
    const txt=document.getElementById('gx-ingest-txt').value.trim();
    if(!txt){ alert('Paste content'); return; }
    const src=document.getElementById('gx-ingest-src').value||'vault';
    const tags=document.getElementById('gx-ingest-tags').value||'galaxy';
    try{
      const r=await fetch('/api/memory/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:txt, source:src, tags})});
      const j=await r.json();
      if(j.ok){
        alert('Ingested #'+j.id+' • vectorized: '+j.vectorized);
        document.getElementById('gx-ingest-txt').value='';
        refreshStats(); refreshGraph();
      } else alert('failed: '+(j.error||'unknown'));
    }catch(e){ alert(e); }
  }

  // try inject repeatedly until DOM ready
  let tries=0;
  const ti=setInterval(()=>{
    tries++;
    if(inject() || tries>25) clearInterval(ti);
  }, 250);

  // expose
  window.Galaxy = { refresh: refreshGraph, search: doSearch };
  console.log('[Galaxy] injector ready');
})();
