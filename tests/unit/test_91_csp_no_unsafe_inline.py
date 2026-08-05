"""Phase 2/3 completion — script-src no longer permits 'unsafe-inline'.

This is the directive the whole phase 2 migration existed to remove. Two
things must both hold, permanently:

  1. the enforcing header does not contain 'unsafe-inline' on script-src
  2. the frontend contains no inline handlers or inline <script> blocks

They are one invariant, not two. Re-introducing either half silently restores
the weakness: an inline handler added after the switch is a dead control, and
'unsafe-inline' added back re-opens ~714 unprotected innerHTML sites.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
FRONTEND = ROOT / 'frontend'
INDEX = FRONTEND / 'index.html'
JS_DIR = FRONTEND / 'js'

sys.path.insert(0, str(ROOT / 'scripts'))


def _csp(client) -> str:
    r = client.get('/api/health')
    return r.headers.get('content-security-policy', '')


def _directive(policy: str, name: str) -> str:
    for part in policy.split(';'):
        part = part.strip()
        if part.startswith(name + ' ') or part == name:
            return part
    return ''


# ══ The header ════════════════════════════════════════════════════════════════
def test_script_src_does_not_allow_unsafe_inline(client):
    """The point of the entire phase 2 migration."""
    script_src = _directive(_csp(client), 'script-src')
    assert script_src, 'script-src directive is missing entirely'
    assert "'unsafe-inline'" not in script_src, (
        f"script-src still permits inline script: {script_src}"
    )


def test_script_src_does_not_allow_unsafe_eval(client):
    """The shim parses rather than evaluates precisely so this stays out."""
    assert "'unsafe-eval'" not in _directive(_csp(client), 'script-src')


def test_default_src_is_self(client):
    assert "default-src 'self'" in _csp(client)


def test_object_and_base_uri_stay_locked(client):
    policy = _csp(client)
    assert "object-src 'none'" in policy
    assert "base-uri 'self'" in policy


def test_style_src_inline_is_a_documented_exception(client):
    """style-src deliberately keeps 'unsafe-inline' — the codebase sets
    element.style throughout. Asserted so the exception stays a decision
    rather than drifting into an accident, and so nobody 'fixes' it without
    reading why. A style injection cannot execute script under this policy."""
    assert "'unsafe-inline'" in _directive(_csp(client), 'style-src')
    app_src = (ROOT / 'backend' / 'app.py').read_text(encoding='utf-8')
    assert 'style-src DELIBERATELY keeps' in app_src, (
        'the reasoning must survive alongside the code'
    )


# ══ The frontend must stay free of inline script ══════════════════════════════
INLINE_HANDLER = re.compile(r'\son[a-z]+\s*=\s*"')


def _code_lines(path: pathlib.Path):
    """Yield (lineno, line), skipping comments.

    Several files DOCUMENT a previously-fixed handler bug by quoting the old
    markup. Flagging that prose would push people to delete the explanation,
    which is the opposite of what this review has been preserving.
    """
    for i, line in enumerate(path.read_text(encoding='utf-8').split('\n'), 1):
        if path.suffix == '.js' and line.lstrip().startswith(('//', '*', '/*')):
            continue
        yield i, line


def test_no_inline_event_handlers_remain():
    offenders = []
    for path in [INDEX, *sorted(JS_DIR.glob('*.js'))]:
        for lineno, line in _code_lines(path):
            if INLINE_HANDLER.search(line):
                offenders.append(f'{path.name}:{lineno}')
    assert not offenders, (
        'inline on*= handlers are dead under the CSP — use data-act-<event>=:\n  '
        + '\n  '.join(offenders[:20])
    )


def test_index_html_has_no_inline_script_blocks():
    html = INDEX.read_text(encoding='utf-8')
    blocks = re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', html, re.S)
    non_empty = [b for b in blocks if b.strip()]
    assert not non_empty, (
        f'{len(non_empty)} inline <script> block(s) remain; they will not '
        f'execute under this CSP. Extract them to /static/js/.'
    )


def test_the_extracted_boot_scripts_are_present():
    """Extraction must not have lost anything: each block became a real file
    that index.html actually references."""
    for name in (
        '00-theme-boot.js',
        '90-sidebar-shortcut.js',
        '91-mode-switcher.js',
        '92-pane-error-boundary.js',
        '93-shortcuts-overlay.js',
    ):
        assert (JS_DIR / name).exists(), f'{name} is missing'
        assert name in INDEX.read_text(encoding='utf-8'), f'{name} is not loaded'


def test_theme_boot_stays_render_blocking():
    """It applies the saved theme before first paint. Adding defer would
    reintroduce a flash of the wrong appearance on every load."""
    html = INDEX.read_text(encoding='utf-8')
    m = re.search(r'<script src="/static/js/00-theme-boot\.js"([^>]*)>', html)
    assert m, 'the theme boot script is not loaded'
    assert 'defer' not in m.group(1) and 'async' not in m.group(1)


def test_migration_tool_reports_nothing_left():
    """The tool is the same one used to perform the migration, so this also
    guards against it silently losing the ability to see handlers."""
    r = subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'migrate_inline_handlers.py')],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert 'total handlers : 0' in r.stdout, r.stdout[:600]


def test_shim_and_handlers_are_loaded_before_the_panes():
    """A pane file that renders data-act markup during its own load would find
    no listener attached if the shim came later."""
    html = INDEX.read_text(encoding='utf-8')
    delegate = html.index('00-delegate.js')
    handlers = html.index('00-handlers.js')
    first_pane = html.index('01-app-core.js')
    assert delegate < first_pane
    assert handlers < first_pane


# ══ Every dispatched name must actually exist ═════════════════════════════════
CALL = re.compile(r'^\s*([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\((.*)\)\s*$')
ACT_ATTR = re.compile(r'\bdata-act-[a-z]+\s*=\s*"([^"]*)"')
DEFINITIONS = (
    re.compile(r'^\s*(?:async\s+)?function\s+([A-Za-z_$][\w$]*)', re.M),
    re.compile(
        r'^\s*(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function|\()',
        re.M,
    ),
    re.compile(r'^\s*window\.([A-Za-z_$][\w$]*)\s*=', re.M),
    re.compile(r"on\('([A-Za-z_$][\w$]*)'", re.M),
)
BUILTIN_ROOTS = {'window', 'document', 'navigator', 'console', 'JSON', 'Math'}


def test_every_dispatched_function_is_defined():
    """The failure mode this migration had to avoid: a control that renders,
    looks clickable, and silently does nothing because the shim cannot resolve
    the name. Caught one real instance during the migration —
    `this.parentElement.parentElement.removeAttribute(...)` had been converted
    as though `this.parentElement...` were a function name.
    """
    sources = [INDEX, *sorted(JS_DIR.glob('*.js'))]
    combined = '\n'.join(p.read_text(encoding='utf-8') for p in sources)

    defined: set[str] = set()
    for pattern in DEFINITIONS:
        defined.update(pattern.findall(combined))
    # The shim's own documentation example.
    defined.add('doThing')

    missing: dict[str, str] = {}
    for path in sources:
        for lineno, line in _code_lines(path):
            for spec in ACT_ATTR.findall(line):
                for stmt in spec.split(';'):
                    stmt = stmt.strip()
                    if not stmt:
                        continue
                    # Values assembled at render time -- `${a.action}` in
                    # emptyState/pageHeader/QUICK_ACTIONS, and the
                    # string-concatenated equivalent in the error boundary.
                    # The literal text is a placeholder, not a call; what it
                    # resolves to is covered by
                    # test_runtime_action_strings_are_plain_calls below.
                    if '${' in stmt or "' + " in stmt:
                        continue
                    m = CALL.match(stmt.replace('?.(', '('))
                    if not m:
                        missing.setdefault(stmt[:60], f'{path.name}:{lineno} (unparseable)')
                        continue
                    root = m.group(1).split('.')[0]
                    if root not in defined and root not in BUILTIN_ROOTS:
                        missing.setdefault(m.group(1), f'{path.name}:{lineno}')

    assert not missing, 'data-act names with no definition:\n  ' + '\n  '.join(
        f'{name} <- {where}' for name, where in list(missing.items())[:20]
    )


def test_no_data_act_value_roots_at_a_dom_expression():
    """`this.x.y()` and `event.x()` cannot be resolved by walking window, so
    converting one produces a dead control. The migrator rejects them; this
    stops a hand-written one slipping through."""
    offenders = []
    for path in [INDEX, *sorted(JS_DIR.glob('*.js'))]:
        for lineno, line in _code_lines(path):
            for spec in ACT_ATTR.findall(line):
                for stmt in spec.split(';'):
                    m = CALL.match(stmt.strip().replace('?.(', '('))
                    if m and m.group(1).split('.')[0] in ('this', 'event', 'e', 'ev'):
                        offenders.append(f'{path.name}:{lineno} {m.group(1)}')
    assert not offenders, offenders[:10]


@pytest.mark.parametrize('attr', ['data-close', 'data-hide'])
def test_declarative_intents_use_known_directives(attr):
    """A typo'd directive fails open — nothing happens and nothing is logged."""
    pattern = re.compile(rf'\b{attr}\s*=\s*"([^"]*)"')
    for path in [INDEX, *sorted(JS_DIR.glob('*.js'))]:
        for lineno, line in _code_lines(path):
            for value in pattern.findall(line):
                if '${' in value:
                    continue
                assert (
                    value in ('self', 'parent')
                    or value.startswith(('id:', 'closest:', 'parent:'))
                ), f'{path.name}:{lineno} unknown {attr} directive: {value!r}'


# ══ Runtime-assembled action strings ══════════════════════════════════════════
ACTION_LITERAL = re.compile(r"""action:\s*(['"`])([^'"`]+)\1""")


def test_runtime_action_strings_are_plain_calls():
    """`data-act-click="${a.action}"` puts a value from a data structure into
    the attribute. The shim will only dispatch a plain call of a known
    function, so every `action:` literal in the codebase must be exactly that
    — a bare name with no parentheses renders a button that does nothing.

    Templated actions like `nav('${paneId}')` are truncated by this regex at
    the interpolation; the prefix is still enough to prove the call shape.
    """
    bad = []
    for path in sorted(JS_DIR.glob('*.js')):
        text = path.read_text(encoding='utf-8')
        # Only files that actually feed an action into a data-act attribute
        # are in scope. 57-account-settings.js uses `data-action="..."` as a
        # lookup KEY dispatched by its own addEventListener — those values are
        # deliberately bare names and are not the shim's concern.
        if 'data-act-' not in text or '${a.action}' not in text and '${action}' not in text:
            continue
        for lineno, line in _code_lines(path):
            for _, value in ACTION_LITERAL.findall(line):
                if '(' not in value.strip():
                    bad.append(f'{path.name}:{lineno} action:{value!r} is not a call')
    assert not bad, '\n  '.join(bad)


def test_shim_refuses_a_bare_name_rather_than_guessing():
    """Documents the contract the test above relies on: the shim will not
    'helpfully' call a function named by a bare identifier."""
    shim = (JS_DIR / '00-delegate.js').read_text(encoding='utf-8')
    assert 'not a plain call, refusing' in shim
