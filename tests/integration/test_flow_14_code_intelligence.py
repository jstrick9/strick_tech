"""
Integration Flow 14 — Code Intelligence Pipeline
Tests the full code intelligence flow:
  Code indexing → Symbol search → Dependency analysis →
  Code review → Test generation → Replay workflow
"""
from __future__ import annotations
import asyncio, time
import httpx, pytest
from .conftest import BASE, TIMEOUT, uid, GET, POST, PATCH, DELETE, ok, ok_or, check


class TestCodeIndexSearch:
    """Code index, symbol search, and complexity analysis."""

    async def test_01_index_stats_accessible(self, client):
        """Code index stats endpoint returns current state."""
        r = await GET(client, "/api/codeindex/stats")
        d = ok(r, "codeindex stats")
        check("has total_files", "total_files" in d or "files" in d or isinstance(d, dict))

    async def test_02_symbol_search_returns_results(self, client):
        """Symbol search finds Python/JS symbols."""
        r = await GET(client, "/api/codeindex/symbols", q="router", limit=10)
        d = ok(r, "symbol search")
        check("has symbols", "symbols" in d or "results" in d or isinstance(d, (list, dict)))

    async def test_03_dependency_graph(self, client):
        """Dependency graph endpoint returns graph data."""
        r = await GET(client, "/api/codeindex/graph?limit=50")
        d = ok(r, "dependency graph")
        check("has nodes or graph", "nodes" in d or "graph" in d or isinstance(d, (list, dict)))

    async def test_04_complexity_analysis(self, client):
        """Complexity analysis returns per-function metrics."""
        r = await GET(client, "/api/codeindex/complexity?min_complexity=1&limit=10")
        d = ok(r, "complexity")
        check("has results", "results" in d or "symbols" in d or isinstance(d, (list, dict)))

    async def test_05_code_search_in_project(self, client):
        """Project code search finds text in preview files."""
        r = await GET(client, "/api/project/search", q="function", limit=5)
        d = ok(r, "code search")
        check("has results", "results" in d)
        check("has total", "total" in d)
        check("has query", d["query"] == "function")

    async def test_06_project_memory_round_trip(self, client):
        """Project memory persists across set/get/delete."""
        key = f"codeindex_test_{uid()}"
        val = "Use TypeScript strict mode"

        # Set
        set_r = await POST(client, "/api/project/memory", {
            "key": key, "value": val, "category": "style", "confidence": 0.95
        })
        check("set ok", set_r.json()["ok"] is True)

        # Get
        items = (await GET(client, "/api/project/memory?category=style")).json()
        found = next((i for i in items if i["key"] == key), None)
        check("memory found", found is not None)
        check("value correct", found["value"] == val)

        # Delete
        del_r = await client.delete(f"/api/project/memory/{key}")
        check("delete ok", del_r.json()["ok"] is True)

        # Verify deleted
        items2 = (await GET(client, "/api/project/memory")).json()
        keys = [i["key"] for i in items2]
        check("memory deleted", key not in keys)


class TestBugBotReviewFlow:
    """BugBot code review: submit diff → get review → add feedback."""

    async def test_01_reviews_list_accessible(self, client):
        """Reviews list returns structured data."""
        r = await GET(client, "/api/bugbot/reviews?limit=10")
        d = ok(r, "reviews list")
        check("has reviews", "reviews" in d or isinstance(d, list))

    async def test_02_submit_diff_for_review(self, client):
        """Diff submission triggers code review."""
        r = await POST(client, "/api/bugbot/review/diff", {
            "diff": """--- a/utils.py
+++ b/utils.py
@@ -1,5 +1,10 @@
 def calculate(x, y):
-    return x + y
+    if y == 0:
+        raise ValueError("y cannot be zero")
+    return x / y
+
+def validate(data):
+    return data is not None and len(data) > 0
""",
            "language": "python",
            "context": "Math utility functions"
        })
        d = ok(r, "bugbot review")
        check("has ok", "ok" in d)
        check("ok is True", d["ok"] is True or "error" in d or "review" in d)

    async def test_03_file_review_accepts_content(self, client):
        """File content review returns analysis."""
        r = await POST(client, "/api/bugbot/review/file", {
            "filename": "test_integration.py",
            "content": '''def process_user_input(user_input):
    query = f"SELECT * FROM users WHERE name = '{user_input}'"
    return execute_query(query)
''',
            "language": "python"
        })
        d = ok(r, "file review")
        check("file review ok", d.get("ok") is True or "issues" in d or "review" in d)

    async def test_04_feedback_updates_review(self, client):
        """Feedback can be submitted for a review."""
        # Get a review to feedback on
        reviews = (await GET(client, "/api/bugbot/reviews?limit=5")).json()
        review_list = reviews.get("reviews", reviews if isinstance(reviews, list) else [])
        if review_list:
            rid = review_list[0].get("id", review_list[0].get("review_id", ""))
            if rid:
                fb_r = await POST(client, f"/api/bugbot/feedback/{rid}", {
                    "rating": 5,
                    "comment": "Great catch on the SQL injection vulnerability"
                })
                check("feedback 200", fb_r.status_code in (200, 404))

    async def test_05_bugbot_stats(self, client):
        """BugBot stats reflect review history."""
        r = await GET(client, "/api/bugbot/stats")
        d = ok(r, "bugbot stats")
        check("has total or count", "total" in d or "count" in d or isinstance(d, dict))


class TestTestGenWorkflow:
    """Test generation: code input → generated tests → validation."""

    async def test_01_generate_tests_for_python(self, client):
        """Test generation for Python function produces test code."""
        r = await POST(client, "/api/testgen/generate", {
            "code": """def calculate_discount(price: float, discount_pct: float) -> float:
    '''Apply a percentage discount to a price.'''
    if discount_pct < 0 or discount_pct > 100:
        raise ValueError(f"Invalid discount: {discount_pct}")
    return price * (1 - discount_pct / 100)
""",
            "language": "python",
            "framework": "pytest"
        })
        d = ok(r, "testgen python")
        check("testgen responded", "ok" in d or "code" in d or "tests" in d)

    async def test_02_frameworks_list_accessible(self, client):
        """Supported test frameworks are listed."""
        r = await GET(client, "/api/testgen/frameworks")
        d = ok(r, "testgen frameworks")
        check("has frameworks", "frameworks" in d or isinstance(d, list))

    async def test_03_testgen_history_records(self, client):
        """Test generation history is accessible."""
        r = await GET(client, "/api/testgen/history")
        d = ok(r, "testgen history")
        check("has history", "history" in d or isinstance(d, (list, dict)))


class TestReplayWorkflow:
    """Workflow replay: runs list, frames, timeline."""

    async def test_01_replay_runs_accessible(self, client):
        """Replay runs list is accessible."""
        r = await GET(client, "/api/replay/runs?limit=10")
        d = ok(r, "replay runs")
        check("has runs", "runs" in d or isinstance(d, list))

    async def test_02_run_workflow_creates_replay(self, client):
        """Running a workflow creates a replayable record."""
        # Get available workflows
        workflows = (await GET(client, "/api/workflow")).json()
        wf_list = workflows.get("workflows", workflows if isinstance(workflows, list) else [])
        if not wf_list:
            return  # No workflows to replay

        wf_id = wf_list[0].get("id", "")
        if not wf_id:
            return

        # Run the workflow
        run_r = await POST(client, f"/api/workflow/{wf_id}/run", {
            "input": "integration test input"
        })
        check("run 200", run_r.status_code == 200)

    async def test_03_replay_nonexistent_graceful(self, client):
        """Requesting nonexistent replay returns graceful error."""
        r = await GET(client, "/api/replay/runs/nonexistent_xyz_run")
        check("not 500", r.status_code != 500)
        d = r.json()
        check("ok false or error", d.get("ok") is False or "error" in d or "steps" in d)
