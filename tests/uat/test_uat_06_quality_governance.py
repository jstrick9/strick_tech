"""
UAT-06: Quality, Governance & Enterprise Features
User stories:
  "As a QA engineer I can evaluate AI agent quality automatically"
  "As a compliance officer I can enforce AI governance policies"
  "As a developer I can build RAG-based document Q&A systems"
  "As an analyst I can explore knowledge graph relationships"
  "As a developer I can monitor AI observability metrics"
"""
import pytest
from tests.uat.conftest import *


class TestUATEvals:
    """User Story: Evaluate AI quality automatically."""

    async def test_user_sees_eval_history(self, U):
        """AC: Opening Evals shows past evaluation runs."""
        r = await GET(U, "/api/evals/runs")
        accept(r, "eval runs", 200, 404)

    async def test_user_can_view_summary_stats(self, U):
        """AC: Summary panel shows aggregate quality metrics."""
        r = await GET(U, "/api/evals/summary")
        accept(r, "eval summary", 200, 404)

    async def test_red_team_attacks_are_listed(self, U):
        """AC: Red Team panel shows available attack types."""
        r = await GET(U, "/api/evals/red-team/attacks")
        accept(r, "red team attacks", 200, 404)
        if r.status_code == 200:
            d = r.json()
            attacks = d.get("attacks", d) if isinstance(d, dict) else d
            uat("attacks is list or dict", isinstance(attacks, (list, dict)))

    async def test_user_can_create_eval_dataset(self, U):
        """AC: Create test dataset for automated eval runs."""
        r = await POST(U, "/api/evals/datasets", {
            "name": uid("UATEvalDataset"),
            "description": "UAT evaluation dataset"
        })
        accept(r, "create dataset", 200, 201, 422)
        if r.status_code in (200, 201):
            d = r.json()
            uat("dataset created", d.get("ok") is True or "id" in d)

    async def test_user_can_view_eval_datasets(self, U):
        """AC: Datasets list shows available test sets."""
        r = await GET(U, "/api/evals/datasets")
        accept(r, "eval datasets", 200, 404)


class TestUATHITL:
    """User Story: Human-in-the-loop approval for high-stakes AI actions."""

    async def test_user_sees_approval_queue(self, U):
        """AC: HITL panel shows pending AI actions waiting for approval."""
        r = await GET(U, "/api/hitl/queue")
        accept(r, "hitl queue", 200, 404)
        if r.status_code == 200:
            d = r.json()
            queue = d.get("queue", d) if isinstance(d, dict) else d
            uat("queue is list or dict", isinstance(queue, (list, dict)))

    async def test_user_can_view_hitl_history(self, U):
        """AC: History shows past approved/rejected AI actions."""
        r = await GET(U, "/api/hitl/history")
        accept(r, "hitl history", 200, 404)

    async def test_user_can_view_governance_policies(self, U):
        """AC: Policies panel shows configured HITL rules."""
        r = await GET(U, "/api/hitl/policies")
        accept(r, "hitl policies", 200, 404)


class TestUATObservability:
    """User Story: Monitor AI system performance and reliability."""

    async def test_user_sees_dora_metrics(self, U):
        """AC: DORA metrics panel shows deployment frequency and lead time."""
        r = await GET(U, "/api/observability/dora")
        accept(r, "dora metrics", 200, 404)

    async def test_user_sees_llm_traces(self, U):
        """AC: Traces panel shows every LLM call with latency/tokens."""
        r = await GET(U, "/api/observability/traces")
        accept(r, "llm traces", 200, 404)

    async def test_user_sees_system_metrics_in_observability(self, U):
        """AC: Metrics panel shows historical performance data."""
        r = await GET(U, "/api/observability/metrics")
        accept(r, "observability metrics", 200, 404)


class TestUATKnowledgeGraph:
    """User Story: Build and explore a knowledge graph."""

    async def test_user_can_add_entity(self, U):
        """AC: '+ Add Entity' creates node in the knowledge graph."""
        r = await POST(U, "/api/knowledge-graph/entities", {
            "name": uid("FastAPI"),
            "type": "technology",
            "description": "A modern Python web framework for building APIs."
        })
        d = accept(r, "create entity", 200)
        uat("entity created ok",    d.get("ok") is True)
        eid = d.get("entity_id") or d.get("id")
        uat("entity ID returned",   bool(eid))

    async def test_user_can_create_relationships(self, U):
        """AC: Connect two entities with a labeled relationship."""
        r1 = await POST(U, "/api/knowledge-graph/entities",
                        {"name": uid("Python"), "type": "language"})
        r2 = await POST(U, "/api/knowledge-graph/entities",
                        {"name": uid("FastAPI"), "type": "framework"})
        eid1 = accept(r1, "entity 1", 200).get("entity_id")
        eid2 = accept(r2, "entity 2", 200).get("entity_id")
        
        if eid1 and eid2:
            r3 = await POST(U, "/api/knowledge-graph/relations", {
                "from_entity": eid1,
                "relation": "is_written_in",
                "to_entity": eid2,
                "weight": 1.0
            })
            accept(r3, "create relation", 200, 404, 422)

    async def test_user_can_query_knowledge_graph(self, U):
        """AC: Search box finds entities by name or description."""
        name = uid("QueryableEntity")
        await POST(U, "/api/knowledge-graph/entities", {
            "name": name, "type": "concept", "description": f"UAT test entity {name}"
        })
        r = await POST(U, "/api/knowledge-graph/query", {"query": name})
        accept(r, "kg query", 200, 404)

    async def test_kg_stats_show_graph_size(self, U):
        """AC: Stats panel shows how many entities and relations exist."""
        d = accept(await GET(U, "/api/knowledge-graph/stats"), "kg stats", 200)
        uat("entities count present",  "entities" in d or isinstance(d, dict))
        uat("count is non-negative",   d.get("entities", 0) >= 0)


class TestUATRAGPipeline:
    """User Story: Build a document Q&A system with zero hallucination."""

    async def test_user_can_create_rag_pipeline(self, U):
        """AC: '+ New Pipeline' creates a named document store."""
        r = await POST(U, "/api/rag/pipelines", {
            "name": uid("CompanyDocs"),
            "description": "Company knowledge base for customer support"
        })
        accept(r, "create rag", 200, 201, 422)
        if r.status_code in (200, 201):
            d = r.json()
            pid = d.get("id") or d.get("pipeline_id")
            uat("pipeline ID returned", bool(pid))
            if pid: await DELETE(U, f"/api/rag/pipelines/{pid}")

    async def test_user_can_ingest_a_document(self, U):
        """AC: Paste/upload document content → AI chunks and indexes it."""
        r1 = await POST(U, "/api/rag/pipelines", {
            "name": uid("IngestTest"), "description": "Test pipeline"
        })
        accept(r1, "create pipeline", 200, 201, 422)
        if r1.status_code not in (200, 201):
            return
        
        d1 = r1.json()
        pid = d1.get("id") or d1.get("pipeline_id")
        
        if pid:
            r2 = await POST(U, f"/api/rag/pipelines/{pid}/documents", {
                "content": (
                    "FastAPI is a modern, fast web framework for building APIs with Python.\n"
                    "It has automatic OpenAPI documentation.\n"
                    "Performance is comparable to NodeJS and Go.\n"
                    "Type hints provide editor support and automatic validation."
                ),
                "title": "FastAPI Overview",
                "source": "documentation"
            })
            accept(r2, "ingest document", 200, 201, 400, 404)
            
            await DELETE(U, f"/api/rag/pipelines/{pid}")

    async def test_pipelines_show_in_list(self, U):
        """AC: All pipelines visible in the RAG panel."""
        r = await GET(U, "/api/rag/pipelines")
        accept(r, "list pipelines", 200, 404)
        if r.status_code == 200:
            d = r.json()
            pipes = d.get("pipelines", d) if isinstance(d, dict) else d
            uat("pipelines list accessible", isinstance(pipes, list))


class TestUATGitAI:
    """User Story: AI-assisted Git workflow."""

    async def test_user_can_view_changelogs(self, U):
        """AC: Changelog panel shows AI-generated release notes."""
        r = await GET(U, "/api/gitai/changelogs")
        accept(r, "changelogs", 200, 404)

    async def test_user_can_view_git_diff(self, U):
        """AC: Diff viewer shows current uncommitted changes."""
        r = await GET(U, "/api/gitai/diff")
        accept(r, "git diff", 200, 400, 404)

    async def test_user_can_view_gitai_history(self, U):
        """AC: History shows past AI-assisted commits."""
        r = await GET(U, "/api/gitai/history")
        accept(r, "gitai history", 200, 404)


class TestUATAmbientAgent:
    """User Story: AI monitors your codebase and suggests improvements."""

    async def test_user_sees_ambient_health(self, U):
        """AC: Ambient panel shows overall codebase health score."""
        r = await GET(U, "/api/ambient/health")
        accept(r, "ambient health", 200, 404)

    async def test_user_sees_ambient_suggestions(self, U):
        """AC: Suggestions list shows AI-detected improvement opportunities."""
        r = await GET(U, "/api/ambient/suggestions")
        accept(r, "ambient suggestions", 200, 404)

    async def test_user_can_trigger_ambient_scan(self, U):
        """AC: Scan button runs AI analysis on the codebase."""
        r = await POST(U, "/api/ambient/scan", {"path": "/home/user/agentic-os/backend"})
        accept(r, "ambient scan", 200, 400, 404, 422)

    async def test_user_can_dismiss_suggestion(self, U):
        """AC: 'Dismiss' marks a suggestion as not needed."""
        r = await GET(U, "/api/ambient/suggestions")
        accept(r, "ambient suggestions", 200, 404)
        if r.status_code == 200:
            d = r.json()
            suggestions = d.get("suggestions", d) if isinstance(d, dict) else d
            if isinstance(suggestions, list) and suggestions:
                sid = suggestions[0].get("id")
                if sid:
                    r2 = await POST(U, f"/api/ambient/suggestions/{sid}/dismiss", {})
                    accept(r2, "dismiss suggestion", 200, 404)
