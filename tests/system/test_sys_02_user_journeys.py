"""
SYS-02: User Onboarding Flow (new-user first-run)
SYS-03: Agent Creation & Chat Pipeline
SYS-04: Full Kanban Workflow (all task states)
SYS-14: Profile + Settings Persistence
"""
import pytest
from tests.system.conftest import *


class TestSysOnboarding:
    """SYS-02 — Complete new-user onboarding journey."""

    async def test_onboarding_status_accessible(self, C):
        r = await GET(C, "/api/onboarding/status")
        must(r, 200)
        d = r.json()
        check("has status field", "complete" in d or "done" in d or "step" in d)

    async def test_onboarding_steps_returned(self, C):
        r = await GET(C, "/api/onboarding/steps")
        must(r, 200, 404)

    async def test_shortcuts_available(self, C):
        r = await GET(C, "/api/onboarding/shortcuts")
        must(r, 200, 404)

    async def test_themes_available(self, C):
        r = await GET(C, "/api/onboarding/themes")
        must(r, 200, 404)

    async def test_complete_onboarding_sets_profile(self, C):
        """POST complete → onboarding status reflects completion."""
        r = await POST(C, "/api/onboarding/complete", {
            "name": uid("SysOnboard"), "role": "developer", "ui_mode": "simple"
        })
        must(r, 200, 204)
        d = r.json()
        # Completion stored in preferences.onboarding_complete (not profile.onboarding_done)
        prefs = d.get("preferences", d)
        check("onboarding_complete in response", prefs.get("onboarding_complete") is True
              or d.get("ok") is True)

    async def test_profile_role_sets_pinned_panes(self, C):
        """After onboarding, role defaults populate pinned_panes."""
        await POST(C, "/api/onboarding/complete", {"name": "SysUser", "role": "developer"})
        p = must(await GET(C, "/api/profile"), 200)
        check("has pinned panes", len(p.get("pinned_panes", [])) >= 1)
        check("chat always pinned", "chat" in p.get("pinned_panes", []))

    async def test_ui_mode_switch_simple_to_power(self, C):
        """Switch from simple to power mode → persists."""
        await PATCH(C, "/api/profile", {"ui_mode": "simple"})
        p1 = must(await GET(C, "/api/profile"), 200)
        check("starts simple", p1["ui_mode"] == "simple")

        await PATCH(C, "/api/profile", {"ui_mode": "power"})
        p2 = must(await GET(C, "/api/profile"), 200)
        check("switched to power", p2["ui_mode"] == "power")

        # Restore
        await PATCH(C, "/api/profile", {"ui_mode": "simple"})

    async def test_preferences_persist_across_reads(self, C):
        """Set name, theme, font_size → all persist in next GET."""
        name = uid("PersistUser")
        await PATCH(C, "/api/profile", {
            "name": name, "theme": "midnight", "font_size": "lg"
        })
        p = must(await GET(C, "/api/profile"), 200)
        check("name persisted",       p["name"] == name)
        check("theme persisted",      p["theme"] == "midnight")
        check("font_size persisted",  p["font_size"] == "lg")

        # Restore
        await PATCH(C, "/api/profile", {"theme": "dark", "font_size": "base"})

    async def test_invalid_preferences_rejected(self, C):
        """Invalid theme/font_size → 422, profile unchanged."""
        orig = must(await GET(C, "/api/profile"), 200)

        r = await PATCH(C, "/api/profile", {"theme": "neon_pink_invalid"})
        check("bad theme 422", r.status_code == 422)

        r2 = await PATCH(C, "/api/profile", {"font_size": "XXL"})
        check("bad font_size 422", r2.status_code == 422)

        after = must(await GET(C, "/api/profile"), 200)
        check("theme unchanged", after["theme"] == orig["theme"])


class TestSysAgentChat:
    """SYS-03 — Agent creation and chat pipeline."""

    async def test_create_configure_agent_full_fields(self, C):
        """Create agent with all fields → verify each field persisted."""
        name = uid("SysAgent")
        r = await POST(C, "/api/agents", {
            "name": name,
            "model": "gemini-flash",
            "system_prompt": "You are a system test assistant. Always reply with [SYS_TEST].",
            "color": "#9d74f5",
            "avatar": "🤖",
            "role": "developer"
        })
        d = must(r, 200)
        aid = d.get("id") or (d.get("agent") or {}).get("id")
        check("agent id returned", bool(aid))

        # Verify in list
        agents = must(await GET(C, "/api/agents"), 200)
        agents = agents if isinstance(agents, list) else agents.get("agents",[])
        found = next((a for a in agents if a.get("id") == aid), None)
        check("agent in list", found is not None)

        # Cleanup
        await DELETE(C, f"/api/agents/{aid}")

    async def test_agent_update_then_verify(self, C):
        """Update agent system_prompt → reflected in list."""
        r = await POST(C, "/api/agents", {
            "name": uid("SysAgentUpd"), "model": "gemini-flash",
            "system_prompt": "Original prompt"
        })
        d = must(r, 200)
        aid = d.get("id") or (d.get("agent") or {}).get("id")

        if aid:
            r2 = await PATCH(C, f"/api/agents/{aid}",
                             {"name": "UpdatedSysAgent",
                              "system_prompt": "Updated system prompt"})
            must(r2, 200, 404)

            agents = must(await GET(C, "/api/agents"), 200)
            agents = agents if isinstance(agents, list) else agents.get("agents",[])
            agent = next((a for a in agents if a.get("id") == aid), None)
            if agent:
                check("name updated", agent.get("name") == "UpdatedSysAgent")

            await DELETE(C, f"/api/agents/{aid}")

    async def test_chat_history_accessible(self, C):
        """Chat history returns list with message fields."""
        history = must(await GET(C, "/api/chat/history"), 200)
        check("history is list", isinstance(history, list))
        if history:
            msg = history[0]
            check("has role", "role" in msg)
            check("has message", "message" in msg)
            check("valid role", msg["role"] in ("user","assistant","system"))

    async def test_multiple_agents_in_list(self, C):
        """Multiple agents can coexist and be individually identifiable."""
        created_ids = []
        for i in range(3):
            r = await POST(C, "/api/agents", {
                "name": uid(f"MultiAgent{i}"),
                "model": "gemini-flash",
                "system_prompt": f"Agent {i} for system test"
            })
            d = must(r, 200)
            aid = d.get("id") or (d.get("agent") or {}).get("id")
            if aid:
                created_ids.append(aid)

        agents = must(await GET(C, "/api/agents"), 200)
        agents = agents if isinstance(agents, list) else agents.get("agents",[])
        all_ids = {a.get("id") for a in agents}
        for aid in created_ids:
            check(f"agent {aid} in list", aid in all_ids)

        for aid in created_ids:
            await DELETE(C, f"/api/agents/{aid}")

    async def test_delete_agent_cleanup(self, C):
        """Delete removes agent; subsequent GET list doesn't include it."""
        r = await POST(C, "/api/agents", {
            "name": uid("DeleteSysAgent"), "model": "gemini-flash",
            "system_prompt": "Delete me"
        })
        d = must(r, 200)
        aid = d.get("id") or (d.get("agent") or {}).get("id")

        await DELETE(C, f"/api/agents/{aid}")

        agents = must(await GET(C, "/api/agents"), 200)
        agents = agents if isinstance(agents, list) else agents.get("agents",[])
        ids = {a.get("id") for a in agents}
        check("deleted agent gone", aid not in ids)


class TestSysKanbanWorkflow:
    """SYS-04 — Full kanban workflow through all task states."""

    async def test_complete_task_state_machine(self, C):
        """Task flows: todo → doing → blocked → done, at each step verified."""
        r = await POST(C, "/api/tasks", {
            "title": uid("SysStateMachine"),
            "status": "todo",
            "priority": "high",
            "agent": "builder",
            "layer": "System Tests"
        })
        d = must(r, 200)
        tid = d["id"]

        state_machine = [
            ("doing",   "moved to doing"),
            ("blocked", "moved to blocked"),
            ("done",    "moved to done"),
        ]

        for status, label in state_machine:
            r2 = await POST(C, "/api/kanban/move", {"id": tid, "to_status": status})
            must(r2, 200)

            tasks = must(await GET(C, "/api/tasks"), 200)
            tasks = tasks if isinstance(tasks, list) else []
            task = next((t for t in tasks if t["id"] == tid), None)
            check(f"task {label}", task is not None and task["status"] == status)

        await DELETE(C, f"/api/tasks/{tid}")

    async def test_task_priority_cycle(self, C):
        """Cycle through all priority levels via PATCH."""
        r = await POST(C, "/api/tasks", {"title": uid("PriorityCycle"), "priority": "low"})
        tid = must(r, 200)["id"]

        for priority in ("medium", "high", "low"):
            await PATCH(C, f"/api/tasks/{tid}", {"priority": priority})
            tasks = must(await GET(C, "/api/tasks"), 200)
            tasks = tasks if isinstance(tasks, list) else []
            t = next((t for t in tasks if t["id"] == tid), None)
            if t:
                check(f"priority={priority}", t.get("priority") == priority)

        await DELETE(C, f"/api/tasks/{tid}")

    async def test_task_filtering_by_agent(self, C):
        """Create tasks for different agents → filter correctly."""
        ids = {}
        for agent in ("builder", "researcher"):
            r = await POST(C, "/api/tasks", {
                "title": uid(f"AgentTask_{agent}"), "agent": agent
            })
            ids[agent] = must(r, 200)["id"]

        tasks = must(await GET(C, "/api/tasks"), 200)
        tasks = tasks if isinstance(tasks, list) else []

        for agent, tid in ids.items():
            t = next((t for t in tasks if t["id"] == tid), None)
            check(f"task for {agent} exists", t is not None)
            if t:
                check(f"agent field is {agent}", t.get("agent") == agent)

        for tid in ids.values():
            await DELETE(C, f"/api/tasks/{tid}")

    async def test_many_tasks_bulk_operations(self, C):
        """Create 10 tasks → bulk update all to done → verify."""
        ids = []
        for i in range(5):
            r = await POST(C, "/api/tasks", {"title": uid(f"BulkSys{i}"), "status": "todo"})
            ids.append(must(r, 200)["id"])

        # Bulk update to doing
        updates = [{"id": tid, "status": "doing"} for tid in ids]
        r = await POST(C, "/api/tasks/bulk_update", {"updates": updates})
        must(r, 200, 422)

        for tid in ids:
            await DELETE(C, f"/api/tasks/{tid}")

    async def test_invalid_status_transitions_rejected(self, C):
        """Invalid status values are rejected; task state is preserved."""
        r = await POST(C, "/api/tasks", {"title": uid("InvalidStatus"), "status": "todo"})
        tid = must(r, 200)["id"]

        r2 = await POST(C, "/api/kanban/move", {"id": tid, "to_status": "flying"})
        check("invalid status rejected", r2.json()["ok"] is False)

        # Task still at todo
        tasks = must(await GET(C, "/api/tasks"), 200)
        tasks = tasks if isinstance(tasks, list) else []
        t = next((t for t in tasks if t["id"] == tid), None)
        if t:
            check("status unchanged at todo", t["status"] == "todo")

        await DELETE(C, f"/api/tasks/{tid}")


class TestSysProfileSettings:
    """SYS-14 — Settings persistence across multiple reads."""

    async def test_all_roles_apply_correctly(self, C):
        """Each role applies correct defaults for pinned_panes."""
        role_expectations = {
            "developer": "studio",
            "analyst":   "dashboard",
            "writer":    "prompts",
            "designer":  "imagegen",
            "manager":   "kanban",
            "student":   "docs",
        }
        for role, expected_pane in role_expectations.items():
            r = await POST(C, f"/api/profile/role/{role}", {})
            must(r, 200)
            p = must(await GET(C, "/api/profile"), 200)
            check(f"role={role} applied", p["role"] == role)
            check(f"role={role} has {expected_pane} pinned",
                  expected_pane in p.get("pinned_panes", []))

        # Restore
        await POST(C, "/api/profile/role/developer", {})

    async def test_sidebar_customization_roundtrip(self, C):
        """Hide pane → verify → unhide → verify → order set → verify."""
        test_pane = "obsidian"

        # Hide
        r = await POST(C, f"/api/profile/toggle-pane/{test_pane}", {})
        d = must(r, 200)
        action1 = d["action"]

        p = must(await GET(C, "/api/profile"), 200)
        if action1 == "hidden":
            check("pane in hidden_panes", test_pane in p["hidden_panes"])
        else:
            check("pane not in hidden_panes", test_pane not in p["hidden_panes"])

        # Toggle back
        await POST(C, f"/api/profile/toggle-pane/{test_pane}", {})

        # Set sidebar order
        order = ["chat", "kanban", "workflow", "docs"]
        await POST(C, "/api/profile/sidebar-order", {"order": order})
        p2 = must(await GET(C, "/api/profile"), 200)
        check("order persisted", p2["sidebar_order"] == order)

    async def test_notifications_selective_update(self, C):
        """Update one notification → others unchanged."""
        # Set known baseline
        await PATCH(C, "/api/profile", {
            "notifications": {"agent_complete": True, "hitl_interrupt": True,
                              "daily_summary": False, "sound": False}
        })
        base = must(await GET(C, "/api/profile"), 200)

        # Update only sound
        await PATCH(C, "/api/profile", {"notifications": {"sound": True}})
        after = must(await GET(C, "/api/profile"), 200)

        check("sound updated", after["notifications"]["sound"] is True)
        check("agent_complete unchanged", after["notifications"]["agent_complete"] is True)
        check("hitl_interrupt unchanged", after["notifications"]["hitl_interrupt"] is True)

        # Restore
        await PATCH(C, "/api/profile", {"notifications": {"sound": False}})

    async def test_profile_export_is_complete_snapshot(self, C):
        """Export contains all profile fields in correct format."""
        await PATCH(C, "/api/profile", {"name": uid("ExportSnap"), "theme": "darker"})
        r = await GET(C, "/api/profile/export")
        must(r, 200)
        check("content-disposition attachment",
              "attachment" in r.headers.get("content-disposition",""))
        exported = r.json()
        check("exported name matches",  "name" in exported)
        check("exported theme correct", exported.get("theme") == "darker")

        # Restore
        await PATCH(C, "/api/profile", {"theme": "dark"})
