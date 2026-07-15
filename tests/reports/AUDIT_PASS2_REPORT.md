# Audit Pass 2 — High Impact Fixes
## Completion Report · 2026-07-13

**Status:** ✅ COMPLETE
**Regression tests:** 215/215 passing (100%, no regressions)
**Files modified:** 15 backend routers + frontend/index.html

---

## Backend Fixes — DB Connection Leaks (Category B)

All 13 routers with unprotected `get_conn()` calls now have full `try/finally: con.close()` coverage.

| Router | Before (gap) | After | Notes |
|--------|-------------|-------|-------|
| `workspaces.py` | 8 missing | ✅ 0 gap | Seed block, activate, update all fixed; variable scope bug also caught and fixed |
| `steering.py` | 8 missing | ✅ 0 gap | _ensure_schema seed loops, delete, toggle, store_learned loop all fixed |
| `evals.py` | 5 missing | ✅ 0 gap | _ensure_schema, dataset create, run_dataset inner conn fixed |
| `replay.py` | 6 missing | ✅ 0 gap | Replay save, history, branch, SSE inner conn all fixed |
| `rag.py` | 5 missing | ✅ 0 gap | add_document complex insert loop wrapped; FTS rebuild moved inside try |
| `terminal.py` | 3 missing | ✅ 0 gap | get_history if/else, clear_history if/else both fixed |
| `hitl.py` | 5 missing | ✅ 0 gap | _ensure_schema, create_interrupt, decide_interrupt (early-return bug fixed), undo_snapshot fixed |
| `chat.py` | 2 missing | ✅ 0 gap | chat_history where-clause block, clear_chat fixed |
| `bugbot.py` | 6 missing | ✅ 0 gap | _ensure_schema, review_code inner conn, list_reviews, feedback all fixed |
| `arena.py` | 2 missing | ✅ 0 gap | _ensure_schema seed loop, arena_start insert fixed |
| `swarm.py` | 1 missing | ✅ 0 gap | swarm_history save fixed |
| `webhooks.py` | 2 missing | ✅ 0 gap | test_webhook and log_event fixed |
| `websearch.py` | 1 missing | ✅ 0 gap | Already had local `get_conn()` function — confirmed all 7 calls are wrapped |

### Secondary Bugs Caught During Fix

Three routers had logic bugs exposed when the auto-fixer restructured code:

**`hitl.py` — `decide_interrupt()` early return inside finally**
The auto-fixer moved `return {"ok":False,"error":"Interrupt not found"}` into the `finally:` block, which would have always executed even on success. Fixed: early return moved inside the `try:` block, `finally:` only closes the connection.

**`workspaces.py` — variable `wid` out of scope**
The `if count == 0:` seed block defined `wid` inside the if, but `CURRENT_FILE.write_text(wid)` was placed at the same level as the if-block (outside it), causing an `UnboundLocalError` at startup. Fixed: `write_text` moved inside the if block.

**`steering.py` — 3 separate indentation errors**
For-loops and if-blocks in `_ensure_schema`, `delete_steering`, `toggle_steering`, and `store_learned` had their bodies collapsed to the parent indent level. All fixed with proper 4-space indentation.

---

## Backend Fixes — inject_steering=False (Category C)

| Router | LLM calls | Before | After |
|--------|-----------|--------|-------|
| `agents.py` | 1 | missing | ✅ `inject_steering=False` added to `llm.complete()` |
| `workflow.py` | 1 | missing | ✅ `inject_steering=False` added to `llm_svc.complete()` in agent node execution |

**Why this matters:** Without `inject_steering=False`, every agent test call and workflow node execution would have the user's steering files (architecture.md, coding-style.md, etc.) injected into the system prompt — causing the LLM to apply project-specific constraints to generic agent calls and producing hallucinated, project-biased results.

---

## Frontend Fixes — XSS Prevention (Category E)

Six `onclick` attributes were interpolating raw values directly into HTML event handlers. A malicious ID containing a quote or script fragment could execute arbitrary JavaScript.

All fixed with `JSON.stringify()`:

| Issue | Before | After |
|-------|--------|-------|
| E-1 deleteTask | `deleteTask(${t.id})` | `deleteTask(${JSON.stringify(t.id)})` |
| E-2 deleteGxNode | `deleteGxNode(${memId})` | `deleteGxNode(${JSON.stringify(memId)})` |
| E-3 deleteGxNode | `deleteGxNode(${m.id})` | `deleteGxNode(${JSON.stringify(m.id)})` |
| E-4 doDeploy (×2) | `doDeploy('${id}')` | `doDeploy(${JSON.stringify(id)})` |
| E-5 openAgentModal (×2) | `openAgentModal('${a.id}')` | `openAgentModal(${JSON.stringify(a.id)})` |
| E-6 openSkillModal | `openSkillModal('${s.id}')` | `openSkillModal(${JSON.stringify(s.id)})` |

---

## Frontend Fixes — Crash Prevention (Category D)

Twelve `fetch().then(r=>r.json())` calls lacked an `r.ok` guard. Any non-200 response (404, 500, network error) would throw a `SyntaxError: Unexpected end of JSON input` that could silently crash entire UI sections or leave them in broken state.

All fixed with the pattern `.then(r=>r.ok?r.json():fallback)`:

| Issue | Location | Fallback |
|-------|----------|---------|
| D-1 Kanban task create | Task board | `null` (with `j?.ok` guard) |
| D-2 Agents status poll (interval) | Agent list refresh | `null` (with early return) |
| D-3a Composer file history (on open) | Studio status bar | `[]` |
| D-3b Composer file history (post-commit) | Studio status bar | `[]` |
| D-4 Skills list | Plugin/skills pane | `[]` |
| D-5 Onboarding preferences | Settings init | `{}` (with early return) |
| D-6 Secrets API key check | Settings panel | `{}` |
| D-7a Collab session create | Topbar share | `{}` |
| D-7b Collab session restore | Session init | `{}` |
| D-8 Profiler dashboard (Promise.all) | 4 parallel fetches | `{}` per fetch with `.catch(()=>({}))` |
| D-9a Profiler flamegraph | Flame view | `{}` with `.catch(()=>({}))` |
| D-9b Profiler memory snapshot | Memory pane | `{}` (variable also renamed `r` → `snap` to avoid shadowing) |

---

## Final Verification

### Static Analysis
```
DB Coverage (13 routers):    ✅ ALL gaps closed
inject_steering (2 routers): ✅ ALL calls covered
Frontend E-fixes (6 items):  ✅ ALL JSON.stringify applied
Frontend D-fixes (12 items): ✅ ALL r.ok guards added
Syntax errors introduced:     0 (all indentation issues fixed)
```

### Live Endpoint Tests
```
✅ GET /api/workspaces     → 2 workspaces
✅ GET /api/steering       → 5 files
✅ GET /api/hitl/stats     → total=16
✅ GET /api/knowledge-graph/stats → entities=0
✅ GET /api/audit-log/verify → ok=True entries=398
✅ GET /api/evals/runs     → OK
✅ GET /api/specs          → count=1
```

### Regression Tests
```
215/215 = 100% ✅  (25.4s)
Sprint A: 52/52   Sprint B: 69/69
Sprint C: 49/49   Sprint D: 45/45
```

---

## Pass 3 Remaining (Medium Priority)

Per `AUDIT_CHECKLIST.md`, the remaining 🟡 Medium items include:

**Backend DB (minor gaps):**
- `codeindex.py` (3 missing), `crdt.py` (4 missing), `hooks.py` (4 missing), `websearch.py` (1 — already confirmed fixed)
- Various Sprint A/B/C routers with 1–2 remaining gaps

**Frontend (medium):**
- E-7 through E-15: remaining onclick raw IDs (copyCodeBlock, copyMsgContent, applyTheme, etc.)
- F-1 through F-10: missing `encodeURIComponent` in fetch URL paths
- I-5/I-6: `doDeploy('${provider}')` and plugin install path encoding

**Services:**
- H-1/H-2: `memory_db.py` internal `audit_log()` and seed functions
- H-3: `scheduler.py` `_run_goal_loop` inline get_conn
