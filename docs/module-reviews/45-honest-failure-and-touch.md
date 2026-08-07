# 45 — Fabricated data, persistent failure state, and touch targets

**Status:** shipped
**Batch:** 32
**Scope:** `frontend/js/28-kanban.js`, `frontend/js/00-connection-status.js`
(new), `frontend/js/00-csrf.js`, `frontend/js/11-ux-accessibility.js`,
`frontend/js/44-websearch.js`, `frontend/index.html`,
`frontend/styles-redesign.css`, `tests/unit/test_116_honest_failure_ux.py`

Found by two probes: forcing every `/api/` call to return HTTP 500 and walking
the panes, and measuring every interactive control at phone width.

---

## 1. Kanban fabricated tasks during an outage

`kanbanFetchTasks()` fell back to `kanbanGetSampleTasks()` on **both** the
non-ok branch and the catch:

```js
} else {
  kanbanTasks = kanbanGetSampleTasks();
} catch (e) {
  kanbanTasks = kanbanGetSampleTasks();
}
```

With the API down the board rendered **"6 tasks"** of invented work. A user
could drag, edit or delete cards that do not exist, and would reasonably
conclude that real tasks had been lost.

This is the worst class of the "fabricated data" pattern catalogued in
`31-fabricated-data.md`: not merely unhelpful, actively misleading about the
state of the user's own work.

**Fixed.** A failed load now clears the list, records the error, and renders:

> ⚠️ **Couldn't load your tasks**
> Your tasks are safe — this is a connection problem, not lost work. (HTTP 500)
> `↻ Try again`

Verified live: fabricated tasks **6 → 0**, count label reads `unavailable`,
message carries `role="alert"`. The 969-byte generator was deleted as dead
code once nothing referenced it.

---

## 2. A persistent signal that the app is degraded

### The correction I had to make mid-batch

My first framing was that **334 fetch sites across 33 files** silently resolve
failure to an empty collection (`r.ok ? r.json() : {goals: []}`), leaving the
user with no indication of an outage.

That was **wrong**, and I want it on the record. `00-net-feedback.js` already
wraps `fetch` and toasts on 5xx and transport failures. My probe only read
pane *text*, so it never saw the toasts. I had proposed a fix for a problem
that was already partly solved.

### The gap that is actually real

Those toasts **auto-dismiss after 6 seconds**. Measured against a live server
with every API returning 500, then waiting ten seconds:

```
Skills pane:  "⚡ Skills Hub … All (0)"
mentions any failure:  False
toasts remaining:      1 (unrelated)
```

A user who looks away, or arrives at a pane after the burst, sees a calm empty
state indistinguishable from an account with nothing in it. Transient
notification and persistent state are different jobs.

**Fixed** with `00-connection-status.js`: when API failures cluster
(3 within 8 s), one dismissible banner appears —

> Some data couldn't load. Your work is safe — this looks like a connection
> problem. `↻ Retry` `✕`

Design decisions worth recording:

- **Threshold, not per-request.** A single endpoint failing is routine
  (an unconfigured feature, an optional service). Firing on one would train
  users to ignore the banner.
- **5xx / 429 / 408 only.** A 404 usually means the client asked for something
  that legitimately is not there. `/api/secrets/get` is explicitly excluded —
  it 404s constantly when a key is not configured.
- **Any success clears the tally**, so unrelated failures spread over hours
  never accumulate into a false alarm.
- **Retry re-renders the current pane** rather than reloading the document,
  which would discard unsaved input.
- **`role="status"`, not `alert`** — the app is still usable, so it should not
  interrupt a screen-reader user mid-sentence.

### A second correction: I nearly added a third `fetch` wrapper

The first implementation wrapped `window.fetch` itself.
`scripts/lint_globals.py` failed the build, and it was right to: the app
already layers **two** wrappers by design — `00-csrf.js` attaches tokens, then
`00-net-feedback.js` reports failures on top of it, each marked
`intentional-override`. A third would deepen a chain where load order silently
decides behaviour.

Rewritten so the watcher exposes `observeResponse` / `observeNetworkError`
hooks that the existing CSRF wrapper calls. Both call sites are wrapped in
`try/catch` so a bug in the watcher can never break an API request.

---

## 3. Touch targets

At 390 px, **48 interactive controls measured under the 44×44 CSS px minimum**
(WCAG 2.5.5, Apple HIG). The notification bell and settings gear were 27×32 —
genuinely hard to hit, with neighbours close enough that a miss activates the
wrong control.

Fixed with rules scoped to `@media (pointer: coarse)`, so the desktop layout —
where density was deliberately tuned and a mouse is precise — is untouched.
This is a hit-area change, not a visual one: padding grows, icon and font
sizes do not.

| | before | after |
|---|---|---|
| Targets < 44 px (390 px phone) | 48 | **6** |
| Horizontal overflow | 0 | 0 |
| Desktop `pointer: coarse` matches | — | `false` (rules inert) |

**A regression I introduced and fixed:** widening the top-bar buttons pushed
`#topbar-actions` past the viewport. Two causes — my selector was
`.topbar__actions`, a class that does not exist in this markup, so the gap
rule silently did nothing; and the row was `nowrap`. Now targets the real
`#topbar-actions` and allows wrapping. Overflow back to 0.

The remaining 6 are inside dense generated tables where a blanket rule would
change layouts this batch is not trying to touch.

---

## 4. Accessibility gaps

| Finding | Before | After |
|---|---|---|
| `<h1>` on the page | **0** | 1 |
| Dialogs with no accessible name | 3 | **0** |
| Inputs with no `autocomplete` | 6 | **0** |
| Destructive action with no confirmation | 1 | **0** |

**No `<h1>` at all** — assistive tech reported no top-level heading and
heading navigation began at `h2` with nothing above it. The app title is now
the `h1`. Verified pixel-identical before and after: **163×23 at (54, 16)** in
both builds, because the parent `.logo` is a flex container that blockifies
children either way.

**A nested dialog.** `setupModalAccessibility()` marked every `.modal` as
`role="dialog"`, including panels already inside a dialog backdrop — a dialog
within a dialog, announced twice and with no name of its own. It now defers to
the outer element and adopts the panel's heading as `aria-labelledby`. Focus
trapping and Escape verified still working, no recursion.

**`deleteHistoryEntry()`** removed a search on a single click with no prompt
and no undo, unlike every other delete in the app. Now confirms via
`gmDanger`. (I got the signature wrong first — it is
`(title, body, confirmLabel)`, not an options object — caught before commit.)

---

## Tests — `tests/unit/test_116_honest_failure_ux.py` (17)

Proven to fail before the fix:

| Reverted | Result |
|---|---|
| Kanban fabricates again | 1 failed |
| Banner fires on a single failure | 1 failed |
| Delete without confirmation | 1 failed |

`test_no_module_substitutes_sample_data_on_a_failure_path` guards the
**pattern**, not the instance: introducing a *new* fabrication in a different
file (`40-loops.js`) was verified to fail it.

`test_the_banner_complements_the_transient_toasts` records why the banner
exists given the toasts already do, and asserts the 6-second auto-dismiss that
makes it necessary — so if toasts ever become persistent, the test points at
the redundancy rather than silently keeping both.

---

## Verification

- **Full suite: 3,178 passed / 2 skipped (unit) + 1,044 passed / 17 skipped
  = 4,222 passing, 0 failing.**
- Real Chromium, all 68 panes: **0 errors, 0 blank panes, 0 broken
  workstations.**
- Banner verified in three states: absent when healthy, present during an
  outage, still present after the toasts expire, gone after dismiss.
- `ruff`, `lint_inline_handlers`, `lint_globals` all clean.
