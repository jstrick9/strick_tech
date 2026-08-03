"""
Unit Tests — Web Search module review
(`tests/unit/test_57_websearch_module_review.py`)

Regression guards for real defects found during the Web Search review:

1. Web search returned ZERO results for every query while reporting
   {"ok": true}. Two independent causes, both verified live:
     • it scraped lite.duckduckgo.com with the User-Agent
       'Mozilla/5.0 AgenticOS/6.0', which that endpoint now answers with
       HTTP 403;
     • its regex matched a generic <a href>…</a>, which is not how DuckDuckGo
       marks up results — so even a 200 would have yielded navigation chrome.
   The documented instant-answers fallback does not cover ordinary queries
   either (empty AbstractText, zero RelatedTopics), so every path produced
   nothing and the endpoint still reported success.
2. Result URLs were DuckDuckGo /l/?uddg= redirect wrappers, not real targets.
3. escHtml() does not neutralise a dangerous URL scheme — `javascript:` URLs
   survived it intact and stayed live in an href. Every URL this pane renders
   comes from scraped third-party content.
4. Eight error paths (including an SSRF rejection) returned HTTP 200.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.routers.websearch import _clean_html_text, _is_ssrf_blocked_url, _unwrap_ddg_url

ROOT = Path(__file__).resolve().parents[2]
WEBSEARCH_PY = (ROOT / 'backend' / 'routers' / 'websearch.py').read_text(encoding='utf-8')
WEBSEARCH_JS = (ROOT / 'frontend' / 'js' / '44-websearch.js').read_text(encoding='utf-8')


def executable_source(src: str) -> str:
    """Strip comments AND docstrings, so assertions about REMOVED code are not
    satisfied by fix notes that deliberately quote the old values."""
    import ast
    import io
    import tokenize

    kept = [t for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type != tokenize.COMMENT]
    stripped = tokenize.untokenize(kept)
    doc_lines: set[int] = set()
    for node in ast.walk(ast.parse(stripped)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, 'body', [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                doc_lines.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
    return '\n'.join(ln for i, ln in enumerate(stripped.splitlines(), 1) if i not in doc_lines)


class TestSearchActuallyReturnsResults:
    """The scraper targeted an endpoint that 403s and markup that doesn't exist."""

    def test_uses_a_real_browser_user_agent(self):
        assert '_SEARCH_UA' in WEBSEARCH_PY
        assert 'Chrome/' in WEBSEARCH_PY
        # The UA that gets a 403 must be gone from the search path.
        code = executable_source(WEBSEARCH_PY)
        assert "'Mozilla/5.0 AgenticOS/6.0'" not in code.split('_fetch_page_text')[0]

    def test_targets_the_endpoint_that_serves_results(self):
        assert 'html.duckduckgo.com/html' in WEBSEARCH_PY

    def test_parses_the_markup_duckduckgo_emits(self):
        assert 'result__a' in WEBSEARCH_PY
        assert 'result__snippet' in WEBSEARCH_PY

    def test_generic_anchor_regex_is_gone(self):
        assert r'<a[^>]+href="(https?://[^"]+)"[^>]*>([^<]+)</a>' not in WEBSEARCH_PY


class TestRedirectUnwrapping:
    """DuckDuckGo wraps every result URL in /l/?uddg=<encoded>."""

    def test_unwraps_a_wrapped_url(self):
        wrapped = '//duckduckgo.com/l/?uddg=https%3A%2F%2Frealpython.com%2Fasync-io-python%2F&rut=abc'
        assert _unwrap_ddg_url(wrapped) == 'https://realpython.com/async-io-python/'

    def test_leaves_a_direct_url_untouched(self):
        assert _unwrap_ddg_url('https://docs.python.org/3/') == 'https://docs.python.org/3/'

    def test_handles_empty_and_malformed_input(self):
        assert _unwrap_ddg_url('') == ''
        assert _unwrap_ddg_url('not a url') == 'not a url'

    def test_protocol_relative_urls_get_a_scheme(self):
        assert _unwrap_ddg_url('//example.com/x').startswith('https://')


class TestHtmlCleaning:
    def test_strips_tags_and_decodes_entities(self):
        assert _clean_html_text('<b>Python&#39;s</b> asyncio') == "Python's asyncio"

    def test_handles_empty_input(self):
        assert _clean_html_text('') == ''
        assert _clean_html_text(None) == ''


class TestResultUrlsAreFiltered:
    """Scraped URLs are attacker-influenced; only http(s) may reach the client."""

    def test_backend_rejects_non_http_schemes(self):
        assert "startswith(('http://', 'https://'))" in WEBSEARCH_PY

    def test_backend_applies_the_ssrf_guard_to_results(self):
        idx = WEBSEARCH_PY.index('async def _ddg_search')
        body = WEBSEARCH_PY[idx:idx + 5000]
        assert '_is_ssrf_blocked_url(target)' in body

    @pytest.mark.parametrize(
        'url',
        [
            'http://169.254.169.254/latest/meta-data/',
            'http://localhost:8787/api/secrets/list',
            'http://127.0.0.1:8787/',
            'http://[::1]/',
            'http://2130706433/',
            'file:///etc/passwd',
        ],
    )
    def test_ssrf_targets_stay_blocked(self, url):
        assert _is_ssrf_blocked_url(url) is True

    def test_public_urls_are_allowed(self):
        assert _is_ssrf_blocked_url('https://docs.python.org/3/') is False


class TestFrontendUrlSafety:
    """escHtml() makes text safe, not URLs."""

    def test_safe_url_helper_exists(self):
        assert 'function safeUrl(' in WEBSEARCH_JS

    def test_every_href_is_routed_through_it(self):
        # No href may interpolate a raw URL any more.
        assert "href=\"${escHtml(c.url||'')}\"" not in WEBSEARCH_JS
        assert "href=\"${escHtml(res.url||'')}\"" not in WEBSEARCH_JS
        assert WEBSEARCH_JS.count('escHtml(safeUrl(') >= 4

    def test_helper_rejects_dangerous_schemes(self):
        """Mirrors the shipped implementation's contract."""
        import re as _re

        m = _re.search(r'function safeUrl\(url\) \{[\s\S]*?\n\}', WEBSEARCH_JS)
        assert m, 'safeUrl must be defined'
        body = m.group(0)
        assert "startsWith('http://')" in body and "startsWith('https://')" in body
        assert "return '#'" in body
        # Control characters must be stripped so "java\tscript:" cannot slip past.
        assert 'u0000' in body or '\\u0000' in body


class TestStatusCodes:
    def test_no_bare_ok_false_returns_remain(self):
        assert "return {'ok': False, 'error'" not in WEBSEARCH_PY

    def test_validation_failures_are_400(self):
        assert 'status_code=400' in WEBSEARCH_PY

    def test_ssrf_rejection_is_403(self):
        assert 'status_code=403' in WEBSEARCH_PY

    def test_missing_history_entry_is_404(self):
        assert 'status_code=404' in WEBSEARCH_PY
