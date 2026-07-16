// ═══════════════════════════════════════════════════════════════
//  Agentic OS — Voice & TTS Frontend Integration
//  Adds speak buttons to messages, voice input to chat bar,
//  and voice settings to the settings pane.
// ═══════════════════════════════════════════════════════════════
'use strict';

(function() {
  var _ttsPlaying = null;
  var _ttsAudio = null;
  var _recognition = null;
  var _isListening = false;

  // ── Speak a message (TTS) ──────────────────────────────────
  window.speakMessage = function(text, agentId) {
    if (!text) return;
    
    // Stop any current playback
    if (_ttsAudio) {
      _ttsAudio.pause();
      _ttsAudio = null;
      _ttsPlaying = null;
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
    updateSpeakButtons();
    
    _ttsAudio.play().catch(function(e) {
      console.warn('TTS play failed:', e);
      _ttsAudio = null;
      _ttsPlaying = null;
      updateSpeakButtons();
    });
    
    _ttsAudio.onended = function() {
      _ttsAudio = null;
      _ttsPlaying = null;
      updateSpeakButtons();
    };
    
    _ttsAudio.onerror = function() {
      _ttsAudio = null;
      _ttsPlaying = null;
      updateSpeakButtons();
    };
  };

  window.stopSpeaking = function() {
    if (_ttsAudio) {
      _ttsAudio.pause();
      _ttsAudio = null;
      _ttsPlaying = null;
      updateSpeakButtons();
    }
  };

  function updateSpeakButtons() {
    document.querySelectorAll('.speak-btn').forEach(function(btn) {
      var isPlaying = btn.dataset.text && _ttsPlaying && btn.dataset.text.startsWith(_ttsPlaying);
      btn.textContent = isPlaying ? '⏹' : '🔊';
      btn.title = isPlaying ? 'Stop speaking' : 'Read aloud';
    });
  }

  // ── Inject speak buttons into messages ──────────────────────
  window.injectSpeakButtons = function() {
    document.querySelectorAll('.msg-bubble').forEach(function(bubble) {
      if (bubble.querySelector('.speak-btn')) return; // already injected
      var msg = bubble.closest('.msg');
      if (!msg || msg.classList.contains('user')) return; // only for agent messages
      
      var text = bubble.textContent || '';
      if (text.length < 10) return; // too short to speak
      
      var btn = document.createElement('button');
      btn.className = 'speak-btn';
      btn.dataset.text = text.slice(0, 50);
      btn.textContent = '🔊';
      btn.title = 'Read aloud';
      btn.style.cssText = 'position:absolute;top:8px;right:8px;background:var(--bg-3);border:1px solid var(--border);border-radius:6px;padding:2px 6px;font-size:12px;cursor:pointer;opacity:0;transition:opacity .2s;z-index:5';
      btn.onclick = function(e) {
        e.stopPropagation();
        if (_ttsPlaying) { stopSpeaking(); }
        else { speakMessage(text, msg.dataset?.agentId); }
      };
      
      bubble.style.position = 'relative';
      bubble.appendChild(btn);
      
      // Show on hover
      bubble.addEventListener('mouseenter', function() { btn.style.opacity = '1'; });
      bubble.addEventListener('mouseleave', function() { btn.style.opacity = '0'; });
    });
  };

  // ── Voice Input (WebSpeech API) ────────────────────────────
  window.toggleVoiceInput = function() {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
      if (window.showToast) showToast('Voice input not supported in this browser. Try Chrome or Edge.');
      return;
    }
    
    if (_isListening) {
      stopVoiceInput();
      return;
    }
    
    var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    _recognition = new SpeechRecognition();
    _recognition.continuous = false;
    _recognition.interimResults = true;
    _recognition.lang = 'en-US';
    
    var voiceBtn = document.getElementById('voice-input-btn');
    var chatInput = document.getElementById('chat-input');
    
    _recognition.onstart = function() {
      _isListening = true;
      if (voiceBtn) {
        voiceBtn.style.background = 'var(--danger)';
        voiceBtn.style.color = 'white';
        voiceBtn.textContent = '⏹';
        voiceBtn.title = 'Stop listening';
      }
      if (window.showToast) showToast('🎤 Listening…');
    };
    
    _recognition.onresult = function(event) {
      var transcript = '';
      for (var i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      if (chatInput) {
        chatInput.value = transcript;
        // Auto-resize
        chatInput.style.height = 'auto';
        chatInput.style.height = Math.min(chatInput.scrollHeight, 160) + 'px';
      }
      
      // If final result, parse as voice command
      if (event.results[event.results.length - 1].isFinal) {
        parseVoiceCommand(transcript);
      }
    };
    
    _recognition.onerror = function(event) {
      console.warn('Speech recognition error:', event.error);
      stopVoiceInput();
      if (event.error !== 'no-speech' && window.showToast) {
        showToast('Voice error: ' + event.error);
      }
    };
    
    _recognition.onend = function() {
      stopVoiceInput();
    };
    
    _recognition.start();
  };

  function stopVoiceInput() {
    _isListening = false;
    if (_recognition) {
      try { _recognition.stop(); } catch(e) {}
      _recognition = null;
    }
    var voiceBtn = document.getElementById('voice-input-btn');
    if (voiceBtn) {
      voiceBtn.style.background = '';
      voiceBtn.style.color = '';
      voiceBtn.textContent = '🎤';
      voiceBtn.title = 'Voice input (Ctrl+Shift+V)';
    }
  }

  // ── Parse voice command ────────────────────────────────────
  async function parseVoiceCommand(transcript) {
    if (!transcript || transcript.length < 3) return;
    
    try {
      var resp = await fetch('/api/voice/parse', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({transcript: transcript})
      });
      var data = await resp.json();
      
      if (data.ok && data.action !== 'chat_send') {
        // It's a command — execute it
        executeVoiceAction(data.action, data.payload);
        if (window.showToast) showToast('🎤 Voice command: ' + data.action);
      }
      // If chat_send, the text is already in the input — user just needs to press Enter
    } catch(e) {
      // Silently fail — voice parsing is optional
    }
  }

  function executeVoiceAction(action, payload) {
    switch(action) {
      case 'navigate':
        if (window.nav) nav(payload);
        break;
      case 'command_palette':
        if (window.openPalette) openPalette();
        break;
      case 'toggle_sidebar':
        if (window.toggleSidebar) toggleSidebar();
        break;
      case 'new_chat':
        if (window.clearChatHistory) clearChatHistory();
        break;
      case 'clear_chat':
        if (window.clearChatHistory) clearChatHistory();
        break;
      case 'help':
        if (window.showKeyboardShortcuts) showKeyboardShortcuts();
        break;
      case 'save':
        if (window.studioSaveFile) studioSaveFile();
        break;
      case 'search':
        if (window.openPalette) openPalette();
        break;
      default:
        // Unknown command — just send as chat
        break;
    }
  }

  // ── Inject voice button into chat bar ───────────────────────
  function injectVoiceButton() {
    var chatTools = document.querySelector('.chat-tools');
    if (!chatTools || document.getElementById('voice-input-btn')) return;
    
    var btn = document.createElement('button');
    btn.id = 'voice-input-btn';
    btn.className = 'chat-tool';
    btn.textContent = '🎤';
    btn.title = 'Voice input (Ctrl+Shift+V)';
    btn.onclick = function() { toggleVoiceInput(); };
    chatTools.appendChild(btn);
  }

  // ── Keyboard shortcut for voice ────────────────────────────
  document.addEventListener('keydown', function(e) {
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'V') {
      e.preventDefault();
      toggleVoiceInput();
    }
  });

  // ── Auto-inject buttons ────────────────────────────────────
  setTimeout(function() {
    injectVoiceButton();
    // Re-inject speak buttons when chat messages change
    var observer = new MutationObserver(function() {
      injectSpeakButtons();
    });
    var chatMessages = document.getElementById('chat-messages');
    if (chatMessages) {
      observer.observe(chatMessages, { childList: true, subtree: true });
    }
  }, 2000);

  console.log('%c✅ Voice & TTS integration loaded', 'color:#c084fc;font-weight:bold');
})();
