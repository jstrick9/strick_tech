"""Hot read-path indexes (migration 5): chat_log, audit, e2e_traces, tasks.

Found by the r73 schema-wide index-coverage audit (130 tables cross-referenced
with their query shapes): the four usage-growing tables had no index any of
their readers could use. chat_log — the fastest grower, one row per message —
had exactly ONE index, on `message`. Measured on a seeded DB (100k chat_log /
30k audit / 50k e2e_traces):

  * chat history `WHERE session_id=? ORDER BY id DESC` full-scanned (10.5ms)
  * the message-count maintenance on EVERY message insert ran a correlated
    `COUNT(*) WHERE session_id=?` that full-scanned the whole table:
    +6.8ms per message, linear forever (the #220 defect class)
  * the analytics dashboard (auto-refreshed every 30s) full-scanned all four
    tables per refresh; its audit query used date(created_at)=date('now'),
    which no index can serve.

Migration 5 adds six indexes; the two audit predicates were rewritten to the
sargable range form. Post-fix: correlated count 6.8ms -> 0.03ms (covering
index), history by session 10.5ms -> 7.8ms, and every dashboard sub-shape now
compiles to an index search. The dashboard's whole-table aggregates remain
O(n) by nature and are addressed separately (response cache).
"""
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import analytics as analytics_module
from backend.routers.analytics import router as analytics_router
from backend.services.memory_db import get_conn

INDEXES = {
    "idx_chat_log_session": "chat_log",
    "idx_chat_log_agent": "chat_log",
    "idx_chat_log_created": "chat_log",
    "idx_audit_created": "audit",
    "idx_e2e_status_run": "e2e_traces",
    "idx_tasks_status_updated": "tasks",
}


def _plan(con, sql):
    return "; ".join(r[3] for r in con.execute("EXPLAIN QUERY PLAN " + sql))


class TestMigration5:
    def test_all_six_indexes_exist(self):
        con = get_conn()
        try:
            for name, table in INDEXES.items():
                got = con.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='index' AND name=? AND tbl_name=?",
                    (name, table),
                ).fetchone()
                assert got is not None, f"{name} missing on {table}"
        finally:
            con.close()

    def test_migration_is_recorded(self):
        con = get_conn()
        try:
            row = con.execute(
                "SELECT name FROM _schema_migrations WHERE version=5"
            ).fetchone()
        finally:
            con.close()
        assert row is not None and row[0] == "hot_read_path_indexes"


class TestQueryPlans:
    """Pins the plans so a future rewrite that drops index usage fails here."""

    def test_chat_history_by_session(self):
        con = get_conn()
        try:
            plan = _plan(con, "SELECT * FROM chat_log WHERE session_id='x' ORDER BY id DESC LIMIT 100")
        finally:
            con.close()
        assert "idx_chat_log_session" in plan, plan

    def test_message_count_correlated_subquery_is_covering(self):
        """The per-message insert path (chat.py) counts a session's messages;
        it must never touch the table itself."""
        con = get_conn()
        try:
            plan = _plan(con, "SELECT COUNT(*) FROM chat_log WHERE session_id='x'")
        finally:
            con.close()
        assert "idx_chat_log_session" in plan and "COVERING" in plan, plan

    def test_audit_today_uses_created_index(self):
        con = get_conn()
        try:
            plan = _plan(
                con,
                "SELECT action, COUNT(*) FROM audit WHERE created_at >= date('now') GROUP BY action",
            )
        finally:
            con.close()
        assert "idx_audit_created" in plan, plan

    def test_e2e_pass_count_distinct_is_covering(self):
        con = get_conn()
        try:
            plan = _plan(con, "SELECT COUNT(DISTINCT run_id) FROM e2e_traces WHERE status='pass'")
        finally:
            con.close()
        assert "idx_e2e_status_run" in plan and "COVERING" in plan, plan

    def test_tasks_velocity_uses_status_index(self):
        con = get_conn()
        try:
            plan = _plan(
                con,
                "SELECT agent, COUNT(*) FROM tasks WHERE status='done'"
                " AND updated_at >= date('now','-7 days') GROUP BY agent",
            )
        finally:
            con.close()
        assert "idx_tasks_status_updated" in plan, plan


class TestAuditPredicateRewrite:
    def test_range_form_matches_date_form_exactly(self):
        """created_at >= date('now') must return exactly what
        date(created_at)=date('now') returned, midnight boundary included."""
        con = get_conn()
        try:
            midnight = time.strftime("%Y-%m-%d 00:00:00", time.gmtime())
            before_midnight = time.strftime(
                "%Y-%m-%d 23:59:59", time.gmtime(time.time() - 86400)
            )
            probe = [("q_mid", midnight), ("q_pre", before_midnight)]
            for tag, ts in probe:
                con.execute(
                    "INSERT INTO audit(action,detail,created_at) VALUES ('q_audit', ?, ?)",
                    (tag, ts),
                )
            con.commit()
            old = con.execute(
                "SELECT COUNT(*) FROM audit WHERE date(created_at)=date('now')"
            ).fetchone()[0]
            new = con.execute(
                "SELECT COUNT(*) FROM audit WHERE created_at >= date('now')"
            ).fetchone()[0]
            con.execute("DELETE FROM audit WHERE action='q_audit'")
            con.commit()
        finally:
            con.close()
        assert old >= 1, "expected the midnight boundary row in the count"
        assert new == old


class TestDashboardStillCorrect:
    @pytest.fixture(scope="class")
    def client(self):
        app = FastAPI()
        app.include_router(analytics_router)
        with TestClient(app) as c:
            yield c

    def test_dashboard_returns_all_sections(self, client):
        body = client.get("/api/analytics/dashboard?days=7").json()
        for key in ("cost", "swarm", "e2e", "activity", "agents", "tasks", "memory", "kpis"):
            assert key in body, f"dashboard section {key} missing"
        assert set(body["cost"]) == {"by_agent", "over_30_days", "over_period"}
        assert "total_runs" in body["e2e"]
        # the rewritten audit predicate feeds activity.today (audit-by-day)
        assert "today" in body["activity"] and "recent" in body["activity"]

    def test_kpis_endpoint_shape(self, client):
        body = client.get("/api/analytics/kpis").json()
        for key in ("done_tasks", "completion_rate", "e2e_pass_rate"):
            assert key in body, f"kpi {key} missing"
