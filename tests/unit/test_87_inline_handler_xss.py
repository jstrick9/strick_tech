"""Phase 1 of the CSP recommendation: close the live stored XSS.

THE BUG
───────
`onclick="f('${value}')"` places `value` inside a JavaScript string, inside an
HTML attribute. escHtml() does NOT protect that position — the browser
HTML-decodes the attribute BEFORE the JS parser runs, so an escaped quote comes
straight back:

    escHtml("a'),alert(1),('")  ->  a&#39;),alert(1),(&#39;
    rendered : onclick="f('a&#39;),alert(1),(&#39;')"
    decoded  : f('a'),alert(1),('')        <- valid JS, executes

Shipped instance, verified end to end against the running server:

    POST /api/agents {"name": "X'),alert(document.cookie),('"}
      -> stored verbatim (agents.py applied only .strip()[:80])
    rendered at 01-app-core.js:3783 as
      onclick="selectMention('@X'),alert(document.cookie),('')"
    new Function(body) -> PARSES AS VALID JS

Stored XSS, persisted in the database, triggered by opening the @-mention
dropdown. `unsafe-inline` in the CSP is what allows it to execute, and that
directive cannot be removed while 772 inline handlers exist — which is why the
fix is at the interpolation site, not the CSP.

THE FIX (two independent layers)
  1. jsArg() in 01-app-core.js — emits a complete quoted JS literal via
     JSON.stringify, then HTML-encodes the quotes so the decode step cannot
     undo it. Applied to 58 handler interpolations.
  2. Server-side character validation on agent names, so a renderer that
     forgets is not a vulnerability on its own.
  3. scripts/lint_inline_handlers.py in CI — the part that makes it permanent.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JS_DIR = ROOT / 'frontend' / 'js'
CORE_JS = (JS_DIR / '01-app-core.js').read_text(encoding='utf-8')

ATTR = re.compile(r'\bon[a-z]+\s*=\s*"([^"]*)"')
INTERP = re.compile(r'\$\{([^}]*)\}')


def _js_arg(value) -> str:
    """Python mirror of jsArg() — the property under test, not the syntax."""
    return (
        json.dumps(value)
        .replace('&', '&amp;')
        .replace('"', '&quot;')
        .replace("'", '&#39;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
    )


def _html_decode(s: str) -> str:
    """What the browser does to an attribute value before the JS parser runs."""
    return (
        s.replace('&#39;', "'")
        .replace('&quot;', '"')
        .replace('&lt;', '<')
        .replace('&gt;', '>')
        .replace('&amp;', '&')
    )


# ══ The vulnerability, and that jsArg closes it ═══════════════════════════════
def test_eschtml_does_not_protect_a_js_string_context():
    """The premise. If this ever stops being true the fix can be simplified —
    but it is true, and it is why 24 handlers using escHtml() were unsafe."""
    payload = "a'),alert(1),('"
    esc = payload.replace('&', '&amp;').replace('<', '&lt;').replace(
        '>', '&gt;').replace('"', '&quot;').replace("'", '&#39;')
    rendered = f"f('{esc}')"
    decoded = _html_decode(rendered)
    assert decoded == "f('a'),alert(1),('')"
    assert decoded.count('(') > 1, 'the payload did not break out — premise wrong'


@pytest.mark.parametrize('payload', [
    "X'),alert(document.cookie),('",
    'X"),alert(1),("',
    "'; alert(1); '",
    "a\\'),alert(1),(\\'",
    "</script><script>alert(1)</script>",
    "\u0000\u001f control",
])
def test_jsarg_survives_html_decoding(payload):
    """After the browser decodes the attribute, the value must still be one
    inert string argument — not code."""
    decoded = _html_decode(f'f({_js_arg(payload)})')
    # Exactly one argument, and it round-trips to the original text.
    m = re.fullmatch(r'f\((".*")\)', decoded, re.S)
    assert m, f'jsArg produced something other than a single literal: {decoded}'
    assert json.loads(m.group(1)) == payload


def test_jsarg_exists_and_is_documented():
    assert 'function jsArg(value)' in CORE_JS
    assert 'HTML-decodes' in CORE_JS, 'the reasoning must survive with the code'


def test_the_shipped_instance_is_fixed():
    """selectMention was the live exploit.

    Matches either handler syntax. Phase 2 migrated this site from
    `onclick=` to `data-act-click=`; the property under test is that the agent
    name is passed through jsArg(), not which attribute carries it. Pinning
    the attribute name made this test fail on a change that did not weaken
    anything.
    """
    m = re.search(
        r'(?:onclick|data-act-click)="selectMention\(([^"]*)\)"', CORE_JS
    )
    assert m, 'the mention handler moved — re-verify it is still safe'
    assert 'jsArg(' in m.group(1), f'still interpolating raw: {m.group(1)}'


# ══ Repo-wide: no handler interpolates untrusted data ═════════════════════════
def test_no_unsafe_interpolation_remains():
    """The cleanup. Mirrors the CI lint so a failure here names the file."""
    result = subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'lint_inline_handlers.py')],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout


def test_no_handler_uses_eschtml_inside_a_js_string():
    """The specific wrong-escaper pattern, called out by name so it cannot
    quietly return."""
    offenders = []
    for path in sorted(JS_DIR.glob('*.js')):
        for i, line in enumerate(path.read_text(encoding='utf-8').split('\n'), 1):
            if line.lstrip().startswith(('//', '*', '/*')):
                continue
            for m in ATTR.finditer(line):
                body = m.group(1)
                if re.search(r"'\$\{escHtml\(", body) or re.search(r'"\$\{escHtml\(', body):
                    offenders.append(f'{path.name}:{i}')
    assert not offenders, f'escHtml() used inside a JS string context: {offenders}'


def test_lint_is_wired_into_ci():
    """The cleanup is the easy half; the invariant is the half that lasts."""
    ci = (ROOT / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
    assert 'lint_inline_handlers.py' in ci


def test_lint_actually_fails_on_a_bad_handler(tmp_path, monkeypatch):
    """Prove the guard catches what it claims, rather than trusting a green run."""
    bad = JS_DIR / 'zz_lint_probe.js'
    bad.write_text('const x = `<button onclick="f(\'${user.name}\')">go</button>`;\n')
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / 'scripts' / 'lint_inline_handlers.py')],
            capture_output=True, text=True,
        )
        assert result.returncode == 1, 'the lint passed an unsafe handler'
        assert 'zz_lint_probe.js' in result.stdout
    finally:
        bad.unlink()


def test_lint_accepts_the_correct_form(tmp_path):
    # Spelled data-act-click, not onclick. Since script-src dropped
    # 'unsafe-inline' the linter also rejects inline handlers outright — they
    # are dead controls, not merely risky — so the old onclick fixture now
    # fails for a second, unrelated reason. jsArg() is what this test is
    # actually about, and it applies identically to both attributes.
    good = JS_DIR / 'zz_lint_ok.js'
    good.write_text('const x = `<button data-act-click="f(${jsArg(user.name)})">go</button>`;\n')
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / 'scripts' / 'lint_inline_handlers.py')],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f'jsArg form rejected: {result.stdout}'
    finally:
        good.unlink()


def test_lint_ignores_commented_out_code():
    """Several files DOCUMENT a previously-fixed handler bug by quoting the old
    code. Flagging that prose would push people to delete the explanation."""
    src = (ROOT / 'scripts' / 'lint_inline_handlers.py').read_text(encoding='utf-8')
    assert "startswith(('//', '*', '/*'))" in src


# ══ Server-side defence in depth ══════════════════════════════════════════════
@pytest.mark.parametrize('name', [
    "X'),alert(document.cookie),('",
    'has"quote',
    '<script>alert(1)</script>',
    'back\\slash',
])
def test_agent_names_with_breakout_characters_are_rejected(client, name):
    """The frontend fix closes this instance; validation stops the class."""
    r = client.post('/api/agents', json={'name': name, 'role': 'probe'})
    assert r.status_code == 400, f'accepted a dangerous agent name: {name!r}'
    assert 'cannot contain' in r.json()['error']


@pytest.mark.parametrize('name', [
    'Research Bot 2',
    'Data-Analyst_v3',
    'Café Assistant',
    '日本語エージェント',
])
def test_legitimate_agent_names_still_work(client, name):
    """Over-blocking would be its own bug — non-ASCII names are fine."""
    r = client.post('/api/agents', json={'name': name, 'role': 'probe'})
    assert r.status_code == 200, f'rejected a legitimate name {name!r}: {r.text[:150]}'
    agent_id = r.json()['agent']['id']
    client.delete(f'/api/agents/{agent_id}')


def test_rejection_is_explicit_not_silent_stripping():
    """A user who typed a quote should be told, not have their name quietly
    altered under them."""
    src = (ROOT / 'backend' / 'routers' / 'agents.py').read_text(encoding='utf-8')
    assert '_UNSAFE_NAME_CHARS' in src
    assert 'status_code=400' in src
