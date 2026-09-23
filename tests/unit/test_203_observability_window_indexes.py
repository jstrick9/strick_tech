"""Unit tests — observability time-window indexes (r76, #238)

The trace emitter runs in the LLM layer, so obs_traces grows by one row per
LLM call in the entire app — chat-level heat — yet every time-based read was
a table scan (the r76 registry/growth sweep flagged obs_traces as the only
never-deleted, per-request-written table whose read paths lacked indexes):

  GET /api/observability/traces        ORDER BY created_at DESC LIMIT   — scan+sort
  GET /api/observability/analytics     created_at >= days (summary),
                                       started_at >= days (by_model/by_type)
  GET /api/observability/dora          three windowed counts/averages

Measured at 50k traces / 100k spans: list 60.4ms, limit=500 101.2ms,
analytics 102.0/96.8ms. Two indexes (added in observability._ensure_schema
next to the CREATE TABLEs — the tables are router-created, so a memory_db
migration would hit the Migration 7 trap and be recorded as applied while
the CREATE INDEX silently failed):

  idx_obs_traces_created ON obs_traces(created_at)
  idx_obs_spans_started  ON obs_spans(started_at)

After: list 7.2ms (8.4x), limit=500 30.5ms (3.3x, 936KB serialization floor),
analytics 4.5/4.7ms (~21x). The existing (agent_id, created_at) and
(session_id) indexes continue to serve the filtered listings.
"""
import sqlite3

from tests.unit.conftest import assert_ok


def _db():
    from backend.services.memory_db import db_path, get_conn

    get_conn().close()
    return sqlite3.connect(db_path())


class TestIndexes:
    def test_created_indexes_exist(self):
        con = _db()
        try:
            t = {r[1] for r in con.execute('PRAGMA index_list(obs_traces)')}
            s = {r[1] for r in con.execute('PRAGMA index_list(obs_spans)')}
        finally:
            con.close()
        assert 'idx_obs_traces_created' in t, 'time-window index for the traces pane missing'
        assert 'idx_obs_spans_started' in s, 'time-window index for span aggregates missing'
        # pre-existing filter indexes must survive
        assert 'idx_obs_traces_agent' in t and 'idx_obs_session' in t
        assert 'idx_obs_spans_trace' in s

    def test_list_uses_created_index_without_sort(self):
        con = _db()
        try:
            plans = ' | '.join(r[-1] for r in con.execute(
                'EXPLAIN QUERY PLAN SELECT * FROM obs_traces '
                'ORDER BY created_at DESC LIMIT 50'))
        finally:
            con.close()
        assert 'USING INDEX idx_obs_traces_created' in plans
        assert 'TEMP B-TREE' not in plans, (
            f'the default pane listing regressed to scan+sort: {plans}'
        )

    def test_summary_window_is_a_search(self):
        con = _db()
        try:
            plans = ' | '.join(r[-1] for r in con.execute(
                'EXPLAIN QUERY PLAN SELECT COUNT(*), AVG(total_latency_ms), '
                'SUM(total_tokens), SUM(total_cost) FROM obs_traces '
                "WHERE created_at >= datetime('now','-7 days')"))
        finally:
            con.close()
        assert 'USING INDEX idx_obs_traces_created' in plans
        assert 'SCAN obs_traces' not in plans

    def test_span_aggregate_window_is_a_search(self):
        con = _db()
        try:
            plans = ' | '.join(r[-1] for r in con.execute(
                'EXPLAIN QUERY PLAN SELECT model, COUNT(*), AVG(latency_ms), '
                'SUM(tokens_in+tokens_out) FROM obs_spans '
                "WHERE started_at >= datetime('now','-7 days') AND model != '' "
                'GROUP BY model ORDER BY COUNT(*) DESC LIMIT 10'))
        finally:
            con.close()
        assert 'USING INDEX idx_obs_spans_started' in plans
        assert 'SCAN obs_spans' not in plans

    def test_dora_error_count_window_is_a_search(self):
        con = _db()
        try:
            plans = ' | '.join(r[-1] for r in con.execute(
                'EXPLAIN QUERY PLAN SELECT COUNT(*) FROM obs_traces '
                "WHERE status='error' AND created_at >= datetime('now','-7 days')"))
        finally:
            con.close()
        assert 'USING INDEX idx_obs_traces_created' in plans
        assert 'SCAN obs_traces' not in plans


class TestEndpoints:
    def test_trace_lifecycle_through_the_pane(self, client):
        """POST a trace (as the emitter would), then read it back through the
        pane listing — newest first."""
        r = client.post('/api/observability/traces',
                        json={'id': 'tr_unit_0001', 'session_id': 'sess_unit',
                              'agent_id': 'agent_unit', 'name': 'unit trace',
                              'input': 'hello'})
        assert r.status_code == 200, r.text[:200]

        d = assert_ok(client.get('/api/observability/traces?limit=10'))
        ids = [t['id'] for t in d['traces']]
        assert 'tr_unit_0001' in ids
        assert d['count'] == len(d['traces'])

    def test_analytics_shape(self, client):
        d = assert_ok(client.get('/api/observability/analytics?days=7'))
        assert d['days'] == 7
        for key in ('total_traces', 'avg_latency', 'total_tokens',
                    'total_cost', 'error_count', 'error_rate'):
            assert key in d['summary'], f'summary.{key} missing'
        assert isinstance(d['by_model'], list)
        assert isinstance(d['by_type'], list)
        assert isinstance(d['hourly'], list)

    def test_dora_shape(self, client):
        d = assert_ok(client.get('/api/observability/dora?days=7'))
        for key in ('deployment_frequency', 'lead_time_ms', 'change_failure_rate',
                    'mttr_ms', 'p95_latency_ms', 'total_traces', 'period_days'):
            assert key in d, f'dora.{key} missing'
        assert d['period_days'] == 7
