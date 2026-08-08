"""Timestamps across timezone boundaries.

THE DEFECT
──────────
SQLite's `CURRENT_TIMESTAMP` — used as a column default **141 times** in this
codebase — stores UTC as `YYYY-MM-DD HH:MM:SS` with **no timezone designator**.
A handful of routers also call naive `datetime.now().isoformat()`.

`2026-08-08 14:42:08` is not a moment in time; it is a moment in an unstated
place. The browser's guess is the damaging one:

    new Date('2026-08-08 14:42:08')    // interpreted as LOCAL time

A UTC timestamp written by the server is therefore rendered unshifted in the
user's zone. Nothing throws — the clock is simply wrong by the size of the
offset. Measured live with Chromium in Australia/Eucla (UTC+8:45): a task
created *that second* displayed as **"in 3 minutes"**, an event in the future
that had already happened.

WHY UTC+8:45 AND NOT UTC+9
──────────────────────────
A whole-hour zone makes an off-by-one-hour bug and a correct rendering look
identical whenever the server clock is near the hour. A 45-minute offset cannot
be produced by any rounding error.

THE FIX
───────
`backend/services/timestamps.py`, applied in the middleware's existing JSON
buffering pass. Rewriting 141 schema defaults would change stored data and
every query comparing against it, with no way to stop the 142nd; editing each
router is ~60 files and misses new ones. Normalising on the way out covers
every endpoint including ones added later, and cannot corrupt data at rest
because it never writes.

THE GATE BUG FOUND WHILE FIXING IT
──────────────────────────────────
The buffering pass was gated to POST/PUT/PATCH/DELETE, which is correct for
its original job (restatusing a refused write). Timestamps are returned almost
entirely by **GET**, so with the gate unchanged the fix was live and did
nothing: `/api/tasks` still returned `2026-08-08 14:42:08`. Verified before and
after.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.services import timestamps

REPO = Path(__file__).resolve().parent.parent.parent
AUDIT = REPO / 'scripts' / 'audit'
APP_SRC = (REPO / 'backend' / 'app.py').read_text(encoding='utf-8')


# ──────────────────────────────────────────────────────────────────────
#  The normaliser
# ──────────────────────────────────────────────────────────────────────
def test_naive_timestamp_gains_the_utc_designator():
    assert timestamps.normalise_value('2026-08-08 14:42:08') == '2026-08-08T14:42:08Z'
    assert timestamps.normalise_value('2026-08-08T14:42:08') == '2026-08-08T14:42:08Z'
    assert timestamps.normalise_value('2026-08-08 14:42:08.123456') == (
        '2026-08-08T14:42:08.123456Z')


def test_an_already_aware_timestamp_is_untouched():
    """Stamping a second designator onto an offset value would corrupt it."""
    for value in ('2026-08-08T14:42:08Z',
                  '2026-08-08T14:42:08+00:00',
                  '2026-08-08T14:42:08-04:00'):
        assert timestamps.normalise_value(value) == value


def test_a_date_only_value_is_untouched():
    """A calendar date pinned to a UTC instant shifts across midnight for half
    the world, turning a correct date into a wrong one."""
    assert timestamps.normalise_value('2026-08-08') == '2026-08-08'


def test_free_text_is_not_rewritten():
    """The pattern is anchored; a substring match would rewrite prose."""
    assert timestamps.normalise_value(
        'meeting on 2026-08-08 14:42:08 in room 3'
    ) == 'meeting on 2026-08-08 14:42:08 in room 3'


def test_only_time_keys_are_normalised():
    """A free-text field containing a timestamp-shaped value is not a
    timestamp."""
    body = {'created_at': '2026-08-08 14:42:08',
            'note': '2026-08-08 14:42:08'}
    out = timestamps.normalise(body)
    assert out['created_at'] == '2026-08-08T14:42:08Z'
    assert out['note'] == '2026-08-08 14:42:08'


def test_keys_that_merely_contain_time_letters_are_not_matched():
    """`timeout` and `date_format` are not moments in time."""
    assert not timestamps.is_time_key('timeout')
    assert not timestamps.is_time_key('date_format')
    assert timestamps.is_time_key('created_at')
    assert timestamps.is_time_key('updated_at')
    assert timestamps.is_time_key('last_login')


def test_nested_structures_are_walked():
    body = {'tasks': [{'created_at': '2026-08-08 14:42:08'},
                      {'created_at': '2026-08-09 01:00:00'}]}
    out = timestamps.normalise(body)
    assert out['tasks'][0]['created_at'].endswith('Z')
    assert out['tasks'][1]['created_at'].endswith('Z')


def test_an_unchanged_payload_returns_the_same_object():
    """So the middleware can cheaply skip re-serialising an untouched body."""
    body = {'created_at': '2026-08-08T14:42:08Z', 'name': 'x'}
    assert timestamps.normalise(body) is body


# ──────────────────────────────────────────────────────────────────────
#  Wiring
# ──────────────────────────────────────────────────────────────────────
def test_reads_go_through_the_normaliser(client):
    """THE GATE BUG. The buffering pass was mutating-methods-only, so the fix
    was live and did nothing -- GET is where timestamps are returned.

    The row is CREATED here rather than assumed. The first version of this
    test read whatever /api/tasks happened to contain; the test database is
    empty, so the list was empty, the naive-value list was empty, and it
    PASSED against the reverted gate. It proved nothing. A test that cannot
    fail is worse than no test because it is counted as coverage -- the eighth
    time this pattern has appeared in this review.
    """
    created = client.post('/api/tasks', json={'title': 'timezone probe'})
    assert created.status_code < 400, created.text

    r = client.get('/api/tasks')
    assert r.status_code == 200
    body = r.json()
    rows = body.get('tasks', body) if isinstance(body, dict) else body
    assert isinstance(rows, list) and rows, (
        'no rows to inspect; this test would pass vacuously')

    stamps = [row.get('created_at') for row in rows
              if isinstance(row, dict) and row.get('created_at')]
    assert stamps, 'no created_at values returned; nothing was measured'

    naive = [v for v in stamps
             if re.match(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?$', v)]
    assert not naive, f'GET returned timezone-less timestamps: {naive[:3]}'


def test_the_middleware_still_only_restatuses_mutating_methods():
    """Widening the gate must not make a GET that reports ok:false answer 400.
    A read describing state is not refusing work -- verified across all 287 GET
    endpoints in an earlier batch."""
    assert 'allow_restatus' in APP_SRC
    helper = APP_SRC[APP_SRC.index('async def _restatus_refused_write'):]
    helper = helper[:helper.index('\n\n\n')]
    assert 'allow_restatus and isinstance(parsed, dict)' in helper


def test_normalisation_shares_the_existing_buffering_pass():
    """A second middleware would buffer the body again, with a second chance
    to break SSE -- the trap already recorded in _restatus_refused_write."""
    assert APP_SRC.count('async def _restatus_refused_write') == 1
    assert '_timestamps.normalise' in APP_SRC


def test_large_bodies_are_not_walked():
    assert 'MAX_BYTES' in APP_SRC or 'MAX_BYTES' in (
        REPO / 'backend' / 'services' / 'timestamps.py').read_text(encoding='utf-8')


# ──────────────────────────────────────────────────────────────────────
#  The probe
# ──────────────────────────────────────────────────────────────────────
def test_the_probe_uses_a_non_hour_offset():
    """A whole-hour zone makes an off-by-one-hour bug and a correct rendering
    indistinguishable when the server clock is near the hour."""
    src = (AUDIT / 'timezones.py').read_text(encoding='utf-8')
    assert 'Australia/Eucla' in src
    assert '8:45' in src, 'record why a 45-minute offset was chosen'


def test_the_probe_inspects_strings_rather_than_parsing():
    """Parsing with a library that assumes UTC for naive values papers over
    exactly the defect being looked for."""
    src = (AUDIT / 'timezones.py').read_text(encoding='utf-8')
    assert 'NAIVE_ISO' in src


def test_the_probe_scopes_relative_labels_to_timestamp_elements():
    """The unscoped version matched the onboarding modal's marketing copy
    ("set up in 3 minutes"). Same trap as "Private - Ollama - Offline"."""
    src = (AUDIT / 'timezones.py').read_text(encoding='utf-8')
    assert 'onboarding' in src
    assert 'datetime]' in src or '[datetime]' in src


def test_the_audit_is_registered():
    assert 'timezones' in (AUDIT / 'run_all.py').read_text(encoding='utf-8')
    ratchet = (REPO / 'tests' / 'unit' / 'test_120_audit_ratchet.py').read_text(
        encoding='utf-8')
    assert 'timezone-correctness' in ratchet
    baseline = json.loads((AUDIT / 'baseline.json').read_text(encoding='utf-8'))
    assert baseline.get('timezone-correctness') == 0
