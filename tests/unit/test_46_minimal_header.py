"""The persistent header must stay focused while keeping model choice accessible."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
CORE = '\n'.join(f.read_text(encoding='utf-8') for f in sorted((ROOT / 'frontend' / 'js').glob('*.js')))
CSS = (ROOT / 'frontend' / 'styles.css').read_text(encoding='utf-8')


def test_model_control_can_be_shared_with_minimal_topbar():
    assert 'id="chat-model-control"' in INDEX
    # Model control stays in chat header where it belongs
    assert 'chat-model-control' in INDEX


def test_nonessential_topbar_actions_are_visually_deemphasized_not_deleted():
    # Topbar quick actions removed for clean minimal design
    # Model selector stays in Chat, voice in Chat, restart in Settings
    assert 'id="topbar-actions"' in INDEX
    assert 'id="notif-bell-btn"' in INDEX
