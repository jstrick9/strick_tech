// Agentic OS — CSRF token attachment
// ───────────────────────────────────────────────────────────────────────────
// The server issued CSRF tokens and validated them, but the frontend never
// sent one. That combination is why the middleware read:
//
//     if csrf_token and csrf_token not in _CSRF_TOKENS:   # reject
//
// i.e. a request WITHOUT the header skipped validation entirely, because
// requiring it would have broken all 282 POST call sites. Verified against the
// running server before the fix:
//
//     POST /api/tasks  (no header)          -> 200
//     POST /api/tasks  (X-CSRF-Token: bogus) -> 403
//
// An attacker's forged cross-site request simply omits the header, so the
// control protected nobody while looking present.
//
// Rather than edit 282 call sites, window.fetch is wrapped once here: every
// same-origin state-changing request gets the token automatically. That also
// means a NEW call site is protected by default, which is the property the
// per-call-site arrangement lacked.
(function () {
  'use strict';

  const MUTATING = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
  let tokenPromise = null;
  let cachedToken = null;

  function readCookie(name) {
    const m = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
    return m ? decodeURIComponent(m[1]) : null;
  }

  async function getToken() {
    if (cachedToken) return cachedToken;
    // The server also sets a readable cookie; prefer it so a page reload does
    // not need a round trip.
    const fromCookie = readCookie('agentic_os_csrf');
    if (fromCookie) {
      cachedToken = fromCookie;
      return cachedToken;
    }
    if (!tokenPromise) {
      tokenPromise = originalFetch('/api/security/csrf-token', { credentials: 'same-origin' })
        .then(r => (r.ok ? r.json() : null))
        .then(d => {
          cachedToken = (d && (d.csrf_token || d.token)) || null;
          return cachedToken;
        })
        .catch(() => null)
        .finally(() => { tokenPromise = null; });
    }
    return tokenPromise;
  }

  // Requests identical in method, path and body inside this window are
  // treated as the same user intent. Long enough to absorb a double-click and
  // a retry; short enough that repeating an action deliberately still works.
  const IDEMPOTENCY_WINDOW_MS = 10000;

  // A short, stable, non-cryptographic digest. This only needs to avoid
  // accidental collisions between different requests from one browser tab,
  // not resist an attacker -- the server scopes every key by method and path
  // as well.
  function hashKey(text) {
    let h1 = 0x811c9dc5, h2 = 0x01000193;
    for (let i = 0; i < text.length; i++) {
      const c = text.charCodeAt(i);
      h1 = Math.imul(h1 ^ c, 0x01000193);
      h2 = Math.imul(h2 + c, 0x85ebca6b) ^ (h2 >>> 13);
    }
    return 'c-' + (h1 >>> 0).toString(36) + (h2 >>> 0).toString(36);
  }

  const originalFetch = window.fetch.bind(window);

  window.fetch = async function (input, init) {
    init = init || {};
    const method = (init.method || (typeof input === 'object' && input.method) || 'GET').toUpperCase();

    // Only same-origin mutations need a token. Cross-origin requests must not
    // receive it — that would leak the token to third parties, turning a CSRF
    // fix into a token-disclosure bug.
    let sameOrigin = true;
    try {
      const url = new URL(typeof input === 'string' ? input : input.url, window.location.origin);
      sameOrigin = url.origin === window.location.origin;
    } catch (_) { sameOrigin = true; }

    if (MUTATING.has(method) && sameOrigin) {
      const token = await getToken();
      const headers = new Headers(init.headers || (typeof input === 'object' ? input.headers : undefined) || {});
      if (token && !headers.has('X-CSRF-Token')) headers.set('X-CSRF-Token', token);

      // Idempotency: derive a key from the request itself so a double-click,
      // a retry, or the same action fired from two tabs collapses into ONE
      // record instead of five. Measured before this existed: 5 concurrent
      // identical POSTs to /api/specs created 5 specs.
      //
      // The key is a hash of method + path + body, bucketed to a short
      // window. Identical requests inside the window share a key and are
      // deduplicated by the server; the same action taken deliberately a
      // minute later gets a new key and is allowed through, which is what
      // keeps "create two identical items on purpose" possible.
      //
      // A caller that wants explicit control can set the header itself; this
      // never overwrites one.
      if (!headers.has('Idempotency-Key')) {
        try {
          const url = new URL(typeof input === 'string' ? input : input.url,
                              window.location.origin);
          let bodyText = '';
          if (typeof init.body === 'string') bodyText = init.body;
          const bucket = Math.floor(Date.now() / IDEMPOTENCY_WINDOW_MS);
          headers.set('Idempotency-Key',
                      hashKey(method + ' ' + url.pathname + ' ' + bodyText + ' ' + bucket));
        } catch (_) { /* a key is an optimisation; never block the request */ }
      }

      init = Object.assign({}, init, { headers, credentials: init.credentials || 'same-origin' });
    }

    const _requestUrl = (typeof input === 'string') ? input
                      : (input && input.url) ? input.url : '';

    let response;
    try {
      response = await originalFetch(input, init);
    } catch (err) {
      // Report network-level failures (offline, DNS, refused) to the
      // connection watcher, then rethrow untouched.
      if (window.connectionStatus && window.connectionStatus.observeNetworkError) {
        try { window.connectionStatus.observeNetworkError(_requestUrl); } catch (_) {}
      }
      throw err;
    }

    // A token can expire (24h TTL) or be dropped by a server restart, which
    // would otherwise surface as an unexplained 403 mid-session. Refresh once
    // and retry so the user never sees it.
    if (response.status === 403 && MUTATING.has(method) && sameOrigin) {
      let body = null;
      try { body = await response.clone().json(); } catch (_) { /* not JSON */ }
      if (body && typeof body.error === 'string' && body.error.toLowerCase().includes('csrf')) {
        cachedToken = null;
        const fresh = await getToken();
        if (fresh) {
          const headers = new Headers(init.headers || {});
          headers.set('X-CSRF-Token', fresh);
          response = await originalFetch(input, Object.assign({}, init, { headers }));
        }
      }
    }

    // This is the app's single fetch wrapper, so it is also where the
    // connection watcher learns whether requests are succeeding. Keeping the
    // observation here rather than adding a second window.fetch wrapper
    // means one owner for the global (see scripts/lint_globals.py).
    if (window.connectionStatus && window.connectionStatus.observeResponse) {
      try { window.connectionStatus.observeResponse(_requestUrl, response); } catch (_) {}
    }

    return response;
  };

  // Warm the cache so the first mutation does not pay a round trip.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { getToken(); });
  } else {
    getToken();
  }
})();
