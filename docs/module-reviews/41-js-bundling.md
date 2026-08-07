# 41 — JavaScript bundling: 79 requests → 2

**Status:** shipped
**Batch:** 28
**Scope:** `frontend/index.html` script delivery, `scripts/build_bundle.py`,
`backend/services/asset_bundle.py`, `backend/app.py` (index route, static cache
policy), `tests/unit/test_112_js_bundle.py`

This was the largest item left open in `23-recommendations.md` and was
deliberately deferred through eight autonomous-hunt batches because it changes
the build story and the CSP posture. The user chose the shape of the change
before any code was written (see "Decisions taken" below).

---

## The finding

`frontend/index.html` loaded **79 separate `<script>` tags totalling 2,068,163
bytes**. Three problems compounded:

1. **79 round trips.** The browser opens a limited number of connections per
   origin, so these queue. The slowest single file previously measured 364 ms.
2. **No compression.** Verified live:

   ```
   $ curl -s -H 'Accept-Encoding: gzip' -o /dev/null -D- .../app.js | grep -i content-
   content-length: 1677104
   ```

   No `Content-Encoding` at all — the full 1.6 MB went over the wire.
3. **Nothing was cacheable.** `backend/app.py` applied
   `Cache-Control: no-cache, no-store, must-revalidate` to *every* path ending
   in `.js`. That is a reasonable default for hand-edited module files during
   development. It also meant the entire frontend was re-downloaded on **every
   single visit**, forever, for every user.

### Why this was not visible in earlier profiling

Batch 27's measurements were taken against `localhost`. Over loopback there is
no latency and effectively no connection limit, so 79 requests cost almost
nothing. Measured that way, bundling looks like a *regression* — and the first
run of this work did in fact show FCP going from 146 ms to 363 ms.

That result was real but irrelevant. Re-measuring with CDP network emulation
gave the honest picture.

---

## Measurements

Real Chromium, live server, cold cache, median of 3 runs per row, network
conditions applied via `Network.emulateNetworkConditions`. Harness:
`probe_net.py` (reproduced in this doc's history; not committed, it is a probe).

| Profile | | requests | DOMContentLoaded | JS transfer window | domInteractive |
|---|---|---|---|---|---|
| **localhost** | before | 79 | 535 ms | 317 ms | 510 ms |
| | after | 2 | **325 ms** | **32 ms** | **261 ms** |
| **wifi, 20 ms RTT** | before | 79 | 953 ms | 917 ms | 599 ms |
| | after | 2 | **429 ms** | **226 ms** | **378 ms** |
| **fast 3G, 40 ms RTT** | before | 79 | 2,518 ms | 2,458 ms | 1,770 ms |
| | after | 2 | **953 ms** | **825 ms** | **506 ms** |
| **slow, 150 ms RTT** | before | 79 | 13,667 ms | 13,474 ms | 9,968 ms |
| | after | 2 | **4,089 ms** | **3,838 ms** | **1,795 ms** |

The worst case improves most, which is the right shape: the users who were
suffering are the ones on slow links.

Sizes: **2,068,163 B raw → 1,683,612 B bundled → 391,336 B gzipped.**
`domInteractive` on the slow profile drops **9,968 ms → 1,795 ms** (5.6×),
because the app becomes responsive as soon as the single bundle lands rather
than after the 79th file.

Second and subsequent visits now cost **zero bytes of JS** instead of 2 MB.

---

## Decisions taken (user-confirmed before implementation)

| Question | Choice | Reasoning |
|---|---|---|
| Toolchain | **Zero-dependency Python** (`scripts/build_bundle.py`) | The platform installs with pip only. Adding Node as a hard build dependency would mean a fresh clone renders a broken UI until someone runs `npm install`. |
| Artifact | **Committed**, with a staleness guard | `python run.py` on a fresh clone gets the fast path with no extra step. `--check` fails CI if `frontend/js` changed without a rebuild. |
| Debug path | **`AGENTIC_JS_BUNDLE=0`** serves the 79 files | Bundled by default, unbundled on demand. |
| Minification | **Conservative** — comments and code indentation only | This codebase resolves handlers by string name off `window` (`00-handlers.js`, `data-act-click` attributes). Identifier renaming would be a live hazard for no proportionate gain, especially once gzip is doing the real work. |

---

## Design notes

**`index.html` stays the single source of truth for load order.** The build
parses the script tags out of the HTML rather than duplicating the list in a
config file, and the server rewrites those same tags at serve time. A list that
must be kept in sync by hand is a list that goes out of sync; here, adding one
`<script>` tag and rerunning the build keeps both modes correct automatically.

**Head and body get separate bundles.** `00-style-hydrate.js` must execute
before the body is parsed — under the enforced `style-src 'self'` the parser
refuses inline style attributes and the hydrator re-applies them (batch 22,
batch 27). Folding it into a deferred body bundle would render the whole UI
unstyled for a beat. `test_head_scripts_stay_in_the_head` pins this.

**Execution order is preserved exactly.** The browser runs non-`defer` scripts
in document order, then `defer` scripts in document order. The build emits
non-deferred modules first, then deferred ones, so relative order is unchanged.

**Concatenation was proven safe before it was relied on.** All 79 files parse
individually and as a single blob, in both sloppy and strict mode. There is
exactly one duplicated top-level `const` across files
(`CONNECTOR_CATEGORY_ICONS` in `50-mcp-gateway.js` and `51-connectors.js`) and
both are inside separate IIFEs, so they do not collide.

**Precompression instead of `GZipMiddleware`.** The obvious fix for the missing
compression is compressing middleware. That is the wrong tool here: this app
streams SSE from the chat endpoint, and middleware that buffers or reframes
streaming responses has broken it in this codebase before (batch 23, three
iterations). Because the bundles are static and content-hashed, they can be
compressed **once at build time at maximum level** and served as bytes. Faster,
and it leaves the request path for every other route completely untouched.

**Content-hashed names make caching safe.** `app.<hash>.js` can be
`immutable, max-age=31536000` because a code change produces a *different
filename* — a stale cache entry becomes unreachable rather than wrong. The
document itself stays `no-store` so the browser always learns the new hash.

---

## Two real bugs found in the minifier during development

Both were caught by comparing parse trees, and both are pinned by regression
tests that fail against the broken version.

### 1. Whitespace stripped inside template literals

The first implementation collapsed indentation line by line across the whole
file — including lines *inside* template literals. Nearly every UI module
renders markup with ``pane.innerHTML = `...` ``, so the minifier was rewriting
the application's own HTML:

```
A: "\n        <div style=\"font-weight:700;margin-bottom:6px\">"
B: "\n<div style=\"font-weight:700;margin-bottom:6px\">"
```

Most of that would have rendered identically. The damage would have surfaced
much later and much more confusingly, in `<pre>` blocks, whitespace-sensitive
CSS and copy-to-clipboard payloads. **54 of 79 files were affected.**

Fix: `tokenize()` replaces every literal with an opaque placeholder before the
whitespace pass, and `restore()` puts them back byte-for-byte.

### 2. A regex containing a quote, inside an interpolation

The second implementation scanned `${...}` with a brace counter that skipped
strings but not regexes. `frontend/js/22-integrations.js` contains:

```js
`#int-card-${JSON.stringify(id).replace(/"/g,'')} .btn-primary`
```

The `"` inside the regex read as the start of a string literal. The scanner ran
past the closing backtick and swallowed **~1,200 characters of live code** into
what it believed was one literal (span `8007–9302` instead of `8007–8070`).

Fix: `_scan_interpolation` recurses through the same string / regex / template
handling as top-level code, rather than counting braces.

---

## Mistakes made in the verification itself, and corrected

Worth recording, because the *oracle* was wrong twice before the code was:

- **First checker had an argv off-by-one** and reported all 79 files as
  failures with an ENOENT buried in the noise. The bundles had actually parsed
  fine.
- **Second checker was the same class of hand-written scanner as the thing it
  was checking** — not a trustworthy oracle. Replaced with real `acorn`.
- **Third checker compared acorn's UTF-16 code-unit offsets against Python's
  code-point offsets.** This codebase is full of emoji (surrogate pairs), so
  every file containing one reported a spurious 9-character drift. Confirmed
  precisely: `len(src[:7129].encode('utf-16-le'))//2 == 7138`, exactly acorn's
  number. Fixed by comparing **parse trees instead of offsets**, which removes
  the entire class of error — positions are ignored, meaning is compared.

`scripts/verify_bundle_ast.js` is the surviving oracle: it normalises away
`start`/`end`/`loc`/`range`/`raw` and structurally compares everything else,
including the exact value of every string, template chunk and regex.

**Result: 0 of 79 files differ semantically after minification.**

---

## Tests — `tests/unit/test_112_js_bundle.py` (96 tests)

Proven to fail before the fix, by reverting each change in turn:

| Reverted change | Result |
|---|---|
| Whitespace pass applied after literal restore (bug 1) | **56 failed**, 40 passed |
| Regex handling removed from `_scan_interpolation` (bug 2) | **3 failed** — including `22-integrations.js` by name |
| `/static/dist/` exemption from the no-store rule | **1 failed** |
| HTML rewrite disabled | **2 failed** |

The AST-equivalence test is parametrised per module, so a future edit that
breaks one file names that file rather than reporting a vague total.

`test_minifier_actually_shrinks_the_code` exists because a pass-through
minifier that changed nothing would satisfy every other test in the file.

Two tests deliberately do **not** go through `TestClient`:
`test_bundle_lookup_rejects_anything_but_a_plain_filename` asserts against the
function directly, because `httpx` resolves `../` in the URL before sending, so
`/static/dist/../index.html` arrives as `/static/index.html` and never reaches
the handler. Verified against a live server with `curl` (which sends the raw
path): **404**. Testing it through the client would have proved nothing.

The AST tests skip cleanly (exit 2, distinct from a real failure) when `acorn`
is not installed, so the suite does not become Node-dependent.

---

## Follow-ups not taken

- **Brotli** is supported by the build (`~15%` better than gzip) but
  `brotli` is not in `requirements.txt`, so no `.br` files are produced today.
  Adding the dependency is a one-line change if desired.
- **Route-level code splitting** — loading only the modules a workstation needs
  — is the next tier of win, but it requires a real dependency graph across 79
  files that currently communicate through `window` globals. That is a
  refactor, not a build change, and should be its own decision.
- **The 13 MB `frontend/vendor/` tree** is untouched. Those files are loaded on
  demand (Monaco, three.js) and are already cached independently.
