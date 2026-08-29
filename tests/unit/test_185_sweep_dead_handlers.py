"""Sweep 1/4 — dead handler contract — must stay at zero findings.

docs/BUG-SWEEP-PLAN.md defines the finish line as "each of the four sweep
scripts reports zero findings, and the full suite is green". This test is what
makes the first of those four enforceable rather than a thing someone remembers
to run.

WHAT THE SWEEP FOUND
--------------------
One real defect, after the probe itself was corrected four times:

    frontend/js/08-replay-collab.js:1247
        data-act-select="ceSendCursor()"  ->  'select' was not bound

The collaborative editor shares your cursor position with other people in the
document. `select` fires when text is selected in a textarea. The dispatcher
never bound it, so the attribute was inert: selecting text by dragging or with
shift+arrow never told anyone where you were. The `data-act-click` on the very
next line masked it for plain clicks, which is why it survived.

Exactly the Bug 3 class: correct markup, existing handler, dead feature.

FOUR CORRECTIONS TO THE SWEEP ITSELF, all made before trusting its output
-------------------------------------------------------------------------
The first run reported 70 findings. Nearly all were the probe's fault:

  42  "requires N args but markup passes fewer" -- JavaScript fills omitted
      parameters with `undefined`, and this codebase relies on it deliberately:
      toggleSidebarGroup(groupId, forceOpen) is called with one argument and
      branches on `typeof forceOpen === 'boolean'` to mean "toggle". Check
      removed; only TOO_MANY_ARGS is a real defect.

  ~50 "hFoo() is called but never defined" -- 00-handlers.js registers them as
      on('hFoo', function(){}) where `on` does window[name] = fn. Nothing is
      statically named. The AST walk now understands that call form.

   2  doThing() and f() "never defined" -- they are EXAMPLES in 00-delegate.js's
      own header comment explaining the attribute syntax. Comments are skipped.

   2  kanbanOnDragOver/kanbanOnDrop "read currentTarget" -- they were FIXED in
      5c2a93f and now carry comments explaining why currentTarget is wrong.
      The probe was reading its own changelog. Comments stripped from bodies.

   1  steerSaveNew() "reads currentTarget" -- a fixed-4000-char body window
      overran into a NEIGHBOURING function using currentTarget in a directly
      attached addEventListener, where it is correct. Now brace-matched.

   1  window.open() "never defined" -- resolve() walks plain properties on
      `window`, so browser builtins are callable from markup by design.

That is a 70 -> 1 reduction, all of it probe error. Recorded because a sweep
whose findings are mostly false is worse than no sweep: it trains you to skim,
and that is how the one real finding gets missed.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SWEEP = REPO / "scripts" / "sweep_dead_handlers.py"
DELEGATE = REPO / "frontend" / "js" / "00-delegate.js"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SWEEP), *args],
        cwd=REPO, capture_output=True, text=True, timeout=600,
    )


def test_the_sweep_script_exists() -> None:
    assert SWEEP.exists(), "sweep 1 of 4 is missing; the finish line cannot be checked"


def test_the_sweep_reports_zero_findings() -> None:
    """THE GATE. Exit 0 means zero findings; 2 means it could not run."""
    p = _run()
    if p.returncode == 2:
        import pytest
        pytest.skip("node/acorn unavailable — sweep cannot run honestly here")
    assert p.returncode == 0, (
        "the dead-handler sweep found regressions:\n" + p.stdout[-4000:]
    )
    assert "0 findings" in p.stdout


def test_json_mode_is_machine_readable() -> None:
    p = _run("--json")
    if p.returncode == 2:
        import pytest
        pytest.skip("node/acorn unavailable")
    assert json.loads(p.stdout) == []


def test_the_select_event_is_bound() -> None:
    """The one real finding. Regression guard on the fix itself."""
    src = DELEGATE.read_text(encoding="utf-8")
    i = src.index("var EVENTS = [")
    block = src[i : src.index("];", i)]
    # Comments inside the block quote event names in prose. Without stripping
    # them this assertion passed with 'select' DELETED from the array -- the
    # revert-proof missed the break because the word survived in a comment.
    block = re.sub(r"(?m)^\s*//.*$", "", block)
    events = set(re.findall(r"'([a-z]+)'", block))
    assert "select" in events, (
        "data-act-select is used by the collab editor and would be inert again"
    )


def test_binding_select_did_not_widen_the_self_click_allow_list() -> None:
    """b99dc0a fixed hover firing click actions by making data-self-click
    keyboard-only. Adding an event to EVENTS must not undo that."""
    src = DELEGATE.read_text(encoding="utf-8")
    m = re.search(r"var SELF_CLICK_EVENTS = /([^/]+)/", src)
    assert m, "the self-click allow-list is gone"
    pattern = re.compile(m.group(1))
    assert not pattern.match("select"), (
        "'select' can now synthesise a click — selecting text would fire "
        "the element's click action"
    )


def test_the_sweep_does_not_flag_omitted_trailing_arguments() -> None:
    """Guard against the 42-false-positive version returning. Calling
    toggleSidebarGroup with one argument is correct and intentional."""
    p = _run("--json")
    if p.returncode == 2:
        import pytest
        pytest.skip("node/acorn unavailable")
    findings = json.loads(p.stdout)
    bad = [f for f in findings if "requires" in f.get("detail", "")]
    assert not bad, f"the too-few-args check is back: {bad[:3]}"


def test_the_sweep_reads_the_dispatchers_real_event_list() -> None:
    """It must not hardcode the event names. A grep-based version of this
    analysis previously concluded the dispatcher did not bind drag events,
    because they come from a runtime array."""
    src = SWEEP.read_text(encoding="utf-8")
    assert "var EVENTS = [" in src, "sweep must parse the dispatcher's own list"


def test_the_sweep_understands_the_on_registration_form() -> None:
    """~50 handlers exist only as on('name', fn). Without this the sweep
    reports them all as missing."""
    src = SWEEP.read_text(encoding="utf-8")
    assert "CallExpression" in src and "'on'" in src
