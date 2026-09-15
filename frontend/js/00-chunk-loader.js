// Agentic OS — lazy pane chunk loader
//
// WHY
// ───
// 34% of the frontend (703 KB across 30 modules) belongs to exactly one pane
// each and is referenced by nothing during boot. Shipping it in the core
// bundle means every user downloads the MCP Gateway, the compliance report and
// the A2A console before they can send their first chat message.
//
// This module fetches a pane's code the first time that pane is opened, and
// quietly prefetches the rest once the browser is idle. By the time a user
// clicks anything, the chunk is usually already in cache.
//
// WHERE IT HOOKS IN
// ─────────────────
// Three separate call sites invoke pane renderers: `nav()` in 01-app-core.js,
// `showWorkstationTab()` in 00-workstations.js, and a third in
// 14-prompt-library.js. Patching all three would be the "second door" bug this
// review has hit six times -- one call site protected, the others quietly
// unprotected.
//
// So the interception happens at MASTER_PANE_REGISTRY itself, which all three
// go through. Each lazy pane's registry entry is replaced with a function that
// loads the chunk, then calls the real renderer that the chunk installed. No
// caller needs to know this exists, and a new call site added tomorrow is
// covered automatically.
//
// The registry already resolves renderers lazily (`typeof window.X ===
// 'function' && window.X()`), which is what makes this safe: the original
// entries never captured a function reference, they looked it up at call time.
'use strict';

(function () {
  var manifest = window.__CHUNK_MANIFEST__ || {};
  var loaded = Object.create(null);    // pane -> Promise
  var failed = Object.create(null);    // pane -> true, so retry is possible

  function chunkUrl(pane) {
    var entry = manifest[pane];
    return entry ? '/static/dist/' + entry : null;
  }

  // Load a chunk exactly once. Concurrent callers share the same promise, so
  // double-clicking a nav item cannot start two downloads of the same file.
  function loadChunk(pane) {
    if (loaded[pane]) return loaded[pane];
    var url = chunkUrl(pane);
    if (!url) return Promise.resolve(false);

    loaded[pane] = new Promise(function (resolve) {
      var script = document.createElement('script');
      script.src = url;
      script.async = false;   // preserve execution order against other chunks
      script.onload = function () {
        // The chunk just defined new renderer globals; wrap them too, or a
        // lazily loaded pane escapes render deduplication.
        if (typeof window.installRenderDedupe === 'function') {
          window.installRenderDedupe();
        }
        resolve(true);
      };
      script.onerror = function () {
        // Allow a retry on the next navigation rather than leaving the pane
        // permanently dead: a chunk fetch can fail for transient reasons
        // (offline, a proxy hiccup) and the user's next click should try again.
        delete loaded[pane];
        failed[pane] = true;
        console.warn('[chunks] failed to load ' + url);
        resolve(false);
      };
      document.head.appendChild(script);
    });
    return loaded[pane];
  }

  window.loadPaneChunk = loadChunk;
  window.paneChunkLoaded = function (pane) { return !!loaded[pane]; };
  // Shared failure affordance so other call sites that invoke pane renderers
  // directly (06-sprint-features.js masterNav18) can show the same honest
  // error box instead of leaving a blank pane after a renderer crash.
  window.paneChunkError = function (pane, mode) { showError(pane, mode); };

  // ── Wrap the registry entries ────────────────────────────────────────
  //
  // The renderer may be async, and callers ignore the return value, so the
  // wrapper returns immediately after kicking off the load. The pane element
  // already exists (nav() creates it), so there is somewhere for the "loading"
  // state to live.
  function install() {
    var registry = window.MASTER_PANE_REGISTRY;
    if (!registry) return;

    Object.keys(manifest).forEach(function (pane) {
      var original = registry[pane];
      if (typeof original !== 'function') return;

      registry[pane] = function () {
        if (loaded[pane] && !failed[pane]) {
          // Already loaded: re-navigation (including the Retry button in the
          // error box, which calls nav(pane)). The same honesty rules apply
          // as on first load — a renderer that is missing or throws must not
          // leave a silently blank pane on THIS path either.
          try {
            var quick = original.apply(this, arguments);
            return quick === false ? showError(pane, 'broken') : quick;
          } catch (e) {
            console.warn('[chunks] renderer error for ' + pane + ':', e);
            return showError(pane, 'crashed');
          }
        }

        var self = this;
        var args = arguments;
        showPending(pane);
        return loadChunk(pane).then(function (ok) {
          clearPending(pane);
          if (!ok) { showError(pane); return; }
          delete failed[pane];
          try {
            var out = original.apply(self, args);
            // Registry entries follow the idiom
            //   `typeof window.X === 'function' && window.X()`
            // which evaluates to exactly `false` when the renderer symbol
            // never appeared — the chunk fetched 200 but failed to parse,
            // or the manifest points at a build that lacks it. Before this
            // check such a pane rendered as an empty shell: no content, no
            // error, no retry, just the nav chrome (verified live with a
            // corrupted chunk served over the real route).
            if (out === false) { showError(pane, 'broken'); return; }
          } catch (e) {
            // The renderer itself crashed while drawing. A console.warn
            // alone leaves a blank pane the user cannot distinguish from
            // an empty feature.
            console.warn('[chunks] renderer error for ' + pane + ':', e);
            showError(pane, 'crashed');
          }
        });
      };
    });
  }

  // ── Loading / error affordances ──────────────────────────────────────
  // Only shown if the fetch is slow enough to notice. On a fast connection the
  // chunk lands in a few milliseconds and flashing a spinner would look worse
  // than showing nothing.
  var pendingTimers = Object.create(null);

  function paneEl(pane) { return document.getElementById('pane-' + pane); }

  function showPending(pane) {
    var el = paneEl(pane);
    if (!el || el.dataset.chunkPending === '1') return;
    pendingTimers[pane] = setTimeout(function () {
      if (el.innerText.trim().length > 0) return;   // renderer already drew
      el.dataset.chunkPending = '1';
      var box = document.createElement('div');
      box.className = 'chunk-loading';
      box.setAttribute('role', 'status');
      box.setAttribute('aria-live', 'polite');
      box.textContent = 'Loading…';
      el.appendChild(box);
    }, 150);
  }

  function clearPending(pane) {
    clearTimeout(pendingTimers[pane]);
    var el = paneEl(pane);
    if (!el) return;
    delete el.dataset.chunkPending;
    var box = el.querySelector('.chunk-loading');
    if (box) box.remove();
  }

  function showError(pane, mode) {
    var el = paneEl(pane);
    if (!el) return;
    // Idempotent: the registry wrapper and a nav hook can both report the
    // same crash — one box, not a stack of them.
    if (el.querySelector('.chunk-error')) return;
    var box = document.createElement('div');
    box.className = 'chunk-error';
    box.setAttribute('role', 'alert');
    box.textContent =
      mode === 'broken'
        ? 'This section could not start — its code failed to load correctly. Your data is safe; this is a display problem. Try again, or reload the page.'
        : mode === 'crashed'
          ? 'This section went wrong while rendering. Your data is safe. Try again, or reload the page.'
          : 'Could not load this section. Check your connection, then try again.';
    var retry = document.createElement('button');
    retry.className = 'btn btn-sm btn-primary';
    retry.textContent = 'Retry';
    retry.addEventListener('click', function () {
      box.remove();
      if (typeof window.nav === 'function') window.nav(pane);
    });
    box.appendChild(retry);
    el.appendChild(box);
  }

  // ── Idle prefetch ────────────────────────────────────────────────────
  //
  // Boot stays as light as possible, then the remaining chunks are fetched
  // during idle time so the first click on any pane is instant. Prefetch is
  // skipped when the browser reports a slow or metered connection: pulling
  // 600 KB speculatively is exactly wrong on a capped mobile plan.
  function shouldPrefetch() {
    var c = navigator.connection;
    if (!c) return true;
    if (c.saveData) return false;
    return !/(^|-)2g$/.test(c.effectiveType || '');
  }

  function prefetchIdle() {
    if (!shouldPrefetch()) return;
    var panes = Object.keys(manifest).filter(function (p) { return !loaded[p]; });
    var i = 0;

    function next(deadline) {
      while (i < panes.length) {
        // Stop if this idle slice is used up; resume in the next one.
        if (deadline && deadline.timeRemaining && deadline.timeRemaining() <= 0
            && !deadline.didTimeout) break;
        var pane = panes[i++];
        if (!loaded[pane]) prefetch(pane);
      }
      if (i < panes.length) schedule(next);
    }
    schedule(next);
  }

  function schedule(fn) {
    if (typeof requestIdleCallback === 'function') requestIdleCallback(fn, { timeout: 4000 });
    else setTimeout(function () { fn(null); }, 400);
  }

  // Prefetch with <link rel=prefetch> rather than executing the script: it
  // warms the HTTP cache at low priority without running any code, so a
  // prefetched pane cannot have side effects on a user who never opens it.
  function prefetch(pane) {
    var url = chunkUrl(pane);
    if (!url) return;
    var link = document.createElement('link');
    link.rel = 'prefetch';
    link.as = 'script';
    link.href = url;
    document.head.appendChild(link);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      install();
      setTimeout(prefetchIdle, 1200);
    });
  } else {
    install();
    setTimeout(prefetchIdle, 1200);
  }
})();
