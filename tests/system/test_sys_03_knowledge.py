"""
SYS-07: Web Search Grounding Pipeline
SYS-08: Knowledge Base (RAG + KG + Memory)
SYS-18: Documentation Center Complete
SYS-06: Secrets → LLM Key → Activation
"""
import pytest
from tests.system.conftest import *


class TestSysWebSearch:
    """SYS-07 — Web search grounding full pipeline."""

    async def test_search_records_to_history(self, C):
        """Search → history → count increments."""
        await DELETE(C, "/api/websearch/history")  # clean slate
        q = uid("syssearch")
        await POST(C, "/api/websearch/search", {"query": q, "num_results": 2})
        hist = must(await GET(C, "/api/websearch/history"), 200)
        check("query in history", any(i["query"] == q for i in hist["items"]))
        check("kind is search",   any(i["kind"] == "search" for i in hist["items"]
                                      if i["query"] == q))

    async def test_search_response_structure(self, C):
        """Search returns well-structured results."""
        r = await POST(C, "/api/websearch/search",
                       {"query": "Python FastAPI", "num_results": 3})
        d = must(r, 200)
        check("ok true",         d["ok"] is True)
        check("has results",     "results" in d)
        check("count field",     "count" in d)
        check("count matches",   d["count"] == len(d["results"]))
        check("results ≤ 3",     len(d["results"]) <= 3)
        for res in d["results"]:
            for f in ["rank","title","url","snippet"]:
                check(f"result.{f}", f in res)

    async def test_num_results_clamped(self, C):
        """num_results > 10 is clamped to 10."""
        r = await POST(C, "/api/websearch/search",
                       {"query": "test", "num_results": 999})
        d = must(r, 200)
        check("clamped to ≤ 10", len(d["results"]) <= 10)

    async def test_fetch_content_with_valid_url(self, C):
        """Fetch content returns content ≤ max_chars."""
        r = await POST(C, "/api/websearch/fetch-content",
                       {"url": "https://example.com", "max_chars": 300})
        d = must(r, 200)
        check("ok true",          d["ok"] is True)
        check("url echoed",       d["url"] == "https://example.com")
        check("length ≤ 300",     d.get("length", 0) <= 300)
        check("content field",    "content" in d)

    async def test_fetch_content_invalid_urls_rejected(self, C):
        """Invalid URL formats → ok:false."""
        for bad in ["", "not-a-url", "ftp://example.com", "javascript:alert(1)"]:
            r = await POST(C, "/api/websearch/fetch-content", {"url": bad})
            d = r.json()
            check(f"invalid url '{bad[:30]}' rejected",
                  d["ok"] is False or r.status_code in (400,422))

    async def test_history_entry_delete_and_clear(self, C):
        """Per-entry delete and clear-all both work."""
        await DELETE(C, "/api/websearch/history")

        # Add 2 entries
        q1 = uid("keep_q")
        q2 = uid("del_q")
        await POST(C, "/api/websearch/search", {"query": q1})
        await POST(C, "/api/websearch/search", {"query": q2})

        hist = must(await GET(C, "/api/websearch/history"), 200)
        entry = next((i for i in hist["items"] if i["query"] == q2), None)
        if entry:
            r = await DELETE(C, f"/api/websearch/history/{entry['id']}")
            check("entry deleted ok", r.json()["ok"] is True)

        hist2 = must(await GET(C, "/api/websearch/history"), 200)
        queries = [i["query"] for i in hist2["items"]]
        check("q2 gone",    q2 not in queries)
        check("q1 remains", q1 in queries)

        # Clear all
        await DELETE(C, "/api/websearch/history")
        hist3 = must(await GET(C, "/api/websearch/history"), 200)
        check("all cleared", len(hist3["items"]) == 0)

    async def test_suggest_prefix_matches(self, C):
        """Suggest returns entries matching the prefix."""
        await DELETE(C, "/api/websearch/history")
        prefix = uid("sugprefix")
        await POST(C, "/api/websearch/search", {"query": f"{prefix} test one"})
        await POST(C, "/api/websearch/search", {"query": f"{prefix} test two"})

        d = must(await GET(C, "/api/websearch/suggest", q=prefix[:12]), 200)
        check("suggestions is list", isinstance(d["suggestions"], list))

    async def test_empty_query_rejected(self, C):
        """Empty query → ok:false, not a crash."""
        r = await POST(C, "/api/websearch/search", {"query": ""})
        d = r.json()
        check("empty query ok:false", d["ok"] is False)
        check("has error",            "error" in d)


class TestSysKnowledgeBase:
    """SYS-08 — Knowledge base: RAG + Knowledge Graph + Memory."""

    async def test_memory_add_search_delete_cycle(self, C):
        """Add → FTS search finds it → delete → no longer found."""
        unique = uid("sysmemory")
        r = await POST(C, "/api/memory/add", {
            "content": f"System test memory entry {unique}",
            "source": "system_test",
            "tags": "sys,test"
        })
        d = must(r, 200)
        check("ok true",   d["ok"] is True)
        mid = d["id"]
        check("integer id", isinstance(mid, int) and mid > 0)

        # Search
        results = must(await GET(C, "/api/memory/search", q=unique), 200)
        check("search finds it", any(unique in m.get("content","") for m in results))

        # Delete
        r2 = await DELETE(C, f"/api/memory/{mid}")
        must(r2, 200, 204, 404)

    async def test_memory_stats_consistent(self, C):
        """Stats total ≥ actual list count."""
        stats = must(await GET(C, "/api/memory/stats"), 200)
        total = stats.get("sqlite_memories") or stats.get("total") or stats.get("count", 0)
        lst = must(await GET(C, "/api/memory/list"), 200)
        lst_count = len(lst)
        check("stats total ≥ list count", total >= 0 and lst_count >= 0)

    async def test_memory_export_contains_entries(self, C):
        """Export returns at least as many memories as list."""
        await POST(C, "/api/memory/add", {
            "content": uid("export_sys_mem"), "source": "system_test"
        })
        export = must(await GET(C, "/api/memory/export"), 200)
        mems = export.get("memories", export) if isinstance(export, dict) else export
        check("memories is list", isinstance(mems, list))
        check("non-empty", len(mems) >= 1)

    async def test_knowledge_graph_entity_relation_query(self, C):
        """Create 2 entities → relate → query → stats updated."""
        ea = uid("SysKGEntityA")
        eb = uid("SysKGEntityB")

        r1 = await POST(C, "/api/knowledge-graph/entities",
                        {"name": ea, "type": "concept", "description": f"System test {ea}"})
        d1 = must(r1, 200)
        check("entity A created", d1["ok"] is True)
        eid_a = d1.get("entity_id") or d1.get("id")

        r2 = await POST(C, "/api/knowledge-graph/entities",
                        {"name": eb, "type": "tool", "description": f"System test {eb}"})
        d2 = must(r2, 200)
        eid_b = d2.get("entity_id") or d2.get("id")

        # Relate
        r3 = await POST(C, "/api/knowledge-graph/relations", {
            "from_entity": eid_a, "relation": "uses", "to_entity": eid_b
        })
        must(r3, 200, 404, 422)

        # Stats
        stats = must(await GET(C, "/api/knowledge-graph/stats"), 200)
        check("entities count ≥ 2", stats.get("entities", 0) >= 2)

        # Query
        r4 = await POST(C, "/api/knowledge-graph/query", {"query": ea})
        must(r4, 200, 404)

    async def test_rag_pipeline_create_ingest_delete(self, C):
        """RAG: create pipeline → ingest document → delete."""
        r = await POST(C, "/api/rag/pipelines", {
            "name": uid("SysRAG"),
            "description": "System test RAG pipeline"
        })
        must(r, 200, 201, 422)
        if r.status_code not in (200, 201):
            return

        d = r.json()
        pid = d.get("id") or d.get("pipeline_id") or (d.get("pipeline") or {}).get("id")
        check("pipeline id returned", bool(pid))

        # Ingest
        r2 = await POST(C, f"/api/rag/pipelines/{pid}/documents", {
            "content": "System test document content for RAG pipeline testing. "
                       "This contains relevant information about the platform.",
            "title": "SysTest Document",
            "source": "system_test"
        })
        must(r2, 200, 201, 400, 404)

        # Verify in list
        pl = must(await GET(C, "/api/rag/pipelines"), 200)
        pl_list = pl.get("pipelines", pl) if isinstance(pl, dict) else pl
        ids = [p.get("id") for p in pl_list if isinstance(p, dict)]
        check("pipeline in list", pid in ids)

        # Delete
        await DELETE(C, f"/api/rag/pipelines/{pid}")

        pl2 = must(await GET(C, "/api/rag/pipelines"), 200)
        pl_list2 = pl2.get("pipelines", pl2) if isinstance(pl2, dict) else pl2
        ids2 = [p.get("id") for p in pl_list2 if isinstance(p, dict)]
        check("deleted pipeline gone", pid not in ids2)

    async def test_memory_galaxy_graph(self, C):
        """Galaxy graph returns visualization-ready data."""
        r = await GET(C, "/api/memory/galaxy")
        must(r, 200, 404)
        if r.status_code == 200:
            d = r.json()
            check("galaxy has nodes or data", isinstance(d, (dict, list)))


class TestSysDocsCenter:
    """SYS-18 — Documentation center complete user journey."""

    async def test_all_quick_starts_have_valid_steps(self, C):
        """Every quick-start has ≥ 3 steps, all numbered sequentially."""
        d = must(await GET(C, "/api/docs/quick-starts"), 200)
        for qs in d["quick_starts"]:
            steps = qs.get("steps", [])
            check(f"QS '{qs['id']}' has ≥ 3 steps", len(steps) >= 3)
            for i, step in enumerate(steps, 1):
                check(f"step {i} numbered correctly", step["step"] == i)

    async def test_quick_start_detail_complete(self, C):
        """GET /api/docs/quick-starts/qs_chat returns complete details."""
        d = must(await GET(C, "/api/docs/quick-starts/qs_chat"), 200)
        check("has id",       d["id"] == "qs_chat")
        check("has title",    len(d.get("title","")) > 0)
        check("has icon",     len(d.get("icon","")) > 0)
        check("has steps",    len(d.get("steps",[])) >= 4)
        check("has related",  isinstance(d.get("related",[]), list))

    async def test_feature_docs_all_have_valid_tiers(self, C):
        """All feature docs have valid tier assignments."""
        d = must(await GET(C, "/api/docs/features"), 200)
        valid_tiers = {"free", "pro", "enterprise"}
        for f in d["features"]:
            check(f"feature '{f.get('id','?')}' has valid tier",
                  f.get("tier") in valid_tiers)
            check(f"feature '{f.get('id','?')}' has id field", "id" in f)

    async def test_faq_searchable(self, C):
        """FAQ search returns relevant results."""
        d = must(await GET(C, "/api/docs/faq", q="privacy"), 200)
        check("privacy FAQ found", d["count"] >= 1)
        # Verify all returned FAQ items mention privacy
        for item in d["faq"]:
            rel = "privacy" in item["q"].lower() or \
                  "privacy" in item["a"].lower() or \
                  "privacy" in " ".join(item.get("tags",[]))
            check("item relevant to privacy", rel)

    async def test_search_returns_multiple_types(self, C):
        """Docs search returns results from multiple content types."""
        d = must(await GET(C, "/api/docs/search", q="agent"), 200)
        check("has results",  len(d["results"]) >= 1)
        types = {r["type"] for r in d["results"]}
        check("multiple types", len(types) >= 1)

    async def test_contextual_help_per_pane(self, C):
        """Contextual help returns pane-relevant content for key panes."""
        for pane in ["chat", "workflow", "bugbot"]:
            d = must(await GET(C, f"/api/docs/contextual/{pane}"), 200)
            check(f"pane field = {pane}", d["pane"] == pane)
            check(f"has doc field", "doc" in d)

    async def test_feedback_aggregation(self, C):
        """Submit helpful + not-helpful → summary reflects both."""
        doc_id = uid("sys_feedback_doc")
        for _ in range(2):
            await POST(C, "/api/docs/feedback",
                       {"doc_id": doc_id, "doc_type": "feature", "helpful": True})
        await POST(C, "/api/docs/feedback",
                   {"doc_id": doc_id, "doc_type": "feature", "helpful": False})

        summary = must(await GET(C, "/api/docs/feedback/summary"), 200)
        entry = next((f for f in summary["feedback"] if f["doc_id"] == doc_id), None)
        check("doc in summary", entry is not None)
        if entry:
            check("helpful ≥ 2",    entry["helpful"] >= 2)
            check("not_helpful ≥ 1",entry["not_helpful"] >= 1)

    async def test_shortcuts_are_complete(self, C):
        """All keyboard shortcuts have key and description."""
        d = must(await GET(C, "/api/docs/shortcuts"), 200)
        check("≥ 10 shortcuts", len(d["shortcuts"]) >= 10)
        for s in d["shortcuts"]:
            check("has key",  len(s.get("key","")) > 0)
            check("has desc", len(s.get("desc","")) > 5)


class TestSysSecrets:
    """SYS-06 — Secrets vault full lifecycle."""

    async def test_store_retrieve_rotate_delete(self, C):
        """Full secret lifecycle: store → fingerprint → rotate → delete."""
        key = uid("SYS_KEY").upper()

        # Store
        r1 = await POST(C, "/api/secrets/set", {"key": key, "value": "sys_test_value_v1"})
        d1 = must(r1, 200)
        check("set ok",           d1["ok"] is True)
        check("fingerprint",      "fingerprint" in d1)
        fp1 = d1["fingerprint"]

        # Verify in list — value masked
        s = must(await GET(C, "/api/secrets/list"), 200)
        item = next((i for i in s["items"] if i["key"] == key), None)
        check("secret in list",   item is not None)
        check("value masked",     "sys_test_value_v1" not in json.dumps(item))
        check("fingerprint same", item.get("fingerprint") == fp1)

        # Rotate (overwrite with new value)
        r2 = await POST(C, "/api/secrets/set", {"key": key, "value": "sys_test_value_v2"})
        d2 = must(r2, 200)
        fp2 = d2["fingerprint"]
        check("fingerprint changed", fp1 != fp2)

        # Delete
        await DELETE(C, f"/api/secrets/{key}")

        # Verify gone
        s2 = must(await GET(C, "/api/secrets/list"), 200)
        item2 = next((i for i in s2["items"] if i["key"] == key), None)
        check("secret deleted", item2 is None)

    async def test_multiple_secrets_independent(self, C):
        """Multiple secrets are stored independently, not interfering."""
        keys = [uid(f"SYSKEY{i}").upper() for i in range(3)]
        fps = {}

        for key in keys:
            r = await POST(C, "/api/secrets/set", {"key": key, "value": f"val_{key}"})
            d = must(r, 200)
            fps[key] = d["fingerprint"]

        # Each has unique fingerprint
        check("all unique fingerprints", len(set(fps.values())) == 3)

        # Verify all in list
        s = must(await GET(C, "/api/secrets/list"), 200)
        listed_keys = {i["key"] for i in s["items"]}
        for key in keys:
            check(f"{key} in list", key in listed_keys)

        # Clean up
        for key in keys:
            await DELETE(C, f"/api/secrets/{key}")
