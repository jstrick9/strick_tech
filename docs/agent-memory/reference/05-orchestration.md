# 05 — Orchestration: Loops, Graphs, Multi-Agent

> How work actually gets executed. Start with a workflow; earn the agent loop.

---

## Workflow vs agent — the decision you make first

- **Workflow:** predefined code paths that orchestrate a model. Predictable,
  cheap, debuggable.
- **Agent:** the model dynamically directs its own process. Flexible,
  expensive, non-deterministic.

Anthropic's guidance is blunt and correct: **reach for the workflow first.**
Accept the cost and unpredictability of a full agentic loop only when the task
genuinely needs it — when the steps cannot be known in advance.

Most "agent" products would be better, cheaper, and more reliable as a workflow
with one or two model calls inside it.

## Loop engineering

The canonical loop:

```
gather context → take action → verify work → repeat
```

**Verification is the step that unlocks quality.** Anthropic's own finding:
Claude performed dramatically better on web-app work once given browser
automation and told to test features the way a human would — because it could
then find bugs invisible from the code alone.

> **Build the verifier before you scale the generator.**

Every loop needs, explicitly:

| Control | Why |
|---|---|
| Max iterations | Prevents infinite loops |
| Max cost / token budget | Prevents Denial-of-Wallet, self-inflicted or not |
| Max wallclock | Prevents a hung tool stalling forever |
| Stop-on-success | The loop should know when it is done |
| Progress check | Detect "same action repeated with no state change" |
| Recovery / retry policy | Distinguish transient from terminal failure |

All of these must be **enforced**, not merely configured. A stored limit nothing
reads is a lie told to the operator.

**Long-running loops must survive restart.** Persist the schedule, the run
count, and the history. A loop that was *paused* comes back paused — silently
resuming someone's autonomous agent because the process bounced is worse than
leaving it stopped.

## Graph engineering

When control flow has genuine branching, state, and joins, model it as a graph:
nodes are steps, edges are transitions, state is explicit and checkpointed.

**What a graph buys you:** durable state across restarts, time-travel debugging,
explicit human-in-the-loop breakpoints, retry per node, parallel fan-out with
a join, and a topology you can *see* — which is the point when you need to audit
a routing mistake.

**DAG execution notes:** validate acyclicity before running; compute waves for
parallelism; propagate failure explicitly (does a failed node abort, skip, or
substitute?); make the join semantics deliberate (all, any, quorum).

## Multi-agent topologies

Three dominate production in 2026:

**1. Supervisor / hierarchical.** One coordinator routes to N specialists and
aggregates. Pros: oversight, scoped budgets, one trace tree, high debuggability.
Cons: coordination overhead; supervisor context grows and can OOM.

**2. Orchestrator–worker (~70% of production).** Planner decomposes; workers
execute in parallel; results synthesised. Pros: parallelism, specialisation.
Cons: orchestrator bottleneck.

**3. Swarm / network.** Peers hand off directly, no central coordinator, with a
termination rule. Pros: good for embarrassingly parallel exploration. Cons:
token cost is quadratic if peers broadcast; **debuggability is low**; the
signature failure is an infinite handoff loop.

| | Supervisor | Swarm |
|---|---|---|
| Coordinator | Single central | None; peer-to-peer |
| Best for | Heterogeneous specialists | Parallel research |
| Token cost | Linear + supervisor growth | Quadratic if broadcasting |
| Debuggability | High — one trace tree | Low — handoff graph |
| Failure mode | Supervisor context OOM | Infinite handoff loop |

**Naming is not standardised.** LangGraph "supervisor", CrewAI "hierarchical
process", AutoGen "group chat with manager", OpenAI "orchestrator-worker" are
the same pattern with different ergonomics. Pick one internal name, document it
once, use it everywhere.

## Framework landscape (know the mental models, not the star counts)

| Framework | Mental model | Best for |
|---|---|---|
| **LangGraph** | Graph (StateGraph + checkpointers) | Explicit state, HITL gates, durable production |
| **OpenAI Agents SDK** | Handoff is the primitive | OpenAI-native delegation, built-in tracing |
| **CrewAI** | Role (Agent + Task + Crew) | Fast scaffolding of role-based pipelines |
| **AutoGen / MS Agent Framework** | Actor / async message-passing | Conversational and group-chat patterns |
| **Smolagents** | Code-first (agent writes Python) | Script-shaped tasks |
| **Temporal** | Durable workflow, event-history replay | Multi-day workflows that must survive restarts |

Pick by mental model, not popularity — matching model to workflow shape is what
prevents painful rewrites. And note: the *inner loop* is often best served by
the vendor SDK, wrapped in a graph framework on the outside.

## Judging and aggregation

When multiple agents produce candidates and one must be selected:

- **Validate the verdict against reality.** A judge naming an agent that never
  ran must not win. Check the winner is in the set of runs that actually
  produced output.
- **Fall back explicitly and say so.** "Judge named X, which produced no
  response — fell back to the longest valid answer" is a good message.
- **Do not carry a fabricated score.** If the verdict was rejected, the score
  goes with it.
- **A run where everything failed is not a success.** Report
  `complete` / `partial` / `failed` with counts, never a hardcoded `ok: true`.

## Failure modes specific to this layer

- **Agent used where a workflow would do.** Non-determinism and cost with no
  compensating benefit.
- **No stopping condition.** The single most expensive class of bug in
  autonomous systems.
- **Kill switch that was never tested.** A documented stop that has never been
  exercised does not exist.
- **Retirement one tick late.** Budget checked *before* an iteration means an
  N-run loop sits scheduled until its N+1th wake-up.
- **Hallucinated identifiers trusted.** Judges and planners invent names
  routinely; validate every reference against what exists.
- **Cascading failure with no circuit breaker.** A small error in planning
  propagates through execution and into memory, where it compounds.
- **Partial success reported as success.** 1 of 200 files written, `ok: true`.
- **Unbounded delegation depth.** A → B → C → … until cost or context explodes.
  Default to one hop.
