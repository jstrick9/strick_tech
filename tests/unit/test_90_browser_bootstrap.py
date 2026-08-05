"""Phase 2 unblocker — the desktop install provisions a test browser.

Phase 2 (migrating 859 inline handlers off `script-src 'unsafe-inline'`) is
blocked on VERIFICATION rather than effort: a bad conversion yields "button
does nothing, no error anywhere", and tests/e2e_browser is the only thing that
catches it. Those 31 tests errored out on any machine without Chromium.

scripts/ensure_browser.py installs it on first run, wired into run.py (which
the Tauri desktop shell launches directly), start.sh and start.bat.

The properties that matter are all about NOT breaking the product for the sake
of an optional test dependency.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts' / 'ensure_browser.py'
RUN_PY = (ROOT / 'run.py').read_text(encoding='utf-8')

sys.path.insert(0, str(ROOT / 'scripts'))


# ══ The bootstrap script ══════════════════════════════════════════════════════
def test_script_exists_and_runs():
    assert SCRIPT.exists()
    r = subprocess.run(
        [sys.executable, str(SCRIPT), '--check'], capture_output=True, text=True, timeout=120
    )
    assert r.returncode == 0
    assert 'available' in json.loads(r.stdout)


def test_availability_check_actually_launches_the_browser():
    """My first version checked only that the executable FILE existed.

    On this machine the 425MB binary downloaded fine and executable_path
    pointed at a real file — so the check reported "available" while every
    launch failed with "Host system is missing dependencies". Reporting a
    browser as ready when it cannot start is the "looks present, does nothing"
    shape this review exists to remove, and it would have let the desktop
    bootstrap claim success while leaving phase 2 just as blocked.
    """
    src = SCRIPT.read_text(encoding='utf-8')
    assert 'p.chromium.launch(' in src, 'availability is not verified by launching'
    assert 'deep' in src, 'no distinction between a shallow and a real check'


def test_check_reports_missing_system_libraries_distinctly():
    """"Not downloaded" and "downloaded but unlaunchable" need different
    remedies; collapsing them sends the user to the wrong fix."""
    from ensure_browser import browser_available

    ok, detail = browser_available()
    assert isinstance(ok, bool)
    if not ok:
        assert detail, 'a failure must explain itself'


def test_exit_code_is_always_zero(monkeypatch, tmp_path):
    """A non-zero exit would fail an installer over something optional.

    AGENTIC_SKIP_BROWSER_SETUP short-circuits the real work. Without it this
    launched Chromium for a deep availability probe, which is fine alone and
    intermittently exceeded its timeout inside a 3900-test run — a slow test
    reporting a bug that does not exist. The exit-code contract is what
    matters here, and the skip path exercises the same return.
    """
    env = dict(os.environ, AGENTIC_SKIP_BROWSER_SETUP='1')
    r = subprocess.run(
        [sys.executable, str(SCRIPT), '--quiet'],
        capture_output=True, text=True, timeout=120, env=env,
    )
    assert r.returncode == 0, r.stdout[-400:] + r.stderr[-400:]


def test_exit_code_is_zero_even_when_the_browser_is_unavailable(monkeypatch):
    """The case that matters: a machine where the download or launch fails
    must not break `python run.py`."""
    import ensure_browser as eb

    monkeypatch.setattr(eb, 'browser_available', lambda **k: (False, 'simulated failure'))
    monkeypatch.setattr(eb, '_can_sudo', lambda: False)
    monkeypatch.setattr(
        eb.subprocess, 'run',
        lambda *a, **k: subprocess.CompletedProcess(a[0] if a else [], 1, '', 'boom'),
    )
    # Must return, not raise.
    result = eb.ensure(quiet=True)
    assert isinstance(result, dict)


def test_failure_is_recorded_so_it_is_not_retried_every_launch(tmp_path, monkeypatch):
    """A 120MB download retried at every startup is its own bug."""
    import ensure_browser as eb

    marker = tmp_path / 'memory' / eb.MARKER_NAME
    monkeypatch.setattr(eb, '_marker_path', lambda: marker)
    monkeypatch.setattr(eb, 'browser_available', lambda **k: (False, 'chromium executable not downloaded'))
    monkeypatch.setattr(
        eb.subprocess, 'run',
        lambda *a, **k: subprocess.CompletedProcess(a[0], 1, '', 'boom'),
    )

    first = eb.ensure(quiet=True)
    assert first['status'] == 'failed'
    assert marker.exists(), 'no marker written — the next launch would retry'

    second = eb.ensure(quiet=True)
    assert second['status'] == 'deferred', 'a known-failing install was retried'


def test_force_overrides_the_deferral(tmp_path, monkeypatch):
    import ensure_browser as eb

    marker = tmp_path / 'memory' / eb.MARKER_NAME
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({'failed_at': 9e9, 'error': 'x'}))
    monkeypatch.setattr(eb, '_marker_path', lambda: marker)
    monkeypatch.setattr(eb, 'browser_available', lambda **k: (False, 'chromium executable not downloaded'))
    calls = []
    monkeypatch.setattr(
        eb.subprocess, 'run',
        lambda *a, **k: calls.append(1) or subprocess.CompletedProcess(a[0], 1, '', 'x'),
    )
    eb.ensure(quiet=True, force=True)
    assert calls, '--force did not re-attempt'


def test_missing_playwright_is_not_an_error(monkeypatch):
    """playwright lives in requirements-test.txt; a runtime install lacking it
    is normal, not a fault to report."""
    import ensure_browser as eb

    monkeypatch.setattr(eb, 'browser_available', lambda **k: (False, 'playwright package not installed'))
    assert eb.ensure(quiet=True)['status'] == 'skipped'


def test_present_browser_short_circuits(monkeypatch):
    """Adding this to a startup path must cost almost nothing when already
    installed."""
    import ensure_browser as eb

    monkeypatch.setattr(eb, 'browser_available', lambda **k: (True, '/path/chrome'))
    called = []
    monkeypatch.setattr(eb.subprocess, 'run', lambda *a, **k: called.append(1))
    assert eb.ensure(quiet=True)['status'] == 'present'
    assert not called, 'it tried to install an already-present browser'


def test_system_deps_is_opt_in():
    """--with-deps needs root and would prompt for a password mid-launch."""
    src = SCRIPT.read_text(encoding='utf-8')
    assert 'system_deps' in src
    assert "'--with-deps'" in src
    i = src.index("cmd.append('--with-deps')")
    assert 'if system_deps:' in src[max(0, i - 200):i]


# ══ Wiring into the install paths ═════════════════════════════════════════════
def test_run_py_hooks_the_bootstrap():
    """The DESKTOP case specifically: the Tauri shell launches run.py directly
    and never touches the shell scripts, so hooking only start.sh would miss
    exactly the install this is meant to serve."""
    assert 'def ensure_test_browser' in RUN_PY
    assert 'ensure_test_browser()' in RUN_PY.split('def ensure_test_browser')[1]


def test_bootstrap_does_not_block_startup():
    """A ~120MB download must never delay the desktop window appearing."""
    assert 'threading.Thread' in RUN_PY
    assert 'daemon=True' in RUN_PY


def test_bootstrap_can_be_disabled():
    assert 'AGENTIC_SKIP_BROWSER_SETUP' in RUN_PY


def test_bootstrap_never_raises_into_startup():
    seg = RUN_PY.split('def ensure_test_browser')[1].split('def seed_db')[0]
    assert 'except Exception' in seg, 'an optional download could abort startup'


def test_tauri_launches_run_py_so_the_hook_covers_the_desktop_app():
    """Documents WHY run.py is the right hook point, so a future refactor does
    not move it somewhere the desktop app never reaches."""
    main_rs = (ROOT / 'src-tauri' / 'src' / 'main.rs').read_text(encoding='utf-8')
    assert 'run.py' in main_rs


@pytest.mark.parametrize('script,needle', [
    ('start.sh', 'scripts/ensure_browser.py'),
    ('start.bat', 'ensure_browser.py'),
])
def test_shell_launchers_also_bootstrap(script, needle):
    assert needle in (ROOT / script).read_text(encoding='utf-8')


def test_shell_launchers_cannot_fail_the_startup():
    assert '|| true' in (ROOT / 'start.sh').read_text(encoding='utf-8')


# ══ e2e suite degrades honestly ═══════════════════════════════════════════════
def test_e2e_suite_skips_instead_of_erroring():
    """31 module-scope import errors said "the suite is broken". A skip says
    "this needs a browser" — and that distinction is what tells a developer
    whether they have a problem to fix."""
    conftest = (ROOT / 'tests' / 'e2e_browser' / 'conftest.py').read_text(encoding='utf-8')
    assert "importorskip('playwright'" in conftest


def test_e2e_browser_fixture_skips_on_unlaunchable_chromium():
    conftest = (ROOT / 'tests' / 'e2e_browser' / 'conftest.py').read_text(encoding='utf-8')
    assert 'missing dependencies' in conftest
    assert 'pytest.skip(' in conftest


def test_e2e_collection_no_longer_errors():
    r = subprocess.run(
        [sys.executable, '-m', 'pytest', 'tests/e2e_browser', '-q', '--collect-only',
         '-p', 'no:randomly'],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    )
    # Check the RETURN CODE and pytest's own error line, not a substring
    # search of stdout. Collection lists every test name, and
    # `test_a_server_error_produces_a_visible_toast` contains "error" — so the
    # naive check failed on a clean collection as soon as a test was named
    # after the condition it covers.
    assert r.returncode == 0, r.stdout[-600:]
    assert 'errors' not in r.stdout.split('\n')[-2].lower(), r.stdout[-600:]


# ══ System dependencies ═══════════════════════════════════════════════════════
# Downloading Chromium is only half the job. On a bare Linux host the 120MB
# binary installs fine and then FAILS TO LAUNCH because libnss3 and friends are
# absent — which is the default state of a fresh machine, and is what blocked
# the browser E2E suite for this entire review. Installing the libraries turned
# 31 skipped tests into 53 passing ones.
def test_bootstrap_installs_system_libraries_when_it_can():
    src = (ROOT / 'scripts' / 'ensure_browser.py').read_text(encoding='utf-8')
    assert '_install_system_deps' in src
    assert 'libnss3' in src, 'the core launch dependency is not installed'


def test_sudo_probe_never_prompts():
    """A bootstrap that blocks on a password prompt during app startup would
    hang the desktop launch. `sudo -n` fails immediately instead."""
    src = (ROOT / 'scripts' / 'ensure_browser.py').read_text(encoding='utf-8')
    assert "'sudo', '-n'" in src
    assert 'def _can_sudo' in src


def test_font_packages_are_deliberately_excluded():
    """`playwright install-deps` exits non-zero when any package is
    unavailable, and two font packages are absent on Debian 13. Treating that
    as fatal would skip the libraries that actually matter; the fonts only
    affect glyph coverage."""
    src = (ROOT / 'scripts' / 'ensure_browser.py').read_text(encoding='utf-8')
    assert 'ttf-' not in src, 'font packages break the install on Debian'
    assert 'cosmetic' in src or 'glyph' in src, (
        'the reason fonts are excluded must survive with the code'
    )


def test_a_missing_sudo_is_not_an_error():
    """Most users will not have passwordless sudo. The app must still start."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / 'scripts'))
    import ensure_browser

    assert isinstance(ensure_browser._can_sudo(), bool)
