// Agentic OS — Enhanced Notification Center
// Improved notifications with sample data and better UI
'use strict';

let notifPanelOpen = false;
let unreadCount = 0;

// Sample notifications for demo
const SAMPLE_NOTIFICATIONS = [
  {
    id: 'welcome',
    type: 'system',
    title: 'Welcome to Agentic OS',
    message: 'Your AI operating system is ready. Start by connecting an AI provider in Settings.',
    timestamp: Date.now() / 1000,
    read: false,
    link: 'settings'
  },
  {
    id: 'setup-tip',
    type: 'info',
    title: 'Quick Setup Tip',
    message: 'Press ⌘K to open the command palette and quickly navigate to any feature.',
    timestamp: Date.now() / 1000 - 300,
    read: false,
    link: null
  },
  {
    id: 'feature-highlight',
    type: 'success',
    title: 'New: Kanban Board',
    message: 'Try the drag-and-drop task board to manage your projects. Navigate to Tasks in the sidebar.',
    timestamp: Date.now() / 1000 - 600,
    read: true,
    link: 'kanban'
  }
];

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
        <button data-act-click="toggleNotifPanel()" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:16px;padding:2px">✕</button>
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

  // Try to fetch from API. The backend always returns ok:true with the real
  // (possibly empty) notification list and seeds its own welcome/status
  // notifications, so on success we trust the response EXACTLY — even when it
  // is empty. The old code fell back to fabricated SAMPLE_NOTIFICATIONS whenever
  // the list was empty, so a healthy but empty inbox displayed notifications
  // that did not exist in the store, and they re-appeared on every poll. Samples
  // are only shown on an actual fetch failure, as a clear error, never as real
  // data.
  try {
    const r = await fetch('/api/notifications/list?limit=30');
    const d = await r.json();
    if (d.ok) {
      notifs = d.notifications || [];
      count = d.unread_count ?? notifs.filter(n => !n.read && !n.read_at).length;
    } else {
      loadError = d.error || ('Server error ' + r.status);
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
    el.innerHTML = `
      <div style="text-align:center;padding:40px 20px;color:var(--text-3)" role="alert">
        <div style="font-size:32px;margin-bottom:12px">⚠️</div>
        <div style="font-size:14px;font-weight:600;color:var(--text-2);margin-bottom:4px">Couldn't load notifications</div>
        <div class="u-6cb285c6">${escapeHtml(loadError)}</div>
      </div>
    `;
    return;
  }
  if (!notifs.length) {
    el.innerHTML = `
      <div style="text-align:center;padding:40px 20px;color:var(--text-3)">
        <div style="font-size:32px;margin-bottom:12px">🔔</div>
        <div style="font-size:14px;font-weight:600;color:var(--text-2);margin-bottom:4px">No notifications</div>
        <div class="u-6cb285c6">You're all caught up!</div>
      </div>
    `;
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
      <div data-act-click="handleNotifClick(${jsArg(n.id)},${jsArg(n.link || '')})" 
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
    const r = await fetch(`/api/notifications/mark-read/${encodeURIComponent(id)}`, { method: 'POST' });
    // Marking read is a real state change: if it fails the badge count is
    // wrong and the notification comes back on the next poll, which reads as
    // the app losing track rather than as an error.
    if (!r.ok) toast(`Could not mark that notification read (HTTP ${r.status}).`, 'err', 4000);
  } catch (e) {
    toast('Could not mark that notification read: ' + (e && e.message ? e.message : 'network error'), 'err', 4000);
  }
  
  // Update local sample notifications
  const notif = SAMPLE_NOTIFICATIONS.find(n => n.id === id);
  if (notif) notif.read = true;
  
  refreshNotifications();
}

async function markAllNotifRead() {
  try {
    await fetch('/api/notifications/mark-all-read', { method: 'POST' });
  } catch (e) {}
  
  // Update local sample notifications
  SAMPLE_NOTIFICATIONS.forEach(n => n.read = true);
  
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
