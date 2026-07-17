// Agentic OS v6.0 — Features B — GitHub, DB studio, composer, templates, plugins, control tower
// Extracted from index.html (block 3)


'use strict';

// ══════════════════════════════════════════════════════════════════
//  SPEC-DRIVEN DEVELOPMENT — Kiro-style 4-phase pipeline
// ══════════════════════════════════════════════════════════════════

let _specList = [], _specCurrent = null;

async function renderSpecs() {
  const pane = document.getElementById('pane-specs');
  if (!pane) return;

  pane.innerHTML = `
  

  <div class="spec-layout">
    <div class="spec-sidebar">
      <div class="spec-sidebar-top">
        <h3>📋 Specs</h3>
        <button onclick="specNew()" style="width:100%;padding:7px;background:var(--accent);border:none;border-radius:7px;color:#fff;font-size:12px;font-weight:600;cursor:pointer">＋ New Spec</button>
      </div>
      <div class="spec-list" id="spec-list"><div style="color:var(--text-3);font-size:12px;padding:8px">Loading…</div></div>
    </div>
    <div class="spec-main">
      <div class="spec-topbar">
        <span id="spec-title-display" style="font-size:14px;font-weight:700;color:var(--text-0);flex:1">Select or create a spec</span>
        <div class="spec-pipeline" id="spec-pipeline" style="display:none">
          <button class="spec-phase-btn" id="sbtn-req" onclick="specShowPhase('requirements')">📝 Requirements</button>
          <button class="spec-phase-btn" id="sbtn-design" onclick="specShowPhase('design')">🏗️ Design</button>
          <button class="spec-phase-btn" id="sbtn-tasks" onclick="specShowPhase('tasks')">✅ Tasks</button>
          <button class="spec-phase-btn" id="sbtn-code" onclick="specShowPhase('execute')">⚡ Execute</button>
        </div>
      </div>
      <div class="spec-content" id="spec-content">
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:300px;color:var(--text-3);text-align:center">
          <div style="font-size:48px;margin-bottom:16px">📋</div>
          <div style="font-size:18px;font-weight:700;margin-bottom:8px">Spec-Driven Development</div>
          <div style="font-size:13px;max-width:420px;line-height:1.7;color:var(--text-2)">
            Like Kiro + Windsurf Cascade — describe a feature, get structured Requirements → Design → Tasks → Code. Every decision is documented and traceable.
          </div>
          <button class="spec-run-all-btn" onclick="specNew()" style="margin-top:20px">＋ Create Your First Spec</button>
        </div>
      </div>
    </div>
  </div>`;

  await specLoadList();
}

async function specLoadList() {
  try {
    const r = await fetch('/api/specs');
    const d = await r.json();
    _specList = d.specs || [];
    const list = document.getElementById('spec-list');
    if (!list) return;
    list.innerHTML = _specList.map(s => `
      <div class="spec-item ${_specCurrent?.id===s.id?'active':''}" onclick="specSelect(${JSON.stringify(s.id)})">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">
          <span style="font-weight:600;font-size:13px;color:var(--text-0);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml(s.title)}</span>
          <span class="spec-phase-badge ${s.phase}">${s.phase}</span>
          <button onclick="event.stopPropagation();specDelete(${JSON.stringify(s.id)},${JSON.stringify(s.title)})"            style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:12px;padding:0 2px;line-height:1" title="Delete spec">🗑</button>
        </div>
        <div style="font-size:10px;color:var(--text-3)">${new Date(s.updated_at).toLocaleDateString()}</div>
      </div>
    `).join('') || '<div style="color:var(--text-3);font-size:12px">No specs yet</div>';
  } catch(e) {}
}

async function specNew() {
  const title = await gmPrompt('Feature name:', 'User Authentication');
  if (!title) return;
  const desc  = await gmPrompt('Describe the feature (the more detail, the better):', '');

  try {
    const r = await fetch('/api/specs', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({title, description:desc})
    });
    const d = await r.json();
    await specLoadList();
    specSelect(d.spec.id, desc);
  } catch(e) {}
}

async function specDelete(specId, title) {
  // FIX 1: delete spec with confirmation
  if (!(await gmDanger('Delete Spec', `Delete "${title}"? This removes all requirements, design, and tasks permanently.`))) return;
  try {
    await fetch(`/api/specs/${encodeURIComponent(specId)}`, {method:'DELETE'});
    if (_specCurrent?.id === specId) {
      _specCurrent = null;
      document.getElementById('spec-title-display').textContent = 'Select or create a spec';
      document.getElementById('spec-pipeline').style.display = 'none';
      document.getElementById('spec-content').innerHTML = '';
    }
    await specLoadList();
    showToast('🗑️ Spec deleted');
  } catch(e) {
    showToast('⚠️ Delete failed — check connection');
  }
}

async function specSelect(specId, initialDesc='') {
  try {
    const r = await fetch(`/api/specs/${encodeURIComponent(specId)}`);
    _specCurrent = await r.json();
  } catch(e) { return; }

  document.getElementById('spec-title-display').textContent = _specCurrent.title;
  document.getElementById('spec-pipeline').style.display = '';
  specLoadList();
  specShowPhase('requirements', initialDesc);
}

function specShowPhase(phase, desc='') {
  const content = document.getElementById('spec-content');
  if (!content || !_specCurrent) return;

  // Update button states
  document.querySelectorAll('.spec-phase-btn').forEach(b => b.classList.remove('active'));
  const map = {requirements:'sbtn-req',design:'sbtn-design',tasks:'sbtn-tasks',execute:'sbtn-code'};
  document.getElementById(map[phase])?.classList.add('active');

  if (phase === 'requirements') {
    const existing = _specCurrent.requirements || '';
    content.innerHTML = `
      <div>
        <div style="font-size:13px;font-weight:700;color:var(--text-0);margin-bottom:8px">📝 Requirements</div>
        <div style="font-size:12px;color:var(--text-2);margin-bottom:12px;line-height:1.6">
          Describe what you want to build. The AI will generate structured requirements with user stories, acceptance criteria, and EARS notation.
        </div>
        <textarea class="spec-desc-input" id="spec-desc" placeholder="e.g. A user authentication system with email/password login, Google OAuth, password reset via email, and session management. Users should be able to update their profile and delete their account.">${escHtml(desc || _specCurrent.description || '')}</textarea>
        <div style="display:flex;gap:10px;margin-top:12px;flex-wrap:wrap">
          <button class="btn" onclick="specGenReq()" id="spec-gen-req-btn">📝 Generate Requirements</button>
          <button class="spec-run-all-btn" onclick="specRunAll()" id="spec-run-all">🚀 Run Full Pipeline</button>
        </div>
      </div>
      ${existing ? `
      <div class="spec-artifact">
        <div class="spec-artifact-hdr"><span>📄</span><strong>requirements.md</strong><span style="margin-left:auto;font-size:10px;color:var(--text-3)">${existing.length} chars</span></div>
        <div class="spec-artifact-body">${escHtml(existing)}</div>
      </div>` : ''}
      <div class="spec-stream-log" id="spec-log" style="display:none"></div>
    `;
  } else if (phase === 'design') {
    const existing = _specCurrent.design || '';
    content.innerHTML = `
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
        <div>
          <div style="font-size:13px;font-weight:700;color:var(--text-0)">🏗️ Design Document</div>
          <div style="font-size:12px;color:var(--text-2)">Architecture, data models, API contracts, sequence diagrams generated from your requirements.</div>
        </div>
        <button class="btn" onclick="specGenDesign()" style="flex-shrink:0">🏗️ Generate Design</button>
      </div>
      ${existing ? `
      <div class="spec-artifact">
        <div class="spec-artifact-hdr"><span>🏗️</span><strong>design.md</strong><span style="margin-left:auto;font-size:10px;color:var(--text-3)">${existing.length} chars</span></div>
        <div class="spec-artifact-body">${escHtml(existing)}</div>
      </div>` : '<div style="color:var(--text-3);font-size:12px">Generate requirements first, then design.</div>'}
      <div class="spec-stream-log" id="spec-log" style="display:none"></div>
    `;
  } else if (phase === 'tasks') {
    content.innerHTML = `<div style="color:var(--text-2)">Loading tasks…</div>`;
    specLoadTasks();
  } else if (phase === 'execute') {
    content.innerHTML = `
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
        <div>
          <div style="font-size:13px;font-weight:700;color:var(--text-0)">⚡ Wave Execution</div>
          <div style="font-size:12px;color:var(--text-2)">Tasks run in parallel waves. Independent tasks execute simultaneously.</div>
        </div>
        <div style="display:flex;gap:6px;margin-left:auto">
          <button class="btn-sm" onclick="specExecuteAll(false)">⚡ Execute All</button>
          <button class="btn-sm" onclick="specExecuteAll(true)">👁 Dry Run</button>
        </div>
      </div>
      <div class="spec-stream-log" id="spec-log" style="display:none"></div>
      <div id="spec-exec-results"></div>
    `;
  }
}

async function specGenReq() {
  if (!_specCurrent) return;
  const desc = document.getElementById('spec-desc')?.value || '';
  const btn  = document.getElementById('spec-gen-req-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Generating…'; }
  specStreamStart();
  try {
    const resp = await fetch(`/api/specs/${encodeURIComponent(_specCurrent.id)}/requirements`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({description:desc})
    });
    await specConsumeStream(resp, (d) => {
      if (d.type==='phase_done') {
        setTimeout(async () => {
          const r = await fetch(`/api/specs/${encodeURIComponent(_specCurrent.id)}`);
          _specCurrent = await r.json();
          specShowPhase('requirements');
        }, 500);
      }
    });
  } catch(ex) { specLog('Error: '+ex.message); }
  if (btn) { btn.disabled = false; btn.textContent = '📝 Generate Requirements'; }
}

async function specGenDesign() {
  if (!_specCurrent) return;
  specStreamStart();
  try {
    const resp = await fetch(`/api/specs/${encodeURIComponent(_specCurrent.id)}/design`, {method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    if (!resp.ok) { specLog(`Error: HTTP ${resp.status}`); return; }
    await specConsumeStream(resp, (d) => {
      if (d.type==='phase_done') setTimeout(async()=>{const r=await fetch(`/api/specs/${encodeURIComponent(_specCurrent.id)}`);_specCurrent=await r.json();specShowPhase('design');},500);
      if (d.type==='phase_error') specLog(`Error: ${d.error}`);
    });
  } catch(ex) { specLog(`Error: ${ex.message}`); }
}

async function specLoadTasks() {
  if (!_specCurrent) return;
  try {
    const r = await fetch(`/api/specs/${encodeURIComponent(_specCurrent.id)}/tasks`);
    const d = await r.json();
    const content = document.getElementById('spec-content');
    if (!content) return;

    const waves = d.waves || {};
    const waveCount = Object.keys(waves).length;

    let html = `
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
        <div>
          <div style="font-size:13px;font-weight:700;color:var(--text-0)">✅ Implementation Tasks</div>
          <div style="font-size:12px;color:var(--text-2)">${d.count||0} tasks across ${waveCount} waves</div>
        </div>
        <button class="btn-sm" onclick="specGenTasks()" style="flex-shrink:0">🔄 Regenerate Tasks</button>
      </div>
      <div class="spec-stream-log" id="spec-log" style="display:none"></div>
    `;

    if (!d.count) {
      html += `
        <div style="color:var(--text-3);font-size:12px;padding:20px;text-align:center">
          No tasks yet.<br>
          <button class="btn" onclick="specGenTasks()" style="margin-top:12px">✅ Generate Tasks from Design</button>
        </div>`;
    } else {
      for (const [wave, tasks] of Object.entries(waves)) {
        html += `<div class="spec-wave-label"><span>Wave ${wave}</span><div class="spec-wave-line"></div><span style="font-size:10px;color:var(--text-3)">${tasks.length} parallel task${tasks.length>1?'s':''}</span></div>`;
        for (const t of tasks) {
          const done = t.status==='done';
          html += `
            <div class="spec-task-card ${done?'done':''}">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
                <span style="font-size:14px">${done?'✅':'⬜'}</span>
                <strong style="color:var(--text-0);font-size:12px">${t.task_no}. ${escHtml(t.title)}</strong>
                <span style="margin-left:auto;font-size:10px;background:var(--bg-3);padding:1px 6px;border-radius:4px;color:var(--text-3)">${escHtml(t.agent_id||'builder')}</span>
              </div>
              <div style="font-size:11px;color:var(--text-2);margin-left:22px">${escHtml(t.description||'')}</div>
              ${done && t.output ? `<div style="font-size:10px;color:var(--text-3);margin-left:22px;margin-top:4px">Output: ${escHtml((t.output||'').slice(0,80))}…</div>` : ''}
            </div>`;
        }
      }
    }

    content.innerHTML = html;
  } catch(e) {}
}

async function specGenTasks() {
  if (!_specCurrent) return;
  specStreamStart();
  try {
    const resp = await fetch(`/api/specs/${encodeURIComponent(_specCurrent.id)}/tasks`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    if (!resp.ok) { specLog(`Error: HTTP ${resp.status}`); return; }
    await specConsumeStream(resp, (d) => {
      if (d.type==='phase_done') setTimeout(()=>specLoadTasks(),300);
      if (d.type==='phase_error') specLog(`Error: ${d.error}`);
    });
  } catch(ex) { specLog(`Error: ${ex.message}`); }
}

async function specExecuteAll(dryRun=false) {
  if (!_specCurrent) return;
  specStreamStart();
  try {
    const resp = await fetch(`/api/specs/${encodeURIComponent(_specCurrent.id)}/execute`,{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({dry_run:dryRun})
    });
    if (!resp.ok) { specLog(`Error: HTTP ${resp.status}`); return; }
    await specConsumeStream(resp, (d) => {
      if (d.type==='wave_start') specLog(`🌊 Wave ${d.wave} starting (${d.task_count} parallel tasks)…`);
      if (d.type==='task_done')  specLog(`  ✅ Task ${d.task_no}: ${d.title} (${d.output_len} chars)`);
      if (d.type==='task_skip')  specLog(`  ⏭ Skip ${d.task_no}: ${d.title} [dry run]`);
      if (d.type==='task_error') specLog(`  ✗ Error: ${d.error}`);
      if (d.type==='wave_done')  specLog(`✓ Wave ${d.wave} complete`);
      if (d.type==='exec_done')  { specLog(`\n🎉 Execution complete! ${d.total_completed} tasks done.`); specLoadTasks(); }
    });
  } catch(ex) { specLog(`Error: ${ex.message}`); }
}

async function specRunAll() {
  if (!_specCurrent) return;
  const btn = document.getElementById('spec-run-all');
  if (btn) { btn.disabled=true; btn.textContent='🔄 Running pipeline…'; }
  specStreamStart();
  try {
    const desc = document.getElementById('spec-desc')?.value || '';
    const resp = await fetch(`/api/specs/${encodeURIComponent(_specCurrent.id)}/run-all`,{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({description:desc})
    });
    if (!resp.ok) { specLog(`Error: HTTP ${resp.status}`); return; }
    await specConsumeStream(resp, (d) => {
      if (d.type==='pipeline_phase') specLog(`\n▶ Phase: ${d.phase}`);
      if (d.type==='phase_error')    specLog(`  ✗ Phase error: ${d.error}`);
      if (d.type==='pipeline_done') {
        specLog('\n✅ Full pipeline complete!');
        setTimeout(async()=>{const r=await fetch(`/api/specs/${encodeURIComponent(_specCurrent.id)}`);_specCurrent=await r.json();specLoadList();},500);
      }
    });
  } catch(ex) {
    specLog(`Error: ${ex.message}`);
  } finally {
    if (btn) { btn.disabled=false; btn.textContent='🚀 Run Full Pipeline'; }
  }
}

function specStreamStart() {
  const log = document.getElementById('spec-log');
  if (log) { log.style.display='block'; log.textContent=''; }
}

function specLog(msg) {
  const log = document.getElementById('spec-log');
  if (!log) return;
  log.textContent += msg + '\n';
  log.scrollTop = log.scrollHeight;
}

async function specConsumeStream(resp, onEvent) {
  // FIX 3: guard against null body (failed responses)
  if (!resp.body) { specLog('Error: no response body received'); return; }
  const reader = resp.body.getReader();
  const dec    = new TextDecoder();
  let   buf    = '';
  while (true) {
    const {done,value} = await reader.read();
    if (done) break;
    buf += dec.decode(value, {stream:true});
    const parts = buf.split('\n\n');
    buf = parts.pop() || '';
    for (const part of parts) {
      if (!part.startsWith('data:')) continue;
      try {
        const d = JSON.parse(part.slice(5).trim());
        if (d.type==='chunk') specLog(d.text||'');
        else onEvent(d);
      } catch(e) {}
    }
  }
}


// ══════════════════════════════════════════════════════════════════
//  AGENT HOOKS — event-driven automations
// ══════════════════════════════════════════════════════════════════

async function renderHooks() {
  const pane = document.getElementById('pane-hooks');
  if (!pane) return;

  try {
    const [hooks, events] = await Promise.all([
      fetch('/api/hooks').then(r=>r.ok?r.json():null),
      fetch('/api/hooks/events/types').then(r=>r.ok?r.json():null),
    ]);

    const hookList = hooks.hooks || [];
    const eventMap = {};
    (events.events||[]).forEach((e) =>{ eventMap[e.id]=e.label; });

    pane.innerHTML = `
    
    <div style="padding:20px;max-width:900px;margin:0 auto">
      <div class="section-head">
        <div>
          <h2>⚡ Agent Hooks</h2>
          <p>Event-driven automations — AI agents fire automatically on file save, git commit, tests, and more</p>
        </div>
        <div style="display:flex;gap:8px">
          <button class="btn" onclick="hookCreate()">＋ New Hook</button>
          <button class="btn-sm" onclick="hookFireTest()">▶ Test Fire</button>
        </div>
      </div>

      <!-- Event types quick filter -->
      <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:16px">
        ${(events.events||[]).map((e) =>`
          <button class="btn-sm" onclick="hookFilterEvent(${JSON.stringify(e.id)})" id="hfbtn-${e.id}" style="font-size:11px">${e.label}</button>
        `).join('')}
      </div>

      <!-- Hook cards -->
      <div id="hook-list">
        ${hookList.map((h) => hookCardHTML(h, eventMap)).join('') || '<div style="color:var(--text-3);padding:20px;text-align:center">No hooks yet. Create one or enable a built-in hook below.</div>'}
      </div>

      <!-- Recent runs -->
      <div style="margin-top:24px">
        <div style="font-size:13px;font-weight:700;margin-bottom:10px">📋 Recent Hook Runs</div>
        <div id="hook-runs-list" style="font-size:11px;color:var(--text-2)">Loading…</div>
      </div>
    </div>`;

    hookLoadRuns();
  } catch(e) {
    pane.innerHTML = `<div style="padding:20px;color:var(--danger)">Failed to load hooks: ${e?.message||e}</div>`;
  }
}

function hookCardHTML(h, eventMap) {
  const isOn  = !!h.enabled;
  const evLbl = eventMap[h.event] || h.event;
  return `
    <div class="hook-card" id="hook-${h.id}">
      <div style="display:flex;align-items:flex-start;gap:10px">
        <button class="hook-toggle ${isOn?'on':''}" onclick="hookToggle(${JSON.stringify(h.id)},this)" title="${isOn?'Enabled':'Disabled'}"></button>
        <div style="flex:1">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:5px">
            <strong style="color:var(--text-0);font-size:13px">${escHtml(h.name)}</strong>
            <span class="hook-event-tag">${escHtml(evLbl)}</span>
            ${h.run_count>0?`<span style="font-size:10px;color:var(--text-3)">× ${h.run_count} runs</span>`:''}
          </div>
          <div style="font-size:12px;color:var(--text-2);margin-bottom:8px">${escHtml(h.description||'')}</div>
          ${h.condition?`<div style="font-size:10px;font-family:monospace;color:var(--text-3);background:var(--bg-3);padding:3px 7px;border-radius:5px;margin-bottom:8px">if: ${escHtml(h.condition)}</div>`:''}
          <div style="font-size:11px;font-family:monospace;color:var(--text-1);background:var(--bg-3);padding:6px 8px;border-radius:6px;line-height:1.5;max-height:60px;overflow:hidden">${escHtml((h.prompt||'').slice(0,200))}</div>
        </div>
        <div style="display:flex;flex-direction:column;gap:5px;flex-shrink:0">
          <button class="btn-sm" onclick="hookManualRun(${JSON.stringify(h.id)})">▶ Run</button>
          <button class="btn-sm" onclick="hookEdit(${JSON.stringify(h.id)})">✏</button>
          <button class="btn-sm" style="color:var(--danger)" onclick="hookDelete(${JSON.stringify(h.id)})">🗑</button>
        </div>
      </div>
    </div>`;
}

async function hookToggle(hookId, btn) {
  try {
    const r = await fetch(`/api/hooks/${encodeURIComponent(hookId)}/toggle`,{method:'POST'});
    if (!r.ok) { showToast('Toggle failed: server error ' + r.status, 'err'); return; }
    const d = await r.json();
    if (!d.ok) { showToast('Toggle failed: ' + (d.error||''), 'err'); return; }
    btn.classList.toggle('on', d.enabled);
    showToast(d.enabled ? '⚡ Hook enabled' : 'Hook disabled');
  } catch(ex) { showToast('Toggle failed: ' + ex.message, 'err'); }
}

async function hookManualRun(hookId) {
  try {
    const evData = await gmPrompt('Event data (JSON, optional):', '{}');
    let data = {};
    try { data = JSON.parse(evData||'{}'); } catch(e) {}
    const r = await fetch(`/api/hooks/${encodeURIComponent(hookId)}/run`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({event_data:data})});
    const d = await r.json();
    if (d.ok) gmAlert(`✅ Hook ran!\n\n${(d.output||'').slice(0,400)}`);
  } catch(ex) { gmAlert('Run failed: '+ex.message); }
}

async function hookCreate() {
  const name  = await gmPrompt('Hook name:','My Hook');
  if (!name) return;
  const event = await gmPrompt('Event (file_save, git_commit, schedule, etc.):','file_save');
  if (!event) return;
  const prompt= await gmPrompt('AI prompt (use {{file.path}}, {{commit.message}}, etc.):','Review this file: {{file.path}}\n{{file.content}}');
  if (!prompt) return;
  try {
    const r = await fetch('/api/hooks',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name, event, prompt, description:'Custom hook', enabled:true})});
    if (!r.ok) { gmAlert('Failed to create hook: server error ' + r.status); return; }
    const d = await r.json();
    if (!d.ok) { gmAlert('Failed to create hook: ' + (d.error||'unknown error')); return; }
    showToast('⚡ Hook created: ' + name, 'ok');
    renderHooks();
  } catch(ex) { gmAlert('Failed to create hook: ' + ex.message); }
}

async function hookDelete(hookId) {
  const ok = await gmDanger('Delete this hook? This cannot be undone.');
  if (!ok) return;
  try {
    const r = await fetch(`/api/hooks/${encodeURIComponent(hookId)}`,{method:'DELETE'});
    if (!r.ok) { gmAlert('Delete failed: server error ' + r.status); return; }
    showToast('Hook deleted', 'ok', 1500);
    renderHooks();
  } catch(ex) { gmAlert('Delete failed: ' + ex.message); }
}

async function hookFireTest() {
  const event = await gmPrompt('Event to fire:','file_save');
  if (!event) return;
  try {
    await fetch('/api/hooks/fire',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({event,data:{file:{path:'test.py',content:'print("hello")',extension:'.py',size_lines:1}}})});
    showToast(`⚡ Fired "${event}" event`);
    setTimeout(hookLoadRuns, 2000);
  } catch(e) {}
}

async function hookEdit(hookId) {
  try {
    const r = await fetch(`/api/hooks/${encodeURIComponent(hookId)}`);
    if (!r.ok) { gmAlert('Could not load hook'); return; }
    const h = await r.json();
    if (h.ok === false) { gmAlert('Hook not found'); return; }

    const name   = await gmPrompt('Hook name:', h.name || '');
    if (name === null) return;
    const event  = await gmPrompt('Event type:', h.event || 'file_save');
    if (event === null) return;
    const prompt = await gmPrompt('AI prompt:', h.prompt || '');
    if (prompt === null) return;
    const cond   = await gmPrompt('Condition (optional):', h.condition || '');

    const pr = await fetch(`/api/hooks/${encodeURIComponent(hookId)}`, {
      method: 'PATCH',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({name: name||h.name, event: event||h.event,
                            prompt: prompt||h.prompt, condition: cond})
    });
    if (!pr.ok) { gmAlert('Update failed: server error ' + pr.status); return; }
    const pd = await pr.json();
    if (!pd.ok) { gmAlert('Update failed: ' + (pd.error||'')); return; }
    showToast('✅ Hook updated', 'ok');
    renderHooks();
  } catch(ex) { gmAlert('Edit failed: ' + ex.message); }
}

async function hookLoadRuns() {
  try {
    const r = await fetch('/api/hooks/runs/recent?limit=10');
    const d = await r.json();
    const el = document.getElementById('hook-runs-list');
    if (!el) return;
    el.innerHTML = (d.runs||[]).map((run) => `
      <div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-top:1px solid var(--border)">
        <span style="font-size:10px;background:var(--bg-3);padding:1px 5px;border-radius:4px;color:var(--text-3)">${escHtml(run.event||'')}</span>
        <span style="font-weight:600">${escHtml(run.hook_name||'')}</span>
        <span style="color:var(--text-3)">${run.duration_ms}ms</span>
        <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-2)">${escHtml((run.output||'').slice(0,60))}</span>
        <span style="font-size:10px;color:var(--text-3)">${new Date(run.created_at).toLocaleTimeString()}</span>
      </div>
    `).join('') || '<div style="color:var(--text-3)">No hook runs yet</div>';
  } catch(e) {}
}

async function hookFilterEvent(event) {
  document.querySelectorAll('[id^="hfbtn-"]').forEach(b => b.style.background='');
  const btn = document.getElementById(`hfbtn-${event}`);
  if (btn) btn.style.background = 'var(--accent)';
  try {
    const r = await fetch(`/api/hooks?event=${encodeURIComponent(event)}`);
    if (!r.ok) { showToast('Filter failed: server error ' + r.status, 'err'); return; }
    const d = await r.json();
    const list = document.getElementById('hook-list');
    if (!list) return;
    list.innerHTML = (d.hooks||[]).map((h) =>hookCardHTML(h,{})).join('') || '<div style="color:var(--text-3);padding:12px">No hooks for this event</div>';
  } catch(ex) { showToast('Filter failed: ' + ex.message, 'err'); }
}


// ══════════════════════════════════════════════════════════════════
//  CODEBASE INDEX + DEPENDENCY GRAPH
// ══════════════════════════════════════════════════════════════════

let _codeGraphData = {nodes:[],edges:[]};
let _ciAnimFrame = null;  // FIX 7

async function renderCodeIndex() {
  const pane = document.getElementById('pane-codeindex');
  if (!pane) return;

  pane.innerHTML = `
  

  <div class="ci-layout">
    <div class="ci-sidebar">
      <div class="ci-panel">
        <h4>🔍 Symbol Search</h4>
        <input id="ci-search" placeholder="Search functions, classes…" style="width:100%;background:var(--bg-2);border:1px solid var(--border);border-radius:7px;color:var(--text-0);font-size:12px;padding:6px 10px;box-sizing:border-box"
               oninput="ciSearch(this.value)">
      </div>
      <div style="flex:1;overflow-y:auto;padding:8px" id="ci-sym-list">
        <div style="color:var(--text-3);font-size:12px;padding:8px">Index your codebase first →</div>
      </div>
      <div class="ci-panel">
        <button class="btn" style="width:100%" onclick="ciIndexNow()">🔄 Index Codebase</button>
        <div style="font-size:10px;color:var(--text-3);margin-top:6px" id="ci-index-status">Not indexed</div>
      </div>
    </div>

    <div class="ci-main">
      <div class="ci-tabs">
        <div class="ci-tab active" onclick="ciShowTab('graph',this)">🕸️ Dependency Graph</div>
        <div class="ci-tab" onclick="ciShowTab('complexity',this)">🔥 Complexity</div>
        <div class="ci-tab" onclick="ciShowTab('dead',this)">💀 Dead Code</div>
        <div class="ci-tab" onclick="ciShowTab('stats',this)">📊 Stats</div>
      </div>

      <div class="ci-graph-area" id="ci-graph-area">
        <canvas id="ci-graph-canvas" class="ci-graph-canvas"></canvas>
        <div id="ci-tab-content" style="position:absolute;inset:0;overflow:auto;display:none;padding:16px;background:var(--bg-0)"></div>
        <div id="ci-empty-state" style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;color:var(--text-3)">
          <div style="font-size:48px;margin-bottom:12px">🕸️</div>
          <div style="font-size:16px;font-weight:600;margin-bottom:8px">Codebase Index</div>
          <div style="font-size:13px;max-width:340px;text-align:center;line-height:1.6">
            Like Windsurf Codemaps & Augment Code — index your project to see a live dependency graph, find complex functions, detect dead code.
          </div>
          <button class="btn" onclick="ciIndexNow()" style="margin-top:16px">🔄 Index Now</button>
        </div>
        <div id="ci-node-tooltip" style="position:absolute;display:none;background:var(--bg-2);border:1px solid var(--border);border-radius:8px;padding:8px 12px;font-size:11px;color:var(--text-0);pointer-events:none;z-index:10;max-width:220px"></div>
      </div>
    </div>
  </div>`;

  await ciLoadStats();
}
window.renderCodeIndex = renderCodeIndex;

async function ciIndexNow() {
  const btn = document.querySelector('#pane-codeindex .btn') || null;  // FIX 4: logical OR
  const status = document.getElementById('ci-index-status');
  if (btn) btn.disabled = true;
  if (status) status.textContent = 'Indexing…';

  try {
    const r = await fetch('/api/codeindex/index',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({include_backend:true})});
    const d = await r.json();
    if (status) status.textContent = `✅ ${d.indexed_files} files, ${d.symbols_found} symbols`;
    await ciLoadGraph();
    await ciLoadStats();
    ciSearch('');
  } catch(ex) {
    if (status) status.textContent = '❌ Error: '+ex.message;
  }
  if (btn) btn.disabled = false;
}

async function ciLoadStats() {
  try {
    const d = await fetch('/api/codeindex/stats').then(r=>r.ok?r.json():null);
    const status = document.getElementById('ci-index-status');
    if (status && d.total_symbols>0) {
      status.textContent = `${d.total_files} files · ${d.total_symbols} symbols`;
    }
    if (d.total_symbols>0) {
      document.getElementById('ci-empty-state')?.style.display = 'none';
      await ciLoadGraph();
    }
  } catch(e) {}
}

async function ciLoadGraph() {
  try {
    const d = await fetch('/api/codeindex/graph?limit=150').then(r=>r.ok?r.json():null);
    _codeGraphData = {nodes:d.nodes||[],edges:d.edges||[]};
    ciDrawGraph();
  } catch(e) {}
}

function ciDrawGraph() {
  const canvas = document.getElementById('ci-graph-canvas');  // FIX 5
  if (!canvas) return;
  const empty = document.getElementById('ci-empty-state');
  if (empty) empty.style.display = 'none';

  const nodes = _codeGraphData.nodes;
  const edges = _codeGraphData.edges;
  if (!nodes.length) return;

  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const W   = canvas.clientWidth  || 800;
  const H   = canvas.clientHeight || 500;
  canvas.width  = W;
  canvas.height = H;

  // Simple force-directed layout (spring simulation)
  const positions = {};
  nodes.forEach((n,i) => {
    const angle = (i/nodes.length)*Math.PI*2;
    positions[n.id] = {
      x: W/2 + Math.cos(angle)*(Math.min(W,H)*0.35),
      y: H/2 + Math.sin(angle)*(Math.min(W,H)*0.35),
      vx:0, vy:0
    };
  });

  const nodeMap = new Map(nodes.map(n=>[n.id,n]));
  let frame = 0;
  if (_ciAnimFrame) { cancelAnimationFrame(_ciAnimFrame); _ciAnimFrame = null; }  // FIX 7
  const simulate = () => {
    if (frame++ > 150) return; // Stop after convergence

    // Repulsion
    for (let i=0;i<nodes.length;i++) {
      for (let j=i+1;j<nodes.length;j++) {
        const a=positions[nodes[i].id], b=positions[nodes[j].id];
        const dx=b.x-a.x, dy=b.y-a.y;
        const dist=Math.sqrt(dx*dx+dy*dy)||1;
        const force=800/(dist*dist);
        const fx=force*dx/dist, fy=force*dy/dist;
        a.vx-=fx; a.vy-=fy;
        b.vx+=fx; b.vy+=fy;
      }
    }
    // Spring attraction along edges
    edges.forEach(e=>{
      const a=positions[e.source], b=positions[e.target];
      if(!a||!b) return;
      const dx=b.x-a.x, dy=b.y-a.y;
      const dist=Math.sqrt(dx*dx+dy*dy)||1;
      const force=(dist-120)*0.04;
      const fx=force*dx/dist, fy=force*dy/dist;
      a.vx+=fx; a.vy+=fy;
      b.vx-=fx; b.vy-=fy;
    });
    // Gravity to center
    nodes.forEach(n=>{
      const p=positions[n.id];
      p.vx+=(W/2-p.x)*0.005;
      p.vy+=(H/2-p.y)*0.005;
      p.x+=p.vx*0.6; p.y+=p.vy*0.6;
      p.vx*=0.8; p.vy*=0.8;
      p.x=Math.max(30,Math.min(W-30,p.x));
      p.y=Math.max(30,Math.min(H-30,p.y));
    });

    // Draw
    ctx.clearRect(0,0,W,H);
    ctx.fillStyle='#07080f';
    ctx.fillRect(0,0,W,H);

    // Edges
    edges.forEach(e=>{
      const a=positions[e.source], b=positions[e.target];
      if(!a||!b) return;
      ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y);
      ctx.strokeStyle='rgba(255,255,255,.08)'; ctx.lineWidth=1;
      ctx.stroke();
    });

    // Nodes
    nodes.forEach(n=>{
      const p=positions[n.id];
      const r=Math.max(6, Math.min(18, 6+n.size*0.8));
      ctx.beginPath(); ctx.arc(p.x,p.y,r,0,Math.PI*2);
      const ext=n.name.split('.').pop()||'';
      const col = ext==='py'?'#5b8af8':ext==='ts'||ext==='tsx'?'#38c5d8':ext==='js'||ext==='jsx'?'#f0c060':'#9d74f5';
      ctx.fillStyle=col+'cc'; ctx.fill();
      ctx.strokeStyle=col; ctx.lineWidth=1.5; ctx.stroke();

      if (r>10) {
        ctx.fillStyle='rgba(255,255,255,.8)';
        ctx.font=`${Math.max(8,r*0.7)}px Inter,sans-serif`;
        ctx.textAlign='center';
        const label=n.name.slice(0,14);
        ctx.fillText(label,p.x,p.y+r+11);
      }
    });

    if (frame<150) _ciAnimFrame = requestAnimationFrame(simulate);  // FIX 7
  };

  requestAnimationFrame(simulate);

  // Hover tooltip
  canvas.onmousemove = (e) => {
    const rect=canvas.getBoundingClientRect();
    const mx=e.clientX-rect.left, my=e.clientY-rect.top;
    const tip = document.getElementById('ci-node-tooltip');
    for (const n of nodes) {
      const p=positions[n.id];
      if(!p) continue;
      const dist=Math.sqrt((p.x-mx)**2+(p.y-my)**2);
      if (dist<20) {
        tip.style.display='block';
        tip.style.left=(mx+12)+'px'; tip.style.top=(my-10)+'px';
        tip.innerHTML=`<strong>${escHtml(n.name)}</strong><br><span style="color:var(--text-3)">${n.size} symbols</span>`;
        return;
      }
    }
    tip.style.display='none';
  };
}

function ciShowTab(tab, el) {
  document.querySelectorAll('#pane-codeindex .ci-tab').forEach(t=>t.classList.remove('active'));
  el.classList.add('active');

  const canvas  = document.getElementById('ci-graph-canvas');
  const content = document.getElementById('ci-tab-content');
  if (!canvas || !content) return;  // FIX 10

  if (tab==='graph') {
    canvas.style.display=''; content.style.display='none';
    ciLoadGraph();
  } else {
    canvas.style.display='none'; content.style.display='block';
    if (tab==='complexity') ciShowComplexity(content);
    else if (tab==='dead')  ciShowDeadCode(content);
    else if (tab==='stats') ciShowStats(content);
  }
}

async function ciShowComplexity(el) {
  const d = await fetch('/api/codeindex/complexity?min_complexity=3').then(r=>r.ok?r.json():null);
  const max = Math.max(...(d.hotspots||[]).map((h) =>h.complexity), 10);
  el.innerHTML = `
    <div style="font-size:13px;font-weight:700;margin-bottom:12px">🔥 High Complexity Functions (cyclomatic complexity ≥ 3)</div>
    ${(d.hotspots||[]).map((h) => {
      const pct=Math.round(h.complexity/max*100);
      const col=h.complexity>10?'var(--danger)':h.complexity>5?'var(--warning)':'var(--success)';
      return `
        <div class="spec-task-card" style="margin-bottom:6px">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <strong style="font-size:12px">${escHtml(h.symbol_name)}</strong>
            <span style="font-size:11px;color:${col};font-weight:700">CC: ${h.complexity}</span>
            <span style="font-size:10px;color:var(--text-3);margin-left:auto">${escHtml(h.filepath?.split('/').slice(-2).join('/'))}</span>
          </div>
          <div class="ci-complexity-bar"><div class="ci-complexity-fill" style="width:${pct}%;background:${col}"></div></div>
        </div>`;
    }).join('')||'<div style="color:var(--text-3)">No complex functions found (index codebase first)</div>'}`;
}

async function ciShowDeadCode(el) {
  const d = await fetch('/api/codeindex/dead-code').then(r=>r.ok?r.json():null);
  el.innerHTML = `
    <div style="font-size:13px;font-weight:700;margin-bottom:12px">💀 Potentially Dead Code (${d.count} symbols unreferenced)</div>
    ${(d.dead_symbols||[]).slice(0,30).map((s) => `
      <div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-top:1px solid var(--border);font-size:12px">
        <span style="color:var(--danger)">💀</span>
        <strong>${escHtml(s.symbol_name)}</strong>
        <span style="color:var(--text-3);font-size:10px;margin-left:auto">${escHtml((s.filepath||'').split('/').slice(-2).join('/'))}</span>
      </div>
    `).join('')||'<div style="color:var(--text-3)">No dead code detected</div>'}`;
}

async function ciShowStats(el) {
  const d = await fetch('/api/codeindex/stats').then(r=>r.ok?r.json():null);
  el.innerHTML = `
    <div class="ci-stats-grid">
      ${[
        ['📁','Files',d.total_files],['⚡','Functions',d.by_type?.function||0],
        ['🏛','Classes',d.by_type?.class||0],['📥','Imports',d.total_imports],
        ['📞','Calls',d.total_calls],['🔥','Avg Complexity',d.avg_complexity],
      ].map(([icon,label,val])=>`
        <div class="ci-stat-card">
          <div style="font-size:24px">${icon}</div>
          <div style="font-size:11px;color:var(--text-3);text-transform:uppercase;letter-spacing:.5px">${label}</div>
          <div style="font-size:22px;font-weight:700;color:var(--text-0)">${val}</div>
        </div>
      `).join('')}
    </div>`;
}

async function ciSearch(q) {
  if (!q) { ciSearchDefault(); return; }
  try {
    const r = await fetch(`/api/codeindex/symbols?q=${encodeURIComponent(q)}&limit=30`);
    const d = await r.json();
    const el = document.getElementById('ci-sym-list');
    if (!el) return;
    el.innerHTML = (d.symbols||[]).map((s) => `
      <div class="ci-sym-row" onclick="ciShowReferences('${escHtml(s.symbol_name)}')">
        <span class="ci-type-badge ${s.symbol_type}">${s.symbol_type.slice(0,3)}</span>
        <span style="color:var(--text-0);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml(s.symbol_name)}</span>
        <span style="font-size:9px;color:var(--text-3)">L${s.line_no}</span>
      </div>
    `).join('') || '<div style="color:var(--text-3);font-size:12px;padding:6px">No symbols found</div>';
  } catch(e) {}
}

async function ciSearchDefault() {
  try {
    const r = await fetch('/api/codeindex/symbols?limit=30');
    const d = await r.json();
    const el = document.getElementById('ci-sym-list');
    if (!el) return;
    el.innerHTML = (d.symbols||[]).map((s) => `
      <div class="ci-sym-row" onclick="ciShowReferences('${escHtml(s.symbol_name)}')">
        <span class="ci-type-badge ${s.symbol_type}">${s.symbol_type.slice(0,3)}</span>
        <span style="color:var(--text-0);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml(s.symbol_name)}</span>
        <span style="font-size:9px;color:var(--text-3)">L${s.line_no}</span>
      </div>
    `).join('') || '<div style="color:var(--text-3);font-size:12px;padding:6px">Index codebase first</div>';
  } catch(e) {}
}

async function ciShowReferences(symbolName) {
  try {
    const r = await fetch(`/api/codeindex/references/${encodeURIComponent(symbolName)}`);
    const d = await r.json();
    const overlay = document.createElement('div');
    overlay.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    overlay.innerHTML=`
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:14px;max-width:500px;width:100%;padding:20px;max-height:70vh;overflow-y:auto">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <h3 style="margin:0;color:var(--text-0)">References: ${escHtml(symbolName)}</h3>
          <button onclick="this.closest('[style*=\"fixed\"]').remove()" style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
        </div>
        <div style="font-size:12px;color:var(--text-2);margin-bottom:10px">Defined in ${(d.defined_in||[]).length} place(s) · Called ${d.ref_count} time(s)</div>
        ${(d.defined_in||[]).map((s) =>`
          <div style="padding:6px 0;border-top:1px solid var(--border);font-size:12px">
            <strong style="color:var(--success)">DEF</strong> ${escHtml(s.filepath?.split('/').slice(-2).join('/'))} :${s.line_no}
          </div>`).join('')}
        ${(d.called_in||[]).slice(0,20).map((c) =>`
          <div style="padding:6px 0;border-top:1px solid var(--border);font-size:12px">
            <strong style="color:var(--accent)">CALL</strong> from <strong>${escHtml(c.from_symbol)}</strong> in ${escHtml(c.from_file?.split('/').slice(-2).join('/'))} :${c.line_no}
          </div>`).join('')}
      </div>`;
    overlay.onclick = e => { if(e.target===overlay) overlay.remove(); };
    document.body.appendChild(overlay);
  } catch(ex) {}
}


// ══════════════════════════════════════════════════════════════════
//  ARENA MODE — A/B Model Testing
// ══════════════════════════════════════════════════════════════════

let _arenaBattleId = null;
let _arenaModels = [];

async function renderArena() {
  const pane = document.getElementById('pane-arena');
  if (!pane) return;

  const [models, lb, stats] = await Promise.all([
    fetch('/api/arena/models').then(r=>r.ok?r.json():null).catch(()=>({models:[]})),
    fetch('/api/arena/leaderboard').then(r=>r.ok?r.json():null).catch(()=>({leaderboard:[]})),
    fetch('/api/arena/stats').then(r=>r.ok?r.json():null).catch(()=>({})),
  ]);

  _arenaModels = models.models || [];

  pane.innerHTML = `
  

  <div style="display:flex;flex-direction:column;height:100%;overflow:hidden">
    <!-- Top: battle area -->
    <div style="flex:1;overflow:hidden;display:flex;flex-direction:column">
      <!-- Prompt + controls -->
      <div style="padding:12px 16px;background:var(--bg-1);border-bottom:1px solid var(--border);display:flex;flex-direction:column;gap:8px;flex-shrink:0">
        <div style="display:flex;align-items:center;gap:8px">
          <span style="font-size:14px;font-weight:700;color:var(--text-0)">⚔️ Arena Mode</span>
          <span style="font-size:11px;color:var(--text-3)">Test any two models on the same prompt — vote on the winner</span>
          <div style="margin-left:auto;font-size:12px;color:var(--text-2)">${stats.total_battles||0} battles · ${stats.voted_battles||0} voted</div>
        </div>
        <div style="display:flex;gap:8px;align-items:flex-end">
          <textarea class="arena-prompt" id="arena-prompt" placeholder="Enter a prompt to test both models… e.g. 'Explain async/await in JavaScript' or 'Write a Python function to validate email'"></textarea>
          <div style="display:flex;flex-direction:column;gap:5px;flex-shrink:0">
            <select class="arena-model-select" id="arena-model-a" style="width:150px">
              ${_arenaModels.map(m=>`<option value="${m.id}" ${m.id==='claude-sonnet'?'selected':''}>${m.id}</option>`).join('')}
            </select>
            <select class="arena-model-select" id="arena-model-b" style="width:150px">
              ${_arenaModels.map(m=>`<option value="${m.id}" ${m.id==='gpt-4o'?'selected':''}>${m.id}</option>`).join('')}
            </select>
          </div>
          <button class="btn" onclick="arenaStartBattle()" id="arena-go-btn" style="height:60px;padding:0 20px;align-self:stretch">⚔️ Battle!</button>
        </div>
      </div>

      <!-- Side-by-side responses -->
      <div class="arena-layout" id="arena-battle-area" style="flex:1;overflow:hidden;display:grid">
        <div class="arena-side">
          <div class="arena-side-hdr">
            <span style="font-size:16px">🤖</span>
            <strong id="arena-label-a" style="color:var(--accent)">Model A</strong>
            <span id="arena-lat-a" style="margin-left:auto;font-size:10px;color:var(--text-3)"></span>
          </div>
          <div class="arena-response" id="arena-resp-a"><span style="color:var(--text-3)">Response will appear here…</span></div>
          <div class="arena-response-footer" id="arena-footer-a"></div>
        </div>
        <div class="arena-side">
          <div class="arena-side-hdr">
            <span style="font-size:16px">🤖</span>
            <strong id="arena-label-b" style="color:#9d74f5">Model B</strong>
            <span id="arena-lat-b" style="margin-left:auto;font-size:10px;color:var(--text-3)"></span>
          </div>
          <div class="arena-response" id="arena-resp-b"><span style="color:var(--text-3)">Response will appear here…</span></div>
          <div class="arena-response-footer" id="arena-footer-b"></div>
        </div>
      </div>

      <!-- Vote bar -->
      <div id="arena-vote-area" style="display:none;padding:12px 16px;background:var(--bg-1);border-top:1px solid var(--border);text-align:center;flex-shrink:0">
        <div style="font-size:13px;font-weight:600;color:var(--text-0);margin-bottom:10px">Which response was better?</div>
        <div class="arena-vote-row">
          <button class="arena-vote-btn arena-vote-a" onclick="arenaVote('a')">👈 A is Better</button>
          <button class="arena-vote-btn arena-vote-tie" onclick="arenaVote('tie')">🤝 Tie</button>
          <button class="arena-vote-btn arena-vote-b" onclick="arenaVote('b')">B is Better 👉</button>
        </div>
      </div>
    </div>

    <!-- Bottom: leaderboard -->
    <div style="background:var(--bg-1);border-top:2px solid var(--border);max-height:220px;overflow:hidden;display:flex;flex-direction:column;flex-shrink:0">
      <div style="padding:10px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;flex-shrink:0">
        <span style="font-weight:700;font-size:13px">🏆 ELO Leaderboard</span>
        <span style="font-size:11px;color:var(--text-3)">Based on your votes</span>
        <button class="btn-sm" onclick="arenaAutoJudge()" style="margin-left:auto">🤖 Auto-Judge Last</button>
      </div>
      <div class="arena-lb" id="arena-lb">
        ${(lb.leaderboard||[]).length ? lb.leaderboard.map((m, i) => {
          const maxElo = Math.max(...lb.leaderboard.map((x) =>x.elo));
          const pct    = Math.round(m.elo/maxElo*100);
          const medal  = i===0?'🥇':i===1?'🥈':i===2?'🥉':'';
          return `
            <div class="arena-lb-row">
              <span class="arena-lb-rank">${medal||('#'+(i+1))}</span>
              <span style="font-weight:600;width:120px;flex-shrink:0">${escHtml(m.model)}</span>
              <div class="arena-elo-bar"><div class="arena-elo-fill" style="width:${pct}%"></div></div>
              <span style="color:var(--accent);font-weight:700;width:50px;text-align:right">${Math.round(m.elo)}</span>
              <span style="color:var(--text-3);width:80px;text-align:right">${m.win_rate}% WR</span>
              <span style="color:var(--text-3);width:60px;text-align:right">${m.battles}B</span>
            </div>`;
        }).join('') : '<div style="color:var(--text-3);padding:16px;text-align:center">No battles yet — start one above!</div>'}
      </div>
    </div>
  </div>`;
}

async function arenaStartBattle() {
  const prompt  = document.getElementById('arena-prompt')?.value?.trim();
  const modelA  = document.getElementById('arena-model-a')?.value;
  const modelB  = document.getElementById('arena-model-b')?.value;
  if (!prompt) { gmAlert('Enter a prompt first!'); return; }

  const btn = document.getElementById('arena-go-btn');
  if (btn) { btn.disabled=true; btn.textContent='⚔️ Battling…'; }

  // Reset UI
  document.getElementById('arena-resp-a')?.innerHTML = '<span class="typing-cursor"></span>';
  document.getElementById('arena-resp-b')?.innerHTML = '<span class="typing-cursor"></span>';
  document.getElementById('arena-label-a')?.textContent = modelA;
  document.getElementById('arena-label-b')?.textContent = modelB;
  document.getElementById('arena-lat-a')?.textContent = '';
  document.getElementById('arena-lat-b')?.textContent = '';
  document.getElementById('arena-footer-a')?.textContent = '';
  document.getElementById('arena-footer-b')?.textContent = '';
  document.getElementById('arena-vote-area')?.style.display = 'none';

  let textA='', textB='';

  try {
    const resp = await fetch('/api/arena/battle', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({prompt, model_a:modelA, model_b:modelB})
    });
    const reader = resp.body!.getReader();
    const dec    = new TextDecoder();
    let   buf    = '';

    while (true) {
      const {done,value} = await reader.read();
      if (done) break;
      buf += dec.decode(value, {stream:true});
      const parts = buf.split('\n\n');
      buf = parts.pop() || '';
      for (const part of parts) {
        if (!part.startsWith('data:')) continue;
        try {
          const d = JSON.parse(part.slice(5).trim());
          if (d.type==='battle_start') { _arenaBattleId = d.battle_id; }
          else if (d.type==='chunk') {
            const el = document.getElementById(`arena-resp-${d.side}`)!;
            if (d.side==='a') textA+=d.text||'';
            else              textB+=d.text||'';
            el.innerHTML = escHtml(d.side==='a'?textA:textB)+'<span class="typing-cursor"></span>';
            el.scrollTop = el.scrollHeight;
          } else if (d.type==='model_done') {
            const lat = document.getElementById(`arena-lat-${d.side}`)!;
            lat.textContent = `${d.latency_ms}ms · ~${d.tokens} tokens`;
            const el = document.getElementById(`arena-resp-${d.side}`)!;
            el.innerHTML = escHtml(d.side==='a'?textA:textB);
          } else if (d.type==='battle_ready') {
            document.getElementById('arena-vote-area')?.style.display = '';
          }
        } catch(e) {}
      }
    }
  } catch(ex) { gmAlert('Battle error: '+ex.message); }

  if (btn) { btn.disabled=false; btn.textContent='⚔️ Battle!'; }
}

async function arenaVote(winner) {
  if (!_arenaBattleId) return;
  const reason = winner==='tie' ? '' : await gmPrompt('Why? (optional):', '') || '';
  try {
    await fetch(`/api/arena/battle/${encodeURIComponent(_arenaBattleId)}/vote`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({winner, reason})
    });

    const labels = {a:'Model A 👈',b:'Model B 👉',tie:'Tie 🤝'};
    document.getElementById('arena-vote-area')?.innerHTML = `
      <div style="font-size:16px;font-weight:700;color:var(--success)">✅ Vote recorded: <strong>${labels[winner]}</strong></div>
      <div style="font-size:12px;color:var(--text-2);margin-top:6px">ELO updated. Run another battle!</div>
    `;

    // Refresh leaderboard
    setTimeout(async () => {
      const lb = await fetch('/api/arena/leaderboard').then(r=>r.ok?r.json():null);
      const el = document.getElementById('arena-lb');
      if (el && lb.leaderboard?.length) {
        el.innerHTML = lb.leaderboard.map((m, i) => {
          const maxE = Math.max(...lb.leaderboard.map((x) =>x.elo));
          const pct  = Math.round(m.elo/maxE*100);
          const medal= i===0?'🥇':i===1?'🥈':i===2?'🥉':'';
          return `<div class="arena-lb-row">
            <span class="arena-lb-rank">${medal||('#'+(i+1))}</span>
            <span style="font-weight:600;width:120px;flex-shrink:0">${escHtml(m.model)}</span>
            <div class="arena-elo-bar"><div class="arena-elo-fill" style="width:${pct}%"></div></div>
            <span style="color:var(--accent);font-weight:700;width:50px;text-align:right">${Math.round(m.elo)}</span>
            <span style="color:var(--text-3);width:80px;text-align:right">${m.win_rate}% WR</span>
          </div>`;
        }).join('');
      }
    }, 500);
  } catch(ex) { gmAlert('Vote failed: '+ex.message); }
}

async function arenaAutoJudge() {
  if (!_arenaBattleId) { gmAlert('Run a battle first'); return; }
  try {
    const r = await fetch('/api/arena/auto-judge',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({battle_id:_arenaBattleId})});
    const d = await r.json();
    if (d.ok) showToast(`🤖 Auto-judged: ${d.winner} wins — ${d.reason?.slice(0,50)}`);
  } catch(ex) {}
}


// ══════════════════════════════════════════════════════════════════
//  VOICE CODING — WebSpeech API + Voice Commands
// ══════════════════════════════════════════════════════════════════

// ── Voice Coding State ────────────────────────────────────────────
let _voiceRecognition = null;
let _voiceActive      = false;
let _voiceBtn         = null;
let _voiceLang        = 'en-US';
let _voiceContinuous  = false;

function initVoiceCoding() {
  if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
    console.warn('[Voice] Speech Recognition not supported in this browser');
    return false;
  }
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  _voiceRecognition = new SR();
  _voiceRecognition.continuous    = _voiceContinuous;
  _voiceRecognition.interimResults = true;
  _voiceRecognition.lang           = _voiceLang;
  _voiceRecognition.maxAlternatives = 1;

  _voiceRecognition.onresult = async (event) => {
    const transcript = Array.from(event.results)
      .map(r => r[0].transcript).join('');
    const isFinal = event.results[event.results.length - 1].isFinal;
    updateVoiceOverlay(transcript, !isFinal);
    if (isFinal) {
      _voiceActive = false;
      updateVoiceBtn(false);
      hideVoiceOverlay();
      await processVoiceTranscript(transcript);
    }
  };

  _voiceRecognition.onerror = (e) => {
    if (e.error !== 'no-speech') {
      showToast(`🎤 Voice error: ${e.error}`);
    }
    _voiceActive = false;
    updateVoiceBtn(false);
    hideVoiceOverlay();
  };

  _voiceRecognition.onend = () => {
    _voiceActive = false;
    updateVoiceBtn(false);
    setTimeout(hideVoiceOverlay, 500);
  };

  return true;
}

function toggleVoice() {
  if (!_voiceRecognition && !initVoiceCoding()) {
    gmAlert('Voice coding requires Chrome, Edge, or Safari.\n\nOther browsers do not support the Web Speech API.');
    return;
  }
  if (_voiceActive) {
    _voiceRecognition.stop();
    _voiceActive = false;
    updateVoiceBtn(false);
    hideVoiceOverlay();
  } else {
    try {
      _voiceRecognition.start();
      _voiceActive = true;
      updateVoiceBtn(true);
      showVoiceOverlay();
    } catch(ex) {
      showToast('🎤 Could not start voice: ' + (ex?.message || String(ex)));
      _voiceActive = false;
      updateVoiceBtn(false);
    }
  }
}

function updateVoiceBtn(active) {
  const btn = document.getElementById('voice-btn');
  if (!btn) return;
  btn.style.background  = active ? 'var(--danger)' : 'transparent';
  btn.style.color       = active ? '#fff' : 'var(--text-2)';
  btn.style.borderColor = active ? 'var(--danger)' : 'var(--border)';
  btn.title             = active ? 'Stop listening (Ctrl+Shift+V)' : 'Voice coding (Ctrl+Shift+V)';
  btn.innerHTML         = active ? '🔴 Listening…' : '🎤';
}

function showVoiceOverlay(interim) {
  interim = interim || '';
  let overlay = document.getElementById('voice-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'voice-overlay';
    overlay.style.cssText = [
      'position:fixed;bottom:80px;left:50%;transform:translateX(-50%)',
      'background:var(--bg-2);border:1px solid var(--accent);border-radius:14px',
      'padding:14px 24px;z-index:9990;font-size:14px;color:var(--text-0)',
      'text-align:center;min-width:280px;max-width:500px',
      'box-shadow:0 8px 32px rgba(91,138,248,.35)',
      'animation:_vc-in .2s ease',
    ].join(';');
    // Inject animation + blink keyframes once
    if (!document.getElementById('_vc-styles')) {
      const style = document.createElement('style');
      style.id = '_vc-styles';
      style.textContent = [
        '@keyframes _vc-in{from{opacity:0;transform:translateX(-50%) translateY(12px)}to{opacity:1;transform:translateX(-50%) translateY(0)}}',
        '@keyframes _vc-blink{0%,100%{opacity:1}50%{opacity:0}}',
        '._vc-dot{animation:_vc-blink 1s step-end infinite}',
      ].join('\n');
      document.head.appendChild(style);
    }
    document.body.appendChild(overlay);
  }
  overlay.innerHTML = `
    <div style="display:flex;align-items:center;gap:8px;justify-content:center;margin-bottom:6px">
      <span class="_vc-dot" style="color:var(--danger);font-size:18px">●</span>
      <strong>Listening…</strong>
      <button onclick="toggleVoice()" style="margin-left:8px;background:none;border:none;color:var(--text-3);cursor:pointer;font-size:16px" title="Stop">✕</button>
    </div>
    <div id="voice-transcript" style="color:var(--text-2);font-size:12px;min-height:18px;line-height:1.5">${escHtml(interim)}</div>
    <div style="font-size:10px;color:var(--text-3);margin-top:8px">
      Try: "go to chat" · "run tests" · "create app.py" · "search for auth" · "help"
    </div>`;
}

function updateVoiceOverlay(text, isInterim) {
  const t = document.getElementById('voice-transcript');
  if (t) t.innerHTML = `<em style="color:${isInterim ? 'var(--text-3)' : 'var(--text-0)'}">${escHtml(text)}</em>`;
}

function hideVoiceOverlay() {
  document.getElementById('voice-overlay')?.remove();
}

async function processVoiceTranscript(transcript) {
  try {
    const r = await fetch('/api/voice/parse', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({transcript})
    });
    if (!r.ok) {
      showToast(`🎤 Parse failed: HTTP ${r.status}`);
      return;
    }
    const d = await r.json();
    if (!d.ok) { showToast(`🎤 ${d.error||'Unknown error'}`); return; }

    showToast(`🎤 "${transcript.slice(0,40)}" → ${d.action}`);

    switch (d.action) {
      case 'navigate':
        if (d.payload) nav(d.payload);
        break;

      case 'chat_send': {
        nav('chat');
        const chatInput = document.getElementById('chat-input');
        if (chatInput) {
          chatInput.value = d.payload;
          chatInput.dispatchEvent(new Event('input'));
          setTimeout(() => document.getElementById('send-btn')?.click(), 100);
        }
        break;
      }

      case 'run_agent': {
        const agentName = d.payload.toLowerCase();
        showToast(`🤖 Starting agent: ${agentName}`);
        // Navigate to swarm and try to trigger the named agent
        nav('swarm');
        break;
      }

      case 'create_file': {
        const filename = d.payload;
        if (!filename) break;
        nav('studio');
        showToast(`📄 Creating ${filename}…`);
        // Trigger file creation via studio if available
        setTimeout(() => {
          if (typeof createNewFile === 'function') createNewFile(filename);
          else if (typeof studioNewFile === 'function') studioNewFile(filename);
        }, 300);
        break;
      }

      case 'open_file': {
        nav('studio');
        const filename = d.payload;
        showToast(`📂 Opening ${filename}…`);
        setTimeout(() => {
          if (typeof studioOpenFile === 'function') studioOpenFile(filename);
          else if (typeof openFileInStudio === 'function') openFileInStudio(filename);
        }, 300);
        break;
      }

      case 'run_tests':
        nav('testgen');
        setTimeout(() => document.getElementById('tg-run-btn')?.click(), 400);
        break;

      case 'deploy':
        nav('deploy');
        break;

      case 'save': {
        showToast('💾 Saving…');
        // Try Monaco save, then fallback toast
        if (window.S?.monacoEditor) {
          window.S.monacoEditor.trigger('voice', 'editor.action.saveFile', {});
        } else {
          showToast('💾 Use Ctrl+S to save the current file');
        }
        break;
      }

      case 'undo': {
        showToast('↩ Undoing…');
        if (window.S?.monacoEditor) {
          window.S.monacoEditor.trigger('voice', 'undo', {});
        } else {
          document.execCommand('undo');
        }
        break;
      }

      case 'search': {
        nav('codesearch');
        const si = document.getElementById('cs-input');
        if (si) {
          si.value = d.payload;
          si.dispatchEvent(new Event('input'));
          setTimeout(() => document.getElementById('cs-btn')?.click(), 200);
        }
        break;
      }

      case 'run_workflow': {
        nav('workflow');
        showToast(`⚙️ Workflow: ${d.payload}`);
        break;
      }

      case 'command_palette':
        window.openCommandPalette?.() || document.getElementById('cmd-palette-input')?.focus();
        break;

      case 'toggle_sidebar':
        window.toggleSidebar?.();
        break;

      case 'new_chat':
        nav('chat');
        setTimeout(() => document.getElementById('new-chat-btn')?.click(), 200);
        break;

      case 'clear_chat': {
        const ok = await gmDanger('Clear Chat', 'Clear the current chat history?');
        if (ok) {
          nav('chat');
          setTimeout(() => {
            if (typeof clearChat === 'function') clearChat();
            else document.getElementById('clear-chat-btn')?.click();
          }, 200);
        }
        break;
      }

      case 'stop_agents':
        await fetch('/api/control/runs/kill-all', {method: 'POST'}).catch(() => {});
        showToast('🛑 Stopped all agents');
        break;

      case 'change_model': {
        const modelName = d.payload;
        showToast(`🤖 Model: ${modelName} — open Settings to change`);
        nav('settings');
        break;
      }

      case 'help': {
        try {
          const cr = await fetch('/api/voice/commands');
          if (!cr.ok) { showToast('Could not load commands'); break; }
          const cmds = await cr.json();
          const examplesList = (cmds.commands||[]).slice(0,15).map(c => `• ${c.example}`).join('\n');
          gmAlert(`🎤 Voice Commands (${cmds.count} total)\n\n${examplesList}\n\n…or just speak naturally to send a chat message`);
        } catch(ex) {
          showToast('Help load error: '+ex?.message);
        }
        break;
      }

      default:
        showToast(`🎤 ${d.action}: ${(d.payload||'').slice(0,50)}`);
    }
  } catch(ex) {
    console.warn('[Voice] processVoiceTranscript error:', ex);
    showToast('🎤 Voice error: ' + (ex?.message || String(ex)));
    hideVoiceOverlay();
  }
}

// Show voice command history overlay
async function showVoiceHistory() {
  try {
    const r = await fetch('/api/voice/history?limit=20');
    if (!r.ok) { showToast('History load failed'); return; }
    const d = await r.json();
    if (!d.history?.length) { gmAlert('No voice commands yet. Try talking!'); return; }
    const items = d.history.map(h =>
      `<div style="padding:6px 0;border-bottom:1px solid var(--border);font-size:12px">
        <span style="color:var(--accent);font-family:monospace">${escHtml(h.action)}</span>
        ${h.payload ? `<span style="color:var(--text-2)"> → ${escHtml(h.payload.slice(0,60))}</span>` : ''}
        <div style="font-size:10px;color:var(--text-3)">"${escHtml(h.transcript)}"</div>
      </div>`
    ).join('');
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    overlay.innerHTML = `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:16px;max-width:480px;width:100%;max-height:70vh;overflow-y:auto;padding:20px">
        <div style="display:flex;justify-content:space-between;margin-bottom:12px">
          <h3 style="margin:0;color:var(--text-0)">🎤 Voice History (${d.count})</h3>
          <button onclick="this.closest('[style*=fixed]').remove()" style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
        </div>
        ${items}
        <button class="btn-sm" style="margin-top:10px;color:var(--danger)" onclick="fetch('/api/voice/history',{method:'DELETE'}).then(()=>this.closest('[style*=fixed]').remove()).then(()=>showToast('🗑 History cleared'))">🗑 Clear History</button>
      </div>`;
    overlay.onclick = e => { if(e.target===overlay) overlay.remove(); };
    document.body.appendChild(overlay);
  } catch(ex) {
    showToast('History error: '+ex?.message);
  }
}

// Add voice button to topbar
(function addVoiceBtn() {
  const topbar = document.getElementById('topbar');
  if (!topbar || document.getElementById('voice-btn')) return;
  const btn = document.createElement('button');
  btn.id       = 'voice-btn';
  btn.innerHTML = '🎤';
  btn.title    = 'Voice coding (Ctrl+Shift+V)';
  btn.style.cssText = [
    'background:transparent;border:1px solid var(--border);border-radius:8px',
    'color:var(--text-2);padding:4px 8px;cursor:pointer;font-size:14px',
    'transition:all .12s',
  ].join(';');
  btn.onclick = toggleVoice;
  // Insert before the last child (works even without .spacer)
  topbar.appendChild(btn);
  _voiceBtn = btn;
})();

// Keyboard shortcut for voice coding
document.addEventListener('keydown', (e) => {
  if (e.ctrlKey && e.shiftKey && e.key === 'V') {
    e.preventDefault();
    toggleVoice();
  }
  // Escape stops voice
  if (e.key === 'Escape' && _voiceActive) {
    toggleVoice();
  }
});




// ══════════════════════════════════════════════════════════════════
//  PATCH MASTER NAV — Sprint 16 panes
// ══════════════════════════════════════════════════════════════════
(function patchNavSprint16() {
  const _base = window.nav || function(){};
  window.nav = function masterNav16(pane) {
    _base(pane);
    if (pane==='specs')     renderSpecs?.();
    if (pane==='hooks')     renderHooks?.();
    if (pane==='codeindex') renderCodeIndex?.();
    if (pane==='arena')     renderArena?.();
  };
  console.log('%c✅ Sprint 16 loaded: Spec Builder, Hooks, Code Graph, Arena, Voice', 'color:#f06080;font-weight:bold');
})();

// Keyboard shortcuts Sprint 16
document.addEventListener('keydown', (e) => {
  if (!e.metaKey && !e.ctrlKey) return;
  if (e.shiftKey && e.key==='S') { e.preventDefault(); nav('specs'); }
  if (e.shiftKey && e.key==='H') { e.preventDefault(); nav('hooks'); }
  if (e.shiftKey && e.key==='G') { e.preventDefault(); nav('codeindex'); }
  if (e.shiftKey && e.key==='A') { e.preventDefault(); nav('arena'); }
});

