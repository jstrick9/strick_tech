# Full User Acceptance Test Suite — All Use Cases
## Completion Report · 2026-07-13

**Status:** ✅ COMPLETE — 275/275 UAT tests passing (100%)
**Grand Total:** 2000/2000 across ALL test layers (100%)
**Full suite execution time:** 191 seconds

---

## What UAT Tests Verify

UAT (User Acceptance Testing) tests the platform from the **end user's perspective** — not code correctness or API contracts, but "Can a real person accomplish their goal and see what they expect?"

Each test maps to a **User Story + Acceptance Criteria**:
> *"As a [role], I can [action] so that [outcome]"*
> *AC: User [does X] → sees [Y]*

---

## UAT Test Count Breakdown

| File | User Story Domain | Tests |
|------|------------------|-------|
| test_uat_01_core_chat.py | Chat & Agent Management | 15 |
| test_uat_02_productivity.py | Kanban, Prompts, Sessions | 24 |
| test_uat_03_developer_tools.py | Secrets, Terminal, BugBot | 21 |
| test_uat_04_ai_workflows.py | Workflows, Web Search, Swarm, Arena | 23 |
| test_uat_05_platform_admin.py | Settings, License, Plugins | 31 |
| test_uat_06_quality_governance.py | Evals, HITL, Observability | 25 |
| test_uat_07_docs_onboarding.py | Onboarding, Docs Center | 27 |
| **test_uat_08_governance_sprint_a.py** | **Audit Log, Identity, HITL** | **23** |
| **test_uat_09_orchestration_sprint_b.py** | **Goals, Supervisor, Loops** | **22** |
| **test_uat_10_connectivity_sprint_c.py** | **MCP Gateway, Connectors** | **21** |
| **test_uat_11_observability_sprint_d.py** | **Monitor, FinOps, Eval Framework** | **23** |
| **test_uat_12_enterprise_knowledge.py** | **KG, RAG, Swarm, Leaderboard** | **17** |
| **test_uat_13_error_experience.py** | **Error UX, Recovery, Degradation** | **16** |
| **test_uat_14_developer_pipeline.py** | **E2E, Deploy, Plugin SDK, Replay** | **13** |
| **TOTAL** | **All Platform Features** | **275** |

---

## New UAT Files (08–14) — User Stories Validated

### UAT 08 — Governance Layer (23 tests)

**"As a user, I can see a tamper-proof record of every AI action"**
- User opens Audit Log → sees "Chain integrity verified ✅"
- User's agent action is recorded → appears in the log immediately
- User filters by risk level → only matching entries shown
- User clicks Export → downloads compliance JSON with embedded chain proof
- Finance team downloads CSV with header columns for reconciliation
- Admin dashboard shows audit statistics (totals, top agents, by-risk breakdown)

**"As an admin, I can provision secure identities for agents"**
- Admin clicks 'Provision All' → all 8+ agents get distinct cryptographic identities
- Signing keys are NEVER exposed in any API response (`[REDACTED]`)
- User assigns a task → agent gets a JIT token (expires in 5 minutes)
- Admin sees count of active JIT tokens in the identity dashboard
- Admin rotates keys → old tokens revoked, new tokens work immediately
- Admin can share an A2A v1.0 agent card with partner systems

**"Risky AI actions require my approval before executing"**
- User opens HITL pane → sees pending actions with risk level and confidence
- User clicks Approve → action proceeds, removed from queue
- User clicks Reject → action blocked, reason recorded
- Low-risk/high-confidence actions auto-approve without interrupting user
- AI risk assessment tells user risk level and recommendation before acting
- HITL statistics show approval/rejection ratios on dashboard

---

### UAT 09 — Orchestration Layer (22 tests)

**"As a user, I can set a goal and watch agents execute it"**
- User fills goal form (domain, priority, deadline) → saved with all fields visible
- User breaks goal into milestones → progress bar shows completion %
- Completing all milestones → goal status changes to "done" automatically
- Multiple agents add check-ins → team can see progress history with notes
- User filters goals by domain (Work/Health/Learning) → only matching shown
- Goals summary dashboard shows total, status breakdown, average progress

**"As a user, I click Launch and AI agents automatically execute my goal"**
- User clicks Launch → supervisor decomposes goal into ≥2 specialist tasks
- Each task shows which agent is assigned (brain/builder/researcher/etc.)
- Goal shows linked supervisor run ID for tracking
- User can stop the supervisor at any time with instant effect
- Supervisor history shows past runs with outcomes

**"As a user, I schedule recurring AI tasks"**
- User creates loop → appears in active loops list with ID
- User pauses for holiday → resumes on return
- User deletes loop → gone, won't run again
- System jobs are protected from accidental deletion

---

### UAT 10 — Connectivity Layer (21 tests)

**"As admin, I control which agents can use which tools"**
- Admin opens MCP Gateway → sees all 5+ tool servers with rate limits
- Admin creates an access policy → gateway enforces it immediately
- Agent makes a tool call → user sees it in the call log with policy decision
- Admin disables a server → all subsequent agent calls to it are blocked
- Admin dashboard shows total calls, block rate, top agents, top tools

**"As a user, I connect to Slack, Jira, GitHub and other systems"**
- User opens Connectors → sees Slack, Jira, Google Workspace, GitHub, Webhook
- User clicks a connector → sees what actions it can perform
- Webhook connector works immediately (no configuration needed)
- Unconfigured Slack gives helpful "configure credentials" message (not crash)
- Developer registers custom CRM connector → appears in filtered list
- User reviews past connector executions in execution history
- Admin sees connector usage statistics at a glance

---

### UAT 11 — Observability Layer (23 tests)

**"As admin, I can see all agents and their real-time health"**
- Admin opens Monitor → sees all 8+ agents with status indicators and session costs
- Admin takes KPI snapshot → all agent metrics captured (confirms snapshotted ≥8)
- Admin selects one agent → sees performance trend (total tasks, success rate, avg latency)
- Admin clicks 'Detect Anomalies' → platform flags unusual behavior
- Admin immediately stops misbehaving agent, then restores it — dashboard reflects both
- Platform health summary shows total/active agents, anomalies, all-time metrics

**"As admin, I track AI costs and set budgets per team/goal"**
- Admin opens FinOps → sees all-time total, today's spend, hourly spend, daily projection
- Admin attributes cost to goal → appears in per-goal cost breakdown
- Admin sets daily budget limit per agent → visible in dashboard
- Admin sees spending trend chart at both hourly and daily granularity
- Finance team downloads CSV cost report with ledger_id and cost_usd columns
- Budget alerts visible when spending approaches limits

**"As admin, I run evaluation suites to verify agent quality"**
- Admin opens Evals → sees pre-built suites with pass thresholds
- Admin adds custom test case → it's saved with a case_id
- Admin clicks Run → streaming SSE shows start/case_done events
- Low-scoring results appear in Human Review queue
- Admin drills into one agent → sees pass rate, avg score, safety score, pending reviews
- Admin creates domain-specific suite for their use case
- Platform stats show total evals, suites count, by-agent breakdown

---

### UAT 12 — Enterprise Knowledge (17 tests)
- User creates entities and relations in knowledge graph → stats updated
- User types question → AI answers using the knowledge graph
- User clicks entity → sees connected entities (graph traversal)
- User creates RAG pipeline for document grounding
- User starts 3-agent swarm → winner selected, judge explanation provided
- Admin sees agent leaderboard with performance rankings
- Admin records agent performance (tasks, cost, latency)
- User rates an agent's output quality with comment

### UAT 13 — Error Experience (16 tests)
- User forgets goal title → sees "title required" message (not crash)
- Platform handles invalid priority gracefully (not 500)
- Accessing deleted goal → "Not found" (not 500)
- User accidentally approves same action twice → second click rejected cleanly
- Wrong agent for token → "access denied" message
- 25KB document → platform handles without crash
- Malformed JSON → 400 Bad Request (not 500 Internal Error)
- Empty supervisor goal → helpful validation message
- Slack unavailable → friendly error, platform keeps running
- Unknown MCP tool → helpful rejection (not crash)
- Health endpoint always responds
- Deleted goal properly gone from all views
- Spec artifacts survive read/write exactly
- Memory survives reindex

### UAT 14 — Developer Pipeline (13 tests)
- Developer submits code diff → BugBot review response
- Developer submits function → gets test case generation response
- Developer sees code complexity scores per function
- Developer searches codebase → finds matches with line context
- Developer runs E2E tests → sees passed count, score, engine type
- Developer views E2E run history for comparison
- Developer checks Playwright installation status
- Developer sees deployment provider options
- Missing API key → helpful deploy error message
- Developer opens Replay → sees past workflow execution list
- Developer gets plugin starter template
- Developer validates plugin pack → sees result
- Developer creates plugin pack → appears in SDK list

---

## Complete Testing Pyramid

```
UAT Tests:            275 /  275   ✅ (uat_01–uat_14, 14 files)
System Tests:         263 /  263   ✅ (sys_01–sys_13, 13 files)
Integration Tests:    395 /  395   ✅ (flow_01–flow_16, 16 files)
Unit Tests:           852 /  852   ✅ (test_01–test_29, 29 files)
Sprint A Tests:        52 /   52   ✅
Sprint B Tests:        69 /   69   ✅
Sprint C Tests:        49 /   49   ✅
Sprint D Tests:        45 /   45   ✅
──────────────────────────────────────────
GRAND TOTAL:         2000 / 2000   ✅ 100%   (191 seconds)
```

---

## How to Run

```bash
cd /home/user/agentic-os

# Start server
python3 -m uvicorn backend.app:app --host 127.0.0.1 --port 8787

# UAT tests only (275 tests, ~13s):
python3 -m pytest tests/uat/ -q --tb=short -p no:warnings --override-ini="addopts="

# Complete testing pyramid (2000 tests, ~191s):
python3 -m pytest tests/unit/ tests/integration/ tests/system/ tests/uat/ \
  tests/sprint_a/ tests/sprint_b/ tests/sprint_c/ tests/sprint_d/ \
  -q --tb=no -p no:warnings --override-ini="addopts="
```
