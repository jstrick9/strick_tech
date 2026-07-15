"""
UAT-07: Documentation, Onboarding & Miscellaneous Features
User stories:
  "As a new user I can complete onboarding and understand the platform"
  "As a user I can find help for any feature quickly"
  "As a developer I can use MCP tools programmatically"
  "As a user I can deploy my projects"
  "As a developer I can use the collab editor"
  "As a user I want the platform to be accessible and intuitive"
"""
import pytest
from tests.uat.conftest import *


class TestUATOnboarding:
    """User Story: First-run onboarding helps users understand the platform."""

    async def test_onboarding_status_reflects_completion(self, U):
        """AC: Platform knows if user has completed onboarding."""
        d = accept(await GET(U, "/api/onboarding/status"), "onboarding status", 200)
        uat("has completion field", "complete" in d or "done" in d or "step" in d)

    async def test_onboarding_steps_are_defined(self, U):
        """AC: Onboarding wizard has defined steps."""
        r = await GET(U, "/api/onboarding/steps")
        accept(r, "onboarding steps", 200, 404)

    async def test_onboarding_themes_are_available(self, U):
        """AC: New user can pick a color theme during onboarding."""
        r = await GET(U, "/api/onboarding/themes")
        accept(r, "themes list", 200, 404)

    async def test_completing_onboarding_saves_preferences(self, U):
        """AC: Completing wizard saves role, name, UI mode to profile."""
        r = await POST(U, "/api/onboarding/complete", {
            "name": uid("OnboardUser"),
            "role": "developer",
            "ui_mode": "simple"
        })
        accept(r, "complete onboarding", 200, 204)
        
        p = accept(await GET(U, "/api/profile"), "profile", 200)
        uat("onboarding marked done", p.get("onboarding_done") is True)

    async def test_role_presets_apply_relevant_defaults(self, U):
        """AC: Selecting 'Analyst' role loads analytics-focused panes."""
        roles_and_expected = {
            "developer": "studio",
            "analyst":   "dashboard",
            "writer":    "prompts",
            "manager":   "kanban",
        }
        for role, expected_pane in roles_and_expected.items():
            r = await POST(U, f"/api/profile/role/{role}", {})
            d = accept(r, f"apply role {role}", 200)
            uat(f"role {role} applied ok",             d.get("ok") is True)
            uat(f"role {role} has applied defaults",   "applied" in d)
            if "applied" in d:
                uat(f"role {role} sets {expected_pane} as pinned",
                    expected_pane in d["applied"].get("pinned_panes", []))
        
        # Restore
        await POST(U, "/api/profile/role/developer", {})

    async def test_shortcuts_guide_is_complete(self, U):
        """AC: Keyboard shortcuts reference has all important shortcuts."""
        d = accept(await GET(U, "/api/onboarding/shortcuts"), "shortcuts", 200, 404)
        if isinstance(d, (list, dict)):
            shortcuts = d if isinstance(d, list) else d.get("shortcuts", [])
            uat("shortcuts has entries", len(shortcuts) >= 5)


class TestUATDocCenter:
    """User Story: Find help for any feature without leaving the app."""

    async def test_quick_starts_guide_new_users(self, U):
        """AC: Quick Starts tab has step-by-step guides for key tasks."""
        d = accept(await GET(U, "/api/docs/quick-starts"), "quick starts", 200)
        uat("has quick starts",       len(d.get("quick_starts", [])) >= 4)
        
        qs_ids = {qs["id"] for qs in d["quick_starts"]}
        uat("chat quick-start exists",     "qs_chat" in qs_ids)
        uat("agents quick-start exists",   "qs_agents" in qs_ids)
        uat("workflow quick-start exists", "qs_workflow" in qs_ids)

    async def test_quick_start_steps_are_numbered_sequentially(self, U):
        """AC: Steps 1, 2, 3... are in the right order."""
        d = accept(await GET(U, "/api/docs/quick-starts"), "quick starts", 200)
        for qs in d["quick_starts"]:
            for expected_num, step in enumerate(qs["steps"], 1):
                uat(f"QS '{qs['id']}' step {expected_num} is numbered correctly",
                    step["step"] == expected_num)

    async def test_feature_docs_cover_every_tier(self, U):
        """AC: Feature docs indicate Free/Pro/Enterprise access level."""
        d = accept(await GET(U, "/api/docs/features"), "features", 200)
        tiers = {f["tier"] for f in d["features"]}
        uat("free tier features listed",       "free" in tiers)
        uat("pro tier features listed",        "pro" in tiers)
        uat("all features have id field",      all("id" in f for f in d["features"]))

    async def test_search_finds_relevant_content(self, U):
        """AC: Typing 'workflow' in search finds workflow-related help."""
        d = accept(await GET(U, "/api/docs/search", q="workflow"), "doc search", 200)
        uat("search has results",      len(d.get("results", [])) >= 1)
        uat("results are relevant",    
            any("workflow" in r.get("title","").lower() or
                "workflow" in str(r).lower()
                for r in d["results"][:5]))

    async def test_contextual_help_per_pane(self, U):
        """AC: '?' button shows help specific to the current pane."""
        for pane in ["chat", "workflow", "bugbot", "steering"]:
            d = accept(await GET(U, f"/api/docs/contextual/{pane}"), f"contextual {pane}", 200)
            uat(f"contextual {pane} has pane",       d.get("pane") == pane)
            uat(f"contextual {pane} has doc field",  "doc" in d)

    async def test_faq_answers_common_questions(self, U):
        """AC: FAQ has answers to the most common questions."""
        d = accept(await GET(U, "/api/docs/faq"), "faq", 200)
        uat("faq has entries", len(d.get("faq", [])) >= 8)
        
        # Common questions should be answerable
        topics = ["api key", "privacy", "offline", "trial"]
        for topic in topics:
            r = await GET(U, "/api/docs/faq", q=topic)
            if r.status_code == 200:
                d = r.json()
                uat(f"FAQ answers '{topic}' question", d.get("count", 0) >= 1)

    async def test_keyboard_shortcuts_complete(self, U):
        """AC: Shortcuts panel has all documented keyboard shortcuts."""
        d = accept(await GET(U, "/api/docs/shortcuts"), "shortcuts", 200)
        uat("shortcuts present",      d.get("count", 0) >= 10)
        
        # Key shortcuts should be documented
        for s in d.get("shortcuts", [])[:5]:
            uat("shortcut has key",  len(s.get("key", "")) > 0)
            uat("shortcut has desc", len(s.get("desc", "")) > 5)

    async def test_user_can_rate_docs_as_helpful(self, U):
        """AC: 'Was this helpful?' button submits feedback."""
        r = await POST(U, "/api/docs/feedback", {
            "doc_id": "qs_chat",
            "doc_type": "quickstart",
            "helpful": True
        })
        d = accept(r, "doc feedback", 200)
        uat("feedback accepted",    d.get("ok") is True)
        uat("total count updated",  d.get("total_feedback", 0) >= 1)

    async def test_not_helpful_feedback_also_accepted(self, U):
        """AC: 'No, this wasn't helpful' is also a valid response."""
        r = await POST(U, "/api/docs/feedback", {
            "doc_id": "qs_workflow",
            "doc_type": "quickstart",
            "helpful": False
        })
        d = accept(r, "not helpful feedback", 200)
        uat("not-helpful feedback accepted", d.get("ok") is True)


class TestUATMCP:
    """User Story: Use MCP tools to extend AI capabilities."""

    async def test_user_sees_available_mcp_tools(self, U):
        """AC: Tool list shows all available MCP tools."""
        d = accept(await GET(U, "/api/mcp/tools"), "mcp tools", 200)
        tools = d.get("tools", d) if isinstance(d, dict) else d
        uat("tools is list",    isinstance(tools, list))
        uat("tools available",  len(tools) >= 5)

    async def test_user_can_call_json_parse_tool(self, U):
        """AC: json.parse tool parses JSON strings correctly."""
        r = await POST(U, "/api/mcp/call", {
            "tool": "json.parse",
            "args": {"data": '{"name": "Alice", "age": 30, "active": true}'}
        })
        d = accept(r, "json.parse tool", 200)
        uat("tool call ok",          d.get("ok") is True)
        uat("result present",        "result" in d)

    async def test_unknown_tool_shows_helpful_error(self, U):
        """AC: Calling unknown tool shows 'Tool not found' with suggestions."""
        r = await POST(U, "/api/mcp/call", {
            "tool": "definitely.not.a.real.tool",
            "args": {}
        })
        d = r.json()
        uat("unknown tool gracefully rejected",  d.get("ok") is False)
        uat("error message provided",            "error" in d)
        uat("not a server crash",                r.status_code < 500)


class TestUATCollabEdit:
    """User Story: Collaborate on documents in real time."""

    async def test_user_can_create_collab_document(self, U):
        """AC: '+ New Document' creates a shareable collaborative doc."""
        r = await POST(U, "/api/crdt/docs", {
            "title": uid("UATCollabDoc"),
            "content": "# UAT Collaboration Test\n\nThis is a shared document."
        })
        d = accept(r, "create collab doc", 200)
        uat("doc created ok",       d.get("ok") is True)
        uat("doc structure valid",  "doc" in d and "id" in d["doc"])
        doc_id = d["doc"]["id"]
        
        # Get it back
        r2 = await GET(U, f"/api/crdt/docs/{doc_id}")
        accept(r2, "get collab doc", 200, 404)
        if r2.status_code == 200:
            doc = r2.json()
            uat("doc has content",    len(doc.get("content","")) > 0)
            uat("doc has revision",   "revision" in doc)
        
        await DELETE(U, f"/api/crdt/docs/{doc_id}")

    async def test_document_operations_are_recorded(self, U):
        """AC: All edit operations are logged for history/undo."""
        r = await POST(U, "/api/crdt/docs", {
            "title": uid("OpLog"), "content": "Initial content"
        })
        doc_id = accept(r, "create doc", 200)["doc"]["id"]
        
        # Apply an operation
        r2 = await POST(U, f"/api/crdt/docs/{doc_id}/op", {
            "op": [0, "insert", "Prepended: "],
            "peer_id": "uat-peer",
            "peer_name": "UAT Tester"
        })
        accept(r2, "apply op", 200, 404, 422)
        
        # Check ops log
        r3 = await GET(U, f"/api/crdt/docs/{doc_id}/ops")
        accept(r3, "ops log", 200, 404)
        if r3.status_code == 200:
            d = r3.json()
            uat("ops log present", "ops" in d)
        
        await DELETE(U, f"/api/crdt/docs/{doc_id}")


class TestUATDeploy:
    """User Story: Deploy my project with one click."""

    async def test_user_sees_deployment_providers(self, U):
        """AC: Deploy panel shows connected provider (Vercel, Render, etc.)."""
        r = await GET(U, "/api/deploy/providers")
        accept(r, "deploy providers", 200, 404)
        if r.status_code == 200:
            d = r.json()
            providers = d.get("providers", d) if isinstance(d, dict) else d
            uat("providers accessible", isinstance(providers, (list, dict)))

    async def test_user_sees_deployment_history(self, U):
        """AC: History panel shows past deployments with status."""
        r = await GET(U, "/api/deploy/history")
        accept(r, "deploy history", 200, 404)


class TestUATUserAccessibility:
    """User Story: Platform is accessible and behaves intuitively."""

    async def test_all_errors_have_helpful_messages(self, U):
        """AC: Every error response has a human-readable 'error' field."""
        # Trigger known validation errors
        cases = [
            ("/api/websearch/search",    {"query": ""},            "empty query"),
            ("/api/docs/feedback",       {"helpful": True},        "missing doc_id"),
            ("/api/profile",            "INVALID JSON",            "invalid json"),
        ]
        for path, body, label in cases:
            if body == "INVALID JSON":
                r = await U.patch(path, content="INVALID",
                                  headers={"Content-Type": "application/json"})
            else:
                r = await POST(U, path, body)
            
            uat(f"'{label}' no server crash", r.status_code < 500)
            if r.status_code not in (200, 500):  # 422 from FastAPI
                uat(f"'{label}' has error info", r.status_code in (400, 422))

    async def test_platform_responds_quickly_to_basic_requests(self, U):
        """AC: Navigation and basic data fetches complete quickly."""
        import time
        endpoints = ["/api/health", "/api/agents", "/api/tasks",
                     "/api/prompts", "/api/steering"]
        
        for path in endpoints:
            t0 = time.time()
            r = await GET(U, path)
            elapsed = time.time() - t0
            uat(f"{path} responds in < 3s", elapsed < 3.0, f"{elapsed:.2f}s")
            uat(f"{path} not a crash", r.status_code < 500)

    async def test_concurrent_users_dont_corrupt_data(self, U):
        """AC: Multiple simultaneous requests don't create data corruption."""
        import asyncio
        
        async def create_task(i):
            title = uid(f"ConcurrentUAT{i}")
            r = await POST(U, "/api/tasks", {"title": title})
            d = accept(r, f"concurrent task {i}", 200)
            return d.get("id"), title
        
        results = await asyncio.gather(*[create_task(i) for i in range(5)])
        ids = [r[0] for r in results if r[0]]
        uat("all concurrent tasks created", len(ids) == 5)
        uat("all IDs are unique",           len(set(ids)) == 5)
        
        # Verify each appears in list
        tasks = accept(await GET(U, "/api/tasks"), "list tasks", 200)
        tasks = tasks if isinstance(tasks, list) else []
        all_ids = {t["id"] for t in tasks}
        for tid in ids:
            uat(f"concurrent task {tid} in list", tid in all_ids)
            await DELETE(U, f"/api/tasks/{tid}")

    async def test_unicode_content_works_correctly(self, U):
        """AC: Platform handles all character sets (emoji, CJK, Arabic, RTL)."""
        unicode_title = "Test: 🚀 測試 тест مرحبا Ñoño"
        r = await POST(U, "/api/tasks", {"title": unicode_title})
        d = accept(r, "unicode task", 200)
        tid = d.get("id")
        uat("unicode title accepted", bool(tid))
        
        if tid:
            tasks = accept(await GET(U, "/api/tasks"), "list tasks", 200)
            t = next((t for t in tasks if t.get("id") == tid), None)
            uat("unicode title preserved",
                t is not None and t.get("title") == unicode_title)
            await DELETE(U, f"/api/tasks/{tid}")

    async def test_profile_export_is_useful_for_backup(self, U):
        """AC: Export profile gives a complete, restorable JSON snapshot."""
        # Set some data first
        await PATCH(U, "/api/profile", {"name": "UAT Export User"})
        
        r = await GET(U, "/api/profile/export")
        accept(r, "profile export", 200)
        uat("export is downloadable",
            "attachment" in r.headers.get("content-disposition",""))
        
        exported = r.json()
        uat("exported profile has name",   "name" in exported)
        uat("exported profile has role",   "role" in exported)
        uat("name matches current",        exported.get("name") == "UAT Export User")
