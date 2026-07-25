// Agentic OS — Notification Center
// Extracted from 01-app-core.js for modularity
// ── Notification Center ────────────────────────────────────────────
let notifPanelOpen = false, unreadCount = 0;

function toggleNotifPanel() {
  notifPanelOpen = !notifPanelOpen;
  let panel = document.getElementById('notif-panel');
  if (!panel) { panel = createNotifPanel(); document.getElementById('shell').appendChild(panel); }
  panel.style.display = notifPanelOpen ? 'flex' : 'none';
  if (notifPanelOpen) refreshNotifications();
}
function createNotifPanel() {
  const p = document.createElement('div');
  p.id = 'notif-panel';
  p.style.cssText='position:fixed;top:52px;right:0;width:340px;height:calc(100vh - 52px);background:var(--bg-1);border-left:1px solid var(--border);z-index:8000;flex-direction:column;box-shadow:var(--shadow-lg);display:none';
  p.innerHTML=`<div style="display:flex;align-items:center;justify-content:space-between;padding:12px 14px;border-bottom:1px solid var(--border);flex-shrink:0">
    <div style="font-weight:700;font-size:14px">🔔 Notifications</div>
    <div style="display:flex;gap:6px">
      <button onclick="markAllNotifRead()" class="btn btn-ghost btn-sm">Mark all read</button>
      <button onclick="toggleNotifPanel()" style="background:none;border:none;color:var(--text-2);cursor:pointer;font-size:16px">×</button>
    </div>
  </div>
  <div id="notif-list" style="flex:1;overflow-y:auto;padding:6px"></div>`;
  document.addEventListener('click', e => {
    if(notifPanelOpen && !p.contains(e.target) && !document.getElementById('notif-bell-btn')?.contains(e.target))
      { notifPanelOpen=false; p.style.display='none'; }
  });
  return p;
}
async function refreshNotifications() {
  const el = document.getElementById('notif-list'); if(!el) return;
  try {
    let notifs = [], count = 0;
    try {
      const r0 = await fetch('/api/notifications/list?limit=30');
      const d0 = await r0.json();
      if (d0.ok) { notifs = d0.notifications || []; count = d0.unread_count || 0; }
    } catch(err) {
      const r = await fetch('/api/control/notifications?limit=30');
      const d = await r.json();
      notifs = d.notifications||[]; count = d.unread_count||0;
    }
    unreadCount = count;
    updateNotifBadge(unreadCount);
    if(!notifs.length) { el.innerHTML=`<div style="text-align:center;padding:32px 16px;color:var(--text-3)"><div style="font-size:24px;margin-bottom:6px">🔔</div><div style="font-size:12.5px">No notifications right now</div></div>`; return; }
    const icons={run_complete:'✅',budget_alert:'⚠️',error:'❌',deploy:'🚀',system:'ℹ️',info:'ℹ️',success:'✅',warning:'⚠️'};
    el.innerHTML=notifs.map(n=>{
      const unread = !n.read && !n.read_at;
      const title = n.title || '';
      const body = n.message || n.body || '';
      const timeStr = n.timestamp ? new Date(n.timestamp*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : (n.created_at||'').slice(5,16);
      
      let actionButtons = '';
      if (title.includes('HITL') || n.type === 'hitl_interrupt' || n.link === 'control') {
        actionButtons = `<div style="display:flex;gap:6px;margin-top:6px">
          <button onclick="handleNotifAction(event, 'approve-hitl', '${n.id}')" class="btn btn-primary btn-sm" style="padding:2px 8px;font-size:10px;background:var(--success);border:none;color:#fff">✅ Approve Now</button>
          <button onclick="handleNotifAction(event, 'reject-hitl', '${n.id}')" class="btn btn-ghost btn-sm" style="padding:2px 8px;font-size:10px;color:var(--danger)">❌ Reject</button>
        </div>`;
      } else if (title.includes('Vulnerability') || title.includes('Zero-Day') || n.link === 'bounty') {
        actionButtons = `<div style="display:flex;gap:6px;margin-top:6px">
          <button onclick="handleNotifAction(event, 'autopatch', '${n.id}')" class="btn btn-primary btn-sm" style="padding:2px 8px;font-size:10px">🛠️ Auto-Patch Now</button>
        </div>`;
      } else if (n.type === 'budget_alert' || title.includes('Budget')) {
        actionButtons = `<div style="display:flex;gap:6px;margin-top:6px">
          <button onclick="handleNotifAction(event, 'finops', '${n.id}')" class="btn btn-ghost btn-sm" style="padding:2px 8px;font-size:10px;color:var(--warning)">⚙️ Adjust Cap</button>
        </div>`;
      }

      return `<div onclick="markNotifRead(${JSON.stringify(n.id)}); if('${n.link||''}') nav('${n.link}'); toggleNotifPanel()" style="padding:10px 13px;border-bottom:1px solid var(--border);cursor:pointer;background:${unread?'rgba(91,138,248,.08)':''}">
        <div style="display:flex;gap:9px">
          <span style="font-size:15px;flex-shrink:0">${icons[n.type]||'🔔'}</span>
          <div style="flex:1;min-width:0">
            <div style="font-size:12.5px;font-weight:${unread?700:500};color:var(--text-0);margin-bottom:2px">${escHtml(title)}</div>
            <div style="font-size:11px;color:var(--text-2);line-height:1.5">${escHtml(body)}</div>
            ${actionButtons}
            <div style="font-size:10px;color:var(--text-3);margin-top:3px">${timeStr}</div>
          </div>
          ${unread?'<span style="width:7px;height:7px;border-radius:50%;background:var(--accent);flex-shrink:0;margin-top:4px"></span>':''}
        </div>
      </div>`;
    }).join('');
  } catch(e) { el.innerHTML=`<div style="color:var(--danger);padding:12px;font-size:12px">Error: ${escHtml(e.message)}</div>`; }
}
function updateNotifBadge(count) {
  const b=document.getElementById('notif-badge'); if(b) { b.style.display=count>0?'block':'none'; b.textContent=count>99?'99+':count; }
}
async function markNotifRead(id) {
  try { await fetch(`/api/notifications/mark-read/${encodeURIComponent(id)}`,{method:'POST'}); } catch(e){}
  try { await fetch(`/api/control/notifications/${encodeURIComponent(id)}/read`,{method:'PATCH'}); } catch(e){}
  refreshNotifications();
}
async function markAllNotifRead() {
  try { await fetch('/api/notifications/mark-all-read',{method:'POST'}); } catch(e){}
  try { await fetch('/api/control/notifications/read-all',{method:'POST'}); } catch(e){}
  refreshNotifications(); toast('✅ All read','ok',1200);
}

window.handleNotifAction = async function(evt, actionType, notifId) {
  if (evt) { evt.stopPropagation(); evt.preventDefault(); }
  if (actionType === 'approve-hitl' || actionType === 'reject-hitl') {
    const decision = actionType === 'approve-hitl' ? 'approve' : 'reject';
    try {
      await fetch(`/api/hitl/interrupt/${encodeURIComponent(notifId)}/decide`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({decision: decision, note: 'Actioned via Notification Center'})
      });
      toast(`HITL Interrupt ${decision.toUpperCase()}ED successfully`, 'ok', 2500);
    } catch(e) {}
  } else if (actionType === 'autopatch') {
    try {
      await fetch(`/api/security/bounty-hunter/scans/${encodeURIComponent(notifId)}/autopatch`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({vulnerability_id: notifId, apply_to_codebase: true})
      });
      toast('🛠️ Autonomously applied security patch!', 'ok', 3000);
    } catch(e) {}
  } else if (actionType === 'finops') {
    nav('finops');
  }
  markNotifRead(notifId);
};
setInterval(async()=>{
  try {
    let c = 0, firstNotif = null;
    try {
      const r0 = await fetch('/api/notifications/list?unread_only=true&limit=1');
      const d0 = await r0.json();
      if (d0.ok) { c = d0.unread_count || 0; firstNotif = d0.notifications?.[0]; }
    } catch(err) {
      const r = await fetch('/api/control/notifications?unread_only=true&limit=1');
      const d = await r.json(); c = d.unread_count||0; firstNotif = d.notifications?.[0];
    }
    if(c!==unreadCount){unreadCount=c;updateNotifBadge(c);
      if(c>0&&firstNotif&&'Notification'in window&&Notification.permission==='granted'){
        new Notification('Agentic OS',{body:firstNotif.title||firstNotif.message});
      }
    }
    if(notifPanelOpen) refreshNotifications();
  } catch(e){}
}, 15000);
setTimeout(()=>{ if('Notification'in window&&Notification.permission==='default') Notification.requestPermission(); }, 5000);

// Add to palette
if(typeof PALETTE_CMDS!=='undefined') PALETTE_CMDS.push(
  {icon:'🎛️',label:'Control Tower',desc:'Live traces, kill switch, budget rules',action:()=>nav('control')},
  {icon:'🛑',label:'Kill All Agents',desc:'Emergency stop',action:()=>killAllRuns()},
  {icon:'📁',label:'Workspaces',desc:'Switch projects, export ZIP',action:()=>nav('workspaces')},
  {icon:'📦',label:'Export ZIP',desc:'Download project',action:()=>exportCurrentZip()},
  {icon:'🌐',label:'Webhooks',desc:'External triggers',action:()=>nav('webhooks')},
  {icon:'🧪',label:'Generate Tests',desc:'AI test suites',action:()=>nav('testgen')},
  {icon:'🔔',label:'Notifications',desc:'View all alerts',action:()=>toggleNotifPanel()},
);

// ═══════════════════════════════════════════════════════════════
//  SPRINT 12 — Terminal, Image Gen, Integrations, Docs, UX
// ═══════════════════════════════════════════════════════════════

