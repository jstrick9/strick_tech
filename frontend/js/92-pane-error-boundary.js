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
    errorDiv.style.cssText = 'display:flex;flex-direction:column;align-items:center;justify-content:center;padding:48px;text-align:center;flex:1;margin:20px;border-radius:18px';
    errorDiv.innerHTML = 
      '<div class="neural-orb-3d" style="width:50px;height:50px;margin:0 auto 16px;filter:hue-rotate(140deg)"></div>' +
      '<div style="font-size:18px;font-weight:800;color:var(--text-0);margin-bottom:8px">Workstation Panel Notice</div>' +
      '<div style="font-size:13px;color:var(--text-2);max-width:440px;line-height:1.6;margin-bottom:20px">' +
        'The <strong>' + paneId + '</strong> workstation encountered a rendering check while loading (' + (error || 'status refresh') + '). ' +
        'You can retry initialization or return to active chat.' +
      '</div>' +
      '<div style="display:flex;gap:10px">' +
        '<button type="button" class="btn-3d btn-primary btn-sm" onclick="retryPane(\'' + paneId + '\')" style="padding:8px 18px">↻ Retry Workstation</button>' +
        '<button type="button" class="btn-3d btn-ghost btn-sm" data-act-click="nav(\'chat\')" style="padding:8px 18px">← Back to Chat</button>' +
      '</div>';
    pane.appendChild(errorDiv);
  };

  window.retryPane = function(paneId) {
    var errorDiv = document.querySelector('#pane-' + paneId + ' .pane-error-state');
    if (errorDiv) errorDiv.remove();
    delete _renderErrors[paneId];
    window.nav(paneId);
  };

  // Add helpful empty states for panes that load successfully but have no data
  window.showEmptyState = function(paneId, config) {
    var pane = document.getElementById('pane-' + paneId);
    if (!pane) return;
    var target = pane.querySelector('.page-content') || pane;
    var existing = target.querySelector('.empty-state');
    if (existing) return;
    var emptyDiv = document.createElement('div');
    emptyDiv.className = 'empty-state surface-z1';
    emptyDiv.innerHTML = 
      (config.icon ? '<div class="empty-state__icon">' + config.icon + '</div>' : '<div class="neural-orb-3d" style="width:48px;height:48px;margin:0 auto 16px"></div>') +
      '<div class="empty-state__title">' + (config.title || 'Workstation Ready') + '</div>' +
      '<div class="empty-state__body">' + (config.body || 'This specialist workstation is armed and waiting for your first task.') + '</div>' +
      (config.action ? '<div role="button" tabindex="0" class="empty-state__actions"><button type="button" class="btn-3d btn-primary" onclick="' + config.action + '" data-keys="Enter\, \" data-prevent="1" data-self-click="1">' + (config.actionLabel || '⚡ Launch Task') + '</button></div>' : '');
    target.appendChild(emptyDiv);
  };

  console.log('%c✅ Render Error Handler loaded', 'color:#e8a237;font-weight:bold');
})();
