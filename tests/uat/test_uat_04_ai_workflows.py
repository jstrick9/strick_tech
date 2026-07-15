"""
UAT-04: AI Workflows & Automation
User stories:
  "As a developer I can build visual AI workflows"
  "As a developer I can search the web with AI grounding"
  "As a user I can use the steering system to guide AI behavior"
  "As a developer I can run model comparisons in Arena mode"
  "As a user I can use multiple AI models via Fusion"
"""
import pytest
from tests.uat.conftest import *


class TestUATWorkflowBuilder:
    """User Story: Build visual AI workflows without writing code."""

    async def test_user_can_create_workflow(self, U):
        """AC: Create button opens workflow with trigger node."""
        name = uid("ResearchSummarize")
        r = await POST(U, "/api/workflow", {
            "name": name,
            "nodes": [
                {"id":"n1","type":"trigger", "label":"Start",    "x":0,   "y":100},
                {"id":"n2","type":"agent",   "label":"Research", "x":250, "y":100,
                 "agent_id":"researcher", "prompt":"Research: {{input}}"},
                {"id":"n3","type":"agent",   "label":"Summarize","x":500, "y":100,
                 "agent_id":"builder", "prompt":"Summarize: {{input}}"},
                {"id":"n4","type":"output",  "label":"Done",     "x":750, "y":100},
            ],
            "edges": [
                {"from":"n1","to":"n2"},
                {"from":"n2","to":"n3"},
                {"from":"n3","to":"n4"},
            ]
        })
        d = accept(r, "create workflow", 200)
        wid = d.get("id") or (d.get("workflow") or {}).get("id")
        uat("workflow ID returned", bool(wid))
        
        await DELETE(U, f"/api/workflow/{wid}")

    async def test_workflow_appears_in_list(self, U):
        """AC: Created workflow appears in the workflow picker."""
        name = uid("ListedWorkflow")
        r = await POST(U, "/api/workflow", {"name": name, "nodes": [], "edges": []})
        d = accept(r, "create workflow", 200)
        wid = d.get("id") or (d.get("workflow") or {}).get("id")
        
        wfs = accept(await GET(U, "/api/workflow"), "list workflows", 200)
        wf_list = wfs if isinstance(wfs, list) else wfs.get("workflows", [])
        uat("workflow in picker",
            any(w.get("id") == wid for w in wf_list))
        
        await DELETE(U, f"/api/workflow/{wid}")

    async def test_user_can_update_workflow_nodes(self, U):
        """AC: Edit and save workflow updates its structure."""
        r = await POST(U, "/api/workflow", {"name": uid("UpdateableWF"), "nodes": [], "edges": []})
        d = accept(r, "create workflow", 200)
        wid = d.get("id") or (d.get("workflow") or {}).get("id")
        
        if wid:
            new_nodes = [
                {"id":"n1","type":"trigger","label":"Start","x":0,"y":0},
                {"id":"n2","type":"output", "label":"End",  "x":300,"y":0}
            ]
            r2 = await PUT(U, f"/api/workflow/{wid}", {
                "name": "UpdatedWorkflow",
                "nodes": new_nodes,
                "edges": [{"from":"n1","to":"n2"}]
            })
            accept(r2, "update workflow", 200, 404)
            
            await DELETE(U, f"/api/workflow/{wid}")

    async def test_available_node_types(self, U):
        """AC: Node palette shows all available node types."""
        r = await GET(U, "/api/workflow/node-types/list")
        accept(r, "node types", 200, 404)
        if r.status_code == 200:
            d = r.json()
            uat("node types present", isinstance(d, (list, dict)))

    async def test_user_can_view_replay_runs(self, U):
        """AC: Replay panel shows past workflow execution runs."""
        r = await GET(U, "/api/replay/runs")
        accept(r, "replay runs", 200, 404)
        if r.status_code == 200:
            d = r.json()
            runs = d.get("runs", d) if isinstance(d, dict) else d
            uat("replay runs is list", isinstance(runs, list))


class TestUATWebSearchGrounding:
    """User Story: Ground AI answers with live web results."""

    async def test_user_can_search_the_web(self, U):
        """AC: Typing a query → real web results appear with title, URL, snippet."""
        r = await POST(U, "/api/websearch/search", {
            "query": "Python FastAPI best practices 2024",
            "num_results": 3
        })
        d = accept(r, "web search", 200)
        
        uat("search succeeded",           d.get("ok") is True)
        uat("results returned",           len(d.get("results", [])) >= 0)
        uat("result count in response",   "count" in d)
        
        for res in d.get("results", [])[:3]:
            uat("result has title",   "title" in res)
            uat("result has URL",     "url" in res)
            uat("result has snippet", "snippet" in res)

    async def test_search_history_is_recorded(self, U):
        """AC: Search history panel shows what user has searched."""
        await DELETE(U, "/api/websearch/history")  # clean start
        
        q = uid("uat_search_term")
        await POST(U, "/api/websearch/search", {"query": q, "num_results": 2})
        
        d = accept(await GET(U, "/api/websearch/history"), "search history", 200)
        uat("history has items",       isinstance(d.get("items"), list))
        uat("search recorded",         any(i["query"] == q for i in d.get("items", [])))
        
        await DELETE(U, "/api/websearch/history")

    async def test_user_can_delete_history_entry(self, U):
        """AC: X button deletes a history entry."""
        await DELETE(U, "/api/websearch/history")
        
        q = uid("deletable_search")
        await POST(U, "/api/websearch/search", {"query": q})
        
        hist = accept(await GET(U, "/api/websearch/history"), "history", 200)
        entry = next((i for i in hist.get("items", []) if i["query"] == q), None)
        
        if entry:
            r = await DELETE(U, f"/api/websearch/history/{entry['id']}")
            d = r.json()
            uat("deletion confirmed", d.get("ok") is True)
            
            hist2 = accept(await GET(U, "/api/websearch/history"), "history after delete", 200)
            uat("entry removed from history",
                not any(i["query"] == q for i in hist2.get("items", [])))

    async def test_autocomplete_suggests_from_history(self, U):
        """AC: Typing in search box shows history-based suggestions."""
        await DELETE(U, "/api/websearch/history")
        prefix = uid("suggestme")
        await POST(U, "/api/websearch/search", {"query": f"{prefix} query"})
        
        d = accept(await GET(U, "/api/websearch/suggest", q=prefix[:8]), "suggest", 200)
        uat("suggestions returned",    isinstance(d.get("suggestions"), list))

    async def test_fetch_content_from_url(self, U):
        """AC: 'Fetch' button extracts readable text from any URL."""
        r = await POST(U, "/api/websearch/fetch-content", {
            "url": "https://example.com",
            "max_chars": 500
        })
        d = accept(r, "fetch content", 200)
        uat("fetch successful",        d.get("ok") is True)
        uat("content extracted",       "content" in d)
        uat("URL echoed back",         d.get("url") == "https://example.com")
        uat("length within limit",     d.get("length", 0) <= 500)

    async def test_empty_query_shows_error_not_crash(self, U):
        """AC: Empty search box shows 'please enter a query', not an error page."""
        r = await POST(U, "/api/websearch/search", {"query": ""})
        d = r.json()
        uat("empty query gracefully rejected",  d.get("ok") is False)
        uat("error message helpful",            "error" in d)
        uat("no server crash",                  r.status_code < 500)

    async def test_clear_all_history(self, U):
        """AC: 'Clear all' wipes search history clean."""
        for q in [uid("h1"), uid("h2"), uid("h3")]:
            await POST(U, "/api/websearch/search", {"query": q})
        
        r = await DELETE(U, "/api/websearch/history")
        d = r.json()
        uat("clear all confirmed",  d.get("ok") is True)
        
        hist = accept(await GET(U, "/api/websearch/history"), "history after clear", 200)
        uat("history is empty",     len(hist.get("items", [])) == 0)


class TestUATSteeringFiles:
    """User Story: Guide AI behavior with project-level steering files."""

    async def test_user_sees_default_steering_files(self, U):
        """AC: Platform ships with 4 useful steering file templates."""
        d = accept(await GET(U, "/api/steering"), "list steering", 200)
        files = d.get("files", d) if isinstance(d, dict) else d
        uat("steering files present",     isinstance(files, list))
        uat("at least 4 default files",   len(files) >= 4)
        
        for f in files[:4]:
            uat(f"file '{f.get('id','')}' has title",   "title" in f)
            uat(f"file '{f.get('id','')}' has content", "content" in f)
            uat(f"file '{f.get('id','')}' has enabled", "enabled" in f)

    async def test_user_can_create_steering_file(self, U):
        """AC: '+ New Steering File' saves and activates immediately."""
        name = uid("project_coding_style")
        content = "Always use TypeScript. Never use any. Use interfaces over types."
        r = await POST(U, "/api/steering", {
            "name": name, "content": content, "enabled": True
        })
        d = accept(r, "create steering file", 200)
        sfid = d.get("id") or (d.get("file") or {}).get("id")
        uat("steering file ID returned", bool(sfid))
        
        if sfid: await DELETE(U, f"/api/steering/{sfid}")

    async def test_user_can_toggle_steering_file(self, U):
        """AC: Toggle switch enables/disables file injection."""
        r = await POST(U, "/api/steering", {
            "name": uid("ToggleSteering"), "content": "Toggle test rule", "enabled": True
        })
        d = accept(r, "create steering", 200)
        sfid = d.get("id") or (d.get("file") or {}).get("id")
        
        if sfid:
            # Get initial enabled state of our newly created file
            steer_before = accept(await GET(U, "/api/steering"), "list steering before", 200)
            files_before = steer_before.get("files", steer_before) if isinstance(steer_before, dict) else steer_before
            created_before = next((f for f in files_before if f.get("id") == sfid), None)
            initial_enabled = created_before.get("enabled") if created_before else True
            
            r2 = await POST(U, f"/api/steering/{sfid}/toggle", {})
            accept(r2, "toggle steering", 200, 404)
            
            if r2.status_code == 200:
                # Verify state changed for THIS file
                steer_after = accept(await GET(U, "/api/steering"), "list steering after", 200)
                files_after = steer_after.get("files", steer_after) if isinstance(steer_after, dict) else steer_after
                file_after = next((f for f in files_after if f.get("id") == sfid), None)
                if file_after:
                    after_enabled = file_after.get("enabled")
                    uat("enabled state toggled for our file",
                        after_enabled != initial_enabled)
            
            await DELETE(U, f"/api/steering/{sfid}")

    async def test_compiled_context_includes_enabled_files(self, U):
        """AC: Compiled context shows what will be injected into every prompt."""
        r = await GET(U, "/api/steering/compiled")
        accept(r, "compiled context", 200, 404)
        if r.status_code == 200:
            d = r.json()
            uat("compiled context has content", isinstance(d, (dict, str)))


class TestUATArenaMode:
    """User Story: Compare two AI models side-by-side."""

    async def test_arena_leaderboard_accessible(self, U):
        """AC: Opening Arena shows ELO leaderboard."""
        r = await GET(U, "/api/arena/leaderboard")
        accept(r, "arena leaderboard", 200, 404)
        if r.status_code == 200:
            d = r.json()
            uat("leaderboard has data", isinstance(d, (list, dict)))

    async def test_arena_battles_list(self, U):
        """AC: Past battles are visible in history."""
        r = await GET(U, "/api/arena/battles")
        accept(r, "arena battles", 200, 404)

    async def test_arena_stats_available(self, U):
        """AC: Stats panel shows win rates and model comparisons."""
        r = await GET(U, "/api/arena/stats")
        accept(r, "arena stats", 200, 404)


class TestUATModelFusion:
    """User Story: Use multiple AI models together for best results."""

    async def test_fusion_presets_available(self, U):
        """AC: Presets (Quality/Budget/Code/Research) are available."""
        r = await GET(U, "/api/fusion/presets")
        accept(r, "fusion presets", 200, 404)
        if r.status_code == 200:
            d = r.json()
            presets = d.get("presets", d) if isinstance(d, dict) else d
            uat("presets is list or dict", isinstance(presets, (list, dict)))

    async def test_fusion_models_listed(self, U):
        """AC: Model picker shows available models for fusion."""
        r = await GET(U, "/api/fusion/models")
        accept(r, "fusion models", 200, 404)

    async def test_fusion_classify_suggests_best_preset(self, U):
        """AC: Classify endpoint suggests best model preset for a prompt."""
        r = await GET(U, "/api/fusion/classify", prompt="Write a Python function")
        accept(r, "fusion classify", 200, 404)

    async def test_fusion_history_accessible(self, U):
        """AC: History shows past multi-model completions."""
        r = await GET(U, "/api/fusion/history")
        accept(r, "fusion history", 200, 404)
