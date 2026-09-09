# Module Review Backlog — Agentic OS

Ordered by *highest user impact first* (per user direction). Each module is
reviewed → fixed → verified (unit tests + live browser probe + audit suite
green) → committed. Large architectural rewrites are deferred; defects and UX
polish are in scope.

| # | Module | Frontend | Backend | Priority | Status |
|---|--------|----------|---------|----------|--------|
| 1 | **Chat** | 01-app-core.js (chat) | chat.py, engine.py, llm.py | Core daily | IN PROGRESS |
| 2 | **Studio** | 02-studio.js | builder.py, multifile_agent.py, multitab.py | Core daily | DONE (#078) |
| 3 | **Tasks / Kanban** | 28-kanban.js | tasks.py | Core daily | VERIFIED (no defect) |
| 4 | **ICM Workspaces** | 59-icm-workspaces.js, 60-inbox.js | icm.py + icm_* services | Core daily | VERIFIED (no defect) |
| 5 | **Settings / Account** | 57-account-settings.js | secrets.py, userprofile.py, auth.py | Core daily | VERIFIED (no defect) |
| 6 | **Knowledge Graph** | 05-evals-observability.js | knowledge_graph.py | Knowledge | VERIFIED (no defect) |
| 7 | **RAG** | 05-evals-observability.js | rag.py | Knowledge | VERIFIED (no defect) |
| 8 | **Docs / Knowledge** | 12-information-hierarchy.js | hierarchy.py, docs_center.py | Knowledge | VERIFIED (no defect) |
| 9 | **Search / Code** | (search) | search.py, codesearch.py, codeindex.py | Knowledge | VERIFIED (no defect) |
| 10 | **ICM Router / Memory** | — | icm_router.py, memory.py, memory_tiers.py | Ops | VERIFIED (no defect) |
| 11 | **Supervisor / Swarm** | 48-supervisor.js, 26-swarm.js | supervisor.py, swarm.py | Ops/collab | VERIFIED (no defect) |
| 12 | **Goals / Loops / Fusion** | 49-goals.js, 40-loops.js, 41-fusion.js | goal_manager.py, loops.py, fusion.py | Ops/collab | backlog |
| 13 | **MCP / Connectors / Plugins** | 39-mcp-panel.js, 50-mcp-gateway.js, 35-connect-hub.js, 34-plugin-hub.js | mcp.py, mcp_gateway.py, connectors.py | Integrations | backlog |
| 14 | **Evals / Observability** | 05-evals-observability.js | evals.py, observability.py, eval_framework.py | Quality | backlog |
| 15 | **Terminal / Security / System** | 16-terminal.js | terminal.py, security.py, system.py | Ops | backlog |
| 16 | **Templates / Prompts / Skills** | 21-template-gallery.js, 14-prompt-library.js, 25-skills.js | templates.py, prompts.py, skills.py | Content | backlog |
| 17 | **Workspaces / Deploy / Git** | 30-workspaces.js, 35-deploy.js, 18-github.js | workspaces.py, deploy.py, github.py, gitai.py | Ops | backlog |

Rules:
- Each module: enumerate endpoints + UI behaviour → find real defects /
  incompleteness / improvement opportunities → fix (tools + tests) → live probe
  → run audit + full test suite → commit with `#NNN`.
- Record findings in docs/round-5-progress.md as `#NNN`.
- Do NOT re-litigate already-fixed items (#064–#076).
