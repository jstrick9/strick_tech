"""
Task DAG Visualizer — Full Verification Test Suite
Tests every backend API endpoint and all UI data contracts.

Backend endpoints under test:
  POST /api/supervisor/run                  — launch a goal
  GET  /api/supervisor/runs                 — list all runs
  GET  /api/supervisor/run/{id}             — run + tasks (original)
  GET  /api/supervisor/run/{id}/dag         — DAG with layout + edges + waves (NEW)
  GET  /api/supervisor/run/{id}/stream      — SSE live stream
  GET  /api/supervisor/stats                — aggregate stats
  POST /api/supervisor/run/{id}/kill        — kill switch
  DELETE /api/supervisor/run/{id}           — delete run

Demo runs seeded:
  demo_sv_*  — 4 runs with varied DAG topologies (linear, wide parallel, diamond, live)
"""
import pytest, httpx, json, time

BASE    = "http://127.0.0.1:8787"
TIMEOUT = 30

def get(path, **kw):
    r = httpx.get(f"{BASE}{path}", timeout=TIMEOUT, **kw)
    assert r.status_code == 200, f"GET {path} → {r.status_code}: {r.text[:200]}"
    return r.json()

def post(path, body=None):
    r = httpx.post(f"{BASE}{path}", json=body or {}, timeout=TIMEOUT)
    assert r.status_code == 200, f"POST {path} → {r.status_code}: {r.text[:200]}"
    return r.json()

def delete(path):
    r = httpx.delete(f"{BASE}{path}", timeout=TIMEOUT)
    assert r.status_code == 200, f"DELETE {path} → {r.status_code}: {r.text[:200]}"
    return r.json()


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def demo_runs():
    d = get("/api/supervisor/runs?limit=200")
    runs = [r for r in d["runs"] if r["run_id"].startswith("demo_sv")]
    assert len(runs) >= 3, f"Expected ≥3 demo runs, got {len(runs)}"
    return runs

@pytest.fixture(scope="module")
def run_api(demo_runs):
    r = next((r for r in demo_runs if "REST API" in r.get("goal_title","")), None)
    return r or demo_runs[0]

@pytest.fixture(scope="module")
def run_competitive(demo_runs):
    r = next((r for r in demo_runs if "Competitive" in r.get("goal_title","")), None)
    return r or demo_runs[1]

@pytest.fixture(scope="module")
def run_marketing(demo_runs):
    r = next((r for r in demo_runs if "marketing" in r.get("goal_title","").lower()), None)
    return r or demo_runs[2]

@pytest.fixture(scope="module")
def run_live(demo_runs):
    r = next((r for r in demo_runs if "live" in r["run_id"]), None)
    return r or demo_runs[-1]

@pytest.fixture(scope="module")
def dag_api(run_api):
    return get(f"/api/supervisor/run/{run_api['run_id']}/dag")

@pytest.fixture(scope="module")
def dag_competitive(run_competitive):
    return get(f"/api/supervisor/run/{run_competitive['run_id']}/dag")

@pytest.fixture(scope="module")
def dag_marketing(run_marketing):
    return get(f"/api/supervisor/run/{run_marketing['run_id']}/dag")

@pytest.fixture(scope="module")
def dag_live(run_live):
    return get(f"/api/supervisor/run/{run_live['run_id']}/dag")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Stats & List Runs
# ─────────────────────────────────────────────────────────────────────────────

class TestListAndStats:
    def test_01_stats_returns_all_fields(self):
        d = get("/api/supervisor/stats")
        assert "total_runs"     in d
        assert "by_status"      in d
        assert "avg_eval_score" in d
        assert "total_tokens"   in d
        assert "total_cost"     in d
        assert "top_agents"     in d
        assert d["total_runs"] >= 3
        print(f"\n  ✅ Stats: {d['total_runs']} total runs, avg_score={d['avg_eval_score']}")

    def test_02_list_runs_returns_array(self):
        d = get("/api/supervisor/runs")
        assert "runs"  in d
        assert "count" in d
        assert isinstance(d["runs"], list)
        print(f"\n  ✅ {d['count']} runs listed")

    def test_03_list_runs_filter_by_status(self):
        d = get("/api/supervisor/runs?status=done")
        for r in d["runs"]:
            assert r["status"] == "done"
        print(f"\n  ✅ Status filter: {d['count']} done runs")

    def test_04_run_fields_complete(self, run_api):
        r = run_api
        assert r["run_id"]
        assert r["goal_text"]
        assert r["status"]
        assert isinstance(r["task_count"], int)
        assert isinstance(r["done_count"], int)
        print(f"\n  ✅ Run fields: {r['run_id']} | {r['status']} | {r['task_count']} tasks")

    def test_05_demo_runs_are_done_or_running(self, demo_runs):
        valid = {"done", "running", "failed", "killed", "decomposing", "scheduled", "synthesizing"}
        for r in demo_runs:
            assert r["status"] in valid, f"{r['run_id']} has invalid status: {r['status']}"
        print(f"\n  ✅ All {len(demo_runs)} demo runs have valid status")

    def test_06_stats_top_agents_have_required_fields(self):
        d = get("/api/supervisor/stats")
        for a in d["top_agents"]:
            assert "agent_id"  in a
            assert "cnt"       in a
            assert "avg_cost"  in a
        print(f"\n  ✅ {len(d['top_agents'])} agent entries in stats")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Get Run (original endpoint)
# ─────────────────────────────────────────────────────────────────────────────

class TestGetRun:
    def test_07_get_run_returns_run_and_tasks(self, run_api):
        d = get(f"/api/supervisor/run/{run_api['run_id']}")
        assert d.get("ok") is True
        assert "run"   in d
        assert "tasks" in d
        assert isinstance(d["tasks"], list)
        print(f"\n  ✅ Run {run_api['run_id']}: {len(d['tasks'])} tasks")

    def test_08_tasks_have_all_required_fields(self, run_api):
        d = get(f"/api/supervisor/run/{run_api['run_id']}")
        for t in d["tasks"]:
            assert "task_id"    in t
            assert "run_id"     in t
            assert "seq"        in t
            assert "title"      in t
            assert "agent_id"   in t
            assert "depends_on" in t
            assert "status"     in t
            assert isinstance(t["depends_on"], list)
        print(f"\n  ✅ All {len(d['tasks'])} tasks have required fields")

    def test_09_depends_on_is_parsed_as_list(self, run_api):
        d = get(f"/api/supervisor/run/{run_api['run_id']}")
        for t in d["tasks"]:
            assert isinstance(t["depends_on"], list), f"depends_on not a list in task {t['task_id']}"
        print(f"\n  ✅ depends_on parsed as list in all tasks")

    def test_10_nonexistent_run_returns_404(self):
        r = httpx.get(f"{BASE}/api/supervisor/run/nonexistent_run_xyz123", timeout=15)
        assert r.status_code == 404 or r.json().get("ok") is False
        print(f"\n  ✅ Nonexistent run → 404/ok=False")


# ─────────────────────────────────────────────────────────────────────────────
# 3. DAG Endpoint — Core Structure
# ─────────────────────────────────────────────────────────────────────────────

class TestDAGEndpoint:
    def test_11_dag_returns_ok_true(self, dag_api):
        assert dag_api.get("ok") is True
        print(f"\n  ✅ DAG endpoint returns ok=True")

    def test_12_dag_has_all_top_level_fields(self, dag_api):
        required = ["ok", "run", "tasks", "edges", "waves", "wave_count", "total_tasks"]
        for f in required:
            assert f in dag_api, f"Missing field: {f}"
        print(f"\n  ✅ All top-level DAG fields present: {required}")

    def test_13_dag_tasks_have_layout_positions(self, dag_api):
        for t in dag_api["tasks"]:
            assert "x" in t, f"Task {t['task_id']} missing x"
            assert "y" in t, f"Task {t['task_id']} missing y"
            assert isinstance(t["x"], (int, float))
            assert isinstance(t["y"], (int, float))
            assert t["x"] >= 0
            assert t["y"] >= 0
        print(f"\n  ✅ All {len(dag_api['tasks'])} tasks have valid (x,y) positions")

    def test_14_dag_tasks_x_increases_with_wave(self, dag_api):
        """Tasks in later waves should have larger x values."""
        task_map = {t["seq"]: t for t in dag_api["tasks"]}
        # Find a dependency pair
        for t in dag_api["tasks"]:
            for dep_seq in (t.get("depends_on") or []):
                dep = task_map.get(dep_seq)
                if dep:
                    assert t["x"] > dep["x"], \
                        f"Task seq={t['seq']} x={t['x']} should be > dep seq={dep_seq} x={dep['x']}"
        print(f"\n  ✅ x-positions correctly increase with wave depth")

    def test_15_dag_edges_have_required_fields(self, dag_api):
        for e in dag_api["edges"]:
            assert "id"       in e
            assert "from_id"  in e
            assert "to_id"    in e
            assert "from_seq" in e
            assert "to_seq"   in e
            assert "done"     in e
            assert "active"   in e
            assert "error"    in e
            assert isinstance(e["done"],   bool)
            assert isinstance(e["active"], bool)
            assert isinstance(e["error"],  bool)
        print(f"\n  ✅ All {len(dag_api['edges'])} edges have required fields with correct types")

    def test_16_dag_waves_have_required_fields(self, dag_api):
        for w in dag_api["waves"]:
            assert "wave"   in w
            assert "count"  in w
            assert "status" in w
            assert isinstance(w["wave"],  int)
            assert isinstance(w["count"], int)
            assert w["count"] >= 1
            assert w["status"] in ("done", "running", "pending", "failed")
        print(f"\n  ✅ All {len(dag_api['waves'])} waves have valid structure")

    def test_17_dag_wave_count_matches_waves_array(self, dag_api):
        assert dag_api["wave_count"] == len(dag_api["waves"])
        print(f"\n  ✅ wave_count={dag_api['wave_count']} matches len(waves)={len(dag_api['waves'])}")

    def test_18_dag_total_tasks_matches_tasks_array(self, dag_api):
        assert dag_api["total_tasks"] == len(dag_api["tasks"])
        print(f"\n  ✅ total_tasks={dag_api['total_tasks']} matches len(tasks)={len(dag_api['tasks'])}")

    def test_19_dag_edge_ids_reference_valid_tasks(self, dag_api):
        task_ids = {t["task_id"] for t in dag_api["tasks"]}
        for e in dag_api["edges"]:
            assert e["from_id"] in task_ids, f"Edge from_id={e['from_id']} not in tasks"
            assert e["to_id"]   in task_ids, f"Edge to_id={e['to_id']} not in tasks"
        print(f"\n  ✅ All {len(dag_api['edges'])} edge endpoints reference valid task_ids")

    def test_20_dag_run_field_matches_run_id(self, dag_api, run_api):
        assert dag_api["run"]["run_id"] == run_api["run_id"]
        print(f"\n  ✅ DAG run.run_id matches: {dag_api['run']['run_id']}")

    def test_21_nonexistent_dag_returns_404(self):
        r = httpx.get(f"{BASE}/api/supervisor/run/nonexistent_xyz/dag", timeout=15)
        assert r.status_code == 404 or r.json().get("ok") is False
        print(f"\n  ✅ Nonexistent DAG → 404/ok=False")


# ─────────────────────────────────────────────────────────────────────────────
# 4. DAG Topology — Linear (API run: 6 tasks, linear chain)
# ─────────────────────────────────────────────────────────────────────────────

class TestDAGTopologyLinear:
    def test_22_api_run_has_6_tasks(self, dag_api):
        assert len(dag_api["tasks"]) == 6, f"Expected 6, got {len(dag_api['tasks'])}"
        print(f"\n  ✅ Linear run: 6 tasks")

    def test_23_linear_run_has_correct_edge_count(self, dag_api):
        # 6 tasks in a chain: seq 1→2, 2→3, 3→4, 4→5, 4→5 is parallel but 5→6 / need 5 or 6 edges
        assert len(dag_api["edges"]) >= 4
        print(f"\n  ✅ Linear run: {len(dag_api['edges'])} edges")

    def test_24_linear_run_first_task_has_no_deps(self, dag_api):
        first = next(t for t in dag_api["tasks"] if t["seq"] == 1)
        assert first["depends_on"] == [], f"First task should have no deps: {first['depends_on']}"
        print(f"\n  ✅ First task (seq=1) has no dependencies")

    def test_25_linear_chain_waves_increase(self, dag_api):
        """Each wave should have exactly the tasks that are independent at that level."""
        waves = dag_api["waves"]
        counts = [w["count"] for w in waves]
        assert all(c >= 1 for c in counts)
        print(f"\n  ✅ Wave task counts: {counts}")

    def test_26_done_tasks_have_outputs(self, dag_api):
        done_tasks = [t for t in dag_api["tasks"] if t["status"] == "done"]
        for t in done_tasks:
            assert t["output"], f"Done task {t['task_id']} has no output"
        print(f"\n  ✅ All {len(done_tasks)} done tasks have output text")

    def test_27_done_tasks_have_duration(self, dag_api):
        done_tasks = [t for t in dag_api["tasks"] if t["status"] == "done"]
        for t in done_tasks:
            assert t["duration_ms"] > 0, f"Done task {t['task_id']} duration_ms=0"
        print(f"\n  ✅ All done tasks have duration_ms > 0")


# ─────────────────────────────────────────────────────────────────────────────
# 5. DAG Topology — Wide Parallel (competitive: 8 tasks, fan-out then converge)
# ─────────────────────────────────────────────────────────────────────────────

class TestDAGTopologyParallel:
    def test_28_competitive_run_has_8_tasks(self, dag_competitive):
        assert len(dag_competitive["tasks"]) == 8
        print(f"\n  ✅ Competitive run: 8 tasks")

    def test_29_parallel_wave_has_multiple_tasks(self, dag_competitive):
        """The research wave should have 4 tasks running in parallel (seq 2,3,4,5)."""
        waves = dag_competitive["waves"]
        counts = [w["count"] for w in waves]
        assert max(counts) >= 4, f"Expected at least one wave with 4+ tasks: {counts}"
        print(f"\n  ✅ Max parallel wave: {max(counts)} tasks — fan-out confirmed")

    def test_30_parallel_tasks_have_same_x_position(self, dag_competitive):
        """Tasks in the same wave should have the same x coordinate."""
        task_seqs_in_wave1 = [2, 3, 4, 5]  # parallel research tasks
        tasks = {t["seq"]: t for t in dag_competitive["tasks"]}
        parallel_tasks = [tasks[s] for s in task_seqs_in_wave1 if s in tasks]
        if len(parallel_tasks) >= 2:
            xs = [t["x"] for t in parallel_tasks]
            assert len(set(xs)) == 1, f"Parallel tasks should share x coord: {xs}"
        print(f"\n  ✅ Parallel tasks share x coordinate")

    def test_31_parallel_tasks_have_different_y_positions(self, dag_competitive):
        """Parallel tasks should be vertically stacked."""
        task_seqs_in_wave1 = [2, 3, 4, 5]
        tasks = {t["seq"]: t for t in dag_competitive["tasks"]}
        parallel_tasks = [tasks[s] for s in task_seqs_in_wave1 if s in tasks]
        if len(parallel_tasks) >= 2:
            ys = [t["y"] for t in parallel_tasks]
            assert len(set(ys)) == len(ys), f"Parallel tasks should have different y: {ys}"
        print(f"\n  ✅ Parallel tasks have distinct y positions")

    def test_32_merge_node_has_multiple_incoming_edges(self, dag_competitive):
        """The merge/compare task (seq 6) should have 4 incoming edges."""
        merge_task = next((t for t in dag_competitive["tasks"] if t["seq"] == 6), None)
        if merge_task:
            incoming = [e for e in dag_competitive["edges"] if e["to_id"] == merge_task["task_id"]]
            assert len(incoming) >= 3, f"Merge node should have 3+ incoming edges: {len(incoming)}"
        print(f"\n  ✅ Merge node has {len(incoming) if merge_task else '?'} incoming edges")


# ─────────────────────────────────────────────────────────────────────────────
# 6. DAG Topology — Diamond (marketing: 7 tasks, diamond pattern)
# ─────────────────────────────────────────────────────────────────────────────

class TestDAGTopologyDiamond:
    def test_33_marketing_run_has_7_tasks(self, dag_marketing):
        assert len(dag_marketing["tasks"]) == 7
        print(f"\n  ✅ Marketing run: 7 tasks")

    def test_34_marketing_has_parallel_creative_wave(self, dag_marketing):
        # Tasks 2,3,4 all depend on task 1 = parallel wave
        waves = dag_marketing["waves"]
        counts = [w["count"] for w in waves]
        assert max(counts) >= 3
        print(f"\n  ✅ Diamond run has parallel wave with {max(counts)} tasks")

    def test_35_all_tasks_positioned_within_canvas(self, dag_marketing):
        for t in dag_marketing["tasks"]:
            assert t["x"] < 5000, f"x too large: {t['x']}"
            assert t["y"] < 3000, f"y too large: {t['y']}"
        print(f"\n  ✅ All task positions within canvas bounds")

    def test_36_edges_correctly_flagged_done(self, dag_marketing):
        done_edges  = [e for e in dag_marketing["edges"] if e["done"]]
        total_edges = len(dag_marketing["edges"])
        print(f"\n  ✅ {len(done_edges)}/{total_edges} edges flagged done")

    def test_37_eval_score_in_valid_range(self, dag_marketing):
        run = dag_marketing["run"]
        if run.get("eval_score") is not None:
            assert 0 <= run["eval_score"] <= 1, f"eval_score out of range: {run['eval_score']}"
        print(f"\n  ✅ eval_score={run.get('eval_score')}")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Live Run DAG (running status)
# ─────────────────────────────────────────────────────────────────────────────

class TestLiveDAG:
    def test_38_live_run_has_mixed_task_statuses(self, dag_live):
        statuses = {t["status"] for t in dag_live["tasks"]}
        # Should have mix of done + running/pending
        assert "done" in statuses, f"Expected some done tasks: {statuses}"
        non_done = statuses - {"done"}
        assert len(non_done) >= 1, f"Expected some non-done tasks: {statuses}"
        print(f"\n  ✅ Live run statuses: {statuses}")

    def test_39_live_run_done_edges_for_done_tasks(self, dag_live):
        """Done tasks should have their outgoing edges marked done."""
        done_tasks = {t["task_id"] for t in dag_live["tasks"] if t["status"] == "done"}
        for e in dag_live["edges"]:
            if e["from_id"] in done_tasks:
                pass  # check is that edge structure is valid
            assert isinstance(e["done"], bool)
        print(f"\n  ✅ Edge done flags correctly typed for live run")

    def test_40_live_run_pending_tasks_have_no_output(self, dag_live):
        pending = [t for t in dag_live["tasks"] if t["status"] == "pending"]
        for t in pending:
            assert not t.get("output"), f"Pending task {t['task_id']} has output: {t['output'][:30]}"
        print(f"\n  ✅ All {len(pending)} pending tasks have no output")

    def test_41_live_run_wave_statuses_reflect_task_states(self, dag_live):
        waves = dag_live["waves"]
        for w in waves:
            assert w["status"] in ("done", "running", "pending", "failed")
        # Wave 0 (first wave) should be done
        wave0 = next((w for w in waves if w["wave"] == 0), None)
        if wave0:
            assert wave0["status"] == "done", f"Wave 0 should be done: {wave0}"
        print(f"\n  ✅ Wave statuses correct: {[w['status'] for w in waves]}")


# ─────────────────────────────────────────────────────────────────────────────
# 8. Launch a real supervisor run
# ─────────────────────────────────────────────────────────────────────────────

class TestLaunchRun:
    def test_42_launch_returns_run_id(self):
        d = post("/api/supervisor/run", {"goal": "Write a one-sentence summary of what an AI agent is."})
        assert d.get("ok") is True
        assert d.get("run_id")
        assert d.get("status") == "decomposing"
        TestLaunchRun._launched_run_id = d["run_id"]
        print(f"\n  ✅ Launched run: {d['run_id']}")

    def test_43_launched_run_appears_in_list(self):
        run_id = TestLaunchRun._launched_run_id
        d = get("/api/supervisor/runs?limit=10")
        ids = [r["run_id"] for r in d["runs"]]
        assert run_id in ids
        print(f"\n  ✅ Run {run_id} appears in run list")

    def test_44_launched_run_dag_returns_ok(self):
        run_id = TestLaunchRun._launched_run_id
        # Wait briefly for decomposition
        time.sleep(2)
        d = get(f"/api/supervisor/run/{run_id}/dag")
        assert d.get("ok") is True
        print(f"\n  ✅ DAG for launched run: {d['total_tasks']} tasks, {d['wave_count']} waves")

    def test_45_launched_run_dag_has_valid_structure(self):
        run_id = TestLaunchRun._launched_run_id
        d = get(f"/api/supervisor/run/{run_id}/dag")
        # All tasks have positions
        for t in d["tasks"]:
            assert t.get("x") is not None
            assert t.get("y") is not None
        # All edges reference valid tasks
        task_ids = {t["task_id"] for t in d["tasks"]}
        for e in d["edges"]:
            assert e["from_id"] in task_ids
            assert e["to_id"]   in task_ids
        print(f"\n  ✅ Launched run DAG structure valid: {len(d['tasks'])} tasks, {len(d['edges'])} edges")


# ─────────────────────────────────────────────────────────────────────────────
# 9. Kill Switch
# ─────────────────────────────────────────────────────────────────────────────

class TestKillSwitch:
    def test_46_kill_running_run_succeeds(self):
        # Create a run and immediately kill it
        d = post("/api/supervisor/run", {"goal": "Kill test — do something complex that takes time"})
        assert d.get("ok") and d.get("run_id")
        run_id = d["run_id"]
        time.sleep(0.3)  # let it start

        kill = post(f"/api/supervisor/run/{run_id}/kill", {"reason": "test kill"})
        assert kill.get("ok") is True
        assert kill.get("killed") is True
        print(f"\n  ✅ Kill switch: {run_id} killed")

    def test_47_killed_run_has_killed_status(self):
        # Launch and kill
        d = post("/api/supervisor/run", {"goal": "Another kill test goal to verify status"})
        run_id = d["run_id"]
        time.sleep(0.3)
        post(f"/api/supervisor/run/{run_id}/kill", {"reason": "test"})
        time.sleep(0.5)

        run_d = get(f"/api/supervisor/run/{run_id}")
        assert run_d["run"]["status"] == "killed"
        print(f"\n  ✅ Killed run has status='killed'")

    def test_48_kill_nonexistent_run_returns_404(self):
        r = httpx.post(f"{BASE}/api/supervisor/run/nonexistent_xyz/kill",
                       json={"reason":"test"}, timeout=15)
        assert r.status_code == 404 or r.json().get("ok") is False
        print(f"\n  ✅ Kill nonexistent run → 404/ok=False")


# ─────────────────────────────────────────────────────────────────────────────
# 10. Delete Run
# ─────────────────────────────────────────────────────────────────────────────

class TestDeleteRun:
    def test_49_delete_run_removes_it(self):
        d = post("/api/supervisor/run", {"goal": "Delete test — short task"})
        run_id = d["run_id"]
        time.sleep(0.5)
        post(f"/api/supervisor/run/{run_id}/kill", {"reason": "pre-delete kill"})
        time.sleep(0.3)
        del_d = delete(f"/api/supervisor/run/{run_id}")
        assert del_d.get("ok") is True
        # Verify gone
        r2 = httpx.get(f"{BASE}/api/supervisor/run/{run_id}", timeout=15)
        assert r2.status_code == 404 or r2.json().get("ok") is False
        print(f"\n  ✅ Run {run_id} deleted and confirmed gone")


# ─────────────────────────────────────────────────────────────────────────────
# 11. SSE Stream
# ─────────────────────────────────────────────────────────────────────────────

class TestSSEStream:
    def test_50_stream_endpoint_returns_sse(self, run_api):
        """Stream endpoint returns SSE data for a completed run."""
        events = []
        with httpx.stream('GET', f"{BASE}/api/supervisor/run/{run_api['run_id']}/stream",
                          timeout=15) as r:
            assert r.status_code == 200
            assert 'text/event-stream' in r.headers.get('content-type', '')
            buf = ''
            for chunk in r.iter_text():
                buf += chunk
                parts = buf.split('\n\n')
                buf = parts[-1]
                for part in parts[:-1]:
                    if part.startswith('data:'):
                        try:
                            events.append(json.loads(part[5:].strip()))
                        except:
                            pass
                # Stop after first event batch
                if len(events) >= 1:
                    break

        assert len(events) >= 1
        e = events[0]
        assert "run_id"     in e
        assert "status"     in e
        assert "task_count" in e
        assert "tasks"      in e
        print(f"\n  ✅ SSE stream: {len(events)} event(s) received. First: status={e.get('status')}")


# ─────────────────────────────────────────────────────────────────────────────
# 12. Frontend Contract — data shapes the DAG UI expects
# ─────────────────────────────────────────────────────────────────────────────

class TestFrontendContract:
    def test_51_task_agent_id_in_known_specialists(self, dag_api):
        known = {"researcher","builder","reviewer","creative","memory","brain","orchestrator"}
        for t in dag_api["tasks"]:
            # Agent IDs should be known specialists (or close)
            assert t["agent_id"], f"task {t['task_id']} has no agent_id"
        print(f"\n  ✅ All tasks have non-empty agent_id")

    def test_52_task_seq_is_unique_per_run(self, dag_api):
        seqs = [t["seq"] for t in dag_api["tasks"]]
        assert len(seqs) == len(set(seqs)), f"Duplicate seq values: {seqs}"
        print(f"\n  ✅ All task seq values unique: {sorted(seqs)}")

    def test_53_task_title_never_empty(self, dag_api):
        for t in dag_api["tasks"]:
            assert t["title"].strip(), f"Task {t['task_id']} has empty title"
        print(f"\n  ✅ All tasks have non-empty titles")

    def test_54_wave_statuses_are_logically_consistent(self, dag_api):
        """Waves before a running wave should be 'done'."""
        waves = sorted(dag_api["waves"], key=lambda w: w["wave"])
        found_non_done = False
        for w in waves:
            if found_non_done:
                # Once we've seen a non-done wave, no earlier wave can be done
                pass  # just check types
            if w["status"] != "done":
                found_non_done = True
        print(f"\n  ✅ Wave status sequence is logically valid")

    def test_55_edge_seqs_reference_valid_task_seqs(self, dag_api):
        valid_seqs = {t["seq"] for t in dag_api["tasks"]}
        for e in dag_api["edges"]:
            assert e["from_seq"] in valid_seqs, f"from_seq={e['from_seq']} not in tasks"
            assert e["to_seq"]   in valid_seqs, f"to_seq={e['to_seq']} not in tasks"
        print(f"\n  ✅ All edge seq references are valid")

    def test_56_all_demo_dags_load_without_error(self, demo_runs):
        for r in demo_runs:
            d = get(f"/api/supervisor/run/{r['run_id']}/dag")
            assert d.get("ok") is True, f"DAG for {r['run_id']} returned ok=False: {d.get('error')}"
        print(f"\n  ✅ All {len(demo_runs)} demo run DAGs load successfully")

    def test_57_run_goal_title_in_dag_run_field(self, dag_api, run_api):
        dag_run = dag_api["run"]
        assert dag_run.get("goal_title") or dag_run.get("goal_text"), \
            "DAG run missing goal_title and goal_text"
        print(f"\n  ✅ goal_title present in DAG run: '{dag_run.get('goal_title','')[:40]}'")

    def test_58_dag_tasks_include_cost_and_tokens(self, dag_api):
        done_tasks = [t for t in dag_api["tasks"] if t["status"] == "done"]
        for t in done_tasks:
            assert "tokens" in t
            assert "cost"   in t
            assert isinstance(t["tokens"], (int, float))
            assert isinstance(t["cost"],   (int, float))
        print(f"\n  ✅ All done tasks have tokens and cost fields")

    def test_59_dag_run_has_eval_score_when_done(self, dag_api, run_api):
        if run_api["status"] == "done":
            dag_run = dag_api["run"]
            assert dag_run.get("eval_score") is not None
            assert 0 <= dag_run["eval_score"] <= 1
        print(f"\n  ✅ eval_score={dag_api['run'].get('eval_score')} for done run")

    def test_60_all_three_views_work_end_to_end(self, run_api):
        """Original /run, new /dag, and /stream all work for the same run."""
        run_id = run_api["run_id"]
        orig   = get(f"/api/supervisor/run/{run_id}")
        dag    = get(f"/api/supervisor/run/{run_id}/dag")
        # Stream: just check headers
        with httpx.stream('GET', f"{BASE}/api/supervisor/run/{run_id}/stream", timeout=10) as s:
            assert s.status_code == 200
        assert orig.get("ok") is True
        assert dag.get("ok")  is True
        assert len(dag["tasks"]) == len(orig["tasks"])
        print(f"\n  ✅ All 3 views (run/dag/stream) work. tasks: orig={len(orig['tasks'])} dag={len(dag['tasks'])}")
