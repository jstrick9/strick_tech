#!/usr/bin/env python3
"""Ensure a Playwright Chromium is available, installing it on first run.

WHY THIS EXISTS
───────────────
Phase 2 of the CSP work (migrating 859 inline handlers off `unsafe-inline`) is
blocked on VERIFICATION, not on effort: the failure mode of a bad conversion is
"button does nothing, no error anywhere", and `tests/e2e_browser` is the only
thing that can catch it. Those 31 tests currently ERROR rather than skip,
because nobody has a browser installed.

Making the desktop install provide one turns that blocker into a solved
problem for anyone running the app locally — which is where the migration will
actually be verified.

DESIGN NOTES
  * Idempotent and cheap on the happy path. It checks whether a browser is
    already usable before doing anything, so adding it to a hot startup path
    costs one import and a filesystem stat.
  * NEVER fatal. A desktop app must not refuse to start because an optional
    test dependency could not be downloaded. Every failure path returns a
    status, logs a reason, and lets the caller continue.
  * Records its outcome to a marker file so a machine that genuinely cannot
    install (no root for libnss3, offline, corporate proxy) is not re-attempted
    on every launch — a 60-second download retried at every startup is its own
    bug.
  * `--with-deps` is deliberately NOT used by default. It requires root and
    would prompt for a password during a desktop launch. Callers who want it
    can pass --system-deps explicitly.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

MARKER_NAME = '.playwright_bootstrap.json'
# Give up re-attempting for this long after a failure, so a machine that cannot
# install is not punished on every launch. A week is long enough to avoid
# nagging, short enough that fixing the environment takes effect soon after.
RETRY_AFTER_SECONDS = 7 * 24 * 3600


def _marker_path() -> Path:
    base = os.environ.get('AGENTIC_OS_DATA_DIR')
    root = Path(base) if base else Path(__file__).resolve().parent.parent
    return root / 'memory' / MARKER_NAME


def browser_available(*, deep: bool = True) -> tuple[bool, str]:
    """Is a LAUNCHABLE Chromium present? Returns (ok, reason).

    `deep` actually launches the browser. That distinction matters and was a
    bug in my first version of this file: on this machine the 425MB binary
    downloaded successfully and `executable_path` pointed at a real file, so an
    existence check reported "available" -- while every launch failed with
    "Host system is missing dependencies to run browsers".

    Reporting a browser as ready when it cannot start is exactly the "looks
    present, does nothing" shape this review has spent 22 modules removing, and
    it would have made the desktop bootstrap claim success while leaving phase
    2 just as blocked.

    The shallow check exists for hot paths where a ~1s launch is too expensive;
    anything deciding whether to INSTALL must use the deep one.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False, 'playwright package not installed'

    try:
        with sync_playwright() as p:
            path = p.chromium.executable_path
            if not path or not Path(path).exists():
                return False, 'chromium executable not downloaded'
            if not deep:
                return True, path
            browser = p.chromium.launch(args=['--no-sandbox', '--disable-gpu'])
            browser.close()
            return True, path
    except Exception as exc:
        msg = str(exc)
        if 'missing dependencies' in msg or 'libnss3' in msg or 'error while loading' in msg:
            return False, 'system libraries missing (needs --with-deps / root)'
        return False, 'launch failed: ' + msg[:200]


def _read_marker() -> dict:
    try:
        return json.loads(_marker_path().read_text(encoding='utf-8'))
    except Exception:
        return {}


def _write_marker(data: dict) -> None:
    try:
        p = _marker_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2), encoding='utf-8')
    except OSError:
        pass  # a diagnostic marker must never break startup


def ensure(*, quiet: bool = False, force: bool = False, system_deps: bool = False) -> dict:
    """Install Chromium if missing. Returns a status dict; never raises."""
    def say(msg: str) -> None:
        if not quiet:
            print(msg, flush=True)

    ok, detail = browser_available()
    if ok:
        return {'status': 'present', 'detail': detail}

    if detail == 'playwright package not installed':
        # Not an error: playwright lives in requirements-test.txt, so a normal
        # runtime install legitimately lacks it.
        return {'status': 'skipped', 'detail': detail}

    marker = _read_marker()
    if not force and marker.get('failed_at'):
        age = time.time() - float(marker.get('failed_at', 0))
        if age < RETRY_AFTER_SECONDS:
            return {
                'status': 'deferred',
                'detail': f"previous attempt failed: {marker.get('error', 'unknown')}",
            }

    say('  📥 Downloading the Chromium test browser (one-time, ~120MB)…')
    say('     This enables the browser E2E suite. The app works without it.')

    cmd = [sys.executable, '-m', 'playwright', 'install', 'chromium']
    if system_deps:
        # Requires root; only when the caller explicitly asks.
        cmd.append('--with-deps')

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        _write_marker({'failed_at': time.time(), 'error': 'download timed out'})
        say('  ⚠️  Browser download timed out — skipping. The app is unaffected.')
        return {'status': 'failed', 'detail': 'timeout'}
    except Exception as exc:
        _write_marker({'failed_at': time.time(), 'error': str(exc)[:300]})
        return {'status': 'failed', 'detail': str(exc)[:300]}

    ok, detail = browser_available()
    if ok:
        _write_marker({'installed_at': time.time(), 'path': detail})
        say('  ✅ Chromium ready — browser E2E tests are now runnable.')
        return {'status': 'installed', 'detail': detail}

    err = (proc.stderr or proc.stdout or '').strip()[-400:]
    _write_marker({'failed_at': time.time(), 'error': err})
    say('  ⚠️  Could not install the test browser. The app is unaffected.')
    if 'missing dependencies' in err.lower() or 'libnss3' in err.lower():
        say('     Missing system libraries. Run:')
        say(f'       {sys.executable} -m playwright install --with-deps chromium')
    return {'status': 'failed', 'detail': err}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--quiet', action='store_true')
    ap.add_argument('--force', action='store_true', help='ignore the retry marker')
    ap.add_argument('--system-deps', action='store_true',
                    help='also install OS libraries (needs root)')
    ap.add_argument('--check', action='store_true', help='report status only')
    args = ap.parse_args()

    if args.check:
        ok, detail = browser_available()
        print(json.dumps({'available': ok, 'detail': detail}, indent=2))
        return 0

    result = ensure(quiet=args.quiet, force=args.force, system_deps=args.system_deps)
    if not args.quiet:
        print(json.dumps(result, indent=2))
    # Always 0: this is opportunistic setup, and a non-zero exit would fail an
    # installer for something explicitly optional.
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
