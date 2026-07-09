/* Agent Roles Pipeline — /goal /research /code /review /ship — v4.9 */
(function(){
  console.log('[Pipeline] loading Agent Roles v4.9');
  const ROLES = [
    {id:'apollo', name:'Apollo', emoji:'🏛️', role:'planner', color:'#f5c542', desc:'Vision → Goals → Kanban'},
    {id:'artemis', name:'Artemis', emoji:'🔭', role:'researcher', color:'#7dd3a7', desc:'Market • competitors • RAG'},
    {id:'hermes', name:'Hermes', emoji:'⚡', role:'builder', color:'#7aa2f7', desc:'Code • E2E • HMR'},
    {id:'hephaestus', name:'Hephaestus', emoji:'🔨', role:'reviewer', color:'#e06b6b', desc:'Security • perf • tests'},
    {id:'jarvis', name:'Jarvis', emoji:'🎙️', role:'voice', color:'#2ac3de', desc:'Voice — STT → build → TTS'}
  ];

  function inject(){
    const tabs=document.querySelector('.tabs');
    if(!tabs) return false;
    if(document.querySelector('.tab[data-tab="pipeline"]')) return true;
    const b=document.createElement('div');
    b.className='tab';
    b.dataset.tab='pipeline';
    b.innerHTML='🏛️ Pipeline';
    b.style.color='#f5c542';
    b.style.fontWeight='700';
    tabs.appendChild(b);

    const center=document.querySelector('.center');
    if(center && !document.getElementById('pane-pipeline')){
      const pane=document.createElement('div');
      pane.id='pane-pipeline';
      pane.style.display='none';
      pane.style.height='100%';
      pane.style.overflow='auto';
      pane.style.background='#070811';
      pane.innerHTML=`
<div style="max-width:1280px;margin:0 auto;padding:18px">
  <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:14px">
    <div style="font-size:20px;font-weight:800;color:#ffe8a3">🏛️ Agent Team Orchestration</div>
    <span style="font-size:11px;background:#2a2108;color:#fcd34d;padding:3px 9px;border-radius:999px;border:1px solid #5a3a0f">/goal /research /code /review /ship</span>
    <span style="font-size:11px;background:#13231b;color:#9ece6a;padding:3px 9px;border-radius:999px;border:1px solid #294a2b">autonomous</span>
    <span class="spacer"></span>
    <button class="btn-sm btn-ghost" id="pl-history">📜 History</button>
    <button class="btn-sm btn-ghost" id="pl-voice">🎙️ Jarvis voice</button>
  </div>

  <!-- roles row -->
  <div id="pl-roles" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-bottom:16px">
  </div>

  <!-- main grid -->
  <div style="display:grid;grid-template-columns:380px 1fr;gap:16px;align-items:start">
    <!-- left: /goal input -->
    <div style="background:#0e1328;border:1px solid #22305a;border-radius:16px;padding:16px;position:sticky;top:12px">
      <div style="font-weight:700;color:#ffe8a6;margin-bottom:8px">/goal — Apollo planner</div>
      <textarea id="pl-goal-input" placeholder="/goal launch Stripe checkout SaaS for Charlotte SEO agency — Next.js, Tailwind, shadcn, convert 4%+

Try:
/goal build AI outreach CRM
/goal ship mobile onboarding flow
/goal refactor checkout to TypeScript"
        style="width:100%;height:110px;background:#0b1022;color:#f0e6c8;border:1px solid #2a355a;border-radius:12px;padding:11px;font-size:13px;resize:vertical"></textarea>
      
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:#8a95c7;margin:12px 0 6px">Pipeline stages</div>
      <div id="pl-stages" style="display:flex;flex-direction:column;gap:6px;font-size:12.5px">
        ${[
          ['goal','/goal','Apollo','Vision → Kanban',true],
          ['research','/research','Artemis','Market • RAG',true],
          ['code','/code','Hermes','Build • E2E',true],
          ['review','/review','Hephaestus','Security • perf',true],
          ['ship','/ship','Hermes','Vercel deploy',true]
        ].map(([id,cmd,agent,desc,chk])=>`
          <label style="display:flex;align-items:center;gap:9px;background:#0b1022;border:1px solid #1e2a4a;padding:8px 10px;border-radius:10px;cursor:pointer">
            <input type="checkbox" data-stage="${id}" ${chk?'checked':''} style="accent-color:#f5c542">
            <div style="flex:1">
              <b style="color:#ffe8a6">${cmd}</b> <span style="color:#8fa0d7">— ${agent}</span><br>
              <small style="color:#7a88a8">${desc}</small>
            </div>
          </label>
        `).join('')}
      </div>

      <div style="display:flex;gap:8px;margin-top:12px;align-items:center;flex-wrap:wrap">
        <select id="pl-target" style="background:#0b1022;color:#dbe6ff;border:1px solid #273560;border-radius:9px;padding:7px 10px;font-size:12.5px">
          <option value="web">web</option>
          <option value="expo">expo</option>
        </select>
        <label style="font-size:11.5px;color:#9aa7c7;display:flex;align-items:center;gap:5px">
          <input type="checkbox" id="pl-autofix" checked> auto-fix
        </label>
        <label style="font-size:11.5px;color:#9aa7c7;display:flex;align-items:center;gap:5px">
          <input type="checkbox" id="pl-force-ship"> force ship
        </label>
      </div>

      <button class="btn" id="pl-run" style="width:100%;margin-top:12px;background:linear-gradient(90deg,#fcd34d,#f59e0b);color:#1a1200;font-weight:800">
        🚀 Run /goal → /ship pipeline
      </button>
      <div id="pl-status" style="font-size:11.5px;color:#8fa0d7;margin-top:8px;min-height:18px"></div>

      <div style="margin-top:12px;border-top:1px dashed #223054;padding-top:10px;font-size:11px;color:#7b88a5;line-height:1.5">
        <b style="color:#fcd34d">Slash commands</b> — also work in Chat:<br>
        <code>/goal …</code> → Apollo plans<br>
        <code>/research …</code> → Artemis<br>
        <code>/code …</code> → Hermes builds<br>
        <code>/review</code> → Hephaestus<br>
        <code>/ship</code> → Vercel<br>
        <code>Hey Hermes, …</code> → Jarvis voice
      </div>
    </div>

    <!-- right: pipeline visual -->
    <div>
      <!-- stage tracker -->
      <div id="pl-tracker" style="display:flex;gap:0;margin-bottom:14px;overflow:auto;padding-bottom:4px">
        <!-- injected -->
      </div>

      <!-- output cards -->
      <div id="pl-output" style="display:flex;flex-direction:column;gap:12px">
        <div style="background:#0e1326;border:1px dashed #2a355a;border-radius:14px;padding:28px;text-align:center;color:#7a88a8">
          Run a <b style="color:#fcd34d">/goal</b> pipeline left →<br>
          <span style="font-size:12px">Apollo → Artemis → Hermes → Hephaestus → Ship</span><br><br>
          <div style="font-size:11px;color:#6b7ca5">
          Example:<br>
          <i>“/goal launch Stripe checkout SaaS for Charlotte SEO agency”</i>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Jarvis voice modal -->
<div id="jarvisModal" style="display:none;position:fixed;inset:0;background:rgba(2,6,14,.88);z-index:9998;align-items:center;justify-content:center">
  <div style="background:#0f152a;border:1px solid #2a3a5a;border-radius:18px;padding:22px;max-width:560px;width:92%;box-shadow:0 24px 80px rgba(0,0,0,.6)">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <div style="font-weight:800;color:#9eefff;font-size:16px">🎙️ Hermes-Jarvis — voice agent</div>
      <button onclick="document.getElementById('jarvisModal').style.display='none'" style="background:none;border:none;color:#8aa0c7;font-size:18px;cursor:pointer">✕</button>
    </div>
    <div style="font-size:12px;color:#8fa0c8;margin-bottom:10px">
      “Hey Hermes, build me a Stripe checkout page” → voice → STT → agent builds → TTS reply → preview updates<br>
      <span style="color:#6b7ca5">Local: Web Speech API • Server: Whisper.cpp + Piper TTS (optional)</span>
    </div>
    <textarea id="jarvis-input" placeholder='Say: "Hey Hermes, /goal launch …"  (type here — voice STT uses browser mic button)'
      style="width:100%;height:80px;background:#0b1022;color:#e0f7ff;border:1px solid #24445a;border-radius:12px;padding:10px;font-size:13px"></textarea>
    <div style="display:flex;gap:8px;margin-top:10px;align-items:center;flex-wrap:wrap">
      <button class="btn" id="jarvis-mic" style="background:#2ac3de;color:#02131a">🎤 Hold to talk</button>
      <button class="btn-sm btn" id="jarvis-send">Send → Hermes</button>
      <span style="font-size:11px;color:#7a8aaa" id="jarvis-stt-status">Web Speech API ready</span>
    </div>
    <div id="jarvis-out" style="margin-top:12px;background:#0b1122;border:1px solid #1d2a4a;border-radius:12px;padding:11px;font-size:12.5px;color:#c7e6ff;min-height:70px;white-space:pre-wrap">Jarvis response appears here…</div>
    <div style="font-size:10.5px;color:#6b7c9a;margin-top:8px">Tip: allow microphone → hands-free building while walking. Output auto-feeds into /code → /review → /ship.</div>
  </div>
</div>
`;
      const ref=document.getElementById('pane-vault')||document.querySelector('[id^="pane-"]');
      if(ref && ref.parentNode) ref.parentNode.appendChild(pane); else document.querySelector('.center').appendChild(pane);
    }
    hookPipeline();
    renderRoles();
    return true;
  }

  function hookPipeline(){
    document.querySelectorAll('.tab').forEach(tab=>{
      if(tab._pl) return; tab._pl=true;
      tab.addEventListener('click', ()=>{
        const t=tab.dataset.tab;
        document.querySelectorAll('[id^="pane-"]').forEach(p=>p.style.display='none');
        const el=document.getElementById('pane-'+t);
        if(el) el.style.display=t==='chat'?'flex':'block';
      });
    });
    const pt=document.querySelector('.tab[data-tab="pipeline"]');
    if(pt){ pt.addEventListener('click', ()=>{ document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active')); pt.classList.add('active'); }); }

    // bind once
    if(window.__plBound) return;
    window.__plBound=true;
    document.addEventListener('click', e=>{
      if(e.target && e.target.id==='pl-run') runPipeline();
      if(e.target && e.target.id==='pl-history') showHistory();
      if(e.target && e.target.id==='pl-voice') openJarvis();
      if(e.target && e.target.id==='jarvis-send') sendJarvis();
      if(e.target && e.target.id==='jarvis-mic') { e.preventDefault(); toggleMic(); }
    });
  }

  function renderRoles(){
    const el=document.getElementById('pl-roles');
    if(!el) return;
    el.innerHTML = ROLES.map(r=>`
      <div style="background:#0e1326;border:1px solid #242f52;border-radius:14px;padding:13px;position:relative;overflow:hidden">
        <div style="position:absolute;top:0;left:0;right:0;height:3px;background:${r.color}"></div>
        <div style="font-size:22px;margin-bottom:4px">${r.emoji}</div>
        <div style="font-weight:800;color:#fff;font-size:14px">${r.name} <span style="font-size:10.5px;color:${r.color};font-weight:600;text-transform:uppercase;letter-spacing:.06em">${r.role}</span></div>
        <div style="font-size:11.5px;color:#9aa7c7;margin-top:5px;line-height:1.4">${r.desc}</div>
        <div style="font-size:10.5px;color:#6b7ca5;margin-top:7px">${r.model}</div>
      </div>
    `).join('');
    renderTracker([]);
  }

  function renderTracker(activeStages){
    const el=document.getElementById('pl-tracker');
    if(!el) return;
    const stages=[
      {id:'goal',label:'/goal',agent:'Apollo',icon:'🏛️'},
      {id:'research',label:'/research',agent:'Artemis',icon:'🔭'},
      {id:'code',label:'/code',agent:'Hermes',icon:'⚡'},
      {id:'review',label:'/review',agent:'Hephaestus',icon:'🔨'},
      {id:'ship',label:'/ship',agent:'Ship',icon:'🚀'},
    ];
    el.innerHTML = stages.map((s,i)=>{
      const state = activeStages.includes(s.id) ? 'done' : (activeStages.length===i ? 'active' : 'todo');
      const bg = state==='done' ? '#13231b' : state==='active' ? '#2a2108' : '#141a2a';
      const col = state==='done' ? '#9ece6a' : state==='active' ? '#fcd34d' : '#7a88a8';
      const border = state==='done' ? '#294a2b' : state==='active' ? '#5a3a0f' : '#263250';
      return `<div style="flex:1;min-width:140px;background:${bg};border:1px solid ${border};border-radius:12px;padding:10px 12px;margin-right:8px;position:relative">
        <div style="font-size:11px;color:${col};font-weight:700">${s.icon} ${s.label}</div>
        <div style="font-size:10.5px;color:#8a97b8">${s.agent}</div>
        ${i<stages.length-1 ? `<div style="position:absolute;right:-12px;top:50%;transform:translateY(-50%);color:#3a4568;font-size:16px;z-index:2">→</div>`:''}
      </div>`;
    }).join('');
  }

  async function runPipeline(){
    const inputEl=document.getElementById('pl-goal-input');
    const goal=(inputEl?.value||'').trim();
    if(!goal){ inputEl?.focus(); alert('Enter /goal — e.g. "launch Stripe checkout SaaS"'); return; }
    const stages=[...document.querySelectorAll('#pl-stages input:checked')].map(i=>i.dataset.stage);
    const target=document.getElementById('pl-target')?.value||'web';
    const auto_fix=document.getElementById('pl-autofix')?.checked ?? true;
    const force_ship=document.getElementById('pl-force-ship')?.checked ?? false;
    const btn=document.getElementById('pl-run');
    const statusEl=document.getElementById('pl-status');
    if(btn){ btn.disabled=true; btn.textContent='⏳ Running pipeline…'; }
    if(statusEl) statusEl.textContent = 'Apollo planning… → Artemis → Hermes → Hephaestus → Ship';
    renderTracker([]);
    const outEl=document.getElementById('pl-output');
    if(outEl) outEl.innerHTML = stages.map(s=>`
      <div id="pl-step-${s}" style="background:#0e1326;border:1px solid #25325a;border-radius:14px;padding:14px;opacity:.7">
        <div style="font-weight:700;color:#fcd34d">${s.toUpperCase()} — running…</div>
        <div style="font-size:12px;color:#8a97b8;margin-top:4px" id="pl-step-${s}-body">…</div>
      </div>
    `).join('');
    try{
      const r=await fetch('/api/pipeline/run',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({goal, stages, target, auto_fix, force_ship})
      });
      const j=await r.json();
      if(!j.ok && j.status!=='needs_review'){ throw new Error(j.error||'pipeline failed'); }
      // render results
      const results=j.results||[];
      renderTracker(results.map(x=>x.stage));
      if(outEl){
        outEl.innerHTML = results.map(res=>{
          const meta = ROLES.find(rr=>rr.id===res.agent) || {emoji:'⚙️', color:'#7aa2f7', name:res.agent};
          const ok = res.status==='done';
          return `<div style="background:#0e1326;border:1px solid ${ok ? '#294a3a' : '#4a2a2a'};border-radius:14px;padding:15px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;flex-wrap:wrap;gap:6px">
              <div><span style="font-size:16px">${meta.emoji}</span>
                <b style="color:${meta.color};margin-left:6px">${res.stage.toUpperCase()}</b>
                <span style="font-size:11px;color:#8a97b8;margin-left:8px">${res.agent||meta.name} • ${res.duration_ms||'?'}ms • ${res.tokens||0}t</span>
              </div>
              <div style="font-size:11px;padding:2px 8px;border-radius:999px;background:${ok?'#13231b':'#2a1515'};color:${ok?'#9ece6a':'#ff8a8a'}">${res.status}</div>
            </div>
            <pre style="background:#080d1c;color:#c9d8ff;font-size:12px;line-height:1.5;white-space:pre-wrap;max-height:260px;overflow:auto;padding:10px;border-radius:10px;border:1px solid #1a2345;margin:0">${escapeHtml((res.output||'').slice(0,2800))}</pre>
            ${res.score ? `<div style="font-size:11px;color:#9ece6a;margin-top:7px">review score: ${res.score} • e2e: ${res.e2e_score||'—'}</div>`:''}
            ${res.winner ? `<div style="font-size:11px;color:#fcd34d;margin-top:4px">winner: ${res.winner}</div>`:''}
          </div>`;
        }).join('') +
        (j.ship_url ? `<div style="background:linear-gradient(135deg,#13231b,#1a1f2e);border:1px solid #2e5a34;border-radius:14px;padding:16px;text-align:center">
          <div style="font-weight:800;color:#9ece6a;font-size:15px">🚀 Shipped → <a href="${j.ship_url}" target="_blank" style="color:#9ece6a;text-decoration:underline">${j.ship_url}</a></div>
          <div style="font-size:11px;color:#8fbc8f;margin-top:6px">${j.total_latency_ms||j.duration_ms}ms • ${j.status} • ${j.strategy||'apollo→artemis→hermes→hephaestus→ship'}</div>
          <div style="margin-top:10px"><button onclick="navigator.clipboard.writeText('${j.ship_url}').then(()=>alert('Copied'))" class="btn-sm btn-ghost">📋 Copy URL</button>
          <button onclick="window.open('${j.ship_url}','_blank')" class="btn-sm btn" style="margin-left:6px">Open →</button></div>
        </div>` : '') +
        `<div style="font-size:11px;color:#7a88a8;text-align:center;padding:8px">run_id: ${j.run_id} • ${j.status} • <a href="#" onclick="showHistory();return false" style="color:#8fa0d7">history</a></div>`;
      }
      if(statusEl) statusEl.innerHTML = `✓ <b style="color:#9ece6a">${j.status}</b> — ${j.stages_run?.join(' → ')} — ${j.duration_ms}ms` + (j.ship_url ? ` — <a href="${j.ship_url}" target="_blank" style="color:#9ece6a">${j.ship_url}</a>` : '');
      // refresh kanban
      if(window.loadKanban) { try{window.loadKanban();}catch(e){} }
      // chat ping
      if(typeof addChat==='function'){
        addChat(`🏛️ Pipeline complete — ${j.status.toUpperCase()}

Goal: ${goal.slice(0,100)}…

${(j.results||[]).map(r=>`• **/${r.stage}** — ${r.agent} — ${r.duration_ms}ms — ${r.status}`).join('\n')}

${j.ship_url ? `🚀 Shipped → ${j.ship_url}\n` : ''}
Run ID: \`${j.run_id}\`

Next: monitor Kanban → /api/kanban — agents pull ‘doing’ autonomously
Voice: “Hey Hermes, /goal …” → Jarvis`, 'agent');
      }
    }catch(e){
      if(statusEl) statusEl.innerHTML = `<span style="color:#ff8a8a">✗ ${e}</span>`;
      alert('Pipeline error: '+e);
    }finally{
      if(btn){ btn.disabled=false; btn.textContent='🚀 Run /goal → /ship pipeline'; }
    }
  }

  function escapeHtml(s){ return (s||'').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

  async function showHistory(){
    try{
      const r=await fetch('/api/pipeline/history?limit=12'); const j=await r.json();
      if(!j.length){ alert('No pipeline runs yet — run a /goal first'); return; }
      alert('🏛️ Pipeline History — last '+j.length+':\n\n' + j.map((h,i)=>`${i+1}. [${h.ts}] ${h.status} — ${h.current_stage}\n   ${h.prompt}\n   ${h.result_url||'—'}\n   run_id: ${h.run_id}`).join('\n\n'));
    }catch(e){ alert(e); }
  }

  // ---- Jarvis voice ----
  let recognition=null, recognizing=false;
  function openJarvis(){
    const m=document.getElementById('jarvisModal');
    if(m){ m.style.display='flex'; document.getElementById('jarvis-input')?.focus(); }
  }
  window.openJarvis=openJarvis;

  function toggleMic(){
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const statusEl=document.getElementById('jarvis-stt-status');
    if(!SR){ alert('Web Speech API not supported in this browser — type your command, then Send → Hermes'); return; }
    if(recognizing && recognition){
      recognition.stop(); return;
    }
    recognition = new SR();
    recognition.lang='en-US';
    recognition.interimResults=true;
    recognition.continuous=false;
    recognition.onstart=()=>{ recognizing=true; if(statusEl) {statusEl.textContent='🎤 listening… speak now'; statusEl.style.color='#ffcf6e'}; const b=document.getElementById('jarvis-mic'); if(b){b.textContent='■ Stop'; b.style.background='#ff6b6b'} };
    recognition.onend=()=>{ recognizing=false; if(statusEl){statusEl.textContent='Web Speech API ready'; statusEl.style.color='#7a8aaa'}; const b=document.getElementById('jarvis-mic'); if(b){b.textContent='🎤 Hold to talk'; b.style.background='#2ac3de'} };
    recognition.onerror=(e)=>{ if(statusEl) statusEl.textContent='STT error: '+e.error; };
    recognition.onresult=(ev)=>{
      let transcript='';
      for(let i=ev.resultIndex;i<ev.results.length;i++){ transcript+=ev.results[i][0].transcript; }
      const inp=document.getElementById('jarvis-input');
      if(inp) inp.value=transcript;
      if(ev.results[ev.results.length-1].isFinal){
        // auto-send?
        setTimeout(()=>sendJarvis(), 500);
      }
    };
    recognition.start();
  }
  window.toggleMic=toggleMic;

  async function sendJarvis(){
    const inp=document.getElementById('jarvis-input');
    const out=document.getElementById('jarvis-out');
    const q=(inp?.value||'').trim();
    if(!q){ alert('Speak or type a command — e.g. “Hey Hermes, /goal launch Stripe checkout SaaS”'); return; }
    if(out) out.textContent='🧠 Hermes-Jarvis thinking… — RAG + swarm routing…';
    try{
      const r=await fetch('/api/agent/voice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:q})});
      const j=await r.json();
      if(out){
        out.textContent = j.reply_text + (j.actions?.length ? '\n\nActions:\n' + j.actions.map(a=>`• ${a.type}: ${a.status}`).join('\n') : '');
      }
      // TTS speak reply
      try{
        if('speechSynthesis' in window){
          window.speechSynthesis.cancel();
          const u=new SpeechSynthesisUtterance(j.reply_text.slice(0,420));
          u.rate=1.05; u.pitch=1.0; u.volume=0.9;
          // try pick a nice voice
          const vs = window.speechSynthesis.getVoices();
          const pick = vs.find(v=>/nova|zira|samantha|female|en-US/i.test(v.name)) || vs[0];
          if(pick) u.voice=pick;
          window.speechSynthesis.speak(u);
        }
      }catch(e){}
      // if actions include code → refresh UI
      if(j.actions && j.actions.find(a=>a.type==='code')){
        setTimeout(()=>{
          if(window.loadFileTree) loadFileTree();
          const ifr=document.getElementById('previewFrame');
          if(ifr) ifr.src = ifr.src.split('?')[0] + '?jarvis=' + Date.now();
        }, 900);
      }
    }catch(e){
      if(out) out.textContent='Jarvis error: '+e;
    }
  }

  // inject loop
  let tries=0;
  const iv=setInterval(()=>{
    tries++;
    if(inject() || tries>50) clearInterval(iv);
  }, 350);

  // slash commands in chat input — intercept /goal etc
  document.addEventListener('keydown', async (e)=>{
    const inp = e.target;
    if(inp && inp.id==='chatInput' && e.key==='Enter' && !e.shiftKey){
      const v = inp.value.trim();
      const m = v.match(/^\/(goal|research|code|review|ship)\s+(.+)/i);
      if(m){
        e.preventDefault();
        e.stopPropagation();
        const cmd=m[1].toLowerCase();
        const arg=m[2];
        inp.value='';
        // switch to pipeline tab
        document.querySelector('.tab[data-tab="pipeline"]')?.click();
        setTimeout(()=>{
          const goalInput=document.getElementById('pl-goal-input');
          if(goalInput) goalInput.value=arg;
          if(cmd==='goal'){
            // run full pipeline
            setTimeout(()=> document.getElementById('pl-run')?.click(), 200);
          } else {
            // single stage
            fetch('/api/'+cmd, {
              method:'POST', headers:{'Content-Type':'application/json'},
              body: JSON.stringify(cmd==='review'||cmd==='ship' ? {target:'web'} : {prompt:arg, query:arg, goal:arg})
            }).then(r=>r.json()).then(j=>{
              alert(`/${cmd} complete — ${j.status||'done'}\n\n` + (j.output||JSON.stringify(j)).slice(0,600));
            });
          }
        }, 250);
        // add chat bubble
        if(typeof addChat==='function'){
          addChat(`/${cmd} ${arg}\n\n→ routed to Agent Team Orchestration → ${ {goal:'Apollo',research:'Artemis',code:'Hermes',review:'Hephaestus',ship:'Hermes'}[cmd] }`, 'user');
        }
        return false;
      }
      // voice trigger: "hey hermes" or "jarvis"
      if(/^(hey hermes|jarvis|ok hermes)[,\s]/i.test(v)){
        e.preventDefault();
        e.stopPropagation();
        inp.value='';
        openJarvis();
        setTimeout(()=>{
          const ji=document.getElementById('jarvis-input');
          if(ji) { ji.value = v.replace(/^(hey hermes|jarvis|ok hermes)[,\s]+/i,''); ji.focus(); }
        }, 150);
        return false;
      }
    }
  }, true);

  console.log('[Pipeline] Agent Roles — Apollo · Artemis · Hermes · Hephaestus · Jarvis — ready');
})();
