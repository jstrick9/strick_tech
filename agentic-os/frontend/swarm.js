/* Multi-Agent Swarm — Fan-out / Judge v4.3 */
(function(){
  console.log('[Swarm] loading v4.3');
  function inject(){
    const tabs=document.querySelector('.tabs');
    if(!tabs) return false;
    if(document.querySelector('.tab[data-tab="swarm"]')) return true;
    const b=document.createElement('div');
    b.className='tab';
    b.dataset.tab='swarm';
    b.innerHTML='🌀 Swarm';
    b.style.color='#ff9e64';
    b.style.fontWeight='700';
    tabs.appendChild(b);
    // pane
    const center=document.querySelector('.center');
    if(center && !document.getElementById('pane-swarm')){
      const pane=document.createElement('div');
      pane.id='pane-swarm';
      pane.style.display='none';
      pane.style.height='100%';
      pane.style.overflow='auto';
      pane.style.background='#070912';
      pane.innerHTML=`
<div style="max-width:1320px;margin:0 auto;padding:18px">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap">
    <div style="font-size:20px;font-weight:800;color:#ffe0b5">🌀 Multi-Agent Swarm</div>
    <span style="font-size:11px;background:#2a1a12;color:#ff9e64;padding:3px 9px;border-radius:999px;border:1px solid #5a3a20">fan-out / judge</span>
    <span style="font-size:11px;background:#13231b;color:#9ece6a;padding:3px 9px;border-radius:999px;border:1px solid #294a2b">$0 free tiers</span>
    <span style="font-size:11px;background:#241630;color:#bb9af7;padding:3px 9px;border-radius:999px;border:1px solid #4a2c78">+23% quality</span>
    <span class="spacer"></span>
    <button class="device-btn" id="sw-history-btn">📜 History</button>
  </div>

  <div style="display:grid;grid-template-columns:360px 1fr;gap:16px;align-items:start">
    <!-- left control -->
    <div style="background:#0e1326;border:1px solid #1f2a4a;border-radius:16px;padding:16px;position:sticky;top:12px">
      <div style="font-weight:700;color:#ffd9a6;margin-bottom:8px">Swarm Prompt</div>
      <textarea id="sw-prompt" placeholder="e.g. Build me a Stripe checkout SaaS landing page — Next.js, Tailwind, convert at 4%+ — Charlotte SEO agency"
        style="width:100%;height:120px;background:#0b1022;color:#e8efff;border:1px solid #263560;border-radius:12px;padding:12px;font-size:13.5px;resize:vertical"></textarea>
      
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#8a95c7;margin:14px 0 8px">Agents — pick 2-6</div>
      <div id="sw-agent-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12.5px">
        <!-- injected -->
      </div>

      <div style="font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#8a95c7;margin:14px 0 8px">Strategy</div>
      <select id="sw-strategy" style="width:100%;background:#0b1022;color:#dbe6ff;border:1px solid #263560;border-radius:10px;padding:9px;font-size:13px">
        <option value="judge">Judge — pick best (fast)</option>
        <option value="merge">Merge — top2 fused</option>
        <option value="fanout">Fan-out — show all, no judge</option>
      </select>

      <div style="display:flex;gap:8px;margin-top:14px">
        <button class="btn" id="sw-run" style="flex:1;background:linear-gradient(90deg,#ff9e64,#f7768e);color:#1a0a00">🚀 Run Swarm</button>
      </div>
      <div id="sw-status" style="font-size:11.5px;color:#8fa0d7;margin-top:9px;min-height:18px"></div>

      <div style="margin-top:14px;border-top:1px dashed #223054;padding-top:12px;font-size:11.5px;color:#7b88b5;line-height:1.5">
        1 prompt → 4-6 agents parallel<br>
        Judge picks best → merges<br>
        ~2.1s p95 • $0 free tiers<br>
        RAG Memory Galaxy auto-grounded
      </div>
    </div>

    <!-- right results -->
    <div>
      <div id="sw-winner" style="display:none;background:linear-gradient(135deg,#1a1f3a,#18122d);border:1px solid #3a2f66;border-radius:16px;padding:16px;margin-bottom:14px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <div><b style="color:#ffd8a6;font-size:14px" id="sw-winner-title">Winner</b>
            <span id="sw-winner-meta" style="font-size:11px;color:#a99bd6;margin-left:8px"></span>
          </div>
          <div style="display:flex;gap:6px">
            <button class="btn-sm btn-ghost" id="sw-copy-winner">📋 Copy</button>
            <button class="btn-sm btn" id="sw-accept-winner">→ Accept to Monaco</button>
          </div>
        </div>
        <div id="sw-winner-body" style="background:#0a0f22;border:1px solid #222d52;border-radius:12px;padding:13px;font-size:13px;color:#d8e6ff;white-space:pre-wrap;max-height:310px;overflow:auto"></div>
      </div>

      <div id="sw-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
        <!-- agent cards injected -->
      </div>

      <div id="sw-merged" style="display:none;margin-top:14px;background:#0f1a25;border:1px solid #1f3a3a;border-radius:16px;padding:16px">
        <div style="font-weight:700;color:#9ece6a;margin-bottom:8px">🔀 Merged Output — top 2 fused</div>
        <div id="sw-merged-body" style="white-space:pre-wrap;font-size:13px;color:#cfe8d8;background:#0a1418;border:1px solid #1a3a2a;border-radius:10px;padding:12px;max-height:320px;overflow:auto"></div>
      </div>
    </div>
  </div>
</div>`;
      const ref = document.getElementById('pane-galaxy') || document.querySelector('[id^="pane-"]');
      if(ref && ref.parentNode) ref.parentNode.appendChild(pane); else center.appendChild(pane);
    }
    hook();
    loadAgentList();
    return true;
  }

  function hook(){
    document.querySelectorAll('.tab').forEach(tab=>{
      if(tab._swm) return;
      tab._swm=true;
      tab.addEventListener('click', ()=>{
        const t=tab.dataset.tab;
        document.querySelectorAll('[id^="pane-"]').forEach(p=>p.style.display='none');
        const el=document.getElementById('pane-'+t);
        if(el) el.style.display = t==='chat'?'flex':'block';
      });
    });
    const st=document.querySelector('.tab[data-tab="swarm"]');
    if(st){ st.addEventListener('click', ()=>{
      document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
      st.classList.add('active');
    });}
    document.getElementById('sw-run')?.addEventListener('click', runSwarm);
    document.getElementById('sw-copy-winner')?.addEventListener('click', ()=>{
      const txt=document.getElementById('sw-winner-body')?.textContent||'';
      navigator.clipboard.writeText(txt).then(()=>alert('Copied winner output'));
    });
    document.getElementById('sw-accept-winner')?.addEventListener('click', acceptWinner);
    document.getElementById('sw-history-btn')?.addEventListener('click', showHistory);
  }

  let swarmAgents=[];
  async function loadAgentList(){
    try{
      const r=await fetch('/api/swarm/agents');
      swarmAgents=await r.json();
    }catch(e){
      swarmAgents=[
        {id:'claude',name:'Claude',color:'#d97757',style:'analytical'},
        {id:'hermes',name:'Hermes',color:'#7aa2f7',style:'builder'},
        {id:'gemini',name:'Gemini',color:'#bb9af7',style:'code-first'},
        {id:'grok',name:'Grok',color:'#f7768e',style:'creative'},
        {id:'galaxy',name:'Memory Galaxy',color:'#c084fc',style:'RAG'},
        {id:'local',name:'Local LLM',color:'#e0af68',style:'private'},
      ];
    }
    const grid=document.getElementById('sw-agent-grid');
    if(!grid) return;
    const defaults = new Set(['claude','hermes','gemini','grok']);
    grid.innerHTML = swarmAgents.map(a=>`
      <label style="display:flex;align-items:center;gap:8px;background:#0b1022;border:1px solid #25345a;border-radius:10px;padding:8px 10px;cursor:pointer">
        <input type="checkbox" data-agent="${a.id}" ${defaults.has(a.id)?'checked':''} style="accent-color:${a.color}">
        <span>
          <b style="color:${a.color}">${a.name}</b><br>
          <small style="color:#8a9ac8">${a.style||a.model||''}</small>
        </span>
      </label>
    `).join('');
  }

  let lastWinnerText='';
  async function runSwarm(){
    const promptEl=document.getElementById('sw-prompt');
    const prompt=(promptEl?.value||'').trim();
    if(!prompt){ promptEl?.focus(); alert('Enter a swarm prompt'); return; }
    const agents=[...document.querySelectorAll('#sw-agent-grid input:checked')].map(i=>i.dataset.agent);
    if(agents.length<2){ alert('Pick at least 2 agents'); return; }
    const strategy=document.getElementById('sw-strategy')?.value||'judge';
    const statusEl=document.getElementById('sw-status');
    const runBtn=document.getElementById('sw-run');
    if(runBtn){ runBtn.disabled=true; runBtn.textContent='⏳ Swarming…'; }
    if(statusEl) statusEl.textContent = `fanning out to ${agents.join(' + ')}…`;
    // clear
    document.getElementById('sw-winner').style.display='none';
    document.getElementById('sw-merged').style.display='none';
    const grid=document.getElementById('sw-grid');
    if(grid){
      grid.innerHTML = agents.map(a=>{
        const meta = swarmAgents.find(x=>x.id===a)||{name:a,color:'#7aa2f7'};
        return `<div id="sw-card-${a}" style="background:#0e1326;border:1px solid #25345a;border-radius:14px;padding:13px;min-height:180px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <b style="color:${meta.color}">${meta.name}</b>
            <span style="font-size:11px;color:#8aa0d7" id="sw-${a}-meta">running…</span>
          </div>
          <div id="sw-${a}-body" style="font-size:12.5px;color:#b9c8ef;white-space:pre-wrap;max-height:260px;overflow:auto">⏳ ${meta.name} thinking…</div>
        </div>`;
      }).join('');
    }
    try{
      const r=await fetch('/api/swarm/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt, agents, strategy})});
      const j=await r.json();
      if(!j.ok){ throw new Error(j.error||'swarm failed'); }
      // fill cards
      (j.runs||[]).forEach(run=>{
        const bodyEl=document.getElementById(`sw-${run.agent}-body`);
        const metaEl=document.getElementById(`sw-${run.agent}-meta`);
        if(bodyEl) bodyEl.textContent = run.output||'(empty)';
        if(metaEl) metaEl.textContent = `${run.score?.toFixed?.(3)||run.score} • ${run.latency_ms}ms • ${run.tokens}t`;
        const card=document.getElementById(`sw-card-${run.agent}`);
        if(card && run.agent===j.winner){
          card.style.borderColor='#ffcf6e';
          card.style.boxShadow='0 0 0 1px rgba(255,207,110,.25), 0 8px 30px rgba(0,0,0,.35)';
        }
      });
      // winner
      if(j.winner){
        lastWinnerText=j.winner_output||'';
        document.getElementById('sw-winner').style.display='block';
        document.getElementById('sw-winner-title').textContent = `🏆 ${j.winner} — winner`;
        document.getElementById('sw-winner-meta').textContent = j.judge_reason||'';
        document.getElementById('sw-winner-body').textContent = j.winner_output||'';
      }
      // merged
      if(j.merged){
        document.getElementById('sw-merged').style.display='block';
        document.getElementById('sw-merged-body').textContent=j.merged;
        lastWinnerText=j.merged;
      }
      if(statusEl) statusEl.innerHTML = `✓ done in ${j.total_latency_ms}ms • ${j.total_tokens}t • <b style="color:#9ece6a">${j.winner||'—'}</b> won • ${j.improvement_vs_single||''}`;
      // ping chat
      if(typeof addChat==='function'){
        addChat(`🌀 Swarm complete\n\nPrompt: ${prompt.slice(0,90)}…\n\n🏆 Winner: ${j.winner} — score ${j.winner_score}\n\n${(j.winner_output||'').slice(0,260)}…\n\n→ Accept to Monaco | Merge output ready`, 'agent');
      }
    }catch(e){
      if(statusEl) statusEl.textContent = '✗ '+e;
      alert('Swarm error: '+e);
    }finally{
      if(runBtn){ runBtn.disabled=false; runBtn.textContent='🚀 Run Swarm'; }
    }
  }

  function acceptWinner(){
    if(!lastWinnerText){ alert('Run swarm first'); return; }
    // try push into Monaco
    try{
      if(window.monaco && window.monacoEditor){
        const ed = window.monacoEditor;
        const sel = ed.getSelection();
        ed.executeEdits('swarm', [{range: sel, text: '\n\n/* 🌀 Swarm accepted */\n'+lastWinnerText+'\n'}]);
        // switch to builder tab
        document.querySelector('.tab[data-tab="builder"]')?.click();
        alert('Inserted into Monaco ✓');
        return;
      }
    }catch(e){}
    // fallback copy
    navigator.clipboard.writeText(lastWinnerText).then(()=>alert('Copied to clipboard — paste into Monaco'));
  }

  async function showHistory(){
    try{
      const r=await fetch('/api/swarm/history?limit=12'); const j=await r.json();
      if(!j.length){ alert('No swarm history yet'); return; }
      alert('🌀 Swarm History — last '+j.length+':\n\n' + j.map((h,i)=>`${i+1}. [${h.ts}] ${h.winner||'?'} won — ${h.strategy}\n   ${h.prompt}\n   ${h.agents}`).join('\n\n'));
    }catch(e){ alert(e); }
  }

  // inject loop
  let tries=0;
  const ti=setInterval(()=>{
    tries++;
    if(inject() || tries>30) clearInterval(ti);
  }, 300);
  console.log('[Swarm] injector ready');
})();
