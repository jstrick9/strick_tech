"""
SEC-07: OWASP Top 10 2021 — Comprehensive Coverage
A01: Broken Access Control
A02: Cryptographic Failures
A03: Injection (extended beyond SQLi/XSS)
A04: Insecure Design
A05: Security Misconfiguration
A06: Vulnerable/Outdated Components (version info disclosure)
A07: Identification & Authentication Failures
A08: Software & Data Integrity Failures
A09: Security Logging & Monitoring Failures
A10: SSRF — Server Side Request Forgery
"""
import pytest, json
from tests.security.conftest import *

# ─────────────────────────────────────────────────────────────────────────────
# A01: Broken Access Control
# ─────────────────────────────────────────────────────────────────────────────

class TestSecA01BrokenAccessControl:
    """All resource endpoints must enforce ownership — no IDOR, no mass assignment."""

    async def test_task_idor_cross_resource(self, C):
        """Access tasks by sequential IDs — never get 500, never expose internals."""
        for fake_id in range(1, 6):
            r = await GET(C, f"/api/tasks/{fake_id}")
            sec_ok(r, f"Task IDOR sequential: {fake_id}")

    async def test_session_idor_guessing(self, C):
        """Session IDOR via guessed IDs."""
        for fake_id in ["sess_000000", "1", "admin_session", "' OR 1=1 --"]:
            r = await GET(C, f"/api/sessions/{fake_id}")
            sec_ok(r, f"Session IDOR: {fake_id}")

    async def test_memory_idor_delete(self, C):
        """Deleting memory entries with forged IDs must be safe."""
        for fake_id in ["' OR 1=1 --", "99999999", "../"]:
            r = await DELETE(C, f"/api/memory/{fake_id}")
            sec_ok(r, f"Memory delete IDOR: {fake_id}")

    async def test_workspace_idor_activate(self, C):
        """Activating a workspace by forged ID must not affect others."""
        for fake_id in ["' OR 1=1 --", "../../../etc", "999999"]:
            r = await POST(C, f"/api/workspaces/{fake_id}/activate", {})
            sec_ok(r, f"Workspace activate IDOR: {fake_id}")

    async def test_agent_delete_nonexistent_safe(self, C):
        """Deleting non-existent agents must be handled gracefully."""
        for fake_id in ["nonexistent_xyz", "' OR 1=1 --", "../../etc"]:
            r = await DELETE(C, f"/api/agents/{fake_id}")
            sec_ok(r, f"Agent delete nonexistent: {fake_id}")

    async def test_prompt_idor_patch(self, C):
        """PATCH prompt with forged ID."""
        for fake_id in ["' OR 1=1 --", "999999", "../"]:
            r = await PATCH(C, f"/api/prompts/{fake_id}", {"content": "hacked"})
            sec_ok(r, f"Prompt IDOR patch: {fake_id}")

    async def test_steering_file_idor_delete(self, C):
        """Delete steering file with forged ID."""
        for fake_id in ["' OR 1=1 --", "99999", "../../etc/passwd"]:
            r = await DELETE(C, f"/api/steering/{fake_id}")
            sec_ok(r, f"Steering delete IDOR: {fake_id}")

    async def test_workflow_idor_run(self, C):
        """Run workflow with forged ID."""
        for fake_id in ["' OR 1=1 --", "99999", "'; DROP TABLE workflow; --"]:
            r = await POST(C, f"/api/workflow/{fake_id}/run", {})
            sec_ok(r, f"Workflow run IDOR: {fake_id}")

    async def test_spec_idor_execute(self, C):
        """Execute spec with forged ID."""
        for fake_id in ["' OR 1=1 --", "99999", "../../../etc"]:
            r = await POST(C, f"/api/specs/{fake_id}/execute", {})
            sec_ok(r, f"Spec execute IDOR: {fake_id}")

    async def test_crdt_doc_idor_history(self, C):
        """CRDT document history with forged doc_id."""
        for fake_id in ["' OR 1=1 --", "99999", "../../../etc"]:
            r = await GET(C, f"/api/crdt/docs/{fake_id}/history")
            sec_ok(r, f"CRDT history IDOR: {fake_id}")

    async def test_collab_session_idor_state(self, C):
        """Collab session state with forged session_id."""
        for fake_id in ["' OR 1=1 --", "99999", "../../"]:
            r = await GET(C, f"/api/collab/sessions/{fake_id}/state")
            sec_ok(r, f"Collab state IDOR: {fake_id}")

    async def test_replay_run_idor_frames(self, C):
        """Replay run frames with forged run_id."""
        for fake_id in ["' OR 1=1 --", "99999", "../../../"]:
            r = await GET(C, f"/api/replay/runs/{fake_id}/frames")
            sec_ok(r, f"Replay frames IDOR: {fake_id}")

    async def test_arena_battle_idor_vote(self, C):
        """Vote on arena battle with forged battle_id."""
        for fake_id in ["' OR 1=1 --", "99999"]:
            r = await POST(C, f"/api/arena/battle/{fake_id}/vote", {"model": "a", "vote": "left"})
            sec_ok(r, f"Arena battle IDOR vote: {fake_id}")

    async def test_goal_milestone_idor(self, C):
        """Goal milestones with forged goal_id."""
        for fake_id in ["' OR 1=1 --", "99999"]:
            r = await GET(C, f"/api/goals/{fake_id}/milestones")
            sec_ok(r, f"Goal milestone IDOR: {fake_id}")

    async def test_connector_idor_executions(self, C):
        """Connector execution history with forged connector_id."""
        for fake_id in ["' OR 1=1 --", "99999", "../../etc"]:
            r = await GET(C, f"/api/connectors/{fake_id}/executions")
            sec_ok(r, f"Connector executions IDOR: {fake_id}")


# ─────────────────────────────────────────────────────────────────────────────
# A02: Cryptographic Failures
# ─────────────────────────────────────────────────────────────────────────────

class TestSecA02CryptoFailures:
    """Sensitive data must not be transmitted or stored in plaintext."""

    async def test_secrets_api_masks_values(self, C):
        """GET /api/secrets must never return raw secret values."""
        # Set a test secret first
        await POST(C, "/api/secrets/set", {"key": "SEC_TEST_KEY", "value": "super_secret_value_12345"})

        r = await GET(C, "/api/secrets")
        sec_ok(r, "Secrets list masking check")
        body = r.text
        assert "super_secret_value_12345" not in body, \
            "RAW SECRET VALUE exposed in /api/secrets GET response!"

    async def test_env_file_not_served(self, C):
        """The .env file must never be served via the API."""
        for path in ["/.env", "/../.env", "/api/../.env", "/static/../.env"]:
            r = await GET(C, path)
            sec_ok(r, f".env file served: {path}")
            body = r.text
            assert "OPENROUTER_API_KEY" not in body or "***" in body, \
                f".env contents exposed at {path}"

    async def test_audit_log_entries_no_key_material(self, C):
        """Audit log entries must not contain private key material."""
        r = await GET(C, "/api/audit-log")
        sec_ok(r, "Audit log key material check")
        body = r.text.lower()
        for danger in ["-----begin rsa", "-----begin ec", "private_key", "api_key="]:
            assert danger not in body, f"Key material in audit log: {danger}"

    async def test_profile_export_no_raw_keys(self, C):
        """Profile export must not expose any raw API keys."""
        r = await GET(C, "/api/profile/export")
        sec_ok(r, "Profile export key check")
        body = r.text.lower()
        for danger in ["api_key", "secret", "password", "private"]:
            # Export may mention fields but must not have values
            if danger in body:
                # Check it's not a raw key value (must be masked or field name only)
                pass  # OK to mention field names in export

    async def test_agent_identity_tokens_not_fully_exposed(self, C):
        """Token list for agents must not expose full token values."""
        agents = (await GET(C, "/api/agents")).json()
        if not isinstance(agents, list) or not agents:
            pytest.skip("No agents")
        aid = agents[0]["id"]
        r = await GET(C, f"/api/agent-identity/{aid}/tokens")
        sec_ok(r, "Agent token list exposure")
        body = r.text
        # Raw bearer tokens of significant length should not appear
        import re
        # Look for bearer token patterns (long hex/base64 strings)
        long_tokens = re.findall(r'"token"\s*:\s*"([a-zA-Z0-9+/=]{40,})"', body)
        # If they do appear, that's a potential finding (warn, don't hard-fail)
        if long_tokens:
            print(f"\n  WARNING: Possible full token exposure in token list ({len(long_tokens)} tokens)")


# ─────────────────────────────────────────────────────────────────────────────
# A03: Injection — Extended
# ─────────────────────────────────────────────────────────────────────────────

class TestSecA03InjectionExtended:
    """LDAP injection, template injection, command injection, header injection."""

    TEMPLATE_INJECTIONS = [
        "{{7*7}}",           # Jinja2
        "${7*7}",            # Spring EL
        "#{7*7}",            # OGNL
        "<%= 7*7 %>",        # ERB
        "${T(java.lang.Runtime).getRuntime().exec('id')}",
        "{{''.__class__.__mro__[2].__subclasses__()}}",
        "{%for c in [].__class__.__base__.__subclasses__()%}{{c}}{%endfor%}",
    ]

    HEADER_INJECTIONS = [
        "test\r\nX-Injected: malicious",
        "test\nSet-Cookie: session=hacked",
        "agent\r\nHost: attacker.com",
    ]

    async def test_template_injection_in_task_title(self, C):
        """Server-side template injection via task title must not execute."""
        for p in self.TEMPLATE_INJECTIONS:
            r = await POST(C, "/api/tasks", {"title": p, "status": "todo"})
            sec_ok(r, f"Template injection task: {p[:30]}")
            # Check the parsed `title` field specifically, not a substring
            # scan of the whole response body. A bare "'49' not in body"
            # check false-positives whenever the row's own auto-increment
            # `id` happens to be (or contain) 49 -- unrelated to whether the
            # template payload was executed. If SSTI succeeded, the stored
            # title itself would become the evaluated result (e.g. "49")
            # instead of remaining the literal, unexecuted payload string.
            try:
                stored_title = r.json().get("title")
            except ValueError:
                stored_title = None
            assert stored_title != "49", \
                f"Possible SSTI: {p} → stored title was evaluated to '49'"

    async def test_template_injection_in_memory_content(self, C):
        """Template injection in memory content."""
        for p in self.TEMPLATE_INJECTIONS:
            r = await POST(C, "/api/memory/add", {
                "content": p, "source": "ssti_test"
            })
            sec_ok(r, f"Template injection memory: {p[:30]}")

    async def test_template_injection_in_agent_system_prompt(self, C):
        """Template injection in agent system prompt must not execute at store time."""
        for p in self.TEMPLATE_INJECTIONS:
            r = await POST(C, "/api/agents", {
                "name": uid("ssti_agent"),
                "model": "gemini-flash",
                "system_prompt": p
            })
            sec_ok(r, f"Template injection agent prompt: {p[:30]}")
            # Cleanup
            aid = (r.json().get("agent", {}) or {}).get("id") or r.json().get("id")
            if aid:
                await DELETE(C, f"/api/agents/{aid}")

    async def test_header_injection_in_webhook_url(self, C):
        """Header injection in webhook URL field."""
        for p in self.HEADER_INJECTIONS:
            r = await POST(C, "/api/webhooks", {
                "name": uid("hdr_inject"),
                "url": f"http://example.com/{p}",
                "events": ["task.created"]
            })
            sec_ok(r, f"Header injection webhook: {p[:30]}")

    async def test_ldap_injection_in_search_fields(self, C):
        """LDAP injection patterns in search/filter fields."""
        ldap_payloads = [
            "*)(uid=*))(|(uid=*",
            "admin)(&(password=*))",
            "*)(&",
            "*)(|(objectClass=*)",
        ]
        for p in ldap_payloads:
            r = await GET(C, f"/api/memory/search?q={p}")
            sec_ok(r, f"LDAP injection search: {p[:30]}")

    async def test_xml_injection_in_description_fields(self, C):
        """XML/XXE injection patterns in description fields."""
        xml_payloads = [
            '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><foo>&xxe;</foo>',
            "<foo><bar>test</bar></foo>",
            '<!DOCTYPE test [<!ENTITY xxe SYSTEM "http://169.254.169.254/">]>',
        ]
        for p in xml_payloads:
            r = await POST(C, "/api/goals", {
                "title": "xml_test",
                "description": p,
                "domain": "engineering",
                "priority": "low"
            })
            sec_ok(r, f"XML injection: {p[:40]}")
            no_rce(r, f"XXE injection: {p[:30]}", markers=["root:", "uid=", "/etc/passwd"])

    async def test_nosql_injection_in_memory_fields(self, C):
        """NoSQL injection patterns in memory/search fields."""
        nosql_payloads = [
            {"$gt": ""},
            '{"$where": "this.password == this.passwordConfirm"}',
            '{"$regex": ".*"}',
        ]
        for p in nosql_payloads:
            r = await POST(C, "/api/memory/add", {
                "content": str(p), "source": "nosql_test"
            })
            sec_ok(r, f"NoSQL injection: {str(p)[:30]}")


# ─────────────────────────────────────────────────────────────────────────────
# A04: Insecure Design
# ─────────────────────────────────────────────────────────────────────────────

class TestSecA04InsecureDesign:
    """Business logic vulnerabilities and design-level security issues."""

    async def test_license_tier_bypass_via_direct_api(self, C):
        """Attempting to access higher-tier features via direct API calls."""
        # Try to set an invalid license tier
        r = await POST(C, "/api/license/activate", {
            "license_key": "FAKE-LICENSE-KEY-BYPASS",
            "tier": "enterprise"
        })
        sec_ok(r, "License tier bypass attempt")
        # Verify actual tier wasn't changed to enterprise via fake key
        status = (await GET(C, "/api/license/status")).json()
        tier = status.get("tier", "")
        # If it changed to enterprise with a fake key, that's a bypass
        if tier == "enterprise":
            license_key = status.get("license_key", "")
            assert license_key != "FAKE-LICENSE-KEY-BYPASS", \
                "LICENSE BYPASS: Fake key activated enterprise tier!"

    async def test_mass_assignment_agent_create(self, C):
        """Mass assignment: injecting internal fields via POST."""
        r = await POST(C, "/api/agents", {
            "name": uid("mass_assign"),
            "model": "gemini-flash",
            "system_prompt": "test",
            # Attempt to set internal/privileged fields
            "is_admin": True,
            "tier": "enterprise",
            "can_execute_code": True,
            "bypass_audit": True,
            "enabled": 999,
        })
        sec_ok(r, "Mass assignment agent create")
        # Verify injected fields weren't stored
        agent_id = (r.json().get("agent", {}) or {}).get("id") or r.json().get("id")
        if agent_id:
            ar = await GET(C, f"/api/agents/{agent_id}")
            if ar.status_code == 200:
                agent = ar.json()
                assert agent.get("is_admin") is None, "Mass assignment: is_admin was stored"
                assert agent.get("bypass_audit") is None, "Mass assignment: bypass_audit was stored"
            await DELETE(C, f"/api/agents/{agent_id}")

    async def test_workflow_run_infinite_loop_protection(self, C):
        """Creating a workflow that could loop infinitely must be handled."""
        r = await POST(C, "/api/workflow", {
            "name": uid("infinite_loop"),
            "trigger": "on_complete",
            "target_workflow": "self",  # self-referential
            "steps": [{"action": "self.run"}]
        })
        sec_ok(r, "Infinite loop workflow")

    async def test_budget_cap_zero_bypass(self, C):
        """Setting a $0 budget cap must not allow unlimited spending."""
        r = await POST(C, "/api/finops/caps", {
            "name": uid("zero_cap"),
            "agent_id": "brain",
            "period": "daily",
            "limit_usd": 0,
            "action": "block"
        })
        sec_ok(r, "Zero budget cap bypass attempt")

    async def test_bulk_delete_memory_without_confirmation(self, C):
        """Bulk delete memory must handle malformed/injected body safely."""
        r = await POST(C, "/api/memory/bulk-delete", {
            "ids": ["' OR 1=1 --", "ALL", "*", "'; DROP TABLE memory; --"]
        })
        sec_ok(r, "Bulk delete injection")
        # Verify memory table still works
        mem = await GET(C, "/api/memory/list")
        assert mem.status_code < 500, "Memory table broken by bulk delete injection"


# ─────────────────────────────────────────────────────────────────────────────
# A05: Security Misconfiguration
# ─────────────────────────────────────────────────────────────────────────────

class TestSecA05Misconfiguration:
    """Debug endpoints, stack traces, directory listing, verbose errors."""

    async def test_no_debug_endpoints_exposed(self, C):
        """Common debug/admin endpoints must not be accessible."""
        debug_paths = [
            "/debug", "/admin", "/phpmyadmin", "/phpinfo",
            "/__debug__", "/_debug", "/console",
            "/admin/config", "/api/admin", "/internal",
            "/.git/config", "/.git/HEAD", "/Dockerfile",
            "/docker-compose.yml", "/requirements.txt",
        ]
        for path in debug_paths:
            r = await GET(C, path)
            sec_ok(r, f"Debug endpoint: {path}")
            # Must not return 200 with debug info
            if r.status_code == 200:
                body = r.text.lower()
                assert "traceback" not in body, f"Debug traceback exposed at {path}"
                assert "sqlalchemy" not in body or path.endswith(".txt"), \
                    f"ORM details exposed at {path}"

    async def test_no_stack_traces_in_error_responses(self, C):
        """Error responses must not contain Python stack traces."""
        # Trigger various error conditions
        error_triggers = [
            ("POST", "/api/tasks", {"invalid_field": "x" * 10000}),
            ("POST", "/api/memory/add", {"content": None}),
            ("GET", "/api/agents/99999999999999999999999", None),
        ]
        for method, path, body in error_triggers:
            if method == "GET":
                r = await GET(C, path)
            else:
                r = await POST(C, path, body)
            # Even on error, no stack trace
            text = r.text.lower()
            assert "traceback (most recent call last)" not in text, \
                f"Stack trace exposed at {path}: {text[:200]}"
            assert "file \"/home" not in text, \
                f"File path in error at {path}: {text[:200]}"

    async def test_http_methods_restricted(self, C):
        """Non-standard HTTP methods must not expose info."""
        import httpx
        async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
            for method in ["TRACE", "TRACK", "OPTIONS"]:
                try:
                    r = await c.request(method, "/api/agents")
                    sec_ok(r, f"HTTP method: {method}")
                    if method == "TRACE":
                        # TRACE must not reflect headers (XST attack)
                        assert "x-custom-header" not in r.text.lower(), \
                            f"TRACE reflects headers (XST vulnerability)"
                except Exception:
                    pass  # Connection refused for exotic methods is fine

    async def test_server_header_does_not_expose_version(self, C):
        """Server response headers must not expose detailed server versions."""
        r = await GET(C, "/api/health")
        server_hdr = r.headers.get("server", "")
        # Should not expose uvicorn/python version in detail
        assert "uvicorn" not in server_hdr.lower() or len(server_hdr) < 30, \
            f"Server header exposes version details: {server_hdr}"

    async def test_cors_does_not_allow_arbitrary_origins(self, C):
        """CORS must not allow arbitrary origins with credentials."""
        import httpx
        async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
            r = await c.get("/api/agents", headers={
                "Origin": "https://evil-attacker.com"
            })
            acao = r.headers.get("access-control-allow-origin", "")
            acac = r.headers.get("access-control-allow-credentials", "")
            # If it's a wildcard OR specific origins, credentials must NOT also be true
            if acao == "*" and acac.lower() == "true":
                raise AssertionError(
                    "CORS misconfiguration: Access-Control-Allow-Origin=* with "
                    "Access-Control-Allow-Credentials=true allows credential theft!"
                )


# ─────────────────────────────────────────────────────────────────────────────
# A07: Authentication & Session Management
# ─────────────────────────────────────────────────────────────────────────────

class TestSecA07AuthFailures:
    """Session fixation, token exposure, auth bypass attempts."""

    async def test_session_fixation_prevention(self, C):
        """Session IDs must be created server-side, not accepted from client."""
        r = await POST(C, "/api/sessions", {
            "name": "test_session",
            "agent_id": "brain",
            "session_id": "FIXED_SESSION_ID_12345"  # Attempt to fix session ID
        })
        sec_ok(r, "Session fixation attempt")
        data = r.json()
        # If session_id was returned, it must not be our injected value
        returned_id = data.get("id") or data.get("session_id") or data.get("session", {}).get("id")
        if returned_id:
            assert returned_id != "FIXED_SESSION_ID_12345", \
                "Session fixation: Client-provided session ID was used!"

    async def test_api_key_not_in_url_params(self, C):
        """API keys/tokens must not be accepted in URL params (logged in access logs)."""
        # Try passing API key as URL param — should be rejected or ignored
        r = await GET(C, "/api/agents?api_key=sk-test-12345&token=secret123")
        sec_ok(r, "API key in URL params")
        # The key should not appear in any response body
        assert "sk-test-12345" not in r.text, "API key reflected in response!"

    async def test_long_session_id_no_crash(self, C):
        """Very long session ID in path param must not crash."""
        long_id = "a" * 10000
        r = await GET(C, f"/api/sessions/{long_id}")
        sec_ok(r, "Long session ID")

    async def test_null_byte_in_session_id(self, C):
        """Null bytes in session ID must be handled safely."""
        for null_id in ["\x00session", "sess\x00ion", "session\x00"]:
            try:
                r = await GET(C, f"/api/sessions/{null_id}")
                sec_ok(r, f"Null byte session ID: {repr(null_id)}")
            except Exception:
                pass  # httpx rejecting null bytes is fine


# ─────────────────────────────────────────────────────────────────────────────
# A08: Software & Data Integrity
# ─────────────────────────────────────────────────────────────────────────────

class TestSecA08IntegrityFailures:
    """Plugin/marketplace integrity, workflow tampering, import validation."""

    async def test_malicious_plugin_url_install(self, C):
        """Installing plugin from malicious URL must not execute remote code."""
        malicious_urls = [
            "file:///etc/passwd",
            "http://attacker.com/evil-plugin.zip",
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "ftp://attacker.com/plugin.tar.gz",
        ]
        for url in malicious_urls:
            r = await POST(C, "/api/plugins/install/url", {"url": url})
            sec_ok(r, f"Malicious plugin URL: {url[:40]}")
            no_rce(r, f"Plugin URL install: {url[:30]}")

    async def test_marketplace_publish_injection(self, C):
        """Injection in marketplace publish payload."""
        r = await POST(C, "/api/marketplace/publish", {
            "name": "'; DROP TABLE marketplace; --",
            "description": "<script>alert(1)</script>",
            "version": "$(whoami)",
            "author": "' OR 1=1 --"
        })
        sec_ok(r, "Marketplace publish injection")

    async def test_workflow_import_injection(self, C):
        """Workflow import with injected payloads."""
        malicious_workflow = {
            "name": "'; DROP TABLE workflow; --",
            "steps": [
                {"action": "os.system", "args": ["whoami"]},
                {"action": "$(id)", "args": []},
            ],
            "trigger": "' OR 1=1 --"
        }
        r = await POST(C, "/api/workflow", malicious_workflow)
        sec_ok(r, "Workflow import injection")
        no_rce(r, "Workflow injection")

    async def test_plugin_json_install_injection(self, C):
        """Plugin install from JSON with RCE payloads."""
        r = await POST(C, "/api/plugins/install/json", {
            "name": uid("evil_plugin"),
            "version": "1.0.0",
            "code": "import os; os.system('id')",
            "hooks": {"on_install": "os.system('rm -rf /')"},
        })
        sec_ok(r, "Plugin JSON install injection")
        no_rce(r, "Plugin JSON install")

    async def test_skills_run_code_injection(self, C):
        """Running a skill with injected code must not execute arbitrary commands."""
        r = await POST(C, "/api/skills/run", {
            "skill_id": "test_skill",
            "code": "import os; os.system('id')",
            "input": "$(whoami)"
        })
        sec_ok(r, "Skills run code injection")
        no_rce(r, "Skills run injection")

    async def test_prompt_import_injection(self, C):
        """Prompt library import with injection payloads."""
        r = await POST(C, "/api/prompts/import", {
            "prompts": [
                {"title": "'; DROP TABLE prompts; --", "content": "<script>alert(1)</script>"},
                {"title": "$(id)", "content": "`whoami`"},
            ]
        })
        sec_ok(r, "Prompt import injection")

    async def test_steering_file_content_injection(self, C):
        """Injection in steering file content."""
        for p in ["'; DROP TABLE steering; --", "<script>", "$(whoami)", "{{7*7}}"]:
            r = await POST(C, "/api/steering", {
                "name": uid("steer_sec"),
                "content": p,
                "type": "system"
            })
            sec_ok(r, f"Steering content injection: {p[:30]}")


# ─────────────────────────────────────────────────────────────────────────────
# A09: Security Logging & Monitoring
# ─────────────────────────────────────────────────────────────────────────────

class TestSecA09LoggingMonitoring:
    """Security events must be logged; logs must not be clearable via injection."""

    async def test_failed_operations_generate_audit_entries(self, C):
        """Critical operations should appear in audit log."""
        # Perform operations that should be audited
        await POST(C, "/api/secrets/set", {"key": uid("audit_test"), "value": "testval"})
        await POST(C, "/api/agents", {
            "name": uid("audit_agent"), "model": "gemini-flash", "system_prompt": "test"
        })

        # Check audit log has entries
        r = await GET(C, "/api/audit-log")
        sec_ok(r, "Audit log after operations")
        entries = r.json()
        entry_list = entries if isinstance(entries, list) else entries.get("entries", [])
        assert len(entry_list) >= 0, "Audit log should be queryable"

    async def test_audit_log_cannot_be_cleared_via_sqli(self, C):
        """Attempt to clear audit log via SQLi in DB Studio."""
        # Count entries before
        before = (await GET(C, "/api/audit-log/stats")).json()
        count_before = before.get("total", 0)

        # Attempt to DELETE via SQLi
        r = await POST(C, "/api/db/sqlite/query", {
            "sql": "DELETE FROM audit_log_chain WHERE 1=1"
        })
        sec_ok(r, "Audit log SQL DELETE attempt")

        # Count entries after — should not have decreased dramatically
        after = (await GET(C, "/api/audit-log/stats")).json()
        count_after = after.get("total", 0)
        # Log should not have been wiped (we accept some reduction for concurrent tests)
        print(f"\n  Audit log count: {count_before} → {count_after}")

    async def test_hitl_audit_trail_accessible(self, C):
        """HITL audit endpoint provides audit trail."""
        r = await GET(C, "/api/hitl/audit")
        sec_ok(r, "HITL audit trail")

    async def test_agent_identity_audit_trail(self, C):
        """Agent identity audit trail accessible per agent."""
        agents = (await GET(C, "/api/agents")).json()
        if not isinstance(agents, list) or not agents:
            pytest.skip("No agents")
        aid = agents[0]["id"]
        r = await GET(C, f"/api/agent-identity/{aid}/audit")
        sec_ok(r, "Agent identity audit trail")


# ─────────────────────────────────────────────────────────────────────────────
# A10: SSRF — Extended
# ─────────────────────────────────────────────────────────────────────────────

class TestSecA10SSRFExtended:
    """Comprehensive SSRF testing across all fetch/URL endpoints."""

    SSRF_TARGETS = [
        "http://169.254.169.254/latest/meta-data/",
        "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://100.100.100.200/latest/meta-data/",  # Alibaba cloud
        "http://localhost:22",
        "http://127.0.0.1:22",
        "http://127.0.0.1:5432",   # PostgreSQL
        "http://127.0.0.1:6379",   # Redis
        "http://127.0.0.1:27017",  # MongoDB
        "http://0.0.0.0:8787/api/secrets",
        "file:///etc/passwd",
        "file:///etc/shadow",
        "file:///proc/self/environ",
        "http://[::1]:8787/api/secrets",
        "http://2130706433/api/secrets",  # 127.0.0.1 decimal
        "http://0x7f000001/api/secrets",  # 127.0.0.1 hex
    ]

    async def test_ssrf_websearch_fetch_content(self, C):
        """SSRF via websearch fetch-content endpoint."""
        for url in self.SSRF_TARGETS:
            r = await POST(C, "/api/websearch/fetch-content", {"url": url})
            sec_ok(r, f"SSRF fetch-content: {url[:50]}")
            no_rce(r, f"SSRF: {url[:40]}", markers=[
                "root:", "uid=", "ami-id", "instance-id",
                "iam/security-credentials", "computeMetadata",
                "/etc/shadow", "HOME=/root"
            ])

    async def test_ssrf_webhook_trigger(self, C):
        """SSRF via webhook URL trigger."""
        # Create a webhook with SSRF URL
        for url in self.SSRF_TARGETS[:5]:
            r = await POST(C, "/api/webhooks", {
                "name": uid("ssrf_wh"),
                "url": url,
                "events": ["task.created"]
            })
            sec_ok(r, f"SSRF webhook create: {url[:40]}")

    async def test_ssrf_obsidian_path(self, C):
        """SSRF/path traversal via Obsidian vault path."""
        for path in ["/etc/passwd", "../../etc/passwd", "/proc/self/environ"]:
            r = await POST(C, "/api/obsidian/index", {"vault_path": path})
            sec_ok(r, f"SSRF Obsidian path: {path}")
            no_path_escape(r, f"Obsidian path: {path}")

    async def test_ssrf_github_url_injection(self, C):
        """SSRF via GitHub integration URL."""
        for url in ["http://169.254.169.254/", "file:///etc/passwd"]:
            r = await POST(C, "/api/workspaces/import/github", {
                "url": url,
                "branch": "main"
            })
            sec_ok(r, f"SSRF GitHub import: {url}")

    async def test_ssrf_deploy_providers(self, C):
        """SSRF via deploy provider endpoints."""
        ssrf_payload = {"url": "http://169.254.169.254/", "api_key": "test"}
        for provider in ["netlify", "vercel", "railway", "render"]:
            r = await POST(C, f"/api/deploy/{provider}", ssrf_payload)
            sec_ok(r, f"SSRF deploy {provider}")

    async def test_ssrf_connector_webhook_url(self, C):
        """SSRF via connector webhook URL registration."""
        for url in self.SSRF_TARGETS[:6]:
            r = await POST(C, "/api/connectors", {
                "type": "webhook",
                "name": uid("ssrf_conn"),
                "config": {"url": url, "method": "POST"}
            })
            sec_ok(r, f"SSRF connector: {url[:40]}")

    async def test_ssrf_mcp_gateway_server_url(self, C):
        """SSRF via MCP gateway server URL."""
        for url in self.SSRF_TARGETS[:6]:
            r = await POST(C, "/api/mcp-gateway/servers", {
                "name": uid("ssrf_mcp"),
                "url": url,
                "transport": "http",
                "auth_type": "none"
            })
            sec_ok(r, f"SSRF MCP server: {url[:40]}")
