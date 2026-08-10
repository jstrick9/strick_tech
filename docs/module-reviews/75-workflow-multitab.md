# Module 14 — Workflow Builder · Multi-Tab Preview

**Reviewed:** 2026-08-10
**Panes:** `workflow`, `multitab`
**Frontend:** `frontend/js/03-features-a.js`
**Backend:** `backend/routers/workflow.py`, `multitab.py`
**Endpoints:** 21
**Risk score:** 20 (highest genuinely-unreviewed, after fixing the queue)

---

## Summary

Four defects, including a **stored XSS** and a data-integrity bug that
published unprocessed input as a pipeline's finished work.

| # | Component | Defect | Severity |
|---|---|---|---|
| 0 | *instrument* | The risk queue was mis-reporting reviewed modules — **twice** sending the review back to finished work | — |
| 1 | workflow | A failed node left `prev_output` intact, so downstream nodes consumed stale upstream data | High |
| 2 | workflow | The output node published that stale value as the pipeline's result | High |
| 3 | workflow UI | Logged "✅ Workflow complete" for a run the server marked `failed` | Medium |
| 4 | multitab | Tab `url` stored unvalidated and assigned to an iframe `src` — **stored XSS**, both doors | High |

---

## 0. The risk instrument was wrong again

`module_risk.py` decided whether a pane had been reviewed by matching its name
against review **filenames**. A doc covering several panes cannot name them all
in its filename, so `ambient`, `bugbot`, `gitai` (subjects of
`70-quality-tools-trio.md`) and `knowledge-graph`
(`74-evals-rag-observability-kg.md`) all sat at the top of the queue as
unreviewed. Taken at face value, the next module would have re-done Module 9.

This is the **second time** this instrument has misdirected sequencing — the
first was a comment counted as a renderer definition (`0e6b134`).

Now it reads each doc's `**Pane:**` / `**Panes:**` declaration, falling back to
the H1 form older docs use (``# 63 — Module review 2: Docs & Help (`docs`)``).
The queue immediately went from four already-finished modules at the top to a
correct ranking.

---

## 1–2. A failed step published the raw input as its result

`workflow.py`'s agent branch:

```python
try:
    result = await llm_svc.complete(...)
    context['prev_output'] = result.get('text', '')
except Exception as ex:
    node_errors.append(...)
    yield node_error          # prev_output left UNTOUCHED
```

Every downstream node reads `context['prev_output']`. When a node fails, that
value is still whatever the *previous* node produced — so the pipeline carries
on with stale data and presents it as the failed step's work.

Reproduced live: `trigger → agent("Summarise: {{input}}") → output`, no
provider configured:

```
node_error   b: No AI provider is configured…
final_output chat: "CONFIDENTIAL-RAW-INPUT-42"     ← the raw input
done         status: failed
```

The run is *correctly* marked failed — but the output node still delivered the
unsummarised input to the target as though it were a summary. For an `output`
node wired to a webhook, chat or a file, that ships unprocessed data to a real
destination.

**Fix:** a failed node clears `prev_output` (it produced nothing), and the
output node refuses to publish when `node_errors` is non-empty, emitting
`result: null, delivered: false` with a reason. Verified: **zero** occurrences
of the raw input anywhere in the failed run's stream, and the success path
still delivers `delivered: true`.

---

## 3. The UI congratulated a failed run

```js
} else if (data.type === 'done') {
  wfLog('✅ Workflow complete', 'success');
```

The `done` frame carries `status` and an `errors` array; the log ignored both.
A run where every node errored ended with a green "complete". Now branches on
`status` and reports the error count, and renders the non-delivery notice.

---

## 4. Stored XSS in the multi-tab preview

`create_tab` validates `file` carefully — and stored `url` verbatim:

```python
file = (as_text(body.get('file')) or 'index.html').lstrip('/')
url  = body.get('url') or f'/preview/{file}'      # unvalidated
```

The pane assigns it directly: `frame.src = tab.url`. Confirmed end to end —
`POST /api/multitab/tabs {"url": "javascript:alert(document.domain)"}` was
accepted, persisted to disk, and **appeared as a live iframe `src` in
Chromium**. Because tabs persist, the payload re-arms on every page load.

`PATCH /tabs/{id}` — the door the URL bar uses — accepted it too. That is the
**13th "second door"** in this review.

CSP currently blocks execution, which is why nothing visibly fired. That is
defence in depth, not a reason to store an attacker-controlled scheme in a
persisted iframe source.

**Fix:** `_safe_tab_url()` allows only same-origin absolute paths and
`http(s)`, strips control characters first (`java\tscript:` is ignored by the
URL parser but defeats a naive prefix check), rejects `..` segments and
protocol-relative `//host`, and returns **400** rather than silently
substituting a fallback. Applied at both doors.

---

## Verified working (no change needed)

- `/multitab/snapshot` genuinely writes a file and is `is_within()`-guarded —
  I initially misread it as a no-op; the snapshot exists on disk.
- The `file` field was already traversal-safe.
- Workflow `status` correctly reports `failed` when any node errors
  (a prior fix; still holding, now pinned by a test).
- The `code` node honestly refuses instead of claiming "transform applied",
  and the `memory` node genuinely queries FTS — both earlier fixes, still good.
- Workflow validate/import/export/duplicate all behave.

---

## Cross-module impact

- **Any workflow with an `output` node** now delivers nothing when upstream
  fails, instead of forwarding stale data to chat, a webhook or a file. This is
  a behaviour change, and the intended one.
- `final_output` gained `delivered` and `reason`; `result` may now be `null`.
  The only consumer is this pane, updated in the same commit.
- `POST`/`PATCH /multitab/tabs` now return **400** for a URL they previously
  accepted. Existing stored tabs with bad URLs are not rewritten — worth a
  follow-up sweep if any install has one.
- `scripts/audit/module_risk.py` change affects only review sequencing.

---

## Tests

`tests/unit/test_147_module14_workflow_multitab.py` — **22 tests.**

Revert-proof (caches cleared, both routers reverted): **21 of 22 fail.** The
survivor, `test_run_status_reflects_node_errors`, deliberately pins
pre-existing behaviour the change could have broken.

One of my own tests was wrong and I corrected the **test**, not the code:
I asserted a non-string URL should fall back silently, but `as_text()`
stringifies a dict, and a stringified dict must not become a usable URL —
refusing is right.

Full suite: **3,677 unit + 655 regression/system/uat = 4,332 passing, 0 failures.**
