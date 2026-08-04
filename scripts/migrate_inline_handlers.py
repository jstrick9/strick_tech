#!/usr/bin/env python3
"""Convert inline on*= handlers to data-act= for the delegation shim.

SAFETY RULE: only convert a handler whose body is a PLAIN CALL with literal or
jsArg/JSON.stringify arguments. Anything else — DOM expressions like
`this.style.background=...`, multi-statement bodies, event-object use — is left
inline and reported. Those get real listeners in a later pass; guessing at them
would produce buttons that silently do nothing, which is the failure mode this
whole review has been removing.
"""
from __future__ import annotations

import pathlib
import re
import sys
from collections import Counter

# on<event>="<body>"
ATTR = re.compile(r'\b(on[a-z]+)\s*=\s*"([^"]*)"')

# Events the shim listens for.
DELEGATED = {
    'onclick', 'onchange', 'oninput', 'ondblclick', 'onblur',
    'onmouseover', 'onmouseout', 'onkeydown', 'onsubmit',
}

# name(...) or ns.name(...) — one call, nothing after it.
PLAIN_CALL = re.compile(r'^\s*([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\((.*)\)\s*;?\s*$', re.S)

# An argument list is convertible when every piece is a JSON-ish literal or a
# jsArg()/JSON.stringify() interpolation (which produce JSON literals).
SAFE_ARG = re.compile(
    r'''^\s*(?:
          '[^'\\]*'            # 'single quoted'
        | "[^"\\]*"            # "double quoted"
        | -?\d+(?:\.\d+)?      # number
        | true|false|null
        | \$\{jsArg\([^{}]*\)\}
        | \$\{JSON\.stringify\([^{}]*\)\}
        )\s*$''',
    re.X,
)


def split_args(s: str) -> list[str] | None:
    """Split a top-level argument list. None if nesting is unbalanced."""
    out, depth, cur, quote = [], 0, '', None
    i = 0
    while i < len(s):
        c = s[i]
        if quote:
            cur += c
            if c == quote and s[i - 1] != '\\':
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


def convertible(body: str) -> bool:
    b = body.strip()
    if not b or ';' in b.rstrip(';'):
        return False
    if 'this' in b or 'event' in b:
        return False
    m = PLAIN_CALL.match(b)
    if not m:
        return False
    args = split_args(m.group(2))
    if args is None:
        return False
    return all(SAFE_ARG.match(a) for a in args)


def main() -> int:
    apply = '--apply' in sys.argv
    root = pathlib.Path('frontend/js')
    stats = Counter()
    skipped: list[tuple[str, int, str, str]] = []
    per_file = Counter()

    for path in sorted(root.glob('*.js')):
        if path.name in ('00-delegate.js',):
            continue
        lines = path.read_text(encoding='utf-8').split('\n')
        changed = False

        for idx, line in enumerate(lines):
            if line.lstrip().startswith(('//', '*', '/*')):
                continue
            new_line = line
            for ev, body in ATTR.findall(line):
                if ev not in DELEGATED:
                    stats['not-delegated-event'] += 1
                    skipped.append((path.name, idx + 1, ev, body[:60]))
                    continue
                if convertible(body):
                    old = f'{ev}="{body}"'
                    new = f'data-act="{body}"'
                    if old in new_line:
                        new_line = new_line.replace(old, new)
                        stats['converted'] += 1
                        per_file[path.name] += 1
                else:
                    stats['left-inline'] += 1
                    skipped.append((path.name, idx + 1, ev, body[:60]))
            if new_line != line:
                lines[idx] = new_line
                changed = True

        if changed and apply:
            path.write_text('\n'.join(lines), encoding='utf-8')

    print(f'converted      : {stats["converted"]}')
    print(f'left inline    : {stats["left-inline"]}')
    print(f'non-delegated  : {stats["not-delegated-event"]}')
    if apply:
        print('\nper file:')
        for fn, c in per_file.most_common(12):
            print(f'  {c:4}  {fn}')
    else:
        print('\n(dry run — pass --apply to write)')
        print('\nsample of what stays inline:')
        for fn, ln, ev, b in skipped[:15]:
            print(f'  {fn}:{ln} {ev}="{b}"')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
