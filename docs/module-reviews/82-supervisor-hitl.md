# 82 — Supervisor workstation: the `hitl` tab

**Destination:** `supervisor`
**Tabs:** `supervisor` (host), `hitl` (this doc), `a2a`, `agent-identity`, `goals`, `swarm`, `fusion` · `finetune` (doc 71)
**Frontend:** `frontend/js/48-supervisor.js`, `frontend/js/42-hitl.js`
**Backend:** `backend/routers/hitl.py`
**Tests:** `tests/unit/test_157_module21_supervisor_hitl.py` (41)
**Status:** `hitl` reviewed, fixed, verified live

Destination 10 of 20.

---

## Why `hitl` first

The Supervisor workstation hosts eight tabs across ~5,000 backend lines. HITL is
the one that matters most: it is **the human approval gate on autonomous
agents** — the component whose only job is deciding when a person must look
before an agent acts. Its own module docstring cites:

> EU AI Act Article 14 compliance (documented human oversight)

That makes every defect here a governance defect, not just a bug. All eight tabs
were opened in a real browser and checked for dead handlers first (result below);
`hitl` is where the substantive problems were.

Six defects, all reproduced against a live server before any code changed.

---

## Findings

### 1. The always-interrupt list could be side-stepped by capitalisation

`ALWAYS_INTERRUPT` is the hard list of actions that must reach a human *no
matter how confident the agent claims to be* — `delete_file`, `stripe_charge`,
`push_to_main`, `send_email`, `git_force_push`. It was matched with a bare `in`
against the caller's raw string:

```python
force_interrupt = action_type in ALWAYS_INTERRUPT or risk_level == 'critical'
```

…while `risk_level`, on the line above it, was already `.lower()`ed. Verified
live, all with `confidence: 0.99, risk_level: "low"`:

| `action_type` | decision |
|---|---|
| `delete_file` | `pending` ✅ |
| `DELETE_FILE` | **`auto_approved`** |
| `delete_file ` (trailing space) | **`auto_approved`** |
| `delete-file` | **`auto_approved`** |

The caller here is an **agent** emitting a free-form string. A model that writes
`Delete_File` defeats the safety gate with no intent to do so, and the platform
records nothing about it. This is not an attacker-only problem — it is a
coin-flip on LLM formatting.

**Fix:** `_normalise_action()` folds case, surrounding whitespace, and the
`- . space / :` separators before matching. `read_file` still normalises to
itself — a test pins that the normaliser does not collapse unrelated actions.

### 2. An unrecognised `risk_level` silently became the permissive default

```python
if risk_level not in RISK_THRESHOLDS:
    risk_level = 'medium'   # threshold 0.85
```

A caller sending `severe`, or `CRITICAL ` with a stray space, believes it has
asked for the strictest gate and instead gets the **second most permissive**
setting. Now falls back to `high` (always requires review) and returns a
`risk_level_note` saying the value was not understood and what the valid ones
are. Failing towards oversight is the only defensible direction here.

### 3. Auto-approvals were never recorded anywhere

The auto-approve branch returned a decision and forgot it: **no `hitl_queue`
row, no `hitl_audit` row, nothing in `/stats`.** Verified live:

```
BEFORE: total 164, approved 119
  (fire 3 destructive auto-approved actions)
AFTER : total 164, approved 119
```

Three actions approved by the machine; the oversight record moved by **zero
rows**. For a module claiming Article 14 "documented human oversight", the
decisions that were *never seen by a human* were the only ones with no
documentation at all — precisely inverted from what an auditor needs.

**Fix:** recorded with `status='auto_approved'` and `reviewer='system'`, plus an
audit row carrying the reason (`Confidence 99% >= threshold 70%`). Deliberately
**not** `status='approve'`, so machine decisions can never be mistaken for human
ones. The write is best-effort — an audit failure must never be the thing that
stops an agent.

### 4. `approval_rate` would have been polluted by the fix, and lied when empty

Recording auto-approvals naively would let a flood of them push the rate towards
100%, reading as *"humans approve almost everything"* when in fact humans saw
almost none of it. `/stats` now reports:

- `approved` / `rejected` — human decisions only
- `auto_approved` and `auto_approval_share` — what the machine decided alone
- `approval_rate` — human decisions only, **`None`** when nothing has been
  reviewed, with `approval_rate_basis` stating it
- `avg_confidence` — `None` rather than `0` when there is no data

The frontend rendered `${stats.approval_rate||0}%`, which prints **"0%"** for
"not yet measured" — the nullable-value trap this review has now hit three
times. Fixed to show `—`, plus a new *Auto-approved* tile and a line reading
*"🤖 3 action(s) (1.7% of all) were approved automatically without human
review."*

### 5. `assess-confidence` fabricated a verdict when the judge never ran

When the LLM returned unusable output, the endpoint returned a complete,
invented assessment:

```json
{"ok": true, "confidence": 0.5, "risk_level": "medium",
 "is_reversible": true, "recommendation": "proceed"}
```

Reproduced with a judge answering in prose for the action **"rm -rf / on the
production database"**. It said *proceed*, and it said the action was
*reversible*. Both were made up.

This is the module-16 defect (an unrun judge scoring a malware response "fully
safe") reappearing in the one component whose entire purpose is deciding whether
a human needs to look. Now returns **503** with `assessed: false`,
`confidence: null`, and `recommendation: "interrupt"` — an unavailable assessor
escalates rather than waving things through.

### 6. A failed undo reported success

Every failure path in the `file` branch fell through to the generic
`{'ok': True, 'restored': stype}` at the bottom of the function. Verified live:

```
snapshot with no recorded path    -> {"ok":true,"restored":"file"}
snapshot whose directory is gone  -> {"ok":true,"restored":"file"}
```

This is the most damaging place in the platform for a false success: the user has
just been told their destructive action *was reverted*, so they stop looking.
Each failure now returns 422 with a specific reason and `"Nothing was changed."`,
a `custom` state type reports `applied: false` instead of implying a restore, and
a **successful** undo is written to the audit trail — previously the record showed
an action approved and never showed it reverted.

---

## Revert-proof

Each fix individually reverted, `__pycache__` cleared each time.
**16 of 16 breakages caught**, baseline green before and after.

| # | Breakage | Tests failed |
|---|---|---|
| 1 | always-interrupt matched raw | 10 |
| 1b | normaliser drops case/strip | 6 |
| 1c | normaliser drops punctuation folding | 7 |
| 2 | unknown risk downgrades to medium | 1 |
| 2b | high risk no longer forced | 1 |
| 3 | auto-approvals not recorded | 4 |
| 3b | auto-approval audit row omitted | 1 |
| 3c | auto-approval logged as human approve | 3 |
| 4 | `approval_rate` 0 instead of None | 1 |
| 4b | auto count hidden from stats | 1 |
| 5 | unrun assessor claims ok | 1 |
| 5b | unrun assessor invents a verdict | 2 |
| 6 | undo with no path reports success | 1 |
| 6b | undo to missing dir reports success | 1 |
| 6c | undo not written to audit | 1 |
| 6d | custom undo claims restored | 1 |

### Another test that passed for the wrong reason

`test_high_and_critical_always_require_review` did **not** fail when I removed
`risk_level in ('high','critical')` from the force clause. Cause:
`RISK_THRESHOLDS['high']` is `1.0`, so at the default `confidence: 0.99` the
*threshold* comparison gates the action anyway — the assertion could not tell
"forced because the level says so" from "happened to fall under the threshold".
Rewritten to assert at `confidence: 1.0`, with a mirror test proving a low-risk
action at full confidence is still auto-approved (so the fix cannot be satisfied
by gating everything). It now fails correctly when broken.

That is the third harness artifact this review has caught by revert-proofing
(modules 18, 19, 21). Each one passed a full green suite first.

### A pre-existing test that pinned the bug

`test_23_governance_control_tower.py::test_hitl_confidence_assessment` asserted
`ok is True` for *"delete all user data"* **while the suite's LLM is stubbed** —
i.e. while no assessment could possibly have happened. It passed only because
the endpoint fabricated a verdict. **Updated in place, not deleted**, with the
reasoning recorded inline: it now asserts the honest contract in both directions
(a real assessment passes through; an unavailable one escalates with 503).

## Live verification

Server + real Chromium. All eight supervisor tabs open and render:

```
[supervisor     ] len=5163  dead-handlers=0
[a2a            ] len=1542  dead-handlers=0
[agent-identity ] len=12914 dead-handlers=0
[hitl           ] len=14789 dead-handlers=0
[goals          ] len=6949  dead-handlers=0
[swarm          ] len=1443  dead-handlers=0
[fusion         ] len=1140  dead-handlers=0
[finetune       ] len=1556  dead-handlers=0
```

HITL tab after the fix:

```
PENDING 24 | APPROVED BY HUMAN 119 | REJECTED 28 | HUMAN APPROVAL RATE 81% | AUTO-APPROVED 3
🤖 3 action(s) (1.7% of all) were approved automatically without human review.
   Approval rate covers human decisions only; auto-approvals excluded.
```

**Correcting my own probe:** an earlier run reported all seven child tabs as
*empty*. That was the probe, not the app — it read `#ws-body-<tab>`, while the
workstation switcher shows absorbed panes as `#pane-<tab>` and reserves
`ws-body-` for the host's own content. Re-probed with the right selector and
every tab has content. *"When a probe disagrees with the app, suspect the probe
first"* held again.

## Cross-module impact

- **`/api/hitl/interrupt`** now writes a row for auto-approved actions. Anything
  counting `hitl_queue` rows sees more of them; `agent_leaderboard.py` counts
  only `status='pending'` and is unaffected.
- **`/api/hitl/stats`** gains `auto_approved`, `human_reviewed`,
  `auto_approval_share`, `approval_rate_basis`; `approval_rate` and
  `avg_confidence` can now be **`None`**. The one frontend consumer was fixed;
  any other reader must be None-safe.
- **`/api/hitl/assess-confidence`** can return **503**. Callers that assumed a
  200 always carries a `confidence` float must check `assessed`.
- **`/api/hitl/undo/{id}`** can now return **422**. `ok: true` no longer implies
  a restore for `custom` types — check `applied`.
- Remaining supervisor tabs (`a2a`, `agent-identity`, `goals`, `swarm`,
  `fusion`) render cleanly with no dead handlers but have **not** had a deep
  behavioural review; they are the natural next pass on this destination.

## Suite

`4032 unit (2 skipped)` + `655 regression/system/uat (10 skipped)` =
**4,687 passing, 0 failures**. Linters clean.
