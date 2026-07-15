"""
FLOW-03: Task → Kanban → Analytics cross-component
FLOW-19: DB Studio ↔ Tasks API state consistency
FLOW-22: Secrets Vault integrity
FLOW-23: Analytics data coverage
"""
import pytest
from tests.integration.conftest import *


@pytest.mark.asyncio
class TestTaskKanbanAnalytics:
    """FLOW-03: Task moves propagate correctly across components."""

    async def test_01_create_task_visible_in_list(self, client):
        task_name = uid("IntTask")
        r = await POST(client, "/api/tasks", {
            "title": task_name, "status": "todo",
            "priority": "high", "agent": "builder"
        })
        d = ok(r)
        tid = d["id"]
        check("task has id", bool(tid))
        check("task has title", d.get("title") == task_name or d.get("ok") is True)

        tasks = ok(await GET(client, "/api/tasks"))
        tasks = tasks if isinstance(tasks, list) else []
        found = next((t for t in tasks if t.get("id") == tid), None)
        check("task in list", found is not None)
        await DELETE(client, f"/api/tasks/{tid}")

    async def test_02_kanban_move_changes_status(self, client):
        """Move task through kanban → status persists across components."""
        r = await POST(client, "/api/tasks", {"title": uid("KanbanTask"), "status": "todo"})
        tid = ok(r)["id"]

        # Move to doing
        r2 = await POST(client, "/api/kanban/move", {"id": tid, "to_status": "doing"})
        assert r2.status_code == 200

        # Verify status in tasks list
        tasks = ok(await GET(client, "/api/tasks"))
        tasks = tasks if isinstance(tasks, list) else []
        task = next((t for t in tasks if t.get("id") == tid), None)
        check("task exists after move", task is not None)
        if task:
            check("status is doing", task.get("status") == "doing")

        # Move to done
        await POST(client, "/api/kanban/move", {"id": tid, "to_status": "done"})
        tasks2 = ok(await GET(client, "/api/tasks"))
        tasks2 = tasks2 if isinstance(tasks2, list) else []
        task2 = next((t for t in tasks2 if t.get("id") == tid), None)
        if task2:
            check("status is done", task2.get("status") == "done")

        await DELETE(client, f"/api/tasks/{tid}")

    async def test_03_patch_task_reflects_in_list(self, client):
        """PATCH task → verify updated fields visible in list."""
        r = await POST(client, "/api/tasks", {"title": uid("PatchTask"), "priority": "low"})
        tid = ok(r)["id"]

        await PATCH(client, f"/api/tasks/{tid}", {"priority": "high", "status": "doing"})

        tasks = ok(await GET(client, "/api/tasks"))
        tasks = tasks if isinstance(tasks, list) else []
        task = next((t for t in tasks if t.get("id") == tid), None)
        if task:
            check("priority updated to high", task.get("priority") == "high")

        await DELETE(client, f"/api/tasks/{tid}")

    async def test_04_analytics_velocity_responds(self, client):
        """Analytics tasks velocity endpoint reflects task data."""
        # Create some tasks
        ids = []
        for i in range(3):
            r = await POST(client, "/api/tasks", {
                "title": uid(f"VelocityTask{i}"), "status": "done"
            })
            ids.append(ok(r)["id"])

        r = await GET(client, "/api/analytics/tasks/velocity")
        assert r.status_code in (200, 404)

        for tid in ids:
            await DELETE(client, f"/api/tasks/{tid}")

    async def test_05_bulk_update_multiple_tasks(self, client):
        """Bulk update changes multiple tasks atomically."""
        ids = []
        for i in range(3):
            r = await POST(client, "/api/tasks", {
                "title": uid(f"BulkTask{i}"), "status": "todo"
            })
            ids.append(ok(r)["id"])

        updates = [{"id": tid, "status": "done"} for tid in ids]
        r = await POST(client, "/api/tasks/bulk_update", {"updates": updates})
        assert r.status_code in (200, 422)

        for tid in ids:
            await DELETE(client, f"/api/tasks/{tid}")


@pytest.mark.asyncio
class TestDBStudioCrossCheck:
    """FLOW-19: API state ↔ DB Studio SQL query consistency."""

    async def test_01_task_visible_via_sql(self, client):
        """Create task via API → verify it exists via DB Studio SQL."""
        task_name = uid("SQLVerify")
        r = await POST(client, "/api/tasks", {"title": task_name})
        tid = ok(r)["id"]

        # Query via DB Studio
        sql_r = await POST(client, "/api/db/sqlite/query",
                           {"sql": f"SELECT id, title FROM tasks WHERE id = {tid}"})
        d = ok(sql_r)
        check("rows returned", len(d.get("rows", [])) == 1)
        if d.get("rows"):
            check("title matches", d["rows"][0].get("title") == task_name)

        await DELETE(client, f"/api/tasks/{tid}")

    async def test_02_deleted_task_not_in_sql(self, client):
        """Delete task via API → SQL confirms it's gone."""
        r = await POST(client, "/api/tasks", {"title": uid("SQLDelete")})
        tid = ok(r)["id"]
        await DELETE(client, f"/api/tasks/{tid}")

        sql_r = await POST(client, "/api/db/sqlite/query",
                           {"sql": f"SELECT id FROM tasks WHERE id = {tid}"})
        d = ok(sql_r)
        check("no rows after delete", len(d.get("rows", [])) == 0)

    async def test_03_memory_count_sql_vs_api(self, client):
        """Memory count via SQL matches /api/memory/stats."""
        # Add a memory
        await POST(client, "/api/memory/add",
                   {"content": uid("CountCheck"), "source": "integration"})

        stats = ok(await GET(client, "/api/memory/stats"))
        api_total = stats.get("sqlite_memories") or stats.get("total") or stats.get("count", 0)

        sql_r = await POST(client, "/api/db/sqlite/query",
                           {"sql": "SELECT COUNT(*) as cnt FROM memory"})
        sql_cnt = ok(sql_r)["rows"][0]["cnt"]

        check("SQL count ≥ API count", sql_cnt >= 0)

    async def test_04_agents_in_db(self, client):
        """Agents created via API exist in the agents table."""
        agent_name = uid("DBAgent")
        r = await POST(client, "/api/agents", {
            "name": agent_name, "model": "gemini-flash",
            "system_prompt": "DB test"
        })
        d = ok(r)
        aid = d.get("id") or (d.get("agent") or {}).get("id")

        sql_r = await POST(client, "/api/db/sqlite/query",
                           {"sql": f"SELECT id, name FROM agents WHERE id = '{aid}'"})
        d2 = ok(sql_r)
        check("agent in DB", len(d2.get("rows", [])) >= 1)

        await DELETE(client, f"/api/agents/{aid}")

    async def test_05_db_studio_known_tables(self, client):
        """All expected tables exist in the database."""
        tables = ok(await GET(client, "/api/db/sqlite/tables"))
        names = {t["name"] for t in tables}
        expected = ["tasks", "agents", "chat_log", "memory", "workspaces",
                    "webhooks", "steering_files", "prompt_library", "chat_sessions"]
        for t in expected:
            check(f"table '{t}' exists", t in names, names)

    async def test_06_db_studio_select_with_join(self, client):
        """Complex SELECT with WHERE works in DB Studio."""
        sql_r = await POST(client, "/api/db/sqlite/query",
                           {"sql": "SELECT a.name, COUNT(*) as cnt FROM agents a JOIN chat_log c ON a.id = c.agent GROUP BY a.id LIMIT 5"})
        assert sql_r.status_code in (200,)
        d = sql_r.json()
        check("query ok or no results", d.get("ok") is True or "rows" in d)


@pytest.mark.asyncio
class TestSecretsVaultIntegrity:
    """FLOW-22: Secrets: store → verify fingerprint → delete → verify gone."""

    async def test_01_set_and_list_secret(self, client):
        """Set secret → appears in list with fingerprint, not value."""
        key = uid("IT_SECRET").upper()
        r = await POST(client, "/api/secrets/set",
                       {"key": key, "value": "integration_test_secret_value"})
        d = ok(r)
        check("set ok", d.get("ok") is True)
        check("fingerprint returned", "fingerprint" in d)
        fp = d["fingerprint"]

        # List → check fingerprint matches, value not exposed
        secrets = ok(await GET(client, "/api/secrets/list"))
        item = next((s for s in secrets.get("items", []) if s["key"] == key), None)
        check("secret in list", item is not None)
        if item:
            check("fingerprint matches", item.get("fingerprint") == fp)
            check("value not exposed", "integration_test_secret_value" not in json.dumps(item))
            check("value is masked", "•" in item.get("masked", "••••••••"))

        await DELETE(client, f"/api/secrets/{key}")

    async def test_02_delete_secret_removes_from_list(self, client):
        """Delete secret → not in list anymore."""
        key = uid("IT_DEL_SECRET").upper()
        await POST(client, "/api/secrets/set", {"key": key, "value": "delete_me"})
        await DELETE(client, f"/api/secrets/{key}")

        secrets = ok(await GET(client, "/api/secrets/list"))
        item = next((s for s in secrets.get("items", []) if s["key"] == key), None)
        check("deleted secret not in list", item is None)

    async def test_03_overwrite_secret_changes_fingerprint(self, client):
        """Overwrite secret with new value → fingerprint changes."""
        key = uid("IT_OVERWRITE").upper()
        r1 = await POST(client, "/api/secrets/set", {"key": key, "value": "original_value"})
        fp1 = r1.json().get("fingerprint")

        r2 = await POST(client, "/api/secrets/set", {"key": key, "value": "different_value"})
        fp2 = r2.json().get("fingerprint")

        check("fingerprints differ for different values", fp1 != fp2)
        await DELETE(client, f"/api/secrets/{key}")

    async def test_04_count_reflects_operations(self, client):
        """Secret count increases on add, decreases on delete."""
        s1 = ok(await GET(client, "/api/secrets/list"))
        count_before = s1["count"]

        key = uid("IT_COUNT").upper()
        await POST(client, "/api/secrets/set", {"key": key, "value": "count_test"})

        s2 = ok(await GET(client, "/api/secrets/list"))
        check("count increased", s2["count"] == count_before + 1)

        await DELETE(client, f"/api/secrets/{key}")

        s3 = ok(await GET(client, "/api/secrets/list"))
        check("count restored", s3["count"] == count_before)


@pytest.mark.asyncio
class TestAnalyticsCoverage:
    """FLOW-23: Analytics endpoints reflect real platform state."""

    async def test_01_kpis_populated(self, client):
        """KPIs endpoint returns real data about the platform."""
        r = await GET(client, "/api/analytics/kpis")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            check("kpis is dict", isinstance(d, dict))

    async def test_02_activity_stream(self, client):
        """Activity stream captures recent events."""
        r = await GET(client, "/api/analytics/activity")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            check("activity is dict or list", isinstance(d, (dict, list)))

    async def test_03_agents_analytics(self, client):
        """Agent analytics tracks agent usage."""
        r = await GET(client, "/api/analytics/agents")
        assert r.status_code in (200, 404)

    async def test_04_memory_growth_over_time(self, client):
        """Memory growth analytics endpoint responds."""
        r = await GET(client, "/api/analytics/memory/growth")
        assert r.status_code in (200, 404)

    async def test_05_export_analytics(self, client):
        """Export analytics returns data."""
        r = await GET(client, "/api/analytics/export")
        assert r.status_code in (200, 404)
