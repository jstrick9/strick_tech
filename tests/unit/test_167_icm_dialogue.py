"""Module 30 — dialogue → workspace extraction.

Build mode step 1: "The structure is already in how the person describes the
work -- don't impose a shape, surface theirs. Their pauses become stage
boundaries. Their 'I always check X before Y' become human gates. Their 'it
always has to sound like Z' becomes factory reference material."

The tests use descriptions in the register people actually type, not keyword
soup, because an extractor tuned against its own vocabulary list passes its
tests and fails every real user.

The guardrail matters as much as the extraction: the canon says "a workspace
for a thing done twice is scaffolding, not architecture", so the analyser has
to be willing to say no. A tool that only ever says yes produces empty folders.
"""

from __future__ import annotations

import pytest

from backend.services import icm_dialogue as dlg

# A realistic answer to "walk me through one run".
NEWSLETTER = (
    "Every week I put out a newsletter. First I go through the week's links "
    "and pull out the three or four worth writing about. Then I draft the "
    "issue in my own voice — it always has to sound conversational, never "
    "corporate. I always read it out loud and check the links before it goes "
    "out. Finally I schedule it in Buttondown for Tuesday morning."
)

CLIENT_WORK = (
    "I run a small consultancy. Each client gets their own folder with their "
    "brief, their contract and my notes from every call. When a new one signs "
    "I copy the same set of files and fill them in. I need to be able to look "
    "up what we agreed with any client quickly."
)

ONE_STEP = "I use AI to fix my spelling."


# ── form selection ────────────────────────────────────────────────────────────
def test_a_repeating_weekly_run_is_a_pipeline():
    f = dlg.detect_form(NEWSLETTER)
    assert f['form'] == 'pipeline'
    assert f['confident'] is True
    assert f['evidence']


def test_per_client_folders_are_a_record_library():
    """The unit is a record that accumulates, not a run that completes."""
    f = dlg.detect_form(CLIENT_WORK)
    assert f['form'] == 'record_library', f


def test_a_specific_unit_phrase_outranks_incidental_atmosphere():
    """Found live: "Each client gets their own folder ... and my notes from
    every call" was classified knowledge_bundle, because the incidental phrase
    "my notes" outweighed "each client" -- the actual repeating unit and the
    entire basis of form selection. Specificity now beats phrase length.
    """
    f = dlg.detect_form(
        'Each client gets their own folder with my notes from every call.')
    assert f['form'] == 'record_library', f['evidence']


def test_a_second_brain_is_a_knowledge_bundle():
    f = dlg.detect_form('I want a second brain for all my research notes.')
    assert f['form'] == 'knowledge_bundle'


def test_a_team_description_is_a_context_map():
    f = dlg.detect_form('I want to map my team, who does what and the handoffs between them.')
    assert f['form'] == 'context_map'


def test_an_existing_repo_is_a_system_map():
    f = dlg.detect_form('I need to audit the codebase someone else wrote before I change it.')
    assert f['form'] == 'system_map'


def test_no_signal_defaults_to_pipeline_but_says_it_is_not_confident():
    """Presenting a default as a finding is how the wrong skeleton gets built."""
    f = dlg.detect_form('I would like some help with things.')
    assert f['form'] == 'pipeline'
    assert f['confident'] is False
    assert 'default' in f['why']


def test_a_single_weak_signal_does_not_claim_confidence():
    """Isolates the confidence rule.

    One generic single-word hit is not grounds for asserting a form. Claiming
    confidence here is how the wrong skeleton gets built and then lived with.
    """
    f = dlg.detect_form('I keep a wiki.')
    assert f['form'] == 'knowledge_bundle'
    assert f['confident'] is False


def test_every_form_choice_carries_its_reason():
    for text in (NEWSLETTER, CLIENT_WORK, 'map my team and the handoffs'):
        assert dlg.detect_form(text)['why'].strip()


def test_runners_up_are_reported_so_composition_is_visible():
    f = dlg.detect_form(
        'Every week I publish, and each client also gets their own folder of notes.')
    assert f['runners_up']


# ── stages come from their pauses ─────────────────────────────────────────────
def test_sequence_markers_become_stage_boundaries():
    stages = dlg.extract_stages(NEWSLETTER)
    names = [s['name'] for s in stages]
    assert len(stages) >= 4
    assert 'draft' in names
    assert 'schedule' in names


def test_stages_are_named_after_the_work_they_do():
    """A stage folder called '02-draft' is readable; '02-then-i' is not."""
    for s in dlg.extract_stages(NEWSLETTER):
        assert s['name'].isalpha(), s
        assert len(s['name']) > 2


def test_the_stage_verb_is_chosen_over_the_first_long_word():
    """Isolates verb-naming from the fallback.

    Without the verb lookup the slug falls back to the first word over three
    characters, which here would be "through" -- a preposition, not a job.
    """
    stages = dlg.extract_stages(
        'First I go through the pile of receipts. '
        'Then I reconcile them against the statement.')
    names = [s['name'] for s in stages]
    assert 'through' not in names
    assert 'reconcile' in names or 'file' in names


def test_each_stage_cites_the_phrase_that_produced_it():
    """A user confirming a structure must see why each stage exists."""
    for s in dlg.extract_stages(NEWSLETTER):
        assert s['said'].strip()
        assert s['why'].strip()


def test_the_same_verb_twice_is_one_stage_not_two():
    """'One stage, one job' cuts both ways: one job is not two stages."""
    text = ('First I draft the post. Then I draft it again after feedback. '
            'Finally I publish it.')
    names = [s['name'] for s in dlg.extract_stages(text)]
    assert names.count('draft') == 1
    assert 'publish' in names


def test_stage_count_is_capped():
    text = ' '.join(f'Then I {v} it.' for v in dlg.STAGE_VERBS[:20])
    assert len(dlg.extract_stages(text)) <= dlg.MAX_STAGES


def test_text_with_no_markers_yields_at_most_one_stage():
    stages = dlg.extract_stages('I write blog posts about gardening for fun.')
    assert len(stages) <= 1


def test_empty_input_yields_no_stages():
    assert dlg.extract_stages('') == []
    assert dlg.extract_stages(None) == []


# ── gates and factory material ────────────────────────────────────────────────
def test_i_always_check_becomes_a_human_gate():
    a = dlg.analyse(NEWSLETTER)
    assert a['human_gates']
    assert any('read it out loud' in g['said'] for g in a['human_gates'])


def test_it_always_has_to_sound_like_becomes_factory_material():
    a = dlg.analyse(NEWSLETTER)
    assert a['factory']
    assert any('conversational' in f['said'] for f in a['factory'])


def test_gates_and_factory_are_empty_when_nothing_was_said():
    a = dlg.analyse('First I write. Then I post.')
    assert a['human_gates'] == []
    assert a['factory'] == []


# ── the over-structuring guardrail ────────────────────────────────────────────
def test_a_one_step_job_is_told_not_to_build_a_workspace():
    """The ladder: chat -> saved prompt -> folders. Do not skip rungs."""
    a = dlg.analyse(ONE_STEP)
    assert a['recommend_workspace'] is False
    assert 'prompt' in a['advice'] or 'short' in a['advice']


def test_a_very_short_description_asks_for_more_rather_than_guessing():
    a = dlg.analyse('help me')
    assert a['recommend_workspace'] is False
    assert a['advice']


def test_a_long_but_single_step_description_is_still_refused():
    """Isolates the stage-count guardrail from the word-count one.

    The revert proof showed the two guards masked each other: removing either
    alone broke no test, because every short example was also single-step and
    vice versa. This one is comfortably long enough to pass the word check and
    must still be refused for having no sequence.
    """
    text = ('I use an AI assistant to fix the spelling and grammar in the '
            'documents that I write for work, which saves me a fair amount '
            'of time over the course of a normal working week.')
    assert len(text.split()) > dlg.MIN_WORDS_FOR_WORKSPACE
    a = dlg.analyse(text)
    assert a['recommend_workspace'] is False
    assert 'scaffolding' in a['advice'] or 'one saved prompt' in a['advice']


def test_a_short_but_multi_step_description_is_still_refused():
    """The other half: passes the stage check, fails the word check."""
    text = 'First draft. Then ship.'
    assert len(text.split()) < dlg.MIN_WORDS_FOR_WORKSPACE
    a = dlg.analyse(text)
    assert a['recommend_workspace'] is False
    assert 'short' in a['advice']


def test_a_real_multi_stage_process_is_recommended():
    a = dlg.analyse(NEWSLETTER)
    assert a['recommend_workspace'] is True
    assert a['advice'] == ''


# ── follow-up questions ───────────────────────────────────────────────────────
def test_follow_up_does_not_ask_what_was_already_answered():
    """Asking someone what they just told you is how wizards earn their name."""
    a = dlg.analyse(NEWSLETTER)
    joined = ' '.join(a['follow_up']).lower()
    assert 'where do you stop and check' not in joined
    assert 'stays the same every run' not in joined


def test_follow_up_asks_for_gates_when_none_were_described():
    a = dlg.analyse('First I write the thing. Then I build it. Finally I ship it.')
    assert any('stop and check' in q.lower() for q in a['follow_up'])


def test_follow_up_is_bounded():
    assert len(dlg.analyse('help me please with something')['follow_up']) <= 3


# ── handoff to the scaffolder ─────────────────────────────────────────────────
def test_analysis_converts_to_scaffold_arguments():
    args = dlg.to_scaffold_args(dlg.analyse(NEWSLETTER), 'Newsletter')
    assert args['name'] == 'Newsletter'
    assert len(args['stages']) >= 4
    assert all(isinstance(s, str) and s for s in args['stages'])


def test_scaffolding_the_extracted_stages_produces_a_valid_workspace(tmp_path, monkeypatch):
    """End to end: description in, walk-test-passing workspace out."""
    monkeypatch.setenv('AGENTIC_OS_DATA_DIR', str(tmp_path))
    import importlib

    from backend.services import icm as icm_mod

    importlib.reload(icm_mod)

    args = dlg.to_scaffold_args(dlg.analyse(NEWSLETTER), 'newsletter')
    ws = icm_mod.WORKSPACES_DIR / 'newsletter'
    icm_mod.scaffold(ws, args['name'], args['description'], args['stages'])

    result = icm_mod.validate(ws)
    assert not result['errors'], result
    assert len(icm_mod.list_stages(ws)) == len(args['stages'])


# ── routes so the new workspace is reachable ──────────────────────────────────
def test_routes_are_proposed_from_the_description():
    """A workspace with no routes reintroduces the wrong-folder problem."""
    block = dlg.routes_block(NEWSLETTER)
    assert block.startswith('\n## Routes\n')
    assert 'newsletter' in block


def test_routes_do_not_include_stopwords_or_stage_verbs():
    block = dlg.routes_block(NEWSLETTER).lower()
    for bad in ('- the\n', '- and\n', '- draft\n', '- schedule\n'):
        assert bad not in block


def test_routes_prefer_the_subject_over_repeated_filler():
    """Frequency is the wrong signal for finding a subject noun.

    An earlier draft ranked by count with a >=2 threshold. In this description
    "newsletter" appears once and "always"/"links" twice, so it proposed
    "always, links" and dropped the subject entirely -- structurally unable to
    pick the right word. Position now leads, repetition only tie-breaks.
    """
    picks = dlg.routes_block(NEWSLETTER)
    assert 'newsletter' in picks
    assert '- always' not in picks


def test_possessive_stripping_does_not_mangle_words():
    """rstrip("'s") strips a CHARACTER SET, not a suffix.

    It turned "always" into "alway" and "links" into "link", which both
    corrupted the trigger and defeated the stopword check it fed.
    """
    block = dlg.routes_block("The week's newsletter always covers links.")
    assert '- alway' not in block
    assert "- week'" not in block


def test_routes_block_is_empty_for_empty_input():
    assert dlg.routes_block('') == ''


def test_a_scaffolded_workspace_with_routes_is_reachable_by_the_router(tmp_path, monkeypatch):
    """The real end-to-end property: describe it, then find it by asking."""
    monkeypatch.setenv('AGENTIC_OS_DATA_DIR', str(tmp_path))
    import importlib

    from backend.services import icm as icm_mod

    importlib.reload(icm_mod)
    from backend.services import icm_router as router_mod

    importlib.reload(router_mod)

    a = dlg.analyse(NEWSLETTER)
    args = dlg.to_scaffold_args(a, 'newsletter')
    ws = icm_mod.WORKSPACES_DIR / 'newsletter'
    icm_mod.scaffold(ws, args['name'], args['description'], args['stages'])
    ctx = ws / 'CONTEXT.md'
    ctx.write_text(ctx.read_text(encoding='utf-8') + dlg.routes_block(NEWSLETTER),
                   encoding='utf-8')

    d = router_mod.resolve('time to put together this week\'s newsletter')
    assert d['matched']
    assert d['workspace_id'] == 'newsletter'


# ── robustness ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize('bad', ['', None, '   ', '.', '!!!', 'a'])
def test_analyse_never_raises_on_junk(bad):
    a = dlg.analyse(bad)
    assert a['ok'] is True
    assert a['recommend_workspace'] is False


def test_analyse_handles_a_very_long_description(tmp_path):
    a = dlg.analyse(NEWSLETTER * 200)
    assert a['ok'] is True
    assert len(a['stages']) <= dlg.MAX_STAGES


# ── HTTP surface ──────────────────────────────────────────────────────────────
class TestDescribeEndpoints:
    def test_describe_returns_a_proposal(self, client):
        r = client.post('/api/icm/describe', json={'text': NEWSLETTER})
        assert r.status_code == 200
        d = r.json()
        assert d['ok'] is True
        assert d['form']['form'] == 'pipeline'
        assert len(d['stages']) >= 3
        assert d['suggested_routes'].startswith('## Routes')

    def test_describe_creates_nothing(self, client):
        before = client.get('/api/icm/workspaces').json()['workspaces']
        client.post('/api/icm/describe', json={'text': NEWSLETTER})
        after = client.get('/api/icm/workspaces').json()['workspaces']
        assert len(before) == len(after)

    def test_describe_requires_text(self, client):
        assert client.post('/api/icm/describe', json={}).status_code == 422
        assert client.post('/api/icm/describe', json={'text': '  '}).status_code == 422

    def test_create_refuses_a_one_step_job_without_force(self, client):
        r = client.post('/api/icm/describe/create',
                        json={'text': ONE_STEP, 'name': 'spellcheck'})
        assert r.status_code == 400
        assert r.json()['ok'] is False

    def test_create_scaffolds_a_routed_workspace(self, client):
        import uuid

        name = 'dlg-' + uuid.uuid4().hex[:8]
        r = client.post('/api/icm/describe/create',
                        json={'text': NEWSLETTER, 'name': name})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d['ok'] is True
        assert d['workspace']['stages']
        assert not d['validation']['errors']

        routes = client.get('/api/icm/routes').json()['routes']
        row = next(x for x in routes if x['workspace_id'] == name)
        assert row['routes'], 'a new workspace must be reachable by the router'

    def test_create_honours_user_edited_stages(self, client):
        """The user correcting the proposal is the whole point."""
        import uuid

        name = 'dlg-' + uuid.uuid4().hex[:8]
        r = client.post('/api/icm/describe/create', json={
            'text': NEWSLETTER, 'name': name,
            'stages': ['gather', 'write', 'ship'],
        })
        assert r.status_code == 200
        assert r.json()['workspace']['stages'] == ['01-gather', '02-write', '03-ship']

    def test_create_refuses_a_duplicate_workspace(self, client):
        import uuid

        name = 'dlg-' + uuid.uuid4().hex[:8]
        assert client.post('/api/icm/describe/create',
                           json={'text': NEWSLETTER, 'name': name}).status_code == 200
        assert client.post('/api/icm/describe/create',
                           json={'text': NEWSLETTER, 'name': name}).status_code == 409
