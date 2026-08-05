// Applies the saved theme before first paint.
// Extracted from index.html so that script-src can drop
// 'unsafe-inline'. Execution order is unchanged: this file is loaded
// render-blocking in <head>, before styles apply.
// Apply the saved appearance before styles render. Default is dark mode;
// Auto follows the device without replacing a deliberate user selection.
(function () {
  try {
    var preference = localStorage.getItem('agentic_os_theme') || 'dark';
    var dark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    var effective = preference === 'auto' ? (dark ? 'dark' : 'light') : preference;
    document.documentElement.setAttribute('data-theme', effective);
    document.documentElement.setAttribute('data-theme-preference', preference);
    document.documentElement.style.colorScheme = effective === 'light' ? 'light' : 'dark';
  } catch (e) {}
}());
