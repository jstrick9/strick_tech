# 93 — One key, one action: completing the help honesty pass (#260)

This commit exists because two implementations of the same Phase-3 scope
were written in parallel. The concurrent actor's #259 (`702a488`) landed on
main first with the same locked scope — honest help, labelled skeletons,
palettes reference, settings tiles — implemented independently of the local
one (`ec21ea2`, preserved on the local `backup/mine-ec21ea2` branch). #259
was adopted wholesale; #260 is the reconciliation: the pieces the adopted
tree was missing, found by diffing the two implementations.

## What the adopted #259 had that the local one did not

Measured by reading it, not by assuming parity:

* **A real #258 regression fix.** The applyTheme rewrite dropped the
  `accent` local the persistence PATCH still referenced — themes applied
  visually but the preference never reached the server. The local
  implementation never exercised the persist path. Fixed in #259 as
  `persistAccent`, derived before the fetch.
* **A live-pressed inventory.** #259's 44 entries were verified by pressing
  the keys in a browser, which caught what source-citation missed: ⌘⇧P
  lands on Profiler, not Studio (the local list documented the
  first-registered handler, not the landing pane), and Alt+1–7, ⌘R and ⌘U
  were real and missing. The local 36-entry list was wrong about ⌘⇧P.
* **`frontend/palettes.json`** as a third generated artifact beside the CSS
  and markdown, feeding the in-app Themes tab.

## What #260 ports onto it

**The platform modal contract (locked scope (e)).** The adopted overlay was
class-based (`kbs-*`) but stood outside the app's modal machinery: its own
Esc listener, no discovery, no focus trap. It now carries
`kbd-modal-overlay`, which enrolls it in `collectOpenModals()`'s ad-hoc
`[class*="-modal-overlay"]` discovery, `masterEscapeHandler`'s teardown
(remove + focus restore + toast — the same handler every other modal answers
to) and `isTrapRoot`'s Tab focus trap (WCAG 2.4.3: Tab used to walk out of
the dialog to the page behind it). The overlay's own Esc branch stays as
documented belt-and-braces. Pinned live in
`tests/e2e_browser/test_e2e_browser_13_modal_contract.py`.

**The double-binds, resolved.** #259 documented four keys by their final
effect and recorded them in module-review 92's follow-up table. #260
deletes the losing handler instead — the landing pane is unchanged, but
nothing paints underneath and nothing double-fires:

| Key | Kept (documented) | Deleted (the loser) |
|---|---|---|
| ⌘⇧E | Health (07-quality-tools) | 05-evals' `nav('evals')` — painted Evals once underneath on every press |
| ⌘⇧P | Profiler (03-features-a) | app-core's `nav('studio')` + the palette's `(⌘⇧P)` hint on Open Studio |
| ⌘P | palette (app-core) | 14-prompt-library's `nav('codesearch')` — navigated behind the palette on every press |
| ⌘\ | toggleSidebar (app-core) | `90-sidebar-shortcut.js` (duplicate width toggle, file deleted) + 14's split-workspace keydown binding (it keeps its buttons and palette entry, whose `(⌘\)` hint is dropped) |

Deleting a superseded binding is the codebase's own precedent: the comment
above app-core's studio binding documented removing the retired Builder
pane's ⌘⇧E as "a confusing second binding for the exact same destination".

**A fifth lie #259 shipped unknowingly: ⌘R.** The overlay documents
"Review current file", and the review button's own tooltip claimed ⌘⇧R —
but the binding's guard asked for `e.key==='r'` WITH `e.shiftKey`, and
shift makes `e.key` 'R'. The condition can never match: dead code, ⌘R fell
through to the browser reload. The guard now matches the documented key
(and `preventDefault` is the documented, deliberate browser-key steal, as
with ⌘U); the tooltip and palette entry now say ⌘R. ⌘⇧R remains Replay's
alone, as documented.

**Two latent bugs in the adopted vitest file** (its commit noted it was
"re-verified by grep; vitest is not a gate on this platform" — it had never
run): `read('../index.html')` resolved outside `frontend/` (ENOENT before
the first assertion), and the `showShortcuts\s*\(` ban matched a prose
comment in 32-collaboration.js — the same comment-fragility the load-order
pins taught us about. Both fixed; the suite is 9/9.

## Deliberately NOT ported from the local implementation

* ember's `text3` lightening (`#a08d7a`, weakest 5.24:1) — #259's own
  value (`#9d8879`, 4.96:1) also passes AA and is already generated into
  all three artifacts; churning it buys nothing.
* The `test_sys_03` desc-length repoint — #259's feed uses verb-phrase
  descs ("Open Arena"), so its `> 5` check passes as-is.
* The load-order pin hardening — the adopted tree's pins pass without it;
  hardening without a failing signal is churn.

## Verification

* Browser: `test_e2e_browser_11` 5 + `test_e2e_browser_12` 12 (the ⌘P pin
  updated to the single-bind contract — active pane must be unchanged by
  the press) + `test_e2e_browser_13` 4 (new) — 21 passed.
* Unit: the full ladder in three batches — 2359P/1S + 1736P/157S +
  1226P/7S, plus `test_112` 26/26. (4 brotli-variant failures in one batch
  run were a sandbox-reset artifact — the bundle had been rebuilt before
  the `brotli` module was restored; after rebuild, green.)
* Vitest: shortcuts-truth 9/9; full suite 547 passed / 3 failed — the same
  three pre-existing at `e79ecfa` (badge-tag-reconcile, chat-empty-stream,
  studio-galaxy #074), clean-tree-verified there and still untouched.
* Network suites via `run_network_suites.sh`: gap+usability 510P/21S;
  sprint_a–d 215P; integration+regression 519P/5S; system+uat+security
  876P/6S; perf 319P/6S; connectors+benchmarks 270P/249S — 0 failed.
