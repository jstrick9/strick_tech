# 60 — Inline-style migration, and two bugs in the tool that does it

**Task:** cut the CSP `style-src` console noise by removing the attributes that
cause it. 832 static inline `style` attributes → **430** (48% reduction, 402
attributes migrated into 84 utility classes).

**Instrument:** `scripts/audit/computed_style_diff.py` (new) ·
**Tests:** `tests/unit/test_106_inline_style_migration.py` (4 → 7).

---

## I nearly rebuilt something that already existed

`scripts/migrate_inline_styles.py` was already committed by an earlier batch,
complete with a guard I would not have thought of: **`display:none` is state,
not styling.**

```js
isOpen = content.style.display === 'none';   // READ
```

`element.style` exposes only the inline attribute, never a class — so migrating
`display:none` made that read always return `''`, the toggle concluded the group
was already open, and the collapsed sidebar groups stopped expanding. That
shipped once and was caught by a computed-style baseline.

I started writing a second tool with exactly the naive approach that caused it.
Checking the repo first would have been faster.

---

## Bug 1 in the existing tool: it was not idempotent

The generated CSS block is rebuilt from the attributes that are inline **right
now**. On a second run the attributes the first run converted are gone from the
source, so their classes are not regenerated — and rewriting the block deletes
them.

Measured by running it twice: **21 classes referenced in the JS and defined
nowhere.**

The tool was therefore safe to run exactly once, and nothing said so. It now
carries forward every still-referenced class — and writes them **inside** the
`END` marker, because the first version of that fix appended past it, which
would have orphaned them again on the next run.

---

## Bug 2: a lifted declaration can lose a fight the attribute always won

This is the one that matters.

An inline `style` attribute beats **every** selector in the cascade. A flat
`.u-xxxxxxxx` (0-0-1-0) does not:

```
<h2 style="margin:0 0 4px;font-size:20px;font-weight:900">   →  .u-89c33dcc
.section-head h2 { font-size: 17px }        (0-0-1-1)  ← wins
```

Measured live in Chromium: the heading rendered at **17px instead of 24px**,
both rules matching, the utility losing. The generated block's own comment
claimed "the computed result is identical to the attribute it replaces". It was
not.

Selectors are now **doubled** (`.u-x.u-x`, 0-0-2-0), which restores the "beats
ordinary component CSS" property — deliberately **not** `!important`, which
would also beat legitimate state rules like a `.is-hidden` toggle or `:hover`.

---

## The verification harness had to be fixed before it could be trusted

`computed_style_diff.py` snapshots every element's computed style across all 68
panes (23,000+ elements) and compares two runs property by property.

Its first verdict was **25 differing properties**. Then the control run — the
**unchanged app against its own baseline** — also reported 25, at different
paths each time.

Several panes render asynchronously and reorder nodes after the settle window,
so a structural path addresses a different element on the second run. The probe
was measuring its own timing.

It now captures **twice** against the same build and subtracts anything that
differs between those two captures, so app-side render noise is excluded by
construction rather than by a hand-maintained flaky list. `--selftest` reports
the noise floor on demand. Current floor: ~379 properties.

**A probe that cannot reproduce its own result is not evidence.**

---

## Final verdict: zero real regressions

After noise subtraction, 5 properties differed — all in the System Monitor:

```
color: 'rgb(242,101,101)' -> 'rgb(234,179,8)'      # red → amber
```

That is `cpu_pct > 80 ? danger : cpu_pct > 50 ? warning` — **live CPU load
crossing a threshold between runs**, not a styling change. Confirmed in source.

---

## Verification

| Check | Result |
|---|---|
| Static inline attributes | 832 → **430** |
| Orphaned utility classes | **0** |
| Computed-style diff vs pre-migration | **0 real** (5 live-metric, 379 noise) |
| Flatten the selectors again | `test_generated_classes_outrank_ordinary_component_css` fails |
| Full suite | 3,377 unit (2 skipped) + 655 (10 skipped), 0 failures |

A twelfth assertion-matched-its-own-comment: the `!important` test matched the
block header explaining why `!important` was rejected. Comments are now
stripped before asserting.
