/*
 * Agentic OS — Shared inline state components (frontend/js/00-state-feedback.js)
 * Renders the loading / empty / error states that every pane shows inside its
 * body with ONE consistent, accessible pattern instead of each pane hand-rolling
 * its own inline-styled "Loading…" / "No X yet" / "Retry" block.
 *
 *   stateFeedback.setLoading(el, {label})   -> spinner + role=status
 *   stateFeedback.setEmpty(el, {icon,title,message,action,actionLabel})
 *                                          -> empty state (no role, quiet)
 *   stateFeedback.setError(el, {title,message,retry})
 *                                          -> error + role=alert + Retry button
 *   stateFeedback.clearState(el)           -> remove any prior data-state node
 *
 * `action` / `retry` are JS expression strings invoked through the app's
 * delegated `data-act-click` handler (matching the existing pane convention),
 * so they are escaped as attribute values via jsArg.
 */
(function () {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function jsArg(s) {
    return esc(s).replace(/"/g, '&quot;');
  }

  function prefersReducedMotion() {
    try {
      return typeof window.matchMedia === 'function' &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    // eslint-disable-next-line no-unused-vars
    } catch (_) { return false; }
  }

  function idOf(el) {
    return el || document.body;
  }

  // Remove any previously-injected data-state node so replacements don't stack.
  function clearState(el) {
    var root = idOf(el);
    var prev = root.querySelector('.data-state');
    while (prev) {
      prev.remove();
      prev = root.querySelector('.data-state');
    }
  }

  function makeBase(root, className, role) {
    clearState(root);
    var el = document.createElement('div');
    el.className = 'data-state ' + className;
    if (role) el.setAttribute('role', role);
    if (className === 'state-loading') el.setAttribute('aria-live', 'polite');
    if (role === 'alert') el.setAttribute('aria-live', 'assertive');
    root.appendChild(el);
    return el;
  }

  function setLoading(root, opts) {
    opts = opts || {};
    var el = makeBase(root, 'state-loading', 'status');
    if (prefersReducedMotion()) el.classList.add('state-reduced-motion');
    el.innerHTML = loadingHtml(opts.label || 'Loading\u2026');
    if (typeof window.announceToScreenReader === 'function') {
      window.announceToScreenReader(esc(opts.label || 'Loading\u2026'));
    }
    return el;
  }

  // The exact inner markup a loading state uses. Exposed as loadingElement()
  // so panes that render their loading placeholder inside a larger static
  // template can embed the SAME .data-state component markup instead of a
  // hand-rolled inline-styled div — one DOM shape for every loading state.
  function loadingHtml(label) {
    var l = esc(label || 'Loading\u2026');
    return '<span class="data-state-spinner" aria-hidden="true"></span>' +
      '<span class="data-state-copy"><span class="data-state-title">' + l + '</span></span>';
  }

  function loadingElement(label) {
    return '<div class="data-state state-loading" role="status" aria-live="polite">' +
      loadingHtml(label) + '</div>';
  }

  function setEmpty(root, opts) {
    opts = opts || {};
    var el = makeBase(root, 'state-empty', null);
    var icon = opts.icon ? '<span class="data-state-icon" aria-hidden="true">' + esc(opts.icon) + '</span>' : '';
    var action = '';
    if (opts.action) {
      action = '<button type="button" class="btn btn-sm" data-act-click="' + jsArg(opts.action) +
        '">' + esc(opts.actionLabel || opts.action || 'Do it') + '</button>';
    }
    var html = icon + '<div class="data-state-copy">' +
      '<div class="data-state-title">' + esc(opts.title || 'Nothing here yet') + '</div>' +
      (opts.message ? '<div class="data-state-msg">' + esc(opts.message) + '</div>' : '') +
      '</div>' + action;
    el.innerHTML = html;
    return el;
  }

  function setError(root, opts) {
    opts = opts || {};
    var el = makeBase(root, 'state-error', 'alert');
    var title = opts.title || 'Couldn\u2019t load';
    var retry = opts.retry
      ? '<button type="button" class="btn btn-sm" data-act-click="' + jsArg(opts.retry) + '">\u21bb Retry</button>'
      : '';
    el.innerHTML =
      '<span class="data-state-icon" aria-hidden="true">\u26a0\ufe0f</span>' +
      '<div class="data-state-copy">' +
      '<div class="data-state-title">' + esc(title) + '</div>' +
      (opts.message ? '<div class="data-state-msg">' + esc(opts.message) + '</div>' : '') +
      '</div>' + retry;
    if (typeof window.announceToScreenReader === 'function') {
      window.announceToScreenReader(title + (opts.message ? ': ' + opts.message : ''));
    }
    return el;
  }

  window.stateFeedback = { setLoading: setLoading, setEmpty: setEmpty, setError: setError, clearState: clearState, loadingElement: loadingElement };
})();
