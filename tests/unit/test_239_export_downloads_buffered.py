"""Unit tests — export downloads must not iterate their body line-by-line (r91, #253)

The 10x-scaled-DB slow-query bench (Class B) found the DB layer healthy at
10x — every list endpoint <60ms, finops export SQL 41ms via idx_cl_time,
chain verify 139ms over 171k rows — but three DOWNLOAD endpoints crawled:

    /api/finops/export/csv        2,458ms   (query: 41ms, CSV build: 39ms)
    /api/audit-log/export/json    2,712ms
    /api/audit-log/export/csv       238ms

The handler itself ran in 79ms when called directly. The cost was in the
RESPONSE path: all four download endpoints (compliance report download
included) returned StreamingResponse(io.BytesIO(payload)) — and BytesIO
iterates LINE BY LINE, so starlette paid one sync->async threadpool hop
per CSV row / JSON line (~10k hops for a max-size CSV, ~100k for the
pretty-printed audit JSON). analytics.py already used the single-chunk
iter([...]) form; these four sites now return a plain buffered Response,
which writes the already-in-memory payload once.

A/B on a real server against the 10x-scaled DB: finops 2,458->80ms (31x),
audit JSON 2,712->140ms (19x), audit CSV 238->14ms (17x).

These tests pin behaviour (status, content type, disposition, body shape)
AND a wide-margin performance gate: the 10k-row CSV export must complete
in <1.5s through the full ASGI stack (broken: ~2.6s, fixed: ~0.3s).
"""
import csv
import io
import json
import time

import pytest

from backend.services.memory_db import get_conn


def _seed_cost_rows(n: int = 10_000) -> None:
    con = get_conn()
    try:
        con.execute('DELETE FROM cost_ledger WHERE ledger_id LIKE \'bench239-%\'')
        con.executemany(
            'INSERT INTO cost_ledger (ledger_id, agent_id, source_type, model,'
            ' tokens_in, tokens_out, total_tokens, cost_usd, latency_ms, description, created_at)'
            ' VALUES (?,?,?,?,?,?,?,?,?,?,datetime(\'now\'))',
            [(f'bench239-{i:05d}', 'researcher', 'llm', 'gpt-4o-mini',
              100, 200, 300, 0.001 * (i % 17 + 1), 50.0, 'bench row') for i in range(n)],
        )
        con.commit()
    finally:
        con.close()


def _seed_audit_rows(n: int) -> None:
    con = get_conn()
    try:
        con.execute('DELETE FROM audit_log_chain WHERE entry_id LIKE \'bench239-%\'')
        con.executemany(
            'INSERT INTO audit_log_chain (entry_id, agent_id, agent_name, action_type,'
            ' action_detail, reasoning, authority, risk_level, outcome, metadata,'
            ' prev_hash, entry_hash, created_at, epoch_ms)'
            ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?,datetime(\'now\'),?)',
            [(f'bench239-{i:05d}', 'researcher', 'Researcher', 'bench.fill',
              'detail', 'reasoning', 'user', 'low', 'success', '{}',
              '0' * 64, f'{i:064x}', 1700000000 + i) for i in range(n)],
        )
        con.commit()
    finally:
        con.close()


@pytest.fixture(autouse=True)
def _clean_bench_rows():
    yield
    con = get_conn()
    try:
        con.execute('DELETE FROM cost_ledger WHERE ledger_id LIKE \'bench239-%\'')
        con.execute('DELETE FROM audit_log_chain WHERE entry_id LIKE \'bench239-%\'')
        con.commit()
    finally:
        con.close()


class TestFinopsCsvExport:
    def test_ten_thousand_row_export_is_fast_and_wellformed(self, client):
        _seed_cost_rows(10_000)
        t0 = time.perf_counter()
        r = client.get('/api/finops/export/csv')
        wall = time.perf_counter() - t0
        assert r.status_code == 200, r.text
        assert r.headers['content-type'].startswith('text/csv')
        assert 'finops_export_' in r.headers.get('content-disposition', '')

        body = r.content.decode()
        rows = list(csv.reader(io.StringIO(body)))
        assert rows[0][0] == 'ledger_id'  # header row
        data = [row for row in rows[1:] if row]
        assert len(data) == 10_000
        assert data[0][0].startswith('bench239-')
        # Performance gate: the line-iterating StreamingResponse took ~2.6s
        # through the ASGI stack; the buffered Response takes ~0.3s. 1.5s
        # separates the two worlds with 2x headroom on either side.
        assert wall < 1.5, f'10k-row CSV export took {wall:.2f}s — line iteration is back?'


class TestAuditJsonExport:
    def test_export_parses_and_carries_the_chain_verdict(self, client):
        _seed_audit_rows(300)
        # Max window: the app's audit middleware appends rows throughout the
        # session and ours land at the HIGH end of seq, so a small limit would
        # window them out entirely.
        r = client.get('/api/audit-log/export/json?limit=10000')
        assert r.status_code == 200, r.text
        assert 'application/json' in r.headers['content-type']
        assert 'audit_log_' in r.headers.get('content-disposition', '')
        payload = json.loads(r.content)
        assert payload['export_type'] == 'agentic_os_audit_log'
        # The app's own audit middleware appends rows during the session, so
        # exact totals are order-dependent; what must hold: our seeded rows
        # all made it into the export, up to the requested limit.
        mine = [e for e in payload['entries'] if e['entry_id'].startswith('bench239-')]
        assert len(mine) == 300
        assert payload['total'] >= 300
        assert 'chain_verify' in payload


class TestAuditCsvExport:
    def test_export_rows_and_header(self, client):
        _seed_audit_rows(120)
        r = client.get('/api/audit-log/export/csv?limit=10000')
        assert r.status_code == 200, r.text
        assert r.headers['content-type'].startswith('text/csv')
        rows = list(csv.reader(io.StringIO(r.content.decode())))
        assert rows[0][0] == 'seq'
        mine = [x for x in rows[1:] if x and x[1].startswith('bench239-')]
        assert len(mine) == 120


class TestComplianceDownload:
    def test_generated_report_downloads(self, client):
        r = client.post('/api/compliance/generate', json={
            'title': 'bench239 report', 'framework': 'General', 'format': 'json',
        })
        assert r.status_code == 200, r.text
        assert r.headers.get('x-report-id'), 'report id header must survive the buffered Response'
        assert 'attachment' in r.headers.get('content-disposition', '')
        payload = json.loads(r.content)
        assert payload.get('ok') is True or 'framework' in json.dumps(payload)[:2000]
