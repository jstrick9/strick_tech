// ═══════════════════════════════════════════════════════════════
//  Agentic OS — Error Boundaries
//  Wraps render functions with try/catch and provides recovery
// ═══════════════════════════════════════════════════════════════
'use strict';

(function() {
  var errorCounts = {};
  var MAX_RETRIES = 3;

  // ── Wrap a function with error boundary ────────────────────
  window.withErrorBoundary = function(fn, name) {
    return function() {
      try {
        return fn.apply(this, arguments);
      } catch(error) {
        handleError(name || fn.name || 'anonymous', error);
        return undefined;
      }
    };
  };

  // ── Handle render errors ───────────────────────────────────
  function handleError(name, error) {
    if (!errorCounts[name]) errorCounts[name] = 0;
    errorCounts[name]++;
    
    console.error('[ErrorBoundary]', name, error);
    
    // Don't spam the UI for repeated errors
    if (errorCounts[name] > MAX_RETRIES) {
      console.warn('[ErrorBoundary] Max retries reached for', name);
      return;
    }

    // Show user-friendly error
    var pane = document.querySelector('.pane.active');
    if (pane && !pane.querySelector('.error-boundary-toast')) {
      var toast = document.createElement('div');
      toast.className = 'error-boundary-toast';
      toast.style.cssText = 'position:absolute;top:8px;right:8px;z-index:100;background:var(--danger-bg);border:1px solid var(--danger-border);color:var(--danger);padding:8px 14px;border-radius:8px;font-size:12px;max-width:320px;animation:fadeIn .2s ease;cursor:pointer';
      toast.innerHTML = '⚠️ Something went wrong. <strong>Click to retry.</strong>';
      toast.onclick = function() {
        toast.remove();
        // Re-trigger the current pane navigation
        if (window.nav) {
          var activeNav = document.querySelector('.nav-item.active');
          if (activeNav) {
            var paneName = activeNav.getAttribute('data-nav');
            if (paneName) window.nav(paneName);
          }
        }
      };
      pane.style.position = 'relative';
      pane.appendChild(toast);
      
      // Auto-dismiss after 5 seconds
      setTimeout(function() { if (toast.parentNode) toast.remove(); }, 5000);
    }
  }

  // ── Global unhandled error handler ─────────────────────────
  window.addEventListener('error', function(event) {
    // Don't handle errors from external scripts (CDN, etc.)
    if (event.filename && !event.filename.includes(location.origin)) return;
    
    console.error('[GlobalError]', event.message, event.filename, event.lineno);
    // Don't show toast for every JS error — too noisy
  });

  // ── Unhandled promise rejection handler ────────────────────
  window.addEventListener('unhandledrejection', function(event) {
    console.error('[UnhandledRejection]', event.reason);
    // Don't show toast for promise rejections — too noisy
  });

  // ── Reset error counts periodically ────────────────────────
  setInterval(function() { errorCounts = {}; }, 60000);

  console.log('%c✅ Error Boundaries loaded', 'color:#e8a237;font-weight:bold');
})();
