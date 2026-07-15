"""
UAT 12 — Enterprise Knowledge & Intelligence
User Stories:
  • As an enterprise user, I build a knowledge graph of our business domain
  • As a user, I create RAG pipelines to make AI answers grounded in our docs
  • As a user, swarm of agents gives me the best combined answer
  • As admin, I manage the agent leaderboard and governance policies

Acceptance Criteria at the USER level.
"""
from __future__ import annotations
import asyncio, time
import httpx, pytest
from .conftest import BASE, uid, GET, POST, PATCH, DELETE, j, accept, uat, no_error


class TestUATKnowledgeGraphEnterprise:
    """User Story: As an enterprise user, I map our business knowledge as a graph."""

    async def test_user_creates_entities_and_relations(self, U):
        """AC: User adds entities and links them → visible in graph view."""
        suffix = uid()
        e1 = j(await POST(U, "/api/knowledge-graph/entities", {
            "name": f"Agentic OS Platform {suffix}",
            "type": "product",
            "description": "AI operating system platform"
        }))
        uat("entity created", e1["ok"] is True)
        e1_id = e1["entity_id"]

        e2 = j(await POST(U, "/api/knowledge-graph/entities", {
            "name": f"Governance Framework {suffix}",
            "type": "concept",
            "description": "Policy and compliance framework"
        }))
        e2_id = e2["entity_id"]

        # Link them
        rel = j(await POST(U, "/api/knowledge-graph/relations", {
            "from_id": e1_id, "to_id": e2_id,
            "relation": "USES", "confidence": 0.95
        }))
        uat("relation created", rel["ok"] is True)

        # Stats updated
        stats = j(await GET(U, "/api/knowledge-graph/stats"))
        uat("entities count includes new entries", stats["entities"] >= 2)
        uat("relations count includes new entries", stats["relations"] >= 1)

    async def test_user_queries_knowledge_graph(self, U):
        """AC: User types a question → AI answers using the knowledge graph."""
        r = await POST(U, "/api/knowledge-graph/query", {
            "query": "What governance frameworks are used in this platform?"
        })
        no_error(r, "kg query")
        d = j(r)
        uat("query returns an answer", "answer" in d)
        uat("entities found are shown", "entities_found" in d)
        uat("query is reflected back", "query" in d)

    async def test_user_traverses_entity_graph(self, U):
        """AC: User clicks an entity → sees connected entities in a graph."""
        # First create a traversable entity
        e = j(await POST(U, "/api/knowledge-graph/entities", {
            "name": f"Traverse Test Entity {uid()}", "type": "test"
        }))
        entity_id = e["entity_id"]

        r = await GET(U, f"/api/knowledge-graph/traverse/{entity_id}", depth=2)
        no_error(r, "traverse graph")
        d = j(r)
        uat("traversal returns nodes", "nodes" in d)
        uat("traversal returns edges", "edges" in d)
        uat("start entity is included", d["start_entity"] == entity_id)

    async def test_user_can_clear_test_data(self, U):
        """AC: Admin can clear the knowledge graph when needed."""
        # Add something first
        await POST(U, "/api/knowledge-graph/entities", {
            "name": f"To Be Cleared {uid()}", "type": "test"
        })
        r = await U.delete("/api/knowledge-graph/clear")
        no_error(r, "clear kg")
        d = j(r)
        uat("graph cleared successfully", d["ok"] is True)


class TestUATRAGPipelines:
    """User Story: As a user, I ground AI responses in my company's documents."""

    async def test_user_creates_rag_pipeline(self, U):
        """AC: User creates a pipeline → it appears in the RAG panel."""
        r = await POST(U, "/api/rag/pipelines", {
            "name": f"UAT Product Docs Pipeline {uid()}",
            "description": "Ground answers in product documentation",
            "chunk_size": 500,
            "overlap": 50
        })
        no_error(r, "create RAG pipeline")
        d = j(r)
        uat("pipeline created", d["ok"] is True)
        uat("pipeline has trackable ID",
            "id" in d or "pipeline_id" in d)

    async def test_user_sees_rag_pipelines_list(self, U):
        """AC: User opens RAG pane → sees all their pipelines."""
        r = await GET(U, "/api/rag/pipelines")
        no_error(r, "list RAG pipelines")
        d = j(r)
        uat("pipeline list accessible", "pipelines" in d or isinstance(d, (list, dict)))


class TestUATSwarmIntelligence:
    """User Story: As a user, multiple agents collaborate to give me the best answer."""

    async def test_user_starts_swarm_with_multiple_agents(self, U):
        """AC: User selects agents → swarm runs and returns combined result."""
        r = await POST(U, "/api/swarm/run", {
            "prompt": "What are the top 3 benefits of using Python for AI development?",
            "agents": ["brain", "researcher", "builder"],
            "strategy": "judge",
            "max_tokens": 200
        })
        no_error(r, "swarm run")
        d = j(r)
        uat("swarm completed", d["ok"] is True)
        uat("all agents contributed", len(d.get("runs", [])) == 3)
        uat("winner selected", "winner" in d)
        uat("judge explanation provided", "judge_reason" in d)

    async def test_user_can_see_swarm_history(self, U):
        """AC: User can review past swarm runs."""
        r = await GET(U, "/api/swarm/history")
        no_error(r, "swarm history")
        uat("history accessible", isinstance(r.json(), (list, dict)))

    async def test_user_gets_error_with_single_agent(self, U):
        """AC: User accidentally selects only 1 agent → helpful error message."""
        r = await POST(U, "/api/swarm/run", {
            "prompt": "test", "agents": ["brain"]
        })
        no_error(r, "single agent swarm")
        d = j(r)
        uat("user gets helpful error (not crash)", d["ok"] is False)
        uat("error message is informative", "error" in d)


class TestUATLeaderboardGovernance:
    """User Story: As admin, I can monitor agent performance and set governance policies."""

    async def test_admin_sees_agent_leaderboard(self, U):
        """AC: Admin opens Leaderboard → sees agents ranked by performance."""
        r = await GET(U, "/api/agent-leaderboard", limit=10, days=30)
        no_error(r, "leaderboard")
        d = j(r)
        uat("leaderboard has rankings", "leaderboard" in d)
        for entry in d.get("leaderboard", [])[:3]:
            uat("each agent shows performance", "agent_id" in entry)

    async def test_admin_records_agent_performance(self, U):
        """AC: Platform records agent performance automatically."""
        r = await POST(U, "/api/agent-leaderboard/record", {
            "agent_id": "brain",
            "task_type": "research",
            "success": True,
            "tokens": 1500,
            "cost_usd": 0.009,
            "latency_ms": 2100
        })
        no_error(r, "record performance")
        d = j(r)
        uat("performance recorded", d.get("ok") is True)

    async def test_admin_sees_governance_summary(self, U):
        """AC: Admin sees platform-wide governance health."""
        r = await GET(U, "/api/agent-leaderboard/governance/summary")
        no_error(r, "governance summary")
        uat("governance summary accessible", isinstance(r.json(), dict))

    async def test_user_can_rate_an_agent(self, U):
        """AC: User can give thumbs up/down on agent output quality."""
        r = await POST(U, "/api/agent-leaderboard/rate", {
            "agent_id": "brain",
            "rating": 5,
            "comment": "Excellent research and clear explanation",
            "task_type": "research"
        })
        no_error(r, "rate agent")
        d = j(r)
        uat("rating recorded", d.get("ok") is True or "rating" in d)

    async def test_admin_views_agent_detail_stats(self, U):
        """AC: Admin drills into one agent for detailed performance history."""
        r = await GET(U, "/api/agent-leaderboard/agent/brain", days=30)
        no_error(r, "agent detail stats")
        uat("agent detail accessible", isinstance(r.json(), dict))
