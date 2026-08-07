// Agentic OS — connection status banner
//
// THE PROBLEM
// ───────────
// 334 fetch sites across 33 files handle failure by yielding an empty
// collection:
//
//     fetch('/api/goals').then(r => r.ok ? r.json() : {goals: []}).catch(() => ({goals: []}))
//
// Each one is individually defensible -- the pane keeps rendering instead of
// throwing. Collectively they produce the worst possible outcome: a server
// outage is indistinguishable from "you have nothing yet". Verified in a real
// browser with every API returning 500, Goals, Skills and Loops all rendered
// calm, normal-looking empty states. Nothing on screen suggested the data was
// simply missing, so a user would reasonably conclude their work was gone.
//
// WHY A BANNER INSTEAD OF FIXING 334 CALL SITES
// ─────────────────────────────────────────────
// Rewriting every site means 334 edits across 33 files plus a matching change
// to each pane's empty-state renderer, with real regression risk and no way to
// stop the 335th from being written next week. Observing the transport
// instead covers every existing pane, every pane added later, and cannot
// break a render path because it never touches one.
//
// The per-pane inline message is still the better experience where it exists
// (see the Kanban board), so this is a safety net, not a substitute.
//
// WHAT IT DOES NOT DO
// ───────────────────
// It does not fire on a single failed request. Individual endpoints fail for
// ordinary reasons -- a feature that is not configured, an optional service
// that is not running -- and shouting about those would train users to ignore
// the banner. It appears when failures cluster, which is what an outage looks
// like.
'use strict';

(function () {
  // A burst of failures inside this window is treated as one incident.
  var WINDOW_MS = 8000;
  // Show the banner at this many failures within the window.
  var THRESHOLD = 3;
  // After the user dismisses, stay quiet this long.
  var SNOOZE_MS = 60000;

  var failures = [];      // timestamps of recent API failures
  var snoozedUntil = 0;
  var bannerEl = null;
  var lastPaths = [];

  function isApiPath(url) {
    try {
      var u = new URL(url, location.origin);
      if (u.origin !== location.origin) return false;
      return u.pathname.indexOf('/api/') === 0;
    } catch (e) { return false; }
  }

  // Endpoints whose failure is routine and not evidence of an outage.
  // /api/secrets/get 404s constantly when a key simply is not configured.
  var IGNORED = [
    '/api/secrets/get',
    '/api/security/csp-report',
  ];

  function ignored(path) {
    for (var i = 0; i < IGNORED.length; i++) {
      if (path.indexOf(IGNORED[i]) === 0) return true;
    }
    return false;
  }

  function record(path) {
    var now = Date.now();
    failures.push(now);
    lastPaths.push(path);
    if (lastPaths.length > 6) lastPaths.shift();
    failures = failures.filter(function (t) { return now - t < WINDOW_MS; });
    if (failures.length >= THRESHOLD && now >= snoozedUntil) show();
  }

  function clearFailures() {
    failures = [];
  }

  function show() {
    if (bannerEl) return;
    bannerEl = document.createElement('div');
    bannerEl.id = 'connection-banner';
    bannerEl.className = 'connection-banner';
    bannerEl.setAttribute('role', 'status');
    bannerEl.setAttribute('aria-live', 'polite');

    var text = document.createElement('span');
    text.className = 'connection-banner__text';
    // Deliberate wording: say what happened, say what it does NOT mean, and
    // give one obvious action. "Your data is safe" is the sentence a user
    // actually needs when a screen has just gone empty.
    text.textContent = 'Some data couldn\u2019t load. Your work is safe — this looks like a connection problem.';
    bannerEl.appendChild(text);

    var retry = document.createElement('button');
    retry.type = 'button';
    retry.className = 'btn btn-sm btn-primary connection-banner__retry';
    retry.textContent = '\u21bb Retry';
    retry.addEventListener('click', function () {
      clearFailures();
      hide();
      // Re-render the pane the user is actually looking at rather than
      // reloading the whole document, which would lose unsaved input.
      var active = document.querySelector('.pane.active, .ws-body.active');
      var pane = active && active.id ? active.id.replace(/^pane-/, '') : null;
      if (pane && typeof window.nav === 'function') window.nav(pane);
      else location.reload();
    });
    bannerEl.appendChild(retry);

    var dismiss = document.createElement('button');
    dismiss.type = 'button';
    dismiss.className = 'btn btn-sm btn-ghost connection-banner__dismiss';
    dismiss.setAttribute('aria-label', 'Dismiss connection warning');
    dismiss.textContent = '\u2715';
    dismiss.addEventListener('click', function () {
      snoozedUntil = Date.now() + SNOOZE_MS;
      clearFailures();
      hide();
    });
    bannerEl.appendChild(dismiss);

    document.body.appendChild(bannerEl);
  }

  function hide() {
    if (bannerEl && bannerEl.parentNode) bannerEl.parentNode.removeChild(bannerEl);
    bannerEl = null;
  }

  window.connectionStatus = {
    noteFailure: record,
    reset: function () { clearFailures(); hide(); },
    isShowing: function () { return !!bannerEl; },
    _state: function () { return { failures: failures.length, snoozedUntil: snoozedUntil }; },
  };

  // Observing the transport WITHOUT taking ownership of window.fetch.
  //
  // 00-csrf.js already wraps window.fetch to attach CSRF tokens. A second,
  // independent wrapper here meant two files owned the same global -- caught
  // by scripts/lint_globals.py, and rightly: whichever loads last silently
  // decides the behaviour, and un-wrapping in tests becomes order-dependent.
  //
  // So the single existing wrapper reports outcomes here instead. If that
  // wrapper is ever removed, this degrades to "no banner" rather than to a
  // broken app.
  window.connectionStatus.observeResponse = function (url, response) {
    if (!isApiPath(url)) return;
    var path;
    try { path = new URL(url, location.origin).pathname; } catch (e) { return; }
    if (ignored(path)) return;
    // 5xx is a server fault. 4xx usually means the client asked for something
    // that legitimately is not there, so it is not counted -- except 429/408,
    // which mean "try again".
    if (response.status >= 500 || response.status === 429 || response.status === 408) {
      record(path);
    } else if (response.ok) {
      // A success means we are not in an outage; stop accumulating so that
      // unrelated failures spread over time never add up to a false alarm.
      clearFailures();
    }
  };

  window.connectionStatus.observeNetworkError = function (url) {
    if (isApiPath(url)) record(url);
  };

  // The browser's own signal is more reliable than counting, when present.
  window.addEventListener('offline', function () {
    failures = [Date.now(), Date.now(), Date.now()];
    if (Date.now() >= snoozedUntil) show();
  });
  window.addEventListener('online', function () {
    clearFailures();
    hide();
  });
})();
