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


def test_workspace_actions_use_dataset_values_not_breakable_json_inline_handlers():
    assert 'activateWorkspace(this.dataset.workspaceId, this.dataset.workspaceName)' in CORE
    assert 'deleteWorkspace(this.dataset.workspaceId, this.dataset.workspaceName)' in CORE
    assert 'activateWorkspace(${JSON.stringify(w.id)}' not in CORE


def test_memory_search_actions_bind_listeners_instead_of_inline_json_handlers():
    assert "el.querySelectorAll('.gx-delete-memory')" in CORE
    assert "deleteGxNode(button.dataset.memoryId)" in CORE
    assert "deleteGxNode(${JSON.stringify(m.id)})" not in CORE


def test_product_smoke_covers_memory_create_search_and_delete():
    assert "Functional memory" in E2E
    assert "#gx-ingest-text" in E2E
    assert ".gx-delete-memory" in E2E


def test_new_workspace_activation_keeps_a_live_preview_available():
    assert 'def _ensure_preview_index(directory: Path)' in (ROOT / 'backend' / 'routers' / 'workspaces.py').read_text(encoding='utf-8')
    assert 'Open Studio to start creating.' in (ROOT / 'backend' / 'routers' / 'workspaces.py').read_text(encoding='utf-8')


def test_product_smoke_covers_temporary_project_studio_scaffold_and_preview():
    assert "studio-scaffold-prompt" in E2E
    assert "Scaffolded web project" in E2E
    assert "#studio-sidebar" in E2E
