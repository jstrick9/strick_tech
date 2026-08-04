"""Module 20 follow-up — per-agent tool permissions are now ENFORCED.

THE GAP
───────
`agent_permissions` has existed since Sprint A: populated on provisioning,
shown on agent cards, counted in the identity UI. **Nothing ever consulted it
to authorise anything.** The only two readers in the codebase
(`a2a.get_agent_card`, `mcp_gateway.get_agent_card`) both use it for display.

Verified live before the fix, with an agent holding neither `write_files` nor
`delete_files`:

    POST /api/mcp/call {"tool":"fs.write",  "agent_id":"probe_readonly"} -> 200
    POST /api/mcp/call {"tool":"fs.delete", "agent_id":"probe_readonly"} -> 200
    POST /api/mcp/call {"tool":"fs.write",  "agent_id":"i_do_not_exist"} -> 200

The last is the worst: a fictional agent id wrote a file, and the audit chain
recorded it as that agent's action. An identity field that is accepted, logged,
echoed back and audited but never used for a decision is worse than no field —
the trail reads as though authorisation happened.
"""

from __future__ import annotations

import uuid

import pytest

from backend.services import tool_policy as tp


@pytest.fixture()
def restricted_agent(client):
    """A provisioned agent WITHOUT write_files / delete_files / run_code."""
    agent_id = 'perm_probe_' + uuid.uuid4().hex[:8]
    r = client.post('/api/agent-identity/provision', json={
        'agent_id': agent_id, 'display_name': 'Perm Probe'})
    assert r.status_code == 200, r.text

    from backend.services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            "DELETE FROM agent_permissions WHERE agent_id=? AND action IN "
            "('write_files','delete_files','run_code','send_webhook')",
            (agent_id,),
        )
        con.commit()
    finally:
        con.close()
    return agent_id


def _call(client, tool, args, agent_id=None):
    body = {'tool': tool, 'args': args}
    if agent_id is not None:
        body['agent_id'] = agent_id
    return client.post('/api/mcp/call', json=body)


# ══ The three original bypasses ═══════════════════════════════════════════════
def test_unpermitted_write_is_denied(client, restricted_agent):
    r = _call(client, 'fs.write', {'path': 'x.txt', 'content': 'x'}, restricted_agent)
    assert r.status_code == 403, 'an agent without write_files wrote a file'
    assert r.json()['denied'] is True
    assert r.json()['required_permission'] == 'write_files'


def test_unpermitted_delete_is_denied(client, restricted_agent):
    r = _call(client, 'fs.delete', {'path': 'x.txt'}, restricted_agent)
    assert r.status_code == 403
    assert r.json()['required_permission'] == 'delete_files'


def test_fictional_agent_is_denied(client):
    """A completely unknown agent id used to write files successfully."""
    r = _call(client, 'fs.write', {'path': 'ghost.txt', 'content': 'x'}, 'i_do_not_exist_xyz')
    assert r.status_code == 403, 'a nonexistent agent id was authorised'
    assert 'unknown agent' in r.json()['error'].lower()


def test_denial_does_not_perform_the_action(client, restricted_agent):
    """A 403 that still writes the file would be worse than no check at all."""
    path = 'denied_' + uuid.uuid4().hex[:8] + '.txt'
    assert _call(client, 'fs.write', {'path': path, 'content': 'x'},
                 restricted_agent).status_code == 403
    r = _call(client, 'fs.exists', {'path': path}, restricted_agent)
    assert r.status_code == 200
    assert r.json()['result'].get('exists') is False, 'the denied write happened anyway'


# ══ Legitimate use must keep working ══════════════════════════════════════════
def test_permitted_read_is_allowed(client, restricted_agent):
    r = _call(client, 'fs.list', {'path': '.'}, restricted_agent)
    assert r.status_code == 200 and r.json()['ok'] is True


def test_system_caller_is_unrestricted(client):
    """Internal platform code paths pass no agent_id and must keep working."""
    r = _call(client, 'fs.write', {'path': 'sys_ok.txt', 'content': 'x'})
    assert r.status_code == 200, 'the platform locked itself out'


def test_explicit_system_agent_is_unrestricted(client):
    r = _call(client, 'fs.write', {'path': 'sys_ok2.txt', 'content': 'x'}, 'system')
    assert r.status_code == 200


def test_granting_the_permission_restores_access(client, restricted_agent):
    """Enforcement must be driven by the table, not hardcoded."""
    from backend.services.memory_db import get_conn

    assert _call(client, 'fs.write', {'path': 'g.txt', 'content': 'x'},
                 restricted_agent).status_code == 403

    con = get_conn()
    try:
        con.execute(
            "INSERT OR IGNORE INTO agent_permissions(agent_id, action, resource, "
            "granted_by, granted_at) VALUES (?,?,'*','test','')",
            (restricted_agent, 'write_files'),
        )
        con.commit()
    finally:
        con.close()

    r = _call(client, 'fs.write', {'path': 'g.txt', 'content': 'x'}, restricted_agent)
    assert r.status_code == 200, 'granting write_files did not restore access'


# ══ The wildcard must not re-open the hole ════════════════════════════════════
def test_use_tools_does_not_grant_writes(client, restricted_agent):
    """My first version left fs.write out of HIGH_RISK, and the standard
    authority level grants 'use_tools' but not 'write_files' — so the wildcard
    silently re-opened the exact bypass this module closes. Caught by re-running
    the original reproduction against the fix instead of assuming it worked.
    """
    from backend.services.memory_db import get_conn

    con = get_conn()
    try:
        actions = {r['action'] for r in con.execute(
            'SELECT action FROM agent_permissions WHERE agent_id=?', (restricted_agent,))}
    finally:
        con.close()
    assert 'use_tools' in actions, 'fixture assumption broken'
    assert 'write_files' not in actions

    assert _call(client, 'fs.write', {'path': 'w.txt', 'content': 'x'},
                 restricted_agent).status_code == 403


@pytest.mark.parametrize('tool', sorted(tp.HIGH_RISK))
def test_high_risk_tools_need_explicit_grants(tool):
    """'use_tools' is a convenience grant for READ-shaped tools only."""
    assert tool in tp.TOOL_ACTIONS, f'{tool} is high-risk but has no action mapping'


def test_every_mutating_tool_is_high_risk():
    """Anything that changes state on disk, in the repo, or on another system
    must need its own permission — not a blanket grant."""
    mutating_actions = {'write_files', 'delete_files', 'run_code', 'send_webhook'}
    for tool, action in tp.TOOL_ACTIONS.items():
        if action in mutating_actions:
            assert tool in tp.HIGH_RISK, f'{tool} mutates state but is not HIGH_RISK'


# ══ Policy semantics ══════════════════════════════════════════════════════════
def test_unknown_agent_denies_but_unmapped_tool_allows():
    """These look inconsistent and are not: an unknown AGENT is an
    authentication failure (no basis for a decision); an unmapped TOOL is an
    omission in the map, and failing closed there would break every caller the
    moment a tool is added.
    """
    assert tp.check_tool_permission('nope_not_real', 'fs.write')[0] is False
    assert tp.check_tool_permission('system', 'some.brand.new.tool')[0] is True


def test_tool_map_covers_every_registered_tool():
    """The guard that keeps 'unmapped tools are allowed' honest: a new tool
    without a mapping is caught here, at review time, not in production.
    """
    from backend.routers.mcp import TOOLS

    unmapped = sorted(set(TOOLS) - set(tp.TOOL_ACTIONS))
    assert not unmapped, (
        f'these tools have no permission mapping in tool_policy.TOOL_ACTIONS: {unmapped}'
    )


def test_policy_lookup_failure_denies(monkeypatch):
    """A policy lookup that errors must not silently authorise."""
    import backend.services.tool_policy as mod

    monkeypatch.setattr(mod, '_agent_actions', lambda a: None)
    ok, reason = mod.check_tool_permission('some_agent', 'fs.write')
    assert ok is False and reason


def test_expired_permissions_are_ignored(client, restricted_agent):
    """agent_permissions has an expires_at column that nothing honoured."""
    from backend.services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            "INSERT OR REPLACE INTO agent_permissions(agent_id, action, resource, "
            "granted_by, granted_at, expires_at) VALUES (?,?,'*','test','','2000-01-01 00:00:00')",
            (restricted_agent, 'write_files'),
        )
        con.commit()
    finally:
        con.close()

    r = _call(client, 'fs.write', {'path': 'exp.txt', 'content': 'x'}, restricted_agent)
    assert r.status_code == 403, 'an expired permission still authorised the call'


# ══ Both doors ════════════════════════════════════════════════════════════════
def test_gateway_path_is_also_enforced(client, restricted_agent):
    """The gateway dispatches through /api/mcp/call, so one guard covers both —
    asserted rather than assumed, since 'second door' gaps have appeared three
    times in this review."""
    r = client.post('/api/mcp-gateway/call', json={
        'server_id': 'srv_filesystem', 'tool': 'fs.write',
        'args': {'path': 'gw.txt', 'content': 'x'}, 'agent_id': restricted_agent})
    body = r.json()
    assert body.get('ok') is False, 'the gateway bypassed per-agent permissions'
    assert body.get('denied') is True


# ══ Observability ═════════════════════════════════════════════════════════════
def test_denial_is_recorded_in_the_audit_log(client, restricted_agent):
    from backend.services.memory_db import audit_list

    _call(client, 'fs.write', {'path': 'audited.txt', 'content': 'x'}, restricted_agent)
    entries = audit_list(limit=50)
    assert any(e['action'] == 'mcp_denied' and restricted_agent in e['detail']
               for e in entries), 'a denied tool call left no audit trace'


def test_permissions_endpoint_answers_what_can_this_agent_do(client, restricted_agent):
    r = client.get(f'/api/connect/permissions/{restricted_agent}')
    assert r.status_code == 200
    d = r.json()
    denied = {x['tool'] for x in d['denied']}
    allowed = {x['tool'] for x in d['allowed']}
    assert 'fs.write' in denied and 'fs.delete' in denied
    assert 'fs.list' in allowed
    assert all(x['reason'] for x in d['denied']), 'denials must explain themselves'


def test_allowed_tools_helper_matches_enforcement(restricted_agent):
    for tool in tp.allowed_tools(restricted_agent):
        assert tp.check_tool_permission(restricted_agent, tool)[0], (
            f'allowed_tools() listed {tool} but enforcement denies it'
        )


def test_system_sees_every_tool():
    assert set(tp.allowed_tools('system')) == set(tp.TOOL_ACTIONS)
