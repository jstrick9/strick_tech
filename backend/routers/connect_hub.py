"""Agentic OS — Connect Hub: one surface over every integration source.

WHY THIS EXISTS
───────────────
Module 20 found the CONNECT group split across five panes and three unrelated
registries that do not know about each other:

    /api/mcp/tools            23 built-in agent tools
    /api/mcp-gateway/servers   6 tool servers (tool_count: null on all of them)
    /api/connectors           53 rows — 8 real, 45 test residue
    /api/webhooks              inbound triggers
    /api/hooks                 event-driven automations

A user asking the only question that matters — *"what can my agent actually
do right now, and what do I need to set up?"* — had to visit five panes and
reconcile three vocabularies. The connectors list was 85% test residue, so the
eight real integrations were invisible in it.

This is the same federation the Plugin Hub did for plugins in Module 19, and it
is deliberately the same shape: one catalog, one status vocabulary, one detail
view, setup guidance attached to the thing that needs it. ChatGPT, Claude and
Manus all converge on this because the alternative — a user holding a mental
model of your internal service boundaries — is not a user experience.

Normalisation is the substance. The three sources disagree on nearly every
field name for the same concept:

    id          server_id / connector_id / name
    icon        icon / emoji / (none)
    status      active|unconfigured / (implicit) / (none)
    actions     capabilities / tools / args

The UI previously had to branch on which registry a row came from. Now it does
not, and "ready to use" means one thing across all of them.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix='/api/connect', tags=['connect-hub'])
log = logging.getLogger('agentic.connect')

KIND_TOOL = 'tool'
KIND_CONNECTOR = 'connector'
KIND_SERVER = 'server'

# Test residue that must never appear in the user-facing catalog. The same
# reasoning as the Plugin Hub: a shop window showing "UAT Custom CRM
# uat_15b4fa33" teaches a first-run user that nothing here is curated.
# Matched against name AND description. My first version only listed
# underscore-suffixed markers ('uat_', 'sys_') and missed 15 of 23 connectors,
# because the generated names read "Sys SDK Test sys_d52ded616d" and
# "Integration SDK Test conn_1a394625" -- the human-readable half has spaces,
# and the id half is a random hash carrying no marker at all. Checking the
# description too is what catches them reliably: they all say "System test
# custom connector" / "...for UAT testing".
_RESIDUE_MARKERS = (
    'uat_', 'test_', 'sys_', 'regress', 'e2e_',
    'uat testing', 'sdk test', 'test plugin', 'test connector',
    'system test', 'integration test', 'sys sdk', 'uat custom',
)


def _is_residue(name: str, ident: str = '', description: str = '') -> bool:
    blob = f'{name} {ident} {description}'.lower()
    return any(m in blob for m in _RESIDUE_MARKERS)


# ── Setup guidance ─────────────────────────────────────────────────────────────
# What a connector needs, in words, attached to the connector itself. Previously
# this only appeared inside an ERROR MESSAGE after a failed call -- you had to
# get it wrong to find out how to get it right.
SETUP_HINTS: dict[str, dict] = {
    'conn_slack': {
        'needs': ['bot_token'],
        'where': 'api.slack.com/apps → your app → OAuth & Permissions → Bot User OAuth Token',
        'scopes': 'chat:write, channels:read, users:read',
        'docs': 'https://api.slack.com/authentication/token-types',
    },
    'conn_github': {
        'needs': ['token'],
        'where': 'github.com/settings/tokens → Generate new token (classic)',
        'scopes': 'repo, read:user',
        'docs': 'https://docs.github.com/en/authentication',
    },
    'conn_notion': {
        'needs': ['api_key'],
        'where': 'notion.so/my-integrations → New integration → Internal Integration Secret',
        'scopes': 'Share the target pages with your integration',
        'docs': 'https://developers.notion.com/docs/create-a-notion-integration',
    },
    'conn_jira': {
        'needs': ['email', 'api_token', 'domain'],
        'where': 'id.atlassian.com/manage-profile/security/api-tokens',
        'scopes': 'Your Atlassian account permissions apply',
        'docs': 'https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/',
    },
    'conn_gdrive': {
        'needs': ['client_id', 'client_secret'],
        'where': 'console.cloud.google.com → APIs & Services → Credentials → OAuth client ID',
        'scopes': 'drive.file, spreadsheets',
        'docs': 'https://developers.google.com/workspace/guides/create-credentials',
    },
    'conn_salesforce': {
        'needs': ['client_id', 'client_secret', 'instance_url'],
        'where': 'Setup → App Manager → New Connected App',
        'scopes': 'api, refresh_token',
        'docs': 'https://help.salesforce.com/s/articleView?id=sf.connected_app_create.htm',
    },
    'conn_email': {
        'needs': ['smtp_host', 'smtp_user', 'smtp_password'],
        'where': 'Your mail provider\'s SMTP settings (Gmail requires an App Password)',
        'scopes': '',
        'docs': 'https://support.google.com/accounts/answer/185833',
    },
    'conn_webhook': {
        'needs': [],
        'where': 'No setup required — supply a public URL per call.',
        'scopes': '',
        'docs': '',
    },
}


# ── Normalisation ──────────────────────────────────────────────────────────────
def _norm_tool(t: dict) -> dict:
    name = t.get('name', '')
    group = name.split('.')[0] if '.' in name else 'general'
    return {
        'id': name,
        'kind': KIND_TOOL,
        'name': name,
        'description': t.get('description') or t.get('desc') or '',
        'icon': {
            'fs': '📁', 'shell': '⚡', 'git': '🌿', 'http': '🌐', 'search': '🔎',
            'memory': '🧠', 'browser': '🖥️', 'db': '🗄️',
        }.get(group, '🔧'),
        'category': group,
        'status': 'ready',
        'ready': True,
        'needs_setup': False,
        'actions': [name],
    }


def _norm_connector(c: dict) -> dict:
    status = c.get('status') or 'unconfigured'
    ready = status == 'active'
    return {
        'id': c.get('connector_id', ''),
        'kind': KIND_CONNECTOR,
        'name': c.get('name', ''),
        'description': c.get('description', ''),
        'icon': c.get('icon') or '🔗',
        'category': c.get('category') or 'integration',
        'status': status,
        'ready': ready,
        'needs_setup': not ready,
        'auth_type': c.get('auth_type', ''),
        'actions': c.get('capabilities') or [],
    }


def _norm_server(srv: dict) -> dict:
    return {
        'id': srv.get('server_id', ''),
        'kind': KIND_SERVER,
        'name': srv.get('name', ''),
        'description': srv.get('description', ''),
        'icon': '🚪',
        'category': 'mcp-server',
        'status': srv.get('status') or 'unknown',
        'ready': (srv.get('status') or '') == 'active',
        'needs_setup': (srv.get('status') or '') != 'active',
        'actions': [t.get('name') for t in (srv.get('tools') or []) if isinstance(t, dict)],
    }


def _tools() -> list[dict]:
    try:
        from .mcp import TOOLS

        return [
            _norm_tool({'name': name, 'description': spec.get('desc', '')})
            for name, spec in TOOLS.items()
        ]
    except Exception as e:
        log.warning('connect: tools unavailable: %s', e)
        return []


def _connectors() -> list[dict]:
    try:
        from .connectors import _get_conn

        con = _get_conn()
        try:
            rows = con.execute(
                'SELECT connector_id, name, description, category, icon, status, auth_type, '
                'capabilities FROM connector_registry'
            ).fetchall()
        finally:
            con.close()
    except Exception as e:
        log.warning('connect: connectors unavailable: %s', e)
        return []

    import json as _json

    out = []
    for r in rows:
        d = dict(r)
        if _is_residue(d.get('name', ''), d.get('connector_id', ''), d.get('description', '')):
            continue
        try:
            d['capabilities'] = _json.loads(d.get('capabilities') or '[]')
        except (TypeError, ValueError):
            d['capabilities'] = []
        out.append(_norm_connector(d))
    return out


def _servers() -> list[dict]:
    try:
        from .mcp_gateway import _get_conn

        con = _get_conn()
        try:
            rows = con.execute(
                'SELECT server_id, name, description, status, tools_schema FROM mcp_servers'
            ).fetchall()
        finally:
            con.close()
    except Exception as e:
        log.warning('connect: gateway unavailable: %s', e)
        return []

    import json as _json

    out = []
    for r in rows:
        d = dict(r)
        if _is_residue(d.get('name', ''), d.get('server_id', ''), d.get('description', '')):
            continue
        try:
            d['tools'] = _json.loads(d.get('tools_schema') or '[]')
        except (TypeError, ValueError):
            d['tools'] = []
        out.append(_norm_server(d))
    return out


def _catalog() -> list[dict]:
    items = _tools() + _connectors() + _servers()
    # Ready things first, then things needing setup, then alphabetical. A user
    # opening this pane wants "what works now" above "what needs a token".
    return sorted(items, key=lambda x: (not x['ready'], x['kind'], x['name'].lower()))


# ── Endpoints ──────────────────────────────────────────────────────────────────
@router.get('/catalog')
def catalog(q: str = '', kind: str = '', ready: str = ''):
    """Every capability from every source, in one shape."""
    items = _catalog()

    if q:
        n = q.lower()
        items = [
            i for i in items
            if n in i['name'].lower()
            or n in i['description'].lower()
            or any(n in str(a).lower() for a in i['actions'])
        ]
    if kind:
        items = [i for i in items if i['kind'] == kind]
    if ready == 'true':
        items = [i for i in items if i['ready']]
    elif ready == 'false':
        items = [i for i in items if not i['ready']]

    full = _catalog()
    return {
        'ok': True,
        'items': items,
        'total': len(items),
        'kinds': sorted({i['kind'] for i in full}),
        'categories': sorted({i['category'] for i in full if i['category']}),
    }


@router.get('/stats')
def stats():
    items = _catalog()
    return {
        'ok': True,
        'total': len(items),
        'ready': sum(1 for i in items if i['ready']),
        'needs_setup': sum(1 for i in items if i['needs_setup']),
        'tools': sum(1 for i in items if i['kind'] == KIND_TOOL),
        'connectors': sum(1 for i in items if i['kind'] == KIND_CONNECTOR),
        'servers': sum(1 for i in items if i['kind'] == KIND_SERVER),
    }


@router.get('/item/{item_id:path}')
def item_detail(item_id: str):
    """Detail for one capability, including how to set it up if it needs it."""
    entry = next((i for i in _catalog() if i['id'] == item_id), None)
    if not entry:
        return JSONResponse({'ok': False, 'error': 'Not found'}, status_code=404)

    setup = SETUP_HINTS.get(item_id)
    return {
        'ok': True,
        **entry,
        'setup': setup,
        # Stated plainly rather than left implicit: a tool is callable by the
        # agent right now; a connector needs credentials before it is.
        'how_to_use': (
            f'Your agent can call {entry["name"]} directly.'
            if entry['kind'] == KIND_TOOL
            else (
                f'{entry["name"]} is connected and available to your agents.'
                if entry['ready']
                else f'{entry["name"]} needs credentials before your agents can use it.'
            )
        ),
    }


@router.post('/test/{item_id:path}')
async def test_item(item_id: str, req: Request):
    """Verify a capability actually works, rather than trusting its status flag.

    A connector row saying 'active' only means credentials were stored, not
    that they are valid. This is the difference between configured and working,
    which nothing in the UI previously distinguished.
    """
    entry = next((i for i in _catalog() if i['id'] == item_id), None)
    if not entry:
        return JSONResponse({'ok': False, 'error': 'Not found'}, status_code=404)

    if entry['kind'] == KIND_CONNECTOR:
        try:
            from .connectors import test_connector

            result = await test_connector(item_id)
            if isinstance(result, JSONResponse):
                return result

            # connectors.test_connector() returns ok:true to mean "I answered
            # your question", including when the answer is "not configured".
            # Reporting that as a passing test is exactly the configured-vs-
            # working conflation this endpoint exists to remove -- caught by
            # testing my own feature against an unconfigured connector.
            configured = result.get('configured')
            status = result.get('status', '')
            works = bool(result.get('ok')) and configured is not False and status != 'unconfigured'

            return {
                'ok': works,
                'id': item_id,
                'configured': bool(configured),
                'detail': result.get('message') or result,
            }
        except Exception as e:
            return JSONResponse({'ok': False, 'error': str(e)[:300]}, status_code=502)

    if entry['kind'] == KIND_TOOL:
        return {
            'ok': True,
            'id': item_id,
            'detail': 'Built-in tool — always available to agents.',
        }

    return {'ok': entry['ready'], 'id': item_id, 'detail': f"Server status: {entry['status']}"}


@router.get('/setup/{connector_id}')
def setup_guide(connector_id: str):
    """Setup instructions for a connector.

    Previously this text existed only inside the ERROR returned by a failed
    call: you had to get it wrong to find out how to get it right.
    """
    hint = SETUP_HINTS.get(connector_id)
    if not hint:
        entry = next((i for i in _catalog() if i['id'] == connector_id), None)
        if not entry:
            return JSONResponse({'ok': False, 'error': 'Not found'}, status_code=404)
        return {
            'ok': True,
            'id': connector_id,
            'needs': [],
            'where': 'No setup guidance is recorded for this integration yet.',
            'configure_endpoint': f'/api/connectors/{connector_id}/configure',
        }
    return {
        'ok': True,
        'id': connector_id,
        **hint,
        'configure_endpoint': f'/api/connectors/{connector_id}/configure',
    }
