# 43 — Duplicate rendering, and the workstations it was destroying

**Status:** shipped
**Batch:** 30
**Scope:** `frontend/js/00-render-dedupe.js` (new), `frontend/js/01-app-core.js`,
`frontend/js/00-workstations.js`, `frontend/js/00-chunk-loader.js`,
`frontend/js/{38-system-monitor,31-control-tower,33-webhooks,34-test-generator}.js`,
`tests/unit/test_114_duplicate_render.py`, `tests/unit/test_38_*` (updated)

The four pane errors flagged at the end of `42-code-splitting.md`. They turned
out to be the visible symptom of something much larger.

---

## What was reported, and what it actually was

Four panes threw `TypeError: Cannot set properties of null (setting
'innerHTML')` on every visit: `renderSystem`, `renderControlTower`,
`renderWebhooks`, `renderTestGen`. Their `#pane-<id>` elements did not exist.

Tracing *why* they did not exist found the real fault. `window.nav` is wrapped
**14 times across 10 files**, and the wrappers re-invoke renderers that the
base nav already ran through `MASTER_PANE_REGISTRY`:

```js
window.nav = function masterNav19(pane) {
  _base(pane);                                          // registry ran it
  if (pane === 'observability') renderObservability?.();  // and again
};
```

Measured against a live server: **25 redundant API calls across 10 sampled
panes.** But the wasted requests were the mild part.

A workstation host's renderer is async: it awaits fetches, *then* assigns
`pane.innerHTML`. `nav()` builds the workstation into the host — tab strip
plus every absorbed pane moved inside — and then the duplicate render resolves
and wipes all of it.

**7 of the 11 workstations were destroyed on first open, removing 28 absorbed
pane elements from the DOM.** That is why those four renderers found nothing
to render into. The entire 67-pane→24-workstation consolidation was silently
broken for anyone who opened Observability, Evals, Connect, Plugins, Secrets,
Supervisor or Workspaces.

```
observability   lostPanes: [agent-monitor, profiler, health, system,
                            audit-log, replay, finops, dashboard, leaderboard]
evals           lostPanes: [eval-framework, arena, bugbot, testgen]
supervisor      lostPanes: [a2a, agent-identity, hitl, goals, swarm,
                            fusion, finetune]
...
```

---

## Six fixes

### 1. Render deduplication (`00-render-dedupe.js`)

Each pane renderer runs at most once per navigation. Applied by wrapping the
renderers *named in the registry* — not by editing ~40 call sites across 14
wrappers, which is the "second door" pattern this review has hit six times.
Wrappers added later are covered automatically, and the chunk loader re-applies
it after each lazy chunk defines new renderers.

The suppression window lasts exactly one tick, because the wrapper cascade is
synchronous. That also keeps genuine refreshes working — `renderSecretsVault()`
after adding a secret, `renderEvals()` after creating a dataset.

### 2. `nav()` waits for an async host renderer

The old code ran `initWorkstation()` immediately after `renderer()` *returned*,
with a comment asserting this was "AFTER the host's own renderer so panes that
rebuild their innerHTML don't wipe the tab strip". That reasoning only holds
for synchronous renderers. Now it awaits the returned promise.

### 3. `initWorkstation()` checks the DOM, not a flag

`hostEl.dataset.workstationReady === '1'` outlived the thing it described: the
attribute survived an innerHTML wipe that deleted the tab strip and every
absorbed pane. `initWorkstation` then returned early *forever*, so a destroyed
workstation could never rebuild. Now it looks for `.ws-tabs` and `.ws-bodies`.

### 4. Absorbed panes keep `active` in sync with visibility

`initWorkstation()` strips `active` when absorbing a pane, but renderers use
that class to mean "am I on screen?". `refreshControlTower()` returns early
without it, so Control Tower sat on its skeleton forever once it became a tab.
This was a **latent bug the other fixes exposed** — previously the pane was
destroyed before it could get that far.

### 5. Navigation deactivates absorbed panes too

`nav()` swept `document.querySelectorAll('.pane')`, but absorbed panes are
`.ws-body`. A stale `active` meant `refreshControlTower()` kept polling every
5 seconds forever after navigating away. Now `.pane, .ws-body`.

### 6. The workstation redirect no longer renders the tab twice

`nav('system')` redirected to the host and called `showWorkstationTab()`
immediately. That render was always discarded: `nav(host)` waits for the host's
async renderer, rebuilds the workstation and opens the wanted tab itself. Now
the redirect records the tab via `setWorkstationTab()` and lets the host's
navigation open it.

---

## Results

| | before | after |
|---|---|---|
| Console errors across all 68 panes | **16** | **0** |
| Broken workstations | **7 of 11** | **0** |
| Absorbed panes lost from the DOM | **28** | **0** |
| Redundant API calls (10 sampled panes) | **25** | **7** |
| Blank/thin panes | 0 | 0 |

The remaining 7 duplicate calls are the legitimate second render of an
absorbed pane: the registry renders it, the host's async renderer then replaces
the host's innerHTML, and the pane is rendered again into the rebuilt
workstation. Removing that second render is what broke 13 panes below.

---

## Mistakes made and corrected

### Extending the dedupe window past one tick blanked 13 panes

To also suppress `showWorkstationTab()`'s render, the window was held open
across `nav()`'s await. That suppressed **the render that actually matters**.
When an absorbed pane is opened the registry renders it, the host's async
renderer destroys that DOM, and only then is the pane rendered into the
rebuilt workstation. The second render is required, not redundant. Reverted,
and `test_dedupe_window_is_not_held_open_across_awaits` now pins it.

### Making `beginNavRender` non-idempotent made things worse

An intermediate version reset state on every call. Since nav() is wrapped 14
times, an inner wrapper tore down the window the outermost navigation still
needed: duplicates went from 8 panes to **32**.

### My measurement probe was wrong, and briefly convinced me the fix had failed

The probe counted renderer calls by wrapping `window.renderX` — which wraps
*outside* the dedupe layer, so it counted suppressed calls as if they had run.
It reported "32 panes still rendering twice" against a build that was working
correctly. Switched to counting **actual network requests**, which cannot be
faked by instrumentation, and confirmed 25 → 7 against a stashed baseline.

A second probe bug: it measured "the first visible `[id^=pane-]`", which for
an absorbed pane is the workstation **host**, not the pane. That produced
three phantom "blank pane" regressions (`github`, `gitai`, `deploy`) that were
rendering perfectly — `pane-deploy` had 2,358 characters of content.

### A self-recursive setter, shipped for one build

Consolidating `_activeWorkstationTab` behind one owner, a string replacement
hit the wrong occurrence and produced:

```js
window.setWorkstationTab = function (host, pane) {
  window.setWorkstationTab(host, pane);   // calls itself
};
```

Caught immediately by the browser walk: `RangeError: Maximum call stack size
exceeded`, 80 errors, 11 blank panes.

### A test that proved nothing

`test_absorbed_panes_keep_active_in_sync_with_visibility` searched the whole
of `showWorkstationTab` for `classList.toggle('active', on)` — and **passed
with the fix removed**, because the tab *button* loop a few lines below
contains an identical call. Rescoped to the pane-body loop; now fails
correctly.

---

## Tests

`tests/unit/test_114_duplicate_render.py` — 13 tests. Every fix proven to fail
without it:

| Reverted fix | Failing test |
|---|---|
| nav() no longer awaits the host renderer | `test_nav_waits_for_an_async_host_renderer_before_building` |
| `initWorkstation` back to the flag | `test_init_workstation_checks_the_dom_not_a_flag` |
| `active` not synced on absorbed panes | `test_absorbed_panes_keep_active_in_sync_with_visibility` |
| deactivation sweeps `.pane` only | `test_navigation_deactivates_absorbed_panes_too` |
| eager `showWorkstationTab` in the redirect | `test_workstation_redirect_does_not_render_the_tab_twice` |
| dedupe hook removed from nav() | `test_nav_opens_the_dedupe_window` |
| chunk loader stops re-wrapping | `test_lazy_chunks_get_deduplicated_too` |
| null guards removed | `test_crashing_renderers_no_longer_assume_their_pane_exists` |

Assertions strip comments first, so they cannot match their own explanation —
a trap hit 11 times earlier in this review.

### A pre-existing test updated, not deleted

`test_38_navigation_and_settings_integrity.py` required the literal
`window.showWorkstationTab(wsHost, pane)` on the redirect path — pinning fix 6
in place as if it were correct behaviour. Updated **in place with an
explanation**: the requirement (an absorbed id must reach its tab) is
unchanged, so it now asserts the behaviour rather than the specific call that
used to implement it.

---

## Verification

- **Full suite: 3,151 passed / 2 skipped (unit) + 1,044 passed / 17 skipped
  = 4,195 passing, 0 failing.**
- Real Chromium, all 68 panes: **0 errors, 0 blank panes, 0 broken
  workstations** — better than the pre-existing baseline on every axis.
- `ruff`, `lint_inline_handlers`, `lint_globals` clean.

## Not taken

- The 14 nav() wrappers still exist and still contain their redundant renderer
  calls; they are now harmless no-ops. Deleting them is ~40 edits across 10
  files where each wrapper also does unrelated work — worth its own batch.
- The remaining 7 duplicate API calls are inherent to rendering a pane, having
  its host wipe the DOM, and rendering it again. Fixing that means the host
  renderer should not replace innerHTML it does not own, which is part of the
  `01-app-core.js` refactor.
