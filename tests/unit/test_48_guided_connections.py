"""AI setup should begin with plain-language choices and direct next actions."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
CORE = '\n'.join(f.read_text(encoding='utf-8') for f in sorted((ROOT / 'frontend' / 'js').glob('*.js')))
# r94, #258: this used to read frontend/styles.css — the pre-redesign
# monolith that index.html stopped loading on 2026-07-25 (527c463).
# Every assertion below was therefore checked against CSS the browser
# never loaded. It now reads the sheets the page actually loads.
CSS = '\n'.join(
    (ROOT / 'frontend' / s).read_text(encoding='utf-8')
    for s in ('styles-tokens.css', 'styles-unified.css',
              'styles-extracted.css', 'styles-redesign.css',
              'styles-system.css'))


def test_connections_start_with_three_plain_language_paths():
    for label in ('Use AI on this computer', 'Connect to cloud AI', 'Use another server'):
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
