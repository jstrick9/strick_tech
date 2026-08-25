"""
Agentic OS — MCP Tool Router (Model Context Protocol)
Exposes a unified tool registry to all agents:
  filesystem, shell, git, browser, postgres stub, http, search
All tools return structured JSON results agents can reason over.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix='/api/mcp', tags=['mcp'])
log = logging.getLogger('agentic.mcp')
from backend.config import get_data_dir

from ..services.request_body import as_text, json_body_or_error
from ..services.safe_paths import is_within

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


@router.get('/catalog')
def tool_catalog_list():
    """The whole tool catalog, local and federated, with totals.

    Generated on every call from the sources. Never hand-maintained -- a
    curated tool map "rots the second I add a server".
    """
    from ..services import tool_catalog

    return {'ok': True, 'tools': tool_catalog.index(), 'stats': tool_catalog.stats()}


@router.get('/catalog/select')
def tool_catalog_select(intent: str = '', limit: int = 0):
    """Show which tools an intent would expose, and why. Read-only."""
    from ..services import tool_catalog

    if not str(intent).strip():
        raise HTTPException(status_code=422, detail='Send intent=<the task>.')
    return {'ok': True,
            'selection': tool_catalog.select(intent, limit=limit or tool_catalog.MAX_EXPOSED)}


@router.get('/catalog/search')
def tool_catalog_search(q: str = '', limit: int = 25):
    """Free-text search over the catalog, for an agent that wants to look."""
    from ..services import tool_catalog

    return {'ok': True, 'tools': tool_catalog.search(q, limit=limit)}


@router.post('/tools/execute')
@router.post('/call')
async def call_tool(req: Request):
    """
    POST /api/mcp/call
    Body: {tool: str, args: dict, agent_id?: str}
    Returns: {ok, result, tool, duration_ms}
    """
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    tool = as_text(body.get('tool'))
    args = body.get('args') or {}
    agent_id = body.get('agent_id', 'system')

    if tool not in TOOLS:
        # 404, not 200. An agent retrying a typo'd tool name against a 200
        # response has no signal that the name itself is the problem.
        return JSONResponse(
            {
                'ok': False,
                'error': f"Unknown tool '{tool}'",
                'available': sorted(TOOLS.keys()),
            },
            status_code=404,
        )

    # PER-AGENT AUTHORISATION. `agent_permissions` has existed since Sprint A
    # and nothing ever consulted it: the agent_id on this endpoint was
    # accepted, logged, echoed back and written to the audit chain without ever
    # being used to make a decision. Verified before this fix, with an agent
    # holding neither write_files nor delete_files:
    #
    #   {"tool":"fs.write",  "agent_id":"probe_readonly"} -> ok, file written
    #   {"tool":"fs.delete", "agent_id":"probe_readonly"} -> ok, file deleted
    #   {"tool":"fs.write",  "agent_id":"i_do_not_exist"} -> ok, file written
    #
    # The last case is the worst: a fictional agent id wrote a file, and the
    # audit entry recorded it as that agent's action. An unenforced identity
    # field is worse than no field, because the trail reads as though
    # authorisation happened.
    from ..services.tool_policy import check_tool_permission, required_action

    _allowed, _reason = check_tool_permission(agent_id, tool)
    if not _allowed:
        from ..services.memory_db import audit_log as _audit

        _audit('mcp_denied', f'{agent_id}:{tool} — {_reason[:160]}')
        log.warning('Tool call DENIED: %s -> %s (%s)', agent_id, tool, _reason)
        return JSONResponse(
            {
                'ok': False,
                'tool': tool,
                'agent_id': agent_id,
                'error': _reason,
                'denied': True,
                'required_permission': required_action(tool),
            },
            status_code=403,
        )

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
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    prompt = as_text(body.get('prompt'))
    agent_id = body.get('agent_id', 'builder')
    max_steps = min(int(body.get('max_steps', 5)), 10)
    allowed = set(body.get('tools') or list(TOOLS.keys()))

    if not prompt:
        return {'ok': False, 'error': 'prompt required'}

    from ..services import llm, memory_db

    agents = {a['id']: a for a in memory_db.agents_list()}
    agent = agents.get(agent_id, {'name': agent_id, 'model': '', 'system_prompt': ''})

    # SCOPED TOOL LOADING. This used to inline every tool in TOOLS into the
    # system prompt on every call, regardless of the task. That is the same
    # mistake ICM exists to prevent, one layer down: past a certain count a
    # model's tool selection degrades rather than improves, and a hand-written
    # per-task map rots the moment a server is added.
    #
    # The catalog also federates the MCP GATEWAY's tools, which no agent could
    # previously reach at all -- measured live before this change: the gateway
    # held 53 tools across 7 servers and this loop could see none of them,
    # while pasting its own 23 into every prompt.
    from ..services import tool_catalog

    if body.get('tools'):
        # An explicit list is a deliberate choice; honour it exactly.
        selection = [t for t in tool_catalog.index() if t['name'] in allowed]
        selection_meta = {'exposed': len(selection), 'total_available': len(tool_catalog.index()),
                          'withheld_by_cap': 0, 'mode': 'explicit'}
    else:
        picked = tool_catalog.select(prompt, limit=int(body.get('max_tools') or tool_catalog.MAX_EXPOSED))
        selection = picked['tools']
        selection_meta = {k: picked[k] for k in
                          ('exposed', 'total_available', 'withheld_by_cap', 'not_relevant', 'tags')}
        selection_meta['mode'] = 'intent'
        allowed = {t['name'] for t in selection}

    tool_docs = tool_catalog.render_for_prompt(selection)
    if not tool_docs:
        # No relevant tool is a real outcome, and the model must be told that
        # rather than handed an empty bullet list it will hallucinate into.
        tool_docs = '(no tools matched this task; answer directly)'

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
        try:
            result = await llm.complete(
                messages, agent_id=agent.get('model') or agent_id, max_tokens=1024, inject_steering=False
            )
        except llm.LLMUnavailableError as exc:
            # Report the tool selection even when the model is unreachable.
            # The selection is the part a user is debugging when they ask "why
            # didn't it use my tool", and discarding it on the error path made
            # that unanswerable exactly when it mattered.
            payload = {
                'ok': False,
                'error': exc.message,
                'code': 'llm_unavailable',
                'model': exc.model,
                'tool_selection': selection_meta,
                'tools_exposed': sorted(allowed),
            }
            return JSONResponse(payload, status_code=200)
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
        # Which tools this run could actually see, and how many were withheld.
        # An agent that silently could not see a tool looks exactly like one
        # that chose not to use it, so the selection is reported, not implied.
        'tool_selection': selection_meta,
        'tools_exposed': sorted(allowed),
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
    # is_within(): component-wise. The old string prefix let a sibling
    # directory named <sandbox>_ESCAPED pass as inside the sandbox.
    if not is_within(resolved, SANDBOXED_DIR):
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
    """Write inside the sandbox, reporting where the file ACTUALLY went.

    _safe_path() clamps an absolute path into the sandbox, which is correct --
    but the response echoed back the path the caller ASKED for. Verified:

        fs.write {"path": "/tmp/mcp_escape.txt"}
        -> {"ok": true, "path": "/tmp/mcp_escape.txt", "bytes_written": 5}
        and /tmp/mcp_escape.txt did not exist; the file was written to
        <sandbox>/preview/tmp/mcp_escape.txt

    An agent told it wrote to /tmp/x will read back /tmp/x, get nothing, and
    have no way to discover why. Reporting a location the write did not happen
    at is the same class of dishonesty as the "success while doing nothing"
    results found in Modules 15 and 19.
    """
    f = _safe_path(path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding='utf-8')

    try:
        relative = str(f.relative_to(SANDBOXED_DIR))
    except ValueError:  # pragma: no cover - _safe_path guarantees containment
        relative = f.name

    result = {'ok': True, 'path': relative, 'bytes_written': len(content.encode())}
    # Compare against the normalised request: '/tmp/x' clamps to 'tmp/x', which
    # differs from the raw input only by the leading slash. Comparing raw
    # strings marked every absolute path as "relocated" while missing none, but
    # comparing normalised ones silently marked NOTHING -- my first version got
    # this backwards and the test caught it. The user needs telling whenever
    # the path they asked for is not the path used.
    if relative != str(path):
        result['requested_path'] = path
        result['note'] = f'Paths are relative to the workspace; written to {relative}'
    return result


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


# ── Shell command validation ───────────────────────────────────────────────────
# The old check was `command.strip().split()[0] not in ALLOWED_CMDS`, then the
# whole string went to asyncio.create_subprocess_shell(). Only the FIRST TOKEN
# was validated while /bin/sh interpreted the rest, so every shell
# metacharacter was a bypass. Verified live against the running server:
#
#   "ls | id"                    -> uid=1000(user) gid=1000(user) groups=...
#   "echo $(whoami)"             -> user
#   "echo x | cat /etc/passwd"   -> root:x:0:0:root:/root:/bin/bash...
#   "echo pwned > /tmp/shell_escape.txt"  -> wrote OUTSIDE the sandbox
#
# This is the Module 12 terminal finding reproduced exactly: a name-based filter
# in front of a shell is not a control, because shell syntax is not
# prefix-structured. That module fixed it in terminal.py and built
# services/sandbox.py for OS-level isolation; this tool never adopted either.
#
# Two changes:
#   1. Parse with shlex and REFUSE shell metacharacters outright. There is no
#      legitimate use of `|`, `;`, `$(`, backticks or redirection in a tool
#      whose contract is "run one allow-listed command".
#   2. Execute with create_subprocess_EXEC on an argv list, so no shell is
#      involved at all, wrapped in the namespace sandbox when available.
#
# Refusing metacharacters loses `ls | grep x`. That is the correct trade: the
# tool's contract is one allow-listed command, and an agent that needs a
# pipeline can call the two tools in sequence.
_SHELL_METACHARACTERS = ('|', ';', '&', '$(', '`', '>', '<', '\n', '\r', '$((')


def _validate_shell_command(command: str) -> list[str]:
    """Return argv for a permitted command, or raise ToolError.

    Returns a token LIST rather than a string so the caller can exec directly
    without a shell.
    """
    import shlex

    raw = (command or '').strip()
    if not raw:
        raise ToolError('Empty command')

    for meta in _SHELL_METACHARACTERS:
        if meta in raw:
            raise ToolError(
                f'Shell metacharacter {meta!r} is not permitted. This tool runs a single '
                f'allow-listed command with arguments; chaining, pipes, substitution and '
                f'redirection are refused.'
            )

    try:
        argv = shlex.split(raw)
    except ValueError as e:
        raise ToolError(f'Could not parse command: {e}') from e

    if not argv:
        raise ToolError('Empty command')

    cmd_name = argv[0]
    if '/' in cmd_name:
        raise ToolError(
            f"Command must be a bare name, not a path: {cmd_name!r}. "
            f'Allowed: {sorted(ALLOWED_CMDS)}'
        )
    if cmd_name not in ALLOWED_CMDS:
        raise ToolError(f"Command '{cmd_name}' not allowed. Allowed: {sorted(ALLOWED_CMDS)}")

    # `git -c <anything>=<cmd>` turns an allow-listed binary into an arbitrary
    # execution primitive (core.pager, alias.*, diff.external, ssh commands).
    # The same shape applies to find -exec and grep's process options.
    _reject_argument_escapes(cmd_name, argv[1:])
    return argv


# Arguments that let an allow-listed binary execute something else.
_ARG_ESCAPES: dict[str, tuple[str, ...]] = {
    'git': ('-c', '--exec-path', '--upload-pack', '--receive-pack', '--config-env'),
    'find': ('-exec', '-execdir', '-ok', '-okdir', '-fprintf', '-fprint'),
    'grep': ('--devices', '-D'),
    'npm': ('--node-options', '--script-shell'),
    'npx': ('-c', '--call', '--shell'),
    'pip': ('--proxy',),
}


def _reject_argument_escapes(cmd_name: str, args: list[str]) -> None:
    """Refuse arguments that turn a permitted binary into arbitrary execution."""
    bad = _ARG_ESCAPES.get(cmd_name)
    if not bad:
        return
    for arg in args:
        head = arg.split('=', 1)[0]
        if head in bad:
            raise ToolError(
                f"'{cmd_name} {head}' is not permitted: it can execute arbitrary commands "
                f'through an allow-listed binary.'
            )


def _shell_exec_argv(argv: list[str], work_dir: str) -> tuple[list[str], str | None, bool]:
    """Wrap argv in the namespace sandbox when the host supports it.

    Module 12 built services/sandbox.py for exactly this and terminal.py uses
    it; this tool never did, so an escape through the filter had the full
    filesystem. Degrades to plain exec where namespaces are unavailable, and
    the caller reports which happened rather than implying isolation.
    """
    import shutil as _shutil

    try:
        from ..services import sandbox as sandbox_svc

        available, _reason = sandbox_svc.sandbox_available()
        if not available:
            return argv, None, False

        # The jail bootstrap ends in os.execv(argv[0], argv), which requires an
        # ABSOLUTE path -- terminal.py happens to pass '/bin/sh' so this never
        # surfaced there. Passing a bare name like 'echo' failed inside the
        # namespace with FileNotFoundError while the endpoint still reported
        # ok:true, which is the "success while doing nothing" shape this review
        # keeps finding. Resolve on the host before entering the jail.
        resolved = _shutil.which(argv[0])
        if not resolved:
            raise ToolError(f"Command not found on this host: {argv[0]!r}")

        wrapped, scratch = sandbox_svc.wrap_command(
            [resolved, *argv[1:]], work_dir, allow_network=False
        )
        return wrapped, scratch, True
    except Exception as e:  # pragma: no cover - isolation is best-effort
        log.warning('mcp shell: sandbox unavailable (%s); running unsandboxed', e)
        return argv, None, False


async def _shell_run(command: str, cwd: str = '') -> dict:
    """Run a single allow-listed command. No shell is involved."""
    argv = _validate_shell_command(command)
    work_dir = str(SANDBOXED_DIR) if not cwd else str(_safe_path(cwd))
    run_argv, scratch, sandboxed = _shell_exec_argv(argv, work_dir)
    # When sandboxed the jail mounts the workspace at /work and chdirs there
    # itself, so cwd must be left alone. Passing work_dir broke the bootstrap:
    # wrap_command() re-enters `python -c "from backend.services.sandbox ..."`
    # behind `env -i`, which drops PYTHONPATH, so the import only resolves from
    # the repo root. Setting cwd to the sandbox dir made EVERY command fail with
    # ModuleNotFoundError while still reporting ok:true — caught because
    # `echo hello world` returned empty stdout, not because the tests were red.
    exec_cwd = None if sandboxed else work_dir
    try:
        proc = await asyncio.create_subprocess_exec(
            *run_argv,
            cwd=exec_cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
        return {
            'stdout': stdout.decode('utf-8', errors='ignore')[:4000],
            'stderr': stderr.decode('utf-8', errors='ignore')[:1000],
            'returncode': proc.returncode,
            'command': command,
            # Reported rather than implied: on a host without namespace support
            # this is the filter alone, which the caller deserves to know.
            'sandboxed': sandboxed,
        }
    except asyncio.TimeoutError:
        raise ToolError('Command timed out (15s)') from None
    except Exception as e:
        raise ToolError(str(e)) from e


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
    """Run a background job. Same validation as _shell_run — see there.

    This path had the SAME first-token-only bypass and, being background, was
    the easier one to overlook. Guarding one and not the other would have left
    the primitive fully reachable.
    """
    argv = _validate_shell_command(command)
    work_dir = str(SANDBOXED_DIR) if not cwd else str(_safe_path(cwd))
    run_argv, _scratch, sandboxed = _shell_exec_argv(argv, work_dir)
    proc = await asyncio.create_subprocess_exec(
        *run_argv,
        cwd=None if sandboxed else work_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    return {
        'ok': True, 'pid': proc.pid, 'command': command,
        'status': 'background_running', 'sandboxed': sandboxed,
    }


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
    """HTTP GET, refusing internal addresses.

    This is an AGENT-CALLABLE tool, which makes it the most dangerous of the
    three SSRF sites found in this module. Verified before the fix:

        {"tool":"http.get","args":{"url":"http://localhost:8787/api/connectors"}}
        -> {"ok": true, ..., "body": "{\"connectors\":[..."}

    The full internal API response, returned to the caller. It also reached
    169.254.169.254 (HTTP 401 — a response, therefore a successful connection).
    Everything this review has said about prompt injection gets materially
    worse when the model holds a primitive that reads arbitrary internal URLs.

    follow_redirects was True, so even a host check on the original URL would
    have been walked past by a 302; safe_request() disables them.
    """
    from ..services.safe_fetch import UnsafeURLError, safe_request

    try:
        resp = await safe_request('GET', url, headers=headers or {}, timeout=10.0)
    except UnsafeURLError as e:
        raise ToolError(str(e)) from e
    except Exception as e:
        raise ToolError(str(e)) from e

    ct = resp.headers.get('content-type', '')
    body = resp.text[:8000] if 'text' in ct or 'json' in ct else f'[binary {len(resp.content)} bytes]'
    return {'url': url, 'status': resp.status_code, 'content_type': ct, 'body': body}


async def _http_post(url: str, body: Any = None, headers: dict = None) -> dict:
    """HTTP POST, refusing internal addresses. See _http_get()."""
    from ..services.safe_fetch import UnsafeURLError, safe_request

    try:
        resp = await safe_request('POST', url, json=body, headers=headers or {}, timeout=10.0)
    except UnsafeURLError as e:
        raise ToolError(str(e)) from e
    except Exception as e:
        raise ToolError(str(e)) from e

    return {'url': url, 'status': resp.status_code, 'body': resp.text[:4000]}


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
            if isinstance(node, _ast.Attribute) and node.attr.startswith('__') and node.attr.endswith('__'):
                raise ToolError('Dunder attribute access not allowed.')
    except ToolError:
        raise
    except Exception as parse_err:
        raise ToolError(f'Code parse error: {parse_err}') from parse_err
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
        raise ToolError('Code execution timed out (5s)') from None
    except Exception as e:
        raise ToolError(str(e)) from e


def _extract_json(text: str) ->dict | None:
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
