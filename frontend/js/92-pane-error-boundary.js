// Global render error boundary for panes.
// Extracted from index.html so that script-src can drop
// 'unsafe-inline'. Execution order is unchanged: this file is loaded
// with defer, after every other deferred script.
(function() {
  // Global error handler for pane rendering
  var _renderCount = {};
  var _renderErrors = {};

  // Override console.warn to track render errors
  var _origWarn = console.warn;
  console.warn = function() {
    var args = Array.prototype.slice.call(arguments);
    var msg = args.join(' ');
    if (msg.indexOf('Render error') !== -1) {
      var pane = msg.match(/for (\w+)/);
      if (pane) _renderErrors[pane[1]] = msg;
    }
    _origWarn.apply(console, args);
  };

  // Add "Report Issue" button to error states
  window.showPaneError = function(paneId, error) {
    var pane = document.getElementById('pane-' + paneId);
    if (!pane) return;
    var existing = pane.querySelector('.pane-error-state');
    if (existing) return; // Don't double-show
    
    var errorDiv = document.createElement('div');
    errorDiv.className = 'pane-error-state card-elevated surface-z2';
    var useShared = (typeof window.stateFeedback !== 'undefined' && window.stateFeedback.errorElement);
    var title = 'This pane hit a snag';
    var message = 'The <strong>' + paneId + '</strong> workstation encountered a rendering check while loading (' + (error || 'status refresh') + '). ' +
        'You can retry initialization or return to active chat.';
    var html = useShared
      ? window.stateFeedback.errorElement({ title: title, message: message }) +
        '<div class="data-state-actions"><button type="button" class="btn btn-primary btn-sm" data-act-click="retryPane(\'' + paneId + '\')">↻ Retry Workstation</button>' +
        '<button type="button" class="btn btn-ghost btn-sm" data-act-click="nav(\'chat\')">← Back to Chat</button></div>'
      : '<div class="data-state state-error" role="alert" aria-live="assertive">' +
        '<span class="data-state-icon" aria-hidden="true">⚠️</span>' +
        '<div class="data-state-copy"><div class="data-state-title">' + title + '</div>' +
        '<div class="data-state-msg">' + message + '</div></div>' +
        '<div class="data-state-actions"><button type="button" class="btn btn-primary btn-sm" data-act-click="retryPane(\'' + paneId + '\')">↻ Retry Workstation</button>' +
        '<button type="button" class="btn btn-ghost btn-sm" data-act-click="nav(\'chat\')">← Back to Chat</button></div></div>';
    errorDiv.style.cssText = 'flex:1;margin:20px;display:flex;flex-direction:column;justify-content:center';
    errorDiv.innerHTML = html;
    pane.appendChild(errorDiv);
  };

  window.retryPane = function(paneId) {
    var errorDiv = document.querySelector('#pane-' + paneId + ' .pane-error-state');
    if (errorDiv) errorDiv.remove();
    delete _renderErrors[paneId];
    window.nav(paneId);
  };

  // Add helpful empty states for panes that load successfully but have no data.
  // Routes through the shared .data-state state-empty component (role=status +
  // aria-live=polite) instead of bespoke .empty-state__* markup.
  window.showEmptyState = function(paneId, config) {
    var pane = document.getElementById('pane-' + paneId);
    if (!pane) return;
    var target = pane.querySelector('.page-content') || pane;
    var existing = target.querySelector('[class*="data-state"], .empty-state');
    if (existing) return;
    var icon = (config.icon || '🛠️');
    var useShared = (typeof window.stateFeedback !== 'undefined' && window.stateFeedback.emptyElement);
    var html = useShared
      ? window.stateFeedback.emptyElement({
          icon: icon,
          title: config.title || 'Workstation Ready',
          message: config.body || 'This specialist workstation is armed and waiting for your first task.',
          action: config.action,
          actionLabel: config.actionLabel || '⚡ Launch Task',
        })
      : // fallback (shared wiring not loaded yet): equivalent .data-state markup
        '<div class="data-state state-empty" role="status" aria-live="polite">' +
          '<span class="data-state-icon" aria-hidden="true">' + (icon || '') + '</span>' +
          '<div class="data-state-copy"><div class="data-state-title">' + (config.title || 'Workstation Ready') + '</div>' +
          '<div class="data-state-msg">' + (config.body || 'This specialist workstation is armed and waiting for your first task.') + '</div></div>' +
          (config.action ? '<button type="button" class="btn btn-primary" data-act-click="' + config.action + '">' + (config.actionLabel || '⚡ Launch Task') + '</button>' : '') +
        '</div>';
    var emptyDiv = document.createElement('div');
    emptyDiv.className = 'surface-z1';
    emptyDiv.innerHTML = html;
    target.appendChild(emptyDiv);
  };

  console.log('%c✅ Render Error Handler loaded', 'color:#e8a237;font-weight:bold');
})();
