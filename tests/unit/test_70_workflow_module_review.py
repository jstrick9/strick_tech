"""Module 15 — Workflow review contracts.

Workflow is the visual automation builder: users wire trigger → agent →
condition → output graphs and run them. Everything below was reproduced against
a live server before the fix.

1. CONDITION EXPRESSIONS WERE DISCARDED. The executor computed the configured
   expression and threw the result away:

       cfg.get('expression', '').replace('{{prev_output}}', context['prev_output'])
       passed = any(kw in context['prev_output'].lower()
                    for kw in ['yes', 'pass', 'true', 'success', 'ok'])

   A bare statement with no assignment, followed by a keyword scan. Whatever
   the user configured had NO effect on which branch ran. Verified live: an
   expression written to never match still took the "yes" branch because the
   input happened to contain the word "yes".

2. `code` NODES CLAIMED WORK THEY NEVER DID — "Code transform applied" while
   the output passed through unchanged.

3. `memory` READ NODES read nothing — "Memory op done", no retrieval.

4. EVERY RUN WAS PERSISTED AS 'success', hardcoded, even when a node errored.
   Verified live: a run emitting node_error was recorded status='success'.

5. Eight endpoints returned HTTP 200 for a workflow that does not exist — and
   PUT silently CREATED one at the missing id.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from backend.routers import workflow as wfm

REPO = Path(__file__).resolve().parents[2]
SRC = (REPO / 'backend' / 'routers' / 'workflow.py').read_text()


def _executable(src: str) -> str:
    """Source with comments and docstrings stripped.

    evaluate_condition()'s own docstring quotes the broken code it replaced, so
    a raw substring search matches the explanation rather than the code — the
    same trap hit in Modules 10, 12 and 14.
    """
    import ast
    import io
    import tokenize

    stripped = tokenize.untokenize(
        t for t in tokenize.generate_tokens(io.StringIO(src).readline)
        if t.type != tokenize.COMMENT
    )
    docs = set()
    for node in ast.walk(ast.parse(stripped)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docs.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
    return "\n".join(
        ln for i, ln in enumerate(stripped.splitlines(), 1) if i not in docs
    )


CODE = _executable(SRC)


@pytest.fixture
def make_wf(client):
    """Create workflows and clean them up."""
    created = []

    def _make(nodes, edges, name='ReviewProbe'):
        r = client.post('/api/workflow', json={'name': name, 'nodes': nodes, 'edges': edges})
        assert r.status_code == 200, r.text
        wid = r.json()['workflow']['id']
        created.append(wid)
        return wid

    yield _make
    for wid in created:
        client.delete(f'/api/workflow/{wid}')


def sse_events(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        if line.startswith('data:'):
            try:
                out.append(json.loads(line[5:]))
            except ValueError:
                pass
    return out


# ── 1. Condition expressions ───────────────────────────────────────────────────


class TestConditionExpressionsAreEvaluated:
    def test_the_discarded_statement_is_gone(self):
        """A bare expression statement whose value was never used."""
        assert "cfg.get('expression', '').replace('{{prev_output}}'" not in CODE

    @pytest.mark.parametrize(
        'expr,prev,expected',
        [
            ("{{prev_output}} contains 'apple'", 'I like apples', True),
            ("{{prev_output}} contains 'banana'", 'I like apples', False),
            ("{{prev_output}} not_contains 'banana'", 'I like apples', True),
            ("{{prev_output}} equals 'done'", 'done', True),
            ("{{prev_output}} equals 'done'", 'not done', False),
            ("{{prev_output}} starts_with 'ERROR'", 'ERROR: boom', True),
            ("{{prev_output}} ends_with 'ok'", 'all ok', True),
            ("{{prev_output}} matches '^[0-9]+$'", '12345', True),
            ("{{prev_output}} matches '^[0-9]+$'", '12a45', False),
            ('{{prev_output}} is_empty', '', True),
            ('{{prev_output}} is_not_empty', 'x', True),
            ('{{prev_output}} > 5', '10', True),
            ('{{prev_output}} > 5', '2', False),
            ('{{prev_output}} <= 5', '5', True),
        ],
    )
    def test_operators_work(self, expr, prev, expected):
        passed, _ = wfm.evaluate_condition(expr, {'prev_output': prev, 'input': ''})
        assert passed is expected, f'{expr!r} against {prev!r}'

    def test_the_keyword_heuristic_no_longer_overrides_the_expression(self):
        """The exact live repro: 'yes' in the input used to force the yes branch."""
        passed, _ = wfm.evaluate_condition(
            "{{prev_output}} contains 'NEVER_MATCHES'", {'prev_output': 'yes please', 'input': ''}
        )
        assert passed is False

    def test_an_empty_expression_falls_back_and_says_so(self):
        """Existing workflows with no expression must keep working."""
        passed, why = wfm.evaluate_condition('', {'prev_output': 'yes', 'input': ''})
        assert passed is True
        assert 'keyword heuristic' in why

    def test_input_placeholder_resolves(self):
        passed, _ = wfm.evaluate_condition(
            "{{input}} contains 'hello'", {'prev_output': '', 'input': 'hello world'}
        )
        assert passed is True

    def test_a_bad_regex_fails_closed_without_raising(self):
        passed, why = wfm.evaluate_condition(
            '{{prev_output}} matches [unclosed', {'prev_output': 'x', 'input': ''}
        )
        assert passed is False
        assert 'regex' in why.lower()

    def test_non_numeric_comparison_is_reported_not_crashed(self):
        passed, why = wfm.evaluate_condition(
            '{{prev_output}} > 5', {'prev_output': 'not a number', 'input': ''}
        )
        assert passed is False
        assert 'numerically' in why

    def test_no_expression_is_ever_executed_as_code(self):
        """A node that eval'd user input would be worse than the bug it fixes."""
        import inspect

        src = inspect.getsource(wfm.evaluate_condition)
        for danger in ('eval(', 'exec(', '__import__', 'compile('):
            assert danger not in src, f'{danger} in condition evaluation'

    def test_branching_follows_the_expression_end_to_end(self, client, make_wf):
        wid = make_wf(
            [
                {'id': 't', 'type': 'trigger', 'config': {}},
                {'id': 'c', 'type': 'condition',
                 'config': {'expression': "{{prev_output}} contains 'MATCHME'"}},
                {'id': 'y', 'type': 'output', 'label': 'YES', 'config': {}},
                {'id': 'n', 'type': 'output', 'label': 'NO', 'config': {}},
            ],
            [
                {'id': 'e1', 'from': 't', 'to': 'c'},
                {'id': 'e2', 'from': 'c', 'to': 'y', 'label': 'yes'},
                {'id': 'e3', 'from': 'c', 'to': 'n', 'label': 'no'},
            ],
        )
        miss = sse_events(client.post(f'/api/workflow/{wid}/run', json={'input': 'yes please'}).text)
        hit = sse_events(client.post(f'/api/workflow/{wid}/run', json={'input': 'MATCHME now'}).text)

        def cond_of(events):
            return next((e.get('condition') for e in events if 'condition' in e), None)

        assert cond_of(miss) is False, 'the word "yes" must not force the yes branch'
        assert cond_of(hit) is True


# ── 2 & 3. Nodes that claimed work they never did ──────────────────────────────


class TestNodesDoNotFakeSuccess:
    def test_code_node_applies_a_real_transform(self, client, make_wf):
        wid = make_wf(
            [
                {'id': 't', 'type': 'trigger', 'config': {}},
                {'id': 'c', 'type': 'code', 'config': {'operation': 'uppercase'}},
                {'id': 'o', 'type': 'output', 'config': {}},
            ],
            [{'id': 'e1', 'from': 't', 'to': 'c'}, {'id': 'e2', 'from': 'c', 'to': 'o'}],
        )
        events = sse_events(client.post(f'/api/workflow/{wid}/run', json={'input': 'hello'}).text)
        final = next((e for e in events if e.get('type') == 'final_output'), {})
        assert final.get('result') == 'HELLO', 'the transform must actually apply'

    def test_code_node_refuses_raw_code_instead_of_pretending(self, client, make_wf):
        """It used to report 'Code transform applied' and change nothing."""
        wid = make_wf(
            [
                {'id': 't', 'type': 'trigger', 'config': {}},
                {'id': 'c', 'type': 'code', 'config': {'code': 'return x.toUpperCase()'}},
                {'id': 'o', 'type': 'output', 'config': {}},
            ],
            [{'id': 'e1', 'from': 't', 'to': 'c'}, {'id': 'e2', 'from': 'c', 'to': 'o'}],
        )
        events = sse_events(client.post(f'/api/workflow/{wid}/run', json={'input': 'hi'}).text)
        errors = [e for e in events if e.get('type') == 'node_error']
        assert errors, 'a code node that cannot run code must say so'
        assert 'cannot execute code' in errors[0]['error']

    def test_the_code_node_does_not_execute_user_code(self):
        """Deliberate: this runs in-process with database and vault access."""
        idx = CODE.index("elif node['type'] == 'code'")
        body = CODE[idx:idx + 2600]
        for danger in ('eval(', 'exec(', 'subprocess', '__import__'):
            assert danger not in body, f'{danger} in the code node'

    def test_memory_read_actually_retrieves(self, client, make_wf, monkeypatch):
        from backend.services import memory_db

        monkeypatch.setattr(
            memory_db, 'memory_search_fts',
            lambda q, limit=3: [{'content': 'RECALLED_FACT_XYZ'}],
        )
        wid = make_wf(
            [
                {'id': 't', 'type': 'trigger', 'config': {}},
                {'id': 'm', 'type': 'memory', 'config': {'action': 'read', 'query': 'anything'}},
                {'id': 'o', 'type': 'output', 'config': {}},
            ],
            [{'id': 'e1', 'from': 't', 'to': 'm'}, {'id': 'e2', 'from': 'm', 'to': 'o'}],
        )
        events = sse_events(client.post(f'/api/workflow/{wid}/run', json={'input': 'q'}).text)
        final = next((e for e in events if e.get('type') == 'final_output'), {})
        assert 'RECALLED_FACT_XYZ' in final.get('result', ''), 'memory read fed nothing forward'

    def test_memory_read_reports_when_nothing_matched(self, client, make_wf, monkeypatch):
        from backend.services import memory_db

        monkeypatch.setattr(memory_db, 'memory_search_fts', lambda q, limit=3: [])
        wid = make_wf(
            [
                {'id': 't', 'type': 'trigger', 'config': {}},
                {'id': 'm', 'type': 'memory', 'config': {'action': 'read'}},
            ],
            [{'id': 'e1', 'from': 't', 'to': 'm'}],
        )
        events = sse_events(client.post(f'/api/workflow/{wid}/run', json={'input': 'q'}).text)
        outputs = ' '.join(str(e.get('output', '')) for e in events)
        assert 'No matching memories' in outputs
        assert 'Memory op done' not in outputs, 'the old meaningless message'


# ── 4. Run status ──────────────────────────────────────────────────────────────


class TestRunStatusIsHonest:
    def test_status_is_not_hardcoded(self):
        assert "'success', user_input[:1000]" not in CODE
        assert "'failed' if node_errors else 'success'" in SRC

    def test_a_failing_node_makes_the_run_failed(self, client, make_wf):
        """Verified live before the fix: node_error + status='success'."""
        wid = make_wf(
            [
                {'id': 't', 'type': 'trigger', 'config': {}},
                {'id': 'c', 'type': 'code', 'config': {'code': 'boom()'}},
            ],
            [{'id': 'e1', 'from': 't', 'to': 'c'}],
        )
        events = sse_events(client.post(f'/api/workflow/{wid}/run', json={'input': 'x'}).text)
        done = next((e for e in events if e.get('type') == 'done'), {})
        assert done.get('status') == 'failed'
        assert done.get('errors')

    def test_a_clean_run_is_success(self, client, make_wf):
        wid = make_wf(
            [
                {'id': 't', 'type': 'trigger', 'config': {}},
                {'id': 'o', 'type': 'output', 'config': {}},
            ],
            [{'id': 'e1', 'from': 't', 'to': 'o'}],
        )
        events = sse_events(client.post(f'/api/workflow/{wid}/run', json={'input': 'x'}).text)
        done = next((e for e in events if e.get('type') == 'done'), {})
        assert done.get('status') == 'success'

    def test_the_persisted_row_matches_the_outcome(self, client, make_wf):
        """workflow_runs feeds the Replay pane; a wrong status misleads it."""
        import os

        wid = make_wf(
            [
                {'id': 't', 'type': 'trigger', 'config': {}},
                {'id': 'c', 'type': 'code', 'config': {'code': 'boom()'}},
            ],
            [{'id': 'e1', 'from': 't', 'to': 'c'}],
            name='PersistProbe',
        )
        client.post(f'/api/workflow/{wid}/run', json={'input': 'x'})
        db = os.environ.get('AGENTIC_TEST_DB')
        if not db or not Path(db).exists():
            pytest.skip('no sandboxed database to inspect')
        con = sqlite3.connect(db)
        try:
            row = con.execute(
                'SELECT status FROM workflow_runs WHERE workflow_id=? ORDER BY rowid DESC LIMIT 1',
                (wid,),
            ).fetchone()
        finally:
            con.close()
        assert row and row[0] == 'failed'


# ── 5. Status codes ────────────────────────────────────────────────────────────


class TestStatusCodes:
    @pytest.mark.parametrize(
        'method,path',
        [
            ('get', '/api/workflow/does-not-exist'),
            ('delete', '/api/workflow/does-not-exist'),
            ('get', '/api/workflow/does-not-exist/export'),
            ('delete', '/api/workflow/does-not-exist/edges/e1'),
        ],
    )
    def test_missing_workflow_is_404(self, client, method, path):
        assert getattr(client, method)(path).status_code == 404

    @pytest.mark.parametrize(
        'path',
        [
            '/api/workflow/does-not-exist/run',
            '/api/workflow/does-not-exist/duplicate',
            '/api/workflow/does-not-exist/validate',
        ],
    )
    def test_missing_workflow_post_is_404(self, client, path):
        assert client.post(path, json={}).status_code == 404

    def test_put_to_a_missing_id_does_not_silently_create(self, client):
        """A typo in the id used to produce a second, near-invisible workflow
        while the user believed they had saved the original.

        Workflows persist as files on disk, outside the test-database sandbox,
        so a run against the pre-fix code leaves one behind. Clear it first —
        otherwise this test passes or fails depending on what ran before it.
        """
        ghost = 'typo-id-xyz'
        client.delete(f'/api/workflow/{ghost}')
        r = client.put(f'/api/workflow/{ghost}', json={'name': 'Ghost', 'nodes': [], 'edges': []})
        assert r.status_code == 404
        assert client.get(f'/api/workflow/{ghost}').status_code == 404

    def test_import_with_invalid_json_is_400(self, client):
        r = client.post(
            '/api/workflow/import', content=b'{not json',
            headers={'content-type': 'application/json'},
        )
        assert r.status_code == 400


# ── Regressions that must keep working ─────────────────────────────────────────


class TestExistingBehaviourIntact:
    def test_a_trigger_less_workflow_still_reports_the_error(self, client, make_wf):
        wid = make_wf([{'id': 'o', 'type': 'output', 'config': {}}], [])
        events = sse_events(client.post(f'/api/workflow/{wid}/run', json={'input': 'x'}).text)
        assert any('No trigger' in str(e.get('msg', '')) for e in events)

    def test_webhook_ssrf_guard_is_still_applied(self):
        assert '_is_ssrf_blocked_url' in SRC

    def test_the_visited_guard_still_prevents_infinite_loops(self, client, make_wf):
        wid = make_wf(
            [
                {'id': 't', 'type': 'trigger', 'config': {}},
                {'id': 'a', 'type': 'output', 'config': {}},
            ],
            [{'id': 'e1', 'from': 't', 'to': 'a'}, {'id': 'e2', 'from': 'a', 'to': 't'}],
        )
        events = sse_events(client.post(f'/api/workflow/{wid}/run', json={'input': 'x'}).text)
        assert any(e.get('type') == 'done' for e in events), 'the run did not terminate'