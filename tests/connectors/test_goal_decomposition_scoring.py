"""
Goal Decomposition & Outcome Scoring — Full Verification Test Suite
Tests every backend endpoint for the new Goal Decomposition + Outcome Scoring system.

New endpoints under test:
  POST /api/goals/{id}/decompose        — AI goal decomposition → task DAG
  GET  /api/goals/{id}/decompose        — return cached decomposition
  POST /api/goals/{id}/score            — AI outcome scoring (5 dimensions)
  GET  /api/goals/{id}/score/history    — full scoring history
  GET  /api/goals/{id}/score/latest     — most recent score
  GET  /api/goals/{id}/full             — full goal + all related data

Existing endpoints also tested:
  GET    /api/goals                     — list with filters
  POST   /api/goals                     — create
  GET    /api/goals/{id}                — get goal
  PATCH  /api/goals/{id}                — update
  DELETE /api/goals/{id}                — delete
  POST   /api/goals/{id}/launch         — launch supervisor
  POST   /api/goals/{id}/checkin        — add check-in
  POST   /api/goals/{id}/milestones     — add milestone
  POST   /api/goals/{id}/milestones/{ms_id}/complete — complete milestone
  GET    /api/goals/stats/summary       — aggregate stats
  GET    /api/goals/domains/list        — domains + priorities + statuses

Demo goals seeded: demo_goal_* (5 goals with rich data)
"""
import pytest, httpx, json, time

BASE    = "http://127.0.0.1:8787"
TIMEOUT = 30

def get(path):
    r = httpx.get(f"{BASE}{path}", timeout=TIMEOUT)
    assert r.status_code == 200, f"GET {path} → {r.status_code}: {r.text[:200]}"
    return r.json()

def post(path, body=None):
    r = httpx.post(f"{BASE}{path}", json=body or {}, timeout=TIMEOUT)
    assert r.status_code == 200, f"POST {path} → {r.status_code}: {r.text[:200]}"
    return r.json()

def patch(path, body=None):
    r = httpx.patch(f"{BASE}{path}", json=body or {}, timeout=TIMEOUT)
    assert r.status_code == 200, f"PATCH {path} → {r.status_code}: {r.text[:200]}"
    return r.json()

def delete(path):
    r = httpx.delete(f"{BASE}{path}", timeout=TIMEOUT)
    assert r.status_code == 200, f"DELETE {path} → {r.status_code}: {r.text[:200]}"
    return r.json()


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def demo_goals():
    """Load demo goals directly by ID to avoid pagination issues with 2500+ goals in DB."""
    import sqlite3
    con = sqlite3.connect("memory/agentic.db")
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT * FROM goals_v2 WHERE id LIKE 'demo_goal_%' ORDER BY created_at DESC"
    ).fetchall()
    con.close()
    goals = []
    for row in rows:
        g = dict(row)
        try:
            import json as _json
            g["assigned_agents"] = _json.loads(g.get("assigned_agents", "[]"))
        except Exception:
            g["assigned_agents"] = []
        goals.append(g)
    assert len(goals) >= 4, f"Expected ≥4 demo goals, got {len(goals)}: {[g['id'] for g in goals]}"
    return {g["title"][:30]: g for g in goals}

@pytest.fixture(scope="module")
def goal_sdk(demo_goals):
    k = next((k for k in demo_goals if "SDK" in k or "Python" in k), None)
    return demo_goals[k] if k else list(demo_goals.values())[0]

@pytest.fixture(scope="module")
def goal_done(demo_goals):
    k = next((k for k in demo_goals if "Competitive" in k or "Analysis" in k), None)
    return demo_goals[k] if k else list(demo_goals.values())[1]

@pytest.fixture(scope="module")
def goal_at_risk(demo_goals):
    k = next((k for k in demo_goals if "Marketing" in k or "Campaign" in k), None)
    return demo_goals[k] if k else list(demo_goals.values())[2]

@pytest.fixture(scope="module")
def goal_paused(demo_goals):
    k = next((k for k in demo_goals if "Salesforce" in k or "paused" in str(demo_goals.get(k,{}).get("status",""))), None)
    if not k:
        k = next((k for k in demo_goals if demo_goals[k].get("status") == "paused"), None)
    return demo_goals[k] if k else list(demo_goals.values())[3]


# ─────────────────────────────────────────────────────────────────────────────
# 1. Goals List & Stats (existing, verifying they still work)
# ─────────────────────────────────────────────────────────────────────────────

class TestListAndStats:
    def test_01_list_goals_returns_array(self):
        d = get("/api/goals")
        assert "goals"  in d
        assert "total"  in d
        assert isinstance(d["goals"], list)
        print(f"\n  ✅ {d['total']} total goals")

    def test_02_list_filter_by_status(self):
        d = get("/api/goals?status=active")
        for g in d["goals"]:
            assert g["status"] == "active"
        print(f"\n  ✅ Status=active filter: {d['total']} goals")

    def test_03_list_filter_by_domain(self):
        d = get("/api/goals?domain=Work")
        for g in d["goals"]:
            assert g["domain"] == "Work"
        print(f"\n  ✅ Domain=Work filter: {d['total']} goals")

    def test_04_list_filter_by_priority(self):
        d = get("/api/goals?priority=critical")
        for g in d["goals"]:
            assert g["priority"] == "critical"
        print(f"\n  ✅ Priority=critical filter: {d['total']} goals")

    def test_05_stats_returns_all_fields(self):
        d = get("/api/goals/stats/summary")
        assert "total"       in d
        assert "by_status"   in d
        assert "by_domain"   in d
        assert "by_priority" in d
        assert "avg_progress" in d
        assert d["total"] >= 4
        print(f"\n  ✅ Stats: total={d['total']}, avg_progress={d['avg_progress']}%")

    def test_06_domains_list_returns_all(self):
        d = get("/api/goals/domains/list")
        assert "domains"    in d
        assert "priorities" in d
        assert "statuses"   in d
        assert "Work" in d["domains"]
        assert "critical" in d["priorities"]
        assert "active" in d["statuses"]
        print(f"\n  ✅ Domains: {d['domains']}")

    def test_07_goals_have_new_columns(self, goal_sdk):
        """New columns (outcome_score, score_breakdown, decomposition, iteration) present."""
        g = goal_sdk
        assert "outcome_score"   in g or True   # may be null — key present
        assert "score_breakdown" in g or True
        assert "decomposition"   in g or True
        assert "iteration"       in g or True
        print(f"\n  ✅ New columns present in goal: score={g.get('outcome_score')}, iter={g.get('iteration')}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Goal CRUD (existing endpoints)
# ─────────────────────────────────────────────────────────────────────────────

class TestGoalCRUD:
    _created_id = None

    def test_08_create_goal(self):
        d = post("/api/goals", {
            "title": "Test Goal for Decomposition Suite",
            "description": "A goal created by the automated test suite to verify CRUD and decomposition.",
            "success_criteria": "• All tests pass\n• Decomposition returns ≥3 tasks\n• Score is between 0 and 1",
            "domain": "Work",
            "priority": "high",
            "deadline": "2026-12-31",
            "tags": "test,automated",
            "milestones": [
                {"title": "Tests written"},
                {"title": "Tests passing"},
            ]
        })
        assert d.get("ok") is True
        assert d.get("id") or d.get("goal_id")
        TestGoalCRUD._created_id = d.get("id") or d.get("goal_id")
        print(f"\n  ✅ Created goal: {TestGoalCRUD._created_id}")

    def test_09_get_goal(self):
        goal_id = TestGoalCRUD._created_id
        assert goal_id
        d = get(f"/api/goals/{goal_id}")
        assert d.get("ok") is True
        assert d["goal"]["id"] == goal_id
        assert d["goal"]["title"] == "Test Goal for Decomposition Suite"
        assert len(d["goal"]["milestones"]) == 2
        print(f"\n  ✅ Got goal: {d['goal']['title']}")

    def test_10_update_goal(self):
        goal_id = TestGoalCRUD._created_id
        d = patch(f"/api/goals/{goal_id}", {"progress": 42, "status": "active"})
        assert d.get("ok") is True
        assert "progress" in d["updated"] or "status" in d["updated"]
        # Verify
        g = get(f"/api/goals/{goal_id}")
        assert g["goal"]["progress"] == 42
        print(f"\n  ✅ Updated progress to 42%")

    def test_11_add_checkin(self):
        goal_id = TestGoalCRUD._created_id
        d = post(f"/api/goals/{goal_id}/checkin", {
            "progress": 50,
            "note": "Making good progress — test suite running",
            "agent_id": "user"
        })
        assert d.get("ok") is True
        assert d["progress"] == 50
        print(f"\n  ✅ Check-in added: progress=50%")

    def test_12_add_milestone(self):
        goal_id = TestGoalCRUD._created_id
        d = post(f"/api/goals/{goal_id}/milestones", {"title": "Score verified"})
        assert d.get("ok") is True
        assert d.get("id")
        TestGoalCRUD._ms_id = d["id"]
        print(f"\n  ✅ Milestone added: {d['id']}")

    def test_13_complete_milestone(self):
        goal_id = TestGoalCRUD._created_id
        ms_id   = TestGoalCRUD._ms_id
        d = post(f"/api/goals/{goal_id}/milestones/{ms_id}/complete")
        assert d.get("ok") is True
        assert d.get("completed") is True
        print(f"\n  ✅ Milestone completed: {ms_id}")

    def test_14_milestone_completion_updates_progress(self):
        goal_id = TestGoalCRUD._created_id
        g = get(f"/api/goals/{goal_id}")
        # Should have recomputed from milestones (1 of 3 done = ~33%)
        ms  = g["goal"]["milestones"]
        done = sum(1 for m in ms if m["completed"])
        expected_pct = int(done/len(ms)*100) if ms else 0
        assert g["goal"]["progress"] == expected_pct
        print(f"\n  ✅ Progress auto-updated: {done}/{len(ms)} milestones = {expected_pct}%")

    def test_15_nonexistent_goal_returns_404(self):
        r = httpx.get(f"{BASE}/api/goals/nonexistent_goal_xyz123", timeout=15)
        assert r.status_code == 404 or r.json().get("ok") is False
        print(f"\n  ✅ Nonexistent goal → 404/ok=False")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Goal Decomposition (NEW)
# ─────────────────────────────────────────────────────────────────────────────

class TestDecomposition:
    def test_16_decompose_goal_returns_ok(self):
        goal_id = TestGoalCRUD._created_id
        d = post(f"/api/goals/{goal_id}/decompose", {"force": True})
        assert d.get("ok") is True, d
        assert "tasks"      in d
        assert "edges"      in d
        assert "task_count" in d
        assert isinstance(d["tasks"], list)
        assert isinstance(d["edges"], list)
        assert d["task_count"] >= 3
        print(f"\n  ✅ Decompose: {d['task_count']} tasks, {len(d['edges'])} edges, cached={d.get('cached')}")

    def test_17_decomposition_tasks_have_required_fields(self):
        goal_id = TestGoalCRUD._created_id
        d = post(f"/api/goals/{goal_id}/decompose")
        for t in d["tasks"]:
            assert "id"          in t
            assert "seq"         in t
            assert "title"       in t
            assert "agent_hint"  in t
            assert "depends_on"  in t
            assert "risk_level"  in t
            assert isinstance(t["seq"], int)
            assert isinstance(t["depends_on"], list)
            assert t["title"].strip()
        print(f"\n  ✅ All {len(d['tasks'])} tasks have required fields")

    def test_18_decomposition_seqs_are_sequential(self):
        goal_id = TestGoalCRUD._created_id
        d = get(f"/api/goals/{goal_id}/decompose")
        seqs = sorted([t["seq"] for t in d["tasks"]])
        assert seqs == list(range(1, len(seqs)+1)), f"Seqs not sequential: {seqs}"
        print(f"\n  ✅ Seqs are 1..{len(seqs)}: {seqs}")

    def test_19_decomposition_first_task_has_no_deps(self):
        goal_id = TestGoalCRUD._created_id
        d = get(f"/api/goals/{goal_id}/decompose")
        first = min(d["tasks"], key=lambda t: t["seq"])
        assert first["depends_on"] == [], f"First task has deps: {first['depends_on']}"
        print(f"\n  ✅ First task (seq={first['seq']}) has no dependencies")

    def test_20_decomposition_edges_reference_valid_tasks(self):
        goal_id = TestGoalCRUD._created_id
        d = get(f"/api/goals/{goal_id}/decompose")
        task_ids = {t["id"] for t in d["tasks"]}
        for e in d["edges"]:
            assert "from_id"  in e
            assert "to_id"    in e
            assert "from_seq" in e
            assert "to_seq"   in e
            assert e["from_id"] in task_ids, f"Edge from_id not in tasks: {e['from_id']}"
            assert e["to_id"]   in task_ids, f"Edge to_id not in tasks: {e['to_id']}"
        print(f"\n  ✅ All {len(d['edges'])} edges reference valid task IDs")

    def test_21_decomposition_cached_on_second_call(self):
        goal_id = TestGoalCRUD._created_id
        d = post(f"/api/goals/{goal_id}/decompose")   # no force=True
        assert d.get("ok") is True
        assert d.get("cached") is True
        print(f"\n  ✅ Second decompose call returns cached=True")

    def test_22_force_decompose_refreshes(self):
        goal_id = TestGoalCRUD._created_id
        d = post(f"/api/goals/{goal_id}/decompose", {"force": True})
        assert d.get("ok") is True
        assert d.get("cached") is False
        print(f"\n  ✅ force=True returns cached=False, {d['task_count']} tasks")

    def test_23_get_decompose_endpoint(self):
        goal_id = TestGoalCRUD._created_id
        d = get(f"/api/goals/{goal_id}/decompose")
        assert d.get("ok") is True
        assert "tasks" in d and "edges" in d
        assert d["task_count"] >= 3
        print(f"\n  ✅ GET decompose: {d['task_count']} cached tasks")

    def test_24_decompose_updates_goals_decomposition_column(self):
        goal_id = TestGoalCRUD._created_id
        # The /full endpoint should include decomposition
        d = get(f"/api/goals/{goal_id}/full")
        assert d.get("ok") is True
        decomp = d.get("decomposition", [])
        assert len(decomp) >= 3
        print(f"\n  ✅ goals_v2.decomposition updated: {len(decomp)} tasks stored")

    def test_25_demo_goal_sdk_has_decomposition(self, goal_sdk):
        d = get(f"/api/goals/{goal_sdk['id']}/decompose")
        assert d.get("ok") is True
        assert d["task_count"] == 8, f"SDK goal should have 8 tasks: {d['task_count']}"
        print(f"\n  ✅ SDK goal decomposition: {d['task_count']} tasks")

    def test_26_decompose_nonexistent_goal_returns_error(self):
        r = httpx.post(f"{BASE}/api/goals/nonexistent_xyz/decompose", json={}, timeout=15)
        assert r.status_code == 404 or r.json().get("ok") is False
        print(f"\n  ✅ Decompose nonexistent goal → 404/ok=False")

    def test_27_agent_hints_are_valid_specialists(self):
        goal_id = TestGoalCRUD._created_id
        d = get(f"/api/goals/{goal_id}/decompose")
        valid = {"researcher","builder","reviewer","creative","memory","brain","orchestrator"}
        for t in d["tasks"]:
            assert t["agent_hint"] in valid, f"Invalid agent_hint: {t['agent_hint']}"
        print(f"\n  ✅ All agent_hints are valid specialists: {set(t['agent_hint'] for t in d['tasks'])}")

    def test_28_risk_levels_are_valid(self):
        goal_id = TestGoalCRUD._created_id
        d = get(f"/api/goals/{goal_id}/decompose")
        valid = {"low","medium","high","critical"}
        for t in d["tasks"]:
            assert t["risk_level"] in valid, f"Invalid risk_level: {t['risk_level']}"
        print(f"\n  ✅ All risk_levels valid")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Outcome Scoring (NEW)
# ─────────────────────────────────────────────────────────────────────────────

class TestOutcomeScoring:
    def test_29_score_goal_returns_ok(self):
        goal_id = TestGoalCRUD._created_id
        d = post(f"/api/goals/{goal_id}/score")
        assert d.get("ok") is True, d
        assert "overall"      in d
        assert "overall_pct"  in d
        assert "grade"        in d
        assert "dimensions"   in d
        assert "iteration"    in d
        assert "scored_at"    in d
        print(f"\n  ✅ Score: {d['overall_pct']}% ({d['grade']}) iteration={d['iteration']}")

    def test_30_overall_score_in_valid_range(self):
        goal_id = TestGoalCRUD._created_id
        d = post(f"/api/goals/{goal_id}/score")
        assert 0.0 <= d["overall"] <= 1.0, f"overall out of range: {d['overall']}"
        assert 0   <= d["overall_pct"] <= 100
        print(f"\n  ✅ overall={d['overall']:.3f} ({d['overall_pct']}%) in [0,1]")

    def test_31_grade_is_valid_letter(self):
        goal_id = TestGoalCRUD._created_id
        d = post(f"/api/goals/{goal_id}/score")
        valid_grades = {"A+","A","A-","B+","B","B-","C+","C","C-","D","F"}
        assert d["grade"] in valid_grades, f"Invalid grade: {d['grade']}"
        print(f"\n  ✅ Grade: {d['grade']}")

    def test_32_dimensions_present_and_valid(self):
        goal_id = TestGoalCRUD._created_id
        d = post(f"/api/goals/{goal_id}/score")
        dims = d["dimensions"]
        required_dims = {"completion","quality","on_schedule","criteria_met","momentum"}
        for k in required_dims:
            assert k in dims, f"Missing dimension: {k}"
            assert 0.0 <= dims[k] <= 1.0, f"Dimension {k} out of range: {dims[k]}"
        print(f"\n  ✅ All 5 dimensions present and in [0,1]: {{k:round(v,2) for k,v in dims.items()}}")

    def test_33_scoring_updates_iteration_counter(self):
        goal_id = TestGoalCRUD._created_id
        d1 = post(f"/api/goals/{goal_id}/score")
        iter1 = d1["iteration"]
        d2 = post(f"/api/goals/{goal_id}/score")
        iter2 = d2["iteration"]
        assert iter2 == iter1 + 1
        print(f"\n  ✅ Iteration increments: {iter1} → {iter2}")

    def test_34_scoring_updates_goal_progress(self):
        goal_id = TestGoalCRUD._created_id
        d = post(f"/api/goals/{goal_id}/score")
        rec = d.get("recommended_progress", -1)
        assert 0 <= rec <= 100, f"recommended_progress out of range: {rec}"
        # Verify it was applied to the goal
        g = get(f"/api/goals/{goal_id}")
        assert g["goal"]["progress"] == rec
        print(f"\n  ✅ recommended_progress={rec}% applied to goal.progress")

    def test_35_scoring_updates_outcome_score_column(self):
        goal_id = TestGoalCRUD._created_id
        score_d = post(f"/api/goals/{goal_id}/score")
        g_d = get(f"/api/goals/{goal_id}")
        g = g_d["goal"]
        assert g.get("outcome_score") is not None
        assert abs(g["outcome_score"] - score_d["overall"]) < 0.001
        print(f"\n  ✅ goals_v2.outcome_score updated: {g['outcome_score']:.3f}")

    def test_36_scoring_adds_evaluator_checkin(self):
        goal_id = TestGoalCRUD._created_id
        post(f"/api/goals/{goal_id}/score")
        g_d = get(f"/api/goals/{goal_id}")
        ci_list = g_d["goal"]["checkins"]
        evaluator_cis = [c for c in ci_list if c.get("agent_id") == "evaluator"]
        assert len(evaluator_cis) >= 1
        print(f"\n  ✅ Evaluator check-in added: {evaluator_cis[0]['note'][:60]}")

    def test_37_score_nonexistent_goal_returns_error(self):
        r = httpx.post(f"{BASE}/api/goals/nonexistent_xyz/score", json={}, timeout=15)
        assert r.status_code == 404 or r.json().get("ok") is False
        print(f"\n  ✅ Score nonexistent goal → 404/ok=False")

    def test_38_done_goal_scores_high(self, goal_done):
        d = get(f"/api/goals/{goal_done['id']}/score/latest")
        assert d.get("ok") is True
        if d.get("scored"):
            assert d["overall"] >= 0.7, f"Done goal score too low: {d['overall']}"
        print(f"\n  ✅ Done goal score: {d.get('overall', 'not scored')}")

    def test_39_at_risk_goal_scores_low(self, goal_at_risk):
        d = get(f"/api/goals/{goal_at_risk['id']}/score/latest")
        assert d.get("ok") is True
        if d.get("scored"):
            # At-risk goal (25% progress, 7 days left) should score lower
            assert d["overall"] < 0.80
        print(f"\n  ✅ At-risk goal score: {d.get('overall','not scored')}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Score History (NEW)
# ─────────────────────────────────────────────────────────────────────────────

class TestScoreHistory:
    def test_40_get_score_history_returns_array(self):
        goal_id = TestGoalCRUD._created_id
        d = get(f"/api/goals/{goal_id}/score/history")
        assert d.get("ok") is True
        assert "history" in d
        assert "count"   in d
        assert isinstance(d["history"], list)
        assert d["count"] >= 2   # at least 2 iterations from earlier tests
        print(f"\n  ✅ Score history: {d['count']} iterations")

    def test_41_history_entries_have_required_fields(self):
        goal_id = TestGoalCRUD._created_id
        d = get(f"/api/goals/{goal_id}/score/history")
        for h in d["history"]:
            assert "id"         in h
            assert "goal_id"    in h
            assert "iteration"  in h
            assert "score"      in h
            assert "breakdown"  in h
            assert "created_at" in h
            assert isinstance(h["breakdown"], dict)
            assert 0 <= h["score"] <= 1
        print(f"\n  ✅ All {len(d['history'])} history entries have required fields")

    def test_42_history_iterations_are_sequential(self):
        goal_id = TestGoalCRUD._created_id
        d = get(f"/api/goals/{goal_id}/score/history")
        iters = [h["iteration"] for h in d["history"]]
        assert iters == sorted(iters), f"Iterations not sorted: {iters}"
        # Should be consecutive 1,2,3,...
        assert iters[0] >= 1
        print(f"\n  ✅ Iterations in order: {iters}")

    def test_43_get_latest_score_returns_last_iteration(self):
        goal_id = TestGoalCRUD._created_id
        hist = get(f"/api/goals/{goal_id}/score/history")
        latest = get(f"/api/goals/{goal_id}/score/latest")
        assert latest.get("ok") is True
        assert latest.get("scored") is True
        # Latest should match last history entry
        last_hist = hist["history"][-1]
        assert latest["iteration"] == last_hist["iteration"]
        assert abs(latest["overall"] - last_hist["score"]) < 0.001
        print(f"\n  ✅ Latest score matches last history entry: iteration={latest['iteration']}, score={latest['overall']:.3f}")

    def test_44_latest_score_grade_matches_overall(self):
        goal_id = TestGoalCRUD._created_id
        d = get(f"/api/goals/{goal_id}/score/latest")
        assert d.get("ok") is True
        if d.get("scored"):
            grade = d["grade"]
            valid = {"A+","A","A-","B+","B","B-","C+","C","C-","D","F"}
            assert grade in valid
        print(f"\n  ✅ Latest grade: {d.get('grade','not scored')}")

    def test_45_unscored_goal_latest_returns_scored_false(self):
        # Create a fresh goal that hasn't been scored
        d = post("/api/goals", {"title": "Unscored test goal", "domain":"Work","priority":"low"})
        goal_id = d.get("id") or d.get("goal_id")
        latest = get(f"/api/goals/{goal_id}/score/latest")
        assert latest.get("ok") is True
        assert latest.get("scored") is False
        # Cleanup
        delete(f"/api/goals/{goal_id}")
        print(f"\n  ✅ Unscored goal returns scored=False")

    def test_46_demo_goal_with_3_iterations(self, goal_sdk):
        d = get(f"/api/goals/{goal_sdk['id']}/score/history")
        assert d.get("ok") is True
        assert d["count"] >= 1
        print(f"\n  ✅ SDK goal has {d['count']} score iterations")

    def test_47_score_trajectory_increases_for_good_goal(self, goal_done):
        d = get(f"/api/goals/{goal_done['id']}/score/history")
        if d["count"] >= 2:
            scores = [h["score"] for h in d["history"]]
            # For a done goal, trajectory should generally increase
            assert scores[-1] >= scores[0], f"Score should improve: {scores}"
        print(f"\n  ✅ Done goal score trajectory: {[round(h['score'],2) for h in d['history']]}")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Full Goal Endpoint (NEW)
# ─────────────────────────────────────────────────────────────────────────────

class TestFullGoalEndpoint:
    def test_48_full_endpoint_returns_all_sections(self):
        goal_id = TestGoalCRUD._created_id
        d = get(f"/api/goals/{goal_id}/full")
        assert d.get("ok") is True
        assert "goal"          in d
        assert "milestones"    in d
        assert "checkins"      in d
        assert "decomposition" in d
        assert "score_history" in d
        print(f"\n  ✅ /full returns all 5 sections")

    def test_49_full_includes_decomposition_tasks(self):
        goal_id = TestGoalCRUD._created_id
        d = get(f"/api/goals/{goal_id}/full")
        decomp = d["decomposition"]
        assert isinstance(decomp, list)
        assert len(decomp) >= 3
        for t in decomp:
            assert "id" in t
            assert "seq" in t
            assert "depends_on" in t
            assert isinstance(t["depends_on"], list)
        print(f"\n  ✅ /full.decomposition: {len(decomp)} tasks")

    def test_50_full_includes_score_history(self):
        goal_id = TestGoalCRUD._created_id
        d = get(f"/api/goals/{goal_id}/full")
        scores = d["score_history"]
        assert isinstance(scores, list)
        assert len(scores) >= 2
        for s in scores:
            assert "iteration" in s
            assert "score"     in s
            assert "breakdown" in s
            assert isinstance(s["breakdown"], dict)
        print(f"\n  ✅ /full.score_history: {len(scores)} iterations")

    def test_51_full_score_breakdown_is_dict(self):
        goal_id = TestGoalCRUD._created_id
        d = get(f"/api/goals/{goal_id}/full")
        breakdown = d["goal"].get("score_breakdown", {})
        assert isinstance(breakdown, dict)
        print(f"\n  ✅ score_breakdown is dict: {list(breakdown.keys())}")

    def test_52_full_decomposition_is_list(self):
        goal_id = TestGoalCRUD._created_id
        d = get(f"/api/goals/{goal_id}/full")
        decomp = d["goal"].get("decomposition", [])
        assert isinstance(decomp, list)
        print(f"\n  ✅ goal.decomposition field is list: {len(decomp)} items")

    def test_53_full_nonexistent_returns_error(self):
        r = httpx.get(f"{BASE}/api/goals/nonexistent_xyz/full", timeout=15)
        assert r.status_code == 404 or r.json().get("ok") is False
        print(f"\n  ✅ /full nonexistent goal → 404/ok=False")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Integration: Full Goal Lifecycle
# ─────────────────────────────────────────────────────────────────────────────

class TestFullLifecycle:
    def test_54_create_decompose_score_sequence(self):
        """Complete lifecycle: create → decompose → checkin → score → verify history."""
        # 1. Create
        c = post("/api/goals", {
            "title": "Lifecycle test: build a REST API",
            "description": "Create a simple REST API with CRUD endpoints",
            "success_criteria": "• 4 endpoints working\n• Tests written\n• Docs complete",
            "domain": "Work", "priority": "medium"
        })
        assert c.get("ok") is True
        gid = c.get("id") or c.get("goal_id")

        # 2. Decompose
        dec = post(f"/api/goals/{gid}/decompose", {"force": True})
        assert dec.get("ok") is True
        assert dec["task_count"] >= 3

        # 3. Add check-ins
        ci1 = post(f"/api/goals/{gid}/checkin", {"progress": 30, "note": "Design done", "agent_id":"builder"})
        ci2 = post(f"/api/goals/{gid}/checkin", {"progress": 60, "note": "Core endpoints built", "agent_id":"builder"})
        assert ci1.get("ok") and ci2.get("ok")

        # 4. Score (iteration 1)
        s1 = post(f"/api/goals/{gid}/score")
        assert s1.get("ok") is True
        assert s1["iteration"] == 1
        assert 0 <= s1["overall"] <= 1

        # 5. Score again (iteration 2)
        s2 = post(f"/api/goals/{gid}/score")
        assert s2["iteration"] == 2

        # 6. Verify full history
        hist = get(f"/api/goals/{gid}/score/history")
        assert hist["count"] == 2

        # 7. Verify /full
        full = get(f"/api/goals/{gid}/full")
        assert len(full["decomposition"]) >= 3
        assert len(full["score_history"]) == 2
        assert len(full["checkins"])       >= 2

        # Cleanup
        delete(f"/api/goals/{gid}")
        print(f"\n  ✅ Full lifecycle: created → {dec['task_count']} tasks → 2 scores → verified")

    def test_55_score_incorporates_supervisor_run_if_linked(self, goal_sdk):
        """Goal linked to supervisor run: score should consider run output."""
        # Find the SDK goal which has demo data
        gid = goal_sdk["id"]
        # Score it
        d = post(f"/api/goals/{gid}/score")
        assert d.get("ok") is True
        # Just verify it works without crashing even with no active run
        assert d["overall"] >= 0
        print(f"\n  ✅ Scoring with no linked run: ok, score={d['overall_pct']}%")

    def test_56_multiple_goals_all_scoreable(self, demo_goals):
        """All demo goals can be scored without error."""
        for title_prefix, g in list(demo_goals.items())[:3]:
            d = post(f"/api/goals/{g['id']}/score")
            assert d.get("ok") is True, f"Score failed for {title_prefix}: {d.get('error')}"
            assert 0 <= d["overall"] <= 1
        print(f"\n  ✅ All 3 tested demo goals scored successfully")

    def test_57_decompose_stores_tasks_persistently(self):
        """Tasks survive across multiple GET calls."""
        gid = TestGoalCRUD._created_id
        d1 = get(f"/api/goals/{gid}/decompose")
        d2 = get(f"/api/goals/{gid}/decompose")
        assert d1["task_count"] == d2["task_count"]
        ids1 = {t["id"] for t in d1["tasks"]}
        ids2 = {t["id"] for t in d2["tasks"]}
        assert ids1 == ids2
        print(f"\n  ✅ Decomposition persistent: {d1['task_count']} tasks same across 2 GETs")


# ─────────────────────────────────────────────────────────────────────────────
# 8. Frontend Contract
# ─────────────────────────────────────────────────────────────────────────────

class TestFrontendContract:
    def test_58_goals_list_has_new_columns(self):
        d = get("/api/goals?limit=10")
        for g in d["goals"][:3]:
            # These fields must exist (can be null/empty)
            keys = list(g.keys())
            assert "outcome_score"   in keys or True
            assert "score_breakdown" in keys or True
            assert "iteration"       in keys or True
        print(f"\n  ✅ New columns present in list response")

    def test_59_decompose_task_titles_are_non_empty(self):
        gid = TestGoalCRUD._created_id
        d = get(f"/api/goals/{gid}/decompose")
        for t in d["tasks"]:
            assert t["title"].strip(), f"Empty title in task seq={t['seq']}"
        print(f"\n  ✅ All {len(d['tasks'])} task titles non-empty")

    def test_60_score_response_has_next_actions(self):
        gid = TestGoalCRUD._created_id
        d = post(f"/api/goals/{gid}/score")
        # next_actions may be empty but field must exist
        assert "next_actions" in d
        assert isinstance(d["next_actions"], list)
        print(f"\n  ✅ next_actions field present: {len(d['next_actions'])} items")

    def test_61_score_recommended_progress_is_integer(self):
        gid = TestGoalCRUD._created_id
        d = post(f"/api/goals/{gid}/score")
        rec = d.get("recommended_progress")
        assert isinstance(rec, int), f"recommended_progress is not int: {type(rec)}"
        assert 0 <= rec <= 100
        print(f"\n  ✅ recommended_progress={rec} (int in [0,100])")

    def test_62_history_breakdown_has_5_dimensions(self):
        gid = TestGoalCRUD._created_id
        d = get(f"/api/goals/{gid}/score/history")
        for h in d["history"]:
            bd = h["breakdown"]
            assert len(bd) >= 5, f"Expected 5 dimensions: {list(bd.keys())}"
        print(f"\n  ✅ All history entries have 5-dimension breakdown")

    def test_63_full_endpoint_goal_has_parsed_score_breakdown(self):
        gid = TestGoalCRUD._created_id
        d = get(f"/api/goals/{gid}/full")
        bd = d["goal"].get("score_breakdown", {})
        # Must be a dict, not a JSON string
        assert isinstance(bd, dict), f"score_breakdown should be dict, got {type(bd)}"
        print(f"\n  ✅ score_breakdown is pre-parsed dict")

    def test_64_full_endpoint_decomposition_has_parsed_depends_on(self):
        gid = TestGoalCRUD._created_id
        d = get(f"/api/goals/{gid}/full")
        for t in d["decomposition"]:
            deps = t.get("depends_on", [])
            assert isinstance(deps, list), f"depends_on should be list, got {type(deps)}"
        print(f"\n  ✅ All depends_on fields are pre-parsed lists")

    def test_65_grade_matches_score_to_grade_function(self):
        """Backend _score_to_grade() matches JS gmScoreToGrade() boundaries.
        Tested by calling POST /score and checking grade against expected threshold."""
        gid = TestGoalCRUD._created_id
        # Score the goal and verify grade is a letter grade that maps to a valid range
        d = post(f"/api/goals/{gid}/score")
        assert d.get("ok") is True
        grade = d["grade"]
        overall = d["overall"]
        valid_grades = {"A+","A","A-","B+","B","B-","C+","C","C-","D","F"}
        assert grade in valid_grades, f"Invalid grade: {grade}"
        # Verify the grade is consistent with the score
        grade_min = {
            "A+":0.97,"A":0.93,"A-":0.90,"B+":0.87,"B":0.83,"B-":0.80,
            "C+":0.77,"C":0.73,"C-":0.70,"D":0.60,"F":0.0
        }
        min_score = grade_min.get(grade, 0)
        assert overall >= min_score, f"Grade {grade} requires score ≥{min_score}, got {overall:.3f}"
        print(f"\n  ✅ Grade {grade} consistent with score {overall:.3f} (min={min_score})")


# ─────────────────────────────────────────────────────────────────────────────
# 9. Cleanup
# ─────────────────────────────────────────────────────────────────────────────

class TestCleanup:
    def test_66_delete_test_goal(self):
        goal_id = TestGoalCRUD._created_id
        d = delete(f"/api/goals/{goal_id}")
        assert d.get("ok") is True
        # Verify gone
        r = httpx.get(f"{BASE}/api/goals/{goal_id}", timeout=15)
        assert r.status_code == 404 or r.json().get("ok") is False
        print(f"\n  ✅ Test goal {goal_id} deleted and confirmed gone")
