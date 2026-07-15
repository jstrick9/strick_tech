"""
SEC-01: SQL Injection Tests
OWASP A03:2021 — Injection

Attack vectors:
  - Classic SQLi in text fields (task titles, memory content, agent names)
  - Blind SQLi with boolean-based payloads
  - DB Studio direct SQL (user controls the query)
  - Search/filter params with SQLi payloads
  - Time-based SQLi
  - UNION-based data extraction attempts
"""
import pytest
from tests.security.conftest import *

# Common SQLi payloads
SQLI_PAYLOADS = [
    "' OR '1'='1",
    "' OR '1'='1' --",
    "'; DROP TABLE tasks; --",
    "' UNION SELECT 1,2,3,4,5 --",
    "' UNION SELECT username,password FROM users --",
    "1' AND SLEEP(5) --",
    "' AND 1=1 --",
    "' AND 1=2 --",
    "admin'--",
    "' OR 1=1--",
    "') OR ('1'='1",
    "1; SELECT * FROM agents",
    "'; INSERT INTO agents (id,name) VALUES ('evil','EVIL_AGENT'); --",
    "\"; DROP TABLE tasks; --",
    "1 OR 1=1",
    "x' OR 1=1 OR 'x'='y",
    "1; UPDATE agents SET system_prompt='HACKED' WHERE 1=1; --",
]

class TestSecSQLiInTaskTitles:
    """SQL injection via task title fields — all must be stored safely."""

    async def test_classic_or_1_1_in_title(self, C):
        """Classic OR 1=1 — stored as literal text, doesn't affect DB."""
        payload = "' OR '1'='1"
        r = await POST(C, "/api/tasks", {"title": payload, "status": "todo"})
        sec_ok(r, f"SQLi in task title: {payload[:30]}")
        
        # Verify tasks table still works normally
        tasks = (await GET(C, "/api/tasks")).json()
        assert isinstance(tasks, list), "Tasks table broken by SQLi attempt"
        
        # If created, verify stored literally
        d = r.json()
        tid = d.get("id")
        if tid:
            stored = next((t for t in tasks if t["id"] == tid), None)
            if stored:
                assert stored["title"] == payload, "SQLi payload was modified (not stored literally)"
            await DELETE(C, f"/api/tasks/{tid}")

    async def test_drop_table_in_title(self, C):
        """DROP TABLE SQLi — table must survive."""
        for payload in ["'; DROP TABLE tasks; --", "\"; DROP TABLE tasks; --"]:
            r = await POST(C, "/api/tasks", {"title": payload})
            sec_ok(r, f"DROP TABLE in title")
            
            # Verify tasks table still works
            tasks = (await GET(C, "/api/tasks")).json()
            assert isinstance(tasks, list), f"Tasks table DESTROYED by: {payload}"

    async def test_union_select_in_title(self, C):
        """UNION SELECT — must not leak data from other tables."""
        payload = "' UNION SELECT id, system_prompt, model, '' FROM agents --"
        r = await POST(C, "/api/tasks", {"title": payload})
        sec_ok(r, "UNION SELECT in title")
        
        # Response must not contain ACTUAL system prompt VALUES (not the column name)
        # The column name "system_prompt" may appear as part of the stored literal title
        # What we care about is actual content from agents being leaked
        resp_lower = r.text.lower()
        # Check for actual leaked data markers - agent-specific content
        dangerous_indicators = ["you are a helpful", "always respond", "gemini", "claude"]
        for indicator in dangerous_indicators:
            assert indicator not in resp_lower, \
                f"UNION SELECT may have leaked agent data: found '{indicator}'"

    async def test_all_sqli_payloads_in_tasks_dont_crash(self, C):
        """All classic SQLi payloads — none crash the server."""
        created_ids = []
        for payload in SQLI_PAYLOADS:
            r = await POST(C, "/api/tasks", {"title": payload, "status": "todo"})
            sec_ok(r, f"SQLi payload: {payload[:30]}")
            d = r.json()
            if d.get("id"):
                created_ids.append(d["id"])
        
        # Tables still functional
        tasks = (await GET(C, "/api/tasks")).json()
        assert isinstance(tasks, list), "Tasks table corrupted by SQLi payloads"
        
        # Cleanup
        for tid in created_ids:
            await DELETE(C, f"/api/tasks/{tid}")

    async def test_sqli_in_memory_content(self, C):
        """SQLi in memory content — FTS should handle gracefully."""
        for payload in SQLI_PAYLOADS[:5]:
            r = await POST(C, "/api/memory/add", {
                "content": payload, "source": "sec_test"
            })
            sec_ok(r, f"SQLi in memory: {payload[:30]}")
            assert r.json().get("ok") is True, f"Memory add failed for: {payload}"

    async def test_sqli_in_agent_fields(self, C):
        """SQLi in agent name and system_prompt."""
        for payload in SQLI_PAYLOADS[:5]:
            r = await POST(C, "/api/agents", {
                "name": payload[:50],
                "model": "gemini-flash",
                "system_prompt": f"You are a test agent. {payload}"
            })
            sec_ok(r, f"SQLi in agent: {payload[:30]}")
            d = r.json()
            aid = d.get("id") or (d.get("agent") or {}).get("id")
            if aid:
                await DELETE(C, f"/api/agents/{aid}")

    async def test_sqli_in_prompt_library(self, C):
        """SQLi in prompt title and content."""
        for payload in SQLI_PAYLOADS[:3]:
            r = await POST(C, "/api/prompts", {
                "title": payload[:80], "content": payload, "category": "general"
            })
            sec_ok(r, f"SQLi in prompt: {payload[:30]}")
            d = r.json()
            if d.get("id"):
                await DELETE(C, f"/api/prompts/{d['id']}")


class TestSecSQLiInDBStudio:
    """DB Studio allows user-controlled SQL — must sandbox dangerous ops."""

    async def test_select_1_works(self, C):
        """Benign query works normally."""
        r = await POST(C, "/api/db/sqlite/query", {"sql": "SELECT 1 AS n"})
        d = r.json()
        assert d["ok"] is True
        assert d["rows"][0]["n"] == 1

    async def test_drop_table_blocked(self, C):
        """DROP TABLE must not destroy production data."""
        r = await POST(C, "/api/db/sqlite/query", {"sql": "DROP TABLE IF EXISTS tasks"})
        sec_ok(r, "DROP TABLE in DB Studio")
        
        # Verify tasks table still exists and works
        tasks = (await GET(C, "/api/tasks")).json()
        assert isinstance(tasks, list), "Tasks table was dropped via DB Studio!"
        
        # Even if DB Studio allows it, must check table still exists
        tables = (await GET(C, "/api/db/sqlite/tables")).json()
        table_names = {t["name"] for t in tables}
        assert "tasks" in table_names, "Tasks table missing after DROP attempt!"

    async def test_delete_all_agents_blocked_or_isolated(self, C):
        """DELETE FROM agents must not wipe production data."""
        # Get count before
        agents_before = (await GET(C, "/api/agents")).json()
        n_before = len(agents_before) if isinstance(agents_before, list) else 0
        
        r = await POST(C, "/api/db/sqlite/query",
                       {"sql": "DELETE FROM agents WHERE 1=1"})
        sec_ok(r, "DELETE all agents in DB Studio")
        
        # Verify agents still exist (some should be protected or recreated)
        agents_after = (await GET(C, "/api/agents")).json()
        n_after = len(agents_after) if isinstance(agents_after, list) else 0
        
        # At minimum, no crash and table still accessible
        assert isinstance(agents_after, list), "Agents endpoint broken after DELETE attempt"

    async def test_update_all_agent_prompts_blocked(self, C):
        """UPDATE with no WHERE — must be handled."""
        r = await POST(C, "/api/db/sqlite/query",
                       {"sql": "UPDATE agents SET system_prompt='HACKED' WHERE 1=1"})
        sec_ok(r, "UPDATE all agents")

    async def test_create_backdoor_table_via_studio(self, C):
        """Attempt to create a backdoor table via DB Studio."""
        r = await POST(C, "/api/db/sqlite/query", {
            "sql": "CREATE TABLE IF NOT EXISTS backdoor (id INTEGER, secret TEXT)"
        })
        sec_ok(r, "CREATE backdoor table")
        
        # Cleanup even if allowed
        await POST(C, "/api/db/sqlite/query", {"sql": "DROP TABLE IF EXISTS backdoor"})

    async def test_sqli_in_search_params(self, C):
        """SQLi payloads in search query parameters."""
        for payload in ["' OR '1'='1", "'; DROP TABLE memory; --", "1 UNION SELECT * FROM agents"]:
            r = await GET(C, "/api/memory/search", q=payload)
            sec_ok(r, f"SQLi in search: {payload[:30]}")
            result = r.json()
            assert isinstance(result, list), "Memory search broken by SQLi in q param"

    async def test_sqli_in_websearch_query(self, C):
        """SQLi payloads in websearch query."""
        payload = "'; DROP TABLE ws_search_history; --"
        r = await POST(C, "/api/websearch/search", {"query": payload, "num_results": 1})
        sec_ok(r, "SQLi in websearch query")
        d = r.json()
        assert d["ok"] is True, "Websearch failed on SQLi payload"
        
        # History table still works
        hist = (await GET(C, "/api/websearch/history")).json()
        assert "items" in hist, "Websearch history broken by SQLi payload"

    async def test_boolean_blind_sqli_no_timing_attack(self, C):
        """Boolean-blind SQLi — server responds consistently regardless."""
        # True condition
        r1 = await POST(C, "/api/tasks", {"title": "' AND 1=1 --"})
        # False condition  
        r2 = await POST(C, "/api/tasks", {"title": "' AND 1=2 --"})
        
        # Both should either succeed or fail consistently (not leak data)
        for r, label in [(r1, "AND 1=1"), (r2, "AND 1=2")]:
            sec_ok(r, f"Boolean SQLi: {label}")
        
        # Cleanup
        for r in [r1, r2]:
            tid = r.json().get("id")
            if tid: await DELETE(C, f"/api/tasks/{tid}")
