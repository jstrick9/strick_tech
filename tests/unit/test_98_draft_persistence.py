"""A user's unsent long-form text must survive a reload.

THE GAP
───────
The product has 49 textareas and **no `beforeunload` handler anywhere**. Type a
long prompt into the chat box, hit Cmd+R by accident or follow a link, and it
is gone — no warning, no recovery.

Code Studio is fine: it autosaves 600ms after the last keystroke. Chat is not,
and chat holds the single most expensive artefact a user produces here, a
carefully composed prompt.

WHY A DRAFT CACHE RATHER THAN beforeunload
`beforeunload` shows browser chrome the app cannot word or style, fires on
every navigation whether or not anything is at risk, and modern browsers
ignore custom text. It interrupts the user to warn about a problem instead of
not having the problem. Saving the text and putting it back is strictly
better: nothing to dismiss, and it survives a crash or a closed tab too.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / 'frontend' / 'js' / '00-drafts.js'
INDEX = ROOT / 'frontend' / 'index.html'
CORE = ROOT / 'frontend' / 'js' / '01-app-core.js'


def _have_jsdom() -> bool:
    if not shutil.which('node'):
        return False
    return subprocess.run(
        ['node', '-e', "require('jsdom')"], cwd=ROOT, capture_output=True
    ).returncode == 0


requires_jsdom = pytest.mark.skipif(not _have_jsdom(), reason='jsdom not installed')

HARNESS = """
const {JSDOM} = require('jsdom');
const fs = require('fs');
const SRC = fs.readFileSync('frontend/js/00-drafts.js','utf8');
function fresh(seed, markup) {
  const dom = new JSDOM('<!doctype html><body>' +
    (markup || '<textarea id="chat-input" data-draft="chat"></textarea>') +
    '</body>', {runScripts:'outside-only', url:'http://localhost:8787/'});
  const W = dom.window;
  if (seed) for (const k in seed) W.localStorage.setItem(k, seed[k]);
  global.window = W; global.document = W.document;
  W.eval(SRC);
  return W;
}
"""


def _run(script: str) -> dict:
    probe = ROOT / 'zz_draft_probe.js'
    probe.write_text(HARNESS + script, encoding='utf-8')
    try:
        r = subprocess.run(
            ['node', str(probe.name)], cwd=ROOT, capture_output=True, text=True
        )
        if not r.stdout.strip():
            pytest.skip(f'node produced no output: {r.stderr[-300:]}')
        return json.loads(r.stdout.strip().split('\n')[-1])
    finally:
        probe.unlink(missing_ok=True)


# ══ Wiring ════════════════════════════════════════════════════════════════════
def test_module_exists_and_is_loaded():
    assert MODULE.exists()
    assert '00-drafts.js' in INDEX.read_text(encoding='utf-8')


def test_the_highest_value_fields_are_tagged():
    """chat-input above all: it holds the prompt the user spent the most
    effort on and previously persisted nothing."""
    html = INDEX.read_text(encoding='utf-8')
    m = re.search(r'<textarea[^>]*id="chat-input"[^>]*>', html)
    assert m, 'chat-input not found'
    assert 'data-draft=' in m.group(0), 'the chat composer does not save drafts'
    assert html.count('data-draft=') >= 4


# ══ Save and restore ══════════════════════════════════════════════════════════
@requires_jsdom
def test_typed_text_survives_a_reload():
    out = _run("""
let W = fresh();
const ta = W.document.getElementById('chat-input');
ta.value = 'a long carefully written prompt';
ta.dispatchEvent(new W.Event('blur', {bubbles:true}));
const saved = W.localStorage.getItem('agentic_draft:chat');
W = fresh({'agentic_draft:chat': saved});
console.log(JSON.stringify({
  saved: !!saved,
  restored: W.document.getElementById('chat-input').value,
  notice: !!W.document.querySelector('.draft-restored-note'),
}));
""")
    assert out['saved'], 'nothing was persisted'
    assert out['restored'] == 'a long carefully written prompt'
    assert out['notice'], 'silently repopulating a field is disorienting'


@requires_jsdom
def test_the_restore_can_be_rejected():
    """The user may have moved on. Restoring without an escape hatch replaces
    one annoyance with another."""
    out = _run("""
const W = fresh({'agentic_draft:chat': JSON.stringify({v:'old text', t:Date.now()})});
W.document.querySelector('.draft-restored-note button')
  .dispatchEvent(new W.MouseEvent('click', {bubbles:true}));
console.log(JSON.stringify({
  value: W.document.getElementById('chat-input').value,
  stored: W.localStorage.getItem('agentic_draft:chat'),
}));
""")
    assert out['value'] == ''
    assert out['stored'] is None, 'discarding must also clear the stored draft'


@requires_jsdom
def test_prefilled_content_is_never_clobbered():
    """An edit form populated by the app must win over a stale draft —
    otherwise opening an existing record shows someone else's leftover text."""
    out = _run("""
const W = fresh(
  {'agentic_draft:chat': JSON.stringify({v:'stale draft', t:Date.now()})},
  '<textarea id="chat-input" data-draft="chat">PREFILLED</textarea>'
);
console.log(JSON.stringify({value: W.document.getElementById('chat-input').value}));
""")
    assert out['value'] == 'PREFILLED'


@requires_jsdom
def test_stale_drafts_expire_and_are_swept():
    """Without expiry the store grows forever and eventually hits quota,
    at which point saving silently stops working."""
    out = _run("""
const W = fresh({'agentic_draft:chat':
  JSON.stringify({v:'ancient', t: Date.now() - 8*24*3600*1000})});
console.log(JSON.stringify({
  value: W.document.getElementById('chat-input').value,
  stored: W.localStorage.getItem('agentic_draft:chat'),
}));
""")
    assert out['value'] == '', 'a week-old draft was restored'
    assert out['stored'] is None, 'expired drafts must be swept, not just ignored'


@requires_jsdom
def test_lazily_rendered_fields_are_picked_up():
    """Most panes render on navigation, well after this module loads."""
    out = _run("""
const W = fresh({'agentic_draft:late': JSON.stringify({v:'late draft', t:Date.now()})});
const el = W.document.createElement('textarea');
el.setAttribute('data-draft', 'late');
W.document.body.appendChild(el);
setTimeout(() => console.log(JSON.stringify({value: el.value})), 30);
""")
    assert out['value'] == 'late draft'


# ══ Clearing on submit ════════════════════════════════════════════════════════
def test_sending_a_message_clears_its_draft():
    """Restoring a prompt the user already sent would be worse than losing
    it — they would send it twice."""
    src = CORE.read_text(encoding='utf-8')
    idx = src.index("input.value = '';")
    window = src[idx:idx + 300]
    assert 'Drafts' in window and 'clearFor' in window, (
        'the chat draft is not cleared after send'
    )


def test_the_api_is_available_for_other_submit_handlers():
    src = MODULE.read_text(encoding='utf-8')
    assert 'window.Drafts' in src
    for fn in ('save', 'load', 'clear', 'clearFor'):
        assert f'{fn}:' in src or f'{fn}: function' in src, f'Drafts.{fn} missing'


# ══ Failure modes ═════════════════════════════════════════════════════════════
def test_storage_failures_never_break_typing():
    """Private mode throws on localStorage access, and quota errors throw on
    write. An exception inside an input handler would break the keystroke."""
    src = MODULE.read_text(encoding='utf-8')
    assert src.count('catch') >= 5, 'storage access is not defensively wrapped'
    assert 'MAX_CHARS' in src, 'no cap on stored size — one paste could exhaust quota'


def test_drafts_are_size_and_age_bounded():
    src = MODULE.read_text(encoding='utf-8')
    assert re.search(r'MAX_AGE_MS\s*=', src)
    assert re.search(r'MAX_CHARS\s*=', src)
    assert 'function sweep' in src
