# 49 — Audit infrastructure: making findings cumulative

**Status:** shipped
**Batch:** 36
**Scope:** `scripts/audit/` (new, 9 files), `docs/SEAM-REGISTER.md` (new),
`tests/unit/test_120_audit_ratchet.py` (new), plus 4 bug fixes the new audits
found immediately

Answering the question *"how do I get you to find and fix everything without
stopping?"*

---

## The honest answer to that question

"Until there are no more issues" is not a state I can reach and certify. Every
new bug class in this review required inventing a new way of looking:
duplicate rendering was invisible until renderer invocations were counted;
fabricated Kanban tasks were invisible until every API was forced to 500; a
6×12px link was invisible until every control on every pane was measured.
There is no finite list of ways to look.

What *is* achievable: **every bug class ever found stays found**, and
unexplored territory is written down instead of forgotten.

## The actual bottleneck, measured

| | |
|---|---|
| Live-browser discoveries across the review | 109 |
| Static-analysis discoveries | 100 |
| **Self-corrections I had to log** | **66** |
| Ad-hoc probes that found recent bugs | 8 |
| **Those probes committed to the repo** | **0** |

The audit tools lived in `/home/user/`, outside the repo, and were **wiped
between sessions**. They got rewritten from memory each time, slightly
differently. That is not a hypothetical cost:

* **Touch targets took three batches**, once per way of measuring wrongly —
  one pane, then all panes but only height, then finally the `display: inline`
  case where the CSS rule was inert.
* **A "missing focus ring" was reported twice, in two separate batches**, and
  was wrong both times — the same measurement mistake, repeated despite having
  been documented after the first.

I was rebuilding my instruments instead of accumulating them.

---

## What shipped

### Phase A — the instruments are now in the repo

`scripts/audit/` — seven audits over a shared harness:

| Audit | Needs | Covers |
|---|---|---|
| `source_patterns.py` | nothing | Fabricated data, raw-error headlines, unguarded array access |
| `semantics.py` | browser | Headings, landmarks, dialog names, labels |
| `pane_health.py` | browser | Blank panes, console errors, destroyed workstations |
| `keyboard.py` | browser | Unreachable clickables, missing focus rings |
| `touch_targets.py` | browser | Controls under 44×44 on a phone |
| `responsive.py` | browser | Horizontal overflow at 3 viewports |
| `failure_honesty.py` | browser | What a user sees when every API returns 500 |

```
python3 scripts/audit/run_all.py            # human readable
python3 scripts/audit/run_all.py --json     # machine readable
```

`_harness.py` encodes the nine measurement traps that previously produced
false findings — real Tab presses instead of `.focus()`, waiting out the 150ms
transition, resolving a pane's *own* element rather than the first visible one.
A probe in the repo gets its bugs found once; a probe retyped each session
reintroduces them.

### Phase B — the ratchet

`scripts/audit/baseline.json` holds each audit's headline number.
`test_120_audit_ratchet.py` fails the build if any number **rises**.

```json
{ "failure-honesty": 0, "keyboard-operability": 0, "pane-health": 0,
  "responsive-overflow": 0, "semantics": 0, "source-patterns": 17,
  "touch-targets-under-44px": 0 }
```

**Proven to work**: reintroducing the `hooks.hooks` null-deref produced

```
AssertionError: failure-honesty rose from 0 to 1.
  JARGON  hooks  Failed to load hooks: Cannot read properties of null (reading 'hooks')
```

It names the audit, the pane, and the exact text a user would have seen.

Browser audits **skip** rather than fail when no server is running, and the
skip is visible — a CI run with no browser cannot be mistaken for a pass.

### Phase C — the seam register

`docs/SEAM-REGISTER.md` lists every dimension a bug can hide in, each marked
covered / partial / **never examined**, with 13 seams never looked at even
once — concurrency, screen-reader announcement, slow networks, large data
volumes, timezones, zoom, offline recovery, and more.

It also records what is **deliberately out of scope**, so those are not
rediscovered as "gaps", and the nine measurement traps with what each cost.

---

## Four bugs the new audits found immediately

Written to be reproducible, the audits found things my ad-hoc probing had
declared clean:

1. **`hooks.hooks` on null** — `Cannot read properties of null (reading
   'hooks')` rendered into the Hooks pane as the user's explanation. A second
   instance of the same bug appeared once the first was fixed; the audit
   walked me to both.
2. **`h.grade` on null** — the same shape in the Health pane.
3. **611px horizontal document overflow on Goals.** The supervisor DAG's SVG
   uses `overflow: visible` by design, but the `.dag-viewport { overflow:
   hidden }` rule that should contain it exists **only in
   `frontend/styles.css`, which is not linked**. It had never applied. The
   whole app scrolled sideways on a phone.
4. **Six unguarded array accesses** of the exact class fixed last batch,
   in files that batch never touched — now visible in the `source-patterns`
   baseline rather than lost.

---

## Three audit bugs found and fixed before trusting the numbers

Consistent with the rule *"when a probe disagrees with the app, suspect the
probe first"* — which was the correct call more often than not in this review:

* **`keyboard.py` reported 16 unreachable `.agent-row`s.** The app was fine;
  the upgrade is debounced by 50ms and the audit measured mid-flight. It now
  re-checks before reporting.
* **`pane_health.py` flagged `multitab` as blank.** Its entire legitimate
  render is 39 characters of browser-tab chrome. A character threshold was the
  wrong test; it now checks for interactive content.
* **`touch_targets.py` flagged three 44px-tall tabs.** A bounding box measured
  inside a scrolling strip. Now requires both dimensions to genuinely fail.

Each was a false positive that would have sent the next session chasing a bug
that does not exist.

---

## The stopping criterion, stated honestly

Not *"no bugs exist"* — that is unfalsifiable.

> **Every seam in the register has a committed audit, every audit sits at its
> floor, and the ratchet passes.**

Today: **7 seams covered, 7 partial, 13 never examined**, one baseline above
zero (`source-patterns: 17`). Those are the numbers to drive down, and anyone
can verify them without me.

---

## Verification

- **Full suite: 3,212 unit + 655 regression/system/uat = 3,867 passing**,
  plus 10 new ratchet tests = **3,877**, 0 failures.
- Ratchet proven to catch a regression by reintroducing a real bug.
- All 7 audits run clean; 6 at zero.
- `ruff`, `lint_inline_handlers`, `lint_globals` clean.
