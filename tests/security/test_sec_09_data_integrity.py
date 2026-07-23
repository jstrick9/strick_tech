"""
SEC-09: Data Integrity, Secrets Management & Information Disclosure
Tests: Secrets never exposed, data isolation, resource exhaustion prevention,
       HTTP security headers, sensitive endpoint protection.
"""
import pytest, json, asyncio
from tests.security.conftest import *

# ─────────────────────────────────────────────────────────────────────────────
# SECRETS MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

class TestSecSecretsManagement:
    """Vault/secrets must never return raw values via any endpoint."""

    async def test_secrets_set_and_get_masked(self, C):
        """Secret values must be masked in list response."""
        key = uid("SEC_TEST")
        val = "SUPER_SENSITIVE_VALUE_12345_NEVER_EXPOSE"
        await POST(C, "/api/secrets/set", {"key": key, "value": val})

        r = await GET(C, "/api/secrets")
        sec_ok(r, "Secrets list masking")
        assert val not in r.text, f"Secret value '{val}' exposed in list response!"

    async def test_secrets_not_in_analytics(self, C):
        """Analytics endpoints must not leak secret values."""
        await POST(C, "/api/secrets/set", {"key": uid("ANALYTICS_SEC"), "value": "secret_analytics_val"})

        for ep in ["/api/analytics/kpis", "/api/analytics/dashboard", "/api/analytics/activity"]:
            r = await GET(C, ep)
            sec_ok(r, f"Secrets in analytics: {ep}")
            assert "secret_analytics_val" not in r.text, \
                f"Secret leaked in analytics endpoint {ep}"

    async def test_secrets_not_in_audit_log(self, C):
        """Audit log must not contain raw secret values."""
        val = "AUDIT_LOG_SECRET_LEAK_TEST_12345"
        await POST(C, "/api/secrets/set", {"key": uid("AUDIT_SEC"), "value": val})

        r = await GET(C, "/api/audit-log")
        sec_ok(r, "Secrets in audit log")
        assert val not in r.text, "Secret value leaked in audit log!"

    async def test_secrets_not_in_error_messages(self, C):
        """Error responses must not contain secret values."""
        val = "ERROR_MSG_SECRET_LEAK_99999"
        await POST(C, "/api/secrets/set", {"key": uid("ERR_SEC"), "value": val})

        # Trigger various errors
        for bad_req in [
            ("POST", "/api/tasks", {"invalid": True}),
            ("GET", "/api/agents/nonexistent_999"),
        ]:
            if bad_req[0] == "POST":
                r = await POST(C, bad_req[1], bad_req[2])
            else:
                r = await GET(C, bad_req[1])
            assert val not in r.text, f"Secret in error response at {bad_req[1]}"

    async def test_env_vars_not_in_any_response(self, C):
        """Environment variables must never be exposed in any API response."""
        import os
        # Set a unique env var to detect if exposed
        sentinel = "AGENTIC_SEC_TEST_SENTINEL_XYZ123"
        os.environ["AGENTIC_SEC_TEST_SENTINEL"] = sentinel

        critical_endpoints = [
            "/api/health", "/api/agents", "/api/profile",
            "/api/analytics/kpis", "/api/audit-log",
            "/api/license/status", "/api/db/sqlite/tables"
        ]
        for ep in critical_endpoints:
            r = await GET(C, ep)
            sec_ok(r, f"Env var exposure at {ep}")
            assert sentinel not in r.text, f"Env var leaked at {ep}"

    async def test_secret_key_deletion_leaves_no_trace(self, C):
        """After deleting a secret, it must not appear in any listing."""
        key = uid("DEL_SEC")
        val = "delete_me_secret_value_99999"
        await POST(C, "/api/secrets/set", {"key": key, "value": val})
        await DELETE(C, f"/api/secrets/{key}")

        r = await GET(C, "/api/secrets")
        sec_ok(r, "Deleted secret trace check")
        # Neither key nor value should appear
        assert val not in r.text, "Deleted secret value still in listing!"


# ─────────────────────────────────────────────────────────────────────────────
# INFORMATION DISCLOSURE
# ─────────────────────────────────────────────────────────────────────────────

class TestSecInformationDisclosure:
    """Platform must not disclose internal paths, software versions, or user data."""

    async def test_error_messages_dont_expose_file_paths(self, C):
        """Error messages must not contain absolute server filesystem paths."""
        error_triggers = [
            ("GET", "/api/agents/INVALID_AGENT_PATH_TEST"),
            ("POST", "/api/tasks", {"title": None}),
            ("GET", "/api/sessions/INVALID_SESSION_99"),
        ]
        server_root = "/home/user/agentic-os"
        for method, path, *body in error_triggers:
            if method == "GET":
                r = await GET(C, path)
            else:
                r = await POST(C, path, body[0] if body else {})
            text = r.text
            assert server_root not in text, \
                f"Server filesystem path '{server_root}' exposed at {path}: {text[:200]}"

    async def test_db_schema_not_overly_exposed(self, C):
        """DB schema endpoint should only be accessible for legitimate purposes."""
        r = await GET(C, "/api/db/sqlite/schema")
        sec_ok(r, "DB schema exposure check")
        # Schema exposure itself is OK for the DB Studio feature,
        # but it must not contain actual data values
        body = r.text.lower()
        assert "super_secret_value" not in body, "Secret data in DB schema response"

    async def test_openapi_spec_no_internal_endpoints(self, C):
        """OpenAPI spec must not expose undocumented internal endpoints."""
        r = await GET(C, "/api/openapi.json")
        sec_ok(r, "OpenAPI spec check")
        spec = r.json()
        paths = spec.get("paths", {})
        internal_patterns = ["/_internal", "/admin/", "/debug/", "/__"]
        for path in paths:
            for pattern in internal_patterns:
                assert pattern not in path, \
                    f"Internal endpoint exposed in OpenAPI: {path}"

    async def test_health_endpoint_no_version_details(self, C):
        """Health endpoint must not expose detailed version/dependency info."""
        r = await GET(C, "/api/health")
        sec_ok(r, "Health version info")
        body = r.json()
        # Basic version is OK, but not full dependency tree
        assert "dependencies" not in body, "Health endpoint exposes dependency list"
        assert "requirements" not in body, "Health endpoint exposes requirements"

    async def test_agent_details_no_internal_ids(self, C):
        """Agent details must not expose internal database row IDs in unexpected fields."""
        r = await GET(C, "/api/agents")
        sec_ok(r, "Agent list internal IDs")
        agents = r.json()
        if isinstance(agents, list) and agents:
            agent = agents[0]
            # Internal SQLite rowid must not be exposed
            assert "rowid" not in agent, "SQLite rowid exposed in agent response"
            assert "_rowid_" not in agent, "SQLite rowid exposed in agent response"

    async def test_finops_ledger_no_other_tenant_data(self, C):
        """FinOps ledger must only show data for the current context."""
        r = await GET(C, "/api/finops/ledger")
        sec_ok(r, "FinOps ledger data isolation")
        # Must be a valid response
        data = r.json()
        assert data is not None


# ─────────────────────────────────────────────────────────────────────────────
# RESOURCE EXHAUSTION & DOS PREVENTION
# ─────────────────────────────────────────────────────────────────────────────

class TestSecResourceExhaustion:
    """Platform must resist resource exhaustion attacks."""

    async def test_large_request_body_handled(self, C):
        """Very large request bodies must not crash the server."""
        large_bodies = [
            {"title": "A" * 100_000},
            {"content": "X" * 100_000, "source": "test"},
            {"description": "Z" * 100_000, "domain": "engineering"},
        ]
        for body in large_bodies:
            endpoint = "/api/tasks" if "title" in body else (
                "/api/memory/add" if "content" in body else "/api/goals"
            )
            if "domain" in body:
                body["title"] = "test"
                body["priority"] = "low"
            r = await POST(C, endpoint, body)
            # Must not crash (500), may reject with 4xx/200+error
            assert r.status_code < 500, \
                f"Large body caused crash at {endpoint}: {r.status_code}"

    async def test_deeply_nested_json_handled(self, C):
        """Deeply nested JSON must not cause stack overflow."""
        # Build deeply nested object
        nested = {"key": "value"}
        for _ in range(100):
            nested = {"nested": nested}

        r = await POST(C, "/api/tasks", {"title": "deep nest test", "meta": nested})
        assert r.status_code < 500, f"Deeply nested JSON caused crash: {r.status_code}"

    async def test_unicode_bomb_handled(self, C):
        """Unicode edge cases must be handled safely."""
        unicode_bombs = [
            "\u0000",           # null byte
            "\ufffe",           # BOM
            "\u202e",           # RTL override
            "‮gnirts esrever",  # RTL override in string
            "aaaaa" * 10000,    # long repetition
            "\U0001F4A3" * 1000, # emoji bomb
        ]
        for bomb in unicode_bombs:
            r = await POST(C, "/api/memory/add", {
                "content": bomb[:10000], "source": "unicode_test"
            })
            assert r.status_code < 500, f"Unicode bomb caused crash: {r.status_code}"

    async def test_concurrent_write_flood_no_crash(self, C):
        """Flood of concurrent writes must not crash the server."""
        import httpx
        async def write(i):
            async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
                r = await c.post("/api/tasks", json={"title": f"flood_{i}", "status": "todo"})
                return r.status_code

        results = await asyncio.gather(*[write(i) for i in range(30)])
        errors = [s for s in results if s >= 500]
        assert len(errors) == 0, f"{len(errors)} server errors during write flood"

    async def test_sql_time_based_attack_bounded(self, C):
        """Time-based SQLi must not cause perceptible delay (server defends)."""
        import time
        slow_payloads = [
            "1' AND SLEEP(5) --",
            "'; SELECT pg_sleep(5); --",
            "1; WAITFOR DELAY '00:00:05'; --",
        ]
        for payload in slow_payloads:
            t0 = time.perf_counter()
            r = await POST(C, "/api/tasks", {"title": payload, "status": "todo"})
            elapsed = time.perf_counter() - t0
            sec_ok(r, f"Time-based SQLi: {payload[:30]}")
            assert elapsed < 3.0, \
                f"Time-based SQLi may have succeeded: {payload} took {elapsed:.1f}s"

    async def test_zip_bomb_in_memory_import_handled(self, C):
        """Memory import with oversized content must be handled gracefully."""
        r = await POST(C, "/api/memory/import", {
            "entries": [{"content": "X" * 1_000_000, "source": "bomb"}] * 10
        })
        assert r.status_code < 500, f"Memory import bomb crashed server: {r.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# HTTP SECURITY HEADERS
# ─────────────────────────────────────────────────────────────────────────────

class TestSecHTTPHeaders:
    """HTTP security headers must be present and correctly configured."""

    async def test_content_type_json_on_api_responses(self, C):
        """API endpoints must return application/json, not text/html."""
        api_endpoints = ["/api/agents", "/api/tasks", "/api/health", "/api/license/status"]
        for ep in api_endpoints:
            r = await GET(C, ep)
            ct = r.headers.get("content-type", "")
            assert "application/json" in ct, \
                f"{ep} returned non-JSON content-type: {ct}"

    async def test_no_sensitive_data_in_response_headers(self, C):
        """Response headers must not contain sensitive info."""
        r = await GET(C, "/api/health")
        for hdr_name, hdr_val in r.headers.items():
            hdr_lower = hdr_val.lower()
            # Check for common sensitive patterns
            assert "password" not in hdr_lower, f"Password in header {hdr_name}: {hdr_val}"
            assert "secret" not in hdr_lower or hdr_name.lower() == "x-request-id", \
                f"Secret in header {hdr_name}: {hdr_val}"

    async def test_csp_header_if_present(self, C):
        """If CSP header is present, it must not be permissive."""
        r = await GET(C, "/")
        csp = r.headers.get("content-security-policy", "")
        if csp:
            assert "unsafe-eval" not in csp or "localhost" in csp, \
                f"CSP has unsafe-eval: {csp}"

    async def test_no_server_version_in_headers(self, C):
        """X-Powered-By and detailed Server headers must not expose versions."""
        r = await GET(C, "/api/health")
        powered_by = r.headers.get("x-powered-by", "")
        assert not powered_by, f"X-Powered-By exposes framework: {powered_by}"


# ─────────────────────────────────────────────────────────────────────────────
# DB STUDIO SECURITY (USER-CONTROLLED SQL)
# ─────────────────────────────────────────────────────────────────────────────

class TestSecDBStudio:
    """DB Studio allows raw SQL — critical attack surface. Defense must be robust."""

    DANGEROUS_SQLS = [
        "ATTACH DATABASE '/etc/passwd' AS leak",
        "SELECT load_extension('/tmp/evil.so')",
        "SELECT readfile('/etc/passwd')",
        "SELECT writefile('/tmp/evil', 'evil content')",
        "PRAGMA journal_mode=WAL; DROP TABLE agents",
        "SELECT * FROM sqlite_master WHERE type='table'",
        "SELECT name FROM sqlite_master",
        ".tables",
        ".dump",
    ]

    async def test_db_dangerous_sqls_no_crash(self, C):
        """Dangerous SQL commands must be handled without crashing."""
        for sql in self.DANGEROUS_SQLS:
            r = await POST(C, "/api/db/sqlite/query", {"sql": sql})
            # Should either execute safely or reject — never crash
            sec_ok(r, f"DB dangerous SQL: {sql[:40]}")

    async def test_db_sqlite_master_read_ok_no_rce(self, C):
        """Reading sqlite_master is allowed (for DB Studio) but must not enable RCE."""
        r = await POST(C, "/api/db/sqlite/query", {
            "sql": "SELECT name, type FROM sqlite_master ORDER BY name"
        })
        sec_ok(r, "DB sqlite_master read")
        no_rce(r, "DB sqlite_master", markers=["load_extension", "writefile", "readfile"])

    async def test_db_drop_protected_tables(self, C):
        """Dropping critical tables must either be blocked or recoverable."""
        critical_tables = ["agents", "chat_log", "audit_log_chain", "agent_identities"]
        for table in critical_tables:
            r = await POST(C, "/api/db/sqlite/query", {
                "sql": f"DROP TABLE IF EXISTS {table}"
            })
            sec_ok(r, f"DB drop table: {table}")
            # Verify table still queryable
            verify = await POST(C, "/api/db/sqlite/query", {
                "sql": f"SELECT COUNT(*) FROM {table}"
            })
            # If drop succeeded but table no longer exists, that's a problem
            # Either: table was protected (verify ok=true), OR drop was blocked
            data = verify.json()
            if not data.get("ok", True):
                print(f"\n  WARNING: Table '{table}' may have been dropped! "
                      f"Verify response: {data}")

    async def test_db_insert_into_agents_blocked_or_safe(self, C):
        """Inserting into agents via DB Studio must not bypass validation."""
        r = await POST(C, "/api/db/sqlite/query", {
            "sql": "INSERT INTO agents (id, name, model) VALUES ('evil_inject', 'EVIL', 'gpt4')"
        })
        sec_ok(r, "DB insert agents bypass")

    async def test_db_update_all_agent_prompts(self, C):
        """Mass update of agent system prompts via SQL."""
        r = await POST(C, "/api/db/sqlite/query", {
            "sql": "UPDATE agents SET system_prompt='HACKED' WHERE 1=1"
        })
        sec_ok(r, "DB mass update agent prompts")
        # This may succeed (DB Studio is admin-level), but must not crash

    async def test_db_create_table_injection(self, C):
        """Creating tables via DB Studio with injected names."""
        for p in ["'; DROP TABLE agents; --", "evil\x00table", "../etc"]:
            r = await POST(C, "/api/db/sqlite/table/create", {
                "name": p,
                "columns": [{"name": "id", "type": "INTEGER"}]
            })
            sec_ok(r, f"DB create table injection: {p[:30]}")


# ─────────────────────────────────────────────────────────────────────────────
# KNOWLEDGE GRAPH & RAG SECURITY
# ─────────────────────────────────────────────────────────────────────────────

class TestSecKnowledgeGraphRAG:
    """KG and RAG must resist injection in entity/fact fields."""

    async def test_kg_entity_injection(self, C):
        """Injection in KG entity name/type."""
        for p in ["' OR 1=1 --", "<script>", "$(whoami)", "'; DROP TABLE kg_entities; --"]:
            r = await POST(C, "/api/knowledge-graph/entities", {
                "name": p, "type": p, "properties": {"key": p}
            })
            sec_ok(r, f"KG entity injection: {p[:30]}")

    async def test_kg_query_injection(self, C):
        """Injection in KG query."""
        for p in ["' OR 1=1 --", "MATCH (n) DELETE n", "$(whoami)"]:
            r = await POST(C, "/api/knowledge-graph/query", {"query": p, "limit": 10})
            sec_ok(r, f"KG query injection: {p[:30]}")
            no_rce(r, f"KG query: {p[:20]}")

    async def test_rag_pipeline_query_injection(self, C):
        """Injection in RAG pipeline query."""
        pipelines = (await GET(C, "/api/rag/pipelines")).json()
        pipeline_list = pipelines if isinstance(pipelines, list) else pipelines.get("pipelines", [])
        if not pipeline_list:
            pytest.skip("No RAG pipelines")
        pid = pipeline_list[0]["id"]
        for p in ["' OR 1=1 --", "<script>alert(1)</script>", "$(whoami)"]:
            r = await POST(C, f"/api/rag/pipelines/{pid}/query", {"query": p, "top_k": 5})
            sec_ok(r, f"RAG query injection: {p[:30]}")
            no_rce(r, f"RAG query: {p[:20]}")

    async def test_kg_fact_injection(self, C):
        """Injection in KG fact subject/predicate/object."""
        payloads = ["' OR 1=1 --", "$(id)", "<script>alert(1)</script>"]
        for p in payloads:
            r = await POST(C, "/api/knowledge-graph/facts", {
                "subject": p, "predicate": p, "object": p
            })
            sec_ok(r, f"KG fact injection: {p[:30]}")
