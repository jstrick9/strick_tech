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


def test_exit_code_is_always_zero():
    """A non-zero exit would fail an installer over something optional."""
    r = subprocess.run(
        [sys.executable, str(SCRIPT), '--quiet'], capture_output=True, text=True, timeout=300
    )
    assert r.returncode == 0


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
    assert 'error' not in r.stdout.lower(), r.stdout[-600:]
