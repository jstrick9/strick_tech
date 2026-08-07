#!/usr/bin/env python3
"""Build the frontend JavaScript bundle.

Why this exists
---------------
`frontend/index.html` loads 79 separate `<script>` tags totalling ~2.0 MB.
Every one of them is a separate HTTP request, a separate round trip and a
separate parse task; the slowest single file measured 364 ms on a cold load.
Bundling collapses that into two requests (a tiny head bundle and one body
bundle) without changing a single line of application code.

Design constraints this script deliberately respects
----------------------------------------------------
1. **No Node/npm dependency.** The platform installs with pip only. A
   contributor who clones the repo and runs `python run.py` must get a
   working, fast UI. So this is stdlib-only Python.
2. **`index.html` stays the single source of truth for load order.** The
   script tags are parsed out of the HTML rather than duplicated in a config
   file, so a new module added to the page is automatically bundled. A list
   that has to be kept in sync by hand is a list that goes out of sync.
3. **Head scripts stay in the head.** `00-style-hydrate.js` must execute
   before the body is parsed (strict `style-src` refuses inline style
   attributes at parse time), so head and body scripts get separate bundles
   rather than one blob at the end of the document.
4. **Execution order is preserved exactly.** The browser runs all
   non-`defer` scripts in document order, then all `defer` scripts in
   document order. The bundle concatenates in precisely that sequence.
5. **Conservative minification only.** This codebase resolves handlers by
   string name off `window`, so identifier renaming is not safe. We strip
   comments and redundant whitespace, which is behaviour-preserving.

Outputs
-------
    frontend/dist/head.<hash>.js
    frontend/dist/app.<hash>.js
    frontend/dist/manifest.json

The hash is content-derived, so the files are safe to serve immutable and a
rebuild automatically busts the cache.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND = REPO_ROOT / 'frontend'
INDEX = FRONTEND / 'index.html'
DIST = FRONTEND / 'dist'
MANIFEST = DIST / 'manifest.json'

# Matches the script tags we bundle. Only local /static/js/ sources are
# eligible -- vendored libraries under /static/vendor/ are left alone because
# they are large, cacheable, and already loaded on demand.
SCRIPT_RE = re.compile(
    r'<script\s+src="/static/js/(?P<src>[^"]+)"(?P<attrs>[^>]*)></script>'
)


# ──────────────────────────────────────────────────────────────────────────
#  Comment / whitespace stripping
# ──────────────────────────────────────────────────────────────────────────
#
# A note on why this is a hand-written scanner rather than a few regexes.
#
# The first version of this file used a regex whitespace pass and it silently
# corrupted the build: it stripped the leading indentation from every line
# *inside* multi-line template literals. Nearly every UI module in this
# codebase renders markup with `pane.innerHTML = \`...\``, so that pass was
# rewriting the application's own HTML. Most of it would have rendered
# identically and the damage would only have surfaced later in <pre> blocks,
# whitespace-sensitive CSS and copy-to-clipboard payloads. The scanner below
# therefore treats every string, template literal and regex literal as an
# opaque, byte-preserved region; only code outside those regions is touched.

_PLACEHOLDER = '\x00%d\x00'

# Characters that, as the previous significant token, mean a following `/` is
# a division operator rather than the start of a regex literal.
_DIV_CONTEXT = '_$)]}`\'"'


def _scan_string(source: str, i: int) -> int:
    """Return the index just past the quoted string starting at `source[i]`."""
    quote = source[i]
    i += 1
    n = len(source)
    while i < n:
        c = source[i]
        if c == '\\':
            i += 2
            continue
        if c == quote:
            return i + 1
        if c == '\n':          # unterminated; bail rather than run away
            return i
        i += 1
    return n


def _scan_regex(source: str, i: int) -> int:
    """Return the index just past the regex literal starting at `source[i]`."""
    i += 1
    n = len(source)
    in_class = False
    while i < n:
        c = source[i]
        if c == '\\':
            i += 2
            continue
        if c == '[':
            in_class = True
        elif c == ']':
            in_class = False
        elif c == '/' and not in_class:
            i += 1
            break
        elif c == '\n':
            return i
        i += 1
    while i < n and source[i].isalpha():   # flags
        i += 1
    return i


def _scan_interpolation(source: str, i: int) -> int:
    """Return the index just past the `}` closing the `${` at `source[i]`.

    This must be a real (if small) code scanner, not a brace counter. The
    original version simply counted `{`/`}` while skipping strings, and it
    was wrong in a way that silently corrupted output: an interpolation like

        ${JSON.stringify(id).replace(/"/g,'')}

    contains a *regex literal containing a double quote*. Without regex
    awareness the `"` reads as the start of a string, the scanner runs past
    the end of the template, and ~1200 characters of code get swallowed into
    what the minifier believes is one literal. So interpolations recurse
    through the same string/regex/template handling as top-level code.
    """
    assert source[i:i + 2] == '${'
    i += 2
    n = len(source)
    depth = 1
    prev = ''
    while i < n and depth:
        c = source[i]
        nxt = source[i + 1] if i + 1 < n else ''

        if c == '/' and nxt == '/':
            while i < n and source[i] != '\n':
                i += 1
            continue
        if c == '/' and nxt == '*':
            end = source.find('*/', i + 2)
            i = n if end == -1 else end + 2
            continue
        if c == '`':
            i = _scan_template(source, i)
            prev = '`'
            continue
        if c in ('"', "'"):
            i = _scan_string(source, i)
            prev = '"'
            continue
        if c == '/' and not (prev.isalnum() or prev in _DIV_CONTEXT):
            i = _scan_regex(source, i)
            prev = '/'
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return i + 1
        if not c.isspace():
            prev = c
        i += 1
    return i


def _scan_template(source: str, i: int) -> int:
    """Return the index just past the template literal starting at `source[i]`.

    Nesting is arbitrary: an interpolation may contain further templates,
    strings and regexes, each of which may contain backticks or braces.
    """
    assert source[i] == '`'
    i += 1
    n = len(source)
    while i < n:
        c = source[i]
        if c == '\\':
            i += 2
            continue
        if c == '`':
            return i + 1
        if c == '$' and i + 1 < n and source[i + 1] == '{':
            i = _scan_interpolation(source, i)
            continue
        i += 1
    return n


def tokenize(source: str) -> tuple[str, list[str]]:
    """Strip comments and replace every literal with an opaque placeholder.

    Returns `(skeleton, literals)`. The skeleton contains only code, so it is
    safe to reformat; `restore()` puts the literals back byte-for-byte.
    """
    out: list[str] = []
    literals: list[str] = []
    i = 0
    n = len(source)
    prev = ''   # last significant code character, for regex-vs-divide

    while i < n:
        c = source[i]
        nxt = source[i + 1] if i + 1 < n else ''

        if c == '/' and nxt == '/':
            while i < n and source[i] != '\n':
                i += 1
            continue

        if c == '/' and nxt == '*':
            end = source.find('*/', i + 2)
            if end == -1:
                break
            # A comment that spanned lines must leave a newline behind, or it
            # can join two statements and change automatic semicolon insertion.
            if '\n' in source[i:end]:
                out.append('\n')
            i = end + 2
            continue

        if c in ('"', "'", '`'):
            end = _scan_template(source, i) if c == '`' else _scan_string(source, i)
            out.append(_PLACEHOLDER % len(literals))
            literals.append(source[i:end])
            prev = c
            i = end
            continue

        # `/` starts a regex unless the previous token could end an expression.
        if c == '/' and not (prev.isalnum() or prev in _DIV_CONTEXT):
            end = _scan_regex(source, i)
            out.append(_PLACEHOLDER % len(literals))
            literals.append(source[i:end])
            prev = '/'
            i = end
            continue

        out.append(c)
        if not c.isspace():
            prev = c
        i += 1

    return ''.join(out), literals


def restore(skeleton: str, literals: list[str]) -> str:
    return re.sub(r'\x00(\d+)\x00',
                  lambda m: literals[int(m.group(1))], skeleton)


def collapse_whitespace(skeleton: str) -> str:
    """Drop blank lines and indentation from the code skeleton.

    Deliberately line-oriented rather than a full whitespace squeeze: keeping
    one statement per line means a production stack trace still points at a
    recognisable line of code, which matters when the only debugging surface
    is a user's browser console. It also sidesteps every ASI hazard, since no
    newline that the author wrote is ever removed.
    """
    return '\n'.join(
        line.strip() for line in skeleton.split('\n') if line.strip()
    )


def minify(source: str) -> str:
    skeleton, literals = tokenize(source)
    return restore(collapse_whitespace(skeleton), literals)


def strip_comments(source: str) -> str:
    """Comment removal only, literals untouched. Used by tests and tooling."""
    skeleton, literals = tokenize(source)
    return restore(skeleton, literals)


# ──────────────────────────────────────────────────────────────────────────
#  Load-order extraction
# ──────────────────────────────────────────────────────────────────────────
def parse_index(html: str) -> tuple[list[str], list[str]]:
    """Return (head_scripts, body_scripts) in browser execution order.

    Browser semantics being reproduced: within a document, all non-`defer`
    classic scripts execute in source order as the parser reaches them, and
    all `defer` scripts execute afterwards, also in source order. We
    therefore emit non-deferred files first, then deferred ones.
    """
    body_start = html.find('<body')
    if body_start == -1:
        raise SystemExit('build_bundle: could not locate <body> in index.html')

    head_plain: list[str] = []
    head_defer: list[str] = []
    body_plain: list[str] = []
    body_defer: list[str] = []

    for m in SCRIPT_RE.finditer(html):
        src = m.group('src')
        deferred = 'defer' in m.group('attrs')
        in_head = m.start() < body_start
        if in_head:
            (head_defer if deferred else head_plain).append(src)
        else:
            (body_defer if deferred else body_plain).append(src)

    return head_plain + head_defer, body_plain + body_defer


# ──────────────────────────────────────────────────────────────────────────
#  Bundle assembly
# ──────────────────────────────────────────────────────────────────────────
def concat(names: list[str], *, do_minify: bool) -> str:
    """Concatenate modules, isolating each behind an explicit separator.

    Each file is preceded by a banner comment naming it. That single line
    per module is worth its bytes: without it, a bundled stack trace is
    unattributable to a source file. A `;` separator on its own line
    guarantees that a file ending in an expression cannot be glued onto the
    next file's leading parenthesis (the classic IIFE concatenation hazard).
    """
    parts: list[str] = []
    for name in names:
        path = FRONTEND / 'js' / name
        if not path.exists():
            raise SystemExit(f'build_bundle: missing module {path}')
        text = path.read_text(encoding='utf-8')
        if do_minify:
            text = minify(text)
        parts.append(f'\n;/* {name} */\n{text}\n')
    return ''.join(parts)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]


SPLIT_PLAN = REPO_ROOT / 'scripts' / 'split-plan.json'


def load_split_plan(refresh: bool = False) -> dict:
    """Return the pane -> lazy-modules plan.

    The plan is DERIVED from the source by `scripts/analyse_split.js`, which
    uses a real JavaScript parser, and the result is committed to
    `scripts/split-plan.json`. Node is therefore needed only to *change* the
    split, never to build or run the app -- same arrangement as the bundle
    artifact itself.

    A pure-Python regex version of this analysis was written first and
    deleted. It disagreed with the parser on 11 modules, in the direction
    that silently breaks panes: it declared modules deferrable that
    `01-app-core.js` snapshots during boot. Approximating a JS parser with
    regular expressions is not something to ship as a correctness gate.
    """
    if refresh:
        node = shutil.which('node')
        if not node:
            raise SystemExit(
                'build_bundle: --refresh-split needs node.\n'
                'Run: npm install --no-save acorn acorn-walk')
        result = subprocess.run(
            [node, str(REPO_ROOT / 'scripts' / 'analyse_split.js')],
            cwd=REPO_ROOT, capture_output=True, text=True)
        if result.returncode != 0:
            raise SystemExit(f'build_bundle: split analysis failed\n{result.stderr}')
        plan = json.loads(result.stdout)
        SPLIT_PLAN.write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')
        return plan

    if not SPLIT_PLAN.exists():
        return {'lazy': {}, 'lazyFiles': []}
    return json.loads(SPLIT_PLAN.read_text(encoding='utf-8'))


def build(do_minify: bool = True, split: bool = True) -> dict:
    html = INDEX.read_text(encoding='utf-8')
    head_names, body_names = parse_index(html)

    plan = load_split_plan() if split else {'lazy': {}, 'lazyFiles': []}
    lazy_files = set(plan.get('lazyFiles', []))

    # Sanity: the plan must only name modules the page actually loads. A stale
    # plan referencing a deleted module would silently drop it from both the
    # core bundle and every chunk.
    unknown = lazy_files - set(head_names) - set(body_names)
    if unknown:
        raise SystemExit(
            f'build_bundle: split plan names modules that index.html does not '
            f'load: {sorted(unknown)}. Re-run with --refresh-split.')

    body_names = [n for n in body_names if n not in lazy_files]

    head_js = concat(head_names, do_minify=do_minify)
    body_js = concat(body_names, do_minify=do_minify)

    head_hash = content_hash(head_js)
    body_hash = content_hash(body_js)

    raw_bytes = sum(
        (FRONTEND / 'js' / n).stat().st_size for n in head_names + body_names
    )

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True, exist_ok=True)

    head_file = f'head.{head_hash}.js'
    body_file = f'app.{body_hash}.js'
    (DIST / head_file).write_text(head_js, encoding='utf-8')
    (DIST / body_file).write_text(body_js, encoding='utf-8')

    # Precompress at build time rather than compressing per request.
    #
    # The bundle was being served entirely uncompressed -- 1.6 MB on the wire
    # for a file that gzips to roughly a quarter of that. The obvious fix,
    # GZipMiddleware, is the wrong one here: this app streams SSE from the
    # chat endpoint, and a compressing middleware that buffers or reframes
    # those responses has broken streaming in this codebase before. Static,
    # content-hashed artifacts can simply be compressed once at build time
    # and served as-is, which is both faster (maximum compression level, paid
    # once) and touches nothing else in the request path.
    # One chunk per pane, fetched on first navigation to that pane. Each is
    # content-hashed like the core bundles, so it is immutably cacheable.
    chunks = {}
    chunk_outputs = []
    for pane, modules in sorted(plan.get('lazy', {}).items()):
        chunk_js = concat(modules, do_minify=do_minify)
        chunk_hash = content_hash(chunk_js)
        chunk_file = f'pane-{pane}.{chunk_hash}.js'
        (DIST / chunk_file).write_text(chunk_js, encoding='utf-8')
        chunks[pane] = {
            'file': chunk_file,
            'modules': modules,
            'bytes': len(chunk_js.encode()),
        }
        chunk_outputs.append((chunk_file, chunk_js))

    # The chunk manifest is emitted as its own tiny script file rather than
    # inlined into the HTML. Under the enforced `script-src 'self'` an inline
    # <script> is refused outright, and adding a hash or nonce for it would
    # weaken a policy this review spent three phases tightening.
    manifest_js = (
        '/* generated by scripts/build_bundle.py */\n'
        'window.__CHUNK_MANIFEST__=' + json.dumps(
            {pane: c['file'] for pane, c in sorted(chunks.items())},
            separators=(',', ':')) + ';\n'
    )
    manifest_file = f'chunks.{content_hash(manifest_js)}.js'
    (DIST / manifest_file).write_text(manifest_js, encoding='utf-8')

    compressed = {}
    for name, text in ([(head_file, head_js), (body_file, body_js),
                        (manifest_file, manifest_js)]
                       + chunk_outputs):
        raw = text.encode('utf-8')
        gz = gzip.compress(raw, 9)
        (DIST / (name + '.gz')).write_bytes(gz)
        compressed[name] = {'raw': len(raw), 'gzip': len(gz)}
        try:
            import brotli  # optional; produces a further ~15% over gzip
        except ImportError:
            pass
        else:
            br = brotli.compress(raw, quality=11)
            (DIST / (name + '.br')).write_bytes(br)
            compressed[name]['brotli'] = len(br)

    manifest = {
        'head': head_file,
        'body': body_file,
        'minified': do_minify,
        'modules': len(head_names) + len(body_names),
        'head_modules': head_names,
        'body_modules': body_names,
        'raw_bytes': raw_bytes,
        'bundled_bytes': len(head_js.encode()) + len(body_js.encode()),
        'compressed': compressed,
        'chunks': chunks,
        'chunk_manifest': manifest_file,
        'lazy_modules': sorted(lazy_files),
        'lazy_bytes': sum(c['bytes'] for c in chunks.values()),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--no-minify', action='store_true',
                    help='concatenate only, keep comments (debugging)')
    ap.add_argument('--check', action='store_true',
                    help='exit non-zero if the committed bundle is stale')
    ap.add_argument('--refresh-split', action='store_true',
                    help='re-derive the code-splitting plan (needs node+acorn)')
    ap.add_argument('--no-split', action='store_true',
                    help='build one monolithic bundle, no per-pane chunks')
    args = ap.parse_args()

    if args.check:
        if not MANIFEST.exists():
            print('build_bundle: no bundle committed (run scripts/build_bundle.py)',
                  file=sys.stderr)
            return 1
        old = json.loads(MANIFEST.read_text(encoding='utf-8'))
        html = INDEX.read_text(encoding='utf-8')
        head_names, body_names = parse_index(html)
        do_minify = old.get('minified', True)

        # Lazy modules live in their own chunks, not the core bundle, so they
        # must be excluded before hashing -- otherwise the check reports STALE
        # against a perfectly current build.
        plan = load_split_plan()
        lazy_files = set(plan.get('lazyFiles', []))
        body_names = [n for n in body_names if n not in lazy_files]

        head_hash = content_hash(concat(head_names, do_minify=do_minify))
        body_hash = content_hash(concat(body_names, do_minify=do_minify))
        stale = (old.get('head') != f'head.{head_hash}.js'
                 or old.get('body') != f'app.{body_hash}.js')

        # Each pane chunk must match too, or an edited lazy module ships stale.
        for pane, modules in plan.get('lazy', {}).items():
            chunk_hash = content_hash(concat(modules, do_minify=do_minify))
            want = f'pane-{pane}.{chunk_hash}.js'
            if old.get('chunks', {}).get(pane, {}).get('file') != want:
                stale = True
                break
        if stale:
            print('build_bundle: STALE — frontend/js changed since the bundle '
                  'was built. Run: python3 scripts/build_bundle.py',
                  file=sys.stderr)
            return 1
        print('build_bundle: bundle is up to date')
        return 0

    if args.refresh_split:
        plan = load_split_plan(refresh=True)
        print(f"split plan refreshed: {len(plan['lazyFiles'])} modules "
              f"across {len(plan['lazy'])} panes "
              f"({plan['lazyBytes']:,} B deferred)")

    m = build(do_minify=not args.no_minify, split=not args.no_split)
    saved = 100 * (1 - m['bundled_bytes'] / m['raw_bytes'])
    print(f"built {m['modules']} modules -> 2 files")
    print(f"  {m['head']}")
    print(f"  {m['body']}")
    print(f"  {m['raw_bytes']:,} B raw -> {m['bundled_bytes']:,} B "
          f"({saved:.1f}% smaller, {m['modules']} requests -> 2)")
    for name in (m['head'], m['body']):
        sizes = m['compressed'][name]
        enc = ', '.join(f"{k} {v:,} B" for k, v in sizes.items() if k != 'raw')
        print(f"  {name}: {enc}")
    if m['chunks']:
        chunk_gz = sum(m['compressed'][c['file']]['gzip']
                       for c in m['chunks'].values())
        print(f"  + {len(m['chunks'])} lazy pane chunks: "
              f"{m['lazy_bytes']:,} B raw, {chunk_gz:,} B gzip "
              f"(deferred until the pane is opened)")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
