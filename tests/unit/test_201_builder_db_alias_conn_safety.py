"""Unit tests — builder.py DB() alias connection safety (r75, #236)

builder.py aliases the connection factory at module scope:

    DB = memory_db.get_conn

so every `con = DB()` call site was INVISIBLE to #233's close-in-finally
sweep, which matched the get_conn name. Seven acquisitions across six
functions (save / history / version / restore ×2 / commit / scaffold)
closed on the linear path only — the same class #233 fixed: an exception
between acquire and close stranded the handle, and on the write paths an
uncommitted transaction held the WAL write lock until GC. preview_scaffold
held its connection across ~200 lines of template construction, where
write_rel's except tuple does NOT include sqlite3.OperationalError, so a
lock timeout inside its version INSERT escaped with the handle.

The first test is the static regression guard: an alias-aware AST audit of
backend/routers/builder.py asserting every DB()/get_conn() acquisition
closes in a finally. The rest exercise each write path live with a real
connection that fails on chosen SQL, asserting close + rollback.
"""
import ast
import pathlib
import sqlite3
from unittest.mock import patch

import pytest

from tests.unit.conftest import post_json


class GuardedConn:
    """Real connection that raises on statements containing `fail_on`;
    records whether close() ran."""

    instances = []

    def __init__(self, real, fail_on=None):
        self.real = real
        self.fail_on = fail_on
        self.closed = False
        GuardedConn.instances.append(self)

    def execute(self, sql, *a, **k):
        if self.fail_on and self.fail_on in sql:
            raise sqlite3.OperationalError('boom: injected failure')
        return self.real.execute(sql, *a, **k)

    def commit(self):
        return self.real.commit()

    def close(self):
        self.closed = True
        return self.real.close()

    def __getattr__(self, name):
        return getattr(self.real, name)


@pytest.fixture(autouse=True)
def _reset_instances():
    GuardedConn.instances.clear()
    yield
    GuardedConn.instances.clear()


def _guarded_db(monkeypatch, fail_on=None):
    import backend.routers.builder as builder
    from backend.services import memory_db

    real = memory_db.get_conn

    def patched():
        return GuardedConn(real(), fail_on=fail_on)

    monkeypatch.setattr(builder, 'DB', patched)


class TestStaticAudit:
    def test_every_db_alias_acquisition_closes_in_finally(self):
        """The audit that found this unit, run as a regression guard: any
        future `con = DB()` (or get_conn) in builder.py without a
        finally-close fails here."""
        src = (pathlib.Path(__file__).resolve().parents[2]
               / 'backend' / 'routers' / 'builder.py').read_text()
        tree = ast.parse(src)

        def closes_in_finally(fn, var):
            for sub in ast.walk(fn):
                if isinstance(sub, ast.Try):
                    for stmt in sub.finalbody:
                        for s2 in ast.walk(stmt):
                            if (isinstance(s2, ast.Expr) and isinstance(s2.value, ast.Call)
                                    and isinstance(s2.value.func, ast.Attribute)
                                    and s2.value.func.attr == 'close'
                                    and isinstance(s2.value.func.value, ast.Name)
                                    and s2.value.func.value.id == var):
                                return True
            return False

        acquisitions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Assign) and isinstance(sub.value, ast.Call) \
                            and isinstance(sub.value.func, ast.Name) \
                            and sub.value.func.id in ('DB', 'get_conn'):
                        for t in sub.targets:
                            if isinstance(t, ast.Name):
                                acquisitions.append((node.name, t.id))
        assert acquisitions, 'audit found no acquisitions — the guard itself broke'

        unguarded = [f'{fn}({var})' for fn, var in acquisitions
                     if not closes_in_finally(
                         next(n for n in ast.walk(tree)
                              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                              and n.name == fn), var)]
        assert not unguarded, (
            f'DB()/get_conn() acquisition without finally-close: {unguarded} '
            '— see #233/#236 for the WAL-write-lock mechanism'
        )


class TestPreviewSave:
    def test_conn_closed_and_version_rolled_back_when_audit_insert_fails(self, client, monkeypatch):
        _guarded_db(monkeypatch, fail_on='INSERT INTO audit')

        r = post_json(client, '/api/preview/save',
                      {'path': 'conn_safety.html', 'content': '<p>v1</p>'})
        assert r.status_code == 500

        conns = GuardedConn.instances
        assert len(conns) == 1 and conns[0].closed, 'finally must close the handle'

        from backend.services import memory_db
        check = memory_db.get_conn()
        try:
            n = check.execute(
                "SELECT COUNT(*) FROM file_versions WHERE path='conn_safety.html'"
            ).fetchone()[0]
        finally:
            check.close()
        assert n == 0, 'uncommitted version INSERT must be rolled back by close()'


class TestPreviewCommit:
    def test_conn_closed_and_insert_rolled_back_when_rowid_fetch_fails(self, client, monkeypatch):
        _guarded_db(monkeypatch, fail_on='last_insert_rowid')

        r = post_json(client, '/api/preview/commit', {'path': 'index.html'})
        assert r.status_code == 500
        assert GuardedConn.instances and all(c.closed for c in GuardedConn.instances)


class TestPreviewRestore:
    def test_conn_closed_when_version_lookup_fails(self, client, monkeypatch):
        _guarded_db(monkeypatch, fail_on='FROM file_versions')

        r = post_json(client, '/api/preview/restore', {'version_id': 1})
        assert r.status_code == 500
        assert GuardedConn.instances and all(c.closed for c in GuardedConn.instances)


class TestPreviewScaffold:
    def test_conn_closed_when_version_insert_raises_through_write_rel(self, client, monkeypatch):
        """write_rel's except tuple excludes sqlite3.OperationalError, so a
        failing version INSERT escapes the 200-line scaffold body — the
        finally must still close (and roll back) the handle."""
        _guarded_db(monkeypatch, fail_on='INSERT INTO file_versions')

        r = post_json(client, '/api/preview/scaffold', {'prompt': 'plain app'})
        assert r.status_code == 500

        conns = GuardedConn.instances
        assert conns and all(c.closed for c in conns), 'scaffold handle must close on escape'

        from backend.services import memory_db
        check = memory_db.get_conn()
        try:
            n = check.execute(
                "SELECT COUNT(*) FROM file_versions WHERE author='scaffolder'"
            ).fetchone()[0]
        finally:
            check.close()
        assert n == 0, 'partial scaffold versions must be rolled back, not stranded'
