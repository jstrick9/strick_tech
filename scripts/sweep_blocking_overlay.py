#!/usr/bin/env python3
"""Sweep 2 of 4 — BLOCKING OVERLAY.

The class, from docs/BUG-SWEEP-PLAN.md: *a fixed element that intercepts
clicks.* The check: after navigating to a pane, is the element at the centre of
the viewport part of that pane?

WHY THIS SWEEP LOOKS DIFFERENT FROM THE PLAN
--------------------------------------------
The plan predicted Bug 2 ("glitchy clicking") was a blocking overlay -- a
full-screen #onboarding-modal at z-index 29000 eating clicks. That was measured
and it was real on first visit, but it was NOT the reported bug. The actual
cause was `data-self-click` synthesising clicks on all 16 non-click events, so
merely HOVERING ran click actions (fixed in b99dc0a).

So this sweep checks both halves of "can the user actually interact":

  1. CENTRE BLOCKED   -- elementFromPoint(centre) is a fixed overlay that is
                         not part of the pane. The predicted class.
  2. NAV BLOCKED      -- the sidebar nav item for this pane is not the topmost
                         element at its own coordinates. You cannot even leave.
  3. PHANTOM ACTION   -- hovering a nav item changes the active pane, or fires
                         network requests. The class Bug 2 actually was.
  4. CONSOLE ERROR    -- the pane threw while rendering. A pane that errors is
                         not usable regardless of what covers it.

Every finding is a measurement from a real browser, never a static read.

Usage:
    python3 scripts/sweep_blocking_overlay.py                # all panes
    python3 scripts/sweep_blocking_overlay.py --json
    python3 scripts/sweep_blocking_overlay.py --panes chat,kanban
    python3 scripts/sweep_blocking_overlay.py --url http://localhost:8787

Exit 0 = zero findings. Exit 1 = findings. Exit 2 = could not run (a skip is
not a pass).
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "frontend" / "js" / "00-pane-registry.js"
DEFAULT_URL = "http://localhost:8787"

CHROME = (
    "/home/user/.cache/ms-playwright/chromium-1148/chrome-linux/chrome"
)

# Overlays that are SUPPOSED to cover the screen when open. Finding one of
# these at the centre is only a defect if it is present without being asked
# for -- which is what the onboarding checks below test explicitly.
DISMISSIBLE = {
    "onboarding-modal", "onboarding-overlay", "upgrade-modal",
    "novice-api-guide-modal", "command-palette", "gm-modal",
}


def pane_ids() -> list[str]:
    src = REGISTRY.read_text(encoding="utf-8")
    i = src.index("MASTER_PANE_REGISTRY")
    body = src[i:]
    ids: list[str] = []
    for m in re.finditer(r"^\s*'([a-z0-9-]+)'\s*:", body, re.M):
        if m.group(1) not in ids:
            ids.append(m.group(1))
    return ids


def server_up(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=5) as r:  # noqa: S310
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


PROBE_JS = r"""
(paneId) => {
  const vw = window.innerWidth, vh = window.innerHeight;
  const cx = Math.floor(vw / 2), cy = Math.floor(vh / 2);
  const el = document.elementFromPoint(cx, cy);

  function describe(n) {
    if (!n) return null;
    const cs = getComputedStyle(n);
    return {
      tag: n.tagName,
      id: n.id || null,
      cls: (n.className && n.className.toString().slice(0, 60)) || null,
      position: cs.position,
      zIndex: cs.zIndex,
      pointerEvents: cs.pointerEvents,
    };
  }

  // Walk up looking for a fixed/absolute ancestor that is not inside #content.
  let cur = el, overlay = null;
  const content = document.getElementById('content');
  while (cur && cur !== document.body) {
    const cs = getComputedStyle(cur);
    if ((cs.position === 'fixed' || cs.position === 'sticky')
        && cs.pointerEvents !== 'none'
        && !(content && content.contains(cur))) {
      overlay = cur;
      break;
    }
    cur = cur.parentElement;
  }

  const inContent = !!(content && el && content.contains(el));

  // Is this pane's own nav item reachable?
  // Only meaningful for a nav item that is actually rendered AND scrolled
  // into view. A zero-size rect means its sidebar group is COLLAPSED, and a
  // rect outside the sidebar's own scroll viewport means it is simply further
  // down the list. Neither is "blocked" -- my first run reported 16 panes as
  // NAV_BLOCKED for exactly this reason, and "covered by None" in that output
  // was the tell: elementFromPoint returns null for coordinates that are not
  // in the viewport at all.
  const nav = document.querySelector('[data-nav="' + paneId + '"]');
  let navReachable = null, navBlockedBy = null;
  if (nav) {
    const r = nav.getBoundingClientRect();
    // Must also be inside its own SCROLL CONTAINER. The sidebar list scrolls
    // independently, so an item further down has a rect that is on-screen in
    // page coordinates while being clipped out of .sidebar-scroll. Probing
    // that point hits whatever is painted there instead -- the agent list,
    // which sits below the scroll region -- and looks like interception.
    // Measured: imagegen at y=791..831, .sidebar-scroll ends at 708.
    // Scrolling is not blocking; the user scrolls and clicks it.
    const scroller = nav.closest('.sidebar-scroll');
    const sc = scroller ? scroller.getBoundingClientRect() : null;
    const inScroller = !sc || (r.top >= sc.top && r.bottom <= sc.bottom);
    const onScreen = r.width > 0 && r.height > 0
                  && r.top >= 0 && r.bottom <= window.innerHeight
                  && r.left >= 0 && r.right <= window.innerWidth
                  && inScroller;
    if (onScreen) {
      const nx = Math.floor(r.left + r.width / 2);
      const ny = Math.floor(r.top + r.height / 2);
      const top = document.elementFromPoint(nx, ny);
      navReachable = !!(top && (nav.contains(top) || top.contains(nav)));
      if (!navReachable) navBlockedBy = describe(top);
    }
  }

  return {
    centre: describe(el),
    inContent,
    overlay: describe(overlay),
    navReachable,
    navBlockedBy,
    activePane: (document.querySelector('.nav-item.active') || {})
                  .getAttribute?.('data-nav') || null,
  };
}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--panes", default="")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP: playwright not installed. A skip is not a pass.")
        print("      pip install --user playwright && playwright install chromium")
        return 2

    if not Path(CHROME).exists():
        print(f"SKIP: chromium missing at {CHROME}. A skip is not a pass.")
        print("      python3 -m playwright install chromium")
        return 2

    if not server_up(args.url):
        print(f"SKIP: no app on {args.url}. A skip is not a pass.")
        print("      Start it, then re-run.")
        return 2

    panes = [p.strip() for p in args.panes.split(",") if p.strip()] or pane_ids()
    findings: list[dict] = []
    checked = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(args.url, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        # --- Onboarding must not trap. Checked BEFORE dismissing anything. ---
        first = page.evaluate(PROBE_JS, "chat")
        if first["overlay"] and first["overlay"]["id"] in DISMISSIBLE:
            # A modal on first visit is correct. It is only a defect if it
            # cannot be escaped -- so prove Escape works.
            page.keyboard.press("Escape")
            page.wait_for_timeout(800)
            after = page.evaluate(PROBE_JS, "chat")
            if after["overlay"] and after["overlay"]["id"] in DISMISSIBLE:
                findings.append({
                    "pane": "(first visit)",
                    "kind": "OVERLAY_TRAPS",
                    "detail": f"{first['overlay']['id']} survives Escape — "
                              "the user cannot reach the app",
                })

        # Clear any first-run chrome so per-pane results reflect the pane.
        page.evaluate(
            """() => {
                ['#onboarding-modal','#onboarding-overlay','.onboarding-back',
                 '.modal-backdrop','#novice-api-guide-modal']
                  .forEach(s => document.querySelectorAll(s)
                                        .forEach(e => e.remove()));
                try { localStorage.setItem('agentic_os_onboarded','true'); } catch (e) {}
                if (window.applyUIMode) window.applyUIMode('power');
            }"""
        )
        page.wait_for_timeout(800)

        for pane in panes:
            errors.clear()
            try:
                # Expand every sidebar group first. nav() auto-expands the
                # group for the pane it opens, but the probe reads the nav
                # item's rect immediately after -- and for a pane whose group
                # was collapsed the rect is still 0x0 at that instant. That
                # raced, and produced 5 spurious NAV_BLOCKED findings whose
                # tell was `covered by None`: elementFromPoint returns null
                # for coordinates outside the viewport, not an element.
                page.evaluate(
                    """(gs) => gs.forEach(
                        g => window.toggleSidebarGroup && window.toggleSidebarGroup(g, true)
                    )""",
                    ["core", "build", "ship", "tools", "enterprise"],
                )
                page.wait_for_timeout(250)
                page.evaluate("(p) => window.nav && window.nav(p)", pane)
            except Exception as exc:  # noqa: BLE001
                findings.append({"pane": pane, "kind": "NAV_THREW",
                                 "detail": str(exc)[:200]})
                continue
            page.wait_for_timeout(1400)
            checked += 1

            try:
                r = page.evaluate(PROBE_JS, pane)
            except Exception as exc:  # noqa: BLE001
                findings.append({"pane": pane, "kind": "PROBE_FAILED",
                                 "detail": str(exc)[:200]})
                continue

            if r["overlay"]:
                findings.append({
                    "pane": pane, "kind": "CENTRE_BLOCKED",
                    "detail": f"a fixed element covers the viewport centre: "
                              f"{r['overlay']}",
                })
            elif not r["inContent"] and r["centre"]:
                # Not automatically wrong -- some panes render outside #content.
                # Report it so it is a decision, not an oversight.
                findings.append({
                    "pane": pane, "kind": "CENTRE_OUTSIDE_CONTENT",
                    "detail": f"centre element is not inside #content: {r['centre']}",
                })

            if r["navReachable"] is False:
                findings.append({
                    "pane": pane, "kind": "NAV_BLOCKED",
                    "detail": f"the sidebar item for this pane is covered by "
                              f"{r['navBlockedBy']}",
                })

            if errors:
                findings.append({
                    "pane": pane, "kind": "CONSOLE_ERROR",
                    "detail": errors[0][:200],
                })

        # --- Phantom action: hovering must not navigate or fire requests. ---
        page.evaluate("() => window.nav && window.nav('chat')")
        page.wait_for_timeout(1000)
        reqs: list[str] = []
        page.on("request", lambda rq: reqs.append(rq.url))
        before = page.evaluate(
            "() => (document.querySelector('.nav-item.active')||{})"
            ".getAttribute?.('data-nav') || null"
        )
        sidebar = page.query_selector("#sidebar")
        if sidebar:
            box = sidebar.bounding_box()
            if box:
                x = box["x"] + box["width"] / 2
                for i in range(40):
                    page.mouse.move(x, box["y"] + 60 + i * 9)
                    page.wait_for_timeout(20)
                page.wait_for_timeout(1200)
        after_pane = page.evaluate(
            "() => (document.querySelector('.nav-item.active')||{})"
            ".getAttribute?.('data-nav') || null"
        )
        if before != after_pane:
            findings.append({
                "pane": "(sidebar hover)", "kind": "PHANTOM_NAV",
                "detail": f"hovering changed the active pane {before} -> {after_pane} "
                          "with no click",
            })
        api = [u for u in reqs if "/api/" in u]
        if len(api) > 12:
            findings.append({
                "pane": "(sidebar hover)", "kind": "PHANTOM_REQUESTS",
                "detail": f"hovering fired {len(api)} /api/ requests — this is what "
                          "produced the rate-limit toasts",
            })

        browser.close()

    if args.json:
        print(json.dumps(findings, indent=2))
    else:
        print("SWEEP 2/4 — BLOCKING OVERLAY / INTERACTION")
        print(f"  panes navigated : {checked}")
        print("-" * 62)
        if not findings:
            print("  0 findings.")
        else:
            by: dict[str, list[dict]] = {}
            for f in findings:
                by.setdefault(f["kind"], []).append(f)
            for kind, items in sorted(by.items()):
                print(f"\n  {kind}  ({len(items)})")
                for f in items[:25]:
                    print(f"    {f['pane']:22} {f['detail']}")
                if len(items) > 25:
                    print(f"    ... and {len(items) - 25} more")
            print(f"\n  TOTAL: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
