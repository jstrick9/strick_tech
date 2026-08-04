// Agentic OS — event delegation shim
// ───────────────────────────────────────────────────────────────────────────
// Phase 2 of removing `script-src 'unsafe-inline'` from the CSP.
//
// The platform renders 859 inline event handlers (734 of them `onclick`).
// Every one stops working the moment `unsafe-inline` is dropped, because the
// browser refuses to compile an attribute's contents as script.
//
// The usual advice is "replace each with addEventListener". Done literally
// across 859 sites that are generated inside template strings, that is a very
// large, very silent refactor: a mistyped selector produces a button that
// simply does nothing, with no error anywhere. This review has repeatedly
// found that shape of bug (a control that looks present and does nothing), so
// producing 859 opportunities for it would be a poor trade.
//
// This shim takes the safer route. Handlers migrate to a data attribute:
//
//     <button onclick="doThing()">            ->  <button data-act="doThing()">
//     <button onclick="f(${jsArg(x)})">       ->  <button data-act="f(${jsArg(x)})">
//
// A single delegated listener on document reads `data-act` and dispatches it.
// Crucially the dispatch is NOT `eval` — that would reintroduce exactly the
// injection surface phase 1 closed, and would still need 'unsafe-eval' in the
// CSP. Instead the value is PARSED as `name(arg, arg, ...)` where each argument
// must be a JSON literal, and the name is looked up on `window`. Anything that
// is not a plain call of a known function with literal arguments is refused and
// logged.
//
// That restriction is the point: it means a `data-act` value can never execute
// attacker-supplied code, only *name* a function the application already
// exposes. jsArg() (phase 1) guarantees the arguments are JSON literals.
(function () {
  'use strict';

  const ATTR = 'data-act';
  // Events that carry a data-act equivalent. Kept explicit rather than
  // wildcarding: each entry is a decision about what may be delegated.
  const EVENTS = [
    'click', 'change', 'input', 'dblclick', 'blur',
    'mouseover', 'mouseout', 'keydown', 'submit',
  ];

  // name(json, json, ...) — the only shape accepted.
  const CALL = /^\s*([A-Za-z_$][\w$.]*)\s*\((.*)\)\s*$/s;

  function parseArgs(raw) {
    const trimmed = raw.trim();
    if (!trimmed) return [];
    // JSON.parse on an array literal gives us strict JSON semantics for free:
    // no expressions, no function calls, no property access.
    try {
      return JSON.parse('[' + trimmed + ']');
    } catch (_) {
      return null;
    }
  }

  function resolve(name) {
    // Dotted paths are supported for namespaced APIs, but only through plain
    // property lookup on window — never through evaluation.
    let ref = window;
    for (const part of name.split('.')) {
      if (ref == null) return null;
      ref = ref[part];
    }
    return typeof ref === 'function' ? ref : null;
  }

  function dispatch(spec, el, event) {
    const m = CALL.exec(spec);
    if (!m) {
      console.warn('[delegate] not a plain call, refusing:', spec);
      return;
    }
    const fn = resolve(m[1]);
    if (!fn) {
      console.warn('[delegate] unknown function:', m[1]);
      return;
    }
    const args = parseArgs(m[2]);
    if (args === null) {
      console.warn('[delegate] arguments are not JSON literals, refusing:', spec);
      return;
    }
    try {
      fn.apply(el, args);
    } catch (err) {
      console.error('[delegate] handler threw:', m[1], err);
    }
    // `event` is deliberately not forwarded: a handler that needs the event
    // object should be a real listener, not a delegated data-act. Keeping the
    // contract narrow is what makes the parser above safe to reason about.
    void event;
  }

  function onEvent(event) {
    const el = event.target && event.target.closest
      ? event.target.closest('[' + ATTR + ']')
      : null;
    if (!el) return;
    const spec = el.getAttribute(ATTR);
    if (spec) dispatch(spec, el, event);
  }

  for (const type of EVENTS) {
    // Capture phase so a handler still fires if an ancestor stops propagation.
    document.addEventListener(type, onEvent, true);
  }

  // Exposed for tests and for callers that need to trigger the same path.
  window.__delegateDispatch = dispatch;
})();
