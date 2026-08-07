# 39 — The focus ring that never rendered, and the missing skip link

Autonomous hunt, batch 26. Both findings are things **axe-core structurally
cannot detect**, which is why a clean static a11y suite had been hiding them.

---

## 1. Ten controls had no focus ring at all

Measured in Chromium by pressing **real Tab** and reading the computed style
while the element was still focused: **10 of 29 tab stops** matched
`:focus-visible` and rendered no ring — outline width 0, no box-shadow.

Among them the three most-used controls in the product:

| Control | What it is |
|---|---|
| `TEXTAREA#chat-input` | the main prompt box |
| `BUTTON#chat-send` | the send button |
| `SELECT#chat-model-select` | the model picker |
| `INPUT#chat-sessions-search`, `#sidebar-toggle-btn`, `#new-folder-btn`, `#folder-settings-btn`, `#view-folders-btn`, `#view-date-btn`, `#history-toggle-btn` | |

### Cause: a specificity loss

All three stylesheets declare the right rule:

```css
*:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
```

That selector is specificity **0-0-1-0**. Seventeen rules set `outline: none`
to hide the ugly default ring on inputs, and several of those are **ID**
selectors at **1-0-0-0**:

```css
#chat-input { flex:1; background:transparent; border:none; outline:none; }
```

An ID beats the universal focus rule outright, so the suppression won and the
control had **no visible focus state at any time**. WCAG 2.4.7.

A tab stop with no ring is worse than no tab stop — the user's focus is
somewhere they cannot see. A keyboard user tabbing into the chat box literally
could not tell they had arrived.

### Why the existing tests missed it

`axe-core` does not evaluate `:focus-visible` styling — it cannot, without
synthesising real keyboard focus on every node. The existing `test_93` asserts
such a rule **exists** and matches a focused element. It does. **Nothing
checked whether it wins.**

### The fix

One rule appended last, with enough specificity to beat an ID selector, setting
**only** outline/outline-offset and **only** under `:focus-visible`, so mouse
interaction is unaffected and the `outline: none` declarations keep doing their
job in the unfocused state. A matching `box-shadow` guarantees the ring stays
visible where an outline would be clipped by a container edge.

**Verified 10 → 0 with the tab-stop count unchanged at 29 before and after**,
so no tab stops were lost to the change.

---

## 2. No skip-to-content link

A keyboard user tabbed through **12+ chrome controls** — logo, command palette,
Simple/Power mode, shortcuts, share, notifications, settings, profile, then the
entire sidebar — before reaching the content, **on every navigation**, because
this is a single page and the chrome never unmounts. WCAG 2.4.1 (Bypass
Blocks). `grep` for a skip link returned zero.

Added two, as the first elements in `<body>`: *Skip to main content* → `#content`
and *Skip to navigation* → `#sidebar`. Off-screen until focused (not
`display:none`, which would make them unfocusable — the most common way this
pattern is got wrong), and `#content` gained `tabindex="-1"` so it can actually
receive focus.

`window.skipTo()` moves focus explicitly rather than relying on the bare
`href="#content"`, which scrolls but leaves focus in the chrome — so the next
Tab would go straight back through everything the user just asked to skip.

Verified end-to-end: first tab stop, becomes visible at `top: 8px`, Enter moves
focus to `#content`, and the following Tab lands **inside** the content region.

---

## Two tests I wrote and then deleted

Worth recording. `test_the_most_used_controls_specifically_show_a_ring` and
`test_the_focus_rule_can_beat_an_id_selector` **passed against the broken build
as well as the fixed one**, so they asserted nothing:

- the first used `el.focus()`, which does not satisfy `:focus-visible`, so it
  only ever proved the element existed;
- the second built a synthetic probe and then never asserted on the result.

A test that cannot fail is worse than no test — it makes the suite look like it
covers something it does not. Both removed, with a comment in the file saying
why.

## A measurement error I corrected mid-hunt

My first two probes reported **20**, then **21**, then **11** ringless stops,
and the tab-stop count wandered between 40 and 29. The cause was reading the
computed style *after* moving focus on, so the values described the post-blur
state. Reading the ring in the **same `evaluate` call, while the element is
still focused**, made it reproducible: 29 stops, 10 ringless, identical across
runs. The number in this document is the one that reproduces.

## Tests

`tests/e2e_browser/test_e2e_browser_09_focus_ring.py` — 5 tests, all pressing
real keys, since `.focus()` cannot satisfy `:focus-visible`.

**Proven to catch the bugs: with the stylesheet, markup and handler reverted,
3 of 5 fail** (the other 2 are visibility guards that correctly hold either
way).

## Regression status

| Suite | Result |
|---|---|
| `tests/unit` | **3005 passed, 2 skipped, 0 failed** |
| `regression` + `system` + `integration` + `uat` | **1044 passed, 17 skipped, 0 failed** |
| axe-core a11y sweep + focus ring | **13 passed** |
| ruff · inline-handler · globals linters | pass |
