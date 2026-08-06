// Agentic OS — Pipeline
// Extracted from 01-app-core.js for modularity
//
// BUG FIX (quote-collision, total breakage of template buttons): the
// goal-template buttons used
// onclick="document.getElementById('pipe-goal').value=${JSON.stringify(t.goal)}"
// -- the same unconditional-breakage pattern found in Terminal's
// quick-command toolbar and Skills' skill-card grid earlier this
// session. JSON.stringify() ALWAYS wraps its output in literal double
// quotes, which ALWAYS collide with the onclick attribute's own
// double-quote delimiters, regardless of what `t.goal` contains.
// Reproduced live: clicking the "🚀 SaaS Landing Page" template button
// (whose goal text is plain, quote-free prose) still threw "Uncaught
// SyntaxError: Unexpected end of input" and never filled the goal
// textarea -- every one of the 6 preset templates was completely
// unusable via its button. Fixed via data-template-idx + a delegated
// listener on the template button container, looking up the real goal
// string from the already-fetched `templates` array by index instead of
// ever serializing it into an HTML attribute.
// ── Pipeline Pane ─────────────────────────────────────────────────
async function renderPipeline() {
  const pane = document.getElementById('pane-pipeline');
  let templates = [];
  try { const r = await fetch('/api/pipeline/templates'); const d = await r.json(); templates = Array.isArray(d) ? d : (Array.isArray(d.templates) ? d.templates : []); } catch(e){}

  pane.innerHTML = `<div class="section-head">
    <div><h2>🏛️ Pipeline</h2><p>Autonomous multi-stage: Goal → Research → Code → Review → Ship</p></div>
    <button data-act-click="loadPipelineHistory()" class="btn btn-ghost btn-sm">📋 History</button>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
    <div>
      <div class="settings-card">
        <h3>Goal</h3>
        <textarea id="pipe-goal" placeholder="Build a SaaS landing page with hero, pricing, and CTA sections using Tailwind CSS"
          style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;color:var(--text-0);font-size:13px;resize:none;min-height:90px;outline:none;font-family:inherit;margin-bottom:10px"></textarea>
        <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Stages</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px" id="pipe-stages">
          ${['goal','research','code','review','ship'].map(s => `
            <label style="display:flex;align-items:center;gap:5px;background:var(--bg-3);border-radius:var(--radius-sm);padding:5px 10px;cursor:pointer;font-size:12px;border:1px solid var(--border)">
              <input type="checkbox" data-stage="${s}" checked style="accent-color:var(--accent-text)">${s}
            </label>`).join('')}
        </div>
        <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Templates</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px" id="pipe-templates">
          ${templates.map((t, idx) => `<button type="button" data-template-idx="${idx}" class="btn btn-ghost btn-sm">${escHtml(t.label)}</button>`).join('')}
        </div>
        <button data-act-click="runPipeline()" class="btn btn-primary" style="width:100%" id="pipe-run-btn">🏛️ Run Pipeline</button>
        <div id="pipe-status" style="font-size:12px;color:var(--text-2);margin-top:8px;min-height:18px"></div>
      </div>
    </div>
    <div id="pipe-results" style="overflow-y:auto;max-height:calc(100vh - 160px)">
      <div style="color:var(--text-3);font-size:13px;text-align:center;padding:40px">
        Run a pipeline → stage results appear here live
      </div>
    </div>
  </div>`;

  document.getElementById('pipe-templates')?.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-template-idx]');
    if (!btn) return;
    const goalEl = document.getElementById('pipe-goal');
    if (goalEl) goalEl.value = templates[Number(btn.dataset.templateIdx)]?.goal || '';
  });
}

async function runPipeline() {
  const goal = document.getElementById('pipe-goal')?.value.trim();
  if (!goal) { toast('Enter a goal first', 'warn'); return; }
  const stages = [...document.querySelectorAll('#pipe-stages input:checked')].map(i => i.dataset.stage);
  if (!stages.length) { toast('Select at least one stage', 'warn'); return; }

  const btn    = document.getElementById('pipe-run-btn');
  const status = document.getElementById('pipe-status');
  const results = document.getElementById('pipe-results');
  btn.disabled = true; btn.textContent = '⏳ Running pipeline…';
  status.textContent = 'Starting…';

  // Render skeleton
  results.innerHTML = stages.map(s => `
    <div id="pipe-card-${s}" class="settings-card" style="margin-bottom:12px;opacity:.5">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
        <span class="u-1444c6ea">${{goal:'🏛️',research:'🔭',code:'⚡',review:'🔨',ship:'🚀'}[s]||'⚙️'}</span>
        <span style="font-weight:700;text-transform:uppercase;font-size:12px">${s}</span>
        <span id="pipe-badge-${s}" class="tag u-6d000617" >waiting</span>
      </div>
      <div id="pipe-out-${s}" style="font-size:12.5px;color:var(--text-2);line-height:1.6">…</div>
    </div>`).join('');

  try {
    const resp = await fetch('/api/pipeline/run', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ goal, stages, stream: true }),
    });
    if (!resp.ok) { throw new Error('Server error ' + resp.status); }
    if (!resp.body) { throw new Error('No response body (SSE not supported)'); }

    const reader  = resp.body.getReader();
    const decoder = new TextDecoder();
    let totalTokens = 0, totalCost = 0;
    let sseBuffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      sseBuffer += decoder.decode(value, { stream: true });
      // Process complete SSE messages (terminated by double newline)
      const messages = sseBuffer.split('\n\n');
      sseBuffer = messages.pop() || '';   // keep incomplete tail
      for (const msg of messages) {
        for (const line of msg.split('\n')) {
          if (!line.startsWith('data:')) continue;
          try {
            const ev = JSON.parse(line.slice(5).trim());
            if (ev.type === 'stage_start') {
              const badge = document.getElementById(`pipe-badge-${ev.stage}`);
              const card  = document.getElementById(`pipe-card-${ev.stage}`);
              if (badge) badge.textContent = 'running…';
              if (badge) badge.style.color = 'var(--yellow)';
              if (card)  card.style.opacity = '1';
              status.textContent = `Running ${ev.stage}…`;
            }
            if (ev.type === 'stage_done') {
              const badge = document.getElementById(`pipe-badge-${ev.stage}`);
              const out   = document.getElementById(`pipe-out-${ev.stage}`);
              if (badge) { badge.textContent = `✅ ${ev.result?.latency_ms||0}ms · ${ev.result?.tokens||0}t`; badge.style.color = 'var(--green)'; }
              if (out)   out.innerHTML = renderMarkdown(ev.result?.output || '(empty)');
              totalTokens += ev.result?.tokens || 0;
              totalCost   += ev.result?.cost   || 0;
            }
            if (ev.type === 'stage_error') {
              const badge = document.getElementById(`pipe-badge-${ev.stage}`);
              const out   = document.getElementById(`pipe-out-${ev.stage}`);
              if (badge) { badge.textContent = '❌ error'; badge.style.color = 'var(--red)'; }
              if (out)   out.textContent = ev.error || 'Stage failed';
            }
            if (ev.type === 'complete') {
              status.innerHTML = `✅ Done · ${ev.duration_ms}ms · ${totalTokens} tokens · $${totalCost.toFixed(5)}`;
              toast(`🏛️ Pipeline complete — ${stages.length} stages`, 'ok', 4000);
            }
          } catch(e) {}
        }
      }
    }
  } catch(e) {
    status.textContent = '✗ ' + e.message;
    toast('Pipeline error: ' + e.message, 'err');
  } finally {
    btn.disabled = false; btn.textContent = '🏛️ Run Pipeline';
  }
}

async function loadPipelineHistory() {
  try {
    const r = await fetch('/api/pipeline/history?limit=20');
    if (!r.ok) { gmAlert('Failed to load history: server error ' + r.status); return; }
    const j = await r.json();
    if (!j.length) { await gmAlert('Pipeline History', 'No pipeline runs yet.'); return; }
    const lines = j.map((h,i) => `${i+1}. [${h.ts}] ${(h.detail||'').slice(0,80)}`).join('\n');
    await gmAlert('📋 Pipeline History', `<pre style="font-size:12px;white-space:pre-wrap">${escHtml(lines)}</pre>`);
  } catch(ex) { gmAlert('Pipeline history error: ' + ex.message); }
}

