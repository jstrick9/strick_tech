"""The persistent header must stay focused while keeping model choice accessible."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
CORE = (ROOT / 'frontend' / 'js' / '01-app-core.js').read_text(encoding='utf-8')
CSS = (ROOT / 'frontend' / 'styles.css').read_text(encoding='utf-8')


def test_model_control_can_be_shared_with_minimal_topbar():
    assert 'id="chat-model-control"' in INDEX
    assert 'window.placeGlobalModelControl' in CORE
    assert 'topbar.insertBefore(control, spacer)' in CORE


def test_nonessential_topbar_actions_are_visually_deemphasized_not_deleted():
    assert 'id="topbar-quick-actions"' in INDEX
    assert '#topbar-quick-actions, #topbar > .tech-badge' in CSS
    assert '#topbar-actions > #restart-engine-btn' in CSS
    assert 'id="restart-engine-btn"' in INDEX
