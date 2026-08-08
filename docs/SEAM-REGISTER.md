# Seam register

**A seam is a dimension along which a bug can hide.** This file exists because
the list of "ways to look" was previously held only in my head, and died at the
end of every session — which is why the same class of bug kept being found
"again for the first time".

Every seam here is marked with how thoroughly it has been examined and whether
a **committed, runnable audit** covers it. A seam with no committed audit is
one that will silently rot.

---

## How to use this file

1. Pick a seam marked **NEVER** or **PARTIAL**, highest impact first.
2. Write a probe. When it finds something, **move the probe into
   `scripts/audit/`** — do not leave it in `/home/user`.
3. Fix what it found, with a test proven to fail beforehand.
4. Re-run `python3 scripts/audit/run_all.py --write-baseline` and commit the
   new number.
5. Update the row below.

**Definition of done for the whole review:** every seam has a committed audit,
every audit sits at its floor, and `test_120_audit_ratchet.py` passes. That is
verifiable. "No bugs exist" is not.

---

## Covered by a committed audit

| Seam | Audit | Baseline | Found this way |
|---|---|---|---|
| Failure paths (server 5xx) | `failure_honesty.py` | 0 | Kanban fabricating 6 fake tasks; `runs.filter is not a function`; 2 null-derefs shown to users |
| Recurring source patterns | `source_patterns.py` | 17 | Fabricated data on failure paths; raw errors as headlines; unguarded array access |
| Pane rendering & workstations | `pane_health.py` | 0 | 7 of 11 workstations destroyed on first open, 28 absorbed panes lost |
| Keyboard operability | `keyboard.py` | 0 | 884 mouse-only controls, incl. agent selection |
| Touch targets | `touch_targets.py` | 0 | 41 undersized types; a 6×12px link (1/27th of the minimum) |
| Responsive overflow | `responsive.py` | 0 | 611px horizontal document overflow on Goals |
| DOM semantics / a11y structure | `semantics.py` | 0 | No `<h1>` at all; 3 unnamed dialogs incl. a nested one |
| Concurrency / double-submit | `concurrency.py` | 0 | 5 concurrent identical POSTs created 5 records; `Idempotency-Key` ignored entirely |
| Screen-reader announcement | `announcements.py` | 0 | Verified nav, toasts and dialogs all announce correctly |
| Slow / flaky networks | `slow_network.py` | 0 | Goals blank 3s with no pending state; truncated responses leaked `Unterminated string in JSON`; Goals rendered a dropped connection as "no goals" |
| Browser back / forward | `history_navigation.py` | 0 | Every nav used `replaceState`; 4 navigations created 0 history entries and Back exited to `about:blank` |
| Large data volumes | `large_data.py` | 0 | A host re-render destroyed 7 workstations' tabs; Goals capped at 100 of 250 with no way to reach the rest |
| Session expiry / auth loss | `session_expiry.py` | 0 | Session tokens were **write-only** — `/login` issued a `ses_…` token that every endpoint rejected; every session was born already expired; no logout route existed; a dead session left a calm empty app with no signal and no way back in |
| Offline / reconnect | `offline_reconnect.py` | 0 | **Three** independent `offline` listeners each raised their own message simultaneously, giving contradictory advice: "your work is safe" alongside "changes will not be saved" |
| Long / adversarial input | `adversarial_input.py` | 0 | No XSS and no data loss (verified, not assumed); a 4,000-char title overflowed a 235px card by 1,900px while `documentElement.scrollWidth` stayed exactly 1440px |
| Timezones & dates | `timezones.py` | 0 | SQLite `CURRENT_TIMESTAMP` (141 defaults) emits no timezone designator; `new Date()` reads that as LOCAL time, so a task created that second rendered as **"in 3 minutes"** in UTC+8:45 |
| Reduced motion / high contrast / zoom 200% | `preferences.py` | 0 | Reduced motion clean; 2 indicators meaningful by colour alone; **5 containers overflowed a 640px viewport** — and the topbar's existing fix was inert inside `@media (pointer: coarse)`, which a zoomed desktop never matches |
| Print/export & multi-tab | `print_and_multitab.py` | 0 | Multi-tab clean; **8,808px of tasks printed as 600px** with nothing saying the rest existed; body printed at luminance 0.04 |

**All twelve audits are at 0.** `source-patterns` was cleared from 17 (six
unguarded array accesses, eleven raw-error headlines); the fixes and three
detector corrections are in `docs/module-reviews/50-*`.

---

## Examined, but no committed audit yet — **PARTIAL**

These were investigated in past batches. Without a committed audit they can
regress unnoticed.

| Seam | State | Next step |
|---|---|---|
| Duplicate rendering | Fixed (44 panes rendered 2–3× per nav) | Turn the render-counting probe into an audit |
| Redundant API calls | 25 → 3 on sampled panes | Fold the request counter into `pane_health.py` |
| Content Security Policy | Enforced through 3 phases | Assert the header + violation count |
| Bundle & code splitting | 79 → 3 requests, 185KB critical path | Add a size budget to the ratchet |
| Unsaved-work protection | `data-draft` on 12 of 14 long inputs | Audit every long-form input |
| List pagination | 8 growable lists fixed, 26 unbounded | Audit response sizes |
| Destructive confirmations | Spot-checked, one gap fixed | Enumerate all destructive actions |

---

## Never examined

**The register is empty. Every seam listed here has a committed audit sitting
at its floor.**

That is the stopping criterion agreed at the start of this effort, and it is
worth being precise about what it does and does not claim:

* It **does** mean every dimension anyone has thought to name has an
  instrument, that instrument is committed, and the ratchet fails the build if
  its number rises.
* It **does not** mean the application is free of bugs. Every new bug class
  found in this review required inventing a new way of looking; the register
  is a record of the ways of looking that exist, not a proof that no others
  are possible.

**Adding a seam is the normal way this document grows.** When a new class of
problem is found — by a user, by an incident, or by someone thinking of a
question nobody has asked yet — add a row below, write a probe, commit it to
`scripts/audit/`, register it in `run_all.py` and
`tests/unit/test_120_audit_ratchet.py`, and set a baseline.

Candidate seams that have been *considered* and judged low value for this
codebase, recorded so the thinking is not repeated:

| Considered | Why it was not pursued |
|---|---|
| Internationalisation / pseudo-localisation | The product ships one locale; RTL and emoji fidelity are already covered by `adversarial_input.py` |
| Browser matrix (Firefox / WebKit) | No non-Chromium build is available in this sandbox, so any result would be unverifiable — the one thing this review does not do |
| Load / soak testing | `large_data.py` covers realistic volumes; sustained load is an infrastructure question, not a UI seam |
| Screen-reader end-to-end with a real AT | `announcements.py` covers the ARIA contract; driving NVDA/VoiceOver is not possible headless |

| Seam | Why it matters | Cheap first probe |
|---|---|---|
| *(none outstanding)* | | |

---

## Deliberately out of scope

Recorded so they are not rediscovered as "gaps".

| Item | Why |
|---|---|
| 24×24 checkboxes | WCAG 2.5.8 (AA) compliant; the 44px row is the real target |
| Inline prose links | A 44px block inside a sentence breaks the line box |
| Browser E2E suite instability | Pre-existing, proven by stash+reproduce; a sandbox limitation |
| `TestWebSearchHistory` timeouts | 5 pre-existing failures, live-network calls in a sandbox |
| ~100 more `humanError` sites | Current wording adequate; converting is churn without evidence |
| 5 modules blocked from lazy-loading | Genuine load-time coupling; documented and pinned by a test |

---

## The measurement traps

Every one of these produced a confident finding that was **wrong**. They are
encoded in `scripts/audit/_harness.py` so no future probe has to remember them.

| Trap | What it cost |
|---|---|
| A CSS fix scoped to the wrong media feature | The topbar's wrapping rule sat in `@media (pointer: coarse)`; a desktop user at 200% zoom has a FINE pointer, so it never matched. Second inert-CSS-fix in the same file — one is harder to spot than a missing fix, because review approves it |
| Counting a closed off-canvas drawer as unreachable content | 24 sidebar links reported as WCAG failures, burying the real finding. Detect the drawer by GEOMETRY (and allow 1px: it parks at exactly right:0), not by parsing its transform string |
| A vendored component matching a selector heuristic | `.monaco-status` is Monaco's own aria-live region, not a colour indicator. Exclude third-party UI explicitly |
| Reading whatever the test database happens to contain | A gate-bug test read `/api/tasks`, found an empty list, and passed against the reverted fix. Create the row the assertion depends on, and assert that something was actually measured |
| Testing a timezone bug in a whole-hour zone | An off-by-one-hour error and a correct rendering are indistinguishable when the server clock is near the hour. Use a 45-minute offset |
| Measuring overflow only at the document level | A 4,000-char title spilled 1,900px out of its card while `documentElement.scrollWidth` stayed exactly 1440px. The page was perfect by the global measure and unreadable on screen. Check element-level `scrollWidth > clientWidth` too |
| Searching innerHTML for `<script>` to detect XSS | Finds correctly-escaped values and misses `onerror=` entirely — it reports the safe case and misses the dangerous one. Detect a real side effect instead |
| Searching the whole document for a status word | `/offline/` matched `Private • Ollama • Offline`, a product feature label. It produced a false finding — and worse, would have let a **total absence** of offline reporting pass the presence check. Scope to status surfaces |
| Three overlapping owners of one message | Disabling any single offline handler left the audit clean, because two others still spoke. Redundancy makes every individual owner unprovable; consolidate, then re-verify the probe can fail |
| An off-screen live region counted as visible signal | `#sr-announcer` holds a **copy** of the toast text at `position:absolute` off-screen. The session-expiry probe read it and reported NO-SIGNAL as clean while the user could see nothing at all |
| Over-correcting by dropping every `[aria-live]` | The very next run deleted the new lost-session banner — an `aria-live="assertive"` alert — and reported NO-SIGNAL against a screen that plainly said so. **Visibility is the test, not the presence of an ARIA attribute** |
| Waiting out a toast to find the resting state | Polling re-raises it, so "wait past 6000ms" does not prove the screen is at rest. Remove transient nodes instead of waiting |
| A probe whose writes were all rejected | The concurrency audit reported `0 records created` as a **PASS**; every POST had 403'd on a missing CSRF token. An audit measuring nothing looks identical to one finding nothing |
| A fixed idempotency key across runs | The second run replayed the first run's cached response, created nothing, and passed for the wrong reason |
| `time.sleep()` in a sync Playwright route handler | Blocks the driver's own event loop; the slow-network audit deadlocked for 8 minutes before being cancelled |
| Falling back to "the visible pane" when a pane is merely EMPTY | The workstation host's content satisfied the check, so removing a pane's loading state produced no finding at all |
| Judging the whole message instead of the headline | Flagged `Couldn't load your specs. Nothing was lost. (Unterminated string…)` as a raw parse error — punishing the fix |
| Expecting a live region to announce a dialog | Dialogs are announced by focus moving into a named `role=dialog`; the command palette was wrongly reported as silent |
| Querying an API with a higher limit than the UI uses | `?limit=1000` returned every row, so `len(rows) < total` was never true and the truncation check could never fire |
| Conflating two facts in one check | "Showing X of Y" and "Load more" were tested together, so deleting the disclosure still passed because the button survived |
| Timing a fixed sleep against a budget | A 2500ms `settle` measured against a 2500ms budget reported 2556ms — the sleep WAS the measurement |
| Checking workstations after the pane walk | The walk builds every workstation, so re-navigating takes the idempotent early-return path and never exercises build-then-wipe. With a reload: 7 destroyed. Without: 0 |
| Reading computed style after programmatic `.focus()` | `:focus-visible` does not match — reported a missing focus ring **twice, in two batches** |
| Reading style mid-transition | 150ms transitions report the start value: a 2px ring measured as 0px |
| Measuring only the landing pane | Touch targets reported "48 → 6" when 41 types were broken elsewhere |
| Measuring the first visible `[id^=pane-]` | For an absorbed tab that is the workstation *host* — 3 phantom "blank pane" findings |
| Instrumenting outside the layer under test | Counting `window.renderX` wraps *outside* the dedupe, so suppressed calls counted as run |
| Reading pane text but not toasts | Missed that failure feedback already existed; proposed a partly-solved fix |
| Comparing acorn offsets to Python offsets | UTF-16 vs code points: every file with an emoji showed spurious drift |
| Trusting a hand-written checker | A regex "oracle" had the same bug class as the code it checked |
| Not re-checking a transient state | A debounced DOM upgrade read mid-flight looked like 16 broken controls |

**The general rule: when a probe disagrees with the app, suspect the probe
first.** In this review that was the correct call more often than not.
