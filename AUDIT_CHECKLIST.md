# Agentic OS — Comprehensive Audit Checklist
## Generated: 2026-07-13 | Scope: All 74 routers + 3 services + frontend

**Audit Standards** (from previous sprint reviews):
- `ROOT = Path(__file__).resolve().parents[2]` — ALWAYS
- `try/finally: con.close()` — ALL database connections  
- `inject_steering=False` — ALL LLM calls in routers
- `JSON.stringify(id)` — ALL IDs in onclick attributes
- `escHtml()` — ALL dynamic content in HTML templates
- `r.ok` guard — ALL `fetch().json()` calls
- `gmDanger()` — ALL destructive confirmations
- `encodeURIComponent()` — ALL URL path parameters

---

## CATEGORY A — BACKEND: Wrong ROOT Path

**Pattern required:** `ROOT = Path(__file__).resolve().parents[2]`

| # | File | Current | Issue | Priority |
|---|------|---------|-------|----------|
| A-1 | `control_tower.py` | `parents[3]` | Wrong depth — resolves to `/home/user` not `agentic-os` | 🔴 Critical |

---

## CATEGORY B — BACKEND: Database Connections Missing try/finally

**Pattern required:** `con = get_conn()` → `try:` … `finally: con.close()`

Every `get_conn()` call must be wrapped. The following routers have **more `get_conn()` calls than `finally:` blocks**, meaning some connections can leak on exception.

| # | File | get_conn() | finally: | Gap | Priority |
|---|------|-----------|---------|-----|----------|
| B-1 | `control_tower.py` | 18 | 1 | **17 missing** | 🔴 Critical |
| B-2 | `workspaces.py` | 10 | 2 | 8 missing | 🔴 Critical |
| B-3 | `knowledge_graph.py` | 13 | 4 | 9 missing | 🔴 Critical |
| B-4 | `ambient.py` | 16 | 5 | 11 missing | 🔴 Critical |
| B-5 | `specs.py` | 13 | 5 | 8 missing | 🔴 Critical |
| B-6 | `steering.py` | 14 | 6 | 8 missing | 🔴 Critical |
| B-7 | `evals.py` | 12 | 7 | 5 missing | 🔴 Critical |
| B-8 | `replay.py` | 13 | 7 | 6 missing | 🔴 Critical |
| B-9 | `rag.py` | 10 | 5 | 5 missing | 🔴 Critical |
| B-10 | `secrets.py` | 5 | 0 | **5 missing** | 🔴 Critical |
| B-11 | `codesearch.py` | 8 | 0 | **8 missing** | 🔴 Critical |
| B-12 | `e2e.py` | 5 | 0 | **5 missing** | 🔴 Critical |
| B-13 | `terminal.py` | 4 | 1 | 3 missing | 🔴 Critical |
| B-14 | `hooks.py` | 11 | 7 | 4 missing | 🟠 High |
| B-15 | `codeindex.py` | 10 | 7 | 3 missing | 🟠 High |
| B-16 | `observability.py` | 10 | 6 | 4 missing | 🟠 High |
| B-17 | `hitl.py` | 10 | 5 | 5 missing | 🟠 High |
| B-18 | `crdt.py` | 8 | 4 | 4 missing | 🟠 High |
| B-19 | `arena.py` | 9 | 7 | 2 missing | 🟠 High |
| B-20 | `bugbot.py` | 9 | 3 | 6 missing | 🟠 High |
| B-21 | `chat.py` | 4 | 2 | 2 missing | 🟠 High |
| B-22 | `swarm.py` | 2 | 1 | 1 missing | 🟡 Medium |
| B-23 | `webhooks.py` | 12 | 10 | 2 missing | 🟡 Medium |
| B-24 | `websearch.py` | 8 | 7 | 1 missing | 🟡 Medium |
| B-25 | `supervisor.py` | 15 | 13 | 2 missing | 🟡 Medium |
| B-26 | `goal_manager.py` | 14 | 12 | 2 missing | 🟡 Medium |
| B-27 | `agent_identity.py` | 17 | 15 | 2 missing | 🟡 Medium |
| B-28 | `agent_monitor.py` | 17 | 15 | 2 missing | 🟡 Medium |
| B-29 | `mcp_gateway.py` | 19 | 17 | 2 missing | 🟡 Medium |
| B-30 | `connectors.py` | 13 | 11 | 2 missing | 🟡 Medium |
| B-31 | `finops.py` | 15 | 13 | 2 missing | 🟡 Medium |
| B-32 | `eval_framework.py` | 14 | 12 | 2 missing | 🟡 Medium |
| B-33 | `audit_log.py` | 12 | 10 | 2 missing | 🟡 Medium |
| B-34 | `workflow.py` | 2 | 0 | 2 missing | 🟡 Medium |
| B-35 | `multifile_agent.py` | 3 | 0 | 3 missing | 🟡 Medium |

---

## CATEGORY C — BACKEND: LLM Calls Missing `inject_steering=False`

**Pattern required:** Every `await complete(...)` or `await llm.complete(...)` in a router must pass `inject_steering=False` to prevent steering file injection into code-intelligence / review calls.

| # | File | LLM Calls | inject_false | Missing | Priority |
|---|------|-----------|--------------|---------|----------|
| C-1 | `specs.py` | 4+ (stream+complete) | 0 | ALL | 🔴 Critical |
| C-2 | `agents.py` | 1 (llm.complete) | 0 | 1 | 🔴 Critical |
| C-3 | `evals.py` | 1 (line 402, dataset run) | missing on 1 | 1 | 🟠 High |
| C-4 | `workflow.py` | 1 (node agent run) | 0 | 1 | 🟠 High |
| C-5 | `profiler.py` | 1 | 0 | 1 | 🟡 Medium |

---

## CATEGORY D — FRONTEND: Missing `r.ok` Guards on fetch().json()

**Pattern required:** `fetch(url).then(r => r.ok ? r.json() : ...)` or equivalent error check before `.json()`.

| # | Location (approx line) | Call | Priority |
|---|------------------------|------|----------|
| D-1 | ~3349 | MCP pane tool call result | 🟠 High |
| D-2 | ~3933 | Agent selector `fetch('/api/agents')` | 🟠 High |
| D-3 | ~8599, 8668 | Composer branch/preview fetches | 🟠 High |
| D-4 | ~9297 | Skills list fetch | 🟡 Medium |
| D-5 | ~9820 | Onboarding preferences | 🟡 Medium |
| D-6 | ~12593 | Secrets/API key fetch | 🟡 Medium |
| D-7 | ~13559, 13585 | Collab sessions | 🟡 Medium |
| D-8 | ~13604–13607 | Profiler dashboard multi-fetch | 🟡 Medium |
| D-9 | ~13753, 13788 | Profiler flamegraph + memory snapshot | 🟡 Medium |
| D-10 | ~15101–15102 | Hooks + event types | 🟡 Medium |
| D-11 | ~15406, 15420, 15572 | Code index stats/graph/complexity | 🟡 Medium |

---

## CATEGORY E — FRONTEND: onclick with Raw (Non-Stringified) IDs

**Pattern required:** All IDs interpolated into onclick attributes must use `JSON.stringify(id)` to prevent XSS via malicious IDs.

| # | Line | Code | Priority |
|---|------|------|----------|
| E-1 | ~3317 | `onclick="deleteTask(${t.id})"` | 🔴 Critical |
| E-2 | ~3582 | `onclick="deleteGxNode(${memId})"` | 🔴 Critical |
| E-3 | ~3626 | `onclick="deleteGxNode(${m.id})"` | 🔴 Critical |
| E-4 | ~4737, 8383 | `onclick="doDeploy('${id}')"` | 🟠 High |
| E-5 | ~2715 | `onclick="openAgentModal('${a.id}')"` | 🟠 High |
| E-6 | ~4611 | `onclick="openSkillModal('${s.id}')"` | 🟠 High |
| E-7 | ~6404 | `onclick="copyCodeBlock('${id}')"` | 🟡 Medium |
| E-8 | ~6453, 6455, 6458 | `onclick="copyMsgContent('${msgId}')"` etc | 🟡 Medium |
| E-9 | ~9599 | `onclick="applyTheme('${id}')"` | 🟡 Medium |
| E-10 | ~10155 | Webhook test button | 🟡 Medium |
| E-11 | ~16894 | `onclick="selectRole('${id}')"` | 🟡 Medium |
| E-12 | ~17724 | `onclick="applyRole('${id}')"` | 🟡 Medium |
| E-13 | ~18610, 18611 | KG traverse/relation buttons | 🟡 Medium |
| E-14 | ~18768, 18781, 18790 | RAG pipeline buttons | 🟡 Medium |
| E-15 | ~22721 | Steering save edit | 🟡 Medium |

---

## CATEGORY F — FRONTEND: fetch() Without encodeURIComponent in URL Paths

**Pattern required:** `fetch(\`/api/route/${encodeURIComponent(id)}\`)` for any variable interpolated into a URL path segment.

| # | Line | Code | Priority |
|---|------|------|----------|
| F-1 | ~2826 | `/api/agents/${S.agentModalId}` DELETE | 🟠 High |
| F-2 | ~3327, 3337 | `/api/tasks/${kbDragging}` and `${id}` | 🟠 High |
| F-3 | ~3591 | `/api/memory/${memId}` DELETE | 🟠 High |
| F-4 | ~4281, 4293 | `/api/loops/${jobId}/...` | 🟡 Medium |
| F-5 | ~6901 | `/api/sessions/${currentSessionId}/touch` | 🟡 Medium |
| F-6 | ~8356 | `/api/composer/preview/branches/${name}` | 🟡 Medium |
| F-7 | ~9286, 9307 | `/api/plugins/install/${pluginId}` | 🟡 Medium |
| F-8 | ~9928, 9954 | `/api/control/runs/${runId}` | 🟡 Medium |
| F-9 | ~9980 | `/api/control/budget-rules/${id}` | 🟡 Medium |
| F-10 | ~10023, 10052 | `/api/workspaces/${wsId}/...` | 🟡 Medium |

---

## CATEGORY G — BACKEND: Router-Specific Logic Issues

Issues found inside specific routers beyond the structural patterns above.

| # | File | Issue | Details | Priority |
|---|------|-------|---------|----------|
| G-1 | `evals.py` | Missing `inject_steering=False` | Line ~402: dataset run LLM call has no flag | 🟠 High |
| G-2 | `specs.py` | Missing `inject_steering=False` | All 4 LLM calls (`stream` + `complete`) missing flag | 🔴 Critical |
| G-3 | `agents.py` | Missing `inject_steering=False` | `llm.complete()` call line ~132 missing flag | 🟠 High |
| G-4 | `workflow.py` | Missing `inject_steering=False` + missing finally | Agent node execution missing both | 🟠 High |
| G-5 | `control_tower.py` | `parents[3]` wrong ROOT + near-zero finally blocks | ROOT resolves to wrong dir; 17 unprotected conns | 🔴 Critical |
| G-6 | `swarm.py` | 1 get_conn without finally | Minor but breaks on exception | 🟡 Medium |
| G-7 | `terminal.py` | 3 get_conn without finally | Security-sensitive router | 🟠 High |
| G-8 | `codesearch.py` | 8 get_conn, 0 finally | All connections unprotected | 🔴 Critical |
| G-9 | `e2e.py` | 5 get_conn, 0 finally | All connections unprotected | 🔴 Critical |
| G-10 | `secrets.py` | 5 get_conn, 0 finally | Sensitive data router — all unprotected | 🔴 Critical |
| G-11 | `profiler.py` | Missing `inject_steering=False` | 1 LLM call missing flag | 🟡 Medium |
| G-12 | `gitai.py` | 4 LLM calls, 0 inject_steering | All missing (but agent excluded from steering in llm.py) — verify exclusion covers gitai | 🟡 Medium |
| G-13 | `multifile_agent.py` | 3 get_conn, 0 finally | Connections unprotected | 🟠 High |
| G-14 | `knowledge_graph.py` | 9 missing finally blocks | Most KG write operations unprotected | 🔴 Critical |
| G-15 | `ambient.py` | 11 missing finally blocks | High-frequency background calls | 🔴 Critical |
| G-16 | `arena.py` | 2 missing finally blocks | Arena battle results can leak | 🟠 High |
| G-17 | `bugbot.py` | 6 missing finally blocks | Code review storage can leak | 🟠 High |
| G-18 | `chat.py` | 2 missing finally blocks | Core chat path — high impact | 🟠 High |
| G-19 | `hitl.py` | 5 missing finally blocks | Governance-critical path | 🟠 High |
| G-20 | `observability.py` | 4 missing finally blocks | Trace storage can corrupt | 🟠 High |
| G-21 | `steering.py` | 8 missing finally blocks | Steering file storage | 🟠 High |
| G-22 | `rag.py` | 5 missing finally blocks | RAG pipeline storage | 🟠 High |
| G-23 | `replay.py` | 6 missing finally blocks | Replay storage | 🟠 High |
| G-24 | `codeindex.py` | 3 missing finally blocks | Index storage | 🟡 Medium |
| G-25 | `crdt.py` | 4 missing finally blocks | Collaborative doc storage | 🟡 Medium |
| G-26 | `hooks.py` | 4 missing finally blocks | Event hook storage | 🟡 Medium |
| G-27 | `webhooks.py` | 2 missing finally blocks | Webhook delivery storage | 🟡 Medium |

---

## CATEGORY H — SERVICES AUDIT

| # | File | Issue | Priority |
|---|------|-------|----------|
| H-1 | `memory_db.py` | `audit_log()` function uses no try/finally | 🟡 Medium |
| H-2 | `memory_db.py` | `agents_seed_defaults()` does not close con in finally | 🟡 Medium |
| H-3 | `scheduler.py` | `_run_goal_loop` imports get_conn inline but no finally | 🟡 Medium |
| H-4 | `llm.py` | `_stub_reply` returns generic text — no per-agent personalisation | 🟢 Low |

---

## CATEGORY I — FRONTEND: Additional Issues

| # | Issue | Location | Priority |
|---|-------|----------|----------|
| I-1 | `deferredPrompt.prompt()` — native browser prompt (PWA install, acceptable) | ~18917 | ✅ Acceptable |
| I-2 | 287 innerHTML assignments without visible escHtml — need case-by-case review | Various | 🟡 Medium |
| I-3 | `fetch('/api/analytics/dashboard?days=${days}')` — `days` is a number, safe | ~4429 | ✅ Safe (number) |
| I-4 | `fetch('/api/analytics/export?fmt=csv&days=${days}')` — same as above | ~4452 | ✅ Safe (number) |
| I-5 | `fetch('/api/deploy/${provider}')` — `provider` from dropdown, should encode | ~4780 | 🟡 Medium |
| I-6 | `fetch('/api/plugins/install/${pluginId}')` — pluginId from marketplace JSON | ~9286 | 🟠 High |

---

## SUMMARY BY PRIORITY

| Priority | Count | Categories |
|----------|-------|-----------|
| 🔴 Critical | 15 | A-1, B-1–12, C-1, G-2, G-5, G-8–10, G-14–15 |
| 🟠 High | 34 | B-13–21, C-2–4, D-1–3, E-1–6, F-1–3, G-1,3,4,6–7,13,16–23 |
| 🟡 Medium | 38 | B-22–35, C-5, D-4–11, E-7–15, F-4–10, G-11–12,24–27, H-1–4, I-2,5 |
| ✅ Acceptable | 3 | I-1, I-3, I-4 |

**Total issues to fix: 87** across 74 router files + frontend + services

---

## AUDIT EXECUTION ORDER (Recommended)

### Pass 1 — Critical Safety (Fix First)
1. `control_tower.py` — ROOT fix + all 18 DB connections
2. `codesearch.py` — 8 unprotected connections
3. `e2e.py` — 5 unprotected connections  
4. `secrets.py` — 5 unprotected connections (sensitive data)
5. `knowledge_graph.py` — 9 unprotected connections
6. `ambient.py` — 11 unprotected connections
7. `specs.py` — inject_steering=False on all 4 LLM calls

### Pass 2 — High Impact (DB Leaks + Frontend XSS)
8. `workspaces.py`, `steering.py`, `evals.py`, `replay.py`, `rag.py`
9. `terminal.py`, `hitl.py`, `chat.py`, `bugbot.py`, `arena.py`
10. Frontend: E-1 to E-6 (raw onclick IDs)
11. Frontend: D-1 to D-3 (missing r.ok guards)
12. `agents.py`, `workflow.py` — inject_steering fixes

### Pass 3 — Medium / Polish
13. Remaining B-category DB connection gaps
14. Remaining D-category r.ok guards
15. Remaining E-category onclick IDs
16. Remaining F-category encodeURIComponent
17. Services H-1 to H-4
