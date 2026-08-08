
;/* 44-websearch.js */
(function(nav, toast, escHtml, fetch, document) {
'use strict';
const state = {
tab: 'grounded',
history: [],
};
const TABS = ['grounded', 'search', 'research', 'history'];
const KIND_ICONS = { search: '🔍', grounded: '🤖', grounded_stream: '⚡', research: '📚' };
function $(id) { return document.getElementById(id); }
async function renderWebSearch() {
const pane = $('pane-websearch');
if (!pane) return;
pane.innerHTML = `
  <div style="padding:20px;max-width:900px;margin:0 auto">
    <div class="section-head">
      <div>
        <h2>🔎 Web Search</h2>
        <p>Like Perplexity — ground AI answers with live web citations. Free DuckDuckGo search, no API key needed.</p>
      </div>
      <button type="button" class="btn-sm" data-ws-action="show-history">🕑 History</button>
    </div>

    <!-- Search tabs -->
    <div style="display:flex;gap:8px;margin-bottom:16px">
      <button type="button" class="btn" id="ws-tab-grounded" data-ws-tab="grounded">🤖 Grounded AI</button>
      <button type="button" class="btn-sm" id="ws-tab-search" data-ws-tab="search">🔍 Raw Search</button>
      <button type="button" class="btn-sm" id="ws-tab-research" data-ws-tab="research">📚 Deep Research</button>
      <button type="button" class="btn-sm" id="ws-tab-history" data-ws-tab="history">🕑 History</button>
    </div>

    <!-- Grounded AI (default) -->
    <div id="ws-pane-grounded">
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;overflow:hidden;margin-bottom:16px">
        <div style="display:flex;gap:8px;padding:10px 14px;align-items:center">
          <input id="ws-grounded-q" aria-label="Ask a grounded question" list="ws-grounded-suggest" placeholder="Ask anything — AI will search the web first then answer with citations…" style="flex:1;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:13px;padding:9px 12px">
          <datalist id="ws-grounded-suggest"></datalist>
          <button type="button" class="btn" data-ws-action="grounded">Ask</button>
          <button type="button" class="btn-sm" data-ws-action="grounded-stream">⚡ Stream</button>
        </div>
      </div>
      <div id="ws-grounded-result">
        <div class="pane-empty-intro">
          <div class="pane-empty-intro__icon" aria-hidden="true">🌐</div>
          <div class="pane-empty-intro__title">Answers grounded in live web results</div>
          <div class="pane-empty-intro__body">Unlike a normal chat reply, this searches
            the web first and then answers, citing every source it used — so you can
            check where each claim came from.</div>
          <div class="pane-empty-intro__hint">Good for anything recent: prices, releases,
            documentation, current events.</div>
        </div>
      </div>
    </div>

    <!-- Raw search -->
    <div id="ws-pane-search" style="display:none">
      <div style="display:flex;gap:8px;margin-bottom:14px">
        <input id="ws-search-q" aria-label="Search the web" list="ws-search-suggest" placeholder="Search query…" style="flex:1;background:var(--bg-2);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:13px;padding:9px 12px">
        <datalist id="ws-search-suggest"></datalist>
        <button type="button" class="btn" data-ws-action="search">Search</button>
      </div>
      <div id="ws-search-result"></div>
    </div>

    <!-- Deep research -->
    <div id="ws-pane-research" style="display:none">
      <div style="font-size:12px;color:var(--text-2);margin-bottom:10px">Multi-query deep research: generates 4 search queries, synthesizes into a comprehensive report with citations</div>
      <div style="display:flex;gap:8px;margin-bottom:14px">
        <input id="ws-research-q" aria-label="Enter research topic" list="ws-research-suggest" placeholder="Research topic (e.g. 'FastAPI vs Django for production APIs')" style="flex:1;background:var(--bg-2);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:13px;padding:9px 12px">
        <datalist id="ws-research-suggest"></datalist>
        <button type="button" class="btn" data-ws-action="research">📚 Research</button>
      </div>
      <div id="ws-research-status" style="font-size:12px;color:var(--text-2);margin-bottom:8px"></div>
      <div id="ws-research-result" style="font-size:13px;color:var(--text-1);line-height:1.7;white-space:pre-wrap"></div>
      <div id="ws-research-citations"></div>
    </div>

    <!-- History -->
    <div id="ws-pane-history" style="display:none">
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:14px">
        <span style="font-size:13px;color:var(--text-1);flex:1">Recent searches</span>
        <button type="button" class="btn-sm" data-ws-action="refresh-history">🔄 Refresh</button>
        <button type="button" class="btn-sm" style="color:var(--danger)" data-ws-action="clear-history">🗑️ Clear All</button>
      </div>
      <div id="ws-history-list"><div style="color:var(--text-3);font-size:13px">Loading…</div></div>
    </div>
  </div>`;
wireEvents(pane);
setTab('grounded');
}
function wireEvents(pane) {
pane.querySelectorAll('[data-ws-tab]').forEach(btn => {
btn.addEventListener('click', () => setTab(btn.dataset.wsTab));
});
pane.querySelectorAll('[data-ws-action]').forEach(btn => {
btn.addEventListener('click', () => runAction(btn.dataset.wsAction));
});
bindInput('ws-grounded-q', 'ws-grounded-suggest', () => runAction('grounded'));
bindInput('ws-search-q', 'ws-search-suggest', () => runAction('search'));
bindInput('ws-research-q', 'ws-research-suggest', () => runAction('research'));
const historyList = $('ws-history-list');
if (historyList) {
historyList.addEventListener('click', (e) => {
const delBtn = e.target.closest('[data-ws-delete-idx]');
if (delBtn) {
e.stopPropagation();
const item = state.history[Number(delBtn.dataset.wsDeleteIdx)];
if (item) deleteHistoryEntry(item.id);
return;
}
const row = e.target.closest('[data-ws-replay-idx]');
if (row) {
const item = state.history[Number(row.dataset.wsReplayIdx)];
if (item) replaySearch(item.query, item.kind);
}
});
}
}
function bindInput(inputId, datalistId, onSubmit) {
const inp = $(inputId);
if (!inp) return;
inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') onSubmit(); });
inp.addEventListener('input', () => autocomplete(inputId, datalistId));
}
function runAction(action) {
const handlers = {
'grounded': grounded,
'grounded-stream': groundedStream,
'search': search,
'research': research,
'show-history': () => setTab('history'),
'refresh-history': loadHistory,
'clear-history': clearHistory,
};
const fn = handlers[action];
if (fn) fn();
}
function setTab(tab) {
state.tab = tab;
TABS.forEach(t => {
const p = $(`ws-pane-${t}`);
const b = $(`ws-tab-${t}`);
if (p) p.style.display = t === tab ? 'block' : 'none';
if (b) {
b.style.background = t === tab ? 'var(--accent)' : '';
b.style.color      = t === tab ? 'var(--on-accent, #fff)' : '';
}
});
if (tab === 'history') loadHistory();
}
async function grounded() {
const q = $('ws-grounded-q')?.value?.trim();
if (!q) return;
const el = $('ws-grounded-result');
if (el) el.innerHTML = '<div style="color:var(--text-2)">🔍 Searching &amp; thinking…</div>';
try {
const r = await fetch('/api/websearch/grounded-completion', {
method: 'POST', headers: {'Content-Type':'application/json'},
body: JSON.stringify({prompt: q, num_results: 5})
});
if (!r.ok) throw new Error(`HTTP ${r.status}`);
const d = await r.json();
if (!d.ok) throw new Error(d.error || 'Search failed');
if (el) el.innerHTML = `
      <div class="u-534c2d64">
        <div style="font-size:13px;color:var(--text-0);line-height:1.7;white-space:pre-wrap;margin-bottom:14px">${escHtml(d.answer||'')}</div>
        <div style="border-top:1px solid var(--border);padding-top:10px">
          <div style="font-size:11px;font-weight:700;color:var(--text-3);margin-bottom:6px">SOURCES (${d.sources||0})</div>
          ${(d.citations||[]).map(c=>`
            <a href="${escHtml(safeUrl(c.url))}" target="_blank" rel="noopener" style="display:flex;align-items:center;gap:6px;padding:4px 0;text-decoration:none">
              <span style="font-size:10px;background:var(--bg-3);padding:1px 5px;border-radius:3px;color:var(--text-3)">[${escHtml(String(c.num))}]</span>
              <span style="font-size:12px;color:var(--accent-text)">${escHtml(c.title||c.url||'')}</span>
            </a>`).join('')}
        </div>
      </div>`;
} catch(ex) {
renderRetryError(el, ex, 'grounded');
}
}
async function groundedStream() {
const q = $('ws-grounded-q')?.value?.trim();
if (!q) return;
const el = $('ws-grounded-result');
if (el) el.innerHTML = '<div class="u-534c2d64"><div style="font-size:13px;color:var(--text-1);line-height:1.7;white-space:pre-wrap" id="ws-stream-txt">🔍 Searching…</div></div>';
try {
const resp = await fetch('/api/websearch/grounded-completion/stream', {
method: 'POST', headers: {'Content-Type':'application/json'},
body: JSON.stringify({prompt: q})
});
if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
if (!resp.body) throw new Error('No response body');
await consumeSse(resp.body, (d) => {
const t = $('ws-stream-txt');
if (d.type === 'search_done') {
if (t) t.textContent = `✅ Found ${d.results} sources — generating answer…\n`;
} else if (d.type === 'chunk') {
if (t) t.textContent = (t.dataset.wsBuf = (t.dataset.wsBuf || '') + (d.text || ''));
} else if (d.type === 'done' && d.citations?.length) {
if (t) t.insertAdjacentHTML('afterend', `
          <div style="border-top:1px solid var(--border);padding-top:10px;margin-top:10px">
            <div style="font-size:11px;font-weight:700;color:var(--text-3);margin-bottom:6px">SOURCES</div>
            ${d.citations.map(c=>`<a href="${escHtml(safeUrl(c.url))}" target="_blank" rel="noopener" style="display:block;font-size:12px;color:var(--accent-text);padding:2px 0">[${escHtml(String(c.num))}] ${escHtml(c.title||c.url||'')}</a>`).join('')}
          </div>`);
}
});
} catch(ex) {
renderRetryError(el, ex, 'grounded-stream');
}
}
async function search() {
const q = $('ws-search-q')?.value?.trim();
if (!q) return;
const el = $('ws-search-result');
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
          <a href="${escHtml(safeUrl(res.url))}" target="_blank" rel="noopener" style="font-weight:600;font-size:13px;color:var(--accent-text);text-decoration:none">${escHtml(res.title||'')}</a>
        </div>
        <div style="font-size:12px;color:var(--text-2);line-height:1.5">${escHtml(res.snippet||'')}</div>
        <div style="font-size:10px;color:var(--text-3);margin-top:4px">${escHtml(res.url||'')}</div>
      </div>`).join('') || '<div style="color:var(--text-3);padding:20px;text-align:center">No results found</div>';
} catch(ex) {
renderRetryError(el, ex, 'search');
}
}
async function research() {
const q = $('ws-research-q')?.value?.trim();
if (!q) return;
const statusEl = $('ws-research-status');
const el       = $('ws-research-result');
const citEl    = $('ws-research-citations');
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
let txt = '';
await consumeSse(resp.body, (d) => {
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
                <a href="${escHtml(safeUrl(c.url))}" target="_blank" rel="noopener" style="display:flex;align-items:center;gap:6px;padding:3px 0;text-decoration:none">
                  <span style="font-size:10px;background:var(--bg-3);padding:1px 5px;border-radius:3px;color:var(--text-3);flex-shrink:0">[${escHtml(String(c.num))}]</span>
                  <span style="font-size:12px;color:var(--accent-text)">${escHtml(c.title||c.url||'')}</span>
                </a>`).join('')}
            </div>`;
}
}
});
} catch(ex) {
if (statusEl) statusEl.innerHTML = `<span style="color:var(--danger)">${escHtml(ex?.message||String(ex))}</span>`;
if (el) { el.innerHTML = ''; el.appendChild(buildRetryButton('research')); }
}
}
async function loadHistory() {
const el = $('ws-history-list');
if (!el) return;
el.innerHTML = '<div style="color:var(--text-3);font-size:13px">Loading…</div>';
try {
const r = await fetch('/api/websearch/history?limit=50');
if (!r.ok) throw new Error(`HTTP ${r.status}`);
const d = await r.json();
state.history = d.items || [];
if (!state.history.length) {
el.innerHTML = '<div style="color:var(--text-3);font-size:13px;padding:20px;text-align:center">No search history yet</div>';
return;
}
el.innerHTML = state.history.map((item, idx) => `
      <div data-ws-replay-idx="${idx}" style="display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:8px;background:var(--bg-2);margin-bottom:6px;cursor:pointer">
        <span class="u-1444c6ea">${KIND_ICONS[item.kind] || '🔎'}</span>
        <span style="flex:1;font-size:13px;color:var(--text-0)">${escHtml(item.query)}</span>
        <span style="font-size:11px;color:var(--text-3)">${item.results} results</span>
        <button type="button" class="btn-sm" data-ws-delete-idx="${idx}" style="font-size:10px;padding:2px 6px;color:var(--danger)">✕</button>
      </div>`).join('');
} catch(ex) {
el.innerHTML = `<div style="color:var(--danger);font-size:13px">${escHtml(ex?.message||String(ex))}</div>`;
el.appendChild(buildRetryButton('refresh-history'));
}
}
function replaySearch(query, kind) {
if (kind === 'search') {
setTab('search');
const inp = $('ws-search-q');
if (inp) { inp.value = query; search(); }
} else if (kind === 'research') {
setTab('research');
const inp = $('ws-research-q');
if (inp) { inp.value = query; research(); }
} else {
setTab('grounded');
const inp = $('ws-grounded-q');
if (inp) { inp.value = query; grounded(); }
}
}
async function deleteHistoryEntry(id) {
if (typeof gmDanger === 'function') {
const ok = await gmDanger('Delete search',
'Remove this search from your history?',
'Delete');
if (!ok) return;
}
try {
const r = await fetch(`/api/websearch/history/${encodeURIComponent(id)}`, {method:'DELETE'});
if (!r.ok) throw new Error(`HTTP ${r.status}`);
loadHistory();
} catch(ex) { toast(ex?.message||String(ex), 'err'); }
}
async function clearHistory() {
const ok = await window.gmDanger('Clear all search history?', 'This cannot be undone.', 'Clear History');
if (!ok) return;
try {
const r = await fetch('/api/websearch/history', {method:'DELETE'});
if (!r.ok) throw new Error(`HTTP ${r.status}`);
toast('History cleared', 'ok');
loadHistory();
} catch(ex) { toast(ex?.message||String(ex), 'err'); }
}
async function autocomplete(inputId, datalistId) {
const inp = $(inputId);
if (!inp) return;
const q = inp.value.trim();
if (!q || q.length < 2) return;
try {
const r = await fetch(`/api/websearch/suggest?q=${encodeURIComponent(q)}&limit=8`);
if (!r.ok) return;
const d = await r.json();
const dl = $(datalistId);
if (dl) dl.innerHTML = (d.suggestions||[]).map(s=>`<option value="${escHtml(s)}">`).join('');
} catch(e) {  }
}
async function consumeSse(body, onEvent) {
const reader = body.getReader();
const dec = new TextDecoder();
let buf = '';
while (true) {
const {done, value} = await reader.read();
if (done) break;
buf += dec.decode(value, {stream: true});
const parts = buf.split('\n\n');
buf = parts.pop() || '';
for (const part of parts) {
if (!part.startsWith('data:')) continue;
try { onEvent(JSON.parse(part.slice(5).trim())); }
catch(e) {  }
}
}
}
function buildRetryButton(action) {
const btn = document.createElement('button');
btn.type = 'button';
btn.className = 'btn-sm';
btn.style.marginTop = '8px';
btn.textContent = 'Retry';
btn.dataset.wsAction = action;
btn.addEventListener('click', () => runAction(action));
return btn;
}
function renderRetryError(el, ex, action) {
if (!el) return;
el.innerHTML = '';
const box = document.createElement('div');
box.style.color = 'var(--danger)';
box.style.padding = '12px';
box.textContent = ex?.message || String(ex);
box.appendChild(document.createElement('br'));
box.appendChild(buildRetryButton(action));
el.appendChild(box);
}
window.renderWebSearch = renderWebSearch;
})(window.nav, window.toast, window.escHtml, window.fetch.bind(window), document);
