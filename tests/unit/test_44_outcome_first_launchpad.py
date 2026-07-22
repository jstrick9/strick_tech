"""Mission Control must welcome people with understandable outcomes, not AI jargon."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
CORE = (ROOT / 'frontend' / 'js' / '01-app-core.js').read_text(encoding='utf-8')
CSS = (ROOT / 'frontend' / 'styles.css').read_text(encoding='utf-8')


def test_launchpad_offers_plain_language_outcomes():
    for label in ('Ask a question', 'Research a topic', 'Make a plan', 'Create something'):
        assert label in INDEX
    assert 'mission-outcome-grid' in INDEX
    assert 'OpenRouter OR Local Ollama' not in INDEX


def test_launchpad_actions_leave_prompts_editable_and_focus_input():
    assert 'window.startGuidedChat = function(prompt = \'\')' in CORE
    assert 'input.focus();' in CORE
    assert "launchpad.style.display = 'none'" in CORE


def test_launchpad_is_responsive_and_uses_design_tokens():
    assert '.mission-launchpad {' in CSS
    assert 'var(--bg-1)' in CSS
    assert '@media (max-width:640px)' in CSS


def test_outcome_launchpad_survives_new_chat_and_history_clears():
    assert "let chatEmptyTemplate = document.querySelector('#chat-messages #chat-empty')?.cloneNode(true) || null;" in CORE
    assert 'emptyEl = chatEmptyTemplate.cloneNode(true);' in CORE
