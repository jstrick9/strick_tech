// Browser Agent — autonomous Playwright-driven browser control: run
// natural-language tasks, take quick screenshots, and browse session
// history + saved screenshots.
//
// ARCHITECTURE NOTE (rewritten for correctness + best practices, same
// root cause and fix pattern as the Web Search module's rewrite):
// This file is IIFE-wrapped for private scope, but its rendered HTML used
// bare `onclick="baRun()"` / `onclick="baScreenshot()"` / etc. attributes,
// which resolve against the GLOBAL scope, not this closure. Only
// `renderBrowserAgent` and `installPlaywrightChromium` were ever exported
// to `window` — every OTHER control (Run, Screenshot, History,
// Screenshots, the 4 quick-task chips, session View/Delete/Clear buttons
// inside the History modal) threw "ReferenceError: baXxx is not defined"
// on first click. Reproduced live: clicking "Run" with a task typed in
// immediately crashed with an uncaught ReferenceError; the module was
// otherwise fully inert beyond its initial static render.
//
// Rewritten throughout to use `data-*` attributes + real
// `addEventListener` wiring (delegated where content is
// dynamically-regenerated, e.g. the History/Screenshots modals), keeping
// every handler function properly private to the module closure. No new
// globals except the two that must stay on `window` for cross-module use:
// `renderBrowserAgent` (called by the pane registry) and
// `installPlaywrightChromium` (referenced from the render's own output,
// kept as a `window` export since it can also be invoked before the
// wiring pass runs, and other files may reasonably call it directly).
//
// Also fixed along the way:
//   - `showToast(...)` calls replaced with `toast(...)` — this codebase's
//     standing rule is that `showToast` is a legacy compatibility alias
//     for old code only; new/rewritten code must call `toast()` directly.
//   - The screenshot gallery's thumbnail-click handler used raw
//     `window.open(path, '_blank')`, which is forbidden by this app's
//     Tauri rule (silently does nothing in the desktop app's WebKit
//     webview). Replaced with `openExternalLink()`, matching every other
//     "open in new tab" affordance already fixed elsewhere in this app.
(function(nav, toast, escHtml, fetch, document, window) {
'use strict';

const QUICK_TASKS = [
  'Search DuckDuckGo for Python FastAPI tutorials and list top 3',
  'Extract all links from news.ycombinator.com',
  'Find FastAPI documentation homepage',
  'Search for AI agent frameworks 2024',
];

let stepCount = 0;

function $(id) { return document.getElementById(id); }

// ── Render ───────────────────────────────────────────────────────────────
async function renderBrowserAgent() {
  const pane = $('pane-browser');
  if (!pane) return;

  let status = {playwright_available:false, chromium_installed:false, ready:false, mode:'simulation'};
  try {
    const r = await fetch('/api/browser/status');
    if (r.ok) status = await r.json();
  } catch(e) { /* fall back to the simulation-mode default above */ }

  pane.innerHTML = `
  <div style="display:flex;flex-direction:column;height:100%;overflow:hidden">
    <div style="padding:10px 16px;background:var(--bg-1);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;flex-shrink:0;flex-wrap:wrap">
      <span style="font-size:15px;font-weight:700">🌐 Browser Agent</span>
      <span style="font-size:11px;padding:2px 8px;border-radius:5px;${status.ready ? 'background:rgba(61,186,122,.15);color:var(--success)' : 'background:rgba(232,162,55,.15);color:var(--warning)'}">
        ${status.ready ? '✅ Ready' : '⚠️ ' + escHtml(status.mode === 'simulation' ? 'Simulation Mode' : 'Chromium Missing')}
      </span>
      ${!status.ready ? `<span style="font-size:10px;color:var(--text-3);font-family:monospace">${escHtml(status.install_cmd || 'pip install playwright && python -m playwright install chromium')}</span> <button type="button" data-ba-action="install" class="btn-3d btn-primary btn-sm" style="padding:3px 10px;font-size:11px">⚡ Auto-Install Playwright & Chromium</button>` : ''}
      <div style="margin-left:auto;display:flex;gap:6px">
        <button type="button" class="btn-sm" data-ba-action="history">📋 History</button>
        <button type="button" class="btn-sm" data-ba-action="screenshots">🖼 Screenshots</button>
      </div>
    </div>
    <div style="padding:10px 16px;background:var(--bg-2);border-bottom:1px solid var(--border);flex-shrink:0">
      <div style="display:flex;gap:8px;margin-bottom:8px;flex-wrap:wrap">
        <input id="ba-url" value="https://duckduckgo.com" placeholder="Start URL (https://...)"
               style="width:200px;background:var(--bg-3);border:1px solid var(--border);border-radius:7px;color:var(--text-0);font-size:12px;padding:7px 10px">
        <input id="ba-task" placeholder="Task — e.g. Search for Python tutorials and summarize results"
               style="flex:1;min-width:200px;background:var(--bg-3);border:1px solid var(--border);border-radius:7px;color:var(--text-0);font-size:13px;padding:7px 10px">
        <input id="ba-steps" type="number" min="1" max="20" value="10"
               style="width:55px;background:var(--bg-3);border:1px solid var(--border);border-radius:7px;color:var(--text-0);font-size:12px;padding:7px 8px" title="Max steps">
        <button type="button" class="btn" data-ba-action="run" id="ba-run-btn">▶ Run</button>
        <label title="Simulation mode does not open a browser or fetch anything — an AI narrates the steps a browser agent would take."
               style="display:flex;align-items:center;gap:5px;font-size:11px;color:var(--text-2);white-space:nowrap">
          <input type="checkbox" id="ba-simulate"${status.ready ? '' : ' checked'}> Simulate
        </label>
        <button type="button" class="btn-sm" data-ba-action="screenshot" title="Quick screenshot of start URL">📸</button>
      </div>
      <div style="display:flex;gap:5px;flex-wrap:wrap">
        ${QUICK_TASKS.map((t, i) => `<button type="button" class="btn-sm" data-ba-quick-task="${i}" style="font-size:10px">${escHtml(t.slice(0,42))}…</button>`).join('')}
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

  wireEvents(pane);
}
window.renderBrowserAgent = renderBrowserAgent;

// ── Event wiring (delegated; safe to call once per render since the pane
// is fully replaced via innerHTML each time renderBrowserAgent() runs) ──
function wireEvents(pane) {
  pane.querySelectorAll('[data-ba-action]').forEach(btn => {
    btn.addEventListener('click', () => runAction(btn.dataset.baAction));
  });
  pane.querySelectorAll('[data-ba-quick-task]').forEach(btn => {
    btn.addEventListener('click', () => {
      const inp = $('ba-task');
      if (inp) inp.value = QUICK_TASKS[Number(btn.dataset.baQuickTask)] || '';
    });
  });
  const taskInp = $('ba-task');
  if (taskInp) taskInp.addEventListener('keydown', (e) => { if (e.key === 'Enter') runTask(); });
}

function runAction(action) {
  const handlers = {
    'install': installPlaywrightChromium,
    'run': runTask,
    'screenshot': takeScreenshot,
    'history': loadHistory,
    'screenshots': listScreenshots,
  };
  const fn = handlers[action];
  if (fn) fn();
}

// ── Auto-install (Playwright + Chromium via SSE progress stream) ─────────
async function installPlaywrightChromium() {
  toast('⏳ Initiating live SSE Playwright & Chromium setup...', 'ok', 3000);
  const pane = $('pane-browser');
  let progCard = $('browser-setup-progress-card');
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
          const bar = $('browser-prog-bar');
          const msg = $('browser-prog-msg');
          const pct = $('browser-prog-pct');
          const det = $('browser-prog-detail');
          if (bar) bar.style.width = (d.progress || 0) + '%';
          if (msg) msg.textContent = d.message || 'Installing...';
          if (pct) pct.textContent = (d.progress || 0) + '%';
          if (det) det.textContent = `[SSE Browser Setup Stream] ${d.message || ''}`;
          if (d.done) {
            es.close();
            toast('✅ Playwright & Chromium installed!', 'ok', 3000);
            setTimeout(() => {
              if (progCard) progCard.style.display = 'none';
              renderBrowserAgent();
            }, 2000);
          }
        } catch(err) { /* skip malformed SSE frame */ }
      };
      es.onerror = () => { es.close(); };
    } else {
      setTimeout(renderBrowserAgent, 5000);
    }
  } catch(e) {
    window.gmAlert('Setup error', `Run in terminal:\n\npip install playwright && python -m playwright install chromium`);
  }
}
window.installPlaywrightChromium = installPlaywrightChromium;

// ── Run task (streamed via SSE) ───────────────────────────────────────────
async function runTask() {
  const task  = $('ba-task')?.value?.trim();
  const url   = $('ba-url')?.value?.trim() || 'https://duckduckgo.com';
  const steps = Math.max(1, Math.min(20, parseInt($('ba-steps')?.value || '10', 10)));
  if (!task) { window.gmAlert('Enter a task for the browser agent'); return; }

  const btn       = $('ba-run-btn');
  const stepsList = $('ba-steps-list');
  const result    = $('ba-result');
  const sidEl     = $('ba-session-id');
  const cntEl     = $('ba-step-count');

  if (btn) { btn.disabled = true; btn.textContent = '⏳ Running…'; }
  if (stepsList) stepsList.innerHTML = '<div style="color:var(--text-3);font-size:11px;padding:10px">Starting…</div>';
  if (result)    result.innerHTML    = '<div style="color:var(--text-2)">🌐 Agent running…</div>';
  if (sidEl)     sidEl.textContent   = '';
  if (cntEl)     cntEl.textContent   = '';
  stepCount = 0;

  try {
    const resp = await fetch('/api/browser/task', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({task, start_url:url, max_steps:steps, simulate: !!$('ba-simulate')?.checked})
    });
    if (!resp.ok) {
      // The backend now returns a real status code with an explanatory body
      // (503 when there's no browser and simulation wasn't requested, 403 for
      // a blocked start_url, 400 for a malformed one). Show the reason instead
      // of a bare status number.
      let detail = '';
      try { detail = (await resp.json()).error || ''; } catch(e) { /* non-JSON error body */ }
      if (result) result.innerHTML = `<span style="color:var(--danger)">❌ ${escHtml(detail || `Request failed (HTTP ${resp.status})`)}</span>`;
      if (btn) { btn.disabled = false; btn.textContent = '▶ Run'; }
      return;
    }
    if (!resp.body) throw new Error('No response body');

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
            stepCount++;
            const s   = d.step || {};
            const sim = d.simulated ? ' simulated' : '';
            const err = (s.status === 'error') ? ' error-step' : '';
            const el  = document.createElement('div');
            el.className = `ba-step${sim}${err}`;
            const desc = s.description || s.reason ||
              (s.url && s.url !== url ? s.url : '') ||
              (s.selector ? `sel: ${s.selector}` : '') ||
              (s.result && typeof s.result === 'object' ?
                (s.result.text || s.result.error || JSON.stringify(s.result)).slice(0,80) : '') ||
              '';
            const screenPath = s.result?.screenshot_path;
            el.innerHTML = `
              <span class="ba-num">#${d.step_no||stepCount}</span>
              <span class="ba-act">${escHtml(s.action||'?')}</span>
              <span class="ba-desc">${escHtml(desc.slice(0,100))}${screenPath?`<br><a href="${safeUrl(screenPath)}" target="_blank" rel="noopener" style="color:var(--accent);font-size:10px">📷 screenshot</a>`:''}</span>`;
            stepsList?.appendChild(el);
            if (stepsList) stepsList.scrollTop = stepsList.scrollHeight;
            if (cntEl) cntEl.textContent = stepCount + ' steps';
          } else if (d.type === 'done') {
            const text = d.result_preview || d.result || 'Task completed.';
            if (result) result.textContent = text;
            if (cntEl) cntEl.textContent = `${d.steps||stepCount} steps · ✅ done`;
            if (d.simulated) {
              const note = document.createElement('div');
              note.style.cssText = 'margin-top:12px;font-size:11px;color:var(--text-3);border-top:1px solid var(--border);padding-top:8px';
              note.textContent = '⚠️ Simulated — no browser ran and nothing was fetched. Install Chromium for real browsing.';
              result?.appendChild(note);
            }
          } else if (d.type === 'error') {
            if (result) result.innerHTML = `<span style="color:var(--danger)">❌ Error: ${escHtml(d.error||'Unknown error')}</span>`;
            if (cntEl) cntEl.textContent = '❌ error';
          }
        } catch(e) { /* skip malformed SSE frame */ }
      }
    }
  } catch(ex) {
    if (result) result.innerHTML = `<span style="color:var(--danger)">❌ ${escHtml(ex?.message||String(ex))}</span>`;
  }

  if (btn) { btn.disabled = false; btn.textContent = '▶ Run'; }
}

// ── Quick screenshot ───────────────────────────────────────────────────────
async function takeScreenshot() {
  const url = $('ba-url')?.value?.trim();
  if (!url) { window.gmAlert('Enter a URL in the Start URL field first'); return; }
  toast('📸 Taking screenshot…', 'ok');
  try {
    const r = await fetch('/api/browser/screenshot', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({url})
    });
    if (!r.ok) { window.gmAlert('Screenshot request failed: HTTP '+r.status); return; }
    const d = await r.json();
    if (d.ok && d.b64) {
      const overlay = document.createElement('div');
      overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:9999;display:flex;flex-direction:column;align-items:center;justify-content:center;cursor:zoom-out;gap:10px';
      overlay.innerHTML = `
        <div style="font-size:12px;color:#fff;opacity:.7">${escHtml(d.title||url)} · ${((d.size||0)/1024).toFixed(1)}KB</div>
        <img src="data:image/png;base64,${d.b64}" style="max-width:90vw;max-height:85vh;border-radius:8px;box-shadow:0 8px 40px rgba(0,0,0,.6)">
        <div style="font-size:11px;color:#fff;opacity:.5">Click anywhere to close</div>`;
      overlay.addEventListener('click', () => overlay.remove());
      document.body.appendChild(overlay);
      toast('✅ Screenshot taken', 'ok');
    } else {
      window.gmAlert(d.error || 'Screenshot failed — install Playwright first:\npip install playwright && python -m playwright install chromium');
    }
  } catch(ex) {
    window.gmAlert('Screenshot error: ' + (ex?.message||String(ex)));
  }
}

// ── Session history ─────────────────────────────────────────────────────
async function loadHistory() {
  try {
    const r = await fetch('/api/browser/sessions?limit=20');
    if (!r.ok) { toast('Failed to load history: HTTP '+r.status, 'err'); return; }
    const d = await r.json();
    const sessions = d.sessions || [];
    if (!sessions.length) { window.gmAlert('No browser sessions yet. Run a task first!'); return; }

    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    overlay.innerHTML = `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:16px;max-width:620px;width:100%;max-height:80vh;overflow-y:auto;padding:20px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
          <h3 style="margin:0;color:var(--text-0)">📋 Browser Session History (${sessions.length})</h3>
          <button type="button" data-ba-modal-close style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
        </div>
        ${sessions.map((s, idx) => `
          <div style="border:1px solid var(--border);border-radius:8px;padding:10px;margin-bottom:8px;font-size:12px">
            <div style="display:flex;justify-content:space-between;margin-bottom:4px">
              <span style="font-family:monospace;color:var(--accent)">${escHtml(s.id)}</span>
              <span style="padding:1px 6px;border-radius:4px;font-size:10px;${s.status==='done'?'background:rgba(61,186,122,.15);color:var(--success)':s.status==='error'?'background:rgba(232,82,82,.1);color:var(--danger)':'background:var(--bg-3);color:var(--text-3)'}">${escHtml(s.status)}</span>
            </div>
            <div style="color:var(--text-1);margin-bottom:2px">${escHtml((s.task||'').slice(0,80))}</div>
            <div style="color:var(--text-3)">${escHtml((s.url||'').slice(0,60))} · ${escHtml((s.created_at||'').slice(0,16))}</div>
            ${s.error?`<div style="color:var(--danger);font-size:10px;margin-top:2px">⚠️ ${escHtml(s.error.slice(0,80))}</div>`:''}
            <div style="margin-top:6px;display:flex;gap:4px">
              <button type="button" class="btn-sm" data-ba-view-idx="${idx}" style="font-size:10px">View</button>
              <button type="button" class="btn-sm" data-ba-delete-idx="${idx}" style="font-size:10px;color:var(--danger);border-color:var(--danger)">Delete</button>
            </div>
          </div>`).join('')}
        <button type="button" class="btn-sm" data-ba-clear-all style="color:var(--danger);margin-top:4px">🗑 Clear All Sessions</button>
      </div>`;

    overlay.addEventListener('click', (e) => {
      if (e.target === overlay || e.target.closest('[data-ba-modal-close]')) { overlay.remove(); return; }
      const viewBtn = e.target.closest('[data-ba-view-idx]');
      if (viewBtn) { overlay.remove(); viewSession(sessions[Number(viewBtn.dataset.baViewIdx)]?.id); return; }
      const delBtn = e.target.closest('[data-ba-delete-idx]');
      if (delBtn) { overlay.remove(); deleteSession(sessions[Number(delBtn.dataset.baDeleteIdx)]?.id); return; }
      if (e.target.closest('[data-ba-clear-all]')) { overlay.remove(); clearHistory(); }
    });
    document.body.appendChild(overlay);
  } catch(ex) {
    window.gmAlert('History load error: '+ex?.message);
  }
}

async function viewSession(sessionId) {
  if (!sessionId) return;
  try {
    const r = await fetch(`/api/browser/sessions/${encodeURIComponent(sessionId)}`);
    if (!r.ok) { window.gmAlert('Session not found'); return; }
    const d = await r.json();
    if (d.ok === false) { window.gmAlert('Session not found: '+sessionId); return; }
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
          <button type="button" data-ba-modal-close style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
        </div>
        <div style="font-size:12px;color:var(--text-2);margin-bottom:8px">Task: ${escHtml(d.task||'')}</div>
        <div style="font-size:11px;color:var(--text-3);margin-bottom:12px">URL: ${escHtml(d.url||'')} · Status: ${escHtml(d.status||'')} · ${d.step_count||0} steps</div>
        <div style="background:var(--bg-3);border-radius:8px;overflow:hidden;margin-bottom:12px">${steps||'<div style="padding:12px;color:var(--text-3)">No steps recorded</div>'}</div>
        ${d.result?`<div style="font-size:12px;color:var(--text-1);white-space:pre-wrap;max-height:200px;overflow-y:auto;background:var(--bg-3);padding:10px;border-radius:8px">${escHtml(d.result.slice(0,500))}</div>`:''}
      </div>`;
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay || e.target.closest('[data-ba-modal-close]')) overlay.remove();
    });
    document.body.appendChild(overlay);
  } catch(ex) {
    window.gmAlert('Error: '+ex?.message);
  }
}

async function deleteSession(sessionId) {
  if (!sessionId) return;
  const ok = await window.gmDanger('Delete Session', `Delete browser session "${sessionId}" and its screenshots?`);
  if (!ok) return;
  try {
    const r = await fetch(`/api/browser/sessions/${encodeURIComponent(sessionId)}`, {method:'DELETE'});
    if (!r.ok) { toast('Delete failed: HTTP '+r.status, 'err'); return; }
    toast('🗑 Session deleted', 'ok');
  } catch(ex) {
    toast('Delete error: '+ex?.message, 'err');
  }
}

async function clearHistory() {
  const ok = await window.gmDanger('Clear All Sessions', 'Delete ALL browser session history?');
  if (!ok) return;
  try {
    const r = await fetch('/api/browser/sessions', {method:'DELETE'});
    if (!r.ok) { toast('Clear failed: HTTP '+r.status, 'err'); return; }
    const d = await r.json();
    toast(`🗑 Cleared ${d.deleted||0} sessions`, 'ok');
  } catch(ex) {
    toast('Clear error: '+ex?.message, 'err');
  }
}

// ── Screenshot gallery ─────────────────────────────────────────────────────
async function listScreenshots() {
  try {
    const r = await fetch('/api/browser/screenshots?limit=20');
    if (!r.ok) { toast('Failed: HTTP '+r.status, 'err'); return; }
    const d = await r.json();
    const screenshots = d.screenshots || [];
    if (!screenshots.length) { window.gmAlert('No screenshots yet. Take a screenshot or run a task first.'); return; }

    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    overlay.innerHTML = `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:16px;max-width:640px;width:100%;max-height:80vh;overflow-y:auto;padding:20px">
        <div style="display:flex;justify-content:space-between;margin-bottom:14px">
          <h3 style="margin:0;color:var(--text-0)">🖼 Screenshots (${screenshots.length})</h3>
          <button type="button" data-ba-modal-close style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px">
          ${screenshots.map((s, idx) => `
            <div data-ba-open-shot-idx="${idx}" style="border:1px solid var(--border);border-radius:8px;overflow:hidden;cursor:pointer">
              <img src="${escHtml(s.path)}" style="width:100%;height:100px;object-fit:cover" loading="lazy" data-hide-on-error="1">
              <div style="padding:5px 7px;font-size:10px;color:var(--text-3)">${escHtml((s.filename||'').slice(0,30))} · ${((s.size||0)/1024).toFixed(0)}KB</div>
            </div>`).join('')}
        </div>
      </div>`;

    overlay.addEventListener('click', (e) => {
      if (e.target === overlay || e.target.closest('[data-ba-modal-close]')) { overlay.remove(); return; }
      const shot = e.target.closest('[data-ba-open-shot-idx]');
      if (shot) {
        const path = screenshots[Number(shot.dataset.baOpenShotIdx)]?.path;
        // BUG FIX: previously used raw window.open(path,'_blank'), which
        // is forbidden by this app's Tauri rule (silently does nothing in
        // the desktop app's WebKit webview). openExternalLink() tries the
        // Tauri shell API first, then a backend open-url fallback, and
        // only uses window.open() itself when running in a plain browser
        // tab where it's actually safe.
        if (path && typeof window.openExternalLink === 'function') window.openExternalLink(location.origin + path);
      }
    });
    document.body.appendChild(overlay);
  } catch(ex) {
    window.gmAlert('Error: '+ex?.message);
  }
}

})(window.nav, window.toast, window.escHtml, window.fetch.bind(window), document, window);
