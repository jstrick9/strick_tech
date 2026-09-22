"""Unit tests — e2e pane indexes, Migration 6 (r75, #235)

Every e2e-pane open ran three blob-heavy table scans over e2e_traces (r73
audit, deferred then as low heat; re-measured with realistic blobs at 50k
rows: /trace 36ms, /history 104ms, /status 76ms). Migration 6 adds two
indexes: idx_e2e_run(run_id, target, status, created_at) — deliberately
COVERING for the /history GROUP BY and a seek for /trace's WHERE run_id=?
(Migration 5's idx_e2e_status_run leads with status, so it never served a
bare run_id lookup) — and idx_e2e_created(created_at) for /status's
ORDER BY created_at DESC LIMIT 1, where SQLite's min/max optimization
satisfies the MAX() straight from the index tail (no query rewrite; output
verified identical pre/post). Measured after: 8.4ms / 26.2ms / 6.2ms.
"""
import sqlite3

from tests.unit.conftest import assert_ok


def _db():
    from backend.services.memory_db import db_path, get_conn

    get_conn().close()  # ensure schema/migrations ran in this process
    return sqlite3.connect(db_path())


def _seed_run(con, run_id, target, statuses, base_ts=1_700_000_000):
    con.executemany(
        'INSERT INTO e2e_traces(run_id,target,step_no,step_name,status,'
        'screenshot_b64,dom_snapshot,console,network_json,duration_ms,created_at) '
        'VALUES (?,?,?,?,?,?,?,?,?,?,?)',
        [
            (run_id, target, i, f'step {i}', st, None, '<html></html>', '[]', '{}',
             10 * i, base_ts + i)
            for i, st in enumerate(statuses)
        ],
    )
    con.commit()


class TestMigration6:
    def test_indexes_exist(self):
        con = _db()
        try:
            idx = {r[1] for r in con.execute('PRAGMA index_list(e2e_traces)')}
        finally:
            con.close()
        assert 'idx_e2e_run' in idx, 'covering index for /history + /trace missing'
        assert 'idx_e2e_created' in idx, 'created_at index for /status missing'
        # Migration 5's index must survive — different leading column, serves
        # the analytics status='pass' aggregate.
        assert 'idx_e2e_status_run' in idx

    def test_migration_recorded(self):
        con = _db()
        try:
            row = con.execute(
                "SELECT name FROM _schema_migrations WHERE version=6"
            ).fetchone()
        finally:
            con.close()
        assert row and row[0] == 'e2e_pane_indexes'

    def test_idx_e2e_run_column_order(self):
        con = _db()
        try:
            cols = [r[2] for r in con.execute('PRAGMA index_info(idx_e2e_run)')]
        finally:
            con.close()
        # Covering order matters: GROUP BY run_id,target is a prefix;
        # status + created_at must be IN the index so the pane never reads
        # blob pages for a summary.
        assert cols == ['run_id', 'target', 'status', 'created_at']


class TestQueryPlans:
    """Pin the plans so a schema edit cannot silently regress to scans."""

    TRACE_SQL = (
        'SELECT step_no, step_name, status, screenshot_b64, '
        'substr(dom_snapshot,1,8000) as dom, console, network_json, '
        'duration_ms, created_at FROM e2e_traces WHERE run_id=? ORDER BY step_no'
    )
    HISTORY_SQL = (
        'SELECT DISTINCT run_id, target, SUM(CASE WHEN status=\'pass\' THEN 1 ELSE 0 END) '
        'as passed, COUNT(*) as total, datetime(MAX(created_at),\'localtime\') as ts '
        'FROM e2e_traces GROUP BY run_id, target ORDER BY MAX(created_at) DESC LIMIT ?'
    )
    STATUS_SQL = (
        'SELECT run_id, target, datetime(MAX(created_at),\'localtime\') as ts '
        'FROM e2e_traces ORDER BY created_at DESC LIMIT 1'
    )

    def test_trace_uses_run_index_not_scan(self):
        con = _db()
        try:
            plans = ' | '.join(r[-1] for r in con.execute(
                'EXPLAIN QUERY PLAN ' + self.TRACE_SQL, ('some_run',)))
        finally:
            con.close()
        assert 'USING INDEX idx_e2e_run' in plans
        assert 'SCAN e2e_traces' not in plans, (
            f'/trace regressed to a table scan: {plans}'
        )

    def test_history_is_covered(self):
        con = _db()
        try:
            plans = ' | '.join(r[-1] for r in con.execute(
                'EXPLAIN QUERY PLAN ' + self.HISTORY_SQL, (20,)))
        finally:
            con.close()
        assert 'USING COVERING INDEX idx_e2e_run' in plans, (
            f'/history lost its covering index: {plans}'
        )

    def test_status_uses_created_index(self):
        con = _db()
        try:
            plans = ' | '.join(r[-1] for r in con.execute(
                'EXPLAIN QUERY PLAN ' + self.STATUS_SQL))
        finally:
            con.close()
        assert 'idx_e2e_created' in plans
        # The whole-table scan form shows 'SCAN e2e_traces' — the min/max
        # optimization turns it into a bounded index lookup.
        assert 'SCAN e2e_traces' not in plans


class TestEndpointBehavior:
    def test_trace_returns_steps_ordered_by_step_no(self, client):
        con = _db()
        try:
            _seed_run(con, 'unit_run_plan', 'https://unit.test', ['pass', 'fail', 'pass'])
        finally:
            con.close()

        d = assert_ok(client.get('/api/e2e/trace/unit_run_plan'))
        assert d['run_id'] == 'unit_run_plan'
        assert [s['step_no'] for s in d['steps']] == [0, 1, 2]
        assert d['steps'][1]['status'] == 'fail'
        # network_json is parsed into meta, not shipped raw
        assert 'meta' in d['steps'][0] and 'network_json' not in d['steps'][0]

    def test_history_summarizes_runs(self, client):
        con = _db()
        try:
            _seed_run(con, 'unit_run_hist_a', 'https://unit.test', ['pass', 'pass', 'fail'])
            _seed_run(con, 'unit_run_hist_b', 'https://unit.test', ['fail', 'fail'], base_ts=1_800_000_000)
        finally:
            con.close()

        rows = assert_ok(client.get('/api/e2e/history?limit=10'))
        by_run = {r['run_id']: r for r in rows}
        a = by_run['unit_run_hist_a']
        assert a['passed'] == 2 and a['total'] == 3 and a['score'] == 0.67
        # newest first: b was seeded with a later base timestamp
        assert rows[0]['run_id'] == 'unit_run_hist_b'

    def test_status_reports_last_run(self, client):
        con = _db()
        try:
            _seed_run(con, 'unit_run_status', 'https://status.test', ['pass'], base_ts=1_900_000_000)
        finally:
            con.close()

        d = assert_ok(client.get('/api/e2e/status'))
        assert d['last_run']['run_id'] == 'unit_run_status'
        assert d['last_run']['target'] == 'https://status.test'
        assert 'ts' in d['last_run']
