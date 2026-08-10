"""Module 14 regression tests — workflow builder, multi-tab preview.

Defects found by probing the running module:

1. When an agent node raised, `prev_output` was left UNTOUCHED, so every
   downstream node consumed the previous node's data as though the failed step
   had produced it. Demonstrated live with
   trigger -> agent("Summarise: {{input}}") -> output and no provider:
       final_output: "CONFIDENTIAL-RAW-INPUT-42"
   The raw, unsummarised input was published as the pipeline's finished
   result, indistinguishable from a real summary.
2. The output node emitted `final_output` even when upstream had failed.
3. The UI logged "Workflow complete" on `done` regardless of
   `status: "failed"` — a run whose every node errored reported success.
4. multitab stored a tab `url` without validation, while the pane assigns it
   straight to an iframe src (`frame.src = tab.url`). `javascript:alert(...)`
   was accepted, persisted, and reached a live iframe in Chromium. Both the
   POST and PATCH doors accepted it.
"""

from __future__ import annotations

import inspect

import pytest

from backend.routers import multitab, workflow


# ── 1/2. a failed node must not hand stale data downstream ────────────────────
def test_failed_agent_clears_prev_output():
    """The exact defect: prev_output must not survive a node failure."""
    src = inspect.getsource(workflow)
    # The agent except-branch must reset the carried value.
    idx = src.index("elif node['type'] == 'agent':")
    branch = src[idx:idx + 1800]
    branch = '\n'.join(ln for ln in branch.split('\n') if not ln.strip().startswith('#'))
    assert "context['prev_output'] = ''" in branch, (
        'a failed agent node still carries the previous output forward'
    )


def test_output_node_refuses_to_publish_after_a_failure():
    src = inspect.getsource(workflow)
    idx = src.index("elif node['type'] == 'output':")
    branch = src[idx:idx + 2200]
    body = '\n'.join(ln for ln in branch.split('\n') if not ln.strip().startswith('#'))
    assert 'if node_errors:' in body
    assert "'delivered': False" in body or '"delivered": False' in body


def test_output_node_still_delivers_on_success():
    src = inspect.getsource(workflow)
    idx = src.index("elif node['type'] == 'output':")
    branch = src[idx:idx + 2200]
    assert "'delivered': True" in branch or '"delivered": True' in branch


def test_failed_nodes_are_tracked():
    src = inspect.getsource(workflow)
    assert 'failed_nodes' in src


def test_run_status_reflects_node_errors():
    """Pre-existing behaviour that must keep working."""
    src = inspect.getsource(workflow)
    assert "'failed' if node_errors else 'success'" in src


# ── 4. tab URLs must be validated ─────────────────────────────────────────────
@pytest.mark.parametrize('bad', [
    'javascript:alert(1)',
    'JavaScript:alert(1)',
    '  javascript:alert(1)',
    'data:text/html,<script>alert(1)</script>',
    'vbscript:msgbox(1)',
    '//evil.example.com/x',
    'file:///etc/passwd',
])
def test_dangerous_tab_urls_are_refused(bad):
    url, err = multitab._safe_tab_url(bad, '/preview/index.html')
    assert err is not None, f'{bad!r} was accepted'
    assert url == '/preview/index.html'


def test_control_character_scheme_smuggling_is_refused():
    """'java\\tscript:' is ignored by the URL parser but beats a prefix check."""
    url, err = multitab._safe_tab_url('java\tscript:alert(1)', '/preview/index.html')
    assert err is not None
    assert url == '/preview/index.html'


def test_path_traversal_in_url_is_refused():
    url, err = multitab._safe_tab_url('/../../etc/passwd', '/preview/index.html')
    assert err is not None
    assert 'traversal' in err


@pytest.mark.parametrize('good', [
    '/preview/index.html',
    '/preview/sub/page.html',
    'https://example.com',
    'http://localhost:8787/preview/x.html',
])
def test_legitimate_urls_are_accepted(good):
    url, err = multitab._safe_tab_url(good, '/preview/index.html')
    assert err is None, f'{good!r} was rejected: {err}'
    assert url == good


def test_empty_url_falls_back_without_an_error():
    url, err = multitab._safe_tab_url('', '/preview/index.html')
    assert err is None
    assert url == '/preview/index.html'


def test_non_string_url_is_refused_not_coerced():
    """as_text() stringifies a dict, which must not become a usable URL."""
    url, err = multitab._safe_tab_url({'not': 'a string'}, '/preview/index.html')
    assert err is not None
    assert url == '/preview/index.html'


def test_both_tab_doors_validate_the_url():
    """The URL bar patches; create posts. Fixing one is not enough."""
    for fn in (multitab.create_tab, multitab.update_tab):
        src = inspect.getsource(fn)
        src = '\n'.join(ln for ln in src.split('\n') if not ln.strip().startswith('#'))
        assert '_safe_tab_url' in src, f'{fn.__name__} does not validate the url'


def test_invalid_url_is_a_400_not_a_silent_fallback():
    for fn in (multitab.create_tab, multitab.update_tab):
        src = inspect.getsource(fn)
        assert 'invalid_url' in src
        assert 'status_code=400' in src
