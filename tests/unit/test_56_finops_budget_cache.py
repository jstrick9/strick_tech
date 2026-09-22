"""
FinOps budget-cap aggregation cache.

The cap SUM walks every cost_ledger row inside the cap's period window and
ran after EVERY LLM call (3 seeded caps → 3 SUMs per call) and before every
chat send. Under sustained traffic the window holds the whole day's spend,
so per-call cost grew linearly with history — a 22-minute soak (10.9k LLM
ops) drifted tasks/send p50 129ms → 323ms and py-spy put 54% of on-CPU
request time in _check_budget_caps.

finops._period_spend now TTL-caches the SUM per filter key; the caller's
own just-committed spend is added on top of a cached value (but never on a
fresh recompute, where the SUM already includes it). These tests pin the
cache mechanics deterministically — no sleeps, timestamps are manipulated
directly.
"""
import sqlite3
import time

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
CREATE TABLE cost_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, cap_id TEXT NOT NULL,
    agent_id TEXT NOT NULL DEFAULT '', alert_type TEXT NOT NULL DEFAULT 'warning',
    pct_used REAL NOT NULL DEFAULT 0, cost_at_alert REAL NOT NULL DEFAULT 0,
    limit_usd REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT ''
);
"""


@pytest.fixture()
def db_path(tmp_path):
    p = tmp_path / "finops_gap.db"
    c = sqlite3.connect(p)
    c.executescript(SCHEMA)
    c.commit()
    c.close()
    return p


@pytest.fixture()
def con(db_path):
    # a live handle for assertions; the code under test opens/closes its own
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


@pytest.fixture()
def patched_conn(db_path, monkeypatch):
    def _connect():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr(finops, "_get_conn", _connect)


@pytest.fixture(autouse=True)
def clean_cache():
    finops._BUDGET_CAP_CACHE.clear()
    yield
    finops._BUDGET_CAP_CACHE.clear()


def _spend(con, agent="", goal="", delta=(0.0, 0), period="-1 day",
           stype="platform", sid="*"):
    return finops._period_spend(
        con, period, stype, sid, agent, goal, pending_delta=delta
    )


class TestPeriodSpendCache:
    def test_fresh_sum_then_cache_hit_ignores_new_rows(self, con):
        con.execute(
            "INSERT INTO cost_ledger (ledger_id, cost_usd, total_tokens, created_at) VALUES ('l1', 0.5, 10, datetime('now'))"
        )
        first = _spend(con)
        assert first == (0.5, 10)

        # a new ledger row must NOT be visible while the cache is fresh
        con.execute(
            "INSERT INTO cost_ledger (ledger_id, cost_usd, total_tokens, created_at) VALUES ('l2', 0.7, 20, datetime('now'))"
        )
        assert _spend(con) == (0.5, 10), "cache hit must skip the SUM"

    def test_delta_added_on_cache_hit_not_on_fresh(self, con):
        con.execute(
            "INSERT INTO cost_ledger (ledger_id, cost_usd, total_tokens, created_at) VALUES ('l1', 0.5, 10, datetime('now'))"
        )
        assert _spend(con, delta=(0.2, 5)) == (0.5, 10), (
            "fresh SUM already includes committed rows — delta must not double count"
        )
        # now cached: this call's own spend is added on top
        assert _spend(con, delta=(0.2, 5)) == (0.7, 15)
        # ...and the folded total is written back: the next delta-free
        # pre-flight must see this call's spend, or a cap tripped by call N
        # would wrongly allow call N+1 (found by test_83 in CI, 2026-09-21)
        assert _spend(con) == (0.7, 15)

    def test_ttl_expiry_recomputes(self, con):
        con.execute(
            "INSERT INTO cost_ledger (ledger_id, cost_usd, total_tokens, created_at) VALUES ('l1', 0.5, 10, datetime('now'))"
        )
        _spend(con)
        con.execute(
            "INSERT INTO cost_ledger (ledger_id, cost_usd, total_tokens, created_at) VALUES ('l2', 0.7, 20, datetime('now'))"
        )
        # age every cache entry past the TTL
        now = time.time()
        for k in list(finops._BUDGET_CAP_CACHE):
            ts, cost, tok = finops._BUDGET_CAP_CACHE[k]
            finops._BUDGET_CAP_CACHE[k] = (ts - finops._BUDGET_CAP_CACHE_TTL - 1, cost, tok)
        assert _spend(con) == (1.2, 30), "stale cache must recompute from the ledger"

    def test_cache_is_bounded(self, con):
        for i in range(finops._BUDGET_CAP_CACHE_MAX + 10):
            finops._BUDGET_CAP_CACHE[(f"p{i}", "*", "", "", "platform")] = (time.time(), 0.0, 0)
        _spend(con, agent="bound")
        assert len(finops._BUDGET_CAP_CACHE) <= finops._BUDGET_CAP_CACHE_MAX + 1


class TestCheckBudgetCapsWithCache:
    def _cap(self, con, limit=0.01, on_breach="alert"):
        con.execute(
            "INSERT INTO budget_caps (cap_id, name, scope_type, scope_id, period, "
            "limit_usd, on_breach, enabled) VALUES ('cap_t', 't', 'platform', '*', "
            "'day', ?, ?, 1)",
            (limit, on_breach),
        )
        con.commit()  # the code under test opens its own connection

    def test_single_large_spend_trips_cap_immediately_via_delta(self, con, patched_conn):
        """The whole point of the delta: cached or not, THIS call's spend
        must be able to trip the cap in the same request."""
        self._cap(con, limit=0.01)
        # empty ledger: first check computes a fresh SUM of 0 and caches it
        finops._check_budget_caps("t_agent", 0.005, 5, "")
        assert con.execute("SELECT breached FROM budget_caps WHERE cap_id='cap_t'").fetchone()[0] == 0
        # second call within TTL: cache hit (0.0) + this call's 0.02 >= 0.01
        finops._check_budget_caps("t_agent", 0.02, 5, "")
        row = con.execute("SELECT breached FROM budget_caps WHERE cap_id='cap_t'").fetchone()
        assert row[0] == 1, "cached+delta must trip the cap in-request"
        alerts = con.execute("SELECT alert_type FROM cost_alerts").fetchall()
        assert any(a[0] == "breach" for a in alerts)

    def test_preflight_gate_uses_cached_spend(self, con, patched_conn):
        self._cap(con, limit=0.01, on_breach="pause")
        con.execute(
            "INSERT INTO cost_ledger (ledger_id, cost_usd, total_tokens, agent_id, created_at) "
            "VALUES ('l1', 0.02, 0, 'gate_agent', datetime('now'))"
        )
        con.commit()  # visible to the code's own connection
        gate = finops.check_budget_before_spend(agent_id="gate_agent")
        assert gate["allowed"] is False
        # more spend lands; the cached value is reused within the TTL and the
        # answer must remain a denial (never flip to allowed)
        con.execute(
            "INSERT INTO cost_ledger (ledger_id, cost_usd, total_tokens, agent_id, created_at) "
            "VALUES ('l2', 5.0, 0, 'gate_agent', datetime('now'))"
        )
        con.commit()
        gate2 = finops.check_budget_before_spend(agent_id="gate_agent")
        assert gate2["allowed"] is False

class TestKillCapEnforcementAcrossCalls:
    """End-to-end regression for the coherence bug: a hard cap tripped by
    call N must block call N+1 even though the cache was primed (at zero)
    by call N's own pre-flight."""

    def test_kill_cap_blocks_the_next_call(self, con, patched_conn):
        agent = "kill_agent"
        con.execute(
            "INSERT INTO budget_caps (cap_id, name, scope_type, scope_id, period, "
            "limit_usd, on_breach, enabled) VALUES ('cap_k', 'kill cap', 'agent', ?, "
            "'hour', 0.001, 'kill', 1)",
            (agent,),
        )
        con.commit()

        # call 1: pre-flight passes (empty ledger) and primes the cache at 0
        assert finops.check_budget_before_spend(agent_id=agent)["allowed"] is True
        # call 1's spend lands via the only production write path
        finops.record_cost(agent, "llm", 0.01)
        # call 2: pre-flight must now be denied by the same cap
        gate = finops.check_budget_before_spend(agent_id=agent)
        assert gate["allowed"] is False
        assert gate["action"] == "kill"
        assert gate["cap_name"] == "kill cap"
        assert gate["spent_usd"] >= gate["limit_usd"]
