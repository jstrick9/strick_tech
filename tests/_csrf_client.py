"""Shared CSRF-aware httpx clients for the suites that drive a LIVE server.

WHY THIS EXISTS
───────────────
CSRF enforcement is now ON by default for a single-worker deployment. The
in-process `TestClient` suites are unaffected — the middleware skips CSRF when
`PYTEST_CURRENT_TEST` is set, and that variable is present in their process.

The UAT / system / integration / regression / security / gap suites are
different: they talk to a server started separately, over real HTTP. That
server has no `PYTEST_CURRENT_TEST` in its own environment, so the exemption
does not apply to it — correctly, because from its point of view those suites
are ordinary scripted API clients.

When the default was flipped, 479 tests failed for exactly that reason. That
was not a bug in the flip; it was the flip working, and it is precisely the
"scripted clients will break" scenario the rollout plan predicted. The right
response is the one a real operator would take — fetch a token and send it —
not to switch enforcement back off or to special-case the tests.

Keeping the fetch-and-attach logic here rather than disabling CSRF for tests
also means the suites exercise the enforced path, so a regression in token
issuance or validation shows up as a test failure instead of being masked.
"""

from __future__ import annotations

from typing import Any

import httpx

_MUTATING = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})
_HEADER = 'X-CSRF-Token'


def fetch_token(base_url: str, *, timeout: float = 10.0) -> str | None:
    """Get a CSRF token from a running server. None if unavailable."""
    try:
        with httpx.Client(base_url=base_url, timeout=timeout) as c:
            r = c.get('/api/security/csrf-token')
            if r.status_code != 200:
                return None
            return r.json().get('csrf_token')
    except Exception:
        return None


class _CSRFAuth(httpx.Auth):
    """Attach the token to mutating requests, refreshing once on a 403.

    Implemented as an httpx.Auth rather than an event hook because a hook
    cannot retry a request. The token has a 24h TTL and is dropped by a server
    restart, both of which happen during a long suite run.
    """

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url
        self._token: str | None = None

    def _ensure(self) -> str | None:
        if self._token is None:
            self._token = fetch_token(self._base_url)
        return self._token

    def auth_flow(self, request: httpx.Request):
        if request.method.upper() not in _MUTATING:
            yield request
            return

        token = self._ensure()
        if token:
            request.headers[_HEADER] = token

        response = yield request

        # A stale token surfaces as a 403 naming CSRF. Refresh once and retry
        # so a server restart mid-run does not cascade into dozens of failures.
        if response.status_code == 403 and token is not None:
            try:
                body = response.json()
            except Exception:
                body = {}
            if 'csrf' in str(body.get('error', '')).lower():
                self._token = None
                fresh = self._ensure()
                if fresh:
                    request.headers[_HEADER] = fresh
                    yield request


def csrf_auth(base_url: str) -> httpx.Auth:
    return _CSRFAuth(base_url)


def client(base_url: str, **kwargs: Any) -> httpx.Client:
    """A sync httpx.Client that satisfies CSRF automatically."""
    kwargs.setdefault('auth', csrf_auth(base_url))
    return httpx.Client(base_url=base_url, **kwargs)


def async_client(base_url: str, **kwargs: Any) -> httpx.AsyncClient:
    """An async httpx.AsyncClient that satisfies CSRF automatically."""
    kwargs.setdefault('auth', csrf_auth(base_url))
    return httpx.AsyncClient(base_url=base_url, **kwargs)
