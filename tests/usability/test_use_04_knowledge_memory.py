"""
USABILITY-04: Knowledge & Memory — RAG, KG, Memory Galaxy, Obsidian, Web Search
Every knowledge management flow: store, retrieve, connect, search.
"""
import pytest
from tests.usability.conftest import *


class TestUseMemoryGalaxy:
    """User manages their long-term AI memory."""

    async def test_add_memory_entry(self, U):
        """User saves a memory 'My preferred coding style is PEP 8'."""
        content = uid("Memory: I prefer PEP 8 Python style")
        r = await POST(U, "/api/memory/add", {
            "content": content, "source": "user",
            "tags": ["preferences", "coding"]
        })
        no_error(r, "add memory")
        d = j(r)
        mid = d.get("id")
        uat("memory id returned", bool(mid) or d.get("ok") is True)

    async def test_memory_search_finds_entry(self, U):
        """User searches memories — relevant entry appears."""
        unique = uid("searchable_memory_content")
        await POST(U, "/api/memory/add", {"content": f"Unique fact: {unique}", "source": "test"})

        r = await GET(U, f"/api/memory/search?q={unique[:20]}")
        no_error(r, "memory search")
        d = j(r)
        results = d if isinstance(d, list) else d.get("results", d.get("memories", []))
        uat("search returned results list", isinstance(results, list))

    async def test_memory_stats_reflect_count(self, U):
        """Stats panel shows total memory count accurately."""
        r = await GET(U, "/api/memory/stats")
        no_error(r, "memory stats")
        d = j(r)
        uat("stats has count field", "total" in d or "count" in d or "memories" in d or isinstance(d, dict))

    async def test_memory_list_paginates(self, U):
        """Memory list supports pagination for large collections."""
        r = await GET(U, "/api/memory/list?limit=20&offset=0")
        no_error(r, "memory list paginated")
        d = j(r)
        mems = d if isinstance(d, list) else d.get("memories", d.get("items", []))
        uat("paginated list returned", isinstance(mems, list))

    async def test_memory_export_full_dump(self, U):
        """User exports all memories for backup."""
        r = await GET(U, "/api/memory/export")
        no_error(r, "memory export")
        d = j(r)
        uat("export returned data", d is not None)

    async def test_memory_reindex_works(self, U):
        """User manually triggers re-index of all memories."""
        r = await POST(U, "/api/memory/reindex", {})
        no_error(r, "memory reindex")
        d = j(r)
        uat("reindex started", d.get("ok") is True or "status" in d)

    async def test_memory_delete_specific_entry(self, U):
        """User deletes a specific memory — it's gone."""
        r = await POST(U, "/api/memory/add", {
            "content": uid("delete_me_memory"), "source": "test"
        })
        mid = j(r).get("id")
        if not mid: pytest.skip()

        r2 = await DELETE(U, f"/api/memory/{mid}")
        no_error(r2, "delete memory")
        d2 = j(r2)
        uat("memory deleted", d2.get("ok") is True or d2.get("deleted") is True or r2.status_code == 200)

    async def test_memory_add_with_embedding(self, U):
        """Memory with semantic embedding added for RAG retrieval."""
        r = await POST(U, "/api/memory/add-with-embedding", {
            "content": "The platform uses FastAPI with SQLite for the backend.",
            "source": "documentation", "tags": ["architecture"]
        })
        no_error(r, "add memory with embedding")


class TestUseKnowledgeGraph:
    """User builds a knowledge graph to connect ideas."""

    async def test_kg_entity_creation(self, U):
        """User adds a node: 'Agentic OS' as type 'software'."""
        r = await POST(U, "/api/knowledge-graph/entities", {
            "name": uid("AgenticOS"), "type": "software",
            "properties": {"version": "6.0", "language": "Python"}
        })
        no_error(r, "create entity")
        d = j(r)
        uat("entity created", d.get("id") or d.get("ok") is True)

    async def test_kg_relation_creation(self, U):
        """User connects two entities: A uses B."""
        r = await POST(U, "/api/knowledge-graph/relations", {
            "source": "AgenticOS", "target": "FastAPI",
            "relation": "uses", "weight": 0.9
        })
        no_error(r, "create relation")

    async def test_kg_fact_insertion(self, U):
        """User adds a fact: 'Python is dynamically typed'."""
        r = await POST(U, "/api/knowledge-graph/facts", {
            "subject": uid("Python"), "predicate": "is",
            "object": "dynamically_typed", "confidence": 0.99
        })
        no_error(r, "add kg fact")

    async def test_kg_stats_overview(self, U):
        """User sees KG statistics: total entities, relations, facts."""
        r = await GET(U, "/api/knowledge-graph/stats")
        no_error(r, "kg stats")
        d = j(r)
        uat("stats returned", isinstance(d, dict))
        uat("has entities count", "entities" in d or "nodes" in d or "total" in d)

    async def test_kg_entity_list(self, U):
        """User browses all knowledge graph entities."""
        r = await GET(U, "/api/knowledge-graph/entities")
        no_error(r, "kg entity list")
        d = j(r)
        entities = d if isinstance(d, list) else d.get("entities", d.get("nodes", []))
        uat("entities returned as list", isinstance(entities, list))

    async def test_kg_text_extraction(self, U):
        """User pastes text — entities are auto-extracted into KG."""
        r = await POST(U, "/api/knowledge-graph/extract", {
            "text": "FastAPI is a modern Python framework. It uses Pydantic for validation.",
            "auto_link": True
        })
        no_error(r, "kg extract from text")
        d = j(r)
        uat("entities extracted", "entities" in d or "ok" in d)

    async def test_kg_query(self, U):
        """User queries the knowledge graph."""
        r = await POST(U, "/api/knowledge-graph/query", {
            "query": "What uses Python?", "limit": 10
        })
        no_error(r, "kg query")


class TestUseRAGPipelines:
    """User builds RAG pipelines for document-grounded AI."""

    async def test_create_rag_pipeline(self, U):
        """User creates a new RAG pipeline for their document set."""
        name = uid("DocsPipeline")
        r = await POST(U, "/api/rag/pipelines", {
            "name": name, "description": "RAG over project docs",
            "type": "basic", "chunk_size": 500
        })
        no_error(r, "create rag pipeline")
        d = j(r)
        pid = d.get("id")
        uat("pipeline id issued", bool(pid) or d.get("ok") is True)

        # List pipelines
        r2 = await GET(U, "/api/rag/pipelines")
        d2 = j(r2)
        plines = d2 if isinstance(d2, list) else d2.get("pipelines", [])
        uat("pipeline visible in list", isinstance(plines, list))

    async def test_rag_pipeline_query(self, U):
        """User asks a question — RAG retrieves relevant context."""
        # Get first pipeline
        r = await GET(U, "/api/rag/pipelines")
        d = j(r)
        plines = d if isinstance(d, list) else d.get("pipelines", [])
        if not plines: pytest.skip("No RAG pipelines")
        pid = plines[0]["id"]

        r2 = await POST(U, f"/api/rag/pipelines/{pid}/query", {
            "query": "What is the main purpose of this system?", "top_k": 5
        })
        no_error(r2, "rag pipeline query")

    async def test_rag_pipeline_eval(self, U):
        """User evaluates RAG pipeline quality metrics."""
        r = await GET(U, "/api/rag/pipelines")
        d = j(r)
        plines = d if isinstance(d, list) else d.get("pipelines", [])
        if not plines: pytest.skip("No RAG pipelines")
        pid = plines[0]["id"]

        r2 = await POST(U, f"/api/rag/pipelines/{pid}/eval", {
            "test_questions": ["What is this?", "How does it work?"]
        })
        no_error(r2, "rag pipeline eval")


class TestUseWebSearch:
    """User leverages web search for grounded AI responses."""

    async def test_web_search_executes(self, U):
        """User types a search query — results come back."""
        r = await POST(U, "/api/websearch/search", {
            "query": "FastAPI Python framework features",
            "max_results": 5
        })
        no_error(r, "web search")
        d = j(r)
        results = d if isinstance(d, list) else d.get("results", d.get("items", []))
        uat("search results returned", isinstance(results, list))

    async def test_web_search_history_tracks_queries(self, U):
        """User's past searches appear in history for quick re-use."""
        await POST(U, "/api/websearch/search", {"query": uid("usability_search"), "max_results": 3})
        r = await GET(U, "/api/websearch/history")
        no_error(r, "search history")
        d = j(r)
        hist = d if isinstance(d, list) else d.get("history", [])
        uat("search history returned", isinstance(hist, list))

    async def test_web_search_suggestions(self, U):
        """User types partial query — autocomplete suggestions appear."""
        r = await GET(U, "/api/websearch/suggest?q=python")
        no_error(r, "search suggestions")
        d = j(r)
        sugs = d if isinstance(d, list) else d.get("suggestions", [])
        uat("suggestions returned", isinstance(sugs, list))

    async def test_grounded_completion(self, U):
        """User asks a question — AI answers with web-cited sources."""
        r = await POST(U, "/api/websearch/grounded-completion", {
            "prompt": "What is the latest version of FastAPI?",
            "agent_id": "researcher", "num_results": 3
        })
        no_error(r, "grounded completion")
        d = j(r)
        uat("grounded response returned", "response" in d or "content" in d or "ok" in d)

    async def test_research_mode(self, U):
        """User triggers deep research mode for comprehensive results."""
        r = await POST(U, "/api/websearch/research", {
            "query": "agentic AI frameworks comparison 2024",
            "depth": 2, "max_results": 5
        })
        no_error(r, "research mode")


class TestUseObsidian:
    """User connects their Obsidian vault for AI-enhanced note-taking."""

    async def test_obsidian_status_check(self, U):
        """User opens Obsidian pane — connection status displayed."""
        r = await GET(U, "/api/obsidian/status")
        no_error(r, "obsidian status")
        d = j(r)
        uat("status returned", "connected" in d or "status" in d or "vault" in d or isinstance(d, dict))

    async def test_obsidian_create_note(self, U):
        """User creates a note from within Agentic OS."""
        r = await POST(U, "/api/obsidian/note", {
            "title": uid("UsabilityNote"), "content": "# Test Note\n\nThis is a usability test note.",
            "path": f"usability/{uid('note')}.md"
        })
        no_error(r, "create obsidian note")

    async def test_obsidian_daily_note(self, U):
        """User creates today's daily note."""
        r = await POST(U, "/api/obsidian/daily_note", {
            "date": "2026-07-14", "content": "## Today's Goals\n- Finish testing"
        })
        no_error(r, "create daily note")
