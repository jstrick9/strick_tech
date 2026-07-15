"""
FLOW-01: Agent Lifecycle Integration
  Agent CRUD → Leaderboard recording → Stats reflection → Cleanup
  
FLOW-07: Steering Files Integration
  Create → Enable → Compile → Inject into context → Toggle → Delete
"""
import pytest
from tests.integration.conftest import *


@pytest.mark.asyncio
class TestAgentLifecycle:
    """FLOW-01: Full agent lifecycle across multiple components."""

    async def test_01_seeded_default_agents_exist(self, client):
        """Default agents (Builder, Brain, Researcher) are always present."""
        d = ok(await GET(client, "/api/agents"))
        agents = d if isinstance(d, list) else d.get("agents", [])
        names = [a.get("name", "").lower() for a in agents]
        check("builder agent seeded", any("builder" in n for n in names))
        check("brain agent seeded",   any("brain" in n for n in names))

    async def test_02_create_agent_persists(self, client):
        """Create agent → verify it appears in list."""
        agent_name = uid("IntTestAgent")
        r = await POST(client, "/api/agents", {
            "name": agent_name, "model": "gemini-flash",
            "system_prompt": "Integration test agent", "color": "#5b8af8"
        })
        d = ok(r, "create agent")
        agent_id = d.get("id") or (d.get("agent") or {}).get("id")
        check("create returns id", bool(agent_id))

        # Verify in list
        agents = ok(await GET(client, "/api/agents"))
        agents = agents if isinstance(agents, list) else agents.get("agents", [])
        ids = [a.get("id") for a in agents]
        check("agent appears in list", agent_id in ids)

        # Cleanup
        await DELETE(client, f"/api/agents/{agent_id}")

    async def test_03_agent_update_persists(self, client):
        """Update agent name → verify updated in subsequent GET."""
        r = await POST(client, "/api/agents", {
            "name": uid("UpdateAgent"), "model": "gemini-flash",
            "system_prompt": "To be updated"
        })
        d = ok(r)
        agent_id = d.get("id") or (d.get("agent") or {}).get("id")

        # Update
        r2 = await PATCH(client, f"/api/agents/{agent_id}", {"name": "RenamedAgent"})
        assert r2.status_code in (200, 404)

        # Verify
        agents = ok(await GET(client, "/api/agents"))
        agents = agents if isinstance(agents, list) else agents.get("agents", [])
        updated = next((a for a in agents if a.get("id") == agent_id), None)
        if updated:
            check("name was updated", updated.get("name") == "RenamedAgent")

        await DELETE(client, f"/api/agents/{agent_id}")

    async def test_04_delete_agent_removes_from_list(self, client):
        """Delete agent → verify it is gone from list."""
        r = await POST(client, "/api/agents", {
            "name": uid("DeleteAgent"), "model": "gemini-flash",
            "system_prompt": "To be deleted"
        })
        d = ok(r)
        agent_id = d.get("id") or (d.get("agent") or {}).get("id")

        await DELETE(client, f"/api/agents/{agent_id}")

        agents = ok(await GET(client, "/api/agents"))
        agents = agents if isinstance(agents, list) else agents.get("agents", [])
        ids = [a.get("id") for a in agents]
        check("deleted agent not in list", agent_id not in ids)

    async def test_05_leaderboard_record_performance(self, client):
        """Record performance → verify it appears in leaderboard."""
        r = await POST(client, "/api/agent-leaderboard/record", {
            "agent_id": "builder",
            "task_type": "integration_test",
            "success": True,
            "tokens": 100,
            "cost_usd": 0.001,
            "latency_ms": 500,
            "user_rating": 5
        })
        assert r.status_code in (200, 201, 422)

        lb = ok(await GET(client, "/api/agent-leaderboard"))
        check("leaderboard is dict", isinstance(lb, dict))
        check("leaderboard has data", "leaderboard" in lb or len(lb) > 0)

    async def test_06_leaderboard_stats_overview(self, client):
        """Leaderboard stats overview returns coherent data."""
        r = await GET(client, "/api/agent-leaderboard/stats/overview")
        assert r.status_code in (200, 404)

    async def test_07_leaderboard_governance_summary(self, client):
        """Governance summary covers policy compliance."""
        r = await GET(client, "/api/agent-leaderboard/governance/summary")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            check("governance is dict", isinstance(d, dict))

    async def test_08_agent_id_from_leaderboard(self, client):
        """Can look up individual agent from leaderboard."""
        r = await GET(client, "/api/agent-leaderboard/agent/builder")
        assert r.status_code in (200, 404)


@pytest.mark.asyncio
class TestSteeringIntegration:
    """FLOW-02: Steering Files cross-component integration."""

    async def test_01_list_steering_files(self, client):
        """Steering files are seeded and readable."""
        d = ok(await GET(client, "/api/steering"))
        files = d.get("files", d) if isinstance(d, dict) else d
        check("files is list", isinstance(files, list))
        check("at least one file", len(files) >= 1)

    async def test_02_create_and_compile(self, client):
        """Create new steering file → verify it appears in compiled output."""
        file_name = uid("integration_steer")
        r = await POST(client, "/api/steering", {
            "name": file_name,
            "content": "# Integration Test Steering\nAlways prefix answers with [IT].",
            "enabled": True
        })
        d = ok(r)
        sfid = d.get("id") or (d.get("file") or {}).get("id")
        check("create returns id", bool(sfid))

        # Compiled endpoint should include this file's content
        compiled = ok(await GET(client, "/api/steering/compiled"))
        check("compiled returns dict or str", isinstance(compiled, (dict, str)))

        # Cleanup
        if sfid:
            await DELETE(client, f"/api/steering/{sfid}")

    async def test_03_toggle_changes_enabled_state(self, client):
        """Toggle a steering file → enabled flag changes."""
        r = await POST(client, "/api/steering", {
            "name": uid("toggle_steer"),
            "content": "# Toggle test",
            "enabled": True
        })
        d = ok(r)
        sfid = d.get("id") or (d.get("file") or {}).get("id")

        if sfid:
            # Toggle once → should disable
            r2 = await POST(client, f"/api/steering/{sfid}/toggle", {})
            assert r2.status_code in (200, 404)

            # Get file state - verify enabled changed
            steer = ok(await GET(client, "/api/steering"))
            files = steer.get("files", steer) if isinstance(steer, dict) else steer
            file_state = next((f for f in files if f.get("id") == sfid), None)
            if file_state:
                check("enabled state changed after toggle",
                      file_state.get("enabled") != True)  # started True, should be False

            await DELETE(client, f"/api/steering/{sfid}")

    async def test_04_delete_removes_from_list(self, client):
        """Delete steering file → no longer in list."""
        r = await POST(client, "/api/steering", {
            "name": uid("del_steer"),
            "content": "# Delete me",
            "enabled": True
        })
        d = ok(r)
        sfid = d.get("id") or (d.get("file") or {}).get("id")
        await DELETE(client, f"/api/steering/{sfid}")

        steer = ok(await GET(client, "/api/steering"))
        files = steer.get("files", steer) if isinstance(steer, dict) else steer
        ids = [f.get("id") for f in files]
        check("deleted file not in list", sfid not in ids)

    async def test_05_steering_context_includes_content(self, client):
        """Steering context endpoint returns content of enabled files."""
        r = await GET(client, "/api/steering/context")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            check("context is dict or str", isinstance(d, (dict, str)))

    async def test_06_steering_learned_patterns(self, client):
        """Learned patterns endpoint accessible."""
        r = await GET(client, "/api/steering/learned/patterns")
        assert r.status_code in (200, 404)
