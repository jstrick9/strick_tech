# 57 — Preferences, print, and multi-tab

**Seams:** *reduced motion* · *high contrast* · *zoom to 200%* · *print/export*
· *multi-tab* — **the last five in the register.**

| Audit | Key | Baseline |
|---|---|---|
| `scripts/audit/preferences.py` | `user-preferences` | 7 → **0** |
| `scripts/audit/print_and_multitab.py` | `print-and-multitab` | 3 → **0** |

**Tests:** `test_128_user_preferences.py` (14, 8 fail on revert) ·
`test_129_print_and_multitab.py` (14, 8 fail on revert).

---

## Verified with no defects

Recorded explicitly, because "found nothing" is a result and silence is not:

- **Reduced motion.** Under `prefers-reduced-motion: reduce`, zero elements
  animated past 100ms across six panes.
- **Multi-tab.** A record created in one browser context appeared in a second
  context on opening that pane. The check drives real UI in the second window
  rather than reading the API — the question is whether the second *window*
  learns, not whether the server knows.

---

## Zoom to 200% — 5 defects (WCAG 1.4.4 AA)

At 200% on a 1280×1024 desktop the CSS viewport is 640×512.

| Container | Laid out to | Controls unreachable |
|---|---|---|
| `#topbar` | 838px | notifications, settings, profile |
| `#next-action-bar` | 715px | trailing action |
| `#studio-editor-row` | 719px | Format, Find, Review |
| `.preview-toolbar` | 817px | Full / 375 / 768 / 1280 |
| `#studio-console-drawer` | 844px | Linter, Clear, Collapse |

### A fix already existed and was inert

The topbar had a wrapping rule — inside `@media (pointer: coarse)`. **A desktop
user at 200% zoom has a *fine* pointer**, so it never matched. The constraint
is available width, which is exactly what zoom reduces, so the rules are now
keyed to width.

This is the **second** inert-CSS-fix recorded in this file. The comment above
the existing rule already documents a `.topbar__actions` selector that pointed
at markup which never existed. A fix that is present, reasonable and does
nothing is harder to spot than a missing one, because code review finds it and
approves it.

`#next-action-bar` had a related cause: it is created in JS with
`left: var(--sidebar-w)` **inline**, which is right while the sidebar occupies
space and wrong once the sidebar becomes an off-canvas drawer.

---

## Forced colours — 2 defects

`.agent-status` and `.sb-dot` were empty `<div>`s whose entire meaning was
their background colour. Under `forced-colors: active` the system replaces the
palette and "green = healthy" becomes an unlabelled grey box. Both now carry
`role="img"` + `aria-label`, which fixes screen-reader users at the same time —
they had never been announced either.

The connection dot's update path was refactored into `setDot()` so the label
changes with the colour; changing only `background` would leave it announcing
"Online" while showing red.

---

## Print — 3 defects

| Finding | Detail |
|---|---|
| `PRINT-CHROME` | `#next-action-bar` printed as a floating strip across page 1. The hide-list predated it, and the session/connection/offline banners. |
| `PRINT-CLIPPED` | **`#kanban-col-todo` held 8,808px of tasks in a 600px box.** |
| `PRINT-INVISIBLE` | Body luminance 0.04 under print: a page of toner with light text on it. |

**The clipped case is the one that loses data.** A scroll container prints only
the visible slice, and *nothing on the printed page says the rest exists*. The
output looks complete and is not — the same failure class as finding #9 in this
review, "the response not describing its own completeness".

The fix releases `overflow` and `max-height` **universally** in print rather
than listing containers: enumerating today's misses every one added later, and
paper has no viewport to scroll. The same argument drives forcing the palette
at the leaf level instead of on `body`.

`styles-print.css` has no `@media print` wrapper and does not need one — it is
scoped by `media="print"` on its `<link>`. That looked like a bug on first
reading; a test now pins the arrangement so it is not "fixed" in either
direction.

---

## Probe bugs found before the app's

1. **A closed off-canvas drawer is correct design, not a WCAG failure.**
   Counting the sidebar's 24 links as unreachable buried the real finding
   under noise.
2. **Detecting the drawer by parsing its transform matrix** would miss the
   same drawer moved by `left` or a percentage. Geometry is the definition.
3. **The sidebar parks at exactly `right: 0`**, so a strict `<= 0` treated it
   as on screen. A 1px tolerance was required.
4. **`.monaco-status` was a false positive** — Monaco's own `aria-live`
   region, deliberately empty and invisible, matched only because the selector
   list looks for "status" in a class name. Vendored UI is now excluded.

---

## A pre-existing test updated, not deleted

`test_app_core_offline_handler_does_not_toast` (batch 2 of this session) sliced
the handler to the next `};` and asserted `sb-dot` appeared inside. Extracting
`setDot()` for the forced-colors fix turned the handler into a one-line
delegation, so the assertion broke while the behaviour stayed correct.

It was **updated in place with the reason recorded**, and re-verified: adding a
toast back to the handler still fails it.

---

## Verification

| Check | Result |
|---|---|
| `preferences.py` | 7 → **0** |
| `print_and_multitab.py` | 3 → **0** |
| Remove the print CSS | audit reports all 3 findings again |
| Revert the frontend fixes | 8 of 14 + 8 of 14 tests fail |
| All 18 audits | **0** |
| Full suite | 3,336 unit (2 skipped) + 655 (10 skipped), 0 failures |
