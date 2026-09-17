"""r52 — custom endpoints (custom_url:) finally work.

resolve_model() has parsed 'custom_url:<base>' model strings since v11.5.0,
but no code path ever handled the resulting provider: the base URL fell
through to the OpenRouter post as a model NAME. Verified live before the fix:
chatting with a custom endpoint the Settings page had just verified as
ONLINE returned the "No OPENROUTER_API_KEY set" help text. The optional key
saved by Settings never left localStorage either, and the Settings
connection test itself probed the endpoint from the browser — CORS blocks
that for every cross-origin endpoint, so it reported "SAVED / OFFLINE" for
machines that could reach the endpoint just fine.

Implemented:
  * llm._complete_impl/_stream_impl custom_url branches (OpenAI-compatible
    chat/completions, optional Bearer key, model pinned via
    'custom_url:<base>|<model>' or discovered via GET <base>/models)
  * chat.py forwards custom_api_key on both /api/chat and /api/chat/complete
  * /api/agents/models?base=<url> probes the endpoint SERVER-side (the page
    cannot — CORS); the Settings test and the model picker both use it
"""

import json

import pytest

from backend.services import llm as llm_mod
from backend.services.llm import _split_custom, resolve_model


# ── parsing ────────────────────────────────────────────────────────────────────


def test_resolve_model_passes_custom_urls_through():
    assert resolve_model('a', 'custom_url:http://127.0.0.1:1234/v1') == ('custom_url', 'http://127.0.0.1:1234/v1')
    assert resolve_model('a', 'custom_url:http://x/v1|my-model') == ('custom_url', 'http://x/v1|my-model')


def test_split_custom():
    assert _split_custom('http://x:1234/v1|the-model') == ('http://x:1234/v1', 'the-model')
    assert _split_custom('http://x:1234/v1/') == ('http://x:1234/v1', '')
    assert _split_custom(' http://x |  m ') == ('http://x', 'm')


# ── fakes ─────────────────────────────────────────────────────────────────────


class _Resp:
    def __init__(self, payload=None, exc=None):
        self._p, self._exc, self.status_code = payload, exc, 200

    def raise_for_status(self):
        if self._exc:
            raise self._exc

    def json(self):
        return self._p


class _FakeClient:
    """Stands in for httpx.AsyncClient inside llm for the custom branches."""

    calls: list = []
    fail_post = False

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        type(self).calls.append({'kind': 'post', 'url': url, 'headers': headers, 'json': json})
        if type(self).fail_post:
            return _Resp(exc=RuntimeError('connection refused'))
        return _Resp({
            'choices': [{'message': {'content': 'custom says hi'}}],
            'usage': {'prompt_tokens': 2, 'completion_tokens': 3, 'total_tokens': 5},
        })

    async def get(self, url):
        type(self).calls.append({'kind': 'get', 'url': url})
        return _Resp({'data': [{'id': 'discovered-1'}, {'id': 'discovered-2'}]})


class _StreamResp:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _StreamCtx:
    def __init__(self, lines):
        self._lines = lines

    async def __aenter__(self):
        return _StreamResp(self._lines)

    async def __aexit__(self, *a):
        return False


class _FakeStreamClient:
    last: dict = {}
    lines: list = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def stream(self, method, url, headers=None, json=None):
        type(self).last = {'url': url, 'headers': headers, 'json': json}
        return _StreamCtx(type(self).lines)


@pytest.fixture
def fake_httpx(monkeypatch):
    _FakeClient.calls = []
    _FakeClient.fail_post = False
    monkeypatch.setattr(llm_mod.httpx, 'AsyncClient', _FakeClient)
    return _FakeClient


# ── _complete_impl ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_complete_posts_to_the_custom_endpoint(fake_httpx):
    result = await llm_mod._complete_impl(
        [{'role': 'user', 'content': 'hi'}],
        model='custom_url:http://fake:1234/v1|pinned-model',
        custom_api_key='sekrit',
    )
    assert result['ok'] is True
    assert result['text'] == 'custom says hi'
    assert result['model'] == 'pinned-model'
    assert result['provider'] == 'custom_url'
    assert result['tokens'] == 5
    call = fake_httpx.calls[0]
    assert call['url'] == 'http://fake:1234/v1/chat/completions'
    assert call['headers']['Authorization'] == 'Bearer sekrit'
    assert call['json']['model'] == 'pinned-model'


@pytest.mark.asyncio
async def test_complete_without_key_sends_no_auth_header(fake_httpx):
    await llm_mod._complete_impl(
        [{'role': 'user', 'content': 'hi'}], model='custom_url:http://fake2:1/v1|m'
    )
    call = fake_httpx.calls[0]
    assert 'Authorization' not in call['headers']


@pytest.mark.asyncio
async def test_complete_discovers_the_model_when_not_pinned(fake_httpx):
    result = await llm_mod._complete_impl(
        [{'role': 'user', 'content': 'hi'}], model='custom_url:http://fake3:1/v1'
    )
    assert result['model'] == 'discovered-1'
    gets = [c for c in fake_httpx.calls if c['kind'] == 'get']
    assert gets and gets[0]['url'] == 'http://fake3:1/v1/models'


@pytest.mark.asyncio
async def test_complete_reports_endpoint_errors_honestly(fake_httpx):
    fake_httpx.fail_post = True
    result = await llm_mod._complete_impl(
        [{'role': 'user', 'content': 'hi'}], model='custom_url:http://fake4:1/v1|m'
    )
    assert result['ok'] is False
    assert 'connection refused' in result['error']


# ── _stream_impl ──────────────────────────────────────────────────────────────


def _sse(obj):
    return 'data: ' + json.dumps(obj)


@pytest.mark.asyncio
async def test_stream_parses_custom_endpoint_sse(monkeypatch):
    _FakeStreamClient.last = {}
    _FakeStreamClient.lines = [
        _sse({'choices': [{'delta': {'content': 'Hi '}}]}),
        _sse({'choices': [{'delta': {'content': 'there'}}]}),
        _sse({'choices': [{'delta': {}}], 'usage': {'prompt_tokens': 1, 'completion_tokens': 2, 'total_tokens': 3}}),
        'data: [DONE]',
    ]
    monkeypatch.setattr(llm_mod.httpx, 'AsyncClient', _FakeStreamClient)

    chunks = []
    async for c in llm_mod._stream_impl(
        [{'role': 'user', 'content': 'hi'}],
        model='custom_url:http://fakes:1/v1|m1',
        custom_api_key='k1',
    ):
        chunks.append(c)

    frames = [json.loads(c[len('data: '):]) for c in chunks if c.startswith('data: ')]
    deltas = ''.join(f['delta'] for f in frames if f.get('delta') and not f.get('done'))
    assert deltas == 'Hi there'
    done = [f for f in frames if f.get('done')][0]
    assert done['model'] == 'm1'
    assert done['tokens'] == 3
    assert done['provider'] == 'custom_url'
    assert _FakeStreamClient.last['url'] == 'http://fakes:1/v1/chat/completions'
    assert _FakeStreamClient.last['headers']['Authorization'] == 'Bearer k1'
    assert _FakeStreamClient.last['json']['stream'] is True


@pytest.mark.asyncio
async def test_stream_emits_a_final_frame_without_done_sentinel(monkeypatch):
    # Some OpenAI-compatible servers just close the stream. The consumer must
    # still receive a done frame, or the chat renderer treats the reply as
    # truncated.
    _FakeStreamClient.last = {}
    _FakeStreamClient.lines = [_sse({'choices': [{'delta': {'content': 'partial'}}]})]
    monkeypatch.setattr(llm_mod.httpx, 'AsyncClient', _FakeStreamClient)

    chunks = [c async for c in llm_mod._stream_impl(
        [{'role': 'user', 'content': 'hi'}], model='custom_url:http://fakes2:1/v1|m')]

    frames = [json.loads(c[len('data: '):]) for c in chunks if c.startswith('data: ')]
    assert [f for f in frames if f.get('done')], 'no done frame was emitted'


# ── chat.py passthrough ───────────────────────────────────────────────────────


def test_chat_forwards_the_custom_key_on_the_streaming_path(client, monkeypatch):
    captured = {}

    async def fake_stream(messages, **kw):
        captured.update(kw)
        yield 'data: ' + json.dumps({'delta': 'ok', 'done': True}) + '\n\n'

    monkeypatch.setattr(llm_mod, 'stream', fake_stream)
    try:
        r = client.post('/api/chat', json={
            'message': 'hi', 'model': 'custom_url:http://x/v1|m',
            'custom_api_key': 'sekrit', 'stream': True, 'session_id': 'zz-r52-probe',
        })
        assert r.status_code == 200
        assert captured.get('custom_api_key') == 'sekrit'
        assert captured.get('model') == 'custom_url:http://x/v1|m'
    finally:
        _cleanup_chat_rows()


def test_chat_forwards_the_custom_key_on_the_non_streaming_path(client, monkeypatch):
    captured = {}

    async def fake_complete(messages, **kw):
        captured.update(kw)
        return {'text': 'ok', 'tokens': 1, 'cost': 0.0, 'model': 'm', 'ok': True}

    monkeypatch.setattr(llm_mod, 'complete', fake_complete)
    try:
        r = client.post('/api/chat/complete', json={
            'message': 'hi', 'model': 'custom_url:http://x/v1|m',
            'custom_api_key': 'sekrit2',
        })
        assert r.status_code == 200
        assert captured.get('custom_api_key') == 'sekrit2'
    finally:
        _cleanup_chat_rows()


def _cleanup_chat_rows():
    from backend.services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute("DELETE FROM chat_log WHERE session_id LIKE 'zz-r52-probe%'")
        con.commit()
    finally:
        con.close()


# ── /api/agents/models?base= ──────────────────────────────────────────────────


def test_models_endpoint_probes_a_custom_endpoint(client, monkeypatch):
    async def fake_disc(base):
        return ['m-one', 'm-two']

    monkeypatch.setattr(llm_mod, '_discover_custom_models', fake_disc)
    d = client.get('/api/agents/models?base=http://127.0.0.1:9/v1').json()
    assert d['custom'] == {'running': True, 'models': ['m-one', 'm-two']}


def test_models_endpoint_refuses_non_http_schemes(client):
    d = client.get('/api/agents/models?base=ftp://evil/x').json()
    assert d['custom']['running'] is False
    assert d['custom']['error']


def test_models_endpoint_reports_an_unreachable_endpoint(client, monkeypatch):
    async def fake_disc(base):
        return []

    monkeypatch.setattr(llm_mod, '_discover_custom_models', fake_disc)
    d = client.get('/api/agents/models?base=http://127.0.0.1:9/v1').json()
    assert d['custom']['running'] is False
    assert d['custom']['models'] == []
