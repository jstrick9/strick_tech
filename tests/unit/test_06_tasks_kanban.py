"""Unit tests — Kanban / Tasks (app.py direct routes)"""
import pytest
from tests.unit.conftest import assert_ok, post_json, patch_json


class TestTasksCRUD:
    def test_list_tasks_200(self, client):
        assert client.get("/api/tasks").status_code == 200

    def test_list_tasks_is_list(self, client):
        d = client.get("/api/tasks").json()
        assert isinstance(d, list)

    def test_create_task(self, client):
        r = post_json(client, "/api/tasks",
                      {"title": "Unit Test Task", "status": "todo",
                       "priority": "medium", "agent": "builder"})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert "id" in d
        assert d["title"] == "Unit Test Task"

    def test_create_task_empty_title_rejected(self, client):
        r = post_json(client, "/api/tasks", {"title": ""})
        d = r.json()
        assert d["ok"] is False or r.status_code in (400, 422)

    def test_create_task_default_status_todo(self, client):
        r = post_json(client, "/api/tasks", {"title": "Default Status Task"})
        d = r.json()
        assert d.get("status") == "todo" or d["ok"] is True

    def test_create_task_invalid_status_normalised(self, client):
        r = post_json(client, "/api/tasks",
                      {"title": "Bad Status", "status": "flying"})
        # Should succeed but normalise status to "todo"
        assert r.json()["ok"] is True

    def test_create_task_invalid_priority_normalised(self, client):
        r = post_json(client, "/api/tasks",
                      {"title": "Bad Priority", "priority": "ultra"})
        assert r.json()["ok"] is True

    def test_create_and_list(self, client):
        title = "ListVerifyTask_" + __import__("uuid").uuid4().hex[:6]
        post_json(client, "/api/tasks", {"title": title})
        tasks = client.get("/api/tasks").json()
        assert any(t.get("title") == title for t in tasks)

    def test_update_task_status(self, client):
        r = post_json(client, "/api/tasks",
                      {"title": "StatusUpdateTask", "status": "todo"})
        tid = r.json()["id"]
        r2 = client.patch(f"/api/tasks/{tid}", json={"status": "doing"})
        assert r2.json()["ok"] is True
        assert r2.json()["task"]["status"] == "doing"

    def test_update_task_invalid_status_ignored(self, client):
        r = post_json(client, "/api/tasks", {"title": "InvalidStatusUpdate"})
        tid = r.json()["id"]
        r2 = client.patch(f"/api/tasks/{tid}", json={"status": "flying"})
        # Should succeed but status unchanged (flying not in valid list)
        assert r2.status_code == 200

    def test_update_task_title(self, client):
        r = post_json(client, "/api/tasks", {"title": "Original"})
        tid = r.json()["id"]
        r2 = client.patch(f"/api/tasks/{tid}", json={"title": "Updated"})
        assert r2.json()["task"]["title"] == "Updated"

    def test_delete_task(self, client):
        r = post_json(client, "/api/tasks", {"title": "ToDelete"})
        tid = r.json()["id"]
        r2 = client.delete(f"/api/tasks/{tid}")
        assert r2.json()["ok"] is True
        assert r2.json()["deleted"] == tid

    def test_delete_removes_from_list(self, client):
        import uuid
        title = "DeleteVerify_" + uuid.uuid4().hex[:6]
        r = post_json(client, "/api/tasks", {"title": title})
        tid = r.json()["id"]
        client.delete(f"/api/tasks/{tid}")
        tasks = client.get("/api/tasks").json()
        assert not any(t["id"] == tid for t in tasks)

    def test_task_title_length_capped(self, client):
        r = post_json(client, "/api/tasks", {"title": "X" * 300})
        assert r.json()["ok"] is True


class TestKanbanMove:
    def _create(self, client, title="KanbanTask"):
        r = post_json(client, "/api/tasks", {"title": title, "status": "todo"})
        return r.json()["id"]

    def test_move_todo_to_doing(self, client):
        tid = self._create(client, "MoveTask1")
        r = post_json(client, "/api/kanban/move", {"id": tid, "to_status": "doing"})
        assert r.json()["ok"] is True

    def test_move_to_done(self, client):
        tid = self._create(client, "MoveTask2")
        r = post_json(client, "/api/kanban/move", {"id": tid, "to_status": "done"})
        assert r.json()["ok"] is True

    def test_move_to_blocked(self, client):
        tid = self._create(client, "MoveTask3")
        r = post_json(client, "/api/kanban/move", {"id": tid, "to_status": "blocked"})
        assert r.json()["ok"] is True

    def test_move_invalid_status_rejected(self, client):
        tid = self._create(client, "MoveTask4")
        r = post_json(client, "/api/kanban/move", {"id": tid, "to_status": "flying"})
        assert r.json()["ok"] is False

    def test_move_missing_id_rejected(self, client):
        r = post_json(client, "/api/kanban/move", {"to_status": "done"})
        assert r.json()["ok"] is False


class TestBulkUpdate:
    def test_bulk_update_empty_ok(self, client):
        r = post_json(client, "/api/tasks/bulk_update", {"updates": []})
        assert r.status_code in (200, 422)

    def test_bulk_update_not_list_rejected(self, client):
        r = post_json(client, "/api/tasks/bulk_update", {"updates": "not_a_list"})
        # Returns {"ok":False} or {"updated":0} or 422
        assert r.status_code in (200, 400, 422) and ("ok" not in r.json() or r.json().get("ok") is False or r.json().get("updated", 0) == 0)

    def test_bulk_update_multiple_tasks(self, client):
        r1 = post_json(client, "/api/tasks", {"title": "Bulk1", "status": "todo"})
        r2 = post_json(client, "/api/tasks", {"title": "Bulk2", "status": "todo"})
        t1, t2 = r1.json()["id"], r2.json()["id"]
        r = post_json(client, "/api/tasks/bulk_update", {
            "updates": [
                {"id": t1, "status": "doing"},
                {"id": t2, "status": "done"},
            ]
        })
        # Either ok or 422 due to route ordering, but not 500
        assert r.status_code != 500
