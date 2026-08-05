// Agentic OS — mobile navigation drawer
// ───────────────────────────────────────────────────────────────────────────
// THE BUG
//
// Both stylesheets that actually load (styles-unified.css:1258 and
// styles-redesign.css:595) contained the same line:
//
//     @media (max-width: 768px) { #sidebar { display: none !important; } }
//
// and nothing else was ever built to replace it. Measured in Chromium at
// 390x844 and at 768x1024: `#sidebar` computes to `display:none`, width 0,
// height 0, and the 28 `.nav-item` elements inside it are all zero-sized and
// unclickable. `#sidebar-toggle-btn` is a child of the sidebar, so it is
// hidden too — there was no control anywhere on the page capable of bringing
// it back.
//
// Net effect: on any phone, and on a tablet in portrait, the entire product
// collapsed to a single pane. Chat, Code Studio, Memory, Tasks, Settings and
// 23 other destinations had no reachable entry point at all. Not "awkward on
// mobile" — genuinely unreachable, including for keyboard and screen-reader
// users, since `display:none` removes the subtree from the a11y tree too.
//
// THE FIX
//
// Standard drawer pattern, the one ChatGPT and Claude both use:
//   • A hamburger button in the topbar, shown only at <=768px.
//   • The sidebar becomes a fixed overlay drawer, translated off-canvas,
//     slid in when `body.mobile-nav-open` is set.
//   • A scrim behind it that closes on click.
//   • Escape closes it; focus moves into the drawer on open and returns to
//     the hamburger on close.
//   • Choosing a destination closes it — on a phone the drawer covers the
//     content you just navigated to, so leaving it open hides the result.
//   • `inert` + `aria-hidden` while closed, so the 28 items are not in the
//     tab order or the a11y tree when off-canvas. This is why the drawer is
//     translated rather than `display:none`d: it animates, and `inert` gives
//     the same a11y semantics without killing the transition.
//
// The desktop collapse button (`toggleSidebar`) is untouched and still hidden
// under 768px, where a 56px icon rail is not a useful mode.
(function () {
  'use strict';

  var MOBILE_MAX = 768;
  var OPEN_CLASS = 'mobile-nav-open';
  var lastFocus = null;

  function isMobile() {
    return window.matchMedia('(max-width: ' + MOBILE_MAX + 'px)').matches;
  }

  function sidebar() { return document.getElementById('sidebar'); }
  function burger() { return document.getElementById('mobile-nav-btn'); }

  function isOpen() {
    return document.body.classList.contains(OPEN_CLASS);
  }

  // While closed on mobile the drawer must be out of the tab order. On desktop
  // it must never be inert, or the whole nav goes dead — that would be a much
  // worse bug than the one this file fixes, so the desktop branch is explicit.
  function syncInert() {
    var sb = sidebar();
    if (!sb) return;
    var hide = isMobile() && !isOpen();
    if (hide) {
      sb.setAttribute('inert', '');
      sb.setAttribute('aria-hidden', 'true');
    } else {
      sb.removeAttribute('inert');
      sb.removeAttribute('aria-hidden');
    }
    var b = burger();
    if (b) b.setAttribute('aria-expanded', isOpen() ? 'true' : 'false');
  }

  function openNav() {
    if (!isMobile() || isOpen()) return;
    lastFocus = document.activeElement;
    document.body.classList.add(OPEN_CLASS);
    syncInert();
    // Focus the DRAWER, not the first row.
    //
    // The obvious version of this — `document.querySelector('#sidebar
    // .nav-item').focus()` — opened the drawer and closed it again in the same
    // tick, measured in Chromium: classList.add('mobile-nav-open') ran, then
    // body.className came back ''. The nav rows are `div[role="button"]`, and
    // focusing one causes Chromium to deliver a click to it, which hit the
    // close-on-navigate listener below. Landing focus on the container gives
    // screen-reader and keyboard users the same entry point with nothing
    // activatable underneath it.
    var sb = sidebar();
    if (sb && typeof sb.focus === 'function') {
      if (!sb.hasAttribute('tabindex')) sb.setAttribute('tabindex', '-1');
      try { sb.focus(); } catch (e) { /* detached node */ }
    }
  }

  function closeNav(restoreFocus) {
    if (!isOpen()) return;
    document.body.classList.remove(OPEN_CLASS);
    syncInert();
    if (restoreFocus !== false) {
      var b = burger();
      // `lastFocus` is whatever had focus when the drawer opened, but two
      // cases must NOT be restored to, both measured: it is `<body>` (nothing
      // was focused, so restoring there drops the user at the top of the
      // document with no visible focus ring), or it is inside the drawer
      // itself (about to become `inert`, so focus would be discarded). Either
      // way the hamburger is the correct place to land — it is the control
      // that owns the drawer.
      var sb = sidebar();
      var bad = !lastFocus ||
        !document.contains(lastFocus) ||
        lastFocus === document.body ||
        (sb && sb.contains(lastFocus));
      var target = bad ? b : lastFocus;
      if (target && typeof target.focus === 'function') {
        try { target.focus(); } catch (e) { /* detached node */ }
      }
    }
    lastFocus = null;
  }

  window.toggleMobileNav = function () {
    if (isOpen()) closeNav(); else openNav();
  };
  window.closeMobileNav = function () { closeNav(); };

  function injectButton() {
    if (document.getElementById('mobile-nav-btn')) return;
    var bar = document.getElementById('topbar');
    if (!bar) return;
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.id = 'mobile-nav-btn';
    btn.className = 'icon-btn';
    btn.setAttribute('aria-label', 'Open navigation menu');
    btn.setAttribute('aria-controls', 'sidebar');
    btn.setAttribute('aria-expanded', 'false');
    btn.title = 'Navigation';
    // The delegation shim (00-delegate.js) handles this; no inline handler,
    // so it survives the enforcing CSP with no 'unsafe-inline' in script-src.
    btn.setAttribute('data-act-click', 'toggleMobileNav()');
    btn.textContent = '☰';
    bar.insertBefore(btn, bar.firstChild);
  }

  function injectScrim() {
    if (document.getElementById('mobile-nav-scrim')) return;
    var s = document.createElement('div');
    s.id = 'mobile-nav-scrim';
    s.setAttribute('data-act-click', 'closeMobileNav()');
    // Purely decorative: the drawer already has an Escape handler and the
    // hamburger toggles it, so the scrim needs no a11y role of its own.
    s.setAttribute('aria-hidden', 'true');
    document.body.appendChild(s);
  }

  function init() {
    injectButton();
    injectScrim();
    syncInert();

    // Navigating closes the drawer. Capture phase so it runs whatever the
    // nav handler does, and it must not fire for the group headers, which
    // expand/collapse in place rather than navigating.
    document.addEventListener('click', function (ev) {
      if (!isOpen()) return;
      var t = ev.target;
      if (!t || typeof t.closest !== 'function') return;
      if (t.closest('#sidebar .nav-item')) closeNav(false);
    }, true);

    // Capture phase. In the bubble phase this handler was measured NOT to fire
    // for an Escape dispatched at `document` — the app already installs
    // capture-phase Escape handling (00-delegate.js closes the topmost
    // dialog), and whichever handler runs first can stop the event before a
    // bubble-phase document listener ever sees it. Capturing makes the drawer
    // respond to Escape deterministically instead of depending on listener
    // registration order.
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape' && isOpen()) {
        ev.stopPropagation();
        closeNav();
      }
    }, true);

    // Rotating a phone to landscape crosses the breakpoint. Leaving the body
    // class set there would apply drawer positioning to a desktop layout.
    var mq = window.matchMedia('(max-width: ' + MOBILE_MAX + 'px)');
    var onChange = function () {
      if (!isMobile()) document.body.classList.remove(OPEN_CLASS);
      syncInert();
    };
    if (typeof mq.addEventListener === 'function') mq.addEventListener('change', onChange);
    else if (typeof mq.addListener === 'function') mq.addListener(onChange);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
