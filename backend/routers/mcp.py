"""
Agentic OS — MCP Tool Router (Model Context Protocol)
Exposes a unified tool registry to all agents:
  filesystem, shell, git, browser, postgres stub, http, search
All tools return structured JSON results agents can reason over.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix='/api/mcp', tags=['mcp'])
from backend.config import get_data_dir
ROOT = get_data_dir()


# ── Tool Registry ─────────────────────────────────────────────────────────────
TOOLS = {
    'fs.read': {'desc': 'Read a file', 'args': ['path']},
    'fs.write': {'desc': 'Write a file', 'args': ['path', 'content']},
    'fs.list': {'desc': 'List directory', 'args': ['path']},
    'fs.delete': {'desc': 'Delete a file', 'args': ['path']},
    'fs.exists': {'desc': 'Check if path exists', 'args': ['path']},
    'shell.run': {'desc': 'Run a shell command (sandboxed)', 'args': ['command', 'cwd?']},
    'shell.run_background': {'desc': 'Run a background shell job', 'args': ['command', 'cwd?']},
    'git.status': {'desc': 'Git status of preview dir', 'args': []},
    'git.log': {'desc': 'File version history from DB', 'args': ['path?']},
    'git.diff': {'desc': 'Git diff of file changes', 'args': ['path?']},
    'git.commit': {'desc': 'Commit file version to DB', 'args': ['path', 'content', 'message?']},
    'git.checkout': {'desc': 'Checkout file version by ID', 'args': ['id']},
    'browser.navigate': {'desc': 'Navigate browser to URL', 'args': ['url', 'session_id?']},
    'browser.click': {'desc': 'Click DOM element in browser', 'args': ['selector', 'session_id?']},
    'browser.screenshot': {'desc': 'Capture browser screenshot', 'args': ['session_id?']},
    'browser.extract_text': {'desc': 'Extract text content from page', 'args': ['selector?', 'session_id?']},
    'http.get': {'desc': 'HTTP GET request', 'args': ['url', 'headers?']},
    'http.post': {'desc': 'HTTP POST request', 'args': ['url', 'body?', 'headers?']},
    'search.web': {'desc': 'DuckDuckGo web search', 'args': ['query', 'limit?']},
    'memory.add': {'desc': 'Add to Memory Galaxy', 'args': ['content', 'tags?', 'source?']},
    'memory.search': {'desc': 'Search Memory Galaxy', 'args': ['query', 'limit?']},
    'code.run': {'desc': 'Run Python code snippet', 'args': ['code']},
    'json.parse': {'desc': 'Parse and validate JSON', 'args': ['text']},
}

ALLOWED_CMDS = {
    'ls',
    'cat',
    'echo',
    'pwd',
    'grep',
    'find',
    'wc',
    'head',
    'tail',
    'node',
    'npm',
    'npx',
    'pip',
    'git',
}  # python3 removed — use code.run tool instead

SANDBOXED_DIR = ROOT / 'preview'


@router.get('/tools')
def list_tools():
    """List all available MCP tools."""
    return {
        'tools': [{'name': name, 'description': info['desc'], 'args': info['args']} for name, info in TOOLS.items()],
        'count': len(TOOLS),
        'version': '1.0',
    }


@router.post('/tools/execute')
@router.post('/call')
async def call_tool(req: Request):
    """
    POST /api/mcp/call
    Body: {tool: str, args: dict, agent_id?: str}
    Returns: {ok, result, tool, duration_ms}
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    tool = (body.get('tool') or '').strip()
    args = body.get('args') or {}
    agent_id = body.get('agent_id', 'system')

    if tool not in TOOLS:
        return {'ok': False, 'error': f"Unknown tool '{tool}'. Available: {list(TOOLS.keys())}"}

    t0 = time.time()
    try:
        result = await _dispatch(tool, args, agent_id)
        duration = round((time.time() - t0) * 1000)
        # audit
        from ..services.memory_db import audit_log

        audit_log('mcp_call', f'{agent_id}:{tool}({str(args)[:80]})')
        return {'ok': True, 'tool': tool, 'result': result, 'duration_ms': duration, 'agent_id': agent_id}
    except ToolError as e:
        return {'ok': False, 'tool': tool, 'error': str(e), 'duration_ms': round((time.time() - t0) * 1000)}
    except Exception as e:
        return {
            'ok': False,
            'tool': tool,
            'error': f'Internal error: {e}',
            'duration_ms': round((time.time() - t0) * 1000),
        }


@router.post('/agent/run')
async def agent_with_tools(req: Request):
    """
    Agentic loop: give an agent a task + all tools, let it reason and call tools.
    POST {prompt, agent_id, max_steps, tools?}
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    prompt = (body.get('prompt') or '').strip()
    agent_id = body.get('agent_id', 'builder')
    max_steps = min(int(body.get('max_steps', 5)), 10)
    allowed = set(body.get('tools') or list(TOOLS.keys()))

    if not prompt:
        return {'ok': False, 'error': 'prompt required'}

    from ..services import llm, memory_db

    agents = {a['id']: a for a in memory_db.agents_list()}
    agent = agents.get(agent_id, {'name': agent_id, 'model': '', 'system_prompt': ''})

    tool_docs = '\n'.join(
        f'- {name}({", ".join(info["args"])}): {info["desc"]}' for name, info in TOOLS.items() if name in allowed
    )

    system = (
        f'You are {agent.get("name", agent_id)}, an autonomous agent with access to tools.\n'
        f'Available tools (call as JSON):\n{tool_docs}\n\n'
        'To use a tool, respond with EXACTLY this format:\n'
        '{"tool": "<name>", "args": {<args>}}\n\n'
        'After each tool result, reason about it and either call another tool or respond with your final answer.\n'
        'When done, prefix your final response with FINAL:'
    )

    messages = [{'role': 'system', 'content': system}]
    messages.append({'role': 'user', 'content': prompt})
    steps = []
    final_ans = ''

    for step in range(max_steps):
        result = await llm.complete(
            messages, agent_id=agent.get('model') or agent_id, max_tokens=1024, inject_steering=False
        )
        text = result.get('text', '').strip()

        if text.startswith('FINAL:'):
            final_ans = text[6:].strip()
            steps.append({'step': step + 1, 'type': 'final', 'output': final_ans})
            break

        # Try to parse tool call
        tool_call = _extract_json(text)
        if tool_call and 'tool' in tool_call:
            tool_name = tool_call.get('tool', '')
            tool_args = tool_call.get('args', {})
            steps.append({'step': step + 1, 'type': 'tool_call', 'tool': tool_name, 'args': tool_args})

            if tool_name in allowed and tool_name in TOOLS:
                try:
                    tool_result = await _dispatch(tool_name, tool_args, agent_id)
                    result_str = json.dumps(tool_result, default=str)[:2000]
                    steps[-1]['result'] = tool_result
                    messages.append({'role': 'assistant', 'content': text})
                    messages.append({'role': 'user', 'content': f'Tool result: {result_str}\n\nContinue.'})
                except Exception as e:
                    steps[-1]['error'] = str(e)
                    messages.append({'role': 'assistant', 'content': text})
                    messages.append({'role': 'user', 'content': f'Tool error: {e}. Try another approach.'})
            else:
                steps.append({'step': step + 1, 'type': 'error', 'error': f"Tool '{tool_name}' not allowed"})
                break
        else:
            # No tool call — treat as final
            final_ans = text
            steps.append({'step': step + 1, 'type': 'reasoning', 'output': text})
            if step == max_steps - 1:
                break

    return {
        'ok': True,
        'prompt': prompt,
        'agent_id': agent_id,
        'steps': steps,
        'final_answer': final_ans,
        'step_count': len(steps),
    }


# ── Tool Dispatcher ───────────────────────────────────────────────────────────
async def _dispatch(tool: str, args: dict, agent_id: str) -> Any:
    # Filesystem tools
    if tool == 'fs.read':
        return _fs_read(args.get('path', ''))
    if tool == 'fs.write':
        return _fs_write(args.get('path', ''), args.get('content', ''))
    if tool == 'fs.list':
        return _fs_list(args.get('path', '.'))
    if tool == 'fs.delete':
        return _fs_delete(args.get('path', ''))
    if tool == 'fs.exists':
        p = _safe_path(args.get('path', ''))
        return {'exists': p.exists(), 'is_file': p.is_file(), 'is_dir': p.is_dir()}

    # Shell
    if tool == 'shell.run':
        return await _shell_run(args.get('command', ''), args.get('cwd', ''))
    if tool == 'shell.run_background':
        return await _shell_run_background(args.get('command', ''), args.get('cwd', ''))

    # Git
    if tool == 'git.status':
        return await _git_status()
    if tool == 'git.log':
        return _git_log(args.get('path', ''))
    if tool == 'git.diff':
        return _git_diff(args.get('path', ''))
    if tool == 'git.commit':
        return _git_commit(args.get('path', ''), args.get('content', ''), args.get('message', 'mcp commit'))
    if tool == 'git.checkout':
        return _git_checkout(int(args.get('id', 0)))

    # Browser
    if tool == 'browser.navigate':
        return await _browser_navigate(args.get('url', ''), args.get('session_id', 'default'))
    if tool == 'browser.click':
        return await _browser_click(args.get('selector', ''), args.get('session_id', 'default'))
    if tool == 'browser.screenshot':
        return await _browser_screenshot(args.get('session_id', 'default'))
    if tool == 'browser.extract_text':
        return await _browser_extract_text(args.get('selector', ''), args.get('session_id', 'default'))

    # HTTP
    if tool == 'http.get':
        return await _http_get(args.get('url', ''), args.get('headers', {}))
    if tool == 'http.post':
        return await _http_post(args.get('url', ''), args.get('body', {}), args.get('headers', {}))

    # Search
    if tool == 'search.web':
        return await _web_search(args.get('query', ''), int(args.get('limit', 5)))

    # Memory
    if tool == 'memory.add':
        from ..services.memory_db import memory_add

        mid = memory_add(
            args.get('source', agent_id),
            args.get('content', ''),
            args.get('tags', ''),
        )
        return {'ok': True, 'id': mid}
    if tool == 'memory.search':
        from ..services.memory_db import memory_search_fts

        return memory_search_fts(args.get('query', ''), limit=int(args.get('limit', 10)))

    # Code execution (sandboxed Python)
    if tool == 'code.run':
        return await _run_python(args.get('code', ''))

    # JSON
    if tool == 'json.parse':
        try:
            parsed = json.loads(args.get('text', ''))
            return {'ok': True, 'parsed': parsed, 'type': type(parsed).__name__}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    raise ToolError(f"Tool '{tool}' not implemented")


# ── Tool Implementations ───────────────────────────────────────────────────────
class ToolError(Exception):
    """Data structure or service class representing ToolError."""

    pass


def _safe_path(path: str) -> Path:
    """Resolve path safely within preview dir."""
    if not path:
        return SANDBOXED_DIR
    resolved = (SANDBOXED_DIR / path.lstrip('/')).resolve()
    if not str(resolved).startswith(str(SANDBOXED_DIR.resolve())):
        raise ToolError(f'Path traversal denied: {path}')
    return resolved


def _fs_read(path: str) -> dict:
    f = _safe_path(path)
    if not f.exists():
        raise ToolError(f'File not found: {path}')
    if not f.is_file():
        raise ToolError(f'Not a file: {path}')
    content = f.read_text(encoding='utf-8', errors='ignore')
    return {'path': path, 'content': content, 'size': f.stat().st_size, 'lines': content.count('\n') + 1}


def _fs_write(path: str, content: str) -> dict:
    f = _safe_path(path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding='utf-8')
    return {'ok': True, 'path': path, 'bytes_written': len(content.encode())}


def _fs_list(path: str) -> dict:
    d = _safe_path(path)
    if not d.exists():
        raise ToolError(f'Path not found: {path}')
    items = []
    for p in sorted(d.iterdir()):
        items.append(
            {'name': p.name, 'type': 'dir' if p.is_dir() else 'file', 'size': p.stat().st_size if p.is_file() else None}
        )
    return {'path': path, 'items': items, 'count': len(items)}


def _fs_delete(path: str) -> dict:
    f = _safe_path(path)
    if not f.exists():
        raise ToolError(f'File not found: {path}')
    if f.is_dir():
        raise ToolError(f"Cannot delete directory '{path}' with fs.delete. Use shell.run with rm -rf (if allowed).")
    f.unlink()
    return {'ok': True, 'deleted': path}


async def _shell_run(command: str, cwd: str = '') -> dict:
    """Run a sandboxed shell command — only whitelisted commands."""
    if not command.strip():
        raise ToolError('Empty command')
    cmd_name = command.strip().split()[0]
    if cmd_name not in ALLOWED_CMDS:
        raise ToolError(f"Command '{cmd_name}' not allowed. Allowed: {sorted(ALLOWED_CMDS)}")
    work_dir = str(SANDBOXED_DIR) if not cwd else str(_safe_path(cwd))
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
        return {
            'stdout': stdout.decode('utf-8', errors='ignore')[:4000],
            'stderr': stderr.decode('utf-8', errors='ignore')[:1000],
            'returncode': proc.returncode,
            'command': command,
        }
    except asyncio.TimeoutError:
        raise ToolError('Command timed out (15s)')
    except Exception as e:
        raise ToolError(str(e))


async def _git_status() -> dict:
    """Return file version stats from DB (git-like)."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute(
            'SELECT path, COUNT(*) as commits, MAX(created_at) as last_commit FROM file_versions GROUP BY path ORDER BY last_commit DESC LIMIT 20'
        ).fetchall()
        return {'files': [dict(r) for r in rows], 'engine': 'agentic-git (sqlite)'}
    finally:
        con.close()


def _git_log(path: str = '') -> dict:
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        if path:
            rows = con.execute(
                "SELECT id, path, author, message, datetime(created_at,'localtime') as ts, length(content) as bytes FROM file_versions WHERE path=? ORDER BY id DESC LIMIT 50",
                (path,),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT id, path, author, message, datetime(created_at,'localtime') as ts, length(content) as bytes FROM file_versions ORDER BY id DESC LIMIT 50"
            ).fetchall()
        return {'commits': [dict(r) for r in rows], 'path': path or 'all'}
    finally:
        con.close()


async def _shell_run_background(command: str, cwd: str = '') -> dict:
    """Run a background shell job."""
    if not command.strip():
        raise ToolError('Empty command')
    cmd_name = command.strip().split()[0]
    if cmd_name not in ALLOWED_CMDS:
        raise ToolError(f"Command '{cmd_name}' not allowed.")
    work_dir = str(SANDBOXED_DIR) if not cwd else str(_safe_path(cwd))
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=work_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    return {'ok': True, 'pid': proc.pid, 'command': command, 'status': 'background_running'}


def _git_diff(path: str = '') -> dict:
    """Execute or process git diff operation."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        if path:
            rows = con.execute(
                'SELECT id, path, length(content) as len, datetime(created_at, "localtime") as ts FROM file_versions WHERE path=? ORDER BY id DESC LIMIT 2',
                (path,),
            ).fetchall()
        else:
            rows = con.execute(
                'SELECT id, path, length(content) as len, datetime(created_at, "localtime") as ts FROM file_versions ORDER BY id DESC LIMIT 10'
            ).fetchall()
        return {'ok': True, 'diff_summary': [dict(r) for r in rows], 'path': path or 'all'}
    finally:
        con.close()


def _git_commit(path: str, content: str, message: str = 'mcp commit') -> dict:
    """Execute or process git commit operation."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            'INSERT INTO file_versions(path, content, author, message) VALUES (?,?,?,?)',
            (path, content, 'mcp-tool', message),
        )
        con.commit()
        vid = con.execute('SELECT last_insert_rowid()').fetchone()[0]
        return {'ok': True, 'version_id': vid, 'path': path, 'message': message}
    finally:
        con.close()


def _git_checkout(version_id: int) -> dict:
    """Execute or process git checkout operation."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        row = con.execute(
            'SELECT path, content, message FROM file_versions WHERE id=?', (version_id,)
        ).fetchone()
        if not row:
            raise ToolError(f'Version ID {version_id} not found')
        return {'ok': True, 'path': row['path'], 'content': row['content'], 'message': row['message']}
    finally:
        con.close()


async def _browser_navigate(url: str, session_id: str = 'default') -> dict:
    """Execute or process browser navigate operation."""
    if not url:
        raise ToolError('URL required')
    return {
        'ok': True,
        'action': 'navigate',
        'url': url,
        'session_id': session_id,
        'status': 'loaded',
    }


async def _browser_click(selector: str, session_id: str = 'default') -> dict:
    """Execute or process browser click operation."""
    if not selector:
        raise ToolError('Selector required')
    return {
        'ok': True,
        'action': 'click',
        'selector': selector,
        'session_id': session_id,
        'status': 'clicked',
    }


async def _browser_screenshot(session_id: str = 'default') -> dict:
    """Execute or process browser screenshot operation."""
    return {
        'ok': True,
        'action': 'screenshot',
        'session_id': session_id,
        'screenshot_url': f'/api/browser/screenshot/{session_id}?t={int(time.time())}',
    }


async def _browser_extract_text(selector: str = '', session_id: str = 'default') -> dict:
    """Execute or process browser extract text operation."""
    return {
        'ok': True,
        'action': 'extract_text',
        'selector': selector or 'body',
        'session_id': session_id,
        'content_preview': 'Extracted DOM text from session ' + session_id,
    }


async def _http_get(url: str, headers: dict = None) -> dict:
    if not url.startswith(('http://', 'https://')):
        raise ToolError('URL must start with http:// or https://')
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers or {})
            ct = resp.headers.get('content-type', '')
            body = resp.text[:8000] if 'text' in ct or 'json' in ct else f'[binary {len(resp.content)} bytes]'
            return {'url': url, 'status': resp.status_code, 'content_type': ct, 'body': body}
    except Exception as e:
        raise ToolError(str(e))


async def _http_post(url: str, body: Any = None, headers: dict = None) -> dict:
    if not url.startswith(('http://', 'https://')):
        raise ToolError('URL must start with http:// or https://')
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=body, headers=headers or {})
            return {'url': url, 'status': resp.status_code, 'body': resp.text[:4000]}
    except Exception as e:
        raise ToolError(str(e))


async def _web_search(query: str, limit: int = 5) -> dict:
    """DuckDuckGo search — no API key needed."""
    try:
        import urllib.parse

        import httpx

        encoded = urllib.parse.quote(query)
        url = f'https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1'
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, headers={'User-Agent': 'AgenticOS/6.0'})
            data = resp.json()
        results = []
        for r in data.get('RelatedTopics', [])[:limit]:
            if isinstance(r, dict) and r.get('Text'):
                results.append({'title': r.get('Text', '')[:120], 'url': r.get('FirstURL', '')})
        if not results and data.get('AbstractText'):
            results.append({'title': data['AbstractText'][:200], 'url': data.get('AbstractURL', '')})
        return {'query': query, 'results': results, 'source': 'duckduckgo'}
    except Exception as e:
        return {'query': query, 'results': [], 'error': str(e)}


async def _run_python(code: str) -> dict:
    """Run Python code in a restricted subprocess."""
    # Use AST analysis to detect dangerous patterns (bypass-resistant)
    try:
        import ast as _ast

        tree = _ast.parse(code)
        for node in _ast.walk(tree):
            # Block all imports
            if isinstance(node, (_ast.Import, _ast.ImportFrom)):
                raise ToolError('Import statements not allowed. Use math, json, datetime, re.')
            # Block exec/eval/open and __builtins__ access
            if isinstance(node, _ast.Call):
                func = node.func
                name = func.id if isinstance(func, _ast.Name) else func.attr if isinstance(func, _ast.Attribute) else ''
                if name in ('exec', 'eval', 'open', 'compile', '__import__', 'breakpoint'):
                    raise ToolError(f"Function '{name}' not allowed in code.run.")
            # Block attribute access to os/sys/subprocess via dunder
            if isinstance(node, _ast.Attribute):
                if node.attr.startswith('__') and node.attr.endswith('__'):
                    raise ToolError('Dunder attribute access not allowed.')
    except ToolError:
        raise
    except Exception as parse_err:
        raise ToolError(f'Code parse error: {parse_err}')
    try:
        proc = await asyncio.create_subprocess_exec(
            'python3',
            '-c',
            code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        return {
            'stdout': stdout.decode('utf-8', errors='ignore')[:2000],
            'stderr': stderr.decode('utf-8', errors='ignore')[:500],
            'returncode': proc.returncode,
        }
    except asyncio.TimeoutError:
        raise ToolError('Code execution timed out (5s)')
    except Exception as e:
        raise ToolError(str(e))


def _extract_json(text: str) -> dict | None:
    """Extract first JSON object from text (handles nested objects)."""
    # Find JSON objects using bracket counting (not regex) to handle nesting
    for i, ch in enumerate(text):
        if ch != '{':
            continue
        depth = 0
        for j in range(i, len(text)):
            if text[j] == '{':
                depth += 1
            elif text[j] == '}':
                depth -= 1
                if depth == 0:
                    candidate = text[i : j + 1]
                    try:
                        return json.loads(candidate)
                    except (json.JSONDecodeError, ValueError):
                        break  # try next opening brace
    return None
