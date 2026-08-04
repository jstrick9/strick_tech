"""
Unit Tests — Version 9.0 Features (`tests/unit/test_36_v9_0_features.py`)
Tests the remaining pillars of the v9.0 Roadmap:
1. Autonomous zero-day vulnerability bounty hunter & self-patching security scanner (`/api/security/bounty-hunter/*`)
2. Quantum-resistant hybrid post-quantum cryptography (`/api/pqc/*`)
"""
from __future__ import annotations
import pytest


class TestV90Features:
    """Suite validating all 4 strategic capabilities of Agentic OS Platform v9.0."""

    def test_bounty_hunter_scan_and_autopatch(self, client):
        cfg_r = client.get("/api/security/bounty-hunter/config")
        assert cfg_r.status_code == 200
        cfg = cfg_r.json()
        assert cfg["ok"] is True
        assert "Joshua Strickland" in cfg["creator"]
        assert cfg["self_patching_enabled"] is True

        scan_r = client.post("/api/security/bounty-hunter/scan", json={
            "target_url": "http://127.0.0.1:8787",
            "codebase_path": "backend/routers",
            "fuzzing_intensity": "medium"
        })
        assert scan_r.status_code == 200
        scan_data = scan_r.json()
        assert scan_data["ok"] is True
        scan_id = scan_data["scan_id"]
        assert len(scan_data["scan"]["findings"]) > 0
        target_vuln = scan_data["scan"]["findings"][0]["vulnerability_id"]

        # Trigger autonomous self-patching
        patch_r = client.post(f"/api/security/bounty-hunter/scans/{scan_id}/autopatch", json={
            "vulnerability_id": target_vuln,
            "apply_to_codebase": True
        })
        assert patch_r.status_code == 200
        patch = patch_r.json()
        assert patch["ok"] is True
        assert patch["patched"] is True
        assert "patch_diff" in patch

        # Check leaderboard
        lb_r = client.get("/api/security/bounty-hunter/leaderboard")
        assert lb_r.status_code == 200
        assert lb_r.json()["ok"] is True

    def test_post_quantum_cryptography_kem_and_vault(self, client):
        algo_r = client.get("/api/pqc/algorithms")
        assert algo_r.status_code == 200
        # The algorithm list still NAMES these (the UI shows what a real
        # implementation would offer), but every operational response now
        # declares itself simulated — see test_85.
        assert any("Kyber-1024" in a for a in algo_r.json()["kem_algorithms"])

        gen_r = client.post("/api/pqc/keypair/generate", json={
            "algorithm": "ML-KEM-1024-X25519-Hybrid",
            "key_name": "Test PQC Master Key"
        })
        assert gen_r.status_code == 200
        gen = gen_r.json()
        assert gen["ok"] is True
        kid = gen["keypair_id"]
        pub_key = gen["public_key_b64"]

        # Encapsulate
        encap_r = client.post("/api/pqc/kem/encapsulate", json={"public_key_b64": pub_key})
        assert encap_r.status_code == 200
        encap = encap_r.json()
        assert encap["ok"] is True
        shared_secret = encap["shared_secret_b64"]
        ct = encap["ciphertext_b64"]

        # Decapsulate
        decap_r = client.post("/api/pqc/kem/decapsulate", json={
            "keypair_id": kid,
            "ciphertext_b64": ct
        })
        assert decap_r.status_code == 200
        assert decap_r.json()["ok"] is True
        assert decap_r.json()["shared_secret_b64"] == shared_secret

        # Vault PQC encrypt — Module 21: this is now REFUSED by default.
        #
        # This assertion used to require "Kyber-1024" in security_guarantee,
        # i.e. the test was ENFORCING a false cryptographic claim. The module
        # implements SHA3 and an XOR mask; a stored value is recoverable from
        # the public keypair_id alone (demonstrated in test_85). Vault
        # operations therefore refuse unless AGENTIC_PQC_DEMO=1, so an operator
        # cannot put a live credential through a function offering no
        # protection.
        enc_vault = client.post("/api/pqc/vault/encrypt", json={
            "keypair_id": kid,
            "secret_name": "PQC_TEST_SECRET",
            "secret_payload": "super_secret_post_quantum_value"
        })
        assert enc_vault.status_code == 501, "PQC vault encryption should be gated"
        assert "SIMULATION" in enc_vault.json()["detail"]
