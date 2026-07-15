"""
Agentic OS — Locust Load Test
Run: locust -f tests/load/locustfile.py --host=http://127.0.0.1:8787
     --users=100 --spawn-rate=10 --run-time=60s --headless

Simulates realistic user behaviour across all major platform features.
"""
from locust import HttpUser, task, between, events
import json, uuid, random


def uid(p="load"):
    return f"{p}_{uuid.uuid4().hex[:6]}"


class AgenticOSUser(HttpUser):
    """Simulates a real platform user across all feature areas."""
    wait_time = between(0.5, 2.0)
    host = "http://127.0.0.1:8787"

    # ── High-frequency tasks (weight=10-20) ───────────────────────────────────
    @task(20)
    def health_check(self):
        self.client.get("/api/health", name="GET /api/health")

    @task(15)
    def list_agents(self):
        self.client.get("/api/agents", name="GET /api/agents")

    @task(12)
    def list_tasks(self):
        self.client.get("/api/tasks", name="GET /api/tasks")

    @task(12)
    def chat_history(self):
        self.client.get("/api/chat/history", name="GET /api/chat/history")

    @task(10)
    def memory_stats(self):
        self.client.get("/api/memory/stats", name="GET /api/memory/stats")

    @task(10)
    def memory_list(self):
        self.client.get("/api/memory/list?limit=20", name="GET /api/memory/list")

    # ── Mid-frequency tasks (weight=5-8) ──────────────────────────────────────
    @task(8)
    def analytics_kpis(self):
        self.client.get("/api/analytics/kpis", name="GET /api/analytics/kpis")

    @task(8)
    def list_sessions(self):
        self.client.get("/api/sessions", name="GET /api/sessions")

    @task(7)
    def audit_log(self):
        self.client.get("/api/audit-log", name="GET /api/audit-log")

    @task(7)
    def supervisor_runs(self):
        self.client.get("/api/supervisor/runs", name="GET /api/supervisor/runs")

    @task(6)
    def goals_list(self):
        self.client.get("/api/goals", name="GET /api/goals")

    @task(6)
    def finops_dashboard(self):
        self.client.get("/api/finops/dashboard", name="GET /api/finops/dashboard")

    @task(6)
    def eval_suites(self):
        self.client.get("/api/eval-framework/suites", name="GET /api/eval-framework/suites")

    @task(5)
    def monitor_live(self):
        self.client.get("/api/agent-monitor/live", name="GET /api/agent-monitor/live")

    @task(5)
    def mcp_servers(self):
        self.client.get("/api/mcp-gateway/servers", name="GET /api/mcp-gateway/servers")

    @task(5)
    def connectors_list(self):
        self.client.get("/api/connectors", name="GET /api/connectors")

    @task(5)
    def qdrant_status(self):
        self.client.get("/api/memory/qdrant/status", name="GET /api/memory/qdrant/status")

    # ── Write tasks (weight=2-4) ──────────────────────────────────────────────
    @task(4)
    def add_memory(self):
        self.client.post("/api/memory/add",
            json={"content": uid("load_memory_content"), "source": "locust"},
            name="POST /api/memory/add")

    @task(3)
    def create_and_delete_task(self):
        title = uid("load_task")
        r = self.client.post("/api/tasks",
            json={"title": title, "status": "todo"},
            name="POST /api/tasks")
        if r.status_code == 200:
            tid = r.json().get("id")
            if tid:
                self.client.delete(f"/api/tasks/{tid}",
                    name="DELETE /api/tasks/{id}")

    @task(3)
    def append_audit_entry(self):
        self.client.post("/api/audit-log/append", json={
            "actor": "locust", "action": "load.test",
            "resource": "locust", "resource_id": uid("r"),
            "outcome": "success", "detail": "Load test entry"
        }, name="POST /api/audit-log/append")

    @task(2)
    def record_finops_cost(self):
        self.client.post("/api/finops/ledger/record", json={
            "agent_id": random.choice(["brain","builder","researcher"]),
            "model": "gpt4o-mini", "provider": "openrouter",
            "tokens_in": random.randint(100, 1000),
            "tokens_out": random.randint(20, 200),
            "cost_usd": round(random.uniform(0.001, 0.01), 4),
            "session_id": uid("sess"), "task": "load test"
        }, name="POST /api/finops/ledger/record")

    @task(2)
    def broadcast_ws_event(self):
        self.client.post("/api/ws/broadcast",
            json={"event": "load.test.event", "payload": {"n": random.randint(1, 100)}},
            name="POST /api/ws/broadcast")

    @task(2)
    def memory_search(self):
        q = random.choice(["agent","task","memory","test","load"])
        self.client.get(f"/api/memory/search?q={q}", name="GET /api/memory/search")

    @task(2)
    def db_simple_query(self):
        self.client.post("/api/db/sqlite/query",
            json={"sql": "SELECT COUNT(*) as n FROM agents"},
            name="POST /api/db/sqlite/query")

    # ── Low-frequency (weight=1) ─────────────────────────────────────────────
    @task(1)
    def supervisor_dispatch(self):
        self.client.post("/api/supervisor/run", json={
            "goal": "Load test task - analyze performance",
            "strategy": "sequential", "agents": ["brain"], "context": {}
        }, name="POST /api/supervisor/run")

    @task(1)
    def create_goal(self):
        r = self.client.post("/api/goals", json={
            "title": uid("LoadGoal"), "domain": "engineering", "priority": "low"
        }, name="POST /api/goals")
        if r.status_code == 200:
            gid = r.json().get("id")
            if gid:
                self.client.delete(f"/api/goals/{gid}", name="DELETE /api/goals/{id}")

    @task(1)
    def vector_embed_memory(self):
        self.client.post("/api/memory/add-with-embedding",
            json={"content": uid("vector_load_test"), "source": "locust-vector"},
            name="POST /api/memory/add-with-embedding")


class AgenticOSAdminUser(HttpUser):
    """Simulates an admin/monitoring user checking dashboards."""
    wait_time = between(2.0, 5.0)
    weight = 2  # 1 admin per 5 regular users

    @task(5)
    def full_analytics_dashboard(self):
        self.client.get("/api/analytics/dashboard", name="GET /api/analytics/dashboard")

    @task(4)
    def finops_timeseries(self):
        self.client.get("/api/finops/stats/time-series", name="GET /api/finops/stats/time-series")

    @task(4)
    def monitor_summary(self):
        self.client.get("/api/agent-monitor/summary", name="GET /api/agent-monitor/summary")

    @task(3)
    def eval_platform_stats(self):
        self.client.get("/api/eval-framework/stats/platform", name="GET /api/eval-framework/stats/platform")

    @task(3)
    def audit_log_stats(self):
        self.client.get("/api/audit-log/stats", name="GET /api/audit-log/stats")

    @task(2)
    def audit_verify_chain(self):
        self.client.get("/api/audit-log/verify", name="GET /api/audit-log/verify")

    @task(2)
    def identity_system_stats(self):
        self.client.get("/api/agent-identity/system/stats", name="GET /api/agent-identity/system/stats")

    @task(1)
    def security_scan(self):
        self.client.post("/api/gitai/security/scan", json={"path": "."},
            name="POST /api/gitai/security/scan")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("\n🚀 Agentic OS Load Test Starting")
    print(f"   Target: {environment.host}")
    print(f"   Users: {environment.parsed_options.num_users if hasattr(environment, 'parsed_options') else '?'}")

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    stats = environment.stats
    total = stats.total
    print(f"\n📊 Load Test Complete")
    print(f"   Total requests: {total.num_requests}")
    print(f"   Failures:       {total.num_failures}")
    print(f"   Avg response:   {total.avg_response_time:.0f}ms")
    print(f"   p99 response:   {total.get_response_time_percentile(0.99):.0f}ms")
    print(f"   RPS:            {total.total_rps:.1f}")
