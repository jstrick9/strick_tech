"""AI setup should begin with plain-language choices and direct next actions."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
CORE = (ROOT / 'frontend' / 'js' / '01-app-core.js').read_text(encoding='utf-8')
CSS = (ROOT / 'frontend' / 'styles.css').read_text(encoding='utf-8')


def test_connections_start_with_three_plain_language_paths():
    for label in ('Use AI on this Mac', 'Connect cloud AI', 'Use another connection'):
        assert label in INDEX
    assert 'id="connection-local-card"' in INDEX
    assert 'id="connection-cloud-card"' in INDEX
    assert 'id="connection-custom-card"' in INDEX


def test_connection_path_scrolls_and_uses_the_right_next_action():
    assert 'window.startConnectionPath' in CORE
    assert "target.scrollIntoView({behavior: 'smooth', block: 'center'})" in CORE
    assert 'window.testOllamaConnection?.()' in CORE
    assert "'or-key-input'" in CORE


def test_connection_choices_are_responsive_and_tactile():
    assert '.connection-paths' in CSS
    assert '.connection-path:hover' in CSS
