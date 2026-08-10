# Agentic OS — Reference Architecture Research

**Status:** living document. This is the durable memory for how this platform
should evolve. Update it; do not rewrite it from scratch.

**Compiled:** 2026-08-10
**Purpose:** ground every future module review and feature decision in a
researched reference architecture rather than intuition.

---

## 0. How to use this document

| If you are… | Read |
|---|---|
| Reviewing a module | §2 (the layer it belongs to) + §9 (gap table) |
| Adding a feature | §1 (does it belong in an Agentic OS at all?) |
| Working on memory/RAG | §3 |
| Working on multi-agent | §4 |
| Working on workspaces/context | §6 (ICM — the user's specific ask) |
| Planning sequencing | §9 |

---

## 1. What an Agentic OS actually is

The consensus that formed 2024→2026, starting from the AIOS paper
(Mei et al., Rutgers, arXiv:2403.16971) and hardened by production systems:

> An Agentic OS is a **runtime layer between the models and the agents**, providing
> what a conventional OS provides to processes: scheduling, memory, storage,
> tool I/O, isolation, and observability.

The load-bearing distinction, from the Namzu/CortexPrism framing:

- **Frameworks** (LangGraph, CrewAI, AutoGen) answer *"what does the agent do?"* —
  composition, prompts, tool definitions, state graphs.
- **Kernels / OSes** answer *"how does the agent run?"* — lifecycle, scheduling,
  memory boundaries, IPC, sandboxing, checkpoint/resume, runtime observability.

**Good production architectures use both.** Build agents with a framework; run
them inside an OS. This platform is trying to be the OS, and should be judged
on kernel-shaped concerns, not on having the most agent templates.

### The canonical mapping

| Conventional OS | Agentic OS | Maturity of the field |
|---|---|---|
| CPU scheduler | Agent loop + task scheduler | Crowded ("red ocean") |
| RAM | Context window management | **Most complex, highest value** |
| Virtual memory / paging | Context engineering, RAG | Highest value |
| Filesystem | Persistent memory store | Well understood |
| Processes | Sub-agents in parallel | Crowded |
| Applications | Skills and tools | Hot (MCP, Skills) |
| Device drivers | Tool/data connectors (MCP) | Hot |
| System calls | The agent SDK | Settled |
| Cron | Proactive scheduled tasks | Settled |
| Permissions / audit / sandbox | Isolation, observability, decision audit | **About to explode** |

**Implication for this platform:** the two areas with the most headroom are
*context/memory engineering* and *security/observability of agent decisions*.
Both are areas where this codebase already has real assets (MCP Gateway policy
engine, audit log, HITL) and real gaps (no vector tier, no graph memory).

---

## 2. The layer model to build against

Synthesised from AIOS, CortexPrism, Hermes, and the operator-led runtimes.
This is the target architecture.

```
┌─ L6  EXPERIENCE ─────────────────────────────────────────────┐
│  Workstations, chat, panes, HITL review gates, observability │
├─ L5  WORKSPACE / CONTEXT ────────────────────────────────────┤
│  ICM folder-as-architecture, CONTEXT.md cascade, ontologies  │
│  Second memory, project IVREN, steering rules                │
├─ L4  ORCHESTRATION ──────────────────────────────────────────┤
│  Supervisor / swarm / pipeline / graph topologies            │
│  Loop engineering: reflect, critique, retry, budget, halt    │
├─ L3  AGENT RUNTIME (the kernel) ─────────────────────────────┤
│  Scheduler · Context mgr · Memory mgr · Storage mgr          │
│  Tool mgr · Access mgr  ← the six AIOS modules               │
├─ L2  KNOWLEDGE ──────────────────────────────────────────────┤
│  Hybrid retrieval: BM25 + dense + graph traversal + rerank   │
│  Episodic / semantic / procedural / working memory           │
├─ L1  INTEGRATION ────────────────────────────────────────────┤
│  MCP (tools) · A2A (agents) · connectors · webhooks          │
├─ L0  COMPUTE ────────────────────────────────────────────────┤
│  Model routing, local (Ollama/edge) + frontier, cost/budget  │
└──────────────────────────────────────────────────────────────┘
```

### The six kernel modules (L3) — the spine

From AIOS. Every one of these should exist as a **named, testable service**,
not be scattered across routers:

1. **Scheduler** — FIFO / round-robin / priority; dispatches syscalls; caps
   concurrency. AIOS reports up to 2.1× throughput from centralised scheduling.
2. **Context Manager** — snapshot/restore of generation state, context-window
   assembly, interrupt-and-resume.
3. **Memory Manager** — per-agent working memory, isolation, K-LRU eviction.
4. **Storage Manager** — persistence, vector + file, rollback, sharing.
5. **Tool Manager** — `execute_tool` syscall, concurrency conflict resolution,
   **scoped tool loading** (see §5).
6. **Access Manager** — privilege checks, `ask_permission`, cross-agent
   boundaries. **This platform's MCP Gateway is already a strong Access
   Manager** — it just isn't named as one.

---

## 3. Memory & RAG (L2) — the highest-value layer

### 3.1 The memory taxonomy (now industry standard)

| Tier | Holds | Analogue | Typical backend |
|---|---|---|---|
| **Working** | Current task scratchpad | Registers | In-context |
| **Episodic** | Events with outcomes, timestamped | Diary | Log table + vectors |
| **Semantic** | Facts, entities, relations | Encyclopaedia | Vector + graph |
| **Procedural** | How-to, learned strategies | Muscle memory | Markdown / rules |
| **Graph** | Typed relations between entities | Index | Graph store |

The critical property, and where most systems fall short: **episodic memory
must record outcomes (success/failure), not just events.** That is what lets an
agent learn rather than merely recall. The observed pattern:

```
event → extract → find related procedure → evolve procedure with the fix
      → next retrieval includes the fix
```

That feedback loop is what makes agents improve over time.

### 3.2 RAG: the 2026 production baseline

| Layer | 2023 default | 2026 default |
|---|---|---|
| Retrieval | Dense only | **Hybrid BM25 + dense, fused with RRF** |
| Reranking | None | **Cross-encoder on top-k** |
| Query handling | Pass raw | Rewrite (HyDE / decomposition) when ambiguous |
| Orchestration | Retrieve-then-generate | **Agentic loop** when needed |
| Knowledge structure | Flat chunks | Hybrid **+ graph layer** for global questions |
| Evaluation | Spot check | Continuous groundedness + context adherence |
| Runtime safety | None | Inline hallucination guardrail at the boundary |

**Agentic RAG** is formally distinguished from Active RAG by having an
*autonomous control policy*: it separates planning from generation, can
**discard** bad retrievals, rewrite queries, and perform actions that produce
no output tokens. Append-only context accumulation is the old way; read/write/
**prune** over working memory is the new way.

### 3.3 Hybrid retrieval pipeline (the shape to implement)

```
query
  → rewrite / decompose
  → parallel:  BM25 (FTS5)  ·  dense (vector)  ·  graph traversal
  → RRF fusion
  → graph expansion from top entities
  → recency + MMR diversity
  → cross-encoder rerank
  → context assembly (with provenance)
```

Zep/Graphiti is the most production-validated example: BM25 + embedding +
graph traversal with **no LLM calls at retrieval time** — which is what keeps
it fast and cheap.

### 3.4 Known failure mode: memory poisoning

With episodic memory, poisoned entries alter *future retrieval strategy and
tool preference*, and because the corruption is per-user it is far harder to
detect than corpus poisoning. **Any memory write path needs provenance and a
review surface.** This is a security requirement, not a nicety.

---

## 4. Multi-agent (L4)

### 4.1 Topologies, and when each is correct

| Pattern | Who routes | Use when | Main risk |
|---|---|---|---|
| **Supervisor** | Central coordinator | Different specialist capabilities needed. **The 2026 default.** | Supervisor context overflow |
| **Pipeline** | Fixed sequence | Staged work with review gates | Rigid |
| **Swarm** | The agents (handoffs) | Path must emerge from the work | Drift; no parallel speedup |
| **Fan-out** | Coordinator assigns slices | Many independent subtasks | Coordination cost |
| **Graph/DAG** | Developer-defined edges | Quality gates, bounded loops | Upfront design |
| **Debate** | Judge arbitrates | High-stakes correctness | **~2.5× cost** |

### 4.2 Hard-won operational findings

- **Most agent failures are orchestration failures, not model failures.** Things
  break at *handoffs*: lost context, stale state, conflicting instructions.
- **The orchestrator should never execute.** Plan, delegate, validate,
  synthesise. The moment it also writes code, implementation detail pollutes
  its reasoning.
- **Swarms degrade past 8–10 sequential handoffs** — measurable quality loss
  that prompt tuning cannot fix.
- **Below ~3 agent roles, coordination cost exceeds the benefit.** Do not split.
- **Every LLM-routed step costs tokens for the routing decision itself,** on top
  of the work. Deterministic edges cost effectively zero.
- Handoff swarms measured at **7+ API calls / 14k tokens** vs **~5 calls /
  ~9k tokens** for sub-agent patterns on the same multi-domain task.

### 4.3 Mandatory safety rails (from Strands' defaults)

Any swarm/loop **must** ship with these set on day one — shipping without them
is "an unbounded loop with a billing meter attached":

| Rail | Sane default |
|---|---|
| `max_handoffs` | 20 |
| `max_iterations` | 20 |
| `execution_timeout` | 900s |
| `node_timeout` | 300s |
| repetitive-handoff detection window | **enable it** (default off is wrong) |
| min unique agents in window | **enable it** |

### 4.4 Protocols

- **MCP** — agent ↔ **tools**. JSON-RPC 2.0. The device-driver layer.
- **A2A** — agent ↔ **agents**. Discovery, task lifecycle, structured handoff.
  The vendor-neutral interop layer.

They are complementary and operate at different layers. This platform has both.

---

## 5. Loop engineering (L4)

Loops are where cost and correctness are decided.

- **Reflection / self-critique** (Reflexion, Self-RAG): generate → critique →
  revise. Real accuracy gains, real token cost.
- **Explicit halt conditions.** Confidence threshold **or budget exhaustion** —
  never "until done".
- **Bounded retries with backoff**, and a distinction between *retryable*
  (timeout, rate limit) and *terminal* (auth, validation) failures.
- **Checkpoint/resume.** Long loops must survive restart; LangGraph's
  per-mutation checkpointing is the reference.
- **Scoped tool loading.** Loading all tool definitions upfront slows agents and
  raises cost (Anthropic). Scope tools **per stage**.

**Context degradation is the physics constraint here.** Liu et al. showed LLMs
perform markedly worse when relevant information is buried mid-context. More
irrelevant material = worse performance on the material that matters. Every
loop iteration that appends without pruning makes the next iteration worse.

---

## 6. ICM / Model Workspace Protocol (L5) — the user's specific ask

**Source:** *Interpretable Context Methodology: Folder Structure as Agentic
Architecture* — Jake Van Clief & David McDermott, arXiv:2603.16021 (Mar 2026),
MIT licensed. Also called Model Workspace Protocol (MWP).
Channel: youtube.com/@JEVanClief · Repos: `RinDig/Interpretable-Context-Methodology`.

### 6.1 The thesis

> If the prompts and context for each stage of a workflow already exist as files
> in a well-organised folder hierarchy, you do not need multiple agents or a
> coordination framework. You need **one agent that reads the right files at the
> right moment.**

The filesystem does what a framework would do in code:

| Framework concern | ICM mechanism |
|---|---|
| Stage sequencing | Folder **numbering** |
| Context scoping | Folder **hierarchy** |
| State management | **Files on disk** |
| Stage coordination | One folder's `output/` is the next's input |
| Observability | **Open the folder and read** — no logging layer |

### 6.2 The five context layers

```
workspace/
  CLAUDE.md / IDENTITY.md   ← L0  identity, broad goals (always loads)
  CONTEXT.md                ← L1  task routing: which folder handles what
  stages/
    01-research/
      CONTEXT.md            ← L2  STAGE CONTRACT (the control point)
      references/           ← L3  reference material for this stage
      output/               ← L4  working artifacts (handoff point)
    02-script/  …
    03-production/  …
  _config/                  ← L3  brand, voice, design system
  shared/                   ← L3  cross-stage resources
  skills/                   ← L3  bundled domain knowledge
  setup/questionnaire.md    ←     one-time onboarding
```

- **L3 persists across runs** (stable knowledge).
- **L4 changes every run** (working artifacts).
- **L2 is the control point of the entire system.**

### 6.3 The stage contract

Every stage `CONTEXT.md` has **Inputs / Process / Outputs**. The Inputs table
names not just the file but **the section** to load:

```markdown
## Inputs
| Source         | File/Location            | Section/Scope | Why            |
|----------------|--------------------------|---------------|----------------|
| Previous stage | ../01-research/output/   | Full file     | Source material|
| Style guide    | ../../_config/voice.md   | Voice Rules   | Tone guidance  |

## Process
1. Read the research output
2. Identify the narrative angle
3. Write following voice-rules
4. Run audit checks
5. Save to output/

## Outputs
| Artifact | Location                | Format                        |
|----------|-------------------------|-------------------------------|
| Script   | output/[slug]-script.md | Markdown with metadata header |
```

Without this scoping the agent either loads everything or guesses. The Inputs
table makes selection **explicit, editable, and auditable**.

### 6.4 The measured payoff

| Approach | Tokens in context |
|---|---|
| ICM stage (L0–L2 structural ≈1.3–1.6k, +L3 0.5–2k, +L4) | **2,000–8,000** |
| Monolithic (all stages, all refs, all prior outputs) | **30,000–50,000** |

The monolithic bar is mostly *irrelevant* tokens — other stages' instructions,
reference material for a different stage, already-consumed outputs. ICM never
loads them. Compression research treats this after the fact; ICM avoids it by
construction.

### 6.5 The conventions that matter

- **Plain text as the interface.** No binary, no DB, no proprietary format.
- **Configure the factory, not the product.** Set the workspace up once; every
  run reuses it with new inputs.
- **One stage, one job.**
- **Every output is an edit surface** — human reviews/edits between stages.
- **Canonical sources.** Every fact has one home; others point at it. The moment
  a rule lives in two files, they drift.
- **One-way references.** If A references B, B must not reference A.
- **Selective section routing** — load the section, not the file.
- Size discipline: `CONTEXT.md` **< 80 lines**, reference files **< 200 lines**.
- **The walk test:** an agent with no memory opens the root, finds its way,
  acts, and reports status **from the files alone**. If it can't, the workspace
  is wrong.

### 6.6 The known failure mode — and it applies directly to us

> "When you add more and more folders agents begin to skip information.
> Guidelines are missed, rules are overlooked… the model scans economically and
> thinks it knows enough. The solution is simple: **the agent has to actually
> start in the right folder.** Start in a central place and the layered context
> never loads; start in the right place and the agent is instantly grounded."

In a team, *"just cd to the correct directory"* is exactly the invisible,
error-prone step that breaks repeatability. **Any implementation must make
stage entry explicit and automatic, not a convention users must remember.**

### 6.7 ICM vs MCP

Different layers, complementary. MCP standardises how a model *reaches tools*.
ICM structures *what context the agent receives* across a multi-stage workflow.
An ICM stage may use MCP connections; the folder structure decides what context
it has while doing so.

---

## 7. Edge / AI-native infrastructure (L0)

- **Model routing as a first-class kernel concern.** Frontier cores (GPT/Claude/
  Gemini) and local cores (Llama/Mistral/Ollama) behind one dispatcher that
  routes by **cost class and task class**, with quota accounting.
- **Local-first / edge** matters for privacy, latency and cost. Hermes'
  `~/.hermes/` local-memory pattern and portable `SKILL.md` are the reference.
- **Per-workspace container isolation** is the emerging norm (Eduba ships
  exactly this: each workspace in its own container, rendering markdown, editing
  files, installing packages, running Python/Playwright, multi-user real time).
- **Sandboxing tiers observed:** Docker + capability groups → WASM dual-metered
  → Firecracker microVM. Choose by blast radius.

---

## 8. Observability & governance (cross-cutting)

The literature is unusually consistent here, going back decades:

- Opaque automation produces **two** failure modes — blind trust (misuse) and
  abandonment (disuse). Both come from *the human not being able to see what
  happened between input and output* (Parasuraman & Riley).
- **Appropriate trust requires observable behaviour** (Lee & See).
- Mixed-initiative systems must let users **invoke, adjust, and terminate** at
  natural breakpoints (Horvitz) — which requires visible state and reversible
  actions.

ICM's strongest property is arguably accidental: because every intermediate
output is a plain file, **the system is observable by default**. No logging
layer, no dashboard to configure.

> **This is the through-line of the entire module review so far.** Fourteen
> modules in, the dominant defect class has been *confident reporting of things
> the system never verified*. That is precisely the "opaque automation" failure
> the HCI literature predicts. The fix pattern the review converged on
> independently — return `None` for unmeasured, expose the basis, state coverage
> — is the same principle these papers arrived at.

---

## 9. Gap analysis — this platform against the reference

Assessed against the actual codebase, not aspiration.

### Already strong

| Capability | Evidence |
|---|---|
| Tool layer (MCP) | `mcp.py` + `mcp_gateway.py`, 24 endpoints |
| **Access Manager** | MCP Gateway policy engine — priority, conditions, HITL, audit. This is a genuine kernel module. |
| Agent interop (A2A) | `a2a.py`, 16 endpoints |
| HITL | `hitl.py`, 10 endpoints + gateway integration |
| Workspace context | `hierarchy.py` — Tier 1 / IVREN is **already ICM-shaped** |
| Steering / procedural memory | `steering.py`, 11 endpoints, injected into every call |
| Evals | `evals.py` + eval-framework |
| Model routing | `fusion.py` + `services/llm.py` (frontier + Ollama) |
| Audit | `audit_log.py`, compliance reporting |
| Hybrid retrieval (partial) | FTS5 present; Qdrant optional; `embedding_json` column exists |

### Gaps, ranked by value

| # | Gap | Layer | Why it matters | Size |
|---|---|---|---|---|
| 1 | **No explicit memory tiering** (episodic/semantic/procedural/working) | L2 | The single highest-value layer per §1. Outcomes aren't recorded, so agents can't learn. | L |
| 2 | **No reranking, no RRF fusion** | L2 | The 2026 baseline. FTS5 + vectors exist but aren't fused or reranked. | M |
| 3 | **Knowledge graph not wired into retrieval** | L2 | `knowledge_graph.py` exists but isn't a retrieval path. GraphRAG is where global/multi-hop questions get answered. | M |
| 4 | **Kernel modules not named as such** | L3 | Scheduler/context/memory managers are implicit and scattered. Nothing to test or reason about. | L |
| 5 | **No ICM workspace runtime** | L5 | The user's explicit ask. `hierarchy.py` is close but is a fixed 2-tier scheme, not numbered stages with contracts. | M |
| 6 | **Loop safety rails not standardised** | L4 | `loops.py` exists; needs the §4.3 rail set as enforced defaults. | S |
| 7 | **No provenance on memory writes** | L2 | Memory-poisoning exposure (§3.4). | M |
| 8 | **Tool definitions not scoped per stage** | L3 | Cost + latency, per Anthropic. | S |
| 9 | **No ontology layer** | L5 | User asked for ontologies; nothing types entities/relations today. | M |

### Recommended sequence

Ordered by *value ÷ blast radius*, and chosen so each step is independently
shippable and testable:

1. **ICM workspace runtime** (#5, #9) — the explicit ask, and it is additive:
   a new workspace type alongside `hierarchy.py`, not a rewrite. Delivers the
   folder-as-architecture, stage contracts, `.md` ontologies, and the walk test.
2. **Memory tiering + provenance** (#1, #7) — schema plus write-path discipline.
   Unlocks agent learning and closes the poisoning hole.
3. **Hybrid retrieval: RRF + rerank + graph expansion** (#2, #3) — makes RAG
   match the 2026 baseline; reuses FTS5 and the graph tables already present.
4. **Name the kernel** (#4, #8) — refactor the implicit scheduler/context/memory
   managers into named services with tests. Largest blast radius; do it once the
   layers above are stable.
5. **Loop rails** (#6) — small, self-contained, do it opportunistically.

---

## 10. Primary sources

| Source | Why it matters |
|---|---|
| Van Clief & McDermott, *Interpretable Context Methodology*, arXiv:2603.16021 | The ICM/MWP spec. §6 is drawn from it. |
| `github.com/RinDig/Interpretable-Context-Methodology` | Reference implementation, `_core/CONVENTIONS.md` |
| Mei et al., *AIOS: LLM Agent Operating System*, arXiv:2403.16971 | The six kernel modules; syscall catalogue |
| *SoK: Agentic RAG*, arXiv:2603.07379 | Formal Active-vs-Agentic RAG distinction; failure modes |
| Mem0, arXiv:2504.19413 | Two-phase extraction, three-scope hierarchy, hybrid backend |
| MemGraphRAG, arXiv:2606.00610 | Shared-memory multi-agent graph construction |
| Liu et al. 2024 | Lost-in-the-middle — the physics constraint behind §5 |
| Zep / Graphiti | Bitemporal episodic graph; retrieval with no LLM calls |
| Strands multi-agent guide | The §4.3 safety-rail defaults |
| Parasuraman & Riley; Lee & See; Horvitz | Why observability is a correctness property |
