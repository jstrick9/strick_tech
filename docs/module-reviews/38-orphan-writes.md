# 38 — Writes against parents that do not exist

Autonomous hunt, batch 25. You chose **multi-step user journeys** — driving
complete tasks end-to-end rather than probing single endpoints.

## Method

Drove real journeys and checked whether step N's output is usable as step
N+1's input: secret → read back → reveal; workspace → file → switch → switch
back; spec → requirements → design → tasks; goal → milestone.

Then swept **all 86 sub-resource mutating routes** with a ghost parent id —
first with an empty body, then with a **valid** body so nothing else could fail
first and the parent check was the only thing left to test.

## What was already solid

Worth recording, because it is most of what I tested:

- **Secrets** round-trip exactly, masked by default, revealed on request.
- **Workspace isolation** is real — a file written in Alpha is invisible in
  Beta, unreadable by direct path from Beta, and still there after switching
  back.
- **Spec phase gates** correctly refuse tasks before design.
- **Referential integrity** on delete: a deleted spec 404s, its tasks are gone,
  and `PATCH` on a missing spec does not create a phantom.
- Deleting the **active** workspace is refused with a 409.

## The finding: 6 endpoints accepted writes against a non-existent parent

Verified they **persist** — a GET on the same ghost id afterwards returned the
child rows.

| Endpoint | Was |
|---|---|
| `POST /api/agent-identity/{ghost}/permissions` | 200, row persists |
| `POST /api/eval-framework/suites/{ghost}/cases` | 200, case persists |
| `POST /api/rag/pipelines/{ghost}/query` | 200 *"No relevant documents found in this pipeline"* |
| `POST /api/rag/pipelines/{ghost}/retrieve` | 200, empty result |
| `POST /api/goals/{ghost}/milestones` | **500** raw `IntegrityError` |
| `POST /api/crdt/docs/{ghost}/op` | 200 — **deliberate**, left alone |

### Why an orphan matters

It is **invisible**. It hangs off a parent that appears in no list, so it can
never be reviewed, run or deleted through the UI — but it still occupies the
table and counts toward totals. A stale id in an open tab is the ordinary way
to make one.

### The RAG pair is the worst, and not because of the orphan

> *"No relevant documents found in this pipeline."*

for a pipeline that **does not exist** tells the user their corpus is empty.
The rational response is to go and upload documents — into something that was
never there. `/documents` on the same resource already returned a correct 404,
so the two halves of one feature disagreed about whether the pipeline had to
exist.

### The goals one was the database doing the app's job

`sqlite3.IntegrityError: FOREIGN KEY constraint failed` leaked as a bare
**HTTP 500 "Internal Server Error"**. The FK constraint caught it; the
application never checked.

**Result: 6 → 1**, and the remaining one is intentional (CRDT documents
materialise on first edit — that is how collaborative editing is supposed to
work).

## Also fixed: spec phase gates blamed the wrong thing

```
POST /api/specs/{ghost}/tasks  ->  "Generate design first"
```

Workflow advice about a spec that is not there. A user following it would go
looking for a Generate Design button on something that does not exist.

`requirements` was subtler — it **did** call `_get_spec()` but ignored a `None`
result and fell through to `"description required"`, reporting a missing spec
as a problem with the request body and sending the user to fix a field that
was never the issue.

All three phase endpoints now return `404 Spec not found`, and the artifact
gates still work unchanged on a real spec.

## A correction to my own method

My first journey probe reported that a saved file "did not appear in the
listing" and that workspaces did not round-trip. **That was my harness, not the
app** — I used `/switch` (the real route is `/activate`) and assumed
`{files:[...]}` / `{content:...}` when `/files` returns a bare list and `/read`
returns plain text. Re-run against the real contract, every one of those
journeys passed. Recorded because a false positive that survives into a commit
message is worse than no finding.

## Tests

`tests/unit/test_110_orphan_writes.py` — 13 tests.

Each refusal is paired with a **"the legitimate path still works"** assertion:
a parent check that also blocks real writes would be a worse bug than the one
being fixed. Verified live that a real agent still accepts grants, a real goal
still accepts milestones, and a real suite still accepts cases.

**Proven to catch the bugs: with all five routers reverted, 9 of 13 fail.** The
4 that pass are exactly those legitimate-path guards, which correctly pass
either way.

## Regression status

| Suite | Result |
|---|---|
| `tests/unit` | **3005 passed, 2 skipped, 0 failed** |
| `regression` + `system` + `integration` + `uat` | **1044 passed, 17 skipped, 0 failed** |
| ruff · inline-handler · globals linters | pass |
