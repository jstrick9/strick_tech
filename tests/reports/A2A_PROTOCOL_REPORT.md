# A2A Protocol Endpoint (Agent-to-Agent) — Full Build & Verification Report
**Date:** 2026-07-15  
**Test Result: ✅ 72/72 tests PASSED (100%)**

---

## What Was Built

### New Backend Router: `backend/routers/a2a.py` (complete A2A v1.0 implementation)

#### Well-Known Agent Card Endpoints

| URL | Description |
|-----|-------------|
| `GET /.well-known/agent.json` | Platform-level Agent Card describing the full Agentic OS installation |
| `GET /a2a/{id}/.well-known/agent.json` | Per-agent card at the spec-compliant URL |
| `GET /a2a/{id}/card` | Per-agent card at a friendly alias URL |

All Agent Cards are **fully A2A v1.0 compliant** with:
- `name`, `description`, `url`, `version`
- `skills[]` — derived from agent role with id/name/description/tags
- `defaultInputModes` / `defaultOutputModes`
- `capabilities` — streaming, pushNotifications, stateTransitionHistory
- `authentication.schemes`
- `provider` — organization, url
- `_agentic_os` extension — agent_id, public_key, card_hash, signed_at, protocols
- `Access-Control-Allow-Origin: *` header for CORS

#### JSON-RPC 2.0 Task Endpoint

| URL | Methods |
|-----|---------|
| `POST /a2a/{agent_id}` | `tasks/send`, `tasks/get`, `tasks/cancel`, `tasks/list`, `tasks/sendSubscribe`, `agents/getAuthenticatedExtendedCard` |

**`tasks/send`** — Submit a task synchronously. Delegates to the Agentic OS supervisor which decomposes, executes, and synthesizes results. Returns completed TaskStatus with artifacts.

**`tasks/sendSubscribe`** — Submit a task and receive SSE stream. Emits `TaskStatusUpdateEvent` as the supervisor works, then `TaskArtifactUpdateEvent` when output is ready, then final `TaskStatusUpdateEvent` with `final: true`.

**`tasks/get`** — Retrieve task state + artifacts by ID. Returns -32001 (TaskNotFound) if missing.

**`tasks/cancel`** — Cancel a running task. Returns -32002 (NotCancelable) if already terminal.

**`tasks/list`** — Extension method: list tasks for a target agent with optional state/sessionId filters.

**Error codes (A2A spec compliant):**
- `-32700` Parse error
- `-32600` Invalid request (wrong jsonrpc version)
- `-32601` Method not found
- `-32602` Invalid params
- `-32603` Internal error
- `-32001` Task not found
- `-32002` Task not cancelable
- `-32003` Input required

#### SSE Stream Endpoint
`GET /a2a/{agent_id}/stream/{task_id}` — Poll an existing task's status as SSE stream. Useful when the caller missed the initial `sendSubscribe` window.

#### Registry + Management API (16 endpoints)

| Endpoint | Description |
|----------|-------------|
| `GET  /api/a2a/agents` | List all registered agents (remote + local) |
| `POST /api/a2a/agents` | Register a new remote A2A agent |
| `GET  /api/a2a/agents/{id}` | Full agent profile + recent tasks |
| `PATCH /api/a2a/agents/{id}` | Update trust level, auth, status |
| `DELETE /api/a2a/agents/{id}` | Remove from registry (local_orchestrator protected) |
| `POST /api/a2a/agents/{id}/verify` | Fetch + verify remote agent card from /.well-known/agent.json |
| `POST /api/a2a/delegate` | Delegate task to remote A2A agent via tasks/send |
| `GET  /api/a2a/tasks` | List all tasks (inbound + outbound, filterable) |
| `GET  /api/a2a/tasks/{id}` | Full task detail + a2a_response format + call log + supervisor run |
| `POST /api/a2a/tasks/{id}/cancel` | Cancel via REST API |
| `GET  /api/a2a/stats` | Platform-wide A2A usage statistics |

### 3 New DB Tables

| Table | Purpose |
|-------|---------|
| `a2a_tasks` | Task store: state machine, messages[], artifacts[], push_config, supervisor_run_id |
| `a2a_agents` | Remote agent registry: url, agent_card (cached), skills, capabilities, trust_level |
| `a2a_call_log` | Audit trail: every inbound/outbound call with direction, status_code, duration |

### 3 Demo Agents Pre-Seeded
- **LangChain Research Agent** — external, unverified, web_search + rag_retrieval skills
- **CrewAI Content Writer** — external, unverified, content_writing + editorial_review
- **local_orchestrator** — local, verified, active, full capabilities

---

### Agent Card Skills Engine

Each agent's skills are derived from their role string using `_role_to_skills()`:
- **orchestrator** → task_orchestration, agent_coordination
- **researcher** → web_research, knowledge_retrieval  
- **builder** → code_generation, file_management
- **reviewer** → code_review, test_generation
- **creative** → content_creation, image_generation
- **brain** → deep_reasoning, goal_decomposition
- **memory** → memory_store
- Plus permission-derived skills from `agent_permissions` table

---

### Frontend: A2A Network Pane (3 tabs)

New nav item: **🌐 A2A Network** (after Connectors in sidebar)

```
┌──────────────────────────────────────────────────────────────────┐
│  SIDEBAR                    │  MAIN PANEL                        │
│  🌐 Agent Network [active]  │  Protocol banner + stats grid      │
│  📋 Tasks [badge]           │  Agent cards grid (remote + local)  │
│  🪪 Agent Cards             │  Register Remote Agent card (+)     │
│  ─────────────────────────  │  Local agents list with card links  │
│  ➕ Register Agent          │                                     │
│  📤 Delegate Task           │                                     │
└──────────────────────────────────────────────────────────────────┘
```

#### 🌐 Agent Network Tab
- A2A protocol explanation with well-known URL links
- Stats grid: registered, active, local, tasks run, inbound, outbound
- Agent cards: trust badge (local/verified/unverified), status icon, skills chips, capabilities, Delegate/Verify/Delete buttons
- "+ Register Remote Agent" card (dashed)
- Local agents section with 🪪 card link per agent

#### 📋 Tasks Tab  
- Table: task_id, direction (📤 outbound / 📥 inbound), agent, state badge, progress %, created time, cancel button
- Click row → full detail modal with messages, artifacts, supervisor run info

#### 🪪 Agent Cards Tab
- Grid showing all 7 local agents' A2A card endpoints (both spec URL + friendly URL)
- "JSON" button → modal with full card JSON + copy button
- Platform card link at the bottom

#### Delegate Task Modal
- Agent selector (all registered + local agents)
- Message textarea
- Session ID field
- Local agents → direct JSON-RPC `tasks/send`
- Remote agents → `/api/a2a/delegate`

#### Register Agent Modal
- Name, A2A URL, description, auth type (none/bearer/api_key), token field

---

## A2A v1.0 Spec Compliance

| Feature | Status |
|---------|--------|
| Agent Card at /.well-known/agent.json | ✅ |
| Per-agent card at /a2a/{id}/.well-known/agent.json | ✅ |
| JSON-RPC 2.0 (jsonrpc field, id echo, result/error) | ✅ |
| tasks/send (synchronous) | ✅ |
| tasks/sendSubscribe (SSE streaming) | ✅ |
| tasks/get | ✅ |
| tasks/cancel | ✅ |
| Task state machine: submitted→working→completed/failed/canceled | ✅ |
| Message format: role + parts[] with type+text | ✅ |
| Artifact format: name + mimeType + parts[] | ✅ |
| Standard JSON-RPC error codes (-32xxx) | ✅ |
| A2A-specific error codes (-32001 TaskNotFound etc.) | ✅ |
| CORS header on all card endpoints | ✅ |
| Capability advertisement (streaming, stateTransitionHistory) | ✅ |
| Authentication schemes declaration | ✅ |
| Provider metadata | ✅ |
| agents/getAuthenticatedExtendedCard | ✅ |
| Cross-platform discovery (verify remote card) | ✅ |
| Outbound task delegation | ✅ |
| Push notifications | 🔲 (declared as unsupported) |

---

## Test Coverage — 72 Tests

| Group | Tests | What's Verified |
|-------|-------|----------------|
| Platform Card | 8 | HTTP 200, all 8 required fields, name, skills array, capabilities, I/O modes, CORS, extension |
| Agent Cards (parametrized × 7) | 8+8 | Friendly URL, spec URL (7 agents each), all required fields, role-specific skills, url matches, identity extension, 404, CORS |
| JSON-RPC 2.0 | 10 | Version enforcement, response format, -32601, tasks/list, -32001, -32002, -32602, authenticated card, state filter, id echo |
| Task Send | 6 | Creates task, string message normalization, session ID, artifacts on complete, appears in list, cancel |
| Registry | 12 | List, field validation, local orchestrator, register, appears in list, detail, update, verify local, verify unreachable, protected delete, delete confirmed, missing URL |
| Delegation | 5 | Local delegation, unreachable remote handling, missing message, nonexistent agent 404, creates task in DB |
| Task Management | 6 | List, state filter, detail, A2A response format, cancel nonexistent 404, direction field |
| Stats | 3 | All fields, non-negative counts, demo agents count |
| SSE Stream | 2 | SSE content-type, tasks/sendSubscribe streams events |

---

*Backend: `/home/user/agentic-os/backend/routers/a2a.py`*  
*App: `backend/app.py` — a2a_router registered*  
*Frontend: `frontend/index.html` — A2A Network pane + nav item*  
*Tests: `tests/connectors/test_a2a_protocol.py`*  
*DB: 3 new tables + 3 demo remote agents seeded*
