"""Unit tests — knowledge-graph extract persistence (r79, #241)

The /extract endpoint pasted add_entity()'s single-entity pattern into a
loop: a fresh connection, a commit, and a FULL kg_entities_fts index
rebuild after EVERY entity. N extracted entities meant N connections, N
commits, and N rebuilds of an index holding M rows — measured at 50k
pre-existing rows, a 20-entity extraction took 1677ms of pure DB churn
after the LLM call. The fix persists the whole extraction (entities,
relations, facts) on ONE connection in ONE transaction with ONE FTS
rebuild — 81ms under the same conditions, identical results. The
all-or-nothing transaction is also safer crash semantics: relations and
facts reference the entity ids created in the first loop, so a
half-committed extraction could strand rows referencing nothing.

Also: the upsert lookup (WHERE name=? AND type=?) had no index — the PK
is the synthetic id — so every upsert in add_entity() and every per-
entity lookup in extract() scanned the table. idx_kg_ent_name(name, type)
added next to the existing indexes in _SCHEMA.
"""
import json
import sqlite3
from unittest.mock import patch

from tests.unit.conftest import assert_ok, post_json


def _db():
    from backend.services.memory_db import db_path, get_conn

    get_conn().close()
    return sqlite3.connect(db_path())


PAYLOAD = {
    'entities': [
        {'name': 'Alpha', 'type': 'concept', 'description': 'first'},
        {'name': 'Beta', 'type': 'tool', 'description': 'second'},
        {'name': 'Gamma', 'type': 'person', 'description': 'third'},
    ],
    'relations': [
        {'from': 'Alpha', 'to': 'Beta', 'relation': 'USES'},
        {'from': 'Beta', 'to': 'Alpha', 'relation': 'RELATED_TO'},  # dup, IGNOREd
        {'from': 'Alpha', 'to': 'Nowhere', 'relation': 'USES'},     # no such entity
    ],
    'facts': [
        {'subject': 'Alpha', 'predicate': 'has', 'object': 'value'},
        {'subject': 'Nowhere', 'predicate': 'has', 'object': 'x'},  # no such entity
    ],
}


def _mock_llm(payload):
    async def fake_complete(messages, **kw):
        return {'text': json.dumps(payload), 'tokens': 10, 'model': 'mock'}
    return fake_complete


class CountingCon:
    def __init__(self, real):
        self.real = real
        self.rebuilds = 0

    def execute(self, sql, *a, **k):
        if 'rebuild' in sql:
            self.rebuilds += 1
        return self.real.execute(sql, *a, **k)

    def commit(self):
        return self.real.commit()

    def close(self):
        return self.real.close()

    def __getattr__(self, name):
        return getattr(self.real, name)


class TestExtractPersists:
    def test_all_three_phases_persisted(self, client):
        with patch('backend.services.llm.complete', new=_mock_llm(PAYLOAD)):
            d = assert_ok(post_json(client, '/api/knowledge-graph/extract',
                                    {'text': 'text about alpha beta gamma'}))
        assert d['ok'] is True
        assert d['entities_created'] == 3
        assert d['relations_created'] == 2, 'relations to unknown entities must be skipped; reversed pairs are distinct'
        assert d['facts_created'] == 1, 'facts about unknown entities must be skipped'

        con = _db()
        try:
            ents = con.execute(
                "SELECT name FROM kg_entities WHERE name IN ('Alpha','Beta','Gamma')"
            ).fetchall()
            rels = con.execute(
                "SELECT COUNT(*) FROM kg_relations WHERE source='text_extraction'"
            ).fetchone()[0]
            facts = con.execute(
                "SELECT COUNT(*) FROM kg_facts WHERE source='text_extraction'"
            ).fetchone()[0]
        finally:
            con.close()
        assert len(ents) == 3
        assert rels == 2
        assert facts == 1

    def test_re_extraction_upserts_without_duplicates(self, client):
        with patch('backend.services.llm.complete', new=_mock_llm(PAYLOAD)):
            assert_ok(post_json(client, '/api/knowledge-graph/extract', {'text': 'first pass'}))
        updated = dict(PAYLOAD)
        updated['entities'] = [
        dict(e, description='revised') if e['name'] == 'Alpha' else e for e in PAYLOAD['entities']]
        with patch('backend.services.llm.complete', new=_mock_llm(updated)):
            d = assert_ok(post_json(client, '/api/knowledge-graph/extract', {'text': 'second pass'}))

        con = _db()
        try:
            n = con.execute(
                "SELECT COUNT(*) FROM kg_entities WHERE name IN ('Alpha','Beta','Gamma')"
            ).fetchone()[0]
            desc = con.execute(
                "SELECT description FROM kg_entities WHERE name='Alpha'"
            ).fetchone()[0]
        finally:
            con.close()
        assert n == 3, 're-extraction must upsert, not duplicate'
        assert desc == 'revised', 'upsert must refresh the description'


class TestSingleTransaction:
    def test_one_connection_and_one_fts_rebuild_per_extraction(self, client, monkeypatch):
        from backend.services import memory_db

        opened = []

        real = memory_db.get_conn

        def counting():
            c = CountingCon(real())
            opened.append(c)
            return c

        # extract imports get_conn at call time from memory_db
        monkeypatch.setattr(memory_db, 'get_conn', counting)

        with patch('backend.services.llm.complete', new=_mock_llm(PAYLOAD)):
            assert_ok(post_json(client, '/api/knowledge-graph/extract', {'text': 'probe'}))

        assert len(opened) == 1, (
            f'extraction opened {len(opened)} connections — the per-entity '
            'connection churn is back'
        )
        assert opened[0].rebuilds == 1, (
            f'FTS rebuilt {opened[0].rebuilds} times — the per-entity rebuild is back'
        )

    def test_failed_write_rolls_back_the_whole_extraction(self, client, monkeypatch):
        """All-or-nothing: an exception mid-extraction must not leave partial
        rows (the old per-entity commits persisted everything before the
        failure)."""
        from backend.services import memory_db

        real = memory_db.get_conn

        class FailingCon(CountingCon):
            def __init__(self, real):
                super().__init__(real)
                self.entities_seen = 0

            def execute(self, sql, *a, **k):
                if 'INSERT INTO kg_entities' in sql:
                    self.entities_seen += 1
                    if self.entities_seen == 3:  # fail on the third entity
                        raise sqlite3.OperationalError('boom: injected')
                return super().execute(sql, *a, **k)

        def failing():
            return FailingCon(real())

        monkeypatch.setattr(memory_db, 'get_conn', failing)

        payload = dict(PAYLOAD)
        payload['entities'] = [
            {'name': f'E{i}', 'type': 'concept', 'description': 'x'} for i in range(5)
        ]
        with patch('backend.services.llm.complete', new=_mock_llm(payload)):
            r = post_json(client, '/api/knowledge-graph/extract', {'text': 'rollback probe'})
        assert r.status_code == 500

        con = _db()
        try:
            n = con.execute(
                "SELECT COUNT(*) FROM kg_entities WHERE name IN ('E0','E1','E2','E3','E4')"
            ).fetchone()[0]
        finally:
            con.close()
        assert n == 0, 'partial extraction must roll back, not persist'


class TestUpsertIndex:
    def test_name_type_index_exists(self):
        con = _db()
        try:
            idx = {r[1] for r in con.execute('PRAGMA index_list(kg_entities)')}
        finally:
            con.close()
        assert 'idx_kg_ent_name' in idx
        assert 'idx_kg_ent_type' in idx, 'the type-only filter index must survive'

    def test_upsert_lookup_seeks(self):
        con = _db()
        try:
            plans = ' | '.join(r[-1] for r in con.execute(
                'EXPLAIN QUERY PLAN SELECT id FROM kg_entities WHERE name=? AND type=?',
                ('x', 'y')))
        finally:
            con.close()
        assert 'USING INDEX idx_kg_ent_name' in plans, plans


class TestManualAddEntity:
    def test_add_entity_still_works(self, client):
        d = assert_ok(post_json(client, '/api/knowledge-graph/entities',
                                {'name': 'Manual One', 'type': 'concept',
                                 'description': 'handmade'}))
        assert d['ok'] is True and d['entity_id']
        con = _db()
        try:
            row = con.execute(
                "SELECT description FROM kg_entities WHERE name='Manual One'"
            ).fetchone()
        finally:
            con.close()
        assert row and row[0] == 'handmade'
