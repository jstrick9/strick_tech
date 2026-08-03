"""Regression contracts for Mission Control chat-history controls and TTS stopping."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CORE_JS = '\n'.join(f.read_text(encoding='utf-8') for f in sorted((ROOT / 'frontend' / 'js').glob('*.js')))
VOICE_JS = (ROOT / 'frontend' / 'js' / '09-voice-tts.js').read_text(encoding='utf-8')
INDEX_HTML = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')


def test_history_defaults_to_five_and_paginates_the_date_view():
    # Chat-history rendering is owned by 56-chat-history.js. The older
    # 01-app-core.js implementation these assertions were written against was
    # dead code (56-chat-history.js loads later and reassigns the same window
    # functions) and has been removed, along with the #chat-folder-pills /
    # #chat-sort-select / page-size <select> markup it drove.
    assert "window._chatPageSize = window._chatPageSize || 5;" in CORE_JS
    assert 'id="chat-sessions-pagination"' in INDEX_HTML
    assert 'var pageSize=window._chatPageSize||5' in CORE_JS
    assert "page=sessions.slice(start,start+pageSize)" in CORE_JS
    assert "'Page '+cur+' of '+totalPages" in CORE_JS


def test_history_offers_folder_and_date_views():
    # The folder-pill + sort-dropdown model was replaced by a two-view toggle
    # (folder tree / date grouping) plus a per-folder collapsible tree.
    assert 'id="view-folders-btn"' in INDEX_HTML
    assert 'id="view-date-btn"' in INDEX_HTML
    assert "window.switchChatView = function(view)" in CORE_JS
    for group in ('Today', 'Yesterday', 'Previous 7 Days', 'Previous 30 Days', 'Older'):
        assert f"'{group}'" in CORE_JS


def test_history_messages_receive_a_synchronous_safe_id_for_webkit():
    assert 'div.id = `msg_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;' in CORE_JS
    assert 'if (msgDiv && !msgDiv.id)' in CORE_JS


def test_listen_toggle_and_chat_exit_cancel_every_playback_path():
    assert 'if (window._activeListenBtn === btn)' in CORE_JS
    assert "window.speechSynthesis.cancel()" in CORE_JS
    assert "chatPane.addEventListener('mouseleave', stop);" in CORE_JS
    assert "destination && destination !== 'chat'" in CORE_JS
    assert "window.addEventListener('pagehide', stop);" in CORE_JS
    assert "_ttsAudio.src = ''; _ttsAudio.load();" in VOICE_JS


def test_legacy_chat_log_schema_is_migrated_before_history_is_read():
    memory_db = (ROOT / 'backend' / 'services' / 'memory_db.py').read_text(encoding='utf-8')
    assert "ALTER TABLE chat_log ADD COLUMN model TEXT DEFAULT" in memory_db
    assert "parseSessionResponse" in CORE_JS


def test_history_rendering_never_uses_python_style_string_title_method():
    assert 'selectedPersonaId.title()' not in CORE_JS
    assert "(m.agent || 'AI').title()" not in CORE_JS
    assert 'function formatAgentName(value)' in CORE_JS
    assert "formatAgentName(m.agent || 'AI')" in CORE_JS
