"""The persistent header must stay focused while keeping model choice accessible."""
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


def test_model_control_can_be_shared_with_minimal_topbar():
    assert 'id="chat-model-control"' in INDEX
    # Model control stays in chat header where it belongs
    assert 'chat-model-control' in INDEX


def test_nonessential_topbar_actions_are_visually_deemphasized_not_deleted():
    # Topbar quick actions removed for clean minimal design
    # Model selector stays in Chat, voice in Chat, restart in Settings
    assert 'id="topbar-actions"' in INDEX
    assert 'id="notif-bell-btn"' in INDEX
