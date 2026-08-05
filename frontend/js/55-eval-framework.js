// Eval Framework — Extracted from 06-sprint-features.js
(function(S, nav, toast, escHtml, fetch, document) {
async function renderEvalFramework() {
  const pane = document.getElementById('pane-eval-framework');
  if (!pane) return;

  const [stats, suites, queue] = await Promise.all([
    fetch('/api/eval-framework/stats/platform').then(r=>r.ok?r.json():{}).catch(()=>({})),
    fetch('/api/eval-framework/suites').then(r=>r.ok?r.json():{suites:[]}).catch(()=>({suites:[]})),
    fetch('/api/eval-framework/review-queue?limit=5').then(r=>r.ok?r.json():{queue:[]}).catch(()=>({queue:[]})),
  ]);

  const scoreColor = s => s>=0.8?'var(--success)':s>=0.6?'var(--warning)':'var(--danger)';

  pane.innerHTML = `
  <div style="padding:20px;max-width:1100px;margin:0 auto">
    <div class="section-head" style="margin-bottom:20px">
      <div>
        <h2 style="margin:0 0 4px">🧪 Evaluation Framework</h2>
        <p style="margin:0;color:var(--text-2);font-size:13px">Continuous eval pipeline — agents earn autonomy by demonstrating measured quality across task completion, faithfulness, safety, and hallucination scoring</p>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn" data-act-click="evalRunSuite()">▶ Run Eval Suite</button>
        <button class="btn-sm" data-act-click="evalCreateSuite()">+ New Suite</button>
        <button class="btn-sm" data-act-click="renderEvalFramework()">↻ Refresh</button>
      </div>
    </div>

    <!-- Stats -->
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:18px">
      ${[
        ['🧪','Total Evals',stats.total_evals||0,'var(--accent)'],
        ['📚','Test Suites',stats.total_suites||0,'var(--text-2)'],
        ['👁️','Pending Review',stats.pending_review||0,stats.pending_review>0?'var(--warning)':'var(--text-3)'],
        ['🤖','Agents Evaluated',(stats.by_agent||[]).length,'var(--success)'],
      ].map(([icon,label,val,col])=>`
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:12px;text-align:center">
          <div style="font-size:18px">${icon}</div>
          <div style="font-size:9px;color:var(--text-3);text-transform:uppercase">${label}</div>
          <div style="font-size:18px;font-weight:700;color:${col}">${val}</div>
        </div>`).join('')}
    </div>

    <!-- Eval principle -->
    <div style="background:rgba(158,206,106,0.08);border:1px solid var(--success);border-radius:10px;padding:12px 16px;margin-bottom:18px">
      <div style="font-size:12px;font-weight:700;color:var(--success);margin-bottom:4px">📐 Evaluation Philosophy</div>
      <div style="font-size:11px;color:var(--text-2)">MIT: <em>"As long as it can check the answer, the AI agent can perform trial-and-error until it figures out a good strategy."</em> — Every agent must earn its autonomy level by passing scored evaluations. Low scores flag tasks for human review.</div>
    </div>

    <!-- Human review queue -->
    ${(queue.queue||[]).length>0?`
    <div style="background:var(--bg-2);border:1px solid var(--warning);border-radius:10px;padding:14px;margin-bottom:16px">
      <div style="font-size:12px;font-weight:700;margin-bottom:10px">👁️ Human Review Queue (${queue.count||0} pending)</div>
      ${(queue.queue||[]).map(r=>`
        <div style="background:var(--bg-3);border-radius:8px;padding:10px;margin-bottom:8px">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:11px">
            <span style="color:var(--danger);font-weight:700">Score: ${Math.round((r.overall_score||0)*100)}%</span>
            <span style="color:var(--accent)">${escHtml(r.agent_id)}</span>
            <span style="color:var(--text-3)">${new Date(r.created_at).toLocaleTimeString()}</span>
          </div>
          <div style="font-size:11px;color:var(--text-1);margin-bottom:6px">${escHtml((r.prompt||'').slice(0,80))}</div>
          <button class="btn-sm" data-act-click="evalHumanReview(${JSON.stringify(r.result_id)})">👁️ Review</button>
        </div>`).join('')}
    </div>`:''}

    <!-- Test suites -->
    <div style="font-size:12px;font-weight:700;margin-bottom:10px">📚 Evaluation Suites</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;margin-bottom:18px">
      ${(suites.suites||[]).map(s=>`
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:14px">
          <div style="font-weight:700;font-size:13px;margin-bottom:4px">${escHtml(s.name)}</div>
          <div style="font-size:11px;color:var(--text-2);margin-bottom:8px">${escHtml(s.description||'')}</div>
          <div style="font-size:10px;color:var(--text-3);margin-bottom:10px">
            📂 ${escHtml(s.domain)} · ${s.cases_count||0} cases · Pass: ${Math.round((s.pass_threshold||0.7)*100)}%
          </div>
          <div style="display:flex;gap:6px">
            <button class="btn-sm" data-act-click="evalRunSpecific(${JSON.stringify(s.suite_id)})">▶ Run</button>
            <button class="btn-sm" data-act-click="evalViewCases(${JSON.stringify(s.suite_id)})">📋 Cases</button>
            <button class="btn-sm" data-act-click="evalAddCase(${JSON.stringify(s.suite_id)})">+ Case</button>
          </div>
        </div>`).join('')}
    </div>

    <!-- Agent eval leaderboard -->
    ${(stats.by_agent||[]).length>0?`
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:14px">
      <div style="font-size:12px;font-weight:700;margin-bottom:12px">🏆 Agent Eval Leaderboard</div>
      <div style="display:grid;grid-template-columns:120px 1fr 80px 80px;gap:8px;font-size:10px;font-weight:700;color:var(--text-3);text-transform:uppercase;padding:0 8px;margin-bottom:6px">
        <span>Agent</span><span>Score Bar</span><span>Score</span><span>Pass Rate</span>
      </div>
      ${(stats.by_agent||[]).map((a,i)=>{
        const sc = a.sc||0;
        const pct = a.pass_pct||0;
        return `
        <div style="display:grid;grid-template-columns:120px 1fr 80px 80px;gap:8px;align-items:center;padding:6px 8px;background:${i%2===0?'var(--bg-3)':'transparent'};border-radius:6px;font-size:12px">
          <span style="color:var(--accent);font-weight:600">${escHtml(a.agent_id)}</span>
          <div style="background:var(--bg-2);border-radius:4px;height:8px;overflow:hidden">
            <div style="width:${Math.min(sc*100,100)}%;height:8px;background:${scoreColor(sc)};border-radius:4px"></div>
          </div>
          <span style="font-weight:700;color:${scoreColor(sc)}">${Math.round(sc*100)}%</span>
          <span style="color:var(--text-2)">${Math.round(pct)}%</span>
        </div>`}).join('')}
    </div>`:''}
  </div>`;
}

let _evalRunId = null;
async function evalRunSuite() {
  const agents = ['orchestrator','brain','builder','researcher','reviewer','creative'];
  const agentId = await gmPrompt('Run Eval Suite', `Agent to evaluate:\n${agents.map(a=>`• ${a}`).join('\n')}`, 'builder') || 'builder';
  if (!agentId?.trim()) return;
  const suiteId = await gmPrompt('Suite ID:', 'suite_general') || 'suite_general';
  await evalRunSpecific(suiteId, agentId);
}

async function evalRunSpecific(suiteId, agentId) {
  if (!agentId) agentId = await gmPrompt('Agent ID:', 'builder') || 'builder';
  showToast(`🧪 Running eval suite "${suiteId}" on ${agentId}…`);
  const resp = await fetch('/api/eval-framework/run',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({agent_id:agentId,suite_id:suiteId})
  }).catch(()=>null);
  if (!resp) { showToast('⚠️ Eval failed'); return; }
  // Stream results
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let passed=0, failed=0, total=0, done=false;
  while (!done) {
    const {value, done:d} = await reader.read();
    if (d) { done=true; break; }
    const text = dec.decode(value);
    for (const line of text.split('\n')) {
      if (!line.startsWith('data:')) continue;
      try {
        const ev = JSON.parse(line.slice(5));
        if (ev.type==='case_done') { passed+=ev.pass_fail==='pass'?1:0; failed+=ev.pass_fail!=='pass'?1:0; total=ev.total; }
        if (ev.type==='done') {
          showToast(`🧪 Eval done: ${ev.passed}/${ev.total} passed (${Math.round(ev.avg_score*100)}% avg score)`);
          renderEvalFramework();
        }
      } catch(e) {}
    }
  }
}

async function evalHumanReview(resultId) {
  const score = await gmPrompt('Human Review', 'Your quality score (0.0 to 1.0):','0.8');
  if (score===null) return;
  const notes = await gmPrompt('Notes (optional):','') || '';
  const r = await fetch(`/api/eval-framework/results/${encodeURIComponent(resultId)}/review`,{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({score:parseFloat(score)||0,notes,reviewer:'user'})
  }).catch(()=>null);
  const d = r ? await r.json() : {};
  showToast(d.ok ? '👁️ Review saved' : '⚠️ Failed');
  renderEvalFramework();
}

async function evalCreateSuite() {
  const name   = await gmPrompt('New Eval Suite', 'Suite name:');
  if (!name?.trim()) return;
  const domain = await gmPrompt('Domain (general/safety/coding/custom):', 'general') || 'general';
  const thresh = await gmPrompt('Pass threshold (0.0–1.0):', '0.70') || '0.70';
  const r = await fetch('/api/eval-framework/suites',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name,domain,pass_threshold:parseFloat(thresh)||0.7})
  }).catch(()=>null);
  const d = r ? await r.json() : {};
  showToast(d.ok ? `📚 Suite created: ${d.suite_id}` : '⚠️ Failed');
  if (d.ok) renderEvalFramework();
}

async function evalViewCases(suiteId) {
  const d = await fetch(`/api/eval-framework/suites/${encodeURIComponent(suiteId)}/cases`).then(r=>r.ok?r.json():{cases:[]}).catch(()=>({cases:[]}));
  const lines = (d.cases||[]).map((c,i)=>`${i+1}. [${c.difficulty}] ${c.prompt?.slice(0,60)}…`).join('\n');
  await gmAlert(`📋 Cases in Suite`, lines || 'No cases yet. Add some with "+ Case".');
}

async function evalAddCase(suiteId) {
  const prompt   = await gmPrompt('Add Eval Case', 'Test prompt:');
  if (!prompt?.trim()) return;
  const expected = await gmPrompt('Expected output/answer (or keywords):','') || '';
  const diff     = await gmPrompt('Difficulty (easy/medium/hard):', 'medium') || 'medium';
  const r = await fetch(`/api/eval-framework/suites/${encodeURIComponent(suiteId)}/cases`,{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({prompt,expected,difficulty:diff})
  }).catch(()=>null);
  const d = r ? await r.json() : {};
  showToast(d.ok ? `✅ Case added: ${d.case_id}` : '⚠️ Failed');
  if (d.ok) renderEvalFramework();
}

window.renderEvalFramework = renderEvalFramework;
})(S, nav, toast, escHtml, fetch, document);
