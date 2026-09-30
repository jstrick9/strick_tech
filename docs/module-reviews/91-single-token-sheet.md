# 91 — The single token sheet (Phase 2 of the design-system work)

You locked the scope: Core (tokens + dead sheets + skeletons + shell) plus the
chat and settings containers; add ember and ocean as real palettes. This is
that commit (#258), what it found on the way, and what it deliberately did
not claim.

## The token system before

Measured, not assumed:

* Four of the five loaded stylesheets each defined a `:root` block — 56
  distinct tokens, **20 with conflicting values**, the last-loaded sheet
  silently winning while the others' unique tokens leaked through.
* The theme palettes lived only in JS (`THEME_VARS`): `applyTheme()` wrote
  sixteen tokens inline on `<html>` at runtime. But `applyTheme()` also sets
  `data-theme` on `<body>`, and the sheets' `:root, [data-theme="dark"]`
  rules therefore **redefined every token on the body** — a scope between
  the inline writes and the visible app. The old dark/light entries were
  inert below body: the app rendered the sheets' static palette (neutral
  greys, indigo accent), not the navy/cyan table. The four exotic palettes
  had no body-scoped block, so *they* rendered from the table. Two different
  dark palettes depending on which theme you picked.
* Onboarding offered "Ember" and "Ocean" swatches that existed in no table;
  `THEME_VARS[tid] || THEME_VARS.light` silently applied the light palette.
* `frontend/styles.css` (228KB) and `styles-phase5.css` (9KB) had not been
  loaded by any page since the redesign of 2026-07-25.

## What changed

**`frontend/styles-tokens.css`** — the only token definer, loaded first.
`:root` carries the *measured visible* dark palette plus every theme-stable
token; `[data-theme=...]` blocks (dark/light, full-set, matching `<body>` —
the body pin is what keeps a saved custom accent inert in the two default
themes, exactly as before) and `html[data-theme=...]` blocks (the six exotic
palettes, diff-only, so a custom accent stays visible there, exactly as
before). Both selector shapes are load-bearing; `test_244` pins them.

**`scripts/gen_theme_css.py`** — reads `THEME_VARS` and renders the palette
blocks. `THEME_VARS` is the single source; the CSS is its artifact and
cannot drift (`--check` + `test_244`). THEME_VARS.dark/light now carry the
measured visible values; ember and ocean were added (AA-verified per pair,
weakest 4.82:1).

**`applyTheme()`** no longer writes sixteen tokens inline; switching themes
is an attribute change. A custom accent still writes `--accent`/`--accent-
glow` inline (that path is preserved bit-for-bit). Unknown ids warn and stay
on the dark base instead of silently repainting light.

**Dead sheets deleted.** Deleting them exposed that six unit tests had been
reading `styles.css` — asserting CSS the browser hadn't loaded for two
months. Four of the selectors they pinned (`.connection-status` state dots,
`.chat-attachment-chip`, `.mission-launchpad`) existed **only** in the dead
monolith: the 2026-07-25 redesign switched index.html to the split sheets
and never carried these rules over, so the connection-status dot, the
attachment chips and the launchpad card silently lost their styling while
the tests kept passing. The rule groups are restored (declaration-merged —
the monolith redefined several in place) into `styles-system.css`, and the
tests now read the live sheets.

**Inline-style conversion: 823 → 519 first-load refusals (−37%).**
* Static pane skeletons: 211 attrs → `.pane-skeleton*` + `.skel-*` classes
  (153 skeleton bars in seven shapes across 69 panes).
* Settings: 78 attrs → `.set-*` classes, plus the seven `.settings-nav-item`
  buttons whose inline styles had been shadowing their own class rule —
  folded into `styles-unified.css` with the *rendered* values.
* Chat/shell repeated values → `.chat-eyebrow`, `.sb-chevron`, `.sb-count`.
* Single-use values stay inline deliberately: a class per single-use value
  trades an attribute for a single-use class and changes nothing (the
  non-convergence measured in module-review 35).

## The two deliberate visual deltas

Both are "CSS that always meant to apply, now applying" — found, not
designed:

1. **The settings active tab is visibly highlighted again.** The inline
   `background:transparent` on every nav button (including the active one)
   had suppressed `.settings-nav-item.active` since the markup was written;
   `switchSettingsTab()` toggled a class with nothing behind it.
2. **The connection-status dot renders** (amber for attention, green for
   ready) — restored with the orphaned rule groups above.

Everything else is pixel-verified: `computed_style_diff` before/after shows
only the known-unstable width paths (the same 25 the clean tree shows
against itself), and per-theme body-scope token captures are identical to
the pre-change app for all six original palettes.

## What this commit does NOT claim

The full-walk console noise barely moved (~303/pane vs ~305 before; budget
stays 350). It is dominated by pane-render templates in 30+ module files
(browser 1521, goals 1330, mcp-gateway 1284 on one pass) — the long tail
that stays out of scope by design. The first-load ratchet is pinned instead:
`test_e2e_browser_11` fails if first-load refusals exceed 560 (519 measured).

## Verification

* e2e_browser: 107 passed / 13 skipped (102 + 5 new pins in
  `test_e2e_browser_11_design_system.py`).
* Unit: all 276 files — 1014 + 2275 + 152 + 957 passed, 0 failed.
* The hydration floor in `test_e2e_browser_08` moved 500 → 400: 478 attrs
  hydrate now *because* 300+ became classes. The floor tracks the census.
* Network suites via `run_network_suites.sh`: green (see commit message).
* `computed_style_diff` baseline vs after: no color diffs app-wide.
