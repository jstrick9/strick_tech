// Agentic OS — Webhooks
// Extracted from 01-app-core.js for modularity
// ── Webhooks ───────────────────────────────────────────────────────
async function renderWebhooks() {
  const pane = document.getElementById('pane-webhooks');
  pane.innerHTML = skeletonPage();
  try {
    const [wr, tr] = await Promise.all([fetch('/api/webhooks'), fetch('/api/webhooks/templates')]);
    if (!wr.ok) throw new Error('Webhooks API error ' + wr.status);
    if (!tr.ok) throw new Error('Templates API error ' + tr.status);
    const [whs, tmpls] = await Promise.all([wr.json(), tr.json()]);
    pane.innerHTML = `
      ${pageHeader({title:'🌐 Webhooks', subtitle:'External events trigger agent runs — GitHub push, Stripe payment, form submit',
        actions:[{label:'＋ New Webhook', action:'createWebhook()', primary:true}]})}
      <div class="page-content">
      ${helpPanel({title:'Automate with webhooks',body:'Any service can trigger your agents. Get a unique URL, add it to GitHub/Stripe/Zapier.',steps:['Click + New Webhook','Copy the generated URL','Add it to your service','Agents run automatically on every event']})}
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">
        <div>
          <div style="font-weight:700;margin-bottom:10px">Your Webhooks</div>
          ${whs.length===0 ? emptyState({icon:'🌐',title:'No webhooks yet',body:'Create a webhook to trigger agents from external services.',actions:[{label:'Create Webhook',action:'createWebhook()',primary:true}]}) :
          whs.map(w=>`<div class="card" style="margin-bottom:8px">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
              <div style="flex:1;min-width:0"><div style="font-weight:600;font-size:13px">${escHtml(w.name)}</div>
              <div style="font-size:11px;color:var(--text-2)">Agent: ${w.agent_id} · ${w.trigger_count||0} triggers</div></div>
              <span class="badge ${w.enabled?'badge-success':'badge-default'}">${w.enabled?'Active':'Off'}</span>
            </div>
            <div style="background:var(--bg-1);border:1px solid var(--border);border-radius:6px;padding:5px 9px;font-size:11px;font-family:monospace;color:var(--accent);margin-bottom:8px;display:flex;align-items:center;gap:6px">
              <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">POST /api/webhooks/${w.id}/trigger</span>
              <button data-act-click="hCopyWebhookUrl(${jsArg(w.id)})" style="background:none;border:none;color:var(--text-2);cursor:pointer">📋</button>
            </div>
            <div style="display:flex;gap:6px">
              <button data-act-click="testWebhook(${JSON.stringify(w.id)})" class="btn btn-ghost btn-sm">▶ Test</button>
              <button data-act-click="deleteWebhook(${JSON.stringify(w.id)})" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:11px;margin-left:auto">🗑</button>
            </div>
          </div>`).join('')}
        </div>
        <div>
          <div style="font-weight:700;margin-bottom:10px">🚀 Templates</div>
          ${tmpls.map(t=>`<div class="card card-interactive lift" data-act-click="installWebhookTemplate(${JSON.stringify(t.id)})" style="margin-bottom:8px;padding:11px" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
            <div style="font-weight:600;font-size:12.5px;margin-bottom:2px">${escHtml(t.name)}</div>
            <div style="font-size:11.5px;color:var(--text-2);margin-bottom:4px">${escHtml(t.description)}</div>
            <div style="font-size:10.5px;color:var(--text-3)">${escHtml(t.setup)}</div>
          </div>`).join('')}
        </div>
      </div>
      </div>`;
  } catch(e) { pane.innerHTML=`<div class="page-content">${emptyState({icon:'⚠️',title:'Error',body:e.message})}</div>`; }
}
async function createWebhook() {
  const name = await gmPrompt('Webhook Name','e.g. GitHub Push Handler','');
  if (!name) return;
  const agentId = await gmPrompt('Agent','e.g. reviewer, brain','brain')||'brain';
  try {
    const r = await fetch('/api/webhooks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,agent_id:agentId})});
    if (!r.ok) { toast('Create failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) {
      await gmAlert('✅ Webhook Created!',`<div style="margin-bottom:8px">Endpoint:</div>
        <code style="display:block;background:var(--bg-0);padding:8px;border-radius:4px;font-size:12px;word-break:break-all">http://localhost:8787/api/webhooks/${j.id}/trigger</code>
        <div style="margin-top:8px;font-size:12px;color:var(--text-2)">Header: <code>X-Webhook-Secret: ${j.secret}</code></div>`);
      renderWebhooks();
    } else {
      toast('Create failed: ' + (j.error||'unknown error'), 'err');
    }
  } catch(ex) { toast('Create webhook error: ' + ex.message, 'err'); }
}
async function installWebhookTemplate(id) {
  try {
    const r = await fetch('/api/webhooks/templates');
    if (!r.ok) { toast('Failed to load templates: ' + r.status, 'err'); return; }
    const tmpls = await r.json();
    const t = tmpls.find(x=>x.id===id);
    if (!t) { toast('Template not found', 'err'); return; }
    const r2 = await fetch('/api/webhooks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:t.name,agent_id:t.agent_id,prompt_template:t.prompt_template})});
    if (!r2.ok) { toast('Create failed: server error ' + r2.status, 'err'); return; }
    const j = await r2.json();
    if (j.ok) { toast(`✅ ${t.name} created`, 'ok', 3000); renderWebhooks(); }
    else toast('Create failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('Template install error: ' + ex.message, 'err'); }
}
async function testWebhook(id) {
  toast('▶ Sending test event…', 'ok', 1500);
  try {
    const r = await fetch(`/api/webhooks/${encodeURIComponent(id)}/test`, {method:'POST'});
    if (!r.ok) { toast('Test failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) toast(`✅ Test sent — run ${j.run_id}`, 'ok', 3000);
    else toast('Test failed: '+(j.error||''), 'err');
  } catch(ex) { toast('Test error: ' + ex.message, 'err'); }
}
async function deleteWebhook(id) {
  if (!(await gmDanger('Delete Webhook','Remove this endpoint? This cannot be undone.'))) return;
  try {
    const r = await fetch(`/api/webhooks/${encodeURIComponent(id)}`,{method:'DELETE'});
    if (!r.ok) { toast('Delete failed: server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast('Deleted','ok',1200); renderWebhooks(); }
    else toast('Delete failed: ' + (j.error||''), 'err');
  } catch(ex) { toast('Delete error: ' + ex.message, 'err'); }
}

