"""Sweep 4/4 — capability present but never triggered — must stay at zero.

docs/BUG-SWEEP-PLAN.md: "Every integration with a detectable local service: is
it probed automatically?"

The instance that defined the class (Bug 4, fixed in 6a02312) is the sharpest
example in this repository. GET /api/onboarding/detect-local-models shipped,
worked, honoured OLLAMA_BASE_URL, and returned the user's models. NOTHING
CALLED IT. Detection ran only inside POST /api/onboarding/quick-setup, behind
one button in Settings. The user launched with 17 local models installed, saw
none, and reported "Ollama did not auto connect". Every piece passed its own
test. Nothing was broken; there was simply no path to the working code.

THE ONE REAL FINDING
--------------------
    GET /api/fusion/route/models — no caller anywhere in the frontend.

It returns the routing table: which model handles each task type, why, and the
estimated cost per 1k tokens. The Fusion pane's Smart Router panel tells the
user it "picks the optimal model" while giving them no way to see what it will
pick or what it costs -- an unverifiable promise sitting next to a working
endpoint that answers it.

Now rendered with the pane. Verified in Chromium: 1 request fired on pane open,
9 task types rendered, 0 page errors.

TWO CORRECTIONS TO THE SWEEP, both narrowing it
------------------------------------------------
First run reported 19 findings. Thirteen were mine.

  12  NOT_AT_STARTUP on endpoints called from a pane renderer. My check
      searched only the file that defined the fetch, so /api/onboarding/status
      looked untriggered because checkOnboarding() lives in 24-onboarding.js
      while the boot timer calling it lives in 01-app-core.js. Cross-file
      wiring is the normal shape here.

      Then the check was removed entirely, because it was asking the wrong
      question. /api/obsidian/status runs when the Obsidian pane renders. That
      is CORRECT -- probing every integration on boot would fire dozens of
      requests for panes the user may never open, which is exactly the request
      flood that produced the rate-limit toasts in the hover bug. The real
      property is REACHABLE WITHOUT HUNTING, not CALLED ON BOOT.

   5  NO_CALLER on endpoints with no UI surface at all (/api/ws/status,
      /api/e2e/status, /api/engine/status, /api/sync/status,
      /api/e2e/playwright/status). Verified individually: none has a pane in
      MASTER_PANE_REGISTRY and each is covered by the test suite. They are
      operational and test APIs, not features a user is meant to discover.
      Declared in NO_UI_BY_DESIGN with a reason each, because lumping them in
      with the real finding would have buried it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SWEEP = REPO / "scripts" / "sweep_untriggered_capability.py"
FUSION = REPO / "frontend" / "js" / "41-fusion.js"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SWEEP), *args],
        cwd=REPO, capture_output=True, text=True, timeout=600,
    )


def test_the_sweep_script_exists() -> None:
    assert SWEEP.exists(), "sweep 4 of 4 is missing; the finish line cannot be checked"


def test_the_sweep_reports_zero_findings() -> None:
    """THE GATE."""
    p = _run("--json")
    findings = json.loads(p.stdout)
    assert findings == [], (
        "untriggered-capability sweep found regressions:\n"
        + json.dumps(findings, indent=2)[:4000]
    )
    assert p.returncode == 0


def test_the_ollama_probe_still_has_a_caller() -> None:
    """The instance that defined the class. If this regresses, Bug 4 is back."""
    core = (REPO / "frontend" / "js" / "01-app-core.js").read_text(encoding="utf-8")
    assert "detect-local-models" in core
    assert "window.autoDetectLocalModels" in core
    # REVERT-PROOF MISS, corrected. `core.count(...) >= 2` passed with the
    # CALL deleted, because the definition line
    #     window.autoDetectLocalModels = async function autoDetectLocalModels()
    # contains the name twice on its own. Counting occurrences is not counting
    # call sites. Assert an actual invocation instead.
    import re as _re
    calls = _re.findall(r"window\.autoDetectLocalModels\s*\(\s*\)", core)
    assert calls, (
        "autoDetectLocalModels is defined but never invoked — exactly Bug 4"
    )


def test_the_fusion_routing_table_is_wired() -> None:
    """The one real finding of this sweep."""
    src = FUSION.read_text(encoding="utf-8")
    assert "fusion/route/models" in src, "the endpoint has no caller again"
    assert "fusionLoadRoutingTable" in src
    # Same trap as the Ollama assertion above: count occurrences and a bare
    # definition satisfies it. Require a real call.
    import re as _re
    assert _re.search(r"(?<!function )fusionLoadRoutingTable\s*\(\s*\)", src), (
        "defined but never called — the same defect in a new place"
    )


def test_the_routing_table_renders_with_the_pane_not_behind_a_button() -> None:
    """'Reachable without hunting' is the property. A button the user has to
    find is what made Bug 4 invisible."""
    src = FUSION.read_text(encoding="utf-8")
    render_start = src.index("async function renderFusion")
    render_end = src.index("\n}", src.index("fusionSelectPreset('budget')"))
    body = src[render_start:render_end]
    assert "fusionLoadRoutingTable()" in body, (
        "the routing table must load when the pane renders"
    )
    assert 'data-act-click="fusionLoadRoutingTable' not in src, (
        "click-only defeats the purpose"
    )


def test_the_routing_table_never_breaks_the_pane() -> None:
    """Enrichment must fail silently: a dead endpoint must not blank a pane."""
    src = FUSION.read_text(encoding="utf-8")
    i = src.index("async function fusionLoadRoutingTable")
    body = src[i : src.index("\nasync function fusionRoute", i)]
    assert "try {" in body and "catch" in body
    assert "if (!r.ok) return;" in body, "a non-200 must be tolerated quietly"


def test_endpoints_without_ui_are_declared_with_reasons() -> None:
    """An exclusion without a reason is indistinguishable from an oversight —
    and would hide the next real finding."""
    src = SWEEP.read_text(encoding="utf-8")
    assert "NO_UI_BY_DESIGN" in src
    for route in ("/api/ws/status", "/api/e2e/status", "/api/engine/status",
                  "/api/sync/status", "/api/e2e/playwright/status"):
        assert route in src, f"{route} is neither swept nor explicitly excluded"


def test_the_sweep_does_not_demand_startup_probing() -> None:
    """Guard against correction #1 regressing. Probing every integration on
    boot is itself a defect — it is the request flood behind the rate-limit
    toasts."""
    src = SWEEP.read_text(encoding="utf-8")
    assert "NOT_AT_STARTUP" not in src.replace(
        "DELIBERATELY NOT CHECKED", ""
    ).split("CHECKS")[0] or "DELIBERATELY NOT CHECKED" in src, (
        "the startup check is back; it flags correct pane-render probing"
    )
    assert "REACHABLE WITHOUT HUNTING" in src


def test_the_sweep_derives_routes_from_source() -> None:
    """A hardcoded endpoint list stops sweeping the day someone adds one."""
    src = SWEEP.read_text(encoding="utf-8")
    # The literal in the sweep is a regex: r"@router\.get\(..." — my first
    # assertion looked for the plain string and failed against correct code.
    assert "@router" in src and "router" in src, (
        "routes must be parsed from the routers, not hardcoded"
    )
    assert "ROUTERS.glob" in src, "must scan every router file"
    assert "backend_detect_routes" in src
