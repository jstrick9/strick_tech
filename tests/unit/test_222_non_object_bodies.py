"""Non-object JSON bodies must be answered, never crash the handler (round 29).

THE BUG
───────
request.json() accepts ANY JSON value — a bare string, number, list, bool,
null — and 79 handlers across 32 routers dereferenced `.get`/`.items` on the
result unconditionally. Verified live before the fix: POSTing the JSON string
"zzprobe" to 46 of them returned **500** with an AttributeError traceback
through the middleware stack (the round-28 a2a find was four instances of
this same class; the sweep found the rest). A dozen more silently substituted
an empty dict for malformed bodies — the pre-test_99 bug — creating junk
records with default names on broken client serialisation.

THE FIX
──────
Every raw `try: body = await req.json() except ...` idiom was converted to
the shared helper `json_body_or_error(req)` (services/request_body.py), which:
    no body at all        -> {}    (legitimate, keeps working)
    valid JSON object     -> parsed
    valid JSON non-object -> 400
    malformed JSON        -> 400

WHAT THIS LOCKS IN
──────────────────
The previously-crashing routes answer 400 to a non-object body — asserted
here in-process for the no-path-param subset (the param routes 404 on a
dummy id before the body is parsed, so they are covered by the conversion's
shared helper rather than a live probe).
"""
from __future__ import annotations

import pytest

# Every entry here returned HTTP 500 to a bare JSON string body before the
# round-29 conversion (probed live, 2026-09-15).
PREVIOUSLY_CRASHING = [
    ('POST', '/api/agent-identity/provision'),
    ('POST', '/api/agent-identity/token/validate'),
    ('POST', '/api/agent-monitor/shadow'),
    ('POST', '/api/audit-log/append'),
    ('POST', '/api/compliance/generate'),
    ('POST', '/api/docs/feedback'),
    ('POST', '/api/e2e/run'),
    ('POST', '/api/e2e/autofix'),
    ('POST', '/api/e2e/accessibility'),
    ('POST', '/api/e2e/performance'),
    ('POST', '/api/engine/execute'),
    ('POST', '/api/engine/fan-out'),
    ('POST', '/api/engine/map-reduce'),
    ('POST', '/api/engine/loops'),
    ('POST', '/api/engine/harness/test'),
    ('POST', '/api/engine/harness/benchmark'),
    ('POST', '/api/eval-framework/suites'),
    ('POST', '/api/eval-framework/run'),
    ('POST', '/api/finops/ledger/record'),
    ('POST', '/api/finops/caps'),
    ('POST', '/api/hub/review'),
    ('POST', '/api/license/activate'),
    ('POST', '/api/license/set-user'),
    ('POST', '/api/mcp-gateway/servers'),
    ('POST', '/api/mcp-gateway/call'),
    ('POST', '/api/mcp-gateway/policies'),
    ('POST', '/api/mcp-gateway/policies/simulate'),
    ('POST', '/api/mcp-gateway/policies/bulk'),
    ('POST', '/api/mcp-gateway/policies/from-template'),
    ('POST', '/api/memory/add'),
    ('POST', '/api/memory/add-with-embedding'),
    ('POST', '/api/memory/bulk-delete'),
    ('POST', '/api/memory/import'),
    ('POST', '/api/onboarding/quick-setup'),
    ('POST', '/api/plugins/install/url'),
    ('POST', '/api/plugins/install/json'),
    ('POST', '/api/profile/sidebar-order'),
    ('POST', '/api/profile/complete-onboarding'),
    ('POST', '/api/secrets/test-connection'),
    ('POST', '/api/sessions/auto-title'),
    ('POST', '/api/sessions/import-messages'),
    ('POST', '/api/skills/run'),
    ('POST', '/api/supervisor/run'),
    ('POST', '/api/system/open-url'),
    ('POST', '/api/workflow/import'),
    ('POST', '/api/workspace/import'),
    ('POST', '/api/tasks'),
    ('POST', '/api/tasks/bulk_update'),
    ('POST', '/api/kanban/move'),
    ('POST', '/api/chat/clear'),
]


@pytest.mark.parametrize('method,path', PREVIOUSLY_CRASHING)
def test_json_string_body_is_a_400_not_a_500(client, method, path):
    r = client.request(method, path, content=b'"zzprobe"',
                       headers={'Content-Type': 'application/json'})
    assert r.status_code != 500, (
        f'{method} {path} crashed on a non-object JSON body — the handler '
        'dereferences the parsed body without checking it is an object'
    )
    assert r.status_code == 400, (
        f'{method} {path} answered {r.status_code} to a non-object JSON body; '
        'expected the shared 400 Malformed request body response'
    )
    body = r.json()
    assert body.get('ok') is False


@pytest.mark.parametrize('raw', [b'[1,2,3]', b'null', b'42', b'true'])
def test_other_non_object_shapes_always_answered(client, raw):
    for path in ('/api/memory/add', '/api/engine/execute', '/api/tasks'):
        r = client.post(path, content=raw,
                        headers={'Content-Type': 'application/json'})
        assert r.status_code == 400, (
            f'{raw!r} to {path} -> {r.status_code}: must be the shared 400, '
            'not a crash or a silent default-record'
        )


def test_empty_body_still_means_empty_fields(client):
    """No body at all is legitimate: the helper returns {}, the handler's own
    field validation answers (not the body parser)."""
    r = client.post('/api/tasks', headers={'Content-Type': 'application/json'})
    assert r.status_code == 400
    assert 'title' in (r.json().get('error') or '').lower()


def test_malformed_json_is_still_a_400(client):
    r = client.post('/api/memory/add', content=b'not json at all',
                    headers={'Content-Type': 'application/json'})
    assert r.status_code == 400
    assert r.json().get('ok') is False
