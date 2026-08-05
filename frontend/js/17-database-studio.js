// Agentic OS — Database Studio
// Extracted from 01-app-core.js for modularity
// ── Database Studio ────────────────────────────────────────────────
var dbActiveTable = '', dbActiveTab = 'sqlite';

async function renderDBStudio() {
  const pane = document.getElementById('pane-dbstudio');
  pane.innerHTML = `<div class="section-head">
    <div><h2>🗄️ Database Studio</h2><p>Visual table browser, SQL editor, and Supabase connect</p></div>
    <div style="display:flex;gap:8px">
      <button data-act-click="dbSetTab('sqlite')" class="btn ${dbActiveTab==='sqlite'?'btn-primary':'btn-ghost'} btn-sm" id="db-tab-sqlite">📦 SQLite (local)</button>
      <button data-act-click="dbSetTab('supabase')" class="btn ${dbActiveTab==='supabase'?'btn-primary':'btn-ghost'} btn-sm" id="db-tab-supabase">☁️ Supabase</button>
      <button data-act-click="dbSetTab('sql')" class="btn ${dbActiveTab==='sql'?'btn-primary':'btn-ghost'} btn-sm" id="db-tab-sql">💻 SQL Editor</button>
      <button data-act-click="dbSetTab('designer')" class="btn ${dbActiveTab==='designer'?'btn-primary':'btn-ghost'} btn-sm" id="db-tab-designer">🏗️ Schema Designer</button>
      <button data-act-click="dbSetTab('audit')" class="btn ${dbActiveTab==='audit'?'btn-primary':'btn-ghost'} btn-sm" id="db-tab-audit">📜 Audit Trail</button>
    </div>
  </div>
  <div id="db-body"></div>`;
  dbSetTab(dbActiveTab);
}

async function dbSetTab(tab) {
  dbActiveTab = tab;
  ['sqlite','supabase','sql','designer','audit'].forEach(t => {
    const btn = document.getElementById('db-tab-' + t);
    if (btn) { btn.className = btn.className.replace('btn-primary','btn-ghost'); }
    if (t === tab && btn) { btn.className = btn.className.replace('btn-ghost','btn-primary'); }
  });
  const el = document.getElementById('db-body');
  if (!el) return;

  if (tab === 'sqlite') await renderSQLiteTab(el);
  else if (tab === 'supabase') await renderSupabaseTab(el);
  else if (tab === 'sql') renderSQLEditorTab(el);
  else if (tab === 'designer') renderSchemaDesignerTab(el);
  else if (tab === 'audit') await renderDBAuditTab(el);
}

async function renderSQLiteTab(el) {
  let tables = [];
  try {
    const r = await fetch('/api/db/sqlite/tables');
    if (!r.ok) throw new Error('Tables API error ' + r.status);
    const data = await r.json();
    tables = Array.isArray(data) ? data : (Array.isArray(data?.tables) ? data.tables : []);
  } catch(ex) {
    el.innerHTML = `<div style="color:var(--red);padding:16px">Error loading tables: ${escHtml(ex.message)}</div>`;
    return;
  }
  el.innerHTML = `<div style="display:grid;grid-template-columns:200px 1fr;gap:16px;height:calc(100vh - 200px)">
    <!-- Table list -->
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:10px;overflow-y:auto" id="db-table-list">
      <div style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Tables (${tables.length})</div>
      ${tables.map((t, idx) => `
        <div data-table-idx="${idx}" title="${t.restricted ? 'Protected — holds credential material' : (t.sensitive_columns||[]).length ? 'Contains masked columns: ' + escHtml((t.sensitive_columns||[]).join(', ')) : ''}"
             style="padding:6px 8px;border-radius:var(--radius-sm);cursor:pointer;font-size:12.5px;margin-bottom:2px;${dbActiveTable===t.name?'background:var(--accent-glow);color:var(--accent-hi)':''}"
             data-hover="bg:var(--bg-3)" data-hover-out="bg:${dbActiveTable===t.name?'var(--accent-glow)':''}"
        >
          <div style="font-weight:600">${t.restricted ? '🔒 ' : ''}${escHtml(t.name)}${(t.sensitive_columns||[]).length ? ' <span style="color:var(--orange,#e0821c);font-size:10px">🔒</span>' : ''}</div>
          <div style="font-size:10.5px;color:var(--text-3)">${t.row_count} rows</div>
        </div>`).join('')}
    </div>
    <!-- Table data -->
    <div id="db-table-data" style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);overflow:hidden;display:flex;flex-direction:column">
      <div style="color:var(--text-3);font-size:13px;padding:30px;text-align:center">
        ${tables.length ? 'Select a table →' : 'No tables found'}
      </div>
    </div>
  </div>`;
  // Delegated listener on the table-list container — replaces
  // onclick="dbLoadTable(${JSON.stringify(t.name)})", which broke
  // UNCONDITIONALLY (not just on names containing quotes/spaces):
  // JSON.stringify() always wraps its output in literal double quotes
  // that collide with the onclick attribute's own double-quote
  // delimiters, corrupting the HTML. Reproduced live by creating a table
  // named `weird name with spaces` via the SQL Editor tab, then clicking
  // it in this list — threw "Uncaught SyntaxError: Unexpected end of
  // input" before this fix.
  document.getElementById('db-table-list')?.addEventListener('click', e => {
    const row = e.target.closest('[data-table-idx]');
    if (!row) return;
    const t = tables[+row.dataset.tableIdx];
    if (t) dbLoadTable(t.name);
  });
  if (dbActiveTable) dbLoadTable(dbActiveTable);
}

async function dbLoadTable(name) {
  dbActiveTable = name;
  const el = document.getElementById('db-table-data');
  if (!el) return;
  el.innerHTML = `<div style="color:var(--text-2);padding:12px">Loading ${escHtml(name)}…</div>`;
  try {
    const r    = await fetch(`/api/db/sqlite/table/${encodeURIComponent(name)}?limit=100`);
    if (r.status === 403) {
      const err = await r.json().catch(() => ({}));
      el.innerHTML = `<div style="padding:16px">
        <div style="font-weight:700;margin-bottom:6px">🔒 Protected table</div>
        <div style="font-size:13px;color:var(--text-2)">${escHtml(err.error||'This table is not readable through Database Studio.')}</div>
      </div>`;
      return;
    }
    if (!r.ok) { el.innerHTML = `<div style="color:var(--red);padding:12px">Server error ${r.status}</div>`; return; }
    const data = await r.json();
    if (!data.ok) { el.innerHTML = `<div style="color:var(--red);padding:12px">${escHtml(data.error||'error')}</div>`; return; }

    const { columns, rows, total } = data;
    el.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid var(--border);background:var(--bg-1);flex-shrink:0">
        <span style="font-weight:700;font-size:13px">${escHtml(name)}</span>
        <span style="font-size:11px;color:var(--text-2)">${total} rows · ${columns.length} columns</span>
        <div style="margin-left:auto;display:flex;gap:6px">
          <button data-act-click="dbInsertRow(${jsArg(name)})" class="btn btn-primary btn-sm">+ Row</button>
          <button data-act-click="dbSetTab('sql')" class="btn btn-ghost btn-sm">SQL</button>
        </div>
      </div>
      <div style="overflow:auto;flex:1" id="db-table-rows">
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead>
            <tr style="background:var(--bg-1);position:sticky;top:0;z-index:1">
              ${columns.map(c => `<th style="padding:7px 10px;text-align:left;border-bottom:1px solid var(--border);color:var(--text-2);font-weight:700;white-space:nowrap">${escHtml(c)}</th>`).join('')}
              <th style="padding:7px 10px;border-bottom:1px solid var(--border);width:40px"></th>
            </tr>
          </thead>
          <tbody>
            ${rows.map((row, idx) => `
              <tr style="border-bottom:1px solid var(--border)" data-hover="bg:var(--bg-3)" data-hover-out="bg:">
                ${columns.map(c => `<td style="padding:6px 10px;color:var(--text-1);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escHtml(String(row[c]??''))}">${escHtml(String(row[c]??''))}</td>`).join('')}
                <td style="padding:6px 10px"><button data-row-idx="${idx}" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:12px">🗑</button></td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>
      ${rows.length === 0 ? '<div style="text-align:center;padding:20px;color:var(--text-3)">No rows</div>' : ''}`;
    // Delegated listener on the rows container — replaces
    // onclick="dbDeleteRow(${JSON.stringify(name)},${JSON.stringify(...)},${JSON.stringify(...)})",
    // which broke UNCONDITIONALLY (same JSON.stringify()-in-onclick quote
    // collision as the table-list rows above) and additionally exposed
    // arbitrary cell VALUES (not just table/column names) to the same bug
    // — a row whose primary-key value happened to contain a quote or
    // backslash would corrupt the onclick attribute even if the table and
    // column names were both innocuous. Delete button now looks up the
    // real row/columns from the already-fetched `rows`/`columns` arrays
    // by index, never re-serializing cell data into HTML at all.
    document.getElementById('db-table-rows')?.addEventListener('click', e => {
      const btn = e.target.closest('[data-row-idx]');
      if (!btn) return;
      const row = rows[+btn.dataset.rowIdx];
      if (!row) return;
      dbDeleteRow(name, String(row[columns[0]] ?? ''), columns[0]);
    });
  } catch(e) {
    el.innerHTML = `<div style="color:var(--red);padding:12px">${escHtml(e.message)}</div>`;
  }
}

async function dbInsertRow(table) {
  // Get columns first
  try {
    const r    = await fetch(`/api/db/sqlite/table/${encodeURIComponent(table)}?limit=0`);
    if (!r.ok) { toast('Column fetch failed: server error ' + r.status, 'err'); return; }
    const data = await r.json();
    const cols = (data.columns||[]).filter(c => c !== 'id' && c !== 'created_at');
    if (!cols.length) { toast('Cannot determine columns', 'warn'); return; }

    const values = {};
    for (const col of cols.slice(0,5)) {
      const v = await gmPrompt(`Insert row`, `Value for "${col}"`, '');
      if (v === null) return;
      values[col] = v;
    }

    const r2 = await fetch(`/api/db/sqlite/table/${encodeURIComponent(table)}/insert`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({row: values})
    });
    if (!r2.ok) { toast('Insert failed: server error ' + r2.status, 'err'); return; }
    const j = await r2.json();
    if (j.ok) { toast('Row inserted ✅', 'ok', 1500); dbLoadTable(table); }
    else toast('Insert failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('Insert error: ' + ex.message, 'err'); }
}

async function dbDeleteRow(table, value, pk) {
  if (!(await gmDanger(`Delete row`, `Delete row where ${pk}="${value}"?`))) return;
  try {
    const r = await fetch(`/api/db/sqlite/table/${encodeURIComponent(table)}/row`, {
      method:'DELETE', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({pk_column: pk, pk_value: value})
    });
    if (!r.ok) { toast('Delete failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast('Row deleted', 'ok', 1500); dbLoadTable(table); }
    else toast('Delete failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('Delete error: ' + ex.message, 'err'); }
}

async function renderSupabaseTab(el) {
  let s = {connected: false, setup: {steps: [], url: ''}};
  try {
    const r = await fetch('/api/db/supabase/status');
    if (!r.ok) throw new Error('Supabase status error ' + r.status);
    s = await r.json();
  } catch(ex) {
    el.innerHTML = `<div style="color:var(--red);padding:16px">Error: ${escHtml(ex.message)}</div>`;
    return;
  }
  if (!s.connected) {
    // s.error means an actual connection attempt was made and failed
    // (bad URL/key, network error, non-2xx response from Supabase) — vs.
    // simply having no keys saved yet. Previously both cases rendered the
    // identical bare "Connect Supabase" form with zero indication that a
    // save had already happened but the credentials didn't work (same UX
    // gap fixed for GitHub's "Connect GitHub" screen earlier this
    // session).
    const errorBanner = s.error ? `
      <div style="background:rgba(232,82,82,.1);border:1px solid var(--danger);border-radius:var(--radius-sm);padding:12px 14px;margin-bottom:14px;font-size:12.5px;color:var(--danger)">
        ⚠️ Connection failed: ${escHtml(s.error)}
      </div>` : '';
    el.innerHTML = `<div class="settings-card">
      <h3>☁️ Connect Supabase</h3>
      ${errorBanner}
      <p>PostgreSQL + Auth + Storage — the same stack Lovable uses.</p>
      <div style="background:var(--bg-1);border-radius:var(--radius-sm);padding:12px;font-size:13px;line-height:1.8;margin-bottom:14px">
        ${(s.setup?.steps||[]).map(s=>escHtml(s)).join('<br>')}
        <a href="${safeUrl(s.setup?.url||'https://supabase.com')}" target="_blank" style="color:var(--accent);display:block;margin-top:8px">→ Create Supabase project ↗</a>
      </div>
      <div style="display:flex;flex-direction:column;gap:8px">
        <div>
          <label style="font-size:11px;font-weight:700;color:var(--text-2);display:block;margin-bottom:4px">SUPABASE_URL</label>
          <input id="supa-url-input" placeholder="https://xxxx.supabase.co" class="key-input" style="width:100%">
        </div>
        <div>
          <label style="font-size:11px;font-weight:700;color:var(--text-2);display:block;margin-bottom:4px">SUPABASE_ANON_KEY</label>
          <input id="supa-key-input" type="password" placeholder="eyJhbGci…" class="key-input" style="width:100%">
        </div>
        <button data-act-click="saveSupabaseKeys()" class="btn btn-primary">Connect Supabase</button>
      </div>
    </div>`;
    return;
  }

  el.innerHTML = `<div class="settings-card">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px">
      <span style="font-size:24px">☁️</span>
      <div><div style="font-weight:800">Supabase Connected</div>
      <div style="font-size:12px;color:var(--accent)">${escHtml(s.url||'')}</div></div>
      <span class="tag green" style="margin-left:auto">✅ Connected</span>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
      <button data-act-click="supaGenerateSchema()" class="btn btn-primary">🤖 AI Schema Designer</button>
      <button data-act-click="openExternalLink(${jsArg('' + (s.url?.replace('.supabase.co','')||'') + '.supabase.co/project/default/editor')})" class="btn btn-ghost">SQL Editor ↗</button>
      <button data-act-click="openExternalLink(${jsArg('' + (s.url?.replace('.supabase.co','')||'') + '.supabase.co/project/default/auth/users')})" class="btn btn-ghost">Auth Users ↗</button>
      <button data-act-click="openExternalLink(${jsArg('' + (s.url?.replace('.supabase.co','')||'') + '.supabase.co/project/default/storage/buckets')})" class="btn btn-ghost">Storage ↗</button>
    </div>
  </div>`;
}

async function saveSupabaseKeys() {
  const url = document.getElementById('supa-url-input')?.value.trim();
  const key  = document.getElementById('supa-key-input')?.value.trim();
  if (!url || !key) { toast('Both URL and key required', 'warn'); return; }
  try {
    const r1 = await fetch('/api/secrets/set', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:'SUPABASE_URL',value:url,scope:'global'})});
    const r2 = await fetch('/api/secrets/set', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:'SUPABASE_ANON_KEY',value:key,scope:'global'})});
    if (!r1.ok || !r2.ok) { toast('Save failed: server error', 'err'); return; }
    // /api/secrets/set injects into os.environ synchronously in the same
    // request (backend/routers/secrets.py), so both keys are live
    // immediately — no restart needed. Re-render right away instead of
    // telling the user to reload (the same fix applied to GitHub's and
    // Deploy's equivalent "reload to activate" messages earlier this
    // session), and report the REAL connection outcome rather than
    // presuming success.
    toast('🔐 Keys saved — checking connection…', 'ok', 2000);
    const el = document.getElementById('db-body');
    if (el) await renderSupabaseTab(el);
  } catch(ex) { toast('Save failed: ' + ex.message, 'err'); }
}

async function supaGenerateSchema() {
  const desc = await gmPrompt('AI Schema Designer', 'Describe your app data model\ne.g. "SaaS with users, projects, tasks, and comments"', '', true);
  if (!desc) return;
  toast('🤖 Generating schema…', 'ok', 2000);
  try {
    const r = await fetch('/api/db/supabase/ai-setup', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({description: desc})
    });
    if (!r.ok) { toast('Schema generation failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) {
    await gmAlert('Generated Supabase Schema', `<div style="font-size:12px;font-family:monospace;white-space:pre-wrap;max-height:400px;overflow-y:auto;background:var(--bg-0);padding:10px;border-radius:6px">${escHtml(j.sql)}</div>
      <div style="margin-top:10px;font-size:12px;color:var(--text-2)">Copy this SQL and run it in your Supabase SQL Editor.</div>`);
    } else toast('Schema generation failed', 'err');
  } catch(ex) { toast('Schema error: ' + ex.message, 'err'); }
}

function renderSQLEditorTab(el) {
  el.innerHTML = `<div style="display:flex;flex-direction:column;gap:12px">
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:16px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
        <div style="font-weight:700">💻 SQL Editor</div>
        <div style="display:flex;gap:6px">
          <label style="display:flex;align-items:center;gap:5px;font-size:12px;cursor:pointer">
            <input type="checkbox" id="sql-allow-write" style="accent-color:var(--red)">
            <span style="color:var(--red)">Allow writes</span>
          </label>
          <button data-act-click="hRunSqlDryRun()" class="btn btn-ghost btn-sm" title="Run inside a transaction and roll it back — shows how many rows would change, commits nothing">🔍 Dry run</button>
          <button data-act-click="runSQL()" class="btn btn-primary btn-sm">▶ Run SQL</button>
        </div>
      </div>
      <textarea id="sql-editor" placeholder="SELECT * FROM agents LIMIT 10;" style="width:100%;min-height:120px;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;color:var(--text-0);font-size:13px;font-family:'JetBrains Mono',monospace;resize:vertical;outline:none"></textarea>
    </div>
    <div id="sql-results" style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:16px;min-height:100px">
      <div style="color:var(--text-3);font-size:13px">Run a query to see results</div>
    </div>
  </div>`;

  // Keyboard shortcut
  document.getElementById('sql-editor')?.addEventListener('keydown', e => {
    if ((e.ctrlKey||e.metaKey) && e.key==='Enter') { e.preventDefault(); runSQL(); }
  });
}

// Mirror of the server's _sql_risk(): purely a UX affordance so the user gets a
// confirmation dialog before a DROP. It is NOT a security control — the server
// classifies and records independently and never trusts anything sent from here.
function dbSqlLooksDestructive(sql) {
  const u = String(sql || '')
    .replace(/--[^\n]*/g, ' ')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/'[^']*'/g, "''")
    .toUpperCase();
  if (/\b(DROP|TRUNCATE)\b/.test(u)) return true;
  if (/\b(DELETE|UPDATE)\b/.test(u) && !/\bWHERE\b/.test(u)) return true;
  return false;
}

async function runSQL(opts) {
  const dryRun      = !!(opts && opts.dryRun);
  const sql         = document.getElementById('sql-editor')?.value.trim();
  const allowWrite  = dryRun ? true : document.getElementById('sql-allow-write')?.checked;
  if (!sql) return;

  // A dry run commits nothing, so it needs no confirmation — that is the point
  // of offering it: the safe way to find out what a statement would do.
  if (!dryRun && allowWrite && dbSqlLooksDestructive(sql)) {
    const ok = await gmDanger(
      'Run destructive SQL?',
      'This statement can drop a table or empty it entirely. It will be recorded in the immutable audit trail. Continue?'
    );
    if (!ok) return;
  }
  const res = document.getElementById('sql-results');
  if (res) res.innerHTML = '<div style="color:var(--text-2)">Running…</div>';

  try {
    const r = await fetch('/api/db/sqlite/query', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({sql, allow_write: allowWrite, dry_run: dryRun})
    });
    const j = await r.json().catch(() => null);
    if (!r.ok && !j) { if (res) res.innerHTML = `<div style="color:var(--red)">Server error ${r.status}</div>`; return; }
    if (!j.ok) {
    res.innerHTML = `<div style="color:var(--red);font-size:13px">${j.sensitive ? '🔒 ' : ''}Error: ${escHtml(j.error||'')}</div>`;
    return;
  }
  if (j.dry_run) {
    const deltas = j.deltas || {};
    const keys = Object.keys(deltas);
    res.innerHTML = `<div style="border-left:3px solid var(--accent, #4c8dff);padding-left:10px">
      <div style="font-weight:700;margin-bottom:4px">🔍 Dry run — nothing was committed</div>
      <div style="font-size:13px;color:var(--text-1)">${escHtml(j.message||'')}</div>
      <div style="font-size:12px;color:var(--text-2);margin-top:4px">Risk: <b style="color:${j.risk==='critical'?'var(--red)':'var(--text-1)'}">${escHtml(j.risk||'')}</b></div>
      ${keys.length ? `<div style="font-size:12px;margin-top:8px">${keys.map(t =>
        `<div>${escHtml(t)}: ${j.row_count_before[t]} → ${j.row_count_after[t]} <b style="color:${deltas[t]<0?'var(--red)':'var(--green)'}">(${deltas[t]>0?'+':''}${deltas[t]})</b></div>`
      ).join('')}</div>` : ''}
      <div style="font-size:11px;color:var(--text-3);margin-top:8px">Tick “Allow writes” and press Run SQL to apply this for real.</div>
    </div>`;
    return;
  }
  if (j.type === 'write') {
    res.innerHTML = `<div style="color:var(--green)">✅ ${j.rows_affected} rows affected</div>
      <div style="font-size:11px;color:var(--text-3);margin-top:6px">📜 Recorded in the audit trail</div>`;
    return;
  }
  const cols = j.columns || [];
  const rows = j.rows || [];
  const redacted = j.redacted_columns || [];
  res.innerHTML = `<div style="font-size:12px;color:var(--text-2);margin-bottom:8px">${rows.length} rows returned${
    redacted.length ? ` · <span style="color:var(--orange,#e0821c)">🔒 masked: ${escHtml(redacted.join(', '))}</span>` : ''}</div>
    <div style="overflow:auto;max-height:300px">
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr>${cols.map(c=>`<th style="padding:5px 8px;text-align:left;border-bottom:1px solid var(--border);color:var(--text-2);font-weight:700">${escHtml(c)}</th>`).join('')}</tr></thead>
        <tbody>${rows.map(row=>`<tr style="border-bottom:1px solid var(--border)">${cols.map(c=>`<td style="padding:5px 8px;color:var(--text-1)">${escHtml(String(row[c]??''))}</td>`).join('')}</tr>`).join('')}</tbody>
      </table>
    </div>`;
  } catch(ex) { if (res) res.innerHTML = `<div style="color:var(--red)">Error: ${escHtml(ex.message)}</div>`; }
}

async function renderSchemaDesignerTab(el) {
  el.innerHTML = `<div class="settings-card">
    <h3>🏗️ AI Schema Designer</h3>
    <p>Describe your data model in plain English → AI generates the SQL CREATE TABLE statement.</p>
    <textarea id="schema-desc" placeholder="A blog platform with users, posts, categories, tags, and comments. Users can like posts. Posts have a publish status." style="width:100%;min-height:80px;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;color:var(--text-0);font-size:13px;resize:none;outline:none;font-family:inherit;margin-bottom:10px"></textarea>
    <div style="display:flex;gap:8px">
      <button data-act-click="generateSchema('sqlite')" class="btn btn-primary">Generate SQLite</button>
      <button data-act-click="generateSchema('supabase')" class="btn btn-ghost">Generate Supabase SQL</button>
    </div>
    <div id="schema-result" style="margin-top:14px"></div>
  </div>`;
}

async function generateSchema(type) {
  const desc = document.getElementById('schema-desc')?.value.trim();
  if (!desc) { toast('Describe your data model first', 'warn'); return; }
  const el = document.getElementById('schema-result');
  if (el) el.innerHTML = '<div style="color:var(--text-2)">Generating schema…</div>';
  const endpoint = type==='supabase' ? '/api/db/supabase/ai-setup' : '/api/db/sqlite/ai-schema';
  try {
    const r = await fetch(endpoint, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({description: desc})
    });
    if (!r.ok) { if (el) el.innerHTML = `<div style="color:var(--red)">Server error ${r.status}</div>`; return; }
    const j = await r.json();
    if (el && j.sql) {
    // The server analyses the model's DDL against the REAL schema and returns a
    // plan. Nothing is offered for one-click execution until the operator has
    // seen what it would do — LLM-authored SQL against a live database used to
    // sit behind a bare "Create Table" button.
    const plan = j.plan || {};
    const warns = plan.warnings || [];
    const blocked = warns.some(w => String(w).indexOf('will be refused') !== -1);
    el.innerHTML = `<div style="position:relative">
      <pre style="background:var(--bg-0);border:1px solid var(--border);border-radius:var(--radius-sm);padding:12px;font-family:monospace;font-size:12px;white-space:pre-wrap;max-height:300px;overflow-y:auto">${escHtml(j.sql)}</pre>
      <div style="margin-top:10px;padding:10px;border-radius:var(--radius-sm);border:1px solid ${warns.length?'var(--red)':'var(--border)'};background:var(--bg-1)">
        <div style="font-weight:700;font-size:12px;margin-bottom:6px">${warns.length ? '⚠️ Review before running' : '✅ Review'}</div>
        <div style="font-size:12px;color:var(--text-2)">
          Creates: <b>${escHtml((plan.creates||[]).join(', ') || 'none')}</b> ·
          Drops: <b style="color:${(plan.drops||[]).length?'var(--red)':'inherit'}">${escHtml((plan.drops||[]).join(', ') || 'none')}</b> ·
          Statements: <b>${plan.statements ?? '?'}</b> ·
          Risk: <b style="color:${plan.risk==='critical'?'var(--red)':'inherit'}">${escHtml(plan.risk||'')}</b>
        </div>
        ${warns.length ? `<ul style="margin:8px 0 0 16px;padding:0;font-size:12px;color:var(--red)">${
          warns.map(w => `<li>${escHtml(w)}</li>`).join('')}</ul>` : ''}
      </div>
      <div style="display:flex;gap:6px;margin-top:8px">
        <button id="schema-copy-btn" class="btn btn-ghost btn-sm">📋 Copy</button>
        ${type==='sqlite' && !blocked ?`<button id="schema-create-btn" class="btn ${warns.length?'btn-ghost':'btn-primary'} btn-sm">▶ ${warns.length?'Run anyway…':'Create Table'}</button>`:''}
      </div>
    </div>`;
    // Bind via closures over the real `j.sql` string instead of
    // re-serializing it into onclick="...${JSON.stringify(j.sql)}..." —
    // that pattern broke UNCONDITIONALLY (not just on SQL containing
    // quotes) for the exact same reason as every other quote-collision
    // bug fixed this session, and here `j.sql` is arbitrary multi-line
    // LLM-generated SQL that routinely contains both single and double
    // quotes (string literals, quoted identifiers), making it one of the
    // highest-risk instances of this bug class in the app.
    document.getElementById('schema-copy-btn')?.addEventListener('click', () => {
      navigator.clipboard.writeText(j.sql).then(() => toast('📋 Copied', 'ok', 1500));
    });
    document.getElementById('schema-create-btn')?.addEventListener('click', () => {
      runGeneratedSchema(j.sql, plan);
    });
    }
  } catch(ex) { if (el) el.innerHTML = `<div style="color:var(--red)">Error: ${escHtml(ex.message)}</div>`; }
}

async function runGeneratedSchema(sql, plan) {
  const warns = (plan && plan.warnings) || [];
  if (warns.length) {
    const ok = await gmDanger(
      'Run AI-generated SQL against the live database?',
      'The server flagged this statement:<br><br>' +
      warns.map(w => '• ' + escHtml(w)).join('<br>') +
      '<br><br>This runs against your real data and is recorded in the audit trail. Continue?'
    );
    if (!ok) return;
  }
  try {
    const r = await fetch('/api/db/sqlite/table/create', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({sql})
    });
    if (!r.ok) { toast('Create failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast('✅ Table created!', 'ok'); dbSetTab('sqlite'); }
    else toast('Error: ' + (j.error||''), 'err');
  } catch(ex) { toast('Error: ' + ex.message, 'err'); }
}


// ── Audit Trail ──────────────────────────────────────────────────────────────
// Reads the immutable hash-chained ledger, filtered to Database Studio actions.
// Before this existed, a DROP TABLE through the SQL editor left no trace at all.
const DB_AUDIT_ACTIONS = [
  'db_sql_write', 'db_sql_attempt', 'db_sql_refused',
  'db_schema_change', 'db_schema_refused',
  'db_row_insert', 'db_row_delete',
];

async function renderDBAuditTab(el) {
  el.innerHTML = '<div style="color:var(--text-2);padding:16px">Loading audit trail…</div>';
  let entries = [];
  let verified = null;
  try {
    const results = await Promise.all(
      DB_AUDIT_ACTIONS.map(a =>
        fetch(`/api/audit-log?action_type=${encodeURIComponent(a)}&limit=100`)
          .then(r => r.ok ? r.json() : {entries: []})
          .catch(() => ({entries: []}))
      )
    );
    entries = results.flatMap(r => r.entries || []).sort((a, b) => (b.epoch_ms || 0) - (a.epoch_ms || 0)).slice(0, 200);
    const v = await fetch('/api/audit-log/verify').then(r => r.ok ? r.json() : null).catch(() => null);
    verified = v;
  } catch (ex) {
    el.innerHTML = `<div style="color:var(--red);padding:16px">Error loading audit trail: ${escHtml(ex.message)}</div>`;
    return;
  }

  const riskColor = r => r === 'critical' ? 'var(--red)' : r === 'high' ? 'var(--orange, #e0821c)' : 'var(--text-2)';
  const chainOk = verified && (verified.valid ?? verified.ok);

  el.innerHTML = `<div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:16px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
      <div>
        <div style="font-weight:700">📜 Database Audit Trail</div>
        <div style="font-size:12px;color:var(--text-2)">Every write, schema change, and refused statement, append-only and hash-chained.</div>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <span style="font-size:12px;color:${chainOk ? 'var(--green)' : 'var(--red)'}">
          ${verified ? (chainOk ? '🔒 Chain verified' : '⚠️ Chain integrity FAILED') : ''}
        </span>
        <button data-act-click="dbSetTab('audit')" class="btn btn-ghost btn-sm">↻ Refresh</button>
      </div>
    </div>
    ${entries.length ? `<div style="overflow:auto;max-height:520px">
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr>${['When','Action','Risk','Outcome','Statement'].map(h =>
          `<th style="padding:6px 8px;text-align:left;border-bottom:1px solid var(--border);color:var(--text-2);font-weight:700">${h}</th>`).join('')}</tr></thead>
        <tbody>${entries.map(e => {
          let sqlText = '';
          try { sqlText = (JSON.parse(e.metadata || '{}').sql) || e.action_detail || ''; }
          catch (_) { sqlText = e.action_detail || ''; }
          return `<tr style="border-bottom:1px solid var(--border)">
            <td style="padding:6px 8px;color:var(--text-2);white-space:nowrap">${escHtml(String(e.created_at || '').slice(0, 19).replace('T', ' '))}</td>
            <td style="padding:6px 8px;color:var(--text-1)">${escHtml(e.action_type || '')}</td>
            <td style="padding:6px 8px;color:${riskColor(e.risk_level)};font-weight:600">${escHtml(e.risk_level || '')}</td>
            <td style="padding:6px 8px;color:${e.outcome === 'success' ? 'var(--green)' : e.outcome === 'blocked' ? 'var(--red)' : 'var(--text-2)'}">${escHtml(e.outcome || '')}</td>
            <td style="padding:6px 8px;color:var(--text-1);font-family:monospace;max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escHtml(sqlText)}">${escHtml(sqlText.slice(0, 160))}</td>
          </tr>`;
        }).join('')}</tbody>
      </table>
    </div>` : '<div style="color:var(--text-3);font-size:13px;padding:12px 0">No database actions recorded yet.</div>'}
  </div>`;
}
