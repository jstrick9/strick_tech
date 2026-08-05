// Cmd/Ctrl+\ sidebar collapse shortcut.
// Extracted from index.html so that script-src can drop
// 'unsafe-inline'. Execution order is unchanged: this file is loaded
// with defer, after every other deferred script.
// ── Sidebar collapse toggle (⌘\) ───────────────────────────────
document.addEventListener('keydown', function(e) {
  if ((e.metaKey || e.ctrlKey) && e.key === '\\') {
    e.preventDefault();
    var sb = document.getElementById('sidebar');
    if (sb) {
      var collapsed = sb.style.width === '52px' || getComputedStyle(sb).width === '52px';
      sb.style.width = collapsed ? 'var(--sidebar-w)' : '52px';
    }
  }
});


