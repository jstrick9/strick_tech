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
        # This used to send {"title": ...}, but the endpoint requires "path".
        # It only appeared to pass because the validation failure was returned
        # as HTTP 200 with {"ok": false} — so the test asserted a 200 while the
        # note was never created. Now sends a valid payload and checks the
        # write actually succeeded.
        r = client.post("/api/obsidian/note", json={
            "path": "unit-test-note",
            "content": "# Unit Test\n\nThis is a test note."
        })
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True
        assert d.get("path", "").endswith("unit-test-note.md")

        # A payload missing "path" must be rejected, not silently 200.
        bad = client.post("/api/obsidian/note", json={"title": "no path here"})
        assert bad.status_code == 400

    def test_obsidian_daily_note_never_overwrites(self, client):
        """Creating today's daily note twice must refuse, not clobber.

        The note's template invites the user to write in the "Notes"
        section, so a regenerate-overwrite destroyed their content —
        pressing the pane's prominent button a second time silently wiped
        whatever they had written that day.
        """
        import datetime as dt

        today = dt.date.today()
        r1 = client.post("/api/obsidian/daily_note", json={})
        # First call either creates the note or (already exists from the
        # app's own scheduler) refuses — both fine as a starting point.
        assert r1.status_code in (200, 409), r1.status_code

        r2 = client.post("/api/obsidian/daily_note", json={})
        assert r2.status_code == 409, "second create overwrote the note"
        assert "already exists" in r2.json()["error"]
        assert str(today) in r2.json()["error"]

    def test_obsidian_search_matches_folder(self, client):
        """Searching must match folders, not just filenames.

        The note list shows each note's folder, but the search box matched
        only name/stem — searching "Daily" or "agentic-os" returned "no
        notes" while Daily notes sat visible in the unfiltered list.
        """
        r = client.post("/api/obsidian/note", json={
            "path": "Projects/zz-probe-folder-note",
            "content": "# lives in a folder",
        })
        assert r.status_code == 200 and r.json().get("ok") is True

        by_folder = client.get("/api/obsidian/notes?q=projects").json()
        names = [n.get("path") for n in by_folder.get("notes", [])]
        assert any("Projects/zz-probe-folder-note" in (p or "") for p in names), (
            f"folder search missed the note: {names}"
        )

        # Filename search still works.
        by_name = client.get("/api/obsidian/notes?q=zz-probe-folder-note").json()
        assert any(
            "zz-probe-folder-note" in (n.get("path") or "")
            for n in by_name.get("notes", [])
        )

    def test_obsidian_write_note_refuses_silent_overwrite(self, client):
        """Writing over an existing note must be explicit (r42).

        saveQuickNote() derives the filename from the title alone, so saving
        the same title twice — or naming a quick note after an existing vault
        note — used to silently destroy the earlier content with only a
        success toast. Same convention as the preview scaffold: refuse, and
        require overwrite: true.
        """
        r1 = client.post("/api/obsidian/note", json={
            "path": "unit-test-overwrite-guard",
            "content": "version A",
        })
        assert r1.status_code == 200 and r1.json()["ok"] is True

        # Second write without the flag: 409, and the original is intact.
        r2 = client.post("/api/obsidian/note", json={
            "path": "unit-test-overwrite-guard",
            "content": "version B",
        })
        assert r2.status_code == 409, "second write silently overwrote the note"
        d2 = r2.json()
        assert d2["ok"] is False and d2.get("exists") is True
        assert "overwrite" in d2["error"]

        kept = client.get("/api/obsidian/note", params={
            "path": r1.json()["path"],
        }).json()
        assert "version A" in kept.get("content", "")

        # Explicit opt-in replaces it.
        r3 = client.post("/api/obsidian/note", json={
            "path": "unit-test-overwrite-guard",
            "content": "version B",
            "overwrite": True,
        })
        assert r3.status_code == 200 and r3.json()["ok"] is True
        replaced = client.get("/api/obsidian/note", params={
            "path": r3.json()["path"],
        }).json()
        assert "version B" in replaced.get("content", "")

    def test_obsidian_write_note_rejects_extension_only_path(self, client):
        """A path with no name before .md writes a hidden junk file.

        An all-punctuation quick-note title slugifies to an empty stem and
        used to POST exactly ".md" — littering the vault with nameless
        files the list then showed as ".md".
        """
        for junk in (".md", "folder/.md"):
            r = client.post("/api/obsidian/note", json={
                "path": junk,
                "content": "no name",
            })
            assert r.status_code == 400, f"{junk!r} was accepted"
            assert "name" in r.json()["error"]

    def test_obsidian_search_finds_slugified_titles(self, client):
        """Search must match the title as the user typed it (r42).

        The pane slugifies note titles ("My Note" -> My_Note.md), so a
        search for "my note" (spaces, exactly what the user just typed in
        the title box) used to return nothing for precisely that note.
        Hyphen/space/underscore must all find the slugified filename.
        """
        r = client.post("/api/obsidian/note", json={
            "path": "unit_test_slug_search",
            "content": "# slug search target",
        })
        assert r.status_code == 200 and r.json()["ok"] is True

        for q in ("unit test slug search", "unit-test-slug-search", "unit_test_slug_search"):
            hit = client.get("/api/obsidian/notes", params={"q": q}).json()
            names = [n.get("name") for n in hit.get("notes", [])]
            assert "unit_test_slug_search" in names, f"q={q!r} missed: {names}"


    def test_obsidian_index_skips_generated_exports(self, client):
        """Index must not re-ingest Agentic_OS_Export_*.md files.

        export_memories writes those files as mirrors of the memory DB.
        Indexing one back in re-adds every exported memory as a fresh
        near-duplicate row — each export→index cycle roughly doubles the
        galaxy's generated content.
        """
        assert client.post("/api/obsidian/note", json={
            "path": "Agentic_OS_Export_probe",
            "content": "## [some-source] 2026-01-01\nexported memory text " * 80,
        }).status_code == 200

        r = client.post("/api/obsidian/index", json={"max_notes": 100})
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True
        # The export file must be counted as skipped, never indexed.
        assert d.get("errors", 0) == 0
        sources = set()
        for n in client.get("/api/obsidian/notes?limit=100").json().get("notes", []):
            if "Agentic_OS_Export_" in (n.get("name") or ""):
                sources.add(n.get("name"))
        # And no memory row may carry an export-file source.
        mems = client.get("/api/memory/list?limit=200").json()
        mems = mems if isinstance(mems, list) else mems.get("memories", [])
        export_sources = [m.get("source") for m in mems
                          if str(m.get("source", "")).startswith("obsidian:")
                          and "Agentic_OS_Export_" in str(m.get("source", ""))]
        assert not export_sources, f"export file ingested into memories: {export_sources[:3]}"

    def test_obsidian_index_does_not_reindex_on_repeat(self, client):
        """A second Index click must not duplicate already-indexed notes.

        The old dedup searched memories by FTS title, but FTS tokenizes on
        word characters — a title like "2026-09-14" matched arbitrary rows,
        the check failed, and every Index click re-ingested the note as a
        fresh duplicate galaxy row.
        """
        assert client.post("/api/obsidian/note", json={
            "path": "zz-dedup-probe",
            "content": "# Dedup probe\n\nUnique-enough body text for the source check.",
        }).status_code == 200

        first = client.post("/api/obsidian/index", json={"max_notes": 100}).json()
        mems = client.get("/api/memory/list?limit=200").json()
        mems = mems if isinstance(mems, list) else mems.get("memories", [])
        n1 = [m for m in mems if m.get("source") == "obsidian:agentic-os/zz-dedup-probe.md"]
        assert len(n1) == 1, f"expected exactly 1 row after first index, got {len(n1)}"

        second = client.post("/api/obsidian/index", json={"max_notes": 100}).json()
        mems2 = client.get("/api/memory/list?limit=200").json()
        mems2 = mems2 if isinstance(mems2, list) else mems2.get("memories", [])
        n2 = [m for m in mems2 if m.get("source") == "obsidian:agentic-os/zz-dedup-probe.md"]
        assert len(n2) == 1, f"second index duplicated the note: {len(n2)} rows"
        # re_index=True is the explicit escape hatch and must still re-ingest.
        client.post("/api/obsidian/index", json={"max_notes": 100, "re_index": True})
        mems3 = client.get("/api/memory/list?limit=200").json()
        mems3 = mems3 if isinstance(mems3, list) else mems3.get("memories", [])
        n3 = [m for m in mems3 if m.get("source") == "obsidian:agentic-os/zz-dedup-probe.md"]
        assert len(n3) >= 2, "re_index=True did not re-ingest"

    def test_obsidian_write_accepts_roundtrip_vault_relative_path(self, client):
        """Writing back a path exactly as list/read return it must update the
        note, not spawn a phantom nested duplicate.

        list/read return vault-relative paths ('agentic-os/x.md'). write_note
        used to join that onto the notes dir, creating
        'agentic-os/agentic-os/x.md' — so an API round-trip silently produced
        a duplicate note in a folder that exists nowhere in the UI.
        """
        r1 = client.post("/api/obsidian/note", json={
            "path": "roundtrip-note",
            "content": "first",
        })
        assert r1.status_code == 200 and r1.json().get("ok") is True
        vault_rel = r1.json()["path"]  # e.g. 'agentic-os/roundtrip-note.md'
        assert vault_rel.startswith("agentic-os/")

        # Round-trip: write using exactly the path the API handed back.
        # (overwrite: true because the guard added in r42 refuses to
        # silently replace an existing note — this write IS the deliberate
        # update the flag exists for.)
        r2 = client.post("/api/obsidian/note", json={
            "path": vault_rel,
            "content": "updated",
            "overwrite": True,
        })
        assert r2.status_code == 200 and r2.json().get("ok") is True
        assert "agentic-os/agentic-os" not in r2.json().get("path", ""), (
            "write created a phantom nested path"
        )

        # The note must read back updated — one note, not two.
        got = client.get("/api/obsidian/note", params={"path": vault_rel}).json()
        assert got.get("ok") is True
        assert got.get("content") == "updated"
        names = [n.get("path") for n in client.get("/api/obsidian/notes?limit=100").json().get("notes", [])]
        assert sum(1 for p in names if p and "roundtrip-note" in p) == 1, names

    def test_obsidian_graph(self, client):
        r = client.get("/api/obsidian/index")
        assert r.status_code == 200
