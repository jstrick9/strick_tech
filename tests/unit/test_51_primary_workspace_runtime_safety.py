"""Primary workspace libraries must coexist in the same browser runtime."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CORE = (ROOT / 'frontend' / 'js' / '01-app-core.js').read_text(encoding='utf-8')
E2E = (ROOT / 'tests' / 'e2e' / 'test_product_experience_live.py').read_text(encoding='utf-8')


def test_galaxy_libraries_are_loaded_as_browser_globals_after_monaco():
    assert 'async function loadGalaxyLibrary(src)' in CORE
    assert 'window.define = undefined;' in CORE
    assert 'window.require = undefined;' in CORE
    assert "await loadGalaxyLibrary('https://cdn.jsdelivr.net/npm/3d-force-graph" in CORE


def test_primary_workspace_sweep_remains_in_live_product_smoke():
    for pane in ('templates', 'swarm', 'galaxy', 'hierarchy', 'kanban', 'settings', 'builder'):
        assert f"'{pane}'" in E2E


def test_product_smoke_covers_kanban_create_move_and_cleanup_lifecycle():
    assert "Functional browser task" in E2E
    assert "page.locator('#kbcol-doing')" in E2E
    assert "method: 'DELETE'" in E2E
