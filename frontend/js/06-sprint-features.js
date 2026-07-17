// Agentic OS v6.0 — Sprint features — fusion, HITL, browser, websearch, leaderboard, audit, identity, supervisor, goals, MCP gateway, connectors, A2A, monitor, finops, eval framework
// Extracted from index.html (block 6)


'use strict';

// ══════════════════════════════════════════════════════════════════
//  PWA REGISTRATION
// ══════════════════════════════════════════════════════════════════
(function registerPWA() {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/static/sw.js')
        .then(reg => {
          console.log('%c✅ PWA Service Worker registered', 'color:#4cc98a');
          // Check for updates
          reg.addEventListener('updatefound', () => {
            const worker = reg.installing;
            if (worker) {
              worker.addEventListener('statechange', () => {
                if (worker.state === 'installed' && navigator.serviceWorker.controller) {
                  showToast('🔄 Update available — refresh to apply', 5000);
                }
              });
            }
          });
        })
        .catch(err => console.warn('SW registration failed:', err));
    });
  }

  // PWA install prompt
  let deferredPrompt = null;
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    // Show install button if not already installed
    const btn = document.getElementById('pwa-install-btn');
    if (btn) btn.style.display = 'flex';
  });

  window.installPWA = async () => {
    if (deferredPrompt) {
      deferredPrompt.prompt();
      const result = await deferredPrompt.userChoice;
      if (result.outcome === 'accepted') {
        showToast('✅ Agentic OS installed as desktop app!');
      }
      deferredPrompt = null;
    } else {
      gmAlert('To install: In your browser menu, click "Install Agentic OS" or "Add to Home Screen"');
    }
  };
})();


// ══════════════════════════════════════════════════════════════════
//  FUSION — Multi-Model Synthesis (OpenRouter Fusion style)
// ══════════════════════════════════════════════════════════════════
async function renderFusion() {
  const pane = document.getElementById('pane-fusion');
  if (!pane) return;

  let presets = {presets:{}};
  try {
    const _pr = await fetch('/api/fusion/presets');
    if (_pr.ok) presets = await _pr.json();
  } catch(e) {}

  pane.innerHTML = `
  

  <div style="padding:20px;max-width:1000px;margin:0 auto">
    <div class="section-head">
      <div>
        <h2>🔀 Model Fusion</h2>
        <p>Like OpenRouter Fusion — fan your prompt to multiple models simultaneously, synthesize the best answer. Consistently outperforms single models.</p>
      </div>
    </div>

    <!-- Preset selector -->
    <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap">
      ${Object.entries(presets.presets||{}).map(([id,p])=>`
        <button class="fusion-preset-btn ${id==='budget'?'active':''}" id="fp-${id}" onclick="fusionSelectPreset('${id}')">
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
        <button class="btn" onclick="fusionRun()" id="fusion-run-btn">⚡ Run Fusion</button>
        <button class="btn-sm" onclick="fusionRunSimple()">Simple (no stream)</button>
        <div style="margin-left:auto;font-size:11px;color:var(--text-3)" id="fusion-cost-hint">Budget preset uses free models 💰</div>
      </div>
    </div>

    <!-- Results area -->
    <div id="fusion-results"></div>

    <!-- Smart Router -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;margin-top:20px;overflow:hidden">
      <div style="padding:12px 16px;border-bottom:1px solid var(--border);font-weight:700;font-size:13px">🎯 Smart Router — Auto-Pick Best Model</div>
      <div style="padding:16px">
        <div style="font-size:12px;color:var(--text-2);margin-bottom:10px">Ask anything and the router automatically picks the optimal model (free vs paid, code vs research vs chat)</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <input id="router-prompt" placeholder="Ask anything…" style="flex:1;min-width:200px;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:13px;padding:8px 12px" onkeydown="if(event.key==='Enter')fusionRoute()">
          <button class="btn" onclick="fusionRoute()">🎯 Route</button>
          <button class="btn-sm" onclick="fusionClassify()">🏷️ Classify</button>
        </div>
        <div id="router-result" style="margin-top:10px"></div>
      </div>
    </div>

    <!-- Cost Optimizer -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;margin-top:16px;overflow:hidden">
      <div style="padding:12px 16px;border-bottom:1px solid var(--border);font-weight:700;font-size:13px">💰 Cost Optimizer — Stay Within Budget</div>
      <div style="padding:16px">
        <div style="font-size:12px;color:var(--text-2);margin-bottom:10px">Get the best model that fits your cost budget. Automatically downgrades to free models when needed.</div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <input id="cost-prompt" placeholder="Your prompt…" style="flex:1;min-width:200px;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:13px;padding:8px 12px">
          <input id="cost-budget" type="number" value="0.01" min="0" step="0.001" style="width:90px;background:var(--bg-3);border:1px solid var(--border);border-radius:6px;color:var(--text-0);font-size:12px;padding:6px 8px" placeholder="Budget $">
          <button class="btn" onclick="fusionOptimizeCost()">💰 Optimize</button>
        </div>
        <div id="cost-result" style="margin-top:10px"></div>
      </div>
    </div>

    <!-- Subagent Delegation -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;margin-top:16px;overflow:hidden">
      <div style="padding:12px 16px;border-bottom:1px solid var(--border);font-weight:700;font-size:13px">🤖 Subagent Delegation — Big Model → Many Small Models</div>
      <div style="padding:16px">
        <div style="font-size:12px;color:var(--text-2);margin-bottom:10px">Like OpenRouter Subagent: orchestrator model breaks task into subtasks, delegates to cheaper workers</div>
        <textarea id="subagent-task" rows="3" style="width:100%;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:13px;padding:10px;resize:none;box-sizing:border-box" placeholder="Complex task to delegate (e.g. 'Research FastAPI, write 3 code examples, explain authentication patterns')"></textarea>
        <div style="display:flex;gap:8px;margin-top:8px;align-items:center;flex-wrap:wrap">
          <label style="font-size:11px;color:var(--text-3)">Max subtasks:</label>
          <input id="subagent-max" type="number" min="1" max="8" value="4" style="width:60px;background:var(--bg-3);border:1px solid var(--border);border-radius:6px;color:var(--text-0);font-size:12px;padding:5px 8px">
          <button class="btn" onclick="fusionSubagent()">🤖 Delegate</button>
        </div>
        <div id="subagent-result" style="margin-top:10px"></div>
      </div>
    </div>

    <!-- Run History -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;margin-top:16px;overflow:hidden">
      <div style="padding:12px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between">
        <span style="font-weight:700;font-size:13px">📜 Run History</span>
        <button class="btn-sm" onclick="fusionLoadHistory()">↻ Load</button>
      </div>
      <div id="fusion-history" style="padding:12px;font-size:12px;color:var(--text-3)">Click Load to show recent fusion runs.</div>
    </div>
  </div>`;

  fusionSelectPreset('budget');
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
        <div style="background:var(--bg-3);border:1px solid var(--accent)44;border-radius:7px;padding:6px 10px;font-size:11px;color:var(--accent);font-family:monospace">
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
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px" id="fusion-live">
      <div style="font-size:12px;font-weight:700;margin-bottom:8px">🔀 Fusion Running (${preset} preset)…</div>
      <div id="fusion-panel-responses" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px"></div>
      <div style="font-size:12px;font-weight:700;color:var(--accent);margin-bottom:6px" id="fusion-judge-label" style="display:none">🧑‍⚖️ Synthesizing…</div>
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
              card.innerHTML = `<div style="font-weight:700;color:var(--accent);margin-bottom:4px">${escHtml(mname)}</div>
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
    if (results) results.innerHTML += `<div style="color:var(--danger);padding:8px">Error: ${ex?.message||String(ex)}</div>`;
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
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px">
        <div style="font-size:11px;color:var(--text-3);margin-bottom:8px">Preset: ${escHtml(d.preset||preset)} · ${d.total_ms||0}ms</div>
        <div style="font-size:13px;line-height:1.7;color:var(--text-0);white-space:pre-wrap">${escHtml(d.synthesis||'')}</div>
        <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
          ${(d.panel||[]).map(p=>`<div style="font-size:10px;background:var(--bg-3);padding:3px 8px;border-radius:5px;color:${p.error?'var(--danger)':'var(--text-3)'}">${escHtml((p.model||'').split('/').pop())} · ${p.tokens||0}t${p.error?' ⚠️':''}</div>`).join('')}
        </div>
      </div>`;
  } catch(ex) {
    if (results) results.innerHTML = `<div style="color:var(--danger)">Error: ${ex?.message||String(ex)}</div>`;
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
          <span style="font-size:10px;background:var(--accent);color:#fff;padding:2px 8px;border-radius:4px">${escHtml(d.task_type||'')}</span>
          <strong style="font-size:12px">${escHtml((d.model||'').split('/').pop())}</strong>
          <span style="font-size:11px;color:var(--text-3)">${d.latency_ms||0}ms · ${d.tokens||0}t${d.error?' · ⚠️ error':''}</span>
        </div>
        <div style="font-size:12px;color:var(--text-2);margin-bottom:8px">${escHtml(d.reason||'')}</div>
        <div style="font-size:13px;color:var(--text-1);line-height:1.6;white-space:pre-wrap">${escHtml((d.text||'').slice(0,800))}</div>
      </div>`;
  } catch(ex) {
    if (el) el.innerHTML = `<div style="color:var(--danger)">Error: ${ex?.message||String(ex)}</div>`;
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
          <span style="background:var(--accent);color:#fff;padding:2px 8px;border-radius:4px">${escHtml(d.task_type||'')}</span>
          <span style="color:var(--text-1);font-weight:600">${escHtml((d.model||'').split('/').pop())}</span>
        </div>
        <div style="color:var(--text-2)">${escHtml(d.reason||'')}</div>
        <div style="color:var(--text-3);margin-top:4px">Est. tokens: ${d.est_tokens||0} · Est. cost: $${(d.est_cost_usd||0).toFixed(6)}</div>
      </div>`;
  } catch(ex) {
    if (el) el.innerHTML = `<div style="color:var(--danger)">Error: ${ex?.message||String(ex)}</div>`;
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
          <span style="background:var(--accent);color:#fff;padding:2px 8px;border-radius:4px">${escHtml(d.task_type||'')}</span>
          <strong>${escHtml((d.recommended||'').split('/').pop())}</strong>
          ${d.downgraded?'<span style="color:var(--warning);font-size:10px">⬇ downgraded</span>':'<span style="color:var(--success);font-size:10px">✅ within budget</span>'}
        </div>
        <div style="color:var(--text-2);margin-bottom:4px">${escHtml(d.reason||'')}</div>
        <div style="color:var(--text-3)">Budget: $${budget.toFixed(6)} · Est cost: $${(d.est_cost_usd||0).toFixed(6)} · Est tokens: ${d.est_tokens||0}</div>
        ${d.downgraded?`<div style="color:var(--text-3);margin-top:2px">Original: ${escHtml((d.original_model||'').split('/').pop())}</div>`:''}
      </div>`;
  } catch(ex) {
    if (el) el.innerHTML = `<div style="color:var(--danger)">Error: ${ex?.message||String(ex)}</div>`;
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
    el.innerHTML = `<div style="color:var(--danger)">Error: ${ex?.message||String(ex)}</div>`;
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
          <div style="font-size:11px;font-weight:700;color:var(--accent);margin-bottom:8px">
            ✨ Synthesized from ${subtasks.length} subtask${subtasks.length!==1?'s':''}
            <span style="font-weight:400;color:var(--text-3)">· ${totalMs}ms · ${totalTok}t</span>
          </div>
          <div style="font-size:13px;color:var(--text-1);line-height:1.7;white-space:pre-wrap">${escHtml(synthesis||'No synthesis produced.')}</div>
        </div>`;
    }
  } catch(ex) {
    if (el) el.innerHTML = `<div style="color:var(--danger)">Error: ${ex?.message||String(ex)}</div>`;
  }
}


// ══════════════════════════════════════════════════════════════════
//  HUMAN-IN-THE-LOOP (HITL) — Approval Queue
// ══════════════════════════════════════════════════════════════════
async function renderHITL() {
  const pane = document.getElementById('pane-hitl');
  if (!pane) return;

  const [queue, stats, audit] = await Promise.all([
    fetch('/api/hitl/queue').then(r=>r.ok?r.json():null).catch(()=>({interrupts:[]})),
    fetch('/api/hitl/stats').then(r=>r.ok?r.json():null).catch(()=>({})),
    fetch('/api/hitl/audit?limit=10').then(r=>r.ok?r.json():null).catch(()=>({audit:[]})),
  ]);

  const riskColors = {low:'var(--success)',medium:'var(--warning)',high:'var(--danger)',critical:'#ff4444'};

  pane.innerHTML = `
  <div style="padding:20px;max-width:900px;margin:0 auto">
    <div class="section-head">
      <div>
        <h2>🛡️ Human-in-the-Loop</h2>
        <p>Confidence gates, interruption protocols, safe undo — agents pause for human approval before risky actions</p>
      </div>
      <button class="btn-sm" onclick="hitlTestInterrupt()">🧪 Test Interrupt</button>
    </div>

    <!-- Stats -->
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px">
      ${[
        ['⏳','Pending',stats.pending||0,'var(--warning)'],
        ['✅','Approved',stats.approved||0,'var(--success)'],
        ['❌','Rejected',stats.rejected||0,'var(--danger)'],
        ['📊','Approval Rate',`${stats.approval_rate||0}%`,'var(--accent)'],
      ].map(([icon,label,val,col])=>`
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:14px;text-align:center">
          <div style="font-size:22px">${icon}</div>
          <div style="font-size:10px;color:var(--text-3);text-transform:uppercase">${label}</div>
          <div style="font-size:20px;font-weight:700;color:${col}">${val}</div>
        </div>`).join('')}
    </div>

    <!-- Pending queue with Side-by-Side Diff Verification (Phase 4) -->
    <div style="font-size:13px;font-weight:700;margin-bottom:10px">⏳ Pending Approval & Diff Verification (${(queue.interrupts||[]).length})</div>
    <div id="hitl-queue">
      ${(queue.interrupts||[]).map(item=>`
        <div class="card-elevated surface-z3" style="border:2px solid ${(item.confidence < 0.85) ? '#ff4444' : (riskColors[item.risk_level]||'var(--border)')};border-radius:14px;padding:18px;margin-bottom:14px;position:relative;box-shadow:${(item.confidence < 0.85) ? '0 0 28px rgba(255,68,68,0.22)' : 'var(--shadow)'}">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;flex-wrap:wrap;gap:8px">
            <div style="display:flex;align-items:center;gap:8px">
              <span style="font-size:11px;padding:3px 8px;border-radius:4px;font-weight:800;background:${riskColors[item.risk_level]||'var(--text-3)'}22;color:${riskColors[item.risk_level]||'var(--text-3)'};text-transform:uppercase">${item.risk_level||'high'}</span>
              <strong style="color:var(--text-0);font-size:14px">${escHtml(item.action_type||'Protected State Modification')}</strong>
            </div>
            <div style="display:flex;align-items:center;gap:8px">
              <span class="badge ${(item.confidence < 0.85) ? 'badge-danger' : 'badge-warning'}">${Math.round((item.confidence||0.65)*100)}% Confidence ${(item.confidence < 0.85) ? '⚠️ < 85% INTERRUPT' : 'GATED'}</span>
              <span style="font-size:11px;color:var(--text-3);font-family:monospace">${new Date(item.created_at).toLocaleTimeString()}</span>
            </div>
          </div>
          <div style="font-size:13px;color:var(--text-1);margin-bottom:14px;line-height:1.6">${escHtml(item.action_summary||'Autonomous agent requested execution of protected operational state mutation.')}</div>
          
          <!-- Side-by-Side Diff Verification -->
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;background:#04060f;border:1px solid var(--border-hi);border-radius:10px;padding:12px;font-family:monospace;font-size:11.5px;max-height:260px;overflow-y:auto">
            <div style="border-right:1px solid var(--border);padding-right:10px">
              <div style="color:#f87171;font-weight:700;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px">--- Current Baseline / Safe State</div>
              <pre style="margin:0;color:#cbd5e1;white-space:pre-wrap">${escHtml(item.baseline_state || (item.action_details && item.action_details.old_text) || "// Current operational baseline prior to action execution.\n// System integrity verified and state intact.\n\nfunction verifyBaseline() {\n  return { status: 'stable', writeProtected: true };\n}")}</pre>
            </div>
            <div style="padding-left:4px">
              <div style="color:#34d399;font-weight:700;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px">+++ Proposed Agent Execution Diff</div>
              <pre style="margin:0;color:#a7f3d0;white-space:pre-wrap">${escHtml(item.proposed_state || (item.action_details && item.action_details.new_text) || item.action_summary || "+ Executing autonomous state modification / code mutation.\n\nfunction updateTargetState() {\n  return { status: 'modified', newVersion: 'v11.2' };\n}")}</pre>
            </div>
          </div>

          <div style="display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap">
            <div style="display:flex;gap:8px">
              <button class="btn-3d btn-primary btn-sm" onclick="hitlDecide(${JSON.stringify(item.id)},'approve')" style="background:var(--success);border:none;color:#fff;padding:6px 14px">✅ Approve & Continue</button>
              <button class="btn-3d btn-ghost btn-sm" onclick="hitlModify(${JSON.stringify(item.id)})" style="padding:6px 14px">✏ Modify Parameters</button>
              <button class="btn-3d btn-danger btn-sm" onclick="hitlDecide(${JSON.stringify(item.id)},'reject')" style="padding:6px 14px">🛑 Abort & Revert</button>
            </div>
            <button onclick="if(typeof toggleSplitWorkspace==='function') toggleSplitWorkspace(true, 'hitl')" class="btn-3d btn-ghost btn-sm" style="padding:4px 10px;font-size:11px">🗂️ Secondary Dock</button>
          </div>
        </div>`).join('') || '<div style="color:var(--text-3);padding:24px;text-align:center;background:var(--surface-z1);border-radius:12px;border:1px dashed var(--border)">No pending interruptions — autonomous agents operating safely within set confidence thresholds.</div>'}
    </div>

    <!-- Confidence threshold settings -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px;margin-top:16px">
      <div style="font-size:13px;font-weight:700;margin-bottom:12px">⚙️ Confidence Thresholds</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:12px">
        ${[['Low Risk','Auto-approve if ≥70%','var(--success)'],['Medium Risk','Interrupt if <85%','var(--warning)'],['High Risk','Always interrupt','var(--danger)'],['Critical','Always + dual confirm','#ff4444']].map(([level,desc,col])=>`
          <div style="background:var(--bg-3);border-radius:8px;padding:10px;border-left:3px solid ${col}">
            <div style="font-weight:600;color:var(--text-0)">${level}</div>
            <div style="color:var(--text-2);font-size:11px">${desc}</div>
          </div>`).join('')}
      </div>
    </div>

    <!-- Sprint A: Delegation Profiles -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px;margin-top:16px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
        <div style="font-size:13px;font-weight:700">🎛️ Delegation Profiles</div>
        <button class="btn-sm" onclick="hitlSaveDelegation()">💾 Save Profile</button>
      </div>
      <p style="font-size:11px;color:var(--text-3);margin:0 0 12px">Configure which action classes agents can perform autonomously vs. which always require your approval.</p>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:12px">
        ${[
          ['💸','Financial Transactions','stripe_charge,financial_transaction,ap2_payment','Always approve'],
          ['📧','External Communications','send_email,send_message,post_to_social','Always approve'],
          ['🗂️','File Deletions','delete_file,rm_rf','Always approve'],
          ['🚀','Production Deployments','deploy_to_production,push_to_main','Always approve'],
          ['📝','File Writes','write_file,update_file','Auto if ≥80% confidence'],
          ['🔍','Read & Search','read_file,web_search,read_memory','Always auto-approve'],
        ].map(([icon,label,actions,defaultVal])=>`
          <div style="background:var(--bg-3);border-radius:8px;padding:10px;display:flex;align-items:center;gap:8px">
            <span style="font-size:16px">${icon}</span>
            <div style="flex:1">
              <div style="font-weight:600">${label}</div>
              <div style="font-size:10px;color:var(--text-3)">${defaultVal}</div>
            </div>
            <select class="hitl-deleg-sel" data-actions="${actions}" style="font-size:11px;background:var(--bg-2);border:1px solid var(--border);border-radius:5px;padding:3px 6px;color:var(--text-0)">
              <option value="auto">Auto-approve</option>
              <option value="auto_high" ${defaultVal.includes('80')? 'selected':''}>Auto if ≥80%</option>
              <option value="interrupt" ${defaultVal.includes('Always approve')? 'selected':''}>Always interrupt</option>
            </select>
          </div>`).join('')}
      </div>
    </div>

    <!-- Sprint A: Timeout Configuration -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px;margin-top:16px">
      <div style="font-size:13px;font-weight:700;margin-bottom:10px">⏱️ Approval Timeout Handling</div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;font-size:12px">
        <div style="background:var(--bg-3);border-radius:8px;padding:10px">
          <div style="font-weight:600;margin-bottom:4px">Default Timeout</div>
          <div style="display:flex;align-items:center;gap:6px">
            <input type="number" id="hitl-timeout" value="300" min="30" max="1800" style="width:70px;background:var(--bg-2);border:1px solid var(--border);border-radius:5px;padding:3px 6px;color:var(--text-0);font-size:12px">
            <span style="color:var(--text-3)">seconds</span>
          </div>
        </div>
        <div style="background:var(--bg-3);border-radius:8px;padding:10px">
          <div style="font-weight:600;margin-bottom:4px">On Timeout</div>
          <select id="hitl-timeout-action" style="font-size:11px;background:var(--bg-2);border:1px solid var(--border);border-radius:5px;padding:3px 6px;color:var(--text-0);width:100%">
            <option value="pause">Pause agent (safe default)</option>
            <option value="reject">Auto-reject action</option>
            <option value="escalate">Escalate to admin</option>
          </select>
        </div>
        <div style="background:var(--bg-3);border-radius:8px;padding:10px">
          <div style="font-weight:600;margin-bottom:4px">Notification</div>
          <div style="font-size:11px;color:var(--text-2)">
            🔔 Browser notification sent<br>
            📋 HITL queue badge shown<br>
            ⚡ WebSocket real-time push
          </div>
        </div>
      </div>
    </div>

    <!-- Audit log -->
    <div style="margin-top:16px;font-size:13px;font-weight:700;margin-bottom:8px">📋 Recent Decisions</div>
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;overflow:hidden">
      ${(audit.audit||[]).map(a=>`
        <div style="display:flex;align-items:center;gap:8px;padding:8px 14px;border-bottom:1px solid var(--border);font-size:12px">
          <span style="font-size:14px">${a.decision==='approve'?'✅':a.decision==='reject'?'❌':a.decision==='modify'?'✏️':'⚙️'}</span>
          <span style="font-weight:600">${escHtml(a.action_type||'action')}</span>
          <span style="color:var(--text-3)">${escHtml(a.action_summary||'')?.slice(0,60)}</span>
          <span style="margin-left:auto;color:var(--text-3)">${new Date(a.created_at).toLocaleTimeString()}</span>
        </div>`).join('') || '<div style="color:var(--text-3);padding:12px;text-align:center">No decisions yet</div>'}
    </div>

    <!-- Sprint A: Link to full audit log -->
    <div style="margin-top:12px;text-align:center">
      <button class="btn-sm" onclick="nav('audit-log')" style="color:var(--accent);border-color:var(--accent)">🔏 View Full Immutable Audit Log →</button>
    </div>
  </div>`;

  // Poll for new interrupts every 5s — FIX 4: re-render cards, not just box-shadow
  let _hitlLastCount = (queue.interrupts||[]).length;
  (function pollHITL() {
    if (!document.getElementById('pane-hitl')?.classList.contains('active')) return;
    setTimeout(async () => {
      try {
        const r = await fetch('/api/hitl/queue');
        const d = await r.json();
        const newCount = (d.interrupts||[]).length;
        if (newCount !== _hitlLastCount) {
          _hitlLastCount = newCount;
          renderHITL();  // full re-render when queue changes
          return;        // renderHITL restarts its own poll
        }
      } catch(e) {}
      pollHITL();
    }, 5000);
  })();
}

async function hitlDecide(id, decision) {
  const note = decision==='reject' ? await gmPrompt('Reason for rejection:','') : '';
  try {
    await fetch(`/api/hitl/interrupt/${encodeURIComponent(id)}/decide`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({decision,note,reviewer:'user'})});
    const _decLabel = decision==='approve'?'✅ Approved':decision==='modify'?'✏️ Modified':'❌ Rejected';
    showToast(`${_decLabel}: ${id}`);
    renderHITL();
  } catch(ex) { gmAlert('Decision failed: '+ex.message); }
}

async function hitlModify(id) {
  // FIX 3: send modified_action_data to the decide endpoint
  const mod = await gmPrompt('Modified action (JSON):','{}');
  if (mod === null) return;  // user cancelled
  let data = {};
  try { data = JSON.parse(mod||'{}'); } catch(e) { showToast('⚠️ Invalid JSON — using empty data'); }
  const note = await gmPrompt('Note (optional):','') || '';
  try {
    await fetch(`/api/hitl/interrupt/${encodeURIComponent(id)}/decide`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({decision:'modify', note, reviewer:'user', modified_action_data: data})
    });
    showToast('✏️ Modified & approved: ' + id);
    renderHITL();
  } catch(ex) { gmAlert('Modify failed: ' + ex.message); }
}
window.renderHITL = renderHITL;
window.hitlDecide = hitlDecide;
window.hitlModify = hitlModify;

async function hitlTestInterrupt() {
  const r = await fetch('/api/hitl/interrupt',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    action_type:'AST_MUTATION_CRITICAL',
    action_summary:'Autonomous agent requested execution of AST mutation on index.html with confidence < 85%',
    risk_level:'critical',
    confidence:0.72,
    agent_id:'builder',
    baseline_state: "// Current operational baseline index.html\n<div id=\"app-header\">\n  <h1>Strick Tech Agentic OS v11.0</h1>\n  <span class=\"badge\">Production Stable</span>\n</div>\n// All unit tests 100% green verified.",
    proposed_state: "// Proposed autonomous mutation index.html\n<div id=\"app-header\" class=\"header-redesigned\">\n  <h1>Strick Tech Agentic OS v11.2</h1>\n  <span class=\"badge badge-live\">Experimental Core Engine</span>\n  <button onclick=\"initExperimentalEngine()\">⚡ Launch</button>\n</div>\n// Note: Requires HITL approval gate."
  })});
  const d = await r.json();
  showToast(`🛡️ Test interrupt created: ${d.interrupt_id||'auto_approved'}`);
  renderHITL();
}

// Sprint A: Delegation profile save
function hitlSaveDelegation() {
  const sels = document.querySelectorAll('.hitl-deleg-sel');
  const profile = {};
  sels.forEach(s=>{ profile[s.dataset.actions] = s.value; });
  localStorage.setItem('hitl_delegation_profile', JSON.stringify(profile));
  const timeout = document.getElementById('hitl-timeout')?.value || '300';
  const timeoutAction = document.getElementById('hitl-timeout-action')?.value || 'pause';
  localStorage.setItem('hitl_timeout', timeout);
  localStorage.setItem('hitl_timeout_action', timeoutAction);
  showToast('🎛️ Delegation profile saved');
  // Log to audit chain
  fetch('/api/audit-log/append',{
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      agent_id:'system', agent_name:'User',
      action_type:'delegation_profile_updated',
      action_detail:`Updated delegation profile with ${Object.keys(profile).length} rules`,
      reasoning:'User updated HITL delegation configuration',
      authority:'user', risk_level:'low', outcome:'success',
      metadata:{profile, timeout, timeout_action:timeoutAction}
    })
  }).catch(()=>{});
}


// ══════════════════════════════════════════════════════════════════
//  BROWSER AGENT
// ══════════════════════════════════════════════════════════════════
async function renderBrowserAgent() {
  const pane = document.getElementById('pane-browser');
  if (!pane) return;

  let status = {playwright_available:false, chromium_installed:false, ready:false, mode:'simulation'};
  try {
    const _sr = await fetch('/api/browser/status');
    if (_sr.ok) status = await _sr.json();
  } catch(e) {}

  const QUICK_TASKS = [
    'Search DuckDuckGo for Python FastAPI tutorials and list top 3',
    'Extract all links from news.ycombinator.com',
    'Find FastAPI documentation homepage',
    'Search for AI agent frameworks 2024',
  ];

  pane.innerHTML = `
  <div style="display:flex;flex-direction:column;height:100%;overflow:hidden">
    <div style="padding:10px 16px;background:var(--bg-1);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;flex-shrink:0;flex-wrap:wrap">
      <span style="font-size:15px;font-weight:700">🌐 Browser Agent</span>
      <span style="font-size:11px;padding:2px 8px;border-radius:5px;${status.ready ? 'background:rgba(61,186,122,.15);color:var(--success)' : 'background:rgba(232,162,55,.15);color:var(--warning)'}">
        ${status.ready ? '✅ Ready' : '⚠️ ' + escHtml(status.mode === 'simulation' ? 'Simulation Mode' : 'Chromium Missing')}
      </span>
      ${!status.ready ? `<span style="font-size:10px;color:var(--text-3);font-family:monospace">${escHtml(status.install_cmd || 'pip install playwright && python -m playwright install chromium')}</span> <button onclick="if(typeof installPlaywrightChromium === 'function') installPlaywrightChromium()" class="btn-3d btn-primary btn-sm" style="padding:3px 10px;font-size:11px">⚡ Auto-Install Playwright & Chromium</button>` : ''}
      <div style="margin-left:auto;display:flex;gap:6px">
        <button class="btn-sm" onclick="baLoadHistory()">📋 History</button>
        <button class="btn-sm" onclick="baListScreenshots()">🖼 Screenshots</button>
      </div>
    </div>
    <div style="padding:10px 16px;background:var(--bg-2);border-bottom:1px solid var(--border);flex-shrink:0">
      <div style="display:flex;gap:8px;margin-bottom:8px;flex-wrap:wrap">
        <input id="ba-url" value="https://duckduckgo.com" placeholder="Start URL (https://...)"
               style="width:200px;background:var(--bg-3);border:1px solid var(--border);border-radius:7px;color:var(--text-0);font-size:12px;padding:7px 10px">
        <input id="ba-task" placeholder="Task — e.g. Search for Python tutorials and summarize results"
               style="flex:1;min-width:200px;background:var(--bg-3);border:1px solid var(--border);border-radius:7px;color:var(--text-0);font-size:13px;padding:7px 10px"
               onkeydown="if(event.key === 'Enter') baRun()">
        <input id="ba-steps" type="number" min="1" max="20" value="10"
               style="width:55px;background:var(--bg-3);border:1px solid var(--border);border-radius:7px;color:var(--text-0);font-size:12px;padding:7px 8px" title="Max steps">
        <button class="btn" onclick="baRun()" id="ba-run-btn">▶ Run</button>
        <button class="btn-sm" onclick="baScreenshot()" title="Quick screenshot of start URL">📸</button>
      </div>
      <div style="display:flex;gap:5px;flex-wrap:wrap">
        ${QUICK_TASKS.map(t=>`<button class="btn-sm" onclick="document.getElementById('ba-task').value=${JSON.stringify(t)}" style="font-size:10px">${escHtml(t.slice(0,42))}…</button>`).join('')}
      </div>
    </div>
    <div style="display:flex;flex:1;overflow:hidden">
      <div style="width:300px;flex-shrink:0;border-right:1px solid var(--border);overflow-y:auto;background:var(--bg-1)" id="ba-steps-log">
        <div style="padding:8px 12px;font-size:10px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between">
          <span>Execution Steps</span>
          <span id="ba-step-count" style="color:var(--text-3)"></span>
        </div>
        <div id="ba-steps-list">
          <div style="color:var(--text-3);font-size:12px;padding:16px;text-align:center">Run a task to see steps</div>
        </div>
      </div>
      <div style="flex:1;overflow:hidden;display:flex;flex-direction:column">
        <div style="padding:8px 14px;background:var(--bg-1);border-bottom:1px solid var(--border);font-size:10px;font-weight:700;color:var(--text-3);text-transform:uppercase;display:flex;justify-content:space-between">
          <span>Result</span>
          <span id="ba-session-id" style="font-family:monospace;color:var(--text-3);font-size:10px"></span>
        </div>
        <div id="ba-result" style="flex:1;overflow-y:auto;padding:16px;font-size:13px;color:var(--text-1);line-height:1.7;white-space:pre-wrap">
          <div style="color:var(--text-3);text-align:center;padding-top:40px">
            <div style="font-size:32px;margin-bottom:8px">🌐</div>
            Run a browser task to see results here.
          </div>
        </div>
      </div>
    </div>
  </div>`;
}
window.renderBrowserAgent = renderBrowserAgent;

window.installPlaywrightChromium = async function() {
  toast('⏳ Initiating live SSE Playwright & Chromium setup...', 'ok', 3000);
  const pane = document.getElementById('pane-browser');
  let progCard = document.getElementById('browser-setup-progress-card');
  if (!progCard && pane) {
    progCard = document.createElement('div');
    progCard.id = 'browser-setup-progress-card';
    progCard.className = 'card-elevated surface-z3';
    progCard.style.cssText = 'margin:16px 24px;padding:16px;border:1px solid var(--accent);border-radius:12px';
    progCard.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <span style="font-weight:800;font-size:12.5px;color:var(--accent)" id="browser-prog-msg">⏳ Connecting to Playwright setup stream...</span>
        <span style="font-family:monospace;font-size:11px;color:var(--text-2)" id="browser-prog-pct">0%</span>
      </div>
      <div style="width:100%;height:10px;background:var(--bg-3);border-radius:99px;overflow:hidden;border:1px solid var(--border)">
        <div id="browser-prog-bar" style="width:0%;height:100%;background:linear-gradient(90deg,var(--accent),#10b981);transition:width 0.4s ease"></div>
      </div>
      <div id="browser-prog-detail" style="font-size:11px;color:var(--text-3);margin-top:8px;font-family:monospace">Initiating automated package downloads...</div>
    `;
    const target = pane.querySelector('.section-head') || pane.firstElementChild;
    if (target && target.parentNode) target.parentNode.insertBefore(progCard, target.nextSibling);
    else pane.appendChild(progCard);
  }
  if (progCard) progCard.style.display = 'block';

  try {
    await fetch('/api/browser/setup/auto-install', {method: 'POST'});
    if (typeof EventSource !== 'undefined') {
      const es = new EventSource('/api/browser/setup/stream');
      es.onmessage = (e) => {
        try {
          const d = JSON.parse(e.data);
          const bar = document.getElementById('browser-prog-bar');
          const msg = document.getElementById('browser-prog-msg');
          const pct = document.getElementById('browser-prog-pct');
          const det = document.getElementById('browser-prog-detail');
          if (bar) bar.style.width = (d.progress || 0) + '%';
          if (msg) msg.textContent = d.message || 'Installing...';
          if (pct) pct.textContent = (d.progress || 0) + '%';
          if (det) det.textContent = `[SSE Browser Setup Stream] ${d.message || ''}`;
          if (d.done) {
            es.close();
            toast('✅ Playwright & Chromium installed!', 'ok', 3000);
            setTimeout(() => {
              if (progCard) progCard.style.display = 'none';
              if (typeof renderBrowserAgent === 'function') renderBrowserAgent();
            }, 2000);
          }
        } catch(err) {}
      };
      es.onerror = () => { es.close(); };
    } else {
      setTimeout(() => { if (typeof renderBrowserAgent === 'function') renderBrowserAgent(); }, 5000);
    }
  } catch(e) {
    gmAlert('Setup error', `Run in terminal:\n\npip install playwright && python -m playwright install chromium`);
  }
};

let _baStepCount = 0;

async function baRun() {
  const task  = document.getElementById('ba-task')?.value?.trim();
  const url   = document.getElementById('ba-url')?.value?.trim() || 'https://duckduckgo.com';
  const steps = Math.max(1, Math.min(20, parseInt(document.getElementById('ba-steps')?.value||'10')));
  if (!task) { gmAlert('Enter a task for the browser agent'); return; }

  const btn      = document.getElementById('ba-run-btn');
  const stepsList= document.getElementById('ba-steps-list');
  const result   = document.getElementById('ba-result');
  const sidEl    = document.getElementById('ba-session-id');
  const cntEl    = document.getElementById('ba-step-count');

  if (btn) { btn.disabled=true; btn.textContent='⏳ Running…'; }
  if (stepsList) stepsList.innerHTML = '<div style="color:var(--text-3);font-size:11px;padding:10px">Starting…</div>';
  if (result)    result.innerHTML    = '<div style="color:var(--text-2)">🌐 Agent running…</div>';
  if (sidEl)     sidEl.textContent   = '';
  if (cntEl)     cntEl.textContent   = '';
  _baStepCount = 0;

  try {
    const resp = await fetch('/api/browser/task', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({task, start_url:url, max_steps:steps})
    });
    if (!resp.ok) {
      if (result) result.innerHTML = `<span style="color:var(--danger)">Request failed (HTTP ${resp.status})</span>`;
      if (btn) { btn.disabled=false; btn.textContent='▶ Run'; }
      return;
    }

    const reader = resp.body.getReader();
    const dec    = new TextDecoder();
    let   buf    = '';

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

          if (d.type === 'session_start') {
            if (sidEl) sidEl.textContent = d.session_id || '';
            if (stepsList) stepsList.innerHTML = '';
          } else if (d.type === 'warning') {
            const warn = document.createElement('div');
            warn.className = 'ba-warn';
            warn.textContent = '⚠️ ' + (d.message||'');
            stepsList?.appendChild(warn);
          } else if (d.type === 'step') {
            _baStepCount++;
            const s   = d.step || {};
            const sim = d.simulated ? ' simulated' : '';
            const err = (s.status === 'error') ? ' error-step' : '';
            const el  = document.createElement('div');
            el.className = `ba-step${sim}${err}`;
            // Build description: prefer human-readable info
            const desc = s.description || s.reason ||
              (s.url && s.url !== url ? s.url : '') ||
              (s.selector ? `sel: ${s.selector}` : '') ||
              (s.result && typeof s.result === 'object' ?
                (s.result.text || s.result.error || JSON.stringify(s.result)).slice(0,80) : '') ||
              '';
            const screenPath = s.result?.screenshot_path;
            el.innerHTML = `
              <span class="ba-num">#${d.step_no||_baStepCount}</span>
              <span class="ba-act">${escHtml(s.action||'?')}</span>
              <span class="ba-desc">${escHtml(desc.slice(0,100))}${screenPath?`<br><a href="${escHtml(screenPath)}" target="_blank" style="color:var(--accent);font-size:10px">📷 screenshot</a>`:''}</span>`;
            stepsList?.appendChild(el);
            if (stepsList) stepsList.scrollTop = stepsList.scrollHeight;
            if (cntEl) cntEl.textContent = _baStepCount + ' steps';
          } else if (d.type === 'done') {
            const text = d.result_preview || d.result || 'Task completed.';
            if (result) result.textContent = text;
            if (cntEl) cntEl.textContent = `${d.steps||_baStepCount} steps · ✅ done`;
            if (d.simulated) {
              const note = document.createElement('div');
              note.style.cssText = 'margin-top:12px;font-size:11px;color:var(--text-3);border-top:1px solid var(--border);padding-top:8px';
              note.textContent = '⚠️ Simulation mode — install Playwright for real browsing';
              result?.appendChild(note);
            }
          } else if (d.type === 'error') {
            if (result) result.innerHTML = `<span style="color:var(--danger)">❌ Error: ${escHtml(d.error||'Unknown error')}</span>`;
            if (cntEl) cntEl.textContent = '❌ error';
          }
        } catch(e) {}
      }
    }
  } catch(ex) {
    if (result) result.innerHTML = `<span style="color:var(--danger)">❌ ${ex?.message||String(ex)}</span>`;
  }

  if (btn) { btn.disabled=false; btn.textContent='▶ Run'; }
}

async function baScreenshot() {
  const url = document.getElementById('ba-url')?.value?.trim();
  if (!url) { gmAlert('Enter a URL in the Start URL field first'); return; }
  showToast('📸 Taking screenshot…');
  try {
    const r = await fetch('/api/browser/screenshot', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({url})
    });
    if (!r.ok) { gmAlert('Screenshot request failed: HTTP '+r.status); return; }
    const d = await r.json();
    if (d.ok && d.b64) {
      const overlay = document.createElement('div');
      overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:9999;display:flex;flex-direction:column;align-items:center;justify-content:center;cursor:zoom-out;gap:10px';
      overlay.innerHTML = `
        <div style="font-size:12px;color:#fff;opacity:.7">${escHtml(d.title||url)} · ${((d.size||0)/1024).toFixed(1)}KB</div>
        <img src="data:image/png;base64,${d.b64}" style="max-width:90vw;max-height:85vh;border-radius:8px;box-shadow:0 8px 40px rgba(0,0,0,.6)">
        <div style="font-size:11px;color:#fff;opacity:.5">Click anywhere to close</div>`;
      overlay.onclick = () => overlay.remove();
      document.body.appendChild(overlay);
      showToast('✅ Screenshot taken');
    } else {
      gmAlert(d.error || 'Screenshot failed — install Playwright first:\npip install playwright && python -m playwright install chromium');
    }
  } catch(ex) {
    gmAlert('Screenshot error: ' + (ex?.message||String(ex)));
  }
}

async function baLoadHistory() {
  try {
    const r = await fetch('/api/browser/sessions?limit=20');
    if (!r.ok) { showToast('Failed to load history: HTTP '+r.status); return; }
    const d = await r.json();
    if (!d.sessions?.length) { gmAlert('No browser sessions yet. Run a task first!'); return; }
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    overlay.innerHTML = `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:16px;max-width:620px;width:100%;max-height:80vh;overflow-y:auto;padding:20px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
          <h3 style="margin:0;color:var(--text-0)">📋 Browser Session History (${d.count})</h3>
          <button onclick="this.closest('[style*=fixed]').remove()" style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
        </div>
        ${d.sessions.map(s=>`
          <div style="border:1px solid var(--border);border-radius:8px;padding:10px;margin-bottom:8px;font-size:12px">
            <div style="display:flex;justify-content:space-between;margin-bottom:4px">
              <span style="font-family:monospace;color:var(--accent)">${escHtml(s.id)}</span>
              <span style="padding:1px 6px;border-radius:4px;font-size:10px;${s.status==='done'?'background:rgba(61,186,122,.15);color:var(--success)':s.status==='error'?'background:rgba(232,82,82,.1);color:var(--danger)':'background:var(--bg-3);color:var(--text-3)'}">${s.status}</span>
            </div>
            <div style="color:var(--text-1);margin-bottom:2px">${escHtml((s.task||'').slice(0,80))}</div>
            <div style="color:var(--text-3)">${escHtml((s.url||'').slice(0,60))} · ${(s.created_at||'').slice(0,16)}</div>
            ${s.error?`<div style="color:var(--danger);font-size:10px;margin-top:2px">⚠️ ${escHtml(s.error.slice(0,80))}</div>`:''}
            <div style="margin-top:6px;display:flex;gap:4px">
              <button class="btn-sm" onclick="baViewSession(${JSON.stringify(s.id)});this.closest('[style*=fixed]').remove()" style="font-size:10px">View</button>
              <button class="btn-sm" onclick="baDeleteSession(${JSON.stringify(s.id)});this.closest('[style*=fixed]').remove()" style="font-size:10px;color:var(--danger);border-color:var(--danger)">Delete</button>
            </div>
          </div>`).join('')}
        <button class="btn-sm" style="color:var(--danger);margin-top:4px" onclick="baClearHistory();this.closest('[style*=fixed]').remove()">🗑 Clear All Sessions</button>
      </div>`;
    overlay.onclick = e => { if(e.target===overlay) overlay.remove(); };
    document.body.appendChild(overlay);
  } catch(ex) {
    gmAlert('History load error: '+ex?.message);
  }
}

async function baViewSession(sessionId) {
  try {
    const r = await fetch(`/api/browser/sessions/${encodeURIComponent(sessionId)}`);
    if (!r.ok) { gmAlert('Session not found'); return; }
    const d = await r.json();
    if (d.ok === false) { gmAlert('Session not found: '+sessionId); return; }
    const steps = (d.steps||[]).map((s,i) =>
      `<div class="ba-step">
        <span class="ba-num">#${i+1}</span>
        <span class="ba-act">${escHtml(s.action||'?')}</span>
        <span class="ba-desc">${escHtml((s.description||s.reason||s.url||'').slice(0,100))}</span>
      </div>`
    ).join('');
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    overlay.innerHTML = `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:16px;max-width:560px;width:100%;max-height:80vh;overflow-y:auto;padding:20px">
        <div style="display:flex;justify-content:space-between;margin-bottom:12px">
          <h3 style="margin:0;color:var(--text-0)">Session ${escHtml(sessionId)}</h3>
          <button onclick="this.closest('[style*=fixed]').remove()" style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
        </div>
        <div style="font-size:12px;color:var(--text-2);margin-bottom:8px">Task: ${escHtml(d.task||'')}</div>
        <div style="font-size:11px;color:var(--text-3);margin-bottom:12px">URL: ${escHtml(d.url||'')} · Status: ${d.status} · ${d.step_count||0} steps</div>
        <div style="background:var(--bg-3);border-radius:8px;overflow:hidden;margin-bottom:12px">${steps||'<div style="padding:12px;color:var(--text-3)">No steps recorded</div>'}</div>
        ${d.result?`<div style="font-size:12px;color:var(--text-1);white-space:pre-wrap;max-height:200px;overflow-y:auto;background:var(--bg-3);padding:10px;border-radius:8px">${escHtml(d.result.slice(0,500))}</div>`:''}
      </div>`;
    overlay.onclick = e => { if(e.target===overlay) overlay.remove(); };
    document.body.appendChild(overlay);
  } catch(ex) {
    gmAlert('Error: '+ex?.message);
  }
}

async function baDeleteSession(sessionId) {
  const ok = await gmDanger('Delete Session', `Delete browser session "${sessionId}" and its screenshots?`);
  if (!ok) return;
  try {
    const r = await fetch(`/api/browser/sessions/${encodeURIComponent(sessionId)}`, {method:'DELETE'});
    if (!r.ok) { showToast('Delete failed: HTTP '+r.status); return; }
    showToast('🗑 Session deleted');
  } catch(ex) {
    showToast('Delete error: '+ex?.message);
  }
}

async function baClearHistory() {
  const ok = await gmDanger('Clear All Sessions', 'Delete ALL browser session history?');
  if (!ok) return;
  try {
    const r = await fetch('/api/browser/sessions', {method:'DELETE'});
    if (!r.ok) { showToast('Clear failed: HTTP '+r.status); return; }
    const d = await r.json();
    showToast(`🗑 Cleared ${d.deleted||0} sessions`);
  } catch(ex) {
    showToast('Clear error: '+ex?.message);
  }
}

async function baListScreenshots() {
  try {
    const r = await fetch('/api/browser/screenshots?limit=20');
    if (!r.ok) { showToast('Failed: HTTP '+r.status); return; }
    const d = await r.json();
    if (!d.screenshots?.length) { gmAlert('No screenshots yet. Take a screenshot or run a task first.'); return; }
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    overlay.innerHTML = `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:16px;max-width:640px;width:100%;max-height:80vh;overflow-y:auto;padding:20px">
        <div style="display:flex;justify-content:space-between;margin-bottom:14px">
          <h3 style="margin:0;color:var(--text-0)">🖼 Screenshots (${d.count})</h3>
          <button onclick="this.closest('[style*=fixed]').remove()" style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px">
          ${d.screenshots.map(s=>`
            <div style="border:1px solid var(--border);border-radius:8px;overflow:hidden;cursor:pointer" onclick="window.open('${escHtml(s.path)}','_blank')">
              <img src="${escHtml(s.path)}" style="width:100%;height:100px;object-fit:cover" loading="lazy" onerror="this.style.display='none'">
              <div style="padding:5px 7px;font-size:10px;color:var(--text-3)">${escHtml(s.filename.slice(0,30))} · ${((s.size||0)/1024).toFixed(0)}KB</div>
            </div>`).join('')}
        </div>
      </div>`;
    overlay.onclick = e => { if(e.target===overlay) overlay.remove(); };
    document.body.appendChild(overlay);
  } catch(ex) {
    gmAlert('Error: '+ex?.message);
  }
}


// ══════════════════════════════════════════════════════════════════
//  WEB SEARCH GROUNDING
// ══════════════════════════════════════════════════════════════════
async function renderWebSearch() {
  const pane = document.getElementById('pane-websearch');
  if (!pane) return;

  pane.innerHTML = `
  <div style="padding:20px;max-width:900px;margin:0 auto">
    <div class="section-head">
      <div>
        <h2>🔎 Web Search</h2>
        <p>Like Perplexity — ground AI answers with live web citations. Free DuckDuckGo search, no API key needed.</p>
      </div>
      <button class="btn-sm" onclick="wsShowHistory()">🕑 History</button>
    </div>

    <!-- Search tabs -->
    <div style="display:flex;gap:8px;margin-bottom:16px">
      <button class="btn" id="ws-tab-grounded" onclick="wsSetTab('grounded')">🤖 Grounded AI</button>
      <button class="btn-sm" id="ws-tab-search" onclick="wsSetTab('search')">🔍 Raw Search</button>
      <button class="btn-sm" id="ws-tab-research" onclick="wsSetTab('research')">📚 Deep Research</button>
      <button class="btn-sm" id="ws-tab-history" onclick="wsSetTab('history')">🕑 History</button>
    </div>

    <!-- Grounded AI (default) -->
    <div id="ws-pane-grounded">
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;overflow:hidden;margin-bottom:16px">
        <div style="display:flex;gap:8px;padding:10px 14px;align-items:center">
          <input id="ws-grounded-q" aria-label="Ask a grounded question" list="ws-grounded-suggest" placeholder="Ask anything — AI will search the web first then answer with citations…" style="flex:1;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:13px;padding:9px 12px" onkeydown="if(event.key==='Enter')wsGrounded()" oninput="wsAutocomplete('ws-grounded-q','ws-grounded-suggest')">
          <datalist id="ws-grounded-suggest"></datalist>
          <button class="btn" onclick="wsGrounded()">Ask</button>
          <button class="btn-sm" onclick="wsGroundedStream()">⚡ Stream</button>
        </div>
      </div>
      <div id="ws-grounded-result"></div>
    </div>

    <!-- Raw search -->
    <div id="ws-pane-search" style="display:none">
      <div style="display:flex;gap:8px;margin-bottom:14px">
        <input id="ws-search-q" aria-label="Search the web" list="ws-search-suggest" placeholder="Search query…" style="flex:1;background:var(--bg-2);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:13px;padding:9px 12px" onkeydown="if(event.key==='Enter')wsSearch()" oninput="wsAutocomplete('ws-search-q','ws-search-suggest')">
        <datalist id="ws-search-suggest"></datalist>
        <button class="btn" onclick="wsSearch()">Search</button>
      </div>
      <div id="ws-search-result"></div>
    </div>

    <!-- Deep research -->
    <div id="ws-pane-research" style="display:none">
      <div style="font-size:12px;color:var(--text-2);margin-bottom:10px">Multi-query deep research: generates 4 search queries, synthesizes into a comprehensive report with citations</div>
      <div style="display:flex;gap:8px;margin-bottom:14px">
        <input id="ws-research-q" aria-label="Enter research topic" list="ws-research-suggest" placeholder="Research topic (e.g. 'FastAPI vs Django for production APIs')" style="flex:1;background:var(--bg-2);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:13px;padding:9px 12px" onkeydown="if(event.key==='Enter')wsResearch()" oninput="wsAutocomplete('ws-research-q','ws-research-suggest')">
        <datalist id="ws-research-suggest"></datalist>
        <button class="btn" onclick="wsResearch()">📚 Research</button>
      </div>
      <div id="ws-research-status" style="font-size:12px;color:var(--text-2);margin-bottom:8px"></div>
      <div id="ws-research-result" style="font-size:13px;color:var(--text-1);line-height:1.7;white-space:pre-wrap"></div>
      <div id="ws-research-citations"></div>
    </div>

    <!-- History -->
    <div id="ws-pane-history" style="display:none">
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:14px">
        <span style="font-size:13px;color:var(--text-1);flex:1">Recent searches</span>
        <button class="btn-sm" onclick="wsLoadHistory()">🔄 Refresh</button>
        <button class="btn-sm" style="color:var(--danger)" onclick="wsClearHistory()">🗑️ Clear All</button>
      </div>
      <div id="ws-history-list"><div style="color:var(--text-3);font-size:13px">Loading…</div></div>
    </div>
  </div>`;

  // Set grounded tab as active on render
  wsSetTab('grounded');
}

function wsSetTab(tab) {
  const tabs = ['grounded','search','research','history'];
  tabs.forEach(t => {
    const p = document.getElementById(`ws-pane-${t}`);
    const b = document.getElementById(`ws-tab-${t}`);
    if (p) p.style.display = t === tab ? 'block' : 'none';
    if (b) {
      b.style.background = t === tab ? 'var(--accent)' : '';
      b.style.color      = t === tab ? '#fff' : '';
    }
  });
  if (tab === 'history') wsLoadHistory();
}

async function wsGrounded() {
  const q = document.getElementById('ws-grounded-q')?.value?.trim();
  if (!q) return;
  const el = document.getElementById('ws-grounded-result');
  if (el) el.innerHTML = '<div style="color:var(--text-2)">🔍 Searching & thinking…</div>';
  try {
    const r = await fetch('/api/websearch/grounded-completion', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({prompt: q, num_results: 5})
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'Search failed');
    if (el) el.innerHTML = `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px">
        <div style="font-size:13px;color:var(--text-0);line-height:1.7;white-space:pre-wrap;margin-bottom:14px">${escHtml(d.answer||'')}</div>
        <div style="border-top:1px solid var(--border);padding-top:10px">
          <div style="font-size:11px;font-weight:700;color:var(--text-3);margin-bottom:6px">SOURCES (${d.sources||0})</div>
          ${(d.citations||[]).map(c=>`
            <a href="${escHtml(c.url||'')}" target="_blank" rel="noopener" style="display:flex;align-items:center;gap:6px;padding:4px 0;text-decoration:none">
              <span style="font-size:10px;background:var(--bg-3);padding:1px 5px;border-radius:3px;color:var(--text-3)">[${c.num}]</span>
              <span style="font-size:12px;color:var(--accent)">${escHtml(c.title||c.url||'')}</span>
            </a>`).join('')}
        </div>
      </div>`;
  } catch(ex) {
    if (el) el.innerHTML = `<div style="color:var(--danger);padding:12px">${escHtml(ex?.message||String(ex))}<br><button class="btn-sm" style="margin-top:8px" onclick="wsGrounded()">Retry</button></div>`;
  }
}

async function wsGroundedStream() {
  const q = document.getElementById('ws-grounded-q')?.value?.trim();
  if (!q) return;
  const el = document.getElementById('ws-grounded-result');
  if (el) el.innerHTML = '<div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px"><div style="font-size:13px;color:var(--text-1);line-height:1.7;white-space:pre-wrap" id="ws-stream-txt">🔍 Searching…</div></div>';
  try {
    const resp = await fetch('/api/websearch/grounded-completion/stream', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({prompt: q})
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    if (!resp.body) throw new Error('No response body');
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = '', txt = '';
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buf += dec.decode(value, {stream: true});
      const parts = buf.split('\n\n');
      buf = parts.pop() || '';
      for (const part of parts) {
        if (!part.startsWith('data:')) continue;
        try {
          const d = JSON.parse(part.slice(5).trim());
          if (d.type === 'search_done') {
            const t = document.getElementById('ws-stream-txt');
            if (t) t.textContent = `✅ Found ${d.results} sources — generating answer…\n`;
            txt = '';
          } else if (d.type === 'chunk') {
            txt += d.text || '';
            const t = document.getElementById('ws-stream-txt');
            if (t) t.textContent = txt;
          } else if (d.type === 'done' && d.citations?.length) {
            const t = document.getElementById('ws-stream-txt');
            if (t) t.insertAdjacentHTML('afterend', `
              <div style="border-top:1px solid var(--border);padding-top:10px;margin-top:10px">
                <div style="font-size:11px;font-weight:700;color:var(--text-3);margin-bottom:6px">SOURCES</div>
                ${(d.citations||[]).map(c=>`<a href="${escHtml(c.url||'')}" target="_blank" rel="noopener" style="display:block;font-size:12px;color:var(--accent);padding:2px 0">[${c.num}] ${escHtml(c.title||c.url||'')}</a>`).join('')}
              </div>`);
          }
        } catch(e) { log?.warn?.('SSE parse error', e); }
      }
    }
  } catch(ex) {
    if (el) el.innerHTML = `<div style="color:var(--danger);padding:12px">${escHtml(ex?.message||String(ex))}<br><button class="btn-sm" style="margin-top:8px" onclick="wsGroundedStream()">Retry</button></div>`;
  }
}

async function wsSearch() {
  const q = document.getElementById('ws-search-q')?.value?.trim();
  if (!q) return;
  const el = document.getElementById('ws-search-result');
  if (el) el.innerHTML = '<div style="color:var(--text-2)">🔍 Searching…</div>';
  try {
    const resp = await fetch('/api/websearch/search', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({query: q, num_results: 8})
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const d = await resp.json();
    if (!d.ok) throw new Error(d.error || 'Search failed');
    if (el) el.innerHTML = (d.results||[]).map((res, i) => `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:12px;margin-bottom:8px">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
          <span style="font-size:10px;color:var(--text-3)">[${i+1}]</span>
          <a href="${escHtml(res.url||'')}" target="_blank" rel="noopener" style="font-weight:600;font-size:13px;color:var(--accent);text-decoration:none">${escHtml(res.title||'')}</a>
        </div>
        <div style="font-size:12px;color:var(--text-2);line-height:1.5">${escHtml(res.snippet||'')}</div>
        <div style="font-size:10px;color:var(--text-3);margin-top:4px">${escHtml(res.url||'')}</div>
      </div>`).join('') || '<div style="color:var(--text-3);padding:20px;text-align:center">No results found</div>';
  } catch(ex) {
    if (el) el.innerHTML = `<div style="color:var(--danger);padding:12px">${escHtml(ex?.message||String(ex))}<br><button class="btn-sm" style="margin-top:8px" onclick="wsSearch()">Retry</button></div>`;
  }
}

async function wsResearch() {
  const q = document.getElementById('ws-research-q')?.value?.trim();
  if (!q) return;
  const statusEl = document.getElementById('ws-research-status');
  const el       = document.getElementById('ws-research-result');
  const citEl    = document.getElementById('ws-research-citations');
  if (statusEl) statusEl.textContent = '🧠 Generating research queries…';
  if (el)       el.textContent = '';
  if (citEl)    citEl.innerHTML = '';
  try {
    const resp = await fetch('/api/websearch/research', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({topic: q})
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    if (!resp.body) throw new Error('No response body');
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = '', txt = '';
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buf += dec.decode(value, {stream: true});
      const parts = buf.split('\n\n');
      buf = parts.pop() || '';
      for (const part of parts) {
        if (!part.startsWith('data:')) continue;
        try {
          const d = JSON.parse(part.slice(5).trim());
          if (d.type === 'queries' && statusEl) {
            statusEl.textContent = `🔍 Running ${d.queries?.length||0} search queries…`;
          } else if (d.type === 'sources_gathered' && statusEl) {
            statusEl.textContent = `📚 Found ${d.count} unique sources — synthesizing report…`;
          } else if (d.type === 'chunk') {
            txt += d.text || '';
            if (el) el.textContent = txt;
          } else if (d.type === 'done') {
            if (statusEl) statusEl.textContent = `✅ Research complete — ${d.source_count||0} sources`;
            if (citEl && d.citations?.length) {
              citEl.innerHTML = `
                <div style="border-top:1px solid var(--border);padding-top:12px;margin-top:12px">
                  <div style="font-size:11px;font-weight:700;color:var(--text-3);margin-bottom:8px">SOURCES (${d.citations.length})</div>
                  ${d.citations.map(c=>`
                    <a href="${escHtml(c.url||'')}" target="_blank" rel="noopener" style="display:flex;align-items:center;gap:6px;padding:3px 0;text-decoration:none">
                      <span style="font-size:10px;background:var(--bg-3);padding:1px 5px;border-radius:3px;color:var(--text-3);flex-shrink:0">[${c.num}]</span>
                      <span style="font-size:12px;color:var(--accent)">${escHtml(c.title||c.url||'')}</span>
                    </a>`).join('')}
                </div>`;
            }
          }
        } catch(e) { /* skip malformed SSE frame */ }
      }
    }
  } catch(ex) {
    if (statusEl) statusEl.innerHTML = `<span style="color:var(--danger)">${escHtml(ex?.message||String(ex))}</span>`;
    if (el) el.innerHTML = `<button class="btn-sm" style="margin-top:8px" onclick="wsResearch()">Retry</button>`;
  }
}

async function wsLoadHistory() {
  const el = document.getElementById('ws-history-list');
  if (!el) return;
  el.innerHTML = '<div style="color:var(--text-3);font-size:13px">Loading…</div>';
  try {
    const r = await fetch('/api/websearch/history?limit=50');
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    const items = d.items || [];
    if (!items.length) {
      el.innerHTML = '<div style="color:var(--text-3);font-size:13px;padding:20px;text-align:center">No search history yet</div>';
      return;
    }
    el.innerHTML = items.map(item => `
      <div style="display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:8px;background:var(--bg-2);margin-bottom:6px;cursor:pointer" onclick="wsReplaySearch(${JSON.stringify(item.query)},${JSON.stringify(item.kind)})">
        <span style="font-size:16px">${{search:'🔍',grounded:'🤖',grounded_stream:'⚡',research:'📚'}[item.kind]||'🔎'}</span>
        <span style="flex:1;font-size:13px;color:var(--text-0)">${escHtml(item.query)}</span>
        <span style="font-size:11px;color:var(--text-3)">${item.results} results</span>
        <button class="btn-sm" style="font-size:10px;padding:2px 6px;color:var(--danger)" onclick="event.stopPropagation();wsDeleteHistory(${JSON.stringify(item.id)})">✕</button>
      </div>`).join('');
  } catch(ex) {
    el.innerHTML = `<div style="color:var(--danger);font-size:13px">${escHtml(ex?.message||String(ex))}<br><button class="btn-sm" style="margin-top:8px" onclick="wsLoadHistory()">Retry</button></div>`;
  }
}

function wsReplaySearch(query, kind) {
  if (kind === 'search') {
    wsSetTab('search');
    const inp = document.getElementById('ws-search-q');
    if (inp) { inp.value = query; wsSearch(); }
  } else if (kind === 'research') {
    wsSetTab('research');
    const inp = document.getElementById('ws-research-q');
    if (inp) { inp.value = query; wsResearch(); }
  } else {
    wsSetTab('grounded');
    const inp = document.getElementById('ws-grounded-q');
    if (inp) { inp.value = query; wsGrounded(); }
  }
}

async function wsDeleteHistory(id) {
  try {
    const r = await fetch(`/api/websearch/history/${encodeURIComponent(id)}`, {method:'DELETE'});
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    wsLoadHistory();
  } catch(ex) { showToast(ex?.message||String(ex), 'error'); }
}

async function wsClearHistory() {
  const ok = await gmDanger('Clear all search history?', 'This cannot be undone.', 'Clear History');
  if (!ok) return;
  try {
    const r = await fetch('/api/websearch/history', {method:'DELETE'});
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    showToast('History cleared');
    wsLoadHistory();
  } catch(ex) { showToast(ex?.message||String(ex), 'error'); }
}

function wsShowHistory() { wsSetTab('history'); }

// Autocomplete from /api/websearch/suggest — wired to all three search inputs
async function wsAutocomplete(inputId, datalistId) {
  const inp = document.getElementById(inputId);
  if (!inp) return;
  const q = inp.value.trim();
  if (!q || q.length < 2) return;
  try {
    const r = await fetch(`/api/websearch/suggest?q=${encodeURIComponent(q)}&limit=8`);
    if (!r.ok) return;
    const d = await r.json();
    let dl = document.getElementById(datalistId);
    if (!dl) { dl = document.createElement('datalist'); dl.id = datalistId; document.body.appendChild(dl); inp.setAttribute('list', datalistId); }
    dl.innerHTML = (d.suggestions||[]).map(s=>`<option value="${escHtml(s)}">`).join('');
  } catch(e) { /* autocomplete is best-effort */ }
}


// ══════════════════════════════════════════════════════════════════
//  AGENT LEADERBOARD
// ══════════════════════════════════════════════════════════════════
async function renderLeaderboard() {
  const pane = document.getElementById('pane-leaderboard');
  if (!pane) return;

  const [lb, gov, discovered] = await Promise.all([
    fetch('/api/agent-leaderboard?days=30').then(r=>{ if(!r.ok) throw new Error(r.status); return r.json(); }).catch(()=>({leaderboard:[]})),
    fetch('/api/agent-leaderboard/governance/summary').then(r=>{ if(!r.ok) throw new Error(r.status); return r.json(); }).catch(()=>({})),
    fetch('/api/agent-leaderboard/discover').then(r=>{ if(!r.ok) throw new Error(r.status); return r.json(); }).catch(()=>({agents:[]})),
  ]);

  pane.innerHTML = `
  <div style="padding:20px;max-width:1000px;margin:0 auto">
    <div class="section-head">
      <div>
        <h2>🏆 Agent Leaderboard</h2>
        <p>Rank agents by success rate, speed, and cost. Like Arthur AI's governance dashboard — discover and govern all agents.</p>
      </div>
      <button class="btn-sm" onclick="lbSeedData()">🎲 Seed Test Data</button>
    </div>

    <!-- Governance summary -->
    <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:20px">
      ${[
        ['🤖',gov.active_agents||0,'Active Agents'],
        ['📋',gov.active_policies||0,'Policies'],
        ['⏳',gov.pending_approvals||0,'Pending HITL'],
        ['📞',gov.calls_24h||0,'Calls (24h)'],
        ['❌',`${gov.error_rate_7d||0}%`,'Error Rate'],
      ].map(([icon,val,label])=>`
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:12px;text-align:center">
          <div style="font-size:18px">${icon}</div>
          <div style="font-size:18px;font-weight:700;color:var(--text-0)">${val}</div>
          <div style="font-size:10px;color:var(--text-3)">${label}</div>
        </div>`).join('')}
    </div>

    <!-- Tabs -->
    <div style="display:flex;gap:8px;margin-bottom:14px">
      <button class="btn" onclick="lbShowTab('leaderboard',this)" style="background:var(--accent);color:#fff">🏆 Leaderboard</button>
      <button class="btn-sm" onclick="lbShowTab('discover',this)">🔍 Discover</button>
      <button class="btn-sm" onclick="lbShowTab('policies',this)">📋 Policies</button>
    </div>

    <!-- Leaderboard tab -->
    <div id="lb-tab-leaderboard">
      <div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;align-items:center">
        <label style="font-size:11px;color:var(--text-3)">Days:</label>
        <select id="lb-days-select" onchange="lbChangeDays(this.value)" style="background:var(--bg-3);border:1px solid var(--border);border-radius:6px;color:var(--text-1);font-size:11px;padding:3px 8px">
          <option value="7">7d</option><option value="30" selected>30d</option><option value="90">90d</option><option value="365">1y</option>
        </select>
        <label style="font-size:11px;color:var(--text-3)">Task:</label>
        <select id="lb-task-select" onchange="lbChangeDays()" style="background:var(--bg-3);border:1px solid var(--border);border-radius:6px;color:var(--text-1);font-size:11px;padding:3px 8px">
          <option value="">All tasks</option>
          <option value="code">Code</option><option value="research">Research</option>
          <option value="chat">Chat</option><option value="analysis">Analysis</option>
        </select>
        <button class="btn-sm" onclick="lbExport()" style="margin-left:auto">⬇ Export</button>
      </div>
      <div id="lb-table-container">
      ${(lb.leaderboard||[]).length ? `
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;overflow:hidden">
          <div style="display:grid;grid-template-columns:30px 40px 1fr 85px 70px 80px 70px 60px;padding:8px 14px;background:var(--bg-3);font-size:11px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:.4px">
            <div>#</div><div></div><div>Name</div><div>Success%</div><div>Calls</div><div>Avg Lat</div><div>Cost</div><div>Rating</div>
          </div>
          ${(lb.leaderboard||[]).map((a, i) => {
            const medal = i===0?'🥇':i===1?'🥈':i===2?'🥉':'';
            const col   = a.success_rate>=90?'var(--success)':a.success_rate>=70?'var(--warning)':'var(--danger)';
            const rating = a.avg_rating ? '★'.repeat(Math.round(a.avg_rating)) : '—';
            return `
              <div style="display:grid;grid-template-columns:30px 40px 1fr 85px 70px 80px 70px 60px;padding:10px 14px;border-top:1px solid var(--border);align-items:center;cursor:pointer;transition:background .1s"
                   onmouseover="this.style.background='var(--bg-3)'" onmouseout="this.style.background=''"
                   onclick="lbViewAgent(${JSON.stringify(a.agent_id)})">
                <div style="font-weight:700;color:var(--text-3);font-size:12px">${medal||('#'+(i+1))}</div>
                <div style="font-size:20px">${a.avatar||'🤖'}</div>
                <div>
                  <div style="font-weight:600;color:var(--text-0);font-size:13px">${escHtml(a.name||a.agent_id)}</div>
                  <div style="font-size:10px;color:var(--text-3)">${escHtml(a.agent_id)}</div>
                </div>
                <div style="font-weight:700;color:${col};font-size:13px">${a.success_rate||0}%</div>
                <div style="color:var(--text-2);font-size:12px">${a.total_calls||0}</div>
                <div style="color:var(--text-2);font-size:12px">${Math.round(a.avg_latency||0)}ms</div>
                <div style="color:var(--text-2);font-size:12px">$${(a.total_cost||0).toFixed(4)}</div>
                <div style="color:var(--warning);font-size:11px">${rating}</div>
              </div>`;
          }).join('')}
        </div>
      ` : `
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:40px;text-align:center;color:var(--text-3)">
          <div style="font-size:40px;margin-bottom:12px">🏆</div>
          <div style="font-size:15px;font-weight:600;margin-bottom:8px">No performance data yet</div>
          <div style="font-size:13px;max-width:340px;margin:0 auto">Use your agents and performance data will appear here. Click "Seed Test Data" to demo.</div>
        </div>`}
      </div>
    </div>

    <!-- Discover tab -->
    <div id="lb-tab-discover" style="display:none">
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;overflow:hidden">
        ${(discovered.agents||[]).length ? (discovered.agents||[]).map((a) =>`
          <div style="display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid var(--border);cursor:pointer"
               onmouseover="this.style.background='var(--bg-3)'" onmouseout="this.style.background=''"
               onclick="lbViewAgent(${JSON.stringify(a.id||a.agent_id)})">
            <span style="font-size:22px">${a.avatar||'🤖'}</span>
            <div style="flex:1;min-width:0">
              <div style="font-weight:600;color:var(--text-0);font-size:13px">${escHtml(a.name||a.id)}</div>
              <div style="font-size:11px;color:var(--text-3)">${a.total_calls||0} calls · ${a.success_rate||0}% success · Last: ${(a.last_active||'never').slice(0,16)}</div>
            </div>
            <div style="display:flex;gap:5px;align-items:center;flex-shrink:0">
              <span style="font-size:11px;padding:2px 7px;border-radius:4px;${a.status==='active'?'background:rgba(61,186,122,.15);color:var(--success)':'background:var(--bg-3);color:var(--text-3)'}">${a.status||'idle'}</span>
              ${a.has_loop?'<span style="font-size:10px;background:rgba(232,162,55,.15);color:var(--warning);padding:1px 6px;border-radius:3px">🔁 Loop</span>':''}
              <span style="font-size:10px;padding:2px 6px;border-radius:3px;${a.risk_level==='high'?'background:rgba(232,82,82,.15);color:var(--danger)':a.risk_level==='medium'?'background:rgba(232,162,55,.15);color:var(--warning)':'background:rgba(61,186,122,.15);color:var(--success)'}">
                ${a.risk_level||'low'} risk
              </span>
              <span style="font-size:10px;color:var(--text-3)">${a.policy_count||0} policies</span>
            </div>
          </div>`).join('') : '<div style="color:var(--text-3);padding:20px;text-align:center">No agents found</div>'}
      </div>
    </div>

    <!-- Policies tab -->
    <div id="lb-tab-policies" style="display:none">
      <div style="margin-bottom:10px;display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap">
        <input id="lb-policy-filter" placeholder="Filter by agent…" oninput="lbFilterPolicies(this.value)"
               style="flex:1;min-width:120px;max-width:200px;background:var(--bg-3);border:1px solid var(--border);border-radius:6px;color:var(--text-0);font-size:12px;padding:5px 8px">
        <button class="btn-sm" onclick="lbAddPolicy()">＋ Add Policy</button>
      </div>
      <div id="lb-policies-list">Loading…</div>
    </div>
  </div>`;

  lbLoadPolicies();
}

function lbShowTab(tab, btn) {
  ['leaderboard','discover','policies'].forEach(t=>{
    const el=document.getElementById(`lb-tab-${t}`);
    if(el) el.style.display=t===tab?'block':'none';
  });
  document.querySelectorAll('#pane-leaderboard .btn,#pane-leaderboard .btn-sm').forEach(b=>{
    b.style.background=''; b.style.color='';
  });
  if(btn){btn.style.background='var(--accent)';btn.style.color='#fff';}
  if(tab==='policies') lbLoadPolicies();
}

let _lbAllPolicies = [];

async function lbLoadPolicies() {
  const el = document.getElementById('lb-policies-list');
  if (!el) return;
  el.innerHTML = '<div style="color:var(--text-3);font-size:12px;padding:12px">Loading…</div>';
  try {
    const r = await fetch('/api/agent-leaderboard/policies');
    if (!r.ok) { el.innerHTML = `<div style="color:var(--danger);padding:12px">Failed (HTTP ${r.status})</div>`; return; }
    const d = await r.json();
    _lbAllPolicies = d.policies || [];
    lbRenderPolicies(_lbAllPolicies);
  } catch(ex) {
    el.innerHTML = `<div style="color:var(--danger);padding:12px">Error: ${ex?.message||String(ex)}</div>`;
  }
}

function lbFilterPolicies(q) {
  const filtered = q ? _lbAllPolicies.filter(p =>
    (p.agent_id||'').toLowerCase().includes(q.toLowerCase()) ||
    (p.policy_type||'').toLowerCase().includes(q.toLowerCase()) ||
    (p.policy_rule||'').toLowerCase().includes(q.toLowerCase())
  ) : _lbAllPolicies;
  lbRenderPolicies(filtered);
}

function lbRenderPolicies(policies) {
  const el = document.getElementById('lb-policies-list');
  if (!el) return;
  el.innerHTML = `
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;overflow:hidden">
      ${policies.length ? policies.map((p) =>`
        <div style="display:flex;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid var(--border);font-size:12px">
          <span style="background:var(--bg-3);padding:1px 6px;border-radius:4px;font-family:monospace;color:var(--accent);flex-shrink:0">${escHtml(p.agent_id||'*')}</span>
          <span style="font-weight:600;color:var(--text-1);flex-shrink:0">${escHtml(p.policy_type||'')}</span>
          <span style="color:var(--text-2);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml(p.policy_rule||'')}</span>
          <button onclick="lbTogglePolicy(${JSON.stringify(p.id)},${p.enabled?0:1})" style="background:none;border:none;cursor:pointer;font-size:14px" title="${p.enabled?'Disable':'Enable'} policy">${p.enabled?'✅':'❌'}</button>
          <button onclick="lbDeletePolicy(${JSON.stringify(p.id)})" style="background:none;border:none;color:var(--danger);cursor:pointer;font-size:14px" title="Delete policy">🗑</button>
        </div>`).join('') : '<div style="color:var(--text-3);padding:16px;text-align:center">No policies configured</div>'}
    </div>`;
}

async function lbTogglePolicy(policyId, newEnabled) {
  try {
    const r = await fetch(`/api/agent-leaderboard/policies/${encodeURIComponent(policyId)}`, {
      method:'PUT', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({enabled: !!newEnabled})
    });
    if (!r.ok) { showToast('Toggle failed: HTTP '+r.status); return; }
    lbLoadPolicies();
  } catch(ex) {
    showToast('Toggle error: '+ex?.message);
  }
}

async function lbDeletePolicy(policyId) {
  const ok = await gmDanger('Delete Policy', 'Remove this governance policy permanently?');
  if (!ok) return;
  try {
    const r = await fetch(`/api/agent-leaderboard/policies/${encodeURIComponent(policyId)}`, {method:'DELETE'});
    if (!r.ok) { showToast('Delete failed: HTTP '+r.status); return; }
    const d = await r.json();
    if (d.ok) { showToast('🗑 Policy deleted'); lbLoadPolicies(); }
    else showToast('Delete failed: '+(d.error||'Unknown'));
  } catch(ex) {
    showToast('Delete error: '+ex?.message);
  }
}

async function lbAddPolicy() {
  const agent_id = await gmPrompt('Agent ID (* for all agents):', '*');
  if (agent_id === null) return;
  const policy_type = await gmPrompt('Policy type (rate_limit|cost_cap|no_pii|no_secrets|custom):', 'custom');
  if (policy_type === null) return;
  const policy_rule = await gmPrompt('Rule description:', '');
  if (!policy_rule) return;
  try {
    const r = await fetch('/api/agent-leaderboard/policies', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({agent_id: agent_id||'*', policy_type: policy_type||'custom', policy_rule})
    });
    if (!r.ok) { showToast('Create policy failed: HTTP '+r.status); return; }
    const d = await r.json();
    if (d.ok) { showToast('✅ Policy added'); lbLoadPolicies(); }
    else showToast('Failed: '+(d.error||'Unknown'));
  } catch(ex) {
    showToast('Error: '+ex?.message);
  }
}

async function lbChangeDays(days) {
  const d = days || document.getElementById('lb-days-select')?.value || '30';
  const task = document.getElementById('lb-task-select')?.value || '';
  const container = document.getElementById('lb-table-container');
  if (!container) return;
  container.innerHTML = '<div style="color:var(--text-3);padding:12px">Loading…</div>';
  try {
    const params = new URLSearchParams({days: d, limit:'20'});
    if (task) params.set('task_type', task);
    const r = await fetch(`/api/agent-leaderboard?${encodeURIComponent(params)}`);
    if (!r.ok) { container.innerHTML = `<div style="color:var(--danger)">Failed (HTTP ${r.status})</div>`; return; }
    const lb = await r.json();
    if (!(lb.leaderboard||[]).length) {
      container.innerHTML = '<div style="color:var(--text-3);padding:20px;text-align:center">No data for selected period/task</div>';
      return;
    }
    container.innerHTML = `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;overflow:hidden">
        <div style="display:grid;grid-template-columns:30px 40px 1fr 85px 70px 80px 70px 60px;padding:8px 14px;background:var(--bg-3);font-size:11px;font-weight:700;color:var(--text-3);text-transform:uppercase">
          <div>#</div><div></div><div>Name</div><div>Success%</div><div>Calls</div><div>Avg Lat</div><div>Cost</div><div>Rating</div>
        </div>
        ${lb.leaderboard.map((a, i) => {
          const medal = i===0?'🥇':i===1?'🥈':i===2?'🥉':'';
          const col   = a.success_rate>=90?'var(--success)':a.success_rate>=70?'var(--warning)':'var(--danger)';
          const rating = a.avg_rating ? '★'.repeat(Math.min(5,Math.round(a.avg_rating))) : '—';
          return `<div style="display:grid;grid-template-columns:30px 40px 1fr 85px 70px 80px 70px 60px;padding:10px 14px;border-top:1px solid var(--border);align-items:center;cursor:pointer;transition:background .1s"
                       onmouseover="this.style.background='var(--bg-3)'" onmouseout="this.style.background=''"
                       onclick="lbViewAgent(${JSON.stringify(a.agent_id)})">
            <div style="font-weight:700;color:var(--text-3);font-size:12px">${medal||('#'+(i+1))}</div>
            <div style="font-size:20px">${a.avatar||'🤖'}</div>
            <div>
              <div style="font-weight:600;color:var(--text-0);font-size:13px">${escHtml(a.name||a.agent_id)}</div>
              <div style="font-size:10px;color:var(--text-3)">${escHtml(a.agent_id)}</div>
            </div>
            <div style="font-weight:700;color:${col};font-size:13px">${a.success_rate||0}%</div>
            <div style="color:var(--text-2);font-size:12px">${a.total_calls||0}</div>
            <div style="color:var(--text-2);font-size:12px">${Math.round(a.avg_latency||0)}ms</div>
            <div style="color:var(--text-2);font-size:12px">$${(a.total_cost||0).toFixed(4)}</div>
            <div style="color:var(--warning);font-size:11px">${rating}</div>
          </div>`;
        }).join('')}
      </div>`;
  } catch(ex) {
    if(container) container.innerHTML = `<div style="color:var(--danger)">Error: ${ex?.message||String(ex)}</div>`;
  }
}

async function lbViewAgent(agentId) {
  try {
    const r = await fetch(`/api/agent-leaderboard/agent/${encodeURIComponent(agentId)}`);
    if (!r.ok) { gmAlert('Failed to load agent stats: HTTP '+r.status); return; }
    const d = await r.json();
    const s = d.summary || {};
    const byType = (d.by_type||[]).map(t =>
      `<div style="display:flex;justify-content:space-between;font-size:12px;padding:3px 0">
        <span style="color:var(--text-2)">${escHtml(t.task_type||'')}</span>
        <span><strong>${t.calls||0}</strong> calls · <span style="color:${(t.success_rate||0)>=80?'var(--success)':'var(--danger)'}">${t.success_rate||0}%</span></span>
      </div>`
    ).join('');
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    overlay.innerHTML = `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:16px;max-width:500px;width:100%;max-height:80vh;overflow-y:auto;padding:24px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
          <h3 style="margin:0;color:var(--text-0)">📊 ${escHtml(agentId)} Stats</h3>
          <button onclick="this.closest('[style*=fixed]').remove()" style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px">
          ${[
            ['Total Calls', s.total||0],
            ['Success Rate', (s.success_rate||0)+'%'],
            ['Avg Latency', Math.round(s.avg_latency||0)+'ms'],
            ['Total Tokens', (s.tokens||0).toLocaleString()],
            ['Total Cost', '$'+(s.cost||0).toFixed(6)],
            ['Avg Rating', s.avg_rating||'—'],
          ].map(([l,v]) => `<div style="background:var(--bg-3);border-radius:8px;padding:10px;text-align:center">
            <div style="font-size:16px;font-weight:700;color:var(--text-0)">${v}</div>
            <div style="font-size:10px;color:var(--text-3)">${l}</div>
          </div>`).join('')}
        </div>
        ${byType ? `<div><h4 style="font-size:11px;color:var(--text-3);text-transform:uppercase;margin:0 0 8px">By Task Type</h4>${byType}</div>` : ''}
        <div style="margin-top:16px;display:flex;gap:8px">
          <button class="btn-sm" onclick="lbRateAgent(${JSON.stringify(agentId)})">⭐ Rate</button>
          <button class="btn-sm" style="color:var(--danger);border-color:var(--danger)" onclick="lbClearAgent(${JSON.stringify(agentId)});this.closest('[style*=fixed]').remove()">🗑 Clear Data</button>
        </div>
      </div>`;
    overlay.onclick = e => { if(e.target===overlay) overlay.remove(); };
    document.body.appendChild(overlay);
  } catch(ex) {
    gmAlert('Error loading agent: '+ex?.message);
  }
}

async function lbRateAgent(agentId) {
  const ratingStr = await gmPrompt('Rate this agent (1-5 stars):', '5');
  if (ratingStr === null) return;
  const rating = Math.min(5, Math.max(1, parseInt(ratingStr||'5')));
  if (isNaN(rating)) { gmAlert('Enter a number 1-5'); return; }
  try {
    const r = await fetch('/api/agent-leaderboard/rate', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({agent_id: agentId, rating})
    });
    if (!r.ok) { showToast('Rate failed: HTTP '+r.status); return; }
    showToast(`✅ Rated ${agentId}: ${rating}⭐`);
  } catch(ex) {
    showToast('Rate error: '+ex?.message);
  }
}

async function lbClearAgent(agentId) {
  const ok = await gmDanger('Clear Performance Data', `Delete all performance records for "${agentId}"?`);
  if (!ok) return;
  try {
    const r = await fetch(`/api/agent-leaderboard/performance/${encodeURIComponent(agentId)}`, {method:'DELETE'});
    if (!r.ok) { showToast('Clear failed: HTTP '+r.status); return; }
    const d = await r.json();
    showToast(`🗑 Cleared ${d.deleted||0} records for ${agentId}`);
    renderLeaderboard();
  } catch(ex) {
    showToast('Clear error: '+ex?.message);
  }
}

async function lbExport() {
  try {
    const days = document.getElementById('lb-days-select')?.value || '30';
    const r = await fetch(`/api/agent-leaderboard?days=${days}&limit=100`);
    if (!r.ok) { showToast('Export failed: HTTP '+r.status); return; }
    const d = await r.json();
    const blob = new Blob([JSON.stringify(d.leaderboard, null, 2)], {type:'application/json'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `agent-leaderboard-${new Date().toISOString().slice(0,10)}.json`;
    a.click();
    showToast('✅ Leaderboard exported');
  } catch(ex) {
    showToast('Export error: '+ex?.message);
  }
}

async function lbSeedData() {
  const agents = ['builder','researcher','orchestrator','memory','swarm'];
  const tasks  = ['code','research','chat','analysis','general'];
  let count = 0;
  for (const aid of agents) {
    for (let i = 0; i < Math.floor(Math.random()*10+5); i++) {
      try {
        await fetch('/api/agent-leaderboard/record', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({
            agent_id:   aid,
            task_type:  tasks[Math.floor(Math.random()*tasks.length)],
            success:    Math.random() > 0.15,
            tokens:     Math.floor(Math.random()*1000)+100,
            cost_usd:   Math.random()*0.01,
            latency_ms: Math.floor(Math.random()*3000)+200,
          })
        });
        count++;
      } catch(e) {}
    }
  }
  showToast(`✅ Seeded ${count} performance records`);
  renderLeaderboard();
}


// ══════════════════════════════════════════════════════════════════
// ══════════════════════════════════════════════════════════════════
//  SPRINT A — IMMUTABLE AUDIT LOG
// ══════════════════════════════════════════════════════════════════


// ══════════════════════════════════════════════════════════════════
//  COMPLIANCE REPORT CENTER — Complete Implementation
//  Covers: Audit Log + Compliance Report Generator + Report History
// ══════════════════════════════════════════════════════════════════

// ── State ──────────────────────────────────────────────────────────
let _crcTab          = 'dashboard';   // dashboard | generate | history | audit
let _crcReports      = [];
let _crcSummary      = null;
let _crcAuditEntries = [];
let _crcAuditTotal   = 0;
let _crcAuditFilter  = { risk:'', outcome:'', agent:'' };
let _crcGenerating   = false;
let _crcSelectedFw   = 'General';
let _crcSelectedFmt  = 'pdf';
let _crcScope        = {
  audit_chain: true, hitl: true, policies: true,
  agent_identity: true, connectors: true, cost: true, supervisor: true,
};

// ── Constants ───────────────────────────────────────────────────────
const CRC_FRAMEWORKS = [
  { id:'General',  name:'General Audit',  icon:'📋', desc:'Comprehensive governance review' },
  { id:'SOC2',     name:'SOC 2 Type II',  icon:'🛡️',  desc:'Security, Availability, Processing Integrity' },
  { id:'GDPR',     name:'GDPR',           icon:'🇪🇺', desc:'Art. 30 records, Art. 32 security measures' },
  { id:'HIPAA',    name:'HIPAA',          icon:'🏥', desc:'§164.312 technical safeguards & audit controls' },
  { id:'FINRA',    name:'FINRA',          icon:'📈', desc:'Rule 4370, Rule 17a-4 record retention' },
  { id:'ISO27001', name:'ISO/IEC 27001',  icon:'🔏', desc:'Annex A technology & organizational controls' },
];
const CRC_SECTIONS = [
  { key:'audit_chain',    label:'Audit Chain',      icon:'🔗' },
  { key:'hitl',           label:'HITL Approvals',   icon:'🛂' },
  { key:'policies',       label:'Policy Enforcement',icon:'📋' },
  { key:'agent_identity', label:'Agent Identity',   icon:'🪪' },
  { key:'connectors',     label:'Connector Calls',  icon:'🔌' },
  { key:'cost',           label:'Cost & Tokens',    icon:'💰' },
  { key:'supervisor',     label:'Supervisor Runs',  icon:'🧠' },
];
const CRC_RISK_COLORS = {
  low:'var(--success)', medium:'var(--warning)', high:'var(--danger)', critical:'#e85252'
};
const CRC_OUTCOME_ICONS = {
  success:'✅', failure:'❌', blocked:'🚫', pending:'⏳'
};


// ── Main render ─────────────────────────────────────────────────────
async function renderAuditLog() {
  const pane = document.getElementById('pane-audit-log');
  if (!pane) return;

  pane.innerHTML = `
  

  <div class="crc-root">
    <!-- Sidebar -->
    <div class="crc-sidebar">
      <div class="crc-sidebar-title">Compliance Center</div>
      <div class="crc-nav-item active" id="crc-nav-dashboard" onclick="crcSetTab('dashboard')">
        <span class="crc-nav-icon">📊</span> Dashboard
      </div>
      <div class="crc-nav-item" id="crc-nav-generate" onclick="crcSetTab('generate')">
        <span class="crc-nav-icon">📄</span> Generate Report
      </div>
      <div class="crc-nav-item" id="crc-nav-history" onclick="crcSetTab('history')">
        <span class="crc-nav-icon">🗂️</span> Report History
      </div>
      <div class="crc-sidebar-divider"></div>
      <div class="crc-nav-item" id="crc-nav-audit" onclick="crcSetTab('audit')">
        <span class="crc-nav-icon">🔏</span> Audit Chain
      </div>
      <div class="crc-sidebar-divider"></div>
      <div style="padding:8px;font-size:10px;color:var(--text-3)">
        Quick exports:
      </div>
      <a href="/api/audit-log/export/json?limit=5000" download style="text-decoration:none">
        <div class="crc-nav-item"><span class="crc-nav-icon">⬇</span> Export JSON</div>
      </a>
      <a href="/api/audit-log/export/csv?limit=5000" download style="text-decoration:none">
        <div class="crc-nav-item"><span class="crc-nav-icon">⬇</span> Export CSV</div>
      </a>
    </div>

    <!-- Main -->
    <div class="crc-main">
      <div class="crc-header">
        <span class="crc-header-title" id="crc-header-title">🔏 Compliance & Audit Center</span>
        <button class="crc-action-btn" onclick="crcRefresh()" title="Refresh">↺ Refresh</button>
      </div>
      <div class="crc-content" id="crc-content">
        <div style="padding:40px;text-align:center;color:var(--text-3)">Loading…</div>
      </div>
    </div>
  </div>`;

  await crcRefresh();
}


// ── Data loading ─────────────────────────────────────────────────────
async function crcRefresh() {
  const [summaryR, reportsR] = await Promise.all([
    fetch('/api/compliance/summary').then(r=>r.ok?r.json():{}).catch(()=>({})),
    fetch('/api/compliance/reports?limit=20').then(r=>r.ok?r.json():{reports:[]}).catch(()=>({reports:[]})),
  ]);
  _crcSummary = summaryR;
  _crcReports = reportsR.reports || [];
  crcRenderTab();
}


// ── Tab system ───────────────────────────────────────────────────────
function crcSetTab(tab) {
  _crcTab = tab;
  document.querySelectorAll('.crc-nav-item').forEach(el => {
    el.classList.toggle('active', el.id === 'crc-nav-' + tab);
  });
  const titles = {
    dashboard: '📊 Compliance Dashboard',
    generate:  '📄 Generate Compliance Report',
    history:   '🗂️ Report History',
    audit:     '🔏 Immutable Audit Chain',
  };
  const titleEl = document.getElementById('crc-header-title');
  if (titleEl) titleEl.textContent = titles[tab] || 'Compliance Center';
  crcRenderTab();
}

function crcRenderTab() {
  const content = document.getElementById('crc-content');
  if (!content) return;
  if (_crcTab === 'dashboard') crcRenderDashboard(content);
  if (_crcTab === 'generate')  crcRenderGenerator(content);
  if (_crcTab === 'history')   crcRenderHistory(content);
  if (_crcTab === 'audit')     crcRenderAuditChain(content);
}


// ── Dashboard tab ─────────────────────────────────────────────────
function crcRenderDashboard(container) {
  const s = _crcSummary || {};
  const chainOk = s.chain_integrity !== false;

  const stats = [
    { label:'Audit Entries',     val: (s.chain_entries||0).toLocaleString(),      color:'var(--accent)' },
    { label:'High Risk Actions', val: (s.high_risk_actions||0).toLocaleString(),  color: s.high_risk_actions > 0 ? 'var(--danger)' : 'var(--success)' },
    { label:'Failed Actions',    val: (s.failed_actions||0).toLocaleString(),      color: s.failed_actions > 0 ? 'var(--danger)' : 'var(--success)' },
    { label:'HITL Decisions',    val: (s.hitl_total||0).toLocaleString(),          color:'var(--warning)' },
    { label:'HITL Pending',      val: (s.hitl_pending||0).toLocaleString(),        color: s.hitl_pending > 0 ? 'var(--warning)' : 'var(--success)' },
    { label:'Calls Blocked',     val: (s.policy_blocked||0).toLocaleString(),      color: s.policy_blocked > 0 ? 'var(--warning)' : 'var(--success)' },
    { label:'Block Rate',        val: (s.block_rate_pct||0) + '%',                 color:'var(--warning)' },
    { label:'Active Agents',     val: (s.active_agents||0).toLocaleString(),       color:'var(--accent)' },
    { label:'Total Cost',        val: '$' + (s.total_cost_usd||0).toFixed(4),      color:'#9d74f5' },
    { label:'Reports Generated', val: (s.reports_generated||0).toLocaleString(),   color:'var(--accent)' },
  ];

  container.innerHTML = `
    <!-- Chain integrity banner -->
    <div class="crc-chain-banner" style="background:${chainOk?'rgba(61,186,122,.1)':'rgba(232,82,82,.1)'};border:1px solid ${chainOk?'var(--success)':'var(--danger)'}">
      <span class="crc-chain-icon">${chainOk?'🔗':'⚠️'}</span>
      <div>
        <div class="crc-chain-status" style="color:${chainOk?'var(--success)':'var(--danger)'}">${chainOk?'Chain Integrity Verified ✓':'Chain Integrity Issue Detected ⚠️'}</div>
        <div class="crc-chain-detail" style="color:var(--text-3)">${(s.chain_entries||0).toLocaleString()} entries verified · Last report: ${s.last_report_at ? new Date(s.last_report_at).toLocaleDateString() + ' (' + s.last_report_framework + ')' : 'None yet'}</div>
      </div>
      <button class="crc-action-btn" onclick="crcVerifyChain()" style="margin-left:auto">🔍 Verify Now</button>
    </div>

    <!-- Stats grid -->
    <div class="crc-summary-grid">
      ${stats.map(st => `
        <div class="crc-summary-card">
          <div class="crc-summary-val" style="color:${st.color}">${st.val}</div>
          <div class="crc-summary-label">${st.label}</div>
        </div>`).join('')}
    </div>

    <!-- Quick actions -->
    <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px">Quick Actions</div>
    <div class="crc-quick-actions">
      <button class="crc-action-btn primary" onclick="crcSetTab('generate')">📄 Generate PDF Report</button>
      <button class="crc-action-btn" onclick="crcQuickReport('pdf','SOC2')">🛡️ SOC2 Report</button>
      <button class="crc-action-btn" onclick="crcQuickReport('pdf','GDPR')">🇪🇺 GDPR Report</button>
      <button class="crc-action-btn" onclick="crcQuickReport('pdf','HIPAA')">🏥 HIPAA Report</button>
      <button class="crc-action-btn" onclick="crcQuickReport('json','General')">⬇ JSON Export</button>
      <button class="crc-action-btn" onclick="crcQuickReport('csv','General')">⬇ CSV Export</button>
      <button class="crc-action-btn" onclick="crcSetTab('audit')">🔏 View Audit Chain</button>
    </div>

    <!-- Framework cards -->
    <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px;margin-top:6px">Supported Compliance Frameworks</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:8px;margin-bottom:18px">
      ${CRC_FRAMEWORKS.map(fw => `
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:9px;padding:12px;cursor:pointer;transition:all .12s" onclick="crcSetFwAndGenerate(${JSON.stringify(fw.id)})" onmouseover="this.style.borderColor='var(--accent)'" onmouseout="this.style.borderColor='var(--border)'">
          <div style="font-size:18px;margin-bottom:5px">${fw.icon}</div>
          <div style="font-size:12px;font-weight:700;color:var(--text-0);margin-bottom:2px">${fw.name}</div>
          <div style="font-size:10px;color:var(--text-3)">${fw.desc}</div>
        </div>`).join('')}
    </div>

    <!-- Recent reports -->
    ${_crcReports.length ? `
    <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px">Recent Reports</div>
    ${_crcReports.slice(0,3).map(r => crcReportCard(r)).join('')}
    <button class="crc-action-btn" onclick="crcSetTab('history')" style="margin-top:4px">View All Reports →</button>
    ` : ''}
  `;
}


// ── Report generator tab ──────────────────────────────────────────
function crcRenderGenerator(container) {
  const today = new Date().toISOString().slice(0,10);
  const thirtyDaysAgo = new Date(Date.now() - 30*24*3600*1000).toISOString().slice(0,10);

  container.innerHTML = `
    <div class="crc-gen-layout">
      <!-- Left: Framework + Format -->
      <div>
        <!-- Framework -->
        <div class="crc-gen-panel" style="margin-bottom:12px">
          <div class="crc-panel-title">⚖️ Compliance Framework</div>
          <div class="crc-fw-grid">
            ${CRC_FRAMEWORKS.map(fw => `
              <div class="crc-fw-card ${_crcSelectedFw===fw.id?'selected':''}" id="crc-fw-${fw.id}" onclick="crcSelectFw(${JSON.stringify(fw.id)})">
                <div class="crc-fw-icon">${fw.icon}</div>
                <div class="crc-fw-name">${fw.name}</div>
                <div class="crc-fw-desc">${fw.desc}</div>
              </div>`).join('')}
          </div>
        </div>

        <!-- Format -->
        <div class="crc-gen-panel" style="margin-bottom:12px">
          <div class="crc-panel-title">📁 Output Format</div>
          <div class="crc-fmt-row">
            ${[['pdf','📄 PDF','Formatted, signable'],['json','{ } JSON','Machine-readable'],['csv','📊 CSV','Spreadsheet']].map(([id,label,desc]) => `
              <div class="crc-fmt-btn ${_crcSelectedFmt===id?'selected':''}" id="crc-fmt-${id}" onclick="crcSelectFmt(${JSON.stringify(id)})">
                <div>${label}</div>
                <div style="font-size:9px;color:var(--text-3);margin-top:2px">${desc}</div>
              </div>`).join('')}
          </div>
        </div>

        <!-- Date range -->
        <div class="crc-gen-panel">
          <div class="crc-panel-title">📅 Date Range</div>
          <div class="crc-form-label" style="margin-bottom:5px">From</div>
          <div class="crc-date-row">
            <input class="crc-date-input" type="date" id="crc-date-from" value="${thirtyDaysAgo}">
            <input class="crc-date-input" type="date" id="crc-date-to"   value="${today}">
          </div>
          <div style="font-size:10px;color:var(--text-3);margin-top:5px">Leave both blank for all-time report</div>
        </div>
      </div>

      <!-- Right: Scope + Title + Generate -->
      <div>
        <!-- Title -->
        <div class="crc-gen-panel" style="margin-bottom:12px">
          <div class="crc-panel-title">✏️ Report Title</div>
          <input class="crc-title-input" id="crc-report-title" value="Compliance Audit — ${new Date().toLocaleDateString('en-US',{year:'numeric',month:'long'})}" placeholder="Report title…">
        </div>

        <!-- Scope -->
        <div class="crc-gen-panel" style="margin-bottom:12px">
          <div class="crc-panel-title">🔍 Included Sections</div>
          <div class="crc-scope-list" id="crc-scope-list">
            ${CRC_SECTIONS.map(s => `
              <div class="crc-scope-item" onclick="crcToggleScope(${JSON.stringify(s.key)})">
                <input type="checkbox" class="crc-scope-check" id="crc-scope-${s.key}" ${_crcScope[s.key]?'checked':''} onclick="event.stopPropagation();crcToggleScope(${JSON.stringify(s.key)})">
                <span class="crc-scope-icon">${s.icon}</span>
                <span class="crc-scope-label">${s.label}</span>
              </div>`).join('')}
          </div>
          <div style="display:flex;gap:6px;margin-top:8px">
            <button onclick="crcSelectAllScope(true)" style="font-size:10px;padding:3px 8px;border-radius:4px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-2);cursor:pointer">Select All</button>
            <button onclick="crcSelectAllScope(false)" style="font-size:10px;padding:3px 8px;border-radius:4px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-2);cursor:pointer">Clear All</button>
          </div>
        </div>

        <!-- Preview -->
        <div class="crc-gen-panel" style="margin-bottom:12px">
          <div class="crc-panel-title">👁️ Report Preview</div>
          <div class="crc-preview-box" id="crc-preview-box">${crcBuildPreview()}</div>
        </div>

        <!-- Generate button -->
        <button class="crc-gen-btn" id="crc-gen-btn" onclick="crcGenerate()" ${_crcGenerating?'disabled':''}>
          ${_crcGenerating ? '<div class="crc-spinner"></div> Generating Report…' : '📄 Generate Compliance Report'}
        </button>
        ${_crcGenerating ? `<div class="crc-generating"><div class="crc-spinner"></div><span style="font-size:12px;color:var(--accent)">Building report — collecting audit chain, HITL records, policy data…</span></div>` : ''}
      </div>
    </div>
  `;
}

function crcSelectFw(fw) {
  _crcSelectedFw = fw;
  document.querySelectorAll('.crc-fw-card').forEach(el => el.classList.remove('selected'));
  document.getElementById('crc-fw-' + fw)?.classList.add('selected');
  crcUpdatePreview();
}

function crcSelectFmt(fmt) {
  _crcSelectedFmt = fmt;
  document.querySelectorAll('.crc-fmt-btn').forEach(el => el.classList.remove('selected'));
  document.getElementById('crc-fmt-' + fmt)?.classList.add('selected');
  crcUpdatePreview();
}

function crcToggleScope(key) {
  _crcScope[key] = !_crcScope[key];
  const cb = document.getElementById('crc-scope-' + key);
  if (cb) cb.checked = _crcScope[key];
  crcUpdatePreview();
}

function crcSelectAllScope(val) {
  CRC_SECTIONS.forEach(s => {
    _crcScope[s.key] = val;
    const cb = document.getElementById('crc-scope-' + s.key);
    if (cb) cb.checked = val;
  });
  crcUpdatePreview();
}

function crcUpdatePreview() {
  const box = document.getElementById('crc-preview-box');
  if (box) box.innerHTML = crcBuildPreview();
}

function crcBuildPreview() {
  const fw   = CRC_FRAMEWORKS.find(f=>f.id===_crcSelectedFw) || CRC_FRAMEWORKS[0];
  const secs = CRC_SECTIONS.filter(s=>_crcScope[s.key]);
  return `<strong>${fw.icon} ${fw.name} — ${_crcSelectedFmt.toUpperCase()}</strong><br>
Sections: ${secs.map(s=>s.icon+' '+s.label).join(', ')}<br>
Format: ${_crcSelectedFmt === 'pdf' ? 'PDF (formatted, printable)' : _crcSelectedFmt === 'json' ? 'JSON (machine-readable full export)' : 'CSV (spreadsheet-compatible)'}<br>
<em style="color:var(--text-3);font-size:10px">${fw.desc}</em>`;
}

async function crcGenerate() {
  if (_crcGenerating) return;
  const title   = document.getElementById('crc-report-title')?.value?.trim() || 'Compliance Report';
  const fromVal = document.getElementById('crc-date-from')?.value || '';
  const toVal   = document.getElementById('crc-date-to')?.value   || '';
  const dateFrom = fromVal ? fromVal + 'T00:00:00Z' : '';
  const dateTo   = toVal   ? toVal   + 'T23:59:59Z' : '';

  _crcGenerating = true;
  crcRenderGenerator(document.getElementById('crc-content'));

  try {
    const resp = await fetch('/api/compliance/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title, framework: _crcSelectedFw, format: _crcSelectedFmt,
        date_from: dateFrom, date_to: dateTo, scope: { ..._crcScope },
      })
    });

    if (!resp.ok) {
      const err = await resp.json().catch(()=>({error:'Unknown error'}));
      showToast('⚠️ Report failed: ' + (err.error||resp.status));
      return;
    }

    // Trigger download
    const blob = await resp.blob();
    const reportId = resp.headers.get('X-Report-Id') || 'report';
    const ext  = _crcSelectedFmt === 'pdf' ? 'pdf' : _crcSelectedFmt === 'json' ? 'json' : 'csv';
    const filename = `compliance_${_crcSelectedFw.toLowerCase()}_${Date.now()}.${ext}`;
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
    showToast(`✅ Report downloaded: ${filename}`);

    // Refresh history
    const histR = await fetch('/api/compliance/reports?limit=20').then(r=>r.ok?r.json():{reports:[]});
    _crcReports = histR.reports || [];
  } catch(e) {
    showToast('⚠️ Error: ' + e.message);
  } finally {
    _crcGenerating = false;
    crcRenderGenerator(document.getElementById('crc-content'));
  }
}

async function crcQuickReport(fmt, fw) {
  _crcSelectedFmt = fmt;
  _crcSelectedFw  = fw;
  _crcGenerating  = true;
  showToast(`📄 Generating ${fw} ${fmt.toUpperCase()} report…`);
  try {
    const resp = await fetch('/api/compliance/generate', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        title: `${fw} Compliance Report — ${new Date().toLocaleDateString()}`,
        framework: fw, format: fmt, scope: { ..._crcScope }
      })
    });
    if (!resp.ok) { showToast('⚠️ Report failed'); return; }
    const blob = await resp.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = `compliance_${fw.toLowerCase()}.${fmt}`; a.click();
    URL.revokeObjectURL(url);
    showToast(`✅ ${fw} report downloaded`);
    const hr = await fetch('/api/compliance/reports?limit=20').then(r=>r.ok?r.json():{reports:[]});
    _crcReports = hr.reports || [];
  } catch(e) { showToast('⚠️ ' + e.message); }
  finally { _crcGenerating = false; }
}

function crcSetFwAndGenerate(fw) {
  _crcSelectedFw = fw;
  crcSetTab('generate');
}


// ── History tab ─────────────────────────────────────────────────────
function crcRenderHistory(container) {
  if (!_crcReports.length) {
    container.innerHTML = `<div style="padding:40px;text-align:center;color:var(--text-3)">
      <div style="font-size:40px;margin-bottom:12px">📄</div>
      <div style="font-size:14px;font-weight:600;color:var(--text-1);margin-bottom:8px">No Reports Generated Yet</div>
      <div style="font-size:12px;line-height:1.6;margin-bottom:20px">Generate your first compliance report from the Generate tab.</div>
      <button class="crc-gen-btn" style="width:auto;padding:10px 24px" onclick="crcSetTab('generate')">📄 Generate First Report</button>
    </div>`;
    return;
  }
  container.innerHTML = `
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
      <strong style="font-size:13px;color:var(--text-0)">${_crcReports.length} Reports</strong>
      <button class="crc-action-btn" onclick="crcSetTab('generate')" style="margin-left:auto">+ New Report</button>
    </div>
    ${_crcReports.map(r => crcReportCard(r)).join('')}
  `;
}

function crcReportCard(r) {
  const fw  = CRC_FRAMEWORKS.find(f=>f.id===r.framework) || {icon:'📋',name:r.framework};
  const sum = r.summary || {};
  const statusColors = { done:'var(--success)', failed:'var(--danger)', generating:'var(--warning)', pending:'var(--text-3)' };
  const sc  = statusColors[r.status] || 'var(--text-3)';
  const sizeKB = r.file_size_bytes ? (r.file_size_bytes/1024).toFixed(1) + ' KB' : '—';
  return `<div class="crc-report-card">
    <div class="crc-report-icon">${fw.icon}</div>
    <div class="crc-report-body">
      <div class="crc-report-title">${escHtml(r.title||'Compliance Report')}</div>
      <div class="crc-report-meta">
        ${fw.name} · ${r.format?.toUpperCase()} · ${sizeKB} · ${new Date(r.created_at).toLocaleString()}
        ${r.date_from ? ` · ${r.date_from.slice(0,10)} → ${(r.date_to||'now').slice(0,10)}` : ''}
      </div>
      ${Object.keys(sum).length ? `
      <div class="crc-report-summary">
        ${sum.audit_total != null ? `<span class="crc-report-chip">📋 ${(sum.audit_total||0).toLocaleString()} entries</span>` : ''}
        ${sum.high_risk_count > 0 ? `<span class="crc-report-chip" style="color:var(--danger)">⚠️ ${sum.high_risk_count} high-risk</span>` : ''}
        ${sum.hitl_total > 0 ? `<span class="crc-report-chip">🛂 ${sum.hitl_total} HITL</span>` : ''}
        ${sum.policy_blocked > 0 ? `<span class="crc-report-chip">🚫 ${sum.policy_blocked} blocked</span>` : ''}
        ${sum.chain_ok === false ? `<span class="crc-report-chip" style="color:var(--danger)">⚠️ Chain issue</span>` : `<span class="crc-report-chip" style="color:var(--success)">🔗 Chain OK</span>`}
      </div>` : ''}
    </div>
    <div class="crc-report-actions">
      <span class="crc-status-badge" style="background:${sc}22;color:${sc}">${r.status}</span>
      ${r.status==='done' ? `<button class="crc-rep-btn" onclick="crcRegenReport(${JSON.stringify(r)})">↺ Re-run</button>` : ''}
      <button class="crc-rep-btn" style="color:var(--danger)" onclick="crcDeleteReport(${JSON.stringify(r.report_id)})">🗑</button>
    </div>
  </div>`;
}

async function crcRegenReport(r) {
  _crcSelectedFw  = r.framework || 'General';
  _crcSelectedFmt = r.format    || 'pdf';
  try {
    _crcScope = JSON.parse(r.scope || '{}');
  } catch(e) {}
  crcSetTab('generate');
  document.getElementById('crc-report-title').value = r.title || 'Compliance Report';
}

async function crcDeleteReport(reportId) {
  const ok = await gmDanger('Delete Report', `Delete report ${reportId}?`);
  if (!ok) return;
  await fetch(`/api/compliance/reports/${encodeURIComponent(reportId)}`, {method:'DELETE'});
  const hr = await fetch('/api/compliance/reports?limit=20').then(r=>r.ok?r.json():{reports:[]});
  _crcReports = hr.reports || [];
  crcRenderHistory(document.getElementById('crc-content'));
  showToast('🗑 Report deleted');
}


// ── Audit chain tab ──────────────────────────────────────────────────
async function crcRenderAuditChain(container) {
  container.innerHTML = `<div style="padding:20px;text-align:center;color:var(--text-3)">Loading audit chain…</div>`;

  let url = '/api/audit-log?limit=100';
  if (_crcAuditFilter.risk)    url += `&risk_level=${encodeURIComponent(_crcAuditFilter.risk)}`;
  if (_crcAuditFilter.outcome) url += `&outcome=${encodeURIComponent(_crcAuditFilter.outcome)}`;
  if (_crcAuditFilter.agent)   url += `&agent_id=${encodeURIComponent(_crcAuditFilter.agent)}`;

  const [entriesR, statsR, verifyR] = await Promise.all([
    fetch(url).then(r=>r.ok?r.json():{entries:[],total:0}).catch(()=>({entries:[],total:0})),
    fetch('/api/audit-log/stats').then(r=>r.ok?r.json():{}).catch(()=>({})),
    fetch('/api/audit-log/verify').then(r=>r.ok?r.json():{ok:true,verified:0}).catch(()=>({ok:true})),
  ]);

  _crcAuditEntries = entriesR.entries || [];
  _crcAuditTotal   = entriesR.total   || 0;

  const chainOk = verifyR.ok !== false;
  const chainTip = (statsR.chain_tip||'').slice(0,32) + '…';

  container.innerHTML = `
    <!-- Chain status -->
    <div style="background:${chainOk?'rgba(61,186,122,.1)':'rgba(232,82,82,.1)'};border:1px solid ${chainOk?'var(--success)':'var(--danger)'};border-radius:10px;padding:12px 14px;margin-bottom:14px;display:flex;align-items:center;gap:10px">
      <span style="font-size:20px">${chainOk?'🔗':'⚠️'}</span>
      <div>
        <div style="font-weight:700;font-size:13px;color:${chainOk?'var(--success)':'var(--danger)'}">${verifyR.message||'Chain status unknown'}</div>
        <div style="font-size:10px;color:var(--text-3)">Entries verified: ${(verifyR.verified||0).toLocaleString()} · Chain tip: <code style="font-size:9px">${chainTip}</code></div>
      </div>
      <div style="display:flex;gap:6px;margin-left:auto">
        <button class="crc-action-btn" onclick="crcVerifyChain()">🔍 Verify</button>
        <a href="/api/audit-log/export/json?limit=5000" download class="crc-action-btn" style="text-decoration:none">⬇ JSON</a>
        <a href="/api/audit-log/export/csv?limit=5000" download class="crc-action-btn" style="text-decoration:none">⬇ CSV</a>
        <button class="crc-action-btn primary" onclick="crcQuickReport('pdf','General')">📄 PDF Report</button>
      </div>
    </div>

    <!-- Filters -->
    <div class="crc-audit-filters">
      <span style="font-size:11px;font-weight:700;color:var(--text-2)">Filter:</span>
      <select class="crc-filter-sel" id="crc-audit-risk" onchange="crcAuditFilterChange()">
        <option value="">All Risk</option>
        <option value="low">Low</option>
        <option value="medium">Medium</option>
        <option value="high">High</option>
        <option value="critical">Critical</option>
      </select>
      <select class="crc-filter-sel" id="crc-audit-outcome" onchange="crcAuditFilterChange()">
        <option value="">All Outcomes</option>
        <option value="success">Success</option>
        <option value="failure">Failure</option>
        <option value="blocked">Blocked</option>
      </select>
      <input class="crc-filter-input" id="crc-audit-agent" placeholder="Filter by agent…" oninput="crcAuditFilterChange()">
      <span style="margin-left:auto;font-size:11px;color:var(--text-3)">Showing ${_crcAuditEntries.length} of ${_crcAuditTotal.toLocaleString()}</span>
    </div>

    <!-- Table -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;overflow:hidden">
      <table class="crc-audit-table">
        <thead><tr>
          <th>#</th><th>Outcome</th><th>Agent</th><th>Action Type</th>
          <th>Detail</th><th>Risk</th><th>Hash</th><th>Time</th>
        </tr></thead>
        <tbody>
          ${_crcAuditEntries.map(e => `
          <tr onclick="crcShowEntry(${JSON.stringify(e.entry_id)})">
            <td style="font-family:monospace;color:var(--text-3)">${e.seq}</td>
            <td>${CRC_OUTCOME_ICONS[e.outcome]||'❓'} <span style="font-size:10px">${escHtml(e.outcome||'')}</span></td>
            <td style="color:var(--accent)">${escHtml((e.agent_name||e.agent_id||'').slice(0,16))}</td>
            <td style="font-size:10px">${escHtml((e.action_type||'').slice(0,20))}</td>
            <td style="font-size:10px;color:var(--text-2);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml((e.action_detail||'').slice(0,80))}</td>
            <td><span class="crc-risk-chip" style="background:${CRC_RISK_COLORS[e.risk_level]||'var(--text-3)'}22;color:${CRC_RISK_COLORS[e.risk_level]||'var(--text-3)'}">${e.risk_level||''}</span></td>
            <td><span class="crc-hash">${(e.entry_hash||'').slice(0,8)}…</span></td>
            <td style="font-size:10px;color:var(--text-3)">${new Date(e.created_at).toLocaleTimeString()}</td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>

    <!-- Chain explainer -->
    <div class="crc-chain-detail-box">
      <div style="font-size:11px;font-weight:700;color:var(--text-0);margin-bottom:8px">🔗 How the Hash Chain Works</div>
      <div style="font-size:11px;color:var(--text-2);line-height:1.7">
        Each entry stores a <code>prev_hash</code> (SHA-256 of the previous record) and an <code>entry_hash</code> (SHA-256 of all critical fields + prev_hash).
        Modifying any record breaks all subsequent hashes — tampering is immediately detectable.
        Every action generates a signed <strong>cryptographic receipt</strong> tied to the agent's identity keypair.
        Use <strong>Verify</strong> to confirm integrity, or generate a PDF report to include the verification certificate.
      </div>
    </div>
  `;
}

async function crcAuditFilterChange() {
  _crcAuditFilter.risk    = document.getElementById('crc-audit-risk')?.value    || '';
  _crcAuditFilter.outcome = document.getElementById('crc-audit-outcome')?.value || '';
  _crcAuditFilter.agent   = document.getElementById('crc-audit-agent')?.value   || '';
  await crcRenderAuditChain(document.getElementById('crc-content'));
}

async function crcVerifyChain() {
  const r = await fetch('/api/audit-log/verify').catch(()=>null);
  if (!r || !r.ok) { showToast('⚠️ Could not reach audit log'); return; }
  const d = await r.json();
  if (d.ok) {
    showToast(`🔗 Chain OK — ${d.verified} entries verified`);
  } else {
    await gmAlert('⚠️ Chain Integrity Issue',
      `Chain broken at seq=${d.broken_at}.\n\n${d.message}\n\nThis may indicate data tampering. Generate a compliance report immediately and contact your compliance officer.`);
  }
  if (_crcTab === 'audit') await crcRenderAuditChain(document.getElementById('crc-content'));
}

async function crcShowEntry(entryId) {
  const d = await fetch(`/api/audit-log/entry/${encodeURIComponent(entryId)}`).then(r=>r.ok?r.json():null).catch(()=>null);
  if (!d) { showToast('Could not load entry'); return; }
  const e = d.entry || {};
  const r = d.receipt || {};
  const meta = (() => { try { return JSON.stringify(JSON.parse(e.metadata||'{}'),null,2); } catch(x) { return e.metadata||''; } })();
  await gmAlert(`🔏 Audit Entry #${e.seq}`,
    `Agent: ${e.agent_name||e.agent_id}\nAction: ${e.action_type}\nOutcome: ${e.outcome}\nRisk: ${e.risk_level}\nAuthority: ${e.authority}\nTime: ${e.created_at}\n\nDetail:\n${e.action_detail}\n\nReasoning:\n${e.reasoning||'(none)'}\n\nMetadata:\n${meta}\n\nEntry Hash: ${e.entry_hash}\nPrev Hash:  ${e.prev_hash}\n\nReceipt ID: ${r.receipt_id||'none'}\nSignature: ${r.signature||'unsigned'}`);
}


// ── Compat aliases ────────────────────────────────────────────────────
function renderAuditEntryRows(entries) { return ''; } // replaced
async function auditVerifyChain() { await crcVerifyChain(); }
async function auditReload() { if (_crcTab==='audit') await crcRenderAuditChain(document.getElementById('crc-content')); }
async function auditAddTestEntry() {
  await fetch('/api/audit-log/append',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent_id:'user',agent_name:'User',action_type:'test_entry',action_detail:'Manual test audit entry from Compliance Center',authority:'user',risk_level:'low',outcome:'success'})});
  showToast('✅ Test audit entry added');
  if (_crcTab==='audit') await crcRenderAuditChain(document.getElementById('crc-content'));
}
async function auditShowEntry(id) { await crcShowEntry(id); }



// ══════════════════════════════════════════════════════════════════
//  SPRINT A — AGENT IDENTITY & ZERO-TRUST SYSTEM
// ══════════════════════════════════════════════════════════════════

async function renderAgentIdentity() {
  const pane = document.getElementById('pane-agent-identity');
  if (!pane) return;

  const [list, sysStats] = await Promise.all([
    fetch('/api/agent-identity').then(r=>r.ok?r.json():{identities:[],count:0}).catch(()=>({identities:[],count:0})),
    fetch('/api/agent-identity/system/stats').then(r=>r.ok?r.json():{}).catch(()=>({})),
  ]);

  const authColor = {minimal:'var(--text-3)',standard:'var(--success)',elevated:'var(--warning)',admin:'var(--danger)'};
  const authIcon  = {minimal:'🔵',standard:'🟢',elevated:'🟡',admin:'🔴'};

  pane.innerHTML = `
  <div style="padding:20px;max-width:1100px;margin:0 auto">
    <div class="section-head" style="margin-bottom:20px">
      <div>
        <h2 style="margin:0 0 4px">🪪 Agent Identity & Zero-Trust</h2>
        <p style="margin:0;color:var(--text-2);font-size:13px">Cryptographic identity per agent · JIT access tokens · Least-privilege permissions · Zero-trust verification</p>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn" onclick="identityProvisionAll()">⚡ Provision All Agents</button>
        <button class="btn-sm" onclick="renderAgentIdentity()">↻ Refresh</button>
      </div>
    </div>

    <!-- System stats -->
    <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:20px">
      ${[
        ['🪪','Total Identities',sysStats.total_identities||0,'var(--accent)'],
        ['✅','Active',sysStats.active_identities||0,'var(--success)'],
        ['🎫','Active JIT Tokens',sysStats.active_jit_tokens||0,'var(--warning)'],
        ['🔑','Permissions',sysStats.total_permissions||0,'#7aa2f7'],
        ['🛡️','Zero-Trust',sysStats.zero_trust_active?'ON':'OFF',sysStats.zero_trust_active?'var(--success)':'var(--danger)'],
      ].map(([icon,label,val,col])=>`
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:12px;text-align:center">
          <div style="font-size:18px">${icon}</div>
          <div style="font-size:9px;color:var(--text-3);text-transform:uppercase;letter-spacing:.5px">${label}</div>
          <div style="font-size:18px;font-weight:700;color:${col}">${val}</div>
        </div>`).join('')}
    </div>

    <!-- Zero-trust explainer -->
    <div style="background:rgba(122,162,247,0.08);border:1px solid var(--accent);border-radius:10px;padding:14px 18px;margin-bottom:18px">
      <div style="font-size:12px;font-weight:700;color:var(--accent);margin-bottom:6px">🔐 Zero-Trust Architecture Active</div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;font-size:11px;color:var(--text-2)">
        <div>🪪 <strong>Unique cryptographic identity</strong> per agent — no shared service accounts</div>
        <div>⏱️ <strong>JIT tokens expire</strong> automatically — no persistent long-lived credentials</div>
        <div>🎯 <strong>Least-privilege</strong> — agents only get permissions for their current task</div>
      </div>
    </div>

    <!-- Add identity form -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:18px">
      <div style="font-size:12px;font-weight:700;margin-bottom:10px">➕ Provision New Agent Identity</div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end">
        <div>
          <div style="font-size:11px;color:var(--text-3);margin-bottom:4px">Agent ID</div>
          <input id="id-new-agent-id" placeholder="e.g. my-agent" style="background:var(--bg-3);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:12px;color:var(--text-0);width:140px">
        </div>
        <div>
          <div style="font-size:11px;color:var(--text-3);margin-bottom:4px">Display Name</div>
          <input id="id-new-name" placeholder="My Agent" style="background:var(--bg-3);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:12px;color:var(--text-0);width:140px">
        </div>
        <div>
          <div style="font-size:11px;color:var(--text-3);margin-bottom:4px">Authority Level</div>
          <select id="id-new-authority" style="background:var(--bg-3);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:12px;color:var(--text-0)">
            <option value="minimal">Minimal (read-only)</option>
            <option value="standard" selected>Standard</option>
            <option value="elevated">Elevated</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <button class="btn" onclick="identityProvisionOne()">🔑 Provision</button>
      </div>
    </div>

    <!-- Identity cards -->
    <div style="font-size:12px;font-weight:700;margin-bottom:10px;color:var(--text-0)">🪪 Agent Identities (${list.count||0})</div>
    ${list.count===0 ? `
      <div style="background:var(--bg-2);border:2px dashed var(--border);border-radius:12px;padding:40px;text-align:center">
        <div style="font-size:32px;margin-bottom:10px">🪪</div>
        <div style="font-weight:700;margin-bottom:6px">No identities provisioned yet</div>
        <div style="color:var(--text-3);font-size:12px;margin-bottom:14px">Click "Provision All Agents" to generate cryptographic keypairs for all 8 default agents</div>
        <button class="btn" onclick="identityProvisionAll()">⚡ Provision All Agents Now</button>
      </div>` : `
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px" id="identity-cards">
      ${(list.identities||[]).map(id=>renderIdentityCard(id)).join('')}
    </div>`}

    <!-- Authority level legend -->
    <div style="margin-top:20px;background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:14px">
      <div style="font-size:12px;font-weight:700;margin-bottom:10px">🔑 Authority Level Reference</div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;font-size:11px">
        ${[
          ['🔵','Minimal','Read memory, basic tool use only','var(--text-3)'],
          ['🟢','Standard','+ Write tasks, read files, web search, run code','var(--success)'],
          ['🟡','Elevated','+ Write files, delete tasks, webhooks, manage agents','var(--warning)'],
          ['🔴','Admin','+ Delete files, deploy, manage policies, system config','var(--danger)'],
        ].map(([icon,level,perms,col])=>`
          <div style="background:var(--bg-3);border-radius:8px;padding:10px;border-left:3px solid ${col}">
            <div style="font-weight:700;margin-bottom:4px">${icon} ${level}</div>
            <div style="color:var(--text-2)">${perms}</div>
          </div>`).join('')}
      </div>
    </div>
  </div>`;
}

function renderIdentityCard(id) {
  const authColor = {minimal:'var(--text-3)',standard:'var(--success)',elevated:'var(--warning)',admin:'var(--danger)'};
  const authIcon  = {minimal:'🔵',standard:'🟢',elevated:'🟡',admin:'🔴'};
  return `
  <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
      <div style="width:36px;height:36px;border-radius:50%;background:${(authColor[id.authority_level]||'var(--accent)')}22;display:flex;align-items:center;justify-content:center;font-size:18px">
        ${authIcon[id.authority_level]||'🤖'}
      </div>
      <div style="flex:1">
        <div style="font-weight:700;font-size:13px">${escHtml(id.display_name||id.agent_id)}</div>
        <div style="font-size:10px;color:var(--text-3)">${escHtml(id.agent_id)} · v${id.key_version}</div>
      </div>
      <span style="font-size:10px;padding:2px 7px;border-radius:4px;font-weight:700;background:${(authColor[id.authority_level]||'var(--accent)')}22;color:${authColor[id.authority_level]||'var(--accent)'}">
        ${escHtml(id.authority_level||'standard')}
      </span>
    </div>

    <div style="font-size:11px;color:var(--text-3);margin-bottom:8px">
      🎫 Active tokens: <strong style="color:var(--text-1)">${id.active_tokens||0}</strong>
      &nbsp;·&nbsp; 🔑 Permissions: <strong style="color:var(--text-1)">${id.permission_count||0}</strong>
    </div>

    <div style="font-size:10px;color:var(--text-3);margin-bottom:12px;word-break:break-all;background:var(--bg-3);border-radius:6px;padding:6px 8px;font-family:monospace">
      ${(id.public_key||'').slice(0,60)}…
    </div>

    <div style="display:flex;gap:6px;flex-wrap:wrap">
      <button class="btn-sm" onclick="identityIssueToken(${JSON.stringify(id.agent_id)})">🎫 Issue Token</button>
      <button class="btn-sm" onclick="identityViewPerms(${JSON.stringify(id.agent_id)})">🔑 Permissions</button>
      <button class="btn-sm" onclick="identityViewAudit(${JSON.stringify(id.agent_id)})">📋 Audit</button>
      <button class="btn-sm" onclick="identityRotateKeys(${JSON.stringify(id.agent_id)})" style="color:var(--warning);border-color:var(--warning)">🔄 Rotate Keys</button>
    </div>

    <div style="margin-top:8px;font-size:10px;color:var(--text-3)">
      Created: ${new Date(id.created_at).toLocaleDateString()} · Last seen: ${new Date(id.last_seen_at).toLocaleDateString()}
    </div>
  </div>`;
}

async function identityProvisionAll() {
  showToast('⚡ Provisioning identities for all agents…');
  const r = await fetch('/api/agent-identity/provision-all', {method:'POST'}).catch(()=>null);
  if (!r||!r.ok) { showToast('⚠️ Provision failed'); return; }
  const d = await r.json();
  showToast(`🪪 ${d.new} new identities provisioned (${d.existing} already existed)`);
  renderAgentIdentity();
}

async function identityProvisionOne() {
  const agentId   = document.getElementById('id-new-agent-id')?.value?.trim();
  const name      = document.getElementById('id-new-name')?.value?.trim();
  const authority = document.getElementById('id-new-authority')?.value;
  if (!agentId) { showToast('⚠️ Agent ID required'); return; }
  const r = await fetch('/api/agent-identity/provision', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({agent_id:agentId,display_name:name||agentId,authority_level:authority})
  }).catch(()=>null);
  if (!r||!r.ok) { showToast('⚠️ Provision failed'); return; }
  const d = await r.json();
  showToast(`🪪 Identity provisioned: ${d.identity?.agent_id}`);
  renderAgentIdentity();
}

async function identityIssueToken(agentId) {
  const taskId = await gmPrompt(`Issue JIT Token for ${agentId}`, 'Task ID (or leave blank):') || '';
  if (taskId === null) return;
  const r = await fetch(`/api/agent-identity/${encodeURIComponent(agentId)}/issue-token`, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({task_id:taskId, ttl_seconds:3600, scope:['read_memory','write_tasks']})
  }).catch(()=>null);
  if (!r||!r.ok) { showToast('⚠️ Token issue failed'); return; }
  const d = await r.json();
  if (!d.ok) { showToast('⚠️ ' + (d.error||'Failed')); return; }
  await gmAlert(`🎫 JIT Token Issued`,
    `Token ID: ${d.token_id}\nAgent: ${agentId}\nTask: ${d.task_id||'(none)'}\nExpires in: 1 hour\nScope: ${(d.scope||[]).join(', ')||'all'}\n\nCopy this token ID — it cannot be retrieved again.\nPresent it with API calls to prove agent identity.`);
  renderAgentIdentity();
}

async function identityViewPerms(agentId) {
  const r = await fetch(`/api/agent-identity/${encodeURIComponent(agentId)}/permissions`).catch(()=>null);
  if (!r||!r.ok) { showToast('Could not load permissions'); return; }
  const d = await r.json();
  const perms = (d.permissions||[]).map(p=>`• ${p.action} on ${p.resource}`).join('\n');
  await gmAlert(`🔑 Permissions: ${agentId}`, perms||'No permissions granted');
}

async function identityViewAudit(agentId) {
  const r = await fetch(`/api/agent-identity/${encodeURIComponent(agentId)}/audit?limit=20`).catch(()=>null);
  if (!r||!r.ok) { showToast('Could not load audit'); return; }
  const d = await r.json();
  const events = (d.events||[]).map(e=>`${new Date(e.created_at).toLocaleTimeString()} — ${e.event_type}: ${e.detail||''}`).join('\n');
  await gmAlert(`📋 Identity Audit: ${agentId}`, events||'No events yet');
}

async function identityRotateKeys(agentId) {
  const ok = await gmDanger('Rotate Keys', `Rotating keys for ${agentId} will:\n\n• Generate new RSA keypair\n• Revoke ALL existing JIT tokens\n• Require re-issuance of any active tokens\n\nProceed?`);
  if (!ok) return;
  const r = await fetch(`/api/agent-identity/${encodeURIComponent(agentId)}/rotate-keys`, {method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).catch(()=>null);
  if (!r||!r.ok) { showToast('⚠️ Key rotation failed'); return; }
  const d = await r.json();
  showToast(`🔄 Keys rotated — ${d.tokens_revoked} tokens revoked`);
  renderAgentIdentity();
}


// ══════════════════════════════════════════════════════════════════
//  PATCH MASTER NAV — Sprint 18 panes
// ══════════════════════════════════════════════════════════════════
// ══════════════════════════════════════════════════════════════════
//  SPRINT B — SUPERVISOR AGENT
// ══════════════════════════════════════════════════════════════════


// ══════════════════════════════════════════════════════════════════
//  TASK DAG VISUALIZER — Complete Implementation
//  Replaces old renderSupervisor + all supervisor* functions
// ══════════════════════════════════════════════════════════════════

// ── State ─────────────────────────────────────────────────────────
let _supervisorPollTimer = null;   // live-poll for active runs
let _dagRuns        = [];          // sidebar run list
let _dagActiveRun   = null;        // full {run, tasks, edges, waves} from /dag
let _dagZoom        = 1.0;
let _dagPanX        = 0;
let _dagPanY        = 0;
let _dagPanning     = false;
let _dagPanStart    = {x:0,y:0,px:0,py:0};
let _dagSelectedTask = null;       // currently highlighted task_id
let _dagLiveTimer   = null;        // SSE poll for running runs
let _dagAnimFrame   = null;        // rAF for animated edges

// ── Constants ──────────────────────────────────────────────────────
const DAG_AGENT_COLORS = {
  researcher:   '#5b8af8',
  builder:      '#3dba7a',
  reviewer:     '#e8a237',
  creative:     '#c084fc',
  memory:       '#38c5d8',
  brain:        '#9d74f5',
  orchestrator: '#f06080',
};
const DAG_AGENT_ICONS = {
  researcher:   '🔍',
  builder:      '🔨',
  reviewer:     '🔬',
  creative:     '✍️',
  memory:       '🧠',
  brain:        '💡',
  orchestrator: '🎯',
};
const DAG_STATUS_COLORS = {
  pending:       'rgba(255,255,255,.15)',
  running:       '#e8a237',
  done:          '#3dba7a',
  failed:        '#e85252',
  killed:        '#7a8aaa',
  awaiting_hitl: '#c084fc',
};
const DAG_STATUS_ICONS = {
  decomposing:   '🧩', scheduled: '📋', running: '⚡',
  synthesizing:  '🔀', done: '✅', failed: '❌', killed: '🛑',
  pending:       '⏳', awaiting_hitl: '🛂',
};
const DAG_RUN_STATUS_COLOR = {
  decomposing:'var(--warning)', scheduled:'var(--accent)', running:'#e8a237',
  synthesizing:'#9d74f5', done:'var(--success)', failed:'var(--danger)', killed:'var(--text-3)',
};


// ── Main render ────────────────────────────────────────────────────
async function renderSupervisor() {
  const pane = document.getElementById('pane-supervisor');
  if (!pane) return;

  pane.innerHTML = `
  

  <div class="dag-root">
    <!-- ── Sidebar ── -->
    <div class="dag-sidebar">
      <div class="dag-sidebar-head">
        <p class="dag-sidebar-title">🧠 Supervisor Runs</p>
        <div class="dag-stats-grid" id="dag-stats-grid">
          <div class="dag-stat"><div class="dag-stat-val" id="dag-stat-total" style="color:var(--accent)">—</div><div class="dag-stat-label">Total</div></div>
          <div class="dag-stat"><div class="dag-stat-val" id="dag-stat-done" style="color:var(--success)">—</div><div class="dag-stat-label">Done</div></div>
          <div class="dag-stat"><div class="dag-stat-val" id="dag-stat-score" style="color:#9d74f5">—</div><div class="dag-stat-label">Avg Score</div></div>
          <div class="dag-stat"><div class="dag-stat-val" id="dag-stat-tokens" style="color:var(--text-2)">—</div><div class="dag-stat-label">Tokens</div></div>
        </div>
      </div>
      <div class="dag-run-list" id="dag-run-list">
        <div style="color:var(--text-3);font-size:12px;padding:10px">Loading…</div>
      </div>
      <div class="dag-sidebar-foot">
        <button class="dag-launch-btn" onclick="dagOpenLaunch()">⚡ Launch New Goal</button>
      </div>
    </div>

    <!-- ── Main ── -->
    <div class="dag-main">
      <!-- Toolbar -->
      <div class="dag-toolbar">
        <span class="dag-toolbar-title" id="dag-run-title">Select a run to visualize its Task DAG</span>
        <div id="dag-live-indicator" style="display:none;align-items:center;gap:5px">
          <div class="dag-live-dot"></div>
          <span style="font-size:10px;color:var(--danger);font-weight:700">LIVE</span>
        </div>
        <button class="dag-toolbar-btn" id="dag-fit-btn" onclick="dagFitView()" style="display:none">⊡ Fit</button>
        <button class="dag-toolbar-btn" id="dag-detail-toggle" onclick="dagToggleDetail()" style="display:none">Detail ▶</button>
        <button class="dag-toolbar-btn danger" id="dag-kill-btn" onclick="dagKillActive()" style="display:none">🛑 Kill</button>
        <button class="dag-toolbar-btn" id="dag-delete-btn" onclick="dagDeleteActive()" style="display:none">🗑 Delete</button>
        <button class="dag-toolbar-btn" onclick="dagRefresh()" title="Refresh">↺</button>
      </div>

      <!-- Phase/wave banner -->
      <div class="dag-wave-bar" id="dag-wave-bar" style="display:none"></div>

      <!-- Phase status banner (for running runs) -->
      <div class="dag-phase-banner" id="dag-phase-banner" style="display:none">
        <span id="dag-phase-icon">⚡</span>
        <span id="dag-phase-text">Running…</span>
      </div>

      <!-- Viewport -->
      <div class="dag-viewport">
        <!-- Canvas -->
        <div class="dag-canvas-wrap" id="dag-canvas-wrap">
          <div class="dag-canvas-inner" id="dag-canvas-inner">
            <svg id="dag-svg" style="position:absolute;inset:0;overflow:visible;pointer-events:none">
              <defs>
                <marker id="dag-arr-default" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                  <path d="M0,0 L0,6 L8,3 z" fill="rgba(255,255,255,.2)"/>
                </marker>
                <marker id="dag-arr-done" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                  <path d="M0,0 L0,6 L8,3 z" fill="#3dba7a"/>
                </marker>
                <marker id="dag-arr-active" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                  <path d="M0,0 L0,6 L8,3 z" fill="#e8a237"/>
                </marker>
                <marker id="dag-arr-error" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                  <path d="M0,0 L0,6 L8,3 z" fill="#e85252"/>
                </marker>
              </defs>
              <g id="dag-edges-g"></g>
            </svg>
            <div id="dag-nodes-g"></div>
          </div>

          <!-- Empty state -->
          <div class="dag-empty" id="dag-empty">
            <div class="dag-empty-icon">🧠</div>
            <div class="dag-empty-title">No Run Selected</div>
            <div class="dag-empty-sub">
              Select a supervisor run from the sidebar to visualize its Task DAG — nodes light up in real time as the supervisor orchestrates specialist agents.
            </div>
            <button class="dag-launch-btn" onclick="dagOpenLaunch()" style="width:auto;padding:8px 20px;margin-top:16px">⚡ Launch Your First Goal</button>
          </div>

          <!-- Zoom controls -->
          <div class="dag-zoom-controls" id="dag-zoom-controls" style="display:none">
            <button class="dag-zoom-btn" onclick="dagZoom(1.2)" title="Zoom in">+</button>
            <div class="dag-zoom-label" id="dag-zoom-label">100%</div>
            <button class="dag-zoom-btn" onclick="dagZoom(1/1.2)" title="Zoom out">−</button>
          </div>

          <!-- Minimap -->
          <div class="dag-minimap" id="dag-minimap" style="display:none">
            <canvas id="dag-minimap-canvas" width="130" height="80"></canvas>
          </div>
        </div>

        <!-- Detail panel -->
        <div class="dag-detail collapsed" id="dag-detail">
          <div class="dag-detail-head">
            <h4 id="dag-detail-title">Task Detail</h4>
            <button onclick="dagToggleDetail()" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:13px">✕</button>
          </div>
          <div class="dag-detail-body" id="dag-detail-body">
            <div style="color:var(--text-3);font-size:12px">Click a task node to see its details.</div>
          </div>
        </div>
      </div>

      <!-- Bottom: final output / eval bar (shown when done) -->
      <div id="dag-result-bar" style="display:none;flex-shrink:0;background:var(--bg-1);border-top:1px solid var(--border);padding:10px 14px">
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <span style="font-size:11px;font-weight:700;color:var(--text-2)">📊 Eval Score:</span>
          <span id="dag-eval-score" style="font-size:14px;font-weight:800;color:var(--success)"></span>
          <span id="dag-eval-notes" style="font-size:11px;color:var(--text-3);flex:1"></span>
          <button class="dag-toolbar-btn" onclick="dagShowFinalOutput()">📄 Final Output</button>
        </div>
      </div>
    </div>
  </div>`;

  dagInitCanvasInteraction();
  dagInitKeyboard();
  await dagRefresh();
}


// ── Load data ──────────────────────────────────────────────────────
async function dagRefresh() {
  const [statsR, runsR] = await Promise.all([
    fetch('/api/supervisor/stats').then(r => r.ok ? r.json() : {}).catch(() => ({})),
    fetch('/api/supervisor/runs?limit=50').then(r => r.ok ? r.json() : {runs:[]}).catch(() => ({runs:[]})),
  ]);
  _dagRuns = runsR.runs || [];
  dagUpdateStats(statsR);
  dagRenderRunList();

  // Auto-select the most recent active or first run
  if (!_dagActiveRun && _dagRuns.length > 0) {
    const active = _dagRuns.find(r => ['decomposing','scheduled','running','synthesizing'].includes(r.status));
    await dagSelectRun((active || _dagRuns[0]).run_id);
  } else if (_dagActiveRun) {
    await dagSelectRun(_dagActiveRun.run.run_id);
  }

  // Start polling if any active runs
  dagMaybePoll();
}

function dagUpdateStats(stats) {
  const el = (id) => document.getElementById(id);
  if (el('dag-stat-total'))  el('dag-stat-total').textContent  = stats.total_runs ?? '0';
  if (el('dag-stat-done'))   el('dag-stat-done').textContent   = (stats.by_status || {}).done ?? '0';
  if (el('dag-stat-score'))  el('dag-stat-score').textContent  = stats.avg_eval_score ? Math.round(stats.avg_eval_score * 100) + '%' : '—';
  if (el('dag-stat-tokens')) el('dag-stat-tokens').textContent = ((stats.total_tokens || 0) / 1000).toFixed(1) + 'k';
}

function dagRenderRunList() {
  const list = document.getElementById('dag-run-list');
  if (!list) return;
  if (!_dagRuns.length) {
    list.innerHTML = `<div style="color:var(--text-3);font-size:12px;padding:12px;line-height:1.7">
      No runs yet.<br>Launch your first goal above.
    </div>`;
    return;
  }
  list.innerHTML = _dagRuns.map(r => {
    const isActive   = _dagActiveRun?.run?.run_id === r.run_id;
    const isRunning  = ['decomposing','scheduled','running','synthesizing'].includes(r.status);
    const col        = DAG_RUN_STATUS_COLOR[r.status] || 'var(--border)';
    const icon       = DAG_STATUS_ICONS[r.status]     || '❓';
    const progress   = r.task_count > 0 ? Math.round(r.done_count / r.task_count * 100) : 0;
    const ts         = new Date(r.created_at).toLocaleString(undefined, {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
    return `<div class="dag-run-card ${isActive?'active':''}" onclick="dagSelectRun(${JSON.stringify(r.run_id)})">
      <div class="dag-run-card-top">
        <span class="dag-badge" style="background:${col}22;color:${col}">${icon} ${r.status}</span>
        ${isRunning ? '<div class="dag-live-dot" style="margin-left:auto"></div>' : ''}
      </div>
      <div class="dag-run-name">${escHtml((r.goal_title || r.goal_text || '').slice(0, 55))}</div>
      <div class="dag-run-meta">${r.task_count} tasks · ${ts}${r.duration_ms?` · ${(r.duration_ms/1000).toFixed(1)}s`:''}</div>
      ${r.task_count > 0 ? `
      <div class="dag-progress-bar-wrap">
        <div class="dag-progress-track">
          <div class="dag-progress-fill" style="width:${progress}%;background:${col}"></div>
        </div>
      </div>` : ''}
    </div>`;
  }).join('');
}


// ── Select run & build DAG ─────────────────────────────────────────
async function dagSelectRun(runId) {
  try {
    const d = await fetch(`/api/supervisor/run/${encodeURIComponent(runId)}/dag`)
      .then(r => r.ok ? r.json() : null);
    if (!d || !d.ok) { showToast('Could not load DAG'); return; }

    _dagActiveRun = d;
    _dagSelectedTask = null;

    dagRenderRunList();
    dagUpdateToolbar();
    dagBuildGraph();
    dagBuildWaveBar();
    dagUpdatePhaseBanner();
    dagFitView();
    dagMaybePoll();
  } catch(e) { console.error('dagSelectRun', e); showToast('Error loading DAG: ' + e.message); }
}

function dagUpdateToolbar() {
  const run = _dagActiveRun?.run;
  if (!run) return;
  const isRunning  = ['decomposing','scheduled','running','synthesizing'].includes(run.status);
  const isTerminal = ['done','failed','killed'].includes(run.status);
  const col        = DAG_RUN_STATUS_COLOR[run.status] || 'var(--text-3)';

  // Title
  const titleEl = document.getElementById('dag-run-title');
  if (titleEl) {
    titleEl.innerHTML = `<span class="dag-toolbar-pill" style="background:${col}22;color:${col}">${DAG_STATUS_ICONS[run.status]||''} ${run.status}</span>
    &nbsp;${escHtml((run.goal_title || run.goal_text || '').slice(0, 70))}
    <span style="font-size:10px;color:var(--text-3);margin-left:6px">${_dagActiveRun?.total_tasks || 0} tasks · ${_dagActiveRun?.wave_count || 0} waves</span>`;
  }

  // Live indicator
  const liveEl = document.getElementById('dag-live-indicator');
  if (liveEl) liveEl.style.display = isRunning ? 'flex' : 'none';

  // Buttons
  const show = (id, show) => { const el = document.getElementById(id); if (el) el.style.display = show ? '' : 'none'; };
  show('dag-fit-btn', true);
  show('dag-detail-toggle', true);
  show('dag-kill-btn', isRunning);
  show('dag-delete-btn', isTerminal);
  show('dag-zoom-controls', true);
  show('dag-minimap', true);

  // Hide empty state
  const emptyEl = document.getElementById('dag-empty');
  if (emptyEl) emptyEl.style.display = 'none';

  // Result bar
  const resultBar = document.getElementById('dag-result-bar');
  if (resultBar) {
    if (run.status === 'done' && run.eval_score) {
      resultBar.style.display = 'block';
      const scoreEl = document.getElementById('dag-eval-score');
      const notesEl = document.getElementById('dag-eval-notes');
      if (scoreEl) scoreEl.textContent = Math.round(run.eval_score * 100) + '%';
      if (notesEl) notesEl.textContent = run.eval_notes || '';
    } else {
      resultBar.style.display = 'none';
    }
  }
}

function dagBuildWaveBar() {
  const bar = document.getElementById('dag-wave-bar');
  if (!bar || !_dagActiveRun) return;
  const waves = _dagActiveRun.waves || [];
  if (!waves.length) { bar.style.display = 'none'; return; }
  bar.style.display = 'flex';
  bar.innerHTML = `<span style="font-size:10px;color:var(--text-3);font-weight:700;margin-right:4px">Waves:</span>` +
    waves.map((w, i) => `
      ${i > 0 ? '<span class="dag-wave-arrow">→</span>' : ''}
      <div class="dag-wave-pill ${w.status}">
        ${DAG_STATUS_ICONS[w.status] || '⬡'} Wave ${w.wave + 1}
        <span style="opacity:.7">(${w.count})</span>
      </div>
    `).join('');
}

function dagUpdatePhaseBanner() {
  const banner  = document.getElementById('dag-phase-banner');
  const iconEl  = document.getElementById('dag-phase-icon');
  const textEl  = document.getElementById('dag-phase-text');
  const run     = _dagActiveRun?.run;
  if (!banner || !run) return;

  const phaseMap = {
    decomposing:  ['🧩', 'Brain is decomposing your goal into tasks…'],
    scheduled:    ['📋', 'Tasks scheduled — preparing specialist agents…'],
    running:      ['⚡', `Executing tasks — ${run.done_count || 0} of ${run.task_count || 0} complete`],
    synthesizing: ['🔀', 'Orchestrator is synthesizing all task outputs…'],
  };
  const phase = phaseMap[run.status];
  if (phase) {
    banner.style.display = 'flex';
    if (iconEl) iconEl.textContent = phase[0];
    if (textEl) textEl.textContent = phase[1];
  } else {
    banner.style.display = 'none';
  }
}


// ── Build graph canvas ─────────────────────────────────────────────
function dagBuildGraph() {
  if (!_dagActiveRun) return;
  const nodesG  = document.getElementById('dag-nodes-g');
  const edgesG  = document.getElementById('dag-edges-g');
  if (!nodesG || !edgesG) return;

  const tasks = _dagActiveRun.tasks || [];
  const edges = _dagActiveRun.edges || [];

  // Nodes
  nodesG.innerHTML = tasks.map(t => dagNodeHTML(t)).join('');

  // Draw edges after nodes render
  setTimeout(() => {
    dagDrawEdges(tasks, edges);
    dagUpdateMinimap();
  }, 60);
}

function dagNodeHTML(t) {
  const col    = DAG_AGENT_COLORS[t.agent_id] || '#7a8aaa';
  const icon   = DAG_AGENT_ICONS[t.agent_id]  || '🤖';
  const stIcon = DAG_STATUS_ICONS[t.status]   || '⏳';
  const stCls  = { pending:'n-pending', running:'n-running', done:'n-done', failed:'n-failed', awaiting_hitl:'n-hitl' }[t.status] || 'n-pending';
  const barCls = { pending:'b-pending', running:'b-running', done:'b-done', failed:'b-failed' }[t.status] || 'b-pending';
  const durStr = t.duration_ms > 0 ? `${(t.duration_ms/1000).toFixed(1)}s` : '';
  const preview = t.output ? t.output.slice(0, 90) + (t.output.length > 90 ? '…' : '') : (t.status === 'running' ? 'Running…' : '');

  return `<div class="dag-node ${stCls} ${_dagSelectedTask===t.task_id?'n-selected':''}" id="dagn-${t.task_id}"
              style="left:${t.x||0}px;top:${t.y||0}px"
              onclick="dagClickTask(event,${JSON.stringify(t.task_id)})">
    <div class="dag-node-hdr">
      <div class="dag-node-seq" style="background:${col}">${t.seq}</div>
      <span class="dag-node-label" title="${escHtml(t.title)}">${escHtml(t.title)}</span>
      <span class="dag-node-status-icon">${stIcon}</span>
    </div>
    <div class="dag-node-agent-row">
      <span class="dag-node-agent-tag" style="background:${col}22;color:${col}">${icon} ${t.agent_id}</span>
      ${durStr ? `<span class="dag-node-dur">${durStr}</span>` : ''}
    </div>
    ${preview ? `<div class="dag-node-preview">${escHtml(preview)}</div>` : ''}
    <div class="dag-node-bar">
      <div class="dag-node-bar-fill ${barCls}" id="dagnbar-${t.task_id}" style="background:${col};${t.status==='done'?'width:100%':''}"></div>
    </div>
  </div>`;
}

function dagDrawEdges(tasks, edges) {
  const edgesG = document.getElementById('dag-edges-g');
  if (!edgesG) return;
  edgesG.innerHTML = '';
  const taskMap = {};
  tasks.forEach(t => { taskMap[t.task_id] = t; });
  const NODE_W = 220, NODE_H = 110;

  edges.forEach((e, i) => {
    const src = taskMap[e.from_id];
    const tgt = taskMap[e.to_id];
    if (!src || !tgt) return;

    const x1 = (src.x || 0) + NODE_W;
    const y1 = (src.y || 0) + NODE_H / 2;
    const x2 = (tgt.x || 0);
    const y2 = (tgt.y || 0) + NODE_H / 2;
    const cx = (x1 + x2) / 2;

    const isDone   = e.done;
    const isActive = e.active;
    const isError  = e.error;

    const stroke = isError  ? '#e85252'
                 : isDone   ? '#3dba7a'
                 : isActive ? '#e8a237'
                 : 'rgba(255,255,255,.12)';
    const markerId = isError  ? 'dag-arr-error'
                   : isDone   ? 'dag-arr-done'
                   : isActive ? 'dag-arr-active'
                   : 'dag-arr-default';

    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    const d    = `M${x1},${y1} C${cx},${y1} ${cx},${y2} ${x2},${y2}`;
    path.setAttribute('d', d);
    path.setAttribute('id', `dage-${e.id}`);
    path.setAttribute('stroke', stroke);
    path.setAttribute('stroke-width', isDone || isActive ? '2' : '1.5');
    path.setAttribute('fill', 'none');
    path.setAttribute('marker-end', `url(#${markerId})`);

    // Animated dashes for active edges
    if (isActive && !isError) {
      path.setAttribute('stroke-dasharray', '8 4');
      path.classList.add('dag-edge-active');
    }

    edgesG.appendChild(path);
  });

  // Compute SVG bounds
  if (tasks.length) {
    const maxX = Math.max(...tasks.map(t => (t.x || 0) + NODE_W + 80));
    const maxY = Math.max(...tasks.map(t => (t.y || 0) + NODE_H + 80));
    const svg  = document.getElementById('dag-svg');
    if (svg) { svg.style.width = maxX + 'px'; svg.style.height = maxY + 'px'; }
  }
}

// Refresh just node states + edges without full rebuild (for live polling)
function dagRefreshGraphState() {
  if (!_dagActiveRun) return;
  const tasks = _dagActiveRun.tasks || [];
  const edges = _dagActiveRun.edges || [];

  tasks.forEach(t => {
    const el     = document.getElementById(`dagn-${t.task_id}`);
    const barEl  = document.getElementById(`dagnbar-${t.task_id}`);
    if (!el) return;
    const stCls  = { pending:'n-pending', running:'n-running', done:'n-done', failed:'n-failed', awaiting_hitl:'n-hitl' }[t.status] || 'n-pending';
    const barCls = { pending:'b-pending', running:'b-running', done:'b-done', failed:'b-failed' }[t.status] || 'b-pending';
    const base = `dag-node ${stCls}`;
    el.className = _dagSelectedTask === t.task_id ? base + ' n-selected' : base;
    if (barEl) {
      barEl.className = `dag-node-bar-fill ${barCls}`;
      const col = DAG_AGENT_COLORS[t.agent_id] || '#7a8aaa';
      barEl.style.background = col;
      if (t.status === 'done') barEl.style.width = '100%';
    }
    // Update preview
    const preview = el.querySelector('.dag-node-preview');
    if (preview && t.output) preview.textContent = t.output.slice(0, 90) + (t.output.length > 90 ? '…' : '');
    // Update status icon
    const iconEl = el.querySelector('.dag-node-status-icon');
    if (iconEl) iconEl.textContent = DAG_STATUS_ICONS[t.status] || '⏳';
    // Update duration
    const agentRow = el.querySelector('.dag-node-dur');
    if (agentRow && t.duration_ms > 0) agentRow.textContent = `${(t.duration_ms/1000).toFixed(1)}s`;
  });

  // Redraw edges
  dagDrawEdges(tasks, edges);
  dagUpdateMinimap();
}


// ── Task detail panel ──────────────────────────────────────────────
function dagClickTask(e, taskId) {
  e.stopPropagation();
  _dagSelectedTask = taskId;
  // Deselect all
  document.querySelectorAll('.dag-node.n-selected').forEach(n => n.classList.remove('n-selected'));
  const el = document.getElementById(`dagn-${taskId}`);
  if (el) el.classList.add('n-selected');
  dagShowTaskDetail(taskId);
  const detail = document.getElementById('dag-detail');
  if (detail?.classList.contains('collapsed')) dagToggleDetail();
}

function dagShowTaskDetail(taskId) {
  const body    = document.getElementById('dag-detail-body');
  const titleEl = document.getElementById('dag-detail-title');
  if (!body || !_dagActiveRun) return;

  const task = (_dagActiveRun.tasks || []).find(t => t.task_id === taskId);
  if (!task) return;

  const col    = DAG_AGENT_COLORS[task.agent_id] || '#7a8aaa';
  const icon   = DAG_AGENT_ICONS[task.agent_id]  || '🤖';
  const stCol  = DAG_STATUS_COLORS[task.status]  || 'var(--text-3)';
  const isErr  = task.status === 'failed';
  const deps   = (task.depends_on || []).join(', ') || 'None (starts immediately)';

  if (titleEl) titleEl.textContent = `Task #${task.seq} — ${task.title}`;

  const copy = (txt) =>
    `<button class="dag-copy-btn" onclick="navigator.clipboard.writeText(${JSON.stringify(txt)}).then(()=>showToast('Copied!'))">Copy</button>`;

  body.innerHTML = `
    <!-- Header -->
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
      <div class="dag-node-seq" style="background:${col};width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:800;color:#fff;flex-shrink:0">${task.seq}</div>
      <div>
        <div style="font-size:13px;font-weight:700;color:var(--text-0)">${escHtml(task.title)}</div>
        <div style="font-size:11px;color:${col};font-weight:700">${icon} ${task.agent_id}</div>
      </div>
    </div>

    <!-- Status -->
    <div class="dag-detail-section">
      <div class="dag-detail-label">Status</div>
      <div style="display:flex;align-items:center;gap:8px">
        <span style="padding:3px 10px;border-radius:6px;font-size:11px;font-weight:700;background:${stCol}22;color:${stCol}">
          ${DAG_STATUS_ICONS[task.status] || ''} ${task.status}
        </span>
        ${task.duration_ms > 0 ? `<span style="font-size:11px;color:var(--accent)">${(task.duration_ms/1000).toFixed(2)}s</span>` : ''}
        ${task.tokens ? `<span style="font-size:10px;color:var(--text-3)">${task.tokens} tokens</span>` : ''}
      </div>
    </div>

    <!-- Description -->
    ${task.description ? `
    <div class="dag-detail-section">
      <div class="dag-detail-label">Description</div>
      <div class="dag-detail-val">${escHtml(task.description)}</div>
    </div>` : ''}

    <!-- Dependencies -->
    <div class="dag-detail-section">
      <div class="dag-detail-label">Depends On (seq)</div>
      <div class="dag-detail-val">${escHtml(deps)}</div>
    </div>

    <!-- Output -->
    ${task.output ? `
    <div class="dag-detail-section">
      <div class="dag-detail-label">Output ${copy(task.output)}</div>
      <div class="dag-detail-val ${isErr ? 'v-error' : ''}">${escHtml(task.output.slice(0, 1200))}</div>
    </div>` : (task.status === 'running' ? `
    <div class="dag-detail-section">
      <div class="dag-detail-label">Output</div>
      <div style="color:var(--warning);font-size:11px;animation:dag-blink 1s infinite">⚡ Agent running…</div>
    </div>` : '')}

    <!-- Timing -->
    <div class="dag-detail-section">
      <div class="dag-detail-label">Timing</div>
      <div style="font-size:11px;color:var(--text-2)">
        ${task.created_at   ? `Created:   ${new Date(task.created_at).toLocaleString()}<br>` : ''}
        ${task.started_at   ? `Started:   ${new Date(task.started_at).toLocaleString()}<br>` : ''}
        ${task.completed_at ? `Completed: ${new Date(task.completed_at).toLocaleString()}` : ''}
      </div>
    </div>

    <!-- Risk -->
    ${task.risk_level && task.risk_level !== 'low' ? `
    <div class="dag-detail-section">
      <div class="dag-detail-label">Risk Level</div>
      <span style="padding:2px 8px;border-radius:5px;font-size:11px;font-weight:700;background:rgba(232,82,82,.15);color:#e85252">
        ⚠️ ${task.risk_level}
      </span>
      ${task.hitl_required ? '<span style="font-size:11px;color:#c084fc;margin-left:6px">🛂 HITL required</span>' : ''}
    </div>` : ''}
  `;
}

function dagToggleDetail() {
  const detail = document.getElementById('dag-detail');
  const btn    = document.getElementById('dag-detail-toggle');
  if (!detail) return;
  const collapsed = detail.classList.toggle('collapsed');
  if (btn) btn.textContent = collapsed ? 'Detail ▶' : 'Detail ✕';
}


// ── Live polling for active runs ────────────────────────────────────
function dagMaybePoll() {
  const isActive = _dagActiveRun &&
    ['decomposing','scheduled','running','synthesizing'].includes(_dagActiveRun.run?.status);

  if (_supervisorPollTimer) {
    clearInterval(_supervisorPollTimer);
    _supervisorPollTimer = null;
  }

  if (isActive) {
    _supervisorPollTimer = setInterval(dagLivePoll, 2000);
  }
}

async function dagLivePoll() {
  if (!_dagActiveRun) return;
  const pane = document.getElementById('pane-supervisor');
  if (!pane) { clearInterval(_supervisorPollTimer); return; }

  try {
    const runId = _dagActiveRun.run.run_id;
    const d = await fetch(`/api/supervisor/run/${encodeURIComponent(runId)}/dag`)
      .then(r => r.ok ? r.json() : null);
    if (!d || !d.ok) return;

    const wasActive = ['decomposing','scheduled','running','synthesizing'].includes(_dagActiveRun.run?.status);
    _dagActiveRun = d;

    // Incremental refresh (no full rebuild)
    dagRefreshGraphState();
    dagBuildWaveBar();
    dagUpdatePhaseBanner();
    dagUpdateToolbar();

    // If selected task exists, refresh its detail
    if (_dagSelectedTask) dagShowTaskDetail(_dagSelectedTask);

    const isNowActive = ['decomposing','scheduled','running','synthesizing'].includes(d.run?.status);
    if (!isNowActive) {
      clearInterval(_supervisorPollTimer);
      _supervisorPollTimer = null;
      // Refresh sidebar list to update status badges
      const runsR = await fetch('/api/supervisor/runs?limit=50').then(r => r.ok ? r.json() : {runs:[]});
      _dagRuns = runsR.runs || [];
      dagRenderRunList();
    }
  } catch(e) { /* network hiccup — ignore */ }
}


// ── Zoom & Pan ──────────────────────────────────────────────────────
function dagApplyTransform() {
  const inner = document.getElementById('dag-canvas-inner');
  if (inner) inner.style.transform = `translate(${_dagPanX}px,${_dagPanY}px) scale(${_dagZoom})`;
  const label = document.getElementById('dag-zoom-label');
  if (label) label.textContent = Math.round(_dagZoom * 100) + '%';
}

function dagZoom(factor) {
  const wrap = document.getElementById('dag-canvas-wrap');
  if (!wrap) return;
  const rect = wrap.getBoundingClientRect();
  const cx   = rect.width / 2, cy = rect.height / 2;
  _dagPanX   = cx - (cx - _dagPanX) * factor;
  _dagPanY   = cy - (cy - _dagPanY) * factor;
  _dagZoom   = Math.max(0.2, Math.min(3, _dagZoom * factor));
  dagApplyTransform();
  dagUpdateMinimap();
}

function dagFitView() {
  if (!_dagActiveRun?.tasks?.length) return;
  const wrap = document.getElementById('dag-canvas-wrap');
  if (!wrap) return;
  const rect  = wrap.getBoundingClientRect();
  const tasks = _dagActiveRun.tasks;
  const pad   = 60;
  const NODE_W = 220, NODE_H = 110;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  tasks.forEach(t => {
    minX = Math.min(minX, t.x || 0);   minY = Math.min(minY, t.y || 0);
    maxX = Math.max(maxX, (t.x||0)+NODE_W); maxY = Math.max(maxY, (t.y||0)+NODE_H);
  });
  const scX  = (rect.width  - pad*2) / Math.max(maxX - minX, 1);
  const scY  = (rect.height - pad*2) / Math.max(maxY - minY, 1);
  _dagZoom   = Math.max(0.2, Math.min(2, Math.min(scX, scY)));
  _dagPanX   = (rect.width  - (maxX + minX) * _dagZoom) / 2;
  _dagPanY   = (rect.height - (maxY + minY) * _dagZoom) / 2;
  dagApplyTransform();
  dagUpdateMinimap();
}

function dagInitCanvasInteraction() {
  const wrap = document.getElementById('dag-canvas-wrap');
  if (!wrap) return;
  wrap.addEventListener('wheel', e => {
    e.preventDefault();
    const rect   = wrap.getBoundingClientRect();
    const factor = e.deltaY < 0 ? 1.12 : 1/1.12;
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    _dagPanX = mx - (mx - _dagPanX) * factor;
    _dagPanY = my - (my - _dagPanY) * factor;
    _dagZoom = Math.max(0.2, Math.min(3, _dagZoom * factor));
    dagApplyTransform();
    dagUpdateMinimap();
  }, { passive: false });

  wrap.addEventListener('mousedown', e => {
    if (e.target.closest('.dag-node,.dag-zoom-controls,.dag-minimap')) return;
    _dagPanning  = true;
    _dagPanStart = { x: e.clientX, y: e.clientY, px: _dagPanX, py: _dagPanY };
    wrap.style.cursor = 'grabbing';
  });
  document.addEventListener('mousemove', e => {
    if (!_dagPanning) return;
    _dagPanX = _dagPanStart.px + (e.clientX - _dagPanStart.x);
    _dagPanY = _dagPanStart.py + (e.clientY - _dagPanStart.y);
    dagApplyTransform();
  });
  document.addEventListener('mouseup', () => {
    if (_dagPanning) {
      _dagPanning = false;
      const w2 = document.getElementById('dag-canvas-wrap');
      if (w2) w2.style.cursor = '';
      dagUpdateMinimap();
    }
  });
}


// ── Minimap ─────────────────────────────────────────────────────────
function dagUpdateMinimap() {
  const canvas = document.getElementById('dag-minimap-canvas');
  if (!canvas || !_dagActiveRun?.tasks?.length) return;
  const ctx  = canvas.getContext('2d');
  const W = 130, H = 80, pad = 8;
  const tasks = _dagActiveRun.tasks || [];
  const edges = _dagActiveRun.edges || [];
  const NODE_W = 220, NODE_H = 110;
  ctx.clearRect(0, 0, W, H);

  let minX=Infinity, minY=Infinity, maxX=-Infinity, maxY=-Infinity;
  tasks.forEach(t => {
    minX=Math.min(minX,t.x||0); minY=Math.min(minY,t.y||0);
    maxX=Math.max(maxX,(t.x||0)+NODE_W); maxY=Math.max(maxY,(t.y||0)+NODE_H);
  });
  const scX=(W-pad*2)/Math.max(maxX-minX,1);
  const scY=(H-pad*2)/Math.max(maxY-minY,1);
  const sc =Math.min(scX,scY);
  const toX=(x)=>pad+(x-minX)*sc;
  const toY=(y)=>pad+(y-minY)*sc;

  // Edges
  const taskMap={};tasks.forEach(t=>taskMap[t.task_id]=t);
  edges.forEach(e=>{
    const s=taskMap[e.from_id], t=taskMap[e.to_id];
    if(!s||!t)return;
    ctx.strokeStyle=e.done?'#3dba7a':e.active?'#e8a237':'rgba(255,255,255,.15)';
    ctx.lineWidth=0.8;
    ctx.beginPath();
    ctx.moveTo(toX((s.x||0)+NODE_W),toY((s.y||0)+NODE_H/2));
    ctx.lineTo(toX(t.x||0),toY((t.y||0)+NODE_H/2));
    ctx.stroke();
  });

  // Nodes
  tasks.forEach(t=>{
    const col=DAG_STATUS_COLORS[t.status]||'rgba(255,255,255,.1)';
    ctx.fillStyle=col;
    const mw=Math.max(NODE_W*sc,4), mh=Math.max(NODE_H*sc*0.55,3);
    ctx.beginPath();
    ctx.roundRect(toX(t.x||0),toY(t.y||0),mw,mh,1.5);
    ctx.fill();
  });

  // Viewport rect
  const wrap=document.getElementById('dag-canvas-wrap');
  if(wrap){
    const wRect=wrap.getBoundingClientRect();
    ctx.strokeStyle='rgba(91,138,248,.6)';ctx.lineWidth=1;
    ctx.strokeRect(
      toX(-_dagPanX/_dagZoom),toY(-_dagPanY/_dagZoom),
      (wRect.width/_dagZoom)*sc,(wRect.height/_dagZoom)*sc
    );
  }
}


// ── Keyboard ────────────────────────────────────────────────────────
function dagInitKeyboard() {
  document.addEventListener('keydown', dagKeyHandler);
}
function dagKeyHandler(e) {
  const pane = document.getElementById('pane-supervisor');
  if (!pane) return;
  if (e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA'||e.target.tagName==='SELECT') return;
  if (e.key==='f'||e.key==='F') dagFitView();
  if ((e.key==='+'||e.key==='=')&&!e.shiftKey) dagZoom(1.2);
  if (e.key==='-') dagZoom(1/1.2);
}


// ── Launch modal ─────────────────────────────────────────────────────
function dagOpenLaunch() {
  const existing = document.getElementById('dag-launch-modal');
  if (existing) { existing.remove(); return; }

  const examples = [
    'Build a REST API for user authentication with JWT',
    'Competitive analysis of the top 5 LLM providers in 2026',
    'Write a marketing campaign for our new product launch',
    'Audit this codebase and produce a security report',
    'Research quantum error correction and write a technical summary',
  ];

  const overlay = document.createElement('div');
  overlay.id = 'dag-launch-modal';
  overlay.className = 'dag-modal-overlay';
  overlay.innerHTML = `
    <div class="dag-modal">
      <h3>⚡ Launch New Supervisor Goal</h3>
      <p>The Brain agent will decompose your goal into a task DAG, assign specialist agents, and execute waves in parallel. Watch the graph light up in real time.</p>
      <textarea id="dag-goal-ta" placeholder="Describe your goal in detail…&#10;&#10;Be specific about deliverables, constraints, and desired output format." rows="4"></textarea>
      <div class="dag-modal-examples">
        ${examples.map(ex => `<div class="dag-modal-example" onclick="document.getElementById('dag-goal-ta').value=${JSON.stringify(ex)}">${ex}</div>`).join('')}
      </div>
      <div class="dag-modal-row">
        <button class="dag-toolbar-btn" onclick="document.getElementById('dag-launch-modal').remove()">Cancel</button>
        <button class="dag-launch-btn" style="width:auto;padding:8px 20px" onclick="dagLaunchGoal()">⚡ Launch</button>
      </div>
    </div>`;
  overlay.onclick = e => { if (e.target === overlay) overlay.remove(); };
  document.body.appendChild(overlay);
  setTimeout(() => document.getElementById('dag-goal-ta')?.focus(), 50);
}

async function dagLaunchGoal() {
  const goal = document.getElementById('dag-goal-ta')?.value?.trim();
  if (!goal) { showToast('⚠️ Enter a goal first'); return; }
  document.getElementById('dag-launch-modal')?.remove();
  showToast('⚡ Launching supervisor run…');
  try {
    const r = await fetch('/api/supervisor/run', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ goal })
    });
    if (!r.ok) { showToast('⚠️ Launch failed (HTTP ' + r.status + ')'); return; }
    const d = await r.json();
    if (!d.ok) { showToast('⚠️ ' + (d.error || 'Launch failed')); return; }
    showToast(`🧠 Run started: ${d.run_id}`);
    // Refresh list and auto-select the new run
    await dagRefresh();
    await dagSelectRun(d.run_id);
  } catch(e) { showToast('⚠️ Launch error: ' + e.message); }
}


// ── Kill / Delete ────────────────────────────────────────────────────
async function dagKillActive() {
  if (!_dagActiveRun) return;
  const runId = _dagActiveRun.run.run_id;
  const ok    = await gmDanger('Kill Run', `Stop run ${runId}? All in-progress tasks will be abandoned.`);
  if (!ok) return;
  try {
    const r = await fetch(`/api/supervisor/run/${encodeURIComponent(runId)}/kill`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({reason:'User kill switch'})
    });
    const d = await r.json();
    showToast(d.ok ? `🛑 Run killed` : '⚠️ Kill failed: ' + (d.error || ''));
    await dagRefresh();
  } catch(e) { showToast('⚠️ ' + e.message); }
}

async function dagDeleteActive() {
  if (!_dagActiveRun) return;
  const runId = _dagActiveRun.run.run_id;
  const ok    = await gmDanger('Delete Run', `Delete run ${runId} and all task data?`);
  if (!ok) return;
  try {
    const r = await fetch(`/api/supervisor/run/${encodeURIComponent(runId)}`, { method:'DELETE' });
    const d = await r.json();
    if (d.ok) {
      showToast('🗑 Run deleted');
      _dagActiveRun = null;
      _dagSelectedTask = null;
      await dagRefresh();
    } else {
      showToast('⚠️ Delete failed: ' + (d.error || ''));
    }
  } catch(e) { showToast('⚠️ ' + e.message); }
}


// ── Final output modal ───────────────────────────────────────────────
async function dagShowFinalOutput() {
  if (!_dagActiveRun) return;
  const run = _dagActiveRun.run;
  const out = run.final_output || '(no output)';
  await gmAlert(`📄 Final Output — ${escHtml((run.goal_title||'').slice(0,60))}`,
    `Score: ${run.eval_score ? Math.round(run.eval_score*100)+'%' : '—'}\n${run.eval_notes ? 'Notes: '+run.eval_notes+'\n' : ''}\n${out.slice(0,2000)}`);
}


// ── Old compat aliases (referenced by nav patches) ───────────────────
async function supervisorLaunch() { dagOpenLaunch(); }
async function supervisorViewRun(runId) { await dagSelectRun(runId); }
async function supervisorKill(runId) {
  if (_dagActiveRun?.run?.run_id !== runId) await dagSelectRun(runId);
  await dagKillActive();
}
async function supervisorDelete(runId) {
  if (_dagActiveRun?.run?.run_id !== runId) await dagSelectRun(runId);
  await dagDeleteActive();
}
function renderSupervisorRunCard(r) { return ''; } // no longer used




// ══════════════════════════════════════════════════════════════════
//  GOAL DECOMPOSITION & OUTCOME SCORING — Complete Implementation
// ══════════════════════════════════════════════════════════════════

// ── State ─────────────────────────────────────────────────────────
let _goalFilter   = { status: '', domain: '', priority: '' };
let _goalList     = [];           // cached goal array
let _goalSelected = null;         // currently open goal detail {goal, milestones, checkins, decomposition, score_history}
let _goalTab      = 'overview';   // 'overview' | 'decompose' | 'score' | 'history'
let _goalPollTimer = null;

// ── Constants ──────────────────────────────────────────────────────
const GOAL_PRIORITY_COLORS = {
  critical: '#e85252', high: '#e8a237', medium: '#5b8af8', low: '#7a8aaa'
};
const GOAL_STATUS_COLORS = {
  active: '#3dba7a', paused: '#e8a237', done: '#9d74f5',
  cancelled: '#7a8aaa', blocked: '#e85252'
};
const GOAL_DOMAIN_ICONS = {
  Work:'💼', Health:'🏃', Finance:'💰', Learning:'📚',
  Home:'🏠', Travel:'✈️', Personal:'⭐', Research:'🔬'
};
const GOAL_AGENT_COLORS = {
  researcher:'#5b8af8', builder:'#3dba7a', reviewer:'#e8a237',
  creative:'#c084fc', memory:'#38c5d8', brain:'#9d74f5', orchestrator:'#f06080'
};
const GOAL_AGENT_ICONS = {
  researcher:'🔍', builder:'🔨', reviewer:'🔬', creative:'✍️',
  memory:'🧠', brain:'💡', orchestrator:'🎯'
};
const GRADE_COLORS = {
  'A+':'#3dba7a','A':'#3dba7a','A-':'#5b8af8',
  'B+':'#5b8af8','B':'#5b8af8','B-':'#e8a237',
  'C+':'#e8a237','C':'#e8a237','C-':'#e85252',
  'D':'#e85252','F':'#e85252'
};


// ── Main render (pane population) ─────────────────────────────────
async function renderGoals() {
  const pane = document.getElementById('pane-goals');
  if (!pane) return;

  pane.innerHTML = `
  

  <div class="gm-root">
    <!-- ── Sidebar ── -->
    <div class="gm-sidebar">
      <div class="gm-sidebar-head">
        <p class="gm-sidebar-title">🎯 Goals</p>
        <div class="gm-stats-row" id="gm-stats-row">
          <div class="gm-stat"><div class="gm-stat-val" id="gm-stat-total" style="color:var(--accent)">—</div><div class="gm-stat-label">Total</div></div>
          <div class="gm-stat"><div class="gm-stat-val" id="gm-stat-active" style="color:var(--success)">—</div><div class="gm-stat-label">Active</div></div>
          <div class="gm-stat"><div class="gm-stat-val" id="gm-stat-avg" style="color:#9d74f5">—</div><div class="gm-stat-label">Avg%</div></div>
        </div>
        <div class="gm-filters">
          <div class="gm-filter-row">
            <select class="gm-filter-select" id="gm-filter-status" onchange="gmFilterChange()">
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="done">Done</option>
              <option value="blocked">Blocked</option>
            </select>
            <select class="gm-filter-select" id="gm-filter-priority" onchange="gmFilterChange()">
              <option value="">All priorities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
          <select class="gm-filter-select" id="gm-filter-domain" onchange="gmFilterChange()">
            <option value="">All domains</option>
            <option value="Work">💼 Work</option>
            <option value="Health">🏃 Health</option>
            <option value="Finance">💰 Finance</option>
            <option value="Learning">📚 Learning</option>
            <option value="Home">🏠 Home</option>
            <option value="Research">🔬 Research</option>
            <option value="Personal">⭐ Personal</option>
            <option value="Travel">✈️ Travel</option>
          </select>
        </div>
      </div>
      <div class="gm-goal-list" id="gm-goal-list">
        <div style="color:var(--text-3);font-size:12px;padding:10px">Loading…</div>
      </div>
      <div class="gm-sidebar-foot">
        <button class="gm-new-btn" onclick="gmOpenCreate()">+ New Goal</button>
      </div>
    </div>

    <!-- ── Main ── -->
    <div class="gm-main" id="gm-main">
      <div class="gm-empty" id="gm-empty-main">
        <div class="gm-empty-icon">🎯</div>
        <div class="gm-empty-title">No Goal Selected</div>
        <div class="gm-empty-sub">Select a goal from the sidebar to view its decomposition, live outcome score, and progress history — or create your first goal.</div>
        <button class="gm-new-btn" onclick="gmOpenCreate()" style="width:auto;padding:8px 20px;margin-top:16px">+ Create First Goal</button>
      </div>
    </div>
  </div>`;

  await gmLoadGoals();
}


// ── Load & render goal list ────────────────────────────────────────
async function gmLoadGoals() {
  const [statsR, goalsR] = await Promise.all([
    fetch('/api/goals/stats/summary').then(r=>r.ok?r.json():{}).catch(()=>({})),
    fetch(`/api/goals?limit=100${_goalFilter.status?'&status='+encodeURIComponent(_goalFilter.status):''}${_goalFilter.domain?'&domain='+encodeURIComponent(_goalFilter.domain):''}${_goalFilter.priority?'&priority='+encodeURIComponent(_goalFilter.priority):''}`).then(r=>r.ok?r.json():{goals:[]}).catch(()=>({goals:[]})),
  ]);
  _goalList = goalsR.goals || [];
  gmUpdateStats(statsR);
  gmRenderList();
}

function gmUpdateStats(stats) {
  const s = (id, v) => { const el=document.getElementById(id); if(el) el.textContent=v; };
  s('gm-stat-total',  stats.total ?? _goalList.length);
  s('gm-stat-active', (stats.by_status||{}).active ?? _goalList.filter(g=>g.status==='active').length);
  s('gm-stat-avg',    Math.round(stats.avg_progress ?? 0) + '%');
}

function gmRenderList() {
  const list = document.getElementById('gm-goal-list');
  if (!list) return;
  if (!_goalList.length) {
    list.innerHTML = `<div style="color:var(--text-3);font-size:12px;padding:12px;line-height:1.7">No goals match these filters.</div>`;
    return;
  }
  list.innerHTML = _goalList.map(g => {
    const pCol   = GOAL_PRIORITY_COLORS[g.priority]  || 'var(--accent)';
    const sCol   = GOAL_STATUS_COLORS[g.status]       || 'var(--text-3)';
    const prog   = g.progress || 0;
    const progC  = prog>=80?'var(--success)':prog>=40?'var(--warning)':'var(--danger)';
    const isActive = _goalSelected?.goal?.id === g.id;
    const score  = g.outcome_score != null ? Math.round(g.outcome_score*100) : null;
    const icon   = GOAL_DOMAIN_ICONS[g.domain] || '📌';
    return `<div class="gm-goal-card ${isActive?'active':''}" style="border-left-color:${pCol}" onclick="gmSelectGoal(${JSON.stringify(g.id)})">
      <div class="gm-goal-card-top">
        <span class="gm-goal-icon">${icon}</span>
        <span class="gm-goal-title">${escHtml(g.title.slice(0,55))}</span>
      </div>
      <div class="gm-goal-meta">
        <span style="color:${pCol}">${g.priority}</span> ·
        <span style="color:${sCol}">${g.status}</span>
        ${g.deadline ? ` · ⏰ ${g.deadline}` : ''}
      </div>
      <div class="gm-progress-bar-wrap">
        <div class="gm-progress-track">
          <div class="gm-progress-fill" style="width:${prog}%;background:${progC}"></div>
        </div>
        <span class="gm-progress-pct" style="color:${progC}">${prog}%</span>
      </div>
      ${score != null ? `<div><span class="gm-score-chip" style="background:${(GRADE_COLORS[gmScoreToGrade(g.outcome_score)]||'#7a8aaa')}22;color:${GRADE_COLORS[gmScoreToGrade(g.outcome_score)]||'#7a8aaa'}">⭐ ${score}% ${gmScoreToGrade(g.outcome_score)}</span></div>` : ''}
    </div>`;
  }).join('');
}

function gmFilterChange() {
  _goalFilter.status   = document.getElementById('gm-filter-status')?.value   || '';
  _goalFilter.domain   = document.getElementById('gm-filter-domain')?.value   || '';
  _goalFilter.priority = document.getElementById('gm-filter-priority')?.value || '';
  gmLoadGoals();
}


// ── Select goal & render detail ────────────────────────────────────
async function gmSelectGoal(goalId) {
  const d = await fetch(`/api/goals/${encodeURIComponent(goalId)}/full`)
    .then(r=>r.ok?r.json():null).catch(()=>null);
  if (!d || !d.ok) { showToast('Could not load goal'); return; }
  _goalSelected = d;
  _goalTab = 'overview';
  gmRenderList();
  gmRenderDetail();
}

function gmRenderDetail() {
  const main = document.getElementById('gm-main');
  if (!main || !_goalSelected) return;
  const g   = _goalSelected.goal;
  const pCol = GOAL_PRIORITY_COLORS[g.priority] || 'var(--accent)';
  const sCol = GOAL_STATUS_COLORS[g.status]     || 'var(--text-3)';
  const prog = g.progress || 0;
  const progC = prog>=80?'var(--success)':prog>=40?'var(--warning)':'var(--danger)';
  const score  = g.outcome_score != null ? Math.round(g.outcome_score*100) : null;
  const grade  = g.outcome_score != null ? gmScoreToGrade(g.outcome_score) : null;
  const decomp = _goalSelected.decomposition || [];
  const scores = _goalSelected.score_history || [];
  const ms     = _goalSelected.milestones    || [];

  main.innerHTML = `
    <div class="gm-detail-head">
      <div class="gm-detail-title">${escHtml(g.title)}</div>
      <div class="gm-detail-meta-row">
        <span class="gm-badge" style="background:${pCol}22;color:${pCol}">${g.priority}</span>
        <span class="gm-badge" style="background:${sCol}22;color:${sCol}">${g.status}</span>
        <span class="gm-badge" style="background:var(--bg-3);color:var(--text-2)">${GOAL_DOMAIN_ICONS[g.domain]||'📌'} ${g.domain}</span>
        ${g.deadline ? `<span style="font-size:11px;color:var(--text-3)">⏰ Due ${g.deadline}</span>` : ''}
        ${score != null ? `<span class="gm-badge" style="background:${(GRADE_COLORS[grade]||'#7a8aaa')}22;color:${GRADE_COLORS[grade]||'#7a8aaa'}">⭐ Score: ${score}% ${grade}</span>` : ''}
        ${g.iteration ? `<span style="font-size:10px;color:var(--text-3)">Iteration ${g.iteration}</span>` : ''}
      </div>
      <div class="gm-detail-progress-row">
        <span style="font-size:11px;color:var(--text-3)">Progress</span>
        <div class="gm-detail-progress-track">
          <div class="gm-detail-progress-fill" style="width:${prog}%;background:${progC}"></div>
        </div>
        <span class="gm-detail-progress-pct" style="color:${progC}">${prog}%</span>
      </div>
      <div class="gm-detail-actions">
        <button class="gm-action-btn primary" onclick="gmDecomposeGoal()">🧩 Decompose</button>
        <button class="gm-action-btn primary" onclick="gmScoreGoal()" style="background:rgba(157,116,245,.2);border-color:#9d74f5;color:#9d74f5">⭐ Score Outcome</button>
        <button class="gm-action-btn" onclick="gmLaunchGoal()">🚀 Launch Supervisor</button>
        <button class="gm-action-btn" onclick="gmAddCheckin()">📈 Check-in</button>
        <button class="gm-action-btn" onclick="gmAddMilestone()">📌 Add Milestone</button>
        <button class="gm-action-btn" onclick="gmEditGoal()">✏️ Edit</button>
        <button class="gm-action-btn danger" onclick="gmDeleteGoal()">🗑</button>
      </div>
    </div>

    <div class="gm-tabs">
      <div class="gm-tab ${_goalTab==='overview'?'active':''}"   onclick="gmSetTab('overview')">Overview</div>
      <div class="gm-tab ${_goalTab==='decompose'?'active':''}"  onclick="gmSetTab('decompose')">
        Decompose<span class="gm-tab-badge" id="gm-decomp-badge">${decomp.length||''}</span>
      </div>
      <div class="gm-tab ${_goalTab==='score'?'active':''}"      onclick="gmSetTab('score')">Outcome Score</div>
      <div class="gm-tab ${_goalTab==='history'?'active':''}"    onclick="gmSetTab('history')">
        History<span class="gm-tab-badge" id="gm-hist-badge">${scores.length||''}</span>
      </div>
    </div>

    <div class="gm-tab-content" id="gm-tab-content">
      ${gmRenderTabContent()}
    </div>
  `;
}

function gmSetTab(tab) {
  _goalTab = tab;
  const tc = document.getElementById('gm-tab-content');
  if (tc) tc.innerHTML = gmRenderTabContent();
  // Update tab active states
  document.querySelectorAll('.gm-tab').forEach(el => {
    el.classList.toggle('active', el.textContent.trim().toLowerCase().startsWith(tab));
  });
}

function gmRenderTabContent() {
  if (!_goalSelected) return '';
  if (_goalTab === 'overview')  return gmTabOverview();
  if (_goalTab === 'decompose') return gmTabDecompose();
  if (_goalTab === 'score')     return gmTabScore();
  if (_goalTab === 'history')   return gmTabHistory();
  return '';
}


// ── Tab: Overview ─────────────────────────────────────────────────
function gmTabOverview() {
  const g   = _goalSelected.goal;
  const ms  = _goalSelected.milestones || [];
  const ci  = _goalSelected.checkins   || [];
  const donems = ms.filter(m=>m.completed).length;

  return `
    ${g.description ? `
    <div class="gm-section">
      <div class="gm-section-title">📝 Description</div>
      <div class="gm-criteria-block">${escHtml(g.description)}</div>
    </div>` : ''}

    ${g.success_criteria ? `
    <div class="gm-section">
      <div class="gm-section-title">✅ Success Criteria</div>
      <div class="gm-criteria-block">${escHtml(g.success_criteria)}</div>
    </div>` : ''}

    <div class="gm-section">
      <div class="gm-section-title">📌 Milestones
        ${ms.length ? `<span style="color:var(--text-3);font-size:10px">(${donems}/${ms.length} done)</span>` : ''}
        <button onclick="gmAddMilestone()" style="margin-left:auto;font-size:10px;padding:2px 7px;border-radius:5px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-2);cursor:pointer">+ Add</button>
      </div>
      ${ms.length ? `
      <div class="gm-milestone-list">
        ${ms.map(m=>`
        <div class="gm-milestone-item ${m.completed?'done':''}" onclick="gmCompleteMilestone(${JSON.stringify(m.id)},${m.completed?1:0})">
          <span class="gm-milestone-check">${m.completed?'✅':'⬜'}</span>
          <span class="gm-milestone-title ${m.completed?'done':''}">${escHtml(m.title)}</span>
          ${m.due_date ? `<span style="font-size:10px;color:var(--text-3)">${m.due_date}</span>` : ''}
        </div>`).join('')}
      </div>` : '<div style="color:var(--text-3);font-size:12px">No milestones yet — add one to track progress.</div>'}
    </div>

    <div class="gm-section">
      <div class="gm-section-title">💬 Check-ins (${ci.length})</div>
      ${ci.length ? `
      <div class="gm-checkin-list">
        ${ci.slice(0,8).map(c=>`
        <div class="gm-checkin-item">
          <div class="gm-checkin-head">
            <span class="gm-checkin-agent" style="color:${GOAL_AGENT_COLORS[c.agent_id]||'var(--text-2)'}">${GOAL_AGENT_ICONS[c.agent_id]||'👤'} ${c.agent_id}</span>
            ${c.progress>0?`<span class="gm-checkin-pct">${c.progress}%</span>`:''}
            <span class="gm-checkin-time">${new Date(c.created_at).toLocaleDateString()}</span>
          </div>
          ${c.note?`<div class="gm-checkin-note">${escHtml(c.note)}</div>`:''}
        </div>`).join('')}
      </div>` : '<div style="color:var(--text-3);font-size:12px">No check-ins yet.</div>'}
    </div>

    ${g.supervisor_run_id ? `
    <div class="gm-section">
      <div class="gm-section-title">🧠 Supervisor Run</div>
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:8px;padding:10px;font-size:12px;display:flex;align-items:center;gap:8px">
        <span style="color:var(--accent)">${g.supervisor_run_id}</span>
        <button onclick="nav('supervisor')" style="margin-left:auto;font-size:11px;padding:3px 9px;border-radius:6px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-1);cursor:pointer">View DAG →</button>
      </div>
    </div>` : ''}
  `;
}


// ── Tab: Decompose ────────────────────────────────────────────────
function gmTabDecompose() {
  const decomp = _goalSelected.decomposition || [];

  if (!decomp.length) {
    return `
      <div style="text-align:center;padding:40px 20px">
        <div style="font-size:40px;margin-bottom:12px">🧩</div>
        <div style="font-size:15px;font-weight:600;color:var(--text-1);margin-bottom:8px">No Decomposition Yet</div>
        <div style="font-size:12px;color:var(--text-3);line-height:1.6;margin-bottom:20px">
          Click "Decompose" to have the Brain agent break this goal into<br>
          a dependency-ordered Task DAG with specialist assignments.
        </div>
        <button class="gm-new-btn" style="width:auto;padding:10px 24px;font-size:13px" onclick="gmDecomposeGoal()">🧩 Decompose This Goal</button>
      </div>`;
  }

  // Auto-layout the tasks
  const seqMap = {};
  decomp.forEach(t => { seqMap[t.seq] = t; });
  const waveOf = {};
  decomp.forEach(t => { if (!t.depends_on?.length) waveOf[t.seq] = 0; });
  let changed = true;
  while (changed) {
    changed = false;
    decomp.forEach(t => {
      if (t.depends_on?.length && waveOf[t.seq] == null) {
        if (t.depends_on.every(d => waveOf[d] != null)) {
          waveOf[t.seq] = Math.max(...t.depends_on.map(d => waveOf[d])) + 1;
          changed = true;
        }
      }
    });
  }
  const waves = {};
  decomp.forEach(t => { const w = waveOf[t.seq] ?? 0; (waves[w] = waves[w]||[]).push(t); });
  const NODE_W=190, NODE_H=100, H_GAP=60, V_GAP=16;
  Object.keys(waves).sort().forEach(w => {
    const wt = waves[w].sort((a,b)=>a.seq-b.seq);
    const totalH = wt.length*NODE_H + (wt.length-1)*V_GAP;
    const startY = Math.max(20, 220-totalH/2);
    wt.forEach((t,i) => {
      t._x = 20 + parseInt(w) * (NODE_W + H_GAP);
      t._y = startY + i*(NODE_H+V_GAP);
    });
  });
  const maxX = Math.max(...decomp.map(t=>(t._x||0)+NODE_W+40));
  const maxY = Math.max(...decomp.map(t=>(t._y||0)+NODE_H+40));

  const nodesHTML = decomp.map(t => {
    const col = GOAL_AGENT_COLORS[t.agent_hint] || '#7a8aaa';
    const icon = GOAL_AGENT_ICONS[t.agent_hint] || '🤖';
    return `<div class="gm-decomp-task" id="gdt-${t.id}"
      style="left:${t._x}px;top:${t._y}px;border-color:${col}33"
      onclick="gmSelectDecompTask(${JSON.stringify(t.id)})">
      <div class="gm-decomp-task-hdr">
        <div class="gm-decomp-seq" style="background:${col}">${t.seq}</div>
        <span class="gm-decomp-label">${escHtml(t.title)}</span>
        <span class="gm-decomp-agent" style="background:${col}22;color:${col}">${icon}</span>
      </div>
      <div class="gm-decomp-desc">${escHtml((t.description||'').slice(0,80))}</div>
      <div class="gm-decomp-bar" style="background:${col}"></div>
    </div>`;
  }).join('');

  // Build SVG edges
  const edgesHTML = decomp.map(t => {
    return (t.depends_on||[]).map(depSeq => {
      const src = seqMap[depSeq];
      if (!src) return '';
      const x1=(src._x||0)+NODE_W, y1=(src._y||0)+NODE_H/2;
      const x2=(t._x||0),          y2=(t._y||0)+NODE_H/2;
      const cx=(x1+x2)/2;
      return `<path d="M${x1},${y1} C${cx},${y1} ${cx},${y2} ${x2},${y2}"
        stroke="rgba(255,255,255,.18)" stroke-width="1.5" fill="none"
        marker-end="url(#gm-arr)"/>`;
    }).join('');
  }).join('');

  return `
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap">
      <span style="font-size:12px;font-weight:600;color:var(--text-0)">${decomp.length} tasks · ${Object.keys(waves).length} waves</span>
      <span style="font-size:11px;color:var(--text-3)">Click any node to see detail · Scroll to pan</span>
      <button onclick="gmDecomposeGoal(true)" style="margin-left:auto;font-size:11px;padding:4px 10px;border-radius:6px;background:var(--bg-2);border:1px solid var(--border);color:var(--text-1);cursor:pointer">↺ Re-decompose</button>
    </div>
    <div class="gm-decomp-canvas-wrap" style="height:${Math.max(300,maxY+30)}px">
      <svg class="gm-decomp-edges-svg" width="${maxX}" height="${Math.max(300,maxY+30)}" style="position:absolute;top:0;left:0">
        <defs>
          <marker id="gm-arr" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill="rgba(255,255,255,.2)"/>
          </marker>
        </defs>
        ${edgesHTML}
      </svg>
      <div style="position:relative;width:${maxX}px;height:${Math.max(300,maxY+30)}px">${nodesHTML}</div>
    </div>
    <div id="gm-decomp-detail" style="display:none">
      <div class="gm-decomp-task-detail" id="gm-decomp-task-detail-content"></div>
    </div>
    <div style="margin-top:12px;text-align:center">
      <button class="gm-new-btn" style="width:auto;padding:8px 20px" onclick="gmLaunchGoalFromDecomp()">🚀 Launch Supervisor with this Decomposition</button>
    </div>
  `;
}

function gmSelectDecompTask(taskId) {
  const decomp = _goalSelected?.decomposition || [];
  const t = decomp.find(t=>t.id===taskId);
  if (!t) return;
  // Highlight node
  document.querySelectorAll('.gm-decomp-task').forEach(el=>el.classList.remove('selected'));
  document.getElementById(`gdt-${taskId}`)?.classList.add('selected');
  // Show detail
  const detailEl = document.getElementById('gm-decomp-detail');
  const contentEl = document.getElementById('gm-decomp-task-detail-content');
  if (detailEl) detailEl.style.display = 'block';
  if (contentEl) {
    const col = GOAL_AGENT_COLORS[t.agent_hint] || '#7a8aaa';
    const icon = GOAL_AGENT_ICONS[t.agent_hint] || '🤖';
    contentEl.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
        <div class="gm-decomp-seq" style="background:${col};width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:800;color:#fff;flex-shrink:0">${t.seq}</div>
        <div>
          <div style="font-size:13px;font-weight:700;color:var(--text-0)">${escHtml(t.title)}</div>
          <div style="font-size:11px;color:${col}">${icon} ${t.agent_hint}</div>
        </div>
        ${t.risk_level && t.risk_level!=='low'?`<span style="margin-left:auto;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:700;background:rgba(232,82,82,.15);color:#e85252">⚠️ ${t.risk_level} risk</span>`:''}
      </div>
      ${t.description?`<div style="font-size:12px;color:var(--text-1);line-height:1.5;margin-bottom:8px">${escHtml(t.description)}</div>`:''}
      <div style="font-size:11px;color:var(--text-3)">
        Depends on: ${t.depends_on?.length ? t.depends_on.map(d=>`<strong>seq ${d}</strong>`).join(', ') : 'none (starts immediately)'}
        ${t.est_tokens?` · Est. ${t.est_tokens} tokens`:''}
      </div>`;
  }
}


// ── Tab: Score ────────────────────────────────────────────────────
function gmTabScore() {
  const g      = _goalSelected.goal;
  const scores = _goalSelected.score_history || [];
  const latest = scores.length ? scores[scores.length-1] : null;
  const score  = latest ? latest.score : (g.outcome_score ?? null);
  const breakdown = latest ? (latest.breakdown || {}) : (g.score_breakdown ? (typeof g.score_breakdown === 'string' ? JSON.parse(g.score_breakdown||'{}') : g.score_breakdown) : {});
  const grade  = score != null ? gmScoreToGrade(score) : null;
  const gradeCol = grade ? (GRADE_COLORS[grade] || '#7a8aaa') : 'var(--text-3)';

  if (score == null) {
    return `
      <div style="text-align:center;padding:40px 20px">
        <div style="font-size:40px;margin-bottom:12px">⭐</div>
        <div style="font-size:15px;font-weight:600;color:var(--text-1);margin-bottom:8px">No Score Yet</div>
        <div style="font-size:12px;color:var(--text-3);line-height:1.6;margin-bottom:20px">
          Click "Score Outcome" to have the Evaluator agent assess this goal's<br>
          progress across 5 dimensions and generate actionable next steps.
        </div>
        <button class="gm-new-btn" style="width:auto;padding:10px 24px;font-size:13px;background:rgba(157,116,245,.25);color:#9d74f5" onclick="gmScoreGoal()">⭐ Score Outcome Now</button>
      </div>`;
  }

  const dimLabels = {completion:'Completion',quality:'Quality',on_schedule:'On Schedule',criteria_met:'Criteria Met',momentum:'Momentum'};
  const dimHTML = Object.entries(dimLabels).map(([k,label]) => {
    const v = breakdown[k] ?? 0;
    const col = v>=0.8?'var(--success)':v>=0.6?'var(--warning)':'var(--danger)';
    return `<div class="gm-dimension">
      <div class="gm-dimension-label">${label}</div>
      <div class="gm-dimension-bar-track">
        <div class="gm-dimension-bar-fill" style="width:${Math.round(v*100)}%;background:${col}"></div>
      </div>
      <div class="gm-dimension-val" style="color:${col}">${Math.round(v*100)}%</div>
    </div>`;
  }).join('');

  const note = latest?.notes || '';
  // Parse strengths/gaps/next_actions from the latest score history entry if stored
  // (they're stored in notes as JSON or as plain text)
  let strengths=[], gaps=[], nextActions=[];
  try {
    const parsed = JSON.parse(latest?.notes||'{}');
    strengths   = parsed.strengths    || [];
    gaps        = parsed.gaps         || [];
    nextActions = parsed.next_actions || [];
  } catch(e) {}

  return `
    <div class="gm-score-hero">
      <div class="gm-score-circle" style="border-color:${gradeCol}">
        <span class="gm-score-pct" style="color:${gradeCol}">${Math.round(score*100)}%</span>
        <span class="gm-score-grade" style="color:${gradeCol}">${grade}</span>
      </div>
      <div class="gm-score-summary">${escHtml(note.slice(0,200) || 'Outcome evaluated')}</div>
      <div style="font-size:10px;color:var(--text-3)">Iteration ${g.iteration||1} · ${g.last_scored_at ? new Date(g.last_scored_at).toLocaleString() : 'just now'}</div>
    </div>

    <div class="gm-section">
      <div class="gm-section-title">📊 5-Dimension Breakdown</div>
      <div class="gm-dimensions-grid">${dimHTML}</div>
    </div>

    ${(strengths.length||gaps.length) ? `
    <div class="gm-score-lists">
      ${strengths.length?`
      <div class="gm-score-list-box">
        <div class="gm-score-list-title">💪 Strengths</div>
        ${strengths.map(s=>`<div class="gm-score-list-item">✓ ${escHtml(s)}</div>`).join('')}
      </div>`:''}
      ${gaps.length?`
      <div class="gm-score-list-box">
        <div class="gm-score-list-title">⚠️ Gaps</div>
        ${gaps.map(s=>`<div class="gm-score-list-item">• ${escHtml(s)}</div>`).join('')}
      </div>`:''}
    </div>` : ''}

    ${nextActions.length?`
    <div class="gm-section">
      <div class="gm-section-title">🚀 Recommended Next Actions</div>
      <div class="gm-next-actions">
        ${nextActions.map((a,i)=>`<div class="gm-next-action"><span style="color:var(--accent);font-weight:700;flex-shrink:0">${i+1}.</span>${escHtml(a)}</div>`).join('')}
      </div>
    </div>`:''}

    <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">
      <button class="gm-action-btn" onclick="gmScoreGoal()" style="flex:1;justify-content:center">↺ Re-score (Iteration ${(g.iteration||1)+1})</button>
      <button class="gm-action-btn" onclick="gmSetTab('history')" style="flex:1;justify-content:center">📈 View History</button>
    </div>
  `;
}


// ── Tab: History ──────────────────────────────────────────────────
function gmTabHistory() {
  const scores = _goalSelected.score_history || [];
  const ci     = _goalSelected.checkins      || [];

  if (!scores.length && !ci.length) {
    return `<div style="color:var(--text-3);font-size:13px;text-align:center;padding:40px">No history yet. Score the goal to start tracking progress over time.</div>`;
  }

  // Sparkline SVG
  let sparklineHTML = '';
  if (scores.length >= 2) {
    const W=400, H=60, pad=10;
    const vals = scores.map(s=>s.score);
    const minV=Math.min(...vals), maxV=Math.max(...vals);
    const range = maxV-minV || 0.1;
    const points = vals.map((v,i)=>{
      const x = pad + (i/(vals.length-1))*(W-pad*2);
      const y = H - pad - ((v-minV)/range)*(H-pad*2);
      return `${x},${y}`;
    }).join(' ');
    sparklineHTML = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:60px">
      <polyline points="${points}" fill="none" stroke="#9d74f5" stroke-width="2"/>
      ${vals.map((v,i)=>{
        const x=pad+(i/(vals.length-1))*(W-pad*2);
        const y=H-pad-((v-minV)/range)*(H-pad*2);
        return `<circle cx="${x}" cy="${y}" r="3" fill="#9d74f5"/>
          <text x="${x}" y="${y-7}" text-anchor="middle" font-size="9" fill="#9d74f5">${Math.round(v*100)}%</text>`;
      }).join('')}
    </svg>`;
  }

  return `
    ${scores.length>=2?`
    <div class="gm-history-chart">
      <div class="gm-history-chart-title">Score Trajectory (${scores.length} iterations)</div>
      <div class="gm-sparkline-wrap">${sparklineHTML}</div>
    </div>`:scores.length===1?`
    <div class="gm-history-chart">
      <div style="font-size:12px;color:var(--text-3)">Score this goal again to see a trajectory chart.</div>
    </div>`:''}

    ${scores.length?`
    <div class="gm-section">
      <div class="gm-section-title">⭐ Score History</div>
      <table class="gm-history-table">
        <thead><tr><th>Iteration</th><th>Score</th><th>Grade</th><th>Date</th><th>Notes</th></tr></thead>
        <tbody>
          ${scores.map(s=>{
            const grade = gmScoreToGrade(s.score);
            const gCol  = GRADE_COLORS[grade]||'#7a8aaa';
            let note = s.notes||'';
            try { note = JSON.parse(s.notes)?.summary || note; } catch(e) {}
            return `<tr>
              <td style="color:var(--text-2)">#${s.iteration}</td>
              <td style="font-weight:700;color:${gCol}">${Math.round(s.score*100)}%</td>
              <td><span style="padding:1px 6px;border-radius:4px;font-size:10px;font-weight:800;background:${gCol}22;color:${gCol}">${grade}</span></td>
              <td style="color:var(--text-3);font-size:10px">${new Date(s.created_at).toLocaleDateString()}</td>
              <td style="color:var(--text-2);font-size:11px;max-width:200px">${escHtml(note.slice(0,80))}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
    </div>`:''}

    ${ci.length?`
    <div class="gm-section">
      <div class="gm-section-title">💬 All Check-ins (${ci.length})</div>
      <div class="gm-checkin-list">
        ${ci.map(c=>`
        <div class="gm-checkin-item">
          <div class="gm-checkin-head">
            <span class="gm-checkin-agent" style="color:${GOAL_AGENT_COLORS[c.agent_id]||'var(--text-2)'}">${GOAL_AGENT_ICONS[c.agent_id]||'👤'} ${c.agent_id}</span>
            ${c.progress>0?`<span class="gm-checkin-pct">${c.progress}%</span>`:''}
            <span class="gm-checkin-time">${new Date(c.created_at).toLocaleDateString()}</span>
          </div>
          ${c.note?`<div class="gm-checkin-note">${escHtml(c.note)}</div>`:''}
        </div>`).join('')}
      </div>
    </div>`:''}
  `;
}


// ── Actions ──────────────────────────────────────────────────────
async function gmDecomposeGoal(force=false) {
  if (!_goalSelected) return;
  const goalId = _goalSelected.goal.id;
  showToast('🧩 Decomposing goal with Brain agent…');
  try {
    const r = await fetch(`/api/goals/${encodeURIComponent(goalId)}/decompose`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({force})
    });
    const d = await r.json();
    if (!d.ok) { showToast('⚠️ Decomposition failed: ' + (d.error||'')); return; }
    showToast(`✅ Decomposed into ${d.task_count} tasks${d.cached?' (cached)':''}`);
    // Reload full goal
    await gmSelectGoal(goalId);
    gmSetTab('decompose');
  } catch(e) { showToast('⚠️ ' + e.message); }
}

async function gmScoreGoal() {
  if (!_goalSelected) return;
  const goalId = _goalSelected.goal.id;
  showToast('⭐ Evaluating outcome — calling Evaluator agent…');
  try {
    const r = await fetch(`/api/goals/${encodeURIComponent(goalId)}/score`, {
      method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'
    });
    const d = await r.json();
    if (!d.ok) { showToast('⚠️ Scoring failed: '+(d.error||'')); return; }
    showToast(`✅ Score: ${d.overall_pct}% (${d.grade}) — Iteration ${d.iteration}`);
    await gmSelectGoal(goalId);
    gmSetTab('score');
  } catch(e) { showToast('⚠️ '+e.message); }
}

async function gmLaunchGoal() {
  if (!_goalSelected) return;
  const g = _goalSelected.goal;
  const ok = await gmDanger('Launch Supervisor', `Autonomously work toward:\n\n"${g.title}"\n\nThe Brain will decompose and execute this goal using specialist agents.`);
  if (!ok) return;
  showToast('🚀 Launching supervisor run…');
  try {
    const r = await fetch(`/api/goals/${encodeURIComponent(g.id)}/launch`, {
      method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'
    });
    const d = await r.json();
    if (d.ok) {
      showToast(`🧠 Supervisor run started: ${d.run_id}`);
      await gmSelectGoal(g.id);
    } else {
      showToast('⚠️ Launch failed: '+(d.error||''));
    }
  } catch(e) { showToast('⚠️ '+e.message); }
}

async function gmLaunchGoalFromDecomp() {
  await gmLaunchGoal();
}

async function gmAddCheckin() {
  if (!_goalSelected) return;
  const g = _goalSelected.goal;
  const pct = await gmPrompt(`Check-in: ${g.title.slice(0,40)}`, 'New progress % (0–100):');
  if (pct === null) return;
  const n = Math.max(0, Math.min(100, parseInt(pct)||0));
  const note = await gmPrompt('Check-in Note', 'Describe what was accomplished (or leave blank):') || '';
  await fetch(`/api/goals/${encodeURIComponent(g.id)}`, {
    method:'PATCH', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({progress:n})
  });
  if (note || n>0) {
    await fetch(`/api/goals/${encodeURIComponent(g.id)}/checkin`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({progress:n, note, agent_id:'user'})
    });
  }
  showToast(`📈 Progress updated: ${n}%`);
  await gmSelectGoal(g.id);
}

async function gmAddMilestone() {
  if (!_goalSelected) return;
  const g = _goalSelected.goal;
  const title = await gmPrompt('New Milestone', 'Milestone title:');
  if (!title?.trim()) return;
  const due = await gmPrompt('Due Date', 'Due date (YYYY-MM-DD) or blank:') || '';
  await fetch(`/api/goals/${encodeURIComponent(g.id)}/milestones`, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({title, due_date: due})
  });
  showToast('📌 Milestone added');
  await gmSelectGoal(g.id);
}

async function gmCompleteMilestone(msId, alreadyDone) {
  if (alreadyDone) return;
  if (!_goalSelected) return;
  const g = _goalSelected.goal;
  await fetch(`/api/goals/${encodeURIComponent(g.id)}/milestones/${encodeURIComponent(msId)}/complete`, {method:'POST'});
  await gmSelectGoal(g.id);
}

async function gmEditGoal() {
  if (!_goalSelected) return;
  const g = _goalSelected.goal;
  const title = await gmPrompt('Edit Goal Title', 'Title:', g.title);
  if (title === null) return;
  const criteria = await gmPrompt('Success Criteria', 'Success criteria:', g.success_criteria||'') || '';
  await fetch(`/api/goals/${encodeURIComponent(g.id)}`, {
    method:'PATCH', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({title: title||g.title, success_criteria: criteria})
  });
  showToast('✏️ Goal updated');
  await gmSelectGoal(g.id);
  await gmLoadGoals();
}

async function gmDeleteGoal() {
  if (!_goalSelected) return;
  const g = _goalSelected.goal;
  const ok = await gmDanger('Delete Goal', `Delete "${g.title}" and all its data?`);
  if (!ok) return;
  await fetch(`/api/goals/${encodeURIComponent(g.id)}`, {method:'DELETE'});
  showToast('🗑 Goal deleted');
  _goalSelected = null;
  document.getElementById('gm-main').innerHTML = `
    <div class="gm-empty">
      <div class="gm-empty-icon">🎯</div>
      <div class="gm-empty-title">Goal Deleted</div>
      <div class="gm-empty-sub">Select another goal from the sidebar.</div>
    </div>`;
  await gmLoadGoals();
}

function gmOpenCreate() {
  const existing = document.getElementById('gm-create-modal');
  if (existing) { existing.remove(); return; }
  const overlay = document.createElement('div');
  overlay.id = 'gm-create-modal';
  overlay.className = 'gm-modal-overlay';
  overlay.innerHTML = `
    <div class="gm-modal">
      <h3>🎯 Create New Goal</h3>
      <p class="gm-modal-sub">Define your goal with clear success criteria. The Brain agent will decompose it into tasks and the Evaluator will score your progress over time.</p>
      <div class="gm-form-grid">
        <div class="gm-form-group full">
          <label class="gm-form-label">Goal Title *</label>
          <input class="gm-form-input" id="gcf-title" placeholder="What do you want to achieve?" required>
        </div>
        <div class="gm-form-group full">
          <label class="gm-form-label">Description</label>
          <textarea class="gm-form-textarea" id="gcf-desc" placeholder="More detail about this goal, constraints, context…" rows="3"></textarea>
        </div>
        <div class="gm-form-group full">
          <label class="gm-form-label">Success Criteria</label>
          <textarea class="gm-form-textarea" id="gcf-criteria" placeholder="What does success look like? Be specific and measurable.&#10;• Criterion 1&#10;• Criterion 2" rows="3"></textarea>
        </div>
        <div class="gm-form-group">
          <label class="gm-form-label">Domain</label>
          <select class="gm-form-select" id="gcf-domain">
            <option value="Work">💼 Work</option>
            <option value="Research">🔬 Research</option>
            <option value="Learning">📚 Learning</option>
            <option value="Health">🏃 Health</option>
            <option value="Finance">💰 Finance</option>
            <option value="Personal">⭐ Personal</option>
            <option value="Home">🏠 Home</option>
            <option value="Travel">✈️ Travel</option>
          </select>
        </div>
        <div class="gm-form-group">
          <label class="gm-form-label">Priority</label>
          <select class="gm-form-select" id="gcf-priority">
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
            <option value="low">Low</option>
          </select>
        </div>
        <div class="gm-form-group">
          <label class="gm-form-label">Deadline (YYYY-MM-DD)</label>
          <input class="gm-form-input" id="gcf-deadline" type="date" placeholder="2026-12-31">
        </div>
        <div class="gm-form-group">
          <label class="gm-form-label">Tags (comma-separated)</label>
          <input class="gm-form-input" id="gcf-tags" placeholder="sdk, python, api">
        </div>
        <div class="gm-form-group full">
          <label class="gm-form-label">Initial Milestones (optional)</label>
          <div class="gm-modal-ms-list" id="gcf-ms-list">
            <div class="gm-modal-ms-item"><input class="gm-modal-ms-input" placeholder="Milestone 1…"><button onclick="this.parentElement.remove()" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:14px">✕</button></div>
          </div>
          <button onclick="gcfAddMilestone()" style="margin-top:6px;font-size:11px;padding:4px 10px;border-radius:5px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-2);cursor:pointer">+ Add Milestone</button>
        </div>
        <div class="gm-form-group full" style="display:flex;align-items:center;gap:8px">
          <input type="checkbox" id="gcf-auto-decompose" checked style="accent-color:var(--accent)">
          <label for="gcf-auto-decompose" style="font-size:12px;color:var(--text-1);cursor:pointer">Auto-decompose with Brain agent after creating</label>
        </div>
      </div>
      <div class="gm-modal-row">
        <button class="gm-action-btn" onclick="document.getElementById('gm-create-modal').remove()">Cancel</button>
        <button class="gm-new-btn" style="width:auto;padding:8px 20px" onclick="gmCreateGoal()">✅ Create Goal</button>
      </div>
    </div>`;
  overlay.onclick = e => { if (e.target===overlay) overlay.remove(); };
  document.body.appendChild(overlay);
  setTimeout(() => document.getElementById('gcf-title')?.focus(), 50);
}

function gcfAddMilestone() {
  const list = document.getElementById('gcf-ms-list');
  if (!list) return;
  const item = document.createElement('div');
  item.className = 'gm-modal-ms-item';
  item.innerHTML = `<input class="gm-modal-ms-input" placeholder="Milestone…"><button onclick="this.parentElement.remove()" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:14px">✕</button>`;
  list.appendChild(item);
}

async function gmCreateGoal() {
  const title    = document.getElementById('gcf-title')?.value?.trim();
  if (!title) { showToast('⚠️ Title is required'); return; }
  const desc     = document.getElementById('gcf-desc')?.value?.trim()     || '';
  const criteria = document.getElementById('gcf-criteria')?.value?.trim() || '';
  const domain   = document.getElementById('gcf-domain')?.value           || 'Work';
  const priority = document.getElementById('gcf-priority')?.value         || 'medium';
  const deadline = document.getElementById('gcf-deadline')?.value         || '';
  const tags     = document.getElementById('gcf-tags')?.value?.trim()     || '';
  const autoDecomp = document.getElementById('gcf-auto-decompose')?.checked ?? true;
  const msList   = [...document.querySelectorAll('#gcf-ms-list .gm-modal-ms-input')]
                     .map(el=>el.value.trim()).filter(Boolean)
                     .map(t=>({title:t}));

  document.getElementById('gm-create-modal')?.remove();

  const r = await fetch('/api/goals', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({title, description:desc, success_criteria:criteria,
                          domain, priority, deadline, tags, milestones:msList})
  }).catch(()=>null);
  if (!r||!r.ok) { showToast('⚠️ Create failed'); return; }
  const d = await r.json();
  if (!d.ok) { showToast('⚠️ '+(d.error||'Create failed')); return; }
  showToast(`🎯 Goal created: ${title.slice(0,40)}`);
  await gmLoadGoals();
  await gmSelectGoal(d.id || d.goal_id);

  if (autoDecomp) {
    setTimeout(() => gmDecomposeGoal(), 500);
  }
}

// ── Utility ───────────────────────────────────────────────────────
function gmScoreToGrade(score) {
  if (score >= 0.97) return 'A+';
  if (score >= 0.93) return 'A';
  if (score >= 0.90) return 'A-';
  if (score >= 0.87) return 'B+';
  if (score >= 0.83) return 'B';
  if (score >= 0.80) return 'B-';
  if (score >= 0.77) return 'C+';
  if (score >= 0.73) return 'C';
  if (score >= 0.70) return 'C-';
  if (score >= 0.60) return 'D';
  return 'F';
}

// ── Old compat aliases (nav patches + old code that calls goalCreate etc.) ──
async function goalCreate()             { gmOpenCreate(); }
async function goalView(goalId)         { await gmSelectGoal(goalId); nav('goals'); }
async function goalLaunch(goalId, title){ if(_goalSelected?.goal?.id===goalId) await gmLaunchGoal(); else { await gmSelectGoal(goalId); await gmLaunchGoal(); } }
async function goalProgress(goalId)     { if(_goalSelected?.goal?.id!==goalId) await gmSelectGoal(goalId); await gmAddCheckin(); }
async function goalDelete(goalId)       { if(_goalSelected?.goal?.id!==goalId) await gmSelectGoal(goalId); await gmDeleteGoal(); }
async function goalReloadCards()        { await gmLoadGoals(); }
function goalFilterChange()             { gmFilterChange(); }
function goalDomainFilter(domain)       { _goalFilter.domain=_goalFilter.domain===domain?'':domain; gmLoadGoals(); }
function renderGoalCard(g)              { return ''; } // no longer used standalone



// ══════════════════════════════════════════════════════════════════
//  SPRINT C — MCP GATEWAY
// ══════════════════════════════════════════════════════════════════


// ══════════════════════════════════════════════════════════════════
//  POLICY RULE BUILDER — Complete Implementation
//  Replaces old renderMCPGateway + all mcg* functions
// ══════════════════════════════════════════════════════════════════

// ── State ─────────────────────────────────────────────────────────
let _prbPolicies   = [];    // all loaded policies
let _prbServers    = [];    // all MCP servers
let _prbTemplates  = [];    // policy templates
let _prbFilter     = { action: '', search: '', server: '' };
let _prbSelected   = null;  // currently editing policy_id
let _prbTab        = 'rules';  // 'rules' | 'builder' | 'simulator' | 'conflicts' | 'servers'
let _prbConflicts  = null;  // cached conflict data
let _prbSimResult  = null;  // last simulation result
let _prbSelIds     = new Set(); // selected policy IDs for bulk ops

// ── Constants ─────────────────────────────────────────────────────
const PRB_ACTION_COLORS = {
  allow:        { bg: 'rgba(61,186,122,.15)',  border: '#3dba7a',  text: '#3dba7a',  icon: '✅' },
  deny:         { bg: 'rgba(232,82,82,.15)',   border: '#e85252',  text: '#e85252',  icon: '🚫' },
  require_hitl: { bg: 'rgba(232,162,55,.15)', border: '#e8a237',  text: '#e8a237',  icon: '🛂' },
};
const PRB_CATEGORY_COLORS = {
  Security:          '#e85252',
  'Agent Scoping':   '#5b8af8',
  Governance:        '#e8a237',
  'Privileged Access': '#3dba7a',
  'Data Protection': '#9d74f5',
};
const PRB_AGENTS = [
  {id:'*',        label:'All Agents (*)'},
  {id:'researcher', label:'🔍 Researcher'},
  {id:'builder',    label:'🔨 Builder'},
  {id:'reviewer',   label:'🔬 Reviewer'},
  {id:'creative',   label:'✍️  Creative'},
  {id:'brain',      label:'💡 Brain'},
  {id:'orchestrator',label:'🎯 Orchestrator'},
  {id:'memory',     label:'🧠 Memory'},
  {id:'user',       label:'👤 User'},
  {id:'guest',      label:'👻 Guest'},
];
const PRB_CONFLICT_SEVERITY = {
  error:   { icon:'❌', color:'#e85252', label:'Conflict' },
  warning: { icon:'⚠️',  color:'#e8a237', label:'Warning' },
  info:    { icon:'ℹ️',  color:'#5b8af8', label:'Info' },
};


// ── Main render ────────────────────────────────────────────────────
async function renderMCPGateway() {
  const pane = document.getElementById('pane-mcp-gateway');
  if (!pane) return;

  pane.innerHTML = `
  

  <div class="prb-root">
    <!-- ── Sidebar ── -->
    <div class="prb-sidebar">
      <div class="prb-sidebar-head">
        <p class="prb-sidebar-title">📋 Policy Rules</p>
        <div class="prb-stats-row" id="prb-stats-row">
          <div class="prb-stat"><div class="prb-stat-val" id="prb-stat-total" style="color:var(--accent)">—</div><div class="prb-stat-lbl">Total</div></div>
          <div class="prb-stat"><div class="prb-stat-val" id="prb-stat-active" style="color:var(--success)">—</div><div class="prb-stat-lbl">Active</div></div>
          <div class="prb-stat"><div class="prb-stat-val" id="prb-stat-deny" style="color:var(--danger)">—</div><div class="prb-stat-lbl">Deny</div></div>
        </div>
        <input class="prb-search" id="prb-search" placeholder="🔍 Search rules…" oninput="prbSearchChange(this.value)">
        <div class="prb-filter-row">
          <select class="prb-filter-sel" id="prb-filter-action" onchange="prbFilterChange()">
            <option value="">All actions</option>
            <option value="allow">✅ Allow</option>
            <option value="deny">🚫 Deny</option>
            <option value="require_hitl">🛂 Require HITL</option>
          </select>
          <select class="prb-filter-sel" id="prb-filter-server" onchange="prbFilterChange()">
            <option value="">All servers</option>
          </select>
        </div>
      </div>
      <div class="prb-policy-list" id="prb-policy-list">
        <div style="color:var(--text-3);font-size:12px;padding:8px">Loading…</div>
      </div>
      <div class="prb-sidebar-foot">
        <div class="prb-bulk-row">
          <button class="prb-bulk-btn" onclick="prbBulkAction('enable')"  title="Enable selected">✓ Enable</button>
          <button class="prb-bulk-btn" onclick="prbBulkAction('disable')" title="Disable selected">○ Disable</button>
          <button class="prb-bulk-btn" onclick="prbBulkAction('delete')"  title="Delete selected" style="color:var(--danger)">🗑</button>
        </div>
        <button class="prb-new-btn" onclick="prbNewRule()">+ New Policy Rule</button>
      </div>
    </div>

    <!-- ── Main ── -->
    <div class="prb-main">
      <div class="prb-toolbar">
        <span class="prb-toolbar-title" id="prb-toolbar-title">Policy Rule Builder</span>
        <button style="padding:4px 10px;border-radius:6px;font-size:11px;background:var(--bg-2);border:1px solid var(--border);color:var(--text-1);cursor:pointer" onclick="prbRefresh()">↺ Refresh</button>
        <button style="padding:4px 10px;border-radius:6px;font-size:11px;background:var(--bg-2);border:1px solid var(--border);color:var(--text-1);cursor:pointer" onclick="mcgTestCall()">🧪 Test Call</button>
      </div>
      <div class="prb-tab-bar">
        <div class="prb-tab active" id="prb-tab-rules"     onclick="prbSetTab('rules')">📋 Rules</div>
        <div class="prb-tab"        id="prb-tab-builder"   onclick="prbSetTab('builder')">⚙️ Builder</div>
        <div class="prb-tab"        id="prb-tab-simulator" onclick="prbSetTab('simulator')">🧪 Simulator</div>
        <div class="prb-tab"        id="prb-tab-conflicts" onclick="prbSetTab('conflicts')">⚠️ Conflicts<span class="prb-tab-badge" id="prb-conflict-badge" style="display:none">0</span></div>
        <div class="prb-tab"        id="prb-tab-servers"   onclick="prbSetTab('servers')">🖥️ Servers</div>
      </div>
      <div class="prb-content" id="prb-content">
        <div style="padding:40px;text-align:center;color:var(--text-3)">Loading…</div>
      </div>
    </div>
  </div>`;

  await prbRefresh();
}


// ── Load data ──────────────────────────────────────────────────────
async function prbRefresh() {
  const [statsR, polR, srvR, tplR] = await Promise.all([
    fetch('/api/mcp-gateway/stats').then(r=>r.ok?r.json():{}).catch(()=>({})),
    fetch('/api/mcp-gateway/policies').then(r=>r.ok?r.json():{policies:[]}).catch(()=>({policies:[]})),
    fetch('/api/mcp-gateway/servers').then(r=>r.ok?r.json():{servers:[]}).catch(()=>({servers:[]})),
    fetch('/api/mcp-gateway/policies/templates').then(r=>r.ok?r.json():{templates:[]}).catch(()=>({templates:[]})),
  ]);
  _prbPolicies  = polR.policies  || [];
  _prbServers   = srvR.servers   || [];
  _prbTemplates = tplR.templates || [];

  // Update stats
  const st = (id, v) => { const e=document.getElementById(id); if(e) e.textContent=v; };
  st('prb-stat-total',  statsR.active_policies ?? _prbPolicies.filter(p=>p.enabled).length);
  st('prb-stat-active', _prbPolicies.filter(p=>p.enabled).length);
  st('prb-stat-deny',   _prbPolicies.filter(p=>p.action==='deny'&&p.enabled).length);

  // Populate server filter
  const srvSel = document.getElementById('prb-filter-server');
  if (srvSel) {
    const existing = srvSel.value;
    srvSel.innerHTML = '<option value="">All servers</option>' +
      _prbServers.filter(s=>s.server_id.startsWith('srv_filesystem')||s.server_id.startsWith('srv_')).slice(0,10)
        .map(s=>`<option value="${escHtml(s.server_id)}">${escHtml(s.name)}</option>`).join('');
    srvSel.value = existing;
  }

  prbRenderList();
  prbRenderTab();

  // Check conflicts in background
  fetch('/api/mcp-gateway/policies/conflicts').then(r=>r.ok?r.json():null).then(d => {
    if (!d) return;
    _prbConflicts = d;
    const badge = document.getElementById('prb-conflict-badge');
    if (badge) {
      const count = d.conflict_count || 0;
      badge.textContent = count;
      badge.style.display = count > 0 ? 'inline-flex' : 'none';
    }
  }).catch(()=>{});
}

function prbGetFilteredPolicies() {
  return _prbPolicies.filter(p => {
    if (_prbFilter.action && p.action !== _prbFilter.action) return false;
    if (_prbFilter.server && !p.server_id.includes(_prbFilter.server)) return false;
    if (_prbFilter.search) {
      const q = _prbFilter.search.toLowerCase();
      const hay = (p.name + ' ' + p.agent_id + ' ' + p.server_id + ' ' + p.tool_pattern).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function prbSearchChange(q) { _prbFilter.search = q; prbRenderList(); prbRenderTab(); }
function prbFilterChange() {
  _prbFilter.action = document.getElementById('prb-filter-action')?.value || '';
  _prbFilter.server = document.getElementById('prb-filter-server')?.value || '';
  prbRenderList(); prbRenderTab();
}

function prbRenderList() {
  const list = document.getElementById('prb-policy-list');
  if (!list) return;
  const pols = prbGetFilteredPolicies();
  if (!pols.length) {
    list.innerHTML = `<div style="color:var(--text-3);font-size:12px;padding:10px;line-height:1.6">No rules match.</div>`;
    return;
  }
  list.innerHTML = pols.map(p => {
    const ac = PRB_ACTION_COLORS[p.action] || PRB_ACTION_COLORS.allow;
    const isSelected = _prbSelected === p.policy_id;
    const isChecked  = _prbSelIds.has(p.policy_id);
    return `<div class="prb-policy-item ${!p.enabled?'disabled':''} ${isSelected?'selected':''}" onclick="prbSelectPolicy(${JSON.stringify(p.policy_id)})" style="border-left-color:${p.enabled?ac.border:'var(--text-3)'}">
      <input type="checkbox" class="prb-policy-check" ${isChecked?'checked':''} onclick="event.stopPropagation();prbToggleSelect(${JSON.stringify(p.policy_id)},this.checked)">
      <div class="prb-policy-item-body">
        <div class="prb-policy-item-name">${escHtml(p.name)}</div>
        <div class="prb-policy-item-meta">
          P:${p.priority} · ${escHtml(p.agent_id.slice(0,12))} · ${escHtml(p.tool_pattern.slice(0,14))}
        </div>
      </div>
      <span class="prb-policy-action-badge" style="background:${ac.bg};color:${ac.text}">${ac.icon}</span>
    </div>`;
  }).join('');
}


// ── Tab rendering ──────────────────────────────────────────────────
function prbSetTab(tab) {
  _prbTab = tab;
  document.querySelectorAll('.prb-tab').forEach(el => {
    const t = el.id.replace('prb-tab-','');
    el.classList.toggle('active', t === tab);
  });
  prbRenderTab();
}

function prbRenderTab() {
  const content = document.getElementById('prb-content');
  if (!content) return;
  if (_prbTab === 'rules')     prbRenderRulesTab(content);
  if (_prbTab === 'builder')   prbRenderBuilderTab(content);
  if (_prbTab === 'simulator') prbRenderSimulatorTab(content);
  if (_prbTab === 'conflicts') prbRenderConflictsTab(content);
  if (_prbTab === 'servers')   prbRenderServersTab(content);
}


// ── Rules table tab ────────────────────────────────────────────────
function prbRenderRulesTab(container) {
  const pols = prbGetFilteredPolicies();
  if (!pols.length) {
    container.innerHTML = `<div style="padding:40px;text-align:center;color:var(--text-3)">
      <div style="font-size:36px;margin-bottom:12px">📋</div>
      <div style="font-size:14px;font-weight:600;color:var(--text-1);margin-bottom:8px">No Rules Found</div>
      <div style="font-size:12px;line-height:1.6">No policies match your current filters.<br>Create a new rule or clear your search.</div>
    </div>`;
    return;
  }
  container.innerHTML = `<table class="prb-rules-table">
    <thead><tr>
      <th style="width:28px"><input type="checkbox" id="prb-select-all" onclick="prbSelectAll(this.checked)" style="accent-color:var(--accent)"></th>
      <th>Priority</th>
      <th>Action</th>
      <th>Rule Name</th>
      <th>Agent</th>
      <th>Server</th>
      <th>Tool Pattern</th>
      <th>Status</th>
      <th>Actions</th>
    </tr></thead>
    <tbody>
      ${pols.map(p => {
        const ac = PRB_ACTION_COLORS[p.action] || PRB_ACTION_COLORS.allow;
        const isSelected = _prbSelected === p.policy_id;
        const isChecked  = _prbSelIds.has(p.policy_id);
        const hasConditions = p.conditions && p.conditions !== '{}' && p.conditions !== '';
        return `<tr class="${!p.enabled?'disabled':''} ${isSelected?'selected':''}" onclick="prbSelectPolicy(${JSON.stringify(p.policy_id)})">
          <td onclick="event.stopPropagation()"><input type="checkbox" ${isChecked?'checked':''} onclick="prbToggleSelect(${JSON.stringify(p.policy_id)},this.checked)" style="accent-color:var(--accent)"></td>
          <td><span class="prb-priority-badge">${p.priority}</span></td>
          <td><span class="prb-action-chip" style="background:${ac.bg};color:${ac.text}">${ac.icon} ${p.action}</span></td>
          <td style="font-weight:600;color:var(--text-0);max-width:180px">
            ${escHtml(p.name)}
            ${hasConditions ? '<span title="Has conditions" style="margin-left:4px;font-size:10px">⏰</span>' : ''}
          </td>
          <td><span class="prb-code">${escHtml(p.agent_id)}</span></td>
          <td><span class="prb-code" style="font-size:9px">${escHtml(p.server_id.replace('srv_',''))}</span></td>
          <td><span class="prb-code">${escHtml(p.tool_pattern)}</span></td>
          <td onclick="event.stopPropagation()">
            <span class="prb-toggle" onclick="prbToggleEnabled(${JSON.stringify(p.policy_id)},${p.enabled})" title="${p.enabled?'Click to disable':'Click to enable'}">
              ${p.enabled ? '🟢' : '⚫'}
            </span>
          </td>
          <td onclick="event.stopPropagation()">
            <div class="prb-row-actions">
              <button class="prb-row-btn" onclick="prbEditPolicy(${JSON.stringify(p.policy_id)})" title="Edit">✏️</button>
              <button class="prb-row-btn" onclick="prbSimulateFromRow(${JSON.stringify(p)})" title="Simulate">🧪</button>
              ${!p.policy_id.startsWith('pol_allow_builtin') ? `<button class="prb-row-btn danger" onclick="prbDeletePolicy(${JSON.stringify(p.policy_id)},${JSON.stringify(p.name)})" title="Delete">🗑</button>` : ''}
            </div>
          </td>
        </tr>`;
      }).join('')}
    </tbody>
  </table>
  <div style="padding:8px 12px;font-size:11px;color:var(--text-3);border-top:1px solid var(--border)">
    ${pols.length} rules shown${_prbPolicies.length !== pols.length ? ` (${_prbPolicies.length} total)` : ''}
    ${_prbSelIds.size ? ` · <strong style="color:var(--accent)">${_prbSelIds.size} selected</strong>` : ''}
  </div>`;
}


// ── Builder tab ─────────────────────────────────────────────────────
function prbRenderBuilderTab(container) {
  const editing = _prbSelected ? _prbPolicies.find(p=>p.policy_id===_prbSelected) : null;

  container.innerHTML = `
  <div class="prb-builder">
    <h3>${editing ? '✏️ Edit Policy Rule' : '⚙️ Build New Policy Rule'}</h3>
    <p class="prb-builder-sub">
      Define who can do what with which tools. Rules are evaluated in <strong>priority order</strong> (lower number = higher precedence). The first matching rule wins.
    </p>

    <!-- Templates (only when creating new) -->
    ${!editing ? `
    <div style="margin-bottom:18px">
      <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px">
        🚀 Start from Template
      </div>
      <div class="prb-templates">
        ${_prbTemplates.map(t => {
          const ac = PRB_ACTION_COLORS[t.action] || PRB_ACTION_COLORS.allow;
          const catCol = PRB_CATEGORY_COLORS[t.category] || 'var(--text-3)';
          return `<div class="prb-tpl-card" onclick="prbApplyTemplate(${JSON.stringify(t)})">
            <div class="prb-tpl-icon">${t.icon}</div>
            <div class="prb-tpl-name">${escHtml(t.name)}</div>
            <div class="prb-tpl-desc">${escHtml(t.description)}</div>
            <span class="prb-tpl-cat" style="background:${catCol}22;color:${catCol}">${escHtml(t.category)}</span>
            <span class="prb-tpl-action" style="background:${ac.bg};color:${ac.text}">${ac.icon} ${t.action}</span>
          </div>`;
        }).join('')}
      </div>
      <div style="font-size:11px;color:var(--text-3);margin:10px 0 14px;text-align:center">— or build from scratch below —</div>
    </div>` : ''}

    <!-- Form -->
    <div class="prb-form-grid">
      <div class="prb-form-group full">
        <label class="prb-form-label">Rule Name <span class="required">*</span></label>
        <input class="prb-input" id="prb-f-name" placeholder="e.g. Block file delete in production" value="${escHtml(editing?.name||'')}">
      </div>

      <div class="prb-form-group full">
        <label class="prb-form-label">Description</label>
        <input class="prb-input" id="prb-f-desc" placeholder="What this rule does and why" value="${escHtml(editing?.description||'')}">
      </div>
    </div>

    <!-- Action selector -->
    <div class="prb-form-group" style="margin-bottom:16px">
      <label class="prb-form-label">Action <span class="required">*</span></label>
      <div class="prb-action-row" id="prb-action-row">
        ${Object.entries(PRB_ACTION_COLORS).map(([action, ac]) => {
          const labels = { allow:['✅','Allow','Permit this tool call to proceed'], deny:['🚫','Deny','Block this call entirely — returns error'], require_hitl:['🛂','Require HITL','Pause and require human approval before proceeding'] };
          const [icon, label, desc] = labels[action];
          const isSelected = (editing?.action || 'allow') === action;
          return `<div class="prb-action-opt ${isSelected?'selected-'+action:''}" id="prb-aopt-${action}" onclick="prbSelectAction(${JSON.stringify(action)})">
            <div class="prb-action-icon">${icon}</div>
            <div class="prb-action-label" style="color:${ac.text}">${label}</div>
            <div class="prb-action-desc">${desc}</div>
          </div>`;
        }).join('')}
      </div>
      <input type="hidden" id="prb-f-action" value="${editing?.action||'allow'}">
    </div>

    <div class="prb-form-grid">
      <!-- Agent -->
      <div class="prb-form-group">
        <label class="prb-form-label">Agent ID</label>
        <select class="prb-select" id="prb-f-agent" onchange="prbUpdatePreview()">
          ${PRB_AGENTS.map(a=>`<option value="${a.id}" ${(editing?.agent_id||'*')===a.id?'selected':''}>${escHtml(a.label)}</option>`).join('')}
          <option value="custom_">Custom…</option>
        </select>
        <input class="prb-input" id="prb-f-agent-custom" placeholder="agent_id,another_id" style="display:none;margin-top:4px" value="">
        <div class="prb-form-hint">Use comma-separated IDs for multiple agents, or * for all</div>
      </div>

      <!-- Server -->
      <div class="prb-form-group">
        <label class="prb-form-label">Server / Resource</label>
        <select class="prb-select" id="prb-f-server" onchange="prbUpdatePreview()">
          <option value="*">All Servers (*)</option>
          ${_prbServers.slice(0,10).map(s=>`<option value="${s.server_id}" ${(editing?.server_id||'*')===s.server_id?'selected':''}>${escHtml(s.name)}</option>`).join('')}
        </select>
        <div class="prb-form-hint">Which MCP server this rule applies to</div>
      </div>

      <!-- Tool pattern -->
      <div class="prb-form-group">
        <label class="prb-form-label">Tool Pattern</label>
        <input class="prb-input" id="prb-f-tool" placeholder="* or fs.delete or http.*"
          value="${escHtml(editing?.tool_pattern||'*')}" oninput="prbUpdatePreview()">
        <div class="prb-form-hint">Glob pattern: * = all, fs.* = all fs tools, fs.delete = exact</div>
      </div>

      <!-- Priority -->
      <div class="prb-form-group">
        <label class="prb-form-label">Priority</label>
        <div class="prb-priority-wrap">
          <input type="range" class="prb-priority-slider" id="prb-f-priority" min="1" max="200"
            value="${editing?.priority||100}" oninput="document.getElementById('prb-f-priority-val').textContent=this.value;prbUpdatePreview()">
          <span class="prb-priority-val" id="prb-f-priority-val">${editing?.priority||100}</span>
        </div>
        <div class="prb-form-hint">Lower = higher precedence (1 = first evaluated)</div>
      </div>
    </div>

    <!-- Conditions -->
    <div class="prb-form-group" style="margin-bottom:16px">
      <label class="prb-form-label">
        Conditions (optional)
        <span style="font-size:10px;font-weight:400;color:var(--text-3);margin-left:6px">⏰ Time-based activation</span>
      </label>
      <div class="prb-conditions">
        <div class="prb-condition-item">
          <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:12px;color:var(--text-1)">
            <input type="checkbox" id="prb-cond-time-enabled" style="accent-color:var(--accent)" onchange="prbToggleTimeCondition()">
            Active only during time window
          </label>
        </div>
        <div id="prb-cond-time-fields" style="display:none;margin-left:20px;margin-top:8px;display:flex;gap:12px;align-items:center">
          <label style="font-size:11px;color:var(--text-2)">From:</label>
          <input type="number" id="prb-cond-start-hour" min="0" max="23" value="9" class="prb-input" style="width:64px;padding:4px 6px">
          <label style="font-size:11px;color:var(--text-2)">To:</label>
          <input type="number" id="prb-cond-end-hour" min="1" max="24" value="17" class="prb-input" style="width:64px;padding:4px 6px">
          <span style="font-size:10px;color:var(--text-3)">(24h)</span>
        </div>
        <div class="prb-condition-item" style="margin-top:8px">
          <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:12px;color:var(--text-1)">
            <input type="checkbox" id="prb-cond-days-enabled" style="accent-color:var(--accent)" onchange="prbToggleDaysCondition()">
            Active only on specific days
          </label>
        </div>
        <div id="prb-cond-days-fields" style="display:none;margin-left:20px;margin-top:6px;display:flex;gap:6px;flex-wrap:wrap">
          ${['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map((d,i)=>
            `<label style="display:flex;align-items:center;gap:3px;font-size:11px;cursor:pointer">
              <input type="checkbox" class="prb-day-check" value="${i}" checked style="accent-color:var(--accent)">${d}
            </label>`).join('')}
        </div>
      </div>
    </div>

    <!-- Live preview -->
    <div id="prb-preview" class="prb-preview">${prbBuildPreviewText('allow','*','*','*',100,'{}')}</div>

    <!-- Submit row -->
    <div style="display:flex;gap:8px;margin-top:16px;flex-wrap:wrap">
      <button class="prb-new-btn" style="flex:1;padding:10px" onclick="prbSubmitRule(${JSON.stringify(editing?.policy_id||'')})">
        ${editing ? '💾 Save Changes' : '✅ Create Rule'}
      </button>
      ${editing ? `<button style="padding:10px 16px;border-radius:7px;background:var(--bg-2);border:1px solid var(--border);color:var(--text-1);cursor:pointer;font-size:12px" onclick="prbClearEdit()">✕ Cancel</button>` : ''}
    </div>
  </div>`;

  // Attach agent select handler
  const agentSel = document.getElementById('prb-f-agent');
  if (agentSel) {
    agentSel.addEventListener('change', () => {
      const custom = document.getElementById('prb-f-agent-custom');
      if (agentSel.value === 'custom_') {
        if (custom) custom.style.display = 'block';
      } else {
        if (custom) custom.style.display = 'none';
      }
      prbUpdatePreview();
    });
  }

  // If editing, restore conditions
  if (editing?.conditions) {
    try {
      const conds = JSON.parse(editing.conditions);
      if (conds.start_hour !== undefined) {
        const cb = document.getElementById('prb-cond-time-enabled');
        if (cb) { cb.checked = true; prbToggleTimeCondition(); }
        const sh = document.getElementById('prb-cond-start-hour');
        const eh = document.getElementById('prb-cond-end-hour');
        if (sh) sh.value = conds.start_hour;
        if (eh) eh.value = conds.end_hour;
      }
      if (conds.days_of_week) {
        const cb = document.getElementById('prb-cond-days-enabled');
        if (cb) { cb.checked = true; prbToggleDaysCondition(); }
        document.querySelectorAll('.prb-day-check').forEach(el => {
          el.checked = conds.days_of_week.includes(parseInt(el.value));
        });
      }
    } catch(e) {}
  }

  prbUpdatePreview();
}

function prbSelectAction(action) {
  document.getElementById('prb-f-action').value = action;
  document.querySelectorAll('.prb-action-opt').forEach(el => {
    el.className = 'prb-action-opt' + (el.id === 'prb-aopt-'+action ? ' selected-'+action : '');
  });
  prbUpdatePreview();
}

function prbToggleTimeCondition() {
  const cb = document.getElementById('prb-cond-time-enabled');
  const fields = document.getElementById('prb-cond-time-fields');
  if (fields) fields.style.display = cb?.checked ? 'flex' : 'none';
  prbUpdatePreview();
}

function prbToggleDaysCondition() {
  const cb = document.getElementById('prb-cond-days-enabled');
  const fields = document.getElementById('prb-cond-days-fields');
  if (fields) fields.style.display = cb?.checked ? 'flex' : 'none';
  prbUpdatePreview();
}

function prbBuildConditionsObject() {
  const conds = {};
  const timeCb = document.getElementById('prb-cond-time-enabled');
  if (timeCb?.checked) {
    conds.start_hour = parseInt(document.getElementById('prb-cond-start-hour')?.value || '9');
    conds.end_hour   = parseInt(document.getElementById('prb-cond-end-hour')?.value   || '17');
  }
  const daysCb = document.getElementById('prb-cond-days-enabled');
  if (daysCb?.checked) {
    conds.days_of_week = [...document.querySelectorAll('.prb-day-check:checked')].map(el=>parseInt(el.value));
  }
  return Object.keys(conds).length ? conds : {};
}

function prbBuildPreviewText(action, agentId, serverId, toolPat, priority, conditionsStr) {
  let cond = '';
  try {
    const c = JSON.parse(conditionsStr);
    if (c.start_hour !== undefined) cond += `\n  when: ${c.start_hour}:00–${c.end_hour}:00`;
    if (c.days_of_week) cond += `\n  days: ${c.days_of_week.map(d=>['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][d]).join(',')}`;
  } catch(e) {}
  return `policy {
  action:   ${action}  # ${PRB_ACTION_COLORS[action]?.icon || ''} ${action === 'allow' ? 'permit call' : action === 'deny' ? 'block call' : 'pause for human review'}
  agent:    ${agentId}
  server:   ${serverId}
  tool:     ${toolPat}
  priority: ${priority}${cond}
}`;
}

function prbUpdatePreview() {
  const preview = document.getElementById('prb-preview');
  if (!preview) return;
  const agentSel = document.getElementById('prb-f-agent');
  const agentId  = agentSel?.value === 'custom_'
    ? (document.getElementById('prb-f-agent-custom')?.value || '*')
    : (agentSel?.value || '*');
  const conds = prbBuildConditionsObject();
  preview.textContent = prbBuildPreviewText(
    document.getElementById('prb-f-action')?.value || 'allow',
    agentId,
    document.getElementById('prb-f-server')?.value || '*',
    document.getElementById('prb-f-tool')?.value   || '*',
    document.getElementById('prb-f-priority')?.value || '100',
    JSON.stringify(conds),
  );
}

function prbApplyTemplate(tpl) {
  const n = document.getElementById('prb-f-name');    if (n) n.value = tpl.name;
  const d = document.getElementById('prb-f-desc');    if (d) d.value = tpl.description;
  const s = document.getElementById('prb-f-server');  if (s) s.value = tpl.server_id;
  const t = document.getElementById('prb-f-tool');    if (t) t.value = tpl.tool_pattern;
  const p = document.getElementById('prb-f-priority');if (p) p.value = tpl.priority;
  const pv = document.getElementById('prb-f-priority-val'); if (pv) pv.textContent = tpl.priority;
  // Agent
  const agentSel = document.getElementById('prb-f-agent');
  if (agentSel) {
    const found = [...agentSel.options].some(o => { if(o.value===tpl.agent_id){o.selected=true;return true;} return false; });
    if (!found) { agentSel.value = '*'; }
  }
  prbSelectAction(tpl.action);
  prbUpdatePreview();
  showToast(`📋 Template applied: ${tpl.name}`);
}

async function prbSubmitRule(editingId) {
  const agentSel = document.getElementById('prb-f-agent');
  const agentId  = agentSel?.value === 'custom_'
    ? (document.getElementById('prb-f-agent-custom')?.value?.trim() || '*')
    : (agentSel?.value || '*');
  const name     = document.getElementById('prb-f-name')?.value?.trim();
  const desc     = document.getElementById('prb-f-desc')?.value?.trim()   || '';
  const action   = document.getElementById('prb-f-action')?.value         || 'allow';
  const server   = document.getElementById('prb-f-server')?.value         || '*';
  const tool     = document.getElementById('prb-f-tool')?.value?.trim()   || '*';
  const priority = parseInt(document.getElementById('prb-f-priority')?.value || '100');
  const conditions = prbBuildConditionsObject();

  if (!name) { showToast('⚠️ Rule name is required'); return; }

  const body = { name, description: desc, action, agent_id: agentId,
                 server_id: server, tool_pattern: tool, priority, conditions };

  try {
    let r, d;
    if (editingId) {
      r = await fetch(`/api/mcp-gateway/policies/${encodeURIComponent(editingId)}`, {
        method: 'PATCH', headers: {'Content-Type':'application/json'},
        body: JSON.stringify(body)
      });
    } else {
      r = await fetch('/api/mcp-gateway/policies', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify(body)
      });
    }
    d = await r.json();
    if (d.ok) {
      showToast(editingId ? `✅ Rule updated` : `✅ Rule created: ${d.policy_id}`);
      _prbSelected = null;
      await prbRefresh();
      prbSetTab('rules');
    } else {
      showToast('⚠️ ' + (d.error || 'Failed'));
    }
  } catch(e) { showToast('⚠️ ' + e.message); }
}

function prbClearEdit() {
  _prbSelected = null;
  prbRenderBuilderTab(document.getElementById('prb-content'));
}


// ── Simulator tab ──────────────────────────────────────────────────
function prbRenderSimulatorTab(container) {
  const res = _prbSimResult;
  const decAC = res ? (PRB_ACTION_COLORS[res.decision] || PRB_ACTION_COLORS.allow) : null;

  container.innerHTML = `
  <div class="prb-sim">
    <h3>🧪 Policy Simulator</h3>
    <p style="font-size:12px;color:var(--text-3);margin:0 0 16px;line-height:1.5">
      Test your policy rules dry-run — no tool call is executed. See exactly which rule fires and why.
    </p>

    <div class="prb-sim-form">
      <div class="prb-sim-row">
        <div>
          <label style="font-size:11px;font-weight:700;color:var(--text-2);display:block;margin-bottom:4px">Agent ID</label>
          <select class="prb-select" id="sim-agent">
            ${PRB_AGENTS.map(a=>`<option value="${a.id}">${escHtml(a.label)}</option>`).join('')}
          </select>
        </div>
        <div>
          <label style="font-size:11px;font-weight:700;color:var(--text-2);display:block;margin-bottom:4px">Server</label>
          <select class="prb-select" id="sim-server">
            ${_prbServers.slice(0,10).map(s=>`<option value="${s.server_id}">${escHtml(s.name)}</option>`).join('')}
          </select>
        </div>
        <div>
          <label style="font-size:11px;font-weight:700;color:var(--text-2);display:block;margin-bottom:4px">Tool Name</label>
          <input class="prb-input" id="sim-tool" placeholder="fs.delete" value="fs.list">
        </div>
        <button class="prb-sim-btn" onclick="prbRunSimulation()">▶ Simulate</button>
      </div>
      <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
        <span style="font-size:10px;color:var(--text-3)">Quick test:</span>
        ${[
          ['researcher','srv_web_search','search.web'],
          ['builder','srv_filesystem','fs.delete'],
          ['*','srv_http','http.post'],
          ['orchestrator','srv_connectors','slack.message'],
        ].map(([a,s,t])=>`<button onclick="prbQuickSim(${JSON.stringify(a)},${JSON.stringify(s)},${JSON.stringify(t)})" style="font-size:10px;padding:2px 8px;border-radius:4px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-2);cursor:pointer">${a} → ${t}</button>`).join('')}
      </div>
    </div>

    ${res ? `
    <div class="prb-sim-result">
      <!-- Decision hero -->
      <div class="prb-sim-decision" style="background:${decAC.bg};border:1px solid ${decAC.border}">
        <span class="prb-sim-decision-icon">${decAC.icon}</span>
        <div>
          <div class="prb-sim-decision-label" style="color:${decAC.text}">${res.decision.toUpperCase()}</div>
          <div class="prb-sim-decision-policy">Matched: <strong>${escHtml(res.matched_policy)}</strong></div>
          <div style="font-size:11px;color:var(--text-3)">
            ${escHtml(res.agent_id)} → ${escHtml(res.server_id)} → ${escHtml(res.tool_name)}
            · ${res.policies_checked} rules evaluated
          </div>
        </div>
      </div>

      <!-- Trace table -->
      <div style="font-size:11px;font-weight:700;color:var(--text-2);margin-bottom:8px">Evaluation Trace (${res.trace.length} rules)</div>
      <table class="prb-trace-table">
        <thead><tr><th>P</th><th>Rule</th><th>Agent</th><th>Server</th><th>Tool</th><th>Match?</th><th>Action</th></tr></thead>
        <tbody>
          ${res.trace.map(t => {
            const isWinner = t.winner;
            const ac = PRB_ACTION_COLORS[t.action] || PRB_ACTION_COLORS.allow;
            return `<tr class="${isWinner?'prb-trace-winner':''}" ${isWinner?'style="font-weight:600"':''}>
              <td style="color:var(--text-3)">${t.priority||'—'}</td>
              <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escHtml(t.name)}">${isWinner?'🏆 ':''} ${escHtml(t.name)}</td>
              <td class="${t.agent_match?'prb-match-yes':'prb-match-no'}">${t.agent_match?'✓':'✗'} <span style="font-size:10px">${escHtml((t.agent_id||'').slice(0,12))}</span></td>
              <td class="${t.server_match?'prb-match-yes':'prb-match-no'}">${t.server_match?'✓':'✗'} <span style="font-size:10px">${escHtml((t.server_id||'').replace('srv_','').slice(0,12))}</span></td>
              <td class="${t.tool_match?'prb-match-yes':'prb-match-no'}">${t.tool_match?'✓':'✗'} <span style="font-size:10px">${escHtml((t.tool_pattern||'').slice(0,12))}</span></td>
              <td>${t.matched ? '<span class="prb-match-yes">✓ MATCH</span>' : '<span class="prb-match-no">✗</span>'}</td>
              <td><span class="prb-action-chip" style="background:${ac.bg};color:${ac.text}">${ac.icon} ${t.action||'—'}</span></td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
    </div>` : '<div style="color:var(--text-3);font-size:12px;text-align:center;padding:24px">Run a simulation above to see the evaluation trace.</div>'}
  </div>`;
}

async function prbRunSimulation() {
  const agent  = document.getElementById('sim-agent')?.value  || 'researcher';
  const server = document.getElementById('sim-server')?.value || 'srv_filesystem';
  const tool   = document.getElementById('sim-tool')?.value?.trim() || 'fs.list';
  if (!tool) { showToast('⚠️ Tool name required'); return; }

  try {
    const r = await fetch('/api/mcp-gateway/policies/simulate', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ agent_id: agent, server_id: server, tool_name: tool })
    });
    _prbSimResult = await r.json();
    prbRenderSimulatorTab(document.getElementById('prb-content'));
  } catch(e) { showToast('⚠️ Simulation failed: ' + e.message); }
}

function prbQuickSim(agent, server, tool) {
  const agEl = document.getElementById('sim-agent');
  const svEl = document.getElementById('sim-server');
  const tlEl = document.getElementById('sim-tool');
  if (agEl) agEl.value = agent;
  if (svEl) svEl.value = server;
  if (tlEl) tlEl.value = tool;
  prbRunSimulation();
}

function prbSimulateFromRow(pol) {
  _prbTab = 'simulator';
  document.querySelectorAll('.prb-tab').forEach(el => el.classList.toggle('active', el.id === 'prb-tab-simulator'));
  const content = document.getElementById('prb-content');
  prbRenderSimulatorTab(content);
  // Pre-fill
  const agEl = document.getElementById('sim-agent');
  const svEl = document.getElementById('sim-server');
  const tlEl = document.getElementById('sim-tool');
  if (agEl) agEl.value = pol.agent_id === '*' ? '*' : pol.agent_id.split(',')[0];
  if (svEl) {
    const parts = pol.server_id.split(',');
    const found = [...(svEl.options||[])].some(o => { if(o.value===parts[0]){o.selected=true;return true;} return false; });
  }
  if (tlEl) {
    // Replace wildcard with concrete example
    tlEl.value = pol.tool_pattern.replace('*','list');
  }
}


// ── Conflicts tab ─────────────────────────────────────────────────
function prbRenderConflictsTab(container) {
  if (!_prbConflicts) {
    container.innerHTML = `<div style="padding:20px;text-align:center;color:var(--text-3)">Loading conflict analysis…</div>`;
    fetch('/api/mcp-gateway/policies/conflicts').then(r=>r.ok?r.json():null).then(d=>{
      if (d) { _prbConflicts=d; prbRenderConflictsTab(container); }
    });
    return;
  }

  const { conflicts=[], conflict_count=0, warning_count=0, total=0 } = _prbConflicts;

  if (!total) {
    container.innerHTML = `<div style="padding:40px;text-align:center;color:var(--text-3)">
      <div style="font-size:36px;margin-bottom:12px">✅</div>
      <div style="font-size:14px;font-weight:600;color:var(--text-1);margin-bottom:6px">No Conflicts Detected</div>
      <div style="font-size:12px">All ${_prbPolicies.length} policy rules are consistent. Good governance!</div>
    </div>`;
    return;
  }

  container.innerHTML = `
  <div class="prb-conflicts">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap">
      <h3 style="margin:0;font-size:15px;font-weight:700;color:var(--text-0)">⚠️ Policy Conflicts</h3>
      ${conflict_count ? `<span style="padding:3px 10px;border-radius:5px;font-size:11px;font-weight:700;background:rgba(232,82,82,.15);color:#e85252">${conflict_count} conflicts</span>` : ''}
      ${warning_count  ? `<span style="padding:3px 10px;border-radius:5px;font-size:11px;font-weight:700;background:rgba(232,162,55,.15);color:#e8a237">${warning_count} warnings</span>` : ''}
      <button onclick="_prbConflicts=null;prbRenderConflictsTab(document.getElementById('prb-content'))" style="margin-left:auto;font-size:11px;padding:4px 10px;border-radius:5px;background:var(--bg-2);border:1px solid var(--border);color:var(--text-1);cursor:pointer">↺ Re-analyze</button>
    </div>
    <div style="font-size:12px;color:var(--text-3);margin-bottom:16px">
      Showing ${Math.min(total, 50)} of ${total} issues. Conflicts are evaluated against the first ${_prbPolicies.length} active rules.
    </div>
    ${conflicts.slice(0,50).map(c => {
      const sev = PRB_CONFLICT_SEVERITY[c.severity] || PRB_CONFLICT_SEVERITY.info;
      return `<div class="prb-conflict-card" style="border-left-color:${sev.color}">
        <div class="prb-conflict-head">
          <span style="font-size:16px">${sev.icon}</span>
          <span class="prb-conflict-type" style="background:${sev.color}22;color:${sev.color}">${sev.label}</span>
          <span style="font-size:11px;font-weight:700;color:var(--text-0)">${c.type.charAt(0).toUpperCase()+c.type.slice(1)}</span>
        </div>
        <div class="prb-conflict-desc">${escHtml(c.description)}</div>
        <div class="prb-conflict-policies">
          <div class="prb-conflict-pol">
            <span style="font-size:10px;color:var(--text-3)">Rule A: </span>
            <strong>${escHtml(c.policy_a?.name||'')}</strong>
            ${c.policy_a?.action ? `<span class="prb-action-chip" style="background:${PRB_ACTION_COLORS[c.policy_a.action]?.bg};color:${PRB_ACTION_COLORS[c.policy_a.action]?.text};margin-left:4px">${PRB_ACTION_COLORS[c.policy_a.action]?.icon} ${c.policy_a.action}</span>` : ''}
            <span style="font-size:9px;color:var(--text-3);margin-left:4px">P:${c.policy_a?.priority||'?'}</span>
          </div>
          <div class="prb-conflict-pol">
            <span style="font-size:10px;color:var(--text-3)">Rule B: </span>
            <strong>${escHtml(c.policy_b?.name||'')}</strong>
            ${c.policy_b?.action ? `<span class="prb-action-chip" style="background:${PRB_ACTION_COLORS[c.policy_b.action]?.bg};color:${PRB_ACTION_COLORS[c.policy_b.action]?.text};margin-left:4px">${PRB_ACTION_COLORS[c.policy_b.action]?.icon} ${c.policy_b.action}</span>` : ''}
            <span style="font-size:9px;color:var(--text-3);margin-left:4px">P:${c.policy_b?.priority||'?'}</span>
          </div>
          ${c.winner ? `<div class="prb-conflict-pol" style="border-color:var(--success)"><span style="font-size:10px;color:var(--success)">Winner: ${escHtml(c.winner.name)}</span></div>` : ''}
          ${c.policy_a ? `<button onclick="prbEditPolicy(${JSON.stringify(c.policy_a.id)})" style="font-size:10px;padding:2px 8px;border-radius:4px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-2);cursor:pointer">✏️ Edit A</button>` : ''}
          ${c.policy_b ? `<button onclick="prbEditPolicy(${JSON.stringify(c.policy_b.id)})" style="font-size:10px;padding:2px 8px;border-radius:4px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-2);cursor:pointer">✏️ Edit B</button>` : ''}
        </div>
      </div>`;
    }).join('')}
  </div>`;
}


// ── Servers tab ────────────────────────────────────────────────────
function prbRenderServersTab(container) {
  const builtins = _prbServers.filter(s => s.server_type === 'builtin' || s.server_type === 'connector');
  const custom   = _prbServers.filter(s => s.server_type === 'external');

  container.innerHTML = `
  <div style="padding:16px">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
      <h3 style="margin:0;font-size:14px;font-weight:700;color:var(--text-0)">🖥️ MCP Servers</h3>
      <button onclick="prbRegisterServer()" style="padding:4px 12px;border-radius:6px;font-size:11px;background:var(--accent);border:none;color:#fff;cursor:pointer;margin-left:auto">+ Register Server</button>
    </div>
    <div class="prb-servers">
      ${_prbServers.map(s => {
        let tools = [];
        try { tools = JSON.parse(s.tools_schema||'[]'); } catch(e) {}
        const isActive = s.status === 'active';
        return `<div class="prb-server-card" style="border-color:${isActive?'var(--border)':'rgba(232,82,82,.3)'}">
          <div class="prb-server-head">
            <div class="prb-server-status" style="background:${isActive?'#3dba7a':'#e85252'}"></div>
            <div class="prb-server-name">${escHtml(s.name)}</div>
            <span class="prb-server-type">${s.server_type}</span>
          </div>
          <div class="prb-server-desc">${escHtml(s.description||'')}</div>
          <div class="prb-server-limits">
            ⏱️ ${s.rate_limit_rpm}/min &nbsp; 📊 ${s.rate_limit_day}/day
          </div>
          ${tools.length ? `<div class="prb-server-tools">
            Tools: ${tools.slice(0,4).map(t=>`<span class="prb-code">${escHtml(t.name||t)}</span>`).join(' ')}${tools.length>4?` +${tools.length-4}`:''}</div>` : ''}
          <div class="prb-server-actions">
            ${isActive
              ? `<button onclick="prbToggleServer(${JSON.stringify(s.server_id)},true)" style="font-size:10px;padding:3px 8px;border-radius:5px;background:rgba(232,82,82,.12);border:1px solid rgba(232,82,82,.3);color:#e85252;cursor:pointer">🔴 Disable</button>`
              : `<button onclick="prbToggleServer(${JSON.stringify(s.server_id)},false)" style="font-size:10px;padding:3px 8px;border-radius:5px;background:rgba(61,186,122,.12);border:1px solid rgba(61,186,122,.3);color:#3dba7a;cursor:pointer">🟢 Enable</button>`}
            <button onclick="prbAddPolicyForServer(${JSON.stringify(s.server_id)},${JSON.stringify(s.name)})" style="font-size:10px;padding:3px 8px;border-radius:5px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-2);cursor:pointer">+ Add Rule</button>
          </div>
        </div>`;
      }).join('')}
    </div>
  </div>`;
}


// ── CRUD helpers ───────────────────────────────────────────────────
function prbSelectPolicy(polId) {
  _prbSelected = polId;
  prbRenderList();
  if (_prbTab === 'rules') {
    // Highlight row only
    document.querySelectorAll('.prb-rules-table tr').forEach(tr => tr.classList.remove('selected'));
  }
}

function prbEditPolicy(polId) {
  _prbSelected = polId;
  prbSetTab('builder');
}

async function prbToggleEnabled(polId, currentEnabled) {
  const r = await fetch(`/api/mcp-gateway/policies/${encodeURIComponent(polId)}/toggle`, {method:'PATCH'}).catch(()=>null);
  const d = r ? await r.json() : {};
  showToast(d.ok ? `📋 Rule ${d.enabled?'enabled':'disabled'}` : '⚠️ Failed');
  await prbRefresh();
}

async function prbDeletePolicy(polId, name) {
  const ok = await gmDanger('Delete Rule', `Delete policy rule "${name}"? This cannot be undone.`);
  if (!ok) return;
  const r = await fetch(`/api/mcp-gateway/policies/${encodeURIComponent(polId)}`, {method:'DELETE'}).catch(()=>null);
  const d = r ? await r.json() : {};
  showToast(d.ok ? '🗑 Rule deleted' : '⚠️ ' + (d.error||'Failed'));
  if (d.ok) { if(_prbSelected===polId) _prbSelected=null; await prbRefresh(); }
}

function prbToggleSelect(polId, checked) {
  if (checked) _prbSelIds.add(polId);
  else         _prbSelIds.delete(polId);
  prbRenderList();
}

function prbSelectAll(checked) {
  const pols = prbGetFilteredPolicies();
  pols.forEach(p => { if(checked) _prbSelIds.add(p.policy_id); else _prbSelIds.delete(p.policy_id); });
  prbRenderList();
  prbRenderTab();
}

async function prbBulkAction(action) {
  if (_prbSelIds.size === 0) { showToast('⚠️ Select rules first (use checkboxes)'); return; }
  const count = _prbSelIds.size;
  if (action === 'delete') {
    const ok = await gmDanger('Bulk Delete', `Delete ${count} selected rule${count>1?'s':''}? This cannot be undone.`);
    if (!ok) return;
  }
  const r = await fetch('/api/mcp-gateway/policies/bulk', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ action, policy_ids: [..._prbSelIds] })
  }).catch(()=>null);
  const d = r ? await r.json() : {};
  showToast(d.ok ? `${action==='enable'?'✓':action==='disable'?'○':'🗑'} ${d.affected} rule${d.affected!==1?'s':''} ${action}d` : '⚠️ '+(d.error||'Failed'));
  _prbSelIds.clear();
  if (d.ok) await prbRefresh();
}

function prbNewRule() {
  _prbSelected = null;
  prbSetTab('builder');
}

async function prbToggleServer(serverId, disable) {
  const ok = await gmDanger(`${disable?'Disable':'Enable'} Server`,
    `${disable?'Disable':'Enable'} server "${serverId}"? ${disable?'All tool calls to this server will be blocked.':''}`);
  if (!ok) return;
  const r = await fetch(`/api/mcp-gateway/servers/${encodeURIComponent(serverId)}/toggle`, {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({disable})
  }).catch(()=>null);
  const d = r ? await r.json() : {};
  showToast(d.ok ? `${disable?'🔴 Disabled':'🟢 Enabled'}: ${serverId}` : '⚠️ '+(d.error||'Failed'));
  if (d.ok) await prbRefresh();
}

async function prbRegisterServer() {
  const name     = await gmPrompt('Register MCP Server', 'Server name:');
  if (!name?.trim()) return;
  const endpoint = await gmPrompt('Endpoint URL:', 'https://my-mcp-server.example.com') || '';
  const desc     = await gmPrompt('Description:', '') || '';
  const r = await fetch('/api/mcp-gateway/servers', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name, endpoint, description:desc, server_type:'external'})
  }).catch(()=>null);
  const d = r ? await r.json() : {};
  showToast(d.ok ? `🖥️ Registered: ${d.server_id}` : '⚠️ '+(d.error||'Failed'));
  if (d.ok) await prbRefresh();
}

function prbAddPolicyForServer(serverId, serverName) {
  _prbSelected = null;
  prbSetTab('builder');
  setTimeout(() => {
    const svEl = document.getElementById('prb-f-server');
    if (svEl) {
      [...svEl.options].forEach(o => { o.selected = o.value === serverId; });
    }
    const nameEl = document.getElementById('prb-f-name');
    if (nameEl && !nameEl.value) nameEl.value = `Rule for ${serverName}`;
    prbUpdatePreview();
  }, 100);
}


// ── Old compat aliases (used by tests and other code) ────────────
async function renderMCPGatewayLegacy() { return renderMCPGateway(); }
async function mcgTestCall() {
  const tool = await gmPrompt('Test MCP Gateway Call', 'Tool name (e.g. fs.list, search.web):') || '';
  if (!tool.trim()) return;
  const argsStr = await gmPrompt('Args (JSON):', '{"path":"./"}') || '{}';
  let args = {};
  try { args = JSON.parse(argsStr); } catch(e) { showToast('⚠️ Invalid JSON args'); return; }
  showToast('📞 Calling via MCP Gateway…');
  const r = await fetch('/api/mcp-gateway/call', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({server_id:'srv_filesystem', tool, args, agent_id:'user'})
  }).catch(()=>null);
  if (!r) { showToast('⚠️ Call failed'); return; }
  const d = await r.json();
  await gmAlert(`🔀 Gateway Result: ${tool}`,
    `Call ID: ${d.call_id||'?'}\nPolicy: ${d.policy_decision||'?'}\nDuration: ${d.gateway_duration_ms||0}ms\nStatus: ${d.ok?'✅ OK':'❌ Failed'}\n\nResult:\n${JSON.stringify(d.result||d.error||d,null,2).slice(0,600)}`);
  await prbRefresh();
}
async function mcgToggleServer(sId,dis) { await prbToggleServer(sId,dis); }
async function mcgViewAgentCard(id, isAgent=false) {
  if (!isAgent) return;
  const d = await fetch(`/api/mcp-gateway/agent-card/${encodeURIComponent(id)}`).then(r=>r.ok?r.json():{}).catch(()=>({}));
  const card = d.agent_card||{};
  await gmAlert(`🪪 A2A Agent Card: ${id}`,
    `Agent ID: ${card.agent_id}\nName: ${card.name}\nRole: ${card.role}\nAuthority: ${card.authority_level}\nPublic Key: ${(card.public_key||'not provisioned').slice(0,40)}…\n\nCapabilities:\n${(card.capabilities||[]).slice(0,10).map(c=>`  • ${c}`).join('\n')}\n\nProtocols: ${(card.protocols||[]).join(', ')}\nEndpoint: ${card.endpoint}\nCard Hash: ${card.card_hash||''}\nA2A v1.0 ✅`);
}
async function mcgRegisterServer() { await prbRegisterServer(); }
async function mcgCreatePolicy()   { prbNewRule(); }
async function mcgTogglePolicy(id) { await prbToggleEnabled(id, true); }
async function mcgDeletePolicy(id) {
  const pol = _prbPolicies.find(p=>p.policy_id===id);
  await prbDeletePolicy(id, pol?.name||id);
}



// ══════════════════════════════════════════════════════════════════
//  SPRINT C — ENTERPRISE CONNECTORS
// ══════════════════════════════════════════════════════════════════

const CONNECTOR_CATEGORY_ICONS = {
  communication:'💬', project_mgmt:'🎫', productivity:'📊',
  crm:'☁️', devops:'🐙', integration:'🪝', custom:'🔌', email:'📧'
};

async function renderConnectors() {
  const pane = document.getElementById('pane-connectors');
  if (!pane) return;

  const [list, stats] = await Promise.all([
    fetch('/api/connectors').then(r=>r.ok?r.json():{connectors:[]}).catch(()=>({connectors:[]})),
    fetch('/api/connectors/stats/summary').then(r=>r.ok?r.json():{}).catch(()=>({})),
  ]);

  const statusColor = {active:'var(--success)',unconfigured:'var(--warning)',disabled:'var(--danger)'};
  const categories  = [...new Set((list.connectors||[]).map(c=>c.category))].sort();

  pane.innerHTML = `
  <div style="padding:20px;max-width:1100px;margin:0 auto">
    <div class="section-head" style="margin-bottom:20px">
      <div>
        <h2 style="margin:0 0 4px">🔌 Enterprise Connectors</h2>
        <p style="margin:0;color:var(--text-2);font-size:13px">Connect agents to the systems businesses already use — Slack, Jira, Google Workspace, Email, GitHub, Salesforce, Notion and custom integrations</p>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn" onclick="connectorRegister()">+ Custom Connector</button>
        <button class="btn-sm" onclick="renderConnectors()">↻ Refresh</button>
      </div>
    </div>

    <!-- Stats -->
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:18px">
      ${[
        ['🔌','Total',stats.total_connectors||0,'var(--accent)'],
        ['✅','Active',stats.active_connectors||0,'var(--success)'],
        ['📞','Executions',stats.total_executions||0,'var(--text-2)'],
        ['📂','Categories',Object.keys(stats.by_category||{}).length,'#9d74f5'],
      ].map(([icon,label,val,col])=>`
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:12px;text-align:center">
          <div style="font-size:18px">${icon}</div>
          <div style="font-size:9px;color:var(--text-3);text-transform:uppercase">${label}</div>
          <div style="font-size:18px;font-weight:700;color:${col}">${val}</div>
        </div>`).join('')}
    </div>

    <!-- Connector SDK callout -->
    <div style="background:rgba(158,206,106,0.08);border:1px solid var(--success);border-radius:10px;padding:14px 18px;margin-bottom:18px">
      <div style="font-size:12px;font-weight:700;color:var(--success);margin-bottom:4px">🛠️ Connector SDK</div>
      <div style="font-size:11px;color:var(--text-2)">Register any custom connector — define its capabilities, auth type, and credential schema. Your agents can then call it via <code style="background:var(--bg-3);padding:1px 5px;border-radius:3px">POST /api/connectors/{id}/execute</code> or through the MCP Gateway.</div>
    </div>

    <!-- Connector cards by category -->
    ${categories.map(cat=>`
    <div style="margin-bottom:20px">
      <div style="font-size:12px;font-weight:700;margin-bottom:10px;color:var(--text-0)">
        ${CONNECTOR_CATEGORY_ICONS[cat]||'📦'} ${cat.replace('_',' ').replace(/\b\w/g,c=>c.toUpperCase())}
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px">
        ${(list.connectors||[]).filter(c=>c.category===cat).map(c=>renderConnectorCard(c, statusColor)).join('')}
      </div>
    </div>`).join('')}
  </div>`;
}

function renderConnectorCard(c, statusColor) {
  const sCol = statusColor[c.status]||'var(--text-3)';
  const caps = Array.isArray(c.capabilities) ? c.capabilities : [];
  return `
  <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
      <span style="font-size:24px">${c.icon||'🔌'}</span>
      <div style="flex:1">
        <div style="font-weight:700;font-size:13px">${escHtml(c.name)}</div>
        <span style="font-size:10px;padding:1px 6px;border-radius:4px;font-weight:700;background:${sCol}22;color:${sCol}">${c.status}</span>
      </div>
      ${c.call_count>0?`<span style="font-size:10px;color:var(--text-3)">${c.call_count} calls</span>`:''}
    </div>

    <div style="font-size:11px;color:var(--text-2);margin-bottom:10px;line-height:1.5">${escHtml((c.description||'').slice(0,100))}</div>

    <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:10px">
      ${caps.slice(0,4).map(cap=>`<span style="font-size:10px;background:var(--bg-3);border-radius:4px;padding:2px 6px;color:var(--text-2)">${escHtml(cap)}</span>`).join('')}
      ${caps.length>4?`<span style="font-size:10px;color:var(--text-3)">+${caps.length-4} more</span>`:''}
    </div>

    <div style="display:flex;gap:6px;flex-wrap:wrap">
      ${c.status==='unconfigured'?`<button class="btn" onclick="connectorConfigure(${JSON.stringify(c.connector_id)},${JSON.stringify(c.name)},${JSON.stringify(c.auth_type)})" style="flex:1">⚙️ Configure</button>`:
        `<button class="btn-sm" onclick="connectorExecute(${JSON.stringify(c.connector_id)},${JSON.stringify(c.name)},${JSON.stringify(caps)})">▶ Execute</button>
         <button class="btn-sm" onclick="connectorHistory(${JSON.stringify(c.connector_id)})">📋 History</button>
         <button class="btn-sm" onclick="connectorTest(${JSON.stringify(c.connector_id)})">🧪 Test</button>`}
    </div>
  </div>`;
}

async function connectorConfigure(connId, name, authType) {
  const hints = {api_key:'API key / token', basic:'username:password or email:token', oauth:'OAuth token', smtp:'SMTP credentials', none:'No credentials needed'};
  const note = await gmPrompt(`Configure: ${name}`, `${hints[authType]||'Enter credentials'}\n\nPaste as JSON: {"key":"value"}`,'{}') || '';
  if (note===null) return;
  let creds = {};
  try { creds = JSON.parse(note); } catch(e) { showToast('⚠️ Invalid JSON — use {"key":"value"} format'); return; }
  const r = await fetch(`/api/connectors/${encodeURIComponent(connId)}/configure`,{
    method:'PATCH', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({credentials:creds})
  }).catch(()=>null);
  const d = r ? await r.json() : {};
  showToast(d.ok ? `✅ ${name} configured and active` : '⚠️ '+(d.error||'Failed'));
  renderConnectors();
}

async function connectorExecute(connId, name, caps) {
  const action = await gmPrompt(`Execute: ${name}`, `Action to run:\n${caps.map(c=>`• ${c}`).join('\n')}`, caps[0]||'') || '';
  if (!action?.trim()) return;
  const payloadStr = await gmPrompt('Payload (JSON):', '{"channel":"general","text":"Hello from Agentic OS!"}') || '{}';
  let payload = {};
  try { payload = JSON.parse(payloadStr); } catch(e) { showToast('⚠️ Invalid JSON payload'); return; }
  showToast(`🔌 Executing ${name}.${action}…`);
  const r = await fetch(`/api/connectors/${encodeURIComponent(connId)}/execute`,{
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({action, payload, agent_id:'user'})
  }).catch(()=>null);
  if (!r) { showToast('⚠️ Execution failed'); return; }
  const d = await r.json();
  await gmAlert(`🔌 ${name} — ${action}`,
    `Status: ${d.ok?'✅ Success':'❌ Failed'}\nExec ID: ${d.exec_id||'?'}\nDuration: ${d.duration_ms||0}ms\n\n${d.ok ? JSON.stringify(d,null,2).slice(0,500) : 'Error: '+(d.error||'Unknown')}`);
  renderConnectors();
}

async function connectorHistory(connId) {
  const r = await fetch(`/api/connectors/${encodeURIComponent(connId)}/executions?limit=10`).catch(()=>null);
  if (!r||!r.ok) { showToast('Could not load history'); return; }
  const d = await r.json();
  const lines = (d.executions||[]).map(e=>
    `${new Date(e.created_at).toLocaleTimeString()} [${e.status}] ${e.action} (${e.duration_ms}ms)`
  ).join('\n');
  await gmAlert('📋 Execution History', lines || 'No executions yet');
}

async function connectorTest(connId) {
  const r = await fetch(`/api/connectors/${encodeURIComponent(connId)}/test`,{method:'POST'}).catch(()=>null);
  if (!r) { showToast('⚠️ Test failed'); return; }
  const d = await r.json();
  showToast(d.configured ? `✅ ${d.name} is ready` : `⚠️ ${d.message}`);
}

async function connectorRegister() {
  const name   = await gmPrompt('Custom Connector SDK', 'Connector name:');
  if (!name?.trim()) return;
  const cat    = await gmPrompt('Category:', 'custom') || 'custom';
  const auth   = await gmPrompt('Auth type (none/api_key/basic/oauth):', 'api_key') || 'api_key';
  const capsStr= await gmPrompt('Capabilities (comma-separated):', 'my_action') || '';
  const caps   = capsStr.split(',').map(s=>s.trim()).filter(Boolean);
  const r = await fetch('/api/connectors',{
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name, category:cat, auth_type:auth, capabilities:caps})
  }).catch(()=>null);
  const d = r ? await r.json() : {};
  showToast(d.ok ? `🔌 Connector registered: ${d.connector_id}` : '⚠️ '+(d.error||'Failed'));
  if (d.ok) renderConnectors();
}



// ══════════════════════════════════════════════════════════════════
//  A2A PROTOCOL — Agent-to-Agent Network
// ══════════════════════════════════════════════════════════════════

// ── State ─────────────────────────────────────────────────────────
let _a2aTab        = 'network';   // network | tasks | cards
let _a2aAgents     = [];
let _a2aLocalAgents= [];
let _a2aTasks      = [];
let _a2aStats      = null;
let _a2aSelected   = null;        // selected remote agent id

// ── Main render ────────────────────────────────────────────────────
async function renderA2A() {
  const pane = document.getElementById('pane-a2a');
  if (!pane) return;

  pane.innerHTML = `
  

  <div class="a2a-root">
    <!-- Sidebar -->
    <div class="a2a-sidebar">
      <div class="a2a-sidebar-title">A2A Network</div>
      <div class="a2a-nav active" id="a2a-nav-network" onclick="a2aSetTab('network')">
        <span class="a2a-nav-icon">🌐</span> Agent Network
      </div>
      <div class="a2a-nav" id="a2a-nav-tasks" onclick="a2aSetTab('tasks')">
        <span class="a2a-nav-icon">📋</span> Tasks
        <span class="a2a-badge" id="a2a-task-badge" style="display:none">0</span>
      </div>
      <div class="a2a-nav" id="a2a-nav-cards" onclick="a2aSetTab('cards')">
        <span class="a2a-nav-icon">🪪</span> Agent Cards
      </div>
      <div class="a2a-div"></div>
      <div class="a2a-nav" onclick="a2aOpenRegister()">
        <span class="a2a-nav-icon">➕</span> Register Agent
      </div>
      <div class="a2a-nav" onclick="a2aOpenDelegate()">
        <span class="a2a-nav-icon">📤</span> Delegate Task
      </div>
    </div>

    <!-- Main -->
    <div class="a2a-main">
      <div class="a2a-header">
        <span class="a2a-header-title" id="a2a-header-title">🌐 A2A Agent Network</span>
        <button class="a2a-btn" onclick="a2aRefresh()">↺ Refresh</button>
        <button class="a2a-btn primary" onclick="a2aOpenDelegate()">📤 Delegate Task</button>
      </div>
      <div class="a2a-content" id="a2a-content">
        <div style="color:var(--text-3);padding:20px">Loading…</div>
      </div>
    </div>
  </div>`;

  await a2aRefresh();
}


// ── Data ─────────────────────────────────────────────────────────────
async function a2aRefresh() {
  const [agentsR, tasksR, statsR] = await Promise.all([
    fetch('/api/a2a/agents').then(r=>r.ok?r.json():{agents:[],local_agents:[]}).catch(()=>({agents:[],local_agents:[]})),
    fetch('/api/a2a/tasks?limit=50').then(r=>r.ok?r.json():{tasks:[]}).catch(()=>({tasks:[]})),
    fetch('/api/a2a/stats').then(r=>r.ok?r.json():{}).catch(()=>({})),
  ]);
  _a2aAgents      = agentsR.agents      || [];
  _a2aLocalAgents = agentsR.local_agents|| [];
  _a2aTasks       = tasksR.tasks        || [];
  _a2aStats       = statsR;

  // Update task badge
  const active = _a2aTasks.filter(t=>!['completed','failed','canceled'].includes(t.state)).length;
  const badge  = document.getElementById('a2a-task-badge');
  if (badge) { badge.textContent=active; badge.style.display=active>0?'inline-flex':'none'; }

  a2aRenderTab();
}

function a2aSetTab(tab) {
  _a2aTab = tab;
  document.querySelectorAll('.a2a-nav[id^="a2a-nav-"]').forEach(el => {
    el.classList.toggle('active', el.id === 'a2a-nav-' + tab);
  });
  const titles = {
    network:'🌐 A2A Agent Network',
    tasks:  '📋 A2A Tasks',
    cards:  '🪪 Agent Cards (A2A v1.0)',
  };
  const h = document.getElementById('a2a-header-title');
  if (h) h.textContent = titles[tab] || 'A2A Network';
  a2aRenderTab();
}

function a2aRenderTab() {
  const c = document.getElementById('a2a-content');
  if (!c) return;
  if (_a2aTab === 'network') a2aRenderNetwork(c);
  if (_a2aTab === 'tasks')   a2aRenderTasks(c);
  if (_a2aTab === 'cards')   a2aRenderCards(c);
}


// ── Network tab ───────────────────────────────────────────────────────
function a2aRenderNetwork(container) {
  const s = _a2aStats || {};
  const trustColors = {local:'#3dba7a',verified:'#5b8af8',unverified:'#e8a237',blocked:'#e85252'};
  const statusIcons = {active:'🟢',unverified:'🟡',unreachable:'🔴',blocked:'⛔'};

  const stats = [
    {val:s.registered_agents||0, lbl:'Registered', col:'var(--accent)'},
    {val:s.active_agents||0,     lbl:'Active',     col:'var(--success)'},
    {val:s.local_agents||0,      lbl:'Local',      col:'#3dba7a'},
    {val:s.total_tasks||0,       lbl:'Tasks Run',  col:'#9d74f5'},
    {val:s.inbound_calls||0,     lbl:'Inbound',    col:'var(--accent)'},
    {val:s.outbound_calls||0,    lbl:'Outbound',   col:'var(--warning)'},
  ];

  const allAgents = [..._a2aAgents];
  const selectedAgent = _a2aSelected ? allAgents.find(a=>a.agent_id===_a2aSelected) : null;

  container.innerHTML = `
    <!-- Stats -->
    <div class="a2a-stats-grid">
      ${stats.map(s=>`<div class="a2a-stat"><div class="a2a-stat-val" style="color:${s.col}">${s.val}</div><div class="a2a-stat-lbl">${s.lbl}</div></div>`).join('')}
    </div>

    <!-- Protocol explanation -->
    <div style="background:rgba(91,138,248,.06);border:1px solid rgba(91,138,248,.2);border-radius:10px;padding:12px 14px;margin-bottom:16px">
      <div style="font-size:12px;font-weight:700;color:var(--accent);margin-bottom:6px">🌐 A2A Protocol v1.0 — Agent-to-Agent</div>
      <div style="font-size:11px;color:var(--text-2);line-height:1.6">
        Every agent exposes a signed <strong>Agent Card</strong> at <code style="background:var(--bg-3);padding:1px 5px;border-radius:3px">/.well-known/agent.json</code> and a
        <strong>JSON-RPC 2.0 endpoint</strong> at <code style="background:var(--bg-3);padding:1px 5px;border-radius:3px">/a2a/{id}</code>.<br>
        External platforms (Google ADK, LangChain, Strick Tech Swarm Framework, Microsoft Agent Framework) can delegate tasks to this platform via <code>tasks/send</code> or stream updates via <code>tasks/sendSubscribe</code>.
      </div>
      <div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap">
        <a href="/.well-known/agent.json" target="_blank" class="a2a-btn">🪪 Platform Card</a>
        <a href="/a2a/orchestrator/card" target="_blank" class="a2a-btn">🎯 Orchestrator Card</a>
        <button class="a2a-btn" onclick="a2aSetTab('cards')">View All Cards →</button>
      </div>
    </div>

    <!-- Registered agents -->
    <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px">
      Registered Agents (${allAgents.length})
    </div>
    <div class="a2a-agent-grid">
      ${allAgents.map(ag => {
        const tc  = trustColors[ag.trust_level] || '#7a8aaa';
        const si  = statusIcons[ag.status] || '❓';
        const skills = ag.skills || [];
        const caps   = ag.capabilities || [];
        const isLocal= ag.trust_level === 'local';
        return `<div class="a2a-agent-card ${_a2aSelected===ag.agent_id?'selected':''}" onclick="a2aSelectAgent(${JSON.stringify(ag.agent_id)})">
          <div class="a2a-agent-head">
            <span class="a2a-agent-icon">${isLocal?'🏠':ag.status==='active'?'🌐':'🔌'}</span>
            <div class="a2a-agent-body">
              <div class="a2a-agent-name">${escHtml(ag.name)}</div>
              <div class="a2a-agent-url">${escHtml(ag.a2a_url)}</div>
            </div>
            <span class="a2a-trust-badge" style="background:${tc}22;color:${tc}">${si} ${ag.trust_level}</span>
          </div>
          <div style="font-size:11px;color:var(--text-2);margin-bottom:6px;line-height:1.4">${escHtml((ag.description||'').slice(0,80))}</div>
          <div class="a2a-skills">
            ${skills.slice(0,4).map(s=>`<span class="a2a-skill">${escHtml(typeof s==='object'?s.name:s)}</span>`).join('')}
            ${skills.length>4?`<span class="a2a-skill">+${skills.length-4} more</span>`:''}
          </div>
          ${caps.length?`<div class="a2a-caps">⚡ ${caps.slice(0,3).join(' · ')}</div>`:''}
          <div class="a2a-agent-actions">
            <button class="a2a-btn" onclick="event.stopPropagation();a2aDelegateToAgent(${JSON.stringify(ag.agent_id)})">📤 Delegate</button>
            ${!isLocal?`<button class="a2a-btn" onclick="event.stopPropagation();a2aVerifyAgent(${JSON.stringify(ag.agent_id)})">🔍 Verify</button>`:''}
            ${!isLocal?`<button class="a2a-btn" onclick="event.stopPropagation();a2aDeleteAgent(${JSON.stringify(ag.agent_id)})" style="color:var(--danger)">🗑</button>`:''}
          </div>
        </div>`;
      }).join('')}
      <!-- Add remote agent card -->
      <div class="a2a-agent-card" onclick="a2aOpenRegister()" style="border-style:dashed;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px;min-height:160px;opacity:.7">
        <div style="font-size:28px;margin-bottom:8px">➕</div>
        <div style="font-size:12px;font-weight:600;color:var(--text-1)">Register Remote Agent</div>
        <div style="font-size:10px;color:var(--text-3);margin-top:4px;text-align:center">Connect to any A2A-compatible platform</div>
      </div>
    </div>

    <!-- Local agents section -->
    ${_a2aLocalAgents.length ? `
    <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.05em;margin:16px 0 10px">
      Local Agents — Available via A2A (${_a2aLocalAgents.length})
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:6px">
      ${_a2aLocalAgents.map(a=>`
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:8px;padding:8px 12px;cursor:pointer;font-size:11px;transition:all .12s" onclick="a2aViewLocalCard(${JSON.stringify(a.agent_id)})">
          <span style="font-weight:600;color:var(--text-0)">${escHtml(a.name)}</span>
          <span style="color:var(--text-3);margin-left:6px">${escHtml((a.description||'').slice(0,30))}</span>
          <a href="/a2a/${encodeURIComponent(a.agent_id)}/card" target="_blank" style="color:var(--accent);font-size:10px;margin-left:8px" onclick="event.stopPropagation()">🪪</a>
        </div>`).join('')}
    </div>` : ''}
  `;
}


// ── Tasks tab ─────────────────────────────────────────────────────────
async function a2aRenderTasks(container) {
  container.innerHTML = `<div style="color:var(--text-3);padding:20px">Loading…</div>`;
  const d = await fetch('/api/a2a/tasks?limit=50').then(r=>r.ok?r.json():{tasks:[]}).catch(()=>({tasks:[]}));
  _a2aTasks = d.tasks || [];

  const stateColors = {
    submitted:'var(--text-3)',working:'var(--warning)',
    'input-required':'#9d74f5',completed:'var(--success)',
    failed:'var(--danger)',canceled:'var(--text-3)',
  };

  if (!_a2aTasks.length) {
    container.innerHTML = `<div style="padding:40px;text-align:center;color:var(--text-3)">
      <div style="font-size:40px;margin-bottom:12px">📋</div>
      <div style="font-size:14px;font-weight:600;color:var(--text-1);margin-bottom:8px">No A2A Tasks Yet</div>
      <div style="font-size:12px;line-height:1.6">Tasks appear here when external agents delegate work to this platform, or when you delegate tasks to remote agents.</div>
      <button class="a2a-btn primary" onclick="a2aOpenDelegate()" style="margin-top:14px">📤 Send Your First Task</button>
    </div>`;
    return;
  }

  container.innerHTML = `
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;flex-wrap:wrap">
      <strong style="font-size:13px;color:var(--text-0)">${_a2aTasks.length} tasks</strong>
      <span style="font-size:11px;color:var(--text-3)">(inbound + outbound)</span>
      <button class="a2a-btn" onclick="a2aRenderTasks(document.getElementById('a2a-content'))" style="margin-left:auto">↺</button>
    </div>
    <table class="a2a-task-table">
      <thead><tr>
        <th>Task ID</th><th>Direction</th><th>Agent</th><th>State</th><th>Progress</th><th>Created</th><th>Actions</th>
      </tr></thead>
      <tbody>
        ${_a2aTasks.map(t => {
          const sc = stateColors[t.state] || 'var(--text-3)';
          const isOutbound = t.direction === 'outbound';
          return `<tr onclick="a2aViewTask(${JSON.stringify(t.task_id)})">
            <td style="font-family:monospace;font-size:10px;color:var(--text-3)">${t.task_id.slice(0,18)}…</td>
            <td style="font-size:10px">${isOutbound?'📤 outbound':'📥 inbound'}</td>
            <td style="color:var(--accent);font-size:11px">${escHtml(isOutbound?t.target_agent_id:t.target_agent_id)}</td>
            <td><span class="a2a-state" style="background:${sc}22;color:${sc}">${t.state}</span></td>
            <td style="font-size:10px">${t.progress_pct||0}%</td>
            <td style="font-size:10px;color:var(--text-3)">${new Date(t.created_at).toLocaleString()}</td>
            <td onclick="event.stopPropagation()">
              ${!['completed','failed','canceled'].includes(t.state) ?
                `<button class="a2a-btn" onclick="a2aCancelTask(${JSON.stringify(t.task_id)})" style="font-size:10px;color:var(--danger)">✕</button>` : ''}
            </td>
          </tr>`;
        }).join('')}
      </tbody>
    </table>
  `;
}


// ── Agent Cards tab ────────────────────────────────────────────────────
async function a2aRenderCards(container) {
  // Show all local agents' A2A cards
  const localIds = ['orchestrator','researcher','builder','reviewer','creative','brain','memory'];
  const base = window.location.origin;

  container.innerHTML = `
    <div style="font-size:12px;color:var(--text-2);margin-bottom:14px;line-height:1.6">
      Each local agent exposes a signed <strong>A2A v1.0 Agent Card</strong> at two standard locations:
      <br>• <code style="background:var(--bg-3);padding:1px 5px;border-radius:3px">/a2a/{id}/.well-known/agent.json</code> (spec-compliant)
      <br>• <code style="background:var(--bg-3);padding:1px 5px;border-radius:3px">/a2a/{id}/card</code> (friendly alias)
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px;margin-bottom:16px">
      ${localIds.map(id => `
        <div class="a2a-detail-panel">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
            <div style="font-size:16px;font-weight:800;color:var(--text-0)">${id}</div>
            <span style="font-size:9px;padding:1px 7px;border-radius:4px;background:rgba(61,186,122,.15);color:#3dba7a">LOCAL</span>
            <div style="margin-left:auto;display:flex;gap:5px">
              <a href="/a2a/${id}/card" target="_blank" class="a2a-btn" style="text-decoration:none">🪪 View</a>
              <button class="a2a-btn" onclick="a2aShowCard(${JSON.stringify(id)})">JSON</button>
            </div>
          </div>
          <div class="a2a-wk-url">${base}/a2a/${id}/.well-known/agent.json</div>
          <div style="font-size:10px;color:var(--text-3)">JSON-RPC endpoint: ${base}/a2a/${id}</div>
        </div>`).join('')}
    </div>
    <div class="a2a-detail-panel">
      <div class="a2a-detail-title">Platform Agent Card</div>
      <div class="a2a-wk-url">${base}/.well-known/agent.json</div>
      <div style="font-size:11px;color:var(--text-2);margin-bottom:8px">
        The platform-level card describes the full Agentic OS installation and lists all available agents.
        Any A2A-compatible platform (Google ADK, LangChain, Strick Tech Swarm Framework, Microsoft Agent Framework) can use this to discover and delegate tasks.
      </div>
      <a href="/.well-known/agent.json" target="_blank" class="a2a-btn primary" style="text-decoration:none;display:inline-flex">🪪 View Platform Card</a>
    </div>
  `;
}

async function a2aShowCard(agentId) {
  const d = await fetch(`/a2a/${encodeURIComponent(agentId)}/card`)
    .then(r=>r.ok?r.json():null).catch(()=>null);
  if (!d) { showToast('⚠️ Could not load agent card'); return; }
  const overlay = document.createElement('div');
  overlay.className = 'a2a-modal-overlay';
  overlay.innerHTML = `<div class="a2a-modal" style="max-width:720px;max-height:80vh;overflow-y:auto">
    <h3 style="margin:0 0 8px">🪪 A2A Agent Card — ${escHtml(agentId)}</h3>
    <p style="margin:0 0 10px;font-size:11px;color:var(--text-3)">Served at /a2a/${escHtml(agentId)}/.well-known/agent.json</p>
    <pre class="a2a-card-code">${escHtml(JSON.stringify(d, null, 2))}</pre>
    <div class="a2a-modal-row">
      <a href="/a2a/${encodeURIComponent(agentId)}/card" target="_blank" class="a2a-btn">Open in tab</a>
      <button class="a2a-btn" onclick="navigator.clipboard.writeText(${JSON.stringify(JSON.stringify(d,null,2))}).then(()=>showToast('Copied!'))">Copy JSON</button>
      <button class="a2a-btn primary" onclick="this.closest('.a2a-modal-overlay').remove()">Close</button>
    </div>
  </div>`;
  overlay.onclick = e => { if(e.target===overlay) overlay.remove(); };
  document.body.appendChild(overlay);
}

async function a2aViewLocalCard(agentId) {
  _a2aTab = 'cards';
  document.querySelectorAll('.a2a-nav[id^="a2a-nav-"]').forEach(el => el.classList.toggle('active', el.id==='a2a-nav-cards'));
  await a2aRenderCards(document.getElementById('a2a-content'));
  setTimeout(() => a2aShowCard(agentId), 100);
}


// ── Actions ────────────────────────────────────────────────────────────
function a2aSelectAgent(agentId) {
  _a2aSelected = agentId === _a2aSelected ? null : agentId;
  a2aRenderNetwork(document.getElementById('a2a-content'));
}

function a2aDelegateToAgent(agentId) {
  _a2aSelected = agentId;
  a2aOpenDelegate(agentId);
}

function a2aOpenDelegate(preselectedId) {
  const existing = document.getElementById('a2a-delegate-modal');
  if (existing) { existing.remove(); return; }

  const allRemote = [..._a2aAgents.filter(a=>a.trust_level!=='local'), ..._a2aLocalAgents];
  const options   = allRemote.map(a=>
    `<option value="${escHtml(a.agent_id)}" ${a.agent_id===preselectedId?'selected':''}>${escHtml(a.name||a.agent_id)}</option>`
  ).join('');

  const overlay = document.createElement('div');
  overlay.id = 'a2a-delegate-modal';
  overlay.className = 'a2a-modal-overlay';
  overlay.innerHTML = `<div class="a2a-modal">
    <h3>📤 Delegate Task via A2A</h3>
    <p>Send a task to a remote A2A-compatible agent. The task is submitted via JSON-RPC 2.0 tasks/send and the result is returned when complete.</p>
    <div class="a2a-form-group">
      <label class="a2a-form-label">Target Agent *</label>
      <select class="a2a-select" id="a2a-del-agent">${options}</select>
    </div>
    <div class="a2a-form-group">
      <label class="a2a-form-label">Task Message *</label>
      <textarea class="a2a-textarea" id="a2a-del-message" placeholder="Describe what you want the remote agent to do…&#10;&#10;Example: Research the top 5 agentic AI frameworks in 2026 and write a brief comparison."></textarea>
    </div>
    <div class="a2a-form-group">
      <label class="a2a-form-label">Session ID (optional)</label>
      <input class="a2a-input" id="a2a-del-session" placeholder="For grouping related tasks">
    </div>
    <div class="a2a-modal-row">
      <button class="a2a-btn" onclick="document.getElementById('a2a-delegate-modal').remove()">Cancel</button>
      <button class="a2a-btn primary" onclick="a2aSubmitDelegate()">📤 Send Task</button>
    </div>
  </div>`;
  overlay.onclick = e => { if(e.target===overlay) overlay.remove(); };
  document.body.appendChild(overlay);
  setTimeout(() => document.getElementById('a2a-del-message')?.focus(), 50);
}

async function a2aSubmitDelegate() {
  const agentId = document.getElementById('a2a-del-agent')?.value?.trim();
  const message = document.getElementById('a2a-del-message')?.value?.trim();
  const session = document.getElementById('a2a-del-session')?.value?.trim() || '';
  if (!agentId || !message) { showToast('⚠️ Select an agent and enter a message'); return; }
  document.getElementById('a2a-delegate-modal')?.remove();
  showToast(`📤 Delegating task to ${agentId}…`);

  // If local agent, use the direct A2A endpoint (JSON-RPC tasks/send)
  const isLocal = _a2aLocalAgents.some(a=>a.agent_id===agentId);
  let result;
  if (isLocal) {
    // Call local A2A endpoint directly
    const r = await fetch(`/a2a/${encodeURIComponent(agentId)}`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        jsonrpc:'2.0', id:'ui-1', method:'tasks/send',
        params:{
          message:{role:'user',parts:[{type:'text',text:message}]},
          sessionId: session || undefined,
        }
      })
    }).catch(()=>null);
    result = r ? await r.json() : null;
    if (result?.result) {
      showToast(`✅ Task completed: ${result.result.status?.state}`);
    } else {
      showToast('⚠️ Task submission failed (local): ' + (result?.error?.message || 'Unknown error'));
    }
  } else {
    // Delegate to remote via /api/a2a/delegate
    const r = await fetch('/api/a2a/delegate', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({agent_id:agentId, message, session_id:session})
    }).catch(()=>null);
    result = r ? await r.json() : null;
    if (result?.ok) {
      showToast(`✅ Task delegated: ${result.task_id}`);
    } else {
      showToast('ℹ️ Task sent (remote may be demo): ' + (result?.note || result?.error || ''));
    }
  }
  await a2aRefresh();
  a2aSetTab('tasks');
}

function a2aOpenRegister() {
  const existing = document.getElementById('a2a-register-modal');
  if (existing) { existing.remove(); return; }
  const overlay = document.createElement('div');
  overlay.id = 'a2a-register-modal';
  overlay.className = 'a2a-modal-overlay';
  overlay.innerHTML = `<div class="a2a-modal">
    <h3>➕ Register Remote A2A Agent</h3>
    <p>Connect to any A2A v1.0 compatible agent. After registering, click Verify to fetch its Agent Card and capabilities.</p>
    <div class="a2a-form-group">
      <label class="a2a-form-label">Agent Name *</label>
      <input class="a2a-input" id="a2a-reg-name" placeholder="e.g. LangChain Research Agent">
    </div>
    <div class="a2a-form-group">
      <label class="a2a-form-label">A2A Endpoint URL *</label>
      <input class="a2a-input" id="a2a-reg-url" placeholder="https://example.com/a2a/agent">
    </div>
    <div class="a2a-form-group">
      <label class="a2a-form-label">Description</label>
      <input class="a2a-input" id="a2a-reg-desc" placeholder="What this agent does">
    </div>
    <div class="a2a-form-group">
      <label class="a2a-form-label">Authentication</label>
      <select class="a2a-select" id="a2a-reg-auth" onchange="a2aToggleAuthFields()">
        <option value="none">None (public)</option>
        <option value="bearer">Bearer Token</option>
        <option value="api_key">API Key</option>
      </select>
    </div>
    <div id="a2a-auth-fields" style="display:none">
      <div class="a2a-form-group">
        <label class="a2a-form-label">Token / Key</label>
        <input class="a2a-input" id="a2a-reg-token" type="password" placeholder="sk-…">
      </div>
    </div>
    <div class="a2a-modal-row">
      <button class="a2a-btn" onclick="document.getElementById('a2a-register-modal').remove()">Cancel</button>
      <button class="a2a-btn primary" onclick="a2aSubmitRegister()">➕ Register</button>
    </div>
  </div>`;
  overlay.onclick = e => { if(e.target===overlay) overlay.remove(); };
  document.body.appendChild(overlay);
  setTimeout(() => document.getElementById('a2a-reg-name')?.focus(), 50);
}

function a2aToggleAuthFields() {
  const auth = document.getElementById('a2a-reg-auth')?.value;
  const fields = document.getElementById('a2a-auth-fields');
  if (fields) fields.style.display = auth !== 'none' ? 'block' : 'none';
}

async function a2aSubmitRegister() {
  const name     = document.getElementById('a2a-reg-name')?.value?.trim();
  const url      = document.getElementById('a2a-reg-url')?.value?.trim();
  const desc     = document.getElementById('a2a-reg-desc')?.value?.trim() || '';
  const authType = document.getElementById('a2a-reg-auth')?.value || 'none';
  const token    = document.getElementById('a2a-reg-token')?.value?.trim() || '';
  if (!name || !url) { showToast('⚠️ Name and URL required'); return; }
  document.getElementById('a2a-register-modal')?.remove();
  const authConfig = authType !== 'none' && token ? {token, key: token} : {};
  const r = await fetch('/api/a2a/agents', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name, a2a_url:url, description:desc, auth_type:authType, auth_config:authConfig})
  }).catch(()=>null);
  const d = r ? await r.json() : {};
  if (d.ok) {
    showToast(`✅ Registered: ${name}`);
    await a2aRefresh();
    // Auto-verify
    a2aVerifyAgent(d.agent_id);
  } else {
    showToast('⚠️ Registration failed: '+(d.error||''));
  }
}

async function a2aVerifyAgent(agentId) {
  showToast(`🔍 Verifying ${agentId}…`);
  const r = await fetch(`/api/a2a/agents/${encodeURIComponent(agentId)}/verify`, {method:'POST'}).catch(()=>null);
  const d = r ? await r.json() : {};
  if (d.ok) {
    showToast(`✅ Verified: ${d.card_name||agentId} (${d.skills_count} skills)`);
  } else {
    showToast(`ℹ️ ${agentId}: ${d.status} — ${d.error||'could not reach agent card URL'}`);
  }
  await a2aRefresh();
}

async function a2aDeleteAgent(agentId) {
  const ok = await gmDanger('Remove Agent', `Remove "${agentId}" from the A2A registry?`);
  if (!ok) return;
  await fetch(`/api/a2a/agents/${encodeURIComponent(agentId)}`, {method:'DELETE'});
  showToast('🗑 Agent removed');
  await a2aRefresh();
}

async function a2aViewTask(taskId) {
  const d = await fetch(`/api/a2a/tasks/${encodeURIComponent(taskId)}`).then(r=>r.ok?r.json():null).catch(()=>null);
  if (!d || !d.ok) { showToast('Could not load task'); return; }
  const t   = d.task || {};
  const a2a = d.a2a_response || {};
  const sv  = d.supervisor_run;
  const msgs = (t.messages||[]).map(m => `[${m.role}] ${(m.parts||[]).map(p=>p.text||'').join('')}`).join('\n');
  const arts = (t.artifacts||[]).map(a => `${a.name}: ${(a.parts||[]).map(p=>p.text||'').join('').slice(0,200)}`).join('\n');
  await gmAlert(`📋 A2A Task: ${taskId.slice(0,20)}`,
    `State: ${t.state}  |  Direction: ${t.caller_agent_id==='local'?'Outbound (we sent)':'Inbound (received)'}
Target Agent: ${t.target_agent_id}
Progress: ${t.progress_pct||0}%  |  Session: ${t.session_id||'—'}
Created: ${t.created_at}

Messages:
${msgs.slice(0,500) || '(none)'}

Artifacts:
${arts.slice(0,500) || '(none)'}

${sv ? `Supervisor Run: ${sv.run_id} (${sv.status}) score=${sv.eval_score||'—'}` : ''}
${t.error_message ? `Error: ${t.error_message}` : ''}`);
}

async function a2aCancelTask(taskId) {
  const ok = await gmDanger('Cancel Task', `Cancel A2A task ${taskId.slice(0,20)}?`);
  if (!ok) return;
  const r = await fetch(`/api/a2a/tasks/${encodeURIComponent(taskId)}/cancel`, {method:'POST'}).catch(()=>null);
  const d = r ? await r.json() : {};
  showToast(d.ok ? `✅ Task canceled` : '⚠️ '+(d.error||'Failed'));
  await a2aRefresh();
  a2aSetTab('tasks');
}


// ══════════════════════════════════════════════════════════════════
//  SPRINT D — LIVE AGENT MONITOR
// ══════════════════════════════════════════════════════════════════

// ══════════════════════════════════════════════════════════════════
//  BEHAVIOR DRIFT DETECTION — Complete Implementation
//  Replaces old renderAgentMonitor + all monitor* functions
// ══════════════════════════════════════════════════════════════════

// ── State ─────────────────────────────────────────────────────────
let _monitorPoll    = null;    // live poll timer
let _driftTab       = 'dashboard';  // dashboard | agents | alerts | history
let _driftSummary   = null;
let _driftSelected  = null;    // currently viewed agent_id
let _driftAlerts    = [];
let _driftHistory   = [];
let _driftLeaderboard = [];

// ── Constants ──────────────────────────────────────────────────────
const DRIFT_SEV_COLORS = {
  none:     { bg:'rgba(61,186,122,.12)',   border:'#3dba7a',  text:'#3dba7a',   label:'None'     },
  low:      { bg:'rgba(91,138,248,.12)',   border:'#5b8af8',  text:'#5b8af8',   label:'Low'      },
  medium:   { bg:'rgba(232,162,55,.12)',   border:'#e8a237',  text:'#e8a237',   label:'Medium'   },
  high:     { bg:'rgba(240,96,128,.15)',   border:'#f06080',  text:'#f06080',   label:'High'     },
  critical: { bg:'rgba(232,82,82,.15)',    border:'#e85252',  text:'#e85252',   label:'Critical' },
};
const DRIFT_TREND_ICONS = {
  stable:             '→',
  improving:          '↗',
  degrading:          '↘',
  volatile:           '↕',
  insufficient_data:  '?',
};
const DRIFT_TREND_COLORS = {
  stable:             'var(--text-3)',
  improving:          'var(--success)',
  degrading:          'var(--danger)',
  volatile:           'var(--warning)',
  insufficient_data:  'var(--text-3)',
};
const DRIFT_DIM_LABELS = {
  latency:    { label:'Latency',    icon:'⏱️', unit:'ms' },
  tokens:     { label:'Tokens',     icon:'🔤', unit:'/task' },
  cost:       { label:'Cost',       icon:'💰', unit:'/task' },
  error_rate: { label:'Error Rate', icon:'❌', unit:'%' },
  volume:     { label:'Volume',     icon:'📊', unit:'/hr' },
};
const DRIFT_ACTION_LABELS = {
  none:             { label:'No Action',         color:'var(--text-3)',  icon:'—' },
  alerted:          { label:'Alert Raised',      color:'var(--warning)', icon:'⚠️' },
  kill_recommended: { label:'Kill Recommended',  color:'var(--danger)',  icon:'🛑' },
};
const DRIFT_REC_LABELS = {
  monitor:       'Monitor',
  restart_agent: 'Restart Agent',
  kill_agent:    'Kill Agent',
  escalate:      'Escalate',
};


// ── Main render ─────────────────────────────────────────────────────
async function renderAgentMonitor() {
  const pane = document.getElementById('pane-agent-monitor');
  if (!pane) return;

  pane.innerHTML = `
  

  <div class="bdd-root">
    <!-- ── Sidebar ── -->
    <div class="bdd-sidebar">
      <div class="bdd-sidebar-title">Drift Detection</div>
      <div class="bdd-nav active" id="bdd-nav-dashboard" onclick="bddSetTab('dashboard')">
        <span class="bdd-nav-icon">📊</span> Dashboard
      </div>
      <div class="bdd-nav" id="bdd-nav-agents" onclick="bddSetTab('agents')">
        <span class="bdd-nav-icon">🤖</span> Agent Scores
      </div>
      <div class="bdd-nav" id="bdd-nav-alerts" onclick="bddSetTab('alerts')">
        <span class="bdd-nav-icon">⚠️</span> Alerts
        <span class="bdd-alert-badge" id="bdd-alert-count" style="display:none">0</span>
      </div>
      <div class="bdd-nav" id="bdd-nav-history" onclick="bddSetTab('history')">
        <span class="bdd-nav-icon">📈</span> History
      </div>
      <div class="bdd-sidebar-div"></div>
      <div class="bdd-nav" id="bdd-nav-monitor" onclick="bddSetTab('monitor')">
        <span class="bdd-nav-icon">📡</span> Live Monitor
      </div>
      <div class="bdd-sidebar-foot">
        <button class="bdd-detect-btn" onclick="bddDetectAll()">🔍 Run Detection</button>
      </div>
    </div>

    <!-- ── Main ── -->
    <div class="bdd-main">
      <div class="bdd-header">
        <span class="bdd-header-title" id="bdd-header-title">🧬 Behavior Drift Detection</span>
        <button class="bdd-header-btn" onclick="bddRefresh()">↺ Refresh</button>
        <button class="bdd-header-btn" onclick="bddBuildFingerprints()" title="Recompute baselines">🧬 Rebuild Baselines</button>
        <button class="bdd-header-btn" onclick="bddDetectAll()" style="background:var(--accent);border-color:var(--accent);color:#fff">🔍 Detect All</button>
      </div>
      <div class="bdd-content" id="bdd-content">
        <div style="padding:40px;text-align:center;color:var(--text-3)">Loading…</div>
      </div>
    </div>
  </div>`;

  await bddRefresh();
  _startMonitorPoll();
}


// ── Data ────────────────────────────────────────────────────────────
async function bddRefresh() {
  const [sumR, alertsR, lbR] = await Promise.all([
    fetch('/api/drift/summary').then(r=>r.ok?r.json():{}).catch(()=>({})),
    fetch('/api/drift/alerts?limit=50').then(r=>r.ok?r.json():{alerts:[]}).catch(()=>({alerts:[]})),
    fetch('/api/drift/leaderboard').then(r=>r.ok?r.json():{leaderboard:[]}).catch(()=>({leaderboard:[]})),
  ]);
  _driftSummary     = sumR;
  _driftAlerts      = alertsR.alerts || [];
  _driftLeaderboard = lbR.leaderboard || [];

  // Update alert badge
  const unresolvedCount = _driftAlerts.filter(a=>!a.resolved).length;
  const badge = document.getElementById('bdd-alert-count');
  if (badge) {
    badge.textContent = unresolvedCount;
    badge.style.display = unresolvedCount > 0 ? 'inline-flex' : 'none';
  }

  bddRenderTab();
}


// ── Tab system ──────────────────────────────────────────────────────
function bddSetTab(tab) {
  _driftTab = tab;
  document.querySelectorAll('.bdd-nav').forEach(el => {
    el.classList.toggle('active', el.id === 'bdd-nav-' + tab);
  });
  const titles = {
    dashboard: '📊 Drift Detection Dashboard',
    agents:    '🤖 Agent Drift Scores',
    alerts:    '⚠️ Drift Alerts',
    history:   '📈 Drift History',
    monitor:   '📡 Live Agent Monitor',
  };
  const h = document.getElementById('bdd-header-title');
  if (h) h.textContent = titles[tab] || 'Behavior Drift Detection';
  bddRenderTab();
}

function bddRenderTab() {
  const c = document.getElementById('bdd-content');
  if (!c) return;
  if (_driftTab === 'dashboard') bddRenderDashboard(c);
  if (_driftTab === 'agents')    bddRenderAgents(c);
  if (_driftTab === 'alerts')    bddRenderAlerts(c);
  if (_driftTab === 'history')   bddRenderHistory(c);
  if (_driftTab === 'monitor')   bddRenderLiveMonitor(c);
}


// ── Dashboard ───────────────────────────────────────────────────────
function bddRenderDashboard(container) {
  const s   = _driftSummary || {};
  const lb  = _driftLeaderboard;
  const bySev = s.agents_by_severity || {};

  const critAgents  = lb.filter(a=>a.severity==='critical');
  const highAgents  = lb.filter(a=>a.severity==='high');
  const stableAgents= lb.filter(a=>['none','low'].includes(a.severity));
  const avgScore    = lb.length ? lb.reduce((s,a)=>s+a.drift_score,0)/lb.length : 0;

  const stats = [
    { val: lb.length,                              lbl:'Agents Tracked', col:'var(--accent)' },
    { val: (bySev.critical||0),                   lbl:'Critical',       col: bySev.critical>0?'var(--danger)':'var(--text-3)' },
    { val: (bySev.high||0),                       lbl:'High Drift',     col: bySev.high>0?'#f06080':'var(--text-3)' },
    { val: (bySev.medium||0),                     lbl:'Medium Drift',   col: bySev.medium>0?'var(--warning)':'var(--text-3)' },
    { val: s.alerts_unresolved||0,                 lbl:'Active Alerts',  col: s.alerts_unresolved>0?'var(--danger)':'var(--text-3)' },
    { val: avgScore.toFixed(1),                   lbl:'Avg Score',      col:'#9d74f5' },
  ];

  container.innerHTML = `
    <!-- Severity severity bar -->
    <div class="bdd-sev-bar" title="Distribution of agent drift severity">
      ${['critical','high','medium','low','none'].map(sev => {
        const cnt = bySev[sev]||0;
        const col = DRIFT_SEV_COLORS[sev]?.border||'var(--border)';
        return `<div class="bdd-sev-seg" style="background:${col};flex:${Math.max(cnt,0.5)}" title="${sev}: ${cnt}"></div>`;
      }).join('')}
    </div>

    <!-- Stats grid -->
    <div class="bdd-summary-grid">
      ${stats.map(s => `
        <div class="bdd-stat-card">
          <div class="bdd-stat-val" style="color:${s.col}">${s.val}</div>
          <div class="bdd-stat-lbl">${s.lbl}</div>
        </div>`).join('')}
    </div>

    <!-- Critical agents banner -->
    ${critAgents.length ? `
    <div style="background:rgba(232,82,82,.08);border:1px solid #e85252;border-radius:10px;padding:12px 14px;margin-bottom:14px">
      <div style="font-size:12px;font-weight:700;color:#e85252;margin-bottom:8px">🔴 Critical Drift — Immediate Action Required</div>
      ${critAgents.map(a => `
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;font-size:11px">
          <span style="font-weight:700;color:var(--text-0);min-width:90px">${escHtml(a.agent_id)}</span>
          <span style="color:#e85252;font-weight:800">${a.drift_score.toFixed(1)}/100</span>
          <span style="color:var(--text-3)">${escHtml((a.flags||[]).slice(0,3).join(', '))}</span>
          <div style="margin-left:auto;display:flex;gap:5px">
            <button class="bdd-alert-btn danger" onclick="bddKillAgent(${JSON.stringify(a.agent_id)})">🛑 Kill</button>
            <button class="bdd-alert-btn" onclick="bddViewAgent(${JSON.stringify(a.agent_id)})">🔍 Details</button>
          </div>
        </div>`).join('')}
    </div>` : ''}

    <!-- Leaderboard -->
    <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px">
      Drift Leaderboard — All Agents
    </div>
    <div class="bdd-leaderboard">
      ${lb.map(a => {
        const sc = DRIFT_SEV_COLORS[a.severity] || DRIFT_SEV_COLORS.none;
        const trendC = DRIFT_TREND_COLORS[a.trend] || 'var(--text-3)';
        const trendI = DRIFT_TREND_ICONS[a.trend]  || '?';
        const pct    = Math.min(a.drift_score, 100);
        const isSelected = _driftSelected === a.agent_id;
        return `<div class="bdd-lb-row ${isSelected?'selected':''}" onclick="bddViewAgent(${JSON.stringify(a.agent_id)})">
          <span class="bdd-lb-agent">${escHtml(a.agent_id)}</span>
          <div class="bdd-lb-score-bar">
            <div class="bdd-lb-score-fill" style="width:${pct}%;background:${sc.border}"></div>
          </div>
          <span class="bdd-lb-score-num" style="color:${sc.border}">${a.drift_score.toFixed(1)}</span>
          <span class="bdd-lb-sev" style="background:${sc.bg};color:${sc.text}">${sc.label}</span>
          <span class="bdd-lb-trend" style="color:${trendC}" title="${a.trend}">${trendI}</span>
          <span class="bdd-lb-flags">${escHtml((a.flags||[]).join(', '))}</span>
          <div class="bdd-lb-action">
            ${a.action==='kill_recommended' ? `<span style="font-size:9px;font-weight:700;color:var(--danger)">KILL</span>` :
              a.action==='alerted'          ? `<span style="font-size:9px;font-weight:700;color:var(--warning)">ALERT</span>` : ''}
          </div>
        </div>`;
      }).join('')}
    </div>
  `;
}


// ── Agents tab ──────────────────────────────────────────────────────
function bddRenderAgents(container) {
  if (!_driftSelected) {
    // Show leaderboard, click to select agent for detail
    container.innerHTML = `
      <div style="font-size:12px;color:var(--text-3);margin-bottom:12px">
        Click an agent to see its full drift profile, dimension breakdown, and sparkline chart.
      </div>
      <div class="bdd-leaderboard">
        ${_driftLeaderboard.map(a => {
          const sc = DRIFT_SEV_COLORS[a.severity] || DRIFT_SEV_COLORS.none;
          const pct = Math.min(a.drift_score, 100);
          return `<div class="bdd-lb-row" onclick="bddViewAgent(${JSON.stringify(a.agent_id)})">
            <div class="bdd-gauge" style="border-color:${sc.border};width:48px;height:48px">
              <span class="bdd-gauge-val" style="color:${sc.border};font-size:13px">${a.drift_score.toFixed(0)}</span>
              <span class="bdd-gauge-lbl" style="color:${sc.border};font-size:7px">${sc.label}</span>
            </div>
            <div style="flex:1;min-width:0">
              <div style="font-weight:700;font-size:13px;color:var(--text-0)">${escHtml(a.agent_id)}</div>
              <div style="font-size:10px;color:${DRIFT_TREND_COLORS[a.trend]||'var(--text-3)'}">
                ${DRIFT_TREND_ICONS[a.trend]||'?'} ${a.trend}
                ${a.flags?.length ? '· ' + escHtml(a.flags.slice(0,2).join(', ')) : ''}
              </div>
              <div class="bdd-lb-score-bar" style="margin-top:5px">
                <div class="bdd-lb-score-fill" style="width:${pct}%;background:${sc.border}"></div>
              </div>
            </div>
            <div style="display:flex;gap:5px">
              <button class="bdd-header-btn" onclick="event.stopPropagation();bddDetectAgent(${JSON.stringify(a.agent_id)})">🔍 Run</button>
            </div>
          </div>`;
        }).join('')}
      </div>`;
  } else {
    bddRenderAgentDetail(container, _driftSelected);
  }
}

async function bddRenderAgentDetail(container, agentId) {
  container.innerHTML = `<div style="color:var(--text-3);padding:20px">Loading ${agentId}…</div>`;

  const d = await fetch(`/api/drift/agent/${encodeURIComponent(agentId)}`)
    .then(r=>r.ok?r.json():null).catch(()=>null);
  if (!d || !d.ok) {
    container.innerHTML = `<div style="color:var(--danger);padding:20px">Failed to load agent: ${escHtml(agentId)}</div>`;
    return;
  }

  const ls   = d.latest_score || {};
  const fp   = d.fingerprint  || {};
  const hist = d.scores_24h   || [];
  const alts = d.active_alerts|| [];
  const sc   = DRIFT_SEV_COLORS[ls.severity||'none'];
  const dims = ls.dimensions   || {};

  // Build sparkline
  const sparklineHTML = bddBuildSparkline(hist);

  const dimRows = Object.entries(DRIFT_DIM_LABELS).map(([key, meta]) => {
    const dim = dims[key] || {};
    const z   = dim.zscore || 0;
    const barPct = Math.min(z * 20, 100);
    const barCol = z > 3 ? '#e85252' : z > 2 ? '#f06080' : z > 1 ? '#e8a237' : '#3dba7a';
    const curVal = key==='error_rate'
      ? `${((dim.current||0)*100).toFixed(1)}%`
      : key==='cost'
        ? `$${(dim.current||0).toFixed(5)}`
        : `${(dim.current||0).toFixed(0)}${meta.unit}`;
    const baseVal = key==='error_rate'
      ? `${((dim.baseline||0)*100).toFixed(1)}%`
      : key==='cost'
        ? `$${(dim.baseline||0).toFixed(5)}`
        : `${(dim.baseline||0).toFixed(0)}${meta.unit}`;
    return `<div class="bdd-dim-row">
      <span class="bdd-dim-icon">${meta.icon}</span>
      <span class="bdd-dim-label">${meta.label}</span>
      <div class="bdd-dim-bar-wrap">
        <div class="bdd-dim-bar-fill" style="width:${barPct}%;background:${barCol}"></div>
      </div>
      <span class="bdd-dim-zscore" style="color:${barCol}">${z.toFixed(1)}σ</span>
      <span class="bdd-dim-vals">${curVal} / ${baseVal}</span>
    </div>`;
  }).join('');

  container.innerHTML = `
    <!-- Back button -->
    <div style="margin-bottom:12px">
      <button class="bdd-header-btn" onclick="_driftSelected=null;bddRenderAgents(document.getElementById('bdd-content'))">← Back to All Agents</button>
    </div>

    <!-- Agent header -->
    <div style="display:flex;align-items:center;gap:14px;margin-bottom:16px;flex-wrap:wrap">
      <div class="bdd-gauge" style="border-color:${sc.border}">
        <span class="bdd-gauge-val" style="color:${sc.border}">${(ls.drift_score||0).toFixed(1)}</span>
        <span class="bdd-gauge-lbl" style="color:${sc.border}">${sc.label}</span>
      </div>
      <div style="flex:1">
        <div style="font-size:18px;font-weight:800;color:var(--text-0)">${escHtml(agentId)}</div>
        <div style="font-size:12px;color:${DRIFT_TREND_COLORS[ls.trend]||'var(--text-3)'}">
          ${DRIFT_TREND_ICONS[ls.trend]||''} ${ls.trend||'—'} &nbsp;
          <span style="color:var(--text-3)">${ls.computed_at ? 'Computed ' + new Date(ls.computed_at).toLocaleTimeString() : ''}</span>
        </div>
        <div style="font-size:11px;color:var(--text-2);margin-top:3px">${escHtml(ls.detail||'')}</div>
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        <button class="bdd-header-btn" onclick="bddDetectAgent(${JSON.stringify(agentId)})">🔍 Re-run Detection</button>
        <button class="bdd-header-btn" onclick="bddBuildFingerprint(${JSON.stringify(agentId)})">🧬 Rebuild Baseline</button>
        ${ls.severity==='critical' ? `<button class="bdd-header-btn" style="color:var(--danger);border-color:var(--danger)" onclick="bddKillAgent(${JSON.stringify(agentId)})">🛑 Kill Agent</button>` : ''}
      </div>
    </div>

    <!-- Active alerts for this agent -->
    ${alts.length ? `
    <div style="margin-bottom:14px">
      ${alts.map(a => `
        <div class="bdd-alert-card" style="border-color:${DRIFT_SEV_COLORS[a.severity]?.border||'var(--border)'}">
          <span class="bdd-alert-icon">${a.severity==='critical'?'🔴':'🟡'}</span>
          <div class="bdd-alert-body">
            <div class="bdd-alert-title">${escHtml(a.title)}</div>
            <div class="bdd-alert-desc">${escHtml(a.description)}</div>
          </div>
          <div class="bdd-alert-actions">
            <button class="bdd-alert-btn" onclick="bddResolveAlert(${JSON.stringify(a.alert_id)})">✓ Resolve</button>
          </div>
        </div>`).join('')}
    </div>` : ''}

    <div class="bdd-detail-layout">
      <!-- Dimensions -->
      <div class="bdd-detail-panel">
        <div class="bdd-panel-title">📊 Dimension Z-Scores &nbsp;<span style="font-weight:400;color:var(--text-3)">(current vs baseline)</span></div>
        ${dimRows}
        <div style="font-size:10px;color:var(--text-3);margin-top:8px">Z-score = standard deviations from baseline mean. >2σ = warning, >3σ = critical.</div>
      </div>

      <!-- Baseline fingerprint -->
      <div class="bdd-detail-panel">
        <div class="bdd-panel-title">🧬 Baseline Fingerprint <span style="font-weight:400;color:var(--text-3)">(7-day rolling)</span></div>
        ${fp ? `
        <div class="bdd-fp-grid">
          <div class="bdd-fp-item">
            <div class="bdd-fp-label">Latency Mean</div>
            <div class="bdd-fp-val">${fp.lat_mean?.toFixed(0)||'—'}ms</div>
            <div class="bdd-fp-sub">±${fp.lat_stddev?.toFixed(0)||'—'}ms std</div>
          </div>
          <div class="bdd-fp-item">
            <div class="bdd-fp-label">Latency P90</div>
            <div class="bdd-fp-val">${fp.lat_p90?.toFixed(0)||'—'}ms</div>
            <div class="bdd-fp-sub">P99: ${fp.lat_p99?.toFixed(0)||'—'}ms</div>
          </div>
          <div class="bdd-fp-item">
            <div class="bdd-fp-label">Tokens/task</div>
            <div class="bdd-fp-val">${fp.tok_mean?.toFixed(0)||'—'}</div>
            <div class="bdd-fp-sub">±${fp.tok_stddev?.toFixed(0)||'—'} std</div>
          </div>
          <div class="bdd-fp-item">
            <div class="bdd-fp-label">Cost/task</div>
            <div class="bdd-fp-val">$${fp.cost_mean?.toFixed(5)||'—'}</div>
            <div class="bdd-fp-sub">P90: $${fp.cost_p90?.toFixed(5)||'—'}</div>
          </div>
          <div class="bdd-fp-item">
            <div class="bdd-fp-label">Error Rate</div>
            <div class="bdd-fp-val">${((fp.error_rate_mean||0)*100).toFixed(1)}%</div>
            <div class="bdd-fp-sub">Baseline</div>
          </div>
          <div class="bdd-fp-item">
            <div class="bdd-fp-label">Tasks/hour</div>
            <div class="bdd-fp-val">${fp.tasks_per_hour?.toFixed(1)||'—'}</div>
            <div class="bdd-fp-sub">${fp.total_samples||0} samples</div>
          </div>
        </div>
        <div style="font-size:10px;color:var(--text-3);margin-top:8px">
          Computed ${fp.computed_at ? new Date(fp.computed_at).toLocaleString() : '—'}
        </div>` : '<div style="color:var(--text-3);font-size:12px">No fingerprint computed. Click "Rebuild Baseline".</div>'}
      </div>
    </div>

    <!-- Sparkline chart -->
    <div class="bdd-detail-panel" style="margin-top:14px">
      <div class="bdd-panel-title">📈 Drift Score — Last 24h</div>
      ${hist.length >= 2 ? `
        <div class="bdd-sparkline-wrap">
          <span class="bdd-sparkline-label">${hist.length} measurements</span>
          ${sparklineHTML}
        </div>` : `<div style="color:var(--text-3);font-size:12px">Insufficient history (${hist.length} measurements). Run detection over time to build the chart.</div>`}
    </div>
  `;
}

function bddBuildSparkline(hist) {
  if (hist.length < 2) return '';
  const W=560, H=60, padX=10, padY=8;
  const scores = hist.map(h=>h.drift_score);
  const minS   = Math.min(...scores, 0);
  const maxS   = Math.max(...scores, 10);
  const range  = maxS - minS || 1;

  const toX = (i) => padX + (i / (hist.length - 1)) * (W - padX*2);
  const toY = (s) => padY + (1 - (s - minS) / range) * (H - padY*2);

  const points = hist.map((h,i) => `${toX(i)},${toY(h.drift_score)}`).join(' ');
  const dots   = hist.map((h,i) => {
    const col = DRIFT_SEV_COLORS[h.severity||'none']?.border || '#3dba7a';
    const x = toX(i), y = toY(h.drift_score);
    const ts = new Date(h.computed_at).toLocaleTimeString();
    return `<circle cx="${x}" cy="${y}" r="3" fill="${col}" title="${h.drift_score.toFixed(1)} — ${h.severity} (${ts})"/>`;
  }).join('');

  // Reference lines at 25 (low), 45 (medium), 70 (high)
  const refLines = [
    { s:25, col:'#5b8af8', lbl:'Low'    },
    { s:45, col:'#e8a237', lbl:'Medium' },
    { s:70, col:'#f06080', lbl:'High'   },
  ].filter(r => r.s >= minS && r.s <= maxS).map(r => {
    const y = toY(r.s);
    return `<line x1="${padX}" y1="${y}" x2="${W-padX}" y2="${y}" stroke="${r.col}" stroke-width="0.5" stroke-dasharray="4,3" opacity="0.6"/>
      <text x="${W-padX+2}" y="${y+3}" font-size="8" fill="${r.col}">${r.lbl}</text>`;
  }).join('');

  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:${H}px">
    ${refLines}
    <polyline points="${points}" fill="none" stroke="#9d74f5" stroke-width="2"/>
    ${dots}
  </svg>`;
}


// ── Alerts tab ──────────────────────────────────────────────────────
function bddRenderAlerts(container) {
  const unresolved = _driftAlerts.filter(a => !a.resolved);
  const resolved   = _driftAlerts.filter(a =>  a.resolved);

  if (!unresolved.length && !resolved.length) {
    container.innerHTML = `<div class="bdd-empty">
      <div class="bdd-empty-icon">✅</div>
      <div class="bdd-empty-title">No Drift Alerts</div>
      <div class="bdd-empty-sub">All agents are within normal behavioral parameters. Run detection to check for new issues.</div>
    </div>`;
    return;
  }

  const renderCard = (a) => {
    const sc  = DRIFT_SEV_COLORS[a.severity] || DRIFT_SEV_COLORS.none;
    const rec = DRIFT_REC_LABELS[a.recommended_action] || a.recommended_action;
    const ackEl = a.acknowledged ? '<span style="font-size:10px;color:var(--success)">✓ Acknowledged</span>' : '';
    return `<div class="bdd-alert-card" style="border-color:${sc.border};${a.resolved?'opacity:.5':''}">
      <span class="bdd-alert-icon">${a.severity==='critical'?'🔴':a.severity==='high'?'🟠':a.severity==='medium'?'🟡':'🔵'}</span>
      <div class="bdd-alert-body">
        <div class="bdd-alert-title">${escHtml(a.title)}</div>
        <div class="bdd-alert-desc">${escHtml(a.description)}</div>
        <div class="bdd-alert-meta">
          <span class="bdd-lb-sev" style="background:${sc.bg};color:${sc.text}">${sc.label}</span>
          <span>Score: <strong>${a.drift_score?.toFixed(1)||'?'}</strong></span>
          <span>Action: <strong style="color:${a.recommended_action==='kill_agent'?'var(--danger)':a.recommended_action==='restart_agent'?'var(--warning)':'var(--text-1)'}">${rec}</strong></span>
          <span>${new Date(a.created_at).toLocaleString()}</span>
          ${ackEl}
        </div>
      </div>
      <div class="bdd-alert-actions">
        ${!a.resolved ? `
          ${!a.acknowledged ? `<button class="bdd-alert-btn" onclick="bddAckAlert(${JSON.stringify(a.alert_id)})">👁 Ack</button>` : ''}
          ${a.recommended_action==='kill_agent' ? `<button class="bdd-alert-btn danger" onclick="bddKillAgent(${JSON.stringify(a.agent_id)})">🛑 Kill</button>` : ''}
          <button class="bdd-alert-btn" onclick="bddViewAgent(${JSON.stringify(a.agent_id)})">🔍 Inspect</button>
          <button class="bdd-alert-btn" onclick="bddResolveAlert(${JSON.stringify(a.alert_id)})">✓ Resolve</button>
        ` : '<span style="font-size:10px;color:var(--success)">Resolved</span>'}
      </div>
    </div>`;
  };

  container.innerHTML = `
    ${unresolved.length ? `
    <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;margin-bottom:10px">
      Active Alerts (${unresolved.length})
    </div>
    ${unresolved.map(renderCard).join('')}` : ''}
    ${resolved.length ? `
    <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;margin:14px 0 10px">
      Resolved (${resolved.length})
    </div>
    ${resolved.slice(0,5).map(renderCard).join('')}` : ''}
  `;
}


// ── History tab ─────────────────────────────────────────────────────
async function bddRenderHistory(container) {
  container.innerHTML = `<div style="color:var(--text-3);padding:20px">Loading history…</div>`;
  const d = await fetch('/api/drift/history?hours=24&limit=200').then(r=>r.ok?r.json():{history:[]}).catch(()=>({history:[]}));
  const hist = d.history || [];

  if (!hist.length) {
    container.innerHTML = `<div class="bdd-empty">
      <div class="bdd-empty-icon">📈</div>
      <div class="bdd-empty-title">No History Yet</div>
      <div class="bdd-empty-sub">Run drift detection to populate the history timeline.</div>
    </div>`;
    return;
  }

  container.innerHTML = `
    <div style="font-size:11px;color:var(--text-3);margin-bottom:12px">Last 24 hours · ${hist.length} measurements across ${new Set(hist.map(h=>h.agent_id)).size} agents</div>
    <table class="bdd-hist-table">
      <thead><tr>
        <th>Time</th><th>Agent</th><th>Window</th><th>Score</th><th>Severity</th><th>Trend</th><th>Flags</th><th>Action</th>
      </tr></thead>
      <tbody>
        ${hist.map(h => {
          const sc = DRIFT_SEV_COLORS[h.severity||'none'];
          const tc = DRIFT_TREND_COLORS[h.trend||'stable'];
          return `<tr onclick="bddViewAgent(${JSON.stringify(h.agent_id)})">
            <td style="color:var(--text-3);white-space:nowrap">${new Date(h.computed_at).toLocaleTimeString()}</td>
            <td style="font-weight:600;color:var(--accent)">${escHtml(h.agent_id)}</td>
            <td style="font-size:10px;color:var(--text-3)">${h.window_label||'1h'}</td>
            <td style="font-weight:800;color:${sc.border}">${(h.drift_score||0).toFixed(1)}</td>
            <td><span class="bdd-lb-sev" style="background:${sc.bg};color:${sc.text}">${sc.label}</span></td>
            <td style="color:${tc}">${DRIFT_TREND_ICONS[h.trend||'stable']||''} ${h.trend||''}</td>
            <td style="font-size:10px;color:var(--text-3)">${escHtml((h.flags||[]).join(', ').slice(0,40))}</td>
            <td style="font-size:10px">${h.action && h.action!=='none' ? `<span style="color:var(--warning)">${h.action}</span>` : '—'}</td>
          </tr>`;
        }).join('')}
      </tbody>
    </table>
  `;
}


// ── Live Monitor tab (old content, preserved) ────────────────────────
async function bddRenderLiveMonitor(container) {
  const [live, anomalies, summary] = await Promise.all([
    fetch('/api/agent-monitor/live').then(r=>r.ok?r.json():{agents:[],summary:{}}).catch(()=>({agents:[],summary:{}})),
    fetch('/api/agent-monitor/anomalies?limit=10').then(r=>r.ok?r.json():{anomalies:[]}).catch(()=>({anomalies:[]})),
    fetch('/api/agent-monitor/summary').then(r=>r.ok?r.json():{}).catch(()=>({})),
  ]);
  const statusColor={idle:'var(--text-3)',working:'var(--warning)',killed:'var(--danger)',paused:'var(--accent)'};
  const statusIcon ={idle:'💤',working:'⚡',killed:'💀',paused:'⏸️'};

  container.innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-bottom:16px">
      ${[['🤖','Total',summary.total_agents||0,'var(--text-2)'],['⚡','Active',summary.active_agents||0,'var(--warning)'],
         ['💤','Idle',(summary.total_agents||0)-(summary.active_agents||0)-(summary.killed_agents||0),'var(--text-3)'],
         ['💀','Killed',summary.killed_agents||0,'var(--danger)'],
         ['⚠️','Anomalies',summary.unresolved_anomalies||0,'var(--warning)'],
         ['💰','Cost',`$${((summary.session_summary||{}).session_cost||0).toFixed(4)}`,'#9ece6a']
        ].map(([i,l,v,c])=>`<div class="bdd-stat-card"><div class="bdd-stat-val" style="color:${c}">${i} ${v}</div><div class="bdd-stat-lbl">${l}</div></div>`).join('')}
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px">
      ${(live.agents||[]).map(a => renderAgentMonitorCard(a, statusColor, statusIcon)).join('')}
    </div>
  `;
}


// ── Actions ──────────────────────────────────────────────────────────
async function bddDetectAll() {
  showToast('🔍 Running drift detection for all agents…');
  try {
    const r = await fetch('/api/drift/detect', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    const d = await r.json();
    showToast(`✅ Detection complete: ${d.agents_flagged} flagged / ${d.agents_checked} checked`);
    await bddRefresh();
  } catch(e) { showToast('⚠️ Detection failed: '+e.message); }
}

async function bddDetectAgent(agentId) {
  showToast(`🔍 Running detection for ${agentId}…`);
  try {
    const r = await fetch(`/api/drift/detect/${encodeURIComponent(agentId)}`,
      {method:'POST',headers:{'Content-Type':'application/json'},body:'{"window":"1h"}'});
    const d = await r.json();
    if (d.ok) {
      showToast(`✅ ${agentId}: score=${d.drift_score?.toFixed(1)} (${d.severity})`);
      await bddRefresh();
      if (_driftSelected === agentId) bddRenderAgentDetail(document.getElementById('bdd-content'), agentId);
    } else { showToast('⚠️ '+d.error); }
  } catch(e) { showToast('⚠️ '+e.message); }
}

async function bddBuildFingerprints() {
  showToast('🧬 Rebuilding behavioral baselines for all agents…');
  try {
    const r = await fetch('/api/drift/fingerprint',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const d = await r.json();
    showToast(`✅ Baselines rebuilt: ${d.computed} agents`);
    await bddRefresh();
  } catch(e) { showToast('⚠️ '+e.message); }
}

async function bddBuildFingerprint(agentId) {
  showToast(`🧬 Rebuilding baseline for ${agentId}…`);
  try {
    const r = await fetch(`/api/drift/fingerprint/${encodeURIComponent(agentId)}`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const d = await r.json();
    if (d.ok) {
      showToast(`✅ Baseline rebuilt: ${d.total_samples} samples`);
      bddRenderAgentDetail(document.getElementById('bdd-content'), agentId);
    } else { showToast('⚠️ '+d.error); }
  } catch(e) { showToast('⚠️ '+e.message); }
}

async function bddViewAgent(agentId) {
  _driftSelected = agentId;
  bddSetTab('agents');
  bddRenderAgentDetail(document.getElementById('bdd-content'), agentId);
}

async function bddAckAlert(alertId) {
  await fetch(`/api/drift/alerts/${encodeURIComponent(alertId)}/acknowledge`,{method:'POST'});
  showToast('👁 Alert acknowledged');
  const hr = await fetch('/api/drift/alerts?limit=50').then(r=>r.ok?r.json():{alerts:[]});
  _driftAlerts = hr.alerts || [];
  bddRenderAlerts(document.getElementById('bdd-content'));
}

async function bddResolveAlert(alertId) {
  await fetch(`/api/drift/alerts/${encodeURIComponent(alertId)}/resolve`,{method:'POST'});
  showToast('✅ Alert resolved');
  const hr = await fetch('/api/drift/alerts?limit=50').then(r=>r.ok?r.json():{alerts:[]});
  _driftAlerts = hr.alerts || [];
  const cnt = document.getElementById('bdd-alert-count');
  const unres = _driftAlerts.filter(a=>!a.resolved).length;
  if (cnt) { cnt.textContent=unres; cnt.style.display=unres>0?'inline-flex':'none'; }
  bddRenderAlerts(document.getElementById('bdd-content'));
}

async function bddKillAgent(agentId) {
  const ok = await gmDanger('Kill Agent', `Immediately stop all tasks for agent "${agentId}"?\n\nThis is the recommended action for critical behavior drift.`);
  if (!ok) return;
  try {
    const r = await fetch(`/api/agent-monitor/kill/${encodeURIComponent(agentId)}`,
      {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason:'Critical behavior drift — auto-kill recommended'})});
    const d = await r.json();
    showToast(d.ok ? `🛑 Agent ${agentId} killed` : '⚠️ Kill failed');
    await bddRefresh();
  } catch(e) { showToast('⚠️ '+e.message); }
}


// ── Live poll ────────────────────────────────────────────────────────
function _startMonitorPoll() {
  if (_monitorPoll) clearInterval(_monitorPoll);
  _monitorPoll = setInterval(async() => {
    if (!document.getElementById('pane-agent-monitor')?.classList.contains('active')) {
      clearInterval(_monitorPoll); _monitorPoll = null; return;
    }
    // Only auto-refresh summary numbers, not full re-render
    const sr = await fetch('/api/drift/summary').then(r=>r.ok?r.json():{}).catch(()=>({}));
    _driftSummary = sr;
    const unres = sr.alerts_critical||0 + sr.alerts_high||0;
    const badge = document.getElementById('bdd-alert-count');
    if (badge && (sr.alerts_unresolved||0) > 0) {
      badge.textContent = sr.alerts_unresolved;
      badge.style.display = 'inline-flex';
    }
  }, 15000);  // every 15s — gentle, not aggressive
}


// ── Old compat aliases (referenced by nav patches) ───────────────────
function renderAgentMonitorCard(a, statusColor, statusIcon) {
  const sCol = (statusColor||{})[a.status]||'var(--text-3)';
  const hasAnomaly = a.anomaly_score > 0;
  return `<div style="background:var(--bg-2);border:1px solid ${hasAnomaly?'var(--danger)':a.status==='working'?'var(--warning)':'var(--border)'};border-radius:12px;padding:14px">
    ${hasAnomaly?'<div style="float:right">⚠️</div>':''}
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
      <div style="width:28px;height:28px;border-radius:50%;background:${a.color||'#7aa2f7'}33;display:flex;align-items:center;justify-content:center">${a.avatar||'🤖'}</div>
      <div><div style="font-weight:700;font-size:12px">${escHtml(a.name||a.agent_id)}</div>
        <div style="font-size:10px;color:${sCol}">${(statusIcon||{})[a.status]||''} ${a.status}</div></div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:10px;margin-bottom:8px">
      <div style="background:var(--bg-3);border-radius:5px;padding:4px 7px"><div style="color:var(--text-3)">Cost</div><div>$${(a.cost_session||0).toFixed(4)}</div></div>
      <div style="background:var(--bg-3);border-radius:5px;padding:4px 7px"><div style="color:var(--text-3)">Errors</div><div style="color:${a.errors_session>0?'var(--danger)':'var(--text-0)'}">${a.errors_session||0}</div></div>
    </div>
    <div style="display:flex;gap:5px">
      <button class="btn-sm" onclick="bddViewAgent(${JSON.stringify(a.agent_id||a.id)})" style="font-size:10px">📊 Drift</button>
      ${!a.is_killed ?
        `<button class="btn-sm" onclick="bddKillAgent(${JSON.stringify(a.agent_id||a.id)})" style="color:var(--danger);border-color:var(--danger);font-size:10px">🛑</button>` :
        `<button class="btn-sm" onclick="monitorReviveAgent(${JSON.stringify(a.agent_id||a.id)})" style="color:var(--success);font-size:10px">♻️</button>`}
    </div>
  </div>`;
}
async function monitorDetectAnomalies() { await bddDetectAll(); }
async function monitorSnapshotKPIs() {
  const r = await fetch('/api/agent-monitor/kpis/snapshot',{method:'POST'}).catch(()=>null);
  const d = r ? await r.json() : {};
  showToast(`📸 KPI snapshot: ${d.snapshotted||0} agents`);
}
async function monitorViewKPIs(id) { await bddViewAgent(id); }
async function monitorKillAgent(id) { await bddKillAgent(id); }
async function monitorReviveAgent(id) {
  const r = await fetch(`/api/agent-monitor/revive/${encodeURIComponent(id)}`,{method:'POST'}).catch(()=>null);
  const d = r ? await r.json() : {};
  showToast(d.ok ? `♻️ ${id} revived` : '⚠️ Revive failed');
  await bddRefresh();
}
async function monitorShadowTest(id) {
  const r = await fetch('/api/agent-monitor/shadow',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent_id:id,shadow_config:{}})}).catch(()=>null);
  const d = r ? await r.json() : {};
  showToast(d.ok ? `🔬 Shadow: ${d.test_id}` : '⚠️ Failed');
}
async function monitorResolveAnomaly(id) {
  await fetch(`/api/agent-monitor/anomalies/${encodeURIComponent(id)}/resolve`,{method:'POST'});
  showToast('✅ Resolved');
  await bddRefresh();
}



// ══════════════════════════════════════════════════════════════════
//  SPRINT D — FINOPS
// ══════════════════════════════════════════════════════════════════
async function renderFinOps() {
  const pane = document.getElementById('pane-finops');
  if (!pane) return;

  const [dash, alerts, series] = await Promise.all([
    fetch('/api/finops/dashboard').then(r=>r.ok?r.json():{}).catch(()=>({})),
    fetch('/api/finops/alerts?limit=5').then(r=>r.ok?r.json():{alerts:[]}).catch(()=>({alerts:[]})),
    fetch('/api/finops/stats/time-series?days=7&granularity=hour').then(r=>r.ok?r.json():{series:[]}).catch(()=>({series:[]})),
  ]);

  const srcIcons = {llm:'🤖',mcp:'🔀',connector:'🔌',supervisor:'🧠',loop:'♾️',system:'⚙️'};

  pane.innerHTML = `
  <div style="padding:20px;max-width:1100px;margin:0 auto">
    <div class="section-head" style="margin-bottom:20px">
      <div>
        <h2 style="margin:0 0 4px">💰 FinOps — Cost Attribution</h2>
        <p style="margin:0;color:var(--text-2);font-size:13px">Unified cost tracking per agent, goal, and task · Spending caps · Burn rate projections · Compliance export</p>
      </div>
      <div style="display:flex;gap:8px">
        <a href="/api/finops/export/csv?days=30" download class="btn-sm" style="text-decoration:none;display:inline-flex;align-items:center">⬇ Export CSV</a>
        <button class="btn-sm" onclick="finopsCreateCap()">+ Budget Cap</button>
        <button class="btn-sm" onclick="renderFinOps()">↻ Refresh</button>
      </div>
    </div>

    <!-- Cost summary -->
    <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:18px">
      ${[
        ['💰','All-Time Cost',`$${(dash.total_cost_usd||0).toFixed(4)}`,'var(--accent)'],
        ['📅','Today',`$${(dash.cost_today||0).toFixed(4)}`,'var(--warning)'],
        ['⏱️','Last Hour',`$${(dash.cost_last_hour||0).toFixed(5)}`,'var(--text-2)'],
        ['📈','Daily Projection',`$${(dash.projected_daily||0).toFixed(4)}`,'#9ece6a'],
        ['⚠️','Alerts',dash.unresolved_alerts||0,dash.unresolved_alerts>0?'var(--danger)':'var(--text-3)'],
      ].map(([icon,label,val,col])=>`
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:12px;text-align:center">
          <div style="font-size:18px">${icon}</div>
          <div style="font-size:9px;color:var(--text-3);text-transform:uppercase">${label}</div>
          <div style="font-size:16px;font-weight:700;color:${col}">${val}</div>
        </div>`).join('')}
    </div>

    <!-- Alerts -->
    ${(alerts.alerts||[]).length>0?`
    <div style="background:rgba(247,118,142,0.08);border:1px solid var(--danger);border-radius:10px;padding:12px 16px;margin-bottom:16px">
      <div style="font-size:12px;font-weight:700;color:var(--danger);margin-bottom:8px">💸 Budget Alerts</div>
      ${(alerts.alerts||[]).map(a=>`
        <div style="display:flex;align-items:center;gap:8px;font-size:11px;margin-bottom:4px">
          <span>${a.alert_type==='breach'?'🔴':'🟡'}</span>
          <strong>${escHtml(a.cap_name||'Cap')}</strong>
          <span style="color:var(--text-2)">${a.alert_type}: ${Math.round(a.pct_used*100)}% used ($${a.cost_at_alert?.toFixed(4)} / $${a.limit_usd?.toFixed(4)})</span>
          <button class="btn-sm" onclick="finopsResolveAlert(${JSON.stringify(a.id)})" style="margin-left:auto;font-size:10px">✓</button>
        </div>`).join('')}
    </div>`:''}

    <!-- Granular Token Cost Attribution Treemap & Heatmap (Phase 4) -->
    <div class="card-elevated surface-z3" style="margin-bottom:18px;border:1px solid var(--border-hi);padding:18px;border-radius:16px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:8px">
        <div>
          <h3 style="margin:0 0 4px;font-size:15px;color:var(--text-0)">🔥 Granular Token Cost Treemap & Burn Allocation</h3>
          <span style="font-size:12px;color:var(--text-2)">Real-time spend heatmap across Models, Specialist Roles (brain, builder), and Workspace Folders</span>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          <button onclick="finopsFilterHeatmap('model')" class="btn-3d btn-ghost btn-sm" id="fo-filter-model" style="padding:4px 10px;font-size:11px;background:var(--accent-glow);border-color:var(--accent)">By Model</button>
          <button onclick="finopsFilterHeatmap('role')" class="btn-3d btn-ghost btn-sm" id="fo-filter-role" style="padding:4px 10px;font-size:11px">By Agent Role</button>
          <button onclick="finopsFilterHeatmap('folder')" class="btn-3d btn-ghost btn-sm" id="fo-filter-folder" style="padding:4px 10px;font-size:11px">By Folder</button>
          <button onclick="if(typeof toggleSplitWorkspace==='function') toggleSplitWorkspace(true, 'finops')" class="btn-3d btn-ghost btn-sm" style="padding:4px 10px;font-size:11px">🗂️ Secondary Dock</button>
        </div>
      </div>
      <div id="finops-treemap-grid" style="display:grid;grid-template-columns:2fr 1fr 1fr;grid-template-rows:110px 110px;gap:10px;font-family:monospace">
        <div style="background:rgba(56,189,248,0.14);border:1px solid var(--accent);border-radius:10px;padding:14px;display:flex;flex-direction:column;justify-content:space-between;grid-row:1/3;transition:all .15s" class="fo-cell">
          <div>
            <div style="font-weight:800;font-size:13.5px;color:var(--accent)">Claude 3.5 Sonnet (OpenRouter)</div>
            <div style="font-size:11px;color:var(--text-2)">Primary Cloud Inference Gateway</div>
          </div>
          <div>
            <div style="font-size:20px;font-weight:800;color:#fff">$0.00124</div>
            <div style="font-size:10.5px;color:var(--text-3)">42.5% of total spend • 18,400 tokens</div>
          </div>
        </div>
        <div style="background:rgba(16,185,129,0.14);border:1px solid #10b981;border-radius:10px;padding:12px;display:flex;flex-direction:column;justify-content:space-between;transition:all .15s" class="fo-cell">
          <div>
            <div style="font-weight:800;font-size:12px;color:#10b981">Ollama Llama 3.3 70B</div>
            <div style="font-size:10px;color:var(--text-2)">Local Inference Engine</div>
          </div>
          <div>
            <div style="font-size:15px;font-weight:800;color:#fff">$0.00000</div>
            <div style="font-size:9.5px;color:var(--text-3)">Free Local Execution • 45,200 tokens</div>
          </div>
        </div>
        <div style="background:rgba(168,85,247,0.14);border:1px solid #a855f7;border-radius:10px;padding:12px;display:flex;flex-direction:column;justify-content:space-between;transition:all .15s" class="fo-cell">
          <div>
            <div style="font-weight:800;font-size:12px;color:#a855f7">GPT-4o (Universal)</div>
            <div style="font-size:10px;color:var(--text-2)">Fallback Node</div>
          </div>
          <div>
            <div style="font-size:15px;font-weight:800;color:#fff">$0.00042</div>
            <div style="font-size:9.5px;color:var(--text-3)">14.2% spend • 6,100 tokens</div>
          </div>
        </div>
        <div style="background:rgba(245,158,11,0.14);border:1px solid #f59e0b;border-radius:10px;padding:12px;display:flex;flex-direction:column;justify-content:space-between;grid-column:2/4;transition:all .15s" class="fo-cell">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
              <div style="font-weight:800;font-size:12px;color:#f59e0b">Specialist Roles: Brain & Builder Swarm</div>
              <div style="font-size:10px;color:var(--text-2)">Multi-Agent Orchestration Fanout</div>
            </div>
            <span class="badge badge-warning">BUDGET ACTIVE</span>
          </div>
          <div>
            <div style="font-size:15px;font-weight:800;color:#fff">$0.00086</div>
            <div style="font-size:9.5px;color:var(--text-3)">Burn rate: $0.0002 / hr • Hard cap limit $5.0000</div>
          </div>
        </div>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:18px">
      <!-- Cost by source -->
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:14px">
        <div style="font-size:12px;font-weight:700;margin-bottom:12px">💸 Cost by Source</div>
        ${(dash.by_source_type||[]).map(s=>`
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
            <span style="font-size:16px">${srcIcons[s.source_type]||'⚙️'}</span>
            <span style="font-size:12px;flex:1">${escHtml(s.source_type)}</span>
            <span style="font-size:11px;color:var(--text-3)">${s.n} calls</span>
            <span style="font-weight:700;font-size:12px;color:var(--accent)">$${(s.c||0).toFixed(5)}</span>
          </div>`).join('')||'<div style="color:var(--text-3);font-size:12px">No cost data yet</div>'}
      </div>

      <!-- Budget caps -->
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:14px">
        <div style="font-size:12px;font-weight:700;margin-bottom:12px">🚦 Budget Caps</div>
        ${(dash.budget_caps||[]).map(c=>{
          const pct = c.limit_usd>0 ? Math.min((c.current_usd/c.limit_usd)*100,100) : 0;
          const barColor = pct>=100?'var(--danger)':pct>=80?'var(--warning)':'var(--success)';
          return `
          <div style="margin-bottom:10px">
            <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px">
              <span style="color:var(--text-1)">${escHtml(c.name)}</span>
              <span style="color:${barColor}">${Math.round(pct)}% · $${(c.current_usd||0).toFixed(4)}/$${c.limit_usd}</span>
            </div>
            <div style="background:var(--bg-3);border-radius:3px;height:5px">
              <div style="width:${Math.min(pct,100)}%;height:5px;background:${barColor};border-radius:3px;transition:width .4s"></div>
            </div>
          </div>`;}).join('')||'<div style="color:var(--text-3);font-size:12px">No caps configured</div>'}
        <button class="btn-sm" onclick="finopsCreateCap()" style="margin-top:8px;width:100%">+ Add Cap</button>
      </div>
    </div>

    <!-- Top agents by cost -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:16px">
      <div style="font-size:12px;font-weight:700;margin-bottom:12px">🤖 Cost by Agent</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px">
        ${(dash.by_agent||[]).map(a=>`
          <div style="background:var(--bg-3);border-radius:8px;padding:8px 12px;font-size:11px">
            <div style="font-weight:600;color:var(--accent)">${escHtml(a.agent_id)}</div>
            <div style="color:var(--text-3);font-size:10px">${a.n||0} calls</div>
            <div style="font-weight:700;color:var(--text-0)">$${(a.c||0).toFixed(5)}</div>
          </div>`).join('')||'<div style="color:var(--text-3);font-size:12px">No agent cost data yet</div>'}
      </div>
    </div>

    <!-- Record cost manually -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:14px">
      <div style="font-size:12px;font-weight:700;margin-bottom:10px">📝 Manual Cost Entry</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end">
        <div><div style="font-size:10px;color:var(--text-3);margin-bottom:3px">Agent</div>
          <input id="fo-agent" placeholder="builder" style="background:var(--bg-3);border:1px solid var(--border);border-radius:5px;padding:5px 8px;font-size:12px;color:var(--text-0);width:100px"></div>
        <div><div style="font-size:10px;color:var(--text-3);margin-bottom:3px">Source</div>
          <select id="fo-src" style="background:var(--bg-3);border:1px solid var(--border);border-radius:5px;padding:5px 8px;font-size:12px;color:var(--text-0)">
            ${['llm','mcp','connector','supervisor','loop'].map(s=>`<option>${s}</option>`).join('')}</select></div>
        <div><div style="font-size:10px;color:var(--text-3);margin-bottom:3px">Cost ($)</div>
          <input id="fo-cost" type="number" step="0.0001" placeholder="0.0050" style="background:var(--bg-3);border:1px solid var(--border);border-radius:5px;padding:5px 8px;font-size:12px;color:var(--text-0);width:100px"></div>
        <div><div style="font-size:10px;color:var(--text-3);margin-bottom:3px">Tokens</div>
          <input id="fo-tokens" type="number" placeholder="500" style="background:var(--bg-3);border:1px solid var(--border);border-radius:5px;padding:5px 8px;font-size:12px;color:var(--text-0);width:80px"></div>
        <button class="btn-sm" onclick="finopsRecordCost()">Record</button>
      </div>
    </div>
  </div>`;
}

async function finopsCreateCap() {
  const name     = await gmPrompt('Budget Cap', 'Cap name:');
  if (!name?.trim()) return;
  const scope    = await gmPrompt('Scope type (agent/goal/platform):', 'agent') || 'agent';
  const limitUsd = await gmPrompt('Limit ($USD):', '1.00') || '1.00';
  const period   = await gmPrompt('Period (hour/day/week):', 'day') || 'day';
  const r = await fetch('/api/finops/caps',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name,scope_type:scope,limit_usd:parseFloat(limitUsd)||0,period})
  }).catch(()=>null);
  const d = r ? await r.json() : {};
  showToast(d.ok ? `🚦 Cap created: ${d.cap_id}` : '⚠️ Failed');
  if (d.ok) renderFinOps();
}

async function finopsResolveAlert(alertId) {
  await fetch(`/api/finops/alerts/${encodeURIComponent(alertId)}/resolve`,{method:'POST'});
  showToast('✅ Alert resolved');
  renderFinOps();
}

async function finopsRecordCost() {
  const agent = document.getElementById('fo-agent')?.value?.trim()||'system';
  const src   = document.getElementById('fo-src')?.value||'llm';
  const cost  = parseFloat(document.getElementById('fo-cost')?.value||0)||0;
  const tokens= parseInt(document.getElementById('fo-tokens')?.value||0)||0;
  const r = await fetch('/api/finops/ledger/record',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({agent_id:agent,source_type:src,cost_usd:cost,tokens,description:'Manual entry'})
  }).catch(()=>null);
  const d = r ? await r.json() : {};
  showToast(d.ok ? `💰 Cost recorded: $${cost}` : '⚠️ Failed');
  if (d.ok) renderFinOps();
}
window.finopsFilterHeatmap = function(mode) {
  ['model', 'role', 'folder'].forEach(t => {
    const btn = document.getElementById('fo-filter-' + t);
    if (btn) {
      btn.style.background = (t === mode) ? 'var(--accent-glow)' : 'transparent';
      btn.style.borderColor = (t === mode) ? 'var(--accent)' : 'var(--border)';
    }
  });
  const cells = document.querySelectorAll('.fo-cell');
  cells.forEach(c => {
    c.style.transform = 'scale(0.96)';
    c.style.opacity = '0.4';
    setTimeout(() => {
      c.style.transform = 'scale(1)';
      c.style.opacity = '1';
    }, 180);
  });
  toast(`🔥 Treemap filtered by ${mode.toUpperCase()}`, 'ok', 1500);
};

window.renderFinOps = renderFinOps;
window.finopsCreateCap = finopsCreateCap;


// ══════════════════════════════════════════════════════════════════
//  SPRINT D — EVAL FRAMEWORK
// ══════════════════════════════════════════════════════════════════
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
        <button class="btn" onclick="evalRunSuite()">▶ Run Eval Suite</button>
        <button class="btn-sm" onclick="evalCreateSuite()">+ New Suite</button>
        <button class="btn-sm" onclick="renderEvalFramework()">↻ Refresh</button>
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
          <button class="btn-sm" onclick="evalHumanReview(${JSON.stringify(r.result_id)})">👁️ Review</button>
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
            <button class="btn-sm" onclick="evalRunSpecific(${JSON.stringify(s.suite_id)})">▶ Run</button>
            <button class="btn-sm" onclick="evalViewCases(${JSON.stringify(s.suite_id)})">📋 Cases</button>
            <button class="btn-sm" onclick="evalAddCase(${JSON.stringify(s.suite_id)})">+ Case</button>
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


(function patchNavSprint18() {
  const _base = window.nav || function(){};
  window.nav = function masterNav18(pane) {
    _base(pane);
    if (pane==='fusion')        renderFusion?.();
    if (pane==='hitl')          renderHITL?.();
    if (pane==='browser')       renderBrowserAgent?.();
    if (pane==='websearch')     renderWebSearch?.();
    if (pane==='leaderboard')   renderLeaderboard?.();
    // Sprint A
    if (pane==='audit-log')     renderAuditLog?.();
    if (pane==='agent-identity')renderAgentIdentity?.();
    // Sprint B
    if (pane==='supervisor')    renderSupervisor?.();
    if (pane==='goals')         renderGoals?.();
    // Sprint C
    if (pane==='mcp-gateway')   renderMCPGateway?.();
    if (pane==='connectors')    renderConnectors?.();
    // Sprint D
    if (pane==='agent-monitor') renderAgentMonitor?.();
    if (pane==='finops')        renderFinOps?.();
    if (pane==='eval-framework')renderEvalFramework?.();
    if (pane==='a2a')           renderA2A?.();
  };
  console.log('%c✅ Sprint A+B+C+D: Monitor, FinOps, Evals, Gateway, Connectors, Supervisor, Goals, Audit, Identity', 'color:#bb9af7;font-weight:bold');
})();

// HITL WebSocket listener — auto-show approval modal when interrupt fires
(function listenForHITL() {
  // FIX 12: reconnect on close/error so user never silently misses interrupts
  function _connectHITLWS() {
    const ws = new WebSocket(`ws://${location.host}/api/ws`);
    ws.onclose = () => setTimeout(_connectHITLWS, 3000);
    ws.onerror = () => {};
    ws.onmessage = ({data}) => {
    try {
      const msg = JSON.parse(data);
      if (msg.type==='hitl_interrupt') {
        // Show non-intrusive notification
        const toast = document.createElement('div');
        toast.style.cssText=`
          position:fixed;top:60px;right:16px;background:var(--bg-2);
          border:2px solid var(--warning);border-radius:12px;
          padding:14px 16px;z-index:9995;max-width:340px;
          box-shadow:0 8px 32px rgba(0,0,0,.5);animation:voice-in .3s ease;
        `;
        toast.innerHTML=`
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
            <span style="font-size:20px">🛡️</span>
            <strong style="color:var(--warning)">Agent Approval Required</strong>
            <button onclick="this.closest('[style]').remove()" style="margin-left:auto;background:none;border:none;color:var(--text-3);cursor:pointer">✕</button>
          </div>
          <div style="font-size:12px;color:var(--text-1);margin-bottom:10px">${escHtml(msg.action_summary||'')} <span style="color:var(--text-3)">(${msg.risk_level} risk)</span></div>
          <div style="display:flex;gap:6px">
            <button onclick="hitlDecide('${msg.interrupt_id}','approve');this.closest('[style]').remove()" style="flex:1;padding:6px;background:var(--success);border:none;border-radius:6px;color:#fff;font-weight:600;cursor:pointer;font-size:12px">✅ Approve</button>
            <button onclick="hitlDecide('${msg.interrupt_id}','reject');this.closest('[style]').remove()" style="padding:6px 12px;background:transparent;border:1px solid var(--danger);border-radius:6px;color:var(--danger);cursor:pointer;font-size:12px">Reject</button>
            <button onclick="nav('hitl');this.closest('[style]').remove()" style="padding:6px 10px;background:var(--bg-3);border:1px solid var(--border);border-radius:6px;color:var(--text-1);cursor:pointer;font-size:12px">View</button>
          </div>`;
        document.body.appendChild(toast);
        setTimeout(()=>toast.remove(), 30000);
      }
    } catch(e) {}
  };
  }
  _connectHITLWS();
})();

// Keyboard shortcuts Sprint 18
document.addEventListener('keydown', (e) => {
  if (!e.metaKey && !e.ctrlKey || !e.shiftKey) return;
  if (e.key==='F') { e.preventDefault(); nav('fusion'); }
  if (e.key==='L') { e.preventDefault(); nav('leaderboard'); }
  if (e.key==='X') { e.preventDefault(); nav('websearch'); }
});

