"""Regression checks for shared frontend transport/navigation boundaries."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / 'frontend' / 'index.html'
CORE = ROOT / 'frontend' / 'js' / '01-app-core.js'
API = ROOT / 'frontend' / 'js' / '00-api-client.js'
NAV = ROOT / 'frontend' / 'js' / '00-navigation-state.js'


def test_shared_modules_load_before_core():
    html = INDEX.read_text(encoding='utf-8')
    assert html.index('/static/js/00-api-client.js') < html.index('/static/js/01-app-core.js')
    assert html.index('/static/js/00-navigation-state.js') < html.index('/static/js/01-app-core.js')
    assert html.index('/static/js/00-pane-registry.js') < html.index('/static/js/01-app-core.js')


def test_api_client_exposes_safe_transport_boundary():
    source = API.read_text(encoding='utf-8')
    for method in ('get:', 'post:', 'patch:', 'delete:'):
        assert method in source
    assert 'Authorization' in source
    assert 'response.ok' in source


def test_navigation_state_is_independent_of_dom_rendering():
    source = NAV.read_text(encoding='utf-8')
    core = CORE.read_text(encoding='utf-8')
    assert 'subscribe:' in source
    assert 'window.NavigationState.set(pane)' in core
    assert 'currentPane' in source
