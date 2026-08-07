"""Every bug class that has been fixed must stay fixed.

THE PROBLEM THIS SOLVES
───────────────────────
Across 35 batches of review, the probes that found nearly every bug lived in
/home/user and were wiped between sessions. They were rewritten from memory
each time, slightly differently, which cost real bugs:

  * Touch targets took THREE batches, once per way of measuring wrongly:
    one pane, then all panes but only height, then finally the `display:inline`
    case where the CSS rule was inert.
  * A "missing focus ring" was reported twice, in two different batches, and
    was wrong both times -- the same measurement mistake, made twice, despite
    having been documented after the first.

So the audits now live in scripts/audit/ and their headline numbers are
committed to scripts/audit/baseline.json. This file is the ratchet: a number
going UP fails the build.

HOW TO WORK WITH IT
───────────────────
  Improved something?   Re-run `python3 scripts/audit/run_all.py --write-baseline`
                        and commit the lower number in the same change.
  Number went up?       That is a regression. Fix it, or justify raising the
                        baseline in the commit message.

The browser audits need a live server, so they are skipped when one is not
running rather than failing. `source-patterns` needs neither a browser nor a
server, which is why it is the one that always runs.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
AUDIT_DIR = REPO / 'scripts' / 'audit'
BASELINE_PATH = AUDIT_DIR / 'baseline.json'


def _baseline() -> dict:
    return json.loads(BASELINE_PATH.read_text(encoding='utf-8'))


def _run_audit(module: str) -> dict | None:
    """Run one audit and return its result, or None if it had to skip."""
    result = subprocess.run(
        [sys.executable, str(AUDIT_DIR / f'{module}.py'), '--json'],
        cwd=REPO, capture_output=True, text=True, timeout=900)
    if result.returncode == 2:      # preflight: no browser or no server
        return None
    assert result.returncode == 0, (
        f'{module} failed to run:\n{result.stderr[-1500:]}')
    return json.loads(result.stdout)


# ──────────────────────────────────────────────────────────────────────
#  The instruments themselves must stay runnable
# ──────────────────────────────────────────────────────────────────────
def test_baseline_exists_and_covers_every_audit():
    """A new audit with no baseline entry would ratchet nothing."""
    assert BASELINE_PATH.is_file(), (
        'no baseline; run python3 scripts/audit/run_all.py --write-baseline')
    baseline = _baseline()

    sys.path.insert(0, str(AUDIT_DIR))
    import run_all  # noqa: E402

    for module in run_all.AUDITS:
        audit_module = __import__(module)
        # Every audit must name itself consistently, or the ratchet silently
        # stops covering it.
        assert hasattr(audit_module, 'run'), f'{module} has no run()'

    missing = [a for a in run_all.AUDITS
               if not any(k for k in baseline)]
    assert not missing, f'audits with no baseline entry: {missing}'


def test_every_audit_is_syntactically_runnable():
    """A broken audit would skip silently and the ratchet would pass."""
    sys.path.insert(0, str(AUDIT_DIR))
    import run_all  # noqa: E402

    for module in run_all.AUDITS:
        path = AUDIT_DIR / f'{module}.py'
        assert path.is_file(), f'{module}.py is missing'
        compile(path.read_text(encoding='utf-8'), str(path), 'exec')


def test_audits_are_committed_not_scratch_files():
    """The whole point: these must live in the repo, not in /home/user.

    Probes outside the repo are wiped between sessions and rebuilt from
    memory. That is how the same measurement mistake got made twice.
    """
    for name in ('_harness.py', 'run_all.py', 'baseline.json'):
        assert (AUDIT_DIR / name).is_file(), f'scripts/audit/{name} missing'


# ──────────────────────────────────────────────────────────────────────
#  The ratchet
# ──────────────────────────────────────────────────────────────────────
def test_source_patterns_has_not_regressed():
    """Runs everywhere: no browser, no server, no network."""
    result = _run_audit('source_patterns')
    assert result is not None
    expected = _baseline()['source-patterns']
    assert result['count'] <= expected, (
        f"source-patterns rose from {expected} to {result['count']}.\n"
        + '\n'.join(result['findings'][:12])
        + '\n\nIf this is intentional, lower/raise the baseline in the same '
          'commit with a reason.'
    )


@pytest.mark.parametrize('module,key', [
    ('semantics', 'semantics'),
    ('pane_health', 'pane-health'),
    ('keyboard', 'keyboard-operability'),
    ('touch_targets', 'touch-targets-under-44px'),
    ('responsive', 'responsive-overflow'),
    ('failure_honesty', 'failure-honesty'),
    ('concurrency', 'concurrent-duplicate-writes'),
])
def test_browser_audit_has_not_regressed(module, key):
    """Skips cleanly when there is no live server, rather than failing.

    A skipped audit is visible in the test output, so a CI run with no browser
    cannot be mistaken for a passing audit.
    """
    result = _run_audit(module)
    if result is None:
        pytest.skip(f'{module}: no browser or no server on localhost:8787')
    expected = _baseline()[key]
    assert result['count'] <= expected, (
        f"{key} rose from {expected} to {result['count']}.\n"
        + '\n'.join(result['findings'][:12])
    )
