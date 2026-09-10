"""Shared browser harness for the UX audits.

WHY THIS FILE EXISTS
────────────────────
Every audit in this directory started life as a throwaway script in /home/user
that was rewritten from memory each session. That cost real bugs:

  * Touch targets took THREE batches to get right, because each rewrite
    measured something slightly different -- one pane, then all panes but only
    height, then finally the `display:inline` case where the CSS rule was
    inert.
  * The focus-ring "bug" was reported twice, in two different batches, and was
    wrong both times: `getComputedStyle` was read after a programmatic
    `.focus()`, which does not match `:focus-visible`.

A probe that lives in the repo gets its own bugs found once. A probe retyped
each session reintroduces them. The measurement lessons below are encoded here
so no audit has to remember them.

RUNNING
───────
    python3 scripts/audit/run_all.py              # everything, human output
    python3 scripts/audit/run_all.py --json       # machine readable
    python3 scripts/audit/touch_targets.py        # one audit

Each audit needs a live server. Start one with:
    AGENTIC_OS_DATA_DIR=/tmp/agentic-data python run.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
BASE_URL = os.environ.get('AGENTIC_AUDIT_URL', 'http://localhost:8787')

# Playwright ships several Chromium builds; the audits need the full browser,
# not the headless shell, and the path has to be explicit in this sandbox.
_CHROME_CANDIDATES = [
    # Any Chromium the installed Playwright version downloaded, newest first.
    # The original list pinned chromium-1148/chrome-linux/chrome — a version
    # path that no longer exists under any newer Playwright (they moved to
    # chrome-linux64 and bumped the build number), so on a fresh environment
    # every browser audit silently skipped even though a perfectly good
    # Chromium was installed. Glob beats pin.
    *sorted(Path.home().glob('.cache/ms-playwright/chromium-*/chrome-linux*/chrome'),
            reverse=True),
    Path('/usr/bin/chromium'),
    Path('/usr/bin/google-chrome'),
]

# First-run UI that covers the app and skews every measurement. Removed at the
# start of every audit rather than in each one.
_FIRST_RUN_IDS = ['onboarding-overlay', 'onboarding-modal', 'welcome-banner']

LAUNCH_ARGS = ['--no-sandbox', '--disable-dev-shm-usage']

# Viewports the audits measure at. `is_mobile` also enables touch, which is
# what makes `@media (pointer: coarse)` apply.
VIEWPORTS = {
    'phone':   dict(width=390,  height=844,  is_mobile=True),
    'tablet':  dict(width=768,  height=1024, is_mobile=True),
    'desktop': dict(width=1440, height=900,  is_mobile=False),
}

# How long to let a pane settle after navigation before measuring. Panes fetch
# and re-render, and several host renderers are async.
SETTLE_MS = 320

# CSS transitions run for 150ms in this app. Reading a computed style before
# they finish reports the START value -- which is how a 2px focus ring was
# twice mistaken for a missing one.
TRANSITION_MS = 400


def chrome_path() -> str | None:
    for candidate in _CHROME_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    return None


def playwright_available() -> tuple[bool, str]:
    """Return (usable, reason). Audits skip cleanly rather than crash."""
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False, 'playwright not installed (pip install playwright)'
    if chrome_path() is None:
        return False, 'no Chromium build found (python -m playwright install chromium)'
    return True, ''


def server_reachable() -> bool:
    import urllib.error
    import urllib.request

    # Only http(s) is ever probed here; BASE_URL is developer-supplied, but
    # rejecting other schemes keeps `file:` out of a health check.
    if not BASE_URL.startswith(('http://', 'https://')):
        return False
    try:
        with urllib.request.urlopen(f'{BASE_URL}/api/health', timeout=5) as r:  # noqa: S310
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


@contextmanager
def browser_page(viewport: str = 'desktop', route_handler=None):
    """Open the app with first-run UI dismissed and the page ready to measure.

    `route_handler` is a callable(route) for simulating failures, e.g. forcing
    every API call to return 500.
    """
    from playwright.sync_api import sync_playwright

    spec = VIEWPORTS[viewport]
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome_path(), args=LAUNCH_ARGS)
        context = browser.new_context(
            viewport={'width': spec['width'], 'height': spec['height']},
            is_mobile=spec['is_mobile'],
            has_touch=spec['is_mobile'],
        )
        page = context.new_page()
        # `networkidle` never settles in this app (websockets + polling).
        page.goto(BASE_URL, wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(3500)
        for element_id in _FIRST_RUN_IDS:
            page.evaluate(
                f"const e=document.getElementById({element_id!r}); if(e) e.remove();")
        # Routing is installed AFTER load so the app boots normally and only
        # the behaviour under test fails.
        if route_handler is not None:
            context.route('**/api/**', route_handler)
        try:
            yield page, context
        finally:
            browser.close()


def all_panes(page) -> list[str]:
    return page.evaluate("Object.keys(window.MASTER_PANE_REGISTRY || {})")


def visit(page, pane: str, settle: int = SETTLE_MS) -> None:
    """Navigate to a pane and let it settle.

    Uses `window.nav()` rather than clicking, because many panes are absorbed
    workstation tabs with no sidebar entry of their own.
    """
    page.evaluate(f"window.nav && window.nav({json.dumps(pane)})")
    page.wait_for_timeout(settle)
    # A fixed sleep alone under-measures: a pane that is still fetching
    # renders fewer controls, which made the touch-target count flap
    # 193–202 across runs of an identical build. Wait for the app's own
    # settle signal — panes carry aria-busy while loading and skeleton
    # placeholders while rendering — then let CSS transitions finish
    # before anything measures.
    try:
        page.wait_for_function(
            "() => !document.querySelector("
            "'[aria-busy=\"true\"], .skeleton, .skeleton-loader, .spinner')",
            timeout=4000,
        )
    except Exception:
        # A pane that never settles must not hang the audit; the original
        # settle window has already elapsed by now.
        pass
    page.wait_for_timeout(TRANSITION_MS)


def pane_text(page, pane: str) -> str:
    """The text a user actually sees for this pane.

    NOT "the first visible [id^=pane-]" -- for an absorbed tab that is the
    workstation HOST, which produced three phantom "blank pane" findings in an
    earlier batch.
    """
    return page.evaluate(f"""(() => {{
        const own = document.getElementById('pane-' + {json.dumps(pane)});
        if (own && own.innerText.trim().length) return own.innerText.trim();
        const vis = [...document.querySelectorAll('[id^=pane-]')]
            .find(e => e.offsetParent !== null);
        return vis ? vis.innerText.trim() : '';
    }})()""")


def fail_all_api(status: int = 500, body: str = '{"error":"simulated outage"}'):
    """Route handler that makes every API call fail."""
    def handler(route):
        route.fulfill(status=status, content_type='application/json', body=body)
    return handler


# ──────────────────────────────────────────────────────────────────────
#  Result reporting
# ──────────────────────────────────────────────────────────────────────
class AuditResult:
    """One audit's outcome: a headline count plus the detail behind it.

    `count` is what the ratchet in tests/unit/test_120_audit_ratchet.py
    compares against a committed baseline, so it must be a stable integer that
    only goes down when things improve.
    """

    def __init__(self, name: str, count: int, findings: list, note: str = ''):
        self.name = name
        self.count = count
        self.findings = findings
        self.note = note

    def to_dict(self) -> dict:
        return {
            'audit': self.name,
            'count': self.count,
            'note': self.note,
            'findings': self.findings,
        }

    def print_human(self) -> None:
        print(f'\n=== {self.name}: {self.count}')
        if self.note:
            print(f'    {self.note}')
        for finding in self.findings[:25]:
            print(f'    {finding}')
        if len(self.findings) > 25:
            print(f'    … and {len(self.findings) - 25} more')


def emit(result: AuditResult) -> int:
    """Print a result in the format requested on the command line."""
    if '--json' in sys.argv:
        print(json.dumps(result.to_dict(), indent=1))
    else:
        result.print_human()
    return 0


def preflight() -> None:
    """Exit with a clear message rather than a stack trace."""
    usable, reason = playwright_available()
    if not usable:
        print(f'SKIP: {reason}', file=sys.stderr)
        raise SystemExit(2)
    if not server_reachable():
        print(f'SKIP: no server at {BASE_URL} — start one with `python run.py`',
              file=sys.stderr)
        raise SystemExit(2)


def task_id_snapshot() -> set[int] | None:
    """IDs of every task currently on the server (None if unreachable)."""
    url = f'{BASE_URL}/api/tasks'
    if not url.startswith(('http://', 'https://')):
        return None
    try:
        with urllib.request.urlopen(url, timeout=15) as r:  # noqa: S310
            body = json.loads(r.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None
    rows = body.get('tasks') if isinstance(body, dict) else body
    if not isinstance(rows, list):
        return None
    return {row['id'] for row in rows if isinstance(row, dict) and 'id' in row}


def sweep_created_tasks(before: set[int] | None) -> int:
    """DELETE every task that appeared since `before`; returns how many.

    Audits that write through the real API to measure real behaviour —
    adversarial_input's XSS payloads, print_and_multitab's cross-tab
    marker — used to leave every probe row behind. A day of audit runs
    accumulated 91 junk tasks with payloads as titles in the operator's
    kanban. Snapshot before, sweep after: the same discipline the
    security suite's conftest guard applies to the same problem.
    """
    if before is None:
        return 0
    after = task_id_snapshot()
    if after is None:
        return 0
    fresh = sorted(after - before)
    if not fresh:
        return 0
    token = None
    try:
        with urllib.request.urlopen(  # noqa: S310
                f'{BASE_URL}/api/security/csrf-token', timeout=10) as r:
            body = json.loads(r.read())
        token = body.get('csrf_token') or body.get('token')
    except (urllib.error.URLError, OSError, ValueError):
        return 0
    removed = 0
    for task_id in fresh:
        req = urllib.request.Request(  # noqa: S310
            f'{BASE_URL}/api/tasks/{task_id}', method='DELETE',
            headers={'X-CSRF-Token': token or ''})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310
                if 200 <= r.status < 300:
                    removed += 1
        except (urllib.error.URLError, OSError):
            pass
    return removed
