// Keyboard shortcuts help overlay — the single source of truth for what
// the keys ACTUALLY do (r95, #259).
//
// Two things this file is now responsible for, both pinned by tests:
//
//  1. HONESTY. Every entry below was verified against a real binding in
//     the source (and the ⌘⇧ pane jumps are live-pressed in
//     tests/e2e_browser/test_e2e_browser_12_design_system_p3.py). Three
//     entries the old list carried were fiction and are gone: F7/F8
//     "Next/Previous diff" (never bound anywhere) and Ctrl+Shift+M
//     "Toggle voice mode" (removed as a duplicate of Ctrl+Shift+V long
//     ago). The old list also missed ⌘1–6, ⌘P, Alt+1–7, Alt+Shift+F,
//     ⌘R and ⌘U — all real, all bound.
//
//     r96, #260 — one key, one action. The double-binds #259 documented
//     by their final effect are resolved by deleting the LOSING handler,
//     so every landing pane is unchanged but nothing paints underneath:
//     ⌘⇧E opens Health directly (the dead evals nav in 05-evals is gone),
//     ⌘⇧P opens Profiler directly (app-core's studio nav is gone), ⌘P
//     opens only the palette (the code-search nav in 14-prompt-library is
//     gone), and ⌘\ only toggles the sidebar (90-sidebar-shortcut.js is
//     deleted outright, and 14's split-workspace keydown binding with it —
//     split workspace keeps its buttons and its palette entry). ⌘R now
//     really is "Review current file": its guard used to ask for a
//     lowercase 'r' WITH shift held, which never matches — dead code the
//     overlay documented anyway. See docs/module-reviews/93.
//
//  2. ONE LIST. The backend mirrors (docs_center.KEYBOARD_SHORTCUTS and
//     onboarding's /api/onboarding/shortcuts) must flatten to exactly
//     this list — tests/unit/test_245_help_and_palettes.py parses this
//     file and fails on any divergence.
//
// Rendering is class-based (.kbs-* in styles-tokens.css). The old version
// built ~25 inline style attributes per open, which the enforced
// `style-src 'self'` policy refused on every single open (the hydrator
// re-applied them, at the cost of a refusal burst each time).
//
// Execution order is unchanged: this file is loaded with defer, after
// every other deferred script, and its window.showKeyboardShortcuts
// assignment therefore wins.
(function() {
  var shortcuts = [
    {group: 'Navigation', items: [
      {keys: ['⌘', 'K'], desc: 'Open command palette'},
      {keys: ['⌘', 'P'], desc: 'Open command palette'},
      {keys: ['⌘', '\\'], desc: 'Toggle sidebar'},
      {keys: ['⌘', 'B'], desc: 'Toggle sidebar'},
      {keys: ['⌘', ','], desc: 'Open settings'},
      {keys: ['⌘', '/'], desc: 'Focus chat input'},
      {keys: ['Esc'], desc: 'Close modals / palette'},
      {keys: ['?'], desc: 'Show this help'},
    ]},
    {group: 'Quick nav', items: [
      {keys: ['⌘', '1–6'], desc: 'Chat · Studio · Templates · Kanban · Swarm · Deploy'},
      {keys: ['Alt', '1–7'], desc: 'Chat · Studio · Templates · Swarm · Galaxy · Kanban · Settings'},
    ]},
    {group: 'Jump to pane (⌘⇧ + letter)', items: [
      {keys: ['⌘', '⇧', 'A'], desc: 'Open Arena'},
      {keys: ['⌘', '⇧', 'B'], desc: 'Open BugBot'},
      {keys: ['⌘', '⇧', 'E'], desc: 'Open Health'},
      {keys: ['⌘', '⇧', 'F'], desc: 'Open Model Fusion'},
      {keys: ['⌘', '⇧', 'G'], desc: 'Open Code Index'},
      {keys: ['⌘', '⇧', 'H'], desc: 'Open Hooks'},
      {keys: ['⌘', '⇧', 'I'], desc: 'Open user profile'},
      {keys: ['⌘', '⇧', 'K'], desc: 'Open Knowledge Graph'},
      {keys: ['⌘', '⇧', 'L'], desc: 'Open Leaderboard'},
      {keys: ['⌘', '⇧', 'M'], desc: 'Open Marketplace'},
      {keys: ['⌘', '⇧', 'N'], desc: 'Open AI Guidelines'},
      {keys: ['⌘', '⇧', 'O'], desc: 'Open Observability'},
      {keys: ['⌘', '⇧', 'P'], desc: 'Open Profiler'},
      {keys: ['⌘', '⇧', 'R'], desc: 'Open Replay'},
      {keys: ['⌘', '⇧', 'S'], desc: 'Open Spec Builder'},
      {keys: ['⌘', '⇧', 'W'], desc: 'Open Workflow'},
      {keys: ['⌘', '⇧', 'X'], desc: 'Open Web Search'},
    ]},
    {group: 'Chat', items: [
      {keys: ['Enter'], desc: 'Send message'},
      {keys: ['Shift', 'Enter'], desc: 'New line in message'},
      {keys: ['/'], desc: 'Start slash command'},
    ]},
    {group: 'Studio & files', items: [
      {keys: ['Alt', 'Shift', 'F'], desc: 'Format current file'},
      {keys: ['⌘', 'R'], desc: 'Review current file'},
      {keys: ['⌘', 'U'], desc: 'Share project'},
      {keys: ['⌘', 'Z'], desc: 'Undo (editor)'},
      {keys: ['⌘', '⇧', 'Z'], desc: 'Redo (editor)'},
      {keys: ['Tab'], desc: 'Accept autocomplete (editor)'},
    ]},
    {group: 'Workflow pane', items: [
      {keys: ['⌘', 'S'], desc: 'Save workflow'},
      {keys: ['⌘', 'C'], desc: 'Copy node'},
      {keys: ['⌘', 'V'], desc: 'Paste node'},
      {keys: ['⌘', 'D'], desc: 'Duplicate node'},
      {keys: ['Delete'], desc: 'Delete node'},
    ]},
    {group: 'Multitab pane', items: [
      {keys: ['⌘', 'T'], desc: 'New tab'},
      {keys: ['⌘', 'W'], desc: 'Close tab'},
    ]},
    {group: 'Voice', items: [
      {keys: ['Ctrl', 'Shift', 'V'], desc: 'Toggle voice coding'},
    ]},
  ];

  // r95, #259: the older #shortcuts-modal + showShortcuts() pair in
  // 01-app-core.js is DELETED — this is the only help overlay now, and the
  // header ⌨️ button / palette entry call it directly (32-collaboration.js).
  window.showKeyboardShortcuts = function() {
    var existing = document.getElementById('kb-shortcuts-overlay');
    if (existing) { existing.remove(); return; }

    var overlay = document.createElement('div');
    overlay.id = 'kb-shortcuts-overlay';
    // r96, #260: joins the platform modal contract. The `-modal-overlay`
    // class enrolls this element in collectOpenModals()'s ad-hoc discovery,
    // masterEscapeHandler's teardown (remove + focus restore + toast) and
    // isTrapRoot — so Tab is focus-trapped inside the dialog (WCAG 2.4.3)
    // instead of escaping to the page behind it, and Esc teardown is owned
    // by the same handler every other modal in the app answers to.
    overlay.className = 'kbs-overlay kbd-modal-overlay';
    overlay.addEventListener('click', function(e) { if (e.target === overlay) overlay.remove(); });

    var html = '<div class="kbs-card">';
    html += '<div class="kbs-head">';
    html += '<h2 class="kbs-title">⌨️ Keyboard Shortcuts</h2>';
    html += '<button type="button" data-close="id:kb-shortcuts-overlay" aria-label="Close shortcuts" title="Close shortcuts" class="kbs-close">✕</button>';
    html += '</div>';

    shortcuts.forEach(function(group) {
      html += '<div>';
      html += '<div class="kbs-group-label">' + group.group + '</div>';
      group.items.forEach(function(item) {
        html += '<div class="kbs-row">';
        html += '<span class="kbs-desc">' + item.desc + '</span>';
        html += '<div class="kbs-keys">';
        item.keys.forEach(function(key) {
          html += '<kbd class="kbs-kbd">' + key + '</kbd>';
        });
        html += '</div></div>';
      });
      html += '</div>';
    });

    html += '<div class="kbs-foot">Press <kbd class="kbs-kbd kbs-kbd-sm">?</kbd> or <kbd class="kbs-kbd kbs-kbd-sm">Esc</kbd> to close</div>';
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
    // Esc to close — belt-and-braces. masterEscapeHandler (01-app-core,
    // registered before this file loads) owns the teardown via the
    // kbd-modal-overlay contract: it removes the element, restores focus
    // and toasts. This branch can only matter when the master did not
    // handle the key (e.g. the inspection drawer consumed it first); the
    // double-run is benign — by registration order the element is already
    // gone when this lookup runs.
    if (e.key === 'Escape') {
      var overlay = document.getElementById('kb-shortcuts-overlay');
      if (overlay) overlay.remove();
    }
  });

  console.log('%c✅ Keyboard Shortcuts overlay loaded (press ? for help)', 'color:#5b8af8;font-weight:bold');
})();
