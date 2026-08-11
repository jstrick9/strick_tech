# 02 — Agent Memory

> The CoALA taxonomy, storage substrates, consolidation, forgetting, and
> markdown/folder memory (ICM). Memory is where "agentic" stops being a chatbot.

---

## The taxonomy (CoALA, Princeton 2023)

| Type | Cognitive analogue | Concrete artefact | Substrate | Lifetime |
|---|---|---|---|---|
| **Working** | Attention / current focus | Context window: task, plan, recent tool results, scratchpad | The window itself | One task; discarded unless persisted |
| **Episodic** | "What happened" | Transcripts, event logs, run outcomes | Append-only store, session DB | Days–months; TTL + summarisation |
| **Semantic** | "What is known" | Facts, preferences, entity knowledge | Vector store, KV, graph, tables | Long-lived, individually revisable |
| **Procedural** | "How to do it" | Prompt rules, playbooks, skills, code | **Version-controlled files** | Long-lived; changed by review, not overwrite |

A fifth type matters in any multi-tenant or enterprise setting:
**organisational context** — governed definitions, lineage, access policy,
cross-system entity identity. The first four are agent-scoped; this one is what
they all draw from, and it belongs in a structured layer, not a vector store.

**The single most useful distinction:** procedural memory is *reviewed*, never
auto-written. If an agent can silently rewrite its own rules, it will, and you
will not find out until behaviour drifts.

## Choosing a substrate — by retrieval mode, not by storage

| Substrate | Retrieval | Strong at | Weak at | Natural contents |
|---|---|---|---|---|
| Vector store | Semantic similarity | Fuzzy recall at scale, no schema | No exact lookup; duplicates pile up; **similarity ≠ truth** | Facts, episode summaries, chunks |
| Key-value | Exact key | Fast, cheap, trivial TTL | You must know the key | Preferences, settings, counters |
| Graph | Traversal | Multi-hop, explicit relations | Modelling and upkeep cost | Entity relations, dependencies |
| Relational | Structured predicates | Filtering, aggregation, audit | Rigid; poor fuzzy recall | Episode metadata, audit, bookkeeping |
| **Plain files (versioned)** | Path / name | Human-reviewable, diffable, git-native | No query beyond naming | **Procedural memory: playbooks, rules, notes** |

Most teams reach for a vector DB reflexively. Ask what *retrieval mode* the
content needs. Preferences are a KV lookup. Playbooks are files. Only genuinely
fuzzy recall needs embeddings.

## Consolidation

Three processes turn storage into memory:

1. **Integration** — new information reconciled against existing knowledge;
   conflicts resolved explicitly rather than by last-write-wins.
2. **Abstraction** — recurring patterns in episodic memory promoted to semantic
   facts; frequently used semantic knowledge informs procedural updates.
3. **Refinement** — existing memories revised as evidence changes.

**Supersession over deletion.** When a fact changes, write the new fact with a
pointer to what it replaced. You need the history to debug "why did the agent
believe that?".

## Forgetting is a feature

Unbounded memory is not better memory — it is slower retrieval, higher cost, and
more stale contradictions.

| Content | Default lifetime posture |
|---|---|
| Working snapshots, intermediate tool output | Session-scoped; gone at end |
| Raw episodes | Short TTL (days–months), driven by debugging/compliance |
| Episode summaries | Medium TTL |
| Semantic facts | No fixed TTL; governed by staleness checks and supersession |
| Preferences | No TTL; revised by supersession |
| Procedures | **Never** TTL'd; versioned and deprecated explicitly |

Add a **staleness check**, not just a TTL: a fact with a timestamp, a source,
and a confidence is checkable. A bare string is not.

## Provenance is not optional

Every memory should carry: source, timestamp, confidence, and how it was
derived. Without provenance you cannot answer the two questions that matter
during an incident — *where did this come from?* and *what else did it affect?*

This also makes memory poisoning detectable (see `07-security.md`, ASI06):
poisoned entries usually lack plausible provenance or arrive from a trust tier
that should not be able to write semantic memory.

## Tiering and fusion

A mature memory layer has **tiers** (hot working set, warm episodic, cold
archive) and **fusion** when reading across them. Reciprocal Rank Fusion is the
standard way to merge ranked lists from different retrievers without hand-tuned
weights:

```
RRF(d) = Σ  1 / (k + rank_i(d))        k ≈ 60 by convention
```

RRF is rank-based, so it is robust to retrievers whose scores are on different
scales — which is exactly the case when fusing vector, lexical, and graph hits.

## Markdown and folders as memory (ICM)

The **Interpretable Context Methodology** treats filesystem structure as agent
architecture. Instead of framework orchestration, the folder *is* the program:

| Framework concern | ICM mechanism |
|---|---|
| Stage sequencing | Folder numbering (`01-`, `02-`) |
| Context scoping | Folder hierarchy |
| State | Files on disk |
| Instructions | Markdown, human-readable |

**Layer model:** L0 `IDENTITY.md` (who) → L1 `CONTEXT.md` (what exists) →
L2 stage contract (Inputs / Process / Outputs) → L3 references + config →
L4 output.

**Conventions that make it work:**
- `CONTEXT.md` under ~80 lines; references under ~200.
- One-way references only — no cycles, no reference pointing at a reference.
  One level of indirection is the practical limit before an agent gets lost.
- One canonical source per fact. Duplication guarantees divergence.
- **2–8k tokens per stage** rather than 30–50k monolithic.

**Walk test:** an agent with no memory opens the root, finds its way, and
reports status from files alone.

**Known failure mode:** agents skip information as folders multiply, *unless*
they start in the right folder. So compute the entry point; never assume it.

## Agent Skills — the same idea, standardised

`SKILL.md` + optional `scripts/`, `references/`, `assets/`. Three-level
progressive disclosure:

| Level | Loads | Cost | When |
|---|---|---|---|
| 1 | YAML frontmatter (`name`, `description`) | ~30–100 tokens | Always, per installed skill |
| 2 | SKILL.md body | <5k tokens | When the description matches the task |
| 3 | Bundled files | ~0 until read | Only when the body points there |

Startup cost is proportional to the *number* of skills, not the *volume* of
knowledge. Practical rules: body under 500 lines; references one level deep;
executable scripts for computation so the source never enters context.

**Security caveat:** published skills carry a high rate of "skill smells" and a
meaningful fraction contain security flaws. A skill is executable content from
a supply chain — review it like a dependency (`07-security.md`, ASI04).

## Failure modes specific to this layer

- **Memory that does not survive restart** while the UI implies persistence.
- **Scope stored but never read.** A per-agent memory scope that no retrieval
  path filters on is decorative; worse, it implies isolation that is absent.
- **Empty-scope-means-everything.** `if required and scope and required not in
  scope` skips the check when scope is empty — and empty is usually the default.
- **Similarity mistaken for truth.** Top-k returns nearest neighbours, not
  correct answers. Rank ≠ relevance ≠ correctness.
- **Silent overwrite of procedural memory.** Rules edited by the agent with no
  version, no diff, no review.
- **Unbounded growth.** No TTL, no dedupe, no consolidation; retrieval quality
  degrades and nobody can point to when it started.
