# 13 — The Frontier

> Where the field is going, who is building what, and what that implies for
> what you build next. Dated mid-2026 — treat directional claims as directional.

---

## Who is building the agent-native OS

Fragmentation reveals the disagreement about what the primitive is:

| Actor | Bet | What they expose |
|---|---|---|
| **Anthropic** | Context engineering + skills + MCP | Agent SDK, Skills (`SKILL.md`), sub-agents, MCP (they authored it) |
| **OpenAI** | Platform distribution | Agents SDK with handoff as primitive; apps-in-chat; no kernel primitives |
| **Google** | Cross-agent protocol | ADK, A2A as default agent-to-agent transport |
| **Microsoft** | Enterprise consolidation | Agent Framework (Semantic Kernel + AutoGen merged), Azure-native |
| **AIOS (academic)** | Actual kernel | Scheduler, context manager, syscalls, semantic file system |
| **LangChain** | Explicit topology | LangGraph — the graph *is* the artefact; ~38% of multi-agent production |
| **Temporal** | Durability | Event-history replay; survives a restart at hour 17 |

**Read:** nobody has shipped a real agent OS yet. ChatGPT is architecturally a
conversational interface with app frames — no process table, no scheduler, no
shared-memory model. AIOS has the right architecture and the smallest ecosystem.
**The gap between "agent framework" and "agent operating system" is where the
opportunity is**, and it is a systems-engineering opportunity, not a model one.

## Directional shifts to build toward

**1. Agentic search is displacing classical RAG.** Anthropic's own coding-agent
lesson: *"Everything is a file. Bash is the ultimate tool. Most tool calls are
just code. Agentic search > RAG."* Give the agent primitives (glob, grep, read)
and let it navigate, rather than pre-computing an index of everything. Hybrid in
practice: `CLAUDE.md`-style files loaded up front for speed, primitives for
just-in-time flexibility.

**2. Stateless, cacheable, routable protocols.** MCP 2026-07-28 removed
handshakes and sessions, moved method names into HTTP headers, made list results
cacheable, and replaced held-open bidirectional streams with Multi Round-Trip
Requests. The direction is explicit: *agent infrastructure should work like the
rest of the web.* Build servers that can sit behind a round-robin load balancer.

**3. Skills as the packaging unit.** ~40 platforms now read `SKILL.md`.
Progressive disclosure means library size costs nothing until used. Expect
skills, not plugins, to be how capability is distributed — and expect a skill
supply-chain security problem, because it is already measurable.

**4. Memory as a product surface, not an implementation detail.** Context
editing plus a memory tool measured **+39% over baseline** on 100-turn agentic
search; context editing alone +29%. Memory is now a capability users choose and
inspect, not plumbing.

**5. Verification-centric loops.** As autonomous run duration grows, the model
must verify correctness without constant human feedback. The differentiator
shifts from generation quality to *verification* quality — build the verifier
before you scale the generator.

**6. Governance becomes a gate, not a document.** EU AI Act high-risk
obligations are enforceable from **2 August 2026**. Article 14 human oversight
means the override log is a required artefact. Systems without audit trails will
be procurement-blocked before they are fined.

**7. Multi-agent is consolidating on orchestrator-worker** (~70% of production).
Swarm topologies persist for parallel research but lose on debuggability. Expect
the industry to keep converging on *explicit, traceable* topologies.

## What is genuinely unsolved

Be honest about these rather than claiming to have solved them:

- **Indirect prompt injection.** No robust defence exists. Delimiting helps;
  least agency helps more; nothing eliminates it. Anyone claiming a solution is
  selling something.
- **Long-horizon coherence.** Compaction loses detail; summarisation bias
  accumulates. Anthropic's own framing: maintaining coherence across extended
  interactions "will remain central".
- **Evaluating agent *trajectories*.** We score final answers well and
  intermediate reasoning badly. Joint scoring of trajectory + retrieval is an
  open research area.
- **Cost predictability.** Agentic loops have unbounded worst-case cost.
  Budget caps are a blunt instrument, not a solution.
- **Multi-agent debuggability.** Swarms are hard to reason about; the industry
  chose supervisors largely to make debugging tractable.
- **Do graphs still help once an agent is in the loop?** Papers reach opposing
  conclusions. Measure on your corpus.
- **Trust calibration.** We know over- and under-trust are both harmful. We do
  not have a reliable way to measure calibration in the field.

## What to build next in an Agentic OS

Ordered by leverage:

1. **Name the kernel.** Even if you never write a scheduler, naming the
   scheduler, context manager, tool manager, and access manager as distinct
   concerns clarifies the codebase. *Hidden coupling between these modules is
   the most common source of agent-runtime bugs.*
2. **Scoped tool loading.** Per-stage tool sets. Cheapest security and quality
   win available — fewer tools improves selection accuracy *and* shrinks the
   attack surface.
3. **Verification as a first-class stage.** Every loop declares how it checks
   its own work.
4. **Memory tiers with provenance and forgetting.** Not one vector store.
5. **Trajectory evals in CI**, not just answer evals.
6. **A tested kill switch**, exercised on a schedule.
7. **Semantic file system.** Agents navigating by meaning rather than path
   (AIOS integrated exactly this).

## How to read this file in six months

The specifics will age — spec versions, framework rankings, adoption numbers.
The structural claims will age more slowly:

- The OS decomposition is right, and every serious runtime converges on it.
- Context is a budget; progressive disclosure is the general solution.
- Verification, not generation, is the quality bottleneck.
- Honest reporting is the difference between a demo and a product.

When a specific claim here conflicts with what you observe, **the observation
wins**. Update this file and say what changed.
