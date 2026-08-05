// Agentic OS — MCP Tool Panel
// Extracted from 01-app-core.js for modularity
// ── MCP Tool Panel ────────────────────────────────────────────────
async function renderMCP() {
  const pane = document.getElementById('pane-mcp');
  if (!pane) return;
  pane.innerHTML = `<div class="section-head">
    <div><h2>🔧 MCP Tool Router</h2><p>Model Context Protocol — call any tool directly or let an agent use them autonomously</p></div>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
    <div>
      <div class="settings-card">
        <h3>Direct Tool Call</h3>
        <p>Call any tool directly and inspect the result.</p>
        <label style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px">Tool</label>
        <select id="mcp-tool-sel" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px;color:var(--text-0);font-size:13px;margin:6px 0 10px;outline:none">
          <option value="">Loading tools…</option>
        </select>
        <label style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px">Args (JSON)</label>
        <textarea id="mcp-args" placeholder='{"path": "index.html"}' style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px;color:var(--text-0);font-size:13px;resize:none;min-height:60px;outline:none;font-family:monospace;margin:6px 0 10px"></textarea>
        <button data-act-click="runMCPTool()" class="btn btn-primary" style="width:100%">▶ Call Tool</button>
        <div id="mcp-result" style="margin-top:12px;background:var(--bg-0);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;font-family:monospace;font-size:12px;color:var(--text-1);white-space:pre-wrap;max-height:300px;overflow-y:auto;display:none"></div>
      </div>
      <div class="settings-card">
        <h3>Agentic Run</h3>
        <p>Give an agent a task and let it autonomously use tools to complete it.</p>
        <textarea id="mcp-agent-prompt" placeholder="Research the latest React 19 features and write a summary to index.html" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px;color:var(--text-0);font-size:13px;resize:none;min-height:80px;outline:none;font-family:inherit;margin:6px 0 10px"></textarea>
        <div style="display:flex;gap:8px;margin-bottom:10px">
          <select id="mcp-agent-sel" style="flex:1;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px;color:var(--text-0);font-size:12.5px;outline:none">
            ${S.agents.map(a=>`<option value="${a.id}">${a.avatar||'🤖'} ${escHtml(a.name)}</option>`).join('')}
          </select>
          <input id="mcp-max-steps" type="number" value="5" min="1" max="10" style="width:70px;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px;color:var(--text-0);font-size:12.5px;outline:none" placeholder="Steps">
        </div>
        <button data-act-click="runAgentWithTools()" class="btn btn-primary" style="width:100%" id="mcp-agent-btn">🤖 Run Agent</button>
        <div id="mcp-agent-result" style="margin-top:12px;display:none"></div>
      </div>
    </div>
    <div>
      <div class="settings-card">
        <h3 id="mcp-tools-header">Available Tools</h3>
        <p>All tools available to agents via MCP.</p>
        <div id="mcp-tool-list" style="display:flex;flex-direction:column;gap:6px"></div>
      </div>
    </div>
  </div>`;
  loadMCPTools();
}

async function loadMCPTools() {
  try {
    const r = await fetch('/api/mcp/tools');
    if (!r.ok) throw new Error('Tools API error ' + r.status);
    const j = await r.json();
    const sel = document.getElementById('mcp-tool-sel');
    const list = document.getElementById('mcp-tool-list');
    // Update header with live count
    const hdr = document.getElementById('mcp-tools-header');
    if (hdr) hdr.textContent = `Available Tools (${j.count || j.tools?.length || 0})`;
    if (sel) sel.innerHTML = j.tools.map(t => `<option value="${escHtml(t.name)}">${escHtml(t.name)}</option>`).join('');
    if (list) list.innerHTML = j.tools.map(t => `
      <div style="display:flex;gap:10px;padding:7px 10px;background:var(--bg-3);border-radius:var(--radius-sm);cursor:pointer"
           onclick="document.getElementById('mcp-tool-sel').value=${jsArg(t.name)}">
        <code style="color:var(--accent);font-size:12px;min-width:140px">${t.name}</code>
        <span style="font-size:12px;color:var(--text-2)">${t.description}</span>
      </div>`).join('');
    // auto-fill args hint on select change
    if (sel) sel.onchange = () => {
      const tool = j.tools.find(t => t.name === sel.value);
      if (tool) {
        const exampleArgs = {};
        (tool.args||[]).filter(a=>!a.endsWith('?')).forEach(a => exampleArgs[a] = '');
        document.getElementById('mcp-args').value = JSON.stringify(exampleArgs, null, 2);
      }
    };
  } catch(e) { toast('Failed to load MCP tools', 'err'); }
}

async function runMCPTool() {
  const tool = document.getElementById('mcp-tool-sel')?.value;
  if (!tool) { toast('Select a tool first', 'warn'); return; }
  const argsStr = document.getElementById('mcp-args')?.value || '{}';
  const resultEl = document.getElementById('mcp-result');
  let args = {};
  try { args = JSON.parse(argsStr); } catch(e) { toast('Invalid JSON args — check the format', 'err'); return; }
  if (resultEl) { resultEl.style.display = 'block'; resultEl.textContent = 'Running…'; }
  try {
    const r = await fetch('/api/mcp/call', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({tool, args})
    });
    if (!r.ok) {
      if (resultEl) resultEl.textContent = 'Server error ' + r.status;
      toast('Tool call failed: server error ' + r.status, 'err');
      return;
    }
    const j = await r.json();
    if (resultEl) resultEl.textContent = JSON.stringify(j, null, 2);
    if (j.ok) toast(`✅ ${tool} → ${j.duration_ms}ms`, 'ok', 2000);
    else toast(`❌ ${j.error}`, 'err');
  } catch(ex) {
    if (resultEl) resultEl.textContent = 'Error: ' + ex.message;
    toast('Tool call error: ' + ex.message, 'err');
  }
}

async function runAgentWithTools() {
  const prompt = document.getElementById('mcp-agent-prompt')?.value.trim();
  const agentId = document.getElementById('mcp-agent-sel')?.value || 'builder';
  const maxSteps = parseInt(document.getElementById('mcp-max-steps')?.value || '5');
  if (!prompt) { toast('Enter a prompt', 'warn'); return; }
  const btn = document.getElementById('mcp-agent-btn');
  const resultEl = document.getElementById('mcp-agent-result');
  btn.disabled = true; btn.textContent = '⏳ Running…';
  resultEl.style.display = 'block';
  resultEl.innerHTML = `<div style="color:var(--text-2);font-size:13px">Agent is working…</div>`;
  try {
  const r = await fetch('/api/mcp/agent/run', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({prompt, agent_id: agentId, max_steps: maxSteps})
  });
  if (!r.ok) {
    resultEl.innerHTML = `<div style="color:var(--danger)">Server error ${r.status}</div>`;
    btn.disabled = false; btn.textContent = '🤖 Run Agent';
    return;
  }
  const j = await r.json();
  resultEl.innerHTML = `
    <div style="margin-bottom:10px;font-size:13px;font-weight:700">${j.ok?'✅':'❌'} ${j.step_count} steps</div>
    ${(j.steps||[]).map((s,i) => `<div style="background:var(--bg-3);border-radius:var(--radius-sm);padding:8px;margin-bottom:6px;font-size:12px">
      <div style="font-weight:700;margin-bottom:3px">Step ${s.step}: <span style="color:var(--accent)">${s.type}</span>${s.tool?` → ${s.tool}`:''}</div>
      ${s.output?`<div style="color:var(--text-1);white-space:pre-wrap;max-height:80px;overflow:hidden">${escHtml((s.output||'').slice(0,200))}</div>`:''}
      ${s.error?`<div style="color:var(--red)">${escHtml(s.error)}</div>`:''}
    </div>`).join('')}
    ${j.final_answer?`<div style="background:var(--accent-glow);border:1px solid var(--accent);border-radius:var(--radius-sm);padding:10px;font-size:13px">
      <div style="font-weight:700;margin-bottom:5px">Final Answer</div>
      <div>${renderMarkdown(j.final_answer)}</div>
    </div>`:''}`;
  btn.disabled = false; btn.textContent = '🤖 Run Agent';
  if (j.ok) toast(`✅ Agent done in ${j.step_count} steps`, 'ok');
  } catch(ex) {
    resultEl.innerHTML = `<div style="color:var(--danger)">Error: ${escHtml(ex.message)}</div>`;
    btn.disabled = false; btn.textContent = '🤖 Run Agent';
  }
}

