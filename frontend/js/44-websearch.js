// Web Search — Extracted from 06-sprint-features.js
(function(S, nav, toast, escHtml, fetch, document) {
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
        } catch(e) { console.warn('SSE parse error', e); }
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


window.renderWebSearch = renderWebSearch;
})(S, nav, toast, escHtml, fetch, document);
