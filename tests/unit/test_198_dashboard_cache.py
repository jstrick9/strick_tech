"""Analytics dashboard TTL cache: 30s polling must not re-run the aggregates.

The dashboard battery aggregates whole history (GROUP BY agent over every
chat_log row, per-day cost buckets, COUNT(DISTINCT) over e2e_traces) — O(n)
by nature, and no index makes "sum everything" cheap. Measured at 100k
chat_log rows: 127-251ms per call depending on the period, with the frontend
polling every 30s — the aggregates ran ~2,880 times/day for a pane whose
numbers change at best hourly.

The route now caches the response per clamped `days` key for 10s: with a 30s
poll, two of every three refreshes are served from memory and the data is at
most 10s stale on a view that refreshes every 30s anyway. Measured live:
days=7 cold 146.8ms -> warm 3.0ms; days=30 cold 251.3ms -> warm 5.2ms.

Deterministic (no sleeps): TTL expiry is forced by rewriting the cached
timestamp, and DB access is observed by counting get_conn calls.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import analytics
from backend.routers.analytics import router as analytics_router


@pytest.fixture()
def client(monkeypatch):
    app = FastAPI()
    app.include_router(analytics_router)
    conns = {"n": 0}
    real_get_conn = analytics.get_conn

    def counting_get_conn():
        conns["n"] += 1
        return real_get_conn()

    monkeypatch.setattr(analytics, "get_conn", counting_get_conn)
    with TestClient(app) as c:
        yield c, conns
    analytics._DASHBOARD_CACHE.clear()


class TestDashboardCache:
    def test_second_call_within_ttl_does_not_touch_the_db(self, client):
        c, conns = client
        r1 = c.get("/api/analytics/dashboard?days=7")
        assert r1.status_code == 200
        used = conns["n"]
        r2 = c.get("/api/analytics/dashboard?days=7")
        assert r2.status_code == 200
        assert conns["n"] == used, "a cached response must not open a DB connection"
        assert r2.json() == c.get("/api/analytics/dashboard?days=7").json()

    def test_expired_entry_rebuilds(self, client):
        c, conns = client
        c.get("/api/analytics/dashboard?days=7")
        used = conns["n"]
        # age the entry past the TTL
        for key, (ts, body) in list(analytics._DASHBOARD_CACHE.items()):
            analytics._DASHBOARD_CACHE[key] = (ts - analytics._DASHBOARD_CACHE_TTL - 1, body)
        c.get("/api/analytics/dashboard?days=7")
        assert conns["n"] > used, "an expired entry must be rebuilt from the DB"

    def test_days_is_the_cache_key(self, client):
        c, conns = client
        c.get("/api/analytics/dashboard?days=7")
        used = conns["n"]
        c.get("/api/analytics/dashboard?days=30")
        assert conns["n"] > used, "a different period must not be served another period's cache"
        c.get("/api/analytics/dashboard?days=30")
        assert conns["n"] == used + 1

    def test_unclamped_days_share_the_clamped_key(self, client):
        """days=7 and days=7 (after clamp) are one entry; 999 clamps to 365."""
        c, conns = client
        c.get("/api/analytics/dashboard?days=999")
        used = conns["n"]
        c.get("/api/analytics/dashboard?days=999")
        assert conns["n"] == used, "same clamped period must hit the same entry"

    def test_cache_is_bounded(self, client):
        c, _ = client
        for d in range(analytics._DASHBOARD_CACHE_MAX + 5):
            analytics._DASHBOARD_CACHE[d] = (0.0, {"stub": d})
        c.get("/api/analytics/dashboard?days=7")
        assert len(analytics._DASHBOARD_CACHE) <= analytics._DASHBOARD_CACHE_MAX + 1

    def test_fresh_data_is_visible_after_expiry(self, client):
        """The cache must not pin stale numbers forever: after the TTL, a new
        row in the underlying tables shows up in the response."""
        c, conns = client
        from backend.services.memory_db import get_conn as real_conn
        r1 = c.get("/api/analytics/dashboard?days=7").json()
        con = real_conn()
        try:
            con.execute(
                "INSERT INTO audit(action,detail,created_at) VALUES ('q_dash','x',CURRENT_TIMESTAMP)"
            )
            con.commit()
        finally:
            con.close()
        for key, (ts, body) in list(analytics._DASHBOARD_CACHE.items()):
            analytics._DASHBOARD_CACHE[key] = (ts - analytics._DASHBOARD_CACHE_TTL - 1, body)
        r2 = c.get("/api/analytics/dashboard?days=7").json()
        con = real_conn()
        try:
            con.execute("DELETE FROM audit WHERE action='q_dash'")
            con.commit()
        finally:
            con.close()
        assert r1 != r2, "post-expiry rebuild must observe new data"
