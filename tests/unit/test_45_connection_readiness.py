"""Connection state should be understandable before a user sends a prompt."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
CORE = (ROOT / 'frontend' / 'js' / '01-app-core.js').read_text(encoding='utf-8')
CSS = (ROOT / 'frontend' / 'styles.css').read_text(encoding='utf-8')


def test_chat_and_launchpad_expose_connection_readiness():
    assert 'id="chat-connection-status"' in INDEX
    assert 'id="mission-connection-status"' in INDEX
    assert "window.renderConnectionReadiness" in CORE


def test_readiness_prefers_local_models_then_connected_cloud():
    assert "Local AI ready" in CORE
    assert "AI connection ready" in CORE
    assert "Choose a connection to begin" in CORE
    assert "localModels: modR?.ollama?.running" in CORE


def test_connection_status_has_clear_accessible_visual_states():
    assert '.connection-status.ready::before' in CSS
    assert '.connection-status.attention::before' in CSS
