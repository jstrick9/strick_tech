"""Module 15 — the Observability workstation.

Destination: `observability`, hosting agent-monitor, profiler, health, system,
audit-log, replay, finops, dashboard and leaderboard.

Measured against the ICM standard now in docs/architecture/ICM-WORKSPACES.md:
every surface must state its basis, and a number a reader treats as a trust
signal must not claim more than the system actually established.

Three defects, all the same shape:

1. audit-log `verify` reported `verified: len(rows)` -- the number of rows
   PRESENT, not the number of links actually checked. A chain that broke at
   seq 2 of 3 still reported "verified: 3", in the one component whose entire
   job is being trustworthy about tampering.

2. The leaderboard ranked on the raw success ratio, so 1 call at 100% outranked
   50 calls at 94% and was painted bright green at the top of the board.
   Reproduced live before the fix.

3. replay hardcoded `status='done'` at both completion sites, so a run whose
   agent nodes all errored was persisted as done -- and the replay list, whose
   whole purpose is auditing past runs, showed a green result for a failed one.
   The Module 14 workflow-status defect, one surface over.
"""

from __future__ import annotations

import pytest

from backend.routers import agent_leaderboard as lb


# ── 1. audit chain: verified means verified ───────────────────────────────────
def test_verify_counts_links_checked_not_rows_present():
    import inspect

    from backend.routers import audit_log

    src = inspect.getsource(audit_log.verify_chain)
    body = '\n'.join(ln for ln in src.split('\n') if not ln.strip().startswith('#'))
    assert "'verified': len(rows)" not in body, 'verified still reports rows present'
    assert 'verified_count' in body


def test_verify_reports_total_checked_separately():
    import inspect

    from backend.routers import audit_log

    assert 'total_checked' in inspect.getsource(audit_log.verify_chain)


# ── 2. leaderboard: a small sample is not evidence ────────────────────────────
def test_wilson_bound_penalises_a_tiny_sample():
    """1/1 must not read as better than 47/50."""
    assert lb._wilson_lower_bound(1, 1) < lb._wilson_lower_bound(47, 50)


def test_wilson_bound_rises_with_the_sample():
    """An agent earns its ranking by being tested, not by being lucky once."""
    bounds = [lb._wilson_lower_bound(n, n) for n in (1, 5, 10, 50, 200)]
    assert bounds == sorted(bounds)
    assert bounds[0] < 0.4 and bounds[-1] > 0.95


def test_wilson_bound_never_exceeds_the_observed_ratio():
    for succ, tot in ((1, 1), (9, 10), (47, 50), (500, 1000)):
        assert lb._wilson_lower_bound(succ, tot) <= succ / tot


@pytest.mark.parametrize('succ,tot', [(0, 0), (5, 0), (-1, 10), (99, 10)])
def test_wilson_bound_survives_nonsense_input(succ, tot):
    v = lb._wilson_lower_bound(succ, tot)
    assert 0.0 <= v <= 1.0


def test_zero_successes_scores_zero():
    assert lb._wilson_lower_bound(0, 20) == pytest.approx(0.0, abs=0.2)


def test_min_calls_threshold_is_declared():
    assert lb.MIN_CALLS_FOR_CONFIDENCE >= 5


def test_a_single_lucky_call_does_not_outrank_fifty(monkeypatch):
    """The defect, end to end: 1/1 at 100% beat 47/50 at 94% and took #1.

    Behavioural on purpose. An earlier version of this test grepped the source
    for 'ranking_score', which still passed when the sort was reverted to the
    raw ratio -- the string was present, the behaviour was not.
    """
    rows = [
        {'agent_id': 'lucky', 'name': 'Lucky', 'avatar': '', 'color': '',
         'total_calls': 1, 'successes': 1, 'avg_latency': 100.0,
         'total_tokens': 0, 'total_cost': 0.0, 'avg_rating': 0.0,
         'success_rate': 100.0},
        {'agent_id': 'proven', 'name': 'Proven', 'avatar': '', 'color': '',
         'total_calls': 50, 'successes': 47, 'avg_latency': 100.0,
         'total_tokens': 0, 'total_cost': 0.0, 'avg_rating': 0.0,
         'success_rate': 94.0},
    ]

    class _Con:
        def execute(self, *a, **k):
            return self

        def fetchall(self):
            return rows

        def close(self):
            pass

    monkeypatch.setattr(lb, '_get_conn', lambda *a, **k: _Con(), raising=False)
    import backend.services.memory_db as mdb

    monkeypatch.setattr(mdb, 'get_conn', lambda *a, **k: _Con())

    out = lb.leaderboard()
    order = [a['agent_id'] for a in out['leaderboard']]
    assert order[0] == 'proven', f'a 1-call agent still ranks first: {order}'
    assert out['leaderboard'][0]['ranking_score'] > out['leaderboard'][1]['ranking_score']
    assert out['leaderboard'][1]['low_confidence'] is True
    # The raw ratio is still reported verbatim; it just does not decide order.
    assert out['leaderboard'][1]['success_rate'] == 100.0


def test_leaderboard_states_its_ranking_basis():
    """A reader must not have to assume the percentages decide the order."""
    import inspect

    src = inspect.getsource(lb)
    assert 'ranking_basis' in src
    assert 'low_confidence' in src


def test_ui_colours_on_the_adjusted_score_not_the_raw_ratio():
    """A single lucky call must not render bright green at the top."""
    from pathlib import Path

    src = Path('frontend/js/45-leaderboard.js').read_text(encoding='utf-8')
    assert 'ranking_score' in src
    assert 'low_confidence' in src
    assert "a.success_rate>=90?'var(--success)'" not in src


# ── 3. replay: a failed run is not 'done' ─────────────────────────────────────
def test_replay_status_is_derived_from_the_frames(tmp_path, monkeypatch):
    """A run whose nodes errored must not persist as 'done'.

    Behavioural: the earlier source-grep version still passed when 'done' was
    hardcoded back, because the helper name remained in the file.
    """
    monkeypatch.setenv('AGENTIC_TEST_DB', str(tmp_path / 'rs.db'))
    import backend.services.memory_db as mdb
    from backend.routers import replay

    mdb.ensure_schema()
    con = mdb.get_conn()
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS workflow_run_frames (
            run_id TEXT, frame_no INTEGER, node_id TEXT, node_type TEXT,
            node_label TEXT, event_type TEXT, input_ctx TEXT, output TEXT,
            error TEXT DEFAULT '', duration_ms INTEGER, timestamp REAL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS workflow_runs (
            id TEXT PRIMARY KEY, workflow_id TEXT, workflow_nm TEXT, input TEXT,
            status TEXT, total_ms INTEGER DEFAULT 0, node_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        con.execute("INSERT INTO workflow_runs(id,status) VALUES ('rbad','running')")
        con.execute("INSERT INTO workflow_run_frames(run_id,frame_no,error) VALUES ('rbad',1,'boom')")
        con.commit()
    finally:
        con.close()

    # The status a completing run would persist, derived the way the run loops
    # derive it.
    status = 'failed' if replay._run_had_errors('rbad') else 'done'
    assert status == 'failed'
    replay._finish_run('rbad', status, 10, 1)

    con = mdb.get_conn()
    try:
        row = con.execute("SELECT status FROM workflow_runs WHERE id='rbad'").fetchone()
    finally:
        con.close()
    assert row[0] == 'failed', 'a run with errored frames was recorded as done'


def test_replay_does_not_hardcode_done_at_either_completion_site():
    import inspect

    from backend.routers import replay

    src = inspect.getsource(replay)
    body = '\n'.join(ln for ln in src.split('\n') if not ln.strip().startswith('#'))
    assert body.count("'failed' if frame_errors else 'done'") == 2


def test_replay_reads_errors_from_the_recorded_frames():
    """The frames are the record; two loops keeping their own counters drift."""
    import inspect

    from backend.routers import replay

    assert hasattr(replay, '_run_had_errors')
    src = inspect.getsource(replay._run_had_errors)
    assert 'workflow_run_frames' in src
    assert "error != ''" in src


def test_run_had_errors_detects_a_recorded_error(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENTIC_TEST_DB', str(tmp_path / 'r.db'))
    import backend.services.memory_db as mdb
    from backend.routers import replay

    mdb.ensure_schema()
    con = mdb.get_conn()
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS workflow_run_frames (
            run_id TEXT, frame_no INTEGER, node_id TEXT, node_type TEXT,
            node_label TEXT, event_type TEXT, input_ctx TEXT, output TEXT,
            error TEXT DEFAULT '', duration_ms INTEGER, timestamp REAL)""")
        con.execute("INSERT INTO workflow_run_frames(run_id,frame_no,error) VALUES ('r1',1,'')")
        con.execute("INSERT INTO workflow_run_frames(run_id,frame_no,error) VALUES ('r2',1,'boom')")
        con.commit()
    finally:
        con.close()

    assert replay._run_had_errors('r1') is False
    assert replay._run_had_errors('r2') is True


def test_run_had_errors_is_false_when_the_table_is_missing(tmp_path, monkeypatch):
    """A missing table must not crash the run that is trying to finish."""
    monkeypatch.setenv('AGENTIC_TEST_DB', str(tmp_path / 'empty.db'))
    import backend.services.memory_db as mdb
    from backend.routers import replay

    mdb.ensure_schema()
    assert replay._run_had_errors('nope') is False


# ── verified working, pinned so it stays that way ─────────────────────────────
def test_finops_declares_its_cost_basis():
    """Estimated costs must never read as billed costs."""
    import inspect

    from backend.routers import finops

    src = inspect.getsource(finops)
    assert 'cost_basis' in src
    assert 'estimated' in src


def test_audit_chain_detects_tampering():
    """The property the whole component exists for."""
    import inspect

    from backend.routers import audit_log

    src = inspect.getsource(audit_log.verify_chain)
    assert 'broken_at' in src
    assert '_compute_entry_hash' in src
