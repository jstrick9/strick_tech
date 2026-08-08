# 55 — Long and adversarial input

**Seam:** *long / adversarial input*
**Audit:** `scripts/audit/adversarial_input.py` · **key:** `adversarial-input` ·
**baseline:** 1 → **0**
**Tests:** `tests/unit/test_126_adversarial_input.py` (11) — 4 fail on revert,
1 pinned to the regression specifically.

---

## What was measured

Nine payloads written through the **real API** and rendered by the UI — the
round trip is where escaping bugs live, so injecting into the DOM directly
would test nothing but the browser.

| Payload | Result |
|---|---|
| `<script>window.__xss=1</script>` | inert |
| `<img src=x onerror=…>` | inert |
| `<svg onload=…>` | inert |
| `${constructor.constructor(…)()}` | inert |
| `Ali's Q3 plan` | intact, **not** double-escaped |
| `Ship it 🚀🎉 done` | intact |
| `مرحبا بالعالم` | intact |
| 4,000 unbroken chars | **overflowed its card** |
| 10,800 chars of prose | wrapped correctly |

**No XSS and no data loss.** Recorded as a result rather than silence:
escaping is the single thing most likely to be quietly wrong, and here it is
right. `Ali&#39;s plan` on screen would have been a *safe* bug that still tells
the user their data is corrupted.

---

## The defect

A 4,000-character title rendered in a **235px** card with **`scrollWidth:
2137px`** and `overflow: visible` — spilling straight across neighbouring cards
and making the column unreadable.

`documentElement.scrollWidth` stayed at exactly **1440px** the whole time.

That number matters. The existing `responsive.py` audit measures document width
and reported **0** for this page — and was *right to*. This is a different bug
in a different place, invisible to the global measure, and it needed a
different instrument: element-level `scrollWidth > clientWidth` where
`overflow` is `visible`. A container that clips or scrolls is a deliberate
design choice, not a break.

---

## The fix

A **structural** containment rule, not a patch to `.kanban-card-title`:

```css
.card, .card *, [class*='-title'], [class*='-name'], … {
  overflow-wrap: anywhere;
}
.card > *:not(button):not(a):not(input):not(select):not(textarea):not([role='button']),
… { min-width: 0; }
```

- **Structural, because users paste long values into every field.** Fixing the
  one class that happened to be measured leaves the bug in the dozens of other
  places a title is rendered, and does nothing about the next component
  written. Same reasoning as the structural touch-target rule in batch 34,
  which was adopted after an allow-list approach missed 41 element types.
- **`overflow-wrap: anywhere`, not `word-break: break-all`.** `break-all` chops
  ordinary words mid-letter even when they would fit, making normal text ugly
  in order to fix a rare case. `anywhere` only breaks a run that has no other
  way to fit.
- **`min-width: 0` on flex/grid children.** A flex item's default
  `min-width: auto` refuses to shrink below its content, so a long unbroken
  string forces the whole row wider regardless of what wrapping the child asks
  for. Without this the wrap rule silently does nothing inside a flex row.
- **`.no-wrap-guard` opt-out** for values that genuinely must stay on one line.

---

## The regression the fix caused

The first version applied `min-width: 0` to **every** child. The touch-target
audit went from **0 to 9** immediately:

```
1x BUTTON.prb-bulk-btn        12x44 CRITICAL  🗑
1x BUTTON.file-row-delete-btn 15x44 CRITICAL  🗑
4x BUTTON.kanban-column-add   20x44 CRITICAL  +
…
```

It had overridden the structural 44px rule from batch 34 and collapsed buttons
to as little as 12px wide — a bulk-delete button at 12×44. The rule now
excludes interactive elements.

**A containment rule must never shrink a tap target.** Text needs to wrap; a
control needs to stay hittable. The ratchet caught this within one run, which
is precisely what it was built for.

---

## Verification

| Check | Result |
|---|---|
| `scripts/audit/adversarial_input.py` | 1 → **0** |
| Remove the CSS | audit reports **6** overflowing elements |
| Revert the CSS | **4 of 11** tests fail |
| Revert *only* the `:not()` guards | `test_the_containment_rule_does_not_shrink_controls` fails |
| `touch-targets` | 9 → **0** |
| `responsive`, `semantics`, `pane-health` | still 0 |
