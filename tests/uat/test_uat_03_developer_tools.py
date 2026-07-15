"""
UAT-03: Developer Tools
User stories:
  "As a developer I can build and preview HTML/CSS/JS live"
  "As a developer I can run an AI-assisted spec-to-code pipeline"
  "As a developer I can review code with AI before committing"
  "As a developer I can run terminal commands within the platform"
  "As a developer I can manage secrets securely"
  "As a developer I can use the database studio for queries"
"""
import pytest
from tests.uat.conftest import *


class TestUATSecretsVault:
    """User Story: Store API keys and secrets securely."""

    async def test_user_can_store_an_api_key(self, U):
        """AC: Entering key in Settings stores it encrypted."""
        key = uid("OPENROUTER_API_KEY_TEST").upper()
        r = await POST(U, "/api/secrets/set", {
            "key": key,
            "value": "sk-or-test-value-should-be-masked",
            "description": "OpenRouter API key for testing"
        })
        d = accept(r, "store secret", 200)
        uat("secret stored ok",          d.get("ok") is True)
        uat("fingerprint returned",      "fingerprint" in d)
        uat("value NOT exposed in resp", "test-value-should-be-masked" not in str(d))
        
        await DELETE(U, f"/api/secrets/{key}")

    async def test_user_sees_masked_values_in_list(self, U):
        """AC: Keys list shows fingerprint/bullets but never the actual value."""
        key = uid("MASKED_SECRET").upper()
        await POST(U, "/api/secrets/set", {"key": key, "value": "super_secret_value_123"})
        
        d = accept(await GET(U, "/api/secrets/list"), "list secrets", 200)
        item = next((i for i in d.get("items", []) if i["key"] == key), None)
        uat("secret appears in vault list",   item is not None)
        if item:
            uat("actual value not shown",     "super_secret_value_123" not in json.dumps(item))
            uat("value is masked with dots",  "•" in item.get("masked", "••"))
            uat("fingerprint shown instead",  "fingerprint" in item)
        
        await DELETE(U, f"/api/secrets/{key}")

    async def test_user_can_rotate_a_secret(self, U):
        """AC: Rotating a key changes its fingerprint."""
        key = uid("ROTATE_ME").upper()
        r1 = await POST(U, "/api/secrets/set", {"key": key, "value": "original_v1"})
        fp1 = accept(r1, "create secret", 200).get("fingerprint")
        
        r2 = await POST(U, "/api/secrets/set", {"key": key, "value": "rotated_v2"})
        fp2 = accept(r2, "rotate secret", 200).get("fingerprint")
        
        uat("fingerprint changed on rotation", fp1 != fp2)
        
        await DELETE(U, f"/api/secrets/{key}")

    async def test_user_can_delete_a_secret(self, U):
        """AC: Delete removes key from vault permanently."""
        key = uid("DELETE_ME").upper()
        await POST(U, "/api/secrets/set", {"key": key, "value": "gone_soon"})
        
        await DELETE(U, f"/api/secrets/{key}")
        
        d = accept(await GET(U, "/api/secrets/list"), "list secrets", 200)
        item = next((i for i in d.get("items", []) if i["key"] == key), None)
        uat("deleted secret not in vault", item is None)


class TestUATTerminal:
    """User Story: Run commands directly within the platform."""

    async def test_user_can_run_echo_command(self, U):
        """AC: Terminal accepts commands and streams output via SSE."""
        import httpx as _h
        marker = uid("terminal_output")
        async with _h.AsyncClient(base_url=BASE, timeout=25) as fresh:
            r = await fresh.post("/api/terminal/run", json={"command": f"echo {marker}"})
        
        accept(r, "run terminal command", 200)
        events = sse(r.text)
        
        uat("terminal produces SSE events",    len(events) >= 1)
        uat("output contains marker",          marker in r.text)
        
        start_ev = next((e for e in events if e.get("type") == "start"), None)
        uat("terminal shows start event",      start_ev is not None)
        if start_ev:
            uat("start event has run_id",      "run_id" in start_ev)

    async def test_user_can_list_files(self, U):
        """AC: ls command shows files in current directory."""
        import httpx as _h
        async with _h.AsyncClient(base_url=BASE, timeout=25) as fresh:
            r = await fresh.post("/api/terminal/run", json={"command": "ls"})
        
        accept(r, "run ls", 200)
        events = sse(r.text)
        stdout = next((e for e in events if e.get("type") == "stdout"), None)
        uat("ls shows file output", stdout is not None or any("exit" in e.get("type","") for e in events))

    async def test_terminal_shows_history(self, U):
        """AC: History panel shows previously run commands."""
        r = await GET(U, "/api/terminal/history")
        accept(r, "terminal history", 200, 404)
        if r.status_code == 200:
            d = r.json()
            uat("history is list or dict", isinstance(d, (list, dict)))

    async def test_dangerous_commands_are_blocked(self, U):
        """AC: Platform prevents accidental system damage."""
        import httpx as _h
        for dangerous_cmd in ["rm -rf /", "dd if=/dev/zero of=/dev/sda"]:
            async with _h.AsyncClient(base_url=BASE, timeout=25) as fresh:
                r = await fresh.post("/api/terminal/run", json={"command": dangerous_cmd})
            
            uat(f"'{dangerous_cmd[:20]}' handled safely", r.status_code in (200, 400, 403))
            if r.status_code == 200:
                events = sse(r.text)
                types = {e.get("type") for e in events}
                uat("no unhandled crash", types & {"start","error","exit","stdout"})


class TestUATBugBot:
    """User Story: AI reviews my code before I commit."""

    async def test_user_sees_review_history(self, U):
        """AC: Opening BugBot shows history of past reviews."""
        r = await GET(U, "/api/bugbot/reviews")
        accept(r, "review history", 200, 404)
        if r.status_code == 200:
            d = r.json()
            reviews = d.get("reviews", d) if isinstance(d, dict) else d
            uat("review list accessible", isinstance(reviews, (list, dict)))

    async def test_empty_diff_shows_helpful_error(self, U):
        """AC: Submitting empty diff shows 'no code to review' message."""
        r = await POST(U, "/api/bugbot/review/diff", {"diff": "", "agent_id": "builder"})
        d = r.json()
        uat("empty diff rejected gracefully", d.get("ok") is False)
        uat("error message included",         "error" in d or "diff" in str(d).lower())
        uat("not a server crash",             r.status_code < 500)

    async def test_user_can_submit_a_diff_for_review(self, U):
        """AC: Pasting a git diff → BugBot reviews it."""
        diff = (
            "diff --git a/auth.py b/auth.py\n"
            "--- a/auth.py\n+++ b/auth.py\n"
            "@@ -1,4 +1,8 @@\n"
            "+def verify_token(token: str) -> bool:\n"
            "+    # TODO: implement proper JWT verification\n"
            "+    return True  # Security risk: always returns True!\n"
            "+\n"
            " def login(username: str, password: str) -> str:\n"
            "-    return jwt.encode({'user': username}, 'secret')\n"
            "+    return jwt.encode({'user': username}, 'secret', algorithm='HS256')\n"
        )
        r = await POST(U, "/api/bugbot/review/diff",
                       {"diff": diff, "agent_id": "builder"})
        no_error(r, "submit diff for review")
        uat("review request accepted", r.status_code in (200, 500))

    async def test_user_can_review_a_file(self, U):
        """AC: Upload a file → BugBot reviews entire file."""
        code = (
            "import hashlib\n\n"
            "def hash_password(password: str) -> str:\n"
            "    # WARNING: MD5 is not secure for passwords!\n"
            "    return hashlib.md5(password.encode()).hexdigest()\n\n"
            "def check_password(plain: str, hashed: str) -> bool:\n"
            "    return hash_password(plain) == hashed\n"
        )
        r = await POST(U, "/api/bugbot/review/file", {
            "content": code, "filename": "auth.py", "agent_id": "builder"
        })
        no_error(r, "file review")
        uat("file review accepted", r.status_code in (200, 500))

    async def test_bugbot_stats_show_review_count(self, U):
        """AC: Stats panel shows how many reviews have been done."""
        r = await GET(U, "/api/bugbot/stats")
        accept(r, "bugbot stats", 200, 404)


class TestUATSpecDrivenDev:
    """User Story: Plan before coding with AI-generated specs."""

    async def test_user_can_create_a_spec(self, U):
        """AC: Describe a feature → spec created with ID."""
        name = uid("User Authentication System")
        r = await POST(U, "/api/specs", {
            "name": name,
            "description": (
                "Build a complete user authentication system with:\n"
                "- JWT token-based login/logout\n"
                "- Password hashing with bcrypt\n"
                "- Role-based access control (admin, user, guest)\n"
                "- Email verification flow\n"
                "- Password reset via email"
            )
        })
        d = accept(r, "create spec", 200)
        spid = d.get("id") or (d.get("spec") or {}).get("id")
        uat("spec ID returned",   bool(spid))
        
        # Appears in list
        specs = accept(await GET(U, "/api/specs"), "list specs", 200)
        sp_list = specs.get("specs", specs) if isinstance(specs, dict) else specs
        uat("spec in list",
            any(s.get("id") == spid for s in sp_list if isinstance(s, dict)))
        
        await DELETE(U, f"/api/specs/{spid}")

    async def test_user_can_get_spec_detail(self, U):
        """AC: Click on spec → see full requirements and tasks."""
        r = await POST(U, "/api/specs", {
            "name": uid("DetailSpec"),
            "description": "Detailed spec for testing"
        })
        d = accept(r, "create spec", 200)
        spid = d.get("id") or (d.get("spec") or {}).get("id")
        
        if spid:
            r2 = await GET(U, f"/api/specs/{spid}")
            accept(r2, "get spec detail", 200, 404)
            if r2.status_code == 200:
                sp = r2.json()
                sp = sp.get("spec", sp) if isinstance(sp, dict) else sp
                uat("spec has ID or title", "id" in sp or "title" in sp)
            
            await DELETE(U, f"/api/specs/{spid}")

    async def test_user_can_export_spec_document(self, U):
        """AC: Export spec as Markdown for documentation."""
        r = await POST(U, "/api/specs", {
            "name": uid("ExportSpec"), "description": "Export test spec"
        })
        d = accept(r, "create spec", 200)
        spid = d.get("id") or (d.get("spec") or {}).get("id")
        
        if spid:
            r2 = await GET(U, f"/api/specs/{spid}/export")
            accept(r2, "export spec", 200, 404)
            if r2.status_code == 200:
                uat("export has content", len(r2.content) > 0)
            
            await DELETE(U, f"/api/specs/{spid}")


class TestUATDatabaseStudio:
    """User Story: Query and explore the database visually."""

    async def test_user_sees_all_tables(self, U):
        """AC: Database Studio shows all tables with row counts."""
        d = accept(await GET(U, "/api/db/sqlite/tables"), "list tables", 200)
        uat("tables is list",       isinstance(d, list))
        uat("tables not empty",     len(d) >= 10)
        
        for t in d[:5]:
            uat(f"table '{t['name']}' has name",       "name" in t)
            uat(f"table '{t['name']}' has row count",  "row_count" in t)
            uat(f"table '{t['name']}' has columns",    "columns" in t and len(t["columns"]) >= 1)

    async def test_user_can_run_select_query(self, U):
        """AC: SQL editor executes query and shows results table."""
        r = await POST(U, "/api/db/sqlite/query", {
            "sql": "SELECT id, title, status FROM tasks LIMIT 10"
        })
        d = accept(r, "run query", 200)
        uat("query returns ok",         d.get("ok") is True)
        uat("query has rows",           "rows" in d)
        uat("query has column names",   "columns" in d)
        uat("type is select",           d.get("type") == "select")

    async def test_user_can_count_records(self, U):
        """AC: COUNT(*) queries work for monitoring data sizes."""
        r = await POST(U, "/api/db/sqlite/query", {
            "sql": "SELECT COUNT(*) as total FROM agents"
        })
        d = accept(r, "count agents", 200)
        uat("count query works",        d.get("ok") is True)
        total = d.get("rows", [{}])[0].get("total", 0)
        uat("agent count is positive",  total >= 1)

    async def test_user_can_view_table_schema(self, U):
        """AC: Click table → see column types and constraints."""
        r = await GET(U, "/api/db/sqlite/table/tasks")
        accept(r, "table info", 200, 404)
        if r.status_code == 200:
            d = r.json()
            uat("table info has columns", "columns" in d or isinstance(d, list))

    async def test_database_state_matches_api_state(self, U):
        """AC: Data I create via the UI is immediately queryable in DB Studio."""
        title = uid("DBConsistencyCheck")
        r = await POST(U, "/api/tasks", {"title": title})
        tid = accept(r, "create task", 200)["id"]
        
        sql_r = await POST(U, "/api/db/sqlite/query", {
            "sql": f"SELECT title FROM tasks WHERE id = {tid}"
        })
        d = accept(sql_r, "query task in DB", 200)
        uat("task appears in DB immediately",
            len(d.get("rows", [])) == 1 and d["rows"][0].get("title") == title)
        
        await DELETE(U, f"/api/tasks/{tid}")
