"""Module 20 — CONNECT (MCP, Gateway, Connectors, Integrations, Webhooks, Hooks).

Bugs found and fixed, each reproduced against a live server first.

1. SSRF in the `http.get` / `http.post` MCP TOOLS — the worst of the three,
   because these are AGENT-CALLABLE. Verified:

       {"tool":"http.get","args":{"url":"http://localhost:8787/api/connectors"}}
       -> {"ok": true, ..., "body": "{\\"connectors\\":[..."}

   The full internal API response returned to the caller. Also reached
   169.254.169.254 (HTTP 401 = a response, therefore a successful connection).
   follow_redirects was True, so a host check alone would have been bypassed
   by a 302.

2. SSRF in the outbound-webhook CONNECTOR. Verified: posting to
   169.254.169.254 returned {"status_code": 501} — a response, not a refusal.

   Both are the SAME primitive Module 19 fixed in the plugin installer. It
   recurred because that fix lived inside a router and could not be reused;
   the guard now lives in services/safe_fetch.py.

3. `fs.write` reported a path the file was not written to.

4. The CONNECT catalog was 85% test residue (45 of 53 connectors).

5. 200-on-failure for unknown MCP tools.
"""

from __future__ import annotations

import pytest

from backend.services import safe_fetch


# ══ 1 & 2. SSRF ═══════════════════════════════════════════════════════════════
@pytest.mark.parametrize('url', [
    'http://localhost:8787/api/connectors',
    'http://127.0.0.1:22',
    'http://169.254.169.254/latest/meta-data/',
    'http://10.0.0.1/x',
    'http://192.168.1.1/x',
    'file:///etc/passwd',
    'ftp://example.com/x',
])
def test_url_guard_refuses_internal_and_non_http(url):
    ok, reason = safe_fetch.url_is_safe(url)
    assert not ok, f'guard accepted {url}'
    assert reason


def test_url_guard_allows_public():
    ok, reason = safe_fetch.url_is_safe('https://api.github.com/zen')
    assert ok, reason


def test_allow_private_is_a_server_side_opt_in():
    """Local integrations (Ollama, a local MCP server) are legitimate — but the
    flag must be set by calling code, never by a request body."""
    assert safe_fetch.url_is_safe('http://localhost:11434/api', allow_private=True)[0]
    assert not safe_fetch.url_is_safe('http://localhost:11434/api')[0]


@pytest.mark.parametrize('tool', ['http.get', 'http.post'])
@pytest.mark.parametrize('url', [
    'http://localhost:8787/api/connectors',
    'http://169.254.169.254/latest/meta-data/',
])
def test_agent_callable_http_tools_refuse_internal_urls(client, tool, url):
    """The highest-severity finding: an agent-invokable read of internal URLs."""
    r = client.post('/api/mcp/call', json={'tool': tool, 'args': {'url': url}})
    body = r.json()
    assert body.get('ok') is False, f'{tool} reached {url}'
    assert 'internal address' in str(body.get('error', '')).lower()


def test_http_tool_does_not_leak_internal_response_body(client):
    r = client.post('/api/mcp/call', json={
        'tool': 'http.get', 'args': {'url': 'http://localhost:8787/api/connectors'}})
    assert 'connector_id' not in r.text, 'internal API content leaked through the tool'


def test_webhook_connector_refuses_internal_urls(client):
    # Uses the metadata endpoint rather than 127.0.0.1: a pre-existing
    # test-only stub short-circuits loopback URLs under pytest, so a loopback
    # target would not reach the guard being tested here.
    r = client.post('/api/connectors/conn_webhook/execute', json={
        'action': 'post',
        'payload': {'url': 'http://169.254.169.254/latest/meta-data/', 'data': {}},
    })
    body = r.json()
    assert body.get('ok') is False
    assert body.get('blocked') is True, f'webhook connector reached metadata: {body}'


def test_safe_request_refuses_redirects():
    """A public URL that 302s to 169.254.169.254 walks past a check performed
    only on the original address."""
    import inspect

    src = inspect.getsource(safe_fetch.safe_request)
    assert 'follow_redirects=False' in src
    assert 'is_redirect' in src


def test_plugins_guard_delegates_to_the_shared_one():
    """Module 19's local copy is why this recurred in two more places."""
    from backend.routers.plugins import _url_is_safe

    assert not _url_is_safe('http://169.254.169.254/x')[0]
    assert _url_is_safe('https://raw.githubusercontent.com/a/b/main/p.json')[0]


def test_no_router_defines_its_own_blocked_host_list():
    """Repo-wide guard: a new outbound call must reuse services/safe_fetch.py.

    Three copies of this control in three modules is how the platform ended up
    with two unguarded SSRF sites after fixing the first one.
    """
    from pathlib import Path

    routers = Path(__file__).resolve().parents[2] / 'backend' / 'routers'
    offenders = []
    for f in routers.glob('*.py'):
        src = f.read_text()
        if '169.254' in src and 'safe_fetch' not in src:
            offenders.append(f.name)
    assert not offenders, f'these routers hand-roll an SSRF guard: {offenders}'


# ══ 3. fs.write honesty ═══════════════════════════════════════════════════════
def test_fs_write_reports_where_the_file_actually_went(client):
    """It echoed the REQUESTED path. An agent told it wrote to /tmp/x will read
    back /tmp/x, get nothing, and have no way to discover why."""
    r = client.post('/api/mcp/call', json={
        'tool': 'fs.write', 'args': {'path': '/tmp/probe_honesty.txt', 'content': 'hi'}})
    assert r.status_code == 200
    result = r.json()['result']
    assert result['path'] != '/tmp/probe_honesty.txt', 'still reporting the unwritten path'
    assert result.get('requested_path') == '/tmp/probe_honesty.txt'
    assert 'note' in result


def test_fs_write_then_read_roundtrip_uses_the_reported_path(client):
    """The path in the response must be the one that reads back."""
    w = client.post('/api/mcp/call', json={
        'tool': 'fs.write', 'args': {'path': 'roundtrip.txt', 'content': 'payload-xyz'}})
    written = w.json()['result']['path']
    r = client.post('/api/mcp/call', json={'tool': 'fs.read', 'args': {'path': written}})
    assert r.json()['ok'] is True
    assert 'payload-xyz' in str(r.json()['result'])


def test_fs_traversal_still_denied(client):
    r = client.post('/api/mcp/call', json={
        'tool': 'fs.read', 'args': {'path': '../../../etc/passwd'}})
    assert r.json()['ok'] is False


# ══ 4. Unified catalog ════════════════════════════════════════════════════════
def test_catalog_merges_all_three_registries(client):
    d = client.get('/api/connect/catalog').json()
    kinds = {i['kind'] for i in d['items']}
    assert {'tool', 'connector', 'server'} <= kinds, f'missing sources: {kinds}'


def test_catalog_excludes_test_residue(client):
    """45 of 53 connector rows were UAT/system-test artefacts."""
    for i in client.get('/api/connect/catalog').json()['items']:
        blob = (i['name'] + i['id'] + i['description']).lower()
        for marker in ('uat_', 'sdk test', 'system test', 'integration test'):
            assert marker not in blob, f'test residue in the catalog: {i["id"]} ({i["name"]})'


def test_only_the_real_connectors_are_listed(client):
    ids = {i['id'] for i in client.get('/api/connect/catalog').json()['items']
           if i['kind'] == 'connector'}
    assert 'conn_slack' in ids and 'conn_github' in ids
    assert len(ids) <= 12, f'catalog still polluted: {len(ids)} connectors'


def test_catalog_entries_share_one_shape(client):
    """Three registries disagreed on id, icon, status and action field names;
    the UI had to branch on which one a row came from."""
    required = {'id', 'kind', 'name', 'description', 'icon', 'category',
                'status', 'ready', 'needs_setup', 'actions'}
    for i in client.get('/api/connect/catalog').json()['items']:
        assert required.issubset(i.keys()), f'{i.get("id")} missing {required - i.keys()}'


def test_ready_items_sort_before_setup_items(client):
    """"What works now" belongs above "what needs a token"."""
    items = client.get('/api/connect/catalog').json()['items']
    readiness = [i['ready'] for i in items]
    assert readiness == sorted(readiness, reverse=True), 'setup-needed items sorted above ready ones'


def test_stats_match_the_catalog(client):
    s = client.get('/api/connect/stats').json()
    items = client.get('/api/connect/catalog').json()['items']
    assert s['total'] == len(items)
    assert s['ready'] == sum(1 for i in items if i['ready'])
    assert s['needs_setup'] == sum(1 for i in items if i['needs_setup'])


def test_catalog_search_and_filters(client):
    assert all(i['kind'] == 'tool'
               for i in client.get('/api/connect/catalog?kind=tool').json()['items'])
    assert all(i['ready']
               for i in client.get('/api/connect/catalog?ready=true').json()['items'])


# ══ Setup guidance ════════════════════════════════════════════════════════════
def test_setup_guidance_exists_before_you_fail(client):
    """This text previously appeared only INSIDE the error of a failed call —
    you had to get it wrong to find out how to get it right."""
    g = client.get('/api/connect/setup/conn_slack').json()
    assert g['ok'] is True
    assert 'bot_token' in g['needs']
    assert g['where'] and g['docs']
    assert g['configure_endpoint'] == '/api/connectors/conn_slack/configure'


@pytest.mark.parametrize('cid', ['conn_slack', 'conn_github', 'conn_notion',
                                 'conn_jira', 'conn_gdrive', 'conn_salesforce'])
def test_every_credentialed_connector_has_setup_guidance(client, cid):
    """A connector telling a user to supply credentials without saying which
    ones, or where to get them, is not usable."""
    g = client.get(f'/api/connect/setup/{cid}').json()
    assert g['needs'], f'{cid} has no documented credential fields'
    assert g['where'], f'{cid} does not say where to obtain them'


def test_item_detail_explains_how_to_use_it(client):
    d = client.get('/api/connect/item/conn_notion').json()
    assert d['how_to_use']
    assert d['setup']['needs'] == ['api_key']


def test_tool_detail_says_it_is_ready(client):
    d = client.get('/api/connect/item/fs.read').json()
    assert d['ready'] is True and d['needs_setup'] is False
    assert 'call' in d['how_to_use'].lower()


# ══ Configured vs working ═════════════════════════════════════════════════════
def test_testing_an_unconfigured_connector_reports_failure(client):
    """connectors.test_connector() returns ok:true meaning "I answered you",
    including when the answer is "not configured". Reporting that as a passing
    test is the exact conflation this endpoint exists to remove — caught by
    testing my own feature against an unconfigured connector.
    """
    r = client.post('/api/connect/test/conn_notion')
    body = r.json()
    assert body['ok'] is False, 'an unconfigured connector reported a passing test'
    assert body['configured'] is False


def test_testing_a_builtin_tool_succeeds(client):
    assert client.post('/api/connect/test/fs.read').json()['ok'] is True


# ══ 5. Status codes ═══════════════════════════════════════════════════════════
def test_unknown_mcp_tool_is_404(client):
    r = client.post('/api/mcp/call', json={'tool': 'fs.nope', 'args': {}})
    assert r.status_code == 404, 'unknown tool reported 200'
    assert r.json()['available']


def test_known_mcp_tool_still_200(client):
    r = client.post('/api/mcp/call', json={'tool': 'fs.list', 'args': {'path': '.'}})
    assert r.status_code == 200 and r.json()['ok'] is True


@pytest.mark.parametrize('path', [
    '/api/connect/item/nope', '/api/connect/setup/nope'])
def test_unknown_connect_item_is_404(client, path):
    assert client.get(path).status_code == 404


def test_unknown_connect_test_is_404(client):
    assert client.post('/api/connect/test/nope').status_code == 404


# ══ Shell guard unchanged ═════════════════════════════════════════════════════
def test_shell_run_allowlist_still_enforced(client):
    r = client.post('/api/mcp/call', json={
        'tool': 'shell.run', 'args': {'command': 'whoami'}})
    assert r.json()['ok'] is False
    assert 'not allowed' in r.json()['error'].lower()
