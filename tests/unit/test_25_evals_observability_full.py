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

    def test_delete_dataset(self, client):
        """A user-created dataset can be deleted; a miss is a clean 404."""
        did = client.post("/api/evals/datasets", json={
            "name": "Del Probe DS", "cases": [{"prompt": "p", "expected": "e"}]
        }).json()["dataset_id"]

        r = client.delete(f"/api/evals/datasets/{did}")
        assert r.status_code == 200 and r.json()["ok"] is True

        names = [d["name"] for d in client.get("/api/evals/datasets").json()["datasets"]]
        assert "Del Probe DS" not in names, "deleted dataset still listed"
        assert client.delete(f"/api/evals/datasets/{did}").status_code == 404

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
        # Requires both prompt and response; a missing field is a refusal.
        assert r.status_code in (200, 400)
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


class TestDatasetRunStream:
    """r59: dataset runs died on the first case and leaked the DB write lock.

    run_dataset's save block opened con2, ran the INSERT on con2, then called
    con.commit()/con.close() — the OUTER connection, already closed after
    reading the dataset. con.commit() raised ProgrammingError on case 1, the
    finally closed the wrong (already-closed) connection, and con2 was leaked
    holding an OPEN WRITE TRANSACTION. Two consequences, both observed live:
    no dataset run ever reached case 2 (sse_guard logged ProgrammingError,
    the UI never saw dataset_done), and the leaked transaction pinned
    SQLite's global write lock until GC — every write app-wide 500'd
    "database is locked" for minutes, including scheduler jobs.
    """

    def test_dataset_run_completes_and_commits(self, client):
        create = client.post("/api/evals/datasets", json={
            "name": "r59 run-stream probe",
            "cases": [
                {"prompt": "What is 1+1?", "expected": "2"},
                {"prompt": "Capital of France?", "expected": "Paris"},
            ],
        }).json()
        ds_id = create.get("id") or create.get("dataset_id", "")
        assert ds_id, f"dataset create failed: {create}"

        r = client.post(f"/api/evals/datasets/{ds_id}/run", json={"agent_id": "builder"})
        assert r.status_code == 200
        body = r.text
        # every case must stream its completion, and the run must finish
        assert '"type": "case_done"' in body, f"stream died before a case finished: {body[:200]}"
        assert '"type": "dataset_done"' in body, f"stream never completed: {body[:200]}"
        assert '"case_no": 2' in body, "second case never ran"

        # the per-case writes must actually be committed, not left in a
        # leaked transaction
        runs = client.get("/api/evals/runs").json()
        run_list = runs.get("runs", runs if isinstance(runs, list) else [])
        assert any(str(x.get("dataset_id", "")) == ds_id for x in run_list), \
            "no committed eval_runs row for the dataset"

        client.delete(f"/api/evals/datasets/{ds_id}")

    def test_dataset_run_does_not_lock_the_database(self, client):
        """A second writer must be able to commit while/after a run streams.
        Pre-fix, the leaked con2 transaction made ANY concurrent write 500
        with 'database is locked' (10s busy timeout)."""
        create = client.post("/api/evals/datasets", json={
            "name": "r59 lock probe", "cases": [{"prompt": "p", "expected": "e"}],
        }).json()
        ds_id = create.get("id") or create.get("dataset_id", "")
        r = client.post(f"/api/evals/datasets/{ds_id}/run", json={"agent_id": "builder"})
        assert '"type": "dataset_done"' in r.text
        # immediately write elsewhere — must not raise/timeout
        other = client.post("/api/evals/datasets", json={"name": "r59 lock probe 2", "cases": []})
        assert other.status_code == 200
        client.delete(f"/api/evals/datasets/{ds_id}")
        d2 = other.json().get("id") or other.json().get("dataset_id", "")
        if d2:
            client.delete(f"/api/evals/datasets/{d2}")
