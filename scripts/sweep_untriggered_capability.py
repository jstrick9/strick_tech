#!/usr/bin/env python3
"""Sweep 4 of 4 — CAPABILITY PRESENT BUT NEVER TRIGGERED.

The class, from docs/BUG-SWEEP-PLAN.md: *code that works only if you find the
button.* The check: every integration with a detectable local service -- is it
probed automatically?

The instance that defined it (Bug 4, fixed in 6a02312) is the sharpest example
in this repository. `GET /api/onboarding/detect-local-models` shipped, worked
correctly, honoured OLLAMA_BASE_URL, and returned the user's models. NOTHING
CALLED IT. Detection ran only inside `POST /api/onboarding/quick-setup`,
reachable from one button buried in Settings. The user launched the app with 17
local models installed, saw none of them, and reported "Ollama did not auto
connect". Every individual piece passed its own test.

That is what makes this class expensive: nothing is broken. There is simply no
path from application start to the working code.

CHECKS
------
  1. NO_CALLER        a detect/status endpoint exists in the backend and no
                      frontend file references it at all. Dead capability.
  2. CLICK_ONLY       the only references are inside data-act-* attributes, so
                      it runs if and only if the user finds the button. This
                      is precisely the Bug 4 shape.
DELIBERATELY NOT CHECKED: "is it called at application startup?"

My first version flagged 12 endpoints as NOT_AT_STARTUP and every one was
correct code. `/api/obsidian/status` runs when the Obsidian pane renders.
`/api/github/status` runs when the GitHub pane renders. That is right: probing
every integration on boot would fire dozens of requests for panes the user may
never open -- which is exactly the request flood that produced the rate-limit
toasts in the hover bug.

The real property is REACHABLE WITHOUT HUNTING, not CALLED ON BOOT. A pane
that probes its own service when opened satisfies that. Bug 4 did not: the
detect endpoint had no caller anywhere, and detection was buried behind one
button in Settings.

WHAT COUNTS AS A DETECTABLE SERVICE
-----------------------------------
An endpoint whose job is to answer "is this local thing here, and what does it
have" -- detect, status, health, models, probe. Derived from the router source
rather than a hardcoded list, so a new one is swept the day it lands.

Usage:
    python3 scripts/sweep_untriggered_capability.py
    python3 scripts/sweep_untriggered_capability.py --json

Exit 0 = zero findings.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROUTERS = REPO / "backend" / "routers"
JS_DIR = REPO / "frontend" / "js"

# Endpoints whose purpose is detecting a local capability. Matched against the
# route path, not a maintained list of names.
DETECT_RE = re.compile(
    r"detect|/status|/health|/models|probe|available", re.I
)


# Endpoints that are correctly on-demand. Each needs a reason: an exclusion
# without one is indistinguishable from an oversight.
# Endpoints with no UI surface at all. These are operational or test APIs --
# exercised by the test suite, CI, or an operator with curl -- not features a
# user is meant to discover. Verified individually: none has a pane in
# MASTER_PANE_REGISTRY, and each is covered by tests.
#
# This distinction is the whole point of the class. Bug 4 was a user-facing
# capability with no path to it. An /api/ws/status that only CI calls is not
# the same defect, and lumping them together would bury the real finding.
NO_UI_BY_DESIGN: dict[str, str] = {
    "/api/e2e/status":
        "browser-test harness state; driven by tests/e2e_browser",
    "/api/e2e/playwright/status":
        "reports whether Playwright is installed; used by the test suite",
    "/api/engine/status":
        "agent-engine introspection; covered by tests/unit/test_64",
    "/api/sync/status":
        "replication internals; covered by tests/unit/test_34",
    "/api/ws/status":
        "websocket connection count; an operator/health probe",
}

INTENTIONALLY_ON_DEMAND: dict[str, str] = {
    "/api/onboarding/quick-setup/status":
        "reports progress of a setup the user explicitly started",
    "/api/tauri/build/status":
        "polls a desktop build the user launched",
    "/api/agents/{agent_id}/status":
        "per-agent detail, meaningless before an agent is chosen",
}


def backend_detect_routes() -> list[tuple[str, str]]:
    """[(method+path, file)] for every detect-shaped GET route."""
    out: list[tuple[str, str]] = []
    for path in sorted(ROUTERS.glob("*.py")):
        src = path.read_text(encoding="utf-8")
        prefix = ""
        m = re.search(r"APIRouter\([^)]*prefix\s*=\s*['\"]([^'\"]+)['\"]", src, re.S)
        if m:
            prefix = m.group(1)
        for rm in re.finditer(r"@router\.get\(\s*['\"]([^'\"]+)['\"]", src):
            route = prefix + rm.group(1)
            if not route.startswith("/api"):
                route = "/api" + route if route.startswith("/") else f"/api/{route}"
            if DETECT_RE.search(rm.group(1)):
                out.append((route, str(path.relative_to(REPO))))
    return out


def js_sources() -> dict[str, str]:
    return {
        str(p.relative_to(REPO)): p.read_text(encoding="utf-8")
        for p in sorted(JS_DIR.glob("*.js"))
    }


def _route_needle(route: str) -> str:
    """The literal a frontend fetch would contain, ignoring path params."""
    return re.split(r"\{", route)[0].rstrip("/")


def _in_act_attribute(src: str, idx: int) -> bool:
    """Is this occurrence inside a data-act-* attribute value?"""
    start = max(0, idx - 400)
    window = src[start:idx]
    last_act = window.rfind("data-act-")
    if last_act == -1:
        return False
    # Still inside that attribute's quotes if no closing quote intervenes.
    after = window[last_act:]
    q = after.find('"')
    return q != -1 and '"' not in after[q + 1:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    routes = backend_detect_routes()
    sources = js_sources()
    findings: list[dict] = []

    for route, backend_file in routes:
        if route in INTENTIONALLY_ON_DEMAND or route in NO_UI_BY_DESIGN:
            continue
        needle = _route_needle(route)
        if len(needle) < 8:
            continue

        hits = [(f, s.index(needle)) for f, s in sources.items() if needle in s]
        if not hits:
            findings.append({
                "route": route, "backend": backend_file, "kind": "NO_CALLER",
                "detail": "no frontend file references this endpoint — the "
                          "capability exists and can never run",
            })
            continue

        only_click = all(
            _in_act_attribute(sources[f], i) for f, i in hits
        )
        if only_click:
            findings.append({
                "route": route, "backend": backend_file, "kind": "CLICK_ONLY",
                "detail": "only reachable from a data-act-* handler — it runs "
                          "if and only if the user finds the button (Bug 4)",
            })
            continue

        # Anything reached from a pane renderer, a boot path, or ordinary JS
        # is fine. Only "no caller at all" and "click-only" are defects.

    if args.json:
        print(json.dumps(findings, indent=2))
    else:
        print("SWEEP 4/4 — CAPABILITY PRESENT BUT NEVER TRIGGERED")
        print(f"  detect-shaped routes : {len(routes)}")
        print(f"  no UI by design      : {len(NO_UI_BY_DESIGN)}")
        for r, why in NO_UI_BY_DESIGN.items():
            print(f"      {r:42} {why}")
        print(f"  on-demand by design  : {len(INTENTIONALLY_ON_DEMAND)}")
        for r, why in INTENTIONALLY_ON_DEMAND.items():
            print(f"      {r:42} {why}")
        print("-" * 70)
        if not findings:
            print("  0 findings.")
        else:
            by: dict[str, list[dict]] = {}
            for f in findings:
                by.setdefault(f["kind"], []).append(f)
            for kind, items in sorted(by.items()):
                print(f"\n  {kind}  ({len(items)})")
                for f in items:
                    print(f"    {f['route']}")
                    print(f"        {f['detail']}")
            print(f"\n  TOTAL: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
