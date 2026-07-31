// ═══════════════════════════════════════════════════════════════
//  Agentic OS — Voice & TTS Frontend Integration
//  Text-to-speech playback for AI messages (window.speakMessage /
//  window.stopSpeaking). Voice INPUT lives in 03-features-b.js
//  (window.toggleVoice) — see the note further down for why.
// ═══════════════════════════════════════════════════════════════
'use strict';

(function() {
  var _ttsPlaying = null;
  var _ttsAudio = null;

  // ── Speak a message (TTS) ──────────────────────────────────
  window.speakMessage = function(text, agentId) {
    if (!text) return;
    
    // Stop any current playback
    if (_ttsAudio) {
      _ttsAudio.pause();
      _ttsAudio = null;
      _ttsPlaying = null;
      window._ttsPlaying = null;
      updateSpeakButtons();
    }
    
    // Strip markdown for cleaner speech
    var cleanText = text.replace(/```[\s\S]*?```/g, ' code block ')
                        .replace(/`[^`]+`/g, '')
                        .replace(/\*\*(.+?)\*\*/g, '$1')
                        .replace(/\*(.+?)\*/g, '$1')
                        .replace(/#+\s+/g, '')
                        .replace(/\[(.+?)\]\(.+?\)/g, '$1')
                        .slice(0, 2000);
    
    if (!cleanText.trim()) return;
    
    // Use the TTS API
    var url = '/api/tts/speak?text=' + encodeURIComponent(cleanText) + 
              '&agent_id=' + encodeURIComponent(agentId || 'default');
    
    _ttsAudio = new Audio(url);
    _ttsPlaying = text.slice(0, 50);
    window._ttsPlaying = _ttsPlaying;
    updateSpeakButtons();
    
    _ttsAudio.play().catch(function(e) {
      console.warn('TTS play failed:', e);
      _ttsAudio = null;
      _ttsPlaying = null;
      window._ttsPlaying = null;
      updateSpeakButtons();
    });
    
    _ttsAudio.onended = function() {
      _ttsAudio = null;
      _ttsPlaying = null;
      window._ttsPlaying = null;
      updateSpeakButtons();
    };
    
    _ttsAudio.onerror = function() {
      _ttsAudio = null;
      _ttsPlaying = null;
      window._ttsPlaying = null;
      updateSpeakButtons();
    };
  };

  window.stopSpeaking = function() {
    // Cancel both supported playback paths. Clearing src releases the network
    // stream immediately in WKWebView/Safari as well as Chromium.
    if (_ttsAudio) {
      try { _ttsAudio.pause(); _ttsAudio.currentTime = 0; _ttsAudio.src = ''; _ttsAudio.load(); } catch (e) {}
      _ttsAudio = null;
    }
    if ('speechSynthesis' in window) {
      try { window.speechSynthesis.cancel(); } catch (e) {}
    }
    _ttsPlaying = null;
    window._ttsPlaying = null;
    updateSpeakButtons();
  };

  function updateSpeakButtons() {
    document.querySelectorAll('.speak-btn').forEach(function(btn) {
      var isPlaying = btn.dataset.text && _ttsPlaying && btn.dataset.text.startsWith(_ttsPlaying);
      btn.textContent = isPlaying ? '⏹' : '🔊';
      btn.title = isPlaying ? 'Stop speaking' : 'Read aloud';
    });
    if (!_ttsPlaying && window._activeListenBtn) {
      window._activeListenBtn.innerHTML = '🔊 Listen';
      window._activeListenBtn.style.borderColor = 'var(--border)';
      window._activeListenBtn = null;
    }
  }

  // ── Inject speak buttons into messages (disabled per user preference; Listen button inside .msg-actions handles TTS directly) ──
  window.injectSpeakButtons = function() {
    // No-op: removed top-right absolute speak buttons so only bottom .msg-actions Listen button is shown
  };

  // NOTE: this file used to also define its own separate voice-INPUT
  // system (window.toggleVoiceInput, a #voice-input-btn button, and its
  // own Ctrl+Shift+V shortcut) that duplicated — and directly conflicted
  // with — the richer voice-coding system in 03-features-b.js
  // (window.toggleVoice / #voice-btn / the same Ctrl+Shift+V shortcut).
  // Because both files bound the identical shortcut, a single keypress
  // started TWO separate SpeechRecognition sessions at once, and the two
  // near-identical 🎤 buttons sitting side-by-side in the chat toolbar
  // were confusing and did different things. Removed this file's copy;
  // 03-features-b.js's voice coding (navigate/chat_send/run_agent/
  // create_file/open_file/run_tests command parsing) is the sole voice
  // INPUT implementation now. This file keeps only text-to-speech
  // (window.speakMessage / window.stopSpeaking), which is unique to it.

  // ── Auto-inject buttons ────────────────────────────────────
  setTimeout(function() {
    // Re-inject speak buttons when chat messages change
    var observer = new MutationObserver(function() {
      injectSpeakButtons();
    });
    var chatMessages = document.getElementById('chat-messages');
    if (chatMessages) {
      observer.observe(chatMessages, { childList: true, subtree: true });
    }
  }, 2000);

  console.debug('%c✅ Voice & TTS integration loaded', 'color:#c084fc;font-weight:bold');
})();
