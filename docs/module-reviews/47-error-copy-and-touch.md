# 47 — Error copy, and touch targets done properly

**Status:** shipped
**Batch:** 34
**Scope:** `frontend/js/00-error-copy.js` (new), `frontend/styles-redesign.css`,
`frontend/js/31-control-tower.js`, `frontend/js/34-test-generator.js`,
`frontend/js/03-features-a.js`, and 9 pane modules,
`tests/unit/test_118_copy_and_touch.py`

Two items: the copy/wording seam from batch 26's list that was never explored,
and the touch targets I reported as fixed in batch 32 but had not properly
fixed.

---

## Correction first: batch 32's touch fix was weaker than I reported

I said "48 → 6 undersized targets". That number came from measuring **only the
landing pane**. The rule I wrote was an allow-list of class names
(`.icon-btn`, `.nav-item`, `.btn-sm`, …), so it covered exactly the controls I
had happened to look at.

Auditing **all 68 panes** at 390 px found **41 distinct undersized control
types** it missed, including:

```
477x  BUTTON (no class)      66x20   "✨ Simple"
 28x  .kanban-card-action    20x20   "✏️"
 14x  .hook-toggle            4x4
  4x  .steer-toggle           4x4
  1x  .chat-send-btn         36x36   "➤"   ← the primary action of the product
```

An allow-list also guarantees the *next* control added is undersized again.

### The structural rule

```css
@media (pointer: coarse) {
  button, a[href], [role="button"], [role="tab"], select, summary {
    min-height: 44px;
    min-width: 44px;
  }
  /* inline links keep paragraph flow */
  p a[href], li a[href], .prose a[href] { min-width: 0; display: inline; }
  /* documented opt-out */
  .tight-target { min-height: 0; min-width: 0; }
}
```

**A second mistake caught mid-fix:** my first structural pass set only
`min-height`, which left **20 control types still too narrow** — a 12 px-wide
`+` button that is 44 px tall is still unhittable. Both dimensions are now
covered, and `test_both_dimensions_are_covered` pins it.

| | before batch 32 | after batch 32 | now |
|---|---|---|---|
| Undersized types (all 68 panes) | 41+ | 41 | **6** |
| Page horizontal overflow | 0 | 0 | **0** |

The remaining 6 are checkboxes at 24×24 (the accepted inline exception, still
enlarged from the platform default of ~13 px) and full-width download links
whose *height* is 21 px inside a text row.

**Layout damage checked, not assumed.** All 68 panes at three viewports: max
horizontal overflow **0 px everywhere**. Panes with internally-scrolling wide
children went 31 → 30 (slightly better than baseline). Desktop verified inert:
`matchMedia('(pointer: coarse)')` is `false` at 1440 px.

---

## The copy pass

### What a user actually saw

Forcing every `/api/` call to return HTTP 500 and walking all 68 panes, twelve
rendered developer text where an explanation belongs:

```
templates   Failed to load templates: Templates API: HTTP 500
galaxy      Load failed — HTTP 500
obsidian    Error loading Obsidian status: HTTP 500
dashboard   Failed to load analytics (HTTP 500)
control     runs.filter is not a function
testgen     files.filter is not a function
profiler    DB size: undefined KB
```

"HTTP 500" tells a developer where to look and everyone else nothing.
`runs.filter is not a function` is not a message, it is a stack frame.

### Two of these were real crashes, not wording

`31-control-tower.js` and `34-test-generator.js` called `.filter()` directly
on a parsed response. A failed request returns an error **object**, so the
call threw and the raw `TypeError` became the user's explanation. Both now
check `response.ok` and coerce to an array before using array methods.

`03-features-a.js` printed `DB size: undefined KB` — now `unavailable`.

### `humanError()`

One helper rather than rewriting ~110 call sites by hand. It turns a thrown
error or failed `Response` into a sentence, in a fixed priority order:

1. **What failed, in the user's terms** — "Couldn't load your templates."
2. **What it means** — status codes translated to consequences: 401 → "You
   need to sign in again", 429 → "Too many requests at once — wait a moment",
   409 → "Someone else changed this first."
3. **Reassurance where relevant** — "Nothing was lost."
4. **Technical detail preserved but demoted** — trailing, in parentheses, so
   a bug report still has it without it being the headline.

Runtime noise (`is not a function`, `Cannot read propert…`, `Unexpected
token`) is recognised and replaced with "The response from the server was not
what the app expected", because a user gains nothing from knowing a property
was undefined.

**Result, verified live: 12 panes showing jargon → 4**, and all four remaining
are the *demoted* detail in parentheses after a plain-English sentence, which
is the intended design:

```
Couldn't load your templates. The server ran into a problem. Nothing was lost.
  (Templates API: HTTP 500)
```

### The generic test found 4 more the probe missed

`test_no_pane_leads_with_a_raw_http_status` scans for `Failed to load … HTTP`
as a *headline* and caught four sites the browser probe never reached, because
they need a specific tab or action: `08-replay-collab.js`,
`22-integrations.js`, `43-browser-agent.js`, `45-leaderboard.js`. Fixed rather
than the test weakened.

---

## Tests — `tests/unit/test_118_copy_and_touch.py` (16)

Each fix proven to fail when reverted:

| Reverted | Failing test |
|---|---|
| Control Tower array coercion | `test_control_tower_survives_a_non_list_response` |
| `min-width` (height-only pass) | `test_both_dimensions_are_covered` |
| Profiler `undefined` guard | `test_profiler_does_not_print_undefined` |

`test_desktop_is_untouched` parses the media query's brace depth to prove no
touch sizing leaked outside `pointer: coarse` — a text search would pass even
if the rule had escaped the block.

---

## Verification

- **Full suite: 3,205 unit + 655 regression/system/uat + 384 integration
  = 4,244 passing, 0 new failures.**
- Real Chromium, all 68 panes: **0 errors, 0 blank panes.**
- `ruff`, `lint_inline_handlers`, `lint_globals` clean.

**Pre-existing failure, unchanged:** the same 5
`test_flow_04_search_docs.py::TestWebSearchHistory` tests fail with
`httpx.ReadTimeout`, confirmed in batch 33 by `git stash` + re-run to be
identical on an unmodified tree. Live-network calls timing out in this sandbox.

---

## Not taken

- **The remaining ~100 `humanError`-eligible call sites.** The 13 that were
  demonstrably user-visible are converted; the rest are toasts whose current
  wording is already adequate, or developer-facing console output. Converting
  them wholesale would be churn without evidence.
- **The 6 remaining undersized targets** — checkboxes at 24×24 and inline
  download links. Enlarging checkboxes further changes their visual weight in
  dense tables, which needs a design decision rather than a CSS rule.
