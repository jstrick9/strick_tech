"""A repeated write must not create a second record.

THE FINDING
───────────
Measured against the running server with `scripts/audit/concurrency.py`:

    DUPE   specs      5 concurrent identical POSTs (5 accepted) created 5 records
    DUPE   goals      5 concurrent identical POSTs (5 accepted) created 5 records
    DUPE   webhooks   5 concurrent identical POSTs (5 accepted) created 5 records
           …          Idempotency-Key ignored (5 records for one key)

Every one of those is an ordinary user event: a double-click on "Create", a
retry after a flaky connection, a request replayed when a mobile tab wakes,
the same action fired from two tabs. The user asked for one thing and got
five, then had to clean up by hand.

THE FIX
───────
`backend/services/idempotency.py` plus a claim/record pair in the existing
security middleware, so all ~390 write endpoints are covered by construction
rather than one at a time. `frontend/js/00-csrf.js` derives a key from
method + path + body inside a 10-second window, so the protection applies to
real clicks and not only to API clients that opt in.

THE AUDIT THAT FOUND IT WAS BROKEN FIRST
────────────────────────────────────────
Its first run reported `0 records created` on every endpoint and called that a
PASS. Every write had actually been rejected with 403 for a missing CSRF
token -- an audit measuring nothing looks exactly like an audit finding
nothing. The probe now authenticates, and reports BROKEN rather than ok when
no write is accepted. That guard is asserted below.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from backend.services import idempotency

REPO = Path(__file__).resolve().parent.parent.parent
AUDIT = (REPO / 'scripts' / 'audit' / 'concurrency.py').read_text(encoding='utf-8')
CSRF_JS = (REPO / 'frontend' / 'js' / '00-csrf.js').read_text(encoding='utf-8')
APP_PY = (REPO / 'backend' / 'app.py').read_text(encoding='utf-8')


@pytest.fixture(autouse=True)
def _clean_store():
    idempotency.reset()
    yield
    idempotency.reset()


# ──────────────────────────────────────────────────────────────────────
#  The store's contract
# ──────────────────────────────────────────────────────────────────────
def test_first_caller_proceeds_and_repeat_replays():
    key = idempotency.normalise_key('abc', 'POST', '/api/specs')
    assert key is not None

    state, record = idempotency.begin(key)
    assert state == 'proceed' and record is None

    idempotency.finish(key, 200, b'{"ok":true,"id":1}', 'application/json')

    state, record = idempotency.begin(key)
    assert state == 'replay'
    assert record.status == 200
    assert record.body == b'{"ok":true,"id":1}'


def test_concurrent_second_caller_gets_conflict_not_a_race():
    """This is what makes a concurrent double-submit safe.

    A guard that only handles sequential repeats leaves the exact case a
    double-click produces: two requests in flight at once.
    """
    key = idempotency.normalise_key('abc', 'POST', '/api/specs')
    assert idempotency.begin(key)[0] == 'proceed'
    assert idempotency.begin(key)[0] == 'conflict'


def test_failures_are_not_replayed():
    """Replaying an error would block a legitimate retry after a blip."""
    key = idempotency.normalise_key('abc', 'POST', '/api/specs')
    idempotency.begin(key)
    idempotency.finish(key, 500, b'{"ok":false}', 'application/json')
    # The key is released, so the next attempt runs the handler again.
    assert idempotency.begin(key)[0] == 'proceed'


def test_keys_are_scoped_to_method_and_path():
    """Two endpoints must not collide because a client reused a key."""
    a = idempotency.normalise_key('same', 'POST', '/api/specs')
    b = idempotency.normalise_key('same', 'POST', '/api/goals')
    c = idempotency.normalise_key('same', 'DELETE', '/api/specs')
    assert len({a, b, c}) == 3


def test_reads_and_missing_keys_are_ignored():
    """No key means no behaviour change; nothing is deduplicated implicitly.

    Two genuinely-intended identical records must remain possible.
    """
    assert idempotency.normalise_key(None, 'POST', '/api/specs') is None
    assert idempotency.normalise_key('', 'POST', '/api/specs') is None
    assert idempotency.normalise_key('abc', 'GET', '/api/specs') is None


def test_oversized_keys_are_rejected():
    assert idempotency.normalise_key('x' * 5000, 'POST', '/api/specs') is None


def test_released_key_can_be_retried():
    key = idempotency.normalise_key('abc', 'POST', '/api/specs')
    idempotency.begin(key)
    idempotency.release(key)
    assert idempotency.begin(key)[0] == 'proceed'


def test_store_is_bounded():
    """A client generating unique keys must not grow memory without bound."""
    for i in range(idempotency.MAX_ENTRIES + 500):
        key = idempotency.normalise_key(f'k{i}', 'POST', '/api/specs')
        idempotency.begin(key)
        idempotency.finish(key, 200, b'{}', 'application/json')
    assert idempotency.stats()['entries'] <= idempotency.MAX_ENTRIES


def test_store_is_threadsafe_under_a_burst():
    """Only one of N concurrent claims may proceed."""
    key = idempotency.normalise_key('burst', 'POST', '/api/specs')
    with ThreadPoolExecutor(max_workers=16) as pool:
        states = list(pool.map(lambda _: idempotency.begin(key)[0], range(16)))
    assert states.count('proceed') == 1
    assert states.count('conflict') == 15


# ──────────────────────────────────────────────────────────────────────
#  Wiring
# ──────────────────────────────────────────────────────────────────────
def test_middleware_claims_and_records():
    """Covered in middleware, not per endpoint.

    There are ~390 write routes; a rule applied at one call site is a rule
    the next call site forgets.
    """
    assert 'idempotency.normalise_key(' in APP_PY
    assert 'idempotency.begin(' in APP_PY
    assert 'idempotency.finish(' in APP_PY
    assert "'Idempotency-Replayed'" in APP_PY
    assert 'status_code=409' in APP_PY, 'an in-flight duplicate should conflict'


def test_bookkeeping_cannot_break_a_response():
    section = APP_PY[APP_PY.index('idempotency.finish('):]
    section = section[:section.index('X-Request-ID')]
    assert 'except Exception' in section, (
        'a failure while recording must never propagate into the response')


def test_frontend_sends_a_key_on_writes():
    """Server support alone protects nothing until a client sends the header."""
    assert 'Idempotency-Key' in CSRF_JS
    assert 'IDEMPOTENCY_WINDOW_MS' in CSRF_JS


def test_frontend_never_overwrites_an_explicit_key():
    assert "!headers.has('Idempotency-Key')" in CSRF_JS


def test_frontend_key_covers_method_path_and_body():
    """A key derived from the path alone would collapse different creates."""
    section = CSRF_JS[CSRF_JS.index("!headers.has('Idempotency-Key')"):]
    section = section[:section.index('init = Object.assign')]
    assert 'method' in section and 'pathname' in section and 'bodyText' in section


def test_frontend_key_generation_cannot_block_a_request():
    section = CSRF_JS[CSRF_JS.index("!headers.has('Idempotency-Key')"):]
    section = section[:section.index('init = Object.assign')]
    assert 'catch' in section, 'a key is an optimisation, never a hard dependency'


# ──────────────────────────────────────────────────────────────────────
#  The audit must not be able to pass by measuring nothing
# ──────────────────────────────────────────────────────────────────────
def test_audit_authenticates():
    """Its first run reported 0 records created as a PASS.

    Every write had been rejected 403 for a missing CSRF token.
    """
    # Assert the token is attached to the POST specifically, not merely that
    # the string appears somewhere in the file. An earlier version of this
    # test passed after the header was removed from _post(), because the
    # DELETE cleanup path still mentioned it.
    post_fn = AUDIT[AUDIT.index('def _post('):]
    post_fn = post_fn[:post_fn.index('\ndef ')]
    assert '_csrf_token()' in post_fn, (
        'writes must carry a CSRF token, or every one is rejected 403 and '
        'the audit measures nothing while reporting a pass')

    delete_fn = AUDIT[AUDIT.index('def _delete_matching('):]
    delete_fn = delete_fn[:delete_fn.index('\ndef ')]
    assert '_csrf_token()' in delete_fn, (
        'cleanup must authenticate too, or leftover records pollute the '
        'next run')


def test_audit_reports_broken_when_no_write_is_accepted():
    assert 'BROKEN' in AUDIT
    assert re.search(r'if accepted == 0', AUDIT), (
        'zero accepted writes means the probe is broken, not that the '
        'endpoint is safe')
