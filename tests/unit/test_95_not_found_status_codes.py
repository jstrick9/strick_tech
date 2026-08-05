"""A missing resource must answer 404, not 200 with an error body.

THE PATTERN
───────────
24 GET/DELETE endpoints answered a request for a resource that does not exist
with:

    HTTP 200
    {"ok": false, "error": "Agent not found"}

This is the "HTTP 200 on failure" shape this review has already corrected in
roughly 150 endpoints elsewhere; these were the stragglers. It matters more
now than it did before, for a concrete reason: `frontend/js/00-net-feedback.js`
reports failures to the user by inspecting the STATUS. A 200 is success, so a
missing resource produced no error, no message, and a silently blank screen.

`if (r.ok)` — the idiomatic check every caller uses — is also true for these,
as are HTTP caches, proxies and uptime monitoring.

The body is unchanged, so any caller already reading `data.error` keeps
working. Only the status is now honest.

WHAT THIS FOUND
Three tests were passing against endpoints that DO NOT EXIST. They were green
only because `/{param}` matched the literal segment and returned 200:

    /api/marketplace/search      (search is a query param on the collection)
    /api/marketplace/installed   (the route is /installed/list)
    /api/integrations/list       (the collection is the bare path)

A fourth, test_nonexistent_run, asserted `status_code == 200` for a missing
run outright — a test pinning the bug in place.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ROUTERS = ROOT / 'backend' / 'routers'

# One representative per router that was converted.
NOT_FOUND_ROUTES = [
    '/api/agents/zzz_no_such_thing',
    '/api/specs/zzz_no_such_thing',
    '/api/skills/zzz_no_such_thing',
    '/api/hooks/zzz_no_such_thing',
    '/api/marketplace/zzz_no_such_thing',
    '/api/replay/runs/zzz_no_such_thing',
    '/api/observability/traces/zzz_no_such_thing',
    '/api/evals/runs/zzz_no_such_thing',
    '/api/evals/datasets/zzz_no_such_thing',
    '/api/control/runs/zzz_no_such_thing',
    '/api/collab/sessions/zzz_no_such_thing',
    '/api/pluginsdk/packs/zzz_no_such_thing',
    '/api/integrations/zzz_no_such_thing',
    '/api/ambient/tasks/zzz_no_such_thing',
    '/api/bugbot/reviews/zzz_no_such_thing',
    '/api/arena/battles/zzz_no_such_thing',
]


@pytest.mark.parametrize('path', NOT_FOUND_ROUTES)
def test_missing_resource_returns_404(client, path):
    r = client.get(path)
    assert r.status_code == 404, (
        f'{path} answered {r.status_code} for a resource that does not exist. '
        f'A 200 makes `if (r.ok)` true and hides the failure from the '
        f'frontend error reporter, producing a blank screen with no message.'
    )


@pytest.mark.parametrize('path', NOT_FOUND_ROUTES)
def test_the_error_body_is_preserved(client, path):
    """Callers already reading `data.error` must keep working — only the
    status changed."""
    body = client.get(path).json()
    assert body.get('ok') is False
    assert body.get('error'), f'{path} lost its error message'


# ══ The collection routes must still work ═════════════════════════════════════
@pytest.mark.parametrize('path', [
    '/api/agents',
    '/api/specs',
    '/api/skills',
    '/api/hooks',
    '/api/marketplace',
    '/api/integrations',
    '/api/marketplace/installed/list',
    '/api/marketplace/stats/overview',
])
def test_collection_and_namespaced_routes_still_return_200(client, path):
    """Guards the real risk of this change: converting a lookup to 404 must not
    catch a literal segment that shares the prefix. Verified live for each."""
    assert client.get(path).status_code == 200


def test_a_real_lookup_still_succeeds(client):
    agents = client.get('/api/agents').json()
    items = agents if isinstance(agents, list) else agents.get('agents', [])
    assert items, 'no agents seeded — cannot verify the success path'
    r = client.get(f'/api/agents/{items[0]["id"]}')
    assert r.status_code == 200
    assert r.json().get('ok') is True


# ══ Keep the pattern from coming back ═════════════════════════════════════════
BARE_NOT_FOUND = re.compile(
    r"^\s*return\s*\{'ok':\s*False,\s*'error':\s*[^}]*?(?:not\s+found|not\s+in\s+registry)[^}]*\}\s*$",
    re.I,
)
ROUTE_DECORATOR = re.compile(r"^\s*@router\.(get|post|put|patch|delete)\(")


def _enclosing_verb(lines: list[str], idx: int) -> str | None:
    for i in range(idx, -1, -1):
        m = ROUTE_DECORATOR.match(lines[i])
        if m:
            return m.group(1)
    return None


def test_no_get_or_delete_handler_returns_a_bare_not_found():
    """The CI half of this fix. Without it the next hand-written lookup goes
    back to 200, and it will be invisible again — that is exactly how these 24
    accumulated after ~150 were already corrected."""
    offenders = []
    for path in sorted(ROUTERS.glob('*.py')):
        lines = path.read_text(encoding='utf-8').split('\n')
        for i, line in enumerate(lines):
            if not BARE_NOT_FOUND.match(line):
                continue
            verb = _enclosing_verb(lines, i)
            if verb in ('get', 'delete'):
                offenders.append(f'{path.name}:{i + 1} {line.strip()[:80]}')

    assert not offenders, (
        'GET/DELETE handlers returning "not found" with an implicit HTTP 200:\n  '
        + '\n  '.join(offenders[:20])
        + '\n\nUse JSONResponse({...}, status_code=404) so the failure is '
          'visible to `r.ok`, to the frontend error reporter, and to caches.'
    )
