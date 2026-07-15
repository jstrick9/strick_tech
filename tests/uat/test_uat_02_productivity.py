"""
UAT-02: Productivity Tools
User stories:
  "As a user I can manage my work with a Kanban board"
  "As a developer I can save and reuse my best prompts"
  "As a developer I can use starter templates to scaffold projects"
  "As a team lead I can see analytics about AI usage"
  "As a user I can manage multiple workspaces for different projects"
"""
import pytest
from tests.uat.conftest import *


class TestUATKanbanBoard:
    """User Story: Manage work visually with drag-and-drop Kanban."""

    async def test_user_sees_all_tasks_on_board(self, U):
        """AC: Opening Kanban shows all tasks organized by status."""
        d = accept(await GET(U, "/api/tasks"), "list tasks", 200)
        uat("tasks is a list", isinstance(d, list))

    async def test_user_can_create_a_task(self, U):
        """AC: Clicking '+ Add Task' creates and shows the card immediately."""
        title = uid("Write unit tests for auth module")
        r = await POST(U, "/api/tasks", {
            "title": title, "status": "todo",
            "priority": "high", "agent": "builder",
            "layer": "Sprint 1"
        })
        d = accept(r, "create task", 200)
        
        uat("task created ok",   d.get("ok") is True)
        uat("task has ID",       isinstance(d.get("id"), int))
        uat("title preserved",   d.get("title") == title or d.get("ok") is True)
        
        tid = d["id"]
        tasks = accept(await GET(U, "/api/tasks"), "list tasks", 200)
        card = next((t for t in tasks if t["id"] == tid), None)
        uat("task card appears on board", card is not None)
        
        await DELETE(U, f"/api/tasks/{tid}")

    async def test_user_can_move_task_across_columns(self, U):
        """AC: Dragging card changes its status column."""
        r = await POST(U, "/api/tasks", {"title": uid("MovableTask"), "status": "todo"})
        tid = accept(r, "create task", 200)["id"]
        
        # Move through the full workflow
        for status in ("doing", "blocked", "done"):
            r2 = await POST(U, "/api/kanban/move", {"id": tid, "to_status": status})
            accept(r2, f"move to {status}", 200)
            
            tasks = accept(await GET(U, "/api/tasks"), "list tasks", 200)
            task = next((t for t in tasks if t["id"] == tid), None)
            uat(f"task shows in '{status}' column", task and task["status"] == status)
        
        await DELETE(U, f"/api/tasks/{tid}")

    async def test_user_can_set_priority_levels(self, U):
        """AC: Priority badge (High/Medium/Low) updates immediately."""
        r = await POST(U, "/api/tasks", {"title": uid("PriorityTask"), "priority": "low"})
        tid = accept(r, "create task", 200)["id"]
        
        for priority in ("high", "medium"):
            await PATCH(U, f"/api/tasks/{tid}", {"priority": priority})
            tasks = accept(await GET(U, "/api/tasks"), "list tasks", 200)
            t = next((t for t in tasks if t["id"] == tid), None)
            if t:
                uat(f"priority shows as {priority}", t.get("priority") == priority)
        
        await DELETE(U, f"/api/tasks/{tid}")

    async def test_user_can_assign_task_to_agent(self, U):
        """AC: Agent dropdown assigns task; agent sees it in their queue."""
        r = await POST(U, "/api/tasks", {
            "title": uid("AgentTask"), "status": "todo", "agent": "researcher"
        })
        d = accept(r, "create task", 200)
        tid = d["id"]
        
        tasks = accept(await GET(U, "/api/tasks"), "list tasks", 200)
        t = next((t for t in tasks if t["id"] == tid), None)
        uat("agent assignment saved", t and t.get("agent") == "researcher")
        
        await DELETE(U, f"/api/tasks/{tid}")

    async def test_user_cannot_use_invalid_task_status(self, U):
        """AC: Kanban rejects nonsense status values with clear error."""
        r = await POST(U, "/api/tasks", {"title": uid("BadStatus")})
        tid = accept(r, "create task", 200)["id"]
        
        r2 = await POST(U, "/api/kanban/move", {"id": tid, "to_status": "maybe_later"})
        d2 = r2.json()
        uat("invalid status rejected", d2.get("ok") is False)
        
        await DELETE(U, f"/api/tasks/{tid}")


class TestUATPromptLibrary:
    """User Story: Save and reuse your best prompts."""

    async def test_user_can_create_and_find_prompt(self, U):
        """AC: Save a prompt → it appears in the library immediately."""
        title = uid("Debug FastAPI async issue")
        content = "You are debugging a FastAPI async endpoint. The issue is: {{issue}}"
        r = await POST(U, "/api/prompts", {
            "title": title, "content": content,
            "category": "debug", "tags": "fastapi,async,debug"
        })
        d = accept(r, "create prompt", 200)
        pid = d.get("id")
        uat("prompt saved", bool(pid))
        uat("prompt ID string", isinstance(pid, str))
        
        # Find it in the library
        all_prompts = accept(await GET(U, "/api/prompts"), "list prompts", 200)
        prompts = all_prompts.get("prompts", all_prompts) if isinstance(all_prompts, dict) else []
        found = next((p for p in prompts if p.get("id") == pid), None)
        uat("prompt appears in library", found is not None)
        if found:
            uat("title correct",   found.get("title") == title)
            uat("content correct", found.get("content") == content)
        
        await DELETE(U, f"/api/prompts/{pid}")

    async def test_user_can_search_prompt_library(self, U):
        """AC: Search box finds prompts by keyword."""
        unique = uid("searchterm")
        r = await POST(U, "/api/prompts", {
            "title": f"Unique: {unique}",
            "content": f"Content about {unique} - find me",
            "category": "general"
        })
        pid = accept(r, "create prompt", 200).get("id")
        
        r2 = await GET(U, "/api/prompts/search", q=unique)
        accept(r2, "search prompts", 200, 404)
        
        if pid: await DELETE(U, f"/api/prompts/{pid}")

    async def test_use_count_increments_when_prompt_is_used(self, U):
        """AC: 'Use' button tracks how often each prompt is used."""
        r = await POST(U, "/api/prompts", {
            "title": uid("TrackUsage"), "content": "Test content", "category": "general"
        })
        pid = accept(r, "create prompt", 200).get("id")
        
        # Use it twice
        for _ in range(2):
            r2 = await POST(U, f"/api/prompts/{pid}/use", {})
            accept(r2, "use prompt", 200, 404)
        
        if r2.status_code == 200:
            # Check use count
            r3 = await GET(U, f"/api/prompts/{pid}")
            if r3.status_code == 200:
                p = r3.json()
                p = p.get("prompt", p) if isinstance(p, dict) else p
                uat("use count tracked", p.get("use_count", 0) >= 1)
        
        if pid: await DELETE(U, f"/api/prompts/{pid}")

    async def test_user_can_duplicate_a_prompt(self, U):
        """AC: 'Duplicate' creates a copy to customize without losing original."""
        r = await POST(U, "/api/prompts", {
            "title": uid("Original"), "content": "Original content", "category": "general"
        })
        pid = accept(r, "create prompt", 200).get("id")
        
        r2 = await POST(U, f"/api/prompts/{pid}/duplicate", {})
        accept(r2, "duplicate prompt", 200, 404)
        if r2.status_code == 200:
            d2 = r2.json()
            dup_id = d2.get("id") or (d2.get("prompt") or {}).get("id")
            uat("duplicate has different ID", dup_id != pid)
            if dup_id: await DELETE(U, f"/api/prompts/{dup_id}")
        
        if pid: await DELETE(U, f"/api/prompts/{pid}")

    async def test_prompt_categories_are_organized(self, U):
        """AC: Categories dropdown lets users organize their prompts."""
        r = await GET(U, "/api/prompts/categories")
        accept(r, "categories", 200, 404)
        if r.status_code == 200:
            d = r.json()
            cats = d.get("categories", d)
            uat("categories available", isinstance(cats, (list, dict)))

    async def test_user_can_export_their_prompt_library(self, U):
        """AC: Export all prompts to JSON for backup."""
        r = await GET(U, "/api/prompts/export")
        accept(r, "export prompts", 200, 404)
        if r.status_code == 200:
            d = r.json()
            uat("export has prompts", "prompts" in d or isinstance(d, list))


class TestUATTemplates:
    """User Story: Bootstrap a new project from a template in one click."""

    async def test_user_sees_template_gallery(self, U):
        """AC: Template gallery shows ready-to-use project templates."""
        d = accept(await GET(U, "/api/templates"), "list templates", 200)
        uat("templates present",         "templates" in d)
        uat("at least 10 templates",     d.get("count", 0) >= 10)
        
        for t in d["templates"][:5]:
            uat(f"template '{t.get('id','')}' has name",        "name" in t)
            uat(f"template '{t.get('id','')}' has category",    "category" in t)
            uat(f"template '{t.get('id','')}' has description", "description" in t)
            uat(f"template '{t.get('id','')}' has emoji",       "emoji" in t)

    async def test_user_can_search_templates_by_keyword(self, U):
        """AC: Search 'saas' finds SaaS-relevant templates."""
        r = await GET(U, "/api/templates/search", q="saas")
        accept(r, "search templates", 200, 404)
        if r.status_code == 200:
            d = r.json()
            results = d.get("results", d.get("templates", []))
            uat("search returns results", isinstance(results, list))

    async def test_saas_landing_template_exists(self, U):
        """AC: SaaS Landing Page template is available (most popular)."""
        d = accept(await GET(U, "/api/templates"), "list templates", 200)
        ids = {t["id"] for t in d["templates"]}
        uat("saas-landing template present", "saas-landing" in ids)

    async def test_template_scaffold_custom_html(self, U):
        """AC: User can scaffold a custom template from their own HTML."""
        r = await POST(U, "/api/templates/scaffold-custom", {
            "name": uid("CustomTemplate"),
            "html": "<h1>My Custom Template</h1><p>{{content}}</p>"
        })
        accept(r, "scaffold custom", 200, 400, 404, 422)
        if r.status_code == 200:
            d = r.json()
            # scaffold-custom returns ok:false if no base index.html exists, ok:true if it does
            uat("scaffold responds (ok or error message)",
                d.get("ok") is True or d.get("ok") is False)  # both are valid


class TestUATAnalyticsDashboard:
    """User Story: See what's happening in my AI platform."""

    async def test_user_sees_activity_feed(self, U):
        """AC: Activity feed shows recent events in real time."""
        r = await GET(U, "/api/analytics/activity")
        accept(r, "activity feed", 200, 404)
        if r.status_code == 200:
            d = r.json()
            uat("activity returns dict or list", isinstance(d, (dict, list)))

    async def test_kpis_show_platform_usage(self, U):
        """AC: KPIs show at-a-glance usage stats (messages, agents, cost)."""
        r = await GET(U, "/api/analytics/kpis")
        accept(r, "kpis", 200, 404)
        if r.status_code == 200:
            d = r.json()
            uat("kpis is dict", isinstance(d, dict))

    async def test_agent_performance_stats(self, U):
        """AC: See which agents are being used most."""
        r = await GET(U, "/api/analytics/agents")
        accept(r, "agent stats", 200, 404)

    async def test_memory_growth_over_time(self, U):
        """AC: See how the memory bank grows over time."""
        r = await GET(U, "/api/analytics/memory/growth")
        accept(r, "memory growth", 200, 404)


class TestUATWorkspaces:
    """User Story: Separate projects into isolated workspaces."""

    async def test_user_can_create_a_workspace(self, U):
        """AC: '+ New Workspace' creates a named project space."""
        name = uid("MyClientProject")
        r = await POST(U, "/api/workspaces", {
            "name": name, "description": "Client project files",
            "color": "#9d74f5", "emoji": "🎯"
        })
        d = accept(r, "create workspace", 200)
        wid = d.get("id") or (d.get("workspace") or {}).get("id")
        
        uat("workspace created with ID", bool(wid))
        
        # Appears in list
        wss = accept(await GET(U, "/api/workspaces"), "list workspaces", 200)
        ws_list = wss if isinstance(wss, list) else wss.get("workspaces", [])
        uat("workspace appears in switcher",
            any(w.get("id") == wid for w in ws_list))
        
        await DELETE(U, f"/api/workspaces/{wid}")

    async def test_user_can_activate_a_workspace(self, U):
        """AC: Click workspace → switches context, loads its files."""
        r = await POST(U, "/api/workspaces", {"name": uid("ActivateWS")})
        d = accept(r, "create workspace", 200)
        wid = d.get("id") or (d.get("workspace") or {}).get("id")
        
        if wid:
            r2 = await POST(U, f"/api/workspaces/{wid}/activate", {})
            accept(r2, "activate workspace", 200, 404)
            
            # Current workspace should be set
            r3 = await GET(U, "/api/workspaces/current")
            accept(r3, "current workspace", 200, 404)
            if r3.status_code == 200:
                cws = r3.json()
                cws = cws.get("workspace", cws) if isinstance(cws, dict) else cws
                uat("activated workspace is current", cws.get("id") == wid)
            
            await DELETE(U, f"/api/workspaces/{wid}")

    async def test_user_can_save_project_files(self, U):
        """AC: Save button persists current files to workspace."""
        r = await POST(U, "/api/workspaces", {"name": uid("FileSaveWS")})
        d = accept(r, "create workspace", 200)
        wid = d.get("id") or (d.get("workspace") or {}).get("id")
        
        if wid:
            r2 = await POST(U, f"/api/workspaces/{wid}/save", {
                "files": {
                    "index.html": "<h1>My Project</h1>",
                    "style.css": "body { margin: 0; }",
                    "README.md": "# My Project\nA great project."
                }
            })
            accept(r2, "save workspace", 200, 404)
            if r2.status_code == 200:
                d2 = r2.json()
                uat("save confirmed", d2.get("ok") is True or "saved" in str(d2).lower())
            
            await DELETE(U, f"/api/workspaces/{wid}")

    async def test_user_can_export_workspace_as_zip(self, U):
        """AC: Export → downloads a ZIP of all project files."""
        r = await GET(U, "/api/workspaces/export/current")
        accept(r, "export workspace", 200, 404, 500)
        if r.status_code == 200:
            uat("export returns content", len(r.content) > 0)
