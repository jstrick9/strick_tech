"""Module 28 — ICM entry routing.

The bug this module was built for, reproduced exactly as it existed in
chat.py before the router:

    for _d in sorted(_icm.WORKSPACES_DIR.iterdir()):
        _meta = _icm.read_meta(_d)
        if _d.name in _msg or str(_meta.get('name','')).lower() in _msg:

Measured against real workspaces, that substring test:

    workspace 'os'             + "what is the cost of this?"       -> MATCHED
    workspace 'client-reports' + "write the weekly client report"  -> missed

The false positive is the dangerous one. A wrong workspace does not error; it
loads another project's identity, routing and stage contract into the system
prompt, and the model answers confidently from context that has nothing to do
with the question. Van Clief names starting in the wrong folder as the way ICM
silently fails, so every test here is about the decision being *right and
explained*, not merely produced.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def router(tmp_path, monkeypatch):
    """A router bound to an empty workspace root of its own.

    The unit harness sandboxes the data dir, so these tests seed every
    workspace they rely on rather than trusting ambient dev data.
    """
    monkeypatch.setenv('AGENTIC_OS_DATA_DIR', str(tmp_path))
    from backend.services import icm as icm_mod

    importlib.reload(icm_mod)
    from backend.services import icm_router as router_mod

    importlib.reload(router_mod)
    assert router_mod.icm.WORKSPACES_DIR.is_relative_to(tmp_path)
    return router_mod


def _make(router, ws_id, name, stages=('research',), routes=(), description=''):
    ws = router.icm.WORKSPACES_DIR / ws_id
    router.icm.scaffold(ws, name, description, list(stages))
    if routes:
        ctx = ws / 'CONTEXT.md'
        body = ctx.read_text(encoding='utf-8')
        body += '\n\n## Routes\n' + '\n'.join(f'- {r}' for r in routes) + '\n'
        ctx.write_text(body, encoding='utf-8')
    return ws


# ── the substring false positive ──────────────────────────────────────────────
def test_short_workspace_id_does_not_match_inside_a_longer_word(router):
    """'os' must not match 'cost'. This is the original bug, verbatim."""
    _make(router, 'os', 'os')
    d = router.resolve('what is the cost of this?')
    assert not d['matched'], d
    assert d['status'] == 'no-match'


def test_short_workspace_id_does_not_match_inside_other_words(router):
    _make(router, 'os', 'os')
    for message in ('close this modal please', 'the most obvious choice', 'compose a reply'):
        d = router.resolve(message)
        assert not d['matched'], (message, d)


def test_a_normal_length_id_does_not_match_inside_a_longer_word(router):
    """Isolates the word-boundary rule from the short-id filter.

    'os' is also blocked by the minimum-length guard, so it cannot prove the
    boundary matching works. 'art' is long enough to be a real identity term
    and is a substring of 'start', so only boundary matching saves it.
    """
    _make(router, 'art', 'art')
    for message in ('start the project', 'departure time', 'smart routing'):
        d = router.resolve(message)
        assert not d['matched'], (message, d)


def test_workspace_name_still_matches_as_a_whole_word(router):
    _make(router, 'invoices', 'invoices')
    d = router.resolve('generate the invoices for March')
    assert d['matched']
    assert d['workspace_id'] == 'invoices'


# ── the miss ──────────────────────────────────────────────────────────────────
def test_declared_route_catches_what_the_name_alone_missed(router):
    """'write the weekly client report' never contained 'client-reports'."""
    _make(router, 'client-reports', 'client-reports', routes=['weekly client report'])
    d = router.resolve('write the weekly client report')
    assert d['matched']
    assert d['workspace_id'] == 'client-reports'
    assert any('weekly client report' in e for e in d['candidates'][0]['evidence'])


def test_multiword_route_outranks_an_incidental_name_mention(router):
    _make(router, 'reports', 'reports')
    _make(router, 'billing', 'billing', routes=['weekly client report'])
    d = router.resolve('write the weekly client report')
    assert d['workspace_id'] == 'billing', d['candidates']


# ── ambiguity is asked about, never guessed ───────────────────────────────────
def test_two_close_matches_report_ambiguous_rather_than_picking_one(router):
    _make(router, 'alpha', 'alpha', routes=['quarterly review'])
    _make(router, 'beta', 'beta', routes=['quarterly review'])
    d = router.resolve('start the quarterly review')
    assert d['status'] == 'ambiguous'
    assert not d['matched']
    assert {c['workspace_id'] for c in d['alternatives']} == {'alpha', 'beta'}


def test_a_clear_winner_is_not_reported_as_ambiguous(router):
    _make(router, 'alpha', 'alpha', routes=['quarterly review', 'quarterly', 'review'])
    _make(router, 'beta', 'beta', routes=['unrelated topic'])
    d = router.resolve('start the quarterly review')
    assert d['status'] == 'matched'
    assert d['workspace_id'] == 'alpha'


def test_explicit_request_beats_every_score_and_is_never_ambiguous(router):
    _make(router, 'alpha', 'alpha', routes=['quarterly review'])
    _make(router, 'beta', 'beta', routes=['quarterly review'])
    d = router.resolve('start the quarterly review', requested='beta')
    assert d['matched']
    assert d['workspace_id'] == 'beta'
    assert 'explicitly requested' in d['reason']


def test_requesting_a_workspace_that_does_not_exist_is_reported_not_guessed(router):
    _make(router, 'alpha', 'alpha', routes=['quarterly review'])
    d = router.resolve('start the quarterly review', requested='ghost')
    assert d['status'] == 'not-found'
    assert not d['matched']
    assert d['workspace_id'] == ''


# ── no-match is an honest outcome ─────────────────────────────────────────────
def test_no_workspaces_at_all_is_a_clean_no_match(router):
    d = router.resolve('anything at all')
    assert d['status'] == 'no-match'
    assert d['reason'] == 'no workspaces exist'


def test_unrelated_message_matches_nothing(router):
    _make(router, 'invoices', 'invoices', routes=['invoice', 'billing'])
    d = router.resolve('what is the weather in Charlotte tomorrow')
    assert not d['matched']
    assert d['status'] == 'no-match'


# ── route declaration parsing ─────────────────────────────────────────────────
def test_routes_are_read_from_the_context_md_routes_section(router):
    ws = _make(router, 'ops', 'ops', routes=['deploy to production', 'rollback'])
    assert router.parse_routes(ws) == ['deploy to production', 'rollback']


def test_prose_in_the_routes_section_is_not_treated_as_a_route(router):
    ws = _make(router, 'ops', 'ops')
    ctx = ws / 'CONTEXT.md'
    ctx.write_text(
        ctx.read_text(encoding='utf-8')
        + '\n\n## Routes\nThese are the things that enter here.\n- rollback\n',
        encoding='utf-8',
    )
    assert router.parse_routes(ws) == ['rollback']


def test_a_route_made_only_of_stopwords_is_dropped(router):
    """'- the' would otherwise capture nearly every message in the system."""
    ws = _make(router, 'ops', 'ops', routes=['the', 'and it', 'rollback'])
    assert router.parse_routes(ws) == ['rollback']


def test_workspace_with_no_routes_section_parses_to_empty(router):
    ws = _make(router, 'ops', 'ops')
    assert router.parse_routes(ws) == []


def test_routes_are_case_and_punctuation_insensitive(router):
    _make(router, 'ops', 'ops', routes=['Deploy To Production'])
    d = router.resolve('please deploy to production, now')
    assert d['matched']


# ── the decision is explained ─────────────────────────────────────────────────
def test_every_decision_carries_its_evidence(router):
    _make(router, 'invoices', 'invoices', routes=['invoice'])
    d = router.resolve('send the invoice')
    assert d['reason']
    assert d['candidates'][0]['evidence']


def test_candidates_are_returned_sorted_by_score(router):
    _make(router, 'alpha', 'alpha', routes=['quarterly review', 'quarterly'])
    _make(router, 'beta', 'beta', routes=['quarterly'])
    d = router.resolve('quarterly review')
    scores = [c['score'] for c in d['candidates']]
    assert scores == sorted(scores, reverse=True)


def test_stage_is_resolved_not_assumed(router):
    _make(router, 'pipe', 'pipe', stages=('research', 'draft'), routes=['pipe work'])
    d = router.resolve('do the pipe work')
    assert d['stage'] == '01-research'
    assert d['stage_reason'] == 'first stage with no output'


def test_explicit_stage_overrides_the_resolved_one(router):
    _make(router, 'pipe', 'pipe', stages=('research', 'draft'), routes=['pipe work'])
    d = router.resolve('do the pipe work', stage='02-draft')
    assert d['stage'] == '02-draft'
    assert d['stage_reason'] == 'explicitly requested'


# ── assembly ──────────────────────────────────────────────────────────────────
def test_resolve_and_assemble_loads_only_the_matched_stage(router):
    """Only the entry stage's CONTRACT loads, not every stage's.

    Note the L1 routing table legitimately *names* every stage -- that is the
    catalog pointing at the shelves, and it is supposed to be there. What must
    not appear is the other stage's L2 contract, which is the payload.
    """
    _make(router, 'pipe', 'pipe', stages=('research', 'draft'), routes=['pipe work'])
    d = router.resolve_and_assemble('do the pipe work')
    assert d['matched']
    ctx = d['compiled_context']
    assert 'L2-CONTRACT: stages/01-research/CONTEXT.md' in ctx
    assert 'L2-CONTRACT: stages/02-draft/CONTEXT.md' not in ctx


def test_assembly_on_a_no_match_returns_empty_context_not_a_crash(router):
    _make(router, 'pipe', 'pipe', routes=['pipe work'])
    d = router.resolve_and_assemble('completely unrelated request')
    assert not d['matched']
    assert d['compiled_context'] == ''
    assert d['estimated_tokens'] == 0


def test_assembled_context_stays_within_the_icm_token_budget(router):
    """The canon's whole claim is 2-8k per stage. Assert it holds."""
    _make(router, 'pipe', 'pipe', stages=('research', 'draft'), routes=['pipe work'])
    d = router.resolve_and_assemble('do the pipe work')
    assert 0 < d['estimated_tokens'] <= 8000


# ── the audit log ─────────────────────────────────────────────────────────────
def test_decisions_are_logged_and_readable_back(router):
    _make(router, 'invoices', 'invoices', routes=['invoice'])
    d = router.resolve('send the invoice')
    router.log_decision('send the invoice', d)
    recent = router.recent_decisions()
    assert recent
    assert recent[0]['workspace_id'] == 'invoices'
    assert recent[0]['status'] == 'matched'


def test_no_match_decisions_are_logged_too(router):
    """A run that loaded no workspace is exactly what you debug later."""
    _make(router, 'invoices', 'invoices', routes=['invoice'])
    d = router.resolve('unrelated')
    router.log_decision('unrelated', d)
    assert router.recent_decisions()[0]['status'] == 'no-match'


def test_recent_decisions_are_newest_first(router):
    _make(router, 'invoices', 'invoices', routes=['invoice'])
    for msg in ('invoice one', 'invoice two'):
        router.log_decision(msg, router.resolve(msg))
    recent = router.recent_decisions()
    assert recent[0]['message'] == 'invoice two'


def test_the_log_is_bounded(router):
    _make(router, 'invoices', 'invoices', routes=['invoice'])
    d = router.resolve('invoice')
    for _ in range(router._LOG_LIMIT + 25):
        router.log_decision('invoice', d)
    lines = router._log_path().read_text(encoding='utf-8').splitlines()
    assert len(lines) <= router._LOG_LIMIT


def test_recent_decisions_with_no_log_file_is_empty_not_an_error(router):
    assert router.recent_decisions() == []


# ── the route table ───────────────────────────────────────────────────────────
def test_route_table_lists_every_workspace_and_what_enters_it(router):
    _make(router, 'invoices', 'invoices', routes=['invoice'])
    _make(router, 'ops', 'ops', routes=['rollback'])
    table = {r['workspace_id']: r for r in router.route_table()}
    assert set(table) == {'invoices', 'ops'}
    assert table['invoices']['routes'] == ['invoice']
    assert table['ops']['routes'] == ['rollback']


def test_route_table_reports_stage_progress(router):
    ws = _make(router, 'pipe', 'pipe', stages=('research', 'draft'), routes=['pipe'])
    (ws / 'stages' / '01-research' / 'output' / 'research.md').write_text('done', encoding='utf-8')
    row = router.route_table()[0]
    assert row['total_stages'] == 2
    assert row['complete'] == 1
    assert row['entry_stage'] == '02-draft'


def test_route_table_reports_the_form(router):
    """The UI labels units by form; without it every form draws as a pipeline."""
    _make(router, 'pipe', 'pipe', routes=['pipe'])
    assert router.route_table()[0]['form'] == 'pipeline'


def test_route_table_is_empty_when_there_are_no_workspaces(router):
    assert router.route_table() == []


# ── HTTP surface ──────────────────────────────────────────────────────────────
# These use the shared session client, which does not share the tmp_path data
# dir the fixture above builds. They assert the transport contract -- shape,
# status codes, validation -- not the routing arithmetic, which is covered
# above against seeded workspaces.
class TestRouteEndpoints:
    def test_route_table_endpoint_returns_a_list(self, client):
        r = client.get('/api/icm/routes')
        assert r.status_code == 200
        body = r.json()
        assert body['ok'] is True
        assert isinstance(body['routes'], list)

    def test_route_preview_requires_a_query(self, client):
        """An empty q must be rejected, not silently scored against ''."""
        assert client.get('/api/icm/route').status_code == 422
        assert client.get('/api/icm/route?q=%20%20').status_code == 422

    def test_route_preview_returns_an_explained_decision(self, client):
        r = client.get('/api/icm/route?q=some+arbitrary+request')
        assert r.status_code == 200
        d = r.json()['decision']
        for key in ('status', 'matched', 'workspace_id', 'stage', 'reason', 'candidates'):
            assert key in d

    def test_route_preview_is_read_only(self, client):
        """Previewing must not write a log entry; only real runs are logged."""
        before = len(client.get('/api/icm/route/log?limit=500').json()['decisions'])
        client.get('/api/icm/route?q=preview+only+request')
        after = len(client.get('/api/icm/route/log?limit=500').json()['decisions'])
        assert before == after

    def test_route_log_endpoint_returns_a_list(self, client):
        r = client.get('/api/icm/route/log')
        assert r.status_code == 200
        assert isinstance(r.json()['decisions'], list)

    def test_route_log_out_of_range_limits_are_clamped_not_crashed(self, client):
        for edge in ('0', '-5', '99999'):
            r = client.get(f'/api/icm/route/log?limit={edge}')
            assert r.status_code == 200, edge
            assert len(r.json()['decisions']) <= 500

    def test_route_log_rejects_a_non_numeric_limit(self, client):
        """`limit: int` means FastAPI refuses this before the handler runs."""
        assert client.get('/api/icm/route/log?limit=abc').status_code == 422
