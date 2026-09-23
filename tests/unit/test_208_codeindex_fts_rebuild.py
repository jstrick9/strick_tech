"""Unit tests — codeindex FTS rebuild hoisting (r79, #242)

index_directory called _index_file per file, and each call rebuilt the
FULL code_symbols_fts index — F files meant F rebuilds of an index
holding S symbols, so re-indexing cost O(F*S), growing quadratically as
the index grew. Measured on this repo's own backend tree (136 files,
2,190 symbols): re-index 3642ms -> 2873ms; the rebuild term itself is
136 x ~5ms today and scales with S (at 10x symbols, ~7s of pure rebuild
per run).

The rebuild now happens ONCE per run, after the loop. The per-file
commit stays: a file is the durability unit, and a bad file rolls back
only itself. _index_file keeps rebuild_fts=True as the default so any
future single-file caller keeps the old behavior.

Honesty note recorded in the commit: code_symbols_fts is currently
WRITE-ONLY — no query in backend/, frontend/, scripts/, or tests/ reads
it (symbol search queries code_symbols directly). The single rebuild
per run keeps the table coherent at minimal cost for future/external
SQL use rather than dropping it.
"""
import sqlite3
from pathlib import Path

from tests.unit.conftest import assert_ok, post_json


def _preview_dir() -> Path:
    from backend.config import get_data_dir

    d = get_data_dir() / 'preview'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_project():
    d = _preview_dir()
    (d / 'alpha_r79.py').write_text(
        'def alpha_one():\n    """first."""\n    return 1\n\n\ndef alpha_two(x):\n    return x + 1\n',
        encoding='utf-8',
    )
    (d / 'beta_r79.py').write_text(
        'import json\n\n\nclass BetaThing:\n    def method_a(self):\n        return json.dumps({})\n',
        encoding='utf-8',
    )
    return d


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


class TestIndexDirectory:
    def test_multi_file_run_does_exactly_one_fts_rebuild(self, client, monkeypatch):
        _write_project()
        from backend.services import memory_db

        opened = []
        real = memory_db.get_conn

        def counting():
            c = CountingCon(real())
            opened.append(c)
            return c

        monkeypatch.setattr(memory_db, 'get_conn', counting)

        d = assert_ok(post_json(client, '/api/codeindex/index', {}))
        assert d['ok'] is True
        assert d['indexed_files'] >= 2
        assert d['errors'] == 0

        rebuilds = sum(c.rebuilds for c in opened)
        assert rebuilds == 1, (
            f'{rebuilds} FTS rebuilds for a {d["indexed_files"]}-file run — '
            'the per-file rebuild is back'
        )

    def test_indexed_symbols_are_searchable(self, client):
        _write_project()
        d = assert_ok(post_json(client, '/api/codeindex/index', {}))
        assert d['ok'] is True

        rows = assert_ok(client.get('/api/codeindex/symbols?q=alpha'))['symbols']
        assert any(r['symbol_name'] == 'alpha_one' for r in rows)
        rows = assert_ok(client.get('/api/codeindex/symbols?q=BetaThing&type=class'))['symbols']
        assert any(r['symbol_name'] == 'BetaThing' for r in rows)

    def test_fts_table_is_coherent_after_the_single_rebuild(self, client):
        """The one rebuild must leave code_symbols_fts consistent with
        code_symbols — a batch that forgot the rebuild entirely would
        leave the FTS table stale."""
        _write_project()
        assert_ok(post_json(client, '/api/codeindex/index', {}))

        from backend.services.memory_db import db_path

        con = sqlite3.connect(db_path())
        try:
            n_syms = con.execute(
                "SELECT COUNT(*) FROM code_symbols WHERE filepath LIKE '%r79.py'"
            ).fetchone()[0]
            n_fts = con.execute(
                "SELECT COUNT(*) FROM code_symbols_fts WHERE code_symbols_fts MATCH 'alpha OR beta'"
            ).fetchone()[0]
        finally:
            con.close()
        assert n_syms >= 3
        assert n_fts >= 3, (
            f'FTS holds {n_fts} matching rows for {n_syms} indexed symbols — '
            'the end-of-run rebuild did not run'
        )


class TestIndexFileDefault:
    def test_direct_call_still_rebuilds_by_default(self, monkeypatch):
        """rebuild_fts defaults to True: any future single-file caller
        (e.g. a file-save hook) keeps the index coherent per call."""
        from backend.routers.codeindex import _index_file
        from backend.services import memory_db

        opened = []
        real = memory_db.get_conn

        def counting():
            c = CountingCon(real())
            opened.append(c)
            return c

        monkeypatch.setattr(memory_db, 'get_conn', counting)
        n = _index_file('default_r79.py', 'def default_fn():\n    return 1\n')
        assert n >= 1
        assert sum(c.rebuilds for c in opened) == 1
