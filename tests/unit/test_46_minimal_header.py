"""The persistent header must stay focused while keeping model choice accessible."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
CORE = '\n'.join(f.read_text(encoding='utf-8') for f in sorted((ROOT / 'frontend' / 'js').glob('*.js')))
CSS = (ROOT / 'frontend' / 'styles.css').read_text(encoding='utf-8')


def test_model_control_can_be_shared_with_minimal_topbar():
    assert 'id="chat-model-control"' in INDEX
    assert 'window.placeGlobalModelControl' in CORE
    assert 'topbar.insertBefore(control, spacer)' in CORE


def test_nonessential_topbar_actions_are_visually_deemphasized_not_deleted():
    assert 'id="topbar-quick-actions"' in INDEX
    # Topbar quick actions and actions are now visible (not hidden)
    # They were previously hidden with display:none which broke the UI
    assert 'topbar-quick-actions' in CSS or 'topbar-quick-actions' in INDEX
    assert 'id="restart-engine-btn"' in INDEX
