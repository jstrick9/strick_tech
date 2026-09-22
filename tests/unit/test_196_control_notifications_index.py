"""Notifications partial index: unread queries must not scan the whole table.

GET /api/control/notifications — which the UI polls — runs two unread
queries per call (the unread_only list and the unread COUNT), both filtered
on read_at IS NULL. With no index that can serve read_at IS NULL, both
full-scanned a table that grows with every run lifecycle event: measured
16.9ms p50 at 100k seeded rows (95% read). Same defect class as #229.

The fix is a PARTIAL index carrying only unread rows, already in id-DESC
order: `ON notifications(id DESC) WHERE read_at IS NULL`. The list walks it
directly, the COUNT is an index count over unread rows only, and rows leave
the index the moment they are marked read — so the index stays small however
big the table gets. Measured post-fix on the same 100k-row DB: 5.2ms p50.
"""
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers.control_tower import router as ct_router
from backend.services.memory_db import get_conn


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(ct_router)
    with TestClient(app) as c:
        yield c


def _plan(con, sql):
    return "; ".join(r[3] for r in con.execute("EXPLAIN QUERY PLAN " + sql))


def _seed(count_unread=3, count_read=2):
    """Insert identifiable rows; returns (unread_ids, read_ids)."""
    con = get_conn()
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        unread_ids, read_ids = [], []
        for i in range(count_unread):
            cur = con.execute(
                "INSERT INTO notifications(type,title,body,run_id,read_at,created_at)"
                " VALUES ('q_unread', ?, '', '', NULL, ?)", (f"unread {i}", ts),
            )
            unread_ids.append(cur.lastrowid)
        for i in range(count_read):
            cur = con.execute(
                "INSERT INTO notifications(type,title,body,run_id,read_at,created_at)"
                " VALUES ('q_read', ?, '', '', ?, ?)", (f"read {i}", ts, ts),
            )
            read_ids.append(cur.lastrowid)
        con.commit()
    finally:
        con.close()
    return unread_ids, read_ids


def _cleanup(ids):
    con = get_conn()
    try:
        con.executemany("DELETE FROM notifications WHERE id=?", [(i,) for i in ids])
        con.commit()
    finally:
        con.close()


class TestPartialIndex:
    def test_index_exists_and_is_partial(self):
        con = get_conn()
        try:
            row = con.execute(
                "SELECT sql FROM sqlite_master WHERE name='idx_ntf_unread'"
            ).fetchone()
        finally:
            con.close()
        assert row is not None, "idx_ntf_unread must exist"
        assert "read_at IS NULL" in row[0], (
            "the index must be PARTIAL (unread rows only) or it grows with the table"
        )

    def test_unread_list_uses_the_partial_index(self):
        con = get_conn()
        try:
            plan = _plan(
                con,
                "SELECT * FROM notifications WHERE read_at IS NULL ORDER BY id DESC LIMIT 30",
            )
        finally:
            con.close()
        assert "idx_ntf_unread" in plan, plan

    def test_unread_count_uses_the_partial_index(self):
        con = get_conn()
        try:
            plan = _plan(con, "SELECT COUNT(*) FROM notifications WHERE read_at IS NULL")
        finally:
            con.close()
        assert "idx_ntf_unread" in plan, plan


class TestInboxBehaviour:
    def test_unread_only_list_and_count(self, client):
        unread_ids, read_ids = _seed()
        try:
            body = client.get("/api/control/notifications?unread_only=true&limit=50").json()
            returned = {n["id"] for n in body["notifications"]}
            assert set(unread_ids) <= returned
            assert not (set(read_ids) & returned), "read rows must not appear in unread_only"
            assert body["unread_count"] >= len(unread_ids)
        finally:
            _cleanup(unread_ids + read_ids)

    def test_mark_read_shrinks_the_unread_set(self, client):
        unread_ids, read_ids = _seed(count_unread=2, count_read=0)
        try:
            before = client.get("/api/control/notifications?unread_only=true").json()["unread_count"]
            r = client.patch(f"/api/control/notifications/{unread_ids[0]}/read")
            assert r.status_code == 200
            after = client.get("/api/control/notifications?unread_only=true").json()["unread_count"]
            assert after == before - 1, "one mark-read must drop the count by exactly one"
        finally:
            _cleanup(unread_ids + read_ids)

    def test_read_all_empties_the_unread_set(self, client):
        unread_ids, read_ids = _seed(count_unread=3, count_read=0)
        try:
            r = client.post("/api/control/notifications/read-all")
            assert r.status_code == 200
            body = client.get("/api/control/notifications?unread_only=true").json()
            assert body["unread_count"] == 0
            assert body["notifications"] == []
        finally:
            _cleanup(unread_ids + read_ids)
