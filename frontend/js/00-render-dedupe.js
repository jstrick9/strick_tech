// Agentic OS — render deduplication
//
// THE BUG
// ───────
// `window.nav` is wrapped 14 times across 10 files. Each wrapper calls the
// base nav and then re-invokes renderers that the base already ran through
// MASTER_PANE_REGISTRY:
//
//     window.nav = function masterNav19(pane) {
//       _base(pane);                                  // registry already ran it
//       if (pane === 'observability') renderObservability?.();   // again
//     };
//
// Measured in a live browser: **44 of 68 panes ran their renderer 2 or 3
// times for a single navigation.** Every duplicate refires that pane's API
// calls and rebuilds its DOM from scratch.
//
// It also silently destroyed the workstation feature. A host pane's renderer
// is usually async: it awaits fetches, then assigns `pane.innerHTML = ...`.
// nav() builds the workstation (tab strip + the absorbed panes moved inside)
// after the first render settles -- and then the *duplicate* render resolves
// and wipes all of it. 7 of the 11 workstations were destroyed on first open,
// removing 28 absorbed pane elements from the DOM entirely. That is what
// produced the "Cannot set properties of null" errors from renderSystem,
// renderControlTower, renderWebhooks and renderTestGen: their pane elements
// no longer existed.
//
// THE FIX
// ───────
// Rather than editing ~40 call sites across 14 wrappers -- the "second door"
// pattern this review has hit repeatedly, where one site gets fixed and the
// rest quietly do not -- each renderer is wrapped once so that within a
// single navigation it runs at most once. Wrappers added tomorrow are covered
// automatically.
//
// WHY A SHORT WINDOW AND NOT A PER-PANE FLAG
// ──────────────────────────────────────────
// Renderers are legitimately re-invoked later as refreshes: `renderSecretsVault()`
// after adding a secret, `renderEvals()` after creating a dataset. Those must
// still work. The nav cascade is entirely synchronous -- every wrapper calls
// the next one and then its own renderers in the same tick -- so suppression
// only needs to last until the end of that tick. A `setTimeout(..., 0)`
// closes the window, after which any call is treated as a genuine refresh.
'use strict';

(function () {
  var WRAPPED = '__renderDedupeWrapped';
  var active = null;   // Set of renderer names already run in this navigation

  // The suppression window lasts exactly one tick.
  //
  // The 14 nav() wrappers call each other and their duplicate renderers
  // synchronously, so a tick covers the whole cascade. It must NOT be
  // extended past that, and an attempt to do so was a real mistake worth
  // recording: holding the window open across nav()'s await -- so that
  // showWorkstationTab() would not "duplicate" the absorbed pane's render --
  // suppressed the render that actually matters and left 13 panes blank.
  //
  // That second render is legitimate, not a duplicate. When you open an
  // absorbed pane like `system`, the registry renders it first, then the
  // workstation HOST's async renderer replaces the host's innerHTML, and only
  // then is the pane moved into the rebuilt workstation and rendered again.
  // The first render's DOM no longer exists by that point. Suppressing the
  // second one leaves an empty tab.
  //
  // Keeping the window to one tick also keeps genuine refreshes working:
  // `renderSecretsVault()` after adding a secret, `renderEvals()` after
  // creating a dataset.
  function scheduleClose() {
    setTimeout(function () { active = null; }, 0);
  }

  window.beginNavRender = function () {
    // nav() is wrapped 14 times and the wrappers call each other, so this
    // runs several times for ONE user navigation. It must be idempotent, or
    // an inner wrapper resets the state the outer one is relying on.
    if (active) return;
    active = Object.create(null);
    scheduleClose();
  };

  function wrap(name) {
    var fn = window[name];
    if (typeof fn !== 'function' || fn[WRAPPED]) return;

    var wrapped = function () {
      if (active) {
        if (active[name]) {
          // Already rendered during this navigation. Returning the first
          // call's result keeps `await renderX()` callers working.
          return active[name].result;
        }
        var entry = { result: undefined };
        active[name] = entry;
        entry.result = fn.apply(this, arguments);
        return entry.result;
      }
      return fn.apply(this, arguments);
    };
    wrapped[WRAPPED] = true;
    wrapped.__original = fn;
    try {
      Object.defineProperty(wrapped, 'name', { value: name, configurable: true });
    } catch (e) { /* name is best-effort, for stack traces */ }
    window[name] = wrapped;
  }

  // Which globals are pane renderers? Read them out of the registry rather
  // than listing them here, so a new pane is covered without touching this
  // file.
  function rendererNames() {
    var registry = window.MASTER_PANE_REGISTRY || {};
    var names = {};
    Object.keys(registry).forEach(function (pane) {
      var source = String(registry[pane]);
      var re = /window\.([A-Za-z_$][\w$]*)/g;
      var m;
      while ((m = re.exec(source))) names[m[1]] = true;
    });
    return Object.keys(names);
  }

  // Idempotent, and safe to call again after a lazy chunk defines new
  // renderers (00-chunk-loader.js calls this after each chunk loads).
  window.installRenderDedupe = function () {
    rendererNames().forEach(wrap);
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', window.installRenderDedupe);
  } else {
    window.installRenderDedupe();
  }
})();
