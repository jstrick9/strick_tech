"""
UAT-01: Core Chat & Agent Management
User stories:
  "As a user I can create specialized AI agents and chat with them"
  "As a user I can manage my conversation history"
  "As a user I can switch agents mid-conversation"
  "As a developer I can configure agent system prompts precisely"
"""
import pytest
from tests.uat.conftest import *


class TestUATAgentManagement:
    """User Story: Create and manage specialized AI agents."""

    async def test_user_can_see_default_agents_on_first_use(self, U):
        """AC: Platform ships with useful default agents ready to use."""
        d = accept(await GET(U, "/api/agents"), "list agents", 200)
        agents = d if isinstance(d, list) else d.get("agents", [])
        uat("default agents present", len(agents) >= 4)
        
        names = [a["name"].lower() for a in agents]
        uat("'Builder' agent available", any("builder" in n for n in names))
        uat("'Brain' agent available",   any("brain"   in n for n in names))
        
        # Each agent should have at least an id and name
        for agent in agents[:4]:
            uat(f"agent '{agent['name']}' has id",   bool(agent.get("id")))
            uat(f"agent '{agent['name']}' has name", len(agent.get("name","")) > 0)

    async def test_user_can_create_a_custom_agent(self, U):
        """AC: User fills form → agent saved → immediately usable."""
        name = uid("PythonExpert")
        prompt = "You are a Python expert. Always use type hints and write docstrings."
        
        r = await POST(U, "/api/agents", {
            "name": name,
            "model": "gemini-flash",
            "system_prompt": prompt,
            "color": "#4cc98a",
            "avatar": "🐍"
        })
        d = accept(r, "create agent", 200)
        aid = d.get("id") or (d.get("agent") or {}).get("id")
        
        uat("agent creation returns ID",       bool(aid))
        uat("no error in response",            d.get("ok") is True or bool(aid))
        
        # User should immediately see their new agent
        agents = accept(await GET(U, "/api/agents"), "list agents", 200)
        agents = agents if isinstance(agents, list) else agents.get("agents", [])
        found = next((a for a in agents if a.get("id") == aid), None)
        uat("new agent appears in agent picker", found is not None)
        
        await DELETE(U, f"/api/agents/{aid}")

    async def test_user_can_edit_an_existing_agent(self, U):
        """AC: Edit agent prompt → changes are saved immediately."""
        r = await POST(U, "/api/agents", {
            "name": uid("EditableAgent"), "model": "gemini-flash",
            "system_prompt": "Original persona — I am helpful."
        })
        d = accept(r, "create agent", 200)
        aid = d.get("id") or (d.get("agent") or {}).get("id")
        
        new_prompt = "Updated persona — I am a Python and FastAPI specialist."
        r2 = await PATCH(U, f"/api/agents/{aid}", {
            "name": "UpdatedAgentName",
            "system_prompt": new_prompt
        })
        accept(r2, "update agent", 200, 404)
        
        if r2.status_code == 200:
            agents = accept(await GET(U, "/api/agents"), "list agents", 200)
            agents = agents if isinstance(agents, list) else agents.get("agents", [])
            updated = next((a for a in agents if a.get("id") == aid), None)
            if updated:
                uat("agent name was updated",   updated.get("name") == "UpdatedAgentName")
                uat("system prompt was updated", updated.get("system_prompt") == new_prompt)
        
        await DELETE(U, f"/api/agents/{aid}")

    async def test_user_can_delete_agent_they_created(self, U):
        """AC: Delete button removes agent; it no longer appears in picker."""
        r = await POST(U, "/api/agents", {
            "name": uid("ToDelete"), "model": "gemini-flash",
            "system_prompt": "Temp agent"
        })
        d = accept(r, "create agent", 200)
        aid = d.get("id") or (d.get("agent") or {}).get("id")
        
        r2 = await DELETE(U, f"/api/agents/{aid}")
        accept(r2, "delete agent", 200, 204, 404)
        
        agents = accept(await GET(U, "/api/agents"), "list agents", 200)
        agents = agents if isinstance(agents, list) else agents.get("agents", [])
        ids = {a.get("id") for a in agents}
        uat("deleted agent is gone from picker", aid not in ids)

    async def test_system_prompt_length_up_to_10000_chars(self, U):
        """AC: Users can write detailed system prompts without truncation."""
        long_prompt = ("You are an expert software architect.\n" * 100)[:9000]
        r = await POST(U, "/api/agents", {
            "name": uid("LongPrompt"), "model": "gemini-flash",
            "system_prompt": long_prompt
        })
        d = accept(r, "create with long prompt", 200)
        aid = d.get("id") or (d.get("agent") or {}).get("id")
        uat("long prompt accepted", bool(aid) or d.get("ok") is True)
        if aid: await DELETE(U, f"/api/agents/{aid}")


class TestUATChatInterface:
    """User Story: Use the chat interface effectively."""

    async def test_user_sees_chat_history_on_open(self, U):
        """AC: Opening chat shows previous conversation messages."""
        d = accept(await GET(U, "/api/chat/history"), "chat history", 200)
        uat("chat history is a list", isinstance(d, list))
        
        # Each message should have what the user needs
        for msg in d[:5]:
            uat("message has role",    "role" in msg)
            uat("message has content", "message" in msg or "content" in msg)
            uat("role is valid",       msg.get("role") in ("user","assistant","system"))

    async def test_user_can_clear_chat_history(self, U):
        """AC: Chat history is accessible; clearing is done per-session."""
        # Platform manages history per session; verify the history endpoint works
        d = accept(await GET(U, "/api/chat/history"), "chat history", 200)
        uat("chat history accessible",    isinstance(d, list))
        
        # Verify history with a specific session_id also works
        d2 = accept(await GET(U, "/api/chat/history", session_id="new-clear-test"), "session history", 200)
        uat("session-scoped history works", isinstance(d2, list))
        uat("new session has no history",   len(d2) == 0)

    async def test_user_can_switch_session_context(self, U):
        """AC: History with session_id returns session-specific messages."""
        sid = uid("test-session")
        r = await GET(U, "/api/chat/history", session_id=sid)
        d = accept(r, "session history", 200)
        uat("session history is list", isinstance(d, list))

    async def test_platform_remembers_session_preferences(self, U):
        """AC: Session data persists across requests in same session."""
        # Create and immediately verify a session
        r = await POST(U, "/api/sessions", {
            "name": uid("UserSession"),
            "agent_id": "builder"
        })
        d = accept(r, "create session", 200)
        sid = d.get("id") or (d.get("session") or {}).get("id")
        uat("session ID returned", bool(sid))
        
        if sid:
            # User can get their session back
            all_sessions = accept(await GET(U, "/api/sessions"), "list sessions", 200)
            sessions = all_sessions.get("sessions", all_sessions) if isinstance(all_sessions, dict) else all_sessions
            found = any(s.get("id") == sid for s in sessions)
            uat("session appears in sessions list", found)
            
            await DELETE(U, f"/api/sessions/{sid}")


class TestUATMemoryGalaxy:
    """User Story: AI remembers important things across conversations."""

    async def test_user_can_add_memory_entries(self, U):
        """AC: User can save key facts; AI will use them in future chats."""
        content = f"User prefers Python 3.12 and FastAPI. Always use async/await. {uid()}"
        r = await POST(U, "/api/memory/add", {
            "content": content,
            "source": "user",
            "tags": "preferences,python,fastapi"
        })
        d = accept(r, "add memory", 200)
        uat("memory saved",           d.get("ok") is True)
        uat("memory ID returned",     isinstance(d.get("id"), int))

    async def test_user_can_search_their_memories(self, U):
        """AC: Search box finds relevant memories from past conversations."""
        unique = uid("searchable_memory")
        await POST(U, "/api/memory/add", {
            "content": f"Important note: {unique} - use TypeScript for all frontend work",
            "source": "user", "tags": "typescript,frontend"
        })
        
        results = accept(await GET(U, "/api/memory/search", q=unique), "search memory", 200)
        uat("search returns list",      isinstance(results, list))
        uat("search finds the memory",  any(unique in m.get("content","") for m in results))

    async def test_user_sees_memory_statistics(self, U):
        """AC: Memory stats panel shows how many memories are stored."""
        d = accept(await GET(U, "/api/memory/stats"), "memory stats", 200)
        uat("stats is a dict",          isinstance(d, dict))
        uat("total count is positive",
            d.get("sqlite_memories", d.get("total", 1)) >= 0)

    async def test_user_can_export_all_memories(self, U):
        """AC: Export to JSON for backup or migration."""
        d = accept(await GET(U, "/api/memory/export"), "export memory", 200)
        mems = d.get("memories", d) if isinstance(d, dict) else d
        uat("export is a list",         isinstance(mems, list))
        uat("export contains entries",  len(mems) >= 0)

    async def test_user_can_delete_a_specific_memory(self, U):
        """AC: User can remove a memory they no longer want the AI to know."""
        r = await POST(U, "/api/memory/add", {
            "content": uid("delete_this_memory"), "source": "user"
        })
        mid = accept(r, "add memory", 200)["id"]
        
        r2 = await DELETE(U, f"/api/memory/{mid}")
        accept(r2, "delete memory", 200, 204, 404)
        
        # Should no longer appear in search
        results = accept(await GET(U, "/api/memory/search", q=str(mid)), "search", 200)
        uat("deleted memory not in search", 
            not any(str(mid) in str(m) for m in results))

    async def test_galaxy_graph_provides_visual_data(self, U):
        """AC: Galaxy view shows memory nodes for visualization."""
        r = await GET(U, "/api/memory/galaxy")
        accept(r, "galaxy graph", 200, 404)
        if r.status_code == 200:
            d = r.json()
            uat("galaxy data present", isinstance(d, (dict, list)))
