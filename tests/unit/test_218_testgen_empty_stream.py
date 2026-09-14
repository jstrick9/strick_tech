"""
Unit Tests — testgen empty-stream refusal (#136)

/api/testgen/generate (streaming) buffers llm.stream frames and re-emits
them. A stream that completes without error AND without a single content
delta (content-filtered or empty completion, or a 200 response whose body
is not SSE at all) used to be forwarded as an empty stream: the pane then
reported "1 lines generated" for an empty suite and offered a Save button
that silently wrote nothing. The endpoint now answers with an explicit
error frame (code: empty_stream) instead.
"""
import json

import backend.routers.testgen as testgen_mod


async def _fake_stream_no_content(messages, **kwargs):
    """A healthy-looking stream that carries no content deltas."""
    yield 'data: ' + json.dumps({'delta': '', 'done': True, 'model': 'mock'}) + '\n\n'


async def _fake_stream_with_content(messages, **kwargs):
    yield 'data: ' + json.dumps({'delta': 'test("works", () => {});', 'done': False}) + '\n\n'
    yield 'data: ' + json.dumps({'delta': '', 'done': True, 'model': 'mock'}) + '\n\n'


class TestTestgenEmptyStream:
    def test_empty_stream_refuses_with_explicit_error(self, client, monkeypatch):
        src = testgen_mod.PREVIEW_DIR / 'empty_probe_r20.js'
        src.write_text('function f(){}\n', encoding='utf-8')
        try:
            monkeypatch.setattr(testgen_mod.llm, 'stream', _fake_stream_no_content)
            r = client.post('/api/testgen/generate', json={
                'filepath': 'empty_probe_r20.js', 'framework': 'jest', 'stream': True,
            })
            assert r.status_code == 200
            body = r.text
            assert 'empty_stream' in body
            assert 'no tests were generated' in body
            # no content delta may be forwarded on the empty path
            assert 'test("works"' not in body
        finally:
            src.unlink(missing_ok=True)

    def test_stream_with_content_still_streams(self, client, monkeypatch):
        src = testgen_mod.PREVIEW_DIR / 'content_probe_r20.js'
        src.write_text('function f(){}\n', encoding='utf-8')
        try:
            monkeypatch.setattr(testgen_mod.llm, 'stream', _fake_stream_with_content)
            r = client.post('/api/testgen/generate', json={
                'filepath': 'content_probe_r20.js', 'framework': 'jest', 'stream': True,
            })
            assert r.status_code == 200
            # the content frame is JSON-encoded inside the SSE frame
            assert 'test(' in r.text and 'works' in r.text and '"done": false' in r.text
            assert 'empty_stream' not in r.text
        finally:
            src.unlink(missing_ok=True)
