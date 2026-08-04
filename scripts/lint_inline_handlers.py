#!/usr/bin/env python3
"""CI guard: no untrusted data may be interpolated into an inline handler.

WHY
───
`onclick="f('${value}')"` puts `value` inside a JavaScript string, inside an
HTML attribute. escHtml() does NOT protect that position: the browser
HTML-decodes the attribute BEFORE the JS parser runs, so an escaped quote comes
straight back.

Verified in node:

    escHtml("a'),alert(1),('")  ->  a&#39;),alert(1),(&#39;
    rendered   : onclick="f('a&#39;),alert(1),(&#39;')"
    decoded    : f('a'),alert(1),('')      <- executes

A real instance shipped in this codebase: `onclick="selectMention('@${a.name}')"`
with no server-side validation on agent names, giving stored XSS triggered by
opening the @-mention dropdown.

Cleaning up the 64 occurrences was the easy half. This script is the half that
matters: it makes the invariant permanent, so the next handler written the old
way fails CI instead of shipping.

ALLOWED FORMS
  onclick="f(${jsArg(x)})"          <- correct: quoted JS literal, HTML-encoded
  onclick="f(${JSON.stringify(x)})" <- acceptable: pre-existing pattern
  onclick="f(this.dataset.thing)"   <- best: no interpolation at all
  onclick="f(${v.id})"              <- allowed ONLY via the numeric allowlist
  // inline-handler-ok: <reason>    <- explicit, reviewed escape hatch
"""
from __future__ import annotations

import pathlib
import re
import sys

# on*= (legacy inline) AND data-act= (delegated via 00-delegate.js). Both end
# up executing, so both need the same protection — migrating a handler from one
# to the other must not move it out from under this guard.
ATTR = re.compile(r'\b(?:on[a-z]+|data-act)\s*=\s*"([^"]*)"')
INTERP = re.compile(r'\$\{([^}]*)\}')
MARKER = 'inline-handler-ok'

# Expressions that cannot carry a quote and so cannot break out of the JS
# string. Kept deliberately short: every entry is a promise about a value's
# type, and a wrong promise here is an XSS. Anything not on this list must use
# jsArg().
SAFE_EXPRS = {
    # Integer primary keys (verified INTEGER in the schema).
    'v.id', 'f.id',
    # Developer-authored JS fragments passed as an action string by design;
    # the only dynamic one interpolates an internal pane id.
    'a.action', 'action',
    # Date.now() is a number.
    'Date.now()',
}

# Ternaries producing CSS/style literals contain no caller data.
STYLE_TERNARY = re.compile(r"^[^'\"]*\?\s*'[^']*'\s*:\s*'[^']*'$")

# Ternaries and locals that can only ever yield a number or boolean cannot
# contain a quote, so they cannot break out of the JS string. Matching the
# SHAPE rather than listing names keeps this from becoming a stale allowlist.
NUMERIC_TERNARY = re.compile(r'^[^\'"]*\?\s*\d+\s*:\s*\d+$')
BOOL_OR_COUNTER = re.compile(r'^(is|has|can)[A-Z]\w*$|^\w*\.(frame_no|count|index)$')


def is_safe(expr: str) -> bool:
    expr = expr.strip()
    if expr in SAFE_EXPRS:
        return True
    if expr.startswith('jsArg(') or expr.startswith('JSON.stringify('):
        return True
    if expr.isdigit():
        return True
    if STYLE_TERNARY.match(expr):
        return True
    if NUMERIC_TERNARY.match(expr):
        return True
    return bool(BOOL_OR_COUNTER.match(expr))


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent / 'frontend' / 'js'
    offenders: list[tuple[str, int, str]] = []

    for path in sorted(root.glob('*.js')):
        lines = path.read_text(encoding='utf-8').split('\n')
        for i, line in enumerate(lines, 1):
            if MARKER in line or (i >= 2 and MARKER in lines[i - 2]):
                continue
            # Skip comment lines. Several files DOCUMENT a previously-fixed
            # handler bug by quoting the old code; flagging that prose would
            # push people to delete the explanation, which is the opposite of
            # what this review has been trying to preserve.
            if line.lstrip().startswith(('//', '*', '/*')):
                continue
            for m in ATTR.finditer(line):
                body = m.group(1)
                if '${' not in body:
                    continue
                if 'this.dataset' in body:
                    continue
                for expr in INTERP.findall(body):
                    if not is_safe(expr):
                        offenders.append((path.name, i, expr.strip()[:70]))

    if not offenders:
        print('✓ no unsafe interpolations in inline event handlers')
        return 0

    print('✗ unsafe data interpolated into inline event handlers\n')
    print('  escHtml() does NOT protect a JS string context — the browser')
    print('  HTML-decodes the attribute before the JS parser sees it.')
    print('  Use ${jsArg(value)} (note: jsArg supplies its own quotes),')
    print(f'  or add a "// {MARKER}: <why>" comment if genuinely safe.\n')
    for fn, ln, expr in offenders:
        print(f'  {fn}:{ln}  ->  ${{{expr}}}')
    print(f'\n{len(offenders)} unsafe interpolation(s)')
    return 1


if __name__ == '__main__':
    sys.exit(main())
