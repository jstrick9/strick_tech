# 03 — Retrieval: RAG, GraphRAG, Agentic RAG

> How an agent gets grounded facts. The 2026 baseline is hybrid + rerank, with
> graph for global questions and agentic control for hard ones.

---

## What changed, 2023 → 2026

| Layer | 2023 default | 2026 default |
|---|---|---|
| Retrieval | Dense embeddings only | **Hybrid** (BM25 + dense) fused with RRF |
| Reranking | None | Cross-encoder reranker on top-k |
| Query handling | Pass raw | Rewrite (HyDE, step-back, decomposition) when ambiguous |
| Orchestration | Retrieve → generate | Agentic loop / multi-hop when needed |
| Knowledge shape | Flat chunk store | Hybrid + a graph layer for global questions |
| Evaluation | Manual spot-check | Continuous groundedness + context adherence |
| Runtime safety | None | Inline hallucination guardrail at the boundary |

## The pipeline

**1. Ingestion.** Parse, chunk, normalise, deduplicate. Chunking is the most
under-rated decision: chunk on semantic boundaries (headings, functions), keep
a parent-document pointer, and store metadata (source, date, section) because
you will filter on it later.

**2. Indexing.** BM25 (lexical) + dense embeddings (semantic) + optionally a
graph. Keep them in the same store if you can — a single query that joins them
beats three round trips.

**3. Query processing.** Classify intent. Rewrite when ambiguous. Decompose when
compositional. *HyDE* (generate a hypothetical answer, embed that) helps when
the question and the corpus use different vocabulary. *Step-back* helps when the
question is too specific to match anything.

**4. Retrieval.** Hybrid with RRF:

```
RRF(d) = Σ 1 / (k + rank_i(d))     k ≈ 60
```

Rank-based fusion is robust to incomparable score scales. This is why it beats
weighted score blending in practice.

**5. Reranking.** A cross-encoder over the top ~50 → keep ~5. This is usually
the single highest-ROI addition to a mediocre RAG system, because bi-encoder
retrieval optimises for recall and the reranker supplies precision.

**6. Generation.** With citations. Always with citations.

**7. Guardrail.** Groundedness check at the boundary before the answer ships.

## GraphRAG

Build an entity-and-relation graph from the corpus, summarise densely connected
communities, and retrieve over that structure.

**Where it wins decisively:** *global* questions — "what are the main themes",
"how do these entities relate", "what changed across the corpus". Vector search
is structurally bad at these because no single chunk contains the answer.

**Where vector wins:** local, specific, full-text questions.

**So:** route. An agent that picks GraphRAG for structured/metadata queries and
VectorRAG for nuanced full-text queries beats either fixed pipeline. That
routing decision is itself the "agentic" part.

## Agentic RAG

Retrieval becomes a **tool the model can call repeatedly** within one turn,
rather than a fixed pre-step.

The loop: inspect question → decide whether evidence is sufficient → rewrite and
retrieve again → critique → answer only when grounded.

Four agent roles crossed with three graph operations covers most of the
literature: single-agent iterative traversal, self-evolving graphs, RL-trained
walkers, multi-agent graph systems, agentic graph construction, persistent graph
memory, hybrid structured/unstructured.

**The honest disagreement:** recent papers reach opposing conclusions on whether
graphs still earn their keep once an agent is in the loop. The resolution is
usually corpus shape — graphs pay off when relations are dense and questions are
global; they are overhead when the corpus is a pile of independent documents.
Measure on *your* corpus; do not adopt on principle.

**Cost:** agentic RAG multiplies calls. Budget it, cap the hops, and measure
whether the extra retrieval actually changed the answer.

## Evaluation — the part most teams skip

Four metrics that matter, and where each belongs:

| Metric | Question | Needs ground truth? | Runs |
|---|---|---|---|
| **Faithfulness / groundedness** | Is the answer supported by retrieved context? | No | Every deploy + sampled prod |
| **Answer relevance** | Does it address the question? | No | Every deploy + sampled prod |
| **Context precision/recall** | Did retrieval find the right things? | Yes | CI against golden set |
| **Answer correctness** | Is it right? | Yes | CI against golden set |

Retrieval-specific: recall@k, precision@k, MRR, nDCG. Measure retrieval
separately from generation — otherwise a retrieval regression looks like a
model regression and you tune the wrong thing.

**Golden dataset:** 20–50 items catches gross regressions; 100–200 gives
confidence on 3–5% differences; >500 is diminishing returns. Build from real
traces first, CSV second, synthetic third. Every production incident becomes a
case. Keep a **holdout partition never used in CI** — if CI and holdout diverge,
you are overfitting to the eval set.

## Failure modes specific to this layer

- **Similarity treated as truth.** Top-k is nearest neighbours. A confident
  answer from irrelevant chunks is the default failure, not an edge case.
- **Retrieved text treated as instruction.** The primary indirect prompt
  injection vector. Retrieved content is *data*; delimit it and say so in the
  system prompt (`07-security.md`).
- **No citations.** Ungrounded output is unverifiable, and the user cannot tell
  a hallucination from a fact.
- **Chunking that severs context.** Splitting mid-table, mid-function, or
  mid-clause makes retrieval look broken when ingestion is the culprit.
- **Stale index.** No re-index on source change; the agent confidently cites
  deleted content.
- **Cross-tenant leakage in the vector store.** Embeddings ignore your
  authorisation model unless you filter explicitly — enforce tenancy in the
  query, never in post-processing.
- **Eval set drift.** A static golden set stops representing production while
  still reporting a comfortable, unchanging score.
- **Fabricated scores when the judge fails.** If the evaluator cannot run, the
  result is *unmeasured* — not a default. See `11-quality.md`.
