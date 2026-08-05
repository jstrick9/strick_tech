// Agentic OS — network failure feedback
// ───────────────────────────────────────────────────────────────────────────
// THE PROBLEM THIS SOLVES
//
// The platform makes 673 fetch() calls. When one fails, the user is told
// nothing at all. Three separate mechanisms conspire to hide it:
//
//   1. 236 empty catch blocks — `.catch(() => {})` / `catch (e) {}`
//   2. window.onerror              deliberately logs and shows nothing
//   3. window.onunhandledrejection deliberately logs and shows nothing
//
// Both global handlers carry the comment "too noisy" — which was a fair call
// when the alternative was a toast per stack trace, but it means the product's
// answer to "the server is down" is that buttons stop working with no
// explanation. From the user's side a failed save and a successful save look
// identical. That is the worst possible failure mode: they carry on believing
// their work is stored.
//
// WHAT THIS DOES
//
// Wraps window.fetch once (after 00-csrf.js has wrapped it for tokens) and
// reports failures the user genuinely needs to know about:
//
//   * a transport failure (server down, DNS, offline)  -> "Can't reach ..."
//   * HTTP 5xx                                          -> "... failed"
//   * HTTP 401/403                                      -> auth/permission
//   * HTTP 429                                          -> rate limited
//
// It does NOT report 404 or 4xx generally: those are frequently probes the app
// makes on purpose ("does this optional resource exist?"), and surfacing them
// would recreate the noise the original authors were avoiding.
//
// DEDUPLICATION IS THE POINT
//
// The reason the naive version is unusable is that one broken backend produces
// dozens of identical toasts — polling loops fire every few seconds. Failures
// are therefore collapsed by (kind + endpoint) within a window, and a repeated
// failure updates a counter on the existing toast instead of adding another.
//
// The offline case is special-cased: when the browser reports no connectivity
// there is one honest message to show, and every individual endpoint failure
// underneath it is noise.
(function () {
  'use strict';

  var WINDOW_MS = 8000;      // collapse identical failures inside this window
  var MAX_TOASTS = 3;        // never stack more than this many at once
  var seen = Object.create(null);
  var activeCount = 0;

  // Endpoints whose failure is expected and must stay silent: liveness polling
  // and the CSP report sink would otherwise announce their own outage forever.
  var QUIET = [
    '/api/health',
    '/api/system/health',
    '/api/system/stats',
    '/api/security/csp-report',
    '/api/system/hmr',
  ];

  function isQuiet(url) {
    for (var i = 0; i < QUIET.length; i++) {
      if (url.indexOf(QUIET[i]) !== -1) return true;
    }
    return false;
  }

  function shortEndpoint(url) {
    try {
      var u = new URL(url, window.location.origin);
      var path = u.pathname;
      // Collapse ids so /api/goals/goal_abc123 and /api/goals/goal_def456
      // dedupe together — otherwise a failing list view floods the screen.
      path = path.replace(/\/[0-9a-f]{8,}\b/gi, '/…')
                 .replace(/\/\d+\b/g, '/…')
                 .replace(/\/[a-z]+_[A-Za-z0-9]{6,}\b/g, '/…');
      return path;
    } catch (_) {
      return String(url).slice(0, 60);
    }
  }

  function notify(kind, endpoint, message) {
    var key = kind + ' ' + endpoint;
    var now = Date.now();
    var prev = seen[key];

    if (prev && now - prev.at < WINDOW_MS) {
      prev.count++;
      prev.at = now;
      if (prev.node && prev.node.isConnected) {
        var badge = prev.node.querySelector('.net-fail-count');
        if (badge) badge.textContent = '×' + prev.count;
      }
      return;
    }

    if (activeCount >= MAX_TOASTS) return;

    seen[key] = { at: now, count: 1, node: null };
    seen[key].node = render(message, key);
  }

  function render(message, key) {
    var container = document.getElementById('toast-container');
    if (!container) {
      // No toast host yet (very early failure) — the console is the fallback,
      // but say so rather than pretending it was reported.
      console.error('[net]', message, '(no toast container yet)');
      return null;
    }

    var el = document.createElement('div');
    el.className = 'toast err';
    el.setAttribute('role', 'alert');
    el.setAttribute('aria-live', 'assertive');

    var text = document.createElement('span');
    text.textContent = message;

    // Stays empty until the failure actually repeats. Rendering "×1" on a
    // single occurrence reads as noise, and an unconditional "×" next to the
    // dismiss "×" is worse still — it looked like two close buttons.
    var count = document.createElement('span');
    count.className = 'net-fail-count';
    count.style.cssText = 'margin-left:8px;opacity:.7;font-variant-numeric:tabular-nums';
    count.textContent = '';

    var close = document.createElement('span');
    close.className = 'toast-close';
    close.setAttribute('role', 'button');
    close.setAttribute('tabindex', '0');
    close.setAttribute('aria-label', 'Dismiss');
    close.setAttribute('data-close', 'parent');
    close.setAttribute('data-keys', 'Enter,Space');
    close.setAttribute('data-self-click', '1');
    close.textContent = '×';

    // Order matters for screen readers and for visual scanning: message,
    // then how many times it happened, then the dismiss control last.
    el.appendChild(text);
    el.appendChild(count);
    el.appendChild(close);
    close.style.cssText = 'margin-left:auto;padding-left:10px;cursor:pointer';
    el.style.display = 'flex';
    el.style.alignItems = 'center';
    container.appendChild(el);
    activeCount++;

    if (typeof requestAnimationFrame === 'function') {
      requestAnimationFrame(function () { el.classList.add('show'); });
    } else {
      el.classList.add('show');
    }

    setTimeout(function () {
      el.classList.remove('show');
      setTimeout(function () {
        if (el.parentNode) el.remove();
        activeCount = Math.max(0, activeCount - 1);
        if (seen[key]) seen[key].node = null;
      }, 250);
    }, 6000);

    // Announce to screen readers where that helper exists.
    if (typeof window.announceToScreenReader === 'function') {
      window.announceToScreenReader(message);
    }
    return el;
  }

  // ── Offline handling ─────────────────────────────────────────────────────
  var offlineBanner = null;

  function showOffline() {
    if (offlineBanner && offlineBanner.isConnected) return;
    var el = document.createElement('div');
    el.id = 'net-offline-banner';
    el.setAttribute('role', 'status');
    el.setAttribute('aria-live', 'polite');
    el.style.cssText =
      'position:fixed;top:0;left:0;right:0;z-index:99999;padding:7px 14px;' +
      'text-align:center;font-size:12.5px;font-weight:600;' +
      'background:var(--warning,#e8a237);color:#1a1205';
    el.textContent = '⚠ You are offline — changes will not be saved until the connection returns.';
    document.body.appendChild(el);
    offlineBanner = el;
  }

  function hideOffline() {
    if (offlineBanner && offlineBanner.isConnected) offlineBanner.remove();
    offlineBanner = null;
  }

  window.addEventListener('offline', showOffline);
  window.addEventListener('online', function () {
    hideOffline();
    notifyOnce('back-online');
  });

  function notifyOnce(kind) {
    if (kind === 'back-online') {
      var container = document.getElementById('toast-container');
      if (!container) return;
      var el = document.createElement('div');
      el.className = 'toast ok';
      el.setAttribute('role', 'status');
      el.textContent = '✓ Back online';
      container.appendChild(el);
      if (typeof requestAnimationFrame === 'function') {
        requestAnimationFrame(function () { el.classList.add('show'); });
      } else { el.classList.add('show'); }
      setTimeout(function () {
        el.classList.remove('show');
        setTimeout(function () { el.remove(); }, 250);
      }, 2500);
    }
  }

  // ── The wrapper ──────────────────────────────────────────────────────────
  var inner = window.fetch.bind(window);

  // Layers on top of 00-csrf.js's wrapper. Load order matters: CSRF must be
  // the INNER layer so this sees the final status, after its one stale-token
  // retry, rather than a 403 it is about to resolve. Both delegate.
  // intentional-override: reporting layer above the CSRF fetch wrapper
  window.fetch = async function (input, init) {
    var url = '';
    try {
      url = typeof input === 'string' ? input : (input && input.url) || '';
    } catch (_) { url = ''; }

    var quiet = isQuiet(url);

    try {
      var response = await inner(input, init);

      if (!quiet && response) {
        var endpoint = shortEndpoint(url);
        if (response.status >= 500) {
          notify('5xx', endpoint, '⚠ Server error on ' + endpoint + ' — the action did not complete.');
        } else if (response.status === 429) {
          notify('429', endpoint, '⏳ Too many requests — slow down and retry in a moment.');
        } else if (response.status === 401) {
          notify('401', endpoint, '🔒 Not signed in — your session may have expired.');
        } else if (response.status === 403) {
          // The CSRF wrapper retries a stale token once before this is
          // reached, so a 403 here is a genuine refusal, not a race.
          notify('403', endpoint, '🚫 Not allowed — ' + endpoint + ' refused the request.');
        }
      }

      return response;
    } catch (err) {
      // Transport-level failure: server down, DNS, offline, CORS.
      if (!quiet) {
        if (typeof navigator !== 'undefined' && navigator.onLine === false) {
          showOffline();
        } else {
          notify('down', shortEndpoint(url),
            '⚠ Can\u2019t reach the server — check that Agentic OS is still running.');
        }
      }
      throw err;   // never swallow: callers that DO handle errors must still see them
    }
  };

  // Surface unhandled rejections that came from a fetch chain. The existing
  // handler in 00-errors.js deliberately stays silent to avoid noise; this one
  // reports only the network case, which is the one a user can act on.
  window.addEventListener('unhandledrejection', function (event) {
    var reason = event && event.reason;
    var text = reason && (reason.message || String(reason));
    if (!text) return;
    if (/fetch|network|Failed to fetch|NetworkError|load failed/i.test(text)) {
      notify('down', 'network',
        '⚠ A background request failed — some data on this screen may be stale.');
    }
  });

  // Exposed for tests.
  window.__netFeedback = {
    notify: notify,
    shortEndpoint: shortEndpoint,
    isQuiet: isQuiet,
    reset: function () {
      seen = Object.create(null);
      activeCount = 0;
      hideOffline();
    },
  };
})();
