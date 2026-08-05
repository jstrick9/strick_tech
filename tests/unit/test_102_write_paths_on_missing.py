"""Writes to a resource that does not exist must fail, not invent one.

FOUND BY PROBING WRITE PATHS, which the earlier 404 sweep did not cover — it
only looked at GET/DELETE handlers using the `{'ok': False, 'error': ...}`
return idiom.

1. **PATCH created a phantom agent.** `update_agent` called `agent_upsert()`,
   which INSERTS when the id is absent:

       PATCH /api/agents/nope {"name": "x"}
       -> 200 {"ok": true, "agent": {"id":"nope","role":"","model":"", ...}}

   The half-built record then persisted and appeared in the agent picker with
   no model, where selecting it fails. A typo in an id, or a stale client
   editing a deleted agent, silently corrupted the agent list.

2. **DELETE reported success for a goal that was not there.**
   `{"ok": true, "deleted": "nope"}` for any id at all. A double-delete became
   indistinguishable from a real one, in the UI and in the audit trail.

3. **DELETE of a missing agent answered 200 {"ok": false}** — the
   HTTP-200-on-failure shape again, on a write path this time.
"""

from __future__ import annotations

import pytest

MISSING = 'zzz_no_such_record_zzz'


# ══ PATCH must not create ═════════════════════════════════════════════════════
def test_patching_a_missing_agent_returns_404(client):
    r = client.patch(f'/api/agents/{MISSING}', json={'name': 'ghost'})
    assert r.status_code == 404, (
        f'PATCH on a missing agent returned {r.status_code} — it upserted a '
        f'phantom record'
    )


def test_patching_a_missing_agent_creates_nothing(client):
    """The actual harm: a broken agent in the picker that nobody added."""
    client.patch(f'/api/agents/{MISSING}', json={'name': 'ghost'})
    body = client.get('/api/agents').json()
    agents = body if isinstance(body, list) else body.get('agents', [])
    assert not [a for a in agents if a.get('id') == MISSING], (
        'a phantom agent was persisted by a PATCH to a nonexistent id'
    )


def test_patching_a_real_agent_still_works(client):
    """The fix must not break the operation it guards."""
    body = client.get('/api/agents').json()
    agents = body if isinstance(body, list) else body.get('agents', [])
    assert agents, 'no agents seeded'
    r = client.patch(f'/api/agents/{agents[0]["id"]}', json={'status': 'idle'})
    assert r.status_code == 200
    assert r.json().get('ok') is True


def test_patch_with_no_valid_fields_is_a_400(client):
    """'no valid fields to update' is a client error, not a success."""
    body = client.get('/api/agents').json()
    agents = body if isinstance(body, list) else body.get('agents', [])
    r = client.patch(f'/api/agents/{agents[0]["id"]}', json={'bogus_field': 1})
    assert r.status_code == 400


# ══ DELETE must report reality ════════════════════════════════════════════════
@pytest.mark.parametrize('path', [
    f'/api/agents/{MISSING}',
    f'/api/goals/{MISSING}',
])
def test_deleting_something_absent_returns_404(client, path):
    r = client.delete(path)
    assert r.status_code == 404, (
        f'{path} answered {r.status_code} for a resource that does not exist; '
        f'a no-op delete looked like a successful one'
    )


def test_deleting_a_real_goal_still_works(client):
    created = client.post('/api/goals', json={
        'title': 'temp for delete test',
        'description': 'x',
        'success_criteria': 'y',
    })
    assert created.status_code == 200
    gid = created.json()['goal_id']

    first = client.delete(f'/api/goals/{gid}')
    assert first.status_code == 200
    assert first.json().get('ok') is True

    # And the second attempt is now honest about it.
    assert client.delete(f'/api/goals/{gid}').status_code == 404


def test_core_agents_are_still_protected(client):
    """The protection predates this change and must survive it."""
    r = client.delete('/api/agents/orchestrator')
    assert r.json().get('ok') is False
    assert 'core agent' in r.json().get('error', '').lower()


# ══ The same class, found by sweeping every single-param write route ══════════
# A broader probe of PATCH/PUT/DELETE against nonexistent ids turned up 29 more
# endpoints answering 200. Most are DELETEs where idempotence is a defensible
# reading; these three are not, because they claim an UPDATE happened that did
# not, and one of them fabricates a record.
def test_patching_a_missing_hook_returns_404(client):
    """The rowcount check was already correct here — only the status lied, so
    `if (r.ok)` still treated a no-op as an applied change."""
    r = client.patch(f'/api/hooks/{MISSING}', json={'name': 'x'})
    assert r.status_code == 404


def test_patching_a_missing_hook_with_no_fields_also_404s(client):
    """The no-fields branch skipped the existence check entirely and returned
    {"ok": true} for a hook that may never have existed."""
    r = client.patch(f'/api/hooks/{MISSING}', json={})
    assert r.status_code == 404


def test_patching_a_missing_trace_returns_404(client):
    """A client writing an outcome to a stale trace id believed it had been
    recorded; nothing was stored."""
    r = client.patch(f'/api/observability/traces/{MISSING}', json={'status': 'ok'})
    assert r.status_code == 404


def test_putting_a_missing_plugin_pack_returns_404(client):
    r = client.put(f'/api/pluginsdk/packs/{MISSING}', json={'name': 'ghost'})
    assert r.status_code == 404


def test_putting_a_missing_plugin_pack_creates_nothing(client):
    """PUT wrote a pack file with no name, no skills and no manifest, and the
    ghost then appeared in the pack list."""
    client.put(f'/api/pluginsdk/packs/{MISSING}', json={'name': 'ghost'})
    body = client.get('/api/pluginsdk/packs').json()
    packs = body.get('packs', body) if isinstance(body, dict) else body
    assert not [p for p in packs if p.get('id') == MISSING], (
        'PUT fabricated a plugin pack that nobody created'
    )


def test_configuring_an_unregistered_connector_returns_404(client):
    """The UPDATE matched no row but the handler still answered {"ok": true},
    so credentials saved against a mistyped or uninstalled connector were
    silently discarded — the user saw a success toast and the connector stayed
    unconfigured, with no way to tell those two states apart."""
    r = client.patch(
        f'/api/connectors/{MISSING}/configure',
        json={'credentials': {'token': 'secret'}},
    )
    assert r.status_code == 404


def test_configuring_a_real_connector_still_works(client):
    body = client.get('/api/connectors').json()
    connectors = body.get('connectors', body) if isinstance(body, dict) else body
    assert connectors, 'no connectors registered'
    cid = connectors[0].get('connector_id') or connectors[0].get('id')
    r = client.patch(f'/api/connectors/{cid}/configure', json={'credentials': {}})
    assert r.status_code == 200
    assert r.json().get('ok') is True
