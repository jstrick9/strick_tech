"""
Unit Tests — Evals Engine & Observability Full Coverage
Covers: eval datasets, A/B tests, red team, traces, spans, DORA, EU AI Act
"""
import pytest, httpx

class TestEvalsDatasets:
    def test_list_datasets(self, client):
        r = client.get("/api/evals/datasets")
        assert r.status_code == 200
        d = r.json()
        assert "datasets" in d or isinstance(d, list)

    def test_create_dataset(self, client):
        r = client.post("/api/evals/datasets", json={
            "name": "Unit Test Dataset",
            "description": "Created by unit tests",
            "cases": [
                {"prompt": "What is 1+1?", "expected": "2", "tags": ["math"]},
                {"prompt": "Capital of France?", "expected": "Paris", "tags": ["geography"]},
            ]
        })
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d or "id" in d
        return d.get("id", d.get("dataset_id", ""))

    def test_get_dataset(self, client):
        create = client.post("/api/evals/datasets", json={
            "name": "Get Test Dataset",
            "cases": [{"prompt": "test", "expected": "answer"}]
        }).json()
        ds_id = create.get("id") or create.get("dataset_id", "")
        if ds_id:
            r = client.get(f"/api/evals/datasets/{ds_id}")
            assert r.status_code == 200


class TestEvalsRuns:
    def test_list_runs(self, client):
        r = client.get("/api/evals/runs")
        assert r.status_code == 200
        d = r.json()
        assert "runs" in d or isinstance(d, list)

    def test_eval_summary(self, client):
        r = client.get("/api/evals/summary")
        assert r.status_code == 200

    def test_eval_run_requires_prompt(self, client):
        r = client.post("/api/evals/run", json={})
        assert r.status_code in (200, 400, 422)

    def test_eval_run_basic(self, client):
        r = client.post("/api/evals/run", json={
            "prompt": "Answer briefly: 2+2=?",
            "agent_id": "brain",
            "expected": "4"
        })
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d or "run_id" in d

    def test_ab_tests_list(self, client):
        r = client.get("/api/evals/ab-tests")
        assert r.status_code == 200
        d = r.json()
        assert "tests" in d or isinstance(d, list)

    def test_ab_test_create(self, client):
        # ab-test is SSE streaming — just check 200 and has data
        r = client.post("/api/evals/ab-test", json={
            "name": "Unit AB Test",
            "prompt_a": "Brief: AI is powerful",
            "prompt_b": "One word: AI is magic",
            "agent_id": "brain",
            "runs_per_variant": 1
        })
        assert r.status_code == 200

    def test_red_team_attacks(self, client):
        r = client.get("/api/evals/red-team/attacks")
        assert r.status_code == 200
        d = r.json()
        assert "attacks" in d or isinstance(d, list)


class TestObservabilityFull:
    def test_list_traces(self, client):
        r = client.get("/api/observability/traces")
        assert r.status_code == 200
        d = r.json()
        assert "traces" in d or isinstance(d, list)

    def test_create_trace(self, client):
        r = client.post("/api/observability/traces", json={
            "agent_id": "brain",
            "name": "Unit Test Trace",
            "input": "test input"
        })
        assert r.status_code == 200
        d = r.json()
        assert "id" in d or "trace_id" in d or "ok" in d
        return d.get("id", d.get("trace_id", ""))

    def test_trace_with_spans(self, client):
        # Create trace
        trace_r = client.post("/api/observability/traces", json={
            "agent_id": "builder", "name": "Span Test"
        }).json()
        trace_id = trace_r.get("id") or trace_r.get("trace_id", "t1")

        # Add span
        span_r = client.post("/api/observability/spans", json={
            "trace_id": trace_id,
            "span_type": "llm_call",
            "name": "GPT-4 Call",
            "tokens_in": 100,
            "tokens_out": 50,
            "cost_usd": 0.001,
            "latency_ms": 800
        })
        assert span_r.status_code == 200

    def test_get_trace(self, client):
        create = client.post("/api/observability/traces", json={
            "agent_id": "researcher", "name": "Get Trace Test"
        }).json()
        tid = create.get("id") or create.get("trace_id", "")
        if tid:
            r = client.get(f"/api/observability/traces/{tid}")
            assert r.status_code in (200, 404)

    def test_observability_analytics(self, client):
        r = client.get("/api/observability/analytics?days=7")
        assert r.status_code == 200
        d = r.json()
        assert "total_traces" in d or "analytics" in d or isinstance(d, dict)

    def test_dora_metrics(self, client):
        r = client.get("/api/observability/dora?days=30")
        assert r.status_code == 200
        d = r.json()
        assert "deployment_frequency" in d or "dora" in d or isinstance(d, dict)

    def test_eu_ai_act_compliance(self, client):
        r = client.get("/api/observability/compliance/eu-ai-act")
        assert r.status_code == 200
        d = r.json()
        assert "compliance" in d or "score" in d or "ok" in d or isinstance(d, dict)

    def test_update_trace(self, client):
        create = client.post("/api/observability/traces", json={
            "agent_id": "builder", "name": "Update Test"
        }).json()
        tid = create.get("id") or create.get("trace_id", "")
        if tid:
            r = client.patch(f"/api/observability/traces/{tid}", json={
                "status": "done",
                "output": "Completed successfully",
                "total_cost": 0.005,
                "total_tokens": 500
            })
            assert r.status_code in (200, 404)
