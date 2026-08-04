"""Module 20 follow-ups 2-5.

3. SHELL ESCAPE (the serious one). `shell.run` validated only the FIRST TOKEN
   and then handed the whole string to create_subprocess_shell(), so every
   shell metacharacter was a bypass. Verified live:

       "ls | id"                            -> uid=1000(user) gid=1000(user)...
       "echo $(whoami)"                     -> user
       "echo x | cat /etc/passwd"           -> root:x:0:0:root:/root:/bin/bash
       "echo pwned > /tmp/shell_escape.txt" -> WROTE OUTSIDE THE SANDBOX

   This is the Module 12 terminal finding reproduced exactly. That module fixed
   it in terminal.py and built services/sandbox.py for OS-level isolation; this
   tool adopted neither.

4. WEBHOOK AUTH ANSWERED 200. Missing secret, wrong secret, forged signature
   and unknown webhook id all returned HTTP 200, so a sender (GitHub, Stripe,
   CI) saw success and never retried or alerted. The X-Webhook-Secret branch
   also used `!=`, which short-circuits and leaks the secret to timing.

   CORRECTION to my Module 20 write-up: I listed this as "webhooks have no
   signature verification". They do — HMAC-SHA256, correctly using
   compare_digest. The defects were the status codes and the *other* branch.

2. mcp_gateway tool_count was absent from the response entirely.

5. No rate limit on connector execution.
"""

from __future__ import annotations

import uuid

import pytest


def _run(client, command: str):
    return client.post('/api/mcp/call', json={'tool': 'shell.run', 'args': {'command': command}})


def _out(r) -> str:
    body = r.json()
    result = body.get('result') or {}
    return (result.get('stdout') or '') + (body.get('error') or '')


# ══ 3. Shell escapes ══════════════════════════════════════════════════════════
@pytest.mark.parametrize('command', [
    'ls | id',
    'ls; id',
    'ls && id',
    'echo $(whoami)',
    'echo `id`',
    'echo x > /tmp/should_not_exist.txt',
    'cat < /etc/passwd',
    'ls | cat /etc/passwd',
    'echo a & id',
])
def test_shell_metacharacters_are_refused(client, command):
    r = _run(client, command)
    assert r.json().get('ok') is False, f'shell escape executed: {command!r}'
    assert 'not permitted' in _out(r).lower()


def test_shell_escape_does_not_write_outside_the_sandbox(client, tmp_path):
    target = tmp_path / 'escape_probe.txt'
    r = _run(client, f'echo pwned > {target}')
    assert r.json().get('ok') is False
    assert not target.exists(), 'the redirect executed and wrote outside the sandbox'


def test_shell_cannot_read_etc_passwd_via_pipe(client):
    r = _run(client, 'echo x | cat /etc/passwd')
    assert r.json().get('ok') is False
    assert 'root:x:0:0' not in _out(r)


@pytest.mark.parametrize('command', [
    'git -c core.pager=id log -1',
    'git -c alias.x=!id x',
    'git --exec-path=/tmp status',
    'find . -exec id {} +',
    'npx --call id',
    'npm --script-shell /bin/sh run x',
])
def test_argument_escapes_through_allowlisted_binaries_are_refused(client, command):
    """`git -c core.pager=<cmd>` turns an allow-listed binary into arbitrary
    execution. The allow-list is on the binary NAME, so these all passed it."""
    r = _run(client, command)
    assert r.json().get('ok') is False, f'argument escape executed: {command!r}'


def test_absolute_paths_are_refused(client):
    r = _run(client, '/bin/sh -c id')
    assert r.json().get('ok') is False
    assert 'bare name' in _out(r).lower()


def test_disallowed_command_still_refused(client):
    r = _run(client, 'whoami')
    assert r.json().get('ok') is False
    assert 'not allowed' in _out(r).lower()


# `git status` is deliberately absent: the sandbox workspace is not a git
# repository, so it exits 128 legitimately. Asserting returncode==0 on it was my
# test being wrong about the environment, not the tool being broken.
@pytest.mark.parametrize('command', ['ls', 'echo hello world', 'pwd', 'cat index.html'])
def test_legitimate_commands_still_work(client, command):
    """A guard that breaks the tool is not a fix.

    This caught two of my own bugs: passing cwd while sandboxed broke the jail
    bootstrap's import, and passing a bare command name broke its os.execv --
    both returned ok:true with EMPTY output, the "success while doing nothing"
    shape this review keeps finding.
    """
    r = _run(client, command)
    body = r.json()
    assert body.get('ok') is True, f'{command!r} failed: {body}'
    result = body['result']
    assert result['returncode'] == 0, f'{command!r} stderr: {result.get("stderr", "")[:200]}'


def test_echo_actually_produces_output(client):
    """Explicitly asserts stdout, because 'ok:true, empty output' passed the
    other tests while every command was silently failing inside the jail."""
    r = _run(client, 'echo hello world')
    assert 'hello world' in r.json()['result']['stdout']


def test_response_reports_whether_it_was_sandboxed(client):
    """Isolation is reported, not implied — a host without namespace support
    degrades to the filter alone and the caller deserves to know."""
    assert 'sandboxed' in _run(client, 'ls').json()['result']


def test_background_variant_has_the_same_guard(client):
    """Same first-token bypass, and easier to overlook because it is async."""
    r = client.post('/api/mcp/call', json={
        'tool': 'shell.run_background', 'args': {'command': 'ls | id'}})
    assert r.json().get('ok') is False, 'the background path bypassed the guard'


def test_no_shell_is_used(client):
    """The structural guarantee behind all of the above."""
    import inspect

    from backend.routers import mcp

    src = inspect.getsource(mcp._shell_run) + inspect.getsource(mcp._shell_run_background)
    assert 'create_subprocess_shell' not in src, 'a shell is still being spawned'
    assert 'create_subprocess_exec' in src


# ══ 4. Webhook authentication ═════════════════════════════════════════════════
@pytest.fixture()
def webhook(client):
    r = client.post('/api/webhooks', json={
        'name': 'probe_' + uuid.uuid4().hex[:6], 'secret': 'topsecret123',
        'agent_id': 'builder', 'prompt_template': 'x'})
    assert r.status_code == 200, r.text
    return r.json()['id'], 'topsecret123'


def test_missing_credential_is_401(client, webhook):
    wid, _ = webhook
    r = client.post(f'/api/webhooks/{wid}/trigger', json={})
    assert r.status_code == 401, 'an unauthenticated webhook call returned success'


def test_wrong_secret_is_401(client, webhook):
    wid, _ = webhook
    r = client.post(f'/api/webhooks/{wid}/trigger', json={},
                    headers={'X-Webhook-Secret': 'wrong'})
    assert r.status_code == 401


def test_forged_signature_is_401(client, webhook):
    wid, _ = webhook
    r = client.post(f'/api/webhooks/{wid}/trigger', json={},
                    headers={'X-Hub-Signature-256': 'sha256=deadbeef'})
    assert r.status_code == 401


def test_unknown_webhook_is_404(client):
    r = client.post('/api/webhooks/definitely_not_real/trigger', json={})
    assert r.status_code == 404


def test_correct_secret_is_accepted(client, webhook):
    wid, secret = webhook
    r = client.post(f'/api/webhooks/{wid}/trigger', json={'x': 1},
                    headers={'X-Webhook-Secret': secret})
    assert r.status_code == 200, f'a valid credential was rejected: {r.text[:200]}'


def test_valid_hmac_signature_is_accepted(client, webhook):
    import hashlib
    import hmac
    import json as _json

    wid, secret = webhook
    body = _json.dumps({'event': 'push'}).encode()
    sig = 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    r = client.post(f'/api/webhooks/{wid}/trigger', content=body,
                    headers={'X-Hub-Signature-256': sig, 'Content-Type': 'application/json'})
    assert r.status_code == 200, f'a valid HMAC signature was rejected: {r.text[:200]}'


def test_secret_comparison_is_timing_safe():
    """`!=` short-circuits on the first differing byte, leaking the secret one
    character at a time. The HMAC branch already used compare_digest; the
    plain-secret branch did not."""
    import inspect

    from backend.routers import webhooks

    src = inspect.getsource(webhooks.trigger_webhook)
    assert 'x_webhook_secret != secret' not in src
    assert src.count('compare_digest') >= 2


# ══ 2. Gateway tool_count ═════════════════════════════════════════════════════
def test_gateway_servers_report_a_tool_count(client):
    d = client.get('/api/mcp-gateway/servers').json()
    assert d['servers'], 'no gateway servers seeded'
    for s in d['servers']:
        assert 'tool_count' in s, f'{s["server_id"]} has no tool_count field'
        assert isinstance(s['tool_count'], int)


def test_tool_count_matches_the_schema(client):
    for s in client.get('/api/mcp-gateway/servers').json()['servers']:
        schema = s.get('tools_schema')
        if isinstance(schema, list):
            assert s['tool_count'] == len(schema), f'{s["server_id"]} count mismatch'


def test_at_least_one_server_reports_tools(client):
    """A count that is structurally present but always zero is no better than
    the null it replaced."""
    counts = [s['tool_count'] for s in client.get('/api/mcp-gateway/servers').json()['servers']]
    assert sum(counts) > 0, f'every server reports zero tools: {counts}'


# ══ 5. Connector rate limiting ════════════════════════════════════════════════
def test_connector_calls_are_rate_limited(client):
    from backend.routers.connectors import (
        CONNECTOR_RATE_LIMIT,
        _reset_connector_rate,
    )

    _reset_connector_rate()
    agent = 'rl_' + uuid.uuid4().hex[:6]
    limited = 0
    for _ in range(CONNECTOR_RATE_LIMIT + 5):
        r = client.post('/api/connectors/conn_webhook/execute', json={
            'action': 'post', 'payload': {'url': 'https://example.com/x', 'data': {}},
            'agent_id': agent})
        if r.json().get('rate_limited'):
            limited += 1
    assert limited >= 5, f'no rate limiting applied ({limited} limited)'
    _reset_connector_rate()


def test_rate_limit_is_per_agent(client):
    """One runaway agent must not lock out every other agent."""
    from backend.routers.connectors import (
        CONNECTOR_RATE_LIMIT,
        _reset_connector_rate,
    )

    _reset_connector_rate()
    noisy = 'noisy_' + uuid.uuid4().hex[:6]
    for _ in range(CONNECTOR_RATE_LIMIT + 2):
        client.post('/api/connectors/conn_webhook/execute', json={
            'action': 'post', 'payload': {'url': 'https://example.com/x', 'data': {}},
            'agent_id': noisy})

    quiet = 'quiet_' + uuid.uuid4().hex[:6]
    r = client.post('/api/connectors/conn_webhook/execute', json={
        'action': 'post', 'payload': {'url': 'https://example.com/x', 'data': {}},
        'agent_id': quiet})
    assert not r.json().get('rate_limited'), 'one agent exhausted the limit for all of them'
    _reset_connector_rate()


def test_rate_limit_refusal_does_not_call_the_provider(client, monkeypatch):
    """The limit must be enforced BEFORE credentials are loaded or a request
    leaves the process — otherwise it protects nothing."""
    from backend.routers import connectors as conn_mod

    conn_mod._reset_connector_rate()
    agent = 'pre_' + uuid.uuid4().hex[:6]
    for _ in range(conn_mod.CONNECTOR_RATE_LIMIT):
        client.post('/api/connectors/conn_webhook/execute', json={
            'action': 'post', 'payload': {'url': 'https://example.com/x', 'data': {}},
            'agent_id': agent})

    called = []
    monkeypatch.setattr(conn_mod, '_exec_webhook',
                        lambda *a, **k: called.append(1) or {'ok': True})
    r = client.post('/api/connectors/conn_webhook/execute', json={
        'action': 'post', 'payload': {'url': 'https://example.com/x', 'data': {}},
        'agent_id': agent})
    assert r.json().get('rate_limited') is True
    assert not called, 'the provider was called despite the rate limit'
    conn_mod._reset_connector_rate()


def test_rate_limit_can_be_disabled(client, monkeypatch):
    """Self-hosted operators must be able to opt out."""
    from backend.routers import connectors as conn_mod

    monkeypatch.setattr(conn_mod, 'CONNECTOR_RATE_LIMIT', 0)
    conn_mod._reset_connector_rate()
    ok, msg = conn_mod._check_connector_rate('conn_webhook', 'anyone')
    assert ok and msg == ''
