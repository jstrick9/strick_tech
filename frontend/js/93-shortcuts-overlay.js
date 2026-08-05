// Keyboard shortcuts help overlay.
// Extracted from index.html so that script-src can drop
// 'unsafe-inline'. Execution order is unchanged: this file is loaded
// with defer, after every other deferred script.
(function() {
  var shortcuts = [
    {group: 'Navigation', items: [
      {keys: ['⌘', 'K'], desc: 'Open command palette'},
      {keys: ['⌘', '\\'], desc: 'Toggle sidebar'},
      {keys: ['⌘', ','], desc: 'Open settings'},
      {keys: ['Esc'], desc: 'Close modals / palette'},
    ]},
    {group: 'Chat', items: [
      {keys: ['Enter'], desc: 'Send message'},
      {keys: ['Shift', 'Enter'], desc: 'New line in message'},
      {keys: ['/'], desc: 'Start slash command'},
    ]},
    {group: 'Quick Nav', items: [
      {keys: ['⌘', '⇧', 'B'], desc: 'Open BugBot'},
      {keys: ['⌘', '⇧', 'N'], desc: 'Open Steering'},
      {keys: ['⌘', '⇧', 'E'], desc: 'Open Health'},
      {keys: ['⌘', '⇧', 'M'], desc: 'Open Marketplace'},
      {keys: ['⌘', '⇧', 'R'], desc: 'Open Replay'},
    ]},
    {group: 'General', items: [
      {keys: ['?'], desc: 'Show this help'},
      {keys: ['⌘', 'S'], desc: 'Save (in editor)'},
    ]},
  ];

  // 01-app-core.js:5440 also defines showKeyboardShortcuts (the older
  // #shortcuts-modal). This grouped overlay has won since it was written: it
  // lived inline in index.html, and inline scripts run after the non-deferred
  // core file. Extracting it to a deferred file keeps the same winner, so
  // behaviour is unchanged -- the clash merely became VISIBLE to
  // lint_globals.py, which scans .js and could not see an inline block.
  // intentional-override: richer grouped overlay supersedes the core modal
  window.showKeyboardShortcuts = function() {
    var existing = document.getElementById('kb-shortcuts-overlay');
    if (existing) { existing.remove(); return; }
    
    var overlay = document.createElement('div');
    overlay.id = 'kb-shortcuts-overlay';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(4,6,14,.85);z-index:10000;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(6px)';
    overlay.onclick = function(e) { if (e.target === overlay) overlay.remove(); };
    
    var html = '<div style="background:var(--bg-2);border:1px solid var(--border-hi);border-radius:16px;max-width:560px;width:100%;max-height:80vh;overflow-y:auto;padding:28px;box-shadow:0 32px 80px rgba(0,0,0,.7)">';
    html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">';
    html += '<h2 style="margin:0;font-size:18px;font-weight:800">⌨️ Keyboard Shortcuts</h2>';
    html += '<button type="button" onclick="document.getElementById(\'kb-shortcuts-overlay\').remove()" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:20px">✕</button>';
    html += '</div>';
    
    shortcuts.forEach(function(group) {
      html += '<div style="margin-bottom:16px">';
      html += '<div style="font-size:11px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">' + group.group + '</div>';
      group.items.forEach(function(item) {
        html += '<div style="display:flex;align-items:center;justify-content:space-between;padding:6px 0">';
        html += '<span style="font-size:13px;color:var(--text-1)">' + item.desc + '</span>';
        html += '<div style="display:flex;gap:4px">';
        item.keys.forEach(function(key) {
          html += '<kbd style="background:var(--bg-3);border:1px solid var(--border);border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600;color:var(--text-2);font-family:inherit;min-width:20px;text-align:center">' + key + '</kbd>';
        });
        html += '</div></div>';
      });
      html += '</div>';
    });
    
    html += '<div style="text-align:center;margin-top:16px;font-size:11px;color:var(--text-3)">Press <kbd style="background:var(--bg-3);border:1px solid var(--border);border-radius:3px;padding:1px 5px;font-size:10px">?</kbd> or <kbd style="background:var(--bg-3);border:1px solid var(--border);border-radius:3px;padding:1px 5px;font-size:10px">Esc</kbd> to close</div>';
    html += '</div>';
    
    overlay.innerHTML = html;
    document.body.appendChild(overlay);
  };

  // Listen for ? key (when not in input)
  document.addEventListener('keydown', function(e) {
    if (e.key === '?' && !e.ctrlKey && !e.metaKey && !e.altKey) {
      var tag = (e.target.tagName || '').toLowerCase();
      if (tag !== 'input' && tag !== 'textarea' && tag !== 'select') {
        e.preventDefault();
        window.showKeyboardShortcuts();
      }
    }
    // Esc to close
    if (e.key === 'Escape') {
      var overlay = document.getElementById('kb-shortcuts-overlay');
      if (overlay) overlay.remove();
    }
  });

  console.log('%c✅ Keyboard Shortcuts overlay loaded (press ? for help)', 'color:#5b8af8;font-weight:bold');
})();
