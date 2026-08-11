"""Module 23 — the Connect workstation: `webhooks` and `integrations`.

Destination: `mcp` ("🔌 Connect"), hosting integrations, webhooks and hooks.
`mcp-gateway` was covered by doc 72 and `hooks` by doc 69; this pass closes the
two remaining tabs.

Webhooks are the platform's only *inbound* surface — a public URL that an
external service calls and that starts an LLM agent on the user's account. That
makes its authentication the highest-stakes code in this destination.

Six defects, all reproduced against a live server before the fix:

1. AN EMPTY SECRET CREATED AN UNAUTHENTICATED PUBLIC AGENT TRIGGER.
   `body.get('secret', <generated>)` only defaults when the key is ABSENT, so
   {"secret": ""} stored an empty string — and the trigger endpoint's auth is
   `if secret:`. Verified live: created with secret "", triggered with no
   credential at all -> 200, agent 'brain' started, tokens billed. Anyone
   holding the URL could run the user's agent repeatedly at their expense.

2. A webhook row with an empty secret (created before the fix) still bypassed
   authentication at trigger time.

3. FILTERS WERE STORED, EDITABLE, DISPLAYED — AND NEVER READ. Verified live: a
   webhook filtered to source 'github-push' ran its agent for a completely
   unrelated payload. A filter that silently does nothing is worse than no
   filter, because the user configured it precisely to stop paying for events
   they do not want.

4. GET /api/webhooks RETURNED EVERY SECRET IN PLAINTEXT. That secret is the only
   thing standing between the public trigger endpoint and anyone who can reach
   the list.

5. integrations /stripe/wire reported ok:true with zero files written when the
   model returned nothing usable — the UI said the payment integration was
   wired when not one byte had been.

6. /auth/wire had the same defect (second door #20) AND a worse one: its
   extractor fell back to `html_code = code`, so a model refusal was written to
   disk as auth.html — prose served as a login page.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _clean():
    from backend.services.memory_db import get_conn

    def purge():
        con = get_conn()
        try:
            con.execute("DELETE FROM webhook_events WHERE webhook_id IN (SELECT id FROM webhooks WHERE name LIKE 't159%')")
            con.execute("DELETE FROM webhooks WHERE name LIKE 't159%'")
            con.commit()
        finally:
            con.close()

    purge()
    yield
    purge()


def _create(client, **kw):
    body = {'name': 't159 hook'}
    body.update(kw)
    return client.post('/api/webhooks', json=body)


def _trigger(client, wid, payload=None, secret=None):
    headers = {'X-Webhook-Secret': secret} if secret else {}
    return client.post(f'/api/webhooks/{wid}/trigger', json=payload or {'x': 1}, headers=headers)


# ── 1. an empty secret must never yield an open endpoint ──────────────────────
def test_an_empty_secret_gets_one_generated(client):
    body = _create(client, secret='').json()
    assert len(body['secret']) >= 16, 'an empty secret was stored verbatim'
    assert 'note' in body, 'the substitution was made silently'


def test_a_webhook_created_with_an_empty_secret_still_requires_a_credential(client):
    wid = _create(client, secret='').json()['id']
    assert _trigger(client, wid).status_code == 401, (
        'a public endpoint that runs an LLM agent accepted an unauthenticated call'
    )


def test_an_omitted_secret_still_generates_one(client):
    """The pre-existing behaviour must not regress."""
    assert len(_create(client).json()['secret']) >= 16


def test_a_whitespace_only_secret_is_treated_as_empty(client):
    body = _create(client, secret='    ').json()
    assert len(body['secret']) >= 16


def test_a_too_short_secret_is_rejected(client):
    r = _create(client, secret='abc')
    assert r.status_code == 400
    assert '8 characters' in r.json()['error']


def test_a_real_secret_is_kept_as_given(client):
    body = _create(client, secret='my-real-secret-value').json()
    assert body['secret'] == 'my-real-secret-value'
    assert 'note' not in body


def test_an_update_cannot_reopen_the_hole(client):
    wid = _create(client, secret='my-real-secret-value').json()['id']
    assert client.patch(f'/api/webhooks/{wid}', json={'secret': ''}).status_code == 400
    assert client.patch(f'/api/webhooks/{wid}', json={'secret': 'x'}).status_code == 400
    assert _trigger(client, wid).status_code == 401


def test_an_update_without_a_secret_field_still_works(client):
    wid = _create(client, secret='my-real-secret-value').json()['id']
    assert client.patch(f'/api/webhooks/{wid}', json={'name': 't159 renamed'}).status_code == 200


# ── 2. a legacy empty-secret row must fail closed ─────────────────────────────
def test_a_stored_empty_secret_refuses_at_trigger_time(client):
    """Defence in depth for rows written before the create-path fix."""
    from backend.services.memory_db import get_conn

    wid = _create(client, secret='my-real-secret-value').json()['id']
    con = get_conn()
    try:
        con.execute('UPDATE webhooks SET secret=? WHERE id=?', ('', wid))
        con.commit()
    finally:
        con.close()
    r = _trigger(client, wid)
    assert r.status_code == 403
    assert r.json()['code'] == 'webhook_unconfigured'


def test_a_valid_secret_still_triggers(client):
    wid = _create(client, secret='my-real-secret-value').json()['id']
    r = _trigger(client, wid, secret='my-real-secret-value')
    assert r.status_code == 200 and r.json()['ok'] is True


def test_a_wrong_secret_is_still_a_401(client):
    wid = _create(client, secret='my-real-secret-value').json()['id']
    assert _trigger(client, wid, secret='wrong-secret-value').status_code == 401


# ── 3. filters must actually filter ───────────────────────────────────────────
def test_a_non_matching_event_does_not_run_the_agent(client):
    wid = _create(client, secret='my-real-secret-value', filters={'source': 'github-push'}).json()['id']
    body = _trigger(client, wid, {'totally': 'unrelated'}, secret='my-real-secret-value').json()
    assert body.get('filtered') is True, 'the configured filter was never applied'
    assert 'run_id' not in body
    assert 'github-push' in body['reason']


def test_a_matching_event_still_runs_the_agent(client):
    """Over-filtering would be its own bug."""
    wid = _create(client, secret='my-real-secret-value', filters={'source': 'github-push'}).json()['id']
    body = _trigger(
        client, wid, {'repository': {'name': 'r'}, 'pusher': {'name': 'p'}}, secret='my-real-secret-value'
    ).json()
    assert body.get('filtered') is not True
    assert body['run_id']


def test_an_unfiltered_webhook_runs_everything(client):
    wid = _create(client, secret='my-real-secret-value').json()['id']
    body = _trigger(client, wid, {'anything': 1}, secret='my-real-secret-value').json()
    assert body.get('filtered') is not True


def test_an_event_type_filter_is_applied(client):
    wid = _create(client, secret='my-real-secret-value', filters={'event_type': 'deploy'}).json()['id']
    assert _trigger(client, wid, {'type': 'other'}, secret='my-real-secret-value').json()['filtered'] is True
    body = _trigger(client, wid, {'type': 'deploy'}, secret='my-real-secret-value').json()
    assert body.get('filtered') is not True


def test_a_contains_filter_is_applied(client):
    wid = _create(client, secret='my-real-secret-value', filters={'contains': 'urgent'}).json()['id']
    assert _trigger(client, wid, {'msg': 'routine'}, secret='my-real-secret-value').json()['filtered'] is True
    assert _trigger(client, wid, {'msg': 'urgent fix'}, secret='my-real-secret-value').json().get('filtered') is not True


def test_an_unknown_filter_key_does_not_drop_everything(client):
    """A typo'd key must not silently block every event — that is the same
    failure as never filtering, in the opposite direction."""
    wid = _create(client, secret='my-real-secret-value', filters={'nonsense_key': 'x'}).json()['id']
    assert _trigger(client, wid, {'a': 1}, secret='my-real-secret-value').json().get('filtered') is not True


def test_a_corrupt_filters_column_does_not_break_the_trigger(client):
    from backend.services.memory_db import get_conn

    wid = _create(client, secret='my-real-secret-value').json()['id']
    con = get_conn()
    try:
        con.execute('UPDATE webhooks SET filters=? WHERE id=?', ('not json', wid))
        con.commit()
    finally:
        con.close()
    assert _trigger(client, wid, secret='my-real-secret-value').status_code == 200


def test_a_filtered_event_is_still_recorded(client):
    """The user needs to see that events arrived and why they were skipped."""
    from backend.services.memory_db import get_conn

    wid = _create(client, secret='my-real-secret-value', filters={'source': 'github-push'}).json()['id']
    _trigger(client, wid, {'x': 1}, secret='my-real-secret-value')
    con = get_conn()
    try:
        row = con.execute(
            "SELECT status FROM webhook_events WHERE webhook_id=? ORDER BY rowid DESC LIMIT 1", (wid,)
        ).fetchone()
    finally:
        con.close()
    assert row is not None and row['status'] == 'filtered'


# ── 4. the list must not hand out secrets ─────────────────────────────────────
def test_the_list_does_not_return_secrets(client):
    _create(client, secret='my-real-secret-value')
    rows = client.get('/api/webhooks').json()
    rows = rows if isinstance(rows, list) else rows.get('webhooks', [])
    assert rows
    for r in rows:
        assert 'secret' not in r, 'the trigger credential was handed to any caller of the list'


def test_the_list_still_says_whether_a_secret_is_set(client):
    _create(client, secret='my-real-secret-value')
    rows = client.get('/api/webhooks').json()
    rows = rows if isinstance(rows, list) else rows.get('webhooks', [])
    mine = [r for r in rows if r.get('name', '').startswith('t159')]
    assert mine and mine[0]['has_secret'] is True
    assert mine[0]['secret_hint'] == '…alue'


def test_the_secret_is_still_returned_once_at_creation(client):
    """The caller has to be able to configure the sender."""
    assert _create(client, secret='my-real-secret-value').json()['secret'] == 'my-real-secret-value'


# ── 5 & 6. the wire endpoints must not claim work they did not do ─────────────
def _wire(fn_name, payload, llm_text):
    import asyncio

    from backend.routers import integrations as ig

    class Req:
        async def json(self):
            return payload

    fn = getattr(ig, fn_name)
    with patch('backend.services.llm.complete', new=AsyncMock(return_value={'ok': True, 'text': llm_text, 'tokens': 9})):
        r = asyncio.get_event_loop().run_until_complete(fn(Req()))
    if hasattr(r, 'body'):
        return getattr(r, 'status_code', 200), json.loads(bytes(r.body).decode())
    return 200, r


def test_stripe_wire_reports_failure_when_no_code_was_produced():
    status, body = _wire(
        'stripe_wire',
        {'mode': 'payment', 'target_file': 't159_probe.html'},
        "I'm sorry, I can't generate payment code.",
    )
    assert status == 502, 'the UI was told the Stripe integration was wired'
    assert body['ok'] is False
    assert body['saved_files'] == []


def test_stripe_wire_still_succeeds_on_real_code():
    status, body = _wire(
        'stripe_wire',
        {'mode': 'payment', 'target_file': 't159_probe.html'},
        '### CHECKOUT_HTML\n<html>real checkout</html>\n',
    )
    assert status == 200 and body['ok'] is True
    assert body['saved_files']


def test_auth_wire_reports_failure_when_no_code_was_produced():
    status, body = _wire('auth_wire', {'provider': 'clerk', 'auth_file': 't159_auth.html'}, "I'm sorry, I can't help.")
    assert status == 502, 'the twin of stripe_wire kept the same defect'
    assert body['ok'] is False


def test_auth_wire_does_not_write_prose_to_disk_as_a_login_page():
    """Its extractor fell back to `html_code = code`, so a refusal was saved as
    auth.html and reported as a successful wire-up."""
    status, body = _wire('auth_wire', {'provider': 'clerk', 'auth_file': 't159_auth.html'}, 'I refuse to do that.')
    assert body.get('saved_files') in ([], None)


def test_auth_wire_still_succeeds_on_real_html():
    status, body = _wire(
        'auth_wire', {'provider': 'clerk', 'auth_file': 't159_auth.html'}, '<!DOCTYPE html><html>login</html>'
    )
    assert status == 200 and body['ok'] is True
    assert body['saved_files']
