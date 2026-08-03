"""Connection state should be understandable before a user sends a prompt."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
CORE = '\n'.join(f.read_text(encoding='utf-8') for f in sorted((ROOT / 'frontend' / 'js').glob('*.js')))
CSS = (ROOT / 'frontend' / 'styles.css').read_text(encoding='utf-8')


def test_chat_and_launchpad_expose_connection_readiness():
    assert 'id="chat-connection-status"' in INDEX
    # The Launchpad/Dashboard pane is rendered by 36-dashboard.js (renderDashboard
    # replaces #pane-dashboard's innerHTML), so its readiness button lives in the
    # JS bundle rather than in index.html. It previously existed in neither, which
    # made the 'mission-connection-status' half of renderConnectionReadiness a
    # permanent no-op.
    assert 'id="mission-connection-status"' in CORE
    assert "window.renderConnectionReadiness" in CORE


def test_readiness_prefers_local_models_then_connected_cloud():
    assert "Local AI ready" in CORE
    assert "AI connection ready" in CORE
    assert "Choose a connection to begin" in CORE
    assert "localModels: modR?.ollama?.running" in CORE


def test_connection_status_has_clear_accessible_visual_states():
    assert '.connection-status.ready::before' in CSS
    assert '.connection-status.attention::before' in CSS
