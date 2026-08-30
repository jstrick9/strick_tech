# 89 — ICM Workspaces

**Pane:** `icm`
**Frontend:** `frontend/js/59-icm-workspaces.js` (940 ln)
**Backend:** `backend/routers/icm.py` (704 ln) + 8 services (3,456 ln)
**Tests:** `tests/unit/test_189_icm_stage_extraction.py` (12)
**Status:** reviewed, one defect fixed, verified live

The highest-risk destination in `scripts/audit/module_risk.py` (score 20) and
one of only two with no review document.

---

## What works

Exercised against a running server before changing anything. This module is in
better shape than its risk score implies — the score reflects surface area, not
defect density.

| Surface | Result |
|---|---|
| Create workspace | 200, stages numbered `01-`/`02-`/`03-` |
| Walk test | `can_orient`, `can_find_work`, `can_report_status` all true |
| Entry routing | `01-research`, "first stage with no output" |
| Layered context L0–L4 | compiled in order, correct budgets |
| File read / write | 200; **re-runs the walk test on every save** |
| Path traversal ×5 | `Path escapes the workspace` / 404 |
| Write without CSRF | 403 |
| Malformed create ×7 | 400 / 409 / 422, nothing created |
| Pane + all six tabs | render, 0 page errors, 0 failed requests |
| Templates, forms, inventory | real data, 8 builtin templates |

Re-validating the walk test on save is a genuinely good design choice: the
structure cannot silently rot as a user edits contracts.

---

## The defect: `/api/icm/describe` dropped most of the user's stages

The endpoint turns plain English into a proposed workspace. It split the
narrative at `SEQUENCE_MARKERS` — `then`, `next`, `finally`. **Nothing else
opened a boundary.**

People list their stages at least as often as they narrate them, and a comma is
not a sequence marker. Measured live:

```
"Every week I research a topic, draft an article, then review it"
    -> ['research', 'review']            draft lost
"I research, draft, edit, and publish each piece."
    -> ['research']                      three lost
"I intake the request, triage it, assign an owner, and close it out."
    -> ['intake']                        three lost
```

This is worse than an obvious failure. The proposal *looks* considered — it
names a form, cites evidence, explains its reasoning — then invites the user to
confirm a structure that omits most of their process. Under the ICM canon the
stage list **is** the architecture, so a dropped stage is a folder that never
exists and work with nowhere to go.

### Three causes, all required

1. **Only sequence markers cut.** A comma or `and` followed by a known stage
   verb is now also a boundary (`_LIST_RE`), restricted to the curated
   `STAGE_VERBS` vocabulary so ordinary prose cannot shred a sentence.
2. **A two-word floor discarded the survivors.** Fixing the split alone still
   lost `draft` — the fragment is one word. The floor is kept (it drops "it",
   "that") except when the fragment *is* a stage verb.
3. **The vocabulary was content-production only.** A support or ops workflow
   matched almost nothing. Added `intake`, `triage`, `assign`, `route`,
   `escalate`, `resolve`, `close`, `qualify`, `onboard`, `verify` and 10 more.

After: `['research','draft','review']`, `['research','draft','edit','publish']`,
`['intake','triage','assign','close']` — and non-process prose still yields one
stage.

Revert proof: 4 breaks, 4 caught — including one that lets *any* comma cut,
which guards the opposite failure of inventing stages that were never described.

---

## Improvements considered and NOT made

Recorded so the next pass does not re-litigate them.

- **LLM-based stage extraction.** Would handle arbitrary phrasing, but makes a
  core structural decision non-deterministic and unavailable offline. The
  rule-based splitter is inspectable and every stage cites the words that
  produced it — which is what makes the proposal correctable by the user.
- **Auto-create from `/describe`.** The canon is propose-then-confirm and the
  endpoint is deliberately read-only. Left alone.
- **`window.PANE_RENDERERS`.** `12-information-hierarchy.js` checks it to
  decide whether to show a "moved to Workspaces" pointer. Nothing else reads
  it; it is a load-order sentinel, not dead code. Left with its explanatory
  comment.

## Affected modules

None. `icm_dialogue.py` is imported only by `backend/routers/icm.py`
(`/describe`, `/describe/create`). No other pane consumes stage extraction.
