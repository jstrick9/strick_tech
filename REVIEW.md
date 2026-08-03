# Agentic OS Platform — Comprehensive Technical Review

**Reviewed:** 2026-08-03 · **Version:** 11.5.0 · **Commit reviewed:** `8422556` → **fixes pushed as** `64f8dc2`

Full-repo review across architecture, AI engineering, full-stack implementation, security,
QA, infrastructure and UX. Everything below was verified against a **live running server**,
not just by reading code.

---

## 1. What this system is

A local-first "agentic operating system": a FastAPI backend serving a vanilla-JS SPA,
packaged for desktop via Tauri, with SQLite as the single source of truth.

| Area | Size |
|---|---|
| Backend | ~58.4k LOC · 98 routers · 5 services |
| Frontend | ~47.5k LOC · 63 JS modules · 67 panes |
| Tests | ~54k LOC · 170 test files across 17 suites |
| API surface | ~895 endpoints |

**Stack:** FastAPI + Uvicorn · SQLite (FTS5, optional Qdrant) · vanilla JS (no framework,
no build step) · Monaco · Tauri 2 · Playwright · pytest + vitest + ruff + eslint.

**Request path:** `run.py` → `backend/app.py` (lifespan: schema → seed agents → inject vault
secrets → start scheduler) → security middleware → latency middleware → 98 routers →
`services/{llm,memory_db,agent_engine,scheduler,plugin_sandbox}`.

**LLM routing** (`services/llm.py`) is the strongest piece of AI engineering here: a clean
provider abstraction over OpenRouter / Ollama / custom OpenAI-compatible endpoints, with a
sensible `resolve_model()` rule (unslashed model names route to local Ollama), automatic
fallback to Ollama when no cloud key is present, and steering-context injection with an
explicit opt-out list for meta-agents. The 7 "engineering" patterns in the agent engine
(Loop / Harness / Chain / Reflection / Guard / Cost / Checkpoint) are a genuinely good
decomposition of agent-execution concerns.

---

## 2. Bugs found and fixed (pushed in `64f8dc2`)

### 2.1 Goals module — two tables never created, 4 endpoints returned HTTP 500 🔴

The highest-severity finding. `goal_manager.py` reads and writes `goal_decompositions` and
`goal_score_history` in six places, but `_SCHEMA` only ever created `goals_v2`,
`goal_milestones` and `goal_checkins`.

On **any fresh database**, these all threw `sqlite3.OperationalError: no such table` and
returned a bare `500 Internal Server Error` with no usable message:

- `POST /api/goals/{id}/score`
- `GET  /api/goals/{id}/score/history`
- `GET  /api/goals/{id}/score/latest`
- `POST|GET /api/goals/{id}/decompose`

Compounding it, `/score` UPDATEs five `goals_v2` columns that were never declared
(`outcome_score`, `score_breakdown`, `last_scored_at`, `iteration`, `decomposition`).
Because `CREATE TABLE IF NOT EXISTS` cannot add columns to an existing table, I applied
those as **idempotent `ALTER TABLE` migrations** so already-deployed databases are repaired
rather than only new ones.

Reproduced the 500 live, then confirmed all four endpoints return 200 with correct payloads.

### 2.2 An entire chat-history implementation was dead code 🟠

`01-app-core.js` defined `loadChatSessions`, `selectChatFolder`, `filterChatSessions` and
`toggleChatHistoryDrawer` — but `56-chat-history.js` loads *after* it and unconditionally
reassigns all four on `window`. The core copies **never executed**.

They had silently rotted: they still queried `#chat-folder-pills`, `#chat-sort-select` and a
page-size `<select>` that no longer exist anywhere in the app. Removed ~190 lines so exactly
one module owns chat-history rendering. This is the kind of defect that makes future edits
dangerous — a developer "fixing" chat history in the obvious file would see no effect.

### 2.3 Launchpad connection indicator was a permanent no-op 🟠

`renderConnectionReadiness()` writes to both `chat-connection-status` and
`mission-connection-status`. The second element **existed nowhere in the codebase**, so half
of every call silently did nothing and AI-connection state was only ever visible from inside
Chat. Added the button to the dashboard header it was clearly written for.

### 2.4 Default theme contradicted itself in three places 🟡

`onboarding.py` `DEFAULT_PREFS` said `light`; `index.html` booted `dark`; `onboarding.py`'s
status fallback also said `dark`. Commit `cf11497` moved the frontend to dark and missed the
backend. Aligned on **dark** per your confirmation.

### 2.5 Ruff findings — including one that was a trap

Cleared all 3. Note that ruff's `SIM118` on `workspace_export.py` is a **false positive**:
`sqlite3.Row` iterates *values*, not keys, so the suggested `for c in row` would have
silently corrupted every workspace import. I verified this in the interpreter, reverted my
initial "fix", and suppressed the rule with an explanatory comment instead. Worth flagging
because a future `ruff --fix` run will try to reintroduce it.

### 2.6 Stale test contracts (assertions corrected, no behavior changed)

- Pane count pinned at 68 after Code Editor was **intentionally** merged into Code Studio (→67).
- Three suites hardcoded `version == "6.0"`; actual is `11.5.0`. Now read `backend.version.VERSION`.
- Suites 40/42/45 asserted the literal source text of the dead code in §2.2; retargeted at
  the surviving implementation while preserving the no-inline-`onclick` guarantee they exist
  to protect.

---

## 3. Test results

| Suite | Before | After |
|---|---|---|
| unit / security / regression / system / gap / uat / integration | 5 failed (+1 system) | **2664 passed, 12 skipped, 0 failed** |
| ruff `backend/` | 3 errors | **clean** |

### ⚠️ An important testing-infrastructure finding

Most suites are **live-server integration tests** that require `python run.py` running
first — this is not documented in the README. Run them without it and you get **1184
spurious failures** that look catastrophic but are just connection errors.

Worse: with the server running at defaults you still get **~623 failures**, because the
suites blow through the 300 req/min rate limit and everything 429s. You must start the
server as `RATE_LIMIT_MAX=1000000 python run.py`. The middleware already bypasses rate
limiting when `PYTEST_CURRENT_TEST` is set, but that env var only exists **inside the pytest
process**, never in the separate server process — so the bypass can never fire for these
suites. This is a real gap worth closing (see §6).

### Remaining failures (83, all in `tests/connectors`) — environmental, not code defects

- `test_notion_connector.py` (27) — needs live Notion credentials and hardcoded workspace IDs
- `test_time_travel_debugger.py` (40 err) / `test_dag_visualizer.py` (46 err) — expect seeded
  `demo_*` runs that no longer ship; the `wf_demo_*.json` workflow files exist but nothing
  seeds the `workflow_runs` rows
- `test_goal_decomposition_scoring.py` (8 err) — expects ≥4 seeded demo goals
- `test_drift_detection.py`, `test_compliance_report.py`, `test_a2a_protocol.py` — chained
  fixtures that cascade from the above

I left these alone deliberately: "fixing" them would mean weakening real assertions. They
need a seed script (§6).

---

## 4. Security assessment

**Genuinely good.** This is well above typical for a project of this size, and the security
suite (321 tests) passes cleanly.

Strengths:
- CORS correctly refuses to pair `allow_credentials=True` with a wildcard origin
- Full security-header set incl. a real CSP; `hmac.compare_digest` for token comparison
- Terminal router: command allowlist + blocklist **and** a scrubbed subprocess environment
  so shell-outs can't inherit API keys — that second layer is the part people usually miss
- Encrypted secrets vault; opt-in bearer-token secure mode; audit log with chain verification
- Path-traversal defenses demonstrably work: `brain/agentic-os/%2e%2e%2fetc%2fpasswd.md`
  is an attack payload that got safely neutralized into a literal filename

Concerns:
1. **CSP allows `'unsafe-inline'` for scripts.** With 685 `innerHTML` assignments, XSS
   mitigation rests almost entirely on `escHtml()` discipline. There's one `escHtml`
   definition and it's used widely, but this is the largest residual risk surface.
2. **Rate limiting is in-memory** (`defaultdict(list)`) — resets on restart, and is
   per-process so it breaks under multi-worker deployment.
3. **CSRF validation only rejects a token that is present-and-invalid.** A request with no
   `X-CSRF-Token` header at all passes straight through, so it isn't real CSRF protection
   yet. Low impact for a localhost-first app, real if anyone reverse-proxies it.
4. Committed attack artifacts (the `%2e%2e%2f...` file) should be gitignored — harmless, but
   they'll trip security scanners.

---

## 5. Architecture & code quality

**What's working well**
- Clean layering, one router per feature, consistent `{ok, error}` response envelope
- No build step for the frontend — genuinely fast iteration, easy to debug
- The pane registry (`00-pane-registry.js`) with lazy renderer resolution is a neat solution
  to load-order coupling across 67 panes
- Excellent inline "BUG FIX:" comments explaining *why* a fix exists (the CSP `blob:` one is
  a model example) — this is rare and valuable
- Commit history shows disciplined systematic module-by-module review

**Structural risks**
1. **`window` as the module system.** 63 scripts sharing one global namespace is exactly what
   produced §2.2 and §2.3. I found duplicate `window.*` definitions for `toggleChatHistoryDrawer`,
   `switchHierarchyTab` (3×), `selectChatFolder`, `loadChatSessions`, `filterChatSessions` and
   `renderPQCVault`. Some are *intentional* decoration (13-ui-ergonomics wraps
   `switchHierarchyTab` and calls through — that's fine); others are silent clobbering. There
   is no way to tell which is which without reading every file. **This is the #1 maintainability
   risk in the codebase.**
2. **`app.py` is doing too much** — 970 lines mixing 150 imports, two middlewares, WebSocket
   endpoints, and CRUD for goals/cost/audit/backup/kanban/tasks that belong in routers.
3. **Over-broad exception handling.** The 7-type `except (KeyError, TypeError, ValueError,
   json.JSONDecodeError, OSError, AttributeError, RuntimeError)` tuple appears constantly. It
   reads as defensive but swallows genuine bugs — §2.1's missing tables surfaced as a blank
   500 partly because of this habit.
4. **Version is declared in 4 places** (`VERSION`, `version.py` default, `package.json`,
   `config.yaml` says `"6.0"`). `config.yaml` is stale.
5. **~350 `workspaces/` fixtures + generated artifacts are committed**, and running the test
   suite dirties the working tree (new workspaces, plugin packs, `CHANGELOG.md`, brain notes).
   `.gitignore` needs to cover these.

---

## 6. Recommendations, prioritized

**P0 — do these next**
1. **Seed script for demo data** (`scripts/seed_demo.py`): 3 `demo_*` workflow runs + 4 demo
   goals. Unblocks all 94 erroring connector tests.
2. **Fix the test-mode rate-limit bypass.** Add an explicit `AGENTIC_OS_TEST_MODE` env var the
   *server* can be started with, and document the required invocation in the README. Right
   now the intended `PYTEST_CURRENT_TEST` bypass is structurally incapable of working.
3. **Document the live-server test requirement** in the README — this costs every new
   contributor an hour of confusion.

**P1 — structural**
4. **Add a duplicate-global guard.** A tiny lint script that fails CI when two files assign
   the same `window.X` without an explicit `// intentional-override` marker would have caught
   §2.2 and §2.3 at authoring time. Highest leverage item on this list.
5. Extract the CRUD endpoints out of `app.py` into routers.
6. Move rate-limit state to SQLite or Redis so it survives restart and works multi-worker.
7. Make CSRF reject *missing* tokens, not just invalid ones.

**P2 — hardening**
8. Replace the 7-type exception tuples with narrow catches; let unexpected errors surface.
9. Single-source the version; fix `config.yaml`'s stale `"6.0"`.
10. Progressively replace `innerHTML` with `textContent`/DOM construction in the highest-risk
    panes so `'unsafe-inline'` can eventually be dropped from CSP.
11. `.gitignore` the generated `workspaces/*`, `CHANGELOG.md`, brain exports and attack artifacts.

---

## 7. Bottom line

This is a substantial and, in places, impressively engineered system — the LLM provider
abstraction, the agent-execution patterns, the terminal sandboxing and the security posture
are all better than the norm for a project this size, and the test suite is unusually broad.

The dominant risk is not any single bug but the **global-namespace frontend architecture**:
two of the four real defects I found were caused by one file silently overwriting another,
and that failure mode is invisible to code review and to the current test suite. Fixing the
duplicate-global detection (P1 #4) matters more than any individual bug fix here.

The Goals schema bug (§2.1) was the most severe issue and is now resolved; that feature was
non-functional on every fresh install.
