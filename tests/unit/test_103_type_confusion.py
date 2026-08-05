"""A wrong-typed field must not crash the server.

THE BUG
───────
22 POST endpoints answered **HTTP 500** when a field arrived with the wrong
JSON type, including core ones:

    POST /api/goals  {"title": 12345}    ->  500 Internal Server Error
    POST /api/chat   {"message": 12345}  ->  500 Internal Server Error

The cause is uniform and mechanical: `(body.get('title') or '').strip()`.
`(x or '')` guards against None and nothing else — an int, list or dict has no
`.strip()`, so the handler raises AttributeError and FastAPI turns it into a
500.

A 500 is the wrong answer twice over. It tells the caller the *server* is
broken when the *request* was, it is the status most likely to page an
operator, and it risks exposing a stack trace. The adjacent lines in several of
these same handlers already did it correctly with `str(body.get('model') or '')`,
so this was an oversight rather than a decision.

`as_text()` also strips null bytes: SQLite stores them happily, but they
truncate C-style strings in downstream tooling and render as control
characters in the UI, so they are never intentional.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ROUTERS = ROOT / 'backend' / 'routers'

WRONG_TYPES = [
    pytest.param(12345, id='int'),
    pytest.param(['a', 'b'], id='list'),
    pytest.param({'x': 1}, id='dict'),
    pytest.param(True, id='bool'),
    pytest.param(1.5, id='float'),
]


@pytest.mark.parametrize('value', WRONG_TYPES)
def test_a_wrong_typed_title_does_not_crash(client, value):
    r = client.post('/api/goals', json={
        'title': value, 'description': 'd', 'success_criteria': 's',
    })
    assert r.status_code != 500, (
        f'title={value!r} crashed the handler; a bad request must not be a 500'
    )


@pytest.mark.parametrize('value', WRONG_TYPES)
def test_a_wrong_typed_chat_message_does_not_crash(client, value):
    r = client.post('/api/chat', json={'message': value})
    assert r.status_code != 500


def test_a_list_message_is_still_treated_as_multimodal_content(client):
    """chat.py handles a list deliberately — those are OpenAI content parts.
    The coercion fix must not flatten that into a string."""
    src = (ROUTERS / 'chat.py').read_text(encoding='utf-8')
    assert 'isinstance(raw_message, list)' in src
    assert "p.get('type') == 'text'" in src


def test_null_bytes_are_stripped(client):
    r = client.post('/api/goals', json={
        'title': 'a\x00b', 'description': 'd', 'success_criteria': 's',
    })
    assert r.status_code == 200
    gid = r.json()['goal_id']
    stored = client.get(f'/api/goals/{gid}').json()
    goal = stored.get('goal', stored)
    assert '\x00' not in goal.get('title', ''), 'a null byte reached storage'
    client.delete(f'/api/goals/{gid}')


def test_an_oversized_field_is_bounded(client):
    """A 10MB title was accepted before this guard."""
    r = client.post('/api/goals', json={
        'title': 'A' * 5_000_000, 'description': 'd', 'success_criteria': 's',
    })
    assert r.status_code == 200
    gid = r.json()['goal_id']
    goal = client.get(f'/api/goals/{gid}').json()
    goal = goal.get('goal', goal)
    assert len(goal.get('title', '')) <= 1000, 'an unbounded title was stored'
    client.delete(f'/api/goals/{gid}')


# ══ The helper ════════════════════════════════════════════════════════════════
@pytest.mark.parametrize('value,expected', [
    (None, ''),
    ('ok', 'ok'),
    ('  pad  ', 'pad'),
    (12345, '12345'),
    (True, 'True'),
    ('a\x00b', 'ab'),
])
def test_as_text_coerces_without_raising(value, expected):
    from backend.services.request_body import as_text

    assert as_text(value) == expected


def test_as_text_bounds_length():
    from backend.services.request_body import MAX_FIELD_CHARS, as_text

    assert len(as_text('A' * (MAX_FIELD_CHARS * 2))) == MAX_FIELD_CHARS


def test_as_text_preserves_the_or_default_semantics():
    """Call sites read `as_text(...) or 'default'`; that only works if an
    absent value returns a falsy string rather than None."""
    from backend.services.request_body import as_text

    assert as_text(None) == ''
    assert (as_text(None) or 'fallback') == 'fallback'


# ══ Keep the idiom from coming back ═══════════════════════════════════════════
VULNERABLE = re.compile(
    r"\(\s*[a-z_]{1,8}\.get\(\s*'[\w_]+'\s*\)\s*or\s*[^)]+?\s*\)\s*\.l?strip\("
)


def test_no_router_calls_strip_on_an_unchecked_body_field():
    """The CI half. Without it the next handler written this way reintroduces a
    500, and it will only be found by someone sending the wrong type."""
    offenders = []
    for path in sorted(ROUTERS.glob('*.py')):
        text = path.read_text(encoding='utf-8')
        for m in VULNERABLE.finditer(text):
            line = text[: m.start()].count('\n') + 1
            offenders.append(f'{path.name}:{line}  {m.group(0)[:60]}')
    assert not offenders, (
        '.strip() on a raw body field crashes on a non-string:\n  '
        + '\n  '.join(offenders[:20])
        + '\n\nUse as_text(body.get(...)) from backend.services.request_body.'
    )
