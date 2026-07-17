// Agentic OS v6.0 — Evals, observability, knowledge graph, RAG, agent evals
// Extracted from index.html (block 5)


'use strict';

// ══════════════════════════════════════════════════════════════════
//  AGENT EVALS — Like DeepEval + Confident AI
// ══════════════════════════════════════════════════════════════════
async function renderEvals() {
  const pane = document.getElementById('pane-evals');
  if (!pane) return;

  const [summary, datasets, abTests, attacks] = await Promise.all([
    fetch('/api/evals/summary').then(r=>r.ok?r.json():null).catch(()=>({summary:{},trend:[],by_agent:[]})),
    fetch('/api/evals/datasets').then(r=>r.ok?r.json():null).catch(()=>({datasets:[]})),
    fetch('/api/evals/ab-tests').then(r=>r.ok?r.json():null).catch(()=>({tests:[]})),
    fetch('/api/evals/red-team/attacks').then(r=>r.ok?r.json():null).catch(()=>({attacks:[]})),
  ]);

  const s = summary.summary || {};
  const passColor = (s.avg_score||0)>=70?'var(--success)':(s.avg_score||0)>=50?'var(--warning)':'var(--danger)';

  pane.innerHTML = `
  

  <div style="padding:20px;max-width:1100px;margin:0 auto">
    <div class="section-head">
      <div>
        <h2>🧮 Agent Evals</h2>
        <p>Like DeepEval + Confident AI — score every agent run on task completion, faithfulness, hallucination, safety</p>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn" onclick="evalRunQuick()">▶ Quick Eval</button>
        <button class="btn-sm" onclick="evalRedTeam()">🔴 Red Team</button>
      </div>
    </div>

    <!-- Stats -->
    <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:20px">
      ${[
        ['📊','Avg Score',`${Math.round(s.avg_score||0)}/100`,passColor],
        ['✅','Pass Rate',`${s.pass_rate||0}%`,'var(--success)'],
        ['🧪','Total Runs',s.total||0,'var(--text-0)'],
        ['❌','Failures',s.failures||0,'var(--danger)'],
        ['⏱','Avg Latency',`${Math.round(s.avg_latency||0)}ms`,'var(--text-2)'],
      ].map(([icon,label,val,col])=>`
        <div class="eval-metric-card">
          <div style="font-size:20px">${icon}</div>
          <div style="font-size:10px;color:var(--text-3);text-transform:uppercase">${label}</div>
          <div style="font-size:18px;font-weight:700;color:${col}">${val}</div>
        </div>`).join('')}
    </div>

    <!-- Tabs -->
    <div style="display:flex;border-bottom:1px solid var(--border);margin-bottom:16px">
      <button class="eval-tab active" onclick="evalTab('run',this)">▶ Run Eval</button>
      <button class="eval-tab" onclick="evalTab('history',this)">📋 History</button>
      <button class="eval-tab" onclick="evalTab('datasets',this)">📦 Datasets</button>
      <button class="eval-tab" onclick="evalTab('ab',this)">A/B Test</button>
      <button class="eval-tab" onclick="evalTab('redteam',this)">🔴 Red Team</button>
    </div>

    <!-- Run Eval tab -->
    <div id="eval-pane-run">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:12px">
        <div>
          <label style="font-size:11px;color:var(--text-3);font-weight:700;text-transform:uppercase;display:block;margin-bottom:4px">Prompt / Task</label>
          <textarea id="eval-prompt" rows="4" style="width:100%;background:var(--bg-2);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:12px;padding:10px;resize:vertical;box-sizing:border-box" placeholder="What did the agent ask?"></textarea>
        </div>
        <div>
          <label style="font-size:11px;color:var(--text-3);font-weight:700;text-transform:uppercase;display:block;margin-bottom:4px">Agent Response</label>
          <textarea id="eval-response" rows="4" style="width:100%;background:var(--bg-2);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:12px;padding:10px;resize:vertical;box-sizing:border-box" placeholder="What did the agent respond?"></textarea>
        </div>
      </div>
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">
        <input id="eval-expected" placeholder="Expected answer (optional)" style="flex:2;background:var(--bg-2);border:1px solid var(--border);border-radius:7px;color:var(--text-0);font-size:12px;padding:7px 10px">
        <select id="eval-agent" style="background:var(--bg-2);border:1px solid var(--border);border-radius:7px;color:var(--text-0);font-size:12px;padding:7px 8px">
          <option value="builder">builder</option>
          <option value="researcher">researcher</option>
          <option value="orchestrator">orchestrator</option>
        </select>
        <button class="btn" onclick="evalSubmit()" id="eval-submit-btn">🧮 Evaluate</button>
      </div>
      <div id="eval-result"></div>
    </div>

    <!-- History tab -->
    <div id="eval-pane-history" style="display:none">
      <div id="eval-history-list">Loading…</div>
    </div>

    <!-- Datasets tab -->
    <div id="eval-pane-datasets" style="display:none">
      <div style="display:flex;gap:8px;margin-bottom:12px">
        <button class="btn" onclick="evalCreateDataset()">＋ New Dataset</button>
      </div>
      <div id="eval-datasets-list">
        ${(datasets.datasets||[]).map(ds=>`
          <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:12px;margin-bottom:8px;display:flex;align-items:center;gap:10px">
            <div style="flex:1">
              <div style="font-weight:600;color:var(--text-0)">${escHtml(ds.name||'')}</div>
              <div style="font-size:11px;color:var(--text-3)">${ds.case_count||0} test cases</div>
            </div>
            <button class="btn-sm" onclick="evalRunDataset(${JSON.stringify(ds.id)})">▶ Run</button>
          </div>`).join('') || '<div style="color:var(--text-3);padding:12px">No datasets yet</div>'}
      </div>
    </div>

    <!-- A/B Test tab -->
    <div id="eval-pane-ab" style="display:none">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
        <div>
          <label style="font-size:11px;color:var(--accent);font-weight:700;display:block;margin-bottom:4px">Prompt A</label>
          <textarea id="ab-prompt-a" rows="5" style="width:100%;background:var(--bg-2);border:1px solid var(--accent)44;border-radius:8px;color:var(--text-0);font-size:12px;padding:10px;resize:vertical;box-sizing:border-box" placeholder="First prompt variant (use {{input}} for variable input)"></textarea>
        </div>
        <div>
          <label style="font-size:11px;color:#9d74f5;font-weight:700;display:block;margin-bottom:4px">Prompt B</label>
          <textarea id="ab-prompt-b" rows="5" style="width:100%;background:var(--bg-2);border:1px solid #9d74f544;border-radius:8px;color:var(--text-0);font-size:12px;padding:10px;resize:vertical;box-sizing:border-box" placeholder="Second prompt variant to compare"></textarea>
        </div>
      </div>
      <textarea id="ab-inputs" rows="3" style="width:100%;background:var(--bg-2);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:12px;padding:10px;resize:vertical;box-sizing:border-box;margin-bottom:8px" placeholder="Test inputs (one per line): 'What is FastAPI?', 'Explain async/await', ..."></textarea>
      <div style="display:flex;gap:8px">
        <input id="ab-name" placeholder="Test name" style="flex:1;background:var(--bg-2);border:1px solid var(--border);border-radius:7px;color:var(--text-0);font-size:12px;padding:7px 10px">
        <button class="btn" onclick="evalRunAB()">⚡ Run A/B Test</button>
      </div>
      <div id="ab-result" style="margin-top:12px"></div>
    </div>

    <!-- Red Team tab -->
    <div id="eval-pane-redteam" style="display:none">
      <div style="font-size:12px;color:var(--text-2);margin-bottom:12px">
        Run OWASP LLM Top 10 attacks against your agent. Tests: prompt injection, jailbreak, PII extraction, goal hijacking, and more.
      </div>
      <div style="display:flex;gap:8px;margin-bottom:12px">
        <select id="redteam-agent" style="background:var(--bg-2);border:1px solid var(--border);border-radius:7px;color:var(--text-0);font-size:12px;padding:7px 8px">
          <option value="builder">builder</option>
          <option value="researcher">researcher</option>
        </select>
        <button class="btn" style="background:rgba(232,82,82,.2);border-color:var(--danger);color:var(--danger)" onclick="evalRunRedTeam()">🔴 Run Red Team (${attacks.count||8} attacks)</button>
      </div>
      <div id="redteam-result"></div>
    </div>
  </div>`;

  evalLoadHistory();
}

function evalTab(tab, el) {
  ['run','history','datasets','ab','redteam'].forEach(t=>{
    const p=document.getElementById(`eval-pane-${t}`);
    if(p) p.style.display=t===tab?'block':'none';
  });
  document.querySelectorAll('#pane-evals .eval-tab').forEach(b=>b.classList.remove('active'));
  el?.classList.add('active');
  if(tab==='history') evalLoadHistory();
}

async function evalSubmit() {
  const prompt   = document.getElementById('eval-prompt')?.value?.trim();
  const response = document.getElementById('eval-response')?.value?.trim();
  const expected = document.getElementById('eval-expected')?.value||'';
  const agentId  = document.getElementById('eval-agent')?.value||'builder';
  if (!prompt||!response) { gmAlert('Enter both prompt and response'); return; }

  const btn=document.getElementById('eval-submit-btn');
  if(btn){btn.disabled=true;btn.textContent='⏳ Evaluating…';}

  const el=document.getElementById('eval-result');
  if(el) el.innerHTML='<div style="color:var(--text-2);padding:8px">Scoring with AI judge…</div>';

  try {
    const r=await fetch('/api/evals/run',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({prompt,response,expected,agent_id:agentId})});
    const d=await r.json();
    if(el) el.innerHTML=evalScoreHTML(d);
  } catch(ex){ if(el) el.innerHTML=`<div style="color:var(--danger)">${ex.message}</div>`; }
  if(btn){btn.disabled=false;btn.textContent='🧮 Evaluate';}
}

function evalScoreHTML(d) {
  const col=d.overall_score>=70?'var(--success)':d.overall_score>=50?'var(--warning)':'var(--danger)';
  return `
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px;margin-top:10px">
      <div style="display:flex;align-items:center;gap:14px;margin-bottom:14px">
        <div style="width:60px;height:60px;border-radius:50%;border:3px solid ${col};display:flex;align-items:center;justify-content:center;font-size:22px;font-weight:800;color:${col}">${d.overall_score}</div>
        <div>
          <div style="font-size:14px;font-weight:700;color:var(--text-0)">Overall Score: ${d.overall_score}/100</div>
          <span class="pass-badge ${d.pass_fail}">${d.pass_fail?.toUpperCase()}</span>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px">
        ${[
          ['Task Completion',Math.round((d.task_completion||0)*100)+'%'],
          ['Faithfulness',Math.round((d.faithfulness||0)*100)+'%'],
          ['Hallucination',(Math.round((d.hallucination||0)*100))+'%'],
          ['Quality',d.response_quality+'/100'],
          ['Safety',Math.round((d.safety_score||0)*100)+'%'],
        ].map(([label,val])=>`
          <div style="background:var(--bg-3);border-radius:8px;padding:8px;text-align:center">
            <div style="font-size:10px;color:var(--text-3)">${label}</div>
            <div style="font-size:16px;font-weight:700;color:var(--text-0)">${val}</div>
          </div>`).join('')}
      </div>
      ${(d.issues||[]).length?`<div style="margin-top:10px">
        ${(d.issues||[]).map((iss) =>`<div style="font-size:11px;padding:4px 8px;border-radius:5px;background:rgba(232,82,82,.1);color:var(--danger);margin-top:3px">⚠️ ${escHtml(iss.type||'')} — ${escHtml(iss.detail||'')}</div>`).join('')}
      </div>`:''}
    </div>`;
}

async function evalLoadHistory() {
  const el=document.getElementById('eval-history-list');
  if (!el) return;
  try {
    const r=await fetch('/api/evals/runs?limit=30');
    const d=await r.json();
    el.innerHTML=`
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;overflow:hidden">
        <div style="display:grid;grid-template-columns:1fr 60px 70px 70px 70px;padding:8px 14px;background:var(--bg-3);font-size:11px;font-weight:700;color:var(--text-3);text-transform:uppercase">
          <div>Prompt</div><div>Score</div><div>Status</div><div>Faithful</div><div>Halluc</div>
        </div>
        ${(d.runs||[]).map((r) =>`
          <div class="eval-run-row">
            <div style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-1)">${escHtml((r.prompt||'').slice(0,80))}</div>
            <div style="color:${r.overall_score>=70?'var(--success)':r.overall_score>=50?'var(--warning)':'var(--danger)'};font-weight:700">${r.overall_score}</div>
            <div><span class="pass-badge ${r.pass_fail}">${r.pass_fail}</span></div>
            <div style="color:var(--text-2)">${Math.round((r.faithfulness||0)*100)}%</div>
            <div style="color:var(--text-2)">${Math.round((r.hallucination||0)*100)}%</div>
          </div>`).join('') || '<div style="padding:20px;text-align:center;color:var(--text-3)">No eval runs yet. Run an eval above.</div>'}
      </div>`;
  } catch(e) { el.textContent='Error loading history'; }
}

async function evalRunQuick() {
  const prompt   = await gmPrompt('Enter a prompt to test:','What is FastAPI?');
  if (!prompt) return;
  const response = await gmPrompt('Enter an agent response to evaluate:','FastAPI is a modern web framework for building APIs.');
  if (!response) return;
  const el=document.getElementById('eval-pane-run');
  const pa=document.getElementById('eval-prompt');
  const ra=document.getElementById('eval-response');
  if(pa) pa.value=prompt;
  if(ra) ra.value=response;
  await evalSubmit();
}

async function evalCreateDataset() {
  const name=await gmPrompt('Dataset name:','My Test Suite');
  if(!name) return;
  const r=await fetch('/api/evals/datasets',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name,cases:[
      {prompt:'What is FastAPI?',expected:'FastAPI is a modern Python web framework'},
      {prompt:'What is SQLite?',expected:'SQLite is a lightweight embedded database'},
    ]})});
  const d=await r.json();
  if(d.ok) { showToast(`✅ Dataset created: ${name}`); renderEvals(); }
}

async function evalRunDataset(dsId) {
  const el=document.getElementById('eval-datasets-list');
  if(el) el.insertAdjacentHTML('beforeend','<div style="color:var(--text-2);font-size:12px;padding:8px">Running dataset...</div>');
  try {
    const resp=await fetch(`/api/evals/datasets/${encodeURIComponent(dsId)}/run`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{"agent_id":"builder"}'});
    // FIX 2: null guard on resp.body
    if (!resp.ok || !resp.body) { gmAlert(`Dataset run failed: HTTP ${resp.status}`); if(el) el.querySelectorAll('[style*="Running"]').forEach((n) =>n.remove()); return; }
    const reader=resp.body.getReader(); const dec=new TextDecoder(); let buf=''; let avg=0;
    while(true){const{done,value}=await reader.read();if(done)break;buf+=dec.decode(value,{stream:true});
      const parts=buf.split('\n\n');buf=parts.pop()||'';
      for(const part of parts){if(!part.startsWith('data:'))continue;
        try{const d=JSON.parse(part.slice(5).trim());
          if(d.type==='dataset_done'){avg=d.avg_score; showToast(`✅ Dataset done: avg ${d.avg_score}/100, ${d.pass_rate}% pass rate`);}
        }catch(e){}
      }
    }
    renderEvals();
  }catch(ex){ gmAlert('Dataset run failed: '+ex.message); }
}

async function evalRunAB() {
  const promptA=document.getElementById('ab-prompt-a')?.value?.trim();
  const promptB=document.getElementById('ab-prompt-b')?.value?.trim();
  const inputsRaw=document.getElementById('ab-inputs')?.value||'';
  const name=document.getElementById('ab-name')?.value||'A/B Test';
  if(!promptA||!promptB){gmAlert('Enter both prompts');return;}
  const inputs=inputsRaw.split('\n').map(s=>s.trim()).filter(Boolean).slice(0,10);
  if(!inputs.length){inputs.push('What is Python?');}

  const el=document.getElementById('ab-result');
  if(el) el.innerHTML='<div style="color:var(--text-2);font-size:12px">Running A/B test...</div>';

  try {
    const resp=await fetch('/api/evals/ab-test',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name,prompt_a:promptA,prompt_b:promptB,inputs})});
    // FIX 3: null guard on resp.body
    if (!resp.ok || !resp.body) { if(el) el.innerHTML=`<div style="color:var(--danger)">A/B test failed: HTTP ${resp.status}</div>`; return; }
    const reader=resp.body.getReader(); const dec=new TextDecoder(); let buf='';
    while(true){const{done,value}=await reader.read();if(done)break;buf+=dec.decode(value,{stream:true});
      const parts=buf.split('\n\n');buf=parts.pop()||'';
      for(const part of parts){if(!part.startsWith('data:'))continue;
        try{const d=JSON.parse(part.slice(5).trim());
          if(d.type==='ab_done'&&el){
            el.innerHTML=`
              <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px">
                <div style="font-size:16px;font-weight:700;color:var(--text-0);margin-bottom:12px">
                  Winner: <span style="color:${d.winner==='A'?'var(--accent)':'#9d74f5'}">Prompt ${d.winner}</span>
                  <span style="font-size:12px;color:var(--text-3)"> (+${d.diff} points)</span>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                  <div style="background:var(--bg-3);border-radius:8px;padding:12px;border:2px solid ${d.winner==='A'?'var(--accent)':'transparent'}">
                    <div style="font-weight:700;color:var(--accent)">Prompt A</div>
                    <div style="font-size:22px;font-weight:800;color:var(--text-0)">${d.avg_a}</div>
                    <div style="font-size:10px;color:var(--text-3)">avg score</div>
                  </div>
                  <div style="background:var(--bg-3);border-radius:8px;padding:12px;border:2px solid ${d.winner==='B'?'#9d74f5':'transparent'}">
                    <div style="font-weight:700;color:#9d74f5">Prompt B</div>
                    <div style="font-size:22px;font-weight:800;color:var(--text-0)">${d.avg_b}</div>
                    <div style="font-size:10px;color:var(--text-3)">avg score</div>
                  </div>
                </div>
              </div>`;
          }
        }catch(e){}
      }
    }
  }catch(ex){if(el) el.innerHTML=`<div style="color:var(--danger)">${ex.message}</div>`;}
}

async function evalRunRedTeam() {
  const agentId=document.getElementById('redteam-agent')?.value||'builder';
  const el=document.getElementById('redteam-result');
  if(el) el.innerHTML='<div style="color:var(--text-2);font-size:12px;padding:8px">Running attacks...</div>';

  try {
    const resp=await fetch('/api/evals/red-team',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent_id:agentId})});
    // FIX 4: null guard on resp.body
    if (!resp.ok || !resp.body) { if(el) el.innerHTML=`<div style="color:var(--danger)">Red team failed: HTTP ${resp.status}</div>`; return; }
    const reader=resp.body.getReader(); const dec=new TextDecoder(); let buf=''; const results =[];
    while(true){const{done,value}=await reader.read();if(done)break;buf+=dec.decode(value,{stream:true});
      const parts=buf.split('\n\n');buf=parts.pop()||'';
      for(const part of parts){if(!part.startsWith('data:'))continue;
        try{const d=JSON.parse(part.slice(5).trim());
          if(d.type==='attack_result'){results.push(d);}
          if(d.type==='redteam_done'&&el){
            el.innerHTML=`
              <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px">
                <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px">
                  <div style="font-size:40px;font-weight:800;color:${d.safety_score>=80?'var(--success)':d.safety_score>=60?'var(--warning)':'var(--danger)'}">${d.safety_score}</div>
                  <div>
                    <div style="font-weight:700;font-size:15px;color:var(--text-0)">Safety Score</div>
                    <div style="font-size:12px;color:var(--text-2)">${d.vulnerable} vulnerable / ${d.total} attacks</div>
                  </div>
                </div>
                ${results.map(r=>`
                  <div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-top:1px solid var(--border);font-size:12px">
                    <span style="font-size:16px">${r.status==='PASSED'?'✅':'❌'}</span>
                    <span style="font-weight:600;color:var(--text-0)">${escHtml(r.name||'')}</span>
                    <span style="color:var(--text-3)">${escHtml(r.category||'')}</span>
                    ${r.manipulated?`<span style="color:var(--danger);font-size:11px;margin-left:auto">VULNERABLE: ${escHtml(r.evidence||'')?.slice(0,50)}</span>`:'<span style="color:var(--success);margin-left:auto">Resistant</span>'}
                  </div>`).join('')}
              </div>`;
          }
        }catch(e){}
      }
    }
  }catch(ex){if(el) el.innerHTML=`<div style="color:var(--danger)">${ex.message}</div>`;}
}

async function evalRedTeam() {
  // FIX 6: navigate to evals pane first, then select redteam tab by data attribute or nth-child
  nav('evals');
  setTimeout(() => {
    // The redteam tab is the 5th .eval-tab button (index 4)
    const tabs = document.querySelectorAll('#pane-evals .eval-tab');
    const redteamTab = Array.from(tabs).find((b) => b.textContent?.includes('Red Team'));
    evalTab('redteam', redteamTab || tabs[tabs.length-1]);
  }, 100);
}


// ══════════════════════════════════════════════════════════════════
//  LLM OBSERVABILITY — Traces, DORA, EU AI Act
// ══════════════════════════════════════════════════════════════════
async function renderObservability() {
  const pane = document.getElementById('pane-observability');
  if (!pane) return;

  const [analytics, dora, compliance] = await Promise.all([
    fetch('/api/observability/analytics?days=7').then(r=>r.ok?r.json():null).catch(()=>({summary:{},by_model:[],hourly:[]})),
    fetch('/api/observability/dora').then(r=>r.ok?r.json():null).catch(()=>({})),
    fetch('/api/observability/compliance/eu-ai-act').then(r=>r.ok?r.json():null).catch(()=>({checks:[],score:0})),
  ]);

  const s = analytics.summary || {};
  const doraGradeColor = {Elite:'var(--success)',High:'var(--info)',Medium:'var(--warning)',Low:'var(--danger)'}[dora.grade||'Low'];
  const compColor = compliance.score>=80?'var(--success)':compliance.score>=50?'var(--warning)':'var(--danger)';

  pane.innerHTML = `
  

  <div style="padding:20px;max-width:1100px;margin:0 auto">
    <div class="section-head">
      <div>
        <h2>👁️ Observability</h2>
        <p>Like Langfuse + LangSmith — distributed traces, DORA metrics, EU AI Act compliance dashboard</p>
      </div>
      <button class="btn-sm" onclick="obsRefresh()">🔄 Refresh</button>
    </div>

    <!-- Stats -->
    <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:20px">
      ${[
        ['🔍',s.total_traces||0,'Traces'],
        ['⏱',Math.round(s.avg_latency||0)+'ms','Avg Latency'],
        ['🪙',(s.total_tokens||0).toLocaleString(),'Tokens'],
        ['💰','$'+((s.total_cost||0).toFixed(4)),'Cost'],
        ['❌',`${s.error_rate||0}%`,'Error Rate'],
      ].map(([icon,val,label])=>`
        <div class="obs-metric">
          <div style="font-size:18px">${icon}</div>
          <div style="font-size:18px;font-weight:700;color:var(--text-0)">${val}</div>
          <div style="font-size:10px;color:var(--text-3)">${label}</div>
        </div>`).join('')}
    </div>

    <!-- Tabs -->
    <div style="display:flex;border-bottom:1px solid var(--border);margin-bottom:16px">
      <button class="obs-tab active" onclick="obsTab('traces',this)">🔍 Traces</button>
      <button class="obs-tab" onclick="obsTab('dora',this)">📊 DORA</button>
      <button class="obs-tab" onclick="obsTab('models',this)">🤖 By Model</button>
      <button class="obs-tab" onclick="obsTab('compliance',this)">🇪🇺 EU AI Act</button>
    </div>

    <!-- Traces -->
    <div id="obs-pane-traces">
      <div style="display:flex;gap:8px;margin-bottom:10px">
        <input id="obs-search" placeholder="Search traces…" style="flex:1;background:var(--bg-2);border:1px solid var(--border);border-radius:7px;color:var(--text-0);font-size:12px;padding:7px 10px" oninput="obsSearchTraces(this.value)">
        <button class="btn-sm" onclick="obsLoadTraces()">↺</button>
      </div>
      <div id="obs-traces-list">Loading…</div>
    </div>

    <!-- DORA -->
    <div id="obs-pane-dora" style="display:none">
      <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:14px;margin-bottom:20px">
        ${Object.entries({
          deployment_frequency: dora.deployment_frequency,
          lead_time_ms: dora.lead_time_ms,
          change_failure_rate: dora.change_failure_rate,
          mttr_ms: dora.mttr_ms,
        }).map(([key,m])=>`
          <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px">
            <div style="font-size:11px;font-weight:700;color:var(--text-3);text-transform:uppercase;margin-bottom:6px">${key.replace(/_/g,' ')}</div>
            <div style="font-size:24px;font-weight:800;color:var(--text-0)">${m?.value||0}</div>
            <div style="font-size:12px;color:var(--text-2)">${m?.label||''}</div>
          </div>`).join('')}
      </div>
      <div style="background:var(--bg-2);border:1px solid ${doraGradeColor};border-radius:12px;padding:16px;text-align:center">
        <div style="font-size:40px;font-weight:800;color:${doraGradeColor}">${dora.grade||'?'}</div>
        <div style="font-size:14px;color:var(--text-0)">DORA Performance Level</div>
        <div style="font-size:12px;color:var(--text-2);margin-top:4px">Elite → High → Medium → Low</div>
      </div>
    </div>

    <!-- By Model -->
    <div id="obs-pane-models" style="display:none">
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;overflow:hidden">
        <div style="display:grid;grid-template-columns:1fr 60px 80px 80px 80px;padding:8px 14px;background:var(--bg-3);font-size:11px;font-weight:700;color:var(--text-3);text-transform:uppercase">
          <div>Model</div><div>Calls</div><div>Avg Ms</div><div>Tokens</div><div>Cost</div>
        </div>
        ${(analytics.by_model||[]).map((m) =>`
          <div style="display:grid;grid-template-columns:1fr 60px 80px 80px 80px;padding:10px 14px;border-top:1px solid var(--border);font-size:12px">
            <div style="color:var(--accent);font-family:monospace;font-size:11px">${escHtml((m.model||'').split('/').pop())}</div>
            <div>${m.calls||0}</div>
            <div>${Math.round(m.avg_latency||0)}ms</div>
            <div>${(m.tokens||0).toLocaleString()}</div>
            <div>$${((m.cost||0)).toFixed(4)}</div>
          </div>`).join('') || '<div style="padding:16px;text-align:center;color:var(--text-3)">No model data yet — run some agents</div>'}
      </div>
    </div>

    <!-- EU AI Act Compliance -->
    <div id="obs-pane-compliance" style="display:none">
      <div style="display:flex;align-items:center;gap:16px;margin-bottom:16px;background:var(--bg-2);border:1px solid ${compColor}44;border-radius:12px;padding:16px">
        <div style="width:70px;height:70px;border-radius:50%;border:4px solid ${compColor};display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:800;color:${compColor};flex-shrink:0">${compliance.score||0}%</div>
        <div>
          <div style="font-size:16px;font-weight:700;color:var(--text-0)">EU AI Act Compliance</div>
          <div style="font-size:12px;color:var(--text-2)">${compliance.overall_status} · ${compliance.compliant||0}/${compliance.total_checks||0} checks · Deadline: ${compliance.eu_ai_act_deadline||'Aug 2026'}</div>
          <div style="font-size:11px;color:var(--text-3);margin-top:3px">${compliance.note||''}</div>
        </div>
      </div>
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;overflow:hidden">
        ${(compliance.checks||[]).map((c) =>`
          <div class="compliance-check">
            <span style="font-size:18px">${c.status==='compliant'?'✅':c.status==='partial'?'⚠️':'❌'}</span>
            <div style="flex:1">
              <div style="font-weight:600;color:var(--text-0)">${escHtml(c.article||'')} — ${escHtml(c.name||'')}</div>
              <div style="font-size:11px;color:var(--text-2)">${escHtml(c.description||'')}</div>
              <div style="font-size:10px;color:var(--text-3);margin-top:2px">${escHtml(c.detail||'')}</div>
            </div>
            <span style="font-size:11px;padding:2px 7px;border-radius:4px;font-weight:700;${c.status==='compliant'?'background:rgba(61,186,122,.15);color:var(--success)':c.status==='partial'?'background:rgba(232,162,55,.15);color:var(--warning)':'background:rgba(232,82,82,.15);color:var(--danger)'}">${c.status}</span>
          </div>`).join('')}
      </div>
    </div>
  </div>`;

  obsLoadTraces();
}

function obsTab(tab, el) {
  ['traces','dora','models','compliance'].forEach(t=>{
    const p=document.getElementById(`obs-pane-${t}`);
    if(p) p.style.display=t===tab?'block':'none';
  });
  document.querySelectorAll('#pane-observability .obs-tab').forEach(b=>b.classList.remove('active'));
  el?.classList.add('active');
}

async function obsLoadTraces(q='') {
  const el=document.getElementById('obs-traces-list');
  if(!el) return;
  try {
    const url=q?`/api/observability/traces?q=${encodeURIComponent(q)}&limit=30`:'/api/observability/traces?limit=30';
    const r=await fetch(url);
    const d=await r.json();
    el.innerHTML=`
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;overflow:hidden">
        <div style="display:grid;grid-template-columns:1fr 80px 80px 70px 70px;padding:8px 14px;background:var(--bg-3);font-size:11px;font-weight:700;color:var(--text-3);text-transform:uppercase">
          <div>Trace</div><div>Agent</div><div>Latency</div><div>Tokens</div><div>Status</div>
        </div>
        ${(d.traces||[]).map((t) =>`
          <div class="trace-row" onclick="obsShowTrace(${JSON.stringify(t.id)})">
            <div style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-1)">${escHtml(t.name||t.input?.slice(0,60)||t.id)}</div>
            <div style="color:var(--text-2)">${escHtml(t.agent_id||'')}</div>
            <div style="color:var(--text-2)">${t.total_latency_ms||0}ms</div>
            <div style="color:var(--text-2)">${(t.total_tokens||0).toLocaleString()}</div>
            <div><span style="font-size:10px;padding:2px 6px;border-radius:4px;${t.status==='error'?'background:rgba(232,82,82,.15);color:var(--danger)':'background:rgba(61,186,122,.15);color:var(--success)'}">${t.status||'ok'}</span></div>
          </div>`).join('') || '<div style="padding:20px;text-align:center;color:var(--text-3)">No traces yet. Agent calls will appear here automatically.</div>'}
      </div>`;
  } catch(e) { el.textContent='Error loading traces'; }
}

function obsSearchTraces(q) {
  clearTimeout(window._obsSearchTimer);
  window._obsSearchTimer = setTimeout(()=>obsLoadTraces(q), 300);
}

async function obsShowTrace(traceId) {
  const r=await fetch(`/api/observability/traces/${encodeURIComponent(traceId)}`);
  const d=await r.json();
  const spans=d.spans||[];
  const overlay=document.createElement('div');
  overlay.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
  overlay.innerHTML=`
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:14px;max-width:700px;width:100%;max-height:80vh;overflow-y:auto;padding:20px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
        <h3 style="margin:0;color:var(--text-0)">Trace: ${traceId}</h3>
        <button onclick="this.closest('[style*=\"fixed\"]').remove()" style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
      </div>
      <div style="font-size:12px;color:var(--text-2);margin-bottom:12px">
        Agent: ${d.trace?.agent_id||'?'} · ${d.trace?.total_latency_ms||0}ms · ${d.trace?.total_tokens||0} tokens · $${((d.trace?.total_cost||0)).toFixed(5)}
      </div>
      ${spans.map((s) =>`
        <div style="margin-left:${s.parent_id?20:0}px;background:var(--bg-3);border-radius:8px;padding:10px 12px;margin-bottom:6px;border-left:3px solid ${s.span_type==='llm'?'var(--accent)':s.span_type==='tool'?'var(--success)':'var(--text-3)'}">
          <div style="display:flex;align-items:center;gap:6px;font-size:11px;font-weight:700;color:var(--text-0);margin-bottom:3px">
            <span>${s.span_type==='llm'?'🤖':s.span_type==='tool'?'🔧':'📥'}</span>
            <span>${escHtml(s.name||s.span_type)}</span>
            <span style="margin-left:auto;color:var(--text-3)">${s.latency_ms||0}ms · ${(s.tokens_in||0)+(s.tokens_out||0)}t</span>
          </div>
          ${s.model?`<div style="font-size:10px;color:var(--accent);font-family:monospace">${escHtml(s.model.split('/').pop())}</div>`:''}
          ${s.error?`<div style="font-size:11px;color:var(--danger)">${escHtml(s.error)}</div>`:''}
        </div>`).join('')}
    </div>`;
  overlay.onclick=e=>{if(e.target===overlay)overlay.remove();};
  document.body.appendChild(overlay);
}

async function obsRefresh() {
  const pane=document.getElementById('pane-observability');
  if(pane){pane.innerHTML='';} renderObservability();
}


// ══════════════════════════════════════════════════════════════════
//  KNOWLEDGE GRAPH
// ══════════════════════════════════════════════════════════════════
async function renderKnowledgeGraph() {
  const pane=document.getElementById('pane-knowledge-graph');
  if(!pane) return;

  const stats=await fetch('/api/knowledge-graph/stats').then(r=>r.ok?r.json():null).catch(()=>({}));
  const entities=await fetch('/api/knowledge-graph/entities?limit=20').then(r=>r.ok?r.json():null).catch(()=>({entities:[]}));

  pane.innerHTML=`
  

  <div style="display:flex;flex:1;height:100%;overflow:hidden">
    <!-- Sidebar -->
    <div style="width:280px;flex-shrink:0;background:var(--bg-1);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden">
      <div style="padding:12px;border-bottom:1px solid var(--border)">
        <div style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;margin-bottom:8px">🕸 Knowledge Graph</div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px;margin-bottom:8px">
          ${[['Entities',stats.entities||0],['Relations',stats.relations||0],['Facts',stats.facts||0]].map(([l,v])=>`
            <div style="background:var(--bg-2);border-radius:6px;padding:6px;text-align:center">
              <div style="font-size:14px;font-weight:700;color:var(--text-0)">${v}</div>
              <div style="font-size:9px;color:var(--text-3)">${l}</div>
            </div>`).join('')}
        </div>
        <div style="display:flex;gap:4px">
          <button class="btn" style="flex:1;font-size:11px;padding:6px" onclick="kgAddEntity()">＋ Entity</button>
          <button class="btn-sm" onclick="kgExtract()">🤖 Extract</button>
        </div>
      </div>
      <div style="padding:8px">
        <input id="kg-search" placeholder="Search entities…" style="width:100%;background:var(--bg-2);border:1px solid var(--border);border-radius:7px;color:var(--text-0);font-size:12px;padding:7px 10px;box-sizing:border-box" oninput="kgSearch(this.value)">
      </div>
      <div style="flex:1;overflow-y:auto;padding:0 8px 8px" id="kg-entity-list">
        ${(entities.entities||[]).map((e) =>`
          <div class="kg-entity-card" onclick="kgShowEntity(${JSON.stringify(e.id)})">
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">
              <span class="kg-type-badge">${e.type||'concept'}</span>
              <span style="font-weight:600;color:var(--text-0);font-size:12px">${escHtml(e.name||'')}</span>
            </div>
            <div style="font-size:11px;color:var(--text-2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml((e.description||'').slice(0,60))}</div>
          </div>`).join('') || '<div style="color:var(--text-3);font-size:12px;padding:8px">No entities yet. Add one or extract from text.</div>'}
      </div>
    </div>

    <!-- Main area -->
    <div style="flex:1;display:flex;flex-direction:column;overflow:hidden">
      <!-- Query bar -->
      <div style="padding:10px 14px;background:var(--bg-1);border-bottom:1px solid var(--border);display:flex;gap:8px;flex-shrink:0">
        <input id="kg-query" placeholder="Ask the knowledge graph: 'What does builder agent know about FastAPI?'" style="flex:1;background:var(--bg-2);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:13px;padding:9px 12px" onkeydown="if(event.key==='Enter')kgQuery()">
        <button class="btn" onclick="kgQuery()">Ask Graph</button>
      </div>

      <!-- Detail / result area -->
      <div style="flex:1;overflow-y:auto;padding:16px" id="kg-detail">
        <div style="color:var(--text-3);text-align:center;margin-top:40px">
          <div style="font-size:40px;margin-bottom:12px">🕸</div>
          <div style="font-size:16px;font-weight:600;margin-bottom:8px">Knowledge Graph Memory</div>
          <div style="font-size:13px;max-width:380px;margin:0 auto;line-height:1.7;color:var(--text-2)">
            Like Neo4j — entities and relationships that persist across all agent sessions. Extract facts from text, link concepts, and query the graph in natural language.
          </div>
        </div>
      </div>
    </div>
  </div>`;
}

async function kgSearch(q) {
  const el=document.getElementById('kg-entity-list');
  if(!el) return;
  if(!q) { const d=await fetch('/api/knowledge-graph/entities?limit=20').then(r=>r.ok?r.json():null).catch(()=>({entities:[]})); renderKGList(d.entities||[],el); return; }
  const d=await fetch(`/api/knowledge-graph/entities?q=${encodeURIComponent(q)}&limit=20`).then(r=>r.ok?r.json():null).catch(()=>({entities:[]}));
  renderKGList(d.entities||[],el);
}

function renderKGList(entities, el) {
  el.innerHTML=entities.map(e=>`
    <div class="kg-entity-card" onclick="kgShowEntity(${JSON.stringify(e.id)})">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">
        <span class="kg-type-badge">${e.type||'concept'}</span>
        <span style="font-weight:600;color:var(--text-0);font-size:12px">${escHtml(e.name||'')}</span>
      </div>
      <div style="font-size:11px;color:var(--text-2)">${escHtml((e.description||'').slice(0,60))}</div>
    </div>`).join('') || '<div style="color:var(--text-3);font-size:12px;padding:8px">No entities found</div>';
}

async function kgShowEntity(entityId) {
  const el=document.getElementById('kg-detail');
  if(!el) return;
  const d=await fetch(`/api/knowledge-graph/entities/${encodeURIComponent(entityId)}`).then(r=>r.ok?r.json():null).catch(()=>null);
  if(!d){el.innerHTML='<div style="color:var(--danger)">Failed to load entity</div>';return;}

  el.innerHTML=`
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">
        <span class="kg-type-badge" style="font-size:11px">${d.type||'concept'}</span>
        <h3 style="margin:0;color:var(--text-0)">${escHtml(d.name||'')}</h3>
        <span style="margin-left:auto;font-size:11px;color:var(--text-3)">Confidence: ${Math.round((d.confidence||1)*100)}%</span>
      </div>
      ${d.description?`<p style="font-size:13px;color:var(--text-2);margin:0 0 12px">${escHtml(d.description)}</p>`:''}

      ${d.facts?.length?`
        <div style="margin-bottom:12px">
          <div style="font-size:11px;font-weight:700;color:var(--text-3);text-transform:uppercase;margin-bottom:6px">Facts</div>
          ${d.facts.map((f) =>`<div style="font-size:12px;color:var(--text-1);padding:4px 0;border-bottom:1px solid var(--border)"><strong>${escHtml(f.predicate||'')}</strong>: ${escHtml(f.object_text||'')}</div>`).join('')}
        </div>`:''}

      ${d.outgoing_relations?.length?`
        <div style="margin-bottom:12px">
          <div style="font-size:11px;font-weight:700;color:var(--text-3);text-transform:uppercase;margin-bottom:6px">Outgoing Relations</div>
          ${d.outgoing_relations.map((r) =>`<div style="font-size:12px;color:var(--text-1);padding:4px 0;border-bottom:1px solid var(--border)">→ <strong>${escHtml(r.relation||'')}</strong> → <span style="color:var(--accent);cursor:pointer" onclick="kgShowEntity('${r.to_id}')">${escHtml(r.to_name||'')}</span></div>`).join('')}
        </div>`:''}

      ${d.incoming_relations?.length?`
        <div>
          <div style="font-size:11px;font-weight:700;color:var(--text-3);text-transform:uppercase;margin-bottom:6px">Incoming Relations</div>
          ${d.incoming_relations.map((r) =>`<div style="font-size:12px;color:var(--text-1);padding:4px 0;border-bottom:1px solid var(--border)"><span style="color:var(--accent);cursor:pointer" onclick="kgShowEntity('${r.from_id}')">${escHtml(r.from_name||'')}</span> → <strong>${escHtml(r.relation||'')}</strong> → this</div>`).join('')}
        </div>`:''}

      <div style="display:flex;gap:6px;margin-top:12px">
        <button class="btn-sm" onclick="kgTraverse(${JSON.stringify(entityId)})">🕸 Traverse Graph</button>
        <button class="btn-sm" onclick="kgAddRelation(${JSON.stringify(entityId)},${JSON.stringify(d.name||'')})">＋ Add Relation</button>
      </div>
    </div>`;
}

async function kgQuery() {
  const q=document.getElementById('kg-query')?.value?.trim();
  if(!q) return;
  const el=document.getElementById('kg-detail');
  if(el) el.innerHTML='<div style="color:var(--text-2);padding:12px">Querying graph…</div>';
  try {
    const r=await fetch('/api/knowledge-graph/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q})});
    const d=await r.json();
    if(el) el.innerHTML=`
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px">
        <div style="font-size:13px;color:var(--text-0);line-height:1.7;white-space:pre-wrap;margin-bottom:14px">${escHtml(d.answer||'')}</div>
        ${(d.entities_found||[]).length?`
          <div style="font-size:11px;font-weight:700;color:var(--text-3);text-transform:uppercase;margin-bottom:6px">Entities Found</div>
          <div style="display:flex;flex-wrap:wrap;gap:6px">
            ${(d.entities_found||[]).map((e) =>`<span style="background:var(--bg-3);border:1px solid var(--border);border-radius:6px;padding:3px 9px;font-size:11px;cursor:pointer;color:var(--accent)" onclick="kgShowEntity(${JSON.stringify(e.id)})">${escHtml(e.name||'')} <span style="color:var(--text-3)">(${e.type})</span></span>`).join('')}
          </div>`:''}
      </div>`;
  }catch(ex){if(el) el.innerHTML=`<div style="color:var(--danger)">${ex.message}</div>`;}
}

async function kgExtract() {
  const text=await gmPrompt('Paste text to extract entities and relationships from:','');
  if(!text) return;
  showToast('🧠 Extracting entities…');
  const r=await fetch('/api/knowledge-graph/extract',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,source:'user_input'})});
  const d=await r.json();
  if(d.ok) {
    showToast(`✅ Extracted ${d.entities_created} entities, ${d.relations_created} relations`);
    renderKnowledgeGraph();
  }
}

async function kgAddEntity() {
  const name=await gmPrompt('Entity name:','');
  if(!name) return;
  const type=await gmPrompt('Type (person/project/tool/concept/decision):','concept');
  const desc=await gmPrompt('Description (optional):','');
  await fetch('/api/knowledge-graph/entities',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,type:type||'concept',description:desc})});
  showToast(`✅ Entity "${name}" added`);
  renderKnowledgeGraph();
}

async function kgAddRelation(fromId, fromName) {
  const toName=await gmPrompt(`Relate "${fromName}" to entity:`, '');
  if(!toName) return;
  // Find entity by name
  const r=await fetch(`/api/knowledge-graph/entities?q=${encodeURIComponent(toName)}&limit=1`);
  const d=await r.json();
  const toEntity=d.entities?.[0];
  if(!toEntity) { gmAlert(`Entity "${toName}" not found. Add it first.`); return; }
  const relation=await gmPrompt('Relation type (DEPENDS_ON/USES/CREATED_BY/PART_OF/RELATED_TO):','RELATED_TO');
  await fetch('/api/knowledge-graph/relations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from_id:fromId,to_id:toEntity.id,relation:relation||'RELATED_TO'})});
  showToast(`✅ Relation added: ${fromName} → ${relation} → ${toName}`);
  kgShowEntity(fromId);
}

async function kgTraverse(entityId) {
  const r=await fetch(`/api/knowledge-graph/traverse/${encodeURIComponent(entityId)}?depth=2`);
  const d=await r.json();
  const el=document.getElementById('kg-detail');
  if(el) el.innerHTML=`
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px">
      <h4 style="margin:0 0 12px;color:var(--text-0)">Graph Traversal (2 hops) — ${d.node_count} nodes, ${d.edge_count} edges</h4>
      <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px">
        ${(d.nodes||[]).map((n) =>`<span style="background:var(--bg-3);border:1px solid var(--border);border-radius:6px;padding:4px 10px;font-size:12px;cursor:pointer;color:var(--text-1)" onclick="kgShowEntity(${JSON.stringify(n.id)})">${escHtml(n.name||'')} <span style="color:var(--text-3)">(${n.type})</span></span>`).join('')}
      </div>
      ${(d.edges||[]).map((e) =>`<div style="font-size:11px;color:var(--text-2);padding:3px 0">${escHtml(e.from_id.slice(-4))} → <strong>${escHtml(e.relation)}</strong> → ${escHtml(e.to_id.slice(-4))}</div>`).join('')}
    </div>`;
}


// ══════════════════════════════════════════════════════════════════
//  RAG PIPELINE BUILDER
// ══════════════════════════════════════════════════════════════════
async function renderRAG() {
  const pane=document.getElementById('pane-rag');
  if(!pane) return;

  const pipelines=await fetch('/api/rag/pipelines').then(r=>r.ok?r.json():null).catch(()=>({pipelines:[]}));

  pane.innerHTML=`
  <div style="padding:20px;max-width:900px;margin:0 auto">
    <div class="section-head">
      <div>
        <h2>📚 RAG Pipeline Builder</h2>
        <p>Like LlamaIndex — build document Q&A pipelines with chunking strategies, hybrid retrieval, and quality metrics</p>
      </div>
      <button class="btn" onclick="ragNewPipeline()">＋ New Pipeline</button>
    </div>

    ${(pipelines.pipelines||[]).length?`
      <div id="rag-pipeline-list">
        ${(pipelines.pipelines||[]).map((p) =>`
          <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:12px">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
              <span style="font-size:24px">📚</span>
              <div style="flex:1">
                <div style="font-weight:700;color:var(--text-0);font-size:14px">${escHtml(p.name||'')}</div>
                <div style="font-size:11px;color:var(--text-3)">${p.doc_count||0} docs · ${p.chunk_count||0} chunks · ${p.chunk_strategy} chunks @ ${p.chunk_size}</div>
              </div>
              <div style="display:flex;gap:6px">
                <button class="btn-sm" onclick="ragOpenPipeline(${JSON.stringify(p.id)},${JSON.stringify(p.name||'')})">Open</button>
                <button class="btn-sm" style="color:var(--danger)" onclick="ragDeletePipeline(${JSON.stringify(p.id)})">🗑</button>
              </div>
            </div>
          </div>`).join('')}
      </div>
    ` : `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:40px;text-align:center;color:var(--text-3)">
        <div style="font-size:40px;margin-bottom:12px">📚</div>
        <div style="font-size:16px;font-weight:600;margin-bottom:8px">No RAG Pipelines Yet</div>
        <div style="font-size:13px;max-width:380px;margin:0 auto 16px;line-height:1.7;color:var(--text-2)">
          Create a pipeline to upload documents, chunk and index them, then query with AI using citations.
        </div>
        <button class="btn" onclick="ragNewPipeline()">＋ Create First Pipeline</button>
      </div>`}
  </div>`;
}

async function ragNewPipeline() {
  const name=await gmPrompt('Pipeline name:','My Knowledge Base');
  if(!name) return;
  const strategy=await gmPrompt('Chunk strategy (paragraph/sentence/fixed/semantic):','paragraph');
  try {
    const r=await fetch('/api/rag/pipelines',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name,chunk_strategy:strategy||'paragraph',chunk_size:500,retrieval_k:5})});
    const d=await r.json();
    if(d.ok) { showToast(`✅ Pipeline "${name}" created`); renderRAG(); setTimeout(()=>ragOpenPipeline(d.pipeline_id,name),300); }
  } catch(ex) { gmAlert('Failed: '+ex.message); }
}

async function ragOpenPipeline(pipelineId, name) {
  const pane=document.getElementById('pane-rag');
  if(!pane) return;

  const d=await fetch(`/api/rag/pipelines/${encodeURIComponent(pipelineId)}`).then(r=>r.ok?r.json():null).catch(()=>null);
  if(!d){renderRAG();return;}

  pane.innerHTML=`
  <div style="padding:20px;max-width:900px;margin:0 auto">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">
      <button class="btn-sm" onclick="renderRAG()">← Back</button>
      <h2 style="margin:0;flex:1">${escHtml(name)}</h2>
      <span style="font-size:11px;color:var(--text-3)">${d.doc_count||0} docs · ${d.chunk_count||0} chunks</span>
    </div>

    <!-- Upload doc -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:16px">
      <div style="font-size:13px;font-weight:700;margin-bottom:10px">📄 Add Document</div>
      <textarea id="rag-doc-content" rows="5" style="width:100%;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:12px;padding:10px;resize:vertical;box-sizing:border-box" placeholder="Paste document content here…"></textarea>
      <div style="display:flex;gap:8px;margin-top:8px">
        <input id="rag-doc-name" placeholder="Filename (e.g. fastapi_docs.txt)" style="flex:1;background:var(--bg-3);border:1px solid var(--border);border-radius:7px;color:var(--text-0);font-size:12px;padding:7px 10px">
        <button class="btn" onclick="ragAddDoc(${JSON.stringify(pipelineId)})">Add Document</button>
      </div>
    </div>

    <!-- Documents list -->
    ${(d.documents||[]).length?`
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;margin-bottom:16px;overflow:hidden">
        <div style="padding:10px 14px;border-bottom:1px solid var(--border);font-weight:700;font-size:13px">📁 Documents</div>
        ${d.documents.map((doc) =>`
          <div style="display:flex;align-items:center;gap:8px;padding:8px 14px;border-bottom:1px solid var(--border);font-size:12px">
            <span>📄</span>
            <span style="color:var(--text-1);flex:1">${escHtml(doc.filename||'')}</span>
            <span style="color:var(--text-3)">${doc.chunk_count||0} chunks</span>
            <button class="btn-sm" style="color:var(--danger)" onclick="ragDeleteDoc(${JSON.stringify(pipelineId)},${JSON.stringify(doc.id)})">🗑</button>
          </div>`).join('')}
      </div>`:''}

    <!-- Query -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px">
      <div style="font-size:13px;font-weight:700;margin-bottom:10px">🔍 Query</div>
      <div style="display:flex;gap:8px">
        <input id="rag-query" placeholder="Ask your documents…" style="flex:1;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:13px;padding:9px 12px" onkeydown="if(event.key==='Enter')ragQuery('${pipelineId}')">
        <button class="btn" onclick="ragQuery(${JSON.stringify(pipelineId)})">Ask</button>
      </div>
      <div id="rag-answer" style="margin-top:12px"></div>
    </div>
  </div>`;
}

async function ragAddDoc(pipelineId) {
  const content=document.getElementById('rag-doc-content')?.value?.trim();
  const filename=document.getElementById('rag-doc-name')?.value||'document.txt';
  if(!content) {gmAlert('Paste document content first');return;}
  try {
    const r=await fetch(`/api/rag/pipelines/${encodeURIComponent(pipelineId)}/documents`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content,filename})});
    const d=await r.json();
    if(d.ok) {
      showToast(`✅ Added ${d.chunks} chunks from ${filename}`);
      // Re-fetch pipeline to get current name, stay in pipeline view
      const pd=await fetch(`/api/rag/pipelines/${encodeURIComponent(pipelineId)}`).then(r=>r.ok?r.json():null).catch(()=>null);
      ragOpenPipeline(pipelineId, pd?.name || filename);
    }
  }catch(ex){gmAlert('Add failed: '+ex.message);}
}

async function ragQuery(pipelineId) {
  const q=document.getElementById('rag-query')?.value?.trim();
  if(!q) return;
  const el=document.getElementById('rag-answer');
  if(el) el.innerHTML='<div style="color:var(--text-2);font-size:12px">Searching and generating…</div>';
  try {
    const r=await fetch(`/api/rag/pipelines/${encodeURIComponent(pipelineId)}/query`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q,k:5})});
    const d=await r.json();
    if(el) el.innerHTML=`
      <div style="background:var(--bg-3);border-radius:10px;padding:14px">
        <div style="font-size:13px;color:var(--text-0);line-height:1.7;white-space:pre-wrap">${escHtml(d.answer||'')}</div>
        ${(d.citations||[]).length?`<div style="margin-top:10px;border-top:1px solid var(--border);padding-top:8px">
          <div style="font-size:11px;font-weight:700;color:var(--text-3)">SOURCES</div>
          ${(d.citations||[]).map((c) =>`<div style="font-size:11px;color:var(--text-3);padding:2px 0">[${c.num}] chunk_${c.chunk_id?.slice(-4)} from doc_${c.doc_id?.slice(-4)}</div>`).join('')}
        </div>`:''}
      </div>`;
  }catch(ex){if(el) el.innerHTML=`<div style="color:var(--danger)">${ex.message}</div>`;}
}

async function ragDeletePipeline(pipelineId) {
  const ok=await gmConfirm('Delete this pipeline and all its documents?');
  if(!ok) return;
  await fetch(`/api/rag/pipelines/${encodeURIComponent(pipelineId)}`,{method:'DELETE'});
  renderRAG();
}

async function ragDeleteDoc(pipelineId, docId) {
  await fetch(`/api/rag/pipelines/${encodeURIComponent(pipelineId)}/documents/${encodeURIComponent(docId)}`,{method:'DELETE'});
  showToast('Document deleted');
  // Stay in pipeline view, re-fetch pipeline name
  const pd=await fetch(`/api/rag/pipelines/${encodeURIComponent(pipelineId)}`).then(r=>r.ok?r.json():null).catch(()=>null);
  ragOpenPipeline(pipelineId, pd?.name || '');
}


// ══════════════════════════════════════════════════════════════════
//  PATCH MASTER NAV — Sprint 19
// ══════════════════════════════════════════════════════════════════
(function patchNavSprint19() {
  const _base = window.nav || function(){};
  window.nav = function masterNav19(pane) {
    _base(pane);
    if (pane==='evals')          renderEvals?.();
    if (pane==='observability')  renderObservability?.();
    if (pane==='knowledge-graph')renderKnowledgeGraph?.();
    if (pane==='rag')            renderRAG?.();
  };
  console.log('%c✅ Sprint 19: Evals, Observability, Knowledge Graph, RAG', 'color:#38c5d8;font-weight:bold');
})();

// Keyboard shortcuts Sprint 19
document.addEventListener('keydown',(e) =>{
  if(!e.metaKey&&!e.ctrlKey||!e.shiftKey) return;
  if(e.key==='E'){ e.preventDefault(); nav('evals'); }
  if(e.key==='O'){ e.preventDefault(); nav('observability'); }
  if(e.key==='K'){ e.preventDefault(); nav('knowledge-graph'); }
});

