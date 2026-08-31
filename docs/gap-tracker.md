# Agentic OS — Gap Hunt & Fix Tracker

**Plan:** exhaustively find and fix correctness/security/robustness gaps across all backend + frontend
modules, driving every *runnable* suite to 0 failures and maximizing coverage of reachable code.
Environment-gated suites (browser E2E, AI-provider, seeded-demo, hardware) are verified by static
analysis + unit/integration and documented as "confirm in CI."

**Operating rules (agreed):**
- Bugs & correctness first (no gratuitous refactor).
- Full backend authority.
- Every fix ships with a failing→passing regression test; no collateral regressions.
- Small, verified commits → `main`; rebuild frontend bundle when frontend source changes.
- Verify-by-analysis for environment-gated behavior, documented explicitly.

---

## Baseline (captured 2026-08-31)

- Backend unit suite: **4647 passed / 185 skipped / 0 failed**.
- Frontend vitest: **75 / 75 passed**.
- Backend coverage (unit suite, `.coverage`): **60% of backend** (33,542 stmts / 13,525 miss).
- Repo audit tracker: **22/22 user-facing destinations fully reviewed**; 0 panes with no test mention.
- Linters: ruff + eslint + globals + colour-contrast + bundle-reproducibility all clean (on `main`).

### Lowest-coverage backend files (hunting ground)
connectors 12% · drift 15% · a2a 21% · replay 24% · llm 26% · engine 28% · voice 28% · specs 30% ·
websocket 31% · obsidian 32% · testgen 32% · builder 33% · memory 35% · agent_leaderboard 36% ·
crdt 38% · tauri_build 40% · goal_manager 40% · browser_agent 41% · fusion 44%.

---

## Ledger

| id | Severity | Module | Evidence | Fix | Status |
|----|----------|--------|----------|-----|--------|
| 001 | **High** | `backend/routers/crdt.py` | OT `_compact` merged adjacent ints **regardless of sign**, so a retain next to a delete (e.g. `[1,-1]`) collapsed to `[]` and `[1,-1,3]` to `[3]` — silently corrupting/dropping text on any transform that produced a retain adjacent to a delete. Additionally, `_transform` dropped the surviving side's ops when the *other* side exhausted, losing deletes and breaking convergence (e.g. base `'ab'`, A `[1,'X']`, B `[-2]` → `'aXb'` vs `'X'`). Reachable via live collaborative editing (`apply_and_broadcast` transforms every concurrent op). | `_compact` now merges only **same-direction** ints (retains together, deletes together); `_transform` passes the surviving side's remaining ops through unchanged when the other side exhausts. | **FIXED** — 3 failing→passing regression tests; 200,000-pair fuzz on both transform sides → 0 divergences; 79/79 collab tests pass; full unit suite 4650 pass / 0 fail; ruff clean. |
| 002 | **Critical** | `backend/services/plugin_sandbox.py` | **Sandbox escape → arbitrary file read / RCE.** Runtime `__builtins__` exposed `getattr`, `type`, `setattr`. The static gate only blocked *literal* `getattr(` calls (AST `Call`), but `getattr`/`type` were still in the runtime namespace, so a plugin that **passed validation** (`{'ok': True, 'violations': []}`) could alias `G = getattr`, build dunders at runtime via `chr(95)*2`, then traverse object graph `().__class__.__mro__[1].__subclasses__()` → reach real `__builtins__['open']` and read `/etc/hostname` (reproduced: `'e2b.local'`). Same primitive = arbitrary code execution. | Removed `getattr`/`type`/`setattr`/`delattr`/`vars`/`dir`/`globals`/`locals`/`eval`/`exec`/`compile`/`open` from plugin `__builtins__` (allow-list + hard deny-list belt-and-suspenders). Strengthened static gate with AST checks: reject any private attribute access (attr starting with `_`), any reference to a traversal builtin (even aliased), and any string literal containing `__`. | **FIXED** — 3 failing→passing regression tests; exploit now blocked at validation; benign plugins still run; 197/197 plugin/sandbox tests pass; full unit suite 4653 pass / 0 fail; ruff clean. |

## Environment notes

## Environment notes
- Repo venv must be built with **/usr/local/bin/python3 (3.13.14)**; a 3.13.5 venv segfaults on
  `ctypes` in `backend/services/sandbox.py` (Python build artifact, NOT a code bug).
- Live-server suites (integration/connectors/security/regression/gap) need a server + `RATE_LIMIT_MAX`
  raised, plus seeded `demo_*` data and a real AI provider for the provider-gated paths.
- Browser E2E needs Chromium (unavailable in this sandbox).
