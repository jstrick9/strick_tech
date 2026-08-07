
;/* 38-system-monitor.js */
let sysRefreshTimer = null;
async function renderSystem() {
const pane = document.getElementById('pane-system');
if (!pane) return;
pane.innerHTML = `<div class="section-head">
    <div><h2>💻 System Monitor</h2><p>CPU · RAM · Disk · Processes · Git · HMR</p></div>
    <div style="display:flex;gap:8px">
      <button data-act-click="refreshSystem()" class="btn btn-ghost btn-sm">⟳ Refresh</button>
      <button data-act-click="doGitCommit()" class="btn btn-primary btn-sm">📦 Git Commit</button>
    </div>
  </div>
  <div id="sys-body"><div style="color:var(--text-2);font-size:13px">Loading…</div></div>`;
refreshSystem();
clearInterval(sysRefreshTimer);
sysRefreshTimer = setInterval(refreshSystem, 10000);
}
async function refreshSystem() {
try {
const [hr, mr, gr] = await Promise.all([
fetch('/api/system/health'), fetch('/api/system/metrics'), fetch('/api/system/git')
]);
if (!hr.ok) throw new Error('Health API error ' + hr.status);
if (!mr.ok) throw new Error('Metrics API error ' + mr.status);
const h = await hr.json();
const m = await mr.json();
const g = gr.ok ? await gr.json() : {ok: false, error: 'Git API error ' + gr.status};
renderSystemBody(h, m, g);
} catch(e) {
const el = document.getElementById('sys-body');
if (el) el.innerHTML = `<div style="color:var(--red)">Error: ${escHtml(e.message)}</div>`;
}
}
function renderSystemBody(h, m, g) {
const el = document.getElementById('sys-body');
if (!el) return;
const sys  = h.system || {};
const disk = h.disk   || {};
const db   = h.database || {};
const meter = (label, pct, color='var(--accent)') =>
`<div style="margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px">
        <span style="color:var(--text-1)">${label}</span>
        <span style="font-weight:700;color:${color}">${pct}%</span>
      </div>
      <div style="height:8px;background:var(--bg-3);border-radius:99px;overflow:hidden">
        <div style="width:${Math.min(pct,100)}%;height:100%;background:${color};border-radius:99px;transition:width .6s ease"></div>
      </div></div>`;
el.innerHTML = `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-bottom:20px">
    ${[
      ['💻 CPU', sys.cpu_pct||m.cpu_pct||0, '%', sys.cpu_count ? sys.cpu_count+' cores' : ''],
      ['🧠 RAM', sys.ram_pct||m.ram_pct||0, '%', `${sys.ram_used_mb||m.ram_used_mb||0}/${sys.ram_total_mb||m.ram_total_mb||0} MB`],
      ['💾 Disk', disk.pct||0, '%', `${disk.used_gb||0}/${disk.total_gb||0} GB`],
      ['🗄 DB', 0, '', `${db.counts?.memory||0} memories · ${db.counts?.tasks||0} tasks`],
      ['🔴 Process', sys.process_ram_mb||0, 'MB RAM', `PID ${sys.pid||h.database?.pid||'?'}`],
      ['⚡ HMR', 0, '', `${h.processes?.length||0} processes tracked`],
    ].map(([label,val,unit,sub]) => `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:14px">
        <div style="font-size:11px;color:var(--text-2);font-weight:700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">${label}</div>
        <div style="font-size:22px;font-weight:800;color:var(--text-0)">${val}${unit}</div>
        <div style="font-size:11px;color:var(--text-3);margin-top:2px">${sub}</div>
      </div>`).join('')}
  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
    <div class="settings-card">
      <h3>📊 Resource Usage</h3>
      ${meter('CPU', Math.round(sys.cpu_pct||m.cpu_pct||0), (sys.cpu_pct||0)>80?'var(--red)':(sys.cpu_pct||0)>50?'var(--yellow)':'var(--green)')}
      ${meter('RAM', Math.round(sys.ram_pct||m.ram_pct||0), (sys.ram_pct||0)>85?'var(--red)':(sys.ram_pct||0)>60?'var(--yellow)':'var(--accent)')}
      ${meter('Disk', Math.round(disk.pct||0), (disk.pct||0)>90?'var(--red)':'var(--teal)')}
      <div style="font-size:11.5px;color:var(--text-2);margin-top:8px">
        DB: <strong>${disk.db_mb||0}MB</strong> · Platform: <strong>${sys.platform||'?'}</strong> · Python: <strong>${sys.python||'?'}</strong>
      </div>
    </div>
    <div class="settings-card">
      <h3>🗂 Git Status</h3>
      ${g.ok ? `
        <div class="u-fdf33f23">
          <span class="tag ${g.dirty?'yellow':'green'}">${g.dirty?'Modified':'Clean'}</span>
          <span class="tag blue" style="margin-left:6px">⎇ ${escHtml(g.branch||'')}</span>
        </div>
        ${g.unstaged?.length ? `<div style="font-size:12px;color:var(--yellow);margin-bottom:4px">Modified: ${g.unstaged.slice(0,3).map(f=>escHtml(f)).join(', ')}</div>` : ''}
        ${g.untracked?.length ? `<div style="font-size:12px;color:var(--text-2);margin-bottom:8px">Untracked: ${g.untracked.slice(0,3).map(f=>escHtml(f)).join(', ')}</div>` : ''}
        <div style="font-size:11.5px;font-weight:700;color:var(--text-2);margin-bottom:6px">Recent commits</div>
        ${(g.recent_commits||[]).slice(0,4).map(c => `
          <div style="display:flex;gap:8px;padding:4px 0;border-bottom:1px solid var(--border);font-size:11.5px">
            <code style="color:var(--accent-text);font-size:10.5px">${c.hash}</code>
            <span style="flex:1;color:var(--text-1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escHtml(c.message)}</span>
            <span style="color:var(--text-3)">${c.date}</span>
          </div>`).join('')}
        <button data-act-click="doGitCommit()" class="btn btn-primary btn-sm" style="width:100%;margin-top:10px">📦 Commit preview/</button>`
      : `<div style="color:var(--text-2);font-size:13px">${escHtml(g.error||'Git not available')}</div>
         <div style="font-size:12px;color:var(--text-3);margin-top:4px">${escHtml(g.tip||'')}</div>`}
    </div>
  </div>

  ${(h.processes||[]).length ? `
  <div class="settings-card u-1b0f4999" >
    <h3>⚙️ Key Processes</h3>
    <div style="display:flex;flex-direction:column;gap:4px">
      ${(h.processes||[]).map(p => `
        <div style="display:flex;gap:10px;font-size:12.5px;padding:5px 0;border-bottom:1px solid var(--border)">
          <span style="color:var(--text-3);font-family:monospace">${p.pid}</span>
          <span style="flex:1;font-weight:600">${escHtml(p.name)}</span>
          <span class="tag ${p.status==='running'?'green':''}">${p.status}</span>
          <span style="color:var(--text-2)">${p.ram_mb}MB</span>
        </div>`).join('')}
    </div>
  </div>` : ''}`;
}
async function doGitCommit() {
const message = await gmPrompt('Git Commit', 'Commit message…', 'Agentic OS checkpoint');
if (!message) return;
try {
const r = await fetch('/api/system/git/commit', {
method: 'POST', headers: {'Content-Type':'application/json'},
body: JSON.stringify({ message })
});
if (!r.ok) { toast('Git commit failed: server error ' + r.status, 'err'); return; }
const j = await r.json();
if (j.ok) toast(`📦 Committed: ${j.hash||''} "${message}"`, 'ok', 4000);
else toast('Git error: ' + (j.error||''), 'err');
refreshSystem();
} catch(ex) { toast('Git commit error: ' + ex.message, 'err'); }
}
