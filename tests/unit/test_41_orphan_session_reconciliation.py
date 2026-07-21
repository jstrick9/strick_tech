"""
Unit Test Suite 41 — Self-Healing Orphan Session Reconciliation
Verifies that any chat_sessions entry showing 0 messages (e.g. from ID mismatches or legacy log formats)
is automatically reconciled with its matching chat_log entries by exact title/prefix on GET /api/sessions
and GET /api/sessions/{session_id}/messages.
"""

import sqlite3
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.app import app
from backend.services.memory_db import get_conn


def test_reconciles_orphan_sessions_and_updates_message_count():
    client = TestClient(app)
    con = get_conn()
    try:
        # Create a legacy chat_log entry under an old UUID
        old_uuid = "legacy-uuid-9999-8888"
        con.execute(
            "INSERT INTO chat_log(session_id, agent, role, message, tokens, cost, model) VALUES (?,?,?,?,?,?,?)",
            (old_uuid, "default", "user", "Explain Greek Mythology in detail to me", 15, 0.0, "claude"),
        )
        con.execute(
            "INSERT INTO chat_log(session_id, agent, role, message, tokens, cost, model) VALUES (?,?,?,?,?,?,?)",
            (old_uuid, "default", "assistant", "Greek mythology consists of ancient stories...", 150, 0.0, "claude"),
        )
        # Create a named chat_sessions row under a different ID showing 0 message_count
        new_sid = "named-sid-1111-2222"
        con.execute(
            "INSERT INTO chat_sessions(id, name, agent_id, message_count, description) VALUES (?,?,?,0,?)",
            (new_sid, "Explain Greek Mythology", "default", "General"),
        )
        con.commit()
    finally:
        con.close()

    # 1. Trigger list_sessions (GET /api/sessions) which runs _reconcile_orphan_sessions
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    data = resp.json()
    sessions = data.get("sessions", [])
    matched = next((s for s in sessions if s["id"] == new_sid), None)
    assert matched is not None, "Named session must appear in sessions list"
    assert matched["message_count"] == 2, f"Orphan messages must be reconciled and count updated to 2, got {matched['message_count']}"

    # 2. Trigger session_messages (GET /api/sessions/{id}/messages)
    m_resp = client.get(f"/api/sessions/{new_sid}/messages")
    assert m_resp.status_code == 200
    m_data = m_resp.json()
    assert m_data.get("ok") is True
    messages = m_data.get("messages", [])
    assert len(messages) == 2, f"Must return exactly 2 reconciled messages, got {len(messages)}"
    assert messages[0]["role"] == "user"
    assert "Greek Mythology" in messages[0]["message"]
    assert messages[0]["model"] == "claude"
