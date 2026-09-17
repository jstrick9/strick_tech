// Agentic OS — Notification Center
// r50: rewired from the demo-seeded /api/notifications/* store (fake
// "welcome"/"tip" entries in an in-memory list) to the REAL notification
// store: the control_tower notifications table, populated by run events
// (complete / fail / kill / budget stop) and webhook completions, and the
// same rows r49's toast handler announces live. Field shapes already
// matched (body/read_at/created_at were handled); the actions below now
// target the control endpoints.
'use strict';

let notifPanelOpen = false;
let unreadCount = 0;

function toggleNotifPanel() {
  notifPanelOpen = !notifPanelOpen;
  let panel = document.getElementById('notif-panel');
  if (!panel) {
    panel = createNotifPanel();
    document.getElementById('shell').appendChild(panel);
  }
  panel.style.display = notifPanelOpen ? 'flex' : 'none';
  if (notifPanelOpen) refreshNotifications();
}

function createNotifPanel() {
  const p = document.createElement('div');
  p.id = 'notif-panel';
  p.style.cssText = `
    position: fixed;
    top: 52px;
    right: 0;
    width: 360px;
    height: calc(100vh - 52px);
    background: var(--bg-1);
    border-left: 1px solid var(--border);
    z-index: 8000;
    flex-direction: column;
    box-shadow: var(--shadow-lg);
    display: none;
  `;
  
  p.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid var(--border);flex-shrink:0">
      <div style="display:flex;align-items:center;gap:8px">
        <span class="u-1444c6ea">🔔</span>
        <span style="font-weight:700;font-size:14px;color:var(--text-0)">Notifications</span>
        <span id="notif-count-badge" style="font-size:10px;background:var(--accent);color:var(--on-accent);padding:1px 6px;border-radius:99px;font-weight:700;display:none">0</span>
      </div>
      <div style="display:flex;gap:6px">
        <button data-act-click="markAllNotifRead()" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:11px;padding:4px 8px;border-radius:6px;transition:all 0.15s">Mark all read</button>
        <button aria-label="Close" title="Close" data-act-click="toggleNotifPanel()" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:16px;padding:2px">✕</button>
      </div>
    </div>
    <div id="notif-list" style="flex:1;overflow-y:auto;padding:4px"></div>
  `;

  // Close when clicking outside
  document.addEventListener('click', e => {
    if (notifPanelOpen && !p.contains(e.target) && !document.getElementById('notif-bell-btn')?.contains(e.target)) {
      notifPanelOpen = false;
      p.style.display = 'none';
    }
  });

  return p;
}

async function refreshNotifications() {
  const el = document.getElementById('notif-list');
  if (!el) return;

  let notifs = [];
  let count = 0;
  let loadError = '';

  // Fetch from the real store. The control API returns the true (possibly
  // empty) list, so on success we trust the response EXACTLY — even when it
  // is empty. The old code fabricated sample entries whenever the list was
  // empty, so a healthy but empty inbox displayed notifications that did
  // not exist; samples are long gone, and a fetch failure renders a clear
  // error, never fake data.
  try {
    const r = await fetch('/api/control/notifications?limit=30');
    const d = await r.json();
    if (r.ok && Array.isArray(d.notifications)) {
      notifs = d.notifications;
      count = d.unread_count ?? notifs.filter(n => !n.read && !n.read_at).length;
    } else {
      loadError = (d && d.detail) || ('Server error ' + r.status);
    }
  } catch (err) {
    loadError = 'could not load notifications';
  }

  unreadCount = count;
  updateNotifBadge(unreadCount);

  // Update count badge
  const countBadge = document.getElementById('notif-count-badge');
  if (countBadge) {
    countBadge.style.display = count > 0 ? 'inline' : 'none';
    countBadge.textContent = count;
  }

  if (loadError) {
    // Route through the shared error component (role=alert, aria-live=assertive)
    // instead of bespoke inline-styled markup.
    el.innerHTML = (typeof window.stateFeedback !== 'undefined' && window.stateFeedback.errorElement)
      ? window.stateFeedback.errorElement({ title: "Couldn't load notifications", message: escapeHtml(loadError) })
      : `<div class="data-state state-error" role="alert" aria-live="assertive">
           <span class="data-state-icon" aria-hidden="true">⚠️</span>
           <div class="data-state-copy"><div class="data-state-title">Couldn't load notifications</div>
             <div class="data-state-msg">${escapeHtml(loadError)}</div></div>
         </div>`;
    return;
  }
  if (!notifs.length) {
    // Route through the shared empty component (role=status, aria-live=polite).
    el.innerHTML = (typeof window.stateFeedback !== 'undefined' && window.stateFeedback.emptyElement)
      ? window.stateFeedback.emptyElement({ icon: '🔔', title: 'No notifications yet', message: 'New activity from your agents and collaborators will appear here.' })
      : `<div class="data-state state-empty" role="status" aria-live="polite">
           <span class="data-state-icon" aria-hidden="true">🔔</span>
           <div class="data-state-copy"><div class="data-state-title">No notifications yet</div>
             <div class="data-state-msg">New activity from your agents and collaborators will appear here.</div></div>
         </div>`;
    return;
  }

  const icons = {
    run_complete: '✅',
    budget_alert: '⚠️',
    error: '❌',
    deploy: '🚀',
    system: 'ℹ️',
    info: '💡',
    success: '✅',
    warning: '⚠️'
  };

  el.innerHTML = notifs.map(n => {
    const unread = !n.read && !n.read_at;
    const title = n.title || '';
    const body = n.message || n.body || '';
    const timeStr = n.timestamp 
      ? new Date(n.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      : (n.created_at || '').slice(5, 16);

    return `
      <div role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1" data-act-click="handleNotifClick(${jsArg(n.id)},${jsArg(n.link || (n.run_id ? 'control' : ''))})" 
           style="padding:12px 14px;border-bottom:1px solid var(--border);cursor:pointer;background:${unread ? 'rgba(99,102,241,0.06)' : 'transparent'};transition:background 0.15s"
           data-hover="bg:var(--bg-2)"
           data-hover-out="bg:${unread ? 'rgba(99,102,241,0.06)' : 'transparent'}">
        <div style="display:flex;gap:10px">
          <span style="font-size:16px;flex-shrink:0;margin-top:2px">${icons[n.type] || '🔔'}</span>
          <div class="u-59eddc67">
            <div style="font-size:13px;font-weight:${unread ? 600 : 500};color:var(--text-0);margin-bottom:3px">${escapeHtml(title)}</div>
            <div style="font-size:12px;color:var(--text-2);line-height:1.5">${escapeHtml(body)}</div>
            <div style="font-size:10px;color:var(--text-3);margin-top:4px">${timeStr}</div>
          </div>
          ${unread ? '<span style="width:8px;height:8px;border-radius:50%;background:var(--accent);flex-shrink:0;margin-top:4px"></span>' : ''}
        </div>
      </div>
    `;
  }).join('');
}

function handleNotifClick(id, link) {
  markNotifRead(id);
  if (link) nav(link);
  toggleNotifPanel();
}

function updateNotifBadge(count) {
  const b = document.getElementById('notif-badge');
  if (b) {
    b.style.display = count > 0 ? 'flex' : 'none';
    b.textContent = count > 99 ? '99+' : count;
  }
}

async function markNotifRead(id) {
  try {
    const r = await fetch(`/api/control/notifications/${encodeURIComponent(id)}/read`, { method: 'PATCH' });
    // Marking read is a real state change: if it fails the badge count is
    // wrong and the notification comes back on the next poll, which reads as
    // the app losing track rather than as an error.
    if (!r.ok) toast(`Could not mark that notification read (HTTP ${r.status}).`, 'err', 4000);
  } catch (e) {
    toast('Could not mark that notification read: ' + (e && e.message ? e.message : 'network error'), 'err', 4000);
  }

  refreshNotifications();
}

async function markAllNotifRead() {
  try {
    const r = await fetch('/api/control/notifications/read-all', { method: 'POST' });
    if (!r.ok) { toast(`Could not mark all read (HTTP ${r.status}).`, 'err', 4000); return; }
  } catch (e) {
    toast('Could not mark all read: ' + (e && e.message ? e.message : 'network error'), 'err', 4000);
    return;
  }

  refreshNotifications();
  if (typeof toast === 'function') toast('All notifications marked as read', 'ok');
}

// Utility function
function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Global exports
window.toggleNotifPanel = toggleNotifPanel;
window.markAllNotifRead = markAllNotifRead;
window.handleNotifClick = handleNotifClick;

console.log('%c✅ Enhanced Notifications loaded', 'color:#22c55e;font-weight:bold');
