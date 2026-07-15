# Agentic OS — Complete Testing Gap Analysis
**Date:** 2026-07-14 | **Platform:** v6.0 | **Author:** Arena.ai Testing Agent

---

## Current Test Inventory (What's Done)

| Suite | Tests | Pass Rate | Runtime |
|-------|-------|-----------|---------|
| Unit | 852 | 851/852 = 99.9% | ~23s |
| Integration | 395 | 393/395 = 99.5% | ~130s |
| System | 263 | 262/263 = 99.6% | ~110s |
| UAT | 275 | 275/275 = 100% | ~30s |
| Usability | 455 | 455/455 = 100% | ~20s |
| Security | 321 | 319/321 = 99.4% | ~30s |
| Performance | 325 | ~310/325 = ~95% | ~200s+ |
| Regression | 127 | 126/127 = 99.2% | ~60s |
| Sprint A–D | 215 | 215/215 = 100% | ~30s |
| **TOTAL** | **3,228** | **~3,206/3,228 = 99.3%** | ~10 min |

**Grand total routes in platform:** 706 API endpoints across 74 routers

---

## Active Failures (Fix These First — Priority 1)

### F-1: Webhook `httpbin.org` Network Flakiness (4 suites)
**Failing in:** `unit/test_29`, `integration/test_flow_11`, `system/test_sys_09`, `regression/test_reg_03`
**Root cause:** Tests call `httpbin.org/post` (external network) which times out intermittently in the sandbox environment.
**Fix:** Replace `httpbin.org` with a local mock endpoint or `localhost:8787` self-call for webhook test URL.

```python
# Current (flaky — external network)
"url": "https://httpbin.org/post"

# Fix — use platform's own health endpoint as webhook target
"url": "http://127.0.0.1:8787/api/health"
```

### F-2: Performance Test `supervisor/run` field name (1 test)
**Failing in:** `perf/test_perf_09_feature_correctness.py::TestSupervisorOrchestration`
**Root cause:** Test sends `{"task": "..."}` but supervisor expects `{"goal": "..."}`.
**Fix:** Change field name to `goal` in the perf test.

### F-3: Marketplace install/uninstall state accumulation (1 test)
**Failing in:** `integration/test_flow_16::test_06_marketplace_install_uninstall`
**Root cause:** After many test runs, the pack is already installed and re-install fails.
**Fix:** Add a pre-test uninstall step (idempotent guard).

---

## Testing Gaps by Category

### GAP-1: Untested API Routes (158 routes = 22% of all routes)
These routes exist and are registered but have **zero test coverage** anywhere.

#### High Priority (user-facing, business-critical)
| Route Group | Count | Routes |
|-------------|-------|--------|
| `/api/preview/*` | 10 | `read, save, new, commit, scaffold, restore, delete, files, branch, branches` |
| `/api/specs/*` (deep) | 8 | `design, tasks, execute, run-all, requirements, artifacts` |
| `/api/rag/*` (docs) | 7 | `upload, retrieve, documents CRUD per pipeline` |
| `/api/github/*` (deep) | 9 | `PR creation, branches, gists, pages deploy, sync, pull` |
| `/api/integrations/*` (deep) | 7 | `scaffold, stripe, auth wire, docs/types` |
| `/api/marketplace/*` (advanced) | 8 | `trending, new-arrivals, check-updates, update-all, featured, categories, publish` |
| `/api/replay/*` (frames) | 6 | `frames, frame/N, rerun-from/N, diff` |
| `/api/connectors/*` (ops) | 4 | `configure PATCH, execute POST, test POST, executions GET` |
| `/api/sessions/*` (advanced) | 4 | `messages, export, branch, touch` |
| `/api/imagegen/*` (advanced) | 4 | `inpaint, variations, inject-into-code, figma import` |

#### Medium Priority (infrastructure/admin)
| Route Group | Count | Routes |
|-------------|-------|--------|
| `/api/pm/*` | 4 | Package manager: `list, add, remove, search` |
| `/api/tauri/*` | 5 | Desktop build: `log, cancel, install-cli, artifacts, dev` |
| `/api/db/supabase/*` | 5 | Cloud DB: `status, tables, query, insert, ai-setup` |
| `/api/pluginsdk/*` (advanced) | 4 | `publish, export, import, skill run` |
| `/api/webhooks/*` (ops) | 3 | `trigger, test, events` |
| `/api/steering/*` (advanced) | 3 | `toggle, learn/promote, learned/clear` |
| `/api/hooks/*` (ops) | 2 | `toggle, run` |
| `/api/system/*` (HMR) | 3 | `hmr status, trigger, get` |
| `/api/tunnel/info` | 1 | Tunnel info endpoint |

#### Lower Priority (specialized/desktop)
| Route Group | Count | Routes |
|-------------|-------|--------|
| `/api/agent-identity/*` (advanced) | 3 | `rotate-keys, tokens list, permission delete` |
| `/api/hitl/*` (wait/decide) | 2 | `interrupt wait, decide` |
| `/api/obsidian/*` (advanced) | 3 | `watch start/stop, backlinks` |
| `/api/mcp-gateway/*` (toggle) | 2 | `server toggle, policy toggle` |
| `/api/collab/*` (state) | 2 | `session state GET/POST` |
| `/api/fusion/*` (advanced) | 3 | `route/models, subagent, optimize-cost` |
| `/api/agent-monitor/stream` | 1 | SSE stream endpoint |
| `/api/crdt/docs/{id}/restore/{revision}` | 1 | CRDT restore from snapshot |
| `/api/multitab/*` (refresh) | 3 | `activate, refresh, refresh-all` |
| `/api/memory/qdrant/*` | 2 | `status, sync-all` |
| `/api/ws/broadcast` + `/ws/status` | 2 | WebSocket broadcast + status |
| `/manifest.json` + `/sw.js` | 2 | PWA manifest and service worker |

---

### GAP-2: WebSocket Live Connection Testing (ZERO coverage)
**Severity: High** — The platform has a WebSocket endpoint (`/ws`) used for real-time agent communication, but **no test ever opens a live WebSocket connection**.

What's missing:
- WebSocket handshake + upgrade verification
- Real-time message broadcast (`POST /api/ws/broadcast` then receive via WS)
- Connection persistence under load
- Reconnection after disconnect
- Message ordering guarantees

**Recommended tool:** `websockets` Python library or `httpx`'s WebSocket support.

---

### GAP-3: End-to-End Browser Automation (ZERO coverage)
**Severity: High** — No Playwright/Selenium tests verify the actual frontend UI in a browser. All tests hit the API directly — the JavaScript rendering layer is only tested via static HTML analysis.

What's missing:
- Nav pane switching actually changes the visible pane
- Forms submit and show the correct toast notification
- Agent chat input → real SSE response → displayed in UI
- Modal dialogs (gmAlert/gmConfirm/gmDanger) open and close correctly
- Keyboard shortcuts actually trigger nav
- Mobile/responsive layout

**Recommended:** `pip install playwright && playwright install chromium`

---

### GAP-4: Contract/Schema Validation Testing (Partial coverage)
**Severity: Medium** — API responses are tested for content but not for strict schema compliance.

What's missing:
- OpenAPI schema validation for every response body
- Pydantic model enforcement at the boundary
- Required fields actually rejected on POST with 422 (not silently ignored)
- Field types enforced (integer not string, etc.)
- Response schema never changes between calls (backward compatibility)

---

### GAP-5: Data Persistence Across Restarts (ZERO coverage)
**Severity: Medium** — No test verifies that data written before a server restart is readable after restart.

What's missing:
- Write data → restart server → verify data still present
- SQLite WAL checkpoint integrity after restart
- Scheduler jobs re-register after restart (confirmed via logs but not asserted)
- Agent identity keys survive restart (keys stored in DB, should persist)

---

### GAP-6: Chaos/Fault Injection Testing (ZERO coverage)
**Severity: Medium** — No tests deliberately inject failures to verify graceful recovery.

What's missing:
- DB connection pool exhaustion recovery
- Disk full simulation (SQLite SQLITE_FULL error handling)
- Network timeout during LLM call → proper error propagation
- Malformed SQLite database recovery
- Concurrent schema migration safety
- Memory exhaustion graceful degradation

---

### GAP-7: Multi-Tenant Data Isolation (ZERO coverage)
**Severity: Medium** — Platform is local-first (single user), but Sprint C connectors and Sprint D FinOps have scoping concepts (`scope_id`, `agent_id`, `goal_id`) that need isolation verification.

What's missing:
- Cost entries for `agent_id=brain` don't appear in `agent_id=builder` filtered view
- Budget caps scoped to one agent don't block another
- Eval suites for one agent don't contaminate another's summary
- HITL interrupts for one agent don't show in another's queue

---

### GAP-8: Long-Running Scheduler Jobs (Partial coverage)
**Severity: Low-Medium** — APScheduler runs 4 background jobs. Tests verify they register but don't test their actual execution effects.

What's missing:
- `_memory_auto_index` actually re-indexes memory after run
- `_daily_standup` generates the standup report
- `_cost_digest` writes cost summary to the audit log
- `_agent_status_cleanup` clears stale agent statuses

---

### GAP-9: Performance Under Real Data Volume (Partial)
**Severity: Low-Medium** — Performance tests add synthetic data but don't test the platform at production-scale volumes.

What's missing:
- 10,000+ memory entries: search still < 100ms
- 50,000+ audit log entries: chain verify still completes
- 1,000+ tasks: Kanban list still < 200ms
- 100+ agents: roster load still < 50ms
- 500+ cost ledger entries: dashboard aggregation still < 500ms

---

### GAP-10: Localization/Encoding Edge Cases (ZERO coverage)
**Severity: Low** — No tests use non-ASCII input.

What's missing:
- Unicode agent names (e.g., "脑", "نظام", "🧠 Brain")
- RTL text in task titles
- Emoji in memory content
- Null bytes in string fields (already partially covered in security)
- Very long Unicode strings (> 10,000 chars)

---

## Priority Roadmap to 100% Coverage

### Phase 1 — Fix Active Failures (1–2 hours)
```
1. Fix webhook tests: replace httpbin.org with local mock URL
2. Fix perf test: task→goal field name in supervisor
3. Fix marketplace: add idempotent uninstall guard
```

### Phase 2 — Close High-Priority Gaps (4–8 hours)
```
4. Write test_gap_01_untested_routes.py — covers all 158 untested routes
5. Write test_gap_02_websocket.py — live WS connection tests
6. Write test_gap_03_data_persistence.py — restart survival tests
7. Write test_gap_04_contract_schema.py — OpenAPI schema validation
```

### Phase 3 — Close Medium Gaps (8–16 hours)  
```
8. Write test_gap_05_chaos_fault.py — fault injection tests
9. Write test_gap_06_isolation.py — data isolation per agent/goal/scope
10. Write test_gap_07_scheduler.py — background job effect verification
11. Write test_gap_08_volume_scale.py — production-scale data volume tests
```

### Phase 4 — Browser Automation (1–2 days)
```
12. Install Playwright: pip install playwright && playwright install chromium
13. Write test_e2e_browser_01_navigation.py — full pane navigation
14. Write test_e2e_browser_02_chat.py — chat send/receive UI
15. Write test_e2e_browser_03_forms.py — CRUD forms in browser
16. Write test_e2e_browser_04_modals.py — modal system verification
17. Write test_e2e_browser_05_streaming.py — SSE visual streaming
```

### Phase 5 — Polish (Ongoing)
```
18. Localization/encoding edge cases
19. Accessibility automated scan (axe-playwright)
20. Visual regression screenshots (pixel-diff)
```

---

## Recommended Next Test Files to Write

```
tests/
├── gap/
│   ├── conftest.py
│   ├── test_gap_01_untested_routes.py    # 158 untested routes → no 5xx
│   ├── test_gap_02_websocket.py          # WS handshake, broadcast, receive
│   ├── test_gap_03_data_persistence.py   # data survives server restart
│   ├── test_gap_04_contract_schema.py    # OpenAPI schema compliance
│   ├── test_gap_05_chaos_fault.py        # fault injection + recovery
│   ├── test_gap_06_isolation.py          # per-agent data isolation
│   ├── test_gap_07_scheduler.py          # background job effects
│   └── test_gap_08_volume_scale.py       # 10k+ records performance
└── e2e_browser/                          # needs: playwright install
    ├── conftest.py
    ├── test_e2e_browser_01_navigation.py
    ├── test_e2e_browser_02_chat.py
    ├── test_e2e_browser_03_forms.py
    ├── test_e2e_browser_04_modals.py
    └── test_e2e_browser_05_streaming.py
```

---

## Current Test Coverage Map

```
                           UNIT  INTG  SYS  UAT  USE  SEC  PERF  REG
─────────────────────────────────────────────────────────────────────
Core API routes             ✅    ✅    ✅   ✅   ✅   ✅    ✅   ✅
Sprint A (Audit/Identity)   ✅    ✅    ✅   ✅   ✅   ✅    ✅   ✅
Sprint B (Supervisor/Goals) ✅    ✅    ✅   ✅   ✅   ✅    ✅   ✅
Sprint C (MCP/Connectors)   ✅    ✅    ✅   ✅   ✅   ✅    ✅   ✅
Sprint D (Monitor/FinOps)   ✅    ✅    ✅   ✅   ✅   ✅    ✅   ✅
158 untested routes         ❌    ❌    ❌   ❌   ❌   ❌    ❌   ❌
WebSocket live              ❌    ❌    ❌   ❌   ❌   ❌    ❌   ❌
Browser/UI automation       ❌    ❌    ❌   ❌   ❌   ❌    ❌   ❌
Data persistence (restart)  ❌    ❌    ❌   ❌   ❌   ❌    ❌   ❌
Schema contract validation  ⚠️    ⚠️    ⚠️   ✅   ✅   ✅    ✅   ✅
Fault injection/chaos       ❌    ❌    ❌   ❌   ⚠️   ⚠️    ❌   ❌
Agent data isolation        ❌    ❌    ❌   ❌   ❌   ❌    ❌   ❌
Scheduler job effects       ⚠️    ⚠️    ❌   ❌   ❌   ❌    ❌   ❌
10k+ record volume          ❌    ❌    ❌   ❌   ❌   ❌    ⚠️   ❌
Unicode/encoding edges      ❌    ❌    ❌   ❌   ❌   ⚠️    ❌   ❌

✅ = Full coverage  ⚠️ = Partial  ❌ = Zero coverage
```
