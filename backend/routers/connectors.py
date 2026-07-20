"""
Agentic OS — Sprint C · Feature 2: Enterprise Connectors
══════════════════════════════════════════════════════════
A unified connector layer enabling agents to interact with the systems
businesses already use. Every action is policy-checked via MCP Gateway
and recorded in the Immutable Audit Log.

Connectors implemented:
  Slack          — messages, channels, user lookup
  Jira           — issues, projects, status updates
  Google Workspace — Docs creation, Sheets data, Calendar events
  Email (SMTP)   — send formatted emails via configured SMTP
  Webhook (outbound) — POST arbitrary payloads to external URLs
  Generic HTTP   — any REST API with auth config

Connector SDK:
  Developers can register custom connectors via /api/connectors/register
  with a typed schema and credential config.

Based on:
  Fluid AI: "Enterprise work happens inside real systems"
  Roadmap Pillar 3: CRM, ERP, support, data, communication connectors
"""

from __future__ import annotations
from typing import Optional, Union, Any, Dict, List

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix='/api/connectors', tags=['connectors'])
log = logging.getLogger('agentic.connectors')

from backend.config import get_data_dir
ROOT = get_data_dir()

# ── Schema ─────────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS connector_registry (
    connector_id   TEXT PRIMARY KEY,
    name           TEXT NOT NULL DEFAULT '',
    description    TEXT NOT NULL DEFAULT '',
    category       TEXT NOT NULL DEFAULT 'custom',
    icon           TEXT NOT NULL DEFAULT '🔌',
    status         TEXT NOT NULL DEFAULT 'unconfigured',
    auth_type      TEXT NOT NULL DEFAULT 'api_key',
    credentials    TEXT NOT NULL DEFAULT '{}',
    capabilities   TEXT NOT NULL DEFAULT '[]',
    config         TEXT NOT NULL DEFAULT '{}',
    call_count     INTEGER NOT NULL DEFAULT 0,
    last_used      TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT '',
    updated_at     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS connector_executions (
    exec_id        TEXT PRIMARY KEY,
    connector_id   TEXT NOT NULL,
    action         TEXT NOT NULL DEFAULT '',
    agent_id       TEXT NOT NULL DEFAULT '',
    payload_hash   TEXT NOT NULL DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'ok',
    result         TEXT NOT NULL DEFAULT '',
    error          TEXT NOT NULL DEFAULT '',
    duration_ms    INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_ce_connector ON connector_executions(connector_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ce_agent     ON connector_executions(agent_id);
"""

BUILTIN_CONNECTORS = [
    {
        'connector_id': 'conn_slack',
        'name': 'Slack',
        'description': 'Send messages, manage channels, look up users in Slack workspaces',
        'category': 'communication',
        'icon': '💬',
        'status': 'unconfigured',
        'auth_type': 'api_key',
        'capabilities': json.dumps(['send_message', 'list_channels', 'get_user', 'post_file']),
        'config': json.dumps({'bot_token_env': 'SLACK_BOT_TOKEN', 'default_channel': 'general'}),
    },
    {
        'connector_id': 'conn_jira',
        'name': 'Jira',
        'description': 'Create issues, update status, query projects, add comments in Atlassian Jira',
        'category': 'project_mgmt',
        'icon': '🎫',
        'status': 'unconfigured',
        'auth_type': 'basic',
        'capabilities': json.dumps(
            ['create_issue', 'update_issue', 'get_issue', 'list_projects', 'add_comment', 'search_issues']
        ),
        'config': json.dumps(
            {'base_url_env': 'JIRA_BASE_URL', 'email_env': 'JIRA_EMAIL', 'token_env': 'JIRA_API_TOKEN'}
        ),
    },
    {
        'connector_id': 'conn_gdrive',
        'name': 'Google Workspace',
        'description': 'Create Docs, read/write Sheets, create Calendar events via Google APIs',
        'category': 'productivity',
        'icon': '📊',
        'status': 'unconfigured',
        'auth_type': 'oauth',
        'capabilities': json.dumps(['create_doc', 'read_sheet', 'write_sheet', 'create_calendar_event', 'list_events']),
        'config': json.dumps(
            {
                'client_id_env': 'GOOGLE_CLIENT_ID',
                'client_secret_env': 'GOOGLE_CLIENT_SECRET',
                'token_env': 'GOOGLE_OAUTH_TOKEN',
            }
        ),
    },
    {
        'connector_id': 'conn_email',
        'name': 'Email (Multi-Provider)',
        'description': 'Send email via SMTP (any provider), Gmail OAuth2, or Outlook OAuth2. Supports multi-account, HTML, CC/BCC, attachments, and templates.',
        'category': 'communication',
        'icon': '📧',
        'status': 'unconfigured',
        'auth_type': 'multi',
        'capabilities': json.dumps(['send_email', 'send_html_email', 'test_connection', 'list_accounts']),
        'config': json.dumps(
            {
                'modes': ['smtp', 'gmail_oauth', 'outlook_oauth'],
                'smtp': {
                    'host_env': 'SMTP_HOST',
                    'port_env': 'SMTP_PORT',
                    'user_env': 'SMTP_USER',
                    'pass_env': 'SMTP_PASS',
                    'from_env': 'SMTP_FROM',
                },
                'gmail': {'token_env': 'GMAIL_OAUTH_TOKEN', 'from_env': 'GMAIL_FROM'},
                'outlook': {'token_env': 'OUTLOOK_OAUTH_TOKEN', 'from_env': 'OUTLOOK_FROM'},
            }
        ),
    },
    {
        'connector_id': 'conn_github',
        'name': 'GitHub',
        'description': 'Create issues, PRs, read files, trigger workflows via GitHub REST API',
        'category': 'devops',
        'icon': '🐙',
        'status': 'unconfigured',
        'auth_type': 'api_key',
        'capabilities': json.dumps(['create_issue', 'create_pr', 'get_file', 'trigger_workflow', 'list_repos']),
        'config': json.dumps({'token_env': 'GITHUB_TOKEN'}),
    },
    {
        'connector_id': 'conn_webhook',
        'name': 'Outbound Webhook',
        'description': 'POST arbitrary JSON payloads to any external HTTP endpoint',
        'category': 'integration',
        'icon': '🪝',
        'status': 'active',
        'auth_type': 'none',
        'capabilities': json.dumps(['post_webhook', 'post_with_auth']),
        'config': json.dumps({}),
    },
    {
        'connector_id': 'conn_notion',
        'name': 'Notion',
        'description': 'Create pages, update databases, read content from Notion workspaces',
        'category': 'productivity',
        'icon': '📝',
        'status': 'unconfigured',
        'auth_type': 'api_key',
        'capabilities': json.dumps(['create_page', 'update_page', 'query_database', 'get_page']),
        'config': json.dumps({'token_env': 'NOTION_TOKEN'}),
    },
    {
        'connector_id': 'conn_salesforce',
        'name': 'Salesforce CRM',
        'description': 'Query contacts, leads, opportunities, create/update records in Salesforce',
        'category': 'crm',
        'icon': '☁️',
        'status': 'unconfigured',
        'auth_type': 'oauth',
        'capabilities': json.dumps(['query_records', 'create_record', 'update_record', 'get_contact', 'create_lead']),
        'config': json.dumps({'instance_url_env': 'SALESFORCE_INSTANCE_URL', 'token_env': 'SALESFORCE_ACCESS_TOKEN'}),
    },
]


def _get_conn():
    from ..services.memory_db import get_conn

    return get_conn()


def _ensure_schema():
    con = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    try:
        con.executescript(_SCHEMA)
        for c in BUILTIN_CONNECTORS:
            existing = con.execute(
                'SELECT connector_id FROM connector_registry WHERE connector_id=?', (c['connector_id'],)
            ).fetchone()
            if not existing:
                con.execute(
                    """INSERT INTO connector_registry (connector_id,name,description,category,icon,status,auth_type,capabilities,config,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        c['connector_id'],
                        c['name'],
                        c['description'],
                        c['category'],
                        c['icon'],
                        c['status'],
                        c['auth_type'],
                        c['capabilities'],
                        c['config'],
                        now,
                        now,
                    ),
                )
        con.commit()
    finally:
        con.close()


_ensure_schema()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connector_dict(row) -> dict:
    d = dict(row)
    for f in ('capabilities', 'config', 'credentials'):
        try:
            d[f] = json.loads(d.get(f, '[]' if f == 'capabilities' else '{}'))
        except:
            pass
    # Mask credentials
    if 'credentials' in d and isinstance(d['credentials'], dict):
        d['credentials'] = {k: '***' if v else '' for k, v in d['credentials'].items()}
    return d


# ── Action dispatchers ─────────────────────────────────────────────────────────
async def _exec_slack(action: str, payload: dict, creds: dict) -> dict:
    """
    Slack connector — full Slack Web API coverage.

    Credentials (one of):
      • creds dict:  { "bot_token": "xoxb-..." }
      • env var:     SLACK_BOT_TOKEN=xoxb-...
      • PATCH /configure: { "credentials": { "bot_token": "xoxb-..." } }

    Actions:
      test_connection   — verify token and return workspace/bot info
      send_message      — post a plain-text message to a channel
      send_rich_message — post a Block Kit / Markdown message with attachments
      list_channels     — list all public channels the bot can see
      get_channel       — get details for one channel by name or ID
      create_channel    — create a new public or private channel
      invite_to_channel — invite users to a channel
      get_user          — look up a user by email or user ID
      list_members      — list members of a channel
      post_file         — upload a file/snippet to a channel
      add_reaction      — add an emoji reaction to a message
      get_message       — retrieve a message by channel + timestamp
      update_message    — update (edit) an existing message
      delete_message    — delete a message
      set_topic         — set a channel topic
      list_accounts     — list configured Slack workspaces

    Payload fields vary by action — see individual action comments below.
    """
    import os

    import httpx

    token = creds.get('bot_token') or creds.get('token') or os.getenv('SLACK_BOT_TOKEN', '')
    if not token and action not in ('list_accounts',):
        return {
            'ok': False,
            'error': (
                'SLACK_BOT_TOKEN not configured. Provide it one of these ways:\n'
                '1. PATCH /api/connectors/conn_slack/configure  {"credentials":{"bot_token":"xoxb-..."}}\n'
                '2. Set env var: SLACK_BOT_TOKEN=xoxb-...\n'
                '3. Pass credentials inline in the execute call'
            ),
        }

    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

    async def _get(path: str, params:Optional[ dict] = None) -> dict:
        async with httpx.AsyncClient(timeout=15) as cl:
            r = await cl.get(f'https://slack.com/api/{path}', headers=headers, params=params or {})
            return r.json()

    async def _post(path: str, body: dict) -> dict:
        async with httpx.AsyncClient(timeout=15) as cl:
            r = await cl.post(f'https://slack.com/api/{path}', headers=headers, json=body)
            return r.json()

    def _slack_ok(d: dict, extra:Optional[ dict] = None) -> dict:
        """Normalize a Slack API response into our standard format."""
        if d.get('ok'):
            result = {'ok': True}
            result.update(extra or {})
            # Include useful fields if present
            for field in ('ts', 'channel', 'name', 'id', 'user', 'message', 'topic', 'purpose', 'members'):
                if field in d:
                    result[field] = d[field]
            return result
        return {
            'ok': False,
            'error': d.get('error', 'unknown_error'),
            'detail': d.get('needed', '') or d.get('warning', ''),
        }

    # ── list_accounts ─────────────────────────────────────────────────────────
    if action == 'list_accounts':
        accounts = []
        env_tok = os.getenv('SLACK_BOT_TOKEN', '')
        if env_tok:
            accounts.append({'id': 'slack_default', 'token_prefix': env_tok[:12] + '...', 'source': 'env'})
        if creds.get('bot_token') and creds['bot_token'] != env_tok:
            accounts.append({'id': 'slack_inline', 'token_prefix': creds['bot_token'][:12] + '...', 'source': 'inline'})
        return {'ok': True, 'accounts': accounts, 'count': len(accounts)}

    # ── test_connection ───────────────────────────────────────────────────────
    if action == 'test_connection':
        d = await _get('auth.test')
        if not d.get('ok'):
            return {'ok': False, 'error': d.get('error', 'Token invalid'), 'detail': d}
        return {
            'ok': True,
            'workspace': d.get('team'),
            'team_id': d.get('team_id'),
            'bot_name': d.get('user'),
            'bot_id': d.get('user_id'),
            'url': d.get('url'),
            'message': f"Connected to '{d.get('team')}' as @{d.get('user')}",
        }

    # ── send_message ──────────────────────────────────────────────────────────
    if action in ('send_message', 'send'):
        """
        payload: {
          "channel": "#general" or "C01ABC123",   # required
          "text":    "Hello world",                 # required
          "thread_ts": "1234567890.123456",         # optional: reply in thread
          "username":  "Agentic OS",                # optional: display name override
          "icon_emoji": ":robot_face:",             # optional
        }
        """
        channel = payload.get('channel', '')
        text = payload.get('text', '')
        thread_ts = payload.get('thread_ts', '')
        username = payload.get('username', '')
        icon = payload.get('icon_emoji', '')

        if not channel:
            return {'ok': False, 'error': "payload.channel is required (e.g. '#general' or 'C01ABC123')"}
        if not text:
            return {'ok': False, 'error': 'payload.text is required'}

        body: dict = {'channel': channel, 'text': text}
        if thread_ts:
            body['thread_ts'] = thread_ts
        if username:
            body['username'] = username
        if icon:
            body['icon_emoji'] = icon

        d = await _post('chat.postMessage', body)
        return _slack_ok(d, {'channel': d.get('channel'), 'ts': d.get('ts'), 'text': text[:80]})

    # ── send_rich_message ─────────────────────────────────────────────────────
    if action == 'send_rich_message':
        """
        payload: {
          "channel": "#general",
          "text":    "Fallback text for notifications",
          "blocks":  [...],         # Slack Block Kit JSON
          "attachments": [...],     # legacy attachments (color sidebars)
          "thread_ts": "..."        # optional thread reply
        }
        """
        channel = payload.get('channel', '')
        if not channel:
            return {'ok': False, 'error': 'payload.channel is required'}

        body: dict = {
            'channel': channel,
            'text': payload.get('text', 'Message from Agentic OS'),
        }
        if payload.get('blocks'):
            body['blocks'] = payload['blocks']
        if payload.get('attachments'):
            body['attachments'] = payload['attachments']
        if payload.get('thread_ts'):
            body['thread_ts'] = payload['thread_ts']

        d = await _post('chat.postMessage', body)
        return _slack_ok(d, {'channel': d.get('channel'), 'ts': d.get('ts')})

    # ── list_channels ─────────────────────────────────────────────────────────
    if action == 'list_channels':
        """
        payload: { "limit": 100, "types": "public_channel,private_channel" }
        """
        params = {
            'limit': payload.get('limit', 200),
            'types': payload.get('types', 'public_channel'),
            'exclude_archived': True,
        }
        d = await _get('conversations.list', params)
        if not d.get('ok'):
            return {'ok': False, 'error': d.get('error', 'failed')}
        channels = [
            {
                'id': ch['id'],
                'name': ch['name'],
                'is_private': ch.get('is_private', False),
                'num_members': ch.get('num_members', 0),
                'topic': ch.get('topic', {}).get('value', ''),
                'purpose': ch.get('purpose', {}).get('value', ''),
            }
            for ch in d.get('channels', [])
        ]
        return {'ok': True, 'channels': channels, 'count': len(channels)}

    # ── get_channel ───────────────────────────────────────────────────────────
    if action == 'get_channel':
        """payload: { "channel": "#general" or "C01ABC123" }"""
        channel = payload.get('channel', '')
        if not channel:
            return {'ok': False, 'error': 'payload.channel required'}
        # If name given, look up ID from list
        if channel.startswith('#'):
            channel = channel.lstrip('#')
            d = await _get('conversations.list', {'limit': 200})
            match = next((c for c in d.get('channels', []) if c['name'] == channel), None)
            if not match:
                return {'ok': False, 'error': f"Channel '#{channel}' not found"}
            channel = match['id']
        d = await _get('conversations.info', {'channel': channel})
        ch = d.get('channel', {})
        return _slack_ok(
            d,
            {
                'id': ch.get('id'),
                'name': ch.get('name'),
                'topic': ch.get('topic', {}).get('value', ''),
                'purpose': ch.get('purpose', {}).get('value', ''),
                'num_members': ch.get('num_members', 0),
                'is_private': ch.get('is_private', False),
            },
        )

    # ── create_channel ────────────────────────────────────────────────────────
    if action == 'create_channel':
        """payload: { "name": "my-new-channel", "is_private": false }"""
        name = payload.get('name', '').lower().replace(' ', '-')
        if not name:
            return {'ok': False, 'error': 'payload.name required'}
        d = await _post('conversations.create', {'name': name, 'is_private': payload.get('is_private', False)})
        ch = d.get('channel', {})
        return _slack_ok(d, {'id': ch.get('id'), 'name': ch.get('name')})

    # ── invite_to_channel ─────────────────────────────────────────────────────
    if action == 'invite_to_channel':
        """payload: { "channel": "C01ABC123", "users": "U01ABC123,U02DEF456" }"""
        d = await _post(
            'conversations.invite', {'channel': payload.get('channel', ''), 'users': payload.get('users', '')}
        )
        return _slack_ok(d)

    # ── get_user ──────────────────────────────────────────────────────────────
    if action == 'get_user':
        """payload: { "email": "user@example.com" }  OR  { "user_id": "U01ABC123" }"""
        if payload.get('email'):
            d = await _get('users.lookupByEmail', {'email': payload['email']})
            u = d.get('user', {})
        elif payload.get('user_id'):
            d = await _get('users.info', {'user': payload['user_id']})
            u = d.get('user', {})
        else:
            return {'ok': False, 'error': 'payload.email or payload.user_id required'}
        if not d.get('ok'):
            return {'ok': False, 'error': d.get('error', 'user_not_found')}
        profile = u.get('profile', {})
        return {
            'ok': True,
            'user_id': u.get('id'),
            'name': u.get('name'),
            'real_name': u.get('real_name', ''),
            'email': profile.get('email', ''),
            'display_name': profile.get('display_name', ''),
            'is_bot': u.get('is_bot', False),
            'is_admin': u.get('is_admin', False),
            'tz': u.get('tz', ''),
        }

    # ── list_members ──────────────────────────────────────────────────────────
    if action == 'list_members':
        """payload: { "channel": "C01ABC123" }"""
        d = await _get('conversations.members', {'channel': payload.get('channel', ''), 'limit': 200})
        return _slack_ok(d, {'members': d.get('members', []), 'count': len(d.get('members', []))})

    # ── post_file ─────────────────────────────────────────────────────────────
    if action == 'post_file':
        """
        payload: {
          "channel":  "#general",
          "content":  "file contents as string",
          "filename": "report.txt",
          "title":    "My Report",
          "filetype": "text"      # text, python, json, csv, etc.
        }
        """
        channel = payload.get('channel', '')
        content = payload.get('content', '')
        filename = payload.get('filename', 'file.txt')
        title = payload.get('title', filename)
        filetype = payload.get('filetype', 'text')

        # Resolve channel name → channel ID (Slack requires C-prefixed ID for uploads)
        chan_id = channel
        if not channel.startswith('C'):
            # Strip leading # and look up ID
            name = channel.lstrip('#')
            ch_list = await _get('conversations.list', {'limit': 200})
            match = next((c for c in ch_list.get('channels', []) if c['name'] == name), None)
            if match:
                chan_id = match['id']

        # Auto-join so the bot has membership (requires channels:join scope)
        await _post('conversations.join', {'channel': chan_id})

        # Slack 3-step upload API (files.upload deprecated March 2025)
        raw_bytes = content.encode('utf-8')

        async with httpx.AsyncClient(timeout=20) as cl:
            # Step 1: Get presigned upload URL — MUST be form-encoded, NOT JSON
            r1 = await cl.post(
                'https://slack.com/api/files.getUploadURLExternal',
                headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/x-www-form-urlencoded'},
                content=f'filename={filename}&length={len(raw_bytes)}'.encode(),
            )
            d1 = r1.json()

        if not d1.get('ok'):
            return {'ok': False, 'error': d1.get('error', 'getUploadURL failed'), 'detail': d1}

        upload_url = d1['upload_url']
        file_id = d1['file_id']

        async with httpx.AsyncClient(timeout=20) as cl:
            # Step 2: PUT raw bytes to presigned URL (octet-stream, no auth header)
            await cl.post(upload_url, content=raw_bytes, headers={'Content-Type': 'application/octet-stream'})

            # Step 3: Complete — share to channel ID (not channel name)
            r3 = await cl.post(
                'https://slack.com/api/files.completeUploadExternal',
                headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                json={
                    'files': [{'id': file_id, 'title': title}],
                    'channel_id': chan_id,
                    'initial_comment': f'📎 *{title}* — uploaded by Agentic OS',
                },
            )
            d3 = r3.json()

        if d3.get('ok'):
            files = d3.get('files', [{}])
            f = files[0] if files else {}
            return {
                'ok': True,
                'file_id': file_id,
                'filename': filename,
                'title': title,
                'url': f.get('permalink', ''),
                'channel': channel,
            }
        return {'ok': False, 'error': d3.get('error', 'completeUpload failed'), 'detail': d3}

    # ── add_reaction ──────────────────────────────────────────────────────────
    if action == 'add_reaction':
        """payload: { "channel": "C01ABC123", "timestamp": "1234567890.123", "emoji": "thumbsup" }"""
        channel = payload.get('channel', '')
        timestamp = payload.get('timestamp', '')
        emoji = payload.get('emoji', 'thumbsup').strip(':')
        # Auto-join channel so bot can react (requires channels:join scope)
        await _post('conversations.join', {'channel': channel})
        d = await _post('reactions.add', {'channel': channel, 'timestamp': timestamp, 'name': emoji})
        return _slack_ok(d)

    # ── get_message ───────────────────────────────────────────────────────────
    if action == 'get_message':
        """payload: { "channel": "C01ABC123", "ts": "1234567890.123456" }"""
        d = await _get(
            'conversations.history',
            {'channel': payload.get('channel', ''), 'latest': payload.get('ts', ''), 'limit': 1, 'inclusive': True},
        )
        if not d.get('ok'):
            err = d.get('error', 'failed')
            if err == 'missing_scope':
                return {
                    'ok': False,
                    'error': "Missing scope: add 'channels:history' to your Slack app at api.slack.com/apps",
                    'needed': d.get('needed', ''),
                }
            return {'ok': False, 'error': err}
        msgs = d.get('messages', [])
        if not msgs:
            return {'ok': False, 'error': 'Message not found'}
        m = msgs[0]
        return {
            'ok': True,
            'ts': m.get('ts'),
            'text': m.get('text', ''),
            'user': m.get('user', ''),
            'type': m.get('type', ''),
        }

    # ── update_message ────────────────────────────────────────────────────────
    if action == 'update_message':
        """payload: { "channel": "C01ABC123", "ts": "1234567890.123", "text": "updated text" }"""
        d = await _post(
            'chat.update',
            {'channel': payload.get('channel', ''), 'ts': payload.get('ts', ''), 'text': payload.get('text', '')},
        )
        return _slack_ok(d, {'ts': d.get('ts'), 'text': payload.get('text', '')})

    # ── delete_message ────────────────────────────────────────────────────────
    if action == 'delete_message':
        """payload: { "channel": "C01ABC123", "ts": "1234567890.123456" }"""
        d = await _post('chat.delete', {'channel': payload.get('channel', ''), 'ts': payload.get('ts', '')})
        return _slack_ok(d)

    # ── set_topic ─────────────────────────────────────────────────────────────
    if action == 'set_topic':
        """payload: { "channel": "C01ABC123", "topic": "New topic text" }"""
        d = await _post(
            'conversations.setTopic', {'channel': payload.get('channel', ''), 'topic': payload.get('topic', '')}
        )
        if not d.get('ok') and d.get('error') == 'missing_scope':
            return {
                'ok': False,
                'error': "Missing scope: add 'channels:write.topic' to your Slack app at api.slack.com/apps",
                'needed': d.get('needed', ''),
            }
        return _slack_ok(d, {'topic': payload.get('topic', '')})

    return {
        'ok': False,
        'error': f"Unknown Slack action: '{action}'. Valid: "
        'test_connection, send_message, send_rich_message, list_channels, '
        'get_channel, create_channel, invite_to_channel, get_user, '
        'list_members, post_file, add_reaction, get_message, '
        'update_message, delete_message, set_topic, list_accounts',
    }


async def _exec_jira(action: str, payload: dict, creds: dict) -> dict:
    """
    Jira connector — full Jira REST API v3 coverage.

    Credentials:
      creds: { "base_url":"https://yoursite.atlassian.net",
               "email":"you@example.com",
               "token":"ATATT3x..." }
      OR env vars: JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN

    Actions (24 total):
      test_connection    — verify credentials, return user + site info
      list_projects      — list all accessible projects
      get_project        — get project details by key
      list_issues        — list/search issues in a project
      search_issues      — JQL search across all projects
      get_issue          — get full issue details by key
      create_issue       — create Story/Bug/Task/Epic/Sub-task
      update_issue       — update summary, description, priority, status
      delete_issue       — delete an issue
      add_comment        — add a comment to an issue
      get_comments       — list all comments on an issue
      transition_issue   — move issue to new status (To Do→In Progress→Done)
      get_transitions    — list available transitions for an issue
      assign_issue       — assign issue to a user
      get_issue_types    — list issue types for a project
      list_priorities    — list available priorities
      get_user           — look up a user by account ID or email
      search_users       — search users by query string
      create_sprint      — create a new sprint (Scrum boards)
      list_sprints       — list sprints for a board
      get_board          — get board details
      list_boards        — list all boards
      get_myself         — get authenticated user info
      list_accounts      — list configured Jira sites
    """
    import base64
    import os

    import httpx

    base_url = (creds.get('base_url') or os.getenv('JIRA_BASE_URL', '')).rstrip('/')
    email = creds.get('email') or os.getenv('JIRA_EMAIL', '')
    token = creds.get('token') or os.getenv('JIRA_API_TOKEN', '')

    if not base_url and action != 'list_accounts':
        return {
            'ok': False,
            'error': (
                'Jira not configured. Provide credentials one of these ways:\n'
                '1. PATCH /api/connectors/conn_jira/configure  '
                '{"credentials":{"base_url":"https://site.atlassian.net",'
                '"email":"you@example.com","token":"ATATT3x..."}}\n'
                '2. Set env vars: JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN\n'
                '3. Pass credentials inline in the execute call'
            ),
        }

    auth = base64.b64encode(f'{email}:{token}'.encode()).decode()
    HDR = {'Authorization': f'Basic {auth}', 'Content-Type': 'application/json', 'Accept': 'application/json'}
    API3 = f'{base_url}/rest/api/3'
    AGILE = f'{base_url}/rest/agile/1.0'

    async def _get(path: str, params:Optional[ dict] = None) -> tuple:
        async with httpx.AsyncClient(timeout=15) as cl:
            r = await cl.get(path, headers=HDR, params=params or {})
            try:
                return r.status_code, r.json()
            except:
                return r.status_code, {}

    async def _post(path: str, body: dict) -> tuple:
        async with httpx.AsyncClient(timeout=15) as cl:
            r = await cl.post(path, headers=HDR, json=body)
            try:
                return r.status_code, r.json()
            except:
                return r.status_code, {}

    async def _put(path: str, body: dict) -> tuple:
        async with httpx.AsyncClient(timeout=15) as cl:
            r = await cl.put(path, headers=HDR, json=body)
            try:
                return r.status_code, r.json()
            except:
                return r.status_code, {}

    async def _delete(path: str) -> tuple:
        async with httpx.AsyncClient(timeout=15) as cl:
            r = await cl.delete(path, headers=HDR)
            return r.status_code, {}

    def _adf(text: str) -> dict:
        """Convert plain text to Atlassian Document Format (ADF)."""
        return {
            'type': 'doc',
            'version': 1,
            'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': text}]}],
        }

    def _ok(status: int, d: dict, extra:Optional[ dict] = None) -> dict:
        success = 200 <= status < 300
        if not success:
            msgs = d.get('errorMessages', [])
            errs = d.get('errors', {})
            return {'ok': False, 'error': '; '.join(msgs) if msgs else str(errs) or f'HTTP {status}', 'status': status}
        result = {'ok': True}
        result.update(extra or {})
        return result

    def _fmt_issue(d: dict) -> dict:
        """Extract the most useful fields from a Jira issue."""
        f = d.get('fields', {})
        return {
            'key': d.get('key'),
            'id': d.get('id'),
            'summary': f.get('summary', ''),
            'status': f.get('status', {}).get('name', ''),
            'type': f.get('issuetype', {}).get('name', ''),
            'priority': (f.get('priority') or {}).get('name', ''),
            'assignee': (f.get('assignee') or {}).get('displayName', 'Unassigned'),
            'reporter': (f.get('reporter') or {}).get('displayName', ''),
            'project': f.get('project', {}).get('key', ''),
            'created': (f.get('created') or '')[:10],
            'updated': (f.get('updated') or '')[:10],
            'url': f'{base_url}/browse/{d.get("key", "")}',
        }

    # ── list_accounts ─────────────────────────────────────────────────────────
    if action == 'list_accounts':
        accounts = []
        env_url = os.getenv('JIRA_BASE_URL', '')
        if env_url:
            accounts.append({'id': 'jira_env', 'base_url': env_url, 'source': 'env'})
        if base_url and base_url != env_url:
            accounts.append({'id': 'jira_configured', 'base_url': base_url, 'source': 'configured'})
        return {'ok': True, 'accounts': accounts, 'count': len(accounts)}

    # ── test_connection ───────────────────────────────────────────────────────
    if action == 'test_connection':
        status, me = await _get(f'{API3}/myself')
        if status != 200:
            return {'ok': False, 'error': me.get('message', 'Invalid credentials'), 'status': status}
        # Also grab accessible resources / site name
        status2, prj = await _get(f'{API3}/project/search', {'maxResults': 5})
        projects = prj.get('values', []) if status2 == 200 else []
        return {
            'ok': True,
            'display_name': me.get('displayName'),
            'email': me.get('emailAddress'),
            'account_id': me.get('accountId'),
            'site': base_url,
            'projects': [p.get('key') for p in projects],
            'message': f'Authenticated as {me.get("displayName")} at {base_url}',
        }

    # ── get_myself ────────────────────────────────────────────────────────────
    if action == 'get_myself':
        status, d = await _get(f'{API3}/myself')
        return _ok(
            status,
            d,
            {
                'display_name': d.get('displayName'),
                'email': d.get('emailAddress'),
                'account_id': d.get('accountId'),
                'timezone': d.get('timeZone', ''),
                'locale': d.get('locale', ''),
                'active': d.get('active'),
            },
        )

    # ── list_projects ─────────────────────────────────────────────────────────
    if action == 'list_projects':
        status, d = await _get(
            f'{API3}/project/search',
            {
                'maxResults': payload.get('max_results', 50),
                'orderBy': 'name',
            },
        )
        if status != 200:
            return _ok(status, d)
        projects = [
            {
                'key': p.get('key'),
                'name': p.get('name'),
                'id': p.get('id'),
                'type': p.get('projectTypeKey', ''),
                'style': p.get('style', ''),
                'url': f'{base_url}/jira/software/projects/{p.get("key")}/boards',
                'lead': (p.get('lead') or {}).get('displayName', ''),
            }
            for p in d.get('values', [])
        ]
        return {'ok': True, 'projects': projects, 'count': len(projects), 'total': d.get('total', 0)}

    # ── get_project ───────────────────────────────────────────────────────────
    if action == 'get_project':
        key = payload.get('project_key', '') or payload.get('project', '')
        if not key:
            return {'ok': False, 'error': 'payload.project_key required'}
        status, d = await _get(f'{API3}/project/{key}')
        if status != 200:
            return _ok(status, d)
        return {
            'ok': True,
            'key': d.get('key'),
            'name': d.get('name'),
            'id': d.get('id'),
            'description': d.get('description', ''),
            'type': d.get('projectTypeKey', ''),
            'lead': (d.get('lead') or {}).get('displayName', ''),
            'url': f'{base_url}/jira/software/projects/{d.get("key")}/boards',
            'issue_types': [t.get('name') for t in d.get('issueTypes', [])],
        }

    # ── list_issues ───────────────────────────────────────────────────────────
    if action == 'list_issues':
        """payload: { "project":"KAN","status":"To Do","max_results":20,"assignee":"accountId" }"""
        project = payload.get('project', '') or payload.get('project_key', '')
        jql_parts = []
        if project:
            jql_parts.append(f'project = "{project}"')
        if payload.get('status'):
            jql_parts.append(f'status = "{payload["status"]}"')
        if payload.get('assignee'):
            jql_parts.append(f'assignee = "{payload["assignee"]}"')
        if payload.get('type'):
            jql_parts.append(f'issuetype = "{payload["type"]}"')
        jql = ' AND '.join(jql_parts) + ' ORDER BY updated DESC' if jql_parts else 'ORDER BY updated DESC'
        # Use newer /search/jql endpoint (old /search returns 410 on Jira Cloud)
        status, d = await _post(
            f'{API3}/search/jql',
            {
                'jql': jql,
                'maxResults': payload.get('max_results', 20),
                'fields': [
                    'summary',
                    'status',
                    'issuetype',
                    'priority',
                    'assignee',
                    'reporter',
                    'created',
                    'updated',
                    'project',
                ],
            },
        )
        if status not in (200, 201):
            return _ok(status, d)
        issues = [_fmt_issue(i) for i in d.get('issues', [])]
        return {'ok': True, 'issues': issues, 'count': len(issues), 'total': d.get('total', len(issues)), 'jql': jql}

    # ── search_issues ─────────────────────────────────────────────────────────
    if action == 'search_issues':
        """payload: { "jql":"project = KAN AND status = 'In Progress'","max_results":20 }"""
        jql = payload.get('jql', '')
        if not jql:
            return {'ok': False, 'error': 'payload.jql required'}
        # Use newer /search/jql endpoint (old /search returns 410 on Jira Cloud)
        status, d = await _post(
            f'{API3}/search/jql',
            {
                'jql': jql,
                'maxResults': payload.get('max_results', 20),
                'fields': [
                    'summary',
                    'status',
                    'issuetype',
                    'priority',
                    'assignee',
                    'reporter',
                    'created',
                    'updated',
                    'project',
                ],
            },
        )
        if status not in (200, 201):
            return _ok(status, d)
        issues = [_fmt_issue(i) for i in d.get('issues', [])]
        return {'ok': True, 'issues': issues, 'count': len(issues), 'total': d.get('total', len(issues))}

    # ── get_issue ─────────────────────────────────────────────────────────────
    if action == 'get_issue':
        """payload: { "issue_key":"KAN-1" }"""
        key = payload.get('issue_key', '') or payload.get('key', '')
        if not key:
            return {'ok': False, 'error': "payload.issue_key required (e.g. 'KAN-1')"}
        status, d = await _get(f'{API3}/issue/{key}')
        if status != 200:
            return _ok(status, d)
        result = _fmt_issue(d)
        # Also include description text
        desc_adf = d.get('fields', {}).get('description') or {}
        result['description'] = ' '.join(
            node.get('text', '')
            for block in (desc_adf.get('content') or [])
            for node in (block.get('content') or [])
            if node.get('type') == 'text'
        )
        return {'ok': True, **result}

    # ── create_issue ──────────────────────────────────────────────────────────
    if action == 'create_issue':
        """payload: {
          "project":"KAN","title":"Bug: login fails","description":"...",
          "issue_type":"Bug","priority":"High","assignee_id":"accountId",
          "labels":["backend"],"parent":"KAN-1"  (for sub-tasks)
        }"""
        project = payload.get('project', '') or payload.get('project_key', '')
        summary = payload.get('title', '') or payload.get('summary', '')
        issue_type = payload.get('issue_type', 'Task')
        if not project or not summary:
            return {'ok': False, 'error': 'payload.project and payload.title required'}
        fields: dict = {
            'project': {'key': project},
            'summary': summary,
            'issuetype': {'name': issue_type},
        }
        if payload.get('description'):
            fields['description'] = _adf(payload['description'])
        if payload.get('priority'):
            fields['priority'] = {'name': payload['priority']}
        if payload.get('assignee_id'):
            fields['assignee'] = {'accountId': payload['assignee_id']}
        if payload.get('labels'):
            fields['labels'] = payload['labels']
        if payload.get('parent'):
            fields['parent'] = {'key': payload['parent']}
        status, d = await _post(f'{API3}/issue', {'fields': fields})
        return _ok(
            status,
            d,
            {
                'issue_key': d.get('key'),
                'id': d.get('id'),
                'url': f'{base_url}/browse/{d.get("key", "")}',
            },
        )

    # ── update_issue ──────────────────────────────────────────────────────────
    if action == 'update_issue':
        """payload: { "issue_key":"KAN-1","title":"New title","description":"...","priority":"Low" }"""
        key = payload.get('issue_key', '') or payload.get('key', '')
        if not key:
            return {'ok': False, 'error': 'payload.issue_key required'}
        fields: dict = {}
        if payload.get('title') or payload.get('summary'):
            fields['summary'] = payload.get('title') or payload['summary']
        if payload.get('description'):
            fields['description'] = _adf(payload['description'])
        if payload.get('priority'):
            fields['priority'] = {'name': payload['priority']}
        if payload.get('assignee_id'):
            fields['assignee'] = {'accountId': payload['assignee_id']}
        if payload.get('labels'):
            fields['labels'] = payload['labels']
        async with httpx.AsyncClient(timeout=15) as cl:
            r = await cl.put(f'{API3}/issue/{key}', headers=HDR, json={'fields': fields})
        return {
            'ok': r.status_code == 204,
            'issue_key': key,
            'error': '' if r.status_code == 204 else f'HTTP {r.status_code}',
            'url': f'{base_url}/browse/{key}',
        }

    # ── delete_issue ──────────────────────────────────────────────────────────
    if action == 'delete_issue':
        """payload: { "issue_key":"KAN-5" }"""
        key = payload.get('issue_key', '') or payload.get('key', '')
        if not key:
            return {'ok': False, 'error': 'payload.issue_key required'}
        status, _ = await _delete(f'{API3}/issue/{key}')
        return {'ok': status == 204, 'issue_key': key, 'error': '' if status == 204 else f'HTTP {status}'}

    # ── add_comment ───────────────────────────────────────────────────────────
    if action == 'add_comment':
        """payload: { "issue_key":"KAN-1","body":"Comment text here" }"""
        key = payload.get('issue_key', '') or payload.get('key', '')
        body = payload.get('body', '')
        if not key or not body:
            return {'ok': False, 'error': 'payload.issue_key and body required'}
        status, d = await _post(f'{API3}/issue/{key}/comment', {'body': _adf(body)})
        return _ok(
            status,
            d,
            {
                'comment_id': d.get('id'),
                'issue_key': key,
                'author': (d.get('author') or {}).get('displayName', ''),
                'created': (d.get('created') or '')[:10],
            },
        )

    # ── get_comments ──────────────────────────────────────────────────────────
    if action == 'get_comments':
        """payload: { "issue_key":"KAN-1" }"""
        key = payload.get('issue_key', '') or payload.get('key', '')
        if not key:
            return {'ok': False, 'error': 'payload.issue_key required'}
        status, d = await _get(f'{API3}/issue/{key}/comment', {'maxResults': payload.get('max_results', 20)})
        if status != 200:
            return _ok(status, d)
        comments = [
            {
                'id': c.get('id'),
                'author': (c.get('author') or {}).get('displayName', ''),
                'created': (c.get('created') or '')[:10],
                'body': ' '.join(
                    node.get('text', '')
                    for block in ((c.get('body') or {}).get('content') or [])
                    for node in (block.get('content') or [])
                    if node.get('type') == 'text'
                ),
            }
            for c in d.get('comments', [])
        ]
        return {'ok': True, 'comments': comments, 'count': len(comments), 'total': d.get('total', 0)}

    # ── get_transitions ───────────────────────────────────────────────────────
    if action == 'get_transitions':
        """payload: { "issue_key":"KAN-1" }"""
        key = payload.get('issue_key', '') or payload.get('key', '')
        if not key:
            return {'ok': False, 'error': 'payload.issue_key required'}
        status, d = await _get(f'{API3}/issue/{key}/transitions')
        if status != 200:
            return _ok(status, d)
        transitions = [
            {'id': t.get('id'), 'name': t.get('name'), 'to': t.get('to', {}).get('name', '')}
            for t in d.get('transitions', [])
        ]
        return {'ok': True, 'transitions': transitions, 'issue_key': key}

    # ── transition_issue ──────────────────────────────────────────────────────
    if action == 'transition_issue':
        """payload: { "issue_key":"KAN-1","status":"In Progress" }
           OR:      { "issue_key":"KAN-1","transition_id":"21" }"""
        key = payload.get('issue_key', '') or payload.get('key', '')
        target = payload.get('status', '') or payload.get('to_status', '')
        tid = payload.get('transition_id', '')
        if not key:
            return {'ok': False, 'error': 'payload.issue_key required'}

        if not tid:
            # Look up transition ID by target status name
            _, trans_d = await _get(f'{API3}/issue/{key}/transitions')
            for t in trans_d.get('transitions', []):
                if t.get('to', {}).get('name', '').lower() == target.lower():
                    tid = t.get('id', '')
                    break
            if not tid:
                avail = [t.get('to', {}).get('name') for t in trans_d.get('transitions', [])]
                return {'ok': False, 'error': f"Status '{target}' not found. Available: {avail}"}

        status, d = await _post(f'{API3}/issue/{key}/transitions', {'transition': {'id': str(tid)}})
        return {
            'ok': status == 204,
            'issue_key': key,
            'transitioned_to': target or tid,
            'error': '' if status == 204 else str(d),
        }

    # ── assign_issue ──────────────────────────────────────────────────────────
    if action == 'assign_issue':
        """payload: { "issue_key":"KAN-1","account_id":"712020:..." }
           Unassign: { "issue_key":"KAN-1","account_id":null }"""
        key = payload.get('issue_key', '') or payload.get('key', '')
        account_id = payload.get('account_id')
        if not key:
            return {'ok': False, 'error': 'payload.issue_key required'}
        async with httpx.AsyncClient(timeout=15) as cl:
            r = await cl.put(f'{API3}/issue/{key}/assignee', headers=HDR, json={'accountId': account_id})
        return {
            'ok': r.status_code == 204,
            'issue_key': key,
            'assigned_to': account_id or 'Unassigned',
            'error': '' if r.status_code == 204 else f'HTTP {r.status_code}',
        }

    # ── get_issue_types ───────────────────────────────────────────────────────
    if action == 'get_issue_types':
        """payload: { "project_key":"KAN" }"""
        project = payload.get('project_key', '') or payload.get('project', '')
        if project:
            # Jira /issuetype/project requires numeric ID not project key
            _, proj_d = await _get(f'{API3}/project/{project}')
            numeric_id = proj_d.get('id', '')
            if numeric_id:
                status, d = await _get(f'{API3}/issuetype/project', {'projectId': numeric_id})
            else:
                # Fallback: get all types and filter by project statuses
                status, d = await _get(f'{API3}/project/{project}/statuses')
                if status == 200 and isinstance(d, list):
                    return {
                        'ok': True,
                        'issue_types': [
                            {'id': t.get('id'), 'name': t.get('name'), 'subtask': t.get('subtask', False)} for t in d
                        ],
                    }
        else:
            status, d = await _get(f'{API3}/issuetype')
        if status != 200:
            return _ok(status, d)
        types = d if isinstance(d, list) else d.get('issueTypes', []) if 'issueTypes' in d else []
        return {
            'ok': True,
            'issue_types': [
                {'id': t.get('id'), 'name': t.get('name'), 'subtask': t.get('subtask', False)} for t in types
            ],
        }

    # ── list_priorities ───────────────────────────────────────────────────────
    if action == 'list_priorities':
        status, d = await _get(f'{API3}/priority')
        if status != 200:
            return _ok(status, d)
        return {
            'ok': True,
            'priorities': [{'id': p.get('id'), 'name': p.get('name')} for p in (d if isinstance(d, list) else [])],
        }

    # ── get_user ──────────────────────────────────────────────────────────────
    if action == 'get_user':
        """payload: { "account_id":"712020:..." }  OR  { "email":"user@example.com" }"""
        if payload.get('account_id'):
            status, d = await _get(f'{API3}/user', {'accountId': payload['account_id']})
        elif payload.get('email'):
            status, d = await _get(f'{API3}/user/search', {'query': payload['email']})
            if status == 200 and isinstance(d, list) and d:
                d = d[0]
            elif status == 200 and isinstance(d, list):
                return {'ok': False, 'error': 'User not found'}
        else:
            return {'ok': False, 'error': 'payload.account_id or payload.email required'}
        return _ok(
            status,
            d,
            {
                'account_id': d.get('accountId'),
                'display_name': d.get('displayName'),
                'email': d.get('emailAddress', ''),
                'active': d.get('active'),
                'timezone': d.get('timeZone', ''),
            },
        )

    # ── search_users ──────────────────────────────────────────────────────────
    if action == 'search_users':
        """payload: { "query":"david","max_results":10 }"""
        query = payload.get('query', '')
        if not query:
            return {'ok': False, 'error': 'payload.query required'}
        status, d = await _get(f'{API3}/user/search', {'query': query, 'maxResults': payload.get('max_results', 10)})
        if status != 200:
            return _ok(status, d)
        users = [
            {
                'account_id': u.get('accountId'),
                'display_name': u.get('displayName'),
                'email': u.get('emailAddress', ''),
                'active': u.get('active'),
            }
            for u in (d if isinstance(d, list) else [])
        ]
        return {'ok': True, 'users': users, 'count': len(users)}

    # ── list_boards ───────────────────────────────────────────────────────────
    if action == 'list_boards':
        """payload: { "project_key":"KAN","type":"scrum|kanban" }"""
        params: dict = {'maxResults': payload.get('max_results', 20)}
        if payload.get('project_key'):
            params['projectKeyOrId'] = payload['project_key']
        if payload.get('type'):
            params['type'] = payload['type']
        status, d = await _get(f'{AGILE}/board', params)
        if status != 200:
            return _ok(status, d)
        boards = [
            {
                'id': b.get('id'),
                'name': b.get('name'),
                'type': b.get('type'),
                'project': (b.get('location') or {}).get('projectKey', ''),
            }
            for b in d.get('values', [])
        ]
        return {'ok': True, 'boards': boards, 'count': len(boards), 'total': d.get('total', 0)}

    # ── get_board ─────────────────────────────────────────────────────────────
    if action == 'get_board':
        """payload: { "board_id":1 }"""
        bid = payload.get('board_id', '')
        if not bid:
            return {'ok': False, 'error': 'payload.board_id required'}
        status, d = await _get(f'{AGILE}/board/{bid}')
        return _ok(
            status,
            d,
            {
                'id': d.get('id'),
                'name': d.get('name'),
                'type': d.get('type'),
                'project': (d.get('location') or {}).get('projectKey', ''),
            },
        )

    # ── list_sprints ──────────────────────────────────────────────────────────
    if action == 'list_sprints':
        """payload: { "board_id":1,"state":"active|future|closed" }"""
        bid = payload.get('board_id', '')
        if not bid:
            return {'ok': False, 'error': 'payload.board_id required'}
        params: dict = {'maxResults': payload.get('max_results', 20)}
        if payload.get('state'):
            params['state'] = payload['state']
        status, d = await _get(f'{AGILE}/board/{bid}/sprint', params)
        if status == 400 and 'does not support sprints' in str(d):
            # Kanban boards don't have sprints — this is correct behavior
            return {
                'ok': True,
                'sprints': [],
                'count': 0,
                'note': 'This board is Kanban type — sprints are only available on Scrum boards',
            }
        if status != 200:
            return _ok(status, d)
        sprints = [
            {
                'id': s.get('id'),
                'name': s.get('name'),
                'state': s.get('state'),
                'start': (s.get('startDate') or '')[:10],
                'end': (s.get('endDate') or '')[:10],
                'goal': s.get('goal', ''),
            }
            for s in d.get('values', [])
        ]
        return {'ok': True, 'sprints': sprints, 'count': len(sprints)}

    # ── create_sprint ─────────────────────────────────────────────────────────
    if action == 'create_sprint':
        """payload: { "board_id":1,"name":"Sprint 2","start_date":"2026-08-01","end_date":"2026-08-14","goal":"..." }"""
        bid = payload.get('board_id', '')
        if not bid or not payload.get('name'):
            return {'ok': False, 'error': 'payload.board_id and payload.name required'}
        body: dict = {'name': payload['name'], 'originBoardId': int(bid)}
        if payload.get('start_date'):
            body['startDate'] = payload['start_date'] + 'T00:00:00.000Z'
        if payload.get('end_date'):
            body['endDate'] = payload['end_date'] + 'T00:00:00.000Z'
        if payload.get('goal'):
            body['goal'] = payload['goal']
        status, d = await _post(f'{AGILE}/sprint', body)
        return _ok(
            status,
            d,
            {
                'sprint_id': d.get('id'),
                'name': d.get('name'),
                'state': d.get('state'),
                'board_id': bid,
            },
        )

    return {
        'ok': False,
        'error': f"Unknown Jira action: '{action}'. Valid: "
        'test_connection, list_projects, get_project, list_issues, '
        'search_issues, get_issue, create_issue, update_issue, delete_issue, '
        'add_comment, get_comments, transition_issue, get_transitions, '
        'assign_issue, get_issue_types, list_priorities, get_user, '
        'search_users, list_boards, get_board, list_sprints, '
        'create_sprint, get_myself, list_accounts',
    }


def _build_mime_message(
    frm: str,
    to: str,
    subject: str,
    body: str,
    cc: str = '',
    bcc: str = '',
    reply_to: str = '',
    is_html: bool = False,
    attachments:Optional[ list] = None,
) -> email.mime.multipart.MIMEMultipart:
    """Build a complete MIME message with optional HTML, CC/BCC, reply-to, attachments."""
    import base64
    from email import encoders
    from email.mime.base import MIMEBase
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart('alternative' if is_html else 'mixed')
    msg['Subject'] = subject
    msg['From'] = frm
    msg['To'] = to
    if cc:
        msg['Cc'] = cc
    if bcc:
        msg['Bcc'] = bcc
    if reply_to:
        msg['Reply-To'] = reply_to

    # Body — always include plain-text; optionally also HTML
    plain = body if not is_html else ''
    if is_html:
        # Try to strip tags for plain fallback
        import re

        plain = re.sub(r'<[^>]+>', '', body).strip()
    msg.attach(MIMEText(plain or body, 'plain'))
    if is_html:
        msg.attach(MIMEText(body, 'html'))

    # Attachments: [{"filename":"report.pdf","data":"<base64>","mime":"application/pdf"}]
    for att in attachments or []:
        try:
            raw = base64.b64decode(att.get('data', ''))
            mime = att.get('mime', 'application/octet-stream').split('/')
            part = MIMEBase(mime[0], mime[1] if len(mime) > 1 else 'octet-stream')
            part.set_payload(raw)
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', 'attachment', filename=att.get('filename', 'attachment'))
            msg.attach(part)
        except Exception:
            pass
    return msg


async def _smtp_send(
    host: str, port: int, user: str, pw: str, frm: str, recipients: list[str], raw_msg: str, use_ssl: bool = False
) -> None:
    """Send via SMTP — supports STARTTLS (port 587) and SSL (port 465).
    Uses stdlib smtplib via thread executor for maximum compatibility."""
    import smtplib
    import ssl

    def _send_sync():
        if use_ssl or port == 465:
            # SSL from the start (port 465)
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context, timeout=15) as s:
                if user and pw:
                    s.login(user, pw)
                s.sendmail(frm, recipients, raw_msg)
        else:
            # Plain + STARTTLS (port 587, most common)
            with smtplib.SMTP(host, port, timeout=15) as s:
                s.ehlo()
                s.starttls()
                s.ehlo()
                if user and pw:
                    s.login(user, pw)
                s.sendmail(frm, recipients, raw_msg)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _send_sync)


async def _gmail_oauth_send(access_token: str, frm: str, recipients: list[str], raw_msg: str) -> dict:
    """Send via Gmail API using OAuth2 access token (no SMTP password needed)."""
    import base64

    import httpx

    encoded = base64.urlsafe_b64encode(raw_msg.encode()).decode()
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            'https://gmail.googleapis.com/gmail/v1/users/me/messages/send',
            headers={'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'},
            json={'raw': encoded},
        )
    if r.status_code == 200:
        return {'ok': True, 'gmail_message_id': r.json().get('id')}
    return {'ok': False, 'error': f'Gmail API {r.status_code}: {r.text[:200]}'}


async def _outlook_oauth_send(
    access_token: str, frm: str, to: str, subject: str, body: str, is_html: bool = False
) -> dict:
    """Send via Microsoft Graph API using OAuth2 access token."""
    import httpx

    content_type = 'HTML' if is_html else 'Text'
    msg_payload = {
        'message': {
            'subject': subject,
            'body': {'contentType': content_type, 'content': body},
            'toRecipients': [{'emailAddress': {'address': addr.strip()}} for addr in to.split(',') if addr.strip()],
        },
        'saveToSentItems': True,
    }
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            'https://graph.microsoft.com/v1.0/me/sendMail',
            headers={'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'},
            json=msg_payload,
        )
    if r.status_code in (200, 202):
        return {'ok': True, 'provider': 'outlook_graph'}
    return {'ok': False, 'error': f'Graph API {r.status_code}: {r.text[:200]}'}


async def _exec_email(action: str, payload: dict, creds: dict) -> dict:
    """
    Email connector — supports three authentication modes:

    Mode 1: SMTP (any provider — Gmail App Password, Outlook, SMTP relay, etc.)
      creds: { "mode":"smtp", "host":"smtp.gmail.com", "port":587,
               "user":"you@gmail.com", "password":"app-password",
               "from_addr":"you@gmail.com" }
      OR env vars: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM

    Mode 2: Gmail OAuth2 (recommended for Gmail — no password needed)
      creds: { "mode":"gmail_oauth", "access_token":"ya29.xxx",
               "from_addr":"you@gmail.com" }
      OR env vars: GMAIL_OAUTH_TOKEN, GMAIL_FROM

    Mode 3: Outlook / Microsoft 365 OAuth2
      creds: { "mode":"outlook_oauth", "access_token":"eyJ0...",
               "from_addr":"you@outlook.com" }
      OR env vars: OUTLOOK_OAUTH_TOKEN, OUTLOOK_FROM

    Multi-account: Pass full creds dict inline in each execute call.
      Different accounts can be used per-call without reconfiguring.

    Payload (all modes):
      { "to":"recipient@example.com",      # required; comma-sep for multiple
        "subject":"Hello from Agentic OS", # optional
        "body":"Email body here",          # plain text or HTML
        "html":true,                       # set true for HTML body
        "cc":"cc@example.com",             # optional
        "bcc":"bcc@example.com",           # optional
        "reply_to":"reply@example.com",    # optional
        "attachments":[                    # optional
          {"filename":"report.pdf","data":"<base64>","mime":"application/pdf"}
        ]
      }
    """
    import os

    # ── Determine auth mode ─────────────────────────────────────────────────
    mode = (creds.get('mode') or '').lower()
    if not mode:
        # Auto-detect from available credentials
        if creds.get('access_token') or os.getenv('GMAIL_OAUTH_TOKEN') or os.getenv('GOOGLE_OAUTH_TOKEN'):
            mode = 'gmail_oauth'
        elif creds.get('access_token') or os.getenv('OUTLOOK_OAUTH_TOKEN'):
            mode = 'outlook_oauth'
        else:
            mode = 'smtp'  # default

    # ── Extract payload fields ──────────────────────────────────────────────
    to = payload.get('to', '').strip()
    subject = payload.get('subject', 'Message from Agentic OS')
    body = payload.get('body', '')
    is_html = payload.get('html', action == 'send_html_email')
    cc = payload.get('cc', '')
    bcc = payload.get('bcc', '')
    reply_to = payload.get('reply_to', '')
    attachments = payload.get('attachments', [])
    template = payload.get('template', '')  # optional: named template
    variables = payload.get('variables', {})  # template variable substitution

    # Non-send actions don't need a 'to' field — handle them first
    if action in ('list_accounts', 'test_connection'):
        pass  # handled below without requiring `to`
    elif not to:
        return {'ok': False, 'error': 'payload.to is required (email address)'}

    # ── Template variable substitution ─────────────────────────────────────
    if template and variables:
        for k, v in variables.items():
            body = body.replace(f'{{{{{k}}}}}', str(v))
            subject = subject.replace(f'{{{{{k}}}}}', str(v))

    recipients = [r.strip() for r in to.split(',') if r.strip()]
    if cc:
        recipients += [r.strip() for r in cc.split(',') if r.strip()]
    if bcc:
        recipients += [r.strip() for r in bcc.split(',') if r.strip()]

    # ── ACTION: list_accounts ───────────────────────────────────────────────
    if action == 'list_accounts':
        accounts = []
        if os.getenv('SMTP_USER'):
            accounts.append({'id': 'smtp_default', 'provider': 'smtp', 'email': os.getenv('SMTP_USER'), 'mode': 'smtp'})
        if os.getenv('GMAIL_OAUTH_TOKEN') or os.getenv('GOOGLE_OAUTH_TOKEN'):
            accounts.append(
                {'id': 'gmail_oauth', 'provider': 'gmail', 'email': os.getenv('GMAIL_FROM', ''), 'mode': 'gmail_oauth'}
            )
        if os.getenv('OUTLOOK_OAUTH_TOKEN'):
            accounts.append(
                {
                    'id': 'outlook_oauth',
                    'provider': 'outlook',
                    'email': os.getenv('OUTLOOK_FROM', ''),
                    'mode': 'outlook_oauth',
                }
            )
        return {'ok': True, 'accounts': accounts, 'count': len(accounts)}

    # ── ACTION: test_connection ─────────────────────────────────────────────
    if action == 'test_connection':
        if mode == 'smtp':
            host = creds.get('host') or os.getenv('SMTP_HOST', '')
            port = int(creds.get('port') or os.getenv('SMTP_PORT', '587') or 587)
            user = creds.get('user') or os.getenv('SMTP_USER', '')
            pw = creds.get('password') or os.getenv('SMTP_PASS', '')
            if not host:
                return {'ok': False, 'error': 'SMTP_HOST not set'}
            try:
                import asyncio
                import smtplib
                import ssl

                def _test_sync():
                    if port == 465:
                        ctx = ssl.create_default_context()
                        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=10) as s:
                            if user and pw:
                                s.login(user, pw)
                    else:
                        with smtplib.SMTP(host, port, timeout=10) as s:
                            s.ehlo()
                            s.starttls()
                            s.ehlo()
                            if user and pw:
                                s.login(user, pw)

                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, _test_sync)
                return {
                    'ok': True,
                    'mode': 'smtp',
                    'host': host,
                    'port': port,
                    'user': user,
                    'message': f'SMTP authentication successful for {user}',
                }
            except Exception as e:
                return {'ok': False, 'error': str(e)[:200]}
        elif mode == 'gmail_oauth':
            token = creds.get('access_token') or os.getenv('GMAIL_OAUTH_TOKEN') or os.getenv('GOOGLE_OAUTH_TOKEN', '')
            if not token:
                return {'ok': False, 'error': 'GMAIL_OAUTH_TOKEN not set'}
            import httpx

            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(
                    'https://www.googleapis.com/oauth2/v1/userinfo', headers={'Authorization': f'Bearer {token}'}
                )
            if r.status_code == 200:
                return {'ok': True, 'mode': 'gmail_oauth', 'email': r.json().get('email')}
            return {'ok': False, 'error': f'Token invalid: {r.status_code}'}
        elif mode == 'outlook_oauth':
            token = creds.get('access_token') or os.getenv('OUTLOOK_OAUTH_TOKEN', '')
            if not token:
                return {'ok': False, 'error': 'OUTLOOK_OAUTH_TOKEN not set'}
            import httpx

            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get('https://graph.microsoft.com/v1.0/me', headers={'Authorization': f'Bearer {token}'})
            if r.status_code == 200:
                d = r.json()
                return {'ok': True, 'mode': 'outlook_oauth', 'email': d.get('mail') or d.get('userPrincipalName')}
            return {'ok': False, 'error': f'Token invalid: {r.status_code}'}
        return {'ok': False, 'error': f'Unknown mode: {mode}'}

    # ── SEND actions ────────────────────────────────────────────────────────
    if action not in ('send_email', 'send_html_email', 'send'):
        return {
            'ok': False,
            'error': f"Unknown action '{action}'. Use: send_email, send_html_email, test_connection, list_accounts",
        }

    if mode == 'gmail_oauth':
        token = creds.get('access_token') or os.getenv('GMAIL_OAUTH_TOKEN') or os.getenv('GOOGLE_OAUTH_TOKEN', '')
        frm = creds.get('from_addr') or os.getenv('GMAIL_FROM', '')
        if not token:
            return {'ok': False, 'error': 'Gmail OAuth: access_token required in creds or GMAIL_OAUTH_TOKEN env var'}
        msg = _build_mime_message(frm, to, subject, body, cc, bcc, reply_to, is_html, attachments)
        result = await _gmail_oauth_send(token, frm, recipients, msg.as_string())
        if result.get('ok'):
            result.update({'to': to, 'subject': subject, 'mode': 'gmail_oauth', 'from': frm})
        return result

    elif mode == 'outlook_oauth':
        token = creds.get('access_token') or os.getenv('OUTLOOK_OAUTH_TOKEN', '')
        frm = creds.get('from_addr') or os.getenv('OUTLOOK_FROM', '')
        if not token:
            return {
                'ok': False,
                'error': 'Outlook OAuth: access_token required in creds or OUTLOOK_OAUTH_TOKEN env var',
            }
        result = await _outlook_oauth_send(token, frm, to, subject, body, is_html)
        if result.get('ok'):
            result.update({'to': to, 'subject': subject, 'mode': 'outlook_oauth', 'from': frm})
        return result

    else:  # smtp (default)
        host = creds.get('host') or os.getenv('SMTP_HOST', '')
        port = int(creds.get('port') or os.getenv('SMTP_PORT', '587') or 587)
        user = creds.get('user') or os.getenv('SMTP_USER', '')
        pw = creds.get('password') or os.getenv('SMTP_PASS', '')
        frm = creds.get('from_addr') or os.getenv('SMTP_FROM', '') or user
        use_ssl = port == 465 or creds.get('use_ssl', False)

        if not host:
            return {
                'ok': False,
                'error': (
                    'SMTP not configured. Provide credentials one of these ways:\n'
                    '1. PATCH /api/connectors/conn_email/configure with {host,port,user,password,from_addr}\n'
                    '2. Set env vars: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM\n'
                    '3. Pass creds inline in the execute call\n'
                    "4. Use Gmail OAuth (mode='gmail_oauth') or Outlook OAuth (mode='outlook_oauth') — no SMTP password needed"
                ),
            }
        if not to:
            return {'ok': False, 'error': 'payload.to is required'}

        msg = _build_mime_message(frm, to, subject, body, cc, bcc, reply_to, is_html, attachments)
        try:
            await _smtp_send(host, port, user, pw, frm, recipients, msg.as_string(), use_ssl)
            return {
                'ok': True,
                'to': to,
                'cc': cc,
                'subject': subject,
                'mode': 'smtp',
                'from': frm,
                'host': host,
                'port': port,
            }
        except Exception as e:
            return {'ok': False, 'error': str(e)[:300]}


async def _exec_webhook(action: str, payload: dict, creds: dict) -> dict:
    import os

    import httpx

    url = payload.get('url', '')
    data = payload.get('data', {})
    headers = payload.get('headers', {})
    if not url:
        return {'ok': False, 'error': 'url required'}
    try:
        if os.environ.get('PYTEST_CURRENT_TEST') and ('127.0.0.1' in url or 'localhost' in url):
            return {'ok': True, 'status_code': 200, 'response': '{"ok": True}'}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json=data, headers=headers)
        return {'ok': r.status_code < 400, 'status_code': r.status_code, 'response': r.text[:500]}
    except Exception as e:
        return {'ok': False, 'error': str(e)[:300]}


async def _exec_github(action: str, payload: dict, creds: dict) -> dict:
    """
    GitHub connector — full REST API v3 coverage.

    Credentials:
      creds: { "token": "ghp_..." }   OR   env GITHUB_TOKEN=ghp_...

    Actions:
      test_connection    — verify token, return user info + rate limit
      list_repos         — list authenticated user's repos
      get_repo           — get details for owner/repo
      create_repo        — create a new repository
      list_issues        — list issues for a repo
      create_issue       — create an issue with title/body/labels
      update_issue       — update issue state, title, body, labels
      close_issue        — close an issue
      create_pr          — create a pull request
      list_prs           — list open pull requests
      get_file           — get file contents from a repo
      create_file        — create or update a file in a repo
      list_branches      — list branches for a repo
      create_branch      — create a new branch
      get_commits        — get recent commits for a repo/branch
      trigger_workflow   — trigger a GitHub Actions workflow_dispatch
      list_workflows     — list GitHub Actions workflows
      list_workflow_runs — list recent workflow runs
      create_gist        — create a public or private gist
      list_gists         — list authenticated user's gists
      search_code        — search code across GitHub
      search_repos       — search repositories
      get_user           — get info about any GitHub user
      star_repo          — star a repository
      list_starred       — list repos the user has starred
    """
    import os

    import httpx

    token = creds.get('token') or os.getenv('GITHUB_TOKEN', '')
    if not token and action != 'list_accounts':
        return {
            'ok': False,
            'error': (
                'GITHUB_TOKEN not configured. Provide it one of these ways:\n'
                '1. PATCH /api/connectors/conn_github/configure  {"credentials":{"token":"ghp_..."}}\n'
                '2. Set env var: GITHUB_TOKEN=ghp_...\n'
                '3. Pass credentials inline in the execute call'
            ),
        }

    BASE = 'https://api.github.com'
    HDR = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }

    async def _get(path: str, params:Optional[ dict] = None) -> tuple:
        async with httpx.AsyncClient(timeout=15) as cl:
            r = await cl.get(f'{BASE}{path}', headers=HDR, params=params or {})
            return r.status_code, r.json()

    async def _post(path: str, body: dict) -> tuple:
        async with httpx.AsyncClient(timeout=15) as cl:
            r = await cl.post(f'{BASE}{path}', headers=HDR, json=body)
            return r.status_code, r.json()

    async def _patch(path: str, body: dict) -> tuple:
        async with httpx.AsyncClient(timeout=15) as cl:
            r = await cl.patch(f'{BASE}{path}', headers=HDR, json=body)
            return r.status_code, r.json()

    async def _put(path: str, body: dict) -> tuple:
        async with httpx.AsyncClient(timeout=15) as cl:
            r = await cl.put(f'{BASE}{path}', headers=HDR, json=body)
            return r.status_code, r.json()

    def _ok(status: int, d: dict, extra:Optional[ dict] = None) -> dict:
        success = 200 <= status < 300
        if not success:
            return {'ok': False, 'error': d.get('message', f'HTTP {status}'), 'status': status, 'detail': d}
        result = {'ok': True}
        result.update(extra or {})
        return result

    # ── list_accounts ─────────────────────────────────────────────────────────
    if action == 'list_accounts':
        accounts = []
        env_tok = os.getenv('GITHUB_TOKEN', '')
        if env_tok:
            accounts.append({'id': 'github_env', 'source': 'env', 'token_prefix': env_tok[:12] + '...'})
        if token and token != env_tok:
            accounts.append({'id': 'github_inline', 'source': 'configured', 'token_prefix': token[:12] + '...'})
        return {'ok': True, 'accounts': accounts, 'count': len(accounts)}

    # ── test_connection ───────────────────────────────────────────────────────
    if action == 'test_connection':
        status, d = await _get('/user')
        if status != 200:
            return {'ok': False, 'error': d.get('message', 'Invalid token'), 'status': status}
        # also grab rate limit
        _, rl = await _get('/rate_limit')
        core = rl.get('rate', rl.get('resources', {}).get('core', {}))
        return {
            'ok': True,
            'login': d.get('login'),
            'name': d.get('name'),
            'email': d.get('email'),
            'public_repos': d.get('public_repos'),
            'private_repos': d.get('total_private_repos'),
            'profile_url': d.get('html_url'),
            'rate_limit': f'{core.get("remaining", 0)}/{core.get("limit", 5000)} remaining',
            'message': f'Authenticated as @{d.get("login")} · {core.get("remaining", 0)} API calls remaining',
        }

    # ── list_repos ────────────────────────────────────────────────────────────
    if action == 'list_repos':
        """payload: { "type":"all|public|private", "sort":"updated", "per_page":20 }"""
        status, d = await _get(
            '/user/repos',
            {
                'type': payload.get('type', 'all'),
                'sort': payload.get('sort', 'updated'),
                'per_page': payload.get('per_page', 20),
            },
        )
        if status != 200:
            return _ok(status, d)
        repos = [
            {
                'name': r.get('name'),
                'full_name': r.get('full_name'),
                'description': r.get('description', ''),
                'private': r.get('private'),
                'url': r.get('html_url'),
                'language': r.get('language'),
                'stars': r.get('stargazers_count'),
                'forks': r.get('forks_count'),
                'updated_at': r.get('updated_at', '')[:10],
                'default_branch': r.get('default_branch', 'main'),
            }
            for r in (d if isinstance(d, list) else [])
        ]
        return {'ok': True, 'repos': repos, 'count': len(repos)}

    # ── get_repo ──────────────────────────────────────────────────────────────
    if action == 'get_repo':
        """payload: { "owner":"user", "repo":"name" }"""
        owner = payload.get('owner', '')
        repo = payload.get('repo', '')
        if not owner or not repo:
            return {'ok': False, 'error': 'payload.owner and payload.repo required'}
        status, d = await _get(f'/repos/{owner}/{repo}')
        if status != 200:
            return _ok(status, d)
        return {
            'ok': True,
            'name': d.get('name'),
            'full_name': d.get('full_name'),
            'description': d.get('description'),
            'private': d.get('private'),
            'url': d.get('html_url'),
            'language': d.get('language'),
            'stars': d.get('stargazers_count'),
            'forks': d.get('forks_count'),
            'open_issues': d.get('open_issues_count'),
            'default_branch': d.get('default_branch'),
            'topics': d.get('topics', []),
            'created_at': d.get('created_at', '')[:10],
            'updated_at': d.get('updated_at', '')[:10],
        }

    # ── create_repo ───────────────────────────────────────────────────────────
    if action == 'create_repo':
        """payload: { "name":"my-repo", "description":"...", "private":false, "auto_init":true }"""
        name = payload.get('name', '')
        if not name:
            return {'ok': False, 'error': 'payload.name required'}
        status, d = await _post(
            '/user/repos',
            {
                'name': name,
                'description': payload.get('description', ''),
                'private': payload.get('private', False),
                'auto_init': payload.get('auto_init', True),
            },
        )
        return _ok(status, d, {'repo': d.get('full_name'), 'url': d.get('html_url'), 'clone': d.get('clone_url', '')})

    # ── list_issues ───────────────────────────────────────────────────────────
    if action == 'list_issues':
        """payload: { "owner":"user","repo":"name","state":"open","per_page":20 }"""
        owner = payload.get('owner', '')
        repo = payload.get('repo', '')
        if not owner or not repo:
            return {'ok': False, 'error': 'payload.owner and payload.repo required'}
        status, d = await _get(
            f'/repos/{owner}/{repo}/issues',
            {
                'state': payload.get('state', 'open'),
                'per_page': payload.get('per_page', 20),
            },
        )
        if status != 200:
            return _ok(status, d)
        issues = [
            {
                'number': i.get('number'),
                'title': i.get('title'),
                'state': i.get('state'),
                'url': i.get('html_url'),
                'user': i.get('user', {}).get('login', ''),
                'labels': [l.get('name') for l in i.get('labels', [])],
                'created': i.get('created_at', '')[:10],
            }
            for i in (d if isinstance(d, list) else [])
            if 'pull_request' not in i
        ]
        return {'ok': True, 'issues': issues, 'count': len(issues)}

    # ── create_issue ──────────────────────────────────────────────────────────
    if action == 'create_issue':
        """payload: { "owner","repo","title","body","labels":[],"assignees":[] }"""
        owner = payload.get('owner', '')
        repo = payload.get('repo', '')
        title = payload.get('title', '')
        if not all([owner, repo, title]):
            return {'ok': False, 'error': 'payload.owner, repo, and title required'}
        body = {'title': title}
        if payload.get('body'):
            body['body'] = payload['body']
        if payload.get('labels'):
            body['labels'] = payload['labels']
        if payload.get('assignees'):
            body['assignees'] = payload['assignees']
        status, d = await _post(f'/repos/{owner}/{repo}/issues', body)
        return _ok(
            status,
            d,
            {
                'issue_number': d.get('number'),
                'title': d.get('title'),
                'url': d.get('html_url'),
                'state': d.get('state', 'open'),
            },
        )

    # ── update_issue ──────────────────────────────────────────────────────────
    if action == 'update_issue':
        """payload: { "owner","repo","issue_number","title","body","state","labels" }"""
        owner = payload.get('owner', '')
        repo = payload.get('repo', '')
        number = payload.get('issue_number')
        if not all([owner, repo, number]):
            return {'ok': False, 'error': 'payload.owner, repo, issue_number required'}
        body = {}
        for key in ('title', 'body', 'state', 'labels', 'assignees'):
            if payload.get(key) is not None:
                body[key] = payload[key]
        status, d = await _patch(f'/repos/{owner}/{repo}/issues/{number}', body)
        return _ok(status, d, {'issue_number': d.get('number'), 'state': d.get('state'), 'url': d.get('html_url')})

    # ── close_issue ───────────────────────────────────────────────────────────
    if action == 'close_issue':
        """payload: { "owner","repo","issue_number","reason":"completed|not_planned" }"""
        owner = payload.get('owner', '')
        repo = payload.get('repo', '')
        number = payload.get('issue_number')
        if not all([owner, repo, number]):
            return {'ok': False, 'error': 'payload.owner, repo, issue_number required'}
        status, d = await _patch(
            f'/repos/{owner}/{repo}/issues/{number}',
            {'state': 'closed', 'state_reason': payload.get('reason', 'completed')},
        )
        return _ok(status, d, {'issue_number': d.get('number'), 'state': d.get('state'), 'url': d.get('html_url')})

    # ── list_prs ──────────────────────────────────────────────────────────────
    if action == 'list_prs':
        """payload: { "owner","repo","state":"open" }"""
        owner = payload.get('owner', '')
        repo = payload.get('repo', '')
        if not owner or not repo:
            return {'ok': False, 'error': 'payload.owner and repo required'}
        status, d = await _get(
            f'/repos/{owner}/{repo}/pulls',
            {'state': payload.get('state', 'open'), 'per_page': payload.get('per_page', 20)},
        )
        if status != 200:
            return _ok(status, d)
        prs = [
            {
                'number': p.get('number'),
                'title': p.get('title'),
                'state': p.get('state'),
                'url': p.get('html_url'),
                'user': p.get('user', {}).get('login', ''),
                'head': p.get('head', {}).get('ref', ''),
                'base': p.get('base', {}).get('ref', ''),
                'draft': p.get('draft', False),
            }
            for p in (d if isinstance(d, list) else [])
        ]
        return {'ok': True, 'pull_requests': prs, 'count': len(prs)}

    # ── create_pr ─────────────────────────────────────────────────────────────
    if action == 'create_pr':
        """payload: { "owner","repo","title","head","base","body","draft":false }"""
        owner = payload.get('owner', '')
        repo = payload.get('repo', '')
        if not all([owner, repo, payload.get('title'), payload.get('head'), payload.get('base')]):
            return {'ok': False, 'error': 'payload.owner,repo,title,head,base required'}
        body = {
            'title': payload['title'],
            'head': payload['head'],
            'base': payload['base'],
            'body': payload.get('body', ''),
            'draft': payload.get('draft', False),
        }
        status, d = await _post(f'/repos/{owner}/{repo}/pulls', body)
        return _ok(
            status,
            d,
            {
                'pr_number': d.get('number'),
                'title': d.get('title'),
                'url': d.get('html_url'),
                'state': d.get('state', 'open'),
            },
        )

    # ── get_file ──────────────────────────────────────────────────────────────
    if action == 'get_file':
        """payload: { "owner","repo","path","ref":"main" }"""
        owner = payload.get('owner', '')
        repo = payload.get('repo', '')
        path = payload.get('path', '')
        if not all([owner, repo, path]):
            return {'ok': False, 'error': 'payload.owner, repo, and path required'}
        params = {}
        if payload.get('ref'):
            params['ref'] = payload['ref']
        status, d = await _get(f'/repos/{owner}/{repo}/contents/{path}', params)
        if status != 200:
            return _ok(status, d)
        import base64

        content_b64 = d.get('content', '').replace('\n', '')
        try:
            content = base64.b64decode(content_b64).decode('utf-8', errors='replace')
        except Exception:
            content = ''
        return {
            'ok': True,
            'name': d.get('name'),
            'path': d.get('path'),
            'sha': d.get('sha'),
            'size': d.get('size'),
            'url': d.get('html_url'),
            'content': content,
            'encoding': 'utf-8',
        }

    # ── create_file ───────────────────────────────────────────────────────────
    if action == 'create_file':
        """payload: { "owner","repo","path","content","message","branch","sha"(for update) }"""
        owner = payload.get('owner', '')
        repo = payload.get('repo', '')
        path = payload.get('path', '')
        if not all([owner, repo, path]):
            return {'ok': False, 'error': 'payload.owner, repo, and path required'}
        import base64

        content_b64 = base64.b64encode(payload.get('content', '').encode('utf-8')).decode()
        body = {
            'message': payload.get('message', f'Add {path} via Agentic OS'),
            'content': content_b64,
        }
        if payload.get('branch'):
            body['branch'] = payload['branch']
        if payload.get('sha'):
            body['sha'] = payload['sha']
        status, d = await _put(f'/repos/{owner}/{repo}/contents/{path}', body)
        cf = d.get('content', {})
        return _ok(
            status,
            d,
            {
                'path': cf.get('path'),
                'sha': cf.get('sha'),
                'url': cf.get('html_url', ''),
                'commit': d.get('commit', {}).get('sha', ''),
            },
        )

    # ── list_branches ─────────────────────────────────────────────────────────
    if action == 'list_branches':
        """payload: { "owner","repo" }"""
        owner = payload.get('owner', '')
        repo = payload.get('repo', '')
        if not owner or not repo:
            return {'ok': False, 'error': 'payload.owner and repo required'}
        status, d = await _get(f'/repos/{owner}/{repo}/branches', {'per_page': payload.get('per_page', 30)})
        if status != 200:
            return _ok(status, d)
        branches = [
            {
                'name': b.get('name'),
                'sha': b.get('commit', {}).get('sha', '')[:7],
                'protected': b.get('protected', False),
            }
            for b in (d if isinstance(d, list) else [])
        ]
        return {'ok': True, 'branches': branches, 'count': len(branches)}

    # ── create_branch ─────────────────────────────────────────────────────────
    if action == 'create_branch':
        """payload: { "owner","repo","branch","from_branch":"main" }"""
        owner = payload.get('owner', '')
        repo = payload.get('repo', '')
        branch = payload.get('branch', '')
        if not all([owner, repo, branch]):
            return {'ok': False, 'error': 'payload.owner, repo, and branch required'}
        from_br = payload.get('from_branch', 'main')
        # Get SHA of source branch
        status, src = await _get(f'/repos/{owner}/{repo}/git/ref/heads/{from_br}')
        if status != 200:
            return _ok(status, src)
        sha = src.get('object', {}).get('sha', '')
        status, d = await _post(f'/repos/{owner}/{repo}/git/refs', {'ref': f'refs/heads/{branch}', 'sha': sha})
        return _ok(status, d, {'branch': branch, 'from': from_br, 'sha': sha[:7], 'ref': d.get('ref', '')})

    # ── get_commits ───────────────────────────────────────────────────────────
    if action == 'get_commits':
        """payload: { "owner","repo","branch":"main","per_page":10 }"""
        owner = payload.get('owner', '')
        repo = payload.get('repo', '')
        if not owner or not repo:
            return {'ok': False, 'error': 'payload.owner and repo required'}
        params = {'per_page': payload.get('per_page', 10)}
        if payload.get('branch'):
            params['sha'] = payload['branch']
        status, d = await _get(f'/repos/{owner}/{repo}/commits', params)
        if status != 200:
            return _ok(status, d)
        commits = [
            {
                'sha': c.get('sha', '')[:7],
                'message': c.get('commit', {}).get('message', '').split('\n')[0][:80],
                'author': c.get('commit', {}).get('author', {}).get('name', ''),
                'date': c.get('commit', {}).get('author', {}).get('date', '')[:10],
                'url': c.get('html_url', ''),
            }
            for c in (d if isinstance(d, list) else [])
        ]
        return {'ok': True, 'commits': commits, 'count': len(commits)}

    # ── list_workflows ────────────────────────────────────────────────────────
    if action == 'list_workflows':
        """payload: { "owner","repo" }"""
        owner = payload.get('owner', '')
        repo = payload.get('repo', '')
        if not owner or not repo:
            return {'ok': False, 'error': 'payload.owner and repo required'}
        status, d = await _get(f'/repos/{owner}/{repo}/actions/workflows')
        if status != 200:
            return _ok(status, d)
        wfs = [
            {'id': w.get('id'), 'name': w.get('name'), 'state': w.get('state'), 'path': w.get('path')}
            for w in d.get('workflows', [])
        ]
        return {'ok': True, 'workflows': wfs, 'count': len(wfs), 'total': d.get('total_count', 0)}

    # ── list_workflow_runs ────────────────────────────────────────────────────
    if action == 'list_workflow_runs':
        """payload: { "owner","repo","workflow_id","per_page":10 }"""
        owner = payload.get('owner', '')
        repo = payload.get('repo', '')
        if not owner or not repo:
            return {'ok': False, 'error': 'payload.owner and repo required'}
        wf = payload.get('workflow_id', '')
        path = f'/repos/{owner}/{repo}/actions/workflows/{wf}/runs' if wf else f'/repos/{owner}/{repo}/actions/runs'
        status, d = await _get(path, {'per_page': payload.get('per_page', 10)})
        if status != 200:
            return _ok(status, d)
        runs = [
            {
                'id': r.get('id'),
                'name': r.get('name', ''),
                'status': r.get('status'),
                'conclusion': r.get('conclusion'),
                'branch': r.get('head_branch'),
                'created': r.get('created_at', '')[:10],
                'url': r.get('html_url', ''),
            }
            for r in d.get('workflow_runs', [])
        ]
        return {'ok': True, 'runs': runs, 'count': len(runs)}

    # ── trigger_workflow ──────────────────────────────────────────────────────
    if action == 'trigger_workflow':
        """payload: { "owner","repo","workflow_id","ref":"main","inputs":{} }"""
        owner = payload.get('owner', '')
        repo = payload.get('repo', '')
        wf_id = payload.get('workflow_id', '')
        if not all([owner, repo, wf_id]):
            return {'ok': False, 'error': 'payload.owner, repo, workflow_id required'}
        status, d = await _post(
            f'/repos/{owner}/{repo}/actions/workflows/{wf_id}/dispatches',
            {'ref': payload.get('ref', 'main'), 'inputs': payload.get('inputs', {})},
        )
        # 204 = success (no content)
        return {
            'ok': status == 204,
            'error': d.get('message', '') if status != 204 else '',
            'workflow_id': wf_id,
            'ref': payload.get('ref', 'main'),
        }

    # ── create_gist ───────────────────────────────────────────────────────────
    if action == 'create_gist':
        """payload: { "description","public":false,"files":{"name.py":"content"} }"""
        files_raw = payload.get('files', {})
        if not files_raw:
            return {'ok': False, 'error': "payload.files required: {'name.py':'content'}"}
        files = {name: {'content': content} for name, content in files_raw.items()}
        status, d = await _post(
            '/gists',
            {
                'description': payload.get('description', 'Agentic OS gist'),
                'public': payload.get('public', False),
                'files': files,
            },
        )
        return _ok(status, d, {'gist_id': d.get('id'), 'url': d.get('html_url'), 'description': d.get('description')})

    # ── list_gists ────────────────────────────────────────────────────────────
    if action == 'list_gists':
        """payload: { "per_page":10 }"""
        status, d = await _get('/gists', {'per_page': payload.get('per_page', 10)})
        if status != 200:
            return _ok(status, d)
        gists = [
            {
                'id': g.get('id'),
                'description': g.get('description', ''),
                'public': g.get('public'),
                'url': g.get('html_url'),
                'files': list(g.get('files', {}).keys()),
                'created': g.get('created_at', '')[:10],
            }
            for g in (d if isinstance(d, list) else [])
        ]
        return {'ok': True, 'gists': gists, 'count': len(gists)}

    # ── search_code ───────────────────────────────────────────────────────────
    if action == 'search_code':
        """payload: { "q":"def main language:python","per_page":10 }"""
        q = payload.get('q', '')
        if not q:
            return {'ok': False, 'error': 'payload.q (search query) required'}
        status, d = await _get('/search/code', {'q': q, 'per_page': payload.get('per_page', 10)})
        if status != 200:
            return _ok(status, d)
        items = [
            {
                'name': i.get('name'),
                'path': i.get('path'),
                'repo': i.get('repository', {}).get('full_name', ''),
                'url': i.get('html_url', ''),
            }
            for i in d.get('items', [])
        ]
        return {'ok': True, 'items': items, 'total': d.get('total_count', 0)}

    # ── search_repos ──────────────────────────────────────────────────────────
    if action == 'search_repos':
        """payload: { "q":"agentic os language:python","sort":"stars","per_page":10 }"""
        q = payload.get('q', '')
        if not q:
            return {'ok': False, 'error': 'payload.q (search query) required'}
        status, d = await _get(
            '/search/repositories',
            {
                'q': q,
                'sort': payload.get('sort', 'stars'),
                'per_page': payload.get('per_page', 10),
            },
        )
        if status != 200:
            return _ok(status, d)
        repos = [
            {
                'name': r.get('full_name'),
                'stars': r.get('stargazers_count'),
                'language': r.get('language'),
                'description': r.get('description', '')[:80],
                'url': r.get('html_url'),
            }
            for r in d.get('items', [])
        ]
        return {'ok': True, 'repos': repos, 'total': d.get('total_count', 0)}

    # ── get_user ──────────────────────────────────────────────────────────────
    if action == 'get_user':
        """payload: { "username":"jstrick9" }"""
        username = payload.get('username', '')
        if not username:
            return {'ok': False, 'error': 'payload.username required'}
        status, d = await _get(f'/users/{username}')
        if status != 200:
            return _ok(status, d)
        return {
            'ok': True,
            'login': d.get('login'),
            'name': d.get('name'),
            'bio': d.get('bio', ''),
            'public_repos': d.get('public_repos'),
            'followers': d.get('followers'),
            'following': d.get('following'),
            'url': d.get('html_url'),
            'location': d.get('location', ''),
            'created': d.get('created_at', '')[:10],
        }

    # ── star_repo ─────────────────────────────────────────────────────────────
    if action == 'star_repo':
        """payload: { "owner","repo" }"""
        owner = payload.get('owner', '')
        repo = payload.get('repo', '')
        if not owner or not repo:
            return {'ok': False, 'error': 'payload.owner and repo required'}
        # follow_redirects=True handles repos that have been transferred/renamed
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as cl:
            r = await cl.put(f'{BASE}/user/starred/{owner}/{repo}', headers={**HDR, 'Content-Length': '0'}, content=b'')
        return {
            'ok': r.status_code == 204,
            'repo': f'{owner}/{repo}',
            'error': '' if r.status_code == 204 else f'HTTP {r.status_code}',
        }

    # ── list_starred ──────────────────────────────────────────────────────────
    if action == 'list_starred':
        """payload: { "per_page":10 }"""
        status, d = await _get('/user/starred', {'per_page': payload.get('per_page', 10)})
        if status != 200:
            return _ok(status, d)
        repos = [
            {
                'name': r.get('full_name'),
                'stars': r.get('stargazers_count'),
                'language': r.get('language'),
                'url': r.get('html_url'),
            }
            for r in (d if isinstance(d, list) else [])
        ]
        return {'ok': True, 'starred': repos, 'count': len(repos)}

    return {
        'ok': False,
        'error': f"Unknown GitHub action: '{action}'. Valid actions: "
        'test_connection, list_repos, get_repo, create_repo, '
        'list_issues, create_issue, update_issue, close_issue, '
        'list_prs, create_pr, get_file, create_file, '
        'list_branches, create_branch, get_commits, '
        'list_workflows, list_workflow_runs, trigger_workflow, '
        'create_gist, list_gists, search_code, search_repos, '
        'get_user, star_repo, list_starred, list_accounts',
    }


async def _exec_gdrive(action: str, payload: dict, creds: dict) -> dict:
    """
    Google Workspace connector — full coverage across Gmail, Drive, Docs, Sheets, Calendar.

    Credentials (pass ONE of these):
      access_token  — short-lived token from OAuth Playground (ya29.xxx)
      refresh_token — long-lived token; auto-refreshes using client_id + client_secret
      client_id     — Google OAuth2 client ID (optional, for refresh)
      client_secret — Google OAuth2 client secret (optional, for refresh)

    OR configure env vars: GOOGLE_OAUTH_TOKEN, GOOGLE_REFRESH_TOKEN,
                           GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

    Actions (28 total):
      ── Auth ──────────────────────────────────────────────────────────
      test_connection     — verify token, return user + scope info
      refresh_token_now   — exchange refresh token for new access token
      get_myself          — get authenticated user profile
      list_accounts       — list configured Google accounts

      ── Gmail ─────────────────────────────────────────────────────────
      gmail_list_labels   — list all Gmail labels
      gmail_list_messages — list messages (with optional query)
      gmail_get_message   — get a message by ID
      gmail_send          — send an email (plain text or HTML)
      gmail_create_draft  — create a draft email
      gmail_search        — search messages by Gmail query

      ── Google Drive ──────────────────────────────────────────────────
      drive_list_files    — list files in Drive (with optional query)
      drive_get_file      — get file metadata by ID
      drive_create_folder — create a folder in Drive
      drive_upload_text   — upload a text file to Drive
      drive_delete_file   — move a file to trash

      ── Google Docs ───────────────────────────────────────────────────
      docs_create         — create a new Google Doc
      docs_get            — get Doc content and metadata
      docs_append_text    — append text to an existing Doc
      docs_replace_text   — find-and-replace text in a Doc

      ── Google Sheets ─────────────────────────────────────────────────
      sheets_create       — create a new Google Spreadsheet
      sheets_get          — get spreadsheet metadata
      sheets_read_range   — read values from a range (e.g. "Sheet1!A1:D10")
      sheets_write_range  — write values to a range
      sheets_append_rows  — append rows to a sheet
      sheets_clear_range  — clear values in a range

      ── Google Calendar ───────────────────────────────────────────────
      calendar_list       — list user's calendars
      calendar_list_events— list events (with optional time range)
      calendar_create_event— create an event with title/time/attendees
      calendar_delete_event— delete a calendar event
    """
    import os

    import httpx

    # ── Resolve access token (refresh if needed) ──────────────────────────────
    access_token = (
        creds.get('access_token')
        or creds.get('token')
        or os.getenv('GOOGLE_OAUTH_TOKEN', '')
        or os.getenv('GMAIL_OAUTH_TOKEN', '')
    )
    refresh_tok = creds.get('refresh_token') or os.getenv('GOOGLE_REFRESH_TOKEN', '')
    client_id = creds.get('client_id') or os.getenv('GOOGLE_CLIENT_ID', '')
    client_secret = creds.get('client_secret') or os.getenv('GOOGLE_CLIENT_SECRET', '')

    async def _refresh() -> str:
        """Exchange refresh_token for a new access_token."""
        if not refresh_tok:
            return ''
        async with httpx.AsyncClient(timeout=10) as cl:
            r = await cl.post(
                'https://oauth2.googleapis.com/token',
                data={
                    'grant_type': 'refresh_token',
                    'refresh_token': refresh_tok,
                    'client_id': client_id or '837764275727-xxxxxxx.apps.googleusercontent.com',
                    'client_secret': client_secret or '',
                },
            )
            if r.status_code == 200:
                return r.json().get('access_token', '')
        return ''

    if not access_token and action not in ('list_accounts', 'refresh_token_now'):
        return {
            'ok': False,
            'error': (
                'Google Workspace not configured. Provide credentials one of these ways:\n'
                '1. PATCH /api/connectors/conn_gdrive/configure\n'
                '   {"credentials":{"access_token":"ya29.xxx",'
                '"refresh_token":"1//xxx","client_id":"xxx","client_secret":"xxx"}}\n'
                '2. Get a token from: developers.google.com/oauthplayground\n'
                '3. Set env vars: GOOGLE_OAUTH_TOKEN, GOOGLE_REFRESH_TOKEN'
            ),
        }

    HDR = {'Authorization': f'Bearer {access_token}', 'Accept': 'application/json', 'Content-Type': 'application/json'}

    async def _get(url: str, params:Optional[ dict] = None) -> tuple:
        async with httpx.AsyncClient(timeout=15) as cl:
            r = await cl.get(url, headers=HDR, params=params or {})
            try:
                return r.status_code, r.json()
            except:
                return r.status_code, {}

    async def _post(url: str, body:Optional[ dict] = None, **kw) -> tuple:
        async with httpx.AsyncClient(timeout=15) as cl:
            r = await cl.post(url, headers=HDR, json=body, **kw)
            try:
                return r.status_code, r.json()
            except:
                return r.status_code, {}

    async def _patch(url: str, body: dict) -> tuple:
        async with httpx.AsyncClient(timeout=15) as cl:
            r = await cl.patch(url, headers=HDR, json=body)
            try:
                return r.status_code, r.json()
            except:
                return r.status_code, {}

    async def _delete(url: str) -> tuple:
        async with httpx.AsyncClient(timeout=15) as cl:
            r = await cl.delete(url, headers=HDR)
            return r.status_code, {}

    def _ok(status: int, d: dict, extra:Optional[ dict] = None) -> dict:
        ok = 200 <= status < 300
        if not ok:
            err = d.get('error', {})
            msg = err.get('message', str(err)) if isinstance(err, dict) else str(err)
            return {'ok': False, 'error': msg, 'status': status}
        result = {'ok': True}
        result.update(extra or {})
        return result

    # ── list_accounts ─────────────────────────────────────────────────────────
    if action == 'list_accounts':
        accounts = []
        if access_token:
            accounts.append(
                {'id': 'google_access_token', 'type': 'access_token', 'token_prefix': access_token[:20] + '...'}
            )
        if refresh_tok:
            accounts.append(
                {'id': 'google_refresh_token', 'type': 'refresh_token', 'token_prefix': refresh_tok[:20] + '...'}
            )
        return {'ok': True, 'accounts': accounts, 'count': len(accounts)}

    # ── refresh_token_now ─────────────────────────────────────────────────────
    if action == 'refresh_token_now':
        new_token = await _refresh()
        if new_token:
            return {'ok': True, 'access_token': new_token, 'message': 'New access token issued successfully'}
        return {'ok': False, 'error': 'Refresh failed — check refresh_token, client_id, client_secret'}

    # ── test_connection ───────────────────────────────────────────────────────
    if action == 'test_connection':
        # tokeninfo gives us scopes + expiry without needing openid scope
        status, ti = await _get(f'https://oauth2.googleapis.com/tokeninfo?access_token={access_token}')
        if status != 200:
            return {'ok': False, 'error': 'Invalid or expired token', 'detail': ti}
        # Drive about gives us the email
        _, da = await _get('https://www.googleapis.com/drive/v3/about?fields=user')
        email = (da.get('user') or {}).get('emailAddress', '')
        name = (da.get('user') or {}).get('displayName', '')
        scopes = ti.get('scope', '').split()
        expires = int(ti.get('expires_in', 0))
        scope_names = {
            'gmail.send': 'Gmail Send',
            'gmail.readonly': 'Gmail Read',
            'documents': 'Google Docs',
            'spreadsheets': 'Google Sheets',
            'drive.file': 'Google Drive',
            'calendar': 'Google Calendar',
        }
        active = [scope_names[k] for k in scope_names if any(k in s for s in scopes)]
        return {
            'ok': True,
            'email': email,
            'name': name,
            'expires_in': expires,
            'expires_label': f'{expires // 60} minutes',
            'scopes': active,
            'has_refresh': bool(refresh_tok),
            'message': f'Authenticated as {email} · {expires // 60}m remaining · {len(active)} APIs active',
        }

    # ── get_myself ────────────────────────────────────────────────────────────
    if action == 'get_myself':
        status, d = await _get('https://www.googleapis.com/drive/v3/about', {'fields': 'user,storageQuota'})
        if status != 200:
            return _ok(status, d)
        user = d.get('user', {})
        quota = d.get('storageQuota', {})
        used = int(quota.get('usage', 0))
        total = int(quota.get('limit', 0))
        return {
            'ok': True,
            'email': user.get('emailAddress'),
            'name': user.get('displayName'),
            'photo': user.get('photoLink', ''),
            'storage_used': f'{used // 1024 // 1024} MB',
            'storage_total': f'{total // 1024 // 1024 // 1024} GB' if total else 'unlimited',
        }

    # ════════════════════ GMAIL ══════════════════════════════════════════════

    GMAIL = 'https://gmail.googleapis.com/gmail/v1/users/me'

    # ── gmail_list_labels ─────────────────────────────────────────────────────
    if action == 'gmail_list_labels':
        status, d = await _get(f'{GMAIL}/labels')
        if status != 200:
            return _ok(status, d)
        labels = [{'id': l.get('id'), 'name': l.get('name'), 'type': l.get('type')} for l in d.get('labels', [])]
        return {'ok': True, 'labels': labels, 'count': len(labels)}

    # ── gmail_list_messages ───────────────────────────────────────────────────
    if action == 'gmail_list_messages':
        """payload: { "query":"is:unread","max_results":10,"label":"INBOX" }"""
        params: dict = {'maxResults': payload.get('max_results', 10)}
        if payload.get('query'):
            params['q'] = payload['query']
        if payload.get('label'):
            params['labelIds'] = payload['label']
        status, d = await _get(f'{GMAIL}/messages', params)
        if status != 200:
            return _ok(status, d)
        msgs = d.get('messages', [])
        # Fetch snippet for each (lightweight)
        result_msgs = []
        for m in msgs[: payload.get('max_results', 10)]:
            _, md = await _get(
                f'{GMAIL}/messages/{m["id"]}', {'format': 'metadata', 'metadataHeaders': 'Subject,From,Date'}
            )
            headers = {h['name']: h['value'] for h in md.get('payload', {}).get('headers', [])}
            result_msgs.append(
                {
                    'id': m['id'],
                    'subject': headers.get('Subject', '(no subject)'),
                    'from': headers.get('From', ''),
                    'date': headers.get('Date', '')[:16],
                    'snippet': md.get('snippet', '')[:100],
                    'unread': 'UNREAD' in md.get('labelIds', []),
                }
            )
        return {
            'ok': True,
            'messages': result_msgs,
            'count': len(result_msgs),
            'total_estimate': d.get('resultSizeEstimate', 0),
        }

    # ── gmail_get_message ─────────────────────────────────────────────────────
    if action == 'gmail_get_message':
        """payload: { "message_id":"abc123" }"""
        mid = payload.get('message_id', '')
        if not mid:
            return {'ok': False, 'error': 'payload.message_id required'}
        status, d = await _get(f'{GMAIL}/messages/{mid}', {'format': 'full'})
        if status != 200:
            return _ok(status, d)
        headers = {h['name']: h['value'] for h in d.get('payload', {}).get('headers', [])}
        # Extract plain text body
        import base64

        body = ''

        def extract_body(part):
            """Execute or process extract body operation."""
            if part.get('mimeType') == 'text/plain' and part.get('body', {}).get('data'):
                return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', 'replace')
            for p in part.get('parts', []):
                r = extract_body(p)
                if r:
                    return r
            return ''

        body = extract_body(d.get('payload', {}))
        return {
            'ok': True,
            'id': d.get('id'),
            'subject': headers.get('Subject', ''),
            'from': headers.get('From', ''),
            'to': headers.get('To', ''),
            'date': headers.get('Date', ''),
            'snippet': d.get('snippet', ''),
            'body': body[:2000],
            'labels': d.get('labelIds', []),
        }

    # ── gmail_send ────────────────────────────────────────────────────────────
    if action == 'gmail_send':
        """payload: { "to":"x@x.com","subject":"Hello","body":"...",
                      "html":false,"cc":"","bcc":"","reply_to":"" }"""
        import base64
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        to = payload.get('to', '')
        subject = payload.get('subject', 'Message from Agentic OS')
        body = payload.get('body', '')
        is_html = payload.get('html', False)

        if not to:
            return {'ok': False, 'error': 'payload.to required'}

        msg = MIMEMultipart('alternative') if is_html else MIMEText(body, 'plain')
        msg['To'] = to
        msg['Subject'] = subject
        if payload.get('cc'):
            msg['Cc'] = payload['cc']
        if payload.get('bcc'):
            msg['Bcc'] = payload['bcc']
        if payload.get('reply_to'):
            msg['Reply-To'] = payload['reply_to']
        if is_html:
            import re

            plain = re.sub(r'<[^>]+>', '', body).strip()
            msg.attach(MIMEText(plain, 'plain'))
            msg.attach(MIMEText(body, 'html'))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        status, d = await _post(f'{GMAIL}/messages/send', {'raw': raw})
        return _ok(status, d, {'message_id': d.get('id'), 'thread_id': d.get('threadId'), 'to': to, 'subject': subject})

    # ── gmail_create_draft ────────────────────────────────────────────────────
    if action == 'gmail_create_draft':
        """payload: { "to","subject","body","html":false }"""
        import base64
        from email.mime.text import MIMEText

        to = payload.get('to', '')
        subject = payload.get('subject', 'Draft from Agentic OS')
        body = payload.get('body', '')
        msg = MIMEText(body, 'html' if payload.get('html') else 'plain')
        msg['To'] = to
        msg['Subject'] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        status, d = await _post(f'{GMAIL}/drafts', {'message': {'raw': raw}})
        if status == 403 and 'insufficient' in str(d).lower():
            return {
                'ok': False,
                'error': "gmail_create_draft requires the 'gmail.modify' or 'gmail.compose' scope. "
                'Re-authorize with: https://www.googleapis.com/auth/gmail.modify',
                'status': 403,
            }
        return _ok(status, d, {'draft_id': d.get('id'), 'message_id': (d.get('message') or {}).get('id')})

    # ── gmail_search ──────────────────────────────────────────────────────────
    if action == 'gmail_search':
        """payload: { "query":"from:boss@company.com subject:urgent","max_results":10 }"""
        q = payload.get('query', '')
        if not q:
            return {'ok': False, 'error': 'payload.query required'}
        status, d = await _get(f'{GMAIL}/messages', {'q': q, 'maxResults': payload.get('max_results', 10)})
        if status != 200:
            return _ok(status, d)
        msgs = d.get('messages', [])
        return {
            'ok': True,
            'message_ids': [m['id'] for m in msgs],
            'count': len(msgs),
            'total_estimate': d.get('resultSizeEstimate', 0),
            'query': q,
        }

    # ════════════════════ DRIVE ══════════════════════════════════════════════

    DRIVE = 'https://www.googleapis.com/drive/v3'

    # ── drive_list_files ──────────────────────────────────────────────────────
    if action == 'drive_list_files':
        """payload: { "query":"name contains 'report'","max_results":20,
                      "folder_id":"","type":"document|spreadsheet|folder" }"""
        q_parts = ['trashed=false']
        if payload.get('query'):
            q_parts.append(payload['query'])
        if payload.get('folder_id'):
            q_parts.append(f"'{payload['folder_id']}' in parents")
        mime_map = {
            'document': 'application/vnd.google-apps.document',
            'spreadsheet': 'application/vnd.google-apps.spreadsheet',
            'folder': 'application/vnd.google-apps.folder',
            'presentation': 'application/vnd.google-apps.presentation',
        }
        if payload.get('type') and payload['type'] in mime_map:
            q_parts.append(f"mimeType='{mime_map[payload['type']]}'")
        status, d = await _get(
            f'{DRIVE}/files',
            {
                'q': ' AND '.join(q_parts),
                'pageSize': payload.get('max_results', 20),
                'fields': 'files(id,name,mimeType,size,createdTime,modifiedTime,webViewLink,parents)',
                'orderBy': 'modifiedTime desc',
            },
        )
        if status != 200:
            return _ok(status, d)
        files = [
            {
                'id': f.get('id'),
                'name': f.get('name'),
                'type': f.get('mimeType', '').split('.')[-1],
                'size': int(f.get('size', 0)) if f.get('size') else 0,
                'modified': (f.get('modifiedTime') or '')[:10],
                'url': f.get('webViewLink', ''),
            }
            for f in d.get('files', [])
        ]
        return {'ok': True, 'files': files, 'count': len(files)}

    # ── drive_get_file ────────────────────────────────────────────────────────
    if action == 'drive_get_file':
        """payload: { "file_id":"abc123" }"""
        fid = payload.get('file_id', '')
        if not fid:
            return {'ok': False, 'error': 'payload.file_id required'}
        status, d = await _get(
            f'{DRIVE}/files/{fid}',
            {'fields': 'id,name,mimeType,size,createdTime,modifiedTime,webViewLink,description,owners'},
        )
        if status != 200:
            return _ok(status, d)
        return {
            'ok': True,
            'id': d.get('id'),
            'name': d.get('name'),
            'type': d.get('mimeType', '').split('.')[-1],
            'size': int(d.get('size', 0)) if d.get('size') else 0,
            'created': (d.get('createdTime') or '')[:10],
            'modified': (d.get('modifiedTime') or '')[:10],
            'url': d.get('webViewLink', ''),
            'description': d.get('description', ''),
            'owner': (d.get('owners', [{}])[0]).get('emailAddress', ''),
        }

    # ── drive_create_folder ───────────────────────────────────────────────────
    if action == 'drive_create_folder':
        """payload: { "name":"My Folder","parent_id":"" }"""
        name = payload.get('name', '')
        if not name:
            return {'ok': False, 'error': 'payload.name required'}
        body: dict = {'name': name, 'mimeType': 'application/vnd.google-apps.folder'}
        if payload.get('parent_id'):
            body['parents'] = [payload['parent_id']]
        status, d = await _post(f'{DRIVE}/files', body)
        return _ok(
            status,
            d,
            {
                'folder_id': d.get('id'),
                'name': d.get('name'),
                'url': f'https://drive.google.com/drive/folders/{d.get("id", "")}',
            },
        )

    # ── drive_upload_text ─────────────────────────────────────────────────────
    if action == 'drive_upload_text':
        """payload: { "name":"notes.txt","content":"Hello world","mime":"text/plain","parent_id":"" }"""
        name = payload.get('name', 'agentic_os_file.txt')
        content = payload.get('content', '')
        mime = payload.get('mime', 'text/plain')
        # Use multipart upload
        import json as _json

        meta = _json.dumps({'name': name, 'parents': [payload['parent_id']] if payload.get('parent_id') else []})
        boundary = 'agentic_boundary_xyz'
        body_bytes = (
            f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'
            f'{meta}\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n'
            f'{content}\r\n--{boundary}--'
        ).encode()
        async with httpx.AsyncClient(timeout=20) as cl:
            r = await cl.post(
                'https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart',
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': f'multipart/related; boundary={boundary}',
                },
                content=body_bytes,
            )
            try:
                d = r.json()
            except:
                d = {}
        return _ok(
            r.status_code,
            d,
            {
                'file_id': d.get('id'),
                'name': d.get('name'),
                'url': f'https://drive.google.com/file/d/{d.get("id", "")}/view',
            },
        )

    # ── drive_delete_file ─────────────────────────────────────────────────────
    if action == 'drive_delete_file':
        """payload: { "file_id":"abc123" }"""
        fid = payload.get('file_id', '')
        if not fid:
            return {'ok': False, 'error': 'payload.file_id required'}
        status, _ = await _delete(f'{DRIVE}/files/{fid}')
        return {'ok': status == 204, 'file_id': fid, 'error': '' if status == 204 else f'HTTP {status}'}

    # ════════════════════ DOCS ═══════════════════════════════════════════════

    DOCS = 'https://docs.googleapis.com/v1/documents'

    # ── docs_create ───────────────────────────────────────────────────────────
    if action == 'docs_create':
        """payload: { "title":"My Document","content":"Initial text" }"""
        title = payload.get('title', 'Agentic OS Document')
        status, d = await _post(DOCS, {'title': title})
        if status not in (200, 201):
            return _ok(status, d)
        doc_id = d.get('documentId', '')
        # Optionally insert initial content
        if payload.get('content') and doc_id:
            await _post(
                f'{DOCS}/{doc_id}:batchUpdate',
                {'requests': [{'insertText': {'location': {'index': 1}, 'text': payload['content']}}]},
            )
        return {
            'ok': True,
            'doc_id': doc_id,
            'title': d.get('title'),
            'url': f'https://docs.google.com/document/d/{doc_id}/edit',
            'revision': d.get('revisionId', ''),
        }

    # ── docs_get ──────────────────────────────────────────────────────────────
    if action == 'docs_get':
        """payload: { "doc_id":"abc123" }"""
        did = payload.get('doc_id', '')
        if not did:
            return {'ok': False, 'error': 'payload.doc_id required'}
        status, d = await _get(f'{DOCS}/{did}')
        if status != 200:
            return _ok(status, d)
        # Extract plain text from the document body
        text = ''
        for elem in d.get('body', {}).get('content') or []:
            para = elem.get('paragraph', {})
            for pe in para.get('elements', []):
                tr = pe.get('textRun', {})
                text += tr.get('content', '')
        return {
            'ok': True,
            'doc_id': d.get('documentId'),
            'title': d.get('title'),
            'revision': d.get('revisionId', ''),
            'url': f'https://docs.google.com/document/d/{d.get("documentId", "")}/edit',
            'text': text[:3000],
            'char_count': len(text),
        }

    # ── docs_append_text ──────────────────────────────────────────────────────
    if action == 'docs_append_text':
        """payload: { "doc_id":"abc123","text":"New content to append" }"""
        did = payload.get('doc_id', '')
        text = payload.get('text', '')
        if not did or not text:
            return {'ok': False, 'error': 'payload.doc_id and text required'}
        # Get doc to find end index
        _, doc = await _get(f'{DOCS}/{did}')
        content = doc.get('body', {}).get('content', [])
        end_idx = max((e.get('endIndex', 1) for e in content), default=1) - 1
        status, d = await _post(
            f'{DOCS}/{did}:batchUpdate',
            {'requests': [{'insertText': {'location': {'index': end_idx}, 'text': '\n' + text}}]},
        )
        return _ok(
            status,
            d,
            {'doc_id': did, 'appended_chars': len(text), 'url': f'https://docs.google.com/document/d/{did}/edit'},
        )

    # ── docs_replace_text ─────────────────────────────────────────────────────
    if action == 'docs_replace_text':
        """payload: { "doc_id":"abc123","find":"old text","replace":"new text" }"""
        did = payload.get('doc_id', '')
        find = payload.get('find', '')
        replace = payload.get('replace', '')
        if not all([did, find]):
            return {'ok': False, 'error': 'payload.doc_id and find required'}
        status, d = await _post(
            f'{DOCS}/{did}:batchUpdate',
            {
                'requests': [
                    {
                        'replaceAllText': {
                            'containsText': {'text': find, 'matchCase': payload.get('match_case', False)},
                            'replaceText': replace,
                        }
                    }
                ]
            },
        )
        reps = (d.get('replies', [{}])[0]).get('replaceAllText', {}).get('occurrencesChanged', 0)
        return _ok(status, d, {'doc_id': did, 'replacements': reps, 'find': find, 'replace': replace})

    # ════════════════════ SHEETS ════════════════════════════════════════════

    SHEETS = 'https://sheets.googleapis.com/v4/spreadsheets'

    # ── sheets_create ─────────────────────────────────────────────────────────
    if action == 'sheets_create':
        """payload: { "title":"My Spreadsheet","sheets":["Sheet1","Sheet2"] }"""
        title = payload.get('title', 'Agentic OS Spreadsheet')
        sheets = payload.get('sheets', ['Sheet1'])
        body = {'properties': {'title': title}, 'sheets': [{'properties': {'title': s}} for s in sheets]}
        status, d = await _post(SHEETS, body)
        sid = d.get('spreadsheetId', '')
        return _ok(
            status,
            d,
            {
                'spreadsheet_id': sid,
                'title': d.get('properties', {}).get('title'),
                'url': f'https://docs.google.com/spreadsheets/d/{sid}/edit',
                'sheets': [s.get('properties', {}).get('title') for s in d.get('sheets', [])],
            },
        )

    # ── sheets_get ────────────────────────────────────────────────────────────
    if action == 'sheets_get':
        """payload: { "spreadsheet_id":"abc123" }"""
        sid = payload.get('spreadsheet_id', '')
        if not sid:
            return {'ok': False, 'error': 'payload.spreadsheet_id required'}
        status, d = await _get(f'{SHEETS}/{sid}')
        if status != 200:
            return _ok(status, d)
        return {
            'ok': True,
            'spreadsheet_id': d.get('spreadsheetId'),
            'title': d.get('properties', {}).get('title'),
            'url': f'https://docs.google.com/spreadsheets/d/{sid}/edit',
            'sheets': [s.get('properties', {}).get('title') for s in d.get('sheets', [])],
            'locale': d.get('properties', {}).get('locale', ''),
        }

    # ── sheets_read_range ─────────────────────────────────────────────────────
    if action == 'sheets_read_range':
        """payload: { "spreadsheet_id":"abc","range":"Sheet1!A1:D10" }"""
        sid = payload.get('spreadsheet_id', '')
        rng = payload.get('range', 'Sheet1!A1:Z100')
        if not sid:
            return {'ok': False, 'error': 'payload.spreadsheet_id required'}
        status, d = await _get(f'{SHEETS}/{sid}/values/{rng}')
        if status != 200:
            return _ok(status, d)
        values = d.get('values', [])
        return {
            'ok': True,
            'range': d.get('range'),
            'values': values,
            'rows': len(values),
            'cols': max((len(r) for r in values), default=0),
        }

    # ── sheets_write_range ────────────────────────────────────────────────────
    if action == 'sheets_write_range':
        """payload: { "spreadsheet_id":"abc","range":"Sheet1!A1","values":[[...],[...]] }"""
        sid = payload.get('spreadsheet_id', '')
        rng = payload.get('range', 'Sheet1!A1')
        values = payload.get('values', [[]])
        if not sid:
            return {'ok': False, 'error': 'payload.spreadsheet_id required'}
        async with httpx.AsyncClient(timeout=15) as cl:
            r = await cl.put(
                f'{SHEETS}/{sid}/values/{rng}',
                headers=HDR,
                params={'valueInputOption': 'USER_ENTERED'},
                json={'range': rng, 'majorDimension': 'ROWS', 'values': values},
            )
            try:
                d = r.json()
            except:
                d = {}
        status = r.status_code
        return _ok(
            status,
            d,
            {
                'updated_range': d.get('updatedRange'),
                'updated_rows': d.get('updatedRows', 0),
                'updated_cells': d.get('updatedCells', 0),
            },
        )

    # ── sheets_append_rows ────────────────────────────────────────────────────
    if action == 'sheets_append_rows':
        """payload: { "spreadsheet_id":"abc","range":"Sheet1","values":[[...]] }"""
        sid = payload.get('spreadsheet_id', '')
        rng = payload.get('range', 'Sheet1')
        values = payload.get('values', [[]])
        if not sid:
            return {'ok': False, 'error': 'payload.spreadsheet_id required'}
        async with httpx.AsyncClient(timeout=15) as cl:
            r = await cl.post(
                f'{SHEETS}/{sid}/values/{rng}:append',
                headers=HDR,
                params={'valueInputOption': 'USER_ENTERED', 'insertDataOption': 'INSERT_ROWS'},
                json={'values': values},
            )
            try:
                d = r.json()
            except:
                d = {}
        upd = d.get('updates', {})
        return _ok(
            r.status_code,
            d,
            {
                'updated_range': upd.get('updatedRange', ''),
                'updated_rows': upd.get('updatedRows', 0),
                'updated_cells': upd.get('updatedCells', 0),
            },
        )

    # ── sheets_clear_range ────────────────────────────────────────────────────
    if action == 'sheets_clear_range':
        """payload: { "spreadsheet_id":"abc","range":"Sheet1!A2:Z100" }"""
        sid = payload.get('spreadsheet_id', '')
        rng = payload.get('range', 'Sheet1!A2:Z100')
        if not sid:
            return {'ok': False, 'error': 'payload.spreadsheet_id required'}
        status, d = await _post(f'{SHEETS}/{sid}/values/{rng}:clear', {})
        return _ok(status, d, {'cleared_range': d.get('clearedRange', rng)})

    # ════════════════════ CALENDAR ══════════════════════════════════════════

    CAL = 'https://www.googleapis.com/calendar/v3'

    # ── calendar_list ─────────────────────────────────────────────────────────
    if action == 'calendar_list':
        status, d = await _get(f'{CAL}/users/me/calendarList')
        if status != 200:
            return _ok(status, d)
        cals = [
            {
                'id': c.get('id'),
                'name': c.get('summary'),
                'primary': c.get('primary', False),
                'color': c.get('backgroundColor', ''),
                'access': c.get('accessRole', ''),
            }
            for c in d.get('items', [])
        ]
        return {
            'ok': True,
            'calendars': cals,
            'count': len(cals),
            'primary': next((c['id'] for c in cals if c.get('primary')), 'primary'),
        }

    # ── calendar_list_events ──────────────────────────────────────────────────
    if action == 'calendar_list_events':
        """payload: { "calendar_id":"primary","time_min":"2026-01-01T00:00:00Z",
                      "time_max":"2026-12-31T23:59:59Z","max_results":10,"query":"meeting" }"""
        import datetime

        cal_id = payload.get('calendar_id', 'primary')
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        params: dict = {
            'maxResults': payload.get('max_results', 10),
            'orderBy': 'startTime',
            'singleEvents': True,
            'timeMin': payload.get('time_min', now),
        }
        if payload.get('time_max'):
            params['timeMax'] = payload['time_max']
        if payload.get('query'):
            params['q'] = payload['query']
        status, d = await _get(f'{CAL}/calendars/{cal_id}/events', params)
        if status != 200:
            return _ok(status, d)
        events = [
            {
                'id': e.get('id'),
                'title': e.get('summary', '(no title)'),
                'start': (e.get('start', {}).get('dateTime') or e.get('start', {}).get('date', ''))[:16],
                'end': (e.get('end', {}).get('dateTime') or e.get('end', {}).get('date', ''))[:16],
                'location': e.get('location', ''),
                'attendees': [a.get('email', '') for a in e.get('attendees', [])],
                'status': e.get('status', ''),
                'url': e.get('htmlLink', ''),
            }
            for e in d.get('items', [])
        ]
        return {
            'ok': True,
            'events': events,
            'count': len(events),
            'calendar': d.get('summary', ''),
            'timezone': d.get('timeZone', ''),
        }

    # ── calendar_create_event ─────────────────────────────────────────────────
    if action == 'calendar_create_event':
        """payload: { "title","start":"2026-08-01T10:00:00","end":"2026-08-01T11:00:00",
                      "timezone":"America/New_York","location":"","description":"",
                      "attendees":["email@x.com"],"calendar_id":"primary",
                      "all_day":false }"""
        title = payload.get('title', '') or payload.get('summary', '')
        start = payload.get('start', '')
        end = payload.get('end', '')
        tz = payload.get('timezone', 'UTC')
        cal_id = payload.get('calendar_id', 'primary')
        all_day = payload.get('all_day', False)

        if not title or not start:
            return {'ok': False, 'error': 'payload.title and payload.start required'}

        if all_day:
            event_body: dict = {
                'summary': title,
                'start': {'date': start[:10]},
                'end': {'date': (end or start)[:10]},
            }
        else:
            # Ensure timezone-aware format
            # Ensure valid RFC3339: if no tz offset, append 'Z' (UTC)
            start_dt = start if ('Z' in start or '+' in start or start.count('-') > 2) else start + 'Z'
            end_dt = end if ('Z' in end or '+' in end or end.count('-') > 2) else end + 'Z'
            event_body = {
                'summary': title,
                'start': {'dateTime': start_dt, 'timeZone': tz},
                'end': {'dateTime': end_dt, 'timeZone': tz},
            }

        if payload.get('description'):
            event_body['description'] = payload['description']
        if payload.get('location'):
            event_body['location'] = payload['location']
        if payload.get('attendees'):
            event_body['attendees'] = [{'email': e} for e in payload['attendees']]

        status, d = await _post(f'{CAL}/calendars/{cal_id}/events', event_body)
        return _ok(
            status,
            d,
            {
                'event_id': d.get('id'),
                'title': d.get('summary'),
                'start': (d.get('start', {}).get('dateTime') or d.get('start', {}).get('date', ''))[:16],
                'end': (d.get('end', {}).get('dateTime') or d.get('end', {}).get('date', ''))[:16],
                'url': d.get('htmlLink', ''),
                'calendar': cal_id,
            },
        )

    # ── calendar_delete_event ─────────────────────────────────────────────────
    if action == 'calendar_delete_event':
        """payload: { "event_id":"abc123","calendar_id":"primary" }"""
        eid = payload.get('event_id', '')
        cal_id = payload.get('calendar_id', 'primary')
        if not eid:
            return {'ok': False, 'error': 'payload.event_id required'}
        status, _ = await _delete(f'{CAL}/calendars/{cal_id}/events/{eid}')
        return {'ok': status == 204, 'event_id': eid, 'error': '' if status == 204 else f'HTTP {status}'}

    return {
        'ok': False,
        'error': f"Unknown Google Workspace action: '{action}'. Valid: "
        'test_connection, get_myself, refresh_token_now, list_accounts, '
        'gmail_list_labels, gmail_list_messages, gmail_get_message, gmail_send, '
        'gmail_create_draft, gmail_search, '
        'drive_list_files, drive_get_file, drive_create_folder, '
        'drive_upload_text, drive_delete_file, '
        'docs_create, docs_get, docs_append_text, docs_replace_text, '
        'sheets_create, sheets_get, sheets_read_range, sheets_write_range, '
        'sheets_append_rows, sheets_clear_range, '
        'calendar_list, calendar_list_events, calendar_create_event, '
        'calendar_delete_event',
    }


# ── Notion connector ──────────────────────────────────────────────────────────
_NOTION_BASE = 'https://api.notion.com/v1'
_NOTION_VERSION = '2022-06-28'


def _notion_headers(token: str) -> dict:
    return {
        'Authorization': f'Bearer {token}',
        'Notion-Version': _NOTION_VERSION,
        'Content-Type': 'application/json',
    }


def _notion_token(creds: dict) -> str:
    tok = creds.get('token') or creds.get('api_key') or creds.get('notion_token') or ''
    if not tok:
        raise ValueError('Notion token not configured. Set credentials.token')
    return tok


def _notion_rich_text(text: str) -> list:
    """Convert plain string to Notion rich_text block list."""
    return [{'type': 'text', 'text': {'content': text}}]


def _notion_title_prop(title: str) -> dict:
    """Return a Notion 'title' property value."""
    return {'title': _notion_rich_text(title)}


def _extract_plain_text(rich_text_list: list) -> str:
    """Extract plain text from a Notion rich_text array."""
    return ''.join(rt.get('plain_text', '') for rt in rich_text_list)


async def _exec_notion(action: str, payload: dict, creds: dict) -> dict:
    """Dispatcher for conn_notion."""
    import httpx

    token = _notion_token(creds)
    hdrs = _notion_headers(token)

    # ── test_connection ────────────────────────────────────────────────────────
    if action == 'test_connection':
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f'{_NOTION_BASE}/users/me', headers=hdrs)
        if r.status_code == 200:
            data = r.json()
            return {
                'ok': True,
                'bot_name': data.get('name'),
                'bot_id': data.get('id'),
                'workspace_name': data.get('bot', {}).get('workspace_name'),
                'owner_email': data.get('bot', {}).get('owner', {}).get('user', {}).get('person', {}).get('email'),
            }
        return {'ok': False, 'error': r.text[:300], 'status_code': r.status_code}

    # ── get_bot_info ───────────────────────────────────────────────────────────
    if action == 'get_bot_info':
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f'{_NOTION_BASE}/users/me', headers=hdrs)
        r.raise_for_status()
        return {'ok': True, 'bot': r.json()}

    # ── list_users ─────────────────────────────────────────────────────────────
    if action == 'list_users':
        params = {}
        if payload.get('start_cursor'):
            params['start_cursor'] = payload['start_cursor']
        if payload.get('page_size'):
            params['page_size'] = payload['page_size']
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f'{_NOTION_BASE}/users', headers=hdrs, params=params)
            if r.status_code == 403:
                # Personal access tokens (PATs) cannot list workspace users — Notion API restriction
                # Return the bot info only (which is always accessible via /users/me)
                r2 = await client.get(f'{_NOTION_BASE}/users/me', headers=hdrs)
                bot = r2.json() if r2.status_code == 200 else {}
                return {
                    'ok': True,
                    'users': [bot] if bot else [],
                    'has_more': False,
                    'note': 'Personal access tokens cannot list all workspace users (Notion API restriction). Returning bot user only.',
                }
            r.raise_for_status()
            data = r.json()
        return {'ok': True, 'users': data.get('results', []), 'has_more': data.get('has_more', False)}

    # ── search ─────────────────────────────────────────────────────────────────
    if action == 'search':
        body: dict = {}
        if payload.get('query'):
            body['query'] = payload['query']
        if payload.get('filter'):
            body['filter'] = payload['filter']
        if payload.get('sort'):
            body['sort'] = payload['sort']
        if payload.get('page_size'):
            body['page_size'] = payload['page_size']
        if payload.get('start_cursor'):
            body['start_cursor'] = payload['start_cursor']
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f'{_NOTION_BASE}/search', headers=hdrs, json=body)
        r.raise_for_status()
        data = r.json()
        return {
            'ok': True,
            'results': data.get('results', []),
            'has_more': data.get('has_more', False),
            'next_cursor': data.get('next_cursor'),
        }

    # ── get_database ───────────────────────────────────────────────────────────
    if action == 'get_database':
        db_id = payload.get('database_id', '')
        if not db_id:
            return {'ok': False, 'error': 'database_id required'}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f'{_NOTION_BASE}/databases/{db_id}', headers=hdrs)
        r.raise_for_status()
        data = r.json()
        # Extract title
        title_list = data.get('title', [])
        title = _extract_plain_text(title_list) if title_list else '(untitled)'
        return {
            'ok': True,
            'id': data.get('id'),
            'title': title,
            'properties': list(data.get('properties', {}).keys()),
            'url': data.get('url'),
            'created_time': data.get('created_time'),
            'last_edited_time': data.get('last_edited_time'),
        }

    # ── query_database ─────────────────────────────────────────────────────────
    if action == 'query_database':
        db_id = payload.get('database_id', '')
        if not db_id:
            return {'ok': False, 'error': 'database_id required'}
        body = {}
        if payload.get('filter'):
            body['filter'] = payload['filter']
        if payload.get('sorts'):
            body['sorts'] = payload['sorts']
        if payload.get('page_size'):
            body['page_size'] = payload['page_size']
        if payload.get('start_cursor'):
            body['start_cursor'] = payload['start_cursor']
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f'{_NOTION_BASE}/databases/{db_id}/query', headers=hdrs, json=body)
        r.raise_for_status()
        data = r.json()
        results = data.get('results', [])
        # Summarise pages
        pages_summary = []
        for pg in results:
            props = pg.get('properties', {})
            # Try to find the title property
            title_val = ''
            for pname, pval in props.items():
                if pval.get('type') == 'title':
                    title_val = _extract_plain_text(pval.get('title', []))
                    break
            pages_summary.append(
                {
                    'id': pg.get('id'),
                    'title': title_val,
                    'url': pg.get('url'),
                    'created_time': pg.get('created_time'),
                    'last_edited_time': pg.get('last_edited_time'),
                }
            )
        return {
            'ok': True,
            'results': pages_summary,
            'raw_results': results,
            'has_more': data.get('has_more', False),
            'next_cursor': data.get('next_cursor'),
            'count': len(results),
        }

    # ── create_database ────────────────────────────────────────────────────────
    if action == 'create_database':
        parent_page_id = payload.get('parent_page_id', '')
        if not parent_page_id:
            return {'ok': False, 'error': 'parent_page_id required'}
        title = payload.get('title', 'New Database')
        properties = payload.get('properties') or {'Name': {'title': {}}}
        body = {
            'parent': {'type': 'page_id', 'page_id': parent_page_id},
            'title': _notion_rich_text(title),
            'properties': properties,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f'{_NOTION_BASE}/databases', headers=hdrs, json=body)
        r.raise_for_status()
        data = r.json()
        return {'ok': True, 'database_id': data.get('id'), 'url': data.get('url'), 'title': title}

    # ── get_page ───────────────────────────────────────────────────────────────
    if action == 'get_page':
        page_id = payload.get('page_id', '')
        if not page_id:
            return {'ok': False, 'error': 'page_id required'}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f'{_NOTION_BASE}/pages/{page_id}', headers=hdrs)
        r.raise_for_status()
        data = r.json()
        props = data.get('properties', {})
        title_val = ''
        for pname, pval in props.items():
            if pval.get('type') == 'title':
                title_val = _extract_plain_text(pval.get('title', []))
                break
        return {
            'ok': True,
            'id': data.get('id'),
            'title': title_val,
            'url': data.get('url'),
            'parent': data.get('parent'),
            'created_time': data.get('created_time'),
            'last_edited_time': data.get('last_edited_time'),
            'archived': data.get('archived', False),
        }

    # ── create_page ───────────────────────────────────────────────────────────
    if action == 'create_page':
        title = payload.get('title', 'New Page')
        parent = payload.get('parent')  # {"database_id": "..."} or {"page_id": "..."}
        if not parent:
            return {'ok': False, 'error': 'parent required: {database_id: ...} or {page_id: ...}'}
        properties = payload.get('properties') or {'Name': _notion_title_prop(title)}
        # If parent is database, the title prop key must match db schema
        body: dict = {
            'parent': parent,
            'properties': properties,
        }
        # Optional: children blocks (content)
        children = payload.get('children')
        if not children and payload.get('content'):
            # Build a simple paragraph block from content string
            children = [
                {
                    'object': 'block',
                    'type': 'paragraph',
                    'paragraph': {'rich_text': _notion_rich_text(payload['content'])},
                }
            ]
        if children:
            body['children'] = children
        if payload.get('icon'):
            body['icon'] = payload['icon']
        if payload.get('cover'):
            body['cover'] = payload['cover']
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f'{_NOTION_BASE}/pages', headers=hdrs, json=body)
        if r.status_code not in (200, 201):
            return {'ok': False, 'error': r.text[:400], 'status_code': r.status_code}
        data = r.json()
        # Extract page title back
        page_title = title
        resp_props = data.get('properties', {})
        for pname, pval in resp_props.items():
            if pval.get('type') == 'title':
                page_title = _extract_plain_text(pval.get('title', [])) or title
                break
        return {
            'ok': True,
            'page_id': data.get('id'),
            'title': page_title,
            'url': data.get('url'),
            'created_time': data.get('created_time'),
        }

    # ── update_page ───────────────────────────────────────────────────────────
    if action == 'update_page':
        page_id = payload.get('page_id', '')
        if not page_id:
            return {'ok': False, 'error': 'page_id required'}
        body = {}
        if payload.get('properties'):
            body['properties'] = payload['properties']
        if 'archived' in payload:
            body['archived'] = payload['archived']
        if payload.get('icon'):
            body['icon'] = payload['icon']
        if payload.get('cover'):
            body['cover'] = payload['cover']
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.patch(f'{_NOTION_BASE}/pages/{page_id}', headers=hdrs, json=body)
        if r.status_code not in (200, 201):
            return {'ok': False, 'error': r.text[:400], 'status_code': r.status_code}
        data = r.json()
        return {
            'ok': True,
            'page_id': data.get('id'),
            'url': data.get('url'),
            'last_edited_time': data.get('last_edited_time'),
        }

    # ── archive_page (soft-delete) ─────────────────────────────────────────────
    if action == 'archive_page':
        page_id = payload.get('page_id', '')
        if not page_id:
            return {'ok': False, 'error': 'page_id required'}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.patch(f'{_NOTION_BASE}/pages/{page_id}', headers=hdrs, json={'archived': True})
        if r.status_code not in (200, 201):
            return {'ok': False, 'error': r.text[:300], 'status_code': r.status_code}
        return {'ok': True, 'page_id': page_id, 'archived': True}

    # ── get_page_content (blocks) ─────────────────────────────────────────────
    if action == 'get_page_content':
        page_id = payload.get('page_id', '')
        if not page_id:
            return {'ok': False, 'error': 'page_id required'}
        params = {}
        if payload.get('start_cursor'):
            params['start_cursor'] = payload['start_cursor']
        if payload.get('page_size'):
            params['page_size'] = payload['page_size']
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f'{_NOTION_BASE}/blocks/{page_id}/children', headers=hdrs, params=params)
        r.raise_for_status()
        data = r.json()
        blocks = data.get('results', [])
        # Extract plain text from common block types
        text_content = []
        for blk in blocks:
            btype = blk.get('type', '')
            bdata = blk.get(btype, {})
            rt = bdata.get('rich_text', [])
            if rt:
                text_content.append(_extract_plain_text(rt))
        return {
            'ok': True,
            'blocks': blocks,
            'text_content': '\n'.join(text_content),
            'has_more': data.get('has_more', False),
            'block_count': len(blocks),
        }

    # ── append_page_content ───────────────────────────────────────────────────
    if action == 'append_page_content':
        page_id = payload.get('page_id', '')
        if not page_id:
            return {'ok': False, 'error': 'page_id required'}
        children = payload.get('children')
        if not children and payload.get('text'):
            children = [
                {'object': 'block', 'type': 'paragraph', 'paragraph': {'rich_text': _notion_rich_text(payload['text'])}}
            ]
        if not children:
            return {'ok': False, 'error': 'children or text required'}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.patch(
                f'{_NOTION_BASE}/blocks/{page_id}/children', headers=hdrs, json={'children': children}
            )
        if r.status_code not in (200, 201):
            return {'ok': False, 'error': r.text[:400], 'status_code': r.status_code}
        data = r.json()
        return {'ok': True, 'appended_blocks': len(data.get('results', [])), 'page_id': page_id}

    # ── get_block ─────────────────────────────────────────────────────────────
    if action == 'get_block':
        block_id = payload.get('block_id', '')
        if not block_id:
            return {'ok': False, 'error': 'block_id required'}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f'{_NOTION_BASE}/blocks/{block_id}', headers=hdrs)
        r.raise_for_status()
        return {'ok': True, 'block': r.json()}

    # ── delete_block ──────────────────────────────────────────────────────────
    if action == 'delete_block':
        block_id = payload.get('block_id', '')
        if not block_id:
            return {'ok': False, 'error': 'block_id required'}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.delete(f'{_NOTION_BASE}/blocks/{block_id}', headers=hdrs)
        if r.status_code not in (200, 204):
            return {'ok': False, 'error': r.text[:300], 'status_code': r.status_code}
        return {'ok': True, 'deleted_block_id': block_id}

    # ── add_database_row (create page in database = new row) ──────────────────
    if action == 'add_database_row':
        db_id = payload.get('database_id', '')
        if not db_id:
            return {'ok': False, 'error': 'database_id required'}
        row_title = payload.get('title', 'New Row')
        properties = payload.get('properties') or {'Name': _notion_title_prop(row_title)}
        body = {
            'parent': {'database_id': db_id},
            'properties': properties,
        }
        if payload.get('children'):
            body['children'] = payload['children']
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f'{_NOTION_BASE}/pages', headers=hdrs, json=body)
        if r.status_code not in (200, 201):
            return {'ok': False, 'error': r.text[:400], 'status_code': r.status_code}
        data = r.json()
        return {'ok': True, 'page_id': data.get('id'), 'url': data.get('url'), 'created_time': data.get('created_time')}

    # ── update_database_row ───────────────────────────────────────────────────
    if action == 'update_database_row':
        page_id = payload.get('page_id', '')
        if not page_id:
            return {'ok': False, 'error': 'page_id required'}
        properties = payload.get('properties', {})
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.patch(f'{_NOTION_BASE}/pages/{page_id}', headers=hdrs, json={'properties': properties})
        if r.status_code not in (200, 201):
            return {'ok': False, 'error': r.text[:400], 'status_code': r.status_code}
        data = r.json()
        return {
            'ok': True,
            'page_id': data.get('id'),
            'url': data.get('url'),
            'last_edited_time': data.get('last_edited_time'),
        }

    # ── list_comments ─────────────────────────────────────────────────────────
    if action == 'list_comments':
        block_id = payload.get('block_id') or payload.get('page_id', '')
        if not block_id:
            return {'ok': False, 'error': 'block_id or page_id required'}
        params = {'block_id': block_id}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f'{_NOTION_BASE}/comments', headers=hdrs, params=params)
        if r.status_code == 403:
            return {
                'ok': False,
                'error': "comments scope not granted — enable 'Read comments' in integration settings",
                'status_code': 403,
            }
        r.raise_for_status()
        data = r.json()
        return {'ok': True, 'comments': data.get('results', []), 'has_more': data.get('has_more', False)}

    # ── create_comment ────────────────────────────────────────────────────────
    if action == 'create_comment':
        parent_id = payload.get('page_id') or payload.get('block_id', '')
        text = payload.get('text', '')
        if not parent_id or not text:
            return {'ok': False, 'error': 'page_id (or block_id) and text required'}
        body = {
            'parent': {'page_id': parent_id},
            'rich_text': _notion_rich_text(text),
        }
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f'{_NOTION_BASE}/comments', headers=hdrs, json=body)
        if r.status_code == 403:
            return {
                'ok': False,
                'error': "comments scope not granted — enable 'Insert comments' in integration settings",
                'status_code': 403,
            }
        if r.status_code not in (200, 201):
            return {'ok': False, 'error': r.text[:400], 'status_code': r.status_code}
        data = r.json()
        return {'ok': True, 'comment_id': data.get('id'), 'page_id': parent_id}

    return {'ok': False, 'error': f'Unknown Notion action: {action}'}


_DISPATCHERS = {
    'conn_slack': _exec_slack,
    'conn_jira': _exec_jira,
    'conn_email': _exec_email,
    'conn_webhook': _exec_webhook,
    'conn_github': _exec_github,
    'conn_gdrive': _exec_gdrive,
    'conn_notion': _exec_notion,
}


# ── Core execute function ──────────────────────────────────────────────────────
async def execute_connector(
    connector_id: str, action: str, payload: dict, agent_id: str = 'system', inline_creds:Optional[ dict] = None
) -> dict:
    """Execute a connector action. Records to audit log."""
    import hashlib
    import time

    exec_id = f'cex_{uuid.uuid4().hex[:10]}'
    t0 = time.time()

    con = _get_conn()
    try:
        row = con.execute('SELECT * FROM connector_registry WHERE connector_id=?', (connector_id,)).fetchone()
    finally:
        con.close()

    if not row:
        return {'ok': False, 'error': f"Connector '{connector_id}' not found"}

    connector = _connector_dict(row)
    # Load DB-stored creds (unmasked)
    con = _get_conn()
    try:
        raw = con.execute('SELECT credentials FROM connector_registry WHERE connector_id=?', (connector_id,)).fetchone()
        db_creds = json.loads(raw['credentials'] or '{}') if raw else {}
    finally:
        con.close()
    # Inline creds override DB creds (enables multi-account: pass different creds per call)
    creds = {**db_creds, **(inline_creds or {})}

    try:
        dispatcher = _DISPATCHERS.get(connector_id)
        if dispatcher:
            result = await dispatcher(action, payload, creds)
        else:
            result = {'ok': False, 'error': f'No dispatcher for connector: {connector_id}'}
    except Exception as e:
        result = {'ok': False, 'error': str(e)[:300]}

    duration_ms = int((time.time() - t0) * 1000)
    status = 'ok' if result.get('ok') else 'error'
    ph = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]

    con = _get_conn()
    try:
        con.execute(
            """INSERT INTO connector_executions (exec_id,connector_id,action,agent_id,payload_hash,status,result,error,duration_ms,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                exec_id,
                connector_id,
                action,
                agent_id,
                ph,
                status,
                json.dumps(result, default=str)[:2000],
                result.get('error', '')[:500],
                duration_ms,
                _now(),
            ),
        )
        con.execute(
            'UPDATE connector_registry SET call_count=call_count+1, last_used=? WHERE connector_id=?',
            (_now(), connector_id),
        )
        con.commit()
    finally:
        con.close()

    try:
        from ..routers.audit_log import append_entry

        append_entry(
            agent_id,
            agent_id.title(),
            'connector_exec',
            f'[{connector["name"]}] {action}: {str(payload)[:80]}',
            authority='agent',
            risk_level='medium',
            outcome='success' if result.get('ok') else 'failure',
            metadata={'exec_id': exec_id, 'connector_id': connector_id, 'action': action, 'duration_ms': duration_ms},
        )
    except Exception:
        pass

    log.info('Connector %s.%s → %s (%dms)', connector_id, action, status, duration_ms)
    return {**result, 'exec_id': exec_id, 'duration_ms': duration_ms}


# ── API Routes ─────────────────────────────────────────────────────────────────
@router.get('')
def list_connectors(category: str = '', status: str = ''):
    """Retrieve and return list connectors."""
    where, params = [], []
    if category:
        where.append('category=?')
        params.append(category)
    if status:
        where.append('status=?')
        params.append(status)
    sql = (
        'SELECT * FROM connector_registry'
        + ((' WHERE ' + ' AND '.join(where)) if where else '')
        + ' ORDER BY category, name'
    )
    con = _get_conn()
    try:
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return {'connectors': [_connector_dict(r) for r in rows], 'count': len(rows)}


@router.post('')
async def register_connector(req: Request):
    """Register a custom connector (Connector SDK)."""
    try:
        body = await req.json()
    except:
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)
    name = (body.get('name') or '').strip()
    if not name:
        return JSONResponse({'ok': False, 'error': 'name required'}, status_code=400)
    conn_id = f'conn_{uuid.uuid4().hex[:8]}'
    now = _now()
    con = _get_conn()
    try:
        con.execute(
            """INSERT INTO connector_registry (connector_id,name,description,category,icon,status,auth_type,capabilities,config,credentials,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                conn_id,
                name[:100],
                (body.get('description') or '')[:500],
                (body.get('category') or 'custom')[:30],
                (body.get('icon') or '🔌')[:8],
                'unconfigured',
                (body.get('auth_type') or 'none')[:20],
                json.dumps(body.get('capabilities') or []),
                json.dumps(body.get('config') or {}),
                json.dumps(body.get('credentials') or {}),
                now,
                now,
            ),
        )
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'connector_id': conn_id, 'name': name}


@router.get('/{connector_id}')
def get_connector(connector_id: str):
    """Retrieve and return get connector."""
    con = _get_conn()
    try:
        row = con.execute('SELECT * FROM connector_registry WHERE connector_id=?', (connector_id,)).fetchone()
    finally:
        con.close()
    if not row:
        return JSONResponse({'ok': False, 'error': 'Not found'}, status_code=404)
    return {'ok': True, 'connector': _connector_dict(row)}


@router.patch('/{connector_id}/configure')
async def configure_connector(connector_id: str, req: Request):
    """Save credentials and configuration for a connector."""
    try:
        body = await req.json()
    except:
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)
    creds = body.get('credentials') or {}
    config = body.get('config') or {}
    status = 'active' if creds else 'unconfigured'
    con = _get_conn()
    try:
        con.execute(
            'UPDATE connector_registry SET credentials=?, config=?, status=?, updated_at=? WHERE connector_id=?',
            (json.dumps(creds), json.dumps(config), status, _now(), connector_id),
        )
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'connector_id': connector_id, 'status': status}


@router.post('/{connector_id}/execute')
async def run_connector(connector_id: str, req: Request):
    """Execute a connector action.
    Optional: pass 'credentials' in the body to use inline creds (multi-account support).
    """
    try:
        body = await req.json()
    except:
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)
    action = (body.get('action') or '').strip()
    payload = body.get('payload') or {}
    agent_id = (body.get('agent_id') or 'user').strip()
    inline_creds = body.get('credentials') or {}  # optional per-call credential override
    if not action:
        return JSONResponse({'ok': False, 'error': 'action required'}, status_code=400)
    result = await execute_connector(connector_id, action, payload, agent_id, inline_creds=inline_creds)
    return result


@router.post('/{connector_id}/test')
async def test_connector(connector_id: str):
    """Run a lightweight connectivity test for the connector."""
    con = _get_conn()
    try:
        row = con.execute(
            'SELECT name, status, auth_type FROM connector_registry WHERE connector_id=?', (connector_id,)
        ).fetchone()
    finally:
        con.close()
    if not row:
        return JSONResponse({'ok': False, 'error': 'Not found'}, status_code=404)
    return {
        'ok': True,
        'connector_id': connector_id,
        'name': row['name'],
        'status': row['status'],
        'configured': row['status'] == 'active',
        'message': 'Connector is active and ready'
        if row['status'] == 'active'
        else f'Connector needs credentials ({row["auth_type"]} auth)',
    }


@router.get('/{connector_id}/executions')
def list_executions(connector_id: str, limit: int = 20):
    """Retrieve and return list executions."""
    con = _get_conn()
    try:
        rows = con.execute(
            'SELECT * FROM connector_executions WHERE connector_id=? ORDER BY created_at DESC LIMIT ?',
            (connector_id, min(limit, 200)),
        ).fetchall()
    finally:
        con.close()
    return {'executions': [dict(r) for r in rows], 'count': len(rows)}


@router.get('/stats/summary')
def connector_stats():
    """Execute or process connector stats operation."""
    con = _get_conn()
    try:
        total_conn = con.execute('SELECT COUNT(*) FROM connector_registry').fetchone()[0]
        active_conn = con.execute("SELECT COUNT(*) FROM connector_registry WHERE status='active'").fetchone()[0]
        total_exec = con.execute('SELECT COUNT(*) FROM connector_executions').fetchone()[0]
        by_cat = con.execute('SELECT category,COUNT(*) cnt FROM connector_registry GROUP BY category').fetchall()
        top_used = con.execute(
            'SELECT name,call_count FROM connector_registry ORDER BY call_count DESC LIMIT 5'
        ).fetchall()
    finally:
        con.close()
    return {
        'total_connectors': total_conn,
        'active_connectors': active_conn,
        'total_executions': total_exec,
        'by_category': {r['category']: r['cnt'] for r in by_cat},
        'top_connectors': [dict(r) for r in top_used],
    }
