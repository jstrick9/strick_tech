#!/usr/bin/env python3
"""Module-by-module completeness: is each pane actually WIRED to a backend?

WHY THIS IS A NEW DIMENSION
───────────────────────────
Twenty-two audits check how a pane behaves -- layout, keyboard, failure
honesty, empty accounts, misbehaving models. Every one of them assumes the
pane is a real feature.

None asks the prior question: **is this module finished?** A pane can render
beautifully, pass every accessibility check, handle an outage gracefully, and
still be a facade over an endpoint that does not exist.

That is the question this audit answers, per module:

  MISSING-ROUTE   the pane calls a path that matches NO route pattern in the
                  application. The call can never succeed -- the feature is
                  wired to nothing.

  METHOD-MISMATCH the path exists, but not for the verb the frontend uses:
                  the UI POSTs to a GET-only route, say. Equally fatal, and
                  invisible to any check that looks at paths alone.

  NO-BACKEND      the pane makes no API calls at all. Sometimes correct (a
                  pure-client tool), so this is reported as INFORMATIONAL and
                  triaged by hand rather than counted.

MEASUREMENT NOTES
─────────────────
  * Compared against FastAPI's OWN route table, not against live HTTP.
    The first version fired a GET at each path and called a 404 a dead
    endpoint; 11 of its 13 findings were false, because a GET 404 says
    nothing about a POST-only route or a literal segment shadowed by a path
    parameter (`/api/hooks/fire` matches `/api/hooks/{hook_id}`).
  * Nothing is fired at the server, so the audit cannot mutate state and
    needs no CSRF token -- it is a pure static comparison against the real
    routing table.
  * Template interpolations (`/api/x/${id}`) become a wildcard segment rather
    than being skipped: skipping them hides exactly the routes most likely to
    be wrong.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import AuditResult, emit  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
JS_DIR = REPO / 'frontend' / 'js'

# `/api/...` inside a quote or template literal.
API_PATH = re.compile(r"""['"`](/api/[A-Za-z0-9_\-/${}.]*)['"`]""")

# The verb, when the call site states one: `method: 'POST'` within a short
# window after the path. Absent one, fetch defaults to GET.
METHOD_NEAR = re.compile(r"""method\s*:\s*['"]([A-Za-z]+)['"]""")

# A template hole: replace with something a route will accept as an id.
HOLE = re.compile(r'\$\{[^}]*\}')

# Paths that are POST-only by design, or destructive, or known-noisy.
SKIP = (
    '/api/security/csp-report',
    '/api/chat',
    '/api/secrets/get',
)


def _pane_modules() -> dict[str, Path]:
    """Map each pane id to the JS file most likely to implement it.

    The registry resolves renderers lazily by name, so the mapping is derived
    from which file defines the renderer function.
    """
    registry = (JS_DIR / '00-pane-registry.js').read_text(encoding='utf-8')
    panes = re.findall(r"^\s*'([a-z0-9-]+)':\s*(.*)$", registry, re.M)

    renderers = {}
    for pane, body in panes:
        match = re.search(r'window\.(render[A-Za-z0-9_]+)', body)
        renderers[pane] = match.group(1) if match else None

    out: dict[str, Path] = {}
    # The registry itself mentions every `window.renderX`, so searching it
    # matches every pane and maps all 63 to one file that contains no API
    # calls -- which is why the first run probed 0 paths and reported a clean
    # 0. Exclude it, and the dedupe wrapper that also names the renderers.
    sources = {f: f.read_text(encoding='utf-8', errors='replace')
               for f in sorted(JS_DIR.glob('*.js'))
               if f.name not in ('00-pane-registry.js', '00-render-dedupe.js')}
    # A DEFINITION beats a mention. `renderPrompts` is defined in
    # 14-prompt-library.js, but 01-app-core.js contains
    #   if (typeof window.renderPrompts === 'function' && pane === 'prompts')
    # which the patterns below also match. Iterating files in name order, the
    # 5,800-line app-core won, so prompts/dashboard/codesearch were all mapped
    # to it -- and every /api/ call in that file was then attributed to each of
    # them. That is where "METHOD-MISMATCH /api/preview/restore (used by
    # codesearch, dashboard, prompts)" came from: one Studio call site, blamed
    # on three unrelated panes.
    #
    # Two passes: real definitions first, mentions only as a fallback.
    definition = re.compile
    for pane, fn in renderers.items():
        if not fn:
            continue
        strict = definition(
            rf'(?:async\s+)?function\s+{fn}\s*\(|'
            rf'window\.{fn}\s*=\s*(?:async\s*)?(?:function|\()|'
            rf'(?:const|let|var)\s+{fn}\s*=\s*(?:async\s*)?(?:function|\()'
        )
        for path, src in sources.items():
            if strict.search(src):
                out[pane] = path
                break
    for pane, fn in renderers.items():
        if not fn or pane in out:
            continue
        for path, src in sources.items():
            # `async function renderX()`, `function renderX()`,
            # `const renderX = async () =>`, `window.renderX = ...`.
            # The first version required `function\s+NAME` and missed every
            # `async function`, which is most of them -- so it mapped zero
            # panes to files and the audit probed nothing while reporting a
            # clean 0. An audit that measures nothing looks exactly like one
            # that finds nothing.
            if re.search(
                    rf'(async\s+)?function\s+{fn}\s*\(|'
                    rf'\b{fn}\s*=\s*(async\s*)?(function|\()|'
                    rf'window\.{fn}\s*=', src):
                out[pane] = path
                break
    return out


def _call_options(source: str, start: int, limit: int = 400) -> str:
    """The remainder of the fetch() call that begins at `start`.

    Scans forward tracking paren depth and stops at the close of the call, so
    the verb of a LATER call site cannot be attributed to this one.
    """
    depth = 0
    for i in range(start, min(len(source), start + limit)):
        ch = source[i]
        if ch == '(':
            depth += 1
        elif ch == ')':
            if depth == 0:
                return source[start:i]
            depth -= 1
    return source[start:start + limit]


def _is_fetch_call(source: str, start: int) -> bool:
    r"""Is this /api/ literal the argument of a fetch()?

    A path can appear as `a.href = '/api/.../export'` for a download link, or
    inside a comment, or as an EventSource/WebSocket URL. Only a fetch() has a
    verb to get wrong, so only a fetch() can produce a METHOD-MISMATCH.

    Without this, `a.href=\`/api/workspaces/${wsId}/export\`` on one line and
    `fetch(..., {method:'DELETE'})` three lines below were read as one call,
    and the audit reported "frontend DELETE, server ['GET']" against a plain
    download link that works correctly.
    """
    head = source[max(0, start - 120):start]
    return bool(re.search(r'\bfetch\s*\(\s*$', head))


def _calls_in(source: str) -> set[tuple[str, str]]:
    """Every (path, method) the module invokes."""
    found: set[tuple[str, str]] = set()
    for match in API_PATH.finditer(source):
        raw = match.group(1)
        if any(raw.startswith(skip) for skip in SKIP):
            continue
        # Non-fetch references (href, comments, EventSource) still prove the
        # path is USED -- so they are recorded for MISSING-ROUTE -- but they
        # carry no verb, so they must not be verb-checked.
        is_fetch = _is_fetch_call(source, match.start())

        # A URL built from a variable base is not a route this application
        # mounts. `url + '/api/pull'` is Ollama's own API on a user-supplied
        # host -- reported as a missing route by the first version.
        before = source[max(0, match.start() - 40):match.start()]
        if re.search(r'[A-Za-z0-9_\]\)]\s*\+\s*$', before):
            continue

        # A hole becomes a wildcard segment so it can match a path parameter.
        path = HOLE.sub('\x00', raw)

        # STRING CONCATENATION, not just template literals.
        #
        #   fetch('/api/templates/saved/' + encodeURIComponent(f) + '/restore')
        #
        # The regex stops at the closing quote, leaving `/api/templates/saved/`
        # -- a path that genuinely does not exist, because the real one has a
        # parameter and often further segments. All 11 remaining findings of
        # the previous version were this. A trailing `/` followed by a
        # concatenation means "a parameter goes here"; any literal tail that
        # follows is appended so the full shape is matched.
        after = source[match.end():match.end() + 200]
        # A literal immediately followed by `+` is a PREFIX, not a whole path.
        # `fetch('/api/icm' + path)` never requests /api/icm -- every caller
        # appends '/workspaces...'. Verified live: /api/icm is 404,
        # /api/icm/workspaces is 200. Treating the prefix as a real call
        # produced a MISSING-ROUTE against a router that works.
        if re.match(r'\s*\+', after) and not path.endswith('/'):
            tail = re.match(r"\s*\+[^'\"]*['\"](/[A-Za-z0-9_\-/]+)['\"]", after)
            if tail:
                found.add((path + tail.group(1), 'GET' if not is_fetch else 'GET'))
            continue
        if path.endswith('/') and re.match(r'\s*\+', after):
            path = path + '\x00'
            tail = re.match(r"\s*\+[^'\"]*['\"](/[A-Za-z0-9_\-/]+)['\"]", after)
            if tail:
                path += tail.group(1)

        # The verb must be read from THIS call's options object, not from
        # whatever `method:` happens to appear next in the file.
        #
        # /api/preview/restore is a POST, but a fixed 220-char window from the
        # path caught a different call site's options and reported a
        # METHOD-MISMATCH against correct code. The window now stops at the
        # end of the fetch() call -- the matching close paren -- so a verb
        # belonging to a later call cannot leak in.
        if not is_fetch:
            found.add((path, '*'))          # path used, verb unknown
            continue
        window = _call_options(source, match.end())
        verb = METHOD_NEAR.search(window)
        found.add((path, (verb.group(1) if verb else 'GET').upper()))
    return found


def _route_table() -> list[tuple[re.Pattern, str, set[str]]]:
    """(compiled pattern, original path, methods) for every mounted route."""
    sys.path.insert(0, str(REPO))
    from backend.app import app  # noqa: PLC0415

    table = []
    for route in app.routes:
        path = getattr(route, 'path', None)
        if not path or not path.startswith('/api/'):
            continue
        methods = set(getattr(route, 'methods', set()) or set()) - {'HEAD', 'OPTIONS'}
        pattern = '^' + re.sub(r'\{[^}]+\}', '[^/]+', re.escape(path)
                               .replace('\\{', '{').replace('\\}', '}')) + '$'
        table.append((re.compile(pattern), path, methods))
    return table


def _match(call_path: str, table) -> tuple[str | None, set[str]]:
    """Resolve a frontend path against the route table.

    A `\x00` marks where a template hole was; it matches any single segment,
    exactly as a path parameter does.
    """
    probe = call_path.replace('\x00', 'X')
    # UNION every matching route, do not stop at the first.
    #
    # FastAPI registers one route OBJECT per verb, so `/api/hooks` appears
    # twice -- once with {'GET'} and once with {'POST'}. Returning the first
    # match reported "frontend POST, server ['GET']" for 20+ endpoints that
    # accept POST perfectly well. Every one of those findings was false.
    matched_path, matched_methods = None, set()
    for pattern, original, methods in table:
        if pattern.match(probe):
            matched_path = matched_path or original
            matched_methods |= methods
    if matched_path:
        return matched_path, matched_methods
    # A hole may span a literal the pattern spells out; retry loosely.
    if '\x00' in call_path:
        loose = '^' + re.escape(call_path).replace('\\x00', '[^/]+') + '$'
        loose_re = re.compile(loose)
        loose_path, loose_methods = None, set()
        for _pattern, original, methods in table:
            if loose_re.match(original):
                loose_path = loose_path or original
                loose_methods |= methods
        if loose_path:
            return loose_path, loose_methods
    return None, set()


def run() -> AuditResult:
    findings = []
    modules = _pane_modules()
    table = _route_table()

    users: dict[tuple[str, str], set[str]] = {}
    silent = []
    for pane, source_path in modules.items():
        calls = _calls_in(source_path.read_text(encoding='utf-8', errors='replace'))
        if not calls:
            silent.append(pane)
        for call in calls:
            users.setdefault(call, set()).add(pane)

    missing, mismatched = [], []
    for (path, verb) in sorted(users):
        original, methods = _match(path, table)
        shown = path.replace('\x00', '{id}')
        if original is None:
            missing.append((shown, sorted(users[(path, verb)])))
        elif verb == '*':
            # Recorded from a non-fetch reference (href, comment, EventSource).
            # It proves the path is used -- so MISSING-ROUTE above still
            # applies -- but there is no verb to compare.
            continue
        elif methods and verb not in methods:
            mismatched.append((shown, verb, sorted(methods), sorted(users[(path, verb)])))

    for shown, panes in missing:
        findings.append(
            f'MISSING-ROUTE   {shown}  (used by {", ".join(panes[:4])})')
    for shown, verb, methods, panes in mismatched:
        findings.append(
            f'METHOD-MISMATCH {shown}  frontend {verb}, server {methods}  '
            f'(used by {", ".join(panes[:4])})')

    if silent:
        findings.append(
            f'-- {len(silent)} pane(s) make no API calls (correct for a '
            f'client-only tool): {", ".join(sorted(silent)[:12])}')
    findings.append(
        f'-- checked {len(users)} distinct (path, method) pairs across '
        f'{len(modules)} panes against {len(table)} mounted routes')

    return AuditResult(
        'module-completeness',
        len([f for f in findings if not f.startswith('--')]),
        findings,
        note='panes calling routes that do not exist, or with the wrong verb',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
