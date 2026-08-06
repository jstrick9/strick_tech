# 32 — Full accessibility audit: 684 → 0

Autonomous hunt, batch 22. A real axe-core (v4.13) WCAG 2.1 A + AA audit run in
Chromium against **all 28 panes**, not a static scan.

## Baseline

| Rule | Impact | Nodes | Panes |
|---|---|---|---|
| `aria-allowed-attr` | **critical** | 243 | 24 |
| `aria-required-parent` | **critical** | 243 | 24 |
| `color-contrast` | serious | 169 | 24 |
| `scrollable-region-focusable` | serious | 29 | 24 |
| **Total** | | **684** | |

## After

**0 violations, all 28 panes.**

---

## Cause 1 — `role="menuitem"` (486 nodes, both critical rules)

Every sidebar row was given `role="menuitem"` by two separate blanket ARIA
passes. That broke two critical rules at once:

- **`aria-required-parent`** — a `menuitem` must be inside a `menu`, `menubar`
  or `group`. The real parents (`#group-core`, `#group-build`,
  `#sidebar-favorites-section`, …) are all `role="none"`. An orphaned
  `menuitem` is not exposed as a menu item at all; the role is discarded and
  the sidebar announces as unstructured text.
- **`aria-allowed-attr`** — `aria-selected` is not permitted on `menuitem`, and
  `window.nav` set it on every item on every navigation.

`menuitem` was also semantically wrong: it means an item in an application menu
(the File/Edit kind) and implies typeahead and arrow-key handling the sidebar
does not implement. These are links to panes.

**Fixed:** `role="button"` inside the existing `role="navigation"` landmark,
with **`aria-current="page"`** marking the active destination — the pattern the
WAI-ARIA APG specifies for exactly this. Unlike `aria-selected`, `aria-current`
is *removed* rather than set to `"false"`, so unselected items are not
announced with a state on every pass.

## Cause 2 — a control inside a control (`nested-interactive`)

Each row was interactive **and** contained a real `<button>` to favourite the
pane. The inner button's text is absorbed into the outer control's accessible
name and activation is ambiguous.

**Fixed:** rows are now plain containers holding two **siblings** — `.nav-open`
(navigate) and `.nav-fav-btn` / `.fav-remove-btn` (favourite). Done at runtime
in `splitNavItemControl()` rather than by editing 27 static rows, so the
generated favourites list and the static sidebar share one implementation.

Three follow-on bugs surfaced while doing this, each caught by re-running the
audit rather than by reading code:

1. The blanket ARIA passes re-added a role to the new container on their next
   run, recreating the violation. Both passes now re-point at the inner control.
2. `addFavoriteButton()` was not idempotent — a second call wrapped its own
   wrapper, producing `.nav-open` inside `.nav-open`. **84 nodes.**
3. It also ran on `.fav-item` rows, which are *built* in the correct shape,
   wrapping their two controls in a third.

## Cause 3 — contrast (169 nodes)

Not one bad token. The theme system is correct: every theme's declared
`--on-accent` passes on its own accent. The failures were code that **bypassed**
it, plus one fill that could not be saved.

**The default accent could not carry any accessible foreground.** 127 of the
138 remaining nodes were one pairing — `--on-accent` (#0b1020) on `--accent`
(#6366f1), 4.23:1. Critically, this was **not fixable by choosing a better
foreground**:

```
black / #0b1020  on #6366f1  ->  4.23:1   FAIL
white            on #6366f1  ->  4.47:1   FAIL
```

Neither end of the scale reaches AA — the fill sits in the luminance dead zone.
This is also why the earlier per-theme audit passed: it checked each theme's
declared accent, and `#6366f1` is the CSS default that no theme entry declares.
Nudged two steps lighter to `#6a6df2` (same hue and saturation): `--on-accent`
now reaches **4.58:1**.

Other instances of the same class:

| Where | Was | Ratio | Now |
|---|---|---|---|
| `.btn-primary` | `color: white` | 4.46 / 2.14 | `var(--on-accent)` |
| `.kanban-add-btn` | `color: white` | 4.46 | `var(--on-accent)` |
| `.kanban-filter-btn.active` | `--text-0` | 4.09 | `var(--on-accent)` |
| `.wf-toolbar button.primary` | `#fff` | 4.13 | `var(--on-accent)` |
| `.wf-toolbar button.success` | `#fff` on `--success` | **2.28** | `#0f2a18` |
| websearch active tab | `'#fff'` in JS | 4.13 | `var(--on-accent)` |
| Reload/Save buttons | `#fff` on `#10b981` | **2.54** | `#0c855d` |
| `--danger` as text | `#ef4444` | 4.43 / 3.72 | `#f26565` |

Two subtler ones worth recording:

- **`opacity` is invisible to a token audit.** `<span style="opacity:0.6">⌘K</span>`
  computed to 3.17:1, and `opacity:.8` on the breadcrumb sub-text to 4.23:1.
  Opacity silently multiplies whatever ratio the token achieved, so a token
  that passes on its own can still fail on screen.
- **Alpha backgrounds move with their surroundings.** The file-type badge used
  `background:${c}22` — a 13% tint of *its own text colour*. Because the tint
  is translucent, the row behind shows through, so contrast changed with row
  state: on `.active` the html badge measured 3.88:1. Chasing it by lightening
  the colour does not converge, because lightening the text also lightens the
  backdrop it composites over. Fixed **structurally**: opaque `--bg-0`
  background with the colour as a border, so contrast no longer depends on
  what is behind the row.

## Cause 4 — scrollable regions with no keyboard access (29 nodes)

`#agent-list`, `#wf-node-palette` and `#db-table-list` scroll but contained
nothing focusable, so a keyboard user could not scroll them **at all** —
content below the fold was unreachable. Given `tabindex="0"`, `role="group"`
and a label.

## Also fixed: a control invisible without a mouse

`.fav-remove-btn` was `opacity: 0`, revealed only on `:hover`. A keyboard user
could Tab to it but never see it; a touch user, having no hover, could not
reveal it by any means. Now `opacity: .55`, reaching 1 on hover **or**
`:focus-visible`. Both favourite controls also gained real `aria-label`s and
`aria-pressed` — a ★ glyph alone announces as "star" or as nothing.

---

## Tests

`tests/e2e_browser/test_e2e_browser_07_accessibility.py` — 8 tests.

The headline test reads the destination list **from the live sidebar** rather
than a hardcoded list, so a newly added pane is audited automatically.

Rule scope is deliberately limited to the rules that were broken plus those
most likely to regress from these specific fixes. A blanket "every axe rule"
assertion would fail on unrelated pre-existing issues and get muted — which is
how accessibility suites die.

**These tests caught a real bug during development.** After the rows were
split, `aria-current` was still being written to the row, which no longer has a
role — so the "you are here" cue was silently dropped for screen-reader users
while looking fine visually. `test_the_active_destination_is_marked_with_aria_current`
failed and named the cause.

**Proven to catch the bugs.** With all changes reverted: **7 failed, 1 passed.**

## Three pre-existing tests updated, not deleted

`test_navigation_works_by_keyboard`, `test_every_nav_item_is_reachable_by_tab`
and `test_a_focus_ring_is_declared_and_renders` asserted that focus lands on
`.nav-item` itself. That is now the container. **The user-facing requirement is
unchanged and still asserted** — every destination reachable by Tab, Enter
activates, focus ring renders — only the element carrying `tabindex` moved, so
each test resolves the row's control first. Verified independently that all 28
destinations remain keyboard-reachable and activate.

## Regression status

| Suite | Result |
|---|---|
| Full non-browser | **3959 passed, 19 skipped, 0 failed** |
| Browser E2E | **82 passed, 0 failed** |
| axe-core, 28 panes | **0 violations** (was 684) |
| ruff / inline-handler / globals linters | pass |
