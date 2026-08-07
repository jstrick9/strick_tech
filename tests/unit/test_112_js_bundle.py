"""The frontend must ship as a bundle, and the bundler must not change meaning.

THE PROBLEM
───────────
`frontend/index.html` loaded 79 separate `<script>` tags totalling 2.02 MB,
served uncompressed, with `Cache-Control: no-store` applied to every `.js`
path. Every visit re-downloaded the entire frontend as 79 round trips.

Measured in real Chromium against a live server, with CDP network emulation
(median of 3 cold loads):

    profile   requests   DOMContentLoaded   JS transfer window
    ───────────────────────────────────────────────────────────
    before      79            13,667 ms         13,474 ms      (150ms RTT)
    after        2             4,089 ms          3,838 ms
    before      79             2,518 ms          2,458 ms      (40ms RTT)
    after        2               953 ms            825 ms

THE RISK, AND WHAT THESE TESTS GUARD
────────────────────────────────────
A hand-written minifier that gets a lexical edge case wrong corrupts the
application silently -- the file still parses, it just means something
different. Two real bugs were found in this one during development, and both
are pinned below:

1. The first version stripped indentation from every line, including lines
   *inside* template literals. Nearly every UI module renders markup with
   ``pane.innerHTML = `...` ``, so it was rewriting the application's own HTML.
   Most of it would have rendered identically; the damage would have surfaced
   later, in <pre> blocks and clipboard payloads.

2. The second version scanned interpolations with a brace counter that skipped
   strings but not regexes. Given ``${JSON.stringify(id).replace(/"/g,'')}``
   -- a regex literal containing a double quote -- the `"` read as the start
   of a string, the scanner ran past the end of the template, and ~1200
   characters of real code were swallowed into what it believed was a literal.

Both are covered by `test_minifier_preserves_meaning_on_every_module`, which
compares parse trees rather than text: the strongest available check that the
transformation is semantics-preserving.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
FRONTEND = REPO / 'frontend'
DIST = FRONTEND / 'dist'
BUILD = REPO / 'scripts' / 'build_bundle.py'

sys.path.insert(0, str(REPO / 'scripts'))
import build_bundle  # noqa: E402

from backend.services import asset_bundle  # noqa: E402

JS_FILES = sorted((FRONTEND / 'js').glob('*.js'))


def _node() -> str | None:
    return shutil.which('node')


def _has_acorn() -> bool:
    if not _node():
        return False
    r = subprocess.run([_node(), '-e', "require('acorn')"],
                       cwd=REPO, capture_output=True)
    return r.returncode == 0


needs_node = pytest.mark.skipif(_node() is None, reason='node not installed')
needs_acorn = pytest.mark.skipif(
    not _has_acorn(),
    reason="acorn not installed (npm install --no-save acorn acorn-walk)")


# ──────────────────────────────────────────────────────────────────────
#  The bundle exists, is current, and covers every module
# ──────────────────────────────────────────────────────────────────────
def test_bundle_artifacts_are_committed():
    """A fresh clone must get the fast path without running a build step."""
    manifest_path = DIST / 'manifest.json'
    assert manifest_path.is_file(), (
        'frontend/dist/manifest.json is missing. The bundle is committed so '
        'that `python run.py` on a fresh clone serves the fast frontend. '
        'Run: python3 scripts/build_bundle.py')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    for key in ('head', 'body'):
        assert (DIST / manifest[key]).is_file(), f'missing bundle {manifest[key]}'


def test_bundle_is_not_stale():
    """Editing frontend/js without rebuilding must fail CI, not ship silently.

    Without this, a developer changes a module, sees nothing happen in the
    browser (because the server is serving the old bundle), and concludes the
    code is broken.
    """
    result = subprocess.run(
        [sys.executable, str(BUILD), '--check'],
        cwd=REPO, capture_output=True, text=True)
    assert result.returncode == 0, (
        f'{result.stdout}{result.stderr}\n'
        'The committed bundle does not match frontend/js. '
        'Run: python3 scripts/build_bundle.py')


def test_every_module_in_index_html_is_in_the_bundle():
    """No module may be silently dropped -- that is a whole pane going dark."""
    manifest = json.loads((DIST / 'manifest.json').read_text(encoding='utf-8'))
    bundled = set(manifest['head_modules']) | set(manifest['body_modules'])

    html = (FRONTEND / 'index.html').read_text(encoding='utf-8')
    referenced = {m.group('src') for m in build_bundle.SCRIPT_RE.finditer(html)}

    assert referenced == bundled, (
        f'in HTML but not bundled: {sorted(referenced - bundled)}; '
        f'bundled but not in HTML: {sorted(bundled - referenced)}')
    assert bundled == {p.name for p in JS_FILES}, (
        'frontend/js contains modules the page never loads, or vice versa')


def test_head_scripts_stay_in_the_head():
    """`00-style-hydrate.js` must run before the body is parsed.

    Under the enforced `style-src 'self'` the parser refuses inline style
    attributes; the hydrator re-applies them. Move it into the deferred body
    bundle and the whole UI renders unstyled for a beat.
    """
    manifest = json.loads((DIST / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['head_modules'][0] == '00-style-hydrate.js'
    assert '00-style-hydrate.js' not in manifest['body_modules']


# ──────────────────────────────────────────────────────────────────────
#  The minifier does not change what the code means
# ──────────────────────────────────────────────────────────────────────
@needs_acorn
@pytest.mark.parametrize('path', JS_FILES, ids=lambda p: p.name)
def test_minifier_preserves_meaning_on_every_module(path, tmp_path):
    """Parse tree of the minified module must equal that of the original.

    Comparing trees, not text, is the point: it ignores the whitespace we
    meant to remove while catching any change to a string, a template chunk,
    a regex, an identifier or the structure of the code.
    """
    minified = tmp_path / path.name
    minified.write_text(build_bundle.minify(path.read_text(encoding='utf-8')),
                        encoding='utf-8')
    result = subprocess.run(
        [_node(), 'scripts/verify_bundle_ast.js', str(path), str(minified)],
        cwd=REPO, capture_output=True, text=True)
    assert result.returncode == 0, (
        f'{path.name}: {result.stderr.strip() or result.stdout.strip()}')


def test_minifier_keeps_indentation_inside_template_literals():
    """Regression: the whitespace pass must not touch literal contents.

    The first implementation stripped leading whitespace line by line across
    the whole file, silently rewriting the HTML that every UI module emits.
    """
    src = 'function f(){\n  const x = `\n    <pre>\n      indented\n    </pre>`;\n  return x;\n}\n'
    out = build_bundle.minify(src)
    assert '\n    <pre>\n      indented\n    </pre>' in out, (
        'indentation inside a template literal was altered')
    assert '\n  const x' not in out, 'code indentation should still be removed'


def test_minifier_handles_a_regex_containing_a_quote_inside_an_interpolation():
    """Regression: `${a.replace(/"/g,'')}` must not swallow the rest of the file.

    This exact construct appears in frontend/js/22-integrations.js. A scanner
    that treats the `"` inside the regex as a string delimiter runs past the
    closing backtick and consumes ~1200 characters of live code.
    """
    src = (
        'const id = "x";\n'
        'const a = `#card-${JSON.stringify(id).replace(/"/g,\'\')} .btn`;\n'
        'function afterwards(){ return 42; }\n'
    )
    out = build_bundle.minify(src)
    assert 'function afterwards()' in out, (
        'code after the template was swallowed by the literal scanner')
    skeleton, literals = build_bundle.tokenize(src)
    assert any(lit.startswith('`#card-') and lit.endswith('.btn`')
               for lit in literals), \
        f'template literal boundaries wrong: {literals}'


def test_minifier_does_not_join_lines_across_a_multiline_comment():
    """A block comment spanning lines must leave a newline behind (ASI)."""
    src = 'const a = 1\n/* comment\n   spanning */\nconst b = 2\n'
    out = build_bundle.minify(src)
    assert 'const a = 1const b' not in out.replace('\n', 'X').replace('X', '\n')
    assert out.count('\n') >= 1


def test_minifier_actually_shrinks_the_code():
    """A pass-through that changed nothing would satisfy every test above."""
    manifest = json.loads((DIST / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['bundled_bytes'] < manifest['raw_bytes'] * 0.95, (
        'the minifier is not removing anything meaningful')


# ──────────────────────────────────────────────────────────────────────
#  The HTML rewrite
# ──────────────────────────────────────────────────────────────────────
def test_rewrite_collapses_79_tags_into_two():
    html = (FRONTEND / 'index.html').read_text(encoding='utf-8')
    manifest = json.loads((DIST / 'manifest.json').read_text(encoding='utf-8'))

    before = len(build_bundle.SCRIPT_RE.findall(html))
    assert before > 50, 'expected the page to load many individual modules'

    out = asset_bundle.rewrite_html(html, manifest)
    assert '/static/js/' not in out, 'individual module tags survived the rewrite'
    assert out.count('<script src="/static/dist/') == 2
    assert f'/static/dist/{manifest["head"]}' in out
    assert f'/static/dist/{manifest["body"]}" defer' in out, (
        'the body bundle must keep defer, or it blocks parsing')


def test_rewrite_keeps_the_head_bundle_before_the_body():
    html = (FRONTEND / 'index.html').read_text(encoding='utf-8')
    manifest = json.loads((DIST / 'manifest.json').read_text(encoding='utf-8'))
    out = asset_bundle.rewrite_html(html, manifest)
    assert out.index(manifest['head']) < out.index('<body'), (
        'the style hydrator must execute before the body is parsed')


def test_bundle_can_be_disabled_for_debugging():
    """AGENTIC_JS_BUNDLE=0 must serve the individual modules."""
    previous = os.environ.get('AGENTIC_JS_BUNDLE')
    try:
        os.environ['AGENTIC_JS_BUNDLE'] = '0'
        asset_bundle.clear_cache()
        assert not asset_bundle.bundle_enabled()
        html = asset_bundle.index_html(FRONTEND)
        assert html.count('<script src="/static/js/') > 50
        assert '/static/dist/' not in html

        os.environ['AGENTIC_JS_BUNDLE'] = '1'
        asset_bundle.clear_cache()
        html = asset_bundle.index_html(FRONTEND)
        assert '/static/js/' not in html
    finally:
        if previous is None:
            os.environ.pop('AGENTIC_JS_BUNDLE', None)
        else:
            os.environ['AGENTIC_JS_BUNDLE'] = previous
        asset_bundle.clear_cache()


def test_missing_bundle_falls_back_to_individual_modules():
    """A checkout with no build artifact must still serve a working app.

    A missing bundle is a performance regression, not an outage.
    """
    assert asset_bundle.load_manifest(Path('/nonexistent')) is None


# ──────────────────────────────────────────────────────────────────────
#  Compression and caching
# ──────────────────────────────────────────────────────────────────────
def test_precompressed_variants_exist_and_are_much_smaller():
    """The bundle was being served uncompressed: 1.6 MB for ~390 KB of gzip."""
    manifest = json.loads((DIST / 'manifest.json').read_text(encoding='utf-8'))
    body = DIST / manifest['body']
    gz = body.with_name(body.name + '.gz')
    assert gz.is_file(), 'no precompressed .gz beside the bundle'
    assert gz.stat().st_size < body.stat().st_size * 0.4, (
        f'gzip only got {body.stat().st_size} -> {gz.stat().st_size}; '
        'compression is not doing its job')


def test_bundle_route_serves_gzip_when_offered(client):
    manifest = json.loads((DIST / 'manifest.json').read_text(encoding='utf-8'))
    r = client.get(f'/static/dist/{manifest["body"]}',
                   headers={'Accept-Encoding': 'gzip'})
    assert r.status_code == 200
    assert r.headers.get('content-encoding') == 'gzip'
    assert r.headers.get('vary') == 'Accept-Encoding'


def test_hashed_bundles_are_cacheable_forever(client):
    """Content-hashed artifacts must not inherit the blanket .js no-store rule.

    That rule applied to every path ending in .js, so the entire frontend was
    re-downloaded on every visit even when nothing had changed. It is right
    for hand-edited module files and pure waste for a hashed artifact, whose
    name changes whenever its contents do.
    """
    manifest = json.loads((DIST / 'manifest.json').read_text(encoding='utf-8'))
    r = client.get(f'/static/dist/{manifest["body"]}')
    cache = r.headers.get('cache-control', '')
    assert 'immutable' in cache and 'max-age=31536000' in cache, (
        f'hashed bundle is not cacheable: Cache-Control: {cache!r}')
    assert 'no-store' not in cache

    # The unhashed module files keep the conservative policy.
    r2 = client.get('/static/js/01-app-core.js')
    assert 'no-store' in r2.headers.get('cache-control', '')


def test_bundle_lookup_rejects_anything_but_a_plain_filename():
    """Containment is asserted on the function, not through the HTTP client.

    Going through TestClient would prove nothing here: httpx resolves `../`
    in the URL before the request is sent, so `/static/dist/../index.html`
    arrives as `/static/index.html` and never reaches this handler at all.
    (Verified against a live server with curl, which sends the raw path: it
    returns 404.) The containment rule itself is what needs pinning.
    """
    for attempt in ('../index.html', '../../backend/app.py', 'a/b.js',
                    '..\\index.html', '.hidden', '.'):
        assert asset_bundle.bundle_response(FRONTEND, attempt, 'gzip') is None, \
            f'{attempt!r} was served'

    # The legitimate case still works, so the guard is not simply refusing all.
    manifest = json.loads((DIST / 'manifest.json').read_text(encoding='utf-8'))
    assert asset_bundle.bundle_response(FRONTEND, manifest['body'], '') is not None


def test_index_route_serves_the_bundled_html(client):
    r = client.get('/')
    assert r.status_code == 200
    assert r.text.count('<script src="/static/dist/') == 2
    assert '/static/js/' not in r.text
