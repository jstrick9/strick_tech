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
      if (token) {
        const headers = new Headers(init.headers || (typeof input === 'object' ? input.headers : undefined) || {});
        if (!headers.has('X-CSRF-Token')) headers.set('X-CSRF-Token', token);
        init = Object.assign({}, init, { headers, credentials: init.credentials || 'same-origin' });
      }
    }

    let response = await originalFetch(input, init);

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

    return response;
  };

  // Warm the cache so the first mutation does not pay a round trip.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { getToken(); });
  } else {
    getToken();
  }
})();
