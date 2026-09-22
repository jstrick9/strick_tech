"""
GAP-06: 5xx Hardening — malformed bodies must never crash the server.

Found by a systematic probe: every mutating route fed edge-case payloads
(int where a string is expected, key-present None, dicts for file content,
junk path params). 15 endpoints returned 500 (TypeError / AttributeError /
sqlite bind errors) before the as_text hardening sweep. These tests pin the
contract: garbage in → honest 4xx (or a coerced, bounded 200), never a 500.

The full probe (2.5k requests across all 488 mutating routes) lives in this
session's tooling; this file replays every request that ever produced a 500,
plus representative sites from each fixed bug class.
"""
import pytest
from tests.gap.conftest import *  # noqa: F401,F403


# The payload that broke 15 endpoints: ints where strings are expected,
# key-present None, a dict where file content is expected.
JUNK = {
    "id": -1, "name": 123, "limit": -5, "query": "",
    "path": "/nonexistent", "title": None, "content": {"a": 1},
}
NULLISH = {"name": None, "id": None, "query": None, "data": None}


@pytest.mark.asyncio
class TestGap5xxHardening:
    """Every endpoint that ever returned a 500 to malformed input."""

    async def test_01_ambient_tasks_int_name(self, C):
        r = await POST(C, "/api/ambient/tasks", JUNK)
        assert r.status_code < 500, r.text

    async def test_02_db_table_create_int_name(self, C):
        r = await POST(C, "/api/db/sqlite/table/create", JUNK)
        assert r.status_code < 500, r.text

    async def test_03_evals_ab_test_int_name(self, C):
        r = await POST(C, "/api/evals/ab-test", JUNK)
        assert r.status_code < 500, r.text

    async def test_04_evals_datasets_none_name(self, C):
        """name=None (key present) used to bypass the default and NULL-crash."""
        r = await POST(C, "/api/evals/datasets", NULLISH)
        assert r.status_code < 500, r.text

    async def test_05_license_set_user_int_name(self, C):
        r = await POST(C, "/api/license/set-user", JUNK)
        assert r.status_code < 500, r.text
        # restore a sane user record
        await POST(C, "/api/license/set-user", {"name": "Strick", "email": "strick@strick.tech", "org": "Strick Tech"})

    async def test_06_pluginsdk_packs_int_id(self, C):
        r = await POST(C, "/api/pluginsdk/packs", {"name": "gap 5xx pack", "id": 12345})
        assert r.status_code < 500, r.text
        if r.status_code == 200:
            pid = r.json().get("id") or r.json().get("pack_id")
            if pid:
                await DELETE(C, f"/api/pluginsdk/packs/{pid}")

    async def test_07_pluginsdk_validate_int_id_and_skills(self, C):
        """int id and non-dict skills entries used to AttributeError."""
        r = await POST(C, "/api/pluginsdk/validate", {
            "id": 12345, "name": "x", "version": "1.0.0",
            "description": "x", "skills": [1, "two", {"id": "ok"}],
        })
        assert r.status_code < 500, r.text
        d = r.json()
        assert d.get("ok") is False or "errors" in d

    async def test_08_sessions_int_name_and_id(self, C):
        r = await POST(C, "/api/sessions", JUNK)
        assert r.status_code < 500, r.text

    async def test_09_specs_artifact_dict_content(self, C):
        """Artifact content must be a string; a dict used to crash the write."""
        r = await PUT(C, "/api/specs/nonexistent_spec/artifacts/x.md", JUNK)
        assert r.status_code < 500, r.text

    async def test_10_steering_dict_content(self, C):
        """Steering content is written verbatim: non-string → 400, never 500."""
        for sid in ("-1", "999999999", "abc"):
            r = await PUT(C, f"/api/steering/{sid}", JUNK)
            assert r.status_code < 500, (sid, r.status_code, r.text)

    async def test_11_workflow_int_fields(self, C):
        r = await POST(C, "/api/workflow", JUNK)
        assert r.status_code < 500, r.text
        r = await PUT(C, "/api/workflow/abc", JUNK)
        assert r.status_code < 500, r.text

    async def test_12_coercion_semantics(self, C):
        """as_text coercion: an int name means \"123\", it does not error."""
        r = await POST(C, "/api/agents", {"name": 404})
        assert r.status_code < 500, r.text
        if r.status_code in (200, 201):
            d = r.json()
            agent = d.get("agent") or d
            aid = agent.get("id")
            assert agent.get("name") == "404"
            if aid:
                await DELETE(C, f"/api/agents/{aid}")


@pytest.mark.asyncio
class TestGapClassSweepSmoke:
    """Representative sites from each fixed bug class (str-op on unvalidated
    input): .strip(), .lower(), .upper(), slicing, set() on non-list, int()
    on junk string. All must stay under 500."""

    @pytest.mark.parametrize("path,body", [
        ("/api/chat", {"message": "hi", "agent_id": 123}),          # chat .lower()
        ("/api/hitl/interrupt", {"action": 99, "task": 5}),          # hitl .strip()
        ("/api/mcp/agent/run", {"tools": 12345}),                    # mcp set(non-list)
        ("/api/loops", {"max_runs": "abc"}),                         # loops int()
        ("/api/knowledge-graph/relations", {"relation": 42}),        # kg .upper()
    ])
    async def test_no_5xx(self, C, path, body):
        r = await POST(C, path, body)
        assert r.status_code < 500, (path, r.status_code, r.text[:200])


@pytest.mark.asyncio
class TestGapGetHardening:
    """GET-side edge cases found by the query-param probe (r64)."""

    async def test_preview_read_nul_path(self, C):
        """NUL byte in a path crashed pathlib.resolve() -> 500."""
        r = await C.get("/api/preview/read", params={"path": "\x00evil"})
        assert r.status_code < 500, r.text
        assert r.status_code in (200, 404)

    async def test_preview_read_empty_path(self, C):
        """?path= (explicitly empty) resolved to PREVIEW_DIR itself and
        read_text() raised IsADirectoryError -> 500. Now falls back to the
        documented default."""
        r = await C.get("/api/preview/read", params={"path": ""})
        assert r.status_code == 200, r.text

    async def test_preview_read_directory_path(self, C):
        """A directory path must 404, not crash on read_text."""
        r = await C.get("/api/preview/read", params={"path": "."})
        assert r.status_code == 404, r.text

    async def test_preview_read_traversal_still_403(self, C):
        r = await C.get("/api/preview/read", params={"path": "../../etc/passwd"})
        assert r.status_code == 403, r.text

    async def test_profiler_concurrent_reads(self, C):
        """The latency middleware mutates the stats dict on every request;
        reading it while it grew raised 'dictionary changed size during
        iteration' -> 500 under concurrent load. Snapshot iteration fixed."""
        import asyncio

        async def poll():
            r1 = await GET(C, "/api/profiler/endpoints", sort_by="avg_ms", limit=-1)
            r2 = await GET(C, "/api/profiler/summary")
            return r1.status_code < 500 and r2.status_code < 500

        async def traffic(i):
            return (await GET(C, f"/api/engine/loops/{i}")).status_code < 500

        results = await asyncio.gather(
            *[poll() for _ in range(10)], *[traffic(i) for i in range(20)]
        )
        assert all(results), "5xx under concurrent profiler reads"


@pytest.mark.asyncio
class TestGapSharedStateRaces:
    """Sync (threadpool) handlers lazily iterating module-level dicts that
    other threads mutate — reproduced live as a 500 (see r65): seeded 5k
    collab sessions, interleaved create+list; unfixed code 500'd within
    three rounds, fixed code clean across eight."""

    async def test_collab_sessions_race(self, C):
        import asyncio

        async def create(i):
            return (await POST(C, "/api/collab/sessions")).status_code

        async def listing(i):
            return (await GET(C, "/api/collab/sessions")).status_code

        # Seed enough entries that list iteration takes real time.
        for _ in range(4):
            await asyncio.gather(*[create(i) for i in range(250)])
        for round_ in range(3):
            codes = await asyncio.gather(
                *[listing(i) for i in range(30)], *[create(i) for i in range(30)]
            )
            assert all(c < 500 for c in codes), f"race 5xx in round {round_}"

    async def test_control_tower_active_race(self, C):
        """GET /active and /stats iterate the shared runs dict; must snapshot."""
        for _ in range(3):
            r1 = await GET(C, "/api/control-tower/active")
            r2 = await GET(C, "/api/control-tower/stats")
            assert r1.status_code < 500 and r2.status_code < 500


@pytest.mark.asyncio
class TestGapWebsocketHardening:
    """WS fixes (r66). Two bugs found by live churn (20 chatters + 15
    connect/disconnect churners):

    1. collab's broadcast caught only (KeyError, TypeError, …) — but a send
       to an already-dead peer raises starlette's WebSocketDisconnect, which
       is none of those. It escaped the loop and tore down the SENDING
       peer's connection (10 of 20 chatters killed, code 1006).
    2. Once any send fails, starlette marks the socket DISCONNECTED and
       every later receive_text() raises RuntimeError instantly (no await,
       never a WebSocketDisconnect). crdt's message loop caught it with
       `except Exception: log; continue` — a zero-yield spin at 100% CPU
       that starved the whole event loop: handshakes timed out, health
       checks hung, `ps` would not run. The server stayed wedged for
       minutes after every client was gone.
    """

    async def test_collab_broadcast_survives_dead_peer(self):
        """A dead peer in the session must not kill the broadcasting peer."""
        import json as _json

        from starlette.websockets import WebSocketDisconnect

        from backend.routers.collab import CollabSession

        class DeadWS:
            async def send_text(self, data):
                raise WebSocketDisconnect(code=1006)

        class AliveWS:
            def __init__(self):
                self.sent = []

            async def send_text(self, data):
                self.sent.append(data)

        sess = CollabSession("gap_dead_peer")
        dead, alive = DeadWS(), AliveWS()
        sess.connections = {"d": dead, "a": alive}
        sess.peers = {"d": {"id": "d"}, "a": {"id": "a"}}

        await sess.broadcast({"type": "chat"})  # pre-fix: raised out of broadcast

        assert alive.sent, "alive peer did not receive the broadcast"
        assert "d" not in sess.connections, "dead peer not removed"

    async def test_collab_churn_keeps_chatters_alive(self):
        """Live churn: chattering clients must survive peers dying around
        them (pre-fix: the server killed half of them within 18s)."""
        import websockets

        url = f"ws://127.0.0.1:8787/api/collab/sessions/gap_churn_{uuid.uuid4().hex[:6]}/ws"
        dropped = {}

        async def chatter(i):
            try:
                async with websockets.connect(url, open_timeout=10) as ws:
                    await ws.send(json.dumps({"name": f"chatter_{i}"}))
                    for _ in range(60):
                        await ws.send(
                            json.dumps({"type": "chat", "payload": {"message": "x" * 100}})
                        )
                        await asyncio.sleep(0.05)
            except Exception as exc:
                dropped[i] = repr(exc)

        async def churner(i):
            for _ in range(8):
                try:
                    async with websockets.connect(url, open_timeout=10) as ws:
                        await ws.send(json.dumps({"name": f"churn_{i}"}))
                        await ws.recv()
                except Exception:
                    await asyncio.sleep(0.01)

        await asyncio.gather(
            *[chatter(i) for i in range(4)], *[churner(i) for i in range(4)]
        )
        assert not dropped, f"chatters killed by server: {dropped}"

    async def test_crdt_churn_does_not_wedge_server(self):
        """Live wedge canary: churn on a crdt doc must leave the event loop
        responsive — pre-fix, health checks hung forever afterwards."""
        import websockets

        import httpx

        url = f"ws://127.0.0.1:8787/api/crdt/docs/gap_wedge_{uuid.uuid4().hex[:6]}/ws"

        async def churner(i):
            for _ in range(6):
                try:
                    async with websockets.connect(url, open_timeout=10) as ws:
                        await ws.send(json.dumps({"name": f"c{i}"}))
                        await ws.recv()
                except Exception:
                    await asyncio.sleep(0.01)

        async def cursorer(i):
            try:
                async with websockets.connect(url, open_timeout=10) as ws:
                    await ws.send(json.dumps({"name": f"s{i}"}))
                    await ws.recv()
                    for _ in range(40):
                        await ws.send(
                            json.dumps({"type": "cursor", "position": 3, "selection": None})
                        )
                        await asyncio.sleep(0.05)
            except Exception:
                pass

        await asyncio.gather(
            *[churner(i) for i in range(8)], *[cursorer(i) for i in range(3)]
        )
        async with httpx.AsyncClient(timeout=10) as hc:
            r = await hc.get("http://127.0.0.1:8787/api/system/health")
            assert r.status_code == 200, "server wedged after crdt churn"
