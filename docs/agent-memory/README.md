# Agent Memory — Agentic OS Expertise

An ICM-layered knowledge base for an AI agent that needs to be an expert in
building Agentic OS platforms.

## Start here

```
1. IDENTITY.md      ← who you are, how you decide          (~120 lines)
2. CONTEXT.md       ← what an Agentic OS is, what exists    (~80 lines)
3. reference/NN-*   ← the one domain you are working in     (~200 lines each)
```

**Do not load all of it.** That is the point. Loading everything is the
monolithic-context failure this structure exists to avoid — 2–8k tokens per
stage instead of 30–50k.

## Layout

| Layer | File | Purpose |
|---|---|---|
| **L0** | `IDENTITY.md` | Identity, priorities, working method, refusals |
| **L1** | `CONTEXT.md` | Domain map, seven layers, reference index |
| **L2** | `reference/01-kernel.md` | Scheduling, context management, isolation |
| | `reference/02-memory.md` | CoALA taxonomy, substrates, ICM, skills |
| | `reference/03-retrieval.md` | Hybrid RAG, GraphRAG, agentic RAG, eval |
| | `reference/04-tools-mcp.md` | Tool design, MCP spec, scoped loading |
| | `reference/05-orchestration.md` | Loops, graphs, multi-agent topologies |
| | `reference/06-governance.md` | HITL, audit, EU AI Act, budgets |
| | `reference/07-security.md` | OWASP ASI Top 10, injection, SSRF, secrets |
| | `reference/08-uiux.md` | Progressive disclosure, trust calibration |
| | `reference/09-personas.md` | Novice / intermediate / advanced |
| | `reference/10-engineering.md` | Python, APIs, frontend, observability |
| | `reference/11-quality.md` | Evals, LLM-as-judge, revert-proofing |
| | `reference/12-failure-patterns.md` | **How these systems actually break** |
| | `reference/13-frontier.md` | Where the field is going |

## If you are reviewing code

Read `IDENTITY.md`, then `reference/12-failure-patterns.md`, then the domain
file. The failure catalogue is the highest-yield artefact here — the patterns
recur across every agentic codebase, and the checklist at the end of it turns a
multi-day review into a multi-hour one.

## Conventions

Follows the Interpretable Context Methodology (Van Clief & McDermott,
arXiv:2603.16021): `CONTEXT.md` under ~80 lines, references under ~200, one-way
references only, one canonical source per fact.

**Walk test:** an agent with no memory opens this folder, reads `IDENTITY.md`
then `CONTEXT.md`, and knows what it is, what exists, and where to look next —
from these files alone.

## Provenance

Synthesised mid-2026 from primary sources — AIOS (arXiv:2403.16971), Anthropic's
context-engineering and agent-building guidance, the MCP 2026-07-28
specification, OWASP Top 10 for Agentic Applications and for MCP, CoALA,
GraphRAG and Agentic-GraphRAG surveys, the EU AI Act and NIST AI RMF — combined
with defects observed, reproduced, and fixed in a production Agentic OS
codebase.

**Specifics age; structure ages slower.** Where a claim here conflicts with what
you observe in a running system, the observation wins. Update the file and note
what changed.
