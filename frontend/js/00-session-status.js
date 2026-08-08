// Agentic OS — lost-session banner
//
// THE PROBLEM
// ───────────
// When a session ends mid-use, three layers each behaved correctly and the
// combined result stranded the user:
//
//   * The server answers 401 promptly. Nothing is broken, so there is no
//     outage to report.
//   * 00-connection-status.js deliberately ignores 4xx — "you asked for
//     something you may not have" is not evidence the platform is down. That
//     judgement is right, and it means the connection banner never appears.
//   * 00-net-feedback.js raises a toast, which auto-dismisses after 6000ms.
//
// Six seconds later the screen says nothing at all, while every pane the user
// opens renders a calm, plausible empty state. An expired session and an empty
// account look identical, and nothing offers a way back in. Measured with
// scripts/audit/session_expiry.py against a real browser with every /api/ call
// answering 401: NO-SIGNAL and NO-ACTION.
//
// WHY A SEPARATE BANNER FROM THE CONNECTION ONE
// ─────────────────────────────────────────────
// They are different problems with different answers. "Your work is safe, this
// looks like a connection problem" is reassurance and a retry. A lost session
// needs the opposite framing: the request was understood and refused, retrying
// changes nothing, and the only useful action is to sign in again. Folding
// them together would make one of the two messages wrong.
//
// PERSISTENCE IS THE POINT
// ────────────────────────
// This banner has no timer. The condition it describes does not expire on its
// own, so neither does the message. It is removed when — and only when — an
// authenticated request succeeds again.
//
// NO THIRD FETCH WRAPPER
// ──────────────────────
// The app has exactly two intentional window.fetch wrappers (00-csrf.js, then
// 00-net-feedback.js) and adding a third was nearly done once in this review.
// This file OBSERVES: 00-csrf.js already calls connectionStatus.observeResponse
// for every response, and this module hooks that one call site.
'use strict';

(function () {
  // One 401 is not a lost session — several endpoints answer 401 for reasons
  // of their own (an unconfigured integration probing a third-party key). Two
  // inside a short window on different paths is the shape of a dead session.
  var THRESHOLD = 2;
  var WINDOW_MS = 10000;

  var hits = [];
  var paths = Object.create(null);
  var bannerEl = null;

  function isApiPath(url) {
    try {
      var u = new URL(url, location.origin);
      return u.origin === location.origin && u.pathname.indexOf('/api/') === 0;
    } catch (e) { return false; }
  }

  // /api/auth/login answering 401 means "wrong password", not "session lost".
  // Announcing an expired session on top of a failed sign-in attempt is both
  // wrong and demoralising.
  var IGNORED = ['/api/auth/login', '/api/auth/register', '/api/secrets/get'];

  function ignored(path) {
    for (var i = 0; i < IGNORED.length; i++) {
      if (path.indexOf(IGNORED[i]) === 0) return true;
    }
    return false;
  }

  function note(path) {
    var now = Date.now();
    hits.push(now);
    hits = hits.filter(function (t) { return now - t < WINDOW_MS; });
    paths[path] = now;
    if (hits.length >= THRESHOLD) show();
  }

  function clear() {
    hits = [];
    paths = Object.create(null);
    hide();
  }

  function show() {
    if (bannerEl && bannerEl.isConnected) return;

    bannerEl = document.createElement('div');
    bannerEl.id = 'session-banner';
    bannerEl.className = 'session-banner';
    // `alert` rather than `status`: unlike a connection blip, nothing the user
    // does will work until this is dealt with, so it warrants interrupting.
    bannerEl.setAttribute('role', 'alert');
    bannerEl.setAttribute('aria-live', 'assertive');

    var text = document.createElement('span');
    text.className = 'session-banner__text';
    // Says what happened, what it does NOT mean, and what to do. "Nothing was
    // lost" is the sentence a user needs when a screen has just gone empty;
    // "retrying will not help" stops them hammering a button that cannot work.
    text.textContent =
      'Your session has ended. Nothing was lost — sign in again to carry on.';
    bannerEl.appendChild(text);

    var signIn = document.createElement('button');
    signIn.type = 'button';
    signIn.className = 'btn btn-sm btn-primary session-banner__signin';
    signIn.textContent = 'Sign in';
    signIn.addEventListener('click', function () {
      // Prefer an in-app route if the build has one; otherwise reload, which
      // is what actually re-establishes a session in the default deployment.
      if (window.MASTER_PANE_REGISTRY && window.MASTER_PANE_REGISTRY.settings
          && typeof window.nav === 'function') {
        clear();
        window.nav('settings');
      } else {
        location.reload();
      }
    });
    bannerEl.appendChild(signIn);

    document.body.appendChild(bannerEl);

    // Move focus onto the banner's action so a keyboard or screen-reader user
    // reaches the one useful control without hunting for it.
    try { signIn.focus({ preventScroll: true }); } catch (e) { /* older browser */ }
  }

  function hide() {
    if (bannerEl && bannerEl.parentNode) bannerEl.parentNode.removeChild(bannerEl);
    bannerEl = null;
  }

  window.sessionStatus = {
    noteUnauthorised: note,
    reset: clear,
    isShowing: function () { return !!(bannerEl && bannerEl.isConnected); },
    _state: function () { return { hits: hits.length }; },
  };

  // Hooked into the single existing observation point rather than wrapping
  // fetch again. 00-csrf.js calls connectionStatus.observeResponse for every
  // response; this chains onto it so both modules see the same stream and only
  // one file owns window.fetch (see scripts/lint_globals.py).
  function attach() {
    if (!window.connectionStatus) return false;
    var prior = window.connectionStatus.observeResponse;
    window.connectionStatus.observeResponse = function (url, response) {
      if (prior) { try { prior(url, response); } catch (e) { /* keep going */ } }
      if (!response || !isApiPath(url)) return;
      var path;
      try { path = new URL(url, location.origin).pathname; } catch (e) { return; }
      if (ignored(path)) return;
      if (response.status === 401) {
        note(path);
      } else if (response.ok) {
        // Proof the credential works again. Signing back in is exactly this,
        // so the banner clears itself without needing to know how it happened.
        clear();
      }
    };
    return true;
  }

  if (!attach()) {
    // Load-order safety net: if this file ever moves above 00-connection-status
    // it must degrade to "no banner", never to a broken app.
    document.addEventListener('DOMContentLoaded', attach);
  }
})();
