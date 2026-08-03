# Module 10 — Image Generator

**Commit:** `046e0ad` · **Suite:** 2494 passed / 17 skipped / 0 failed · ruff clean
**Surface:** `backend/routers/imagegen.py` (626 lines, 12 endpoints) ·
`frontend/js/15-image-generation.js` (506 lines)

Every finding below was reproduced against a live server before the fix and
re-verified after.

---

## 🔴 1. The feature had never generated a single image

This is the headline. `/api/imagegen/generate` posted to
`https://openrouter.ai/api/v1/images/generations` with the model
`black-forest-labs/FLUX.1-schnell:free`. **Neither exists.**

| Assumption in the code | Reality (verified live) |
|---|---|
| `POST /images/generations` | OpenRouter generates images via `POST /chat/completions` with `modalities: ['image','text']`, returning base64 data URLs in `choices[0].message.images` |
| `black-forest-labs/FLUX.1-schnell:free` | Not in the catalogue. **0 of 338** model ids match flux, dall-e or sdxl |
| Four models offered by `/models` | All four fictional — including the default |

So every call failed. And this swallowed it:

```python
except Exception as e:
    log.error('Image gen error: %s', e)
# …falls through to…
return {'ok': True, 'type': 'svg_placeholder', ...}
```

**The module reported success 100% of the time while never once producing an
image.** A user would see a grey placeholder captioned "Set OPENROUTER_API_KEY
to generate" — even with a valid key — and reasonably conclude their key was
wrong.

This is the fourth module with the fabricated-success pattern, after Chat,
Supervisor and Browser Agent. The difference here is what it concealed: not a
degraded path, but a feature that had never worked at all.

### The fix

Real contract, live model discovery (filtered on
`architecture.output_modalities`), and a fallback set I verified exists:

```
✓ google/gemini-2.5-flash-image      ✓ openai/gpt-5-image-mini
✓ google/gemini-3-pro-image          ✓ openai/gpt-5-image
```

Proven end-to-end against a mocked OpenRouter — a valid PNG is decoded and
written to disk, `image_config.aspect_ratio` derived from the requested size.
Failures now map by cause: **401** bad key, **402** no credit, **429** rate
limited, **502** upstream/no-image-returned, **504** timeout.

A placeholder is returned **only** when no key is configured, and is tagged
`ok: false, placeholder: true` so no caller can mistake it for a delivered
image.

---

## 🔴 2 & 3. Two stored XSS vectors

### Via the generated placeholder

The prompt was interpolated into the placeholder SVG unescaped. With `save_to`
the file landed in the gallery and was served **from the app's own origin** as
`image/svg+xml`, under a CSP that allows `'unsafe-inline'`:

```
prompt: </text><script>alert(document.domain)</script><text>
→ GET /preview/assets/images/xsstest.svg   →  live <script> tag
```

### Via upload

Uploads were validated on file extension alone. An SVG containing `<script>`
was stored and served verbatim.

### The fix

SVG is not an inert image format — it's XML that can carry script, event
handlers and external references. Added `sanitize_svg()` (strips
`script`/`foreignObject`/`iframe`/`embed`/`object`/`animate`/`set`/`handler`,
`on*` handlers, and `javascript:`/`vbscript:`/`data:text/html` URIs), applied
to everything written to the gallery, plus escaping of the placeholder text.

Defence in depth at the serving layer: `/preview/*.svg` now gets
`Content-Security-Policy: default-src 'none'; sandbox`.

Two details worth noting:

- **Legitimate SVG is byte-identical after sanitisation** — there's a test.
- My first regex dropped `href="javascript:…"` but left the closing quote,
  producing `<a ">x</a>`. Sanitising into malformed XML is its own bug; the
  pattern now consumes the whole attribute, and a test pins the exact output.

---

## 🔴 4. Path traversal — arbitrary file write outside the sandbox

```python
target = (PREVIEW_DIR / relative.lstrip('/')).resolve()
if str(target).startswith(str(PREVIEW_DIR.resolve())):   # ← string prefix
```

That's a prefix test on a *string*, not on path components. Verified live:

```
save_to = '../preview_ESCAPED/pwned.svg'   →  wrote to <root>/preview_ESCAPED/
```

`'<root>/preview_ESCAPED/pwned.svg'` genuinely does start with
`'<root>/preview'`. Classic sibling-directory bypass — `..` filtering wouldn't
have caught it either, because the resolved path contains no `..`. Now uses
`Path.relative_to()`, which compares components.

---

## 🔴 5. HTML attribute injection in `/inject-into-code`

The placeholder description came straight from the user's file into `alt=""`
unescaped:

```html
<!-- IMAGE: cat" onerror="alert(1) -->
→ <img src="…" alt="cat" onerror="alert(1)" style="…">
```

A live event handler written into the user's own source file. Both attributes
are escaped now.

---

## 🔴 6. Cross-module: workspace switching broke the gallery permanently

`ASSETS_DIR` was `mkdir`'d once at import time.
`POST /api/workspaces/{id}/activate` does `shutil.rmtree(PREVIEW_DIR)` to swap
in another workspace's files — taking `assets/images` with it. After **any**
workspace switch:

```
GET  /api/imagegen/gallery         → 200 {"images": [], "count": 0}   (silent)
POST /api/imagegen/gallery/upload  → 500 Internal Server Error        (forever)
```

Worth recording how this surfaced: a test failed only when run *after*
`test_27_system_workspaces_analytics.py`. I went looking for test pollution and
found a real bug instead — the suite had been reproducing a genuine user
scenario by accident. Resolved lazily via `_assets_dir()`.

---

## 🟡 Also fixed

| Issue | Detail |
|---|---|
| **Upload content unverified** | An HTML/script payload uploaded as `fake.png` was stored and served as `image/png`. Now magic-byte sniffed per format. |
| **Size limit after the read** | The 10 MB cap was checked *after* `await file.read()` — an oversized upload was fully buffered into memory before rejection. Now 64 KB chunks, aborting at the cap. |
| **Silent overwrite** | Same-named uploads clobbered existing gallery images. |
| **`count="abc"` → 500** | Unguarded `int()`. Now 400. |
| **Serial variations** | Six image calls at 10–20s each timed out the browser. Now `asyncio.gather`, and a partial failure returns the successes rather than discarding all six. |
| **~12 endpoints 200-on-failure** | Mapped to 400/403/404/413/415/422/502. |
| **Figma "import" overclaimed** | It never contacts Figma — it reads the URL slug and asks an LLM to invent a matching design. Now labelled `approximation: true` with an honest note. |
| **Frontend swallowed reasons** | Showed bare status numbers; now surfaces the server's explanation, labels placeholders as "no image was generated", adds a model picker, and stops rendering failed variations as empty tiles. |

---

## Verified working (no change needed)

- The frontend escapes all rendered text and URLs correctly — one of the
  better-behaved panes in that respect.
- Gallery delete already blocked `/`, `\` and `..` in filenames.
- The style catalogue and prompt-enhancement goal contexts are sensible and
  work as intended.

---

## Cross-module impact

| Module | Impact |
|---|---|
| **Workspaces** | `activate` rmtree's `PREVIEW_DIR`; the gallery had to stop caching that path |
| **Studio / Preview** | Serves the gallery; now sends a hardened CSP for SVG |
| **Composer / Builder** | `inject-into-code` writes into preview files they own |
| **Settings → Connect AI** | Now the single place a missing/invalid key is explained |
| **FinOps** | Image generation still doesn't record spend — see below |

---

## Tests

`tests/unit/test_60_imagegen_module_review.py` — **58 contracts**, including six
SVG sanitiser payload families, five traversal payloads, and an end-to-end
generation test against a mocked OpenRouter.

**Proven to catch the bugs: 47 of 58 fail against the pre-fix code.**

One methodological note: the assertions compare against a comment- and
docstring-stripped copy of the source. The fixes are documented in comments that
necessarily quote the old broken values (`/images/generations`, `FLUX.1-schnell`),
so a naive substring search matches the *explanation* rather than the code — three
tests passed spuriously until I noticed.

---

## Recommended follow-ups

1. **Image generation records no cost.** Every other spend source is being wired
   into the ledger; image models are expensive per call and should preflight
   against the budget guardrail like Chat does.
2. **The gallery is global, not per-workspace.** Now that the workspace-switch
   crash is fixed, the remaining question is design: images survive in
   `preview/assets/images` but are wiped by a switch. Either make the gallery
   workspace-scoped or move it outside `preview/` so it genuinely persists.
   Right now it's neither.
3. **`inpaint` doesn't inpaint.** It appends the mask description to a text
   prompt and generates a brand-new image — no mask, no source image. Either
   wire real image-to-image (the models support `image_url` inputs) or rename it.
4. **No generation history.** Prompts and results aren't recorded, so there's no
   way to revisit or reproduce a generation. Every comparable tool has this.
