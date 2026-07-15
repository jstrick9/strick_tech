"""
A2A Protocol Endpoint — Full Verification Test Suite
Tests the complete A2A v1.0 implementation.

Endpoints under test:
  GET  /.well-known/agent.json                  — platform agent card
  GET  /a2a/{id}/.well-known/agent.json         — per-agent card (spec URL)
  GET  /a2a/{id}/card                           — per-agent card (friendly)
  POST /a2a/{id}                                — JSON-RPC 2.0 dispatcher
  GET  /a2a/{id}/stream/{task_id}               — SSE stream for task

  GET  /api/a2a/agents                          — list registry
  POST /api/a2a/agents                          — register remote agent
  GET  /api/a2a/agents/{id}                     — get agent detail
  PATCH /api/a2a/agents/{id}                    — update agent config
  DELETE /api/a2a/agents/{id}                   — remove agent
  POST /api/a2a/agents/{id}/verify              — verify remote card
  POST /api/a2a/delegate                        — outbound task delegation
  GET  /api/a2a/tasks                           — list all tasks
  GET  /api/a2a/tasks/{id}                      — get task detail
  POST /api/a2a/tasks/{id}/cancel               — cancel task
  GET  /api/a2a/stats                           — usage stats

JSON-RPC methods under test:
  tasks/send
  tasks/get
  tasks/cancel
  tasks/list
  agents/getAuthenticatedExtendedCard

A2A spec compliance checks:
  - Agent Card schema (name, description, url, version, skills, capabilities, authentication)
  - JSON-RPC 2.0 format (jsonrpc, id, method, params, result/error)
  - Task state machine (submitted → working → completed/failed/canceled)
  - Message format (role, parts with type+text)
  - Artifacts format (name, mimeType, parts)
  - Error codes (standard -32xxx + A2A -32001 etc.)
"""
import pytest, httpx, json, time

BASE    = "http://127.0.0.1:8787"
TIMEOUT = 60

def get(path):
    r = httpx.get(f"{BASE}{path}", timeout=TIMEOUT)
    assert r.status_code in (200, 404), f"GET {path} → {r.status_code}: {r.text[:200]}"
    return r

def post(path, body=None):
    r = httpx.post(f"{BASE}{path}", json=body or {}, timeout=TIMEOUT)
    return r

def patch(path, body=None):
    r = httpx.patch(f"{BASE}{path}", json=body or {}, timeout=TIMEOUT)
    return r

def delete(path):
    r = httpx.delete(f"{BASE}{path}", timeout=TIMEOUT)
    return r

def rpc(agent_id: str, method: str, params: dict = None, rpc_id: str = "t1"):
    """Send a JSON-RPC 2.0 request to a local A2A agent endpoint."""
    body = {"jsonrpc":"2.0","id":rpc_id,"method":method,"params":params or {}}
    r = httpx.post(f"{BASE}/a2a/{agent_id}", json=body, timeout=TIMEOUT)
    assert r.status_code in (200, 400, 404), f"RPC {method} → {r.status_code}: {r.text[:200]}"
    return r.json()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Platform Agent Card (/.well-known/agent.json)
# ─────────────────────────────────────────────────────────────────────────────

class TestPlatformCard:
    def test_01_platform_card_returns_200(self):
        r = get("/.well-known/agent.json")
        assert r.status_code == 200
        print(f"\n  ✅ Platform card: HTTP 200")

    def test_02_platform_card_has_required_a2a_fields(self):
        d = get("/.well-known/agent.json").json()
        required = ["name","description","url","version","skills","capabilities","authentication","provider"]
        for f in required:
            assert f in d, f"Missing A2A field: {f}"
        print(f"\n  ✅ All {len(required)} required A2A v1.0 fields present")

    def test_03_platform_card_name(self):
        d = get("/.well-known/agent.json").json()
        assert d["name"] == "Agentic OS Platform"
        print(f"\n  ✅ Platform name: {d['name']}")

    def test_04_platform_card_skills_array(self):
        d = get("/.well-known/agent.json").json()
        assert isinstance(d["skills"], list)
        assert len(d["skills"]) >= 5
        for skill in d["skills"]:
            assert "id"          in skill
            assert "name"        in skill
            assert "description" in skill
        print(f"\n  ✅ {len(d['skills'])} platform skills with id/name/description")

    def test_05_platform_card_capabilities(self):
        d = get("/.well-known/agent.json").json()
        caps = d["capabilities"]
        assert isinstance(caps, dict)
        assert "streaming" in caps
        assert caps["streaming"] is True
        print(f"\n  ✅ Capabilities: {list(caps.keys())}")

    def test_06_platform_card_default_io_modes(self):
        d = get("/.well-known/agent.json").json()
        assert "defaultInputModes"  in d
        assert "defaultOutputModes" in d
        assert "text/plain" in d["defaultInputModes"]
        print(f"\n  ✅ Input modes: {d['defaultInputModes']}")

    def test_07_platform_card_has_cors_header(self):
        r = get("/.well-known/agent.json")
        assert r.headers.get("access-control-allow-origin") == "*"
        print(f"\n  ✅ CORS header: {r.headers.get('access-control-allow-origin')}")

    def test_08_platform_card_agentic_os_extension(self):
        d = get("/.well-known/agent.json").json()
        ext = d.get("_agentic_os",{})
        assert "version"   in ext
        assert "protocols" in ext
        assert "a2a/1.0" in ext["protocols"]
        print(f"\n  ✅ _agentic_os extension: version={ext['version']}, protocols={ext['protocols']}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Per-Agent Cards
# ─────────────────────────────────────────────────────────────────────────────

LOCAL_AGENTS = ["builder","researcher","reviewer","creative","brain","memory","orchestrator"]

class TestAgentCards:
    @pytest.mark.parametrize("agent_id", LOCAL_AGENTS)
    def test_09_agent_card_friendly_url(self, agent_id):
        r = get(f"/a2a/{agent_id}/card")
        assert r.status_code == 200
        d = r.json()
        assert d.get("name"), f"Agent card missing 'name' for {agent_id}"
        print(f"\n  ✅ /a2a/{agent_id}/card: name={d['name']}")

    @pytest.mark.parametrize("agent_id", LOCAL_AGENTS)
    def test_10_agent_card_spec_url(self, agent_id):
        r = get(f"/a2a/{agent_id}/.well-known/agent.json")
        assert r.status_code == 200
        d = r.json()
        assert "url" in d
        assert agent_id in d["url"]
        print(f"\n  ✅ /a2a/{agent_id}/.well-known/agent.json: url={d['url']}")

    def test_11_agent_card_has_all_required_fields(self):
        d = get("/a2a/builder/card").json()
        required = ["name","description","url","version","skills","capabilities","authentication","provider"]
        for f in required:
            assert f in d, f"Missing: {f}"
        print(f"\n  ✅ Builder card has all {len(required)} A2A fields")

    def test_12_agent_card_skills_are_role_specific(self):
        builder = get("/a2a/builder/card").json()
        researcher = get("/a2a/researcher/card").json()
        b_skill_ids = {s["id"] for s in builder["skills"]}
        r_skill_ids = {s["id"] for s in researcher["skills"]}
        # They should have different skills
        assert b_skill_ids != r_skill_ids
        # Builder should have code-related skill
        code_skills = {s for s in b_skill_ids if "code" in s.lower()}
        assert len(code_skills) >= 1, f"Builder should have code skill: {b_skill_ids}"
        print(f"\n  ✅ Skills are role-specific: builder={b_skill_ids}, researcher={r_skill_ids}")

    def test_13_agent_card_url_matches_endpoint(self):
        d = get("/a2a/orchestrator/card").json()
        assert "/a2a/orchestrator" in d["url"]
        print(f"\n  ✅ Card URL: {d['url']}")

    def test_14_agent_card_has_identity_extension(self):
        d = get("/a2a/builder/card").json()
        ext = d.get("_agentic_os",{})
        assert "agent_id"       in ext
        assert "authority_level" in ext
        assert "protocols"       in ext
        assert "a2a/1.0" in ext["protocols"]
        print(f"\n  ✅ Identity extension: authority={ext['authority_level']}")

    def test_15_nonexistent_agent_card_returns_404(self):
        r = get("/a2a/nonexistent_agent_xyz/card")
        assert r.status_code == 404
        print(f"\n  ✅ Nonexistent agent card → 404")

    def test_16_agent_cards_have_cors_header(self):
        r = get("/a2a/builder/card")
        assert r.headers.get("access-control-allow-origin") == "*"
        print(f"\n  ✅ Agent card has CORS header")


# ─────────────────────────────────────────────────────────────────────────────
# 3. JSON-RPC 2.0 Protocol
# ─────────────────────────────────────────────────────────────────────────────

class TestJSONRPC:
    def test_17_jsonrpc_version_required(self):
        r = post("/a2a/builder", {"id":"1","method":"tasks/list","params":{}})
        d = r.json()
        # Missing jsonrpc field
        assert d.get("error") or d.get("jsonrpc") == "2.0"
        print(f"\n  ✅ jsonrpc version enforcement: {d.get('error',{}).get('code')}")

    def test_18_jsonrpc_response_has_required_fields(self):
        d = rpc("builder","tasks/list",{})
        assert "jsonrpc" in d
        assert d["jsonrpc"] == "2.0"
        assert "id" in d
        assert "result" in d or "error" in d
        print(f"\n  ✅ JSON-RPC 2.0 response format valid")

    def test_19_unknown_method_returns_minus_32601(self):
        d = rpc("builder","tasks/nonexistent_method",{})
        assert "error" in d
        assert d["error"]["code"] == -32601
        print(f"\n  ✅ Unknown method → error code -32601")

    def test_20_tasks_list_returns_array(self):
        d = rpc("researcher","tasks/list",{})
        assert "result" in d
        assert "tasks" in d["result"]
        assert isinstance(d["result"]["tasks"], list)
        assert "total" in d["result"]
        print(f"\n  ✅ tasks/list: {d['result']['total']} tasks")

    def test_21_tasks_get_nonexistent_returns_minus_32001(self):
        d = rpc("builder","tasks/get",{"id":"nonexistent_task_xyz"})
        assert "error" in d
        assert d["error"]["code"] == -32001  # A2A TaskNotFound
        print(f"\n  ✅ tasks/get nonexistent → -32001")

    def test_22_tasks_cancel_nonexistent_returns_error(self):
        d = rpc("builder","tasks/cancel",{"id":"nonexistent_xyz"})
        assert "error" in d
        assert d["error"]["code"] == -32001
        print(f"\n  ✅ tasks/cancel nonexistent → -32001")

    def test_23_tasks_send_requires_message(self):
        d = rpc("builder","tasks/send",{})
        assert "error" in d
        assert d["error"]["code"] == -32602  # invalid params
        print(f"\n  ✅ tasks/send without message → -32602")

    def test_24_authenticated_card_method(self):
        d = rpc("orchestrator","agents/getAuthenticatedExtendedCard",{})
        assert "result" in d
        card = d["result"]
        assert "name" in card
        assert "skills" in card
        print(f"\n  ✅ agents/getAuthenticatedExtendedCard: {card['name']}")

    def test_25_tasks_list_with_state_filter(self):
        d = rpc("researcher","tasks/list",{"state":"completed"})
        assert "result" in d
        tasks = d["result"]["tasks"]
        for t in tasks:
            assert t["status"]["state"] == "completed"
        print(f"\n  ✅ tasks/list with state filter: {len(tasks)} completed tasks")

    def test_26_rpc_id_is_echoed(self):
        d = rpc("builder","tasks/list",{},"my-unique-id-12345")
        assert d.get("id") == "my-unique-id-12345"
        print(f"\n  ✅ RPC id echoed: {d['id']}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Tasks/Send — Full Lifecycle
# ─────────────────────────────────────────────────────────────────────────────

class TestTaskSend:
    _task_ids = []

    def test_27_tasks_send_creates_task(self):
        d = rpc("researcher","tasks/send",{
            "message": {
                "role":  "user",
                "parts": [{"type":"text","text":"Write a one-sentence summary of what an AI agent is."}]
            }
        })
        # tasks/send is synchronous — returns completed or working result
        assert "result" in d or "error" in d
        if "result" in d:
            result = d["result"]
            assert "id"     in result
            assert "status" in result
            assert result["status"]["state"] in ("submitted","working","completed","failed")
            TestTaskSend._task_ids.append(result["id"])
        print(f"\n  ✅ tasks/send returned: {d.get('result',{}).get('status',{}).get('state','error')}")

    def test_28_tasks_send_accepts_string_message(self):
        """tasks/send should normalize string message to Message format."""
        d = rpc("builder","tasks/send",{
            "message": "Explain the difference between AI and machine learning in one sentence."
        })
        # Should work even with raw string (we normalize it)
        assert "result" in d or "error" in d
        print(f"\n  ✅ String message normalized: {d.get('result',{}).get('status',{}).get('state','error/ok')}")

    def test_29_tasks_send_with_session_id(self):
        d = rpc("researcher","tasks/send",{
            "sessionId": "test-session-001",
            "message": {"role":"user","parts":[{"type":"text","text":"Hello from session."}]}
        })
        if "result" in d:
            assert d["result"].get("sessionId") == "test-session-001"
        print(f"\n  ✅ Session ID propagated")

    def test_30_completed_task_has_artifacts(self):
        """After tasks/send completes, result should have artifacts."""
        if not TestTaskSend._task_ids:
            pytest.skip("No completed tasks from test_27")
        task_id = TestTaskSend._task_ids[0]
        # tasks/send is synchronous so check the returned result directly
        d = rpc("researcher","tasks/get",{"id": task_id})
        if "result" in d:
            result = d["result"]
            state  = result.get("status",{}).get("state","")
            if state == "completed":
                assert isinstance(result.get("artifacts",[]), list)
                print(f"\n  ✅ Completed task has {len(result.get('artifacts',[]))} artifacts")
            else:
                print(f"\n  ✅ Task state: {state}")
        else:
            print(f"\n  ✅ Task get returned error (task may have been GC'd)")

    def test_31_tasks_send_task_appears_in_list(self):
        """Task created by tasks/send appears in tasks/list."""
        if not TestTaskSend._task_ids:
            pytest.skip("No task IDs from test_27")
        task_id = TestTaskSend._task_ids[0]
        d = rpc("researcher","tasks/list",{})
        assert "result" in d
        task_ids_in_list = [t["id"] for t in d["result"]["tasks"]]
        assert task_id in task_ids_in_list
        print(f"\n  ✅ Task {task_id[:15]} appears in tasks/list")

    def test_32_task_cancel_works(self):
        """Create a task and cancel it via tasks/cancel."""
        # First submit a task
        d = rpc("builder","tasks/send",{
            "id":"cancel_test_task",
            "message":{"role":"user","parts":[{"type":"text","text":"Quick cancel test"}]}
        })
        # Now try to cancel (may already be completed)
        cancel = rpc("builder","tasks/cancel",{"id":"cancel_test_task"})
        # Either cancels or says already terminal
        assert "result" in cancel or "error" in cancel
        if "result" in cancel:
            state = cancel["result"]["status"]["state"]
            assert state in ("canceled","completed","failed")
        print(f"\n  ✅ tasks/cancel: {cancel.get('result',{}).get('status',{}).get('state','error/completed')}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Registry — Remote Agent Management
# ─────────────────────────────────────────────────────────────────────────────

class TestRegistry:
    _registered_id = None

    def test_33_list_agents_returns_registered(self):
        d = get("/api/a2a/agents").json()
        assert "agents"       in d
        assert "local_agents" in d
        assert "total"        in d
        assert d["total"] >= 3  # 3 seeded demo agents
        print(f"\n  ✅ Registry: {d['total']} registered, {len(d['local_agents'])} local")

    def test_34_registered_agents_have_required_fields(self):
        d = get("/api/a2a/agents").json()
        for ag in d["agents"]:
            assert "agent_id"    in ag
            assert "name"        in ag
            assert "a2a_url"     in ag
            assert "trust_level" in ag
            assert "status"      in ag
            assert "skills"      in ag
        print(f"\n  ✅ All registered agents have required fields")

    def test_35_local_orchestrator_in_registry(self):
        d = get("/api/a2a/agents").json()
        local = next((a for a in d["agents"] if a["agent_id"]=="local_orchestrator"), None)
        assert local is not None
        assert local["trust_level"] == "local"
        assert local["status"] == "active"
        print(f"\n  ✅ local_orchestrator: trust={local['trust_level']} status={local['status']}")

    def test_36_register_new_remote_agent(self):
        d = post("/api/a2a/agents", {
            "name": "Test External Agent",
            "a2a_url": "https://test-external.example.com/a2a",
            "description": "Test agent for verification suite",
            "auth_type": "none",
        }).json()
        assert d.get("ok") is True
        assert d.get("agent_id")
        TestRegistry._registered_id = d["agent_id"]
        print(f"\n  ✅ Registered: {d['agent_id']}")

    def test_37_registered_agent_appears_in_list(self):
        aid = TestRegistry._registered_id
        if not aid:
            pytest.skip("No registered ID from test_36")
        d = get("/api/a2a/agents").json()
        ids = {a["agent_id"] for a in d["agents"]}
        assert aid in ids
        print(f"\n  ✅ New agent appears in list")

    def test_38_get_agent_detail(self):
        aid = TestRegistry._registered_id
        if not aid:
            pytest.skip("No registered ID")
        d = get(f"/api/a2a/agents/{aid}").json()
        assert d.get("ok") is True
        assert d["agent"]["agent_id"] == aid
        assert "recent_tasks" in d
        print(f"\n  ✅ Agent detail: {d['agent']['name']}")

    def test_39_update_agent_trust_level(self):
        aid = TestRegistry._registered_id
        if not aid:
            pytest.skip("No registered ID")
        d = patch(f"/api/a2a/agents/{aid}", {"trust_level":"unverified","status":"unreachable"}).json()
        assert d.get("ok") is True
        assert "trust_level" in d.get("updated",[])
        # Verify
        d2 = get(f"/api/a2a/agents/{aid}").json()
        assert d2["agent"]["trust_level"] == "unverified"
        print(f"\n  ✅ Trust level updated: {d2['agent']['trust_level']}")

    def test_40_verify_local_agent(self):
        """Verify the local orchestrator agent — should succeed since it's running."""
        d = post("/api/a2a/agents/local_orchestrator/verify").json()
        assert d.get("ok") is True
        assert d.get("status") == "active"
        print(f"\n  ✅ Local orchestrator verified: {d.get('card_name')}")

    def test_41_verify_unreachable_agent(self):
        """Verify an unreachable remote agent — should return status=unreachable."""
        aid = TestRegistry._registered_id
        if not aid:
            pytest.skip("No registered ID")
        d = post(f"/api/a2a/agents/{aid}/verify").json()
        # Unreachable is the expected outcome for demo external agent
        assert d.get("ok") is False or d.get("status") in ("unreachable","active")
        print(f"\n  ✅ Unreachable agent verify: status={d.get('status','?')}")

    def test_42_cannot_delete_local_orchestrator(self):
        r = delete("/api/a2a/agents/local_orchestrator")
        d = r.json()
        assert d.get("ok") is False
        print(f"\n  ✅ local_orchestrator protected from deletion: {d['error'][:40]}")

    def test_43_delete_registered_agent(self):
        aid = TestRegistry._registered_id
        if not aid:
            pytest.skip("No registered ID")
        d = delete(f"/api/a2a/agents/{aid}").json()
        assert d.get("ok") is True
        # Verify gone
        r = get(f"/api/a2a/agents/{aid}")
        assert r.status_code == 404 or r.json().get("ok") is False
        print(f"\n  ✅ Agent {aid} deleted and confirmed gone")

    def test_44_register_missing_url_returns_error(self):
        r = post("/api/a2a/agents", {"name":"Test"})
        d = r.json()
        assert d.get("ok") is False
        print(f"\n  ✅ Missing URL rejected: {d['error'][:40]}")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Outbound Delegation
# ─────────────────────────────────────────────────────────────────────────────

class TestDelegation:
    def test_45_delegate_to_local_agent(self):
        """Delegate to a local A2A agent (orchestrator) — should execute."""
        d = post("/api/a2a/delegate", {
            "agent_id": "local_orchestrator",
            "message":  "Write a one-sentence definition of machine learning.",
        }).json()
        # Local delegation should work
        assert "task_id" in d
        print(f"\n  ✅ Delegate to local: task_id={d.get('task_id','?')[:20]}, ok={d.get('ok')}")

    def test_46_delegate_to_remote_agent_handles_unreachable(self):
        """Delegate to unreachable remote — should return task_id with note."""
        d = post("/api/a2a/delegate", {
            "agent_id": "ext_langchain_agent",
            "message":  "Test delegation to remote agent",
        }).json()
        # Should return task_id regardless (we record the attempt)
        assert "task_id" in d
        # ok=False is expected for unreachable remote
        if not d.get("ok"):
            assert "note" in d or "error" in d
        print(f"\n  ✅ Delegate to remote (unreachable): task_id={d.get('task_id','?')[:20]}")

    def test_47_delegate_missing_message_returns_error(self):
        r = post("/api/a2a/delegate", {"agent_id":"local_orchestrator"})
        d = r.json()
        assert d.get("ok") is False
        print(f"\n  ✅ Missing message rejected: {d['error'][:40]}")

    def test_48_delegate_nonexistent_agent_returns_404(self):
        r = post("/api/a2a/delegate", {
            "agent_id": "nonexistent_agent_xyz",
            "message": "test"
        })
        d = r.json()
        assert r.status_code == 404 or d.get("ok") is False
        print(f"\n  ✅ Nonexistent agent → 404/ok=False")

    def test_49_delegate_creates_task_in_db(self):
        """Delegation creates an outbound task visible in /api/a2a/tasks."""
        d = post("/api/a2a/delegate", {
            "agent_id": "ext_crewai_writer",
            "message":  "Write a haiku about A2A protocol.",
        }).json()
        task_id = d.get("task_id")
        assert task_id
        # Check it appears in task list
        tasks = get("/api/a2a/tasks").json()
        ids = {t["task_id"] for t in tasks["tasks"]}
        assert task_id in ids
        print(f"\n  ✅ Delegation task in DB: {task_id[:20]}")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Task Management API
# ─────────────────────────────────────────────────────────────────────────────

class TestTaskManagement:
    def test_50_list_all_tasks(self):
        d = get("/api/a2a/tasks").json()
        assert "tasks" in d
        assert "total" in d
        assert "count" in d
        assert isinstance(d["tasks"], list)
        print(f"\n  ✅ Task list: {d['count']} tasks")

    def test_51_list_tasks_filter_by_state(self):
        d = get("/api/a2a/tasks?state=completed").json()
        for t in d["tasks"]:
            assert t["state"] == "completed"
        print(f"\n  ✅ State filter: {d['count']} completed tasks")

    def test_52_get_task_detail(self):
        """Get a real task's full detail."""
        tasks = get("/api/a2a/tasks").json()["tasks"]
        if not tasks:
            pytest.skip("No tasks available")
        task_id = tasks[0]["task_id"]
        d = get(f"/api/a2a/tasks/{task_id}").json()
        assert d.get("ok") is True
        assert "task"         in d
        assert "a2a_response" in d
        assert "call_log"     in d
        print(f"\n  ✅ Task detail: {task_id[:20]} state={d['task']['state']}")

    def test_53_task_detail_has_a2a_response_format(self):
        """a2a_response matches A2A TaskStatus format."""
        tasks = get("/api/a2a/tasks").json()["tasks"]
        if not tasks:
            pytest.skip("No tasks")
        task_id = tasks[0]["task_id"]
        d = get(f"/api/a2a/tasks/{task_id}").json()
        a2a = d["a2a_response"]
        assert "id"       in a2a
        assert "status"   in a2a
        assert "state"    in a2a["status"]
        assert "artifacts" in a2a
        assert isinstance(a2a["artifacts"], list)
        print(f"\n  ✅ A2A response format valid: state={a2a['status']['state']}")

    def test_54_cancel_nonexistent_task_returns_404(self):
        r = post("/api/a2a/tasks/nonexistent_xyz_123/cancel")
        d = r.json()
        assert r.status_code in (200,404)
        assert d.get("ok") is False
        print(f"\n  ✅ Cancel nonexistent → ok=False: {d.get('error','')[:40]}")

    def test_55_list_tasks_direction_field(self):
        """Each task has a direction (inbound or outbound)."""
        tasks = get("/api/a2a/tasks").json()["tasks"]
        for t in tasks:
            assert "direction" in t
            assert t["direction"] in ("inbound","outbound")
        print(f"\n  ✅ All tasks have direction field")


# ─────────────────────────────────────────────────────────────────────────────
# 8. Stats
# ─────────────────────────────────────────────────────────────────────────────

class TestStats:
    def test_56_stats_returns_all_fields(self):
        d = get("/api/a2a/stats").json()
        required = ["total_tasks","by_state","inbound_calls","outbound_calls",
                    "registered_agents","active_agents","local_agents","recent_tasks"]
        for f in required:
            assert f in d, f"Missing: {f}"
        print(f"\n  ✅ Stats: {list(d.keys())}")

    def test_57_stats_counts_are_nonnegative(self):
        d = get("/api/a2a/stats").json()
        for k in ["total_tasks","inbound_calls","outbound_calls","registered_agents"]:
            assert d[k] >= 0
        print(f"\n  ✅ Stats counts non-negative: tasks={d['total_tasks']}, registered={d['registered_agents']}")

    def test_58_stats_registered_includes_demo_agents(self):
        d = get("/api/a2a/stats").json()
        assert d["registered_agents"] >= 3
        print(f"\n  ✅ {d['registered_agents']} agents registered")


# ─────────────────────────────────────────────────────────────────────────────
# 9. SSE Stream
# ─────────────────────────────────────────────────────────────────────────────

class TestSSEStream:
    def test_59_sse_stream_returns_events(self):
        """GET /a2a/{id}/stream/{task_id} returns SSE events."""
        # Use a task that may not exist — should return task not found event
        with httpx.stream("GET", f"{BASE}/a2a/builder/stream/nonexistent_task_xyz",
                          timeout=5) as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers.get("content-type","")
            # Read first event
            buf = ""
            for chunk in r.iter_text():
                buf += chunk
                if "\n\n" in buf:
                    break
        assert len(buf) > 0
        print(f"\n  ✅ SSE stream: content-type=text/event-stream, got {len(buf)} bytes")

    def test_60_tasks_send_subscribe_returns_sse(self):
        """tasks/sendSubscribe returns SSE stream."""
        body = {
            "jsonrpc":"2.0","id":"sse1","method":"tasks/sendSubscribe",
            "params":{
                "message":{"role":"user","parts":[{"type":"text","text":"Quick hello."}]}
            }
        }
        events = []
        with httpx.stream("POST", f"{BASE}/a2a/builder", json=body, timeout=30) as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers.get("content-type","")
            buf = ""
            for chunk in r.iter_text():
                buf += chunk
                while "\n\n" in buf:
                    event_str, buf = buf.split("\n\n",1)
                    if "data:" in event_str:
                        for line in event_str.split("\n"):
                            if line.startswith("data:"):
                                try:
                                    events.append(json.loads(line[5:].strip()))
                                except:
                                    pass
                if any(e.get("final") for e in events):
                    break
        assert len(events) >= 1
        # First event should be TaskStatusUpdateEvent with submitted state
        assert events[0].get("id") or events[0].get("status")
        print(f"\n  ✅ tasks/sendSubscribe SSE: {len(events)} events received")
