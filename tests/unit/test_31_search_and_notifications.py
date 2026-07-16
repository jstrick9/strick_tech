"""
Unit Tests — Features (Global Search across all features & Notification Center UI backend)
Covers: /api/search/global, /api/notifications/list, /api/notifications/unread-count, mark-read, create, clear
"""
from __future__ import annotations
import pytest


class TestSearchAndNotifications:
    """Suite testing Global Search and Notification Center features."""

    def test_global_search_empty_query_returns_top_panes(self, client):
        r = client.get("/api/search/global?q=")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "results" in data
        assert len(data["results"]) > 0
        assert data["results"][0]["category"] == "Navigation"

    def test_global_search_query_swarm(self, client):
        r = client.get("/api/search/global?q=swarm")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert len(data["results"]) > 0
        assert any("swarm" in item["title"].lower() or "swarm" in item["description"].lower() for item in data["results"])

    def test_global_search_query_marketplace_skills(self, client):
        r = client.get("/api/search/global?q=github")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert len(data["results"]) > 0
        assert any("github" in item["title"].lower() or "github" in item["description"].lower() for item in data["results"])

    def test_list_notifications_default(self, client):
        r = client.get("/api/notifications/list")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "count" in data
        assert "unread_count" in data
        assert "notifications" in data
        assert isinstance(data["notifications"], list)

    def test_unread_count(self, client):
        r = client.get("/api/notifications/unread-count")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert isinstance(data["unread_count"], int)

    def test_create_and_mark_read_notification(self, client):
        # Create
        r = client.post("/api/notifications/create", json={
            "title": "Test Notif",
            "message": "This is an automated test alert",
            "type": "warning",
            "link": "kanban"
        })
        assert r.status_code == 200
        notif = r.json()["notification"]
        notif_id = notif["id"]
        assert notif["read"] is False

        # Mark read
        r2 = client.post(f"/api/notifications/mark-read/{notif_id}")
        assert r2.status_code == 200
        assert r2.json()["notification"]["read"] is True

    def test_mark_all_read(self, client):
        r = client.post("/api/notifications/mark-all-read")
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # Check unread count is now 0
        r2 = client.get("/api/notifications/unread-count")
        assert r2.json()["unread_count"] == 0

    def test_delete_and_clear_notifications(self, client):
        r = client.post("/api/notifications/create", json={
            "title": "To Delete",
            "message": "Temporary item",
            "type": "info"
        })
        notif_id = r.json()["notification"]["id"]

        del_r = client.delete(f"/api/notifications/clear/{notif_id}")
        assert del_r.status_code == 200
        assert del_r.json()["ok"] is True

        clear_r = client.delete("/api/notifications/clear-all")
        assert clear_r.status_code == 200
        assert clear_r.json()["ok"] is True
