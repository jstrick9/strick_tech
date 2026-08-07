# 44 — Removing dead coupling in `01-app-core.js`

**Status:** shipped
**Batch:** 31
**Scope:** `frontend/js/01-app-core.js`, `scripts/split-plan.json`,
`tests/unit/test_115_core_refactor.py`, `tests/unit/test_113_*` (updated)

The refactor flagged at the end of `42-code-splitting.md`: free the modules
that `01-app-core.js` was pinning into the eager bundle.

---

## What was holding 23 modules (462 KB) in the boot path

Three constructs. **None of them did anything useful.**

### 1. Eighteen redundant renderer calls

The stacked nav() wrappers each re-invoked renderers that
`MASTER_PANE_REGISTRY` had already run:

```js
if (pane === 'mcp')       renderMCP();
if (pane === 'loops')     renderLoops();
if (pane === 'dashboard') renderDashboard();
...
```

Batch 30 established these were exact duplicates of registry entries — all
verified in a live browser — and made them harmless no-ops via render
deduplication. This batch deletes them. A bare identifier call is a hard
dependency even inside a function body, because an undeclared binding throws
`ReferenceError`, so each one pinned its module into the eager bundle.

**Freed 9 modules.**

### 2. A `wrappedRenders` block that was a pure no-op

```js
const wrappedRenders = {
  dashboard: typeof renderDashboard === 'function' ? renderDashboard : null,
  ...   // nine of these
};
Object.entries(wrappedRenders).forEach(([key, fn]) => {
  if (fn && !window[`render${...}`]) window[`render${...}`] = fn;
});
```

It copied `renderX` onto `window.renderX` "to ensure they exist". They already
existed: these are plain global scripts, so a top-level
`function renderDashboard(){}` **is** `window.renderDashboard`. Verified in a
live browser — all nine were `typeof 'function'` on `window` before the block
ran, so every `if` was false and the loop assigned nothing.

It was not harmless, though. Capturing those references *during boot* is
exactly what makes a module undeferrable: the code-splitting analysis
correctly refuses to lazy-load a module whose names are read at load time,
because the captured value would be `null`.

**Deleting a no-op freed 9 more modules.**

### 3. Four `foo?.()` calls on bare identifiers

```js
action: () => { nav('integrations'); setTimeout(() => switchIntTab?.('rules'), 300) }
action: () => scaffoldIntegration?.('stripe-payments')
```

`?.()` *looks* like it tolerates a missing function, and for a missing **value**
it does. But optional chaining guards `null`/`undefined`, not an absent
**binding**. Verified directly in node:

```
> undeclaredThing?.()
ReferenceError: undeclaredThing is not defined
```

Only `window.foo?.()` is safe, because that is a property read on an object
that exists. These four were command-palette actions — precisely the code that
runs before a lazy chunk has loaded. Rewritten to the `window.` form.

**Freed 3 more modules.**

---

## Results

| | batch 29 | batch 31 |
|---|---|---|
| Lazy modules | 18 | **36** |
| Deferred bytes | 504,456 | **797,211** (38.5% of the frontend) |
| Core bundle (brotli) | 220,456 B | **182,481 B** |
| Critical path before DOMContentLoaded | 223 KB | **185 KB** |
| Redundant API calls (10 sampled panes) | 7 | **3** |

Cumulative across batches 28–31, measured in real Chromium on a 150 ms-RTT
link: **DOMContentLoaded 13,667 ms → 3,042 ms**, and the frontend went from
**79 uncompressed requests / 2.0 MB** to **3 requests / 185 KB** on the
critical path.

Boot behaviour verified directly: `nav`, `toast`, `#chat-input` and `#chat-send`
are all live before any chunk loads, all 68 registry entries are present, and
`renderKanban` is `undefined` until you open Kanban — at which point the chunk
arrives and the pane renders 1,313 characters of content.

---

## Five modules still eager, for real reasons

| Module | Why |
|---|---|
| `04-workflow-specs.js` | `nav()` itself lives here |
| `36-dashboard.js` | `renderDashBody = function(d){...}` wraps it at load time |
| `26-swarm.js` | `loadSwarmHistory` assigned at load time |
| `27-galaxy.js` | `gxGraph` is module-level state read at load time |
| `23-plugin-marketplace.js` | `32-collaboration.js` reads it at load time |

`test_remaining_blocked_modules_are_documented` pins this set, so a module
silently re-coupling into the boot path fails CI.

---

## Tests

`tests/unit/test_115_core_refactor.py` — 9 tests. Each fix proven to fail
without it:

| Reverted | Failing tests |
|---|---|
| One duplicate renderer call restored | 3 |
| `wrappedRenders` restored | 3 |
| One bare `?.()` call restored | 2 |

### A mistake in my own test, caught by the test

The first draft asserted `36-dashboard.js` was freed by deleting the no-op. It
is not — it is still blocked by a *separate* load-time wrapper
(`renderDashBody`). The test failed, which is what a good test does. Corrected,
with the reason recorded in the test body rather than quietly dropped.

### Two batch-29 tests updated, not deleted

`test_113_code_splitting.py` had two tests that pinned this batch's dead code
in place as though it were correct behaviour:

- `test_modules_called_bare_from_nav_are_not_deferred` listed the five modules
  blocked by the redundant calls. Keeping it would have required keeping the
  duplicate calls. The **rule** still needs guarding, so it now asserts
  against a synthetic fixture instead of whichever modules happen to be
  affected today.
- `test_modules_referenced_during_boot_are_not_deferred` asserted on
  `const wrappedRenders`. Repointed at `renderDashBody`, which is still a
  genuine load-time capture.

Both were re-verified to still fail when their underlying analysis rule is
removed, so the update did not weaken them.

---

## Verification

- **Full suite: 3,160 passed / 2 skipped (unit) + 1,044 passed / 17 skipped
  = 4,204 passing, 0 failing.**
- Real Chromium, all 68 panes: **0 errors, 0 blank panes, 0 broken
  workstations.**
- Command-palette actions exercised from a cold start (chunks not yet loaded):
  `switchIntTab`, docs tab, `scaffoldIntegration`, `renderKanban` — all fine,
  0 page errors. This is the scenario the `window.` rewrite protects.
- `ruff`, `lint_inline_handlers`, `lint_globals` clean.

## Not taken

- The 14 nav() wrappers still exist. They no longer contain redundant renderer
  calls, but each still wraps `window.nav` to do other work. Collapsing them
  into one is a larger structural change.
- The last 3 duplicate API calls are inherent to rendering a pane, having its
  workstation host wipe the DOM, and rendering it again. Fixing that means a
  host renderer should not replace innerHTML it does not own.
