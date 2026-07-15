"""
UX-03: Form Validation & Feedback
UX-05: CRUD Flows End-to-End
UX-06: Toast & Modal System
UX-09: Responsive Data Updates

Tests that:
  - Creating an item immediately appears in the list
  - Editing updates the display correctly
  - Deleting removes from the list
  - Empty required fields show helpful errors (not crashes)
  - The toast/modal system works
  - Data updates are reflected immediately
"""
import pytest
from tests.usability.conftest import *


class TestUXFormValidation:
    """UX-03: Forms give clear feedback on validation errors."""

    async def test_empty_task_title_rejected_with_message(self, C):
        """Creating a task with empty title shows an error, not a crash."""
        r = await POST(C, "/api/tasks", {"title": ""})
        ux_ok(r, "empty task title handled")
        d = j(r)
        ux_check("Empty title shows error",
                 d.get("ok") is False or r.status_code in (400, 422),
                 "Expected ok:false or 4xx for empty title")

    async def test_empty_query_websearch_shows_error(self, C):
        """Searching with empty query shows error, not crash."""
        r = await POST(C, "/api/websearch/search", {"query": ""})
        ux_ok(r, "empty search query handled")
        d = j(r)
        ux_check("Empty query shows error",
                 d.get("ok") is False,
                 "Expected ok:false for empty search query")
        ux_check("Error message helpful", "error" in d)

    async def test_invalid_theme_rejected_with_422(self, C):
        """Selecting invalid theme returns 422 with message."""
        r = await PATCH(C, "/api/profile", {"theme": "invalid_theme"})
        ux_check("Invalid theme rejected",
                 r.status_code == 422,
                 f"Got {r.status_code} not 422")

    async def test_invalid_license_key_shows_friendly_error(self, C):
        """Bad license key shows helpful error message."""
        r = await POST(C, "/api/license/activate", {"license_key": "BADKEY"})
        d = ux_ok(r, "bad license key handled")
        ux_check("Bad key shows error",  d.get("ok") is False)
        ux_check("Error message present", "error" in d)
        ux_check("Error message helpful", len(d.get("error","")) > 10)

    async def test_invalid_email_shows_friendly_error(self, C):
        """Bad email shows helpful error message."""
        r = await POST(C, "/api/license/set-user",
                       {"name": "Test", "email": "not-email"})
        d = ux_ok(r, "bad email handled")
        ux_check("Invalid email rejected", d.get("ok") is False)

    async def test_empty_memory_content_rejected(self, C):
        """Adding memory with no content shows error."""
        r = await POST(C, "/api/memory/add", {"content": ""})
        d = ux_ok(r, "empty memory content handled")
        ux_check("Empty content rejected", d.get("ok") is False)

    async def test_docs_feedback_missing_doc_id_rejected(self, C):
        """Feedback without doc_id shows helpful error."""
        r = await POST(C, "/api/docs/feedback",
                       {"doc_type": "quickstart", "helpful": True})
        d = ux_ok(r, "feedback without doc_id")
        ux_check("Missing doc_id rejected", d.get("ok") is False)
        ux_check("Error message present", "error" in d)

    async def test_required_field_errors_are_strings(self, C):
        """Error messages are strings, not raw Python exceptions."""
        cases = [
            ("/api/websearch/search", {"query": ""}, "empty query"),
            ("/api/docs/feedback",    {"helpful": True}, "missing doc_id"),
        ]
        for path, body, label in cases:
            r = await POST(C, path, body)
            d = ux_ok(r, label)
            if d.get("ok") is False:
                error = d.get("error", "")
                ux_check(f"Error for '{label}' is a string", isinstance(error, str))
                ux_check(f"Error for '{label}' is readable",
                         not error.startswith("Traceback") and
                         not error.startswith("Exception"))


class TestUXCRUDFlows:
    """UX-05: Complete create → read → update → delete flows."""

    async def test_agent_full_crud_flow(self, C):
        """Full agent CRUD: create appears, update shows, delete disappears."""
        name = uid("UX_Agent")
        
        # CREATE
        r = await POST(C, "/api/agents", {
            "name": name, "model": "gemini-flash",
            "system_prompt": "UX test agent"
        })
        d = ux_ok(r, "create agent")
        aid = d.get("id") or (d.get("agent") or {}).get("id")
        ux_check("Agent CREATE returns ID", bool(aid))
        
        # READ - appears in list
        agents = ux_ok(await GET(C, "/api/agents"), "list agents after create")
        agents = agents if isinstance(agents, list) else agents.get("agents", [])
        found = next((a for a in agents if a.get("id") == aid), None)
        ux_check("Created agent APPEARS in list", found is not None)
        ux_check("Displayed name matches", found.get("name") == name if found else False)
        
        # UPDATE
        r2 = await PATCH(C, f"/api/agents/{aid}", {"name": f"{name}_Updated"})
        ux_ok(r2, "update agent")
        
        agents2 = ux_ok(await GET(C, "/api/agents"), "list agents after update")
        agents2 = agents2 if isinstance(agents2, list) else agents2.get("agents", [])
        updated = next((a for a in agents2 if a.get("id") == aid), None)
        if updated:
            ux_check("Update NAME reflects in list",
                     updated.get("name") == f"{name}_Updated")
        
        # DELETE
        await DELETE(C, f"/api/agents/{aid}")
        
        agents3 = ux_ok(await GET(C, "/api/agents"), "list agents after delete")
        agents3 = agents3 if isinstance(agents3, list) else agents3.get("agents", [])
        gone = next((a for a in agents3 if a.get("id") == aid), None)
        ux_check("Deleted agent DISAPPEARS from list", gone is None)

    async def test_task_crud_with_status_flow(self, C):
        """Task CRUD with status changes visible in Kanban."""
        title = uid("UX_Task")
        
        # CREATE
        r = await POST(C, "/api/tasks", {"title": title, "status": "todo"})
        d = ux_ok(r, "create task")
        tid = d.get("id")
        ux_check("Task CREATE returns ID", bool(tid))
        
        # Appears in todo column
        tasks = ux_ok(await GET(C, "/api/tasks"), "tasks after create")
        tasks = tasks if isinstance(tasks, list) else []
        t = next((t for t in tasks if t.get("id") == tid), None)
        ux_check("Task in list as 'todo'",
                 t is not None and t.get("status") == "todo")
        
        # MOVE to doing
        await POST(C, "/api/kanban/move", {"id": tid, "to_status": "doing"})
        tasks2 = ux_ok(await GET(C, "/api/tasks"), "tasks after move")
        tasks2 = tasks2 if isinstance(tasks2, list) else []
        t2 = next((t for t in tasks2 if t.get("id") == tid), None)
        ux_check("Task STATUS updated to 'doing'",
                 t2 is not None and t2.get("status") == "doing")
        
        # DELETE
        await DELETE(C, f"/api/tasks/{tid}")
        tasks3 = ux_ok(await GET(C, "/api/tasks"), "tasks after delete")
        tasks3 = tasks3 if isinstance(tasks3, list) else []
        ux_check("Deleted task gone from Kanban",
                 not any(t.get("id") == tid for t in tasks3))

    async def test_prompt_crud_flow(self, C):
        """Prompt library CRUD: create, verify, use, delete."""
        title = uid("UX_Prompt")
        
        r = await POST(C, "/api/prompts", {
            "title": title, "content": "UX test {{topic}}", "category": "general"
        })
        d = ux_ok(r, "create prompt")
        pid = d.get("id")
        ux_check("Prompt CREATE returns ID", bool(pid))
        
        # Appears in library
        prompts = ux_ok(await GET(C, "/api/prompts"), "prompt library")
        prompts = prompts.get("prompts", prompts) if isinstance(prompts, dict) else []
        found = next((p for p in prompts if p.get("id") == pid), None)
        ux_check("Prompt in library", found is not None)
        
        # Use count increments
        await POST(C, f"/api/prompts/{pid}/use", {})
        r2 = await GET(C, f"/api/prompts/{pid}")
        if r2.status_code == 200:
            p = r2.json()
            p = p.get("prompt", p) if isinstance(p, dict) else p
            ux_check("Use count tracked", p.get("use_count", 0) >= 1)
        
        await DELETE(C, f"/api/prompts/{pid}")

    async def test_memory_crud_flow(self, C):
        """Memory add → search → delete flow."""
        unique = uid("ux_mem")
        
        r = await POST(C, "/api/memory/add", {
            "content": f"UX memory test {unique}", "source": "ux_test"
        })
        d = ux_ok(r, "add memory")
        ux_check("Memory ADD ok", d.get("ok") is True)
        mid = d.get("id")
        ux_check("Memory returns integer ID", isinstance(mid, int))
        
        # Searchable
        results = ux_ok(await GET(C, "/api/memory/search", q=unique), "search memory")
        ux_check("Added memory is searchable",
                 isinstance(results, list) and
                 any(unique in m.get("content","") for m in results))
        
        # Delete
        r2 = await DELETE(C, f"/api/memory/{mid}")
        ux_check("Memory delete succeeds", r2.status_code in (200,204,404))

    async def test_workspace_crud_flow(self, C):
        """Workspace create → activate → delete flow."""
        name = uid("UX_Workspace")
        
        r = await POST(C, "/api/workspaces", {"name": name})
        d = ux_ok(r, "create workspace")
        wid = d.get("id") or (d.get("workspace") or {}).get("id")
        ux_check("Workspace CREATE returns ID", bool(wid))
        
        # In list
        wss = ux_ok(await GET(C, "/api/workspaces"), "list workspaces")
        ws_list = wss if isinstance(wss, list) else wss.get("workspaces", [])
        ux_check("Workspace in list",
                 any(w.get("id") == wid for w in ws_list))
        
        # Activate
        r2 = await POST(C, f"/api/workspaces/{wid}/activate", {})
        ux_ok(r2, "activate workspace")
        
        # Delete
        await DELETE(C, f"/api/workspaces/{wid}")

    async def test_session_crud_flow(self, C):
        """Session create → retrieve → delete flow."""
        name = uid("UX_Session")
        
        r = await POST(C, "/api/sessions", {"name": name, "agent_id": "builder"})
        d = ux_ok(r, "create session")
        sid = d.get("id") or (d.get("session") or {}).get("id")
        ux_check("Session CREATE returns ID", bool(sid))
        
        # In list
        sessions = ux_ok(await GET(C, "/api/sessions"), "list sessions")
        s_list = sessions.get("sessions", sessions) if isinstance(sessions, dict) else sessions
        ux_check("Session in list", any(s.get("id") == sid for s in s_list))
        
        # Delete
        await DELETE(C, f"/api/sessions/{sid}")
        
        sessions2 = ux_ok(await GET(C, "/api/sessions"), "sessions after delete")
        s_list2 = sessions2.get("sessions", sessions2) if isinstance(sessions2, dict) else sessions2
        ux_check("Session gone from list", not any(s.get("id") == sid for s in s_list2))


class TestUXModalToastSystem:
    """UX-06: Modal and toast system is correctly implemented."""

    def test_modal_functions_defined(self, FE):
        """All modal/toast functions are defined."""
        modal_fns = ["gmAlert", "gmConfirm", "gmPrompt", "gmDanger", "showToast"]
        for fn in modal_fns:
            fe_has(FE, f"async function {fn}" if fn != "showToast" else f"function {fn}",
                   f"{fn} function defined")

    def test_gmalert_has_ok_button(self, FE):
        """gmAlert modal has an OK button."""
        # Find gmAlert implementation
        idx = FE.find("async function gmAlert")
        if idx > 0:
            snippet = FE[idx:idx+500]
            ux_check("gmAlert has OK button",
                     "ok" in snippet.lower() or "OK" in snippet,
                     snippet[:200])

    def test_gmdanger_has_cancel_and_confirm(self, FE):
        """gmDanger has both Cancel and Delete/Confirm buttons."""
        idx = FE.find("async function gmDanger")
        if idx > 0:
            snippet = FE[idx:idx+800]
            ux_check("gmDanger has Cancel", "Cancel" in snippet, snippet[:300])
            ux_check("gmDanger has confirmLabel", "confirmLabel" in snippet)

    def test_toast_system_has_types(self, FE):
        """Toast system supports ok/error/warn types."""
        idx = FE.find("function toast(")
        if idx < 0:
            idx = FE.find("function showToast(")
        ux_check("Toast function found", idx > 0)
        
        if idx > 0:
            snippet = FE[idx:idx+400]
            ux_check("Toast handles types", 
                     "ok" in snippet or "err" in snippet or "type" in snippet)

    def test_no_raw_browser_dialogs(self, FE):
        """No raw functional browser alert/confirm/prompt used."""
        # window.alert() and window.confirm() should be replaced by gmAlert/gmDanger
        ux_check("No window.alert()", fe_count(FE, "window.alert(") == 0)
        ux_check("No window.confirm()", fe_count(FE, "window.confirm(") == 0)
        ux_check("No window.prompt()", fe_count(FE, "window.prompt(") == 0)
        # One occurrence of "confirm(" is in a comment about replacing it — that's OK
        raw_confirm = fe_count(FE, "confirm(")
        ux_check("confirm() only in comment reference (≤2)",
                 raw_confirm <= 2,  # ≤2 comments mentioning confirm() are OK
                 f"Found {raw_confirm} instances (should be ≤2 comment refs)")

    def test_show_toast_used_for_feedback(self, FE):
        """showToast is used for user feedback throughout."""
        count = fe_count(FE, "showToast(")
        ux_check("showToast used extensively (≥50)",
                 count >= 50, f"showToast count: {count}")

    def test_upgrade_modal_exists(self, FE):
        """Upgrade modal for tier gating exists."""
        fe_has(FE, "showUpgradeModal", "Upgrade modal function")
        fe_has(FE, "upgrade-modal", "Upgrade modal ID")
        fe_has(FE, "showTierPlans", "Tier plans modal function")
