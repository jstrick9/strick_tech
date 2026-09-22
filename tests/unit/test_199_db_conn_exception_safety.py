"""Unit tests — DB connection exception-safety (r74, #233)

A 2024-era pattern survived in nine handlers: `con = get_conn()` … `con.close()`
on the linear path, with the close NOT in a finally. On any exception between
acquire and close the handle was stranded in the unwinding traceback's frame.
For write paths this is not hygiene — an uncommitted transaction holds the WAL
WRITE LOCK until the handle is finalized, so every other writer in the app eats
the full busy_timeout. The first test reproduces that mechanism directly; the
rest assert each fixed handler closes its connection when its SQL raises.
"""
import sqlite3
import time

import pytest

from tests.unit.conftest import post_json


# ── Shared wrapper: a real connection that can fail on chosen SQL ─────────────
class GuardedConn:
    """Wraps a real connection; raises on statements containing `fail_on`.

    Records whether close() ran so tests can assert exception-path cleanup
    without depending on GC or fd counts.
    """

    instances = []  # per-test reset via fixture

    def __init__(self, real, fail_on=None, exc=None):
        self.real = real
        self.fail_on = fail_on
        self.exc = exc or sqlite3.OperationalError('boom: injected failure')
        self.closed = False
        GuardedConn.instances.append(self)

    def execute(self, sql, *a, **k):
        if self.fail_on and self.fail_on in sql:
            raise self.exc
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


def _guarded_get_conn(monkeypatch, target, fail_on=None, exc=None):
    """Patch `target` (module.attr path) so get_conn returns GuardedConn."""
    import importlib

    mod_name, attr = target.rsplit('.', 1)
    mod = importlib.import_module(mod_name)
    from backend.services import memory_db

    real_get_conn = memory_db.get_conn

    def patched():
        return GuardedConn(real_get_conn(), fail_on=fail_on, exc=exc)

    monkeypatch.setattr(mod, attr, patched)


class TestStrandedWriteMechanism:
    def test_uncommitted_write_blocks_writers_until_close(self, tmp_path):
        """WHY the finally matters: a stranded uncommitted INSERT holds the
        WAL write lock; a second writer gets 'database is locked' for its
        whole busy_timeout, then succeeds the instant the handle closes."""
        db = tmp_path / 'lockdemo.db'
        boot = sqlite3.connect(db)
        boot.execute('CREATE TABLE t(x)')
        boot.commit()
        boot.close()

        stranded = sqlite3.connect(db, timeout=10)
        stranded.execute('PRAGMA journal_mode=WAL')
        stranded.execute('INSERT INTO t VALUES (1)')  # uncommitted

        writer = sqlite3.connect(db, timeout=1)
        t0 = time.time()
        with pytest.raises(sqlite3.OperationalError, match='locked'):
            writer.execute('INSERT INTO t VALUES (2)')
        assert time.time() - t0 >= 0.9, 'writer should burn its full timeout'

        stranded.close()  # what the finally now guarantees immediately
        t0 = time.time()
        writer.execute('INSERT INTO t VALUES (2)')
        writer.commit()
        assert time.time() - t0 < 0.5, 'lock must release on close'
        writer.close()


class TestTasksCreate:
    def test_conn_closed_and_lock_released_when_audit_insert_fails(self, client, monkeypatch):
        """Exception between the task INSERT and commit: the finally must
        close (implicitly rolling back) so no write lock lingers."""
        _guarded_get_conn(monkeypatch, 'backend.routers.tasks.get_conn',
                          fail_on='INSERT INTO audit')

        # client fixture runs with raise_server_exceptions=False → 500 response
        r = post_json(client, '/api/tasks', {'title': 'boom task'})
        assert r.status_code == 500

        conns = GuardedConn.instances
        assert len(conns) == 1 and conns[0].closed, 'connection must be closed by finally'

        # Rollback proof: the task INSERT ran but must not have survived.
        from backend.services import memory_db
        check = memory_db.get_conn()
        try:
            n = check.execute(
                "SELECT COUNT(*) FROM tasks WHERE title = 'boom task'"
            ).fetchone()[0]
        finally:
            check.close()
        assert n == 0, 'uncommitted insert must be rolled back by close()'

    def test_conn_closed_when_kanban_select_fails(self, client, monkeypatch):
        """OperationalError is not in kanban's fallback except tuple — it
        propagates, and the finally must still close the handle."""
        _guarded_get_conn(monkeypatch, 'backend.routers.tasks.get_conn',
                          fail_on='FROM tasks')

        r = client.get('/api/kanban')
        assert r.status_code == 500, 'OperationalError is not in the fallback tuple'

        assert GuardedConn.instances and all(c.closed for c in GuardedConn.instances)


class TestGlobalSearch:
    def test_source_conns_closed_when_query_fails(self, client, monkeypatch):
        """global_search catches per-source failures and continues; the
        finally must close the failed source's connection anyway."""
        _guarded_get_conn(monkeypatch, 'backend.services.memory_db.get_conn',
                          fail_on='FROM agents')

        r = client.get('/api/search/global?q=anything')
        assert r.status_code == 200, 'search degrades gracefully, it does not 500'

        conns = GuardedConn.instances
        assert len(conns) >= 2, 'agents source failed, prompts source still ran'
        assert all(c.closed for c in conns), (
            f'leaked: {sum(1 for c in conns if not c.closed)} of {len(conns)} '
            'source connections were not closed'
        )


class TestBuilderHealth:
    def test_conn_closed_when_select1_fails(self, client, monkeypatch):
        _guarded_get_conn(monkeypatch, 'backend.services.memory_db.get_conn',
                          fail_on='SELECT 1')

        r = client.get('/api/health')
        assert r.status_code == 200
        assert r.json().get('db') == 'error'

        assert GuardedConn.instances and all(c.closed for c in GuardedConn.instances)


class TestDatabaseConnect:
    def test_connect_closes_handle_when_pragma_fails(self, monkeypatch):
        """A PRAGMA can fail after sqlite3.connect succeeded; _connect must
        close that half-built handle instead of leaking it in its frame."""
        import backend.routers.database as db_mod

        made = []

        class FakeRaw:
            def __init__(self):
                self.closed = False

            def execute(self, sql, *a):
                if 'PRAGMA' in sql:
                    raise sqlite3.OperationalError('database is locked')
                raise AssertionError(f'unexpected statement {sql!r}')

            def close(self):
                self.closed = True

        def fake_connect(*a, **k):
            c = FakeRaw()
            made.append(c)
            return c

        monkeypatch.setattr(db_mod.sqlite3, 'connect', fake_connect)
        with pytest.raises(sqlite3.OperationalError):
            db_mod._connect()

        assert made and made[0].closed, 'half-built connection must be closed on pragma failure'
