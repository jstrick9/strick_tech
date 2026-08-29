// Fusion — Extracted from 06-sprint-features.js
(function(S, nav, toast, escHtml, fetch, document) {
async function renderFusion() {
  const pane = document.getElementById('pane-fusion');
  if (!pane) return;

  let presets = {presets:{}};
  try {
    const _pr = await fetch('/api/fusion/presets');
    if (_pr.ok) presets = await _pr.json();
  } catch(e) {}

  pane.innerHTML = `
  

  <div class="u-50112d22">
    <div class="section-head">
      <div>
        <h2>🔀 Model Fusion</h2>
        <p>Like OpenRouter Fusion — fan your prompt to multiple models simultaneously, synthesize the best answer. Consistently outperforms single models.</p>
      </div>
    </div>

    <!-- Preset selector -->
    <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap">
      ${Object.entries(presets.presets||{}).map(([id,p])=>`
        <button class="fusion-preset-btn ${id==='budget'?'active':''}" id="fp-${id}" data-act-click="fusionSelectPreset(${jsArg(id)})">
          ${id==='quality'?'⭐':id==='budget'?'💰':id==='code'?'💻':'🔬'} ${id.charAt(0).toUpperCase()+id.slice(1)}
          <div style="font-size:9px;color:var(--text-3);font-weight:400">${(p.desc||'').slice(0,40)}</div>
        </button>
      `).join('')}
    </div>

    <!-- Panel display -->
    <div id="fusion-panel-display" style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap">
      <div style="font-size:12px;color:var(--text-3)">Select a preset above to see the model panel</div>
    </div>

    <!-- Prompt input -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;overflow:hidden;margin-bottom:16px">
      <textarea id="fusion-prompt" rows="5" style="width:100%;background:transparent;border:none;color:var(--text-0);font-size:14px;padding:14px;resize:none;font-family:inherit;line-height:1.6;box-sizing:border-box" placeholder="Ask anything — Fusion sends it to multiple AI models simultaneously and synthesizes the best answer…

Try: 'What are the best practices for building production-ready FastAPI services?'"></textarea>
      <div style="padding:8px 12px;border-top:1px solid var(--border);display:flex;gap:8px;align-items:center">
        <select id="fusion-preset-select" style="background:var(--bg-3);border:1px solid var(--border);border-radius:6px;color:var(--text-1);font-size:12px;padding:5px 8px">
          ${Object.keys(presets.presets||{}).map(k=>`<option value="${k}" ${k==='budget'?'selected':''}>${k}</option>`).join('')}
        </select>
        <button class="btn" data-act-click="fusionRun()" id="fusion-run-btn">⚡ Run Fusion</button>
        <button class="btn-sm" data-act-click="fusionRunSimple()">Simple (no stream)</button>
        <div style="margin-left:auto;font-size:11px;color:var(--text-3)" id="fusion-cost-hint">Budget preset uses free models 💰</div>
      </div>
    </div>

    <!-- Results area -->
    <div id="fusion-results"></div>

    <!-- Smart Router -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;margin-top:20px;overflow:hidden">
      <div class="u-6d452176">🎯 Smart Router — Auto-Pick Best Model</div>
      <div class="u-287f770e">
        <div style="font-size:12px;color:var(--text-2);margin-bottom:10px">Ask anything and the router automatically picks the optimal model (free vs paid, code vs research vs chat)</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <input id="router-prompt" placeholder="Ask anything…" style="flex:1;min-width:200px;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:13px;padding:8px 12px" data-act-keydown="fusionRoute()" data-keys="Enter">
          <button class="btn" data-act-click="fusionRoute()">🎯 Route</button>
          <button class="btn-sm" data-act-click="fusionClassify()">🏷️ Classify</button>
        </div>
        <div id="router-result" class="u-d2c171b1"></div>
        <div id="router-model-table" style="margin-top:12px"></div>
      </div>
    </div>

    <!-- Cost Optimizer -->
    <div class="u-55258e1a">
      <div class="u-6d452176">💰 Cost Optimizer — Stay Within Budget</div>
      <div class="u-287f770e">
        <div style="font-size:12px;color:var(--text-2);margin-bottom:10px">Get the best model that fits your cost budget. Automatically downgrades to free models when needed.</div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <input id="cost-prompt" placeholder="Your prompt…" style="flex:1;min-width:200px;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:13px;padding:8px 12px">
          <input id="cost-budget" type="number" value="0.01" min="0" step="0.001" style="width:90px;background:var(--bg-3);border:1px solid var(--border);border-radius:6px;color:var(--text-0);font-size:12px;padding:6px 8px" placeholder="Budget $">
          <button class="btn" data-act-click="fusionOptimizeCost()">💰 Optimize</button>
        </div>
        <div id="cost-result" class="u-d2c171b1"></div>
      </div>
    </div>

    <!-- Subagent Delegation -->
    <div class="u-55258e1a">
      <div class="u-6d452176">🤖 Subagent Delegation — Big Model → Many Small Models</div>
      <div class="u-287f770e">
        <div style="font-size:12px;color:var(--text-2);margin-bottom:10px">Like OpenRouter Subagent: orchestrator model breaks task into subtasks, delegates to cheaper workers</div>
        <textarea id="subagent-task" rows="3" style="width:100%;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:13px;padding:10px;resize:none;box-sizing:border-box" placeholder="Complex task to delegate (e.g. 'Research FastAPI, write 3 code examples, explain authentication patterns')"></textarea>
        <div style="display:flex;gap:8px;margin-top:8px;align-items:center;flex-wrap:wrap">
          <label style="font-size:11px;color:var(--text-3)">Max subtasks:</label>
          <input id="subagent-max" type="number" min="1" max="8" value="4" style="width:60px;background:var(--bg-3);border:1px solid var(--border);border-radius:6px;color:var(--text-0);font-size:12px;padding:5px 8px">
          <button class="btn" data-act-click="fusionSubagent()">🤖 Delegate</button>
        </div>
        <div id="subagent-result" class="u-d2c171b1"></div>
      </div>
    </div>

    <!-- Run History -->
    <div class="u-55258e1a">
      <div style="padding:12px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between">
        <span class="u-88697aec">📜 Run History</span>
        <button class="btn-sm" data-act-click="fusionLoadHistory()">↻ Load</button>
      </div>
      <div id="fusion-history" style="padding:12px;font-size:12px;color:var(--text-3)">Click Load to show recent fusion runs.</div>
    </div>
  </div>`;

  fusionSelectPreset('budget');
  fusionLoadRoutingTable();
}

let _fusionPreset = 'budget';
const _fusionPresetColors = {quality:'#f0c060',budget:'#4cc98a',code:'#5b8af8',research:'#9d74f5'};

function fusionSelectPreset(preset) {
  _fusionPreset = preset;
  document.querySelectorAll('.fusion-preset-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(`fp-${preset}`)?.classList.add('active');
  const sel = document.getElementById('fusion-preset-select');
  if (sel) sel.value = preset;

  const hints = {quality:'Quality uses frontier models — higher cost',budget:'Budget uses free models — near-frontier quality at $0',code:'Code preset optimized for programming tasks',research:'Research uses strongest reasoning models'};
  const hint = document.getElementById('fusion-cost-hint');
  if (hint) hint.textContent = hints[preset] || '';

  // Show panel
  const display = document.getElementById('fusion-panel-display');
  if (!display) return;
  fetch('/api/fusion/presets')
    .then(r => { if (!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
    .then(d => {
      const p = d.presets?.[preset] || {};
      const panel = p.panel || [];
      display.innerHTML = `
        <div style="font-size:11px;color:var(--text-3);width:100%;margin-bottom:4px">Panel for <strong>${preset}</strong> preset:</div>
        ${panel.map(m=>`
          <div style="background:var(--bg-3);border:1px solid ${_fusionPresetColors[preset]||'var(--border)'}44;border-radius:7px;padding:6px 10px;font-size:11px;color:var(--text-1);font-family:monospace">
            ${escHtml(m.split('/').pop())}
          </div>`).join('')}
        <div style="background:var(--bg-3);border:1px solid var(--accent)44;border-radius:7px;padding:6px 10px;font-size:11px;color:var(--accent-text);font-family:monospace">
          🧑‍⚖️ Judge: ${escHtml((p.judge||'').split('/').pop())}
        </div>`;
    }).catch(()=>{});
}

async function fusionRun() {
  const prompt  = document.getElementById('fusion-prompt')?.value?.trim();
  const preset  = document.getElementById('fusion-preset-select')?.value || _fusionPreset;
  if (!prompt) { gmAlert('Enter a prompt first'); return; }

  const btn = document.getElementById('fusion-run-btn');
  if (btn) { btn.disabled=true; btn.textContent='⏳ Running…'; }

  const results = document.getElementById('fusion-results');
  if (results) results.innerHTML = `
    <div class="u-534c2d64" id="fusion-live">
      <div style="font-size:12px;font-weight:700;margin-bottom:8px">🔀 Fusion Running (${preset} preset)…</div>
      <div id="fusion-panel-responses" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px"></div>
      <div style="font-size:12px;font-weight:700;color:var(--accent-text);margin-bottom:6px" id="fusion-judge-label" style="display:none">🧑‍⚖️ Synthesizing…</div>
      <div id="fusion-synthesis" style="font-size:13px;color:var(--text-1);line-height:1.7;white-space:pre-wrap"></div>
    </div>`;

  const panelResponses = {};

  try {
    const resp = await fetch('/api/fusion/run', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({prompt, preset})
    });
    if (!resp.ok) {
      if (results) results.innerHTML = `<div style="color:var(--danger);padding:8px">Fusion request failed (HTTP ${resp.status})</div>`;
      if (btn) { btn.disabled=false; btn.textContent='⚡ Run Fusion'; }
      return;
    }
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
          if (d.type === 'error') {
            if (results) results.innerHTML = `<div style="color:var(--danger);padding:8px">Error: ${escHtml(d.error||'Unknown error')}</div>`;
            break;
          }
          if (d.type==='panel_response') {
            const mname = (d.model||'').split('/').pop();
            const prEl  = document.getElementById('fusion-panel-responses');
            if (prEl) {
              const card = document.createElement('div');
              card.style.cssText = `background:var(--bg-3);border:1px solid ${d.error?'var(--danger)':'var(--border)'};border-radius:8px;padding:10px;flex:1;min-width:160px;max-width:220px;font-size:11px`;
              card.innerHTML = `<div style="font-weight:700;color:var(--accent-text);margin-bottom:4px">${escHtml(mname)}</div>
                <div style="color:var(--text-2);line-height:1.5">${escHtml((d.text||'').slice(0,150))}${d.text&&d.text.length>150?'…':''}</div>
                <div style="color:var(--text-3);margin-top:4px">${d.latency_ms||0}ms · ${d.tokens||0}t${d.error?' · ⚠️ error':''}</div>`;
              prEl.appendChild(card);
            }
          } else if (d.type==='judging') {
            const jl = document.getElementById('fusion-judge-label');
            if (jl) { jl.style.display='block'; jl.textContent=`🧑‍⚖️ Synthesizing with ${escHtml((d.judge||'').split('/').pop())}…`; }
          } else if (d.type==='synthesis') {
            const syn = document.getElementById('fusion-synthesis');
            if (syn) syn.textContent = d.text || '';
            const jl = document.getElementById('fusion-judge-label');
            if (jl) jl.textContent = `✅ Synthesized from ${d.panel_count||0} models · ${d.total_ms||0}ms · ${d.total_tokens||0}t`;
          }
        } catch(e) {}
      }
    }
  } catch(ex) {
    if (results) results.innerHTML += `<div style="color:var(--danger);padding:8px">Error: ${escHtml(ex?.message||String(ex))}</div>`;
  }

  if (btn) { btn.disabled=false; btn.textContent='⚡ Run Fusion'; }
}

async function fusionRunSimple() {
  const prompt = document.getElementById('fusion-prompt')?.value?.trim();
  const preset = document.getElementById('fusion-preset-select')?.value || _fusionPreset;
  if (!prompt) { gmAlert('Enter a prompt first'); return; }
  const results = document.getElementById('fusion-results');
  if (results) results.innerHTML = '<div style="color:var(--text-2);padding:8px">⏳ Running simple fusion…</div>';
  try {
    const r = await fetch('/api/fusion/run/simple', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({prompt, preset})});
    if (!r.ok) { if (results) results.innerHTML = `<div style="color:var(--danger)">Request failed (HTTP ${r.status})</div>`; return; }
    const d = await r.json();
    if (!d.ok) { if (results) results.innerHTML = `<div style="color:var(--danger)">${escHtml(d.error||'Unknown error')}</div>`; return; }
    if (results) results.innerHTML = `
      <div class="u-534c2d64">
        <div style="font-size:11px;color:var(--text-3);margin-bottom:8px">Preset: ${escHtml(d.preset||preset)} · ${d.total_ms||0}ms</div>
        <div style="font-size:13px;line-height:1.7;color:var(--text-0);white-space:pre-wrap">${escHtml(d.synthesis||'')}</div>
        <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
          ${(d.panel||[]).map(p=>`<div style="font-size:10px;background:var(--bg-3);padding:3px 8px;border-radius:5px;color:${p.error?'var(--danger)':'var(--text-3)'}">${escHtml((p.model||'').split('/').pop())} · ${p.tokens||0}t${p.error?' ⚠️':''}</div>`).join('')}
        </div>
      </div>`;
  } catch(ex) {
    if (results) results.innerHTML = `<div style="color:var(--danger)">Error: ${escHtml(ex?.message||String(ex))}</div>`;
  }
}

// GET /api/fusion/route/models has existed all along and NOTHING CALLED IT.
// It returns the routing table -- which model handles each task type, why, and
// the estimated cost per 1k tokens. The panel above promises the router "picks
// the optimal model" while showing the user no way to see what it will pick or
// what it costs, so the promise is unverifiable from the UI.
//
// This is the Bug 4 class: a working endpoint with no caller. Found by
// scripts/sweep_untriggered_capability.py. It renders with the pane, so the
// information is there before you ask rather than behind a button you have to
// discover.
async function fusionLoadRoutingTable() {
  const el = document.getElementById('router-model-table');
  if (!el) return;
  try {
    const r = await fetch('/api/fusion/route/models');
    if (!r.ok) return;                       // silent: this is enrichment
    const d = await r.json();
    const rows = (d && d.task_types) || [];
    if (!rows.length) return;
    el.innerHTML = `
      <details style="font-size:12px">
        <summary style="cursor:pointer;color:var(--text-2)">
          Routing table — ${rows.length} task types
        </summary>
        <div style="margin-top:8px;display:flex;flex-direction:column;gap:4px">
          ${rows.map(t => `
            <div style="display:flex;gap:8px;align-items:baseline;flex-wrap:wrap">
              <span style="font-size:10px;background:var(--bg-3);padding:2px 8px;border-radius:4px;color:var(--text-1)">${escHtml(t.type || '')}</span>
              <strong style="font-size:11.5px">${escHtml(String(t.model || '').split('/').pop())}</strong>
              <span style="font-size:11px;color:var(--text-3)">${escHtml(t.reason || '')}</span>
              <span style="font-size:10px;color:var(--text-3);margin-left:auto">$${Number(t.est_cost_per_1k || 0).toFixed(4)}/1k</span>
            </div>`).join('')}
        </div>
      </details>`;
  } catch (e) {
    // Enrichment only — never let this break the pane.
  }
}

async function fusionRoute() {
  const prompt = document.getElementById('router-prompt')?.value?.trim();
  if (!prompt) { gmAlert('Enter a prompt to route'); return; }
  const el = document.getElementById('router-result');
  if (el) el.innerHTML = '<div style="color:var(--text-2);font-size:12px">🎯 Routing…</div>';
  try {
    const r = await fetch('/api/fusion/route', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({prompt})});
    if (!r.ok) { if (el) el.innerHTML = `<div style="color:var(--danger)">Route failed (HTTP ${r.status})</div>`; return; }
    const d = await r.json();
    if (!d.ok) { if (el) el.innerHTML = `<div style="color:var(--danger)">${escHtml(d.error||'Unknown error')}</div>`; return; }
    if (el) el.innerHTML = `
      <div style="background:var(--bg-3);border-radius:8px;padding:12px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap">
          <span style="font-size:10px;background:var(--accent);color:var(--on-accent);padding:2px 8px;border-radius:4px">${escHtml(d.task_type||'')}</span>
          <strong class="u-6cb285c6">${escHtml((d.model||'').split('/').pop())}</strong>
          <span style="font-size:11px;color:var(--text-3)">${d.latency_ms||0}ms · ${d.tokens||0}t${d.error?' · ⚠️ error':''}</span>
        </div>
        <div style="font-size:12px;color:var(--text-2);margin-bottom:8px">${escHtml(d.reason||'')}</div>
        <div style="font-size:13px;color:var(--text-1);line-height:1.6;white-space:pre-wrap">${escHtml((d.text||'').slice(0,800))}</div>
      </div>`;
  } catch(ex) {
    if (el) el.innerHTML = `<div style="color:var(--danger)">Error: ${escHtml(ex?.message||String(ex))}</div>`;
  }
}

async function fusionClassify() {
  const prompt = document.getElementById('router-prompt')?.value?.trim();
  if (!prompt) { gmAlert('Enter a prompt to classify'); return; }
  const el = document.getElementById('router-result');
  if (el) el.innerHTML = '<div style="color:var(--text-2);font-size:12px">🏷️ Classifying…</div>';
  try {
    const r = await fetch(`/api/fusion/classify?q=${encodeURIComponent(prompt)}`);
    if (!r.ok) { if (el) el.innerHTML = `<div style="color:var(--danger)">Classify failed (HTTP ${r.status})</div>`; return; }
    const d = await r.json();
    if (!d.ok) { if (el) el.innerHTML = `<div style="color:var(--danger)">${escHtml(d.error||'Unknown error')}</div>`; return; }
    if (el) el.innerHTML = `
      <div style="background:var(--bg-3);border-radius:8px;padding:12px;font-size:12px">
        <div style="display:flex;gap:8px;margin-bottom:6px;flex-wrap:wrap">
          <span style="background:var(--accent);color:var(--on-accent);padding:2px 8px;border-radius:4px">${escHtml(d.task_type||'')}</span>
          <span style="color:var(--text-1);font-weight:600">${escHtml((d.model||'').split('/').pop())}</span>
        </div>
        <div style="color:var(--text-2)">${escHtml(d.reason||'')}</div>
        <div style="color:var(--text-3);margin-top:4px">Est. tokens: ${d.est_tokens||0} · Est. cost: $${(d.est_cost_usd||0).toFixed(6)}</div>
      </div>`;
  } catch(ex) {
    if (el) el.innerHTML = `<div style="color:var(--danger)">Error: ${escHtml(ex?.message||String(ex))}</div>`;
  }
}

async function fusionOptimizeCost() {
  const prompt = document.getElementById('cost-prompt')?.value?.trim();
  const budget = parseFloat(document.getElementById('cost-budget')?.value||'0.01');
  if (!prompt) { gmAlert('Enter a prompt to optimize'); return; }
  const el = document.getElementById('cost-result');
  if (el) el.innerHTML = '<div style="color:var(--text-2);font-size:12px">💰 Optimizing…</div>';
  try {
    const r = await fetch('/api/fusion/optimize-cost', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({prompt, budget_usd:budget})});
    if (!r.ok) { if (el) el.innerHTML = `<div style="color:var(--danger)">Optimize failed (HTTP ${r.status})</div>`; return; }
    const d = await r.json();
    if (!d.ok) { if (el) el.innerHTML = `<div style="color:var(--danger)">${escHtml(d.error||'Unknown error')}</div>`; return; }
    if (el) el.innerHTML = `
      <div style="background:var(--bg-3);border-radius:8px;padding:12px;font-size:12px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap">
          <span style="background:var(--accent);color:var(--on-accent);padding:2px 8px;border-radius:4px">${escHtml(d.task_type||'')}</span>
          <strong>${escHtml((d.recommended||'').split('/').pop())}</strong>
          ${d.downgraded?'<span style="color:var(--warning);font-size:10px">⬇ downgraded</span>':'<span style="color:var(--success);font-size:10px">✅ within budget</span>'}
        </div>
        <div style="color:var(--text-2);margin-bottom:4px">${escHtml(d.reason||'')}</div>
        <div style="color:var(--text-3)">Budget: $${budget.toFixed(6)} · Est cost: $${(d.est_cost_usd||0).toFixed(6)} · Est tokens: ${d.est_tokens||0}</div>
        ${d.downgraded?`<div style="color:var(--text-3);margin-top:2px">Original: ${escHtml((d.original_model||'').split('/').pop())}</div>`:''}
      </div>`;
  } catch(ex) {
    if (el) el.innerHTML = `<div style="color:var(--danger)">Error: ${escHtml(ex?.message||String(ex))}</div>`;
  }
}

async function fusionLoadHistory() {
  const el = document.getElementById('fusion-history');
  if (!el) return;
  el.innerHTML = '<div style="color:var(--text-3);font-size:12px">Loading…</div>';
  try {
    const r = await fetch('/api/fusion/history?limit=10');
    if (!r.ok) { el.innerHTML = `<div style="color:var(--danger)">Failed (HTTP ${r.status})</div>`; return; }
    const d = await r.json();
    if (!d.history?.length) { el.innerHTML = '<div style="color:var(--text-3);font-size:12px">No runs yet. Run a fusion first!</div>'; return; }
    el.innerHTML = d.history.map(h => `
      <div style="border-top:1px solid var(--border);padding:8px 0;font-size:12px">
        <div style="display:flex;gap:6px;margin-bottom:3px">
          <span style="background:var(--bg-3);padding:1px 6px;border-radius:4px;font-size:10px">${escHtml(h.run_type||'fusion')}</span>
          <span style="background:var(--bg-3);padding:1px 6px;border-radius:4px;font-size:10px">${escHtml(h.preset||'')}</span>
          <span style="color:var(--text-3);margin-left:auto;font-size:10px">${(h.created_at||'').slice(0,16)}</span>
        </div>
        <div style="color:var(--text-2);margin-bottom:3px">${escHtml((h.prompt||'').slice(0,80))}${(h.prompt||'').length>80?'…':''}</div>
        <div style="color:var(--text-3);font-size:11px">${h.total_ms||0}ms · ${h.total_tokens||0}t</div>
      </div>`).join('');
  } catch(ex) {
    el.innerHTML = `<div style="color:var(--danger)">Error: ${escHtml(ex?.message||String(ex))}</div>`;
  }
}

async function fusionSubagent() {
  const task  = document.getElementById('subagent-task')?.value?.trim();
  const maxSt = Math.max(1, Math.min(8, parseInt(document.getElementById('subagent-max')?.value||'4')));
  if (!task) { gmAlert('Enter a task to delegate'); return; }

  const el = document.getElementById('subagent-result');
  if (el) el.innerHTML = '<div style="color:var(--text-2);font-size:12px;font-family:monospace">🤖 Planning subtasks…</div>';

  try {
    const resp = await fetch('/api/fusion/subagent', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({task, max_subtasks:maxSt})
    });
    if (!resp.ok) {
      if (el) el.innerHTML = `<div style="color:var(--danger)">Subagent request failed (HTTP ${resp.status})</div>`;
      return;
    }
    const reader = resp.body.getReader();
    const dec    = new TextDecoder();
    let   buf    = '';
    let synthesis = '', subtasks = [], totalMs = 0, totalTok = 0;

    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buf += dec.decode(value, {stream:true});
      const parts = buf.split('\n\n');
      buf = parts.pop() || '';
      for (const part of parts) {
        if (!part.startsWith('data:')) continue;
        try {
          const d = JSON.parse(part.slice(5).trim());
          if (d.type === 'subtasks_planned') {
            subtasks = d.subtasks || [];
            if (el) el.innerHTML = `<div style="font-size:12px;color:var(--text-2);font-family:monospace">Delegating ${d.count} subtasks to worker models…</div>`;
          } else if (d.type === 'subtask_done') {
            if (el) el.innerHTML += `<div style="font-size:11px;color:var(--success);padding:2px 0">✅ ${escHtml((d.subtask||'').slice(0,80))}${d.error?' ⚠️':''}</div>`;
          } else if (d.type === 'synthesis') {
            synthesis = d.text || '';
            totalMs   = d.total_ms || 0;
            totalTok  = d.total_tokens || 0;
          }
        } catch(e) {}
      }
    }
    if (el) {
      el.innerHTML = `
        <div style="background:var(--bg-3);border-radius:8px;padding:12px;margin-top:8px">
          <div style="font-size:11px;font-weight:700;color:var(--accent-text);margin-bottom:8px">
            ✨ Synthesized from ${subtasks.length} subtask${subtasks.length!==1?'s':''}
            <span style="font-weight:400;color:var(--text-3)">· ${totalMs}ms · ${totalTok}t</span>
          </div>
          <div style="font-size:13px;color:var(--text-1);line-height:1.7;white-space:pre-wrap">${escHtml(synthesis||'No synthesis produced.')}</div>
        </div>`;
    }
  } catch(ex) {
    if (el) el.innerHTML = `<div style="color:var(--danger)">Error: ${escHtml(ex?.message||String(ex))}</div>`;
  }
}


window.renderFusion = renderFusion;
// ── Delegated-handler exports ─────────────────────────────────────────────
// These are referenced by data-act-* attributes in this pane. The
// delegated dispatcher resolves handler names by property lookup on
// window, and this file is IIFE-wrapped, so without these assignments
// every one of them silently no-ops.
window.fusionClassify = fusionClassify;
window.fusionLoadHistory = fusionLoadHistory;
window.fusionOptimizeCost = fusionOptimizeCost;
window.fusionRoute = fusionRoute;
window.fusionRun = fusionRun;
window.fusionRunSimple = fusionRunSimple;
window.fusionSelectPreset = fusionSelectPreset;
window.fusionSubagent = fusionSubagent;
})(S, nav, toast, escHtml, fetch, document);
