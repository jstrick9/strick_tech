"""Hovering the sidebar expanded sections and made the UI unclickable.

Reported, verbatim:

    "When I mouse over the sidebar sections like AI Tools, BUILD & SHIP, etc.
     it automatically opens up the section without me having to click to
     expand and the sidebar starts to glitch where I have a hard time trying
     to click on the different modules in each section of the sidebar."

This is the "glitchy clicking" from the original four-bug report. Three earlier
sessions failed to reproduce it because I was clicking, not hovering.

ROOT CAUSE -- frontend/js/00-delegate.js
----------------------------------------
`data-self-click="1"` is a KEYBOARD accessibility polyfill. A <div role=button>
is not natively operable by Enter/Space, so the dispatcher re-dispatches a
click on it. The condition guarding that was:

    el.getAttribute('data-self-click') === '1'
      && type !== 'click'                        <-- deny-list
      && el.click
      && !NATIVELY_CLICKABLE.test(el.tagName)

`type !== 'click'` is a deny-list, and the dispatcher binds SEVENTEEN event
types (00-delegate.js line ~51):

    click change input dblclick blur focus mouseover mouseout mousemove
    keydown keyup submit dragstart dragend dragover dragleave drop error

Sixteen of them satisfy `type !== 'click'`. So mouseover, mouseout, mousemove,
focus, blur and all six drag events synthesised a click on any element carrying
data-self-click. index.html has 52 of them -- every sidebar group header and
every nav item.

Consequences, both reported:
  - moving the pointer over "AI TOOLS" ran toggleSidebarGroup('build') and the
    section expanded with no click
  - mousemove fires continuously, so a pointer resting on a nav item
    re-triggered its action on every pixel of movement. Sections opened and
    closed under the cursor while the user was trying to aim at a module --
    the "glitching" and "hard time trying to click".

MEASURED IN CHROMIUM, before the fix. A bare page.mouse.move() onto the
"AI TOOLS" header, with no click anywhere in the script, produced:

    calls: [{group: "build", force: null, evt: "click",
             stack: "at window.toggleSidebarGroup | at callOne | at dispatch
                     | at handle | at HTMLDocument.<anonymous>"}]
    buildDisplay: "block"

A pure mouse move dispatched a click through the delegate. Hovering all five
headers left every one of them display:block.

THE FIX
-------
Replace the deny-list with an allow-list:

    var SELF_CLICK_EVENTS = /^key(down|up)$/;

A deny-list silently grows every time the dispatcher learns a new event type.
An allow-list states the actual intent: this polyfill exists for the keyboard,
so only keyboard events may drive it.

VERIFIED AFTER THE FIX, same browser, same server:
    hover sweep across all 5 headers -> HOVER_OPENED_ANY []
    mousemove storm over a nav item  -> HOVER_NAVIGATED false
    click on a header                -> opens (block)
    Enter on a focused header        -> opens (block)   <- polyfill still works
    pageerrors []
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DELEGATE = REPO / "frontend" / "js" / "00-delegate.js"
INDEX = REPO / "frontend" / "index.html"


def _src() -> str:
    return DELEGATE.read_text(encoding="utf-8")


def _bound_events() -> list[str]:
    s = _src()
    i = s.index("var EVENTS = [")
    block = s[i : s.index("];", i)]
    return re.findall(r"'([a-z]+)'", block)


def test_self_click_uses_an_allow_list_not_a_deny_list() -> None:
    assert "SELF_CLICK_EVENTS" in _src(), (
        "the synthetic-click guard must name an explicit allow-list of events"
    )


def test_the_allow_list_is_keyboard_only() -> None:
    m = re.search(r"var SELF_CLICK_EVENTS = /([^/]+)/", _src())
    assert m, "SELF_CLICK_EVENTS regex not found"
    pattern = re.compile(m.group(1))
    for ev in ("keydown", "keyup"):
        assert pattern.match(ev), f"{ev} must be allowed -- it is the whole point"
    for ev in ("mouseover", "mouseout", "mousemove", "focus", "blur",
               "dragstart", "dragend", "dragover", "dragleave", "drop",
               "change", "input", "error", "submit", "dblclick"):
        assert not pattern.match(ev), (
            f"{ev} can synthesise a click -- hovering a sidebar header would "
            "run its action without a click"
        )


def test_no_bound_event_other_than_keys_can_synthesise_a_click() -> None:
    """Ties the guard to the ACTUAL bound-event list, so adding a new event
    type to EVENTS cannot silently re-open this hole."""
    m = re.search(r"var SELF_CLICK_EVENTS = /([^/]+)/", _src())
    pattern = re.compile(m.group(1))
    leaking = [e for e in _bound_events() if pattern.match(e) and not e.startswith("key")]
    assert not leaking, f"non-keyboard events would synthesise a click: {leaking}"


def test_mousemove_is_still_bound_but_cannot_click() -> None:
    """mousemove must stay bound (data-hover styling needs it) while being
    unable to reach the synthetic click. Its continuous firing is what turned
    one stray hover into the 'glitching'."""
    assert "mousemove" in _bound_events()
    m = re.search(r"var SELF_CLICK_EVENTS = /([^/]+)/", _src())
    assert not re.compile(m.group(1)).match("mousemove")


def test_the_synthetic_click_block_is_gated_by_the_allow_list() -> None:
    s = _src()
    i = s.index("el.getAttribute('data-self-click') === '1'\n      && SELF_CLICK_EVENTS")
    block = s[i : s.index("el.click();", i)]
    assert "type !== 'click'" not in block, (
        "the old deny-list is still present in the synthetic-click guard"
    )


def test_the_early_return_guard_is_also_gated() -> None:
    """There are TWO places data-self-click is consulted. Fixing only the
    synthetic click would still let non-keyboard events past the early return
    and run the handler through the normal dispatch path."""
    line = next(
        ln for ln in _src().splitlines() if "var hasSelfClick" in ln
    )
    assert "SELF_CLICK_EVENTS" in line, (
        f"hasSelfClick still uses a deny-list: {line.strip()!r}"
    )


def test_keyboard_activation_of_a_non_native_control_still_works() -> None:
    """The polyfill must not be neutered: the natively-clickable exclusion has
    to stay, or <button> double-fires."""
    s = _src()
    i = s.index("&& SELF_CLICK_EVENTS.test(type)")
    block = s[i : s.index("el.click();", i)]
    assert "NATIVELY_CLICKABLE" in block, (
        "dropping the native-element exclusion makes Enter fire twice on <button>"
    )


def test_the_sidebar_headers_that_broke_are_still_keyboard_operable() -> None:
    """The five group headers are div[role=button] and rely on this polyfill."""
    html = INDEX.read_text(encoding="utf-8")
    headers = re.findall(r'<div[^>]*toggleSidebarGroup\(\'(\w+)\'\)[^>]*>', html)
    assert len(headers) >= 5, f"expected the sidebar group headers, found {headers}"
    for m in re.finditer(r'<div([^>]*toggleSidebarGroup[^>]*)>', html):
        attrs = m.group(1)
        assert 'data-self-click="1"' in attrs, "header lost its keyboard polyfill"
        assert "data-keys=" in attrs, "header lost its key gating"


def test_delegate_is_syntactically_valid() -> None:
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        import pytest

        pytest.skip("node not available")
    proc = subprocess.run([node, "--check", str(DELEGATE)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
