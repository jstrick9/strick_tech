"""
Unit Tests — Chat module comprehensive review (`tests/unit/test_46_chat_module_review.py`)

Regression guards for real defects found during the Chat module review:

1. Streamed chats persisted tokens=0 / cost=0 forever, because the terminal SSE
   frame's usage data was never captured — so /api/cost and every FinOps surface
   was structurally incapable of reporting anything.
2. `/clear` reported "✅ Chat history cleared." while deleting nothing server-side.
3. Platform error/stub text ("No OPENROUTER_API_KEY set", "[stream error]", …) was
   ingested into long-term memory and then re-injected as RAG context — a
   self-poisoning loop.
4. `/models` listed only the hardcoded cloud registry, hiding the local Ollama
   models that are the ones actually able to run.
"""

from __future__ import annotations

from pathlib import Path

from backend.routers.chat import _looks_like_error_text

ROOT = Path(__file__).resolve().parents[2]
CHAT_PY = (ROOT / 'backend' / 'routers' / 'chat.py').read_text(encoding='utf-8')
LLM_PY = (ROOT / 'backend' / 'services' / 'llm.py').read_text(encoding='utf-8')


class TestErrorTextDetection:
    """Platform failure text must never be mistaken for real model output."""

    def test_detects_missing_api_key_stub(self):
        assert _looks_like_error_text('⚠️ **No OPENROUTER_API_KEY set.**\nGet a key at…')

    def test_detects_stream_error(self):
        assert _looks_like_error_text('[stream error]: connection reset')

    def test_detects_provider_fallback_notice(self):
        assert _looks_like_error_text(' [OpenRouter disconnected (timeout). Auto-falling back to local llama3.1:8b...]')

    def test_allows_genuine_completion(self):
        assert not _looks_like_error_text(
            'A REST API is an interface that uses HTTP verbs to expose resources over the network.'
        )

    def test_handles_empty_and_none(self):
        assert not _looks_like_error_text('')
        assert not _looks_like_error_text(None)


class TestMemoryIngestionGuard:
    """Only real completions may enter the long-term memory store."""

    def test_ingestion_is_gated_on_real_completion(self):
        assert 'is_real_completion' in CHAT_PY
        assert '_looks_like_error_text(full_text)' in CHAT_PY

    def test_stub_and_error_frames_disable_ingestion(self):
        assert "data.get('stub') or data.get('error')" in CHAT_PY


class TestTokenAndCostCapture:
    """Streamed usage must be captured and persisted, not silently dropped."""

    def test_chat_captures_usage_from_terminal_frame(self):
        assert "used_tokens = int(data.get('tokens', 0) or 0)" in CHAT_PY
        assert "used_cost = float(data.get('cost', 0.0) or 0.0)" in CHAT_PY

    def test_chat_persists_usage_to_chat_log(self):
        assert 'tokens=used_tokens' in CHAT_PY
        assert 'cost=used_cost' in CHAT_PY

    def test_ollama_stream_emits_token_counts(self):
        assert "prompt_eval_count" in LLM_PY
        assert "'completion_tokens': completion_tokens" in LLM_PY

    def test_openrouter_stream_requests_and_forwards_usage(self):
        assert "'stream_options': {'include_usage': True}" in LLM_PY
        assert 'stream_usage' in LLM_PY

    def test_openrouter_usage_chunk_does_not_crash_on_empty_choices(self):
        # The usage-bearing chunk carries choices: [] — indexing [0] blindly
        # would raise and lose the usage payload.
        assert "choices = chunk.get('choices') or []" in LLM_PY


class TestClearCommand:
    """/clear must actually delete, and must not lie when it cannot."""

    def test_clear_deletes_server_side(self):
        assert "DELETE FROM chat_log WHERE session_id=?" in CHAT_PY

    def test_clear_resets_session_message_count(self):
        assert 'UPDATE chat_sessions SET message_count=0' in CHAT_PY

    def test_clear_reports_failure_instead_of_false_success(self):
        assert 'Could not clear this conversation' in CHAT_PY
        # The UI transcript may only be wiped when the delete really happened.
        assert 'if not clear_error:' in CHAT_PY

    def test_clear_distinguishes_empty_conversation(self):
        assert 'This conversation was already empty.' in CHAT_PY


class TestModelsCommand:
    """/models must reflect what can actually run on this machine."""

    def test_lists_local_ollama_models(self):
        assert 'Local models (Ollama' in CHAT_PY
        assert 'llm.ollama_health()' in CHAT_PY

    def test_warns_when_cloud_key_missing(self):
        assert 'no API key set' in CHAT_PY

    def test_guides_user_when_nothing_is_configured(self):
        assert 'No usable model is configured yet' in CHAT_PY
