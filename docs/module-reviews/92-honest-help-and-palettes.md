# 92 — Honest skeletons, honest help, real palettes (Phase 3, r95, #259)

The third and final phase of the design-system work. Phase 1 (#257) made the
first run honest; Phase 2 (#258) made one token sheet from one palette table;
this phase makes the *help* honest, makes the palettes *reachable*, and makes
the loading states *say something*. Scope locked with the user: skeletons
(ARIA + nav() fallback + stagger), help-`?` full honesty pass, generated
palette markdown + in-app themes reference, settings tiles as classes with
Ember and Ocean added.

## The help used to lie, four ways

The `?` overlay existed, but its list was hand-maintained in **four places**
that had drifted apart: the overlay itself, the dead `#shortcuts-modal` +
`showShortcuts()` pair in app-core (fed by `/api/onboarding/shortcuts`),
`docs_center.py`'s `KEYBOARD_SHORTCUTS` (fed the docs pane), and
onboarding.py's own copy of that list. Measured against the actual bindings:

* **Three documented shortcuts were fiction.** F7/F8 "Next/Previous diff" —
  never bound anywhere in the codebase. Ctrl+Shift+M "Toggle voice mode" —
  removed as a duplicate of Ctrl+Shift+V long ago. They lived in two of the
  four lists.
* **Six real shortcuts were undocumented**: ⌘1–6 quick nav, ⌘P, Alt+1–7,
  Alt+Shift+F, ⌘R (review file), ⌘U (share).
* **The backend list was substantively wrong**: ⌘/ was documented as "Open
  documentation center" (it focuses the chat input), ⌘⇧P as "Profiler"
  (double-bound; see below), ⌘⇧E as "Evals".
* **Every open of the overlay emitted ~25 inline-style CSP refusals.** The
  overlay built its HTML with `style="…"` attributes per open; the enforced
  `style-src 'self'` refuses each at parse time and the style-hydrate
  observer re-applied them — visually fine, but a refusal burst on every
  `?`, forever.

**Now:** the overlay file is the single hand-curated source (44 verified
entries, 8 groups). `docs_center.KEYBOARD_SHORTCUTS` is its flattened
mirror; onboarding.py imports that mirror instead of carrying a fourth copy.
`test_245` parses the overlay and fails if any surface diverges. The overlay
renders from `.kbs-*` classes — zero refusals per open, pinned in the
browser. The dead modal, its feeder function and the stale markup are
deleted; the ⌨️ header button and the palette entry call the one overlay.

**Live double-binds found and deliberately NOT fixed** (fixing them changes
behaviour; each is pinned by its final effect instead, and they are recorded
here as follow-up candidates):

| Key | Handlers | Lands on |
|---|---|---|
| ⌘⇧E | evals (05) then health (07) | Health (after a wasted evals nav) |
| ⌘⇧P | studio (app-core) then profiler (03-features-a) | Profiler (after a wasted studio nav) |
| ⌘P | palette (app-core, capture) + code search (14-prompt-library) | palette open over the Studio pane |
| ⌘\\ | toggleSidebar + width toggle (90) + split workspace (14) | all three fire |
| ⌘R / ⌘U | reviewCurrentFile / shareProject — also steal browser reload / view-source | — |

## A #258 regression, found by a test that refused to pass

The docs-Apply browser test kept failing in a way that made no sense —
until instrumenting `applyTheme` produced `ReferenceError: accent is not
defined`. The #258 applyTheme rewrite dropped the `accent` local that the
persistence `fetch` body still referenced, so **every persist-path call
threw after the attribute writes**: the theme applied and localStorage
saved (which is why it survived unnoticed), but the preference PATCH never
fired and anything chained after the call in a `data-act-click` expression
— the picker tile's toast, the docs tab's re-render — never ran. Verified
present on the clean #258 tree. Fixed: the persist body now derives the
accent (override → palette's own) before sending.

## The palettes

* **Settings can finally set Ember and Ocean** — onboarding has offered both
  since the wizard was written; the settings grid had seven tiles and no
  ember/ocean. Nine tiles now, as classes; the per-palette *faces* are
  **generated from THEME_VARS** into styles-tokens.css by the same script
  that renders the palette blocks. A swatch can no longer misrepresent its
  palette (the old "Dark Cyber" tile was navy `#0f172a`; dark is `#0f0f0f`).
* **`applyTheme` marks the current tile** (`.active` + `aria-pressed`) — the
  picker previously gave no indication of which palette was active.
* **Three generated artifacts, one source, one `--check`:** the CSS palette
  blocks + tile faces, `frontend/palettes.json` (served by the new
  `/api/docs/palettes`), and `docs/palettes.md` (token tables + WCAG
  contrast per palette). The Documentation Center gained a Themes tab that
  renders the JSON — swatches, contrast, current-marker, Apply.
* **Two AA fixes #258 missed** (found because test_96, which #258 silently
  broke, was run against the clean #258 tree): light's `onAccent` was white
  on the frozen accent = **4.13:1** on primary-button labels (now `#0b1020`,
  4.58:1, the same value five other palettes use); ember's `text3` was
  verified on bg-2 only and measured **4.47:1** on bg-3 (now `#9d8879`,
  4.96:1). Every palette's weakest pair now clears AA body text — asserted,
  not hoped.

## Skeletons

* All 22 static pane skeletons carry `role="status"` +
  `aria-label="Loading …"`: 153 shimmering bars are announced as a loading
  state instead of silence.
* `nav()`'s fallback for panes with no static markup (unknown ids, stale
  deep links) was an ad-hoc "⚡ Initializing…" string matching nothing; it
  now renders the same design-system skeleton as everything else.
* The bars' 1.5s shimmer all started at t=0 — panes pulsed as one flat
  sheet. Negative `animation-delay` rules stagger the grid (the wave
  travels); the global `prefers-reduced-motion` kill-switch already covers
  them.

## Verification

* e2e_browser: **119 passed / 13 skipped** (107 baseline + 12 new pins in
  `test_e2e_browser_12_design_system_p3.py`: skeleton labelling/stagger/
  fallback; `?` opens class-based with **zero** CSP refusals, contains the
  previously-missing shortcuts, none of the fiction; Esc/input exemption;
  16 ⌘⇧ pane jumps live-pressed and pinned to their landing (workstation
  host + selected tab); ⌘P pinned with its double-bind footnote; nine
  honest tiles + ember applies + current-tile marking; docs Themes tab
  renders the reference and applies a palette).
* Unit: **5297 passed / 187 skipped / 0 failed** across all 278 files
  (run chunked — the single-process run dies at the sandbox CPU cap).
  test_96_colour_contrast modernised to the #258 architecture (its four
  stale pins are what surfaced the AA regressions); test_245 (14 pins) added.
* vitest `shortcuts-truth.test.js` updated to the single-overlay state (its
  assertions re-verified; vitest is not a gate — no node_modules on this
  platform).
* Theme-tile conversion verified value-neutral by computed probes against
  the pre-change markup: layout values identical; the deliberate deltas are
  the honest faces (documented above) and the restored per-tile elevations.
* Network suites via `run_network_suites.sh`: see the commit message.
