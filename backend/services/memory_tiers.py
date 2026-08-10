"""Memory tiering, provenance, and hybrid retrieval fusion.

Closes gaps #1, #2, #3 and #7 from docs/architecture/AGENTIC-OS-RESEARCH.md.

WHY TIERS
The `memory` table is flat: source, content, tags. The industry-standard
taxonomy that every production system converged on by 2026 separates memory by
what it is FOR, because the tiers have different retrieval and retention rules:

    working     current task scratchpad        ephemeral
    episodic    events WITH OUTCOMES           the learning substrate
    semantic    facts, entities, relations     the knowledge substrate
    procedural  how-to, learned strategies     the improvement substrate

The load-bearing one is episodic, and specifically the OUTCOME. An agent that
records "I tried X" learns nothing. An agent that records "I tried X and it
failed because Y" can avoid X. That single field is the difference between a
log and a memory:

    event -> extract -> find related procedure -> evolve it with the fix
          -> next retrieval includes the fix

WHY PROVENANCE
Memory poisoning is the failure mode unique to episodic memory: a poisoned
entry alters the agent's FUTURE retrieval strategy and tool preference, and
because the corruption is per-user it is far harder to detect than corpus
poisoning. Every write therefore records who wrote it, how it was obtained, and
how much to trust it -- so a bad entry can be found and revoked rather than
quietly steering the agent forever.

WHY RRF
`hybrid_search()` merged vector and FTS results by assigning every FTS hit a
hardcoded score of 0.5 and sorting on a scale the two retrievers do not share.
Demonstrated before this module existed:

    vector: id1=0.91, id2=0.62, id3=0.55      fts (ranked): id7, id8, id9
    merged order: [1, 2, 3, 7, 8, 9]

The single best keyword match ranks below the second-best vector match and ties
with the worst keyword match, because all three FTS hits score 0.5. FTS rank
order is discarded entirely, and with a small limit the best keyword hit can be
dropped from the results altogether.

Reciprocal Rank Fusion combines by RANK, which is the only thing the two
retrievers agree on:

    RRF(d) = sum over retrievers of 1 / (k + rank(d))    with k = 60

    fused order: [1, 7, 2, 8, 3, 9]

Each retriever's top hit surfaces. k=60 is the constant from the original
Cormack et al. work and is what most production stacks use: large enough that
rank-1 and rank-2 are not wildly different, small enough that deep results
still fade.
"""

from __future__ import annotations

import contextlib
import logging
import re
import sqlite3
import time
from typing import Any

# The four tiers. `working` is included for completeness but is not persisted
# by default -- a scratchpad that outlives its task is just noise.
TIERS = ('working', 'episodic', 'semantic', 'procedural')
DEFAULT_TIER = 'semantic'

# Episodic outcomes. `pending` matters: an action whose result is not yet known
# must not be recorded as a success.
OUTCOMES = ('success', 'failure', 'partial', 'pending', 'unknown')
DEFAULT_OUTCOME = 'unknown'

# How a memory was obtained. Used to decide how much to trust it and to make
# a poisoned batch findable.
ORIGINS = ('user', 'agent', 'tool', 'import', 'system', 'inference')
DEFAULT_ORIGIN = 'system'

# The RRF constant from Cormack et al.
RRF_K = 60

_log = logging.getLogger('agentic.memory_tiers')


def ensure_schema(con: sqlite3.Connection) -> None:
    """Add tiering and provenance columns to `memory`.

    Strictly additive with defaults, because ~30 call sites across 12 routers
    already write to this table through memory_add(). A migration that
    required them all to change at once would be a migration nobody could
    land safely.
    """
    cols = {r[1] for r in con.execute('PRAGMA table_info(memory)').fetchall()}
    add = {
        'tier': f"TEXT DEFAULT '{DEFAULT_TIER}'",
        'outcome': "TEXT DEFAULT ''",
        'origin': f"TEXT DEFAULT '{DEFAULT_ORIGIN}'",
        'actor': "TEXT DEFAULT ''",
        'confidence': 'REAL DEFAULT 1.0',
        'derived_from': "TEXT DEFAULT ''",
        'revoked_at': 'TEXT DEFAULT NULL',
        'use_count': 'INTEGER DEFAULT 0',
    }
    for name, decl in add.items():
        if name not in cols:
            with contextlib.suppress(sqlite3.Error):
                con.execute(f'ALTER TABLE memory ADD COLUMN {name} {decl}')
    with contextlib.suppress(sqlite3.Error):
        con.execute('CREATE INDEX IF NOT EXISTS idx_memory_tier ON memory(tier)')
        con.execute('CREATE INDEX IF NOT EXISTS idx_memory_outcome ON memory(outcome)')


def normalise_tier(value: Any) -> str:
    v = str(value or '').strip().lower()
    return v if v in TIERS else DEFAULT_TIER


def normalise_outcome(value: Any, tier: str = '') -> str:
    """Outcomes belong to episodic memory.

    A 'success' on a semantic fact is meaningless, and letting it through
    would make outcome filtering unreliable for the tier that depends on it.
    """
    v = str(value or '').strip().lower()
    if tier and tier != 'episodic':
        return ''
    return v if v in OUTCOMES else (DEFAULT_OUTCOME if tier == 'episodic' else '')


def normalise_origin(value: Any) -> str:
    v = str(value or '').strip().lower()
    return v if v in ORIGINS else DEFAULT_ORIGIN


def normalise_confidence(value: Any) -> float:
    try:
        c = float(value)
    except (TypeError, ValueError):
        return 1.0
    return max(0.0, min(1.0, c))


def provenance_for(
    tier: Any = None,
    outcome: Any = None,
    origin: Any = None,
    actor: Any = None,
    confidence: Any = None,
    derived_from: Any = None,
) -> dict[str, Any]:
    """Build a validated provenance record for a memory write."""
    t = normalise_tier(tier)
    return {
        'tier': t,
        'outcome': normalise_outcome(outcome, t),
        'origin': normalise_origin(origin),
        'actor': str(actor or '')[:120],
        'confidence': normalise_confidence(confidence),
        'derived_from': str(derived_from or '')[:200],
    }


# ── Reciprocal Rank Fusion ────────────────────────────────────────────────────
def rrf_fuse(
    ranked_lists: list[list[dict]],
    key: str = 'id',
    k: int = RRF_K,
    weights: list[float] | None = None,
) -> list[dict]:
    """Fuse ranked result lists by rank rather than by score.

    Scores from a vector index and from FTS5 are not on a shared scale, so
    comparing them directly is meaningless -- which is why the previous
    implementation had to invent a constant 0.5 for every FTS hit, discarding
    that retriever's ordering entirely.

    Rank is the one thing both retrievers agree on. Each document scores
    sum(1 / (k + rank)) across the lists it appears in, so appearing in
    several lists is worth more than ranking highly in one.
    """
    if k < 1:
        k = RRF_K
    scores: dict[Any, float] = {}
    seen: dict[Any, dict] = {}
    contributions: dict[Any, list[str]] = {}

    for i, lst in enumerate(ranked_lists or []):
        w = 1.0
        if weights and i < len(weights):
            try:
                w = max(0.0, float(weights[i]))
            except (TypeError, ValueError):
                w = 1.0
        for rank, item in enumerate(lst or [], start=1):
            if not isinstance(item, dict) or key not in item:
                continue
            ident = item[key]
            scores[ident] = scores.get(ident, 0.0) + w * (1.0 / (k + rank))
            contributions.setdefault(ident, []).append(item.get('source_type') or f'list{i}')
            # Keep the richest record we have seen for this document.
            if ident not in seen or len(str(item)) > len(str(seen[ident])):
                seen[ident] = item

    out = []
    for ident, score in sorted(scores.items(), key=lambda kv: (-kv[1], str(kv[0]))):
        rec = dict(seen[ident])
        rec['rrf_score'] = round(score, 6)
        rec['retrievers'] = sorted(set(contributions[ident]))
        out.append(rec)
    return out


# ── Reranking ─────────────────────────────────────────────────────────────────
_WORD = re.compile(r'[A-Za-z0-9_]+')


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _WORD.findall(text or '')]


def rerank(
    query: str,
    results: list[dict],
    limit: int = 20,
    field: str = 'content',
    recency_weight: float = 0.15,
) -> list[dict]:
    """Rerank fused results against the query.

    A cross-encoder is the 2026 production default, but it needs a model this
    platform cannot assume is present. This is a lexical-overlap reranker with
    a mild recency term: it runs everywhere, costs nothing, and is a real
    improvement over returning fusion order untouched. It reports its own
    method so a caller can tell what it got, and so a cross-encoder can be
    swapped in later without changing the contract.
    """
    q = set(_tokens(query))
    if not q or not results:
        return (results or [])[:limit]

    now = time.time()
    scored = []
    for r in results:
        toks = _tokens(str(r.get(field, '')))
        if not toks:
            overlap = 0.0
        else:
            uniq = set(toks)
            # Coverage of the QUERY matters more than coverage of the document:
            # a long document should not be penalised for being long.
            overlap = len(q & uniq) / len(q)
            # A phrase match is stronger evidence than scattered tokens.
            if len(q) > 1 and ' '.join(sorted(q)) in ' '.join(sorted(uniq)):
                overlap = min(1.0, overlap + 0.1)

        recency = 0.0
        ts = r.get('created_at')
        if ts:
            try:
                age_days = max(0.0, (now - _to_epoch(ts)) / 86400.0)
                recency = 1.0 / (1.0 + age_days / 30.0)
            except (TypeError, ValueError):
                recency = 0.0

        base = float(r.get('rrf_score', 0.0))
        conf = normalise_confidence(r.get('confidence', 1.0))
        final = (base * 10.0) + overlap + (recency_weight * recency)
        final *= conf  # a low-confidence memory should not outrank a solid one

        rec = dict(r)
        rec['rerank_score'] = round(final, 6)
        rec['rerank_overlap'] = round(overlap, 4)
        rec['rerank_method'] = 'lexical-overlap+recency'
        scored.append(rec)

    scored.sort(key=lambda x: -x['rerank_score'])
    return scored[:limit]


def _to_epoch(ts: Any) -> float:
    if isinstance(ts, (int, float)):
        return float(ts)
    s = str(ts).strip().replace('T', ' ').replace('Z', '')
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d'):
        try:
            return time.mktime(time.strptime(s[:26], fmt))
        except (ValueError, OverflowError):
            continue
    raise ValueError(f'unparseable timestamp: {ts!r}')


# ── Maximal Marginal Relevance ────────────────────────────────────────────────
def mmr_diversify(results: list[dict], limit: int = 10, lambda_: float = 0.7,
                  field: str = 'content') -> list[dict]:
    """Drop near-duplicates from a result set.

    Retrieval over a memory store returns the same fact phrased five ways far
    more often than a document corpus does, because agents write the same
    observation repeatedly. Five copies of one fact crowd out four other
    facts, so context is spent on redundancy.
    """
    if not results:
        return []
    pool = list(results)
    chosen: list[dict] = [pool.pop(0)]
    chosen_tokens = [set(_tokens(str(chosen[0].get(field, ''))))]

    while pool and len(chosen) < limit:
        best_i, best_score = 0, -1e9
        for i, cand in enumerate(pool):
            ct = set(_tokens(str(cand.get(field, ''))))
            relevance = float(cand.get('rerank_score', cand.get('rrf_score', 0.0)))
            redundancy = 0.0
            for st in chosen_tokens:
                if ct or st:
                    j = len(ct & st) / max(1, len(ct | st))
                    redundancy = max(redundancy, j)
            score = lambda_ * relevance - (1 - lambda_) * redundancy * 10.0
            if score > best_score:
                best_i, best_score = i, score
        pick = pool.pop(best_i)
        chosen.append(pick)
        chosen_tokens.append(set(_tokens(str(pick.get(field, '')))))
    return chosen


def retrieval_report(
    query: str,
    fused: list[dict],
    returned: list[dict],
    retrievers: list[str],
) -> dict[str, Any]:
    """Describe what retrieval actually did.

    The recurring defect class across this review has been confident reporting
    of unverified work. A retrieval pipeline that silently returns fewer, or
    worse, results than the caller assumes is the same failure, so the basis is
    stated rather than implied.
    """
    return {
        'query': query,
        'retrievers': retrievers,
        'candidates': len(fused),
        'returned': len(returned),
        'fusion': f'rrf(k={RRF_K})',
        'rerank': returned[0].get('rerank_method') if returned else None,
        'truncated': len(returned) < len(fused),
    }


# ── Graph expansion ───────────────────────────────────────────────────────────
def graph_expand(query: str, limit: int = 10, depth: int = 1) -> list[dict]:
    """Retrieve via the knowledge graph, as a third ranked list for fusion.

    `knowledge_graph.py` has entities, typed relations and BFS traversal, and
    before this it was referenced ZERO times by any retrieval path -- a graph
    nothing queries is a graph that cannot help. Graph retrieval is what
    answers the global and multi-hop questions vector similarity cannot: "who
    works on the project that Acme owns" is two hops, not a nearest neighbour.

    Entities matching the query seed the walk; one hop out brings in their
    neighbours, ranked behind the direct hits because a neighbour is weaker
    evidence than a match. Returns a RANKED list, which is all RRF needs.
    """
    query = (query or '').strip()
    if not query:
        return []
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        limit = 10

    terms = [t for t in _tokens(query) if len(t) > 2][:6]
    if not terms:
        return []

    from .memory_db import get_conn

    out: list[dict] = []
    seen: set[str] = set()
    con = get_conn()
    try:
        # Seeds: entities whose name or description mentions a query term.
        where = ' OR '.join(['LOWER(name) LIKE ? OR LOWER(description) LIKE ?'] * len(terms))
        params: list[Any] = []
        for t in terms:
            params.extend([f'%{t}%', f'%{t}%'])
        rows = con.execute(
            f'SELECT id, name, type, description, confidence FROM kg_entities '
            f'WHERE {where} ORDER BY confidence DESC LIMIT ?',
            (*params, limit),
        ).fetchall()

        for r in rows:
            d = dict(r)
            if d['id'] in seen:
                continue
            seen.add(d['id'])  # bare id: `seen` holds one representation only
            out.append({
                'id': f"kg:{d['id']}",
                'content': f"{d['name']} ({d['type']}): {d['description'] or ''}".strip(),
                'source': 'knowledge-graph',
                'tags': d['type'],
                'confidence': d.get('confidence', 1.0),
                'source_type': 'graph',
                'graph_hop': 0,
            })

        # One hop out. Neighbours rank behind direct matches because being
        # adjacent to a match is weaker evidence than being one.
        if depth > 0 and seen:
            ids = sorted(seen)
            marks = ','.join('?' * len(ids))
            neighbours = con.execute(
                f'SELECT e.id, e.name, e.type, e.description, e.confidence, r.relation '
                f'FROM kg_relations r JOIN kg_entities e ON e.id = r.to_id '
                f'WHERE r.from_id IN ({marks}) ORDER BY r.confidence DESC LIMIT ?',
                (*ids, limit),
            ).fetchall()
            for r in neighbours:
                d = dict(r)
                if d['id'] in seen:
                    continue
                seen.add(d['id'])
                out.append({
                    'id': f"kg:{d['id']}",
                    'content': f"{d['name']} ({d['type']}): {d['description'] or ''}".strip(),
                    'source': f"knowledge-graph via {d['relation']}",
                    'tags': d['type'],
                    'confidence': d.get('confidence', 1.0),
                    'source_type': 'graph',
                    'graph_hop': 1,
                })
    except sqlite3.Error as ex:
        # A graph that is empty or mid-migration must not break retrieval --
        # the other retrievers still have work to do. But it is scoped to
        # sqlite errors on purpose: a bare `except Exception` here hid an
        # IndexError and made graph expansion silently return seeds only,
        # which looked exactly like working.
        _log.debug('graph_expand: %s', ex)
        return out
    finally:
        con.close()
    return out[:limit]
