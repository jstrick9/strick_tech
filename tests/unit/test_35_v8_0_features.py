"""
Unit Tests — Version 8.0 Features (`tests/unit/test_35_v8_0_features.py`)
Tests the remaining pillars of the v8.0 Roadmap:
1. Enterprise RBAC & API token scoping (`/api/rbac/*`)
2. Distributed multi-node Swarm clustering across edge devices (`/api/cluster/*`)
3. Local zero-shot fine-tuning engine (`/api/finetune/*`)
"""
from __future__ import annotations
import pytest


class TestV80Features:
    """Suite validating all 4 strategic capabilities of Agentic OS Platform v8.0."""

    def test_rbac_roles_and_user_assignment(self, client):
        roles_r = client.get("/api/rbac/roles")
        assert roles_r.status_code == 200
        roles_data = roles_r.json()
        assert roles_data["ok"] is True
        assert "admin" in roles_data["roles"]
        assert "Joshua Strickland" in roles_data["creator"]

        assign_r = client.post("/api/rbac/users/assign", json={
            "user_id": "jstrickland",
            "name": "Joshua Strickland",
            "role": "admin",
            "workspace": "global"
        })
        assert assign_r.status_code == 200
        assert assign_r.json()["ok"] is True
        assert assign_r.json()["user"]["role"] == "admin"

    def test_rbac_token_scoping_and_verification(self, client):
        tok_r = client.post("/api/rbac/tokens/create", json={
            "name": "E2E Worker Token",
            "role": "developer",
            "scopes": ["chat:write", "swarm:execute"],
            "expires_in_days": 30
        })
        assert tok_r.status_code == 200
        token = tok_r.json()["token"]
        assert token.startswith("aos_ent_")

        # Verify exact scope check passes
        ver_pass = client.post("/api/rbac/tokens/verify", json={
            "token": token,
            "required_scope": "swarm:execute"
        })
        assert ver_pass.status_code == 200
        assert ver_pass.json()["valid"] is True

        # Verify missing scope check fails cleanly
        ver_fail = client.post("/api/rbac/tokens/verify", json={
            "token": token,
            "required_scope": "secrets:write"
        })
        assert ver_fail.status_code == 200
        assert ver_fail.json()["valid"] is False
        assert "Insufficient scope" in ver_fail.json()["error"]

    def test_cluster_grid_node_join_and_dispatch(self, client):
        status_r = client.get("/api/cluster/status")
        assert status_r.status_code == 200
        assert status_r.json()["ok"] is True

        join_r = client.post("/api/cluster/nodes/join", json={
            "node_id": "edge_worker_m3",
            "name": "Apple M3 Max Worker",
            "host_url": "http://192.168.1.105:8787",
            "capabilities": {"gpu": "Apple Silicon MLX", "vram_gb": 36}
        })
        assert join_r.status_code == 200
        assert join_r.json()["ok"] is True

        # Dispatch task requiring high VRAM
        disp_r = client.post("/api/cluster/dispatch", json={
            "task_prompt": "Run large swarm reasoning grid across 36GB model",
            "required_vram_gb": 32
        })
        assert disp_r.status_code == 200
        disp = disp_r.json()
        assert disp["ok"] is True
        assert disp["dispatched_to_node"] == "edge_worker_m3"

    def test_finetune_reports_real_capability_not_fabricated_success(self, client):
        """Fine-tuning must not claim to have trained a model it cannot train.

        This test previously asserted the FABRICATED behaviour: lora_supported
        always True, and a job returning status "completed" with hardcoded
        metrics (step 150/150, train_loss 0.284) despite no training library
        being installed anywhere in the dependency set. It now asserts the
        endpoint is honest about what this machine can actually do.
        """
        hw_r = client.get("/api/finetune/hardware")
        assert hw_r.status_code == 200
        hw = hw_r.json()
        assert hw["ok"] is True
        # Capability is detected, not asserted.
        assert isinstance(hw["training_available"], bool)
        assert hw["lora_supported"] == hw["training_available"]
        assert isinstance(hw["accelerator_detected"], bool)
        if not hw["training_available"]:
            assert "notice" in hw, "must explain why fine-tuning is unavailable"

        # Dataset preparation works regardless of training capability.
        ds_r = client.post("/api/finetune/datasets/create", json={
            "dataset_id": "v8_lora_ds",
            "name": "Agentic OS Domain Set",
            "source_type": "chat_history"
        })
        assert ds_r.status_code == 200
        assert ds_r.json()["ok"] is True

        job_r = client.post("/api/finetune/jobs/start", json={
            "job_id": "v8_test_lora",
            "dataset_id": "v8_lora_ds",
            "base_model": "llama3.1:8b",
            "epochs": 2
        })
        if not hw["training_available"]:
            # Refuse honestly rather than reporting a successful run.
            assert job_r.status_code == 501
            assert "training backend" in job_r.json()["detail"]
        else:
            assert job_r.status_code == 200
            # A freshly started job has not finished yet.
            assert job_r.json()["job"]["status"] in ("queued", "running")
