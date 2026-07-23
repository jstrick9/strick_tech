// Agentic OS — navigation state boundary
// Keeps route selection independent from DOM rendering while legacy nav wrappers
// continue to compose feature-specific behavior.
'use strict';

(function() {
  const listeners = new Set();
  let current = (window.Store && window.Store.get('currentPane')) || 'chat';

  const state = {
    get: () => current,
    set: (pane) => {
      if (!pane || pane === current) return current;
      const previous = current;
      current = pane;
      if (window.Store) window.Store.set('currentPane', pane);
      listeners.forEach(fn => { try { fn(pane, previous); } catch (_) {} });
      return current;
    },
    subscribe: (fn) => {
      if (typeof fn !== 'function') return () => {};
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
  };

  window.NavigationState = state;
})();
