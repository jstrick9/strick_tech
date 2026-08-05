"""Malformed JSON must be rejected, not silently turned into an empty object.

THE BUG
───────
179 handlers across 44 routers shared this idiom:

    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}

The intent was sound — several POSTs here legitimately carry no body at all
(`/api/control/runs/kill-all`, `/api/agent-identity/provision-all`), so an
empty request must not fail.

But the same `except` swallowed genuinely broken input. Verified live:

    POST /api/specs     body: not json  ->  200  {"title": "Untitled Feature"}
    POST /api/webhooks  body: not json  ->  200  {"name": "Webhook", ...}

A client with a serialisation bug got a cheerful 200 and a junk record in the
database. Nobody notices until the spec list fills with "Untitled Feature",
and the client never learns it is broken.

Returning 400 is also what makes it visible in the UI: the frontend's failure
reporter keys off status, so a 200 produces silence.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ROUTERS = ROOT / 'backend' / 'routers'

CREATE_ROUTES = [
    '/api/specs',
    '/api/webhooks',
    '/api/goals',
    '/api/prompts',
    '/api/tasks',
]


@pytest.mark.parametrize('path', CREATE_ROUTES)
def test_malformed_json_is_rejected(client, path):
    r = client.post(path, content=b'not json', headers={'Content-Type': 'application/json'})
    assert r.status_code == 400, (
        f'{path} accepted malformed JSON with {r.status_code} — it will have '
        f'written a record from an empty object'
    )


@pytest.mark.parametrize('path', CREATE_ROUTES)
def test_the_rejection_explains_itself(client, path):
    body = client.post(
        path, content=b'not json', headers={'Content-Type': 'application/json'}
    ).json()
    assert body.get('ok') is False
    assert 'error' in body


def test_a_json_array_is_not_accepted_as_fields(client):
    """`[1,2,3]` parses fine but is not a set of fields. Treating it as one
    silently produced a record with every field defaulted."""
    r = client.post(
        '/api/specs', content=b'[1,2,3]', headers={'Content-Type': 'application/json'}
    )
    assert r.status_code == 400


@pytest.mark.parametrize('path', ['/api/specs', '/api/control/runs/kill-all'])
def test_an_empty_body_still_works(client, path):
    """Load-bearing: several POSTs legitimately carry no body, and breaking
    them would be a worse regression than the bug being fixed."""
    r = client.post(path)
    assert r.status_code < 400, (
        f'{path} rejected an empty body — the fallback to {{}} must survive'
    )


def test_malformed_json_does_not_create_a_record(client):
    """The actual harm: a junk row that a human later has to find and delete."""
    before = client.get('/api/specs').json()
    before_count = len(before.get('specs', before) if isinstance(before, dict) else before)

    client.post('/api/specs', content=b'not json',
                headers={'Content-Type': 'application/json'})

    after = client.get('/api/specs').json()
    after_count = len(after.get('specs', after) if isinstance(after, dict) else after)
    assert after_count == before_count, 'malformed input still created a spec'


# ══ The idiom must not come back ══════════════════════════════════════════════
OLD_IDIOM = re.compile(
    r'try:\s*\n\s*body = await (?:req|request)\.json\(\)\s*\n'
    r'\s*except \(json\.JSONDecodeError, TypeError, ValueError\):\s*\n'
    r'\s*body = \{\}'
)


def test_no_router_silently_substitutes_an_empty_body():
    offenders = []
    for path in sorted(ROUTERS.glob('*.py')):
        text = path.read_text(encoding='utf-8')
        for m in OLD_IDIOM.finditer(text):
            offenders.append(f'{path.name}:{text[: m.start()].count(chr(10)) + 1}')
    assert not offenders, (
        'handlers swallowing malformed JSON into {}:\n  '
        + '\n  '.join(offenders[:20])
        + '\n\nUse json_body_or_error(req), which keeps the empty-body '
          'behaviour but rejects broken input with a 400.'
    )


def test_the_helper_distinguishes_empty_from_malformed():
    src = (ROOT / 'backend' / 'services' / 'request_body.py').read_text(encoding='utf-8')
    assert 'if not raw or not raw.strip():' in src, 'empty body is not special-cased'
    assert 'MalformedBodyError' in src
    assert 'isinstance(parsed, dict)' in src, 'a JSON array would pass through'
