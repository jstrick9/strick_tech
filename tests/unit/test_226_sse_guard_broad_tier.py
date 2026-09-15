"""sse_guard's broad-exception tier.

The guard's docstring promises that an exception inside a streaming response
becomes "a final error event and a graceful close" — but only
LLMUnavailableError got that treatment. Any other exception (a provider
returning a shape nobody parsed, a bug in a stream transformer) propagated
out of the generator and truncated the HTTP response mid-chunk: the client
saw `RemoteProtocolError: peer closed connection without sending complete
message body`, not a reason. Same symptom the narrow tier was built to fix,
one exception type broader.

The broad tier must also keep the frame user-safe: str(exc) can carry
paths, URLs and upstream bodies, so the frame carries a stable message and
the traceback goes to the log instead.
"""

from __future__ import annotations

import asyncio
import json

from backend.services.llm import LLMUnavailableError, sse_guard


def _collect(gen):
    async def run():
        out = []
        async for chunk in gen:
            out.append(chunk)
        return out

    return asyncio.run(run())


def _frames(chunks):
    out = []
    for c in chunks:
        for line in c.split('\n'):
            if line.startswith('data:'):
                out.append(json.loads(line[5:].strip()))
    return out


async def _gen_ok_then_raise(exc):
    yield 'data: {"type":"token","data":"hi"}\n\n'
    raise exc


class TestBroadTier:
    def test_unexpected_exception_closes_with_error_frame(self):
        chunks = _collect(sse_guard(_gen_ok_then_raise(RuntimeError('boom /etc/passwd'))))
        frames = _frames(chunks)
        assert frames[0]['type'] == 'token', 'chunks before the raise must pass through'
        err = frames[-1]
        assert err['type'] == 'error'
        assert err['code'] == 'stream_error'
        assert err['done'] is True
        # user-safe copy: the exception's own message must NOT reach the frame
        assert 'boom' not in err['error'] and '/etc/passwd' not in err['error']
        assert 'try again' in err['error'].lower()

    def test_narrow_tier_still_specific(self):
        exc = LLMUnavailableError({'model': 'm'}, 'provider down')
        chunks = _collect(sse_guard(_gen_ok_then_raise(exc)))
        err = _frames(chunks)[-1]
        assert err['code'] == 'llm_unavailable'
        assert err['error'] == 'provider down'
        assert err['model'] == 'm'

    def test_healthy_stream_untouched(self):
        async def gen():
            yield 'data: {"type":"token","data":"a"}\n\n'
            yield 'data: {"type":"done"}\n\n'

        frames = _frames(_collect(sse_guard(gen())))
        assert [f['type'] for f in frames] == ['token', 'done']

    def test_custom_event_type_respected_on_broad_tier(self):
        chunks = _collect(sse_guard(_gen_ok_then_raise(ValueError('x')), event_type='fatal'))
        assert _frames(chunks)[-1]['type'] == 'fatal'
