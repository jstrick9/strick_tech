
;/* 40-loops.js */
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
          <input id="loop-interval" type="number" value="15" min="1" max="10080" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px;color:var(--text-0);font-size:12.5px;outline:none">
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;align-items:end">
        <div>
          <label style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px;display:block;margin-bottom:4px" title="0 means the loop runs until you stop it">Max runs (0 = unlimited)</label>
          <input id="loop-max-runs" type="number" value="0" min="0" max="10000" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px;color:var(--text-0);font-size:12.5px;outline:none">
        </div>
        <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-2);cursor:pointer;padding-bottom:7px">
          <input type="checkbox" id="loop-kill-success"> Stop after first success
        </label>
      </div>
      <div style="font-size:11px;color:var(--text-3);margin-bottom:10px">This agent calls the model on every tick and spends real credit. A bounded loop is safer than an unbounded one.</div>
      <button data-act-click="createLoop()" class="btn btn-primary" style="width:100%">♾️ Start Loop</button>
    </div>
    <div>
      <div class="settings-card">
        <h3>Running Loops</h3>
        <div id="loop-list" style="display:flex;flex-direction:column;gap:8px">
          <div style="color:var(--text-3);font-size:13px">Loading…</div>
        </div>
      </div>
      <div class="settings-card u-56f43562" >
        <h3>Built-in Auto-Jobs</h3>
        <p style="font-size:12px;color:var(--text-2)">These run automatically in the background.</p>
        <div id="loop-builtins" style="display:flex;flex-direction:column;gap:6px;font-size:12px">
          <div style="color:var(--text-3)">Checking…</div>
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
          <span style="color:${l.status==='paused'?'var(--warning)':(l.last_error?'var(--danger)':'var(--green)')};font-size:10px" title="${l.status==='paused'?'Paused':(l.last_error?'Last run failed':'Running')}">●</span>
          <span style="font-weight:700;font-size:12.5px;flex:1">${escHtml(l.id)}</span>
          <span class="tag">${l.interval_minutes}min</span>
          <button data-act-click="pauseLoop(${jsArg(l.id)})" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:11px" title="${l.status==='paused'?'Resume':'Pause'}">${l.status==='paused'?'▶ Resume':'⏸ Pause'}</button>
          <button data-act-click="stopLoop(${jsArg(l.id)})" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:11px">Stop</button>
        </div>
        <div style="font-size:12px;color:var(--text-2);margin-bottom:3px">${escHtml((l.prompt||'').slice(0,100))}</div>
        <div style="font-size:11px;color:var(--text-3)">Runs: ${l.run_count||0}${l.max_runs?' / '+l.max_runs:''} · Next: ${l.next_run?new Date(l.next_run).toLocaleTimeString():'—'}${l.status==='paused'?' · <span style="color:var(--warning)">PAUSED</span>':''}${l.kill_after_success?' · <span class="tag">stops on success</span>':''}${(!l.max_runs && !l.kill_after_success)?' · <span style="color:var(--text-3)">runs until stopped</span>':''}</div>
        ${l.last_error?`<div style="font-size:11px;color:var(--danger);margin-top:4px">⚠ Last run failed: ${escHtml(String(l.last_error).slice(0,140))}</div>`:''}
      </div>`).join('');
} catch(e) { }
refreshBuiltinJobs();
}
const BUILTIN_JOB_LABELS = {
memory_index:   ['Memory FTS reindex',     'Every 30 min',   'memory'],
standup:        ['Daily standup journal',  '8:00 AM daily',  'brain'],
cost_digest:    ['Cost digest log',        'Every 6 hours',  'brain'],
status_cleanup: ['Agent status cleanup',   'Every 5 min',    'system'],
};
async function refreshBuiltinJobs() {
const el = document.getElementById('loop-builtins');
if (!el) return;
try {
const r = await fetch('/api/loops/status');
if (!r.ok) throw new Error('status ' + r.status);
const d = await r.json();
if (!d.scheduler_available || !d.running) {
el.innerHTML = `<div style="color:var(--warning)">⚠ Scheduler is not running — no background jobs are active${d.scheduler_available?'':' (APScheduler not installed)'}.</div>`;
return;
}
const live = new Map((d.builtin_jobs||[]).map(j => [j.id, j]));
el.innerHTML = Object.entries(BUILTIN_JOB_LABELS).map(([id,[name,schedule,agent]]) => {
const j = live.get(id);
const on = !!j;
return `<div style="display:flex;align-items:center;gap:8px;padding:6px 10px;background:var(--bg-3);border-radius:var(--radius-sm)">
        <span style="color:${on?'var(--green)':'var(--danger)'}" title="${on?'Registered':'Not registered'}">●</span>
        <span class="u-392bcb2a">${escHtml(name)}</span>
        <span style="color:var(--text-2)">${escHtml(schedule)}</span>
        <span class="tag">${escHtml(agent)}</span>
        ${on?'':'<span style="color:var(--danger);font-size:11px">not running</span>'}
      </div>`;
}).join('');
} catch(ex) {
el.innerHTML = `<div style="color:var(--text-3)">Could not read scheduler status: ${escHtml(ex.message)}</div>`;
}
}
async function createLoop() {
const prompt = document.getElementById('loop-prompt')?.value.trim();
const agent_id = document.getElementById('loop-agent')?.value || 'builder';
const interval = parseInt(document.getElementById('loop-interval')?.value || '15');
const maxRuns = parseInt(document.getElementById('loop-max-runs')?.value || '0') || 0;
const killAfterSuccess = !!document.getElementById('loop-kill-success')?.checked;
if (!prompt) { toast('Enter a goal/prompt', 'warn'); return; }
try {
const r = await fetch('/api/loops', {
method:'POST', headers:{'Content-Type':'application/json'},
body: JSON.stringify({prompt, agent_id, interval_minutes: interval,
max_runs: maxRuns, kill_after_success: killAfterSuccess})
});
const j = await r.json().catch(() => ({}));
if (!r.ok) { toast('Error: ' + (j.error || ('Server error ' + r.status)), 'err'); return; }
if (j.ok) {
toast(`♾️ Loop started: ${j.job_id}`, 'ok');
if (j.interval_adjusted) toast(j.note, 'warn', 6000);
document.getElementById('loop-prompt').value = '';
refreshLoops();
} else {
toast('Error: ' + (j.error||'unknown'), 'err');
}
} catch(ex) { toast('Network error: ' + ex.message, 'err'); }
}
async function pauseLoop(jobId) {
const loop = document.querySelector(`[data-loop-id="${jobId}"]`);
try {
const r = await fetch('/api/loops');
if (!r.ok) return;
const loops = await r.json();
const l = loops.find(x => x.id === jobId);
const isPaused = l && l.status === 'paused';
const endpoint = isPaused ? 'resume' : 'pause';
const resp = await fetch(`/api/loops/${encodeURIComponent(jobId)}/${encodeURIComponent(endpoint)}`, {method:'POST'});
const d = await resp.json().catch(() => ({}));
if (!resp.ok) { toast('Error: ' + (d.error || ('Server error ' + resp.status)), 'err'); refreshLoops(); return; }
if (d.ok) { toast(isPaused ? '▶ Loop resumed' : '⏸ Loop paused', 'ok', 1500); refreshLoops(); }
else toast('Error: ' + (d.error||''), 'err');
} catch(ex) { toast('Error: ' + ex.message, 'err'); }
}
async function stopLoop(jobId) {
const ok = await gmDanger('Stop loop', `Stop loop "${jobId}"? This cannot be undone.`, 'Stop');
if (!ok) return;
try {
const r = await fetch(`/api/loops/${encodeURIComponent(jobId)}`, {method:'DELETE'});
const j = await r.json().catch(() => ({}));
if (!r.ok) { toast('Error: ' + (j.error || ('Server error ' + r.status)), 'err'); refreshLoops(); return; }
if (j.ok) { toast('Loop stopped', 'ok', 1500); refreshLoops(); }
else toast('Error: ' + (j.error||''), 'err');
} catch(ex) { toast('Network error: ' + ex.message, 'err'); }
}
