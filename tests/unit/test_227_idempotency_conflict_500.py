"""The idempotency-conflict branch 500'd with UnboundLocalError.

_security_middleware had four function-local `from fastapi.responses import
JSONResponse` statements (secure-mode 401, rate-limit 429, CSRF 403 x2).
Any one of them makes the name function-local for the WHOLE scope, so the
idempotency-conflict branch — which runs before any of those imports
executes — referenced an unbound local and raised:

    UnboundLocalError: cannot access local variable 'JSONResponse'

The user-visible effect: two concurrent identical writes carrying the same
Idempotency-Key (a double-click, two tabs, a retry racing the original) got
a 500 instead of the intended 409 "already in progress". Caught live during
a pane-health sweep whose overlapping POSTs collided on a key.

The fix removes the four shadowing imports (the module-level import binds
everywhere). This test pins the conflict branch to its intended response.
"""

import pytest


@pytest.fixture
def conflict_state(monkeypatch):
    """Force the idempotency middleware onto the conflict path for any
    protected request carrying a key, without needing real concurrency."""
    from backend.services import idempotency

    monkeypatch.setattr(idempotency, 'begin', lambda key: ('conflict', None))


class TestIdempotencyConflictBranch:
    def test_conflict_is_409_with_reason_not_500(self, client, conflict_state):
        r = client.post(
            '/api/workspaces',
            json={'name': 'ZZ Conflict Probe'},
            headers={'Idempotency-Key': 'zz-conflict-key-38'},
        )
        assert r.status_code == 409, (
            f'conflict branch must answer 409, got {r.status_code}: {r.text[:200]}'
        )
        body = r.json()
        assert body.get('ok') is False
        assert 'already in progress' in (body.get('error') or '')
        assert r.headers.get('X-Request-ID'), 'tracing header must survive the branch'

    def test_conflict_takes_precedence_over_route_execution(self, client, conflict_state):
        """The middleware answers before the route runs — the workspace must
        NOT be created (that is the entire point of the 409)."""
        before = sorted(w['name'] for w in client.get('/api/workspaces').json())
        client.post(
            '/api/workspaces',
            json={'name': 'ZZ Conflict Probe'},
            headers={'Idempotency-Key': 'zz-conflict-key-38b'},
        )
        after = sorted(w['name'] for w in client.get('/api/workspaces').json())
        assert before == after, 'a conflicted double-write must not execute the route'

    def test_bare_name_is_bound_everywhere_in_the_middleware(self, client):
        """Sibling branches that used to carry their own local imports must
        still answer correctly (regression guard for the removal)."""
        from backend.app import _security_middleware
        import inspect

        src = inspect.getsource(_security_middleware)
        assert 'from fastapi.responses import JSONResponse' not in src.replace(
            'JSONResponse as _HostBlockedResponse', ''), (
            'a function-local JSONResponse import shadows the module-level '
            'name for the whole middleware scope and re-arms the foot-gun'
        )
