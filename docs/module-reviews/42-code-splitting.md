# 42 — Brotli, and per-pane code splitting

**Status:** shipped
**Batch:** 29
**Scope:** `requirements.txt` (Brotli), `backend/services/asset_bundle.py`
(q-value negotiation), `scripts/analyse_split.js`, `scripts/split-plan.json`,
`scripts/build_bundle.py`, `frontend/js/00-chunk-loader.js`,
`tests/unit/test_112_js_bundle.py`, `tests/unit/test_113_code_splitting.py`

Both follow-ups flagged at the end of `41-js-bundling.md`, taken together.

---

## Part 1 — Brotli

`Brotli==1.2.0` added to `requirements.txt`, used at **build time only** — it
never appears in the request path. The build degrades to gzip-only if it is
missing, so a constrained install can drop it.

| | raw | gzip | brotli |
|---|---|---|---|
| `app.<hash>.js` | 1,677,104 B | 391,336 B | **287,705 B** |

**26.5% smaller than gzip**, on top of everything in batch 28.

### A real bug found while verifying it

The first implementation picked an encoding with `if token not in accept`.
Probing the live server across eight `Accept-Encoding` headers surfaced this:

```
AE=br;q=0, gzip   ->  content-encoding: br     ← WRONG
```

`br;q=0` means *"do not send me brotli"*. A substring check sees `br` in the
header and ships a brotli body the client just told us it cannot decode —
which arrives as binary garbage rather than a clean failure.

Replaced with `_acceptable_encodings()`, which parses q-values properly and
honours `*`. All eight cases verified against the live server:

| `Accept-Encoding` | served |
|---|---|
| `br` | br |
| `gzip, deflate, br` | br |
| `gzip` | gzip |
| `br;q=0, gzip` | **gzip** |
| `*` | br |
| `gzip;q=1.0, br;q=0.5` | **gzip** |
| `identity` | uncompressed |
| *(absent)* | uncompressed |

Real Chromium confirmed taking `br` for both bundles, app boots clean.

---

## Part 2 — Per-pane code splitting

18 modules (447,887 B) belong to exactly one pane each and are referenced by
nothing during boot. They are now fetched when that pane is first opened, and
prefetched during browser idle time.

### Measurements (real Chromium, CDP network emulation, median of 3)

| Profile | | DOMContentLoaded | domInteractive |
|---|---|---|---|
| 20 ms RTT | bundled (batch 28) | 429 ms | 378 ms |
| | **+ split** | **411 ms** | **356 ms** |
| 40 ms RTT | bundled | 953 ms | 506 ms |
| | **+ split** | **793 ms** | **501 ms** |
| 150 ms RTT | bundled | 4,089 ms | 1,795 ms |
| | **+ split** | **3,239 ms** | **1,796 ms** |

**Critical path before DOMContentLoaded: 223 KB** (was 288 KB brotli after
batch 28; 1.6 MB uncompressed before any of this work). Idle prefetch then
warms the remaining chunks to 323 KB total, so the first click on any pane is
normally instant.

Cumulative across batches 28 + 29, on the 150 ms profile:
**DOMContentLoaded 13,667 ms → 3,239 ms (4.2×)**, and
**domInteractive 9,968 ms → 1,796 ms (5.5×)**.

---

## How the split is decided

The plan is **derived from the source on every build**, never hand-written.
`scripts/analyse_split.js` parses all 79 modules with acorn and emits
`scripts/split-plan.json`; a test fails if the committed plan is stale.

A module may be deferred only if **both** hold:

1. **Exactly one pane needs it**, resolved by mapping each
   `MASTER_PANE_REGISTRY` entry to the file providing that renderer.
2. **Nothing depends on it before its pane opens** — see the three rules
   below, each of which was learned the hard way.

Node is required only to *change* the split, never to build or run the app —
the same arrangement as the bundle artifact itself.

### Where the loader hooks in

Three separate call sites invoke pane renderers: `nav()` in `01-app-core.js`,
`showWorkstationTab()` in `00-workstations.js`, and a third in
`14-prompt-library.js`. Patching all three would be the **"second door"**
pattern this review has hit six times.

So `00-chunk-loader.js` wraps `MASTER_PANE_REGISTRY` itself, which all three
go through. No caller needs to know it exists, and a call site added tomorrow
is covered by construction. This is only safe because the registry already
resolved renderers lazily (`typeof window.X === 'function' && window.X()`) —
it never captured a function reference.

The chunk manifest ships as its own hashed `.js` file rather than an inline
`<script>`, because under the enforced `script-src 'self'` an inline script is
refused, and adding a hash or nonce would undo CSP phases 1–3.

---

## Three analysis bugs, each caught in a live browser

The split shipped broken **three times** before it was right. Every one was
found by walking all 68 panes in real Chromium and diffing against a no-split
baseline — not by reasoning about the code.

### 1. Load-time snapshots (29 modules → blocked 12)

`01-app-core.js` builds, during top-level execution:

```js
const wrappedRenders = {
  dashboard: typeof renderDashboard === 'function' ? renderDashboard : null,
  ...
};
```

That captures the reference while the page boots. Defer `36-dashboard.js` and
the entry is `null` — the pane dies **with no error at all**.

### 2. Unguarded bare calls inside function bodies (29 → 21)

A reference inside a function is normally safe to defer. But `nav()` is
wrapped several times over, and each layer calls renderers *directly*:

```js
nav = function(pane) {
  _origNav(pane);
  if (pane === 'mcp')   renderMCP();     // bare identifier
  if (pane === 'loops') renderLoops();
};
```

A bare identifier that was never declared throws `ReferenceError` — unlike
`window.renderMCP`, which is merely `undefined`. Live evidence:

```
ReferenceError: renderMCP is not defined
ReferenceError: renderLoops is not defined
ReferenceError: renderIntegrations is not defined
ReferenceError: renderImageGen is not defined
```

### 3. Guards are per call site, not per file (21 → 18)

The fix for (2) collected every `typeof x` in a file into one set and treated
`x` as guarded everywhere. `01-app-core.js` guards `renderMCP` at line 3070:

```js
if (typeof renderMCP === 'function') await renderMCP();
```

…and calls it bare at line 2434. The file-wide set said "safe", the module was
deferred, and the MCP pane threw. **A guard only protects the statement it
encloses.**

Final: **18 modules, 447,887 B, 24.3% of the frontend.** Fewer than the 29 the
first analysis claimed — because 11 of those would have broken panes.

---

## The pure-Python analyzer that was written and deleted

To keep the build Node-free, this analysis was first written in Python using
regexes. It disagreed with the parser on **11 files**, and disagreed in the
dangerous direction: it declared modules deferrable that `01-app-core.js`
snapshots during boot.

The cause was its function-body stripper silently eating real top-level code —
`const wrappedRenders = {...}` vanished from the "top-level" text entirely.
Approximating a JavaScript parser with regular expressions cannot be made
trustworthy enough to serve as a correctness gate, and the conservative
version that *would* have been safe deferred roughly half as much.

Deleted rather than shipped. The user chose the parser-derived plan.

---

## Tests — `test_113_code_splitting.py` (20) + `test_112` updates (106)

Each analysis rule is proven to fail without its fix:

| Reverted rule | Result |
|---|---|
| Guards evaluated per file instead of per call site | **2 failed** |
| Unguarded-bare-call detection removed | **2 failed** |
| Load-time reference detection removed | **1 failed** |

### A test that proved nothing, and was replaced

The first version of `test_modules_snapshotted_during_boot_are_not_deferred`
listed the modules named in `wrappedRenders` and asserted they were eager.
**It passed against a build with the load-time check removed** — because the
bare-call rule happens to catch those same modules for an unrelated reason.

Replaced with a synthetic fixture that isolates load-time capture on its own:
a module referenced *only* from a top-level expression, never called bare.
That version fails correctly when the rule is removed.

`test_a_purely_guarded_module_is_still_deferrable` is its mirror: without it,
"treat every bare name as blocking" would pass every other test while
deferring nothing at all.

### Other honesty notes

- `test_no_accept_encoding_header_means_uncompressed` asserts on the parser,
  not through `TestClient`: **httpx injects `Accept-Encoding: gzip, deflate,
  br` into every request it builds**, so a test that "omitted" the header
  would silently have been testing the brotli path.
- `_analyse_fixture` writes its probe script inside the repo, not `tmp_path`,
  because Node resolves `require('acorn')` by walking up from the *script's*
  directory.
- The `--check` staleness guard was extended to cover chunks; verified it
  catches an edited lazy module. Note it correctly ignores an added comment,
  since the minifier strips those — a code change is what matters.

---

## Verification

- **Full suite: 3,137 passed / 2 skipped (unit) + 1,044 passed / 17 skipped
  = 4,181 passing, 0 failing.**
- **All 68 panes walked in real Chromium: byte-for-byte identical to the
  no-split baseline** — same 16 pre-existing errors (`renderSystem`,
  `renderControlTower`, `renderWebhooks`, `renderTestGen` all fail the same
  way with splitting *disabled*), same one thin pane (`deploy`). Zero new
  failures.
- `ruff`, `lint_inline_handlers`, `lint_globals` all clean.

---

## Not taken

- **The 4 pre-existing pane errors** (`Cannot set properties of null`) are
  real bugs, unrelated to bundling, and were confirmed present before this
  work. Worth their own batch.
- **The 11 blocked modules (~266 KB)** could be freed by changing
  `wrappedRenders` to resolve renderers at call time and by routing the bare
  `nav()` calls through the registry. That is a refactor of `01-app-core.js`,
  not a build change, and would roughly double the deferred bytes.
