"""Sweep 2/4 — blocking overlay / interaction — must stay at zero findings.

docs/BUG-SWEEP-PLAN.md: "Every pane: after navigation, is the element at the
centre of the viewport part of that pane?"

WHAT THE SWEEP CHECKS
---------------------
scripts/sweep_blocking_overlay.py drives a real Chromium through all 70 panes
in MASTER_PANE_REGISTRY and measures four things per pane:

  CENTRE_BLOCKED   a fixed element covers the viewport centre
  NAV_BLOCKED      the pane's own sidebar item is not topmost at its own point
  CONSOLE_ERROR    the pane threw while rendering
  PHANTOM_NAV      hovering the sidebar changed the active pane with no click
  PHANTOM_REQUESTS hovering fired a flood of /api/ calls
  OVERLAY_TRAPS    a first-run modal survives Escape

The last three exist because the plan's prediction for Bug 2 was WRONG. It
predicted a blocking overlay. The overlay was real on first visit but was not
the reported bug -- the actual cause was `data-self-click` synthesising clicks
on all 16 non-click events, so hovering ran click actions (b99dc0a). A sweep
that only checked the predicted mechanism would have passed while the app was
unusable, so it checks the mechanism that actually bit as well.

Result: 0 findings across 70 panes.

THREE CORRECTIONS TO THE SWEEP, all made before trusting its output
--------------------------------------------------------------------
First run reported 16 NAV_BLOCKED. Every one was the probe's fault, and the
tell was in the output itself: "covered by None". elementFromPoint returns
null for coordinates that are not in the viewport -- null is not an element,
so "covered by nothing" should never have been reported as covered.

  16 -> 5   Nav items in COLLAPSED sidebar groups have a 0x0 rect. Not
            blocked; not rendered. Now requires a non-zero on-screen rect.
   5 -> 4   nav() auto-expands the target pane's group, but the probe read the
            rect in the same tick, before layout. Groups are expanded first.
   4 -> 0   The remaining four were genuinely visible in page coordinates but
            scrolled OUT of `.sidebar-scroll`, which clips at y=708 while the
            items sat at y=791. Probing that point hit the agent list painted
            below the scroll region. Scrolling is not blocking.

PROVEN TO ACTUALLY DETECT SOMETHING
-----------------------------------
A sweep that reports zero because it cannot see is worthless. Injecting

    <div style="position:fixed;inset:0;z-index:99999">

into a live page and re-running the probe returns
`{"id": "evil", "position": "fixed", "zIndex": "99999"}` -- DETECTED. That
check is reproduced as a test below so the sweep cannot rot into a no-op.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SWEEP = REPO / "scripts" / "sweep_blocking_overlay.py"
REGISTRY = REPO / "frontend" / "js" / "00-pane-registry.js"

CHROME = Path("/home/user/.cache/ms-playwright/chromium-1148/chrome-linux/chrome")


def _server_up() -> bool:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen("http://localhost:8787/api/health", timeout=3) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _need_browser() -> None:
    import pytest

    if not CHROME.exists():
        pytest.skip("chromium not installed in this environment")
    if not _server_up():
        pytest.skip("no app running on :8787")


def test_the_sweep_script_exists() -> None:
    assert SWEEP.exists(), "sweep 2 of 4 is missing; the finish line cannot be checked"


def test_the_sweep_reports_zero_findings() -> None:
    """THE GATE."""
    _need_browser()
    p = subprocess.run(
        [sys.executable, str(SWEEP), "--json"],
        cwd=REPO, capture_output=True, text=True, timeout=1200,
    )
    if p.returncode == 2:
        import pytest
        pytest.skip(f"sweep could not run: {p.stdout.strip()[:200]}")
    findings = json.loads(p.stdout)
    assert findings == [], (
        "blocking-overlay sweep found regressions:\n"
        + json.dumps(findings, indent=2)[:4000]
    )


def test_the_sweep_covers_every_registered_pane() -> None:
    """A sweep that silently checks 3 of 70 panes reports zero and means
    nothing."""
    import re

    src = REGISTRY.read_text(encoding="utf-8")
    i = src.index("MASTER_PANE_REGISTRY")
    ids = {m.group(1) for m in re.finditer(r"^\s*'([a-z0-9-]+)'\s*:", src[i:], re.M)}
    assert len(ids) >= 60, f"expected the full registry, found {len(ids)}"

    sweep_src = SWEEP.read_text(encoding="utf-8")
    assert "MASTER_PANE_REGISTRY" in sweep_src, (
        "the sweep must read the real registry, not a hardcoded pane list"
    )


def test_the_sweep_can_actually_see_an_overlay() -> None:
    """Revert-proof built into the suite: inject a real full-screen fixed
    element and confirm the sweep's own probe reports it. Without this, a
    probe that silently stopped working would report a permanent clean bill
    of health."""
    _need_browser()
    from playwright.sync_api import sync_playwright

    src = SWEEP.read_text(encoding="utf-8")
    probe = src.split('PROBE_JS = r"""', 1)[1].split('"""', 1)[0]

    with sync_playwright() as pw:
        b = pw.chromium.launch(
            executable_path=str(CHROME),
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        pg = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
        pg.goto("http://localhost:8787", wait_until="domcontentloaded")
        pg.wait_for_timeout(5000)
        pg.evaluate(
            """() => {
                ['#onboarding-modal','#onboarding-overlay','.onboarding-back',
                 '.modal-backdrop'].forEach(
                    s => document.querySelectorAll(s).forEach(e => e.remove()));
                try { localStorage.setItem('agentic_os_onboarded','true'); } catch (e) {}
            }"""
        )
        pg.wait_for_timeout(500)
        clean = pg.evaluate(probe, "chat")
        pg.evaluate(
            """() => {
                const d = document.createElement('div');
                d.id = 'sweep-test-overlay';
                d.style.cssText =
                  'position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.5)';
                document.body.appendChild(d);
            }"""
        )
        pg.wait_for_timeout(300)
        blocked = pg.evaluate(probe, "chat")
        b.close()

    assert clean["overlay"] is None, (
        f"the app is already blocked before injection: {clean['overlay']}"
    )
    assert blocked["overlay"] is not None, (
        "the probe did not notice a full-screen fixed overlay — it is blind"
    )
    assert blocked["overlay"]["id"] == "sweep-test-overlay"


def test_the_sweep_does_not_confuse_offscreen_with_blocked() -> None:
    """Guard against the 16-false-positive version returning. `covered by
    None` was the tell: elementFromPoint returns null outside the viewport."""
    src = SWEEP.read_text(encoding="utf-8")
    assert "sidebar-scroll" in src, "must respect the sidebar's scroll clipping"
    assert "inScroller" in src
    assert "onScreen" in src


def test_the_sweep_checks_the_mechanism_bug_2_actually_was() -> None:
    """The plan predicted an overlay. The real cause was hover firing click
    actions. Both must be swept."""
    src = SWEEP.read_text(encoding="utf-8")
    assert "PHANTOM_NAV" in src, "hover-navigation is not checked"
    assert "PHANTOM_REQUESTS" in src, "hover request floods are not checked"


def test_a_skip_is_reported_as_exit_2_not_success() -> None:
    """If the browser or server is missing the sweep must NOT exit 0 — a skip
    is not a pass, and exit 0 is what the finish line reads."""
    src = SWEEP.read_text(encoding="utf-8")
    assert src.count("return 2") >= 3, (
        "missing prerequisites must exit 2, never 0"
    )
    assert "A skip is not a pass" in src
