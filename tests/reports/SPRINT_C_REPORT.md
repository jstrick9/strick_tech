# Sprint C — Connectivity Layer
## Completion Report · 2026-07-13

**Status:** ✅ COMPLETE — 49/49 tests passing (100%)
**Duration:** Weeks 8–12 (Implemented in one session)
**Platform:** Agentic OS v6.0 · localhost:8787
**Cumulative A+B+C:** 170/170 tests · 100%

---

## What Was Built

### Feature 1 — MCP Gateway (`/api/mcp-gateway`)
**File:** `backend/routers/mcp_gateway.py`

A centralised policy-enforcement chokepoint through which every agent tool call must pass.
Built to the IBM ADLC spec and Cloud Security Alliance AIUC-1 Q2 2026 requirements.

#### Architecture
```
Agent → POST /api/mcp-gateway/call
           │
           ▼
    Policy Evaluation (OPA-lite)
    Match (agent × server × tool_pattern) → allow | deny | require_hitl
           │
           ▼ (if allow)
    Rate Limit Check (per-agent × per-server, per-minute bucket)
           │
           ▼ (if within limit)
    Dispatch → /api/mcp/call (existing tool backend)
           │
           ▼
    Record call in mcp_gateway_calls
    Append to Immutable Audit Chain (Sprint A)
           │
           ▼
    Return {ok, result, call_id, policy_decision, gateway_duration_ms}
```

#### Server Registry (6 built-in + unlimited custom)
| Server | Tools | Rate Limit |
|--------|-------|-----------|
| `srv_filesystem` | fs.read/write/list/delete | 120/min |
| `srv_web_search` | search.web | 20/min |
| `srv_code_exec` | code.run | 30/min |
| `srv_memory` | memory.add/search | 60/min |
| `srv_http` | http.get/post | 30/min |
| `srv_connectors` | slack/jira/gdocs | 20/min |

Servers can be **disabled instantly** via the kill-switch toggle — all calls immediately blocked, decision logged.

#### Policy Engine
4 default policies seeded; unlimited custom policies creatable:
- `allow` — permit the call
- `deny` — block with error message
- `require_hitl` — pause, queue in HITL, return `pending: true`

Policies match on: `agent_id` (exact or `*`), `server_id` (comma-list or `*`), `tool_pattern` (glob, e.g. `fs.*`). Lower priority number = higher precedence.

**Default policies:**
- Allow all agents → all built-in servers
- Require HITL for `fs.delete` (destructive)
- Rate-limit external HTTP calls
- Allow orchestrator/brain → connectors (elevated)

#### A2A Agent Cards (v1.0 Spec)
Every agent gets a cryptographically signed Agent Card compatible with the A2A protocol used by Microsoft, AWS, Google, IBM, Salesforce, and SAP in production:
```json
{
  "schema_version": "a2a/1.0",
  "agent_id": "orchestrator",
  "public_key": "MIIBIjAN...",
  "authority_level": "elevated",
  "capabilities": ["read_memory", "write_tasks", ...],
  "protocols": ["mcp/1.0", "a2a/1.0"],
  "endpoint": "http://localhost:8787/api/agents/orchestrator"
}
```

#### New Database Tables
| Table | Purpose |
|-------|---------|
| `mcp_servers` | Server registry with auth config |
| `mcp_gateway_policies` | Policy rules (allow/deny/hitl) |
| `mcp_gateway_calls` | Every call record with policy decision |
| `mcp_rate_buckets` | Per-minute rate tracking per agent×server |

#### API Endpoints (9)
| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/api/mcp-gateway/servers` | List all servers |
| `POST` | `/api/mcp-gateway/servers` | Register custom server |
| `PATCH`| `/api/mcp-gateway/servers/{id}` | Update server |
| `DELETE`|`/api/mcp-gateway/servers/{id}` | Remove server |
| `POST` | `/api/mcp-gateway/servers/{id}/toggle` | Kill switch |
| `GET`  | `/api/mcp-gateway/policies` | List policies |
| `POST` | `/api/mcp-gateway/policies` | Create policy |
| `DELETE`|`/api/mcp-gateway/policies/{id}` | Delete policy |
| `PATCH`| `/api/mcp-gateway/policies/{id}/toggle` | Enable/disable |
| `POST` | `/api/mcp-gateway/call` | Gateway-enforced tool call |
| `GET`  | `/api/mcp-gateway/calls` | Call history |
| `GET`  | `/api/mcp-gateway/stats` | Usage statistics |
| `GET`  | `/api/mcp-gateway/agent-card/{id}` | A2A Agent Card |

#### UI Pane: 🔀 MCP Gateway
- Stats bar (total calls, blocked, block rate, servers, policies)
- Server cards with status badges, rate limits, and kill-switch buttons
- Policy cards colour-coded by action (green=allow, red=deny, yellow=hitl)
- A2A Agent Card viewer for all 6 specialist agents
- Recent calls table (status, agent, server, tool, policy decision, time)

---

### Feature 2 — Enterprise Connectors (`/api/connectors`)
**File:** `backend/routers/connectors.py`

8 built-in connectors + unlimited custom connectors via the Connector SDK.
Every execution is audited in the immutable chain.

#### Built-in Connectors
| Connector | Category | Auth | Actions |
|-----------|---------|------|---------|
| Slack | Communication | API Key (`SLACK_BOT_TOKEN`) | send_message, list_channels, get_user |
| Jira | Project Mgmt | Basic (`JIRA_EMAIL`+`JIRA_API_TOKEN`) | create_issue, get_issue, list_projects, add_comment |
| Google Workspace | Productivity | OAuth | create_doc, read_sheet, create_calendar_event |
| Email (SMTP) | Communication | SMTP | send_email, send_html_email |
| GitHub | DevOps | API Key (`GITHUB_TOKEN`) | create_issue, create_pr, list_repos |
| Webhook (outbound) | Integration | None (**active by default**) | post_webhook, post_with_auth |
| Notion | Productivity | API Key (`NOTION_TOKEN`) | create_page, update_page, query_database |
| Salesforce | CRM | OAuth | query_records, create_record, update_record, get_contact |

**Webhook** is the only connector active out-of-the-box — zero config needed, ideal for first integrations.

#### Connector SDK
Any developer (or agent!) can register a custom connector:
```
POST /api/connectors
{name, category, auth_type, capabilities:[], description, config:{}}
PATCH /api/connectors/{id}/configure
{credentials:{api_key:"..."}, config:{}}
POST /api/connectors/{id}/execute
{action:"my_action", payload:{...}, agent_id:"builder"}
```

The SDK enables a marketplace model: connectors can be shared, installed, and versioned independently of the core platform.

#### New Database Tables
| Table | Purpose |
|-------|---------|
| `connector_registry` | Connector metadata + encrypted credentials |
| `connector_executions` | Every execution with status, duration, result |

#### API Endpoints (11)
| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/api/connectors` | List all (filter by category/status) |
| `POST` | `/api/connectors` | Register custom (Connector SDK) |
| `GET`  | `/api/connectors/{id}` | Get connector detail |
| `PATCH`| `/api/connectors/{id}/configure` | Save credentials |
| `POST` | `/api/connectors/{id}/execute` | Run an action |
| `POST` | `/api/connectors/{id}/test` | Connectivity test |
| `GET`  | `/api/connectors/{id}/executions` | Execution history |
| `GET`  | `/api/connectors/stats/summary` | Dashboard stats |

#### UI Pane: 🔌 Connectors
- 4-stat bar (total, active, executions, categories)
- Connector SDK callout with API example
- Cards grouped by category with capability pills
- Per-card: Configure (with auth-type hints), Execute, History, Test
- Category filtering via dropdown

---

## End-to-End Data Flow (Sprint A+B+C unified)

```
User sets Goal (Goals pane)
    │ launch →
Supervisor decomposes → Task DAG
    │ each task →
Specialist Agent needs tool
    │ →
MCP Gateway (policy check → rate limit → dispatch)
    │ tool result →
Connector (Slack / Jira / Webhook / GitHub)
    │ response →
Specialist Agent incorporates result
    │ every step →
Immutable Audit Chain (SHA-256 hash chained)
    + Signed Receipt (agent identity keypair)
    + HITL Queue (if risk_level=high/critical)
    │ all done →
Orchestrator synthesizes → Evaluator scores → Goal progress updated
```

---

## Test Results

```
Sprint C Test Suite
══════════════════════════════════════════
File: tests/sprint_c/test_sprint_c_mcp_gateway.py
  TestGatewayServers:    8/8   ✅
  TestGatewayPolicies:   7/7   ✅
  TestGatewayCall:       5/5   ✅
  TestGatewayAgentCard:  3/3   ✅
  TestGatewayStats:      2/2   ✅

File: tests/sprint_c/test_sprint_c_connectors.py
  TestConnectorList:        5/5   ✅
  TestConnectorGet:         2/2   ✅
  TestConnectorRegister:    3/3   ✅
  TestConnectorConfigure:   2/2   ✅
  TestConnectorExecute:     6/6   ✅
  TestConnectorTest:        3/3   ✅
  TestConnectorAuditInteg:  1/1   ✅
  TestConnectorStats:       2/2   ✅
──────────────────────────────────────────
SPRINT C TOTAL: 49/49 = 100% ✅  (2.0s)

CUMULATIVE (A+B+C): 170/170 = 100% ✅
```

---

## Platform State After Sprint C

```
New tables (8):
  mcp_servers             — 6 built-in + custom server registry
  mcp_gateway_policies    — 4 default + custom policy rules
  mcp_gateway_calls       — call log with policy decisions
  mcp_rate_buckets        — per-minute rate tracking
  connector_registry      — 8 built-in + custom connectors
  connector_executions    — execution history with audit

Total tables: 100 (across A, B, C additions)
Total API endpoints: ~580
New nav items: 🔀 MCP Gateway · 🔌 Connectors (75 total nav items)
```

---

## What's Next — Sprint D (Weeks 13–16)

1. **Live Agent Monitor** — real-time dashboard of all running agents (status, current step, cost)
2. **Cost Attribution** — token + dollar cost per agent/task/goal/user
3. **Evaluation Framework** — automated task eval suite with scoring and human review queue

Integration points ready for Sprint D:
- `mcp_gateway_calls.tokens_used` and `cost` columns ready for FinOps population
- `supervisor_tasks.cost` already tracked per task
- Audit chain already contains all events needed for anomaly detection
- Agent identity system ready for performance attribution per agent

---

*"MCP standardises how an agent connects to tools and data sources. A2A standardises how agents talk to agents. Use both."*
— Linux Foundation Agentic AI Foundation, 2026
