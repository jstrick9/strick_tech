"""
Unit Tests — Version 7.0 Features (`tests/unit/test_34_v7_0_features.py`)
Tests all 4 pillars of the v7.0 Roadmap:
1. Plugin/skill marketplace (community submissions & ratings) via `/api/marketplace/community/*`
2. Multi-user collaboration with live CRDT synchronization via `/api/collab/rooms/*`
3. Mobile app bridge (Expo & React Native) via `/api/mobile/*`
4. Cloud sync (self-hosted encrypted vault sync with AES-256) via `/api/sync/*`
"""
from __future__ import annotations
import pytest


class TestV70Features:
    """Suite validating all 4 strategic capabilities of Agentic OS Platform v7.0."""

    def test_marketplace_community_submission_and_listing(self, client):
        # Submit community skill pack
        sub_r = client.post("/api/marketplace/community/submit", json={
            "id": "community-dev-pack",
            "name": "Community Dev Tools",
            "description": "High-leverage developer shortcuts submitted by community.",
            "author": "Joshua Strickland",
            "skills": [{"id": "quick_refactor", "name": "Quick Refactor", "prompt": "Refactor: {{input}}"}]
        })
        assert sub_r.status_code == 200
        sub_data = sub_r.json()
        assert sub_data["ok"] is True
        assert sub_data["pack_id"] == "community-dev-pack"

        # List community packs
        list_r = client.get("/api/marketplace/community/list")
        assert list_r.status_code == 200
        list_data = list_r.json()
        assert list_data["ok"] is True
        assert any(p["id"] == "community-dev-pack" for p in list_data["packs"])

    def test_collab_active_rooms_and_join(self, client):
        # Create a collab room first
        create_r = client.post("/api/collab/sessions")
        assert create_r.status_code == 200
        sid = create_r.json()["session_id"]

        # Join the room
        join_r = client.post(f"/api/collab/rooms/{sid}/join", json={
            "peer_id": "peer_test_joshua",
            "name": "Joshua Strickland",
            "color": "#8b5cf6"
        })
        assert join_r.status_code == 200
        join_data = join_r.json()
        assert join_data["ok"] is True
        assert join_data["session_id"] == sid
        assert "snapshot" in join_data

        # Verify active rooms list
        active_r = client.get("/api/collab/rooms/active")
        assert active_r.status_code == 200
        active_data = active_r.json()
        assert active_data["ok"] is True
        assert active_data["total_peers"] >= 1

    def test_mobile_bridge_config_and_manifest(self, client):
        # Config check
        cfg_r = client.get("/api/mobile/config")
        assert cfg_r.status_code == 200
        cfg = cfg_r.json()
        assert cfg["ok"] is True
        assert cfg["version"] == "7.0.0"
        assert "Joshua Strickland" in cfg["creator"]
        assert "Free" in cfg["editions_supported"]

        # Manifest check
        man_r = client.get("/api/mobile/manifest")
        assert man_r.status_code == 200
        man = man_r.json()
        assert man["ok"] is True
        assert man["expo"]["slug"] == "agentic-os-mobile"
        assert man["expo"]["ios"]["bundleIdentifier"] == "com.stricktech.agenticos"

    def test_mobile_push_token_registration(self, client):
        r = client.post("/api/mobile/push-register", json={
            "token": "expo-push-token-test-12345",
            "platform": "ios",
            "device_name": "iPhone 16 Pro",
            "user_id": "joshua"
        })
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["device_count"] >= 1

        dev_r = client.get("/api/mobile/devices")
        assert dev_r.status_code == 200
        assert any(d["token"] == "expo-push-token-test-12345" for d in dev_r.json()["devices"])

    def test_cloud_sync_status(self, client):
        r = client.get("/api/sync/status")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "Joshua Strickland" in data["creator"]
        assert "sync_target" in data["status"]

    def test_cloud_sync_export_and_import_encrypted_vault(self, client):
        # Export encrypted
        export_r = client.post("/api/sync/export-encrypted", json={
            "passphrase": "test-sync-passphrase-999",
            "include_db": True,
            "include_hierarchy": True
        })
        assert export_r.status_code == 200
        export_data = export_r.json()
        assert export_data["ok"] is True
        assert "encrypted_bundle" in export_data
        bundle = export_data["encrypted_bundle"]
        assert len(bundle) > 50

        # Import encrypted
        import_r = client.post("/api/sync/import-encrypted", json={
            "encrypted_bundle": bundle,
            "passphrase": "test-sync-passphrase-999"
        })
        assert import_r.status_code == 200
        import_data = import_r.json()
        assert import_data["ok"] is True
        assert import_data["restored_hierarchy_files"] >= 0
