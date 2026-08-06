"""List endpoints are bounded, and always say what they are not showing.

THE TWO OPPOSITE BUGS THIS SITS BETWEEN
───────────────────────────────────────
1. Unbounded. 28 GET endpoints returned every row with no `limit` and no UI
   paging. Measured: 331 seeded specs -> 81 KB in one response, all 331
   rendered into innerHTML in a single pass. It grows without bound.

2. Silently capped. Already on record in 26-autonomous-hunt.md: goals were
   capped at 100 of 724 and the UI said nothing, so 624 were unreachable.

Both are the same mistake -- the response does not describe its own
completeness. The envelope in services/pagination.py fixes both by always
carrying `total` and `has_more`.
"""
import pytest

from backend.services.pagination import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    clamp_limit,
    clamp_offset,
    page,
)

# ══ The clamps ════════════════════════════════════════════════════════════════

@pytest.mark.parametrize('given,expected', [
    (10, 10),
    (None, DEFAULT_LIMIT),
    ('', DEFAULT_LIMIT),
    ('abc', DEFAULT_LIMIT),
    (0, DEFAULT_LIMIT),
    (-1, DEFAULT_LIMIT),      # the one that mattered
    (-999, DEFAULT_LIMIT),
    (10_000, MAX_LIMIT),
])
def test_limit_is_clamped_on_both_sides(given, expected):
    """A NEGATIVE limit is the dangerous case.

    `LIMIT -1` in SQLite means UNLIMITED, not "none" -- which is how
    `/api/audit?limit=-1` previously returned 1398 rows against a cap of 2.
    A one-sided `min(limit, MAX)` lets that straight through, so both ends are
    clamped here and no call site has to remember it.
    """
    assert clamp_limit(given) == expected


@pytest.mark.parametrize('given,expected', [(5, 5), (0, 0), (-3, 0), (None, 0), ('x', 0)])
def test_offset_is_never_negative(given, expected):
    assert clamp_offset(given) == expected


# ══ The envelope ══════════════════════════════════════════════════════════════

def test_the_envelope_reports_completeness():
    """`total` and `has_more` are the whole point.

    Without them a truncated list is indistinguishable from a complete one,
    which is exactly how 624 goals went missing.
    """
    body = page(['a', 'b'], key='specs', total=10, limit=2, offset=0)
    assert body['specs'] == ['a', 'b']
    assert body['count'] == 2
    assert body['total'] == 10
    assert body['has_more'] is True


def test_has_more_is_false_on_the_last_page():
    body = page(['i', 'j'], key='specs', total=10, limit=2, offset=8)
    assert body['has_more'] is False


def test_has_more_is_false_when_everything_fits():
    body = page(['a'], key='specs', total=1, limit=100, offset=0)
    assert body['has_more'] is False


def test_count_still_means_what_it_used_to():
    """Existing callers read `count`; it keeps the meaning it had when the list
    was always complete."""
    body = page(['a', 'b', 'c'], key='pipelines', total=3, limit=100, offset=0)
    assert body['count'] == len(body['pipelines']) == 3


# ══ End to end through the API ════════════════════════════════════════════════

def _make_specs(client, n, prefix='PgTest'):
    made = 0
    for i in range(n):
        r = client.post('/api/specs', json={'title': f'{prefix} {i:03d}', 'description': 'x'})
        if r.status_code == 200:
            made += 1
    return made


def test_specs_are_paginated_and_report_the_true_total(client):
    created = _make_specs(client, 12, prefix='PgAlpha')
    if created == 0:
        pytest.skip('specs endpoint unavailable in this build')

    first = client.get('/api/specs?limit=5').json()
    assert first['count'] == 5, 'limit was ignored'
    assert first['total'] >= created, 'total does not reflect everything that exists'
    assert first['has_more'] is True

    # The page actually moves.
    second = client.get('/api/specs?limit=5&offset=5').json()
    assert second['count'] == 5
    ids_a = {s['id'] for s in first['specs']}
    ids_b = {s['id'] for s in second['specs']}
    assert not (ids_a & ids_b), 'offset returned overlapping rows'


def test_a_negative_limit_does_not_dump_the_table(client):
    """The regression that motivated clamping on both sides."""
    _make_specs(client, 3, prefix='PgNeg')
    body = client.get('/api/specs?limit=-1').json()
    assert body['limit'] == DEFAULT_LIMIT
    assert body['count'] <= DEFAULT_LIMIT


def test_an_absurd_limit_is_capped(client):
    body = client.get('/api/specs?limit=99999').json()
    assert body['limit'] <= MAX_LIMIT


def test_search_filters_server_side_and_narrows_the_total(client):
    created = _make_specs(client, 4, prefix='PgFindMe')
    if created == 0:
        pytest.skip('specs endpoint unavailable')
    _make_specs(client, 2, prefix='PgOther')

    all_body = client.get('/api/specs?limit=500').json()
    hit = client.get('/api/specs?q=PgFindMe&limit=500').json()

    assert hit['total'] < all_body['total'], 'search did not narrow the result set'
    assert hit['total'] >= created
    assert all('PgFindMe' in s['title'] for s in hit['specs']), 'search returned non-matching rows'


def test_rag_pipelines_are_paginated_too(client):
    body = client.get('/api/rag/pipelines?limit=3').json()
    for field in ('count', 'total', 'limit', 'offset', 'has_more'):
        assert field in body, f'rag pipelines envelope is missing {field}'
    assert body['limit'] == 3


def test_the_ui_shows_what_it_is_not_showing():
    """A capped list that does not say so is the bug, not the cap."""
    import os
    import re

    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(repo, 'frontend', 'js', '03-features-b.js'), encoding='utf-8') as fh:
        src = fh.read()
    code = '\n'.join(ln for ln in src.split('\n') if not ln.strip().startswith('//'))

    assert 'specRenderListFooter' in code, 'the "showing X of Y" footer is gone'
    assert re.search(r"Showing '\s*\+\s*shown\s*\+\s*' of '\s*\+\s*_specTotal", code), (
        'the footer no longer reports the real total'
    )
    assert 'specLoadMore' in code, 'there is no way to reach the rest of the list'
    assert 'specSearch' in code, 'the search control is gone'
    assert "params.set('q'" in code, 'search is no longer sent to the server'
