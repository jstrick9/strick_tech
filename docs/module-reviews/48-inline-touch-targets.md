# 48 — The last touch targets, and an inert rule

**Status:** shipped
**Batch:** 35
**Scope:** `frontend/styles-redesign.css`,
`tests/unit/test_119_inline_touch_targets.py`

Taken on as "the 6 remaining touch targets (checkboxes at 24×24) — needs a
design call on visual weight in dense tables". Measuring first changed both
halves of that description.

---

## Correction 1: the worst target was not a checkbox

Auditing all 68 panes at 390 px, the smallest interactive element in the
product is a **6×12 px `🪪` link** on the A2A pane, 15 instances — roughly
**1/27th** of the recommended 44×44 area. Also an 8×17 px status toggle on MCP
Gateway and two 386×21 px export links.

### Why batch 34's rule did not catch them

Batch 34 added `min-width: 44px; min-height: 44px` to every control under
`@media (pointer: coarse)`. That rule **was applied to these elements and did
nothing**, because:

> `min-width` and `min-height` have no effect on a `display: inline` box.

Verified directly — the link computed `min-width: 44px` while measuring
6×12 px. **22 interactive elements across the app were affected.** This is a
real gap in the previous batch, not a leftover from it.

### The fix

```css
@media (pointer: coarse) {
  a[href], [role="button"] { display: inline-block; }   /* makes the min take effect */

  p a[href], li a[href], .prose a[href], td a[href],
  a[href].inline-link { min-width: 0; min-height: 0; display: inline; }
}
```

Prose links stay `inline` deliberately: a link inside a sentence must keep
wrapping with the text, and a 44 px block dropped into a paragraph would break
the line box. Source order matters — the exclusion must come **after** the
promotion, since both have equal specificity.

Measured after: the A2A link is **103×44** on touch, **103×21** on desktop.

---

## Correction 2: the checkboxes are not in dense tables

My earlier note said they sat in dense tables and needed a design decision
about visual weight. Measuring found `inTable: False` for all of them — they
are in `<label>` wrappers (Swarm) and list rows (MCP Gateway, Replay).

That makes the design call easy, and it is not "how big should a checkbox be":

**Keep the box at 24×24; make the row the target.** A `<label>` wrapping a
checkbox is already clickable in HTML — the browser forwards the click — so a
44 px `min-height` on the row gives a comfortable tap area with the control's
visual weight completely unchanged.

| | box | row |
|---|---|---|
| Swarm (touch) | 24×24 | **137×44** |
| Replay run card (touch) | 24×24 | **174×44** |
| Swarm (desktop) | 13×13 | 32 px |

24×24 is already ~3× the platform default and satisfies **WCAG 2.5.8 (AA)**.
Inflating to 44×44 would dominate rows next to 13 px body text for no gain,
since the row is the thing being tapped.

---

## Results

| | before | after |
|---|---|---|
| Distinct undersized types (68 panes) | 8 | **3** |
| Smallest target | 6×12 px | **24×24 px** |
| Page horizontal overflow | 0 | **0** |
| Panes with wide children | 30 | **27** |

The 3 remaining are the deliberate 24×24 checkboxes, each inside a 44 px row.

**Desktop verified inert:** `matchMedia('(pointer: coarse)')` is `false` at
1440 px; the A2A link is 21 px tall and the Swarm checkbox 13 px, exactly as
before.

---

## A resilience detail worth recording

`:has()` is kept in **its own rule**, not grouped with `.prb-policy-item` /
`.ttd-run-card-top`:

```css
.prb-policy-item, .ttd-run-card-top { min-height: 44px; }
label:has(> input[type="checkbox"]) { min-height: 44px; }   /* separate */
```

A CSS selector list is parsed as a unit: if any selector in it is unsupported,
the browser discards the **entire rule**. Grouping them would silently drop
the class-based row sizing too on an engine without `:has()`. Isolated, such a
browser loses only this one enhancement.

---

## Two tests of mine that proved nothing, and were fixed

Both passed against deliberately broken CSS on the first attempt.

**`test_has_selector_is_isolated_in_its_own_rule`** sliced *forward* from
`:has()` to the next `}`. A class selector listed **before** `:has()` in the
same list was therefore invisible to it — so the test passed against exactly
the grouping it existed to forbid. Now slices backwards to the true rule
start.

**`test_the_exclusion_comes_after_the_promotion`** compared the index of the
`display: inline-block` *declaration* against the `p a[href]` *selector*. When
the promotion block was physically moved below the exclusion, its declaration
was still textually "before" the exclusion's selector, and the test passed.
Now compares rule start positions, and additionally asserts the two are
distinct rules.

Both re-verified against the same reverts afterwards: each now fails
correctly.

---

## Verification

- **Full suite: 3,212 unit + 655 regression/system/uat = 3,867 passing,
  0 failures.**
- Real Chromium, all 68 panes: **0 errors, 0 blank panes, 0 broken
  workstations.**
- Layout checked at three viewports: **0 px horizontal overflow everywhere**,
  panes with wide children 30 → 27 (better than baseline).
- `ruff`, `lint_inline_handlers`, `lint_globals` clean.
