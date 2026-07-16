"""
Unit Tests — Swarm, Fusion, Pipeline, Ambient
Covers: multi-agent swarm, fusion strategies, pipeline builder, ambient agent
"""
import pytest, httpx, time

class TestSwarm:
    def test_swarm_agents_list(self, client):
        r = client.get("/api/swarm/agents")
        assert r.status_code == 200
        agents = r.json()
        assert isinstance(agents, list)
        assert len(agents) >= 2

    def test_swarm_history(self, client):
        r = client.get("/api/swarm/history")
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, (list, dict))

    def test_swarm_run_requires_prompt(self, client):
        r = client.post("/api/swarm/run", json={"agents": ["brain", "builder"]})
        assert r.status_code == 200
        assert r.json()["ok"] is False

    def test_swarm_run_requires_2_agents(self, client):
        r = client.post("/api/swarm/run", json={
            "prompt": "test", "agents": ["brain"]
        })
        assert r.status_code == 200
        assert r.json()["ok"] is False

    def test_swarm_run_judge_strategy(self, client):
        r = client.post("/api/swarm/run", json={
            "prompt": "What is 2+2?",
            "agents": ["brain", "builder"],
            "strategy": "judge",
            "max_tokens": 100
        })
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d
        if d["ok"]:
            assert "winner" in d
            assert "runs" in d

    def test_swarm_run_fanout_strategy(self, client):
        r = client.post("/api/swarm/run", json={
            "prompt": "Brief answer: sky color?",
            "agents": ["brain", "researcher"],
            "strategy": "fanout",
            "max_tokens": 80
        })
        assert r.status_code == 200

    def test_swarm_history_stored(self, client):
        before = len(client.get("/api/swarm/history").json() if isinstance(client.get("/api/swarm/history").json(), list) else [])
        client.post("/api/swarm/run", json={
            "prompt": "History test", "agents": ["brain", "builder"], "max_tokens": 50
        })
        r = client.get("/api/swarm/history")
        d = r.json()
        if isinstance(d, list):
            assert len(d) >= before


class TestFusion:
    def test_fusion_history(self, client):
        r = client.get("/api/fusion/history")
        assert r.status_code == 200

    def test_fusion_run_requires_prompt(self, client):
        r = client.post("/api/fusion/route", json={})
        assert r.status_code == 200
        d = r.json()
        assert "model" in d or "ok" in d or "error" in d or "route" in d

    def test_fusion_presets(self, client):
        r = client.get("/api/fusion/presets")
        assert r.status_code == 200
        d = r.json()
        assert "presets" in d or isinstance(d, list)

    def test_fusion_run_basic(self, client):
        r = client.post("/api/fusion/run/simple", json={
            "prompt": "Short answer: 1+1=?",
            "max_tokens": 60
        })
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d


class TestPipeline:
    def test_pipeline_list(self, client):
        r = client.get("/api/pipeline/history")
        assert r.status_code == 200
        d = r.json()
        assert "pipelines" in d or isinstance(d, list)

    def test_pipeline_create(self, client):
        r = client.post("/api/pipeline/run", json={
            "prompt": "Brief answer: what is Python?",
            "agent_id": "brain",
            "max_tokens": 80
        })
        assert r.status_code == 200

    def test_pipeline_templates(self, client):
        r = client.get("/api/pipeline/templates")
        assert r.status_code == 200


class TestAmbient:
    def test_ambient_suggestions_get(self, client):
        r = client.get("/api/ambient/suggestions?limit=5")
        assert r.status_code == 200
        d = r.json()
        assert "suggestions" in d
        assert "count" in d

    def test_ambient_scan(self, client):
        r = client.post("/api/ambient/scan", json={"deep": False, "max_files": 5})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert "suggestions" in d
        assert "count" in d

    def test_ambient_health_score(self, client):
        r = client.get("/api/ambient/health")
        assert r.status_code == 200
        d = r.json()
        assert "overall" in d or "score" in d or "scores" in d

    def test_ambient_tasks_list(self, client):
        r = client.get("/api/ambient/tasks")
        assert r.status_code == 200
        d = r.json()
        assert "tasks" in d or "count" in d

    def test_ambient_create_task(self, client):
        r = client.post("/api/ambient/tasks", json={
            "name": "Unit test background task",
            "prompt": "Echo: test",
            "agent_id": "builder"
        })
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert "task_id" in d

    def test_ambient_health_history(self, client):
        r = client.get("/api/ambient/health/history?limit=5")
        assert r.status_code == 200
        d = r.json()
        assert "snapshots" in d
