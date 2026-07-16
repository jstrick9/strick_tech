"""
Agentic OS — Integrated Terminal Router
Real shell execution inside Agentic OS. Run npm, pip, git, and any command.
Output streams via SSE. History persisted. Kill support.
"""

from __future__ import annotations

import contextlib

import asyncio
import json
import logging
import os
import shutil
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..services.memory_db import audit_log, get_conn

router = APIRouter(prefix='/api/terminal', tags=['terminal'])
log = logging.getLogger('agentic.terminal')

from backend.config import get_data_dir
ROOT = get_data_dir()
PREVIEW_DIR = ROOT / 'preview'
WORK_DIR = PREVIEW_DIR  # default working directory
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)  # FIX C: ensure cwd exists

# Safe commands that can run without restriction
SAFE_PREFIXES = {
    'ls',
    'cat',
    'echo',
    'pwd',
    'git',
    'node',
    'npm',
    'npx',
    'pip',
    'pip3',
    'python',
    'python3',
    'mkdir',
    'touch',
    'mv',
    'cp',
    'find',
    'grep',
    'head',
    'tail',
    'wc',
    'curl',
    'wget',
    'which',
    'env',
    'export',
    'cd',
    'clear',
}

# Dangerous commands that are always blocked
BLOCKED_COMMANDS = {
    'rm -rf /',
    'rm -rf ~',
    'sudo rm',
    'mkfs',
    'dd if=',
    'chmod -R 777 /',
    '> /dev/sda',
}

_active_processes: dict[str, asyncio.subprocess.Process] = {}


def _ensure_history_table():
    """FIX 8: create terminal_history at startup, not lazily."""
    try:
        con = get_conn()
        try:
            con.execute("""
            CREATE TABLE IF NOT EXISTS terminal_history (
            id INTEGER PRIMARY KEY,
            session_id TEXT,
            command TEXT,
            cwd TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            con.commit()
        finally:
            con.close()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        pass


_ensure_history_table()


# Additional shell injection chars that bypass single-token check
SHELL_INJECTION_CHARS_RAW = {'&&', '||', '`', '$('}  # Always dangerous
# Sensitive paths cat/head/tail must not read
SENSITIVE_PATH_PREFIXES = ('/etc/', '/root/', '/home/', '~/.ssh', '/proc/', '/sys/')


def _strip_quotes(cmd: str) -> str:
    """Remove quoted substrings to check for bare injection chars."""
    import re

    # Remove double-quoted strings (e.g. python3 -c "import sys; sys.exit(42)")
    stripped = re.sub(r'"[^"]*"', "'QUOTED'", cmd)
    # Remove single-quoted strings
    stripped = re.sub(r"'[^']*'", "'QUOTED'", stripped)
    return stripped


def _is_safe(cmd: str) -> tuple[bool, str]:
    cmd_stripped = cmd.strip()

    # Check for injection chars in the UNQUOTED parts only
    cmd_unquoted = _strip_quotes(cmd_stripped)

    # FIX SECURITY: Block shell injection operators in unquoted context
    for inj_char in SHELL_INJECTION_CHARS_RAW:
        if inj_char in cmd_unquoted:
            return False, f"Command blocked: shell operator '{inj_char}' not permitted"

    # Semicolons in unquoted context are also dangerous (command chaining)
    if ';' in cmd_unquoted:
        return False, "Command blocked: shell operator ';' not permitted"

    # FIX SECURITY: Block pipe operator (allows cat /etc/passwd via: echo x | cat /etc/passwd)
    if '|' in cmd_stripped and 'grep' not in cmd_stripped.split('|')[0]:
        # Allow simple grep pipes but block complex pipe chains
        parts = cmd_stripped.split('|')
        if len(parts) > 1:
            for part in parts[1:]:
                piped_cmd = part.strip().split()[0].split('/')[-1] if part.strip() else ''
                if piped_cmd and piped_cmd not in {'grep', 'head', 'tail', 'wc', 'sort', 'uniq'}:
                    return False, f"Command blocked: pipe to '{piped_cmd}' not permitted"

    # FIX 2: blocklist check
    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_stripped:
            return False, f"Command blocked: contains '{blocked}'"

    # FIX SECURITY: Block sensitive path access for file-reading commands
    file_reading_cmds = {'cat', 'head', 'tail', 'grep', 'find'}
    first_token = cmd_stripped.split()[0] if cmd_stripped else ''
    first_token_clean = first_token.split('/')[-1]

    if first_token_clean in file_reading_cmds:
        for sensitive_prefix in SENSITIVE_PATH_PREFIXES:
            if sensitive_prefix in cmd_stripped or cmd_stripped.endswith(sensitive_prefix.rstrip('/')):
                return False, f"Command blocked: access to '{sensitive_prefix}' not permitted"

    # FIX 2: enforce allowlist — only safe-prefix commands may run
    if first_token_clean and first_token_clean not in SAFE_PREFIXES:
        return False, f"Command not allowed: '{first_token_clean}' is not in the permitted command list"
    return True, ''


def _get_work_dir(cwd: str = '') -> str:
    # FIX 4: constrain cwd to PREVIEW_DIR subtree only (not all of ROOT)
    if cwd:
        resolved = (PREVIEW_DIR / cwd.lstrip('/')).resolve()
        if str(resolved).startswith(str(PREVIEW_DIR.resolve())):
            return str(resolved)
    return str(PREVIEW_DIR)


@router.post('/run')
async def run_command(req: Request):
    """
    POST /api/terminal/run
    Body: {command, cwd?, session_id?}
    Returns: SSE stream of {type, data, exit_code?}
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    command = (body.get('command') or '').strip()
    cwd = body.get('cwd', '')
    session = body.get('session_id', str(uuid.uuid4())[:8])

    if not command:

        async def _empty():
            yield f'data: {json.dumps({"type": "error", "data": "No command provided"})}\n\n'

        return StreamingResponse(_empty(), media_type='text/event-stream')

    safe, reason = _is_safe(command)
    if not safe:

        async def _blocked():
            yield f'data: {json.dumps({"type": "error", "data": reason, "exit_code": 1})}\n\n'

        return StreamingResponse(_blocked(), media_type='text/event-stream')

    work_dir = _get_work_dir(cwd)
    run_id = str(uuid.uuid4())[:8]
    audit_log('terminal_run', f'{session}: {command[:80]}')

    # Store in history
    _store_history(session, command, work_dir)

    async def generate():
        """Execute or process generate operation."""
        yield f'data: {json.dumps({"type": "start", "command": command, "cwd": work_dir, "run_id": run_id})}\n\n'
        t0 = time.time()
        proc = None
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=work_dir,
                env={**os.environ, 'TERM': 'xterm-256color', 'FORCE_COLOR': '1'},
            )
            _active_processes[run_id] = proc

            # Stream output line by line
            async for line in proc.stdout:
                text = line.decode('utf-8', errors='replace')
                yield f'data: {json.dumps({"type": "stdout", "data": text})}\n\n'
                await asyncio.sleep(0)  # yield to event loop

            await proc.wait()
            duration = round((time.time() - t0) * 1000)
            yield f'data: {json.dumps({"type": "exit", "exit_code": proc.returncode, "duration_ms": duration, "run_id": run_id})}\n\n'

        except asyncio.CancelledError:
            if proc:
                proc.kill()
            yield f'data: {json.dumps({"type": "exit", "exit_code": -1, "reason": "cancelled"})}\n\n'
        except Exception as e:
            log.error('Terminal error: %s', e)
            yield f'data: {json.dumps({"type": "error", "data": str(e), "exit_code": 1})}\n\n'
        finally:
            _active_processes.pop(run_id, None)

    return StreamingResponse(
        generate(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


@router.post('/kill/{run_id}')
def kill_process(run_id: str):
    """Execute or process kill process operation."""
    proc = _active_processes.get(run_id)
    if proc:
        try:
            proc.kill()
            _active_processes.pop(run_id, None)
            return {'ok': True, 'killed': run_id}
        except Exception as e:
            return {'ok': False, 'error': str(e)}
    return {'ok': False, 'error': 'Process not found'}


@router.get('/history')
def get_history(session_id: str = '', limit: int = 50):
    # FIX 9: try/except so missing table returns [] not 500
    """Retrieve and return get history."""
    try:
        con = get_conn()
        try:
            if session_id:
                rows = con.execute(
                    'SELECT command, cwd, created_at FROM terminal_history WHERE session_id=? ORDER BY id DESC LIMIT ?',
                    (session_id, min(limit, 200)),
                ).fetchall()
            else:
                rows = con.execute(
                    'SELECT DISTINCT command, cwd, created_at FROM terminal_history ORDER BY id DESC LIMIT ?',
                    (min(limit, 200),),
                ).fetchall()
        finally:
            con.close()
        return [dict(r) for r in rows]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return []


@router.delete('/history')
def clear_history(session_id: str = ''):
    # FIX D: try/except so missing table returns ok not 500
    """Delete or remove specified clear history."""
    try:
        con = get_conn()
        try:
            if session_id:
                con.execute('DELETE FROM terminal_history WHERE session_id=?', (session_id,))
            else:
                con.execute('DELETE FROM terminal_history')
            con.commit()
        finally:
            con.close()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        pass
    return {'ok': True}


@router.get('/suggestions')
def command_suggestions(q: str = ''):
    """Smart command suggestions based on project context."""
    suggestions = [
        {'cmd': 'ls -la', 'desc': 'List files'},
        {'cmd': 'git status', 'desc': 'Git status'},
        {'cmd': 'git log --oneline -10', 'desc': 'Recent commits'},
        {'cmd': 'npm install', 'desc': 'Install npm dependencies'},
        {'cmd': 'npm run dev', 'desc': 'Start dev server'},
        {'cmd': 'npm run build', 'desc': 'Build for production'},
        {'cmd': 'pip install -r requirements.txt', 'desc': 'Install Python deps'},
        {'cmd': 'python -m pytest', 'desc': 'Run Python tests'},
        {'cmd': 'node --version', 'desc': 'Check Node version'},
        {'cmd': 'python --version', 'desc': 'Check Python version'},
        {'cmd': 'git diff HEAD', 'desc': 'See all changes'},
        {'cmd': "git add . && git commit -m 'Update'", 'desc': 'Quick commit'},
        {'cmd': 'npx prettier --write .', 'desc': 'Format all files'},
        {'cmd': 'cat package.json', 'desc': 'View package.json'},
        {'cmd': "find . -name '*.js' -not -path './node_modules/*'", 'desc': 'Find JS files'},
    ]
    if q:
        suggestions = [s for s in suggestions if q.lower() in s['cmd'].lower() or q.lower() in s['desc'].lower()]
    return suggestions[:10]


@router.get('/env')
def get_environment():
    """Return safe environment info."""
    return {
        'cwd': str(PREVIEW_DIR),
        'node': _which_version('node'),
        'npm': _which_version('npm'),
        'python': _which_version('python3'),
        'git': _which_version('git'),
        'has_npm': bool(shutil.which('npm')),
        'has_node': bool(shutil.which('node')),
        'has_git': bool(shutil.which('git')),
        'has_python': bool(shutil.which('python3')),
    }


def _which_version(cmd: str) -> str:
    # FIX 16: cap timeout; sync subprocess is acceptable here since this runs once
    # at renderTerminal time (not in the hot path) and has a 2s cap
    import subprocess

    try:
        r = subprocess.run([cmd, '--version'], capture_output=True, text=True, timeout=2)
        return (r.stdout.strip() or r.stderr.strip()).split('\n')[0][:60]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return ''


def _store_history(session_id: str, command: str, cwd: str):
    try:
        con = get_conn()
        try:
            con.execute(
                'INSERT INTO terminal_history(session_id,command,cwd) VALUES(?,?,?)',
                (session_id, command[:500], cwd[:200]),
            )
            # Keep only last 500 per session
            con.execute(
                'DELETE FROM terminal_history WHERE id NOT IN (SELECT id FROM terminal_history WHERE session_id=? ORDER BY id DESC LIMIT 500)',
                (session_id,),
            )
            con.commit()
        finally:
            con.close()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        pass
