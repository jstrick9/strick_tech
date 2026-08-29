#!/usr/bin/env python3
"""Sweep 1 of 4 — DEAD HANDLER CONTRACT.

The class, from docs/BUG-SWEEP-PLAN.md: *markup calling a handler whose
expectations the dispatcher does not meet.*

The instance that defined it (Bug 3, Kanban drag-and-drop, fixed in 5c2a93f):
three handlers read `event.currentTarget`. `frontend/js/00-delegate.js` binds
ONE listener per event type on `document`, in the CAPTURE phase. So
`currentTarget` is `document` during dispatch and `undefined` afterwards. The
markup was correct, the function existed, the event was bound -- and the
feature was completely dead.

This sweep looks for every other way that contract can be broken:

  1. HANDLER MISSING     -- data-act-X="foo()" where `foo` is never defined.
                            The click does nothing at all.
  2. CURRENTTARGET       -- a delegated handler reading event.currentTarget.
                            Always wrong under capture-phase delegation.
  3. EVENT NOT BOUND     -- data-act-X where X is not in the dispatcher's
                            EVENTS list. The attribute is decoration.
  4. TOO MANY ARGS       -- markup passes more arguments than the function can
                            receive. Those arguments are silently discarded.

DELIBERATELY NOT CHECKED: passing FEWER arguments than the signature declares.
My first version flagged 42 of these and every one I checked was correct code.
JavaScript fills omitted parameters with `undefined`, and this codebase relies
on that everywhere -- `toggleSidebarGroup(groupId, forceOpen)` is called with
one argument on purpose and branches on `typeof forceOpen === 'boolean'` to
mean "toggle". A sweep whose findings are mostly false is worse than no sweep:
it trains you to skim the output, which is how a real finding gets missed.

WHY IT PARSES RATHER THAN GREPS
-------------------------------
A previous version of this analysis used `grep -oE "data-act-[a-z]+"` and I
concluded the dispatcher did not bind drag events. That was wrong -- they are
bound from a runtime array the grep could not see, and the wrong conclusion
nearly sent a bad fix out. Handler names and the EVENTS list are both read
from the parsed JS here, never from a regex over source text.

Exit code is the point: 0 = zero findings, 1 = findings. Re-runnable, so a
regression is caught rather than rediscovered.

Usage:
    python3 scripts/sweep_dead_handlers.py            # human-readable
    python3 scripts/sweep_dead_handlers.py --json     # machine-readable
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
JS_DIR = REPO / "frontend" / "js"
HTML_FILES = [REPO / "frontend" / "index.html"]

# Placeholders 00-delegate.js can resolve. Anything else in an argument list
# is a literal, and that is fine.
PLACEHOLDERS = {
    "$value", "$nvalue", "$checked", "$this", "$event",
    "$text", "$id", "$json", "$data",
}

# Handlers the dispatcher itself implements as intents rather than functions.
INTENT_ATTRS = {"data-close", "data-hide", "data-self-click", "data-click-self"}

# Callable from markup via resolve()'s property walk on `window`, and correctly
# not defined in this codebase.
BROWSER_GLOBALS = {
    "open", "print", "alert", "confirm", "prompt", "close",
    "scrollTo", "reload", "focus", "blur",
}


def _node_available() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return (REPO / "node_modules" / "acorn").exists()
    except Exception:
        return False


def bound_events() -> set[str]:
    """Read the EVENTS array out of the dispatcher rather than assuming it."""
    src = (JS_DIR / "00-delegate.js").read_text(encoding="utf-8")
    i = src.index("var EVENTS = [")
    block = src[i : src.index("];", i)]
    # Strip comments FIRST. The block now carries a comment explaining why
    # 'select' is bound, and that comment quotes the event name -- so a bare
    # regex reported 'select' as bound even after it was removed from the
    # array. My revert-proof MISSED break #1 for exactly this reason: the
    # deleted line was still "found" inside prose.
    block = re.sub(r"(?m)^\s*//.*$", "", block)
    return set(re.findall(r"'([a-z]+)'", block))


def declared_functions() -> dict[str, list[str]]:
    """{name: [param, ...]} for everything reachable as a handler.

    Uses acorn so that IIFE-wrapped `window.foo = function (a, b)` and plain
    `function foo(a, b)` are both seen, with real parameter lists.
    """
    script = r"""
const fs = require('fs');
const acorn = require('acorn');
const walk = require('acorn-walk');
const out = {};
function params(node) {
  return (node.params || []).map(p =>
    p.type === 'Identifier' ? p.name
    : p.type === 'AssignmentPattern' && p.left.type === 'Identifier' ? '?' + p.left.name
    : p.type === 'RestElement' ? '...'
    : '_');
}
for (const file of process.argv.slice(1)) {
  let ast;
  try {
    ast = acorn.parse(fs.readFileSync(file, 'utf8'),
                      {ecmaVersion: 2022, allowReturnOutsideFunction: true});
  } catch (e) { continue; }
  walk.simple(ast, {
    FunctionDeclaration(n) { if (n.id) out[n.id.name] = params(n); },
    AssignmentExpression(n) {
      // window.foo = function (...) {}   |   window.foo = (...) => {}
      if (n.left.type === 'MemberExpression'
          && n.left.object.type === 'Identifier'
          && n.left.object.name === 'window'
          && n.left.property.type === 'Identifier'
          && (n.right.type === 'FunctionExpression'
              || n.right.type === 'ArrowFunctionExpression')) {
        out[n.left.property.name] = params(n.right);
      }
    },
    VariableDeclarator(n) {
      if (n.id.type === 'Identifier' && n.init
          && (n.init.type === 'FunctionExpression'
              || n.init.type === 'ArrowFunctionExpression')) {
        out[n.id.name] = params(n.init);
      }
    },
    CallExpression(n) {
      // 00-handlers.js registers ~70 handlers as on('hFoo', function (el) {...})
      // where `on` does window[name] = fn. Nothing is statically named, so an
      // AST walk looking only for declarations reports every one of them as
      // "called but never defined" -- 70 false positives on my first run.
      if (n.callee.type === 'Identifier' && n.callee.name === 'on'
          && n.arguments.length === 2
          && n.arguments[0].type === 'Literal'
          && typeof n.arguments[0].value === 'string'
          && (n.arguments[1].type === 'FunctionExpression'
              || n.arguments[1].type === 'ArrowFunctionExpression')) {
        out[n.arguments[0].value] = params(n.arguments[1]);
      }
    },
  });
}
process.stdout.write(JSON.stringify(out));
"""
    files = sorted(str(p) for p in JS_DIR.glob("*.js"))
    proc = subprocess.run(
        ["node", "-e", script, *files],
        cwd=REPO, capture_output=True, text=True, timeout=300,
    )
    if proc.returncode != 0:
        raise SystemExit(f"acorn parse failed:\n{proc.stderr[:2000]}")
    # Console noise can precede the JSON; take the last object.
    text = proc.stdout[proc.stdout.rindex('{"') :] if '{"' in proc.stdout else proc.stdout
    return json.loads(text)


def call_sites() -> list[dict]:
    """Every data-act-* occurrence, from markup AND from JS template strings."""
    sites = []
    pattern = re.compile(r'data-act-([a-z]+)\s*=\s*"([^"]*)"')
    sources = list(HTML_FILES) + sorted(JS_DIR.glob("*.js"))
    for path in sources:
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            # Skip JS line comments. 00-delegate.js DOCUMENTS the attribute
            # syntax in its header comment using doThing() and f() as examples;
            # scanning them produced two HANDLER_MISSING findings for functions
            # that were never meant to exist.
            if path.suffix == ".js" and line.lstrip().startswith("//"):
                continue
            for m in pattern.finditer(line):
                sites.append({
                    "file": str(path.relative_to(REPO)),
                    "line": lineno,
                    "event": m.group(1),
                    "spec": m.group(2).strip(),
                })
    return sites


def split_calls(spec: str) -> list[str]:
    """`a(1); b(2)` -> ['a(1)', 'b(2)'], respecting quotes and nesting."""
    out, depth, cur, quote = [], 0, "", None
    for ch in spec:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
            cur += ch
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == ";" and depth == 0:
            out.append(cur.strip())
            cur = ""
            continue
        cur += ch
    if cur.strip():
        out.append(cur.strip())
    return [c for c in out if c]


def split_args(arglist: str) -> list[str]:
    if not arglist.strip():
        return []
    out, depth, cur, quote = [], 0, "", None
    for ch in arglist:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
            cur += ch
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
            continue
        cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def uses_current_target(name: str) -> bool:
    """Does this handler's body read event.currentTarget?"""
    for path in JS_DIR.glob("*.js"):
        src = path.read_text(encoding="utf-8")
        esc = re.escape(name)
        pat = (
            rf"(?:function\s+{esc}\s*\("
            rf"|window\.{esc}\s*=\s*(?:async\s+)?function[^(]*\()"
        )
        for m in re.finditer(pat, src):
            # Crude but adequate body scan: to the next top-level `\n}` .
            # Brace-match the real body. A fixed-size window overran the end
            # of steerSaveNew() into a NEIGHBOURING function that legitimately
            # uses currentTarget in a directly-attached addEventListener --
            # where currentTarget is correct -- and reported the innocent
            # function as broken.
            depth, i, n = 0, m.end() - 1, len(src)
            while i < n and src[i] != "{":
                i += 1
            start = i
            while i < n:
                if src[i] == "{":
                    depth += 1
                elif src[i] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            body = src[start : i + 1]
            # Strip comments before looking. The Kanban handlers were FIXED in
            # 5c2a93f and now carry comments explaining why currentTarget is
            # wrong under delegation -- scanning raw text reported the fixed
            # code as broken. When a probe disagrees with the app, suspect the
            # probe: this one was reading its own changelog.
            body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
            body = re.sub(r"(?m)^\s*//.*$", "", body)
            body = re.sub(r"\s//.*$", "", body, flags=re.M)
            if re.search(r"\bcurrentTarget\b", body):
                return True
    return False


def main() -> int:
    as_json = "--json" in sys.argv
    if not _node_available():
        print("SKIP: node/acorn unavailable — cannot parse handlers honestly.")
        print("      A skip is not a pass. Install with:")
        print("        npm install --no-save acorn acorn-walk")
        return 2

    events = bound_events()
    funcs = declared_functions()
    findings: list[dict] = []

    for site in call_sites():
        if site["event"] not in events:
            findings.append({**site, "kind": "EVENT_NOT_BOUND",
                             "detail": f"'{site['event']}' is not in the dispatcher's EVENTS list"})
            continue

        for call in split_calls(site["spec"]):
            m = re.match(r"^([A-Za-z_$][\w$.]*)\s*\((.*)\)\s*$", call, re.S)
            if not m:
                continue  # bare identifier / expression form; not a call contract
            name, arglist = m.group(1), m.group(2)
            base = name.split(".")[-1] if name.startswith("window.") else name
            if "." in base:
                continue  # obj.method() — out of scope for this sweep

            # 00-delegate.js resolve() walks plain properties on `window`, so
            # browser builtins are legitimately callable from markup.
            # `window.open(...)` was reported as "never defined" because it is
            # not declared anywhere in this codebase -- it does not need to be.
            if base in BROWSER_GLOBALS:
                continue

            if base not in funcs:
                findings.append({**site, "kind": "HANDLER_MISSING",
                                 "detail": f"{base}() is called but never defined"})
                continue

            if uses_current_target(base):
                findings.append({**site, "kind": "CURRENTTARGET",
                                 "detail": f"{base}() reads event.currentTarget, which is "
                                           "`document` under capture-phase delegation"})

            args = split_args(arglist)
            params = funcs[base]
            # Only too-many is a real defect: those arguments go nowhere.
            # Too-few is idiomatic JS and correct throughout this codebase.
            if len(args) > len(params) and "..." not in params:
                findings.append({**site, "kind": "TOO_MANY_ARGS",
                                 "detail": f"{base}() accepts {len(params)} param(s) "
                                           f"but markup passes {len(args)} — "
                                           "the extras are silently discarded"})

    if as_json:
        print(json.dumps(findings, indent=2))
    else:
        print("SWEEP 1/4 — DEAD HANDLER CONTRACT")
        print(f"  dispatcher binds : {len(events)} event types")
        print(f"  handlers parsed  : {len(funcs)}")
        print(f"  call sites       : {len(call_sites())}")
        print("-" * 60)
        if not findings:
            print("  0 findings.")
        else:
            by_kind: dict[str, list[dict]] = {}
            for f in findings:
                by_kind.setdefault(f["kind"], []).append(f)
            for kind, items in sorted(by_kind.items()):
                print(f"\n  {kind}  ({len(items)})")
                for f in items[:40]:
                    print(f"    {f['file']}:{f['line']}  {f['detail']}")
                if len(items) > 40:
                    print(f"    ... and {len(items) - 40} more")
            print(f"\n  TOTAL: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
