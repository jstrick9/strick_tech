// Frontend correctness: a healthy but EMPTY notification inbox must show "No
// notifications", not fabricated SAMPLE_NOTIFICATIONS. refreshNotifications used
// to fall back to samples whenever the API returned an empty list, so fake
// welcome/status notifications appeared as real data (and re-appeared each
// poll). Only a genuine fetch failure may show a (clearly-labelled) error.
import { describe, it, expect, beforeEach, vi } from 'vitest';

function escHtml(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
function jsArg(v) { return JSON.stringify(v === undefined ? null : v).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }

function loadModule() {
  const fs = require('fs'); const path = require('path');
  const source = fs.readFileSync(path.join(__dirname, '..', 'js', '29-notifications.js'), 'utf8');
  const code = source + `\n;window.__refreshNotifications = refreshNotifications;`;
  new Function('window', 'document', 'navigator', 'localStorage', 'console', 'fetch', 'toast', 'nav', 'escHtml', 'jsArg', code)(
    globalThis.window, globalThis.document, globalThis.navigator, globalThis.localStorage,
    globalThis.console, globalThis.fetch, globalThis.toast, globalThis.nav, escHtml, jsArg
  );
}

function setupDom() {
  const list = Object.assign(document.createElement('div'), { id: 'notif-list' });
  const cb = Object.assign(document.createElement('div'), { id: 'notif-count-badge' });
  const b = Object.assign(document.createElement('div'), { id: 'notif-badge' });
  document.body.appendChild(list); document.body.appendChild(cb); document.body.appendChild(b);
  const orig = document.getElementById;
  document.getElementById = (id) => ({ 'notif-list': list, 'notif-count-badge': cb, 'notif-badge': b }[id] || orig(id));
  return { list, cb, b };
}

describe('notification inbox does not fabricate', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    globalThis.toast = vi.fn();
    globalThis.nav = vi.fn();
  });

  it('shows "No notifications" for a healthy but empty inbox', async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ ok: true, notifications: [], unread_count: 0 }) }));
    loadModule();
    const { list } = setupDom();
    await window.__refreshNotifications();
    expect(list.innerHTML).toContain('No notifications');
    // Must NOT show any fabricated sample content.
    expect(list.innerHTML).not.toContain('Welcome to Agentic OS');
    expect(list.innerHTML).not.toContain('setup-tip');
  });

  it('shows a load-error state when the fetch fails', async () => {
    globalThis.fetch = vi.fn(async () => { throw new Error('network down'); });
    loadModule();
    const { list } = setupDom();
    await window.__refreshNotifications();
    expect(list.innerHTML).toContain('load notifications');
    expect(list.innerHTML).not.toContain('Welcome to Agentic OS');
  });

  it('uses unread_count from the API for the badge', async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ ok: true, notifications: [{ id: 'x', title: 'T', read: false }], unread_count: 3 }) }));
    loadModule();
    const { cb } = setupDom();
    await window.__refreshNotifications();
    expect(cb.textContent).toBe('3');
  });
});
