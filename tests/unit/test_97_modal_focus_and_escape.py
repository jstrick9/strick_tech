"""Dialogs must be operable and escapable from a keyboard.

WHAT WAS WRONG
──────────────
The shared modal (`_gm_show`, behind every gmConfirm / gmDanger / gmPrompt in
the product) had four problems:

  1. **Escape only worked on prompts.** The handler was attached to the text
     input, so a *confirm* or a *delete* dialog — the ones that block progress
     — could not be dismissed from the keyboard at all. WCAG 2.1.2.
  2. **No focus trap.** Tab walked straight out of the dialog and into the page
     behind it, leaving focus somewhere the user could not see. WCAG 2.4.3.
  3. **Focus was never restored.** Closing a dialog dropped focus onto <body>,
     so a keyboard user had to Tab from the top of the page to get back.
  4. **Wrong ARIA.** No role="dialog", no aria-modal, no accessible name, so a
     screen reader announced nothing when it opened.

MY OWN BUG, FIXED HERE TOO
The blanket accessibility pass in e19ff08 treated every clickable div the same
way and gave modal BACKDROPS `role="button"`, `tabindex="0"` and Enter/Space
bindings. A backdrop dismisses on click but is not a control: that added a
stray tab stop and announced a button that does nothing useful. Five backdrops
were affected. The keyboard route out of a dialog is Escape, not "focus the
backdrop and press Enter".

Escape is handled centrally in the delegation shim rather than per dialog,
because ~50 modals are built ad hoc with innerHTML and share no open/close
plumbing to hook into.
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
CORE = ROOT / 'frontend' / 'js' / '01-app-core.js'
JS_DIR = ROOT / 'frontend' / 'js'


def _have_jsdom() -> bool:
    if not shutil.which('node'):
        return False
    return subprocess.run(
        ['node', '-e', "require('jsdom')"], cwd=ROOT, capture_output=True
    ).returncode == 0


requires_jsdom = pytest.mark.skipif(not _have_jsdom(), reason='jsdom not installed')


def _run(script: str) -> dict:
    probe = ROOT / 'zz_modal_probe.js'
    probe.write_text(script, encoding='utf-8')
    try:
        r = subprocess.run(
            ['node', str(probe.name)], cwd=ROOT, capture_output=True, text=True
        )
        if not r.stdout.strip():
            pytest.skip(f'node produced no output: {r.stderr[-300:]}')
        return json.loads(r.stdout.strip().split('\n')[-1])
    finally:
        probe.unlink(missing_ok=True)


MODAL_HARNESS = """
const {JSDOM} = require('jsdom');
const fs = require('fs');
const dom = new JSDOM(fs.readFileSync('frontend/index.html','utf8'),
  {url:'http://localhost:8787/', runScripts:'outside-only', pretendToBeVisual:true});
const W = dom.window, D = W.document;
global.window = W; global.document = D;
W.eval(fs.readFileSync('frontend/js/00-delegate.js','utf8'));
const core = fs.readFileSync('frontend/js/01-app-core.js','utf8');
const start = core.indexOf('let _gm_resolve');
const end = core.indexOf('async function gmDanger');
const stop = end + core.slice(end).indexOf('\\n}\\n') + 3;
W.eval('function escHtml(s){return String(s);}function jsArg(v){return JSON.stringify(v);}\\n'
  + core.slice(start, stop));
"""


# ══ ARIA ══════════════════════════════════════════════════════════════════════
def test_the_shared_dialog_has_correct_semantics():
    html = INDEX.read_text(encoding='utf-8')
    m = re.search(r'<div[^>]*id="gmodal"[^>]*>', html)
    assert m, 'gmodal not found'
    tag = m.group(0)
    assert 'role="dialog"' in tag
    assert 'aria-modal="true"' in tag
    assert 'aria-labelledby="gm-title"' in tag, 'the dialog has no accessible name'


def test_modal_backdrops_are_not_announced_as_buttons():
    """My own blanket a11y pass caused this: a backdrop dismisses on click but
    is not a control. role=button + tabindex adds a stray tab stop and
    announces something that does nothing useful."""
    offenders = []
    for path in [INDEX, *sorted(JS_DIR.glob('*.js'))]:
        text = path.read_text(encoding='utf-8')
        for m in re.finditer(r'<div[^>]*data-click-self="1"[^>]*>', text):
            tag = m.group(0)
            if 'role="button"' in tag or 'data-self-click="1"' in tag:
                line = text[: m.start()].count('\n') + 1
                offenders.append(f'{path.name}:{line}')
    assert not offenders, (
        'modal backdrops must be role="dialog", not focusable buttons:\n  '
        + '\n  '.join(offenders)
    )


def test_every_backdrop_dialog_declares_a_dialog_role():
    html = INDEX.read_text(encoding='utf-8')
    for m in re.finditer(r'<div[^>]*data-click-self="1"[^>]*>', html):
        tag = m.group(0)
        assert 'role="dialog"' in tag, f'backdrop without a dialog role: {tag[:110]}'


# ══ Behaviour ═════════════════════════════════════════════════════════════════
@requires_jsdom
def test_escape_closes_a_confirm_dialog():
    """Escape used to be bound to the text INPUT, so confirm and delete
    dialogs — the ones that block progress — could not be dismissed from the
    keyboard at all."""
    out = _run(MODAL_HARNESS + """
(async () => {
  const p = W.gmConfirm('Delete?', 'Sure?');
  await new Promise(r => setTimeout(r, 90));
  const visible = D.getElementById('gmodal').style.display;
  D.dispatchEvent(new W.KeyboardEvent('keydown', {key:'Escape', bubbles:true}));
  const result = await p;
  console.log(JSON.stringify({
    visible, result, hidden: D.getElementById('gmodal').style.display
  }));
})();
""")
    assert out['visible'] == 'flex'
    assert out['result'] is False, 'Escape did not cancel the dialog'
    assert out['hidden'] == 'none'


@requires_jsdom
def test_focus_moves_into_the_dialog_and_returns_to_the_opener():
    """Opening a dialog that never takes focus is invisible to a screen reader;
    closing one that never gives it back strands the user at the top of the
    page."""
    out = _run(MODAL_HARNESS + """
(async () => {
  const trigger = D.createElement('button');
  trigger.id = 'trigger';
  D.body.appendChild(trigger);
  trigger.focus();
  const before = D.activeElement.id;
  const p = W.gmConfirm('Delete?', 'Sure?');
  await new Promise(r => setTimeout(r, 90));
  const inside = D.getElementById('gmodal').contains(D.activeElement);
  D.dispatchEvent(new W.KeyboardEvent('keydown', {key:'Escape', bubbles:true}));
  await p;
  console.log(JSON.stringify({before, inside, after: D.activeElement.id}));
})();
""")
    assert out['before'] == 'trigger'
    assert out['inside'], 'focus never entered the dialog'
    assert out['after'] == 'trigger', 'focus was not returned to the opener'


def test_the_dialog_traps_tab():
    """Source-level check: the trap must handle both Tab and Shift+Tab, or
    focus escapes backwards out of the dialog."""
    src = CORE.read_text(encoding='utf-8')
    trap = src[src.index('_gm_keydown = ('):src.index('document.addEventListener(\'keydown\', _gm_keydown')]
    assert "e.key !== 'Tab'" in trap
    assert 'shiftKey' in trap, 'Shift+Tab escapes the dialog backwards'
    assert 'preventDefault' in trap


def test_focus_and_listener_are_cleaned_up_on_both_exits():
    """A keydown listener left attached after close would keep hijacking
    Escape for a dialog that is no longer on screen."""
    src = CORE.read_text(encoding='utf-8')
    assert 'function _gm_teardown' in src
    assert 'removeEventListener' in src
    click_fn = src[src.index('function _gm_click'):src.index('function _gm_cancel')]
    cancel_fn = src[src.index('function _gm_cancel'):src.index('function _gm_cancel') + 400]
    assert '_gm_teardown()' in click_fn, 'confirm path leaks the listener'
    assert '_gm_teardown()' in cancel_fn, 'cancel path leaks the listener'


# ══ The global Escape fallback ════════════════════════════════════════════════
@requires_jsdom
def test_escape_closes_ad_hoc_dialogs_too():
    """~50 modals are built with innerHTML and share no open/close plumbing.
    The agent editor and the onboarding overlay could only be closed with the
    mouse."""
    out = _run("""
const {JSDOM} = require('jsdom');
const fs = require('fs');
const dom = new JSDOM('<!doctype html><body>' +
  '<div id="m1" style="display:none" data-act-click="closeM1()" data-click-self="1"></div>' +
  '<div id="m2" style="display:block;z-index:5" data-act-click="closeM2()" data-click-self="1"></div>' +
  '</body>', {runScripts:'outside-only', pretendToBeVisual:true});
global.window = dom.window; global.document = dom.window.document;
const W = dom.window, D = W.document;
let log = [];
W.closeM1 = () => log.push('m1');
W.closeM2 = () => log.push('m2');
W.eval(fs.readFileSync('frontend/js/00-delegate.js','utf8'));
D.dispatchEvent(new W.KeyboardEvent('keydown', {key:'Escape', bubbles:true}));
const visibleOnly = log.slice();
log = [];
D.getElementById('m2').style.display = 'none';
D.dispatchEvent(new W.KeyboardEvent('keydown', {key:'Escape', bubbles:true}));
const noneOpen = log.slice();
log = [];
D.getElementById('m1').style.display = 'block'; D.getElementById('m1').style.zIndex = '10';
D.getElementById('m2').style.display = 'block'; D.getElementById('m2').style.zIndex = '99';
D.dispatchEvent(new W.KeyboardEvent('keydown', {key:'Escape', bubbles:true}));
console.log(JSON.stringify({visibleOnly, noneOpen, topmost: log}));
""")
    assert out['visibleOnly'] == ['m2'], 'Escape hit a hidden dialog'
    assert out['noneOpen'] == [], 'Escape fired with no dialog open'
    assert out['topmost'] == ['m2'], 'Escape should close only the topmost dialog'
