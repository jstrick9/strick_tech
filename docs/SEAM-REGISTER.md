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

**All eight audits are at 0.** `source-patterns` was cleared from 17 (six
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

## Never examined — **NEVER**

Ordered by my estimate of expected value. None of these have been looked at
even once.

| Seam | Why it matters | Cheap first probe |
|---|---|---|
| **Screen reader announcement** | Structure is audited, but nothing checks what is actually *announced* — live regions, dynamic updates | Drive with an accessibility-tree dump |
| **Slow / flaky network** | Only "up" and "hard 500" tested. Never 3s latency, partial responses, mid-stream disconnects | CDP throttling + abort mid-body |
| **Large data volumes** | Tested with tiny fixtures. 10k memories, 500 agents, a 50MB file are all untested | Seed at scale, measure render time |
| **Browser back / forward** | Deep links work; history navigation across workstation tabs is unverified | Scripted back/forward walk |
| **Session expiry / auth loss** | What happens mid-edit when a token expires? | Invalidate the token, then act |
| **Offline / reconnect** | A banner exists; recovery behaviour is unverified | Toggle offline, then online |
| **Long / adversarial input** | 10k-char names, RTL text, emoji, `<script>` in every field | Fuzz every input |
| **Timezones & dates** | All timestamps assume the server's zone | Run under `TZ=Pacific/Kiritimati` |
| **Print / export** | `styles-print.css` exists but was never verified | Render to PDF, inspect |
| **Reduced motion / high contrast** | `prefers-reduced-motion` partially honoured; forced-colors never tested | Emulate both media features |
| **Zoom to 200%** | WCAG 1.4.4 requires no loss of content | Re-run responsive audit at 200% |
| **Multi-tab / multi-window** | Two tabs editing the same record | Two contexts, same document |

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
| A probe whose writes were all rejected | The concurrency audit reported `0 records created` as a **PASS**; every POST had 403'd on a missing CSRF token. An audit measuring nothing looks identical to one finding nothing |
| A fixed idempotency key across runs | The second run replayed the first run's cached response, created nothing, and passed for the wrong reason |
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
