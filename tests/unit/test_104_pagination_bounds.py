"""A caller must not be able to bypass the pagination cap.

THE BUG
───────
65 handlers clamp a caller-supplied limit with `min(limit, 500)`. That bounds
the top and leaves the bottom wide open — and **a negative LIMIT means
UNLIMITED in SQLite**:

    SELECT * FROM t LIMIT -1   ->  every row

Demonstrated on a 1000-row table: `LIMIT -1` and `LIMIT -500` both returned all
1000. So `?limit=-1` walked straight past whatever cap the author wrote.

Measured against the running server before the fix:

    GET /api/audit?limit=2   ->     2 rows
    GET /api/audit?limit=-1  ->  1398 rows

Six endpoints were exploitable this way, the audit log worst of all — it is
the largest table in the platform and the one most likely to grow without
bound. It is a denial-of-service shape (unbounded response assembled in
memory) and it silently defeats the "Showing N of M" truncation notices, which
assume the page size is what the server said it was.

`audit_log.py` already used `max(offset, 0)` on the neighbouring value, so the
two-sided form was established in the codebase; the limit clamps never got it.

A floor of 1 rather than 0: `?limit=0` returning an empty page is a confusing
answer to a question nobody means to ask.
"""

from __future__ import annotations

import pathlib
import re
import sqlite3

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ROUTERS = ROOT / 'backend' / 'routers'

LIST_ROUTES = [
    '/api/goals',
    '/api/prompts',
    '/api/audit',
    '/api/e2e/history',
    '/api/marketplace/featured',
    '/api/marketplace/trending',
    '/api/marketplace/new-arrivals',
    '/api/profiler/endpoints',
]


def _count(payload) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list):
                return len(value)
    return 0


def test_sqlite_really_does_treat_negative_limit_as_unlimited():
    """The premise. Recorded so the fix is not mistaken for cargo cult."""
    con = sqlite3.connect(':memory:')
    con.execute('CREATE TABLE t(x)')
    con.executemany('INSERT INTO t VALUES(?)', [(i,) for i in range(100)])
    assert len(con.execute('SELECT * FROM t LIMIT ?', (-1,)).fetchall()) == 100
    assert len(con.execute('SELECT * FROM t LIMIT ?', (5,)).fetchall()) == 5


@pytest.mark.parametrize('path', LIST_ROUTES)
def test_a_negative_limit_cannot_beat_a_small_one(client, path):
    small = _count(client.get(f'{path}?limit=2').json())
    negative = _count(client.get(f'{path}?limit=-1').json())
    assert negative <= max(small, 1), (
        f'{path}: limit=-1 returned {negative} rows against {small} for '
        f'limit=2 — the cap is bypassable'
    )


@pytest.mark.parametrize('path', LIST_ROUTES)
def test_a_huge_limit_is_capped(client, path):
    huge = _count(client.get(f'{path}?limit=999999999').json())
    assert huge <= 10000, f'{path} returned {huge} rows for an absurd limit'


def test_a_zero_limit_still_returns_something(client):
    """Floor of 1, not 0: an empty page is a confusing answer to a question
    nobody means to ask.

    Seeds a row first — the in-process test database starts empty, so an
    assertion against whatever happens to be there would pass or fail on
    ordering rather than on the clamp.
    """
    created = client.post('/api/goals', json={
        'title': 'limit-floor probe', 'description': 'd', 'success_criteria': 's',
    })
    assert created.status_code == 200
    gid = created.json()['goal_id']
    try:
        assert _count(client.get('/api/goals?limit=0').json()) >= 1
    finally:
        client.delete(f'/api/goals/{gid}')


def test_a_normal_limit_is_respected(client):
    """The clamp must not break the ordinary case it exists to bound."""
    assert _count(client.get('/api/goals?limit=3').json()) <= 3


# ══ The data layer clamps too ═════════════════════════════════════════════════
@pytest.mark.parametrize('fn,args', [
    ('memory_search_fts', ('x', -1)),
    ('memory_list', (-1,)),
    ('audit_list', (-1,)),
])
def test_the_data_layer_floors_its_own_limits(fn, args):
    """Defence in depth: a future route that forgets the clamp inherits one.

    Seeds more rows than the requested page so an UNCLAMPED negative limit is
    actually observable. Asserting against an almost-empty table would pass
    whether or not the clamp exists -- verified by reverting it.
    """
    from backend.services import memory_db

    for i in range(12):
        memory_db.memory_add(f'bounds_probe_{i}', 'x', '')
        memory_db.audit_log('bounds_probe', str(i))

    rows = getattr(memory_db, fn)(*args)
    assert len(rows) <= 5, (
        f'{fn} returned {len(rows)} rows for limit=-1; a negative limit is '
        f'UNLIMITED in SQLite, so the clamp needs a floor'
    )


# ══ Keep the one-sided form from coming back ══════════════════════════════════
ONE_SIDED = re.compile(r'(?<!max\(1, )min\(\s*(?:limit|lim|count|top_k)\s*,\s*\d+\s*\)')


def test_no_router_uses_a_one_sided_limit_clamp():
    offenders = []
    for path in sorted(ROUTERS.glob('*.py')):
        text = path.read_text(encoding='utf-8')
        for m in ONE_SIDED.finditer(text):
            line = text[: m.start()].count('\n') + 1
            offenders.append(f'{path.name}:{line}  {m.group(0)}')
    assert not offenders, (
        'min(limit, N) has no floor, and a negative LIMIT is UNLIMITED in '
        'SQLite:\n  ' + '\n  '.join(offenders[:20])
        + '\n\nUse max(1, min(limit, N)).'
    )
