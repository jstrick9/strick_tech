"""Unit tests — event-loop offload for blocking admin endpoints (r80, #243)

An async def handler that runs synchronous subprocesses or long CPU work
INLINE stalls the single event loop — and with it every concurrent request
in the app. Two endpoints did exactly that:

  POST /api/studio/lint {"scope":"platform"} — ast.parse over every
    backend/*.py plus one `node --check` subprocess per frontend JS file
    (89 at last count). Measured on a real tree: 2870ms of handler time,
    2718ms of which the loop was frozen (a timer scheduled mid-call fired
    2.7s late) — every pane poll, WS ping and chat send in the app stops.

  POST /api/bugbot/review/git — two `git diff` subprocesses with 10s
    timeouts EACH, inline: up to 20s of freeze on a slow git.

Both now run their blocking section in the default thread executor (the
established house pattern — connectors.py, multififile_agent.py). Same
work, same results; the loop stays free: measured stall 2718ms → 6.7ms.

The probe technique is the honest one: on a SINGLE event loop (ASGI
transport, not TestClient — which runs its own loop and would hide a
stall), schedule a coroutine wake-up during the call and measure how late
it fires. Loop-blocking code delays the wake-up by the full blocking
duration; offloaded code wakes on time.
"""
import asyncio
import time
from pathlib import Path
from unittest.mock import patch

import httpx

from tests.unit.conftest import assert_ok, post_json


def _data_dir() -> Path:
    from backend.config import get_data_dir

    return get_data_dir()


def _run_offload_check(make_request, delay=0.06, margin=0.35):
    """Run `make_request(ac)` and a timer concurrently on ONE loop; assert
    the timer fires on schedule (the loop never stalled)."""

    async def scenario():
        from backend.app import app

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url='http://testserver', timeout=60
        ) as ac:
            await ac.get('/api/health')  # warm

            async def request():
                return await make_request(ac)

            async def probe():
                intended = time.perf_counter() + delay
                await asyncio.sleep(delay)
                return (time.perf_counter() - intended) * 1000

            resp, overshoot = await asyncio.gather(request(), probe())
            return resp, overshoot

    resp, overshoot = asyncio.run(scenario())
    assert overshoot < (delay + margin) * 1000, (
        f'event loop stalled: scheduled wake-up fired {overshoot:.0f}ms late — '
        'blocking work is back on the event loop'
    )
    return resp


class TestStudioLintPlatformOffloaded:
    def test_platform_scan_does_not_stall_the_loop(self, monkeypatch, tmp_path):
        # 800 real files under a PATCHED builder.ROOT. Two earlier approaches
        # were wrong and are recorded here: patching builder.ast.parse
        # patches the GLOBAL ast module (pytest's own assertion machinery
        # calls it — INTERNALERROR), and writing into the sandbox data dir's
        # backend/ writes into the REAL REPO (the sandbox symlinks repo read
        # paths into the data dir). ROOT is builder's own module attribute —
        # safe to point at a throwaway tree.
        import backend.routers.builder as builder

        d = tmp_path / 'backend'
        d.mkdir(parents=True)
        for i in range(800):
            (d / f'bulk_{i:04d}.py').write_text('x = 1\n', encoding='utf-8')
        monkeypatch.setattr(builder, 'ROOT', tmp_path)

        async def make_request(ac):
            return await ac.post('/api/studio/lint', json={'scope': 'platform'})

        resp = _run_offload_check(make_request, delay=0.10, margin=0.45)
        assert resp.status_code == 200
        assert resp.json()['ok'] is True

    def test_platform_scan_reports_a_broken_file(self, client, monkeypatch, tmp_path):
        import backend.routers.builder as builder

        (tmp_path / 'backend').mkdir()
        (tmp_path / 'backend' / 'r80_broken.py').write_text('def broken(:\n', encoding='utf-8')
        monkeypatch.setattr(builder, 'ROOT', tmp_path)

        r = post_json(client, '/api/studio/lint', {'scope': 'platform'})
        assert r.status_code == 400, 'issues found is reported as a 400'
        d_out = r.json()
        assert d_out['ok'] is False
        assert any('r80_broken.py' in e for e in d_out['errors'])


class TestBugbotGitDiffOffloaded:
    def test_git_diff_does_not_stall_the_loop(self, monkeypatch):
        import backend.routers.bugbot as bugbot

        class FakeResult:
            stdout = 'diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@\n-bad\n+good\n'
            returncode = 0
            stderr = ''

        def slow_run(*a, **kw):
            time.sleep(0.30)  # would be a 300ms freeze inline
            return FakeResult()

        monkeypatch.setattr(bugbot.subprocess, 'run', slow_run)

        async def fake_complete(messages, **kw):
            return {
                'text': '{"issues": [{"issue": "bad code", "severity": "low", '
                        '"fix": "good code"}], "severity": "low", "score": 80}',
                'tokens': 10,
                'model': 'mock',
            }

        with patch('backend.services.llm.complete', new=fake_complete):

            async def make_request(ac):
                return await ac.post('/api/bugbot/review/git', json={})

            resp = _run_offload_check(make_request, delay=0.08, margin=0.5)
        assert resp.status_code == 200
        assert resp.json()['ok'] is True

    def test_git_review_end_to_end_over_the_scratch_repo(self, client):
        """The unit sandbox seeds a scratch git repo (sandbox_notes.md with
        an uncommitted change — _data_sandbox does this for the gitai
        tests), so review/git has real material: it must complete a review
        end-to-end and persist it."""
        async def fake_complete(messages, **kw):
            return {
                'text': '{"issues": [{"issue": "scratch change reviewed", '
                        '"severity": "low", "fix": "none"}], "severity": "low", "score": 90}',
                'tokens': 10, 'model': 'mock',
            }

        with patch('backend.services.llm.complete', new=fake_complete):
            r = post_json(client, '/api/bugbot/review/git', {})
        assert r.status_code == 200
        body = r.json()
        assert body['ok'] is True, body

        from backend.services.memory_db import db_path
        import sqlite3
        con = sqlite3.connect(db_path())
        try:
            n = con.execute(
                "SELECT COUNT(*) FROM bugbot_reviews WHERE title='git diff HEAD'"
            ).fetchone()[0]
        finally:
            con.close()
        assert n >= 1, 'the git review must be persisted'
