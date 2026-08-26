/*
 * Agentic OS — Capture Inbox (frontend/js/60-inbox.js)
 *
 * One door in. A phone share sheet, a forwarded email, a hook, the terminal
 * and this pane all write into the same folder, and the ICM entry router files
 * them into workspaces.
 *
 * The Preview button matters more than the Sweep button: it shows exactly
 * where every item WOULD go before anything moves, which is the same
 * propose-then-confirm gate the restructure and describe flows use. An item
 * the router cannot place stays put and says why, rather than being filed
 * somewhere plausible.
 */
(function () {
  'use strict';

  let items = [];
  let filedItems = [];
  let showFiled = false;

  const esc = (s) => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

  function arg(v) {
    return (window.jsArg ? window.jsArg(v) : JSON.stringify(v));
  }

  async function api(path, opts) {
    const r = await fetch(path, opts);
    let d = null;
    try { d = await r.json(); } catch (e) { d = null; }
    if (!r.ok || (d && d.ok === false)) {
      const msg = (d && (d.detail || d.error)) || ('HTTP ' + r.status);
      throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    }
    return d || {};
  }

  const SOURCE_ICON = {
    share: '📱', email: '✉️', hook: '🪝', terminal: '⌨️',
    web: '🌐', voice: '🎙', api: '🔌',
  };

  function ago(ts) {
    if (!ts) return '';
    const secs = Math.max(0, Math.floor(Date.now() / 1000) - ts);
    if (secs < 60) return 'just now';
    if (secs < 3600) return Math.floor(secs / 60) + 'm ago';
    if (secs < 86400) return Math.floor(secs / 3600) + 'h ago';
    return Math.floor(secs / 86400) + 'd ago';
  }

  async function renderInboxPane() {
    const host = document.getElementById('pane-inbox');
    if (!host) return;
    host.innerHTML = `
      <div style="flex:1;display:flex;flex-direction:column;min-height:0">
        <div style="padding:18px 24px 14px;border-bottom:1px solid var(--border-0)">
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
            <div>
              <div style="font-size:18px;font-weight:700">📥 Inbox</div>
              <div style="font-size:12.5px;color:var(--text-2);margin-top:2px">
                Capture anything from anywhere. The router files it into the right workspace.
              </div>
            </div>
            <div style="flex:1"></div>
            <button type="button" class="btn" data-act-click="inboxPreview()">Preview sweep</button>
            <button type="button" class="btn" data-act-click="inboxSweep()">Sweep now</button>
          </div>
          <div style="display:flex;gap:8px;margin-top:14px">
            <input id="inbox-quick" type="text"
              placeholder="Capture a thought, a link, anything…"
              style="flex:1;padding:11px 13px;background:var(--bg-1);color:var(--text-0);
                     border:1px solid var(--border-0);border-radius:8px;font-size:13px">
            <button type="button" class="btn" data-act-click="inboxCapture()">Capture</button>
          </div>
          <div id="inbox-note" style="font-size:12px;color:var(--text-2);margin-top:8px"></div>
        </div>
        <div id="inbox-body" style="flex:1;overflow-y:auto;padding:16px 24px"></div>
      </div>`;

    const q = document.getElementById('inbox-quick');
    if (q) q.addEventListener('keydown', (e) => { if (e.key === 'Enter') inboxCapture(); });

    // A share from a phone redirects back here with a flag; confirm it landed.
    try {
      const flag = new URLSearchParams(window.location.search).get('captured');
      if (flag) {
        const note = document.getElementById('inbox-note');
        if (note) {
          note.textContent = flag === 'ok'
            ? '✓ Captured from share.'
            : (flag === 'empty' ? 'That share had nothing in it.' : 'Capture failed.');
        }
      }
    } catch (e) { /* querystring is best-effort */ }

    await loadInbox();
  }

  async function loadInbox() {
    try {
      const d = await api('/api/inbox');
      items = d.items || [];
      const f = await api('/api/inbox?filed=true&limit=50');
      filedItems = f.items || [];
      renderList(d.stats || {});
    } catch (e) {
      const body = document.getElementById('inbox-body');
      if (body) {
        body.innerHTML = `<div style="color:var(--danger);font-size:13px">${esc(e.message)}</div>`;
      }
    }
  }

  function renderList(stats) {
    const body = document.getElementById('inbox-body');
    if (!body) return;
    const list = showFiled ? filedItems : items;

    const tabs = `
      <div style="display:flex;gap:16px;margin-bottom:14px;align-items:center">
        <button type="button" data-act-click="inboxTab(false)"
          style="background:none;border:none;cursor:pointer;font-size:13px;font-weight:600;
                 padding:4px 0;border-bottom:2px solid ${showFiled ? 'transparent' : 'var(--accent)'};
                 color:${showFiled ? 'var(--text-2)' : 'var(--text-0)'}">
          Waiting (${esc(String(items.length))})</button>
        <button type="button" data-act-click="inboxTab(true)"
          style="background:none;border:none;cursor:pointer;font-size:13px;font-weight:600;
                 padding:4px 0;border-bottom:2px solid ${showFiled ? 'var(--accent)' : 'transparent'};
                 color:${showFiled ? 'var(--text-0)' : 'var(--text-2)'}">
          Filed (${esc(String(filedItems.length))})</button>
        <div style="flex:1"></div>
        <span style="font-size:11.5px;color:var(--text-2)">
          ${esc(Object.entries(stats.by_source || {})
            .map((e) => (SOURCE_ICON[e[0]] || '') + ' ' + e[1]).join('   '))}
        </span>
      </div>`;

    if (!list.length) {
      body.innerHTML = tabs + `
        <div style="padding:40px;text-align:center;color:var(--text-2)">
          <div style="font-size:32px">${showFiled ? '🗃' : '📥'}</div>
          <div style="font-weight:600;color:var(--text-0);margin-top:10px">
            ${showFiled ? 'Nothing filed yet' : 'Inbox zero'}</div>
          <div style="font-size:13px;margin-top:6px;max-width:440px;margin-left:auto;margin-right:auto">
            ${showFiled
              ? 'Swept items land here with a record of which workspace took them and why.'
              : 'Capture above, share to this app from your phone, or point a hook at /api/inbox. '
                + 'Everything arrives here first and gets filed by the router.'}
          </div>
        </div>`;
      return;
    }

    body.innerHTML = tabs + list.map((i) => `
      <div style="border:1px solid var(--border-0);border-radius:10px;padding:12px 14px;margin-bottom:9px">
        <div style="display:flex;align-items:center;gap:9px;flex-wrap:wrap">
          <span title="${esc(i.source)}">${esc(SOURCE_ICON[i.source] || '🔌')}</span>
          <span style="font-weight:600;font-size:13.5px">${esc(i.title)}</span>
          <span style="font-size:11.5px;color:var(--text-2)">${esc(ago(i.captured_at))}</span>
          <div style="flex:1"></div>
          ${i.workspace
            ? `<span style="font-size:11.5px;color:var(--accent-text)">
                 → ${esc(i.workspace)}${i.stage ? ' / ' + esc(i.stage) : ''}</span>`
            : `<button type="button" class="btn-sm" data-act-click="inboxDelete(${arg(i.id)})">Delete</button>`}
        </div>
        ${i.url ? `<div style="font-size:12px;color:var(--text-2);margin-top:5px;
            overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(i.url)}</div>` : ''}
        ${i.body && i.body !== i.title
          ? `<div style="font-size:12.5px;color:var(--text-2);margin-top:6px;
               display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">
               ${esc(i.body)}</div>`
          : ''}
        ${i.reason ? `<div style="font-size:11.5px;color:var(--text-2);margin-top:6px">
            Filed because: ${esc(i.reason)}</div>` : ''}
      </div>`).join('');
  }

  function inboxTab(filed) {
    showFiled = !!filed;
    renderList({});
    loadInbox();
  }

  async function inboxCapture() {
    const el = document.getElementById('inbox-quick');
    const note = document.getElementById('inbox-note');
    if (!el || !el.value.trim()) return;
    const text = el.value.trim();
    try {
      // A bare URL is a link capture, which is what a phone share usually is.
      const isUrl = /^https?:\/\/\S+$/i.test(text);
      await api('/api/inbox', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(isUrl ? {url: text, text: text, source: 'web'}
          : {text: text, source: 'web'}),
      });
      el.value = '';
      if (note) note.textContent = '✓ Captured.';
      await loadInbox();
    } catch (e) {
      if (note) note.textContent = 'Could not capture: ' + e.message;
    }
  }

  async function inboxDelete(id) {
    if (!window.confirm('Delete this captured item?')) return;
    try {
      await api('/api/inbox/items/' + encodeURIComponent(id), {method: 'DELETE'});
      await loadInbox();
    } catch (e) { /* the list reload will show the truth */ }
  }

  async function inboxPreview() {
    const body = document.getElementById('inbox-body');
    if (!body) return;
    body.innerHTML = '<div style="color:var(--text-2);font-size:13px">Resolving…</div>';
    try {
      const d = await api('/api/inbox/sweep/preview');
      body.innerHTML = `
        <div style="font-weight:700;font-size:14px">Sweep preview</div>
        <div style="font-size:12.5px;color:var(--text-2);margin:5px 0 14px">
          Where everything would go. Nothing has moved.
        </div>
        ${(d.filed || []).map((f) => `
          <div style="display:flex;gap:10px;padding:8px 0;border-bottom:1px solid var(--border-0);font-size:12.5px">
            <span style="min-width:70px;font-weight:700;color:var(--accent-text)">FILE</span>
            <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(f.title)}</span>
            <span style="color:var(--text-2)">→ ${esc(f.workspace_id)}/${esc(f.stage)}</span>
          </div>`).join('')}
        ${(d.left_in_inbox || []).map((l) => `
          <div style="display:flex;gap:10px;padding:8px 0;border-bottom:1px solid var(--border-0);font-size:12.5px">
            <span style="min-width:70px;font-weight:700;color:var(--warning)">STAYS</span>
            <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(l.title)}</span>
            <span style="color:var(--text-2)" title="${esc(l.reason)}">${esc(l.status)}</span>
          </div>`).join('')}
        <div style="margin-top:16px;display:flex;gap:10px;align-items:center">
          <button type="button" class="btn" data-act-click="inboxSweep()">
            File ${esc(String((d.filed || []).length))} of ${esc(String((d.filed || []).length + (d.left_in_inbox || []).length))}</button>
          <button type="button" class="btn-sm" data-act-click="inboxReload()">Back</button>
          <span style="font-size:12px;color:var(--text-2)">Nothing has moved yet.</span>
        </div>`;
    } catch (e) {
      body.innerHTML = `<div style="color:var(--danger);font-size:13px">${esc(e.message)}</div>`;
    }
  }

  async function inboxSweep() {
    const note = document.getElementById('inbox-note');
    try {
      const d = await api('/api/inbox/sweep', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({}),
      });
      if (note) {
        note.textContent = `Filed ${d.filed_count}. ${d.remaining} left in the inbox`
          + (d.remaining ? ' — the router could not place them.' : '.');
      }
      showFiled = false;
      await loadInbox();
    } catch (e) {
      if (note) note.textContent = 'Sweep failed: ' + e.message;
    }
  }

  function inboxReload() { loadInbox(); }

  // IIFE-wrapped, and the delegated dispatcher resolves handlers by plain
  // property lookup on window, so every data-act-click target must be exported
  // or the buttons silently do nothing.
  window.renderInboxPane = renderInboxPane;
  window.inboxTab = inboxTab;
  window.inboxCapture = inboxCapture;
  window.inboxDelete = inboxDelete;
  window.inboxPreview = inboxPreview;
  window.inboxSweep = inboxSweep;
  window.inboxReload = inboxReload;
})();
