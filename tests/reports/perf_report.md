# Agentic OS — Performance Test Report
**Date:** 2026-07-13  
**Result:** ✅ **112/112 — 100% PASS**  
**Total Duration:** ~2m 40s  
**Server:** Single-process uvicorn, SQLite, port 8787

---

## Summary

| Test Suite | Tests | Pass | Fail | Coverage |
|-----------|-------|------|------|---------|
| `test_perf_01_latency.py` | 51 | 51 | 0 | P50/P95/P99 per endpoint |
| `test_perf_02_throughput.py` | 20 | 20 | 0 | RPS + concurrency stress |
| `test_perf_03_scenarios.py` | 14 | 14 | 0 | End-to-end scenario timing |
| `test_perf_04_volume_reliability.py` | 20 | 20 | 0 | Volume + reliability |
| `test_perf_05_sla_report.py` | 7 | 7 | 0 | Full SLA compliance |
| **Total** | **112** | **112** | **0** | **100%** |

---

## SLA Thresholds Defined

| Category | P99 SLA | Rationale |
|----------|---------|-----------|
| Health endpoint | ≤ 50ms (HTTP roundtrip) | Platform heartbeat |
| Simple reads (list, get) | ≤ 50ms | UI responsiveness |
| DB-backed reads | ≤ 100ms | SQLite query time |
| Write operations | ≤ 150ms | Create/update with DB write |
| Complex queries (JOIN) | ≤ 500ms | Multi-table aggregations |
| In-memory endpoints (docs) | ≤ 30ms | No I/O path |
| Min throughput (reads) | ≥ 100 RPS | 10 concurrent clients |
| Min throughput (health) | ≥ 500 RPS | Monitoring overhead |
| Success rate | ≥ 99.9% | Zero tolerance for 5xx |

---

## Latency Results (Measured P99)

### Tier 1: Health & Bootstrap
| Endpoint | P50 | P95 | P99 | SLA | Status |
|----------|-----|-----|-----|-----|--------|
| GET /api/health | 1.9ms | 2.0ms | 2.3ms | ≤50ms | ✅ |
| GET /openapi.json | — | — | 5.4ms | ≤200ms | ✅ |
| GET / (frontend) | — | — | 8.4ms | ≤200ms | ✅ |

### Tier 2: Agent & Chat
| Endpoint | P50 | P95 | P99 | SLA | Status |
|----------|-----|-----|-----|-----|--------|
| GET /api/agents | 4.1ms | 4.5ms | 4.7ms | ≤50ms | ✅ |
| GET /api/chat/history | — | — | 4.9ms | ≤50ms | ✅ |
| POST /api/agents (create) | 8.5ms | — | 8.9ms | ≤150ms | ✅ |
| GET /api/sessions | — | — | 16.8ms | ≤50ms | ✅ |

### Tier 3: Tasks & Kanban
| Endpoint | P50 | P95 | P99 | SLA | Status |
|----------|-----|-----|-----|-----|--------|
| GET /api/tasks | 7.8ms | 7.9ms | 8.1ms | ≤50ms | ✅ |
| POST /api/tasks (create) | 5.6ms | — | 7.0ms | ≤100ms | ✅ |
| POST /api/kanban/move | 4.5ms | — | 24.3ms | ≤100ms | ✅ |

### Tier 4: Memory / Galaxy
| Endpoint | P50 | P95 | P99 | SLA | Status |
|----------|-----|-----|-----|-----|--------|
| GET /api/memory/list | 4.3ms | — | 6.0ms | ≤50ms | ✅ |
| GET /api/memory/stats | — | — | 7.5ms | ≤50ms | ✅ |
| POST /api/memory/add | 4.6ms | — | 4.9ms | ≤100ms | ✅ |
| GET /api/memory/search (FTS) | 3.4ms | — | 4.1ms | ≤100ms | ✅ |
| GET /api/memory/export | — | — | 69.4ms | ≤300ms | ✅ |

### Tier 5: License & Profile (File I/O)
| Endpoint | P50 | P95 | P99 | SLA | Status |
|----------|-----|-----|-----|-----|--------|
| GET /api/license/status | 3.1ms | — | 3.8ms | ≤50ms | ✅ |
| GET /api/license/tiers | — | — | 12.3ms | ≤30ms | ✅ |
| GET /api/license/pane-access/chat | — | — | 3.6ms | ≤50ms | ✅ |
| GET /api/profile | 3.1ms | — | 4.5ms | ≤50ms | ✅ |
| GET /api/profile/ui-config | — | — | 3.6ms | ≤100ms | ✅ |
| PATCH /api/profile | 2.8ms | — | 3.6ms | ≤200ms | ✅ |

### Tier 6: Docs Center (Pure In-Memory)
| Endpoint | P50 | P95 | P99 | SLA | Status |
|----------|-----|-----|-----|-----|--------|
| GET /api/docs/quick-starts | 3.4ms | — | 7.1ms | ≤30ms | ✅ |
| GET /api/docs/features | — | — | 4.5ms | ≤30ms | ✅ |
| GET /api/docs/faq | — | — | 3.9ms | ≤30ms | ✅ |
| GET /api/docs/shortcuts | — | — | 3.8ms | ≤30ms | ✅ |
| GET /api/docs/search | — | — | 4.6ms | ≤50ms | ✅ |
| GET /api/docs/contextual/chat | — | — | 4.7ms | ≤50ms | ✅ |
| POST /api/docs/feedback | — | — | 4.5ms | ≤50ms | ✅ |

### Tier 7: Database Studio
| Endpoint | P50 | P95 | P99 | SLA | Status |
|----------|-----|-----|-----|-----|--------|
| GET /api/db/sqlite/tables | 12.5ms | — | 16.5ms | ≤100ms | ✅ |
| POST /api/db/sqlite/query (SELECT 1) | 2.3ms | — | 3.9ms | ≤50ms | ✅ |
| POST /api/db/sqlite/query (COUNT*) | — | — | 3.8ms | ≤100ms | ✅ |
| POST /api/db/sqlite/query (JOIN) | 3.5ms | — | 3.7ms | ≤500ms | ✅ |

### Tier 8: Knowledge Base
| Endpoint | P50 | P95 | P99 | SLA | Status |
|----------|-----|-----|-----|-----|--------|
| GET /api/knowledge-graph/stats | — | — | 4.5ms | ≤100ms | ✅ |
| GET /api/knowledge-graph/entities | — | — | 5.8ms | ≤200ms | ✅ |
| GET /api/rag/pipelines | — | — | 6.8ms | ≤200ms | ✅ |
| GET /api/websearch/history | — | — | 4.2ms | ≤100ms | ✅ |
| GET /api/websearch/suggest | — | — | 6.8ms | ≤100ms | ✅ |
| GET /api/prompts | 6.2ms | — | 6.5ms | ≤100ms | ✅ |
| GET /api/steering | — | — | 6.1ms | ≤100ms | ✅ |
| GET /api/workflow | — | — | 6.5ms | ≤150ms | ✅ |
| GET /api/specs | — | — | 5.5ms | ≤150ms | ✅ |

### Tier 9: Platform Infrastructure
| Endpoint | P50 | P95 | P99 | SLA | Status |
|----------|-----|-----|-----|-----|--------|
| GET /api/hooks | — | — | 16.2ms | ≤200ms | ✅ |
| GET /api/webhooks | — | — | 5.9ms | ≤200ms | ✅ |
| GET /api/mcp/tools | — | — | 2.2ms | ≤200ms | ✅ |
| GET /api/plugins/installed | — | — | 5.3ms | ≤200ms | ✅ |
| GET /api/skills | — | — | 3.0ms | ≤200ms | ✅ |
| GET /api/workspaces | — | — | 11.3ms | ≤200ms | ✅ |
| GET /api/secrets/list | — | — | 4.6ms | ≤200ms | ✅ |
| GET /api/analytics/kpis | — | — | 3.7ms | ≤200ms | ✅ |

---

## Throughput Results (10 concurrent clients)

| Endpoint | RPS | P50 | P95 | OK% | SLA |
|----------|-----|-----|-----|-----|-----|
| GET /api/health | 950.8 | 9.1ms | 25.3ms | 100% | ≥500 ✅ |
| GET /api/agents | 354.6 | 27.2ms | 53.3ms | 100% | ≥100 ✅ |
| GET /api/tasks | 145.9 | 63.4ms | 102.9ms | 100% | ≥100 ✅ |
| GET /api/memory/list | 331.1 | 30.2ms | 45.8ms | 100% | ≥100 ✅ |
| GET /api/sessions | 304.8 | 32.0ms | 48.7ms | 100% | ≥100 ✅ |
| GET /api/prompts | 214.5 | 44.3ms | 71.0ms | 100% | ≥100 ✅ |
| GET /api/license/status | 464.5 | 21.5ms | 28.4ms | 100% | ≥200 ✅ |
| GET /api/profile | 424.3 | 23.7ms | 30.9ms | 100% | ≥200 ✅ |
| GET /api/docs/quick-starts | 403.9 | 24.8ms | 31.5ms | 100% | ≥300 ✅ |
| POST /api/db/sqlite/query | 747.4 | 13.3ms | 16.5ms | 100% | ≥200 ✅ |

---

## Scenario Timing

| Scenario | Steps | Total | Budget | Status |
|---------|-------|-------|--------|--------|
| New User Boot (6 API calls) | 6 | <100ms | ≤200ms | ✅ |
| Onboarding Flow | 6 | <150ms | ≤300ms | ✅ |
| Create & Use Agent | 4 | <100ms | ≤400ms | ✅ |
| Kanban Full Cycle | 5 | <100ms | ≤400ms | ✅ |
| Web Search Grounding | 5 | <100ms | ≤300ms | ✅ |
| Settings Configuration | 6 | <100ms | ≤400ms | ✅ |
| Documentation Lookup (in-memory) | 6 | <50ms | ≤150ms | ✅ |
| DB Studio Session | 5 | <100ms | ≤600ms | ✅ |
| License Upgrade Flow | 6 | <100ms | ≤300ms | ✅ |
| Secret Vault Operations | 5 | <100ms | ≤400ms | ✅ |
| Knowledge Graph Exploration | 5 | <100ms | ≤600ms | ✅ |
| 5 simultaneous user boots | — | max<500ms | ≤2s | ✅ |
| 10 simultaneous task reads | — | max<300ms | ≤500ms | ✅ |

---

## Concurrency & Reliability

| Test | Result | Status |
|------|--------|--------|
| 20 concurrent health checks | 20/20 succeeded | ✅ |
| 30 concurrent reads (different endpoints) | 0 server errors | ✅ |
| 50 concurrent DB queries | 0 server errors | ✅ |
| 10 concurrent task creates | 10 unique IDs | ✅ |
| 15 concurrent writes | 0 ID collisions | ✅ |
| Read/write mix (20 reads + 10 writes) | 0 server errors | ✅ |

---

## Data Volume Performance

| Test | Result | Status |
|------|--------|--------|
| Tasks list with +50 rows | p95 < 200ms | ✅ |
| Memory FTS with 100 entries | p95 < 200ms | ✅ |
| Prompt library with 50 prompts | p95 < 200ms | ✅ |
| Workflow list with 20 workflows | p95 < 200ms | ✅ |
| Multi-table COUNT(*) query | p95 < 100ms | ✅ |

---

## Response Consistency

| Endpoint | P95/P50 Ratio | P99 Cap | Status |
|----------|--------------|---------|--------|
| /api/health | < 3x | < 50ms | ✅ |
| /api/profile | < 3x | < 100ms | ✅ |
| /api/license/status | < 3x | < 100ms | ✅ |
| /api/memory/list | < 3x | < 100ms | ✅ |
| /api/tasks | < 3x | < 150ms | ✅ |

---

## Reliability Under Load

| Test | Result | Status |
|------|--------|--------|
| 100 sequential health requests | 100/100 succeeded | ✅ |
| 200 mixed endpoint requests | 0 server errors | ✅ |
| 100 rapid task creates | 100 unique IDs | ✅ |
| 30s stability test | < 50% degradation | ✅ |

---

## Specific Component Performance

| Component | Metric | Result | Status |
|-----------|--------|--------|--------|
| WebSearch history CRUD | List latency | < 50ms | ✅ |
| Docs feedback accumulation | p95 after 50 entries | < 50ms | ✅ |
| License history growth | p99 with entries | < 50ms | ✅ |
| Profile export | p99 | < 100ms | ✅ |
| MCP json.parse tool | p99 | < 100ms | ✅ |
| CRDT create/op/get | All < 100ms each | < 100ms | ✅ |

---

## Architecture Notes

This platform runs as **single-process uvicorn + SQLite** — a local-first architecture:
- No connection pool needed for SQLite (single writer)
- In-process async I/O via uvicorn/asyncio
- No network hops between app and DB (same process)
- Performance ceiling: Python GIL limits true parallelism

**Implications for thresholds:**
- Single-user latency is excellent (1-15ms typical)
- 10-concurrent throughput is high (100-950 RPS depending on endpoint)
- Under 20 concurrent clients, p95 stays < 300ms for all endpoints
- The platform is designed for **local-first single-user** with up to ~10 concurrent users

---

## Grand Total Across All Test Layers

```
Test Layer    Tests    Pass    Score
─────────────────────────────────────
Unit          575      575     100.0%
Integration   237      237     100.0%
System        167      167     100.0%
UAT           166      166     100.0%
Performance   112      112     100.0%
─────────────────────────────────────
GRAND TOTAL  1257     1257    100.0% ✅
```
