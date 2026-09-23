"""Unit tests — budget-cap aggregation is sargable (r83, #247)

_period_spend's SUM used the (? = '*' OR agent_id = ?) / (? = '*' OR
goal_id = ?) guard idiom. The planner cannot bind an OR'd parameter
guard to a column index, so EVERY evaluation fell back to
idx_cl_time(created_at) and walked every row in the cap's period
window — an agent-scoped 30-day cap measured 37.8ms p50 per cold
recompute at 100k ledger rows (50 agents x 2k rows), re-paid per
filter key per 30s TTL cache expiry, on synchronous sqlite inside
async handlers. The WHERE is now assembled per scope, so the agent
filter is a plain `agent_id = ?` and the planner seeks
idx_cl_agent(agent_id, created_at DESC) directly: same seed, same
key, 0.8ms p50 — 47x, identical results.

Filter semantics are preserved EXACTLY, including two quirks that
are now pinned explicitly so a future cleanup cannot silently change
enforcement:
  - a goal-scoped cap also filters by the CALLING agent's id (a goal
    cap counts only same-agent spend on that goal);
  - an empty call goal_id compares as the literal '*'.
A global cap (scope_id '*') keeps no agent filter — its whole-window
walk is the true cost of a global sum and remains.

The strongest pin here is the old SQL kept as an ORACLE: the new
implementation must return exactly what the old query returns across
a scope matrix.
"""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from backend.routers import finops

SCHEMA = """
CREATE TABLE cost_ledger (
    ledger_id    TEXT PRIMARY KEY,
    agent_id     TEXT NOT NULL DEFAULT '',
    source_type  TEXT NOT NULL DEFAULT 'llm',
    source_id    TEXT NOT NULL DEFAULT '',
    goal_id      TEXT NOT NULL DEFAULT '',
    run_id       TEXT NOT NULL DEFAULT '',
    task_id      TEXT NOT NULL DEFAULT '',
    user_id      TEXT NOT NULL DEFAULT 'user',
    department   TEXT NOT NULL DEFAULT 'default',
    model        TEXT NOT NULL DEFAULT '',
    tokens_in    INTEGER NOT NULL DEFAULT 0,
    tokens_out   INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd     REAL NOT NULL DEFAULT 0,
    latency_ms   INTEGER NOT NULL DEFAULT 0,
    description  TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_cl_agent ON cost_ledger(agent_id, created_at DESC);
CREATE INDEX idx_cl_goal  ON cost_ledger(goal_id);
CREATE INDEX idx_cl_time  ON cost_ledger(created_at DESC);
CREATE TABLE budget_caps (
    cap_id       TEXT PRIMARY KEY,
    name         TEXT NOT NULL DEFAULT '',
    scope_type   TEXT NOT NULL DEFAULT 'agent',
    scope_id     TEXT NOT NULL DEFAULT '*',
    period       TEXT NOT NULL DEFAULT 'day',
    limit_usd    REAL NOT NULL DEFAULT 0,
    limit_tokens INTEGER NOT NULL DEFAULT 0,
    on_breach    TEXT NOT NULL DEFAULT 'alert',
    current_usd  REAL NOT NULL DEFAULT 0,
    current_tok  INTEGER NOT NULL DEFAULT 0,
    breached     INTEGER NOT NULL DEFAULT 0,
    breached_at  TEXT NOT NULL DEFAULT '',
    reset_at     TEXT NOT NULL DEFAULT '',
    enabled      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL DEFAULT '',
    updated_at   TEXT NOT NULL DEFAULT ''
);
"""

OLD_SQL = """
    SELECT SUM(cost_usd) AS c, SUM(total_tokens) AS t FROM cost_ledger
    WHERE created_at > datetime('now', ?)
      AND (? = '*' OR agent_id = ?)
      AND (? = '*' OR goal_id = ?)
"""


class RecordingConn:
    """Proxy capturing every execute() so tests can EQP the real SQL."""

    def __init__(self, real):
        self.real = real
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))
        return self.real.execute(sql, params)


@pytest.fixture()
def db(tmp_path):
    p = tmp_path / 'finops_r83.db'
    c = sqlite3.connect(p)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    c.commit()
    yield c
    c.close()


@pytest.fixture(autouse=True)
def clean_cache():
    finops._BUDGET_CAP_CACHE.clear()
    yield
    finops._BUDGET_CAP_CACHE.clear()


def _seed(con, rows):
    now = datetime.now(timezone.utc)
    for i, (agent, goal, cost, tok) in enumerate(rows):
        ts = (now - timedelta(minutes=5 + i)).isoformat()
        con.execute(
            'INSERT INTO cost_ledger(ledger_id,agent_id,goal_id,total_tokens,'
            'cost_usd,created_at) VALUES (?,?,?,?,?,?)',
            (f'l{i}', agent, goal, tok, cost, ts),
        )
    con.commit()


def _spend(con, stype='agent', sid='ag_1', agent='ag_1', goal='', period='-30 days'):
    return finops._period_spend(con, period, stype, sid, agent, goal)


class TestSargableAggregation:
    def test_agent_scoped_sum_seeks_the_agent_index(self, db):
        _seed(db, [(f'ag_{a}', '', 1.0, 10) for a in range(20)])
        rec = RecordingConn(db)
        _spend(rec, stype='agent', sid='ag_7', agent='ag_7')
        selects = [c for c in rec.calls if 'SUM(cost_usd)' in c[0]]
        assert len(selects) == 1, 'one aggregation per cold key'
        sql, params = selects[0]
        plan = [r[-1] for r in db.execute('EXPLAIN QUERY PLAN ' + sql, params)]
        assert any('idx_cl_agent' in d and 'agent_id=?' in d for d in plan), plan
        assert not any('SCAN' in d for d in plan), (
            f'agent-scoped cap fell back to a scan: {plan}'
        )

    def test_global_cap_keeps_no_agent_filter(self, db):
        _seed(db, [('ag_1', '', 1.0, 10), ('ag_2', '', 2.0, 20)])
        rec = RecordingConn(db)
        usd, tok = _spend(rec, stype='platform', sid='*', agent='ag_1')
        selects = [c for c in rec.calls if 'SUM(cost_usd)' in c[0]]
        assert len(selects) == 1
        assert 'agent_id' not in selects[0][0], 'a global cap must not filter by agent'
        assert (usd, tok) == (3.0, 30), 'global cap counts every agent'

    def test_goal_cap_counts_only_same_agent_spend_on_that_goal(self, db):
        # The preserved quirk: a goal-scoped cap ALSO filters by the calling
        # agent. Agent X spends $5 on g1, agent Y spends $5 on g1, X spends
        # $2 on another goal -> X's view of g1 is $5, not $10 or $7.
        _seed(db, [('X', 'g1', 5.0, 50), ('Y', 'g1', 5.0, 50), ('X', 'g2', 2.0, 20)])
        usd, tok = _spend(db, stype='goal', sid='g1', agent='X', goal='g1')
        assert (usd, tok) == (5.0, 50)

    def test_new_sql_matches_the_old_sql_across_a_scope_matrix(self, db):
        rows = [
            ('ag_1', '', 1.0, 10),
            ('ag_1', 'g1', 2.0, 20),
            ('ag_2', 'g1', 4.0, 40),
            ('ag_2', '', 8.0, 80),
            ('ag_3', '*', 16.0, 160),
        ]
        _seed(db, rows)
        matrix = [
            ('platform', '*', 'ag_1', ''),
            ('agent', 'ag_1', 'ag_1', ''),
            ('agent', 'ag_2', 'ag_2', 'g1'),
            ('goal', 'g1', 'ag_2', 'g1'),
            ('goal', 'g1', 'ag_2', ''),  # empty call goal compares as '*'
        ]
        for stype, sid, agent, goal in matrix:
            got = _spend(db, stype=stype, sid=sid, agent=agent, goal=goal)
            old = db.execute(
                OLD_SQL,
                ('-30 days', sid, agent, sid if stype == 'goal' else '*', goal or '*'),
            ).fetchone()
            want = (old['c'] or 0.0, old['t'] or 0)
            assert got == want, f'{stype}/{sid}/{agent}/{goal!r}: {got} != {want}'

    def test_preflight_gate_still_denies_the_breached_agent_only(self, db, monkeypatch):
        _seed(db, [('ag_1', '', 50.0, 500), ('ag_2', '', 1.0, 10)])
        db.execute(
            "INSERT INTO budget_caps(cap_id,name,scope_type,scope_id,period,"
            "limit_usd,limit_tokens,on_breach,enabled) "
            "VALUES('c1','ag1 cap','agent','ag_1','day',10.0,0,'pause',1)"
        )
        db.commit()
        monkeypatch.setattr(finops, '_get_conn', lambda: db)
        denied = finops.check_budget_before_spend(agent_id='ag_1')
        assert denied['allowed'] is False
        assert denied['cap_id'] == 'c1'
        other = finops.check_budget_before_spend(agent_id='ag_2')
        assert other['allowed'] is True
