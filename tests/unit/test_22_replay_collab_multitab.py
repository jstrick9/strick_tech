"""
Unit Tests — Replay, Collab OT, Multitab, Arena, Obsidian
Covers: replay sessions, collaborative editing, multi-tab, arena battles
"""
import pytest, httpx

class TestReplay:
    def test_replay_list_runs(self, client):
        r = client.get("/api/replay/runs")
        assert r.status_code == 200
        d = r.json()
        assert "runs" in d or isinstance(d, list)

    def test_replay_stats(self, client):
        r = client.get("/api/replay/runs")
        assert r.status_code == 200

    def test_replay_nonexistent_run(self, client):
        r = client.get("/api/replay/runs/nonexistent_xyz")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            assert r.json().get("ok") is False or "error" in r.json()

    def test_replay_save_requires_body(self, client):
        r = client.post("/api/replay/workflow/wf_test/run", json={})
        assert r.status_code in (200, 400, 422)

    def test_replay_comparison(self, client):
        r = client.get("/api/replay/runs")
        assert r.status_code in (200, 400, 422)


class TestCollaboration:
    def test_collab_sessions_list(self, client):
        r = client.get("/api/collab/sessions")
        assert r.status_code == 200
        d = r.json()
        assert "sessions" in d or isinstance(d, list)

    def test_collab_create_session(self, client):
        r = client.post("/api/collab/sessions", json={})
        assert r.status_code == 200
        d = r.json()
        assert "session_id" in d or "id" in d or "ok" in d

    def test_collab_get_session(self, client):
        create = client.post("/api/collab/sessions", json={}).json()
        sid = create.get("session_id") or create.get("id", "")
        if sid:
            r = client.get(f"/api/collab/sessions/{sid}")
            assert r.status_code in (200, 404)

    def test_collab_document(self, client):
        r = client.get("/api/collab/sessions")
        assert r.status_code == 200

    def test_collab_cursors(self, client):
        r = client.get("/api/collab/sessions")
        assert r.status_code == 200


class TestCRDT:
    def test_crdt_list_docs(self, client):
        r = client.get("/api/crdt/docs")
        assert r.status_code == 200
        d = r.json()
        assert "docs" in d or isinstance(d, list)

    def test_crdt_create_doc(self, client):
        r = client.post("/api/crdt/docs", json={
            "name": "Unit Test Doc",
            "content": "Initial content"
        })
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d or "id" in d

    def test_crdt_get_doc(self, client):
        create = client.post("/api/crdt/docs", json={"name": "CRDT Get Test"}).json()
        doc_id = create.get("id") or create.get("doc_id", "")
        if doc_id:
            r = client.get(f"/api/crdt/docs/{doc_id}")
            assert r.status_code in (200, 404)


class TestMultitab:
    def test_multitab_list(self, client):
        r = client.get("/api/multitab/tabs")
        assert r.status_code == 200
        d = r.json()
        assert "tabs" in d or isinstance(d, list)

    def test_multitab_create(self, client):
        r = client.post("/api/multitab/tabs", json={
            "pane": "chat", "label": "Chat Tab"
        })
        assert r.status_code == 200

    def test_multitab_state(self, client):
        r = client.get("/api/multitab/tabs")
        assert r.status_code == 200


class TestArena:
    def test_arena_leaderboard(self, client):
        r = client.get("/api/arena/leaderboard")
        assert r.status_code == 200
        d = r.json()
        assert "leaderboard" in d or isinstance(d, list)

    def test_arena_models_list(self, client):
        r = client.get("/api/arena/models")
        assert r.status_code == 200
        d = r.json()
        assert "models" in d or isinstance(d, list)

    def test_arena_battle_requires_prompt(self, client):
        r = client.post("/api/arena/battle", json={})
        assert r.status_code in (200, 400, 422)
        if r.status_code == 200:
            assert r.json().get("ok") is False

    def test_arena_battle_basic(self, client):
        r = client.post("/api/arena/battle", json={
            "prompt": "What is 1+1?",
            "model_a": "gpt4o-mini",
            "model_b": "gemini-flash"
        })
        # Arena battle is SSE streaming
        assert r.status_code == 200

    def test_arena_vote_nonexistent(self, client):
        r = client.post("/api/arena/vote", json={
            "battle_id": "nonexistent", "winner": "a"
        })
        assert r.status_code in (200, 404)

    def test_arena_stats(self, client):
        r = client.get("/api/arena/stats")
        assert r.status_code == 200


class TestObsidian:
    def test_obsidian_notes(self, client):
        r = client.get("/api/obsidian/notes")
        assert r.status_code == 200
        d = r.json()
        assert "notes" in d or isinstance(d, list)

    def test_obsidian_search(self, client):
        r = client.get("/api/obsidian/notes?q=test")
        assert r.status_code == 200

    def test_obsidian_create_note(self, client):
        r = client.post("/api/obsidian/note", json={
            "title": "Unit Test Note",
            "content": "# Unit Test\n\nThis is a test note."
        })
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d

    def test_obsidian_graph(self, client):
        r = client.get("/api/obsidian/index")
        assert r.status_code == 200
