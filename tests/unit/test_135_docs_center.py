"""Module review 2: Docs & Help (`docs`).

Risk rank 2 of 68 (score 35): 1,801 lines, 15 endpoints.

WHAT WAS VERIFIED AS ALREADY CORRECT
────────────────────────────────────
Worth stating, because most of this module is genuinely good:

  * All 7 endpoints answer 200 on an empty account.
  * 67 of 68 panes have a feature doc. The one gap (`steering`) is the
    deliberately-retired pane that redirects to `hierarchy`, and it is still
    covered by an FAQ entry.
  * Contextual help resolves to the RIGHT doc for all 68 panes — probed one
    by one, not sampled.
  * An unknown pane id degrades cleanly rather than 500ing.

THE DEFECT: SEARCH COULD NOT ANSWER A QUESTION
──────────────────────────────────────────────
Every match was a whole-phrase substring test (`if qlow in title`), so a query
only matched if it appeared VERBATIM. Measured live:

    'agent'                    -> 20 results
    'how do I add an API key'  ->  0 results   <- the FAQ answers exactly this
    'keyboard shortcuts'       ->  0 results   <- there is a whole endpoint

A help search that returns nothing for a question asked in words is worse than
no search: the user concludes the product has no answer when it is right
there. And this is the *most likely first interaction* with Docs — people
search help because they are already stuck.

Fixed by scoring per TOKEN, with a bonus when the full phrase also appears so
exact matches still rank first. Stop-words are dropped so
"how do I add an API key" scores on {add, api, key}. No stemmer, no index, no
dependency — the corpus is a few hundred short strings in memory.

After: that query returns 21 matches, top hits **Secrets Vault** and
**"Do I need an OpenRouter API key?"**. Single-word rankings are unchanged and
nonsense still returns 0.

TWO UI DEFECTS FOUND IN THE SAME PASS
─────────────────────────────────────
  * SILENT TRUNCATION. The API returns `count` (total) and `shown` (capped at
    20); the UI printed `results.length` and labelled it "N results". A query
    matching 21 rendered "20 results" with nothing saying one was withheld —
    recurring pattern #9. It matters *more* after the search fix, because
    token matching returns far more hits and the cap is now reachable at all.
  * A ONE-CHARACTER QUERY DID NOTHING. `if (q.length < 2) return;` left the
    previous view on screen — indistinguishable from a broken search.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
ROUTER = (REPO / 'backend' / 'routers' / 'docs_center.py').read_text(encoding='utf-8')
JS = (REPO / 'frontend' / 'js' / '04-workflow-specs.js').read_text(encoding='utf-8')
CSS = (REPO / 'frontend' / 'styles-redesign.css').read_text(encoding='utf-8')


def _search(query: str, limit: int = 20) -> dict:
    """Call the real handler, not a reimplementation of it."""
    import sys
    sys.path.insert(0, str(REPO))
    from backend.routers.docs_center import search_docs
    return search_docs(q=query, limit=limit)


# ──────────────────────────────────────────────────────────────────────
#  Search: natural language
# ──────────────────────────────────────────────────────────────────────
def test_a_question_finds_its_answer():
    """The exact query that returned zero before the fix."""
    out = _search('how do I add an API key')
    assert out['count'] > 0, 'a question asked in words must find something'
    titles = ' '.join(r['title'].lower() for r in out['results'][:5])
    assert 'key' in titles or 'vault' in titles, (
        f'top results are not about API keys: {titles[:120]}')


def test_keyboard_shortcuts_query_finds_shortcuts():
    """No individual shortcut DESCRIPTION contains the word "shortcut", so a
    naive token match still returns nothing — the thing the user asked for is
    the list itself."""
    out = _search('keyboard shortcuts')
    assert out['count'] > 0
    assert any(r['type'] == 'shortcut' for r in out['results'])


def test_multi_word_queries_generally_work():
    for query in ('set up openrouter', 'undo a change', 'create an agent'):
        assert _search(query)['count'] > 0, f'{query!r} found nothing'


def test_single_word_search_still_works():
    """The fix must not regress the queries that already worked."""
    for query, expected in (('kanban', 'task'), ('rag', 'rag'),
                            ('swarm', 'swarm'), ('deploy', 'deploy')):
        out = _search(query)
        assert out['count'] > 0, f'{query!r} regressed to zero'
        assert expected in out['results'][0]['title'].lower(), (
            f'{query!r} now ranks {out["results"][0]["title"]!r} first')


def test_nonsense_still_returns_nothing():
    """Token matching must not turn every query into a match."""
    assert _search('xyzzy-nonexistent-qqq')['count'] == 0


def test_an_empty_query_returns_nothing():
    assert _search('')['count'] == 0
    assert _search('   ')['count'] == 0


def test_a_query_of_only_stopwords_still_searches():
    """Dropping every word would score zero — indistinguishable from "no
    answer exists". The stop-list is ignored when it would empty the query."""
    assert _search('how do I')['count'] > 0


def test_stopwords_are_actually_dropped():
    """Otherwise a long question is diluted by words that match nothing."""
    assert '_SEARCH_STOPWORDS' in ROUTER
    assert "'how'" in ROUTER and "'the'" in ROUTER


def test_exact_phrase_still_outranks_a_loose_token_match():
    """Token scoring must not flatten relevance."""
    out = _search('Task Board')
    assert out['count'] > 0
    assert 'task' in out['results'][0]['title'].lower()


def test_the_result_cap_is_reported():
    """`count` is the total matched; `shown` is what was returned."""
    out = _search('how do I add an API key', limit=5)
    assert out['shown'] == 5
    assert out['count'] > out['shown'], (
        'this query should match more than the cap')


# ──────────────────────────────────────────────────────────────────────
#  Search UI
# ──────────────────────────────────────────────────────────────────────
def test_the_ui_reports_the_total_not_the_shown_count():
    """A query matching 21 rendered "20 results" with nothing saying one was
    withheld — an unbounded list and a capped one looked identical."""
    block = JS[JS.index('async function docsSearch('):][:3000]
    assert 'd?.count' in block or 'd.count' in block, (
        'the UI must read the server total, not results.length')
    assert 'Showing the top' in block


def test_a_one_character_query_explains_itself():
    """It used to `return` silently, leaving the previous view on screen."""
    block = JS[JS.index('async function docsSearch('):][:1500]
    assert 'at least two' in block


def test_the_empty_state_suggests_what_to_try():
    """A user searching help is already stuck; one grey line is not help."""
    assert 'docs-search-empty' in JS
    assert 'docs-search-empty' in CSS, 'the empty state is unstyled'
    assert 'docs-search-hint' in CSS


def test_the_empty_state_does_not_also_print_zero_results():
    """"0 results for X" above "No matches for X" is the same sentence twice."""
    block = JS[JS.index('async function docsSearch('):][:3000]
    assert 'results.length === 0 ?' in block


# ──────────────────────────────────────────────────────────────────────
#  Coverage guards
# ──────────────────────────────────────────────────────────────────────
def test_every_pane_has_a_feature_doc_or_a_documented_exemption():
    """Probed live during the review: 67 of 68. The exemption is `steering`,
    the retired pane that redirects to `hierarchy` and is covered by an FAQ.
    """
    import sys
    sys.path.insert(0, str(REPO))
    from backend.routers.docs_center import FEATURE_DOCS

    registry = (REPO / 'frontend' / 'js' / '00-pane-registry.js').read_text(
        encoding='utf-8')
    panes = set(re.findall(r"^\s*'([a-z0-9-]+)':", registry, re.M))
    undocumented = panes - set(FEATURE_DOCS) - {'steering'}
    assert not undocumented, (
        f'panes with no feature doc: {sorted(undocumented)}')


def test_contextual_help_returns_the_matching_doc():
    """A wrong mapping here is invisible: the panel renders, just with the
    wrong page."""
    import sys
    sys.path.insert(0, str(REPO))
    from backend.routers.docs_center import FEATURE_DOCS, contextual_help

    # Derived from the registry rather than hardcoded: my first version listed
    # 'agents', which is not a pane id, so the test failed on its own typo
    # instead of on the product. Probing every real pane is also stronger --
    # the review found the one gap ('steering') by doing exactly this.
    registry = (REPO / 'frontend' / 'js' / '00-pane-registry.js').read_text(
        encoding='utf-8')
    panes = sorted(set(re.findall(r"^\s*'([a-z0-9-]+)':", registry, re.M)))
    wrong = []
    for pane in panes:
        if pane not in FEATURE_DOCS:
            continue          # covered by the coverage test above
        out = contextual_help(pane)
        if not out.get('doc') or out['doc'].get('id') != pane:
            wrong.append(pane)
    assert not wrong, f'contextual help returns the wrong doc for: {wrong}'
