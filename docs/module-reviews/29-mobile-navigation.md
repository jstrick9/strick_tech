# 29 — Mobile navigation, and an invalid CSP source

Autonomous hunt, batch 19. Two bugs, both found by driving the real app in
Chromium rather than by reading code, and both invisible to every existing
test because the existing tests only ever ran at desktop width.

---

## Bug 1 — below 768px the product had no navigation at all

### What was wrong

Both stylesheets that `index.html` actually links carried the same rule:

| File | Line |
|---|---|
| `frontend/styles-unified.css` | 1258 |
| `frontend/styles-redesign.css` | 595 |

```css
@media (max-width: 768px) { #sidebar { display: none !important; } }
```

Nothing was ever built to replace it. There is no hamburger, no drawer, no
bottom tab bar, no overflow menu — the sidebar is hidden and that is the end
of it.

### Evidence (Chromium, measured, before the fix)

| Viewport | `#sidebar` computed | Nav items with width > 0 | Any control able to reveal nav |
|---|---|---|---|
| 390 x 844 (phone) | `display:none`, 0x0 | 0 of 28 | **none** |
| 768 x 1024 (tablet portrait) | `display:none`, 0x0 | 0 of 28 | **none** |
| 1440 x 900 (desktop) | `display:flex`, 260x816 | 28 | n/a |

`#sidebar-toggle-btn` — the existing collapse control — is a **child of the
sidebar**, so it was hidden along with it. There was no element anywhere on
the page capable of bringing the navigation back.

### Impact

On any phone, and on a tablet in portrait, the entire platform collapsed to a
single pane. Chat, Code Studio, Memory, Tasks, Settings and 23 other
destinations had **no reachable entry point**. Because `display:none` also
removes a subtree from the accessibility tree, this hit keyboard and
screen-reader users identically — it was not merely a pointer-input problem.

### The fix

`frontend/js/00-mobile-nav.js` plus a matching CSS block in both sheets.
Standard drawer pattern, the one ChatGPT and Claude both use:

- Hamburger in the topbar, `display:none` above 768px, **44x44** minimum
  (WCAG 2.5.5 / iOS HIG).
- The sidebar becomes a fixed overlay drawer, translated off-canvas, slid in
  on `body.mobile-nav-open`.
- Scrim behind it, closes on tap.
- Escape closes it; focus moves into the drawer on open and back to the
  hamburger on close.
- Choosing a destination closes it — on a phone the drawer covers the pane you
  just navigated to.
- `inert` + `aria-hidden` while closed, so the 28 rows leave the tab order and
  the a11y tree. Translated rather than `display:none`d so it can animate;
  `inert` supplies the same semantics without killing the transition.
- Crossing the breakpoint (rotating to landscape) clears the state.
- Nav rows get a 44px minimum height in drawer mode.

The CSS is duplicated into **both** sheets deliberately: either sheet alone
re-asserts `display:none !important` and reintroduces the bug.

### Two bugs found while building the fix, both worth recording

**Focusing the first nav row opened and closed the drawer in the same tick.**
The obvious implementation — focus `#sidebar .nav-item` on open — was measured
to add `mobile-nav-open` and then come back with `body.className === ''`. The
nav rows are `div[role="button"]`, and Chromium delivers a click on focus,
which hit the close-on-navigate listener. Focus now lands on the drawer
container. (This is the same Playwright/Chromium `[role=button]` focus-click
behaviour already documented in `27-real-browser-e2e.md`.)

**A bubble-phase Escape handler never fired.** Registered on the bubble phase,
the Escape listener was measured not to run at all: the app already installs
capture-phase Escape handling, and whichever handler runs first can stop the
event before a bubble-phase document listener sees it. Registering on the
capture phase makes it deterministic instead of dependent on script order.

---

## Bug 2 — an illegal CSP source, discarded on every page load

`backend/app.py` `connect-src` contained:

```
https://jira.*.atlassian.net
```

That is not legal CSP. A wildcard may only be the **entire leftmost label**
(`*.atlassian.net`); it cannot appear after a label. Chromium logged, on every
single page load:

```
The source list for the Content Security Policy directive 'connect-src'
contains an invalid source: 'https://jira.*.atlassian.net'. It will be ignored.
```

Two consequences:

1. **The allowance never took effect.** Every Jira connector call made from the
   browser was blocked by `connect-src` regardless of host — the source was
   discarded, not narrowed.
2. **Console noise.** A CSP error on every load trains anyone debugging to
   ignore CSP output, which is exactly the signal the Phase 1–3 work exists to
   make legible.

Corrected to `https://*.atlassian.net`, which covers
`jira.<site>.atlassian.net` as intended. A full sweep for other rejected
sources across both the enforcing and Report-Only policies now returns none.

---

## Tests

`tests/e2e_browser/test_e2e_browser_04_mobile_nav.py` — 8 tests.

Written against observable browser state (computed geometry, `inert`, focus,
active pane) rather than markup presence: the pre-fix DOM contained all 28 nav
items, so a DOM-presence test would have passed against the broken build.

**Proven to catch the bugs.** With both fixes reverted (the `<script>` tag
removed and the illegal CSP source restored):

```
7 failed, 1 passed
```

The one that passes is `test_desktop_layout_is_untouched`, which is correct —
desktop was never broken, and that test exists to catch the drawer leaking
into the desktop layout, which would be a worse bug than the one being fixed.

With the fixes in place: **8 passed**.

---

## Also checked, no issue found

A sweep of **all 28 panes** at 390x844 measuring `documentElement.scrollWidth`
against `innerWidth` found **0 panes** overflowing horizontally. The layout
below the breakpoint was already fluid — the sidebar was the whole problem.

## Regression status

| Suite | Result |
|---|---|
| Full non-browser | **3959 passed, 19 skipped, 0 failed** (unchanged) |
| `lint_inline_handlers.py` | pass |
| `ruff check backend frontend scripts` | pass |
| New mobile-nav browser suite | 8 passed |
