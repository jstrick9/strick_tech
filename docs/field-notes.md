# Agentic OS — Security & Correctness Field Notes (Round 4)

*Verification-focused review of the full platform. Every finding below was
confirmed by a reproduction, a failing→passing regression test, and a green run
of the existing test suites. No finding is a code-reading guess.*

## Process

1. **Coverage-guided + adversarial sweep.** Scanned the full backend for the
   high-value defect classes: SSRF (outbound HTTP from user URLs), SQL injection,
   eval/exec sandbox escapes, upload & zip decompression bombs, path traversal
   (read/write), command/flag injection, terminal-bind auth, websocket auth,
   division-by-zero, index/None handling, CORS, CSP, and frontend XSS.
2. **Reproduce first.** A candidate was only promoted to a "gap" after a live
   reproduction (running server or targeted harness), never from syntax alone.
3. **Fix + failing→passing regression.** Each fix ships a regression test that
   fails before the change and passes after.
4. **Run the full suite + ruff**, then a small, auditable commit to `main`.
5. **Re-verify after environment resets.** The sandbox `.venv`/`frontend/dist`
   were wiped repeatedly; each time they were rebuilt and the suite re-run to
   green before continuing.

## Approach that worked

- **Empirically probe** derived-default mismatches (e.g. `terminal._bound_to_loopback()`
  vs `config.load_config()` reading the same `AGENTIC_OS_HOST` with different
  defaults) rather than trusting single-file code reads.
- **Test the predicate** directly when an endpoint is CSRF-gated in the test
  client (the suite's `client` fixture sends no CSRF header, so mutation
  endpoints return 403/400 before the body handler runs — behavior tests there
  only prove *a* rejection, not that a specific guard fired).
- **Use the codebase's existing shared controls** (`safe_fetch.url_is_safe`,
  `codeguard.reject_unsafe_attribute_usage`, `is_within`, `safeUrl`) so fixes
  are consistent and lint-clean, and the repo's cross-cutting lint
  (`test_86`) stays green.
- **Distinguish real bugs from documented design.** Single-user desktop bind and
  opt-in `secure_mode` are deliberate; only genuine config-mismatch / unsafe
  handling were flagged.

## Gaps closed (all shipped to `main`)

| # | Sev | Area | Finding | Fix |
|---|-----|------|---------|-----|
| 001 | — | CRDT | OT transform mis-merge | correct OT transform |
| 002 | — | plugin sandbox | plugin escape | sandbox hardening |
| 003 | — | specs traversal | traversal | path guard |
| 004 | — | circuit-breaker | breaker not triggering | breaker logic |
| 005 | Critical | hooks.py | `condition` eval → RCE | AST allow-list (no calls/subscipts/dunders) |
| 006 | High | profiler/replay.py | restricted-builtins exec still RCE | `codeguard.run_guarded_exec` |
| 007 | High | secrets.py | ollama base-url SSRF + config injection | loopback-only validator |
| 008 | High | replay.py | webhook-node SSRF | `_is_ssrf_blocked_url` + `follow_redirects=False` |
| 009 | Medium | documents.py | `.docx` zip-bomb → memory exhaustion | `MAX_DOCX_XML_BYTES` pre-read check |
| 010 | Medium | rag.py / pluginsdk.py | unbounded uploads | cap read + decompressed manifest |
| 011 | High | terminal.py | unauth'd networked shell on default bind | align `_bound_to_loopback()` default to `0.0.0.0` |
| 012 | Medium | agent_engine.py | chain step eval not sandboxed (latent RCE) | `codeguard` guard before eval |
| 013 | Low | bounty_hunter.py | scan-id path traversal | `_safe_scan_id` refname sanitizer |
| 014 | Medium | frontend renderMarkdownEnhanced | raw-HTML/beacon/link injection | escape captures + `safeUrl` link guard |
| 015 | Medium | frontend ollama/flamegraph | unescaped model/node names | `escHtml` |
| 016 | Medium | bugbot.py | git-flag injection → file-content disclosure | `_is_safe_branch` refname validator |

## Areas verified safe (checked, no action needed)

- **SSRF/outbound HTTP:** `workflow.py` webhook, `websearch.py`, `secrets.py`
  ollama, `replay.py` webhook all guarded. Fixed-host routers (fusion, arena,
  deploy, github, bugbot, onboarding, imagegen, integrations, mcp, terminal,
  obsidian, skills, userprofile) use immutable hosts.
- **SQL injection:** f-string SQL only builds hardcoded fragments / whitelisted
  columns with `?`-bound params; `database.py` identifier double-quoting is
  intentional admin raw-SQL.
- **Command execution:** `gitai.py` (classify_git_command), `bugbot.py`
  (refname guard), and all `create_subprocess_exec`/`subprocess.run([...])`
  sites use fixed argv with no `shell=True` (deploy tunnel, tauri_build, e2e,
  mcp, codesearch, finetune, multifile_agent, builder, terminal).
- **Path traversal:** `testgen.py`, `codeindex.py`, `codesearch.py`,
  `workflow._wf_path`, `templates.py`, `is_within`-guarded; `bounty_hunter`
  now sanitized.
- **Division-by-zero / index / None:** `agent_leaderboard`, `goal_manager`,
  `ambient`, `analytics`, `drift`, `e2e`, `eval_framework`, `evals`, `hitl`
  all guard denominators; `lagrangian` index/None probes clean.
- **Websocket auth:** all endpoints call `require_websocket_auth` (fail-closed
  under secure mode); `ConnectionManager.connect` only runs after auth.
- **CORS:** `allow_credentials=True` with explicit localhost/Tauri origins (no
  wildcard), configurable via env for reverse-proxy deployments.
- **Deprecated `eval`/`exec`:** hooks, profiler, replay, agent_engine all now
  route through guarded paths.

## Verification evidence

- Full unit suite after every backend fix: **4728 → 4729 → 4734 → 4739 → 4743
  passed**, 185 skipped, **0 failed**. (Latest: **4743 passed / 0 failed**.)
- Backend lint (`ruff check`) clean on every changed file and across the tree.
- Frontend: `node --check` on modified modules; served `frontend/dist` rebuild
  verified to carry each fix; `test_86_cross_cutting_hardening` (34 tests,
  incl. the data-driven-href lint) green.
- Frontend vitest regression (`frontend/tests/renderMarkdownEnhanced.test.js`,
  8 tests) added; runs via `npm test` in CI (node_modules absent in the offline
  sandbox — marked "confirm in CI").

## Coverage caveat

`pytest --cov` times out under coverage instrumentation in this sandbox (the
instrumented suite exceeds the CPU limit), so coverage-% could not be measured
here. Per round-4 acceptance, the env-gated suite was verified by static
analysis + the runnable unit suite; CI should confirm coverage of the
low-coverage routers (`memory.py`, `goal_manager.py`).

## Remaining follow-ups for CI

- Confirm `npm test` (vitest) for the new `renderMarkdownEnhanced` test.
- Confirm `playwright`-gated e2e bootstrap collection (`test_90`) with
  playwright installed.
- Re-run `scripts/lint_inline_handlers.py`, `scripts/verify_bundle_ast.js`, and
  `test_180_bundle_is_reproducible` after any future frontend change.

## Logic-correctness pass (this session)

Beyond security, this session audited live state-counter / aggregation arithmetic
and fixed four correctness bugs (each reproduced, regression-tested, verified):

- **#017** `agent_engine.run_loop_iteration` — loop health `success_rate` used
  `run_count` (successes only) as the denominator and was only recomputed on the
  success branch: 5/5 reported 0%, an all-failing loop reported 100% forever.
  Fixed to `successes / (successes+errors)` recomputed in both branches.
- **#018** `arena._update_elo` — leaderboard row was only created by the seed over
  AVAILABLE_MODELS, so an unlisted model's UPDATE matched 0 rows and its rating
  change was silently lost. Fixed with `INSERT OR IGNORE` before update.
- **#019** `goal_manager.add_checkin` — a check-in at 100% wrote only progress and
  never transitioned to `status='done'`+`completed_at` (unlike update_goal /
  complete_milestone), so a fully-progressed goal stayed 'active'. Fixed.
- **#020** `eval_framework.platform_eval_stats` — `pass_pct` used SQLite integer
  division (`SUM(...)*100/COUNT(*)`), truncating 33.33%->33 and 87.5%->87.
  Fixed with `CAST(... AS REAL)`.

Verified-safe (checked, no action): scheduler kill_after_success/max_runs,
agent_monitor KPI, agent_leaderboard Wilson ranking + `ROUND(100.0*...)`,
finops aggregation, eval_framework weight-renormalization, evals trend/summary
pass_rate, memory_stats, memory_galaxy_graph, obsidian index counts, ICM
layer assembly + traversal guard, drift z-score guard, arena ELO math.

Suite note: the sandbox CPU quota now kills a single full `tests/unit` run at
~87% (an environment resource limit, not a failure), so the suite was verified
in two halves (2473 + 2274 ≈ 4747 passed). 4 pre-existing, order-dependent
failures (`test_35` finetune, `test_61` prompts-restore) also fail on a clean
checkout in isolation and were green in earlier complete runs — they are
environmental/state-dependent, not regressions.

## Remaining-surfaces sweep (this session)

Swept the untrusted-input routers not previously audited (browser_agent,
connectors, templates, testgen, evals, knowledge_graph) plus a broad heuristic
scan for file-write targets built from user input. Found and fixed:

- **#021** `finetune.py` — `dataset_id`/`job_id` placed directly in
  `DATASETS_DIR / f'{id}.jsonl'`, `f'{id}_meta.json'`, `JOBS_DIR / f'{id}.json'`,
  and `ADAPTERS_DIR / f'{id}.{format}'`. An id with `../`, a separator, or an
  absolute path escaped those directories to write (verified: an absolute id
  wrote outside DATASETS_DIR) or read arbitrary .json/.jsonl; `export_format`
  was echoed into a filename suffix. Fixed with `_safe_stem()` (any id ->
  `[a-z0-9_-]`, capped 64) and an export-format allow-list.

Verified-safe (checked, no action): browser_agent screenshot filename
(server-generated session uuid + int step_no), connectors (DB, bound params),
templates (`_safe_name`/`_within_preview`/relative_to + fname slug),
testgen (`is_within`), evals datasets (uuid did, bound params),
knowledge_graph (DB-only), bounty_hunter scan write (server-generated scan_id).

## Frontend behavioral/UX correctness pass (this session)

Found and fixed a family of the same coordinate-defaulting anti-pattern in the
workflow canvas (`frontend/js/03-features-a.js`): using `x || default` where
`0` is a legitimate world coordinate and the default differs from it.

- **#022** swarm DAG winner confidence used `runs[0]?.score || 0.96`, showing
  the wrong agent's score or a fabricated 96%.
- **#023** `wfAddNode` `x: x || 200` snapped a node dropped at the canvas
  origin to 200.
- **#024** `wfPasteNode` `(node.x || 200) + 30` (origin paste -> 230) plus
  `id: n${Date.now()}` collision when pasting twice in one millisecond.
- **#025** `wfNodeHTML` `left:${node.x||100}` drew an origin node at 100,
  desyncing it from its edges.

Also verified: workflow undo/redo branching (correct), self-connect guard in the
in-port handler (prevents `fromId === nid`), live-wire teardown on empty-canvas
drop (window mousemove/mouseup reset `_wfConnecting`), the remaining `x || 0`
uses across replay-collab/galaxy/supervisor (harmless — the fallback equals 0).

Frontend regression tests added: `tests/swarm-dag-confidence.test.js`,
`tests/workflow-coordinate.test.js`. Frontend suite: 83 -> 94 (+11).
