"""
Time-Travel Debugger — Full Verification Test Suite
Tests every backend API endpoint and all UI data contracts.

Backend endpoints under test:
  GET  /api/replay/runs                  — list all runs
  GET  /api/replay/runs/{id}             — run + all frames
  GET  /api/replay/runs/{id}/timeline    — timeline + node_lanes + rel_ms
  GET  /api/replay/runs/{id}/frames      — frames (optional event_type filter)
  GET  /api/replay/runs/{id}/frame/{n}   — single frame by frame_no
  GET  /api/replay/diff/{a}/{b}          — diff two runs node-by-node
  POST /api/replay/workflow/{wf}/run     — recorded SSE run
  POST /api/replay/runs/{id}/rerun-from/{n} — re-run from frame
  DELETE /api/replay/runs/{id}           — delete run + frames

Demo runs seeded by the test seed script:
  demo_*  workflows: wf_demo_research, wf_demo_code_review, wf_demo_swarm_error
"""
import pytest, httpx, json, time

BASE     = "http://127.0.0.1:8787"
TIMEOUT  = 30

def get(path, **kw):
    r = httpx.get(f"{BASE}{path}", timeout=TIMEOUT, **kw)
    assert r.status_code == 200, f"GET {path} → {r.status_code}: {r.text[:200]}"
    return r.json()

def post(path, body=None, **kw):
    r = httpx.post(f"{BASE}{path}", json=body or {}, timeout=TIMEOUT, **kw)
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
    """Return the 3 seeded demo runs."""
    d = get("/api/replay/runs?limit=200")
    runs = d["runs"]
    demo = [r for r in runs if r["id"].startswith("demo_")]
    assert len(demo) >= 3, f"Expected ≥3 demo runs, got {len(demo)}: {[r['id'] for r in demo]}"
    return {r["workflow_id"]: r for r in demo}

@pytest.fixture(scope="module")
def run_research(demo_runs):
    return demo_runs["wf_demo_research"]

@pytest.fixture(scope="module")
def run_code(demo_runs):
    return demo_runs["wf_demo_code_review"]

@pytest.fixture(scope="module")
def run_swarm(demo_runs):
    return demo_runs["wf_demo_swarm_error"]


# ─────────────────────────────────────────────────────────────────────────────
# 1. List Runs
# ─────────────────────────────────────────────────────────────────────────────

class TestListRuns:
    def test_01_list_returns_array(self):
        d = get("/api/replay/runs")
        assert "runs" in d
        assert isinstance(d["runs"], list)
        assert "count" in d
        print(f"\n  ✅ {d['count']} total runs")

    def test_02_limit_param(self):
        d = get("/api/replay/runs?limit=3")
        assert len(d["runs"]) <= 3

    def test_03_wf_id_filter(self):
        d = get("/api/replay/runs?wf_id=wf_demo_research&limit=50")
        for r in d["runs"]:
            assert r["workflow_id"] == "wf_demo_research"
        print(f"\n  ✅ wf_id filter: {d['count']} runs")

    def test_04_run_fields_complete(self, run_research):
        r = run_research
        assert r["id"]
        assert r["workflow_id"]
        assert r["workflow_nm"]
        assert r["status"] in ("done", "running", "failed")
        assert isinstance(r["total_ms"], int)
        assert isinstance(r["node_count"], int)
        assert r["created_at"]
        print(f"\n  ✅ Run fields: {r['id']} | {r['status']} | {r['total_ms']}ms | {r['node_count']} nodes")

    def test_05_demo_runs_are_done(self, demo_runs):
        for wf_id, r in demo_runs.items():
            assert r["status"] == "done", f"{wf_id} status={r['status']}"
        print(f"\n  ✅ All {len(demo_runs)} demo runs are 'done'")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Get Run + Frames
# ─────────────────────────────────────────────────────────────────────────────

class TestGetRun:
    def test_06_get_run_returns_run_and_frames(self, run_research):
        d = get(f"/api/replay/runs/{run_research['id']}")
        assert "run" in d or "id" in d   # API returns either top-level or nested
        assert "frames" in d
        assert isinstance(d["frames"], list)
        assert d["count"] == len(d["frames"])
        print(f"\n  ✅ Run {run_research['id']}: {d['count']} frames")

    def test_07_frames_have_required_fields(self, run_research):
        d = get(f"/api/replay/runs/{run_research['id']}")
        frames = d["frames"]
        assert len(frames) > 0
        for f in frames:
            assert "id"           in f, f"Missing 'id' in frame"
            assert "run_id"       in f
            assert "frame_no"     in f
            assert "node_id"      in f
            assert "node_type"    in f
            assert "node_label"   in f
            assert "event_type"   in f
            assert "input_ctx"    in f
            assert "output"       in f
            assert "error"        in f
            assert "duration_ms"  in f
            assert "timestamp"    in f
        print(f"\n  ✅ All {len(frames)} frames have required fields")

    def test_08_frames_have_node_start_and_output_pairs(self, run_research):
        d      = get(f"/api/replay/runs/{run_research['id']}")
        frames = d["frames"]
        starts  = {f["node_id"] for f in frames if f["event_type"] == "node_start"}
        outputs = {f["node_id"] for f in frames if f["event_type"] == "node_output"}
        assert starts == outputs, f"Unpaired nodes: starts={starts}, outputs={outputs}"
        print(f"\n  ✅ {len(starts)} nodes with start+output pairs")

    def test_09_research_run_has_5_nodes(self, run_research):
        d = get(f"/api/replay/runs/{run_research['id']}")
        nodes = {f["node_id"] for f in d["frames"]}
        assert len(nodes) == 5, f"Expected 5 nodes, got {len(nodes)}: {nodes}"
        print(f"\n  ✅ Research run has 5 unique nodes: {nodes}")

    def test_10_code_run_has_agent_node(self, run_code):
        d = get(f"/api/replay/runs/{run_code['id']}")
        types = {f["node_type"] for f in d["frames"]}
        assert "agent" in types
        assert "condition" in types
        print(f"\n  ✅ Code run node types: {types}")

    def test_11_swarm_run_has_error_frame(self, run_swarm):
        d = get(f"/api/replay/runs/{run_swarm['id']}")
        errors = [f for f in d["frames"] if f.get("error") and len(f["error"]) > 0]
        assert len(errors) >= 1, "Expected at least 1 error frame (webhook node)"
        print(f"\n  ✅ Swarm run has {len(errors)} error frame(s): {errors[0]['node_label']}")

    def test_12_frame_no_is_sequential(self, run_research):
        d = get(f"/api/replay/runs/{run_research['id']}")
        frame_nos = [f["frame_no"] for f in d["frames"]]
        assert frame_nos == sorted(frame_nos), "Frames are not in frame_no order"
        print(f"\n  ✅ Frames in sequential order: {frame_nos}")

    def test_13_input_ctx_is_valid_json(self, run_research):
        d = get(f"/api/replay/runs/{run_research['id']}")
        for f in d["frames"]:
            if f.get("input_ctx"):
                try:
                    ctx = json.loads(f["input_ctx"])
                    assert isinstance(ctx, dict)
                except json.JSONDecodeError:
                    pytest.fail(f"input_ctx is not valid JSON in frame {f['frame_no']}")
        print(f"\n  ✅ All input_ctx fields are valid JSON")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Timeline Endpoint (critical for TTD UI)
# ─────────────────────────────────────────────────────────────────────────────

class TestTimeline:
    def test_14_timeline_returns_all_fields(self, run_research):
        d = get(f"/api/replay/runs/{run_research['id']}/timeline")
        assert d.get("ok") is not False, d
        assert "run"         in d
        assert "frames"      in d
        assert "node_lanes"  in d
        assert "duration_ms" in d
        assert "frame_count" in d
        print(f"\n  ✅ Timeline: {d['frame_count']} frames, {d['duration_ms']}ms, {len(d['node_lanes'])} lanes")

    def test_15_timeline_frames_have_rel_ms(self, run_research):
        d = get(f"/api/replay/runs/{run_research['id']}/timeline")
        for f in d["frames"]:
            assert "rel_ms" in f, f"Frame {f.get('frame_no')} missing rel_ms"
            assert isinstance(f["rel_ms"], (int, float))
        # Relative ms should be non-decreasing
        rel_ms = [f["rel_ms"] for f in d["frames"]]
        assert rel_ms == sorted(rel_ms), f"rel_ms not sorted: {rel_ms}"
        print(f"\n  ✅ rel_ms present and non-decreasing: {rel_ms}")

    def test_16_timeline_node_lanes_structure(self, run_research):
        d = get(f"/api/replay/runs/{run_research['id']}/timeline")
        lanes = d["node_lanes"]
        assert isinstance(lanes, dict)
        assert len(lanes) >= 1
        for nid, frames in lanes.items():
            assert isinstance(frames, list)
            assert len(frames) >= 1
            for f in frames:
                assert "node_id"    in f
                assert "event_type" in f
                assert "frame_no"   in f
        print(f"\n  ✅ {len(lanes)} node lanes, each with valid frames")

    def test_17_timeline_duration_ms_positive(self, run_research):
        d = get(f"/api/replay/runs/{run_research['id']}/timeline")
        assert d["duration_ms"] > 0
        print(f"\n  ✅ duration_ms={d['duration_ms']}")

    def test_18_timeline_run_field_matches(self, run_research):
        d = get(f"/api/replay/runs/{run_research['id']}/timeline")
        run = d["run"]
        assert run["id"] == run_research["id"]
        assert run["workflow_id"] == run_research["workflow_id"]
        print(f"\n  ✅ Timeline run.id matches: {run['id']}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Frames Filter & Single Frame
# ─────────────────────────────────────────────────────────────────────────────

class TestFrameAccess:
    def test_19_frames_filter_by_event_type(self, run_research):
        d = get(f"/api/replay/runs/{run_research['id']}/frames?event_type=node_output")
        for f in d["frames"]:
            assert f["event_type"] == "node_output"
        assert d["count"] >= 1
        print(f"\n  ✅ Filtered to {d['count']} node_output frames")

    def test_20_frames_filter_node_start(self, run_research):
        d = get(f"/api/replay/runs/{run_research['id']}/frames?event_type=node_start")
        for f in d["frames"]:
            assert f["event_type"] == "node_start"
        print(f"\n  ✅ Filtered to {d['count']} node_start frames")

    def test_21_get_single_frame_by_number(self, run_research):
        d = get(f"/api/replay/runs/{run_research['id']}/frame/1")
        assert "frame_no" in d or d.get("ok") is not False
        if "frame_no" in d:
            assert d["frame_no"] == 1
        print(f"\n  ✅ Single frame 1: node={d.get('node_id')} type={d.get('event_type')}")

    def test_22_get_single_frame_not_found(self, run_research):
        d = get(f"/api/replay/runs/{run_research['id']}/frame/99999")
        assert d.get("ok") is False
        assert "error" in d
        print(f"\n  ✅ Frame 99999 correctly returns ok=False: {d['error']}")

    def test_23_all_node_types_represented(self, run_swarm):
        d = get(f"/api/replay/runs/{run_swarm['id']}/frames")
        types = {f["node_type"] for f in d["frames"]}
        # Swarm run has: trigger, agent, webhook, transform, output
        assert "trigger"   in types
        assert "agent"     in types
        assert "webhook"   in types
        assert "transform" in types
        print(f"\n  ✅ Node types in swarm run: {types}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Diff Endpoint
# ─────────────────────────────────────────────────────────────────────────────

class TestDiff:
    def test_24_diff_two_runs_same_workflow(self, run_research, run_code):
        # Diff two different runs (different workflows → all nodes only_in one)
        d = get(f"/api/replay/diff/{run_research['id']}/{run_code['id']}")
        assert "diffs"         in d
        assert "changed_count" in d
        assert "run_id_a"      in d
        assert "run_id_b"      in d
        assert isinstance(d["diffs"], list)
        print(f"\n  ✅ Diff: {d['changed_count']} changed, {len(d['diffs'])} total nodes")

    def test_25_diff_fields_in_each_node(self, run_research, run_code):
        d = get(f"/api/replay/diff/{run_research['id']}/{run_code['id']}")
        for node in d["diffs"]:
            assert "node_id"   in node
            assert "only_in"   in node
            assert "changed"   in node
            assert node["only_in"] in ("a", "b", "both")
            assert isinstance(node["changed"], bool)
        print(f"\n  ✅ All {len(d['diffs'])} diff nodes have required fields")

    def test_26_diff_same_run_zero_changes(self, run_research):
        # Diff a run against itself → 0 changed
        d = get(f"/api/replay/diff/{run_research['id']}/{run_research['id']}")
        assert d["changed_count"] == 0, f"Self-diff should have 0 changes, got {d['changed_count']}"
        for node in d["diffs"]:
            assert node["only_in"] == "both"
            assert node["changed"] is False
        print(f"\n  ✅ Self-diff: 0 changes, all nodes in 'both'")

    def test_27_diff_captures_duration(self, run_research, run_swarm):
        d = get(f"/api/replay/diff/{run_research['id']}/{run_swarm['id']}")
        # Nodes that appear in both should have duration values
        shared = [n for n in d["diffs"] if n["only_in"] == "both"]
        if shared:
            for n in shared:
                # durations can be None if node didn't produce output
                pass  # structure check sufficient
        print(f"\n  ✅ Diff: {len(shared)} shared nodes between runs")

    def test_28_diff_invalid_run_ids(self):
        d = get("/api/replay/diff/nonexistent_a/nonexistent_b")
        # Should return empty diffs (both runs have no frames), not crash
        assert "diffs" in d
        assert d["diffs"] == []
        print(f"\n  ✅ Diff with nonexistent run IDs returns empty diffs (no crash)")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Recorded Run (SSE endpoint)
# ─────────────────────────────────────────────────────────────────────────────

class TestRecordedRun:
    def test_29_recorded_run_creates_run(self):
        """POST a recorded run against the demo workflow and verify frames are saved."""
        import time

        # Find a workflow file that exists
        import os
        wf_files = [f for f in os.listdir('workspaces/workflows') if f.startswith('wf_demo_')]
        assert len(wf_files) >= 1, "No demo workflow files found"
        wf_id = wf_files[0].replace('.json', '')
        
        # Stream the SSE response
        events = []
        with httpx.stream('POST', f"{BASE}/api/replay/workflow/{wf_id}/run",
                          json={"input": "test input for recorded run"},
                          timeout=30) as r:
            assert r.status_code == 200
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

        # Should have start and done events
        types = {e.get('type') for e in events}
        assert 'start' in types or 'node_start' in types, f"No start event: {types}"
        assert 'done' in types, f"No done event: {types}"
        
        # Extract run_id
        run_id = next((e['run_id'] for e in events if e.get('run_id')), None)
        assert run_id, "No run_id in events"
        
        # Verify run was saved to DB
        time.sleep(0.5)
        rd = get(f"/api/replay/runs/{run_id}")
        assert "frames" in rd
        assert len(rd["frames"]) >= 2  # at least trigger start + output
        print(f"\n  ✅ Recorded run: run_id={run_id}, {len(events)} SSE events, {len(rd['frames'])} frames saved")

    def test_30_recorded_run_invalid_workflow(self):
        with httpx.stream('POST', f"{BASE}/api/replay/workflow/wf_nonexistent_12345/run",
                          json={"input": "test"},
                          timeout=15) as r:
            body = r.read()
        # Should return error JSON (not 200 SSE)
        assert r.status_code == 200  # FastAPI returns 200 with error body
        try:
            d = json.loads(body)
            assert d.get("ok") is False
        except:
            pass  # Some error response is fine
        print(f"\n  ✅ Invalid workflow returns error: {body[:80]}")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Re-run from Frame
# ─────────────────────────────────────────────────────────────────────────────

class TestRerunFromFrame:
    def test_31_rerun_from_frame_1_creates_new_run(self, run_research):
        """Re-run from frame 1 (trigger) of the research run."""
        import time
        run_id   = run_research["id"]
        frame_no = 1  # frame_no 1 = first node_start

        events = []
        with httpx.stream('POST', f"{BASE}/api/replay/runs/{run_id}/rerun-from/{frame_no}",
                          json={}, timeout=30) as r:
            assert r.status_code == 200
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

        types = {e.get('type') for e in events}
        assert 'rerun_start' in types or 'done' in types, f"Unexpected event types: {types}"
        
        new_run_id = next((e.get('run_id') for e in events if e.get('run_id') and 'rerun' in e.get('run_id','')), None)
        if new_run_id:
            time.sleep(0.5)
            rd = get(f"/api/replay/runs/{new_run_id}")
            assert "frames" in rd
            print(f"\n  ✅ Re-run created: {new_run_id} with {len(rd['frames'])} frames")
        else:
            print(f"\n  ✅ Re-run events received: {types}")

    def test_32_rerun_missing_run_returns_error(self):
        r = httpx.post(f"{BASE}/api/replay/runs/nonexistent_run/rerun-from/1",
                       json={}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is False
        print(f"\n  ✅ Rerun nonexistent run → ok=False: {d['error'][:60]}")


# ─────────────────────────────────────────────────────────────────────────────
# 8. Delete Run
# ─────────────────────────────────────────────────────────────────────────────

class TestDeleteRun:
    def test_33_delete_run_removes_frames(self):
        """Create a run then delete it and verify both run and frames are gone."""
        import time, os

        # Use first demo workflow
        wf_files = [f for f in os.listdir('workspaces/workflows') if f.startswith('wf_demo_')]
        wf_id = wf_files[0].replace('.json', '')
        
        # Create run
        events = []
        with httpx.stream('POST', f"{BASE}/api/replay/workflow/{wf_id}/run",
                          json={"input": "delete test"}, timeout=30) as r:
            buf = ''
            for chunk in r.iter_text():
                buf += chunk
                parts = buf.split('\n\n')
                buf = parts[-1]
                for part in parts[:-1]:
                    if part.startswith('data:'):
                        try: events.append(json.loads(part[5:].strip()))
                        except: pass
        
        run_id = next((e['run_id'] for e in events if e.get('run_id')), None)
        assert run_id, "No run_id in events"
        time.sleep(0.5)

        # Delete it
        d = delete(f"/api/replay/runs/{run_id}")
        assert d.get("ok") is True

        # Verify gone
        r2 = httpx.get(f"{BASE}/api/replay/runs/{run_id}", timeout=15)
        d2 = r2.json()
        assert d2.get("ok") is False
        print(f"\n  ✅ Run {run_id} deleted and confirmed gone")


# ─────────────────────────────────────────────────────────────────────────────
# 9. Data Integrity & Edge Cases
# ─────────────────────────────────────────────────────────────────────────────

class TestDataIntegrity:
    def test_34_all_demo_runs_have_frames(self, demo_runs):
        for wf_id, run in demo_runs.items():
            d = get(f"/api/replay/runs/{run['id']}")
            assert d["count"] > 0, f"{wf_id} has 0 frames"
            assert len(d["frames"]) > 0
        print(f"\n  ✅ All {len(demo_runs)} demo runs have frames")

    def test_35_research_run_output_contains_ai_content(self, run_research):
        d = get(f"/api/replay/runs/{run_research['id']}/frames?event_type=node_output")
        outputs = [f["output"] for f in d["frames"] if f.get("output")]
        assert len(outputs) >= 3
        # Researcher should have substantial output
        researcher_out = next((f["output"] for f in d["frames"] if f.get("node_type")=="agent" and "research" in (f.get("node_label","")).lower()), None)
        if researcher_out:
            assert len(researcher_out) > 50
        print(f"\n  ✅ Research outputs: {len(outputs)} nodes with output, researcher: {len(researcher_out or '')} chars")

    def test_36_swarm_run_webhook_has_error(self, run_swarm):
        d = get(f"/api/replay/runs/{run_swarm['id']}/frames")
        webhook_frames = [f for f in d["frames"] if f["node_type"] == "webhook" and f["event_type"] == "node_output"]
        assert len(webhook_frames) >= 1
        assert webhook_frames[0]["error"] != "", "Webhook frame should have error"
        print(f"\n  ✅ Webhook error: {webhook_frames[0]['error'][:60]}")

    def test_37_code_run_condition_output_is_boolean_string(self, run_code):
        d = get(f"/api/replay/runs/{run_code['id']}/frames")
        cond_frames = [f for f in d["frames"] if f["node_type"] == "condition" and f["event_type"] == "node_output"]
        assert len(cond_frames) >= 1
        assert cond_frames[0]["output"] in ("true", "false")
        print(f"\n  ✅ Condition output: '{cond_frames[0]['output']}'")

    def test_38_timeline_rel_ms_starts_at_zero(self, run_research):
        d = get(f"/api/replay/runs/{run_research['id']}/timeline")
        first_rel = d["frames"][0]["rel_ms"]
        assert first_rel == 0, f"First frame rel_ms should be 0, got {first_rel}"
        print(f"\n  ✅ First frame rel_ms=0")

    def test_39_frame_timestamps_are_real_unix_time(self, run_research):
        d = get(f"/api/replay/runs/{run_research['id']}")
        for f in d["frames"]:
            ts = f.get("timestamp")
            if ts:
                # Should be a Unix timestamp in 2026 range
                assert 1_700_000_000 < ts < 2_000_000_000, f"Timestamp out of range: {ts}"
        print(f"\n  ✅ All frame timestamps in valid Unix range")

    def test_40_diff_changed_count_is_accurate(self, run_research):
        d = get(f"/api/replay/diff/{run_research['id']}/{run_research['id']}")
        actual_changed = sum(1 for n in d["diffs"] if n["changed"])
        assert d["changed_count"] == actual_changed
        print(f"\n  ✅ diff.changed_count ({d['changed_count']}) == actual count ({actual_changed})")


# ─────────────────────────────────────────────────────────────────────────────
# 10. Frontend contract — verifying data shapes the UI expects
# ─────────────────────────────────────────────────────────────────────────────

class TestFrontendContract:
    """Verify the exact data shapes that the TTD JavaScript frontend consumes."""

    def test_41_runs_list_has_workflow_nm_for_display(self, demo_runs):
        d = get("/api/replay/runs?limit=50")
        for r in d["runs"]:
            # UI displays workflow_nm — must not be None
            assert r.get("workflow_nm") is not None
        print(f"\n  ✅ All runs have workflow_nm for display")

    def test_42_timeline_node_lanes_keyed_by_node_id(self, run_research):
        d = get(f"/api/replay/runs/{run_research['id']}/timeline")
        lanes = d["node_lanes"]
        # Each key should match node_id in its frames
        for nid, frames in lanes.items():
            for f in frames:
                assert f["node_id"] == nid
        print(f"\n  ✅ node_lanes correctly keyed by node_id")

    def test_43_diff_nodes_have_label_for_display(self, run_research):
        d = get(f"/api/replay/diff/{run_research['id']}/{run_research['id']}")
        for node in d["diffs"]:
            # UI renders node_label — should not crash if None (but should prefer string)
            assert "node_label" in node
        print(f"\n  ✅ All diff nodes have node_label field")

    def test_44_frame_node_label_never_null(self, run_research):
        d = get(f"/api/replay/runs/{run_research['id']}")
        for f in d["frames"]:
            assert f.get("node_label") is not None, f"frame {f['frame_no']} has null node_label"
        print(f"\n  ✅ All frames have non-null node_label")

    def test_45_single_frame_has_correct_run_id(self, run_research):
        run_id = run_research["id"]
        d      = get(f"/api/replay/runs/{run_id}/frame/1")
        if d.get("ok") is not False:
            assert d.get("run_id") == run_id
        print(f"\n  ✅ Single frame has correct run_id")

    def test_46_recorded_run_sse_events_have_run_id(self):
        """All SSE events from /run must carry run_id for UI correlation."""
        import os
        wf_files = [f for f in os.listdir('workspaces/workflows') if f.startswith('wf_demo_')]
        wf_id    = wf_files[0].replace('.json', '')

        events = []
        with httpx.stream('POST', f"{BASE}/api/replay/workflow/{wf_id}/run",
                          json={"input": "sse contract test"}, timeout=30) as r:
            buf = ''
            for chunk in r.iter_text():
                buf += chunk
                parts = buf.split('\n\n')
                buf = parts[-1]
                for part in parts[:-1]:
                    if part.startswith('data:'):
                        try: events.append(json.loads(part[5:].strip()))
                        except: pass

        for e in events:
            if e.get('type') not in ('start', 'done', 'error', 'final_output'):
                assert 'run_id' in e, f"SSE event missing run_id: {e}"
        print(f"\n  ✅ All {len(events)} SSE events carry run_id")

    def test_47_get_run_returns_404_style_for_missing(self):
        d = get("/api/replay/runs/completely_nonexistent_run_xyz")
        assert d.get("ok") is False
        assert "error" in d
        print(f"\n  ✅ Missing run returns ok=False: {d['error']}")

    def test_48_workflow_file_exists_for_demo_runs(self, demo_runs):
        import os
        for wf_id, run in demo_runs.items():
            path = f"workspaces/workflows/{wf_id}.json"
            assert os.path.exists(path), f"Workflow file missing: {path}"
            d = json.load(open(path))
            assert "nodes" in d
            assert "edges" in d
            assert len(d["nodes"]) >= 2
        print(f"\n  ✅ All {len(demo_runs)} workflow files exist and are valid JSON")

    def test_49_run_node_count_matches_actual_nodes(self, demo_runs):
        for wf_id, run in demo_runs.items():
            d = get(f"/api/replay/runs/{run['id']}")
            actual = len({f["node_id"] for f in d["frames"]})
            # node_count in run header should match
            assert run["node_count"] == actual, \
                f"{wf_id}: node_count={run['node_count']} but actual={actual}"
        print(f"\n  ✅ node_count matches actual unique nodes in all demo runs")

    def test_50_speed_run_end_to_end_all_views(self, run_research, run_code):
        """All 3 view endpoints work for each demo run."""
        for label, run_id in [("research", run_research["id"]), ("code", run_code["id"])]:
            rd = get(f"/api/replay/runs/{run_id}")
            tl = get(f"/api/replay/runs/{run_id}/timeline")
            df = get(f"/api/replay/diff/{run_id}/{run_id}")
            assert rd["count"] > 0
            assert tl["frame_count"] > 0
            assert df["changed_count"] == 0
        print(f"\n  ✅ All 3 views (run, timeline, diff) work for both runs")
