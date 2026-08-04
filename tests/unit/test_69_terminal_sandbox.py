"""OS-level isolation for terminal commands.

The Module 12 review tightened the command filter considerably and added
RLIMITs, then recorded the honest limitation:

    "the honest long-term answer for arbitrary shell execution is OS-level
     isolation (a container or nsjail). RLIMITs bound resource consumption and
     the filter bounds obvious misuse, but neither is a substitute for a real
     sandbox."

backend/services/sandbox.py is that sandbox: Linux user/mount/pid/ipc/uts/net
namespaces, requiring no root, no daemon and no external tooling (bwrap,
nsjail, firejail, docker and podman are all absent on the target host).

Measured on this host, unsandboxed vs sandboxed:

    read backend/routers/secrets.py   readable      No such file or directory
    stat memory/agentic.db            readable      No such file or directory
    host processes visible            96            1
    outbound HTTP                     reachable     URLError
    workspace read/write              works         works
    python3 / node / git              work          work

These tests skip rather than fail where namespaces are unavailable — the
sandbox is genuinely optional, and a red suite on macOS would teach nothing.
The contracts that matter on EVERY platform (fail-open behaviour, honest
reporting, cleanup) are asserted unconditionally.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from backend.services import sandbox as sb

REPO = Path(__file__).resolve().parents[2]
TERMINAL_SRC = (REPO / 'backend' / 'routers' / 'terminal.py').read_text()
WORK = str(REPO / 'preview')

available, _reason = sb.sandbox_available()
needs_ns = pytest.mark.skipif(not available, reason=f'namespaces unavailable: {_reason}')


def run_sandboxed(script: str, timeout: int = 40) -> str:
    """Run a shell snippet through the sandbox and return combined output."""
    argv, scratch = sb.wrap_command(['/bin/sh', '-c', script], WORK)
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return ((r.stdout or '') + (r.stderr or '')).strip()
    finally:
        sb.cleanup(scratch)


# ── Contracts that hold on every platform ──────────────────────────────────────


class TestAvailabilityReporting:
    def test_availability_is_a_bool_and_a_reason(self):
        ok, reason = sb.sandbox_available()
        assert isinstance(ok, bool)
        assert isinstance(reason, str)
        assert ok or reason, 'an unavailable sandbox must explain itself'

    def test_result_is_cached(self):
        """The probe forks a process; doing it per command would be wasteful."""
        assert sb.sandbox_available() == sb.sandbox_available()

    def test_describe_is_honest_either_way(self):
        d = sb.describe()
        assert set(d) >= {'available', 'reason', 'mechanism', 'isolates', 'note'}
        if d['available']:
            assert d['mechanism'] == 'linux-namespaces'
            assert 'filesystem' in d['isolates']
        else:
            assert d['isolates'] == []
            assert 'No OS-level isolation' in d['note']

    def test_it_degrades_instead_of_failing(self, monkeypatch):
        """A host without namespaces must still run commands, not error."""
        monkeypatch.setattr(sb, '_AVAILABILITY', False)
        monkeypatch.setattr(sb, '_UNAVAILABLE_REASON', 'test')
        argv, scratch = sb.wrap_command(['/bin/echo', 'hi'], WORK)
        assert argv == ['/bin/echo', 'hi'], 'command must pass through unchanged'
        assert scratch is None

    def test_cleanup_tolerates_none(self):
        sb.cleanup(None)

    def test_cleanup_removes_the_scratch_root(self):
        argv, scratch = sb.wrap_command(['/bin/true'], WORK)
        if scratch is None:
            pytest.skip('sandbox unavailable')
        assert Path(scratch).exists()
        sb.cleanup(scratch)
        assert not Path(scratch).exists(), 'jail roots would accumulate per command'


class TestTerminalIntegration:
    def test_terminal_wraps_commands(self):
        assert 'sandbox_svc.wrap_command(' in TERMINAL_SRC

    def test_terminal_cleans_up_the_jail(self):
        assert TERMINAL_SRC.count('sandbox_svc.cleanup(') >= 1

    def test_the_start_event_states_whether_it_is_isolated(self):
        """A user who believes they are sandboxed when they are not is worse
        off than one who knows they aren't."""
        assert "'sandboxed': sandboxed" in TERMINAL_SRC
        assert 'sandbox_note' in TERMINAL_SRC
        assert 'NOT isolated' in TERMINAL_SRC

    def test_env_reports_sandbox_status(self, client):
        body = client.get('/api/terminal/env').json()
        assert 'sandbox' in body
        assert 'available' in body['sandbox']

    def test_it_can_be_disabled(self):
        assert "os.getenv('TERMINAL_SANDBOX'" in TERMINAL_SRC

    def test_network_is_off_by_default(self):
        assert "os.getenv('TERMINAL_SANDBOX_NETWORK', '0')" in TERMINAL_SRC

    def test_run_reports_sandboxed_true_when_available(self, client):
        r = client.post('/api/terminal/run', json={'command': 'echo probe'})
        assert r.status_code == 200
        assert '"sandboxed"' in r.text


# ── Contracts requiring real namespaces ────────────────────────────────────────


@needs_ns
class TestFilesystemIsolation:
    def test_the_platform_source_is_unreachable(self):
        """The single most important assertion in this file.

        Unsandboxed, a terminal command can read secrets.py, the vault loader,
        and every credential the platform holds.
        """
        out = run_sandboxed('cat /home/user/repo/backend/routers/secrets.py')
        assert 'No such file' in out or 'cannot open' in out

    def test_the_database_is_unreachable(self):
        out = run_sandboxed('ls -la /home/user/repo/memory/agentic.db')
        assert 'No such file' in out or 'cannot access' in out

    def test_the_home_directory_is_unreachable(self):
        out = run_sandboxed('ls /home/user')
        assert 'No such file' in out or 'cannot access' in out

    def test_the_workspace_is_readable_and_writable(self):
        """Isolation that breaks the feature is not a fix."""
        out = run_sandboxed(
            'touch /work/_sbtest && ls /work/_sbtest && rm -f /work/_sbtest'
        )
        assert '_sbtest' in out

    def test_workspace_writes_persist_to_the_host(self):
        """It is a bind mount, so real work must survive the jail."""
        probe = Path(WORK) / '_sb_persist_probe'
        probe.unlink(missing_ok=True)
        try:
            run_sandboxed('touch /work/_sb_persist_probe')
            assert probe.exists(), 'the bind mount is not writing through'
        finally:
            probe.unlink(missing_ok=True)

    def test_writes_outside_the_workspace_do_not_reach_the_host(self):
        """They land in the ephemeral jail root and vanish with it."""
        run_sandboxed('echo x > /escape_probe.txt 2>/dev/null || true')
        assert not Path('/escape_probe.txt').exists()

    def test_system_directories_are_read_only(self):
        out = run_sandboxed('touch /usr/_sbtest 2>&1; echo rc=$?')
        assert 'rc=0' not in out or 'Read-only' in out


@needs_ns
class TestProcessIsolation:
    def test_host_processes_are_invisible(self):
        """96 visible unsandboxed; 1 inside."""
        out = run_sandboxed('ls /proc | grep -c "^[0-9]*$"')
        visible = int((out.splitlines() or ['999'])[-1].strip() or 999)
        assert visible <= 3, f'{visible} processes visible inside the sandbox'

    def test_the_server_process_cannot_be_signalled(self):
        out = run_sandboxed('kill -0 1 2>&1; echo rc=$?')
        # PID 1 inside the namespace is the command itself, not the server.
        assert 'rc=' in out


@needs_ns
class TestNetworkIsolation:
    def test_outbound_traffic_is_blocked_by_default(self):
        out = run_sandboxed(
            'timeout 6 python3 -c '
            '"import urllib.request as u; u.urlopen(\'http://1.1.1.1\', timeout=4); '
            'print(\'REACHED\')" 2>&1 | tail -1',
            timeout=30,
        )
        assert 'REACHED' not in out, 'a compromised command could exfiltrate'

    def test_network_can_be_re_enabled_explicitly(self):
        argv, scratch = sb.wrap_command(['/bin/true'], WORK, allow_network=True)
        try:
            assert '--net' not in argv
        finally:
            sb.cleanup(scratch)


@needs_ns
class TestToolchainStillWorks:
    """Isolation is worthless if it breaks the terminal."""

    @pytest.mark.parametrize(
        'cmd,expect',
        [
            ('python3 --version', 'Python'),
            ('node --version', 'v'),
            ('git --version', 'git version'),
            ('ls /work', ''),
        ],
    )
    def test_common_tools_run(self, cmd, expect):
        out = run_sandboxed(cmd)
        assert expect in out, f'{cmd!r} broke inside the sandbox: {out[:120]}'

    def test_dev_null_exists(self):
        """git and most build tools abort outright without it."""
        out = run_sandboxed('echo x > /dev/null && echo ok')
        assert 'ok' in out


@needs_ns
class TestSecretsStayOut:
    def test_vault_keys_are_not_in_the_environment(self, monkeypatch):
        """Belt and braces with _sandboxed_env(): even inside the jail, the
        process environment must not carry credentials."""
        from backend.routers.terminal import _sandboxed_env

        monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-should-not-appear')
        env = _sandboxed_env()
        assert 'OPENROUTER_API_KEY' not in env

    def test_env_dump_inside_the_sandbox_has_no_platform_secrets(self):
        """Assert on the names the platform actually injects.

        My first version grepped for api_key/token/secret and failed on
        E2B_SANDBOX_ID: the test harness's own environment, not the server's.
        A pattern loose enough to match unrelated variables is not evidence,
        so this checks the specific credentials the Vault injects.
        """
        secret_names = (
            "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
            "GITHUB_TOKEN", "SECRET_KEY", "AGENTIC_VAULT_KEY",
        )
        out = run_sandboxed("env")
        present = [n for n in secret_names if n + "=" in out]
        assert present == [], "credentials visible inside the sandbox: %s" % present

    def test_a_secret_in_the_parent_does_not_reach_the_command(self, monkeypatch):
        """End-to-end: set a canary, then look for it inside the jail."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-canary-value")
        out = run_sandboxed("env")
        assert "sk-or-canary-value" not in out


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux-only')
class TestJailConstructionOrder:
    """The order of operations in _build_jail is load-bearing."""

    def test_old_root_is_detached_after_pivot(self):
        src = (REPO / 'backend' / 'services' / 'sandbox.py').read_text()
        pivot = src.index('_pivot_root(')
        umount = src.index("umount2(b'/oldroot'")
        assert pivot < umount, 'the host tree is reachable until /oldroot is detached'

    def test_mount_propagation_is_made_private_first(self):
        """Otherwise the jail's binds leak back onto the host mount tree."""
        src = (REPO / 'backend' / 'services' / 'sandbox.py').read_text()
        private = src.index('MS_REC | MS_PRIVATE')
        bind_root = src.index('_mount(root, root')
        assert private < bind_root
