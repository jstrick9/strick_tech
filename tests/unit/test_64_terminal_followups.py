"""Module 12 (Terminal) follow-ups.

Four items from the review write-up, all now implemented.

1. NO AUTHORISATION. The endpoint runs shell commands as the server user and
   had no access control whatsoever. Defensible bound to loopback; not
   defensible when the server is reachable from the network.

2. THE FILTER CAN ONLY ENUMERATE BADNESS. A command allowlist cannot bound
   what an allowed command *does*. Added kernel-enforced RLIMITs, which apply
   regardless of what the command turns out to be.

3. NO STDIN. Interactive commands (`npm init`, `git rebase -i`) hung until the
   runtime cap killed them, showing a timeout with no explanation.

4. `/env` ran four blocking subprocesses per call, 2s timeout each — up to 8s
   of blocked event loop on an endpoint the UI hits every render.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.routers import terminal as term

REPO = Path(__file__).resolve().parents[2]
SRC = (REPO / 'backend' / 'routers' / 'terminal.py').read_text()


# ── 1. Authorisation ───────────────────────────────────────────────────────────


class TestAuthorisationGate:
    def test_loopback_bind_is_recognised(self, monkeypatch):
        for host in ('127.0.0.1', '::1', 'localhost'):
            monkeypatch.setenv('AGENTIC_OS_HOST', host)
            assert term._bound_to_loopback() is True

    def test_public_bind_is_recognised(self, monkeypatch):
        for host in ('0.0.0.0', '192.168.1.10'):
            monkeypatch.setenv('AGENTIC_OS_HOST', host)
            assert term._bound_to_loopback() is False

    def test_auth_is_not_required_on_loopback(self, monkeypatch):
        """Existing single-user desktop installs must keep working."""
        monkeypatch.setenv('AGENTIC_OS_HOST', '127.0.0.1')
        monkeypatch.delenv('TERMINAL_REQUIRE_AUTH', raising=False)
        assert term._auth_required() is False

    def test_auth_is_required_when_exposed(self, monkeypatch):
        monkeypatch.setenv('AGENTIC_OS_HOST', '0.0.0.0')
        monkeypatch.delenv('TERMINAL_REQUIRE_AUTH', raising=False)
        assert term._auth_required() is True

    def test_auth_can_be_forced_on_loopback(self, monkeypatch):
        monkeypatch.setenv('AGENTIC_OS_HOST', '127.0.0.1')
        monkeypatch.setenv('TERMINAL_REQUIRE_AUTH', '1')
        assert term._auth_required() is True

    def test_terminal_can_be_disabled_entirely(self, client, monkeypatch):
        monkeypatch.setenv('TERMINAL_DISABLED', '1')
        r = client.post('/api/terminal/run', json={'command': 'echo hi'})
        assert r.status_code == 403
        assert r.json()['code'] == 'terminal_disabled'

    def test_no_registered_users_does_not_mean_open_access(self):
        """require_api_key() returns None when the user table is empty.

        For most endpoints that first-run convenience is fine. For a shell
        reachable from the network it is a fail-open hole — verified live
        before this fix: TERMINAL_REQUIRE_AUTH=1 with no users ran `echo hi`.
        """
        assert 'terminal_no_users' in SRC
        assert 'if user_id is None:' in SRC

    def test_auth_backend_failure_fails_closed(self):
        """An unavailable auth backend must refuse, not wave the command through."""
        assert 'terminal_auth_unavailable' in SRC
        assert 'status_code=503' in SRC

    def test_the_gate_runs_before_the_handler(self):
        """Originally an inline check at the top of run_command.

        Now a router-level dependency, which FastAPI resolves before the
        handler is entered at all — a stronger guarantee than ordering
        statements inside the function, and one that cannot be forgotten when
        a new endpoint is added.
        """
        from backend.routers.terminal import require_terminal_access, router

        run_routes = [r for r in router.routes if getattr(r, 'path', '') == '/api/terminal/run']
        assert run_routes, '/run route not found'
        dependant = run_routes[0].dependant
        assert require_terminal_access in [sub.call for sub in dependant.dependencies]

    def test_loopback_default_still_executes(self, client, monkeypatch):
        monkeypatch.setenv('AGENTIC_OS_HOST', '127.0.0.1')
        monkeypatch.delenv('TERMINAL_REQUIRE_AUTH', raising=False)
        monkeypatch.delenv('TERMINAL_DISABLED', raising=False)
        r = client.post('/api/terminal/run', json={'command': 'echo backcompat'})
        assert r.status_code == 200


# ── 2. OS-level resource limits ────────────────────────────────────────────────


class TestResourceLimits:
    def test_limits_are_defined_and_configurable(self):
        assert term.TERMINAL_CPU_SECONDS > 0
        assert term.TERMINAL_MEMORY_MB > 0
        assert term.TERMINAL_MAX_FILE_MB > 0
        assert term.TERMINAL_MAX_PROCS > 0
        for var in (
            'TERMINAL_CPU_SECONDS',
            'TERMINAL_MEMORY_MB',
            'TERMINAL_MAX_FILE_MB',
            'TERMINAL_MAX_PROCS',
        ):
            assert var in SRC

    def test_limits_are_applied_to_the_subprocess(self):
        assert 'preexec_fn=_apply_rlimits' in SRC

    def test_apply_rlimits_is_callable_and_safe(self):
        """It runs in the forked child; an exception there is very bad."""
        term._apply_rlimits()  # must not raise in-process

    def test_it_caps_the_four_resources(self):
        assert 'RLIMIT_CPU' in SRC
        assert 'RLIMIT_AS' in SRC
        assert 'RLIMIT_FSIZE' in SRC
        assert 'RLIMIT_NPROC' in SRC

    def test_core_dumps_are_disabled(self):
        """A killed command shouldn't leave a core file in the workspace."""
        assert 'RLIMIT_CORE' in SRC

    def test_it_never_raises_the_hard_limit(self):
        """setrlimit fails if soft > hard; clamp instead of crashing."""
        assert 'min(soft, hard)' in SRC

    @pytest.mark.skipif(os.name != 'posix', reason='POSIX rlimits only')
    def test_limits_actually_bind_in_a_child(self):
        """Fork a child, apply the limits, and read them back."""
        import multiprocessing
        import resource

        def child(q):
            term._apply_rlimits()
            q.put(
                {
                    'cpu': resource.getrlimit(resource.RLIMIT_CPU)[0],
                    'fsize': resource.getrlimit(resource.RLIMIT_FSIZE)[0],
                }
            )

        ctx = multiprocessing.get_context('fork')
        q = ctx.Queue()
        proc = ctx.Process(target=child, args=(q,))
        proc.start()
        proc.join(timeout=15)
        got = q.get(timeout=5)
        assert got['cpu'] == term.TERMINAL_CPU_SECONDS
        assert got['fsize'] == term.TERMINAL_MAX_FILE_MB * 1024 * 1024


# ── 3. Interactive commands ────────────────────────────────────────────────────


class TestInteractiveCommands:
    @pytest.mark.parametrize(
        'cmd',
        [
            'npm init',
            'yarn init',
            'npm login',
            'npm adduser',
            'git rebase -i HEAD~3',
            'git rebase --interactive HEAD~2',
            'git commit',
            'git add -p',
            'git add --patch',
            'git merge feature',
            'git tag v1.0',
        ],
    )
    def test_hanging_forms_are_refused(self, cmd):
        ok, reason = term._is_safe(cmd)
        assert not ok, f'{cmd!r} would hang until the timeout'
        assert 'interactive input' in reason

    @pytest.mark.parametrize(
        'cmd',
        [
            'npm init -y',
            'yarn init --yes',
            'git rebase --onto main feature',
            'git commit -m "message"',
            'git commit --message="x"',
            'git add .',
            'git add src/file.js',
            'git merge --no-edit feature',
            'git tag -m "release" v1.0',
            'git status',
            'npm install',
        ],
    )
    def test_non_interactive_forms_still_work(self, cmd):
        ok, reason = term._is_safe(cmd)
        assert ok, f'{cmd!r} should be allowed: {reason}'

    def test_the_message_names_the_fix(self):
        """A bare refusal teaches nothing; the flag to use is the useful part."""
        _, reason = term._is_safe('npm init')
        assert 'npm init -y' in reason
        _, reason = term._is_safe('git commit')
        assert '-m' in reason

    def test_stdin_is_explicitly_closed(self):
        """Otherwise the child inherits the server's stdin."""
        assert 'stdin=asyncio.subprocess.DEVNULL' in SRC

    def test_blocked_interactive_command_is_403(self, client):
        assert client.post('/api/terminal/run', json={'command': 'npm init'}).status_code == 403


# ── 4. /env caching ────────────────────────────────────────────────────────────


class TestEnvironmentCaching:
    def test_first_call_probes_and_second_is_cached(self, client):
        term._ENV_CACHE.clear()
        first = client.get('/api/terminal/env').json()
        second = client.get('/api/terminal/env').json()
        assert first['cached'] is False
        assert second['cached'] is True

    def test_cached_payload_matches_the_probe(self, client):
        term._ENV_CACHE.clear()
        first = client.get('/api/terminal/env').json()
        second = client.get('/api/terminal/env').json()
        for key in ('node', 'npm', 'python', 'git', 'cwd'):
            assert first[key] == second[key]

    def test_refresh_forces_a_reprobe(self, client):
        """Needed after installing a tool, or the UI shows stale versions."""
        client.get('/api/terminal/env')
        r = client.post('/api/terminal/env/refresh')
        assert r.status_code == 200
        assert r.json()['cached'] is False

    def test_the_probe_is_not_run_inline_anymore(self):
        assert '_probe_environment' in SRC
        assert '_ENV_CACHE_TTL_S' in SRC

    def test_cache_has_a_ttl(self):
        """A permanent cache would never notice a newly installed tool."""
        assert term._ENV_CACHE_TTL_S > 0


# ── Regression guard ───────────────────────────────────────────────────────────


class TestEarlierFixesStillHold:
    @pytest.mark.parametrize(
        'cmd',
        [
            'python3 -c "print(1)"',
            'node -e "1"',
            'echo x > /tmp/y',
            'cat /etc/passwd',
            'rm -rf /',
            'echo `id`',
        ],
    )
    def test_still_blocked(self, cmd):
        assert not term._is_safe(cmd)[0]

    @pytest.mark.parametrize(
        'cmd', ['ls -la', 'pwd', 'python3 -m pytest', 'node server.js', 'printf "a"']
    )
    def test_still_allowed(self, cmd):
        ok, reason = term._is_safe(cmd)
        assert ok, reason

    def test_process_group_termination_intact(self):
        assert 'start_new_session=True' in SRC
        assert 'os.killpg' in SRC

    def test_secrets_still_stripped_from_env(self, monkeypatch):
        monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-x')
        assert 'OPENROUTER_API_KEY' not in term._sandboxed_env()


# ── Follow-up correction: the gate must cover EVERY endpoint ───────────────────


class TestEveryEndpointIsGated:
    """The first version of the gate protected POST /run only.

    That was a real gap, not a theoretical one. Verified live with
    TERMINAL_REQUIRE_AUTH=1 and no API key, before this correction:

      GET    /history      -> 200, returned every command ever run
      DELETE /history      -> 200, wiped the audit trail
      GET    /env          -> 200, disclosed toolchain versions and host paths
      POST   /env/refresh  -> 200, forced four blocking subprocesses on demand
      POST   /kill/{id}    -> reachable; kills someone else's running command

    Command history routinely holds repository URLs, hostnames, absolute paths
    and sometimes embedded credentials, so read access is not harmless, and
    delete access destroys the record of what was run.
    """

    def test_the_gate_is_attached_to_the_router_not_per_endpoint(self):
        """A hand-maintained per-endpoint list is exactly what failed here."""
        assert 'router.dependencies.append(Depends(require_terminal_access))' in SRC

    def test_no_endpoint_carries_its_own_ad_hoc_check(self):
        """Belt-and-braces per route would drift out of sync again."""
        assert SRC.count('await _check_terminal_access(') == 1

    def test_every_route_resolves_the_dependency(self):
        """Enumerate the live routes rather than trusting the source text.

        This is the test that fails if someone adds a terminal endpoint later
        and the gate is not applied to it.
        """
        from backend.routers.terminal import require_terminal_access, router

        assert router.routes, 'no routes registered'
        for route in router.routes:
            names = [d.dependency for d in getattr(route, 'dependencies', [])]
            deps = getattr(route, 'dependant', None)
            resolved = names + [
                sub.call for sub in (deps.dependencies if deps else [])
            ]
            assert require_terminal_access in resolved, (
                f'{route.path} is not gated'
            )

    @pytest.mark.parametrize(
        'method,path',
        [
            ('post', '/api/terminal/run'),
            ('get', '/api/terminal/history'),
            ('delete', '/api/terminal/history'),
            ('get', '/api/terminal/env'),
            ('post', '/api/terminal/env/refresh'),
            ('post', '/api/terminal/kill/abc'),
            ('get', '/api/terminal/suggestions'),
        ],
    )
    def test_disabled_blocks_reads_as_well_as_execution(self, client, monkeypatch, method, path):
        """TERMINAL_DISABLED must turn the whole feature off, not just /run."""
        monkeypatch.setenv('TERMINAL_DISABLED', '1')
        r = getattr(client, method)(path)
        assert r.status_code == 403
        assert r.json()['code'] == 'terminal_disabled'

    def test_refusals_keep_the_platform_error_shape(self, client, monkeypatch):
        """A dependency can only raise; without a handler FastAPI emits
        {"detail": ...}, which no other refusal in this platform uses."""
        monkeypatch.setenv('TERMINAL_DISABLED', '1')
        body = client.get('/api/terminal/env').json()
        assert body['ok'] is False
        assert 'error' in body and 'code' in body
        assert 'detail' not in body

    def test_loopback_default_leaves_everything_open(self, client, monkeypatch):
        """Existing single-user installs must not need a key."""
        monkeypatch.setenv('AGENTIC_OS_HOST', '127.0.0.1')
        monkeypatch.delenv('TERMINAL_REQUIRE_AUTH', raising=False)
        monkeypatch.delenv('TERMINAL_DISABLED', raising=False)
        assert client.get('/api/terminal/env').status_code == 200
        assert client.get('/api/terminal/history').status_code == 200
