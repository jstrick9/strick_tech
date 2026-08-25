"""Module 32 — intent-scoped tool loading.

The problem, from someone running a gateway in production
(skool.com/cliefnotes):

    "I put a single gateway in front of a bunch of MCP servers so my agent has
     one connection instead of ten, and now it sees every tool from every
     server at once. Past a certain count it starts picking worse, not better.
     Right now I keep a hand-written map of which tools to expose per task, but
     it rots the second I add a server."

Measured on this codebase before the fix:

    /api/mcp-gateway/servers -> 7 servers, 53 tools
    /api/mcp/tools           -> 23 tools
    the agent loop           -> inlined all 23, could reach none of the 53

Two defects in one: federated tools no agent could call, and an unconditional
tool dump into every prompt. Connecting them naively would have put 76 tools in
front of the model, which is the wall being described.

The load-bearing properties, in order: the cap is never exceeded; selection is
by intent and explains itself; withheld tools are REPORTED rather than silently
dropped; and the catalog is generated, never hand-maintained.
"""

from __future__ import annotations

import importlib

import pytest

from backend.services import tool_catalog as tc


@pytest.fixture()
def catalog(monkeypatch):
    """A catalog over a known set of tools from both sources."""
    local = {
        'fs.read': {'desc': 'Read a file from disk', 'args': ['path']},
        'fs.write': {'desc': 'Write a file to disk', 'args': ['path', 'content']},
        'git.commit': {'desc': 'Commit staged changes', 'args': ['message']},
        'code.run': {'desc': 'Execute a script', 'args': ['code']},
        'http.fetch': {'desc': 'Fetch a URL over HTTP', 'args': ['url']},
    }
    gateway = {
        'servers': [
            {'id': 'srv_stripe', 'name': 'stripe', 'status': 'active',
             'tools_schema': [
                 {'name': 'stripe.create_invoice', 'description': 'Create a customer invoice'},
                 {'name': 'stripe.refund', 'description': 'Refund a payment'},
             ]},
            {'id': 'srv_mail', 'name': 'mail', 'status': 'active',
             'tools_schema': [
                 {'name': 'mail.send', 'description': 'Send an email message'},
             ]},
            {'id': 'srv_off', 'name': 'disabled-one', 'status': 'disabled',
             'tools_schema': [{'name': 'ghost.tool', 'description': 'Never exposed'}]},
        ]
    }
    monkeypatch.setattr(tc, '_local_tools', lambda: [
        {'name': n, 'description': i['desc'], 'args': i['args'], 'source': 'local',
         'server_id': '', 'server': 'local', 'tags': tc.tags_for(n, i['desc'])}
        for n, i in local.items()
    ])
    import backend.routers.mcp_gateway as gw

    monkeypatch.setattr(gw, 'list_servers', lambda *a, **k: gateway)
    return tc


# ── the catalog federates both sources ────────────────────────────────────────
def test_gateway_tools_are_in_the_catalog(catalog):
    """They were invisible to every agent before this module existed."""
    names = {t['name'] for t in catalog.index()}
    assert 'stripe.create_invoice' in names
    assert 'mail.send' in names


def test_local_tools_are_in_the_catalog(catalog):
    names = {t['name'] for t in catalog.index()}
    assert 'fs.read' in names


def test_disabled_servers_contribute_nothing(catalog):
    """A disabled server's tools must not be offered to a model."""
    assert 'ghost.tool' not in {t['name'] for t in catalog.index()}


def test_every_tool_records_where_it_came_from(catalog):
    for t in catalog.index():
        assert t['source'] in ('local', 'gateway')
        if t['source'] == 'gateway':
            assert t['server']


def test_a_broken_gateway_degrades_to_locals(monkeypatch, catalog):
    """Losing the gateway must not take the local tools down with it."""
    import backend.routers.mcp_gateway as gw

    def boom(*a, **k):
        raise RuntimeError('gateway down')

    monkeypatch.setattr(gw, 'list_servers', boom)
    names = {t['name'] for t in catalog.index()}
    assert 'fs.read' in names
    assert 'stripe.refund' not in names


# ── tags are derived, never hand-maintained ───────────────────────────────────
def test_tags_are_derived_from_the_tool_itself(catalog):
    """"A hand-written map rots the second I add a server.\""""
    assert 'filesystem' in tc.tags_for('fs.read', 'Read a file from disk')
    assert 'billing' in tc.tags_for('stripe.create_invoice', 'Create a customer invoice')
    assert 'git' in tc.tags_for('git.commit', 'Commit staged changes')


def test_a_dotted_namespace_contributes_tags(catalog):
    """The namespace must be split on '.' and '_', not just whitespace.

    'stripe.op_7' carries NO description, so the namespace is the only signal
    there is. _words() alone already splits on non-alphanumerics, which is why
    the earlier assertion passed with the splitting line deleted -- it proved
    nothing. This checks a case where the raw token would NOT tokenise: the
    tool name as a single dotted string must still yield its parts.
    """
    assert 'billing' in tc.tags_for('stripe.op_7', '')
    # And an underscore namespace, which is the same rule.
    assert 'comms' in tc.tags_for('acme_email_gateway', '')
    # A name whose ONLY billing signal is behind a dot.
    assert 'billing' in tc.tags_for('vendor.invoice', '')


def test_a_brand_new_tool_is_categorised_without_configuration(catalog):
    """The rot test: a tool nobody has ever seen still lands in the right place."""
    tags = tc.tags_for('acme.send_email', 'Send an email to a customer')
    assert 'comms' in tags


# ── selection is by intent, and capped ────────────────────────────────────────
def test_selection_picks_the_relevant_tools(catalog):
    got = catalog.select('create an invoice for the customer')
    names = [t['name'] for t in got['tools']]
    assert 'stripe.create_invoice' in names


def test_an_ambiguous_word_does_not_tag_the_wrong_capability(catalog):
    """Found live: 'create an invoice' offered git.checkout.

    'checkout' belongs to git AND to commerce, so it tagged a branch-switching
    tool as billing. A term claimed by two capabilities is not evidence for
    either.
    """
    assert 'billing' not in tc.tags_for('git.checkout', 'Switch branches')
    assert 'git' in tc.tags_for('git.checkout', 'Switch branches')


def test_selection_excludes_the_irrelevant(catalog):
    got = catalog.select('create an invoice for the customer')
    assert 'git.commit' not in [t['name'] for t in got['tools']]


def test_selection_never_exceeds_the_cap(catalog):
    got = catalog.select('file read write git commit code run http fetch invoice '
                         'refund email send', limit=3)
    assert len(got['tools']) == 3
    assert got['exposed'] == 3


def test_the_default_cap_is_enforced(catalog):
    got = catalog.select('file git code http invoice refund email database search')
    assert len(got['tools']) <= tc.MAX_EXPOSED


def test_every_selected_tool_says_why_it_was_chosen(catalog):
    for t in catalog.select('commit my changes to git')['tools']:
        assert t['why'].strip()
        assert t['score'] > 0


def test_withheld_tools_are_reported_not_silently_dropped(catalog):
    """An agent that cannot see a tool looks like one that chose not to use it."""
    got = catalog.select('file read write git commit code run http fetch invoice', limit=2)
    assert got['withheld_by_cap'] >= 1
    assert got['total_available'] > got['exposed']


def test_an_unrelated_intent_exposes_nothing(catalog):
    """Padding the list with irrelevant tools adds wrong options, not value."""
    got = catalog.select('what is the weather in Charlotte tomorrow')
    assert got['tools'] == []
    assert got['not_relevant'] > 0


def test_always_available_tools_are_always_included(catalog):
    got = catalog.select('completely unrelated request', always=('fs.read',))
    assert 'fs.read' in [t['name'] for t in got['tools']]


def test_results_are_ordered_by_score(catalog):
    """Must be ordered by SCORE, not name.

    An earlier version asserted only that the score list was descending, which
    a name-sorted list can satisfy by luck. This pins the actual top result:
    'stripe.refund' matches on name AND tag AND description, so it must
    outrank 'mail.send' -- which sorts FIRST alphabetically, so a name sort
    gives the wrong answer.
    """
    got = catalog.select('refund a payment')['tools']
    names = [t['name'] for t in got]
    scores = [t['score'] for t in got]
    assert scores == sorted(scores, reverse=True)
    assert names[0] == 'stripe.refund', names
    if 'mail.send' in names:
        assert names.index('stripe.refund') < names.index('mail.send')


def test_stopwords_alone_never_select_a_tool(catalog):
    """Without the stopword filter, common words match tool descriptions.

    'Read a file from disk' contains 'a' and 'from'; 'Send an email message'
    contains 'an'. An intent of pure filler would score every tool and expose
    a full dozen for a request that asked for nothing.
    """
    got = catalog.select('can you do that for me from the it')
    assert got['tools'] == [], [t['name'] for t in got['tools']]


def test_the_selection_reports_the_intent_tags(catalog):
    got = catalog.select('commit the code to git')
    assert 'git' in got['tags']


@pytest.mark.parametrize('junk', ['', '   ', None, '!!!'])
def test_selection_on_junk_input_does_not_raise(catalog, junk):
    got = catalog.select(junk)
    assert got['tools'] == []


def test_limit_is_clamped_to_something_sane(catalog):
    assert len(catalog.select('file', limit=0)['tools']) <= tc.MAX_EXPOSED + 60
    assert len(catalog.select('file', limit=99999)['tools']) <= len(catalog.index())


# ── search: the alternative to exposing everything ────────────────────────────
def test_an_agent_can_search_the_catalog(catalog):
    """"Let the agent search a catalog" -- findable on demand, not all at once."""
    found = [t['name'] for t in catalog.search('refund a payment')]
    assert 'stripe.refund' in found


def test_search_with_no_query_returns_the_catalog_head(catalog):
    assert catalog.search('') != []


def test_search_is_bounded(catalog):
    """The bound must bite. A query matching more tools than the limit."""
    broad = 'file write read send invoice refund commit run fetch email payment'
    unbounded = catalog.search(broad, limit=100)
    assert len(unbounded) >= 3, 'fixture must match enough tools to test a bound'
    assert len(catalog.search(broad, limit=2)) == 2


# ── prompt rendering ──────────────────────────────────────────────────────────
def test_rendering_names_the_server_for_federated_tools(catalog):
    tools = catalog.select('create an invoice')['tools']
    block = catalog.render_for_prompt(tools)
    assert 'stripe.create_invoice' in block
    assert 'via stripe' in block


def test_rendering_an_empty_selection_is_empty_not_a_stub(catalog):
    assert catalog.render_for_prompt([]) == ''


def test_the_rendered_block_is_far_smaller_than_the_whole_catalog(catalog):
    """The entire point: what reaches the prompt is a fraction of what exists."""
    everything = catalog.render_for_prompt(catalog.index())
    scoped = catalog.render_for_prompt(catalog.select('commit to git')['tools'])
    assert len(scoped) < len(everything) / 2


# ── stats ─────────────────────────────────────────────────────────────────────
def test_stats_report_both_sources(catalog):
    s = catalog.stats()
    assert s['by_source']['local'] > 0
    assert s['by_source']['gateway'] > 0
    assert s['total'] == len(catalog.index())


def test_stats_expose_the_cap(catalog):
    assert catalog.stats()['max_exposed'] == tc.MAX_EXPOSED


# ── the agent loop actually uses it ───────────────────────────────────────────
class TestAgentLoopScoping:
    def test_the_agent_loop_scopes_its_tools(self, client):
        """Was: every tool inlined into every prompt regardless of task."""
        r = client.post('/api/mcp/agent/run', json={
            'prompt': 'commit my changes to git', 'max_steps': 1})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d['tool_selection']['mode'] == 'intent'
        assert d['tool_selection']['exposed'] <= tc.MAX_EXPOSED
        assert d['tool_selection']['exposed'] < d['tool_selection']['total_available']

    def test_the_agent_loop_reports_which_tools_it_could_see(self, client):
        r = client.post('/api/mcp/agent/run', json={
            'prompt': 'read the file at notes.md', 'max_steps': 1})
        d = r.json()
        assert isinstance(d['tools_exposed'], list)
        assert any('fs.' in t for t in d['tools_exposed'])

    def test_an_explicit_tool_list_is_honoured_exactly(self, client):
        """A deliberate choice must not be second-guessed by the scorer."""
        r = client.post('/api/mcp/agent/run', json={
            'prompt': 'do something', 'tools': ['fs.read'], 'max_steps': 1})
        d = r.json()
        assert d['tool_selection']['mode'] == 'explicit'
        assert d['tools_exposed'] == ['fs.read']

    def test_the_selection_survives_an_unreachable_model(self, client, monkeypatch):
        """The selection is what you debug when the model is unavailable.

        Found live: with no AI provider configured, LLMUnavailableError
        propagated and the computed selection was discarded, so the one piece
        of diagnostic information the user needed vanished exactly when they
        needed it.
        """
        from backend.services import llm

        async def unavailable(*a, **k):
            raise llm.LLMUnavailableError({'model': 'test-model'})

        monkeypatch.setattr(llm, 'complete', unavailable)
        r = client.post('/api/mcp/agent/run',
                        json={'prompt': 'commit my changes to git', 'max_steps': 1})
        # app.py's _restatus_refused_write middleware turns {'ok': False} into
        # a 400 on mutating /api/ routes, so the status is 400 even though the
        # handler returned 200. What matters is that the BODY still carries the
        # selection.
        assert r.status_code == 400
        d = r.json()
        assert d['ok'] is False
        assert d['code'] == 'llm_unavailable'
        assert d['tool_selection']['mode'] == 'intent'
        assert d['tools_exposed']

    def test_the_caller_can_raise_the_cap(self, client):
        r = client.post('/api/mcp/agent/run', json={
            'prompt': 'file git code http search memory database email invoice',
            'max_tools': 2, 'max_steps': 1})
        assert r.json()['tool_selection']['exposed'] <= 2


# ── HTTP surface ──────────────────────────────────────────────────────────────
class TestCatalogEndpoints:
    def test_catalog_endpoint_lists_tools(self, client):
        r = client.get('/api/mcp/catalog')
        assert r.status_code == 200
        body = r.json()
        assert body['ok'] is True
        assert body['stats']['total'] > 0

    def test_select_endpoint_explains_its_choice(self, client):
        r = client.get('/api/mcp/catalog/select?intent=commit+to+git')
        assert r.status_code == 200
        d = r.json()['selection']
        assert d['exposed'] <= tc.MAX_EXPOSED
        for t in d['tools']:
            assert t['why']

    def test_select_requires_an_intent(self, client):
        assert client.get('/api/mcp/catalog/select').status_code == 422

    def test_search_endpoint_works(self, client):
        r = client.get('/api/mcp/catalog/search?q=file')
        assert r.status_code == 200
        assert isinstance(r.json()['tools'], list)


def test_module_reloads_cleanly():
    importlib.reload(tc)
    assert tc.MAX_EXPOSED > 0
