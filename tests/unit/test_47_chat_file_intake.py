"""Textual file intake must be discoverable, safe, and sent as explicit context."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
CORE = '\n'.join(f.read_text(encoding='utf-8') for f in sorted((ROOT / 'frontend' / 'js').glob('*.js')))
CSS = (ROOT / 'frontend' / 'styles.css').read_text(encoding='utf-8')


def test_chat_has_click_and_drop_file_intake():
    assert 'id="chat-file-input"' in INDEX
    assert 'id="chat-attachment-tray"' in INDEX
    assert 'window.setupDragAndDrop' in CORE
    assert "Drop text, code, data, PDF, or Word files" in CORE


def test_file_intake_has_clear_safety_limits_and_removable_chips():
    assert 'const maxTextFileBytes = 250 * 1024;' in CORE
    assert 'const maxDocumentBytes = 4 * 1024 * 1024;' in CORE
    assert 'const maxAttachments = 5;' in CORE
    assert 'window.renderChatAttachments' in CORE
    assert "remove.textContent = '×'" in CORE


def test_attached_text_becomes_explicit_model_context():
    # Text/code attachments are still inlined as fenced context, but images are
    # now split out into OpenAI-format image_url parts (see the vision fix in
    # sendChat), so the payload is built from textAttachments rather than the
    # whole attachment list.
    assert 'const attachmentContext = textAttachments.map' in CORE
    assert 'const promptText = msg + attachmentContext + imageNote;' in CORE
    assert 'message:    messageForModel' in CORE
    assert '.chat-attachment-chip' in CSS


def test_attached_images_are_sent_as_real_multimodal_parts():
    """Images must reach the provider as image_url parts, not as truncated text.

    Regression guard: attachments used to be flattened into the prompt as
    "[image data: <first 80 chars>...]", which is just the data-URL header —
    the image itself never reached the model, making vision impossible.
    """
    assert "type: 'image_url'" in CORE
    assert 'image_url: { url: item.text }' in CORE
    # The old lossy truncation must not come back.
    assert '[image data: ${item.text.slice(0, 80)}...]' not in CORE


def test_chat_routes_pdf_and_word_documents_to_local_extraction():
    assert "['pdf', 'docx'].includes(extension)" in CORE
    assert "fetch('/api/documents/extract'" in CORE
