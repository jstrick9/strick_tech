"""Regression contracts for Mission Control chat-history controls and TTS stopping."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CORE_JS = (ROOT / 'frontend' / 'js' / '01-app-core.js').read_text(encoding='utf-8')
VOICE_JS = (ROOT / 'frontend' / 'js' / '09-voice-tts.js').read_text(encoding='utf-8')
INDEX_HTML = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')


def test_history_defaults_to_five_and_offers_requested_page_sizes():
    assert "window._chatPageSize = window._chatPageSize || 5;" in CORE_JS
    for size in (5, 10, 15, 20, 25):
        assert f'<option value="{size}"' in INDEX_HTML
    assert 'id="chat-sessions-pagination"' in INDEX_HTML
    assert 'const pageSessions = filtered.slice(startIdx, startIdx + pageSize);' in CORE_JS
    assert 'Page ${curPage} of ${totalPages}' in CORE_JS


def test_history_sort_modes_and_all_chats_virtual_filter_are_present():
    for mode in ('newest', 'oldest', 'az', 'za', 'folder_az', 'folder_za'):
        assert f"'{mode}'" in CORE_JS
    assert 'All Chats</button>' in INDEX_HTML
    assert "const showFolderSort = (folderFilter === 'All');" in CORE_JS
    assert "optFAZ.style.display = showFolderSort ? '' : 'none';" in CORE_JS


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
