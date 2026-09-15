"""One rotten DB row must not 500 the whole endpoint (round 31).

THE BUG
───────
List and detail loops parsed JSON columns raw: `json.loads(d.get('issues',
'[]') or '[]')`, `json.loads(r['op_json'])`. A single corrupt or
legacy-shaped value — a partial write, a manual edit, a row from an older
schema — raised JSONDecodeError and took out:

  * the entire eval runs list and each run's detail (issues)
  * eval datasets, including the SSE runner (cases_json)
  * the entire knowledge-graph entity list and detail (properties)
  * a bugbot review's detail (issues/fixes)
  * a spec's task graph walk (depends_on)
  * and worst: a CRDT document with one bad op_json was BRICKED — every
    load of that doc 500'd forever, because _get_doc replays the ops log
    on every open.

Verified live before the fix by inserting a rotten row into each table
and hitting the endpoint: 500 with a traceback. After: 200, the rotten
field degrades to the caller's default ([] / {} / op skipped with the raw
value still visible in the history response).

THE FIX
──────
loads_or(raw, default) joins the coercion family in
services/request_body.py — same never-raises contract as as_text /
safe_int / safe_float, for JSON strings that come from stored columns,
files, or nested request fields rather than the body itself.
"""
from __future__ import annotations

import json
import sqlite3
import uuid

from backend.services.request_body import loads_or


# ── The helper ────────────────────────────────────────────────────────────────

class TestLoadsOr:
    def test_parses_valid_json(self):
        assert loads_or('[1,2]', []) == [1, 2]
        assert loads_or('{"a": 1}', {}) == {'a': 1}

    def test_none_and_empty_mean_the_default(self):
        assert loads_or(None, []) == []
        assert loads_or('', {}) == {}

    def test_already_parsed_values_pass_through(self):
        assert loads_or([1, 2], []) == [1, 2]
        assert loads_or({'a': 1}, {}) == {'a': 1}

    def test_garbage_falls_back(self):
        assert loads_or('not json {{{', []) == []
        assert loads_or('{"unclosed": ', {}) == {}
        assert loads_or(12345, None) is None  # non-string scalar


# ── The endpoints, with a genuinely rotten row in the table ──────────────────

def _insert_rotten(table, cols, values):
    from backend.services.memory_db import get_conn
    con = get_conn()
    try:
        con.execute(f'INSERT INTO {table} ({",".join(cols)}) VALUES ({",".join("?" * len(cols))})', values)
        con.commit()
    finally:
        con.close()


def _delete(table, where, args):
    from backend.services.memory_db import get_conn
    con = get_conn()
    try:
        con.execute(f'DELETE FROM {table} WHERE {where}', args)
        con.commit()
    finally:
        con.close()


class TestRottenRowsDegrade:
    def test_eval_runs_list_survives_a_rotten_issues_row(self, client):
        rid = f'eval_zzrot{uuid.uuid4().hex[:8]}'
        cols = ('id,agent_id,prompt,response,expected,task_completion,faithfulness,'
                'hallucination,response_quality,tool_accuracy,safety_score,'
                'overall_score,latency_ms,cost_usd,tokens,model,pass_fail,issues')
        _insert_rotten('eval_runs', cols.split(','),
                       (rid, 'zz', 'p', 'r', '', 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 'm', 'pass', 'not json {{{'))
        try:
            r = client.get('/api/evals/runs')
            assert r.status_code == 200, r.text[:200]
            mine = [x for x in r.json()['runs'] if x['id'] == rid]
            assert mine, 'rotten row missing from list'
            assert mine[0]['issues'] == [], 'rotten issues should degrade to []'
        finally:
            _delete('eval_runs', 'id=?', (rid,))

    def test_kg_entity_list_survives_a_rotten_properties_row(self, client):
        eid = f'zz_rot_{uuid.uuid4().hex[:8]}'
        _insert_rotten('kg_entities', 'id,name,type,properties'.split(','),
                       (eid, 'zz Rotten', 'concept', 'garbage{not json'))
        try:
            r = client.get('/api/knowledge-graph/entities')
            assert r.status_code == 200, r.text[:200]
            mine = [e for e in r.json()['entities'] if e.get('id') == eid]
            assert mine, 'rotten entity missing from list'
            assert mine[0]['properties'] == {}, 'rotten properties should degrade to {}'
        finally:
            _delete('kg_entities', 'id=?', (eid,))

    def test_crdt_doc_with_a_rotten_op_is_not_bricked(self, client):
        """The worst instance: _get_doc replays the ops log on every open, so
        one corrupt op_json 500'd every endpoint touching that document."""
        from backend.routers import crdt as crdt_mod
        doc_id = f'doc_zzrot{uuid.uuid4().hex[:8]}'
        _insert_rotten('crdt_docs', 'id,title,content,revision'.split(','),
                       (doc_id, 'zz rotten', 'seed', 1))
        _insert_rotten('crdt_ops', 'doc_id,revision,peer_id,peer_name,op_json'.split(','),
                       (doc_id, 1, 'zz', 'ZZ', '{"type":"ins","pos":0,"text":"a"}'),
                       )
        _insert_rotten('crdt_ops', 'doc_id,revision,peer_id,peer_name,op_json'.split(','),
                       (doc_id, 2, 'zz', 'ZZ', '{{{corrupt'))
        try:
            # _get_doc caches by id; make sure a fresh load happens
            crdt_mod._docs.pop(doc_id, None)
            r = client.get(f'/api/crdt/docs/{doc_id}/history')
            assert r.status_code == 200, r.text[:200]
            hist = r.json()['history']
            revs = [h['revision'] for h in hist]
            assert 2 in revs, 'rotten op row should still be listed'
            assert [h['op'] for h in hist if h['revision'] == 2] == [None], (
                'rotten op should render as None, not crash'
            )
            assert [h['op'] for h in hist if h['revision'] == 1][0]['type'] == 'ins', (
                'valid ops must still parse'
            )
        finally:
            crdt_mod._docs.pop(doc_id, None)
            _delete('crdt_ops', 'doc_id=?', (doc_id,))
            _delete('crdt_docs', 'id=?', (doc_id,))
