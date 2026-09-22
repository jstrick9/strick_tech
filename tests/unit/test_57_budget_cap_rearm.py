"""Budget cap breach re-arm on period rollover.

`breached` used to be set once and never cleared: after the FIRST breach
of an hour/day/week cap, the flag stayed 1 forever, so
  * a second breach in a later period window could never raise another
    alert (`pct >= 1.0 and not cap['breached']` was permanently false), and
  * the caps API kept reporting a cap as breached even with $0 spend in
    the current window.
`reset_at` existed in the schema but nothing ever wrote it.

r70: _check_budget_caps now re-arms the cap (breached=0, reset_at=now)
whenever the current window's spend is back under the limit, including the
80–100% band — a cap hovering at 90% in a fresh window must not stay mute
through its next crossing.

Window rollover is simulated deterministically: an hour-scoped cap, ledger
rows aged past the window with UPDATE, and cache entries aged past the TTL
directly. No sleeps.
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

AGENT = "rearm_agent"


@pytest.fixture()
def db_path(tmp_path):
    p = tmp_path / "finops_rearm.db"
    c = sqlite3.connect(p)
    c.executescript(SCHEMA)
    c.execute(
        "INSERT INTO budget_caps (cap_id, name, scope_type, scope_id, period, "
        "limit_usd, on_breach, enabled) VALUES ('cap_r', 'rearm cap', 'platform', "
        "'*', 'hour', 0.10, 'alert', 1)"
    )
    c.commit()
    c.close()
    return p


@pytest.fixture()
def con(db_path):
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


def _breach_alerts(con):
    return con.execute(
        "SELECT COUNT(*) FROM cost_alerts WHERE alert_type='breach'"
    ).fetchone()[0]


def _age_cache():
    for k in list(finops._BUDGET_CAP_CACHE):
        ts, cost, tok = finops._BUDGET_CAP_CACHE[k]
        finops._BUDGET_CAP_CACHE[k] = (ts - finops._BUDGET_CAP_CACHE_TTL - 1, cost, tok)


class TestBudgetCapReArm:
    def test_first_breach_flags_and_alerts(self, con, patched_conn):
        finops.record_cost(AGENT, "llm", 0.20)  # over the $0.10 cap
        row = con.execute("SELECT breached, breached_at FROM budget_caps").fetchone()
        assert row["breached"] == 1
        assert row["breached_at"] != ""
        assert _breach_alerts(con) == 1

    def test_rollover_rearms_and_next_breach_alerts_again(self, con, patched_conn):
        """THE regression: breach in window 1, roll the window over, breach
        again — a second breach alert must appear."""
        # window 1: breach
        finops.record_cost(AGENT, "llm", 0.20)
        assert _breach_alerts(con) == 1

        # roll the window: age every ledger row past the '-1 hour' window
        # and expire the TTL cache so the SUM is recomputed
        con.execute(
            "UPDATE cost_ledger SET created_at = datetime('now', '-2 hours')"
        )
        con.commit()
        _age_cache()

        # a spend inside the new (empty) window triggers the cap check and
        # must re-arm the cap, not leave it flagged
        finops.record_cost(AGENT, "llm", 0.01)
        row = con.execute(
            "SELECT breached, reset_at, current_usd FROM budget_caps"
        ).fetchone()
        assert row["breached"] == 0, "a fresh window must re-arm the cap"
        assert row["reset_at"] != "", "reset_at must record when the re-arm happened"
        assert row["current_usd"] == pytest.approx(0.01)
        assert _breach_alerts(con) == 1, "the re-arm itself is not a breach"

        # breach again in the new window — the second alert is the point
        finops.record_cost(AGENT, "llm", 0.20)
        row = con.execute("SELECT breached, breached_at FROM budget_caps").fetchone()
        assert row["breached"] == 1
        assert _breach_alerts(con) == 2, (
            "a breach in a later window must be able to alert again"
        )

    def test_cap_stays_breached_while_over_the_limit(self, con, patched_conn):
        finops.record_cost(AGENT, "llm", 0.20)
        finops.record_cost(AGENT, "llm", 0.05)  # still way over
        row = con.execute("SELECT breached FROM budget_caps").fetchone()
        assert row["breached"] == 1, "spend still over the cap must not re-arm"
        assert _breach_alerts(con) == 1, "no duplicate breach alerts"

    def test_rearm_in_80_to_100_band_still_warns(self, con, patched_conn):
        """A fresh window already at 80-100% of the cap: the cap re-arms
        AND the 80% warning still fires (dedup: one per hour per cap)."""
        finops.record_cost(AGENT, "llm", 0.20)  # breach
        con.execute("UPDATE cost_ledger SET created_at = datetime('now', '-2 hours')")
        con.commit()
        _age_cache()
        finops.record_cost(AGENT, "llm", 0.09)  # 90% of the cap, no breach
        row = con.execute("SELECT breached, reset_at FROM budget_caps").fetchone()
        assert row["breached"] == 0, "90% in a fresh window is not a breach"
        assert row["reset_at"] != ""
        warnings = con.execute(
            "SELECT COUNT(*) FROM cost_alerts WHERE alert_type='warning'"
        ).fetchone()[0]
        assert warnings == 1

    def test_rollover_with_zero_spend_rearms(self, con, patched_conn):
        """The dashboard-truth case: even $0 spend in the new window must
        clear the stale flag."""
        finops.record_cost(AGENT, "llm", 0.20)
        con.execute("UPDATE cost_ledger SET created_at = datetime('now', '-2 hours')")
        con.commit()
        _age_cache()
        finops.record_cost(AGENT, "llm", 0.001)
        row = con.execute("SELECT breached, current_usd FROM budget_caps").fetchone()
        assert row["breached"] == 0
        assert row["current_usd"] == pytest.approx(0.001)
