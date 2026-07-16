// ═══════════════════════════════════════════════════════════════
//  Agentic OS — State Management Store
//  Lightweight reactive state with subscribers
// ═══════════════════════════════════════════════════════════════
'use strict';

(function() {
  // ── Simple reactive store ──────────────────────────────────
  function createStore(initialState) {
    var state = Object.assign({}, initialState);
    var listeners = {};
    var globalListeners = [];

    return {
      // Get current state
      get: function(key) {
        if (key) return state[key];
        return Object.assign({}, state);
      },

      // Set state and notify subscribers
      set: function(key, value) {
        var old = state[key];
        state[key] = value;
        
        // Notify key-specific listeners
        if (listeners[key]) {
          listeners[key].forEach(function(fn) {
            try { fn(value, old, key); } catch(e) { console.warn('Store listener error:', e); }
          });
        }
        
        // Notify global listeners
        globalListeners.forEach(function(fn) {
          try { fn(state, key); } catch(e) { console.warn('Store global listener error:', e); }
        });
      },

      // Batch update multiple keys
      update: function(obj) {
        var changes = {};
        Object.keys(obj).forEach(function(key) {
          changes[key] = { old: state[key], new: obj[key] };
          state[key] = obj[key];
        });
        
        // Notify all changed keys
        Object.keys(changes).forEach(function(key) {
          if (listeners[key]) {
            listeners[key].forEach(function(fn) {
              try { fn(changes[key].new, changes[key].old, key); } catch(e) {}
            });
          }
        });
        
        // Global listeners
        globalListeners.forEach(function(fn) {
          try { fn(state); } catch(e) {}
        });
      },

      // Subscribe to a specific key
      on: function(key, fn) {
        if (!listeners[key]) listeners[key] = [];
        listeners[key].push(fn);
        return function() {
          listeners[key] = listeners[key].filter(function(f) { return f !== fn; });
        };
      },

      // Subscribe to all changes
      onChange: function(fn) {
        globalListeners.push(fn);
        return function() {
          globalListeners = globalListeners.filter(function(f) { return f !== fn; });
        };
      },

      // Reset to initial state
      reset: function() {
        state = Object.assign({}, initialState);
        globalListeners.forEach(function(fn) {
          try { fn(state); } catch(e) {}
        });
      }
    };
  }

  // ── Create the global store ────────────────────────────────
  var store = createStore({
    // UI State
    currentPane: 'chat',
    sidebarCollapsed: false,
    uiMode: localStorage.getItem('agentic_os_mode') || 'simple',
    
    // Agent State
    currentAgent: null,
    agents: [],
    agentStatuses: {},
    
    // Chat State
    chatHistory: [],
    chatSessionId: null,
    isStreaming: false,
    
    // Builder State
    currentFile: null,
    files: [],
    monacoEditor: null,
    
    // System State
    apiConnected: false,
    apiKeySet: false,
    wsConnected: false,
    
    // Feature State
    memoryStats: null,
    kanbanTasks: null,
    swarmResults: null,
  });

  // ── Export to global scope ─────────────────────────────────
  window.Store = store;
  
  // ── Backward compatibility: sync with legacy S object ──────
  if (window.S) {
    // Migrate existing state
    Object.keys(window.S).forEach(function(key) {
      if (window.S[key] !== undefined) {
        store.set(key, window.S[key]);
      }
    });
  }
  
  // Keep S as a proxy to Store for backward compatibility
  window.S = new Proxy({}, {
    get: function(target, prop) {
      return store.get(prop);
    },
    set: function(target, prop, value) {
      store.set(prop, value);
      return true;
    }
  });

  console.log('%c✅ State Store initialized', 'color:#3dba7a;font-weight:bold');
})();
