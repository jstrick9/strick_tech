// Agentic OS — Loops Panel
// Extracted from 01-app-core.js for modularity
// ── Loops Panel ───────────────────────────────────────────────────
async function renderLoops() {
  const pane = document.getElementById('pane-loops');
  pane.innerHTML = `<div class="section-head">
    <div><h2>♾️ Autonomous Loops</h2><p>Schedule agents to run repeatedly. They wake on a timer, continue working, and commit results.</p></div>
    <button data-act-click="refreshLoops()" class="btn btn-ghost btn-sm">⟳ Refresh</button>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
    <div class="settings-card">
      <h3>Create Loop</h3>
      <p>Define a recurring autonomous task.</p>
      <label style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px">Goal / Prompt</label>
      <textarea id="loop-prompt" placeholder="/goal Monitor the preview app for errors and auto-fix them every 15 minutes" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px;color:var(--text-0);font-size:13px;resize:none;min-height:80px;outline:none;font-family:inherit;margin:6px 0 10px"></textarea>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
        <div>
          <label style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px;display:block;margin-bottom:4px">Agent</label>
          <select id="loop-agent" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px;color:var(--text-0);font-size:12.5px;outline:none">
            ${S.agents.map(a=>`<option value="${a.id}">${a.avatar||'🤖'} ${escHtml(a.name)}</option>`).join('')}
          </select>
        </div>
        <div>
          <label style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px;display:block;margin-bottom:4px">Every (minutes)</label>
          <input id="loop-interval" type="number" value="15" min="1" max="1440" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px;color:var(--text-0);font-size:12.5px;outline:none">
        </div>
      </div>
      <button data-act-click="createLoop()" class="btn btn-primary" style="width:100%">♾️ Start Loop</button>
    </div>
    <div>
      <div class="settings-card">
        <h3>Running Loops</h3>
        <div id="loop-list" style="display:flex;flex-direction:column;gap:8px">
          <div style="color:var(--text-3);font-size:13px">Loading…</div>
        </div>
      </div>
      <div class="settings-card" style="margin-top:12px">
        <h3>Built-in Auto-Jobs</h3>
        <p style="font-size:12px;color:var(--text-2)">These run automatically in the background.</p>
        <div style="display:flex;flex-direction:column;gap:6px;font-size:12px">
          ${[
            ['Memory FTS reindex','Every 30 min','memory'],
            ['Daily standup journal','8:00 AM daily','brain'],
            ['Cost digest log','Every 6 hours','brain'],
            ['Agent status cleanup','Every 5 min','system'],
          ].map(([name,sched,agent])=>`
          <div style="display:flex;align-items:center;gap:8px;padding:6px 10px;background:var(--bg-3);border-radius:var(--radius-sm)">
            <span style="color:var(--green)">●</span>
            <span style="flex:1;font-weight:600">${name}</span>
            <span style="color:var(--text-2)">${sched}</span>
            <span class="tag">${agent}</span>
          </div>`).join('')}
        </div>
      </div>
    </div>
  </div>`;
  refreshLoops();
}

async function refreshLoops() {
  try {
    const r = await fetch('/api/loops');
    const loops = await r.json();
    const el = document.getElementById('loop-list');
    // update count badge
    const badge = document.getElementById('loop-count');
    if (badge) badge.textContent = loops.length;
    if (!el) return;
    if (!loops.length) {
      el.innerHTML = '<div style="color:var(--text-3);font-size:13px">No loops running. Create one ←</div>';
      return;
    }
    el.innerHTML = loops.map(l => `
      <div style="background:var(--bg-3);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
          <span style="color:var(--green);font-size:10px">●</span>
          <span style="font-weight:700;font-size:12.5px;flex:1">${escHtml(l.id)}</span>
          <span class="tag">${l.interval_minutes}min</span>
          <button data-act-click="pauseLoop(${JSON.stringify(l.id)})" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:11px" title="Pause">${l.status==='paused'?'▶ Resume':'⏸ Pause'}</button>
          <button data-act-click="stopLoop(${JSON.stringify(l.id)})" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:11px">Stop</button>
        </div>
        <div style="font-size:12px;color:var(--text-2);margin-bottom:3px">${escHtml((l.prompt||'').slice(0,100))}</div>
        <div style="font-size:11px;color:var(--text-3)">Runs: ${l.run_count||0} · Next: ${l.next_run?new Date(l.next_run).toLocaleTimeString():'—'}${l.status==='paused'?' · <span style="color:var(--warning)">PAUSED</span>':''}</div>
      </div>`).join('');
  } catch(e) { }
}

async function createLoop() {
  const prompt = document.getElementById('loop-prompt')?.value.trim();
  const agent_id = document.getElementById('loop-agent')?.value || 'builder';
  const interval = parseInt(document.getElementById('loop-interval')?.value || '15');
  if (!prompt) { toast('Enter a goal/prompt', 'warn'); return; }
  try {
    const r = await fetch('/api/loops', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({prompt, agent_id, interval_minutes: interval})
    });
    if (!r.ok) { toast('Server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) {
      toast(`♾️ Loop started: ${j.job_id}`, 'ok');
      document.getElementById('loop-prompt').value = '';
      refreshLoops();
    } else {
      toast('Error: ' + (j.error||'unknown'), 'err');
    }
  } catch(ex) { toast('Network error: ' + ex.message, 'err'); }
}

async function pauseLoop(jobId) {
  const loop = document.querySelector(`[data-loop-id="${jobId}"]`);
  // Determine current state by checking list
  try {
    const r = await fetch('/api/loops');
    if (!r.ok) return;
    const loops = await r.json();
    const l = loops.find(x => x.id === jobId);
    const isPaused = l && l.status === 'paused';
    const endpoint = isPaused ? 'resume' : 'pause';
    const resp = await fetch(`/api/loops/${encodeURIComponent(jobId)}/${encodeURIComponent(endpoint)}`, {method:'POST'});
    if (!resp.ok) { toast('Server error ' + resp.status, 'err'); return; }
    const d = await resp.json();
    if (d.ok) { toast(isPaused ? '▶ Loop resumed' : '⏸ Loop paused', 'ok', 1500); refreshLoops(); }
    else toast('Error: ' + (d.error||''), 'err');
  } catch(ex) { toast('Error: ' + ex.message, 'err'); }
}

async function stopLoop(jobId) {
  const ok = await gmDanger(`Stop loop "${jobId}"? This cannot be undone.`);(`Stop loop "${jobId}"? This cannot be undone.`);
  if (!ok) return;
  try {
    const r = await fetch(`/api/loops/${encodeURIComponent(jobId)}`, {method:'DELETE'});
    if (!r.ok) { toast('Server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast('Loop stopped', 'ok', 1500); refreshLoops(); }
    else toast('Error: ' + (j.error||''), 'err');
  } catch(ex) { toast('Network error: ' + ex.message, 'err'); }
}

