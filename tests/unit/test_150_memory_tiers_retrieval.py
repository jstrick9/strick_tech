"""Memory tiering, provenance, and hybrid retrieval fusion.

Closes gaps #1, #2, #3, #7 from docs/architecture/AGENTIC-OS-RESEARCH.md.

THE FUSION DEFECT, reproduced before the fix existed:

    hybrid_search() merged vector and FTS results into one dict and sorted by
    score -- but assigned every FTS hit a hardcoded 0.5, because the two
    retrievers do not share a scale.

        vector: id1=0.91, id2=0.62, id3=0.55   fts (ranked): id7, id8, id9
        merged order: [1, 2, 3, 7, 8, 9]

    The best keyword match ranks below the second-best vector match and ties
    with the worst keyword match. FTS rank order is discarded entirely, and a
    small limit drops the best keyword hit altogether.

    RRF fuses by rank:  [1, 7, 2, 8, 3, 9]

THE TIERING GAP: `memory` was flat, so an agent could record "I tried X" but
not "I tried X and it failed" -- the outcome field is the difference between a
log and something an agent can learn from.

THE POISONING GAP: no provenance, so a bad memory could steer future retrieval
forever with no way to find or revoke it.
"""

from __future__ import annotations

import pytest

from backend.services import memory_tiers as mt


# ── RRF ───────────────────────────────────────────────────────────────────────
def test_rrf_interleaves_by_rank_not_by_score():
    """The exact scenario the old merge got wrong."""
    vector = [{'id': 1}, {'id': 2}, {'id': 3}]
    fts = [{'id': 7}, {'id': 8}, {'id': 9}]
    order = [r['id'] for r in mt.rrf_fuse([vector, fts])]
    assert order == [1, 7, 2, 8, 3, 9]


def test_rrf_surfaces_each_retrievers_top_hit_early():
    vector = [{'id': 1}, {'id': 2}, {'id': 3}, {'id': 4}, {'id': 5}]
    fts = [{'id': 90}, {'id': 91}]
    top2 = [r['id'] for r in mt.rrf_fuse([vector, fts])][:2]
    assert 1 in top2 and 90 in top2


def test_appearing_in_both_lists_outranks_appearing_in_one():
    """Agreement between retrievers is the strongest signal RRF has."""
    a = [{'id': 'x'}, {'id': 'solo'}]
    b = [{'id': 'other'}, {'id': 'x'}]
    assert [r['id'] for r in mt.rrf_fuse([a, b])][0] == 'x'


def test_rrf_records_which_retrievers_contributed():
    a = [{'id': 1, 'source_type': 'vector'}]
    b = [{'id': 1, 'source_type': 'fts5'}]
    assert mt.rrf_fuse([a, b])[0]['retrievers'] == ['fts5', 'vector']


def test_rrf_score_is_reported():
    out = mt.rrf_fuse([[{'id': 1}]])
    assert out[0]['rrf_score'] == round(1 / (mt.RRF_K + 1), 6)


def test_rrf_handles_empty_and_missing_lists():
    assert mt.rrf_fuse([]) == []
    assert mt.rrf_fuse([[], []]) == []
    assert [r['id'] for r in mt.rrf_fuse([[{'id': 1}], []])] == [1]


def test_rrf_skips_malformed_items():
    out = mt.rrf_fuse([[{'id': 1}, {'no_id': True}, 'garbage']])
    assert [r['id'] for r in out] == [1]


def test_rrf_weights_shift_the_balance():
    a = [{'id': 'a'}]
    b = [{'id': 'b'}]
    assert [r['id'] for r in mt.rrf_fuse([a, b], weights=[5.0, 1.0])][0] == 'a'
    assert [r['id'] for r in mt.rrf_fuse([a, b], weights=[1.0, 5.0])][0] == 'b'


def test_rrf_is_deterministic_on_ties():
    a = [{'id': 'b'}, {'id': 'a'}]
    assert [r['id'] for r in mt.rrf_fuse([a])] == ['b', 'a']


def test_invalid_k_falls_back_to_the_default():
    assert mt.rrf_fuse([[{'id': 1}]], k=0)[0]['rrf_score'] == round(1 / (mt.RRF_K + 1), 6)


# ── Reranking ─────────────────────────────────────────────────────────────────
def test_rerank_prefers_higher_query_coverage():
    results = [
        {'id': 1, 'content': 'ingress rules for nginx', 'rrf_score': 0.016},
        {'id': 2, 'content': 'kubernetes ingress controller guide', 'rrf_score': 0.016},
    ]
    assert mt.rerank('ingress controller', results)[0]['id'] == 2


def test_rerank_reports_its_method():
    out = mt.rerank('x', [{'id': 1, 'content': 'x', 'rrf_score': 0.1}])
    assert out[0]['rerank_method'] == 'lexical-overlap+recency'


def test_low_confidence_memory_is_demoted():
    """A doubtful memory must not outrank a solid one on equal relevance."""
    results = [
        {'id': 1, 'content': 'alpha beta', 'rrf_score': 0.016, 'confidence': 0.2},
        {'id': 2, 'content': 'alpha beta', 'rrf_score': 0.016, 'confidence': 1.0},
    ]
    assert mt.rerank('alpha beta', results)[0]['id'] == 2


def test_rerank_respects_the_limit():
    rs = [{'id': i, 'content': f'doc {i} alpha', 'rrf_score': 0.01} for i in range(20)]
    assert len(mt.rerank('alpha', rs, limit=5)) == 5


def test_rerank_without_a_query_returns_the_fusion_order():
    rs = [{'id': 1, 'content': 'a'}, {'id': 2, 'content': 'b'}]
    assert [r['id'] for r in mt.rerank('', rs)] == [1, 2]


def test_rerank_survives_an_unparseable_timestamp():
    rs = [{'id': 1, 'content': 'alpha', 'rrf_score': 0.1, 'created_at': 'not-a-date'}]
    assert mt.rerank('alpha', rs)[0]['id'] == 1


# ── MMR ───────────────────────────────────────────────────────────────────────
def test_mmr_drops_near_duplicates():
    """Agents write the same observation repeatedly; five copies of one fact
    crowd out four other facts."""
    rs = [
        {'id': 1, 'content': 'the deploy failed because the token expired', 'rerank_score': 1.0},
        {'id': 2, 'content': 'the deploy failed because the token expired', 'rerank_score': 0.99},
        {'id': 3, 'content': 'billing runs on the first of the month', 'rerank_score': 0.5},
    ]
    ids = [r['id'] for r in mt.mmr_diversify(rs, limit=2)]
    assert ids == [1, 3]


def test_mmr_keeps_the_top_result():
    rs = [{'id': 1, 'content': 'a', 'rerank_score': 1.0}, {'id': 2, 'content': 'b', 'rerank_score': 0.9}]
    assert mt.mmr_diversify(rs, limit=2)[0]['id'] == 1


def test_mmr_handles_empty_input():
    assert mt.mmr_diversify([]) == []


# ── Tiers ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize('given,expected', [
    ('episodic', 'episodic'), ('EPISODIC', 'episodic'), (' semantic ', 'semantic'),
    ('procedural', 'procedural'), ('working', 'working'),
    ('nonsense', 'semantic'), ('', 'semantic'), (None, 'semantic'),
])
def test_tier_normalisation(given, expected):
    assert mt.normalise_tier(given) == expected


def test_outcome_belongs_to_episodic_memory_only():
    """A 'success' on a semantic fact is meaningless and would make outcome
    filtering unreliable for the tier that depends on it."""
    assert mt.normalise_outcome('success', 'episodic') == 'success'
    assert mt.normalise_outcome('success', 'semantic') == ''
    assert mt.normalise_outcome('success', 'procedural') == ''


def test_episodic_without_an_outcome_is_unknown_not_success():
    """Absence of a result must never read as a good result."""
    assert mt.normalise_outcome('', 'episodic') == 'unknown'
    assert mt.normalise_outcome(None, 'episodic') == 'unknown'
    assert mt.normalise_outcome('garbage', 'episodic') == 'unknown'


def test_pending_is_a_real_outcome():
    assert mt.normalise_outcome('pending', 'episodic') == 'pending'


@pytest.mark.parametrize('given,expected', [
    ('agent', 'agent'), ('USER', 'user'), ('tool', 'tool'),
    ('nonsense', 'system'), ('', 'system'),
])
def test_origin_normalisation(given, expected):
    assert mt.normalise_origin(given) == expected


@pytest.mark.parametrize('given,expected', [
    (0.5, 0.5), (1.0, 1.0), (0.0, 0.0),
    (2.0, 1.0), (-1.0, 0.0), ('bad', 1.0), (None, 1.0),
])
def test_confidence_is_clamped(given, expected):
    assert mt.normalise_confidence(given) == expected


def test_provenance_record_is_complete():
    p = mt.provenance_for('episodic', 'failure', 'agent', 'builder', 0.8, 'mem:42')
    assert p == {
        'tier': 'episodic', 'outcome': 'failure', 'origin': 'agent',
        'actor': 'builder', 'confidence': 0.8, 'derived_from': 'mem:42',
    }


def test_provenance_defaults_are_safe():
    p = mt.provenance_for()
    assert p['tier'] == 'semantic'
    assert p['origin'] == 'system'
    assert p['confidence'] == 1.0


def test_actor_is_bounded():
    assert len(mt.provenance_for(actor='x' * 500)['actor']) == 120


# ── Reporting ─────────────────────────────────────────────────────────────────
def test_retrieval_report_states_the_basis():
    fused = [{'id': i} for i in range(10)]
    returned = mt.rerank('x', [{'id': 1, 'content': 'x', 'rrf_score': 0.1}], limit=1)
    rep = mt.retrieval_report('x', fused, returned, ['fts5'])
    assert rep['candidates'] == 10 and rep['returned'] == 1
    assert rep['truncated'] is True
    assert 'rrf' in rep['fusion']


# ── Integration with the live write/read path ─────────────────────────────────
def test_memory_add_persists_tier_and_provenance(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENTIC_TEST_DB', str(tmp_path / 't.db'))
    import backend.services.memory_db as mdb

    monkeypatch.setattr(mdb, '_TIER_COLUMNS_READY', False, raising=False)
    mdb.ensure_schema()
    mid = mdb.memory_add(
        'probe', 'the deploy failed because the token expired',
        tier='episodic', outcome='failure', origin='agent',
        actor='deployer', confidence=0.9,
    )
    con = mdb.get_conn()
    try:
        row = con.execute(
            'SELECT tier, outcome, origin, actor, confidence FROM memory WHERE id=?', (mid,)
        ).fetchone()
    finally:
        con.close()
    assert dict(row) == {
        'tier': 'episodic', 'outcome': 'failure', 'origin': 'agent',
        'actor': 'deployer', 'confidence': 0.9,
    }


def test_legacy_positional_calls_still_work(tmp_path, monkeypatch):
    """~30 call sites across 12 routers call this positionally."""
    monkeypatch.setenv('AGENTIC_TEST_DB', str(tmp_path / 't2.db'))
    import backend.services.memory_db as mdb

    monkeypatch.setattr(mdb, '_TIER_COLUMNS_READY', False, raising=False)
    mdb.ensure_schema()
    mid = mdb.memory_add('legacy', 'no provenance supplied', 'tag1')
    assert mid > 0
    con = mdb.get_conn()
    try:
        row = con.execute('SELECT tier, origin FROM memory WHERE id=?', (mid,)).fetchone()
    finally:
        con.close()
    assert row['tier'] == 'semantic' and row['origin'] == 'system'


def test_hybrid_search_no_longer_invents_a_constant_score():
    """The 0.5 was the tell: every FTS hit tied."""
    import inspect

    import backend.services.memory_db as mdb

    src = inspect.getsource(mdb.hybrid_search)
    body = '\n'.join(ln for ln in src.split('\n') if not ln.strip().startswith('#'))
    assert "'score': 0.5" not in body
    assert 'rrf_fuse' in body
    assert 'rerank' in body


def test_hybrid_search_ranks_the_better_match_first(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENTIC_TEST_DB', str(tmp_path / 't3.db'))
    import backend.services.memory_db as mdb

    monkeypatch.setattr(mdb, '_TIER_COLUMNS_READY', False, raising=False)
    mdb.ensure_schema()
    mdb.memory_add('doc', 'ingress rules for nginx')
    mdb.memory_add('doc', 'kubernetes ingress controller troubleshooting')
    mdb.memory_add('doc', 'unrelated note about billing')
    out = mdb.hybrid_search('ingress controller', limit=5)
    assert out, 'expected results'
    assert 'controller' in out[0]['content']
    assert all('billing' not in r['content'] for r in out)
