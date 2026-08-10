# Module 8 — Arena · Code Index · Hooks · Specs

**Reviewed:** 2026-08-10
**Panes:** `arena`, `codeindex`, `hooks`, `specs`
**Frontend:** `frontend/js/03-features-b.js` (1,712 lines)
**Backend:** `backend/routers/arena.py`, `codeindex.py`, `hooks.py`, `specs.py`
**Endpoints:** 42 across the four routers
**Risk score:** 19 (highest unreviewed at the time of selection)

---

## Summary

Four real defects, all live-verified before and after the fix. Three of them
are the **same recurring theme this review keeps surfacing: the product
reporting confidence it has not earned.**

| # | Component | Defect | Severity |
|---|---|---|---|
| 1 | codeindex | Dead-code detector reported framework entry points as deletable — **47 of the first 50 rows were live FastAPI route handlers** | High — acting on the report breaks the app |
| 2 | hooks | `{{file.path}}` substitution never worked; placeholders reached the model literally | High — every seeded hook was broken |
| 3 | hooks | `/run` returned `ok:true` for a run it recorded as `status='error'`; UI said "✅ Hook ran!" | Medium |
| 4 | arena | `[Error: No API key]` responses were votable and produced a **permanent ELO leaderboard** | High — fabricated ranking data |

---

## 1. Dead-code detection reported live endpoints as dead

### Evidence

```
GET /api/codeindex/dead-code
{"count": 597, "dead_symbols": [
  {"symbol_name": "bundled_asset", "filepath": "backend/app.py"},
  {"symbol_name": "index",         "filepath": "backend/app.py"},
  {"symbol_name": "manifest",      "filepath": "backend/app.py"},
  {"symbol_name": "favicon",       "filepath": "backend/app.py"}, ...
```

Cross-checking the returned names against decorated definitions in the real
repo: **47 of 50 carried a decorator.** `index` is the route that serves the
application itself. The panel presented these under a header reading
"💀 Potentially Dead Code (597 symbols unreferenced)" with no caveat — a user
trusting it would have deleted live routes.

### Root cause

`_parse_python()` recorded no decorator information at all, and the detector's
only notion of "referenced" was *appears as a call target or import name*.
Three whole categories of reference were invisible:

1. **Decorators** — a `@router.get(...)` handler is invoked by the framework,
   never by name.
2. **Module-level calls** — calls were collected *only* by walking function
   bodies, so `config = load_config()` at import time did not count.
   `load_config` was reported dead.
3. **Type annotations and base classes** — a Pydantic model used only as
   `def login(body: LoginRequest)` looked unreferenced. Every `*Request` model
   in the codebase was listed.

### Fix

- Parser now records `decorators` and an `is_entrypoint` flag per symbol
  (new columns, with an in-place `ALTER TABLE` migration so existing indexes
  do not need a rebuild).
- `ENTRYPOINT_DECORATOR_HINTS` matches on the trailing dotted segment, so
  `router.get` and `app.route` resolve while a user helper named `getter`
  does not.
- Calls are now also collected from module scope, parameter/return
  annotations, decorator expressions and class bases.
- The endpoint returns `excluded_entrypoints`, `confidence: "heuristic"`,
  `truncated`, `returned` and a `note` naming what the analysis cannot see.
- The UI header changed from a verdict ("Potentially Dead Code (597)") to a
  candidate list with a warning-bordered note stating the exclusion count.

### Result — live

| | before | after |
|---|---|---|
| candidates | 597 | **48** |
| entry points excluded | 0 | 516 |
| route handlers in top 50 | 47 | 0 |

The remaining 48 are plausible candidates (`section_divider`,
`reload_templates`, `AgentState`), presented as candidates rather than facts.

---

## 2. Hook template substitution was flat, so every placeholder failed

### Evidence

`fire_event()` and the UI both send nested payloads:

```json
{"file": {"path": "test.py", "content": "print(\"hello\")", "size_lines": 1}}
```

The substitution loop was:

```python
for k, v in event_data.items():
    prompt = prompt.replace(f'{{{{file.{k}}}}}', str(v))
```

With one top-level key `file`, the only pattern it could ever build was
`{{file.file}}`. Reproduced directly:

```
in:  'Review this file: {{file.path}}\n{{file.content}}'
out: 'Review this file: {{file.path}}\n{{file.content}}'   # unchanged
```

This is the **UI's own default prompt**, and both seeded hooks use the same
dotted form (`{{change.description}}`, `{{deploy.target}}`). Every hook in
the product shipped its template braces to the model as literal text.

### Fix

`_render_template()` — a regex substitution that walks dotted paths through
nested dicts and lists. Unresolved placeholders are **left visible** rather
than blanked, so a typo in a hook prompt shows up in the run output instead of
silently vanishing. Dict/list values serialise as JSON.

```
'Review {{file.path}} size {{file.size_lines}}'  ->  'Review a.py size 42'
'{{a.b.c}}'                                      ->  'deep'
'{{nope.x}}'                                     ->  '{{nope.x}}'   (visible)
```

---

## 3. A failed hook run was announced as a success

`_run_hook()` computes `status = 'error'` and writes it to `hook_runs`, but
`POST /hooks/{id}/run` returned only `{'ok': True, 'output': ...}`. The UI's
`if (d.ok)` therefore rendered:

> ✅ Hook ran!
> Hook error: No AI provider is configured or reachable…

`ok` described the HTTP call, not the hook. The endpoint now returns the real
`status`; the UI branches on it and shows "❌ Hook failed". The run history
list also gained a per-row ✅/❌ badge — the status column was being stored
and never displayed.

---

## 4. Arena scored battles in which no model responded

### Evidence

With no API key, both sides produce `[Error: No API key]`. That string was
written to `arena_battles.response_a/b` as though it were a model answer, the
vote endpoint accepted it, and:

```
{"model":"gpt-4o",       "wins":1,"elo":1016.0,"win_rate":100.0,"rank":1}
{"model":"claude-haiku", "wins":0,"elo":984.0, "win_rate":0.0,  "rank":2}
```

A permanent, authoritative-looking ELO ranking derived entirely from two
identical error strings — on a brand-new install, which is exactly when a user
has no key.

### Fix

- The stream tracks `failed_a` / `failed_b`, persists them (new columns +
  migration), and the `battle_ready` frame now carries `votable` and a
  `reason`.
- The UI replaces the vote buttons with an explanatory notice instead of
  offering a choice between two failures.
- **Second door:** the vote endpoint itself refuses a failed battle
  (`code: battle_failed`). The UI hiding the buttons is not enough — a stale
  tab or a direct POST would still write ELO. This is the 10th occurrence of
  the "fixed one entry point, not its twin" pattern in this review.

---

## Verified working (no change needed)

- **specs** — full lifecycle exercised: create → requirements → design → tasks
  → execute → export. Streams SSE correctly and degrades honestly without a
  provider ("⚠️ **No OPENROUTER_API_KEY set.**"). Pagination, artifacts and
  export are all sound.
- **codeindex** re-indexing is idempotent (`DELETE` before `INSERT` per file);
  running it three times gave identical counts.
- **hooks** CRUD, toggle, filter and event-type listing all behave, with
  correct 404s and `ok:false` handling already wired in the UI.
- Directory traversal on `/codeindex/index` is properly blocked by
  `is_within()`.

---

## Cross-module impact

- **Module 6 (quality-tools / project health)** depends on `code_symbols`.
  Its grade now draws on a symbol table with two extra columns and a more
  complete call graph (27,520 calls vs 22,875). Health output re-verified —
  unchanged and still honest about coverage.
- `frontend/styles-redesign.css` gained `.ci-deadcode-note`,
  `.hook-run-status`, `.arena-unvotable`.
- Arena remains the one place that calls OpenRouter directly rather than
  going through `backend/services/llm.py`, so it ignores Vault-stored keys and
  a local Ollama model. **Flagged, not changed** — routing it through the
  shared service is an architectural change with a real blast radius and is
  better done as its own change.

---

## Tests

`tests/unit/test_141_module8_arena_codeindex_hooks.py` — **34 tests.**

Revert-proof (caches cleared, all three routers reverted): **32 of 34 failed.**
The two that survived are genuine guards on the new code path, not passengers:
`test_call_inside_function_is_not_duplicated_as_module_level` was confirmed to
fail when the `_nested` filter is removed, and `test_parser_survives_syntax_error`
pins pre-existing behaviour the new module-level walk could easily have broken
(walking a partially-parsed tree).

Full suite after: **3,528 unit + 655 regression/system/uat = 4,183 passing, 0 failures.**

---

## Known pre-existing failure (not introduced here)

`test_120_audit_ratchet.py::…[console_health]` fails: 13,983 CSP `style-src`
messages against a 12,000 budget. **Verified pre-existing** — stashing all
Module 8 changes and re-running the audit against clean HEAD gives **14,203**,
i.e. worse than with these changes. This is the known deferred CSP-noise item,
not a Module 8 regression. The other 22 audits remain at 0.
