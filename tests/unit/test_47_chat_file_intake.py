"""Textual file intake must be discoverable, safe, and sent as explicit context."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
CORE = (ROOT / 'frontend' / 'js' / '01-app-core.js').read_text(encoding='utf-8')
CSS = (ROOT / 'frontend' / 'styles.css').read_text(encoding='utf-8')


def test_chat_has_click_and_drop_file_intake():
    assert 'id="chat-file-input"' in INDEX
    assert 'id="chat-attachment-tray"' in INDEX
    assert 'window.setupDragAndDrop' in CORE
    assert "Drop text, code, CSV, or JSON files" in CORE


def test_file_intake_has_clear_safety_limits_and_removable_chips():
    assert 'const maxFileBytes = 250 * 1024;' in CORE
    assert 'const maxAttachments = 5;' in CORE
    assert 'window.renderChatAttachments' in CORE
    assert "remove.textContent = '×'" in CORE


def test_attached_text_becomes_explicit_model_context():
    assert 'const attachmentContext = attachments.map' in CORE
    assert 'const messageForModel = msg + attachmentContext;' in CORE
    assert 'message:    messageForModel' in CORE
    assert '.chat-attachment-chip' in CSS
