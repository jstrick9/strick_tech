"""
Unit Tests — Information Hierarchy Engine (`/api/hierarchy`)
Verifies the compounding 2-Tier Information Hierarchy (Universal Context + Standardized Project IVREN Structure).
"""
from __future__ import annotations
import pytest


class TestInformationHierarchy:
    """Suite testing Tier 1 universal context files and Tier 2 IVREN project hierarchies."""

    def test_status_endpoint_initializes_tier1(self, client):
        r = client.get("/api/hierarchy/status")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["initialized"] is True
        assert "tier1" in data
        assert all(data["tier1"].values())

    def test_get_tier1_files(self, client):
        r = client.get("/api/hierarchy/tier1")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "about_me" in data
        assert "about_my_business" in data
        assert "about_my_voice" in data
        assert "about_my_offers" in data

    def test_save_tier1_files(self, client):
        custom_voice = "# Custom Voice\n- **Style:** 10/10 punchy and highly actionable."
        r = client.post("/api/hierarchy/tier1", json={"about_my_voice": custom_voice})
        assert r.status_code == 200
        assert r.json()["ok"] is True

        r2 = client.get("/api/hierarchy/tier1")
        assert r2.json()["about_my_voice"] == custom_voice

    def test_interview_auto_generator(self, client):
        payload = {
            "name_and_role": "Joshua Strickland\nFounder of Strick Tech",
            "business_and_icp": "Software for individuals and organizations to scale autonomous AI agents.",
            "voice_and_words": "Clear, direct, human-first. Use: leverage, compounding. Avoid: delve, synergy.",
            "offers_and_pricing": "Agentic OS Platform tiers: Free, Pro, and Enterprise version."
        }
        r = client.post("/api/hierarchy/tier1/interview", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "Joshua Strickland" in data["tier1"]["about_me"]
        assert "leverage" in data["tier1"]["about_my_voice"]

    def test_create_project_hierarchy_ivren(self, client):
        payload = {
            "project_id": "newsletter",
            "name": "Weekly AI Insights Newsletter",
            "audience": "Founders and tech enthusiasts",
            "description": "Weekly deep dives into multi-agent systems."
        }
        r = client.post("/api/hierarchy/projects/create", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["project"]["project_id"] == "newsletter"

    def test_get_project_ivren_files(self, client):
        r = client.get("/api/hierarchy/projects/newsletter")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "ivren" in data
        ivren = data["ivren"]
        for section in ["instructions", "voice", "references", "examples", "notes"]:
            assert section in ivren
            assert len(ivren[section]) > 0

    def test_save_project_ivren_section(self, client):
        r = client.post("/api/hierarchy/projects/newsletter/save", json={
            "instructions": "# Updated CLAW Instructions\nAlways output exactly 5 actionable tips."
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True

        r2 = client.get("/api/hierarchy/projects/newsletter")
        assert "output exactly 5 actionable tips" in r2.json()["ivren"]["instructions"]

    def test_append_feedback_note_compounding_loop(self, client):
        r = client.post("/api/hierarchy/projects/newsletter/notes/append", json={
            "note": "Issue #14 had 42% open rate. The storytelling hook about friction tax worked best.",
            "author": "joshua"
        })
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "42% open rate" in data["notes_content"]

    def test_compiled_context_auto_injector(self, client):
        r = client.get("/api/hierarchy/compiled-context?project_id=newsletter")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "<information-hierarchy>" in data["compiled_context"]
        assert "UNIVERSAL BUSINESS CONTEXT" in data["compiled_context"]
        assert "TIER 2 PROJECT DELTA" in data["compiled_context"]
