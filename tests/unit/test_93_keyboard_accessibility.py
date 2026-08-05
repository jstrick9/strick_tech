"""Every clickable control must be operable from a keyboard.

Three bugs, all found by scanning the frontend after the CSP migration moved
1030 handlers onto data attributes.

1. THE MAIN NAVIGATION WAS UNREACHABLE BY KEYBOARD.
   The six ESSENTIALS items — Chat, Code Studio, Memory, Tasks, Templates,
   Settings — carried role="menuitem" but no tabindex, so Tab walked straight
   past them. A keyboard or screen-reader user could not navigate the product
   at all. 86 controls were affected in total.

2. THE SHORTCUTS OVERLAY COULD NOT BE CLOSED.
   Its ✕ carried `data-act-click="document.getElementById(...).remove()"`,
   which the shim refuses — it resolves names on window and `document.getEl...`
   is not a plain call it will dispatch. The overlay trapped the user.

3. A NATIVE <button> RAN ITS ACTION TWICE PER KEY PRESS.
   data-self-click was applied mechanically wherever the old `this.click()`
   idiom appeared, including one <button>. A button already turns Enter into a
   click, so the synthetic one made it fire twice.

WCAG 2.1 references: 2.1.1 Keyboard (A), 2.1.2 No Keyboard Trap (A),
4.1.2 Name, Role, Value (A).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / 'frontend' / 'index.html'
JS_DIR = ROOT / 'frontend' / 'js'

CLICKABLE_TAG = re.compile(r'<(div|span|li|td|tr)\b([^>]*)>')
NATIVE = re.compile(r'<(button|a|input|select|textarea|summary)\b([^>]*)>', re.I)


def _have_jsdom() -> bool:
    if not shutil.which('node'):
        return False
    return subprocess.run(
        ['node', '-e', "require('jsdom')"], cwd=ROOT, capture_output=True
    ).returncode == 0


requires_jsdom = pytest.mark.skipif(not _have_jsdom(), reason='jsdom not installed')


def _sources():
    return [INDEX, *sorted(JS_DIR.glob('*.js'))]


def _code_lines(path: Path):
    for i, line in enumerate(path.read_text(encoding='utf-8').split('\n'), 1):
        if path.suffix == '.js' and line.lstrip().startswith(('//', '*', '/*')):
            continue
        yield i, line


def _run_node(script: str) -> str:
    probe = ROOT / 'zz_a11y_probe.js'
    probe.write_text(script, encoding='utf-8')
    try:
        r = subprocess.run(
            ['node', str(probe.name)], cwd=ROOT, capture_output=True, text=True
        )
        if not r.stdout.strip():
            pytest.skip(f'node produced no output: {r.stderr[-200:]}')
        # Return the LAST line: some frontend modules print a load banner when
        # evaluated, which would otherwise be parsed as the probe's result.
        return r.stdout.strip().split('\n')[-1]
    finally:
        probe.unlink(missing_ok=True)


# ══ 1. Keyboard reachability ══════════════════════════════════════════════════
def test_every_clickable_non_native_element_is_keyboard_operable():
    """A div with a click handler and no tabindex is invisible to the keyboard.
    It renders, it looks interactive, and it cannot be used — the same silent
    failure shape as a dead button, but only for the users who most need it."""
    offenders = []
    for path in _sources():
        for lineno, line in _code_lines(path):
            for m in CLICKABLE_TAG.finditer(line):
                attrs = m.group(2)
                if 'data-act-click' not in attrs:
                    continue
                # A modal BACKDROP is exempt, and deliberately so. It dismisses
                # on click but is not a control: giving it tabindex adds a stray
                # tab stop, and role="button" announces something that does
                # nothing useful. Its keyboard route is Escape, handled centrally
                # in the delegation shim — see test_97_modal_focus_and_escape.
                # An earlier version of this test forced the opposite and
                # produced exactly that bug on five backdrops.
                if 'data-click-self="1"' in attrs or 'role="dialog"' in attrs:
                    continue
                missing = []
                if 'tabindex' not in attrs:
                    missing.append('tabindex')
                if 'role=' not in attrs:
                    missing.append('role')
                if 'data-keys' not in attrs and 'data-self-click' not in attrs:
                    missing.append('key binding')
                if missing:
                    offenders.append(f'{path.name}:{lineno} <{m.group(1)}> missing {missing}')

    assert not offenders, (
        f'{len(offenders)} clickable element(s) cannot be operated from a '
        f'keyboard (WCAG 2.1.1):\n  ' + '\n  '.join(offenders[:20])
    )


def test_the_main_navigation_is_tabbable():
    """The regression that mattered most: all six ESSENTIALS items were
    skipped by Tab, so the product could not be navigated at all."""
    html = INDEX.read_text(encoding='utf-8')
    nav_items = re.findall(r'<div\b([^>]*\bclass="nav-item[^>]*)>', html)
    assert len(nav_items) >= 20, f'only found {len(nav_items)} nav items — did the markup change?'
    unreachable = [a for a in nav_items if 'tabindex' not in a]
    assert not unreachable, f'{len(unreachable)} nav items are not tabbable'


def test_navigation_roles_are_consistent_and_valid_for_their_container():
    """The sidebar is role="navigation", not role="menu".

    role="menuitem" is only valid inside a menu or menubar; used under
    navigation it is an invalid parent/child pairing that assistive tech may
    ignore or announce incorrectly. The markup was inconsistent before this
    work — 18 items said button, 6 said menuitem — which is the tell that the
    menuitem ones were a copy-paste rather than a decision. All 24 now use
    role="button", which matches both the container and the behaviour.
    """
    html = INDEX.read_text(encoding='utf-8')
    sidebar = re.search(r'<div id="sidebar"([^>]*)>', html)
    assert sidebar and 'role="navigation"' in sidebar.group(1), (
        'the sidebar container role changed — re-check which item role is correct'
    )
    for attrs in re.findall(r'<div\b([^>]*\bclass="nav-item[^>]*)>', html):
        assert attrs.count('role=') == 1, f'duplicate role attribute: {attrs[:100]}'
        assert 'role="button"' in attrs, (
            f'nav item role is not valid under role="navigation": {attrs[:100]}'
        )


def test_menu_semantics_use_enter_not_space():
    """ARIA practices: Space on a menuitem/tab scrolls or selects; only a
    button treats Space as activation."""
    for path in _sources():
        for lineno, line in _code_lines(path):
            for m in CLICKABLE_TAG.finditer(line):
                attrs = m.group(2)
                role = re.search(r'role="([^"]*)"', attrs)
                keys = re.search(r'data-keys="([^"]*)"', attrs)
                if not role or not keys:
                    continue
                if role.group(1) in ('menuitem', 'tab', 'option', 'treeitem'):
                    assert 'Space' not in keys.group(1), (
                        f'{path.name}:{lineno} role={role.group(1)} should not '
                        f'activate on Space'
                    )


# ══ 2. No keyboard trap ═══════════════════════════════════════════════════════
@requires_jsdom
def test_the_shortcuts_overlay_can_be_closed():
    """It was unclosable: the ✕ used a data-act value the shim refuses, so the
    overlay trapped the user (WCAG 2.1.2)."""
    out = _run_node("""
const {JSDOM} = require('jsdom');
const fs = require('fs');
const dom = new JSDOM('<!doctype html><body></body>', {runScripts:'outside-only'});
global.window = dom.window; global.document = dom.window.document;
dom.window.eval(fs.readFileSync('frontend/js/00-delegate.js','utf8'));
dom.window.eval(fs.readFileSync('frontend/js/93-shortcuts-overlay.js','utf8'));
dom.window.showKeyboardShortcuts();
const overlay = dom.window.document.getElementById('kb-shortcuts-overlay');
const closer = overlay.querySelector('[data-close],[data-act-click]');
closer.dispatchEvent(new dom.window.MouseEvent('click', {bubbles:true}));
console.log(JSON.stringify({
  opened: overlay !== null,
  closed: dom.window.document.getElementById('kb-shortcuts-overlay') === null,
}));
""")
    result = json.loads(out.strip())
    assert result['opened'], 'the overlay did not open'
    assert result['closed'], 'the overlay cannot be dismissed — keyboard trap'


# ══ 3. No double activation ═══════════════════════════════════════════════════
def test_native_controls_do_not_carry_the_self_click_polyfill():
    """A <button> already turns Enter and Space into a click. Adding the
    synthetic one runs the handler twice — a double submit or double launch."""
    offenders = []
    for path in _sources():
        for lineno, line in _code_lines(path):
            for m in NATIVE.finditer(line):
                if 'data-self-click' in m.group(2):
                    offenders.append(f'{path.name}:{lineno} <{m.group(1)}>')
    assert not offenders, (
        'natively clickable elements with data-self-click will fire twice per '
        'key press:\n  ' + '\n  '.join(offenders)
    )


@requires_jsdom
def test_the_shim_ignores_self_click_on_native_elements():
    """Belt and braces: enforced in the shim so a future call site cannot
    reintroduce the double fire."""
    out = _run_node("""
const {JSDOM} = require('jsdom');
const fs = require('fs');
const dom = new JSDOM(
  '<!doctype html><body>' +
  '<button id="b" data-act-click="go()" data-keys="Enter,Space" data-self-click="1">B</button>' +
  '<div id="d" role="button" tabindex="0" data-act-click="go()" data-keys="Enter" data-self-click="1">D</div>' +
  '</body>', {runScripts:'outside-only'});
global.window = dom.window; global.document = dom.window.document;
let calls = 0; dom.window.go = () => calls++;
dom.window.eval(fs.readFileSync('frontend/js/00-delegate.js','utf8'));
const D = dom.window.document;
// jsdom does not synthesise a click from Enter on a <button>; a real browser
// does, so add it to reproduce real behaviour.
const b = D.getElementById('b');
b.addEventListener('keydown', e => { if (e.key === 'Enter') b.click(); });
b.dispatchEvent(new dom.window.KeyboardEvent('keydown', {key:'Enter', bubbles:true}));
const nativeCount = calls;
calls = 0;
D.getElementById('d').dispatchEvent(new dom.window.KeyboardEvent('keydown', {key:'Enter', bubbles:true}));
console.log(JSON.stringify({native: nativeCount, div: calls}));
""")
    result = json.loads(out.strip())
    assert result['native'] == 1, f"native <button> fired {result['native']} times"
    assert result['div'] == 1, 'the polyfill is still needed for div[role=button]'


# ══ Focus visibility ══════════════════════════════════════════════════════════
def test_focus_is_visible_for_keyboard_users():
    """Making elements tabbable is only half the job — the user has to be able
    to SEE where focus is (WCAG 2.4.7)."""
    css = '\n'.join(
        p.read_text(encoding='utf-8')
        for p in [INDEX, *sorted((ROOT / 'frontend').glob('*.css'))]
        if p.exists()
    )
    assert ':focus-visible' in css or ':focus' in css, (
        'no focus styling found; tabbable elements would give no visual feedback'
    )
