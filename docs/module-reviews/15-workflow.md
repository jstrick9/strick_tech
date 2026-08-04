# Module 15 — Workflow

**Commit:** `950ddd2` · **Suite:** 2999 passed / 17 skipped / 0 failed · ruff clean
**Surface:** `backend/routers/workflow.py` (737 lines, 12 endpoints) ·
`frontend/js/04-workflow-specs.js` (1801 lines)
**Workstation:** absorbs `pipeline`, `loops`, `specs`, `ambient`

Workflow is the visual automation builder — users wire
trigger → agent → condition → output graphs and run them. Every finding below
was reproduced against a live server before the fix.

---

## 🔴 1. Condition expressions were computed and thrown away

```python
cfg.get('expression', '').replace('{{prev_output}}', context['prev_output'])
passed = any(kw in context['prev_output'].lower()
             for kw in ['yes', 'pass', 'true', 'success', 'ok'])
```

The first line is a **bare statement whose value is never assigned**. The
configured expression was interpolated, then discarded. What actually decided
the branch was a keyword scan for "yes/pass/true/success/ok".

Verified live — a condition configured to never match still took the *yes*
branch:

```
expression : {{prev_output}} contains 'NEVER_MATCHES'
input      : "yes please"
→ Condition: true          ← because the input contained "yes"
```

For a visual workflow builder, branching that ignores the branch condition is
the module's central feature not working.

### The fix

`evaluate_condition()` implements a small, deliberately **non-executable**
grammar: `contains`, `not_contains`, `equals`, `starts_with`, `ends_with`,
`matches`, `is_empty`, `is_not_empty`, and numeric `> < >= <=`.

There's a test asserting no `eval` / `exec` / `__import__` appears anywhere in
it. Making workflow nodes run arbitrary Python would be a far worse bug than the
one being fixed — this executes in the server process with database and vault
access.

An empty expression still falls back to the keyword heuristic so existing
workflows keep working, but now *says* that's what it did.

---

## 🔴 2. `code` nodes reported work they never performed

```python
elif node['type'] == 'code':
    # JS-like simple expression eval (Python side: just passthrough for safety)
    yield ... "Code transform applied"
```

Output passed through unchanged. The comment shows the author knew — but the
node still reported success. A user debugging a pipeline sees a green node and
looks elsewhere, which is worse than an outright refusal.

Now applies real transforms (`uppercase`, `lowercase`, `trim`, `strip_html`,
`first_line`, `json_pretty`) and, when raw code is configured, **refuses with an
explanation** rather than pretending.

---

## 🔴 3. `memory` read nodes read nothing

The read branch emitted *"Memory op done"* and performed no retrieval. A Memory
node wired for recall contributed nothing to the pipeline and claimed otherwise.
Now performs an FTS search and feeds results forward, or reports that none
matched.

---

## 🔴 4. Every run was persisted as `'success'`

```python
(run_id, wf['id'], wf['name'][:100], 'success', user_input[:1000])
```

Hardcoded. Verified live: a run whose agent node emitted `node_error` was
recorded `status='success'`. The Replay pane and anything built on
`workflow_runs` were systematically wrong about what had happened.

Now tracks `node_errors` and persists `failed` accordingly; the `done` event
carries `status`, `errors` and `nodes_run`.

---

## 🟡 5. Eight endpoints returned 200 for a missing workflow

`get`, `put`, `delete`, `run`, `duplicate`, `export`, `validate`,
`delete-edge` — all 404 now, and `import` with malformed JSON is 400.

**PUT was the worst.** `_load_one(wf_id) or {}` meant a PUT to a nonexistent id
silently **created** a workflow there:

```
PUT /api/workflow/typo-id-xyz  →  200 OK, workflow created
```

A typo in the id produced a second, near-invisible workflow while the user
believed they had saved the original.

---

## Verified working (no change needed)

- **The `loop` node is genuinely implemented**, with iteration caps and an
  early-stop keyword — and its comment honestly scopes it to "iterate this
  node's own agent call" rather than claiming arbitrary cycle-following.
- **Webhook nodes apply the SSRF guard** (`_is_ssrf_blocked_url`) and disable
  redirect-following.
- The `visited` set prevents infinite loops on cyclic graphs; a cycle
  terminates rather than hanging.
- Conditional edge labels (`yes`/`no`/`true`/`false`) were already wired
  correctly — the bug was upstream, in what set `_condition`.
- `sse_guard()` is applied, so an LLM outage closes the stream cleanly.

---

## Cross-module impact

| Module | Impact |
|---|---|
| **Replay** | Reads `workflow_runs`; was being told every run succeeded |
| **Memory / RAG** | Memory nodes now actually query the FTS index |
| **Chat** | `output` nodes target the chat pane |
| **Observability** | Any monitoring over `workflow_runs` inherited the wrong status |

---

## Tests

`tests/unit/test_70_workflow_module_review.py` — **43 contracts**, including 14
condition-operator cases and end-to-end branch selection through the SSE stream.

**Proven to catch the bugs: 39 of 43 fail against the pre-fix code.**

Two self-corrections worth recording:

1. An assertion matched `evaluate_condition()`'s **own docstring**, which quotes
   the broken code it replaced. Now compares against a comment/docstring-stripped
   copy — the same trap hit in Modules 10, 12 and 14. I should be reaching for
   that helper by default at this point.
2. `test_put_to_a_missing_id` passed alone and failed in the full suite.
   Workflows persist as **files on disk, outside the test-database sandbox**, and
   my own earlier pre-fix run had left a "Ghost" workflow behind. That residue
   was itself evidence the bug was real — but a test whose result depends on what
   ran before it is not evidence of anything.

---

## Recommended follow-ups

1. **Workflow files escape the test-database sandbox.** `workspaces/workflows/`
   is plain files, so the isolation added in `50cc986` doesn't cover it — there
   are now 560 workflow files, most of them test residue. The sandbox should
   redirect `WF_DIR` too.
2. **No cost recording.** Agent and loop nodes call the LLM with
   `max_tokens=1024` per invocation, and a loop node multiplies that by up to 10.
   Nothing reaches the cost ledger — the same gap still open in Swarm,
   Supervisor and Composer.
3. **`transform` node is nearly a no-op.** Only `merge` does anything, and it
   just prefixes a label. It should either gain real operations or be folded into
   the `code` node, which now has them.
4. **The executor is single-pass BFS**, so genuine cycles (a retry edge looping
   back) can't be expressed — the `visited` guard silently drops them. Worth
   either supporting bounded revisits or rejecting backward edges at validation
   time with a clear message, rather than accepting the edge and ignoring it.
