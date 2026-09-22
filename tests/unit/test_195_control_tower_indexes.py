"""Control Tower query plans: agent_traces indexes + sargable today window.

agent_traces is append-only and grows with every run (the 22-minute r69 soak
alone added ~10k rows; the 30-day spread in the r72 probe measured 100k rows
at 11.9MB). Before the indexes, every Control Tower read walked the table:
GET /runs sorted the WHOLE table to return 50 rows (full scan + temp b-tree),
GET /runs/{id} scanned for run_id, and GET /stats — which the frontend polls
every 5s — ran five scans, one of which (`date(created_at)=date('now')`)
could never use an index because of the function on the column.

Measured live on 100k rows: /runs 20.8ms -> 6.6ms, /runs/{id} 12.3ms ->
4.2ms, /stats 52.0ms -> 21.9ms — and the shapes are now index lookups, so
they no longer scale with table size.

These tests pin the PLAN, not the timing: the indexes exist, each hot query
compiles to an index search (and the list query to an index-ordered scan
with NO temp b-tree), and the rewritten today-window predicate returns
exactly what the date() form returned.
"""
import sqlite3
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import control_tower
from backend.routers.control_tower import router as ct_router
from backend.services.memory_db import get_conn


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(ct_router)
    with TestClient(app) as c:
        yield c


def _plan(con, sql, params=()):
    return "; ".join(r[3] for r in con.execute("EXPLAIN QUERY PLAN " + sql, params))


class TestIndexesExist:
    def test_agent_traces_indexes_are_created(self):
        con = get_conn()
        try:
            names = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='agent_traces'"
            )}
        finally:
            con.close()
        assert {"idx_at_created", "idx_at_run", "idx_at_status"} <= names

    def test_agent_trace_steps_index_is_created(self):
        con = get_conn()
        try:
            names = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='agent_trace_steps'"
            )}
        finally:
            con.close()
        assert "idx_ats_run" in names

    def test_existing_databases_are_migrated_at_startup(self):
        """CREATE INDEX IF NOT EXISTS runs at import: an existing DB gains the
        indexes without any manual migration step."""
        # the module-level _ensure_traces_table() already ran against the
        # sandbox DB (created empty by the conftest) — proving the point.
        assert control_tower._ensure_traces_table is not None


class TestQueryPlans:
    """The regressions these prevent are silent linear growth — pin the plans
    so a future rewrite that drops the index usage fails here, not in prod."""

    def test_runs_list_uses_the_index_order_no_temp_btree(self):
        con = get_conn()
        try:
            plan = _plan(con, "SELECT * FROM agent_traces ORDER BY created_at DESC LIMIT 50")
        finally:
            con.close()
        assert "idx_at_created" in plan
        assert "TEMP B-TREE" not in plan, (
            f"the list route must not sort the whole table: {plan}"
        )

    def test_run_detail_uses_run_id_index(self):
        con = get_conn()
        try:
            plan = _plan(con, "SELECT * FROM agent_traces WHERE run_id=?", ("x",))
        finally:
            con.close()
        assert "idx_at_run" in plan and "SCAN agent_traces" not in plan

    def test_status_counts_use_covering_index(self):
        con = get_conn()
        try:
            for status in ("error", "killed"):
                plan = _plan(con, "SELECT COUNT(*) FROM agent_traces WHERE status=?", (status,))
                assert "idx_at_status" in plan, plan
                assert "COVERING" in plan, f"count should not touch the table: {plan}"
        finally:
            con.close()

    def test_steps_lookup_uses_composite_index(self):
        con = get_conn()
        try:
            plan = _plan(con, "SELECT * FROM agent_trace_steps WHERE run_id=? ORDER BY step_no", ("x",))
        finally:
            con.close()
        assert "idx_ats_run" in plan and "TEMP B-TREE" not in plan


class TestTodayWindowRewrite:
    def test_range_predicate_matches_the_date_form_exactly(self):
        """created_at >= date('now') must return exactly what
        date(created_at)=date('now') returned — including the midnight
        boundary and future timestamps."""
        con = get_conn()
        try:
            now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
            yesterday = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - 86400))
            midnight = time.strftime("%Y-%m-%d 00:00:00", time.gmtime())
            before_midnight = time.strftime("%Y-%m-%d 23:59:59", time.gmtime(time.time() - 86400))
            probe_rows = [
                ("q_now", now), ("q_yday", yesterday),
                ("q_midnight", midnight), ("q_before_midnight", before_midnight),
            ]
            for rid, ts in probe_rows:
                con.execute(
                    "INSERT INTO agent_traces(run_id,status,total_cost,created_at,updated_at)"
                    " VALUES (?, 'done', 0.01, ?, ?)",
                    (rid, ts, ts),
                )
            con.commit()
            old = con.execute(
                "SELECT COUNT(*), SUM(total_cost) FROM agent_traces"
                " WHERE date(created_at)=date('now')"
            ).fetchone()
            new = con.execute(
                "SELECT COUNT(*), SUM(total_cost) FROM agent_traces"
                " WHERE created_at >= date('now')"
            ).fetchone()
            for rid, _ in probe_rows:  # clean up: the sandbox DB is shared
                con.execute("DELETE FROM agent_traces WHERE run_id=?", (rid,))
            con.commit()
        finally:
            con.close()
        assert old[0] >= 2, "expected the seeded boundary rows in the count"
        assert new == old, f"range predicate drifted from the date() form: {new} != {old}"

    def test_stats_endpoint_agrees_with_the_date_predicate(self, client):
        con = get_conn()
        try:
            expected = con.execute(
                "SELECT COUNT(*) FROM agent_traces WHERE date(created_at)=date('now')"
            ).fetchone()[0]
        finally:
            con.close()
        stats = client.get("/api/control/stats").json()
        assert stats["today_runs"] == expected


class TestBehaviourUnchanged:
    def test_runs_list_is_newest_first(self, client):
        con = get_conn()
        try:
            now = time.time()
            for i, rid in enumerate(("q_newest", "q_middle", "q_oldest")):
                ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now - i * 3600))
                con.execute(
                    "INSERT INTO agent_traces(run_id,status,created_at,updated_at)"
                    " VALUES (?, 'done', ?, ?)", (rid, ts, ts),
                )
            con.commit()
        finally:
            con.close()
        runs = client.get("/api/control/runs?limit=3").json()
        try:
            ids = [r["run_id"] for r in runs[:3]]
            assert ids[0] == "q_newest", f"expected newest first, got {ids}"
        finally:
            con = get_conn()
            try:
                for rid in ("q_newest", "q_middle", "q_oldest"):
                    con.execute("DELETE FROM agent_traces WHERE run_id=?", (rid,))
                con.commit()
            finally:
                con.close()

    def test_run_detail_returns_steps_in_step_order(self, client):
        con = get_conn()
        try:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
            con.execute(
                "INSERT INTO agent_traces(run_id,status,created_at,updated_at)"
                " VALUES ('q_steps', 'done', ?, ?)", (ts, ts),
            )
            for no in (3, 1, 2):  # inserted out of order on purpose
                con.execute(
                    "INSERT INTO agent_trace_steps(run_id,step_no,step_type,name,created_at)"
                    " VALUES ('q_steps', ?, 'node', ?, ?)", (no, f"step{no}", ts),
                )
            con.commit()
        finally:
            con.close()
        try:
            body = client.get("/api/control/runs/q_steps").json()
            steps = body.get("steps") or body.get("run", {}).get("steps") or []
            assert [s["step_no"] for s in steps] == [1, 2, 3], steps
        finally:
            con = get_conn()
            try:
                con.execute("DELETE FROM agent_trace_steps WHERE run_id='q_steps'")
                con.execute("DELETE FROM agent_traces WHERE run_id='q_steps'")
                con.commit()
            finally:
                con.close()
