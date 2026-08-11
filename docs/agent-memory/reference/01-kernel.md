# 01 — The Agent Kernel

> Scheduling, context management, isolation, and resource accounting for
> autonomous agents. Source: AIOS (arXiv:2403.16971) + production practice.

---

## The mapping that makes this tractable

| OS concept | Agentic OS counterpart |
|---|---|
| CPU | LLM (one or many "cores" of differing cost/capability) |
| Process | Agent instance with its own goal and state |
| RAM | Context window |
| Syscall | Tool call — a *request* to the kernel, not a direct action |
| Scheduler | Which agent gets the next model call |
| Context switch | Snapshot/restore of in-flight generation |
| Virtual memory / paging | Compaction, summarisation, spill to storage |
| File system | Vector store, graph, object store, plain files |
| Permissions | Per-agent scoped credentials and tool allow-lists |
| `kill -9` | Kill switch / budget breach / max-iteration stop |

The value of the metaphor is that it names concerns that are otherwise implicit
and therefore untested. If you cannot point at your scheduler, you have one
anyway — it is buried in a queue and nobody owns it.

## The six kernel modules

**1. Scheduler.** Decides which agent request runs next. FIFO is the honest
default; round-robin prevents one agent starving others; priority queues need a
starvation guard. AIOS reports up to **2.1× throughput** from centralising queues
in the scheduler rather than per-module. Centralise the queues — it isolates
request management from execution and gives you one place to add fairness,
quotas, and tracing.

**2. Context manager.** Snapshot and restore of generation state so a long call
can be interrupted and resumed rather than restarted. Also owns compaction
policy. This is the module most systems lack, and its absence shows up as
"the agent forgot what it was doing".

**3. Memory manager.** Per-agent working state. Must be **isolated by
construction** — cross-agent leakage here is both a correctness and a security
failure. See `02-memory.md`.

**4. Storage manager.** Durable state: files, vectors, graphs, snapshots.
The boundary with memory is a swap boundary; treat it like one.

**5. Tool manager.** Loads, validates, and mediates tool invocation. The single
choke point where scoping, rate limits, and audit belong. See `04-tools-mcp.md`.

**6. Access manager.** Privilege checks between agents and resources. Not
dispatched by the scheduler — it gates *before* the queue.

## LLM cores: routing as a kernel concern

Multiple backends of differing cost, latency and capability. The kernel routes;
agent code should not know which model served a request.

- Route by **task class** (cheap model for classification, frontier for
  synthesis), then by load, then by cost.
- Per-agent credentials matter: an agent-scoped API key must actually be used
  when that agent runs, or the scope is decorative.
- Account tokens and cost **at the kernel**, not at 30 call sites. Recording
  cost at each caller reliably produces a 1-in-30 hit rate and a FinOps
  dashboard that reports chat traffic only.
- Budget enforcement belongs at the same layer for the same reason. A cap wired
  into one router stops that router and nothing else.

## Context management in practice

Context is finite and degrades before it fills — "context rot" means recall
falls as tokens grow, because attention is n² over the window.

**Three techniques, in increasing order of complexity:**

1. **Compaction.** Summarise history, reinitialise with the compressed form.
   Preserve architectural decisions, unresolved bugs, exact identifiers, file
   paths. Discard tool outputs and repeated messages. Maximise recall first,
   then improve precision. Risk: cumulative summarisation bias — keep original
   IDs verbatim.
2. **Structured note-taking.** The agent maintains external memory files
   (`NOTES.md` with fixed sections: Goals / Decisions / TODO / Evidence). Cheap,
   inspectable, diffable, and survives a context reset entirely.
3. **Sub-agents.** Isolate a noisy sub-task (search, exploration) in a child
   with its own clean window; the parent receives only the synthesis. This is
   the highest-leverage technique for research-shaped work.

**Choosing:** long conversation → compaction. Iterative build with milestones →
notes. Parallel exploration → sub-agents. Most real systems use all three.

## Isolation model

The honest limitation of the OS metaphor: agent invocations are one-dimensional.
Each has its own context, own state, own lane. There are **no shared-memory
threads**, and inventing a thread analogue adds complexity that buys nothing.
Isolate hard; communicate through explicit, validated messages.

Blast-radius rules that hold up:

- One-hop delegation limit by default (A calls B; B may not call C) unless the
  topology genuinely needs depth. Prevents runaway cost and error propagation.
- Separate credentials per agent, not one shared key.
- Circuit breakers between planner and executor.
- Schema validation on every inter-agent hop — a sub-agent's output is
  untrusted input to its parent.

## What to build, in order

1. Tool calls go through **one** mediated path (you now have a tool manager).
2. Cost and budget accounting at that path (you now have quotas).
3. Explicit per-agent state with no cross-reads (you now have isolation).
4. A queue you can inspect (you now have a scheduler).
5. Compaction + note files (you now have a context manager).
6. Model routing behind an interface (you now have cores).

Steps 1–3 are non-negotiable for anything running unattended. 4–6 are what turn
a script into a platform.

## Failure modes specific to this layer

- **Implicit scheduler.** Queue logic scattered across routers; no fairness, no
  visibility, no way to shed load.
- **Cost recorded at call sites.** Guaranteed to be incomplete, and it regresses
  the moment someone adds a caller.
- **Budget caps that consult a different table than the enforcer.** A cap the
  UI writes and nothing reads is worse than no cap: the user believes they are
  protected.
- **Loops with no ceiling.** Every autonomous loop needs max-iterations,
  max-cost, max-wallclock, and a stop-on-success option — all *enforced*, not
  merely stored.
- **State that does not survive restart.** An "autonomous" background worker
  that evaporates on deploy is the opposite of autonomous, and its absence is
  silent: an empty list looks identical to "you never created one".
- **Attributes that only exist once started.** Reading scheduler state before
  start-up throws; the listing then 500s at exactly the moment the operator
  needs to see it.
