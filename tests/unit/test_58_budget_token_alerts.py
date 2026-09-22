"""Token-dimension budget cap alerts.

A cap with limit_tokens > 0 and limit_usd = 0 was enforced but invisible:
check_budget_before_spend denied calls on over_tok, while _check_budget_caps
only ever looked at the USD dimension (`if cap['limit_usd'] > 0`) — so a
token cap could stop every agent with no alert row, no breached flag, and
nothing but a log-free silence for the operator to find.

r70 (#224): both dimensions now breach-alert. pct_used carries the worst
dimension's ratio; the warning path stays USD-only on purpose (cost_alerts
has no dimension column — a token warning and a USD warning would collide
in the per-cap hourly dedup; breaches are one-shot per episode via the
breached flag, so they cannot collide).
"""
import sqlite3

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

AGENT = "token_agent"


@pytest.fixture()
def db_path(tmp_path):
    p = tmp_path / "finops_token.db"
    c = sqlite3.connect(p)
    c.executescript(SCHEMA)
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


def _add_cap(con, cap_id, limit_usd=0, limit_tokens=0, period="hour", on_breach="kill"):
    con.execute(
        "INSERT INTO budget_caps (cap_id, name, scope_type, scope_id, period, "
        "limit_usd, limit_tokens, on_breach, enabled) VALUES (?, ?, 'platform', '*', "
        "?, ?, ?, ?, 1)",
        (cap_id, cap_id, period, limit_usd, limit_tokens, on_breach),
    )
    con.commit()


def _alerts(con, alert_type):
    return con.execute(
        "SELECT * FROM cost_alerts WHERE alert_type=?", (alert_type,)
    ).fetchall()


class TestTokenCapAlerts:
    def test_token_only_cap_breach_alerts(self, con, patched_conn):
        """THE gap: enforcement existed (pre-flight denies on tokens) but no
        alert, no flag, nothing."""
        _add_cap(con, "cap_tok", limit_tokens=100)
        finops.record_cost(AGENT, "llm", 0.001, tokens=150)
        row = con.execute("SELECT breached FROM budget_caps WHERE cap_id='cap_tok'").fetchone()
        assert row["breached"] == 1
        breaches = _alerts(con, "breach")
        assert len(breaches) == 1
        assert breaches[0]["pct_used"] == pytest.approx(1.5)  # 150/100 tokens

    def test_token_cap_at_80pct_does_not_warn(self, con, patched_conn):
        """Warnings stay USD-only (dimension column doesn't exist; the hourly
        dedup would collide). Pin the scope."""
        _add_cap(con, "cap_tok", limit_tokens=100)
        finops.record_cost(AGENT, "llm", 0.001, tokens=85)
        assert _alerts(con, "warning") == []
        assert con.execute("SELECT breached FROM budget_caps WHERE cap_id='cap_tok'").fetchone()["breached"] == 0

    def test_token_cap_rearms_and_alerts_again(self, con, patched_conn):
        """Token caps get the same rollover re-arm as USD caps (#221)."""
        _add_cap(con, "cap_tok", limit_tokens=100)
        finops.record_cost(AGENT, "llm", 0.001, tokens=150)
        assert len(_alerts(con, "breach")) == 1

        con.execute("UPDATE cost_ledger SET created_at = datetime('now', '-2 hours')")
        con.commit()
        for k in list(finops._BUDGET_CAP_CACHE):
            ts, cost, tok = finops._BUDGET_CAP_CACHE[k]
            finops._BUDGET_CAP_CACHE[k] = (ts - finops._BUDGET_CAP_CACHE_TTL - 1, cost, tok)

        finops.record_cost(AGENT, "llm", 0.001, tokens=5)
        assert con.execute("SELECT breached FROM budget_caps WHERE cap_id='cap_tok'").fetchone()["breached"] == 0
        finops.record_cost(AGENT, "llm", 0.001, tokens=120)
        assert len(_alerts(con, "breach")) == 2, "second window must alert again"

    def test_dual_cap_breaches_on_tokens_with_usd_under(self, con, patched_conn):
        """A cap with both limits: tokens cross first while USD is nowhere
        near — the breach must still raise an alert."""
        _add_cap(con, "cap_dual", limit_usd=1.0, limit_tokens=100)
        finops.record_cost(AGENT, "llm", 0.05, tokens=150)  # 5% usd, 150% tok
        breaches = _alerts(con, "breach")
        assert len(breaches) == 1
        assert breaches[0]["pct_used"] == pytest.approx(1.5)

    def test_usd_only_cap_alerts_unchanged(self, con, patched_conn):
        """The USD path keeps its exact pct in the alert."""
        _add_cap(con, "cap_usd", limit_usd=0.10)
        finops.record_cost(AGENT, "llm", 0.25, tokens=10)
        breaches = _alerts(con, "breach")
        assert len(breaches) == 1
        assert breaches[0]["pct_used"] == pytest.approx(2.5)

    def test_preflight_still_denies_token_only_cap(self, con, patched_conn):
        """The alert now matches the enforcement that already existed."""
        _add_cap(con, "cap_tok", limit_tokens=100, on_breach="kill")
        finops.record_cost(AGENT, "llm", 0.001, tokens=150)
        gate = finops.check_budget_before_spend(agent_id=AGENT)
        assert gate["allowed"] is False
        assert "tokens" in gate["reason"]
