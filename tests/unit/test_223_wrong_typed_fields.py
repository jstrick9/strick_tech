"""Wrong-typed fields must never 500 — the numeric-coercion class (round 30).

THE BUG
───────
`int(body.get('latency_ms', 0))` with {"latency_ms": "abc"} raised ValueError
and took the endpoint out with a 500. `body.get('repo', '').strip()` with
{"repo": 123} raised AttributeError — the default only covers a MISSING key,
not a wrong-typed one. And `(body.get('note', ''))[:500]` with a dict raised
TypeError. Round 30 probed the surface live: 12 endpoints answered 500 to a
single wrong-typed field, and the sweep found ~45 more raw casts of the same
shape waiting for the same accident.

THE FIX
──────
safe_int / safe_float join as_text in services/request_body.py: a numeric
string is honoured ("120" -> 120 — a client that quotes its numbers means
the number), anything unconvertible falls back to the caller's default.
Never raises. Every raw int()/float()/.strip()/[:n] of a body field in the
routers was converted (60 sites across 24 files).
"""
from __future__ import annotations

import pytest

from backend.services.request_body import as_text, safe_float, safe_int


# ── The helpers themselves ───────────────────────────────────────────────────

class TestCoercionHelpers:
    def test_numeric_strings_are_honoured(self):
        assert safe_int('120') == 120
        assert safe_float('1.5') == 1.5
        assert safe_int(body := 7) == 7

    def test_garbage_falls_back_to_the_callers_default(self):
        assert safe_int('abc', 50) == 50
        assert safe_float('abc', 0.7) == 0.7
        assert safe_int([1, 2], 3) == 3
        assert safe_float({'x': 1}, 2.5) == 2.5
        assert safe_int(None, 15) == 15

    def test_as_text_stringifies_wrong_types_instead_of_raising(self):
        assert as_text(123) == '123'
        assert as_text(None) == ''
        # the github/push shape: .strip() on the get() result used to
        # AttributeError on a non-string value
        assert as_text({'x': 1}) != ''


# ── The previously-crashing endpoints ────────────────────────────────────────
# Every entry here answered HTTP 500 to this exact body before the round-30
# conversion (probed live, 2026-09-15).

PREVIOUSLY_CRASHING = [
    ('POST', '/api/evals/run', {'prompt': 'x', 'response': 'y', 'latency_ms': 'abc'}),
    ('POST', '/api/evals/run', {'prompt': 'x', 'response': 'y', 'cost_usd': 'abc'}),
    ('POST', '/api/agent-leaderboard/record', {'agent_id': 'zz', 'task_type': 'zz', 'tokens': 'abc'}),
    ('POST', '/api/agent-leaderboard/rate', {'agent_id': 'zz', 'rating': 'abc'}),
    ('POST', '/api/ambient/scan', {'max_files': 'abc'}),
    ('POST', '/api/bugbot/reviews/zz/feedback', {'issue_index': 'abc'}),
    ('POST', '/api/bugbot/reviews/zz/feedback', {'issue_index': 0, 'note': {'x': 1}}),
    ('POST', '/api/project/memory', {'key': 'zz', 'value': 'zz', 'confidence': 'abc'}),
    ('POST', '/api/project/memory', {'key': 'zz', 'value': 'zz', 'category': 123}),
    ('POST', '/api/crdt/docs/zz/op', {'revision': 'abc', 'op': 'ins'}),
    ('POST', '/api/db/supabase/query', {'limit': 'abc'}),
    ('POST', '/api/drift/fingerprint', {'agent_ids': ['zz'], 'window_hours': 'abc'}),
    ('POST', '/api/e2e/autofix', {'max_iters': 'abc'}),
    ('POST', '/api/eval-framework/suites', {'name': 'zz', 'pass_threshold': 'abc'}),
    ('POST', '/api/github/push', {'repo': 123}),
    ('POST', '/api/fusion/subagent', {'prompt': 'zz', 'max_tokens': 'abc'}),
    ('POST', '/api/fusion/optimize-cost', {'prompt': 'zz', 'budget_usd': 'abc'}),
    ('POST', '/api/websearch/search', {'query': 'zz', 'num_results': 'abc'}),
    ('POST', '/api/loops', {'name': 'zz', 'interval_minutes': 'abc'}),
    ('POST', '/api/gitai/changelog', {'limit': 'abc'}),
    ('POST', '/api/observability/traces', {'tokens_in': 'abc'}),
    ('POST', '/api/mcp-gateway/policies', {'name': 'zz', 'rule': 'allow', 'priority': 'abc'}),
    ('POST', '/api/mcp-gateway/servers', {'name': 'zz', 'url': 'http://127.0.0.1:9', 'rate_limit_rpm': 'abc'}),
]


@pytest.mark.parametrize('method,path,body', PREVIOUSLY_CRASHING)
def test_wrong_typed_field_is_not_a_500(client, method, path, body):
    r = client.request(method, path, json=body)
    assert r.status_code != 500, (
        f'{method} {path} crashed on a wrong-typed field ({body}) — a single '
        'garbage field must never take the endpoint out'
    )


def test_a2a_tasks_list_survives_a_string_limit(client):
    """The JSON-RPC surface too: params arrive as plain JSON, unguarded."""
    r = client.post('/a2a/researcher', json={
        'jsonrpc': '2.0', 'id': 1, 'method': 'tasks/list', 'params': {'limit': 'abc'},
    })
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body.get('jsonrpc') == '2.0'
    assert 'error' not in body


def test_numeric_strings_still_mean_the_number(client):
    """The coercion must not REJECT quoted numbers — a client that quotes
    its numbers means the number (the as_text contract, extended)."""
    r = client.post('/api/evals/run', json={
        'prompt': 'zz probe', 'response': 'zz probe', 'latency_ms': '250',
    })
    assert r.status_code == 200, r.text[:200]
    assert r.json().get('ok') is True
    import sqlite3
    from backend.services.memory_db import get_conn
    con = get_conn()
    try:
        row = con.execute(
            "SELECT latency_ms FROM eval_runs WHERE prompt='zz probe' ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
    finally:
        con.close()
    assert row and row[0] == 250, f'quoted number not honoured: {row}'
