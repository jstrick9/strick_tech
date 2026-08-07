"""Serve the bundled frontend JavaScript in place of 79 separate files.

Background
----------
`frontend/index.html` is the single source of truth for which JS modules load
and in what order. In development that is exactly what you want: 79 readable
`<script>` tags you can breakpoint individually. In normal use it is 79 HTTP
requests, ~2.0 MB, and the page cannot finish booting until the last one
lands.

`scripts/build_bundle.py` concatenates those modules into two files (a small
head bundle that must run before body parsing, and one body bundle) and writes
`frontend/dist/manifest.json`. This module rewrites the served HTML to point at
those two files instead.

Why rewrite the HTML at serve time rather than committing a bundled
`index.html`
--------------------------------------------------------------------------
Because then the repository would contain two copies of the load order that
must be kept in sync by hand, and one of them would eventually drift. Keeping
`index.html` authoritative means a developer adds one `<script>` tag, reruns
the build, and both modes stay correct. The rewrite is a single regex over a
string that is then cached in memory, so it costs nothing per request.

Opting out
----------
Set ``AGENTIC_JS_BUNDLE=0`` to serve the individual module files. Use this
when you need to debug a specific module with unmangled line numbers, or when
you have edited `frontend/js/*.js` and do not want to rerun the build on every
change.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

from fastapi import Response
from fastapi.responses import FileResponse

# Matches only the local application modules. Vendored libraries under
# /static/vendor/ are deliberately left alone: they are large, change almost
# never, and are already cached independently by the browser.
_SCRIPT_RE = re.compile(
    r'[ \t]*<script\s+src="/static/js/(?P<src>[^"]+)"[^>]*></script>\n?'
)

_lock = threading.Lock()
_cache: dict[str, tuple[float, str]] = {}


def bundle_enabled() -> bool:
    """True unless the operator explicitly asked for unbundled modules."""
    return os.environ.get('AGENTIC_JS_BUNDLE', '1').strip().lower() not in (
        '0', 'false', 'no', 'off'
    )


def load_manifest(frontend_dir: Path) -> dict | None:
    """Read `frontend/dist/manifest.json`, or None if no bundle was built.

    Returning None rather than raising is deliberate: a checkout with no
    bundle must still serve a working (if slower) application. A missing
    build artifact is a performance regression, not an outage.
    """
    path = frontend_dir / 'dist' / 'manifest.json'
    try:
        manifest = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    head = manifest.get('head')
    body = manifest.get('body')
    if not head or not body:
        return None
    if not (frontend_dir / 'dist' / head).exists():
        return None
    if not (frontend_dir / 'dist' / body).exists():
        return None
    return manifest


def rewrite_html(html: str, manifest: dict) -> str:
    """Replace the individual module tags with the two bundle tags.

    Placement matters and is preserved exactly:

    * The head bundle replaces the first head script in situ, because
      `00-style-hydrate.js` must execute before the body is parsed -- under
      the enforced `style-src` the parser refuses inline style attributes,
      and the hydrator re-applies them.
    * The body bundle replaces the first body script and carries `defer`, so
      it runs after the document is parsed, exactly as the deferred modules
      did. Non-deferred body modules were already ordered ahead of deferred
      ones by the build, so their relative order is unchanged; the only
      difference is that they now also wait for parsing, which is safe
      because every one of them either waits for DOMContentLoaded or only
      defines functions.
    """
    head_tag = (
        f'<script src="/static/dist/{manifest["head"]}"></script>\n'
    )

    # The chunk manifest must be defined before the body bundle runs, because
    # 00-chunk-loader.js reads window.__CHUNK_MANIFEST__ as it installs its
    # registry wrappers. It is a separate file rather than an inline script:
    # under the enforced `script-src 'self'` an inline <script> is refused, and
    # loosening that policy for it would undo work from CSP phases 1-3.
    chunk_manifest = manifest.get('chunk_manifest')
    body_tag = ''
    if chunk_manifest:
        body_tag += f'<script src="/static/dist/{chunk_manifest}" defer></script>\n'
    body_tag += (
        f'<script src="/static/dist/{manifest["body"]}" defer></script>\n'
    )

    body_start = html.find('<body')
    emitted_head = False
    emitted_body = False

    def repl(match: re.Match) -> str:
        nonlocal emitted_head, emitted_body
        in_head = match.start() < body_start
        if in_head:
            if emitted_head:
                return ''
            emitted_head = True
            return head_tag
        if emitted_body:
            return ''
        emitted_body = True
        return body_tag

    return _SCRIPT_RE.sub(repl, html)


def index_html(frontend_dir: Path) -> str:
    """Return the HTML to serve for `/`, bundled if a bundle is available.

    The result is cached against the mtime of `index.html` so that editing
    the page during development is picked up immediately without a restart,
    while steady-state requests do no file I/O beyond a stat.
    """
    path = frontend_dir / 'index.html'
    mtime = path.stat().st_mtime

    key = f'{path}:{bundle_enabled()}'
    with _lock:
        cached = _cache.get(key)
        if cached and cached[0] == mtime:
            return cached[1]

    html = path.read_text(encoding='utf-8')
    if bundle_enabled():
        manifest = load_manifest(frontend_dir)
        if manifest:
            html = rewrite_html(html, manifest)

    with _lock:
        _cache[key] = (mtime, html)
    return html


def clear_cache() -> None:
    """Drop the memoised HTML. Used by tests that toggle the env flag."""
    with _lock:
        _cache.clear()


# ──────────────────────────────────────────────────────────────────────────
#  Precompressed delivery
# ──────────────────────────────────────────────────────────────────────────
#
# The bundles were going out uncompressed -- 1.6 MB on the wire for a file
# that gzips to about 390 KB. The usual answer, GZipMiddleware, is a poor fit
# here: this application streams SSE from the chat endpoint, and middleware
# that buffers or reframes those responses has broken streaming in this
# codebase before. Because the bundles are static and content-hashed, they
# can be compressed once at build time (at maximum level) and served
# directly, which is faster and leaves the request path for every other route
# completely untouched.

_ENCODINGS = (('br', '.br'), ('gzip', '.gz'))


def _acceptable_encodings(accept_encoding: str) -> list[str]:
    """Parse an Accept-Encoding header into encodings the client will accept.

    Returned in the client's order of preference (highest q first), with
    anything explicitly refused removed.

    A plain substring test is not good enough here, and the difference is not
    theoretical: `Accept-Encoding: br;q=0, gzip` means "I do NOT want brotli,
    send me gzip". A substring check sees "br" in the header and serves a
    brotli body the client just told us it cannot decode -- which arrives as
    binary garbage rather than a clean failure. RFC 9110 also defines `*` and
    lets a q-value order the preferences, so both are honoured.
    """
    prefs: dict[str, float] = {}
    for part in (accept_encoding or '').split(','):
        part = part.strip()
        if not part:
            continue
        token, _, params = part.partition(';')
        token = token.strip().lower()
        quality = 1.0
        for param in params.split(';'):
            key, _, value = param.partition('=')
            if key.strip().lower() == 'q':
                try:
                    quality = float(value.strip())
                except ValueError:
                    quality = 0.0
        prefs[token] = quality

    star = prefs.get('*')
    accepted = []
    for token, _suffix in _ENCODINGS:
        quality = prefs.get(token, star)
        if quality is not None and quality > 0:
            accepted.append((quality, token))

    # Sort by client preference, breaking ties in our own order (brotli first,
    # since it is materially smaller).
    order = {token: i for i, (token, _) in enumerate(_ENCODINGS)}
    accepted.sort(key=lambda item: (-item[0], order[item[1]]))
    return [token for _q, token in accepted]


def bundle_response(frontend_dir: Path, filename: str, accept_encoding: str):
    """Serve a built bundle, preferring a precompressed variant.

    Returns None if the file is not a built artifact, so the caller can fall
    through to the normal static handler.
    """
    # Containment: only ever serve a plain filename from dist/, never a path.
    if '/' in filename or '\\' in filename or filename.startswith('.'):
        return None
    base = (frontend_dir / 'dist' / filename)
    if not base.is_file():
        return None

    accept = (accept_encoding or '').lower()
    headers = {
        # Content-hashed filenames can be cached indefinitely: a code change
        # produces a new name, so a stale cache entry is unreachable rather
        # than wrong.
        'Cache-Control': 'public, max-age=31536000, immutable',
        'Vary': 'Accept-Encoding',
    }

    suffixes = dict(_ENCODINGS)
    for token in _acceptable_encodings(accept):
        variant = base.with_name(base.name + suffixes[token])
        if not variant.is_file():
            continue
        return Response(
            content=variant.read_bytes(),
            media_type='application/javascript',
            headers={**headers, 'Content-Encoding': token},
        )

    return FileResponse(base, media_type='application/javascript',
                        headers=headers)
