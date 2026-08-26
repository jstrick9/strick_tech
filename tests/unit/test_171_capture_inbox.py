"""Module 34 — the capture inbox.

One door in: phone share sheet, email, hook, terminal, web. The ICM entry
router files what lands there.

The two load-bearing properties, both about failure rather than success:

1. CAPTURE MUST NOT FAIL FOR AN INTERESTING REASON. Someone sharing a link from
   a phone on a train cannot debug a workspace mismatch, and a capture that
   errors is a thought that is now lost. So capture() writes a file and does
   nothing else — no routing, no LLM, no network.

2. THE SWEEP MUST NOT GUESS. An item the router cannot place STAYS in the
   inbox. Filing it somewhere plausible is the wrong-folder failure the router
   exists to prevent, and it would be silent. Nothing is ever deleted; swept
   items move to _filed/ carrying a record of where they went and why.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def ci(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENTIC_OS_DATA_DIR', str(tmp_path))
    from backend.services import capture_inbox as mod

    importlib.reload(mod)
    return mod


@pytest.fixture()
def routed(ci, monkeypatch):
    """A router with one real workspace declaring routes."""
    from backend.services import icm as icm_mod

    importlib.reload(icm_mod)
    from backend.services import icm_router as router_mod

    importlib.reload(router_mod)

    ws = icm_mod.WORKSPACES_DIR / 'billing'
    icm_mod.scaffold(ws, 'billing', '', ['gather', 'send'])
    ctx = ws / 'CONTEXT.md'
    ctx.write_text(ctx.read_text(encoding='utf-8') + '\n## Routes\n- invoice\n- billing\n',
                   encoding='utf-8')
    return ci


# ── capture always succeeds ───────────────────────────────────────────────────
def test_capture_writes_a_readable_markdown_file(ci):
    r = ci.capture('Remember to invoice Acme', source='share')
    assert r['ok'] is True
    from pathlib import Path

    text = Path(r['path']).read_text(encoding='utf-8')
    assert text.startswith('---')
    assert 'Remember to invoice Acme' in text


def test_capture_derives_a_title_when_none_is_given(ci):
    """A folder of timestamps is not something a human can scan."""
    r = ci.capture('Call the accountant about Q3')
    assert r['title'] == 'Call the accountant about Q3'


def test_capture_accepts_a_url_with_no_text(ci):
    """A phone share is often just a link."""
    r = ci.capture('', url='https://example.test/article')
    assert r['ok'] is True
    assert ci.get_item(r['id'])['url'] == 'https://example.test/article'


def test_capture_with_nothing_at_all_is_refused(ci):
    assert ci.capture('')['ok'] is False
    assert ci.capture('   ', url='  ')['ok'] is False


def test_an_unknown_source_falls_back_rather_than_failing(ci):
    """Capture must not fail over a metadata quibble."""
    r = ci.capture('something', source='carrier-pigeon')
    assert r['ok'] is True
    assert r['source'] == 'api'


def test_two_captures_in_the_same_second_do_not_collide(ci):
    """Ids are timestamp-based; the second must not overwrite the first."""
    a = ci.capture('first thing', title='same title')
    b = ci.capture('second thing', title='same title')
    assert a['id'] != b['id']
    assert {i['id'] for i in ci.list_items()} == {a['id'], b['id']}
    bodies = {i['body'] for i in ci.list_items()}
    assert bodies == {'first thing', 'second thing'}


def test_a_title_of_pure_punctuation_still_yields_a_valid_id(ci):
    r = ci.capture('body text', title='!!! ??? ***')
    assert r['ok'] is True
    assert ci.ITEM_ID_RE.match(r['id']), r['id']


def test_a_non_latin_title_still_yields_a_valid_id(ci):
    r = ci.capture('body', title='会議のメモ')
    assert r['ok'] is True
    assert ci.ITEM_ID_RE.match(r['id']), r['id']


def test_an_oversized_body_is_truncated_not_rejected(ci):
    r = ci.capture('X' * (ci.MAX_BODY_CHARS * 2))
    assert r['ok'] is True
    assert len(ci.get_item(r['id'])['body']) <= ci.MAX_BODY_CHARS


def test_capture_does_no_routing(ci, monkeypatch):
    """Capture must not be able to fail because routing failed."""
    from backend.services import icm_router

    def explode(*a, **k):
        raise RuntimeError('router down')

    monkeypatch.setattr(icm_router, 'resolve', explode)
    assert ci.capture('anything at all')['ok'] is True


# ── reading ───────────────────────────────────────────────────────────────────
def test_items_list_newest_first(ci):
    ci.capture('older', title='aaa')
    import time

    time.sleep(1.05)
    newer = ci.capture('newer', title='bbb')
    assert ci.list_items()[0]['id'] == newer['id']


def test_get_item_finds_a_captured_item(ci):
    r = ci.capture('find me')
    assert ci.get_item(r['id'])['body'] == 'find me'


def test_get_item_on_a_hostile_id_returns_none(ci):
    for bad in ('../../etc/passwd', '', 'nope', 'x' * 80):
        assert ci.get_item(bad) is None


def test_item_path_refuses_a_malformed_id_outright(ci):
    """Assert the GUARD, not just the symptom.

    get_item() returns None for a bad id whether or not the id is validated,
    because the resulting file does not exist either way -- so it cannot tell a
    working guard from a missing one, and the revert proof showed exactly that.
    safe_path() stops traversal, but without the id rule an empty id resolves
    to '<inbox>/.md' and arbitrary junk resolves to a real writable path.
    """
    assert ci.item_path('') is None
    assert ci.item_path('nope') is None
    assert ci.item_path('x' * 80) is None
    assert ci.item_path('../../etc/passwd') is None
    assert ci.item_path('..%2Fescape') is None
    # The shape it must accept: <10-digit epoch>-<6 lowercase alnum>
    good = ci.item_path('1787764600-abc123')
    assert good is not None and good.name == '1787764600-abc123.md'


def test_delete_removes_an_item(ci):
    r = ci.capture('delete me')
    assert ci.delete_item(r['id']) is True
    assert ci.get_item(r['id']) is None


def test_delete_on_a_hostile_id_is_refused(ci):
    assert ci.delete_item('../../../etc/passwd') is False


def test_stats_count_by_source(ci):
    ci.capture('a', source='share')
    ci.capture('b', source='share')
    ci.capture('c', source='email')
    s = ci.stats()
    assert s['inbox'] == 3
    assert s['by_source'] == {'share': 2, 'email': 1}


# ── the sweep routes, and refuses to guess ────────────────────────────────────
def test_sweep_files_a_matching_item_into_its_workspace(routed):
    routed.capture('Send the invoice to Acme', source='share')
    result = routed.sweep()
    assert result['filed_count'] == 1
    assert result['filed'][0]['workspace_id'] == 'billing'
    assert result['filed'][0]['stage'] == '01-gather'


def test_a_filed_item_lands_as_a_file_in_the_stage_output(routed):
    routed.capture('Send the invoice to Acme')
    routed.sweep()
    from backend.services import icm as icm_mod

    out = icm_mod.WORKSPACES_DIR / 'billing' / 'stages' / '01-gather' / 'output'
    written = [p for p in out.glob('*.md') if p.name != '.gitkeep']
    assert written, 'the captured item must actually arrive in the workspace'
    assert 'Send the invoice to Acme' in written[0].read_text(encoding='utf-8')


def test_an_unroutable_item_stays_in_the_inbox(routed):
    """Filing it somewhere plausible is the wrong-folder failure, silently."""
    routed.capture('what is the weather tomorrow in Charlotte')
    result = routed.sweep()
    assert result['filed_count'] == 0
    assert result['remaining'] == 1
    assert len(routed.list_items()) == 1


def test_the_sweep_reports_why_an_item_was_left(routed):
    routed.capture('completely unrelated thought')
    left = routed.sweep()['left_in_inbox'][0]
    assert left['status'] == 'no-match'
    assert left['reason']


def test_a_filed_item_leaves_the_inbox_but_is_not_deleted(routed):
    """Never silently delete -- least of all the unsorted-thoughts folder."""
    r = routed.capture('invoice Acme now')
    routed.sweep()
    assert routed.list_items() == []
    filed = routed.list_items(filed=True)
    assert len(filed) == 1
    assert filed[0]['id'] == r['id']


def test_a_filed_item_records_where_it_went_and_why(routed):
    routed.capture('invoice Acme now')
    routed.sweep()
    filed = routed.list_items(filed=True)[0]
    assert filed['workspace'] == 'billing'
    assert filed['stage'] == '01-gather'
    assert filed['reason']
    assert filed['status'] == 'filed'


def test_a_dry_run_files_nothing(routed):
    routed.capture('invoice Acme now')
    result = routed.sweep(dry_run=True)
    assert result['dry_run'] is True
    assert result['filed_count'] == 1
    assert len(routed.list_items()) == 1, 'dry run must not move anything'
    assert routed.list_items(filed=True) == []


def test_the_sweep_is_rerunnable(routed):
    routed.capture('invoice Acme now')
    assert routed.sweep()['filed_count'] == 1
    second = routed.sweep()
    assert second['filed_count'] == 0
    assert second['remaining'] == 0


def test_the_sweep_is_bounded(routed):
    for i in range(12):
        routed.capture(f'invoice number {i}', title=f'inv{i}')
    result = routed.sweep(limit=5)
    assert result['filed_count'] <= 5


def test_an_ambiguous_item_is_left_rather_than_coin_flipped(ci):
    """Two workspaces matching equally must not resolve by luck."""
    from backend.services import icm as icm_mod

    importlib.reload(icm_mod)
    from backend.services import icm_router as router_mod

    importlib.reload(router_mod)
    for name in ('alpha', 'beta'):
        ws = icm_mod.WORKSPACES_DIR / name
        icm_mod.scaffold(ws, name, '', ['work'])
        ctx = ws / 'CONTEXT.md'
        ctx.write_text(ctx.read_text(encoding='utf-8') + '\n## Routes\n- quarterly review\n',
                       encoding='utf-8')

    ci.capture('time for the quarterly review')
    result = ci.sweep()
    assert result['filed_count'] == 0
    assert result['left_in_inbox'][0]['status'] == 'ambiguous'


def test_a_failed_workspace_write_leaves_the_item_in_the_inbox(routed, monkeypatch):
    """Reporting success for a capture that went nowhere is the defect family
    this codebase keeps finding. If the workspace write fails, the item must
    still be in the inbox.
    """
    r = routed.capture('invoice Acme now')

    real_write = type(routed.INBOX_DIR).write_text

    def failing(self, *a, **kw):
        if 'stages' in str(self):
            raise OSError('disk full')
        return real_write(self, *a, **kw)

    monkeypatch.setattr(type(routed.INBOX_DIR), 'write_text', failing)
    result = routed.sweep()
    monkeypatch.undo()

    assert result['filed_count'] == 0
    assert [i['id'] for i in routed.list_items()] == [r['id']]
    assert routed.list_items(filed=True) == []


def test_a_non_pipeline_form_files_into_its_own_shelf(ci):
    """A record library has no stages; forcing one would invent a folder."""
    from backend.services import icm as icm_mod

    importlib.reload(icm_mod)
    from backend.services import icm_forms as forms
    from backend.services import icm_router as router_mod

    importlib.reload(router_mod)

    ws = icm_mod.WORKSPACES_DIR / 'clients'
    forms.scaffold_form(ws, forms.RECORD_LIBRARY, 'clients', '', ['acme'])
    ctx = ws / 'CONTEXT.md'
    ctx.write_text(ctx.read_text(encoding='utf-8') + '\n## Routes\n- client note\n',
                   encoding='utf-8')

    ci.capture('a client note about the retainer')
    result = ci.sweep()
    assert result['filed_count'] == 1
    assert (ws / '_inbox').is_dir()
    assert list((ws / '_inbox').glob('*.md'))


# ── export ────────────────────────────────────────────────────────────────────
def test_export_is_jsonl(ci):
    import json

    ci.capture('one')
    ci.capture('two')
    lines = ci.export_items().splitlines()
    assert len(lines) == 2
    assert all(json.loads(x)['id'] for x in lines)


def test_export_of_an_empty_inbox_is_empty(ci):
    assert ci.export_items() == ''


# ── HTTP surface ──────────────────────────────────────────────────────────────
class TestInboxEndpoints:
    def test_capture_over_http(self, client):
        r = client.post('/api/inbox', json={'text': 'http capture test'})
        assert r.status_code == 200, r.text
        assert r.json()['ok'] is True

    def test_capture_requires_content(self, client):
        assert client.post('/api/inbox', json={'text': '   '}).status_code == 422

    def test_the_inbox_lists_items(self, client):
        client.post('/api/inbox', json={'text': 'listed item'})
        body = client.get('/api/inbox').json()
        assert body['ok'] is True
        assert any(i['body'] == 'listed item' for i in body['items'])

    def test_the_share_target_accepts_a_form_post(self, client):
        """The Web Share Target API posts a form, not JSON."""
        r = client.post('/api/inbox/share',
                        data={'title': 'Shared', 'text': 'from a phone',
                              'url': 'https://example.test'},
                        follow_redirects=False)
        assert r.status_code == 303, r.text

    def test_the_share_target_redirects_rather_than_returning_json(self, client):
        """A phone browser handed JSON shows braces on a white screen."""
        r = client.post('/api/inbox/share', data={'text': 'x'}, follow_redirects=False)
        assert r.status_code == 303
        assert 'pane=inbox' in r.headers['location']

    def test_an_empty_share_still_redirects(self, client):
        """Even a malformed share must not error at the user."""
        r = client.post('/api/inbox/share', data={}, follow_redirects=False)
        assert r.status_code == 303

    def test_sweep_preview_files_nothing(self, client):
        client.post('/api/inbox', json={'text': 'preview only item'})
        before = len(client.get('/api/inbox').json()['items'])
        assert client.get('/api/inbox/sweep/preview').status_code == 200
        assert len(client.get('/api/inbox').json()['items']) == before

    def test_an_unknown_item_is_a_404(self, client):
        assert client.get('/api/inbox/items/9999999999-abcdef').status_code == 404

    def test_export_returns_ndjson(self, client):
        client.post('/api/inbox', json={'text': 'exported'})
        r = client.get('/api/inbox/export')
        assert r.status_code == 200
        assert 'ndjson' in r.headers['content-type']


# ── the PWA share target has to be declared or none of this is reachable ──────
def test_the_manifest_declares_the_share_target():
    """Without this the phone OS never offers the app in its share sheet."""
    import json
    from pathlib import Path

    manifest = json.loads(Path('frontend/manifest.json').read_text(encoding='utf-8'))
    st = manifest.get('share_target')
    assert st, 'no share_target: nothing can be shared to this app from a phone'
    assert st['action'] == '/api/inbox/share'
    assert st['method'].upper() == 'POST'
    assert set(st['params']) == {'title', 'text', 'url'}


def test_the_share_target_action_is_a_real_route():
    """A manifest pointing at a 404 fails only on the phone, silently."""
    from backend.app import app
    import json
    from pathlib import Path

    action = json.loads(Path('frontend/manifest.json').read_text(
        encoding='utf-8'))['share_target']['action']
    assert action in {getattr(r, 'path', '') for r in app.routes}
