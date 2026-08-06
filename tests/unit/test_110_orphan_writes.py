"""A write against a parent that does not exist must be refused.

FOUND BY DRIVING MULTI-STEP JOURNEYS
────────────────────────────────────
Probing every sub-resource mutating route with a VALID body and a ghost parent
id found six that accepted the write. Verified they PERSIST -- a GET on the
same ghost id afterwards returned the child rows:

    POST /api/agent-identity/{ghost}/permissions  -> 200, row persists
    POST /api/eval-framework/suites/{ghost}/cases -> 200, case persists
    POST /api/rag/pipelines/{ghost}/query         -> 200 "No relevant documents"
    POST /api/rag/pipelines/{ghost}/retrieve      -> 200, empty result
    POST /api/goals/{ghost}/milestones            -> 500 raw IntegrityError
    POST /api/crdt/docs/{ghost}/op                -> 200 (DELIBERATE, see below)

WHY THESE MATTER
────────────────
An orphan is invisible. It hangs off a parent that appears in no list, so it
can never be reviewed, run or deleted through the UI -- but it still occupies
the table and counts toward totals. A stale id in an open tab is the ordinary
way to create one.

The RAG pair is the worst of them, and not because of the orphan: telling a
user "No relevant documents found in this pipeline" when the pipeline does not
exist says their corpus is EMPTY. The rational response is to go and upload
documents into something that was never there.

The goals one leaked `sqlite3.IntegrityError: FOREIGN KEY constraint failed`
as a bare HTTP 500 -- the database enforcing a rule the application should
have checked.
"""
import pytest

GHOST = 'zzz-no-such-parent-99999'


# ══ The refusals ══════════════════════════════════════════════════════════════

def test_a_permission_cannot_be_granted_to_an_unknown_agent(client):
    """In a permissions table an orphan is worse than untidy: a grant that
    references no real identity never appears in any agent view, so it can
    never be reviewed or revoked through the UI that lists agents."""
    r = client.post(f'/api/agent-identity/{GHOST}/permissions', json={'action': 'chat:write'})
    assert r.status_code == 404, f'granted a permission to a ghost agent: {r.status_code} {r.text[:120]}'
    assert 'unknown agent' in r.text.lower() or 'not found' in r.text.lower()


def test_the_permission_is_not_persisted(client):
    """The check has to happen BEFORE the insert, not just change the status."""
    client.post(f'/api/agent-identity/{GHOST}/permissions', json={'action': 'chat:write'})
    listing = client.get(f'/api/agent-identity/{GHOST}/permissions')
    if listing.status_code != 200:
        return  # a 404 on the listing is also a correct answer
    perms = listing.json().get('permissions') or []
    assert not perms, f'an orphaned permission row persisted: {perms[:2]}'


def test_an_eval_case_cannot_be_added_to_an_unknown_suite(client):
    r = client.post(f'/api/eval-framework/suites/{GHOST}/cases',
                    json={'prompt': 'p', 'expected': 'e'})
    assert r.status_code == 404, f'created an orphaned eval case: {r.status_code} {r.text[:120]}'


def test_a_milestone_on_an_unknown_goal_is_a_404_not_a_500(client):
    """It raised sqlite3.IntegrityError and surfaced as "Internal Server Error",
    which tells the user nothing actionable about a stale goal id."""
    r = client.post(f'/api/goals/{GHOST}/milestones', json={'title': 'M'})
    assert r.status_code != 500, 'a foreign-key violation is still leaking as a 500'
    assert r.status_code == 404
    assert 'not found' in r.text.lower()


@pytest.mark.parametrize('action', ['query', 'retrieve'])
def test_rag_does_not_report_a_missing_pipeline_as_an_empty_one(client, action):
    """"No relevant documents found in this pipeline" for a pipeline that does
    not exist sends the user off to re-upload into nothing.

    /documents on the same resource already 404s, so the two halves of the
    feature disagreed about whether the pipeline had to exist.
    """
    r = client.post(f'/api/rag/pipelines/{GHOST}/{action}', json={'query': 'anything'})
    assert r.status_code == 404, (
        f'{action} answered {r.status_code} for a non-existent pipeline: {r.text[:140]}'
    )
    assert 'not found' in r.text.lower()
    assert 'no relevant documents' not in r.text.lower(), (
        'still telling the user their pipeline is empty when it does not exist'
    )


# ══ The legitimate paths still work ═══════════════════════════════════════════
# A parent check that also blocks real writes would be a worse bug than the one
# being fixed, so each is asserted explicitly.

def test_a_real_agent_can_still_be_granted_a_permission(client):
    r = client.post('/api/agent-identity/builder/permissions', json={'action': 'chat:write'})
    assert r.status_code == 200, f'blocked a legitimate grant: {r.text[:140]}'


def test_a_real_goal_still_accepts_milestones(client):
    created = client.post('/api/goals', json={'title': 'MilestoneHost'})
    if created.status_code != 200:
        pytest.skip('goals endpoint unavailable')
    gid = created.json().get('id') or created.json().get('goal_id')
    r = client.post(f'/api/goals/{gid}/milestones', json={'title': 'M1'})
    assert r.status_code == 200, f'blocked a legitimate milestone: {r.text[:140]}'


def test_a_real_suite_still_accepts_cases(client):
    suites = client.get('/api/eval-framework/suites')
    if suites.status_code != 200:
        pytest.skip('eval framework unavailable')
    body = suites.json()
    rows = body.get('suites') if isinstance(body, dict) else body
    if not rows:
        pytest.skip('no seeded suites')
    sid = rows[0]['suite_id']
    r = client.post(f'/api/eval-framework/suites/{sid}/cases', json={'prompt': 'p', 'expected': 'e'})
    assert r.status_code == 200, f'blocked a legitimate eval case: {r.text[:140]}'


# ══ Spec phase gates ══════════════════════════════════════════════════════════

@pytest.mark.parametrize('phase', ['requirements', 'design', 'tasks'])
def test_a_phase_on_a_missing_spec_says_the_spec_is_missing(client, phase):
    """The gates inferred their state purely from whether an artifact FILE
    existed, and never checked the spec did.

        POST /api/specs/{ghost}/tasks -> "Generate design first"

    That is workflow advice about something that is not there. A user who
    followed it would go looking for a Generate Design button on a spec that
    does not exist. `requirements` was subtler: it called _get_spec() but
    ignored a None result and blamed the request body instead
    ("description required").
    """
    r = client.post(f'/api/specs/{GHOST}/{phase}', json={})
    assert r.status_code == 404, (
        f'{phase} answered {r.status_code} for a ghost spec: {r.text[:140]}'
    )
    assert 'spec not found' in r.text.lower(), f'misleading error: {r.text[:140]}'
    for wrong in ('generate design first', 'generate requirements first', 'description required'):
        assert wrong not in r.text.lower(), f'still blaming the wrong thing: {r.text[:140]}'


def test_the_artifact_gates_still_work_on_a_real_spec(client):
    """The existence check must not have replaced the phase ordering."""
    created = client.post('/api/specs', json={'title': 'GateOrder', 'description': 'x'})
    if created.status_code != 200:
        pytest.skip('specs unavailable')
    sid = created.json()['spec']['id']
    r = client.post(f'/api/specs/{sid}/tasks', json={})
    assert r.status_code == 400, f'the design gate stopped working: {r.status_code}'
    assert 'design' in r.text.lower()
