#!/usr/bin/env python3
"""Convert inline on*= handlers to the data-act-* delegation attributes.

SAFETY RULE
───────────
Only rewrite a handler whose meaning is PROVABLE from its text. Everything else
is left inline and reported. Guessing would produce buttons that silently do
nothing, which is exactly the failure mode this review has been removing.

The tool recognises these provable shapes:

  plain call            f('a', 1)                 -> data-act-click="f('a',1)"
  element reads         f(this.value)             -> data-act-input="f($value)"
                        f(this.checked)           -> $checked
                        f(+this.value)            -> $nvalue
                        f(this.dataset.policyId)  -> $data.policyId
                        f(this)                   -> $this
  event object          f(event)                  -> $event  + data-prevent as needed
  stopPropagation       event.stopPropagation();f() -> data-stop="1" + f()
  key gating            if(event.key==='Enter')f() -> data-keys="Enter" + f()
  backdrop click        if(event.target===this)f() -> data-click-self="1" + f()
  node removal          this.closest('X').remove() -> data-close="closest:X"
                        document.getElementById('x').remove() -> data-close="id:x"
                        this.parentElement.remove()           -> data-close="parent"
  hide                  document.getElementById('x').style.display='none'
                                                  -> data-hide="id:x"
  optional call         f?.()                     -> f()
  typeof guard          if(typeof f==='function')f() -> f()   (shim no-ops on
                        unknown names, so the guard is redundant)
  multi-statement       a();b()                   -> data-act-click="a();b()"

Deliberately NOT converted (left inline, reported):
  * hover styling `this.style.background=...` — presentational, belongs in CSS;
    handled separately by scripts/migrate_hover_styles.py
  * `${a.action}` — the value IS a code string chosen by app code, not markup
  * anything else
"""
from __future__ import annotations

import pathlib
import re
import sys
from collections import Counter

# on<event>="<body>"  (double-quoted attribute)
ATTR = re.compile(r'\b(on[a-z]+)\s*=\s*"([^"]*)"')

# Events the shim listens for.
DELEGATED = {
    'onclick', 'onchange', 'oninput', 'ondblclick', 'onblur', 'onfocus',
    'onmouseover', 'onmouseout', 'onmousemove', 'onkeydown', 'onkeyup',
    'onsubmit', 'ondragstart', 'ondragend', 'ondragover', 'ondragleave',
    'ondrop', 'onerror',
}

# name(...) or ns.name(...) — one call, nothing after it.
PLAIN_CALL = re.compile(
    r'^\s*([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\((.*)\)\s*;?\s*$', re.S
)

SAFE_ARG = re.compile(
    r'''^\s*(?:
          '[^'\\]*'
        | \\'[^'\\]*\\'          # \'escaped\' — handler inside a JS string
        | "[^"\\]*"
        | -?\d+(?:\.\d+)?
        | true|false|null
        | \$\{jsArg\([^{}]*\)\}
        | \$\{JSON\.stringify\([^{}]*\)\}
        )\s*$''',
    re.X,
)

# Interpolations that can only ever yield a number, so they cannot carry a
# quote and cannot break out of the literal. Mirrors the allowlist in
# scripts/lint_inline_handlers.py — the two must agree, and the test suite
# asserts that they do.
NUMERIC_INTERP = re.compile(
    r'^\s*\$\{\s*(?:'
    r'[A-Za-z_$][\w$]*\.(?:id|frame_no|count|index)'
    r'|Date\.now\(\)'
    r'|[^\'"{}]*\?\s*\d+\s*:\s*\d+'
    r')\s*\}\s*$'
)

# Element/event reads that the shim resolves as placeholders.
PLACEHOLDER_MAP = [
    (re.compile(r'^\+\s*this\.value$'), '$nvalue'),
    (re.compile(r'^this\.value$'), '$value'),
    (re.compile(r'^this\.checked$'), '$checked'),
    (re.compile(r'^this\.textContent$'), '$text'),
    (re.compile(r'^this\.id$'), '$id'),
    (re.compile(r'^this$'), '$this'),
    (re.compile(r'^event$'), '$event'),
    (re.compile(r'^this\.dataset\.([A-Za-z_$][\w$]*)$'), r'$data.\1'),
    (re.compile(r'^JSON\.parse\(this\.dataset\.([A-Za-z_$][\w$]*)\)$'), r'$json.\1'),
]

# Prefixes/wrappers stripped before analysing the real call.
STOP_PREFIX = re.compile(r'^\s*event\.stopPropagation\(\)\s*;\s*')
PREVENT_PREFIX = re.compile(r'^\s*event\.preventDefault\(\)\s*;\s*')
TYPEOF_GUARD = re.compile(
    r"^\s*if\s*\(\s*typeof\s+(?:window\.)?([\w$.]+)\s*===?\s*'function'\s*\)\s*", re.S
)
KEY_GUARD = re.compile(
    r"^\s*if\s*\(\s*(?:e|ev|event)\.key\s*===?\s*\\?'([^']+)\\?'"
    r"(?:\s*\|\|\s*(?:e|ev|event)\.key\s*===?\s*\\?'([^']+)\\?')?\s*\)\s*",
    re.S,
)
SELF_GUARD = re.compile(r'^\s*if\s*\(\s*event\.target\s*===\s*this\s*\)\s*', re.S)

# `this.click()` — re-dispatch a click on the element itself. Used by the
# 46 keyboard-accessibility handlers in index.html that make a div behave like
# a button. Expressed declaratively so it needs no global function.
SELF_CLICK = re.compile(r'^this\.click\(\)$')

# Removal / hide idioms.
CLOSEST_REMOVE = re.compile(r"^this\.closest\((['\"])(.+?)\1\)(?:\?)?\.remove\(\)$")
BYID_REMOVE = re.compile(
    r"^document\.getElementById\((['\"])([\w-]+)\1\)\??\.remove\(\)$"
)
BYID_HIDE = re.compile(
    r"^document\.getElementById\((['\"])([\w-]+)\1\)\??\.style\.display\s*=\s*'none'$"
)
PARENT_REMOVE = re.compile(r'^this\.((?:parentElement\.)+)remove\(\)$')


# Hover styling: only these properties, only literal values.
_HOVER_PROP = {'background': 'bg', 'borderColor': 'bc', 'color': 'fg'}
_HOVER_DECL = re.compile(
    r"this\.style\.(background|borderColor|color)\s*=\s*'([^']*)'"
)


def HOVER_DECLS(body: str) -> str | None:
    """Encode `this.style.X='v'` declarations as a compact data-hover value.

    Returns None when the body contains anything other than those assignments
    — e.g. index.html:2809 guards on `window._isSplitResizing`, which is real
    logic and must not be silently dropped.
    """
    remainder = _HOVER_DECL.sub('', body)
    if remainder.strip(' ;'):
        return None
    out = []
    for prop, value in _HOVER_DECL.findall(body):
        if '"' in value:
            return None
        out.append(f'{_HOVER_PROP[prop]}:{value}')
    return '|'.join(out) if out else None


def split_args(s: str) -> list[str] | None:
    """Split a top-level argument list. None if nesting is unbalanced."""
    out: list[str] = []
    depth, cur, quote = 0, '', None
    i = 0
    while i < len(s):
        c = s[i]
        # A backslash-escaped quote is part of the token, never a delimiter.
        # These appear because the handler was emitted from inside a JS string
        # literal (`'... onclick="f(\\'x\\')" ...'`). Treating the `\'` as an
        # opening quote left the scanner permanently "inside a string" and made
        # split_args return None, so every such handler was silently skipped.
        if c == '\\' and i + 1 < len(s) and s[i + 1] in '\'"':
            cur += s[i:i + 2]
            i += 2
            continue
        if quote:
            cur += c
            if c == quote:
                quote = None
        elif c in '\'"':
            quote = c
            cur += c
        elif c == '$' and s[i:i + 2] == '${':
            # Consume the whole ${...} as one opaque unit. Counting its braces
            # against the same depth as the surrounding parens does not work:
            # the inner call's '(' increments and the '}' never decrements.
            j, d2 = i + 2, 1
            while j < len(s) and d2:
                if s[j] == '{':
                    d2 += 1
                elif s[j] == '}':
                    d2 -= 1
                j += 1
            if d2:
                return None
            cur += s[i:j]
            i = j
            continue
        elif c in '([{':
            depth += 1
            cur += c
        elif c in ')]}':
            depth -= 1
            cur += c
            if depth < 0:
                return None
        elif c == ',' and depth == 0:
            out.append(cur)
            cur = ''
        else:
            cur += c
        i += 1
    if depth != 0 or quote:
        return None
    if cur.strip():
        out.append(cur)
    return out


def split_statements(body: str) -> list[str] | None:
    """Split on top-level `;`."""
    out: list[str] = []
    depth, cur, quote = 0, '', None
    i = 0
    while i < len(body):
        c = body[i]
        # Same escaped-quote handling as split_args — see the note there.
        if c == '\\' and i + 1 < len(body) and body[i + 1] in '\'"':
            cur += body[i:i + 2]
            i += 2
            continue
        if quote:
            cur += c
            if c == quote:
                quote = None
        elif c in '\'"':
            quote = c
            cur += c
        elif c == '$' and body[i:i + 2] == '${':
            j, d2 = i + 2, 1
            while j < len(body) and d2:
                if body[j] == '{':
                    d2 += 1
                elif body[j] == '}':
                    d2 -= 1
                j += 1
            if d2:
                return None
            cur += body[i:j]
            i = j
            continue
        elif c in '([{':
            depth += 1
            cur += c
        elif c in ')]}':
            depth -= 1
            cur += c
            if depth < 0:
                return None
        elif c == ";" and depth == 0:
            if cur.strip():
                out.append(cur.strip())
            cur = ''
        else:
            cur += c
        i += 1
    if depth != 0 or quote:
        return None
    if cur.strip():
        out.append(cur.strip())
    return out


def convert_arg(arg: str) -> str | None:
    """Return the shim-safe form of one argument, or None if unprovable."""
    a = arg.strip()
    if SAFE_ARG.match(a):
        # \'x\' is KEPT escaped. These handlers are emitted from inside a
        # single-quoted JS string literal, so unescaping the quotes here would
        # terminate that literal and produce a syntax error at load time. The
        # shim strips the backslashes when it parses the argument instead.
        return a
    if NUMERIC_INTERP.match(a):
        return a
    for pat, repl in PLACEHOLDER_MAP:
        m = pat.match(a)
        if m:
            return pat.sub(repl, a) if '\\1' in repl else repl
    return None


def convert_call(stmt: str) -> str | None:
    """Convert a single statement to a shim call, or None."""
    s = stmt.strip().rstrip(';').strip()
    if not s:
        return None
    # `f?.()` -> `f()`; the shim no-ops on unknown names anyway.
    s = s.replace('?.(', '(')
    m = PLAIN_CALL.match(s)
    if not m:
        return None
    name, raw_args = m.group(1), m.group(2)
    # A bare `event.stopPropagation()` as a whole statement is handled by the
    # data-stop attribute, never as a call.
    if name in ('event.stopPropagation', 'event.preventDefault'):
        return None
    # The shim resolves a dotted name by walking `window`. A name rooted at
    # `this`, `event`, `document` or a DOM expression is NOT resolvable that
    # way, so converting it would produce an attribute the shim silently
    # refuses — a control that looks present and does nothing.
    #
    # Caught in review: index.html's persona <select> carried
    #   `this.parentElement.parentElement.removeAttribute('open')`
    # which PLAIN_CALL happily matched as a dotted "function name". The
    # dropdown would have stopped closing, with nothing in the console.
    root = name.split('.')[0]
    if root in ('this', 'event', 'document', 'e', 'ev'):
        return None
    args = split_args(raw_args)
    if args is None:
        return None
    converted = []
    for a in args:
        c = convert_arg(a)
        if c is None:
            return None
        converted.append(c)
    return f'{name}({",".join(converted)})'


class Result:
    def __init__(self) -> None:
        self.attrs: dict[str, str] = {}
        self.act: str | None = None

    def render(self, event: str) -> str:
        parts = []
        if self.act:
            parts.append(f'data-act-{event}="{self.act}"')
        for k, v in self.attrs.items():
            parts.append(f'{k}="{v}"')
        return ' '.join(parts)


def analyse(event: str, body: str) -> Result | None:
    """Return the replacement attributes for a handler, or None to leave it."""
    res = Result()
    b = body.strip()
    if not b:
        return None

    # ── Presentational hover styling ──
    # `onmouseover="this.style.background='var(--bg-3)'"` is not application
    # logic; it is a :hover rule written in the wrong place. Rather than
    # inventing a JS handler for it, emit a data attribute that CSS targets.
    # Only the three properties actually used in this codebase are supported,
    # and only literal values — so this can never carry caller data.
    if event in ('onmouseover', 'onmouseout', 'onmouseenter', 'onmouseleave'):
        if 'this.style' not in b:
            return None
        decls = HOVER_DECLS(b)
        if decls is None:
            return None
        res = Result()
        # Separate in/out attributes. They are NOT symmetrical in this
        # codebase — several mouseout handlers restore a value that differs
        # from the element's initial one (e.g. 03-features-a.js:2789 returns
        # to 'rgba(56,189,248,0.4)'), so "just undo the hover" would change
        # appearance. Each direction keeps its own literal.
        key = (
            'data-hover'
            if event in ('onmouseover', 'onmouseenter')
            else 'data-hover-out'
        )
        res.attrs[key] = decls
        return res

    if 'this.style' in b and event == 'onerror':
        # `onerror="this.style.display='none'"` on <img>. Declarative equivalent.
        if re.fullmatch(r"this\.style\.display\s*=\s*'none'", b):
            r = Result()
            r.attrs['data-hide-on-error'] = '1'
            return r
        return None

    # `${expr}` as the ENTIRE body: the value is a code string chosen by app
    # code (QUICK_ACTIONS, emptyState actions). Not markup, not convertible.
    if re.fullmatch(r'\$\{[^}]*\}', b):
        return None

    # ── strip guards/prefixes, recording them as attributes ──
    changed = True
    while changed:
        changed = False
        m = SELF_GUARD.match(b)
        if m:
            res.attrs['data-click-self'] = '1'
            b = b[m.end():].strip()
            changed = True
            continue
        m = KEY_GUARD.match(b)
        if m:
            keys = [k for k in (m.group(1), m.group(2)) if k]
            keys = ['Space' if k == ' ' else k for k in keys]
            res.attrs['data-keys'] = ','.join(keys)
            b = b[m.end():].strip()
            changed = True
            continue
        m = TYPEOF_GUARD.match(b)
        if m:
            b = b[m.end():].strip()
            changed = True
            continue
        m = STOP_PREFIX.match(b)
        if m:
            res.attrs['data-stop'] = '1'
            b = b[m.end():].strip()
            changed = True
            continue
        m = PREVENT_PREFIX.match(b)
        if m:
            res.attrs['data-prevent'] = '1'
            b = b[m.end():].strip()
            changed = True
            continue

    # A guard may wrap a braced block: `if(...){ a(); b() }`
    if b.startswith('{') and b.endswith('}'):
        b = b[1:-1].strip()

    if not b:
        # Guard-only handler, e.g. `event.stopPropagation()` alone.
        return res if res.attrs else None

    stmts = split_statements(b)
    if stmts is None:
        return None

    calls: list[str] = []
    for stmt in stmts:
        s = stmt.strip().rstrip(';').strip()
        if not s:
            continue
        # Bare guards appearing mid-body.
        if re.fullmatch(r'event\.stopPropagation\(\)', s):
            res.attrs['data-stop'] = '1'
            continue
        if re.fullmatch(r'event\.preventDefault\(\)', s):
            res.attrs['data-prevent'] = '1'
            continue
        # Removal / hide idioms become declarative attributes.
        m = CLOSEST_REMOVE.match(s)
        if m:
            res.attrs['data-close'] = f'closest:{m.group(2)}'
            continue
        m = BYID_REMOVE.match(s)
        if m:
            res.attrs['data-close'] = f'id:{m.group(2)}'
            continue
        m = BYID_HIDE.match(s)
        if m:
            res.attrs['data-hide'] = f'id:{m.group(2)}'
            continue
        if SELF_CLICK.match(s):
            res.attrs['data-self-click'] = '1'
            continue
        m = PARENT_REMOVE.match(s)
        if m:
            levels = m.group(1).count('parentElement')
            res.attrs['data-close'] = 'parent' if levels == 1 else f'parent:{levels}'
            continue
        c = convert_call(s)
        if c is None:
            return None
        calls.append(c)

    # data-close/data-hide only fire on click in the shim.
    if ('data-close' in res.attrs or 'data-hide' in res.attrs) and event != 'onclick':
        return None

    if calls:
        res.act = ';'.join(calls)
    if not res.act and not res.attrs:
        return None
    return res


def main() -> int:
    apply = '--apply' in sys.argv
    targets = [pathlib.Path('frontend/index.html')]
    targets += sorted(pathlib.Path('frontend/js').glob('*.js'))

    stats: Counter[str] = Counter()
    per_file: Counter[str] = Counter()
    skipped: list[tuple[str, int, str, str]] = []

    for path in targets:
        if path.name == '00-delegate.js' or not path.exists():
            continue
        text = path.read_text(encoding='utf-8')
        lines = text.split('\n')
        changed = False

        for idx, line in enumerate(lines):
            if path.suffix == '.js' and line.lstrip().startswith(('//', '*', '/*')):
                continue
            new_line = line
            for ev, body in ATTR.findall(line):
                if ev not in DELEGATED:
                    stats['not-delegated-event'] += 1
                    skipped.append((path.name, idx + 1, ev, body[:70]))
                    continue
                res = analyse(ev, body)
                if res is None:
                    stats['left-inline'] += 1
                    skipped.append((path.name, idx + 1, ev, body[:70]))
                    continue
                old = f'{ev}="{body}"'
                new = res.render(ev[2:])
                if old in new_line:
                    new_line = new_line.replace(old, new)
                    stats['converted'] += 1
                    per_file[path.name] += 1
            if new_line != line:
                lines[idx] = new_line
                changed = True

        if changed and apply:
            path.write_text('\n'.join(lines), encoding='utf-8')

    total = stats['converted'] + stats['left-inline'] + stats['not-delegated-event']
    print(f'total handlers : {total}')
    print(f'converted      : {stats["converted"]}')
    print(f'left inline    : {stats["left-inline"]}')
    print(f'non-delegated  : {stats["not-delegated-event"]}')
    if apply:
        print('\nper file:')
        for fn, c in per_file.most_common(15):
            print(f'  {c:4}  {fn}')
    else:
        print('\n(dry run — pass --apply to write)')
        print('\nwhat stays inline:')
        for fn, ln, ev, b in skipped[:40]:
            print(f'  {fn}:{ln} {ev}="{b}"')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
