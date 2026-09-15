"""
A2A protocol door — the CSRF boundary, verified against a LIVE server.

WHY A SEPARATE FILE
───────────────────
The unit suite runs in-process, and the CSRF middleware deliberately skips
enforcement while PYTEST_CURRENT_TEST is set — so no in-process test can
ever observe a 403. The boundary can only be tested against a separately
started server (recipe in conftest.py).

THE BUG THIS LOCKS IN AS FIXED
──────────────────────────────
Round 28: the entire /a2a/ JSON-RPC surface sat behind the CSRF wall. A2A
callers are OTHER PLATFORMS' agents — the protocol has no browser-session
step, so an external agent cannot fetch a token first. Every inbound task
submission died with 403 "CSRF token required", verified live by delegating
to this platform's own agent as a remote (the delegate's server-side POST
was refused by its own middleware).

The door is now exempt. Browser CSRF stays structurally blocked without the
token check: a cross-site fetch with a JSON content type must pass a CORS
preflight (the origin allowlist admits only the known frontend hosts), and
a plain HTML form POST cannot produce a JSON body (the handler answers
-32700 Invalid JSON).

The exemption must be surgical: only /a2a/*. The /api/a2a/* management
endpoints (register/list/delete/delegate) are the LOCAL browser's API and
keep demanding the token.
"""
from __future__ import annotations

import httpx
import pytest

BASE = "http://127.0.0.1:8787"


def _post(path: str, content: bytes, ctype: str = 'application/json'):
    return httpx.post(
        BASE + path, content=content,
        headers={'Content-Type': ctype}, timeout=20,
    )


@pytest.mark.parametrize('body', [
    b'"jsonrpc=2.0"',          # bare JSON string (a real client bug seen live)
    b'[1, 2, 3]',              # JSON array
    b'null',                   # JSON null
])
def test_non_object_json_is_answered_in_protocol_not_a_500(body):
    """request.json() accepts any JSON value; the handler must not 500."""
    r = _post('/a2a/researcher', body)
    assert r.status_code == 400, f'{body!r}: expected in-protocol 400, got {r.status_code}: {r.text[:120]}'
    err = r.json().get('error', {})
    assert err.get('code') == -32600, err


def test_tokenless_jsonrpc_reaches_the_handler():
    """The door is open to machines: no 403, and a JSON-RPC answer comes back."""
    r = _post('/a2a/researcher', b'{"jsonrpc":"2.0","id":1,"method":"tasks/get","params":{}}')
    assert r.status_code != 403, (
        '/a2a/ is behind the CSRF wall again — external A2A agents have no '
        'browser session and cannot fetch a token, so the protocol door is dead'
    )
    body = r.json()
    assert body.get('jsonrpc') == '2.0', f'not a JSON-RPC response: {body}'
    # tasks/get with no id → -32602 invalid params, i.e. the handler ran.
    assert body.get('error', {}).get('code') == -32602


def test_agent_card_discovery_is_reachable():
    """The protocol's entry point: card fetch is a GET, must always serve."""
    r = httpx.get(BASE + '/a2a/researcher/.well-known/agent.json', timeout=20)
    assert r.status_code == 200, r.text[:120]
    card = r.json()
    assert card.get('name'), card


def test_form_encoded_body_is_a_parse_error_not_a_csrf_rejection():
    """An HTML form (the CSRF attack shape) can never produce valid JSON."""
    r = _post(
        '/a2a/researcher', b'jsonrpc=2.0&method=tasks/send',
        ctype='application/x-www-form-urlencoded',
    )
    assert r.status_code == 400
    assert r.json().get('error', {}).get('code') == -32700


def test_ordinary_api_writes_still_require_the_token():
    """The exemption must not leak onto the general API surface."""
    r = _post('/api/tasks', b'{"title": "zz-sec-door-probe"}')
    assert r.status_code == 403, (
        f'/api/tasks accepted a tokenless write ({r.status_code}) — the /a2a/ '
        'exemption has leaked onto the ordinary API surface'
    )
    assert 'CSRF' in r.json().get('error', '')


def test_a2a_management_endpoints_still_require_the_token():
    """/api/a2a/* is the LOCAL browser's management API — token required."""
    r = _post('/api/a2a/agents', b'{"name": "zz-door", "a2a_url": "http://127.0.0.1:9/a2a/x"}')
    assert r.status_code == 403, (
        f'/api/a2a/agents accepted a tokenless registration ({r.status_code}) '
        '— management endpoints must keep the CSRF check'
    )
    assert 'CSRF' in r.json().get('error', '')
