"""
Agentic OS — Integrated Terminal Router
Real shell execution inside Agentic OS. Run npm, pip, git, and any command.
Output streams via SSE. History persisted. Kill support.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shlex
import shutil
import signal
import time
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

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
    'export',
    'cd',
    'clear',
    # Ordinary, side-effect-free shell utilities. Their absence meant a plain
    # `printf 'a\nb'` or `false` was rejected as "not in the permitted command
    # list", which is confusing for a terminal that advertises real shell use.
    'printf',
    'true',
    'false',
    'sort',
    'uniq',
    'diff',
    'date',
    'basename',
    'dirname',
    'realpath',
    'stat',
    'du',
    'df',
    'sed',
    'awk',
    'tr',
    'cut',
    'tee',
    'yarn',
    'pnpm',
    'make',
    'cargo',
    'go',
    'rustc',
    'tsc',
    'jq',
}

# SECURITY: 'env' / 'printenv' are intentionally excluded from SAFE_PREFIXES.
# The terminal subprocess previously inherited the full server process
# environment (os.environ), which can hold decrypted API keys and other
# secrets injected by the Vault at startup. Dumping env vars must never be
# a permitted terminal action. See _sandboxed_env() below for the
# defense-in-depth fix applied to the subprocess environment itself.

# Minimal environment variable names that terminal subprocesses are allowed
# to inherit. Deliberately excludes anything that could carry secrets
# (API keys, tokens, vault material) — those are injected into os.environ
# by backend/routers/secrets.py at startup and must never reach a
# user-invoked shell command.
_SAFE_ENV_PASSTHROUGH = {
    'PATH', 'HOME', 'USER', 'LOGNAME', 'SHELL',
    'LANG', 'LC_ALL', 'LC_CTYPE', 'TMPDIR', 'TEMP', 'TMP',
    'PYTHONIOENCODING', 'PYTHONUNBUFFERED',
    'NODE_PATH', 'NPM_CONFIG_PREFIX',
}


def _sandboxed_env() -> dict:
    """Build a minimal, secret-free environment for terminal subprocesses.

    Only a curated allowlist of variables needed for common dev tools
    (node/npm/pip/git/python) is passed through. Everything else —
    including OPENROUTER_API_KEY, ANTHROPIC_API_KEY, GITHUB_TOKEN,
    SECRET_KEY, and any other vault-injected secret — is stripped, so
    it can never be exfiltrated via `env`, `python3 -c "...os.environ..."`,
    `node -e "...process.env..."`, or similar indirect leaks.
    """
    safe = {k: v for k, v in os.environ.items() if k in _SAFE_ENV_PASSTHROUGH}
    safe['TERM'] = 'xterm-256color'
    safe['FORCE_COLOR'] = '1'
    return safe

# Commands that are general-purpose interpreters or can otherwise execute
# arbitrary code. Allowlisting the *command name* is meaningless for these:
# `cat /etc/passwd` is refused by the path filter, but
# `python3 -c "print(open('/etc/pas'+'swd').read())"` was permitted and worked.
# Verified live before this fix — it printed the file.
#
# They stay in SAFE_PREFIXES because running project scripts is the whole point
# of an integrated terminal. What is now refused is the inline-code and
# stdin-program forms, which exist only to smuggle a payload past the filter.
# `python3 manage.py migrate`, `node server.js` and `npm run build` are
# unaffected.
_INTERPRETERS = {'python', 'python3', 'node', 'npx'}
_INLINE_CODE_FLAGS = {'-c', '-e', '--eval', '-p', '--print', '--input-type'}


def _blocks_inline_code(tokens: list[str]) -> str:
    """Return a reason if `tokens` invoke an interpreter with inline code."""
    if not tokens:
        return ''
    name = tokens[0].split('/')[-1]
    if name not in _INTERPRETERS:
        return ''
    for tok in tokens[1:]:
        if tok in _INLINE_CODE_FLAGS:
            return (
                f"Command blocked: '{name} {tok}' runs inline code, which bypasses "
                f'the command and path restrictions. Put the code in a file inside '
                f'the workspace and run that instead.'
            )
        # `python3 -` reads the program from stdin.
        if tok == '-':
            return f"Command blocked: '{name} -' reads a program from stdin"
        # Stop at the first non-flag: that's the script name, which is fine.
        if not tok.startswith('-'):
            break
    return ''


# Commands that read from stdin and will simply hang. stdin is /dev/null for
# these subprocesses, so an interactive prompt waits forever and is then killed
# by the runtime cap — the user sees a timeout with no explanation of why.
# Naming the non-interactive flag is far more useful than a generic failure.
_INTERACTIVE_HINTS = {
    ('npm', 'init'): 'npm init -y',
    ('yarn', 'init'): 'yarn init -y',
    ('pnpm', 'init'): 'pnpm init',
    ('npm', 'login'): None,
    ('npm', 'adduser'): None,
    ('git', 'rebase'): 'git rebase --no-editor, or avoid -i',
    ('git', 'commit'): 'git commit -m "message"',
    ('git', 'tag'): 'git tag -m "message" <name>',
    ('git', 'merge'): 'git merge --no-edit',
    ('git', 'add'): 'git add <paths> (without -p/--patch)',
}
_INTERACTIVE_FLAGS = {'-i', '--interactive', '-p', '--patch', '-e', '--edit'}


def _blocks_interactive(tokens: list[str]) -> str:
    """Return a reason if `tokens` would block waiting for input."""
    if len(tokens) < 2:
        return ''
    cmd = tokens[0].split('/')[-1]
    sub_cmd = tokens[1]
    key = (cmd, sub_cmd)
    rest = tokens[2:]

    if key in {('git', 'rebase'), ('git', 'add')}:
        if not any(f in rest for f in _INTERACTIVE_FLAGS):
            return ''
    elif key in {('git', 'commit'), ('git', 'tag'), ('git', 'merge')}:
        # These only prompt when no message/flag is supplied.
        if any(f.startswith(('-m', '--message', '--no-edit', '-F', '--file')) for f in rest):
            return ''
    elif key in {('npm', 'init'), ('yarn', 'init'), ('pnpm', 'init')}:
        if any(f in {'-y', '--yes'} for f in rest):
            return ''
    elif key not in _INTERACTIVE_HINTS:
        return ''

    if key not in _INTERACTIVE_HINTS:
        return ''
    hint = _INTERACTIVE_HINTS[key]
    base = (
        f"Command blocked: '{cmd} {sub_cmd}' waits for interactive input, and this "
        f'terminal has no stdin — it would hang until the {MAX_RUNTIME_S}s timeout.'
    )
    return f'{base} Try: {hint}' if hint else base


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

# ── Authorisation ─────────────────────────────────────────────────────────────
# This endpoint runs shell commands as the server user. There was no
# authorisation on it at all: anyone who could reach the API had a shell.
#
# That is defensible for a single-user desktop OS bound to 127.0.0.1, so the
# default preserves it rather than breaking every existing install. What is NOT
# defensible is the same behaviour when the server is reachable from the
# network, which is exactly the case nobody notices until it matters.
#
#   * bound to loopback  -> allowed, as before
#   * bound to 0.0.0.0   -> an API key is REQUIRED (401 without one)
#   * TERMINAL_REQUIRE_AUTH=1 -> always require a key
#   * TERMINAL_DISABLED=1     -> refuse outright (403)
_LOOPBACK_HOSTS = {'127.0.0.1', '::1', 'localhost', ''}


def _bound_to_loopback() -> bool:
    """True when the server is only reachable from this machine."""
    host = os.getenv('AGENTIC_OS_HOST', '127.0.0.1').strip()
    return host in _LOOPBACK_HOSTS


def _auth_required() -> bool:
    if os.getenv('TERMINAL_REQUIRE_AUTH', '').strip() in {'1', 'true', 'yes'}:
        return True
    return not _bound_to_loopback()


async def _check_terminal_access(req: Request) -> JSONResponse | None:
    """Return a refusal response if this caller may not run commands."""
    if os.getenv('TERMINAL_DISABLED', '').strip() in {'1', 'true', 'yes'}:
        return JSONResponse(
            {
                'ok': False,
                'error': 'The terminal is disabled on this server (TERMINAL_DISABLED=1).',
                'code': 'terminal_disabled',
            },
            status_code=403,
        )
    if not _auth_required():
        return None
    try:
        from .auth import require_api_key

        # require_api_key() returns None when NO users are registered, treating
        # "auth not configured yet" as "auth not needed". For most endpoints
        # that is a reasonable first-run convenience; for a shell reachable
        # from the network it is a fail-open hole. Verified live: with
        # TERMINAL_REQUIRE_AUTH=1 and an empty user table, `echo hi` ran.
        # Here, no users configured means nobody is authorised.
        user_id = await require_api_key(req)
        if user_id is None:
            return JSONResponse(
                {
                    'ok': False,
                    'error': (
                        'The terminal requires authentication when the server is not bound '
                        'to loopback, but no users are registered. Create one via '
                        'POST /api/auth/register, or bind the server to 127.0.0.1.'
                    ),
                    'code': 'terminal_no_users',
                },
                status_code=401,
            )
    except HTTPException as exc:
        return JSONResponse(
            {
                'ok': False,
                'error': (
                    f'{exc.detail}. The terminal executes shell commands, so it requires '
                    f'authentication when the server is not bound to loopback.'
                ),
                'code': 'terminal_auth_required',
            },
            status_code=exc.status_code,
        )
    except Exception as exc:  # auth backend unavailable — fail CLOSED here
        log.error('Terminal auth check failed: %s', exc)
        return JSONResponse(
            {
                'ok': False,
                'error': 'Authorisation could not be verified; refusing to run a command.',
                'code': 'terminal_auth_unavailable',
            },
            status_code=503,
        )
    return None


# ── OS-level resource limits ──────────────────────────────────────────────────
# The command filter can only ever enumerate badness. These caps are enforced by
# the kernel and apply no matter what the command turns out to be: a fork bomb,
# a memory hog, or a script that writes until the disk fills.
TERMINAL_CPU_SECONDS = int(os.getenv('TERMINAL_CPU_SECONDS', '60'))
TERMINAL_MEMORY_MB = int(os.getenv('TERMINAL_MEMORY_MB', '2048'))
TERMINAL_MAX_FILE_MB = int(os.getenv('TERMINAL_MAX_FILE_MB', '512'))
TERMINAL_MAX_PROCS = int(os.getenv('TERMINAL_MAX_PROCS', '256'))


def _apply_rlimits() -> None:
    """preexec_fn for the subprocess: cap CPU, memory, file size and forks.

    Runs in the forked child before exec. Failures are swallowed deliberately —
    a platform that lacks a given limit should still run the command, just
    without that particular cap.
    """
    try:
        import resource
    except ImportError:  # non-POSIX
        return

    def _set(what, soft):
        try:
            hard = resource.getrlimit(what)[1]
            if hard != resource.RLIM_INFINITY:
                soft = min(soft, hard)
            resource.setrlimit(what, (soft, hard))
        except (ValueError, OSError):
            pass

    if TERMINAL_CPU_SECONDS > 0:
        _set(resource.RLIMIT_CPU, TERMINAL_CPU_SECONDS)
    if TERMINAL_MEMORY_MB > 0 and hasattr(resource, 'RLIMIT_AS'):
        _set(resource.RLIMIT_AS, TERMINAL_MEMORY_MB * 1024 * 1024)
    if TERMINAL_MAX_FILE_MB > 0:
        _set(resource.RLIMIT_FSIZE, TERMINAL_MAX_FILE_MB * 1024 * 1024)
    if TERMINAL_MAX_PROCS > 0 and hasattr(resource, 'RLIMIT_NPROC'):
        _set(resource.RLIMIT_NPROC, TERMINAL_MAX_PROCS)
    # Never leave a core dump behind from a killed command.
    with contextlib.suppress(Exception):
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

# A command had no server-side time limit at all: `sleep 12` ran for the full
# 12 seconds, and nothing stopped a command running indefinitely, holding a
# subprocess and an SSE connection open forever. Output was equally unbounded —
# a loop printing 200-byte lines streamed until the client gave up.
MAX_RUNTIME_S = int(os.getenv('TERMINAL_TIMEOUT_S', '300'))
MAX_OUTPUT_BYTES = int(os.getenv('TERMINAL_MAX_OUTPUT_BYTES', str(2 * 1024 * 1024)))


def _terminate_tree(proc, sig: int) -> None:
    """Signal the whole process group, falling back to the direct child.

    Killing only `proc` leaves grandchildren orphaned (see start_new_session
    above). os.killpg targets everything the command spawned.
    """
    if proc is None or proc.returncode is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), sig)
    except (ProcessLookupError, PermissionError, OSError):
        with contextlib.suppress(ProcessLookupError, OSError):
            proc.kill()


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

    # Output redirection writes anywhere the server user can write, regardless
    # of the cwd sandbox. Verified live before this fix:
    # `echo pwned > /tmp/terminal_pwn.txt` created that file.
    # `>` inside quotes (e.g. grep '>') is not redirection, so check unquoted.
    if '>' in cmd_unquoted:
        return False, "Command blocked: output redirection ('>') is not permitted"

    # Interpreters running inline code sidestep every rule above.
    try:
        tokens = shlex.split(cmd_stripped)
    except ValueError:
        # Unbalanced quotes — the shell would reject it anyway, and we cannot
        # reason about the tokens, so refuse rather than guess.
        return False, 'Command blocked: unbalanced quotes'
    reason = _blocks_inline_code(tokens)
    if reason:
        return False, reason

    reason = _blocks_interactive(tokens)
    if reason:
        return False, reason

    return True, ''


def _get_work_dir(cwd: str = '') -> str:
    """Resolve a working directory, constrained to the PREVIEW_DIR subtree.

    BUG FIX: containment was `str(resolved).startswith(str(PREVIEW_DIR))` — a
    prefix test on a *string*, not on path components. `../preview_ESCAPED`
    resolves to `<root>/preview_ESCAPED`, which does start with
    `<root>/preview`, so it passed. Verified live: a shell was launched with
    cwd=/home/user/repo/preview_ESCAPED, outside the sandbox.

    This is the same defect fixed in imagegen._safe_preview_path during the
    Module 10 review; it is far more serious here because the value becomes the
    cwd of a real subprocess. Path.relative_to() compares components, so a
    sibling directory whose name merely begins with "preview" cannot slip
    through.

    An unresolvable or out-of-tree cwd falls back to PREVIEW_DIR rather than
    raising, matching the previous contract.
    """
    if cwd:
        try:
            resolved = (PREVIEW_DIR / str(cwd).lstrip('/')).resolve()
            resolved.relative_to(PREVIEW_DIR.resolve())
            if resolved.is_dir():
                return str(resolved)
        except (ValueError, OSError):
            pass
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

    denied = await _check_terminal_access(req)
    if denied is not None:
        return denied

    # A rejected command never opens a stream, so it can carry a real status
    # code. These returned HTTP 200 with the refusal buried in an SSE frame,
    # which is indistinguishable from a successful run to any non-SSE client.
    if not command:
        return JSONResponse({'ok': False, 'error': 'No command provided'}, status_code=400)

    safe, reason = _is_safe(command)
    if not safe:
        return JSONResponse({'ok': False, 'error': reason, 'blocked': True}, status_code=403)

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
                env=_sandboxed_env(),
                # No stdin: a command that prompts must fail fast rather than
                # hold a subprocess and an SSE connection until the timeout.
                stdin=asyncio.subprocess.DEVNULL,
                preexec_fn=_apply_rlimits,
                # Run in its own process group. create_subprocess_shell spawns
                # `sh -c <command>`, so proc.kill() only kills the SHELL -- any
                # program it started is re-parented to init and keeps running.
                # Observed while testing the timeout: the shell was terminated
                # on schedule but `python3 sleeper.py` survived with PPID 1.
                start_new_session=True,
            )
            _active_processes[run_id] = proc

            sent = 0
            truncated = False
            deadline = t0 + MAX_RUNTIME_S
            timed_out = False

            # Stream output line by line, bounded in both bytes and wall time.
            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    timed_out = True
                    break
                try:
                    line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
                except TimeoutError:
                    timed_out = True
                    break
                if not line:
                    break
                if not truncated:
                    sent += len(line)
                    if sent > MAX_OUTPUT_BYTES:
                        truncated = True
                        yield (
                            'data: '
                            + json.dumps(
                                {
                                    'type': 'stdout',
                                    'data': f'\n[output truncated at {MAX_OUTPUT_BYTES} bytes — '
                                    f'the command is still running]\n',
                                }
                            )
                            + '\n\n'
                        )
                    else:
                        text = line.decode('utf-8', errors='replace')
                        yield f'data: {json.dumps({"type": "stdout", "data": text})}\n\n'
                await asyncio.sleep(0)  # yield to event loop

            if timed_out:
                # Terminate, then escalate: a process ignoring SIGTERM would
                # otherwise leak for the lifetime of the server.
                _terminate_tree(proc, signal.SIGTERM)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except TimeoutError:
                    _terminate_tree(proc, signal.SIGKILL)
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(proc.wait(), timeout=5)
                duration = round((time.time() - t0) * 1000)
                yield (
                    'data: '
                    + json.dumps(
                        {
                            'type': 'error',
                            'data': f'Command exceeded the {MAX_RUNTIME_S}s limit and was terminated.',
                        }
                    )
                    + '\n\n'
                )
                yield f'data: {json.dumps({"type": "exit", "exit_code": 124, "duration_ms": duration, "run_id": run_id, "timed_out": True})}\n\n'
                return

            await proc.wait()
            duration = round((time.time() - t0) * 1000)
            yield f'data: {json.dumps({"type": "exit", "exit_code": proc.returncode, "duration_ms": duration, "run_id": run_id, "truncated": truncated})}\n\n'

        except asyncio.CancelledError:
            _terminate_tree(proc, signal.SIGKILL)
            yield f'data: {json.dumps({"type": "exit", "exit_code": -1, "reason": "cancelled"})}\n\n'
        except Exception as e:
            log.error('Terminal error: %s', e)
            yield f'data: {json.dumps({"type": "error", "data": str(e), "exit_code": 1})}\n\n'
        finally:
            # A client disconnect cancels this generator mid-stream; without
            # this the subprocess would keep running with nobody reading it.
            _terminate_tree(proc, signal.SIGKILL)
            _active_processes.pop(run_id, None)

    return StreamingResponse(
        generate(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


@router.post('/kill/{run_id}')
def kill_process(run_id: str):
    """Kill a running command by its run_id."""
    proc = _active_processes.get(run_id)
    if not proc:
        return JSONResponse(
            {'ok': False, 'error': 'Process not found — it may have already exited'},
            status_code=404,
        )
    try:
        # Kill the whole group, not just the shell -- otherwise the actual
        # program keeps running after the user presses Kill.
        _terminate_tree(proc, signal.SIGKILL)
    except OSError as e:
        return JSONResponse({'ok': False, 'error': str(e)}, status_code=500)
    finally:
        _active_processes.pop(run_id, None)
    return {'ok': True, 'killed': run_id}


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


_ENV_CACHE: dict = {}
_ENV_CACHE_TTL_S = 300


@router.get('/env')
def get_environment():
    """Return safe environment info.

    Cached: this ran four blocking subprocesses on every call, each with a 2s
    timeout, so a cold or slow toolchain could block the event loop for up to
    8 seconds — on an endpoint the UI hits on every render of the pane.
    Installed tool versions do not change between requests.
    """
    now = time.time()
    cached = _ENV_CACHE.get('data')
    if cached and now - _ENV_CACHE.get('at', 0) < _ENV_CACHE_TTL_S:
        return {**cached, 'cached': True}

    data = _probe_environment()
    _ENV_CACHE['data'] = data
    _ENV_CACHE['at'] = now
    return {**data, 'cached': False}


def _probe_environment() -> dict:
    """Actually run the version probes (uncached)."""
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


@router.post('/env/refresh')
def refresh_environment():
    """Force the environment probe to re-run (e.g. after installing a tool)."""
    _ENV_CACHE.clear()
    return {'ok': True, **_probe_environment(), 'cached': False}


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
