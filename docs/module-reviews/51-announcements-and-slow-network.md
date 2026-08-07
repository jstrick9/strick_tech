# 51 — Screen-reader announcement, and slow/flaky networks

**Status:** shipped
**Batch:** 38
**Scope:** `scripts/audit/announcements.py` (new),
`scripts/audit/slow_network.py` (new), `frontend/js/49-goals.js`,
`frontend/js/33-webhooks.js`, `frontend/js/30-workspaces.js`,
`tests/unit/test_122_announcements_and_slow_network.py`,
`tests/unit/test_101_list_truncation.py` (updated)

Two more seams from the register, both never examined.

---

## Seam 1 — Screen-reader announcement

**Result: no defects.** The app already announces navigation and toasts
through a live region, and dialogs by moving focus into a named
`role=dialog`. This is now pinned by an audit so a refactor cannot silently
remove the only announcements the app makes.

### A correction to my own audit

The first version reported the command palette as `SILENT-ACTION` because
nothing landed in a live region when it opened. **That expectation was
wrong.** A screen reader announces a dialog when focus *moves into* an element
with `role=dialog` and an accessible name — no live region is involved.

Verified: opening the palette moves focus to `#palette-input` inside a dialog
labelled "Command palette", which is exactly the correct pattern. The audit
now checks focus and naming for dialogs, and live regions only for the
non-dialog actions where they apply.

Both checks proven to catch real regressions: removing the nav announcement
produced `SILENT-ACTION navigate to a pane`, and removing the palette's
`aria-label` produced `DIALOG-NO-NAME`.

---

## Seam 2 — Slow and flaky networks

Everything until now tested two states: server up, or a hard 500. Real
connections fail in messier ways, and those produce the worst UI.

With a 3-second delay, and separately with a body truncated mid-JSON:

```
NO-PENDING  goals       blank for 3.0s with no loading state
TRUNCATED   webhooks    "Unterminated string in JSON at position 29"
TRUNCATED   workspaces  "Unterminated string in JSON at position 29"
TRUNCATED   goals       renders 413 chars from a broken response,
                        saying nothing is wrong
```

### Three fixes

**Goals had no pending state.** Blank for the whole request, which is exactly
when a user clicks again — the behaviour that creates the duplicate
submissions batch 37 had to build idempotency to absorb. Now renders a
skeleton with `aria-busy` before its first `await`, and clears both when
content arrives. (Leaving `aria-busy` set would be its own bug: a screen
reader would announce the region as perpetually updating.)

**Webhooks and Workspaces leaked raw parse errors.** Their catch blocks passed
`e.message` straight through, so a dropped connection produced
`Unterminated string in JSON at position 29` where the explanation belongs.
Both now use `humanError()` and offer a retry.

**Goals rendered a dropped connection as "No goals match these filters."**
The same class as the Kanban fabrication in batch 32: `.catch(() => ({goals:
[]}))` makes a failure indistinguishable from an empty account. A user would
reasonably conclude their goals had been deleted. The failure is now recorded
and surfaced with a retry, checked *before* the empty-state branch.

---

## Four audit bugs found before the numbers could be trusted

Consistent with the register's rule — *when a probe disagrees with the app,
suspect the probe first.*

1. **`time.sleep()` in a sync Playwright route handler deadlocked the
   driver.** A sync handler runs on Playwright's own event loop; blocking it
   hangs everything. The audit ran for eight minutes before being cancelled.
   The delay is now injected by wrapping `fetch` inside the page, which also
   means only `/api/` is slowed and the page itself loads normally.

2. **It judged the whole message instead of the headline.** Trailing
   parenthesised detail is the documented design (`00-error-copy.js`), so the
   check flagged `Couldn't load your specs. Nothing was lost. (Unterminated
   string…)` as a raw parse error — punishing the fix rather than finding a
   bug. 6 findings → 3 once corrected.

3. **It measured the wrong element for workstation tabs.** `pane-goals` is
   hidden while its host renders, so measuring it reported "blank, no loading
   state" for a pane that was rendering correctly. The same trap that produced
   three phantom findings in batch 33.

4. **Then the fix for (3) went too far and blinded the audit.** Falling back
   to "the visible pane" whenever a pane was merely *empty* meant the host's
   content satisfied the check — removing the Goals skeleton produced **no
   finding at all**. Caught only by reverting a real fix and confirming the
   audit still fired. The fallback now applies only when the pane is genuinely
   hidden, and the workstation-tab case is reported as informational rather
   than counted.

Two `STUCK` findings also proved to be test artifacts: the audit navigates
panes back to back, so a previous pane's in-flight request left its skeleton
on screen. Verified against a healthy connection — Webhooks renders 953
characters with no skeleton — and the audit now re-checks before reporting.

---

## A pre-existing test my change broke

`test_101_list_truncation.py` loads `gmRenderList` into jsdom with a hand-built
stub of its module-level variables. Adding `_goalLoadError` meant the
extracted function referenced an undeclared name, threw, and **all 7 tests in
the file skipped with an opaque node error** — 2 skips became 5.

A skip is not a pass. The stub now declares the variable, with a comment
explaining why, and the file is back to 7 passing.

---

## Tests

`tests/unit/test_122_announcements_and_slow_network.py` — 12 tests, each fix
proven to fail when reverted:

| Reverted | Failing tests |
|---|---|
| Goals pending state | 1 |
| Goals swallows the failure | 1 |
| Webhooks leaks the raw parse error | 2 |

Two of my own assertions were wrong on first run and were fixed rather than
worked around: one searched for `time.sleep` in prose that deliberately
*mentions* it, the other used an over-escaped regex.

---

## Verification

- **Full suite: 3,241 unit + 655 regression/system/uat = 3,896 passing**,
  0 failures, back to the expected 2 skips.
- **All ten audits at 0.**
- `ruff`, `lint_inline_handlers`, `lint_globals` clean.

## Seam register

`screen-reader announcement` and `slow / flaky networks` move to **covered**.
Ten seams remain unexamined; large data volumes and browser back/forward are
next by expected value.
