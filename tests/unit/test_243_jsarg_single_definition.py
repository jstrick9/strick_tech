"""One jsArg, and it is the quoting one (r93, #257).

THE BUG
───────
Two same-named helpers with incompatible contracts fought for one global:

  01-app-core.js      function jsArg(value)  — JSON.stringify + HTML escape.
                                          Emits a COMPLETE QUOTED JS literal
                                          ("ok"), for interpolating an
                                          argument value into a
                                          data-act-click expression.
  00-state-feedback.js  (function () { function jsArg(s) ... window.jsArg = jsArg })()
                                          — esc() only. Emits a RAW ESCAPED
                                          EXPRESSION for embedding a whole
                                          call like `prbRefresh()` in an
                                          attribute. Never quotes.

Both ended up on `window.jsArg`. The bundle concatenates files into one
classic script, so app-core's top-level declaration instantiated first and
state-feedback's IIFE overwrote it at run time — the esc-only version won.

Every `data-act-click="f(${jsArg(strArg)})"` in the app then rendered its
string argument UNQUOTED (`f(ok)`), the delegation shim's literal parser
refused it ("arguments are not literals/placeholders"), and the button
silently did nothing. Numeric ids kept working — JSON.parse('123') is a
valid literal — which is how it survived on main from #210 to #257. It
surfaced when the task-completion audit drove a kanban delete and the
gmDanger confirm button did nothing: real, trusted clicks included. Every
gm dialog confirm/cancel, favourites rows, vault/studio/RAG/marketplace
delete buttons — every string-arg delegated control — was dead.

THE FIX
───────
state-feedback's escaper is renamed `escAttrExpr` (its real contract: escape
a whole expression, never quote) and the `window.jsArg` export is deleted.
The global jsArg that 40+ files resolve from their own scopes is app-core's
top-level declaration — which is the version whose contract they all expect
(test_87 documents it: "emits a complete quoted JS literal").

WHAT THIS FILE PINS
───────────────────
The invariant, stated once: there is exactly ONE jsArg definition in the
frontend, it lives in 01-app-core.js, it quotes, and nothing ever assigns
`window.jsArg` — because any second binding, from any file, in any load
order, recreates the shadow and silently kills every string-arg delegated
button in the product.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS_DIR = ROOT / 'frontend' / 'js'


def _sources():
    return sorted(p for p in JS_DIR.glob('*.js') if p.is_file())


def test_exactly_one_jsarg_definition_and_it_is_app_cores():
    definers = []
    for path in _sources():
        src = path.read_text(encoding='utf-8')
        if re.search(r'\bfunction\s+jsArg\s*\(', src) or re.search(r'\b(?:var|let|const)\s+jsArg\s*=', src):
            definers.append(path.name)
    assert definers == ['01-app-core.js'], (
        f'jsArg must be defined exactly once, in 01-app-core.js. Found: {definers}. '
        'A second definition anywhere recreates the #257 shadow: whichever binding '
        'wins at runtime, half the app\'s data-act-click contract is wrong.'
    )


def test_nothing_assigns_window_jsarg():
    offenders = []
    for path in _sources():
        src = path.read_text(encoding='utf-8')
        if re.search(r'window\s*\.\s*jsArg\s*=', src) or re.search(r'window\s*\[\s*[\'"]jsArg[\'"]\s*\]\s*=', src):
            offenders.append(path.name)
    assert offenders == [], (
        f'window.jsArg is assigned in {offenders}. The global comes from 01-app-core.js\'s '
        'top-level function declaration; any assignment overwrites it for every file '
        'that resolves jsArg from its own scope.'
    )


def test_app_core_jsarg_still_quotes():
    src = (JS_DIR / '01-app-core.js').read_text(encoding='utf-8')
    m = re.search(r'function\s+jsArg\s*\(([^)]*)\)\s*\{(.*?)\n\}', src, re.S)
    assert m, '01-app-core.js no longer defines jsArg — see test_exactly_one_jsarg_definition'
    body = m.group(2)
    assert 'JSON.stringify' in body, (
        'jsArg must emit a complete quoted JS literal (JSON.stringify) — that is the '
        'contract every `${jsArg(...)}` interpolation in the app is written against.'
    )


def test_state_feedback_expression_escaper_is_renamed_and_never_quotes():
    """The OTHER contract — escape a whole JS expression for an attribute —
    must exist (state-feedback's Retry/action buttons need it), must NOT be
    named jsArg, and must not gain quotes of its own."""
    src = (JS_DIR / '00-state-feedback.js').read_text(encoding='utf-8')
    assert 'function escAttrExpr' in src, (
        '00-state-feedback.js should define its expression escaper as escAttrExpr '
        '(escape a whole call like prbRefresh(); never quote it)'
    )
    m = re.search(r'function\s+escAttrExpr\s*\([^)]*\)\s*\{(.*?)\n\s*\}', src, re.S)
    assert m, 'escAttrExpr body not found'
    body = m.group(1)
    assert 'JSON.stringify' not in body, (
        'escAttrExpr escapes an EXPRESSION (prbRefresh()); JSON-quoting it would make '
        "the delegation shim see a string literal where it expects a function call and "
        'refuse it — the Retry button would silently do nothing'
    )
    # its call sites must use the new name
    assert 'jsArg(' not in re.sub(r'//.*', '', src), (
        '00-state-feedback.js still calls jsArg( — its internal action/retry '
        'templates must use escAttrExpr, the raw-expression escaper'
    )
