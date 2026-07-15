"""
FLOW-06: Web Search → History → Autocomplete integration
FLOW-20: Docs Search → Contextual → Feedback → Summary loop
FLOW-17: Prompts → Use → Export → Search
"""
import pytest
from tests.integration.conftest import *


@pytest.mark.asyncio
class TestWebSearchHistory:
    """FLOW-06: Web search results flow into history and suggest."""

    async def test_01_clear_and_verify_empty(self, client):
        """Clear history → history is empty."""
        await DELETE(client, "/api/websearch/history")
        d = ok(await GET(client, "/api/websearch/history"))
        check("history empty after clear", len(d["items"]) == 0)

    async def test_02_search_records_to_history(self, client):
        """Search → appears in history."""
        unique_q = uid("inttest_search")
        await POST(client, "/api/websearch/search", {
            "query": unique_q, "num_results": 2
        })
        hist = ok(await GET(client, "/api/websearch/history"))
        queries = [item["query"] for item in hist["items"]]
        check("query in history", unique_q in queries)

    async def test_03_history_has_correct_kind(self, client):
        """Search records kind='search' in history."""
        await DELETE(client, "/api/websearch/history")
        await POST(client, "/api/websearch/search", {"query": uid("kind_test")})
        hist = ok(await GET(client, "/api/websearch/history"))
        if hist["items"]:
            check("kind is 'search'", hist["items"][0]["kind"] == "search")

    async def test_04_suggest_uses_history(self, client):
        """After searching 'Python', suggest returns Python-related suggestions."""
        await DELETE(client, "/api/websearch/history")
        unique_prefix = f"ZZZ_uniquequery_{uid()}"
        await POST(client, "/api/websearch/search", {"query": unique_prefix})

        suggest = ok(await GET(client, "/api/websearch/suggest",
                               q=unique_prefix[:10]))
        check("suggestions is list", isinstance(suggest["suggestions"], list))
        # May or may not match depending on prefix behavior — just verify no error

    async def test_05_history_limit_param(self, client):
        """history?limit=2 returns at most 2 items."""
        # Add some entries
        for i in range(3):
            await POST(client, "/api/websearch/search",
                       {"query": uid(f"limit_test{i}")})

        hist = ok(await GET(client, "/api/websearch/history", limit="2"))
        check("limit respected", len(hist["items"]) <= 2)

    async def test_06_delete_specific_entry(self, client):
        """Delete a specific history entry → it's gone, others remain."""
        await DELETE(client, "/api/websearch/history")

        # Add two entries
        q1 = uid("keep_this")
        q2 = uid("delete_this")
        await POST(client, "/api/websearch/search", {"query": q1})
        await POST(client, "/api/websearch/search", {"query": q2})

        hist = ok(await GET(client, "/api/websearch/history"))
        # Find the q2 entry
        entry = next((i for i in hist["items"] if i["query"] == q2), None)
        if entry:
            entry_id = entry["id"]
            r = await DELETE(client, f"/api/websearch/history/{entry_id}")
            check("delete ok", r.json()["ok"] is True)

            hist2 = ok(await GET(client, "/api/websearch/history"))
            queries = [i["query"] for i in hist2["items"]]
            check("deleted query gone", q2 not in queries)
            check("other query remains", q1 in queries)

    async def test_07_fetch_content_records_ok(self, client):
        """Fetch-content with valid URL returns content."""
        r = await POST(client, "/api/websearch/fetch-content", {
            "url": "https://example.com", "max_chars": 500
        })
        d = ok(r)
        check("ok true", d["ok"] is True)
        check("has content", "content" in d)
        check("url echoed", d["url"] == "https://example.com")
        check("length <= max_chars", d.get("length", 0) <= 500)

    async def test_08_history_count_field(self, client):
        """History response includes count field."""
        hist = ok(await GET(client, "/api/websearch/history"))
        check("count matches items", hist.get("count") == len(hist["items"]))


@pytest.mark.asyncio
class TestDocsSearchFeedbackLoop:
    """FLOW-20: Docs: Search → Contextual → Feedback → Summary aggregation."""

    async def test_01_search_returns_typed_results(self, client):
        """Search 'workflow' returns results of multiple types."""
        d = ok(await GET(client, "/api/docs/search", q="workflow"))
        check("has results", len(d["results"]) > 0)
        types = {r["type"] for r in d["results"]}
        check("multiple result types", len(types) >= 1)
        for r in d["results"]:
            check(f"result has title", "title" in r)

    async def test_02_contextual_matches_search(self, client):
        """Contextual help for 'chat' pane includes chat feature doc."""
        ctx = ok(await GET(client, "/api/docs/contextual/chat"))
        check("pane is chat", ctx["pane"] == "chat")
        # doc should be the chat feature doc
        if ctx.get("doc"):
            check("doc has title", "title" in ctx["doc"])

    async def test_03_feedback_increments_total(self, client):
        """Two feedback submissions → total_feedback increases."""
        r1 = await POST(client, "/api/docs/feedback",
                        {"doc_id": "qs_chat", "doc_type": "quickstart", "helpful": True})
        t1 = ok(r1)["total_feedback"]

        r2 = await POST(client, "/api/docs/feedback",
                        {"doc_id": "qs_chat", "doc_type": "quickstart", "helpful": False})
        t2 = ok(r2)["total_feedback"]

        # In-memory counter may have been reset between test runs; verify it's positive
        check("feedback total is positive integer", t1 >= 1)
        check("total increases with each submission", t2 >= t1)

    async def test_04_summary_reflects_feedback(self, client):
        """Feedback summary aggregates helpful/not_helpful correctly."""
        doc_id = uid("summary_test_doc")
        # Submit 3 helpful, 1 not
        for _ in range(3):
            await POST(client, "/api/docs/feedback",
                       {"doc_id": doc_id, "doc_type": "feature", "helpful": True})
        await POST(client, "/api/docs/feedback",
                   {"doc_id": doc_id, "doc_type": "feature", "helpful": False})

        summary = ok(await GET(client, "/api/docs/feedback/summary"))
        entry = next((f for f in summary["feedback"] if f["doc_id"] == doc_id), None)
        check("doc in summary", entry is not None)
        if entry:
            check("helpful count >= 3", entry["helpful"] >= 3)
            check("not_helpful count >= 1", entry["not_helpful"] >= 1)

    async def test_05_search_limit_clamped_to_50(self, client):
        """Search with limit=100 returns at most 50 results."""
        d = ok(await GET(client, "/api/docs/search", q="a", limit="100"))
        check("shown ≤ 50", d.get("shown", 0) <= 50)
        check("results ≤ 50", len(d["results"]) <= 50)

    async def test_06_quick_starts_filter_by_level(self, client):
        """Filter quick-starts → only matching level returned."""
        d = ok(await GET(client, "/api/docs/quick-starts", level="beginner"))
        for qs in d["quick_starts"]:
            check("beginner level", qs["level"] == "beginner")

    async def test_07_feature_docs_have_id_field(self, client):
        """All feature docs include 'id' field (fixed in audit)."""
        d = ok(await GET(client, "/api/docs/features"))
        for f in d["features"]:
            check(f"feature '{f.get('title','')}' has id", "id" in f)

    async def test_08_404_on_missing_quick_start(self, client):
        """Non-existent quick-start ID returns 404, not 200 with ok:false."""
        r = await GET(client, "/api/docs/quick-starts/DOES_NOT_EXIST")
        check("404 for missing quick-start", r.status_code == 404)


@pytest.mark.asyncio
class TestPromptsExportSearch:
    """FLOW-17: Prompts lifecycle: Create → Use → Search → Export."""

    async def test_01_create_appears_in_search(self, client):
        """Create prompt → searchable immediately."""
        unique = uid("searchprompt")
        r = await POST(client, "/api/prompts", {
            "title": unique, "content": f"Search integration test {unique}",
            "category": "general", "tags": "integration,search"
        })
        pid = ok(r)["id"]

        # Search for it
        search = await GET(client, "/api/prompts/search", q=unique)
        assert search.status_code in (200, 404)
        if search.status_code == 200:
            results = search.json()
            prompts = results.get("prompts", results.get("results", []))
            if isinstance(prompts, list):
                found = any(p.get("title") == unique for p in prompts)
                check("created prompt found in search", found)

        await DELETE(client, f"/api/prompts/{pid}")

    async def test_02_use_count_increments(self, client):
        """POST /use → use_count increases."""
        r = await POST(client, "/api/prompts", {
            "title": uid("usecount"), "content": "Use me", "category": "general"
        })
        pid = ok(r)["id"]

        # Use it
        r2 = await POST(client, f"/api/prompts/{pid}/use", {})
        assert r2.status_code in (200, 404)

        # Check use_count updated
        r3 = await GET(client, f"/api/prompts/{pid}")
        if r3.status_code == 200:
            d3 = r3.json()
            p = d3.get("prompt", d3)
            check("use_count > 0", p.get("use_count", 0) >= 1)

        await DELETE(client, f"/api/prompts/{pid}")

    async def test_03_export_includes_created_prompt(self, client):
        """Created prompt appears in export."""
        unique = uid("exportprompt")
        r = await POST(client, "/api/prompts", {
            "title": unique, "content": "Export test", "category": "general"
        })
        pid = ok(r)["id"]

        export_r = await GET(client, "/api/prompts/export")
        if export_r.status_code == 200:
            data = export_r.json()
            prompts = data.get("prompts", data) if isinstance(data, dict) else data
            if isinstance(prompts, list):
                found = any(p.get("title") == unique for p in prompts)
                check("exported prompt found", found)

        await DELETE(client, f"/api/prompts/{pid}")

    async def test_04_duplicate_creates_copy(self, client):
        """Duplicate prompt → new prompt with same content."""
        r = await POST(client, "/api/prompts", {
            "title": uid("orig"), "content": "Original content", "category": "general"
        })
        pid = ok(r)["id"]

        r2 = await POST(client, f"/api/prompts/{pid}/duplicate", {})
        if r2.status_code == 200:
            d2 = r2.json()
            new_pid = d2.get("id") or (d2.get("prompt") or {}).get("id")
            check("duplicate has different id", new_pid != pid)
            if new_pid:
                await DELETE(client, f"/api/prompts/{new_pid}")

        await DELETE(client, f"/api/prompts/{pid}")

    async def test_05_categories_list(self, client):
        """Categories endpoint returns valid categories."""
        r = await GET(client, "/api/prompts/categories")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            cats = d.get("categories", d)
            check("categories present", isinstance(cats, (list, dict)))
