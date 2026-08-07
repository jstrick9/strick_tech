# 46 — Keyboard operability for clickable non-controls

**Status:** shipped
**Batch:** 33
**Scope:** `frontend/js/00-delegate.js`,
`tests/unit/test_117_keyboard_operability.py`

---

## The finding

Walking all 68 panes and counting elements that carry `data-act-click` but are
neither a native control nor given `tabindex`/`role`:

```
884  DIV.agent-row
  6  DIV (anonymous)
  3  DIV.file-row
  1  DIV.sdk-pack-card
  1  STRONG
```

`.agent-row` is how you choose which agent to chat with. It was **mouse-only**:
unreachable by Tab, not announced as a control by screen readers, and
inoperable by keyboard, switch or voice input. That is a core interaction of
an AI product, not a corner of the UI. `file-row` (opening a file in Studio)
and `sdk-pack-card` were the same.

---

## The fix

`00-delegate.js` promotes any non-native `data-act-click` element to
`tabindex="0"` + `role="button"`, and activates it on Enter/Space.

Applied centrally rather than at ~890 render sites. A rule applied at one call
site is a rule the next call site forgets — the "second door" pattern this
review has hit six times. A `MutationObserver` (coalesced to one pass per
burst) re-applies after renders, because panes rebuild their `innerHTML`
constantly and a one-shot pass at load would cover almost nothing.

**Result: 884 keyboard-unreachable controls → 0.**

### Three exclusions, each load-bearing

| Excluded | Why |
|---|---|
| Native controls (`BUTTON`, `A`, `INPUT`, …) | A `<button>` already turns Enter/Space into a real click. A synthetic one fires the handler **twice** per key press. |
| Modal backdrops (`data-click-self="1"`) | They use `data-act-click` for click-outside-to-close. They are not controls; promoting them puts a focus ring on the dimmed background of every dialog. |
| Elements with an existing `tabindex` or non-button `role` | Author intent wins. Relabelling a `tab` or `menuitem` as a button would be worse than leaving it. |

Verified live: Enter fires the handler exactly once, Space fires exactly once,
a native `<button>` produces exactly one click event per Enter, and zero
backdrops became tab stops.

---

## A real double-fire I introduced, caught by an existing test

The full suite failed on `test_93_keyboard_accessibility.py`:

```
AssertionError: the polyfill is still needed for div[role=button]
assert 2 == 1
```

An older shim in the same file already re-dispatches a real click on
Enter/Space for elements marked `data-self-click="1"`. My new keydown path
activated them **again** — the exact double-fire I had been careful to avoid
for native controls, reintroduced for a different category.

Fixed by deferring to the existing shim. Now pinned twice: by the pre-existing
test, and by `test_self_click_elements_are_not_activated_twice` in the new
file, both verified to fail without the guard.

This is the value of the existing suite doing its job — the bug was invisible
in my own probes because I only measured `.agent-row`, which is not a
`data-self-click` element.

---

## Two measurement errors of mine, corrected

Worth recording because both produced confident-looking findings that were
wrong.

### 1. "The focus ring is missing on `.agent-row`"

I read `getComputedStyle` after calling `.focus()` programmatically.
**Programmatic focus does not match `:focus-visible`**, so every element looks
ring-less that way — including `#chat-send`, which demonstrably has one.

`docs/module-reviews/39-focus-visible.md` records this exact trap from batch
26. I repeated it.

### 2. "The ring is still missing even with a real Tab"

With a real Tab press `.agent-row` reported `outline: 0px` — but `.agent-row`
has `transition: var(--transition)` (0.15 s), and I was reading **mid
transition**. After a 600 ms settle:

```
outlineWidth: 2px
boxShadow:    rgba(99,102,241,0.15) 0 0 0 4px
```

Re-measured across the whole tab order with settle time: **25 distinct tab
stops, 0 without a visible ring.** No fix was needed; the keyboard
reachability fix stands on its own.

---

## Tests — `tests/unit/test_117_keyboard_operability.py` (10)

Each exclusion proven to fail without it:

| Reverted | Failing test |
|---|---|
| Native-control exclusion | `test_native_controls_are_excluded_from_promotion` |
| Backdrop exclusion | `test_modal_backdrops_do_not_become_tab_stops` |
| `MutationObserver` re-application | `test_promotion_reapplies_after_renders` |
| `data-self-click` deferral | `test_self_click_elements_are_not_activated_twice` **and** the pre-existing `test_93` |

`test_no_render_site_needs_to_opt_in` asserts the fix is driven by a selector
over the whole document and that the string `agent-row` does **not** appear in
the delegate — so the fix stays generic rather than becoming a list of the
classes that happened to be broken today.

---

## Verification

- **Unit: 3,188 passed / 2 skipped.**
- Real Chromium: 884 → **0** keyboard-unreachable clickable elements; all 68
  panes render with 0 errors; 25/25 tab stops show a focus ring.
- `ruff`, `lint_inline_handlers`, `lint_globals` clean.

### A pre-existing failure, confirmed not mine

`tests/integration/test_flow_04_search_docs.py::TestWebSearchHistory` fails 5
tests with `httpx.ReadTimeout`. Confirmed pre-existing by `git stash` +
re-run: **identical 5 failures on the unmodified tree.** The file contains
zero references to the frontend. These are live-network calls timing out in
this sandbox, not a code fault.
