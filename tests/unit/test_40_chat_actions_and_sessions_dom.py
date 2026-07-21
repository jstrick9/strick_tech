"""
Agentic OS — Unit Test Suite 40
Comprehensive contract and runtime validation for:
  - Chat Sessions & Folder Organization drawer buttons (pin, rename, delete, load)
  - Message action bar buttons (copy, regenerate, listen, fork)
  - Multi-turn consecutive user prompt normalization (_normalize_messages)
  - Model badge rendering inside chat responses (⚡ modelUsed)
"""

import re
import pytest
from pathlib import Path

from backend.services.llm import _normalize_messages
from backend.routers.chat import _system_prompt_for_agent

ROOT = Path(__file__).resolve().parent.parent.parent
CORE_JS = (ROOT / 'frontend' / 'js' / '01-app-core.js').read_text(encoding='utf-8')
INDEX_HTML = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')


def test_normalize_messages_removes_consecutive_user_prompts():
    """Verify that multi-turn consecutive user messages are merged or normalized to avoid HTTP 400 errors."""
    msgs = [
        {'role': 'system', 'content': 'You are Direct AI Chat...'},
        {'role': 'user', 'content': 'First prompt'},
        {'role': 'assistant', 'content': 'First reply'},
        {'role': 'user', 'content': 'Second prompt'},
        {'role': 'user', 'content': 'Second prompt'},  # consecutive duplicate from turn 2 bug
    ]
    cleaned = _normalize_messages(msgs)
    roles = [m['role'] for m in cleaned]
    # Ensure no consecutive identical user messages with same text
    assert len(cleaned) == 4
    assert roles == ['system', 'user', 'assistant', 'user']
    assert cleaned[-1]['content'] == 'Second prompt'


def test_normalize_messages_merges_different_consecutive_user_prompts():
    """Verify that different consecutive user prompts are cleanly separated by newline to preserve strict alternation."""
    msgs = [
        {'role': 'system', 'content': 'System'},
        {'role': 'user', 'content': 'Prompt part 1'},
        {'role': 'user', 'content': 'Prompt part 2'},
    ]
    cleaned = _normalize_messages(msgs)
    assert len(cleaned) == 2
    assert cleaned[0]['role'] == 'system'
    assert cleaned[1]['role'] == 'user'
    assert 'Prompt part 1\n\nPrompt part 2' in cleaned[1]['content']


def test_chat_sessions_onclick_attributes_use_html_safe_quotes():
    """Verify that pin, rename, and delete button onclick attributes inside loadChatSessions escape double quotes using &quot;."""
    assert 'pinChatSession(event, &quot;${sidSafe}&quot;, ${!s.pinned})' in CORE_JS
    assert 'renameChatSessionModal(event, &quot;${sidSafe}&quot;, &quot;${snameSafe}&quot;, &quot;${folderSafe}&quot;)' in CORE_JS
    assert 'deleteChatSession(event, &quot;${sidSafe}&quot;)' in CORE_JS
    assert 'loadChatSession(&quot;${sidSafe}&quot;)' in CORE_JS


def test_message_actions_onclick_attributes_use_html_safe_quotes():
    """Verify that copy, regenerate, listen, and fork buttons in addMessageActions escape quotes and pass `this` element context."""
    assert 'copyMsgContent(this, &quot;${midSafe}&quot;)' in CORE_JS
    assert 'regenerateMsg(this, &quot;${midSafe}&quot;)' in CORE_JS
    assert 'listenToMsg(this, &quot;${midSafe}&quot;)' in CORE_JS
    assert 'branchFromMsg(this, &quot;${midSafe}&quot;)' in CORE_JS


def test_message_actions_fallback_to_btn_closest_msg():
    """Verify that copy, regenerate, listen, and fork functions cleanly find targetMsg using btn.closest('.msg') if getElementById fails."""
    assert 'const targetMsg = (typeof msgId === \'string\' && document.getElementById(msgId)) || btn?.closest?.(\'.msg\');' in CORE_JS
    assert 'window.copyMsgContent = function(btn, msgId)' in CORE_JS
    assert 'window.listenToMsg = function(btn, msgId)' in CORE_JS
    assert 'window.regenerateMsg = async function(btn, msgId)' in CORE_JS
    assert 'window.branchFromMsg = function(btn, msgId)' in CORE_JS


def test_model_used_badge_rendered_in_msg_meta():
    """Verify that addMessage and SSE streaming inject the model badge into .msg-meta."""
    assert 'const modelBadge = (modelUsed && role !== \'user\') ? ` <span class="model-used-tag tag"' in CORE_JS
    assert 'tag.innerHTML = `⚡ <strong>${escHtml(mStr)}</strong>`;' in CORE_JS


def test_direct_ai_chat_system_prompt():
    """Verify that Direct AI Chat persona returns natural universal assistant prompt without Agentic OS pitch."""
    agent = {'id': 'default', 'name': 'Direct AI Chat'}
    prompt = _system_prompt_for_agent(agent)
    assert 'helpful, intelligent, and accurate AI assistant' in prompt
    assert 'Agentic OS — a local-first autonomous AI operating system' not in prompt
