"""
Agentic OS — Agent Hooks System (Kiro + Windsurf Cascade Hooks)
Event-driven automations that fire agents automatically on file/git events.

Hook events:
  - file_save    : triggered when a file is saved in preview/
  - file_create  : new file created
  - git_commit   : before/after git commit
  - api_change   : OpenAPI spec changes detected
  - test_fail    : test runner reports failure
  - schedule     : cron-style time triggers
  - deploy       : before/after deployment
  - chat_send    : on every chat message
  - agent_done   : when any agent run completes
  - manual       : triggered explicitly by user

Hooks are stored in .agentic/hooks.yaml and in SQLite.
"""

from __future__ import annotations

import contextlib

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter(prefix='/api/hooks', tags=['hooks'])
log = logging.getLogger('agentic.hooks')

from backend.config import get_data_dir
ROOT = get_data_dir()
HOOKS_DIR = ROOT / '.agentic'
HOOKS_DIR.mkdir(exist_ok=True)

# ── DB schema ──────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_hooks (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    event       TEXT NOT NULL,
    condition   TEXT DEFAULT '',
    prompt      TEXT NOT NULL,
    agent_id    TEXT DEFAULT 'builder',
    enabled     INTEGER DEFAULT 1,
    run_count   INTEGER DEFAULT 0,
    last_run    TIMESTAMP,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS hook_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hook_id     TEXT NOT NULL,
    event_data  TEXT DEFAULT '',
    output      TEXT DEFAULT '',
    status      TEXT DEFAULT 'pending',
    duration_ms INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_hook_runs_hook ON hook_runs(hook_id, created_at);
"""

BUILT_IN_HOOKS = [
    {
        'id': 'hook_regen_tests',
        'name': 'Auto-Regenerate Tests',
        'description': 'When a source file is saved, regenerate its unit tests',
        'event': 'file_save',
        'condition': "file.extension in ['.py','.js','.ts'] and 'test' not in file.path",
        'prompt': 'A file was just saved: {{file.path}}\n\nContent:\n{{file.content}}\n\nGenerate comprehensive unit tests for this file. Output only the test code.',
        'agent_id': 'builder',
        'enabled': 0,
    },
    {
        'id': 'hook_update_docs',
        'name': 'Auto-Update Documentation',
        'description': 'When an API endpoint changes, update the docs',
        'event': 'api_change',
        'condition': '',
        'prompt': 'An API endpoint changed:\n{{change.description}}\n\nUpdate the documentation for this endpoint. Return only the updated docstring/JSDoc.',
        'agent_id': 'builder',
        'enabled': 0,
    },
    {
        'id': 'hook_security_scan',
        'name': 'Pre-Commit Security Scan',
        'description': 'Before each git commit, scan for secrets and vulnerabilities',
        'event': 'git_commit',
        'condition': '',
        'prompt': "Files being committed:\n{{commit.files}}\n\nScan for:\n1. Hardcoded secrets or API keys\n2. SQL injection vulnerabilities\n3. XSS vulnerabilities\n4. Insecure dependencies\n\nReport any issues found. If clean, say 'CLEAN: no issues found'.",
        'agent_id': 'researcher',
        'enabled': 0,
    },
    {
        'id': 'hook_changelog',
        'name': 'Auto-Generate Changelog',
        'description': 'After each commit, update CHANGELOG.md',
        'event': 'git_commit',
        'condition': '',
        'prompt': 'A git commit was made:\nMessage: {{commit.message}}\nFiles changed: {{commit.files}}\n\nGenerate a changelog entry in Keep a Changelog format. Be concise.',
        'agent_id': 'builder',
        'enabled': 0,
    },
    {
        'id': 'hook_fix_failing_tests',
        'name': 'Auto-Fix Failing Tests',
        'description': 'When tests fail, attempt to fix the source code',
        'event': 'test_fail',
        'condition': '',
        'prompt': 'Tests are failing:\n{{test.output}}\n\nFailing file: {{test.file}}\n\nAnalyze the failures and propose fixes to the source code. Return the corrected code.',
        'agent_id': 'builder',
        'enabled': 0,
    },
    {
        'id': 'hook_perf_check',
        'name': 'Performance Check on Save',
        'description': 'Check for performance issues when large files are saved',
        'event': 'file_save',
        'condition': 'file.size_lines > 200',
        'prompt': 'Review this code for performance issues:\n{{file.content}}\n\nIdentify: O(n²) loops, memory leaks, blocking I/O, redundant re-renders. Return concise findings.',
        'agent_id': 'researcher',
        'enabled': 0,
    },
    {
        'id': 'hook_type_check',
        'name': 'TypeScript Type Check',
        'description': 'On .ts/.tsx save, check for type errors',
        'event': 'file_save',
        'condition': "file.extension in ['.ts','.tsx']",
        'prompt': "Check this TypeScript code for type errors:\n{{file.content}}\n\nList any type errors with line numbers and fixes. If clean, say 'TYPE_CLEAN'.",
        'agent_id': 'builder',
        'enabled': 0,
    },
    {
        'id': 'hook_accessibility',
        'name': 'Accessibility Check on HTML Save',
        'description': 'Check HTML files for WCAG accessibility issues',
        'event': 'file_save',
        'condition': "file.extension in ['.html','.jsx','.tsx']",
        'prompt': 'Check this HTML/JSX for WCAG 2.1 accessibility issues:\n{{file.content}}\n\nCheck: missing alt text, ARIA labels, color contrast, keyboard navigation, focus management.',
        'agent_id': 'researcher',
        'enabled': 0,
    },
    {
        'id': 'hook_daily_standup',
        'name': 'Daily Progress Summary',
        'description': "Every morning, summarize yesterday's work and plan today",
        'event': 'schedule',
        'condition': 'cron: 0 9 * * 1-5',
        'prompt': 'Generate a daily standup summary:\n\nRecent activity:\n{{activity.summary}}\n\nFormat:\n**Yesterday:** What was accomplished\n**Today:** What to focus on\n**Blockers:** Any issues to address',
        'agent_id': 'orchestrator',
        'enabled': 0,
    },
    {
        'id': 'hook_deploy_check',
        'name': 'Pre-Deploy Safety Check',
        'description': 'Before deploying, verify the build is safe to ship',
        'event': 'deploy',
        'condition': '',
        'prompt': 'Pre-deployment checklist for: {{deploy.target}}\n\nVerify:\n1. No console.log statements in production code\n2. Environment variables properly set\n3. No TODO/FIXME comments in critical paths\n4. Error handling in place\n\nReport status: DEPLOY_SAFE or DEPLOY_BLOCKED with reasons.',
        'agent_id': 'researcher',
        'enabled': 0,
    },
    {
        'id': 'hook_ambient_review',
        'name': 'Ambient Code Reviewer',
        'description': 'Proactively review recently edited files and suggest improvements',
        'event': 'schedule',
        'condition': 'cron: 0 */4 * * *',
        'prompt': 'Review the most recently edited files:\n{{recent_files}}\n\nProvide proactive suggestions for: code quality, potential bugs, refactoring opportunities, missing error handling.',
        'agent_id': 'researcher',
        'enabled': 0,
    },
    {
        'id': 'hook_dependency_audit',
        'name': 'Weekly Dependency Audit',
        'description': 'Weekly check for outdated or vulnerable dependencies',
        'event': 'schedule',
        'condition': 'cron: 0 10 * * 1',
        'prompt': 'Audit the project dependencies:\n{{dependencies}}\n\nCheck for: outdated packages, known vulnerabilities, unused dependencies, better alternatives.',
        'agent_id': 'researcher',
        'enabled': 0,
    },
]


def _ensure_schema():
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.executescript(_SCHEMA)
        # Seed built-in hooks
        for h in BUILT_IN_HOOKS:
            row = con.execute('SELECT id FROM agent_hooks WHERE id=?', (h['id'],)).fetchone()
            if not row:
                con.execute(
                    """INSERT INTO agent_hooks(id,name,description,event,condition,prompt,agent_id,enabled)
                               VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        h['id'],
                        h['name'],
                        h['description'],
                        h['event'],
                        h['condition'],
                        h['prompt'],
                        h['agent_id'],
                        h['enabled'],
                    ),
                )
        con.commit()
    finally:
        con.close()


_ensure_schema()


# ── In-memory event queue ─────────────────────────────────────────────────────
_pending_events: list[dict] = []
_running_hooks: set[str] = set()


async def fire_event(event_type: str, event_data: dict):
    """Call this from other routers to trigger hooks."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        hooks = con.execute('SELECT * FROM agent_hooks WHERE event=? AND enabled=1', (event_type,)).fetchall()
    finally:
        con.close()

    for hook in hooks:
        h = dict(hook)
        # Simple condition evaluation
        if h.get('condition'):
            try:
                cond = h['condition']
                # Only evaluate safe conditions
                if 'cron:' in cond:
                    continue  # skip schedule hooks (handled by scheduler)

                # Build a namespace for eval that supports file.extension, event.key etc.
                class _NS:
                    def __init__(self, data):
                        self.__dict__.update(data)

                file_ns = _NS(event_data)
                event_ns = _NS(event_data)
                commit_ns = _NS(event_data)
                test_ns = _NS(event_data)
                safe_locals = {
                    'file': file_ns,
                    'event': event_ns,
                    'commit': commit_ns,
                    'test': test_ns,
                    **event_data,  # also available as flat keys
                }
                # Very limited eval — only comparison expressions
                if not eval(cond, {'__builtins__': {}}, safe_locals):
                    continue
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError):
                pass  # Skip condition errors

        asyncio.create_task(_run_hook(h, event_data))


async def _run_hook(hook: dict, event_data: dict):
    """Execute a single hook."""
    hook_id = hook['id']
    if hook_id in _running_hooks:
        return
    _running_hooks.add(hook_id)
    t0 = time.perf_counter()

    # Build prompt
    prompt = hook['prompt']
    for k, v in event_data.items():
        prompt = prompt.replace(f'{{{{event.{k}}}}}', str(v))
        prompt = prompt.replace(f'{{{{file.{k}}}}}', str(v))
        prompt = prompt.replace(f'{{{{commit.{k}}}}}', str(v))
        prompt = prompt.replace(f'{{{{test.{k}}}}}', str(v))

    output = ''
    status = 'done'
    try:
        from ..services import llm as llm_svc

        msgs = [{'role': 'user', 'content': prompt}]
        result = await llm_svc.complete(
            msgs, agent_id=hook.get('agent_id', 'builder'), max_tokens=1024, inject_steering=False
        )
        output = result.get('text', '')
        if not result.get('ok'):
            status = 'error'
    except Exception as ex:
        output = f'Hook error: {ex}'
        status = 'error'
    finally:
        _running_hooks.discard(hook_id)

    dur_ms = int((time.perf_counter() - t0) * 1000)

    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            """INSERT INTO hook_runs(hook_id,event_data,output,status,duration_ms)
                       VALUES (?,?,?,?,?)""",
            (hook_id, json.dumps(event_data, default=str)[:2000], output[:4000], status, dur_ms),
        )
        con.execute('UPDATE agent_hooks SET run_count=run_count+1,last_run=CURRENT_TIMESTAMP WHERE id=?', (hook_id,))
        con.commit()
    finally:
        con.close()

    # Broadcast to WebSocket if available
    try:
        from ..routers.websocket import broadcast

        await broadcast(
            {
                'type': 'hook_fired',
                'hook_id': hook_id,
                'hook_name': hook['name'],
                'output': output[:200],
                'event': hook['event'],
            }
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError):
        pass

    log.info('Hook %s fired for %s → %d chars output', hook['name'], hook['event'], len(output))
    return output


# ── REST endpoints ─────────────────────────────────────────────────────────────
@router.get('')
def list_hooks(event: str = '', enabled: str = ''):
    """Retrieve and return list hooks."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        where, params = [], []
        if event:
            where.append('event=?')
            params.append(event)
        if enabled:
            where.append('enabled=?')
            params.append(1 if enabled == '1' else 0)
        sql = 'SELECT * FROM agent_hooks' + (f' WHERE {" AND ".join(where)}' if where else '') + ' ORDER BY event,name'
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return {'hooks': [dict(r) for r in rows], 'count': len(rows)}


@router.post('')
async def create_hook(req: Request):
    """Create and initialize a new hook."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    hook_id = body.get('id') or f'hook_{uuid.uuid4().hex[:8]}'
    event = (body.get('event', 'file_save') or '').strip() or 'file_save'
    _event_raw = body.get('event')
    if _event_raw is not None and not str(_event_raw).strip():
        return {'ok': False, 'error': 'event is required'}
    prompt = (body.get('prompt') or '').strip()
    if not prompt:
        return {'ok': False, 'error': 'prompt is required'}
    if not event:
        return {'ok': False, 'error': 'event is required'}
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            """INSERT OR IGNORE INTO agent_hooks(id,name,description,event,condition,prompt,agent_id,enabled)
                       VALUES (?,?,?,?,?,?,?,?)""",
            (
                hook_id,
                (body.get('name') or 'Unnamed Hook')[:100],
                (body.get('description') or '')[:400],
                event,
                (body.get('condition') or '')[:400],
                prompt[:4000],
                body.get('agent_id', 'builder'),
                1 if body.get('enabled', True) else 0,
            ),
        )
        con.commit()
    except Exception as e:
        return {'ok': False, 'error': str(e)}
    finally:
        con.close()
    return {'ok': True, 'id': hook_id, 'hook_id': hook_id}


@router.get('/{hook_id}')
def get_hook(hook_id: str):
    """Retrieve and return get hook."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        row = con.execute('SELECT * FROM agent_hooks WHERE id=?', (hook_id,)).fetchone()
        runs = con.execute(
            'SELECT * FROM hook_runs WHERE hook_id=? ORDER BY created_at DESC LIMIT 10', (hook_id,)
        ).fetchall()
    finally:
        con.close()
    if not row:
        return {'ok': False, 'error': 'Hook not found'}
    return {**dict(row), 'recent_runs': [dict(r) for r in runs]}


@router.patch('/{hook_id}')
async def update_hook(hook_id: str, req: Request):
    """Update existing hook record or state."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        allowed = {'name', 'description', 'event', 'condition', 'prompt', 'agent_id', 'enabled'}
        sets, vals = [], []
        for k in allowed:
            if k in body:
                sets.append(f'{k}=?')
                vals.append(body[k])
        if sets:
            vals.append(hook_id)
            cur = con.execute(f'UPDATE agent_hooks SET {",".join(sets)} WHERE id=?', vals)
            con.commit()
            if cur.rowcount == 0:
                return {'ok': False, 'error': 'Hook not found'}
    finally:
        con.close()
    return {'ok': True}


@router.delete('/{hook_id}')
def delete_hook(hook_id: str):
    """Delete or remove specified hook."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute('DELETE FROM hook_runs WHERE hook_id=?', (hook_id,))
        con.execute('DELETE FROM agent_hooks WHERE id=?', (hook_id,))
        con.commit()
    finally:
        con.close()
    return {'ok': True}


@router.post('/{hook_id}/toggle')
async def toggle_hook(hook_id: str):
    """Execute or process toggle hook operation."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        row = con.execute('SELECT enabled FROM agent_hooks WHERE id=?', (hook_id,)).fetchone()
        if not row:
            return {'ok': False, 'error': 'Not found'}
        new_val = 0 if row['enabled'] else 1
        con.execute('UPDATE agent_hooks SET enabled=? WHERE id=?', (new_val, hook_id))
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'enabled': bool(new_val)}


@router.post('/{hook_id}/run')
async def manual_run_hook(hook_id: str, req: Request):
    """Manually trigger a hook."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        row = con.execute('SELECT * FROM agent_hooks WHERE id=?', (hook_id,)).fetchone()
    finally:
        con.close()
    if not row:
        return {'ok': False, 'error': 'Not found'}
    event_data = body.get('event_data', {})
    output = await _run_hook(dict(row), event_data)
    return {'ok': True, 'output': output, 'hook_id': hook_id}


@router.post('/fire')
async def fire_hook_event(req: Request):
    """Fire an event and trigger all matching enabled hooks."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    event_type = body.get('event', 'file_save')
    event_data = body.get('data', {})
    await fire_event(event_type, event_data)
    return {'ok': True, 'event': event_type}


@router.get('/runs/recent')
def recent_runs(limit: int = 50):
    """Execute or process recent runs operation."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute(
            """
            SELECT r.*, h.name as hook_name, h.event
            FROM hook_runs r
            JOIN agent_hooks h ON h.id=r.hook_id
            ORDER BY r.created_at DESC LIMIT ?
        """,
            (min(limit, 200),),
        ).fetchall()
    finally:
        con.close()
    return {'runs': [dict(r) for r in rows], 'count': len(rows)}


@router.get('/events/types')
def event_types():
    """Execute or process event types operation."""
    return {
        'events': [
            {'id': 'file_save', 'label': '📁 File Save', 'desc': 'Triggered when any file is saved in preview/'},
            {'id': 'file_create', 'label': '✨ File Create', 'desc': 'Triggered when a new file is created'},
            {'id': 'git_commit', 'label': '📝 Git Commit', 'desc': 'Before or after a git commit'},
            {'id': 'api_change', 'label': '🔌 API Change', 'desc': 'When an API endpoint definition changes'},
            {'id': 'test_fail', 'label': '❌ Test Failure', 'desc': 'When a test run reports failures'},
            {'id': 'deploy', 'label': '🚀 Deploy', 'desc': 'Before or after deployment'},
            {'id': 'chat_send', 'label': '💬 Chat Message', 'desc': 'On every chat message sent'},
            {'id': 'agent_done', 'label': '🤖 Agent Complete', 'desc': 'When any agent run finishes'},
            {'id': 'schedule', 'label': '⏰ Schedule', 'desc': 'Cron-based time trigger'},
            {'id': 'manual', 'label': '▶️ Manual', 'desc': 'Triggered explicitly by user'},
            {'id': 'error', 'label': '🚨 Error', 'desc': 'When any error occurs in the platform'},
            {'id': 'memory_add', 'label': '🧠 Memory Added', 'desc': 'When something is added to agent memory'},
        ]
    }
