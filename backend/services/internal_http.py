"""HTTP client for the server's calls to its OWN API.

THE PROBLEM
───────────
Three routes reach their own API over the loopback interface rather than
calling the handler directly:

    goal_manager  /api/goals/{id}/launch -> POST /api/supervisor/run
    mcp_gateway   tool dispatch          -> POST /api/mcp/call
    mcp_gateway   HITL gate              -> POST /api/hitl/interrupt

Turning CSRF enforcement on by default broke all three: the server started
rejecting its own requests with 403, because a plain httpx client sends no
token. Symptom was `POST /api/goals/{id}/launch` returning
`{"ok": false, "error": "CSRF token required."}` — a real production failure,
not a test artefact. It surfaced through 12 failing tests, which is the value
of having them.

THE FIX, AND WHY IT IS NOT A BYPASS
───────────────────────────────────
The obvious shortcut would be to exempt loopback source addresses from CSRF.
That is NOT done here, and the distinction matters: a request from 127.0.0.1
is not necessarily trustworthy. Any local process — a malicious npm postinstall
script, another container sharing the network namespace, a browser extension
proxying through a local port — can originate one. Exempting the address would
convert CSRF from "prove you are the app" into "prove you are on this machine",
which is a much weaker claim and would silently undo the control for the exact
attacker who has already gained a local foothold.

Instead the internal caller mints a REAL token from the same store the token
endpoint uses, in-process, and sends it like any other client. The security
property is unchanged: possession of a token still proves the caller could read
it from this process, which a cross-site attacker cannot do. No new trust
relationship is introduced and no branch is added to the middleware.

LONGER TERM
───────────
Loopback HTTP for an in-process call is the underlying smell — it doubles the
request cost, loses the exception type, and makes the call invisible to the
tracing that wraps direct calls. Replacing these three with direct handler
invocations is the right end state, but it changes control flow in the
supervisor and MCP paths, so it is a separate change with its own tests rather
than something to fold into a CSRF commit.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

_HEADER = 'X-CSRF-Token'


def base_url() -> str:
    port = os.getenv('AGENTIC_OS_PORT', '8787')
    return f'http://127.0.0.1:{port}'


def mint_token() -> str:
    """Create a CSRF token directly in the issuing store.

    An in-process dict write, not an HTTP round trip — calling the token
    endpoint over loopback to satisfy loopback CSRF would be circular.
    """
    import secrets

    from ..routers.security import _CSRF_TOKENS

    token = secrets.token_urlsafe(32)
    _CSRF_TOKENS[token] = time.time()
    return token


_cached_token: str | None = None
_cached_at: float = 0.0
# Well inside the server's 24h TTL, short enough that a restart self-heals.
_CACHE_SECONDS = 300.0


def _fetch_token_over_http() -> str | None:
    """Ask the listening server for a token.

    Needed when the process making the loopback call is NOT the process
    serving it. That is not hypothetical: under the in-process TestClient
    suites, the app object under test mints into its own `_CSRF_TOKENS` while
    the loopback POST travels over TCP to a separately-started server with a
    different store, so the minted token is rejected as invalid.

    It is the same per-process-state problem this whole change is about, just
    appearing inside the app instead of between workers.
    """
    try:
        with httpx.Client(base_url=base_url(), timeout=5) as c:
            r = c.get('/api/security/csrf-token')
            if r.status_code == 200:
                return r.json().get('csrf_token')
    except Exception:
        pass
    return None


def headers() -> dict[str, str]:
    """A token the LISTENING server will accept.

    Prefer one issued by that server, because it is the one that has to
    validate it. Fall back to minting locally when it cannot be reached — in
    the normal single-process case both paths hit the same dict, so the
    fallback is equivalent and avoids a round trip becoming a hard dependency.
    """
    global _cached_token, _cached_at

    now = time.time()
    if _cached_token is not None and now - _cached_at < _CACHE_SECONDS:
        return {_HEADER: _cached_token}

    # Cached because the first version fetched on EVERY internal call. That
    # added a synchronous round trip to each MCP dispatch and supervisor
    # launch: the full suite went from 165s to 437s, and two concurrency tests
    # began failing outright. A token is reusable until it expires, so
    # re-fetching per call bought nothing.
    token = _fetch_token_over_http()
    if token is None:
        token = mint_token()
    _cached_token, _cached_at = token, now
    return {_HEADER: token}


def _invalidate_cache() -> None:
    """Drop the cached token, e.g. after a server restart. Used by tests."""
    global _cached_token, _cached_at
    _cached_token, _cached_at = None, 0.0


def async_client(**kwargs: Any) -> httpx.AsyncClient:
    """An AsyncClient pre-configured for calls to this server's own API."""
    kwargs.setdefault('base_url', base_url())
    kwargs.setdefault('timeout', 10)
    existing = dict(kwargs.pop('headers', {}) or {})
    existing.update(headers())
    return httpx.AsyncClient(headers=existing, **kwargs)
