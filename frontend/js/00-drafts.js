// Agentic OS — draft persistence for long-form input
// ───────────────────────────────────────────────────────────────────────────
// THE PROBLEM
//
// The product has 49 textareas and no `beforeunload` handler anywhere. Type a
// long prompt into the chat box, hit Cmd+R by accident or follow a link, and
// it is gone with no warning and no way back.
//
// Code Studio is fine — it autosaves 600ms after the last keystroke. Chat and
// the other long-form fields are not: they hold the most expensive thing a
// user produces here (a carefully written prompt) and persist nothing.
//
// WHY A DRAFT CACHE RATHER THAN beforeunload
//
// `beforeunload` shows a browser-chrome dialog the app cannot style or word,
// it fires on every navigation whether or not anything is at risk, and modern
// browsers ignore custom text anyway. It interrupts the user to tell them
// about a problem instead of not having the problem.
//
// Saving the draft and putting it back is strictly better: nothing to dismiss,
// and the text is still there after a crash, a reload, or a closed tab.
//
// SCOPE
//
// Deliberately narrow. Only fields tagged `data-draft="<key>"`, only
// localStorage, and drafts expire after 7 days so the store cannot grow
// without bound. A draft is cleared as soon as the content is submitted —
// restoring a prompt the user already sent would be worse than losing it.
(function () {
  'use strict';

  var PREFIX = 'agentic_draft:';
  var MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
  var MAX_CHARS = 100000;   // guard against pasting an enormous file
  var DEBOUNCE_MS = 400;

  function storage() {
    try {
      // Private mode and disabled-storage both throw on access, not on use.
      var probe = '__agentic_probe__';
      window.localStorage.setItem(probe, '1');
      window.localStorage.removeItem(probe);
      return window.localStorage;
    } catch (_) {
      return null;
    }
  }

  var store = storage();

  function save(key, value) {
    if (!store) return;
    try {
      if (!value || !value.trim()) {
        store.removeItem(PREFIX + key);
        return;
      }
      store.setItem(PREFIX + key, JSON.stringify({
        v: value.slice(0, MAX_CHARS),
        t: Date.now(),
      }));
    } catch (_) {
      // Quota exceeded. Losing a draft is bad; throwing inside an input
      // handler and breaking typing is worse.
    }
  }

  function load(key) {
    if (!store) return null;
    try {
      var raw = store.getItem(PREFIX + key);
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      if (!parsed || typeof parsed.v !== 'string') return null;
      if (Date.now() - (parsed.t || 0) > MAX_AGE_MS) {
        store.removeItem(PREFIX + key);
        return null;
      }
      return parsed.v;
    } catch (_) {
      return null;
    }
  }

  function clear(key) {
    if (!store) return;
    try { store.removeItem(PREFIX + key); } catch (_) { /* ignore */ }
  }

  function sweep() {
    if (!store) return;
    try {
      var stale = [];
      for (var i = 0; i < store.length; i++) {
        var k = store.key(i);
        if (!k || k.indexOf(PREFIX) !== 0) continue;
        try {
          var p = JSON.parse(store.getItem(k));
          if (!p || Date.now() - (p.t || 0) > MAX_AGE_MS) stale.push(k);
        } catch (_) {
          stale.push(k);
        }
      }
      for (var j = 0; j < stale.length; j++) store.removeItem(stale[j]);
    } catch (_) { /* ignore */ }
  }

  // ── Wiring ───────────────────────────────────────────────────────────────
  var timers = Object.create(null);

  function attach(el) {
    var key = el.getAttribute('data-draft');
    if (!key || el.__draftBound) return;
    el.__draftBound = true;

    // Restore. Never clobber content the app itself put there first — a
    // pre-filled edit form must win over a stale draft.
    var existing = load(key);
    if (existing && !el.value) {
      el.value = existing;
      notifyRestored(el, key);
    }

    el.addEventListener('input', function () {
      clearTimeout(timers[key]);
      timers[key] = setTimeout(function () { save(key, el.value); }, DEBOUNCE_MS);
    });

    // Persist immediately on the way out rather than waiting for the debounce.
    el.addEventListener('blur', function () {
      clearTimeout(timers[key]);
      save(key, el.value);
    });
  }

  function notifyRestored(el, key) {
    // Tell the user, and give them a one-click way to reject it. Silently
    // repopulating a field is disorienting — they may have moved on.
    var bar = document.createElement('div');
    bar.className = 'draft-restored-note';
    bar.setAttribute('role', 'status');
    bar.style.cssText =
      'display:flex;align-items:center;gap:8px;margin:6px 0;padding:6px 10px;' +
      'font-size:11.5px;border-radius:6px;background:var(--bg-3);' +
      'color:var(--text-2);border:1px solid var(--border)';

    var text = document.createElement('span');
    text.textContent = '↩ Restored your unsent draft.';

    var discard = document.createElement('button');
    discard.type = 'button';
    discard.textContent = 'Discard';
    discard.style.cssText =
      'margin-left:auto;background:none;border:1px solid var(--border);' +
      'border-radius:5px;padding:2px 8px;font-size:11px;cursor:pointer;' +
      'color:var(--accent-text)';
    discard.addEventListener('click', function () {
      el.value = '';
      clear(key);
      bar.remove();
      el.focus();
    });

    bar.appendChild(text);
    bar.appendChild(discard);
    if (el.parentNode) el.parentNode.insertBefore(bar, el);
    setTimeout(function () { if (bar.isConnected) bar.remove(); }, 12000);
  }

  function scan(root) {
    var nodes = (root || document).querySelectorAll('[data-draft]');
    for (var i = 0; i < nodes.length; i++) attach(nodes[i]);
  }

  // Panes render lazily, so watch for fields that appear later.
  function observe() {
    if (typeof MutationObserver !== 'function') return;
    new MutationObserver(function (records) {
      for (var i = 0; i < records.length; i++) {
        var added = records[i].addedNodes;
        for (var j = 0; j < added.length; j++) {
          var node = added[j];
          if (node.nodeType !== 1) continue;
          if (node.hasAttribute && node.hasAttribute('data-draft')) attach(node);
          if (node.querySelectorAll) scan(node);
        }
      }
    }).observe(document.documentElement, { childList: true, subtree: true });
  }

  function init() {
    sweep();
    scan(document);
    observe();
  }

  // Bind whatever exists now AND again once parsing finishes. The script is
  // loaded before the fields it manages, so a DOMContentLoaded-only hook would
  // be correct — but the MutationObserver started here also has to be running
  // before those fields appear, or the ones added during parsing are missed.
  // Running both is idempotent: attach() no-ops on an element it already bound.
  init();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  }

  // Public API — callers clear the draft once the content is committed.
  window.Drafts = {
    save: save,
    load: load,
    clear: clear,
    attach: attach,
    scan: scan,
    /** Clear by element, for use in a submit handler. */
    clearFor: function (el) {
      if (el && el.getAttribute) {
        var k = el.getAttribute('data-draft');
        if (k) clear(k);
      }
    },
  };
})();
