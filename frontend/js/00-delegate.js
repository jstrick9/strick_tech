// Agentic OS — event delegation shim (v2)
// ───────────────────────────────────────────────────────────────────────────
// Phase 2 of removing `script-src 'unsafe-inline'` from the CSP.
//
// The platform renders 1107 inline event handlers (859 in frontend/js plus
// 248 in index.html, which the first count missed). Every one stops working
// the moment `unsafe-inline` is dropped, because the browser refuses to
// compile an attribute's contents as script.
//
// The usual advice is "replace each with addEventListener". Done literally
// across 1107 sites that are generated inside template strings, that is a very
// large, very silent refactor: a mistyped selector produces a button that
// simply does nothing, with no error anywhere. This review has repeatedly
// found that shape of bug (a control that looks present and does nothing), so
// producing 1107 opportunities for it would be a poor trade.
//
// This shim takes the safer route. Handlers migrate to a data attribute:
//
//     <button onclick="doThing()">        ->  <button data-act-click="doThing()">
//     <input  oninput="f(this.value)">    ->  <input  data-act-input="f($value)">
//
// A single delegated listener per event type reads the matching attribute and
// dispatches it. Crucially the dispatch is NOT `eval` — that would reintroduce
// exactly the injection surface phase 1 closed, and would still need
// 'unsafe-eval' in the CSP. Instead the value is PARSED as a sequence of
// `name(arg, ...)` calls where each argument is a JSON literal or a fixed
// placeholder, and each name is looked up on `window`. Anything that is not a
// plain call of a known function is refused and logged.
//
// That restriction is the point: a `data-act-*` value can never execute
// attacker-supplied code, only *name* a function the application already
// exposes. jsArg() (phase 1) guarantees the arguments are JSON literals.
//
// ── WHY PER-EVENT ATTRIBUTES (v2) ─────────────────────────────────────────
// v1 used a single `data-act` attribute and registered every event type
// against it. That is wrong, and it was caught by a jsdom probe before the
// bulk migration ran: an element converted from `oninput` also fired on
// `click` and on `change`, because the listener could not tell which event the
// author had actually written. Measured on a converted <input>: 3 invocations
// for 1 intended handler. Applied across 546 auto-converted handlers that
// would have been a very large, very quiet behavioural regression — double
// saves, double POSTs, duplicated navigations.
//
// So the event type is part of the attribute name. `data-act-click` fires on
// click and on nothing else.
(function () {
  'use strict';

  // Events that carry a data-act-* equivalent. Kept explicit rather than
  // wildcarding: each entry is a decision about what may be delegated.
  var EVENTS = [
    'click', 'change', 'input', 'dblclick', 'blur', 'focus',
    'mouseover', 'mouseout', 'mousemove', 'keydown', 'keyup', 'submit',
    'dragstart', 'dragend', 'dragover', 'dragleave', 'drop', 'error',
  ];

  // name(json, ...) — the only shape accepted. `?.(` is normalised away first.
  var CALL = /^\s*([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\((.*)\)\s*$/;

  // ── Placeholders ─────────────────────────────────────────────────────────
  // The single biggest category of un-convertible handlers (85 of 313) was
  // arguments read off the element: `f(this.value)`, `f(this.checked)`,
  // `f(this.dataset.policyId)`. Those cannot be JSON literals, but they are
  // also not arbitrary code — they are a tiny, fixed vocabulary of reads from
  // the element the event fired on. Supporting them as *named placeholders*
  // keeps the "no evaluation" guarantee while covering the whole category.
  //
  // A placeholder is resolved by this shim from the element. It is never
  // parsed as JavaScript.
  function resolvePlaceholder(token, el, event) {
    switch (token) {
      case '$value':    return el.value;
      case '$nvalue':   return el.value === '' || el.value == null ? null : Number(el.value);
      case '$checked':  return !!el.checked;
      case '$this':     return el;
      case '$event':    return event;
      case '$text':     return el.textContent;
      case '$id':       return el.id;
      default:
        // $data.someKey -> el.dataset.someKey (plain property read, no eval)
        if (token.indexOf('$data.') === 0) {
          var key = token.slice(6);
          return el.dataset ? el.dataset[key] : undefined;
        }
        // $json.someKey -> JSON.parse(el.dataset.someKey), for structured args
        if (token.indexOf('$json.') === 0) {
          var jkey = token.slice(6);
          var raw = el.dataset ? el.dataset[jkey] : undefined;
          if (raw == null) return undefined;
          try { return JSON.parse(raw); } catch (_) { return undefined; }
        }
        return undefined;
    }
  }

  var PLACEHOLDER = /^\$(?:value|nvalue|checked|this|event|text|id|data\.[\w$]+|json\.[\w$]+)$/;

  // Split a top-level argument list on commas, respecting quotes/nesting.
  function splitArgs(s) {
    var out = [], depth = 0, cur = '', quote = null;
    for (var i = 0; i < s.length; i++) {
      var c = s[i];
      // A backslash-escaped quote belongs to the token and is never a
      // delimiter. Handlers emitted from inside a JS string literal arrive as
      // `nav(\'chat\')`; treating the `\'` as an opening quote left the
      // scanner stuck "inside a string" and the whole call was refused.
      if (c === '\\' && i + 1 < s.length && (s[i + 1] === "'" || s[i + 1] === '"')) {
        cur += s[i] + s[i + 1];
        i++;
        continue;
      }
      if (quote) {
        cur += c;
        if (c === quote) quote = null;
      } else if (c === '"' || c === "'") {
        quote = c; cur += c;
      } else if (c === '(' || c === '[' || c === '{') {
        depth++; cur += c;
      } else if (c === ')' || c === ']' || c === '}') {
        depth--; cur += c;
        if (depth < 0) return null;
      } else if (c === ',' && depth === 0) {
        out.push(cur); cur = '';
      } else {
        cur += c;
      }
    }
    if (depth !== 0 || quote) return null;
    if (cur.trim()) out.push(cur);
    return out;
  }

  function parseArgs(raw, el, event) {
    var trimmed = raw.trim();
    if (!trimmed) return [];
    var parts = splitArgs(trimmed);
    if (parts === null) return null;
    var out = [];
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i].trim();
      if (PLACEHOLDER.test(p)) {
        out.push(resolvePlaceholder(p, el, event));
        continue;
      }
      // Everything else must be a strict JSON literal. JSON.parse gives us
      // that for free: no expressions, no calls, no property access. Single
      // quotes are normalised to double because the codebase writes 'x'.
      var jsonish = p;
      // \'x\' — the attribute was emitted from inside a JS string literal, so
      // its quotes arrived escaped. Unescape before parsing.
      if (p.length >= 4 && p.slice(0, 2) === "\\'" && p.slice(-2) === "\\'") {
        p = "'" + p.slice(2, -2) + "'";
      }
      if (p.length >= 2 && p[0] === "'" && p[p.length - 1] === "'" && p.indexOf('\\') === -1) {
        jsonish = '"' + p.slice(1, -1).replace(/"/g, '\\"') + '"';
      }
      try {
        out.push(JSON.parse(jsonish));
      } catch (_) {
        return null;
      }
    }
    return out;
  }

  function resolve(name) {
    // Dotted paths are supported for namespaced APIs, but only through plain
    // property lookup on window — never through evaluation.
    var ref = window;
    var parts = name.split('.');
    for (var i = 0; i < parts.length; i++) {
      if (ref == null) return null;
      ref = ref[parts[i]];
    }
    return typeof ref === 'function' ? ref : null;
  }

  // Split a body into `;`-separated statements, respecting quotes and nesting.
  // Covers the 20 multi-statement handlers like `nav('templates');closeX()`.
  function splitStatements(body) {
    var out = [], depth = 0, cur = '', quote = null;
    for (var i = 0; i < body.length; i++) {
      var c = body[i];
      // Same escaped-quote handling as splitArgs — see the note there.
      if (c === '\\' && i + 1 < body.length && (body[i + 1] === "'" || body[i + 1] === '"')) {
        cur += body[i] + body[i + 1];
        i++;
        continue;
      }
      if (quote) {
        cur += c;
        if (c === quote) quote = null;
      } else if (c === '"' || c === "'") {
        quote = c; cur += c;
      } else if (c === '(' || c === '[' || c === '{') {
        depth++; cur += c;
      } else if (c === ')' || c === ']' || c === '}') {
        depth--; cur += c;
      } else if (c === ';' && depth === 0) {
        if (cur.trim()) out.push(cur.trim());
        cur = '';
      } else {
        cur += c;
      }
    }
    if (cur.trim()) out.push(cur.trim());
    return out;
  }

  function callOne(stmt, el, event) {
    // `f?.()` is a plain call with an existence guard — the shim already
    // no-ops on an unknown function, so the guard is redundant here. Strip it
    // so optional-call syntax from QUICK_ACTIONS still dispatches.
    var norm = stmt.replace(/\?\.\(/g, '(');
    var m = CALL.exec(norm);
    if (!m) {
      console.warn('[delegate] not a plain call, refusing:', stmt);
      return;
    }
    var fn = resolve(m[1]);
    if (!fn) {
      // Not an error: many handlers guard with `typeof f === 'function'`
      // because the owning pane may not be loaded yet.
      console.warn('[delegate] unknown function:', m[1]);
      return;
    }
    var args = parseArgs(m[2], el, event);
    if (args === null) {
      console.warn('[delegate] arguments are not literals/placeholders, refusing:', stmt);
      return;
    }
    try {
      fn.apply(el, args);
    } catch (err) {
      console.error('[delegate] handler threw:', m[1], err);
    }
  }

  function dispatch(spec, el, event) {
    var stmts = splitStatements(spec);
    for (var i = 0; i < stmts.length; i++) callOne(stmts[i], el, event);
  }

  // ── Declarative intents ──────────────────────────────────────────────────
  // A large share of the remaining handlers were not calls into app code at
  // all — they were tiny DOM manipulations written inline:
  //
  //   this.closest('[style*=fixed]').remove()          (17x)
  //   document.getElementById('x-modal').remove()      (11x)
  //   this.parentElement.remove()                      (4x)
  //   event.stopPropagation()                          (44x, usually a prefix)
  //   if(event.key==='Enter') f()                      (many, mostly index.html)
  //
  // Turning each into a bespoke named function would add ~70 one-line globals
  // for no benefit. They are expressed as attributes instead, so the intent is
  // declarative and the shim performs it — no evaluation involved.
  //
  //   data-close="closest:[style*=fixed]" | "id:my-modal" | "parent" | "self"
  //   data-hide="id:my-modal"       (sets display:none rather than removing)
  //   data-stop="1"                 (stopPropagation before anything else)
  //   data-prevent="1"              (preventDefault)
  //   data-keys="Enter,Space"       (gate a keydown handler on specific keys)
  //   data-click-self="1"           (only fire when the target IS the element,
  //                                  i.e. the `if(event.target===this)` modal
  //                                  backdrop idiom)
  function performClose(el, directive) {
    var target = null;
    if (directive === 'self') {
      target = el;
    } else if (directive === 'parent') {
      target = el.parentElement;
    } else if (directive.indexOf('parent:') === 0) {
      target = el;
      var levels = parseInt(directive.slice(7), 10) || 1;
      for (var i = 0; i < levels && target; i++) target = target.parentElement;
    } else if (directive.indexOf('id:') === 0) {
      target = document.getElementById(directive.slice(3));
    } else if (directive.indexOf('closest:') === 0) {
      target = el.closest ? el.closest(directive.slice(8)) : null;
    }
    if (target && target.remove) target.remove();
  }

  function performHide(el, directive) {
    var target = null;
    if (directive === 'self') target = el;
    else if (directive === 'parent') target = el.parentElement;
    else if (directive.indexOf('id:') === 0) target = document.getElementById(directive.slice(3));
    else if (directive.indexOf('closest:') === 0) target = el.closest ? el.closest(directive.slice(8)) : null;
    if (target && target.style) target.style.display = 'none';
  }

  var KEY_ALIASES = { Space: ' ', Spacebar: ' ' };

  // ── Hover styling ────────────────────────────────────────────────────────
  // `data-hover="bg:var(--bg-3)"` / `data-hover-out="bg:"` replace the
  // `onmouseover="this.style.background=..."` idiom. Values are literals
  // written by the template author, never caller data, and only three
  // properties are supported — anything else was left inline by the migrator.
  var HOVER_PROPS = { bg: 'background', bc: 'borderColor', fg: 'color' };

  function applyHover(el, spec) {
    var decls = spec.split('|');
    for (var i = 0; i < decls.length; i++) {
      var idx = decls[i].indexOf(':');
      if (idx === -1) continue;
      var prop = HOVER_PROPS[decls[i].slice(0, idx)];
      if (prop) el.style[prop] = decls[i].slice(idx + 1);
    }
  }

  function handle(type, event) {
    // Hover and image-error are handled on the event target itself rather
    // than via closest(), because they are element-local presentation.
    var tgt = event.target;
    if (tgt && tgt.getAttribute) {
      if (type === 'mouseover' && tgt.getAttribute('data-hover')) {
        applyHover(tgt, tgt.getAttribute('data-hover'));
      } else if (type === 'mouseout' && tgt.getAttribute('data-hover-out')) {
        applyHover(tgt, tgt.getAttribute('data-hover-out'));
      } else if (type === 'error' && tgt.getAttribute('data-hide-on-error') === '1') {
        tgt.style.display = 'none';
      }
    }

    var el = event.target && event.target.closest
      ? event.target.closest(
          '[data-act-' + type + '],[data-close],[data-hide],[data-self-click]'
        )
      : null;
    if (!el) return;

    // Only act for this element's own registered event type. `data-close` and
    // friends default to click so the common "✕" button needs one attribute.
    var spec = el.getAttribute('data-act-' + type);
    var hasIntent = type === 'click' && (el.hasAttribute('data-close') || el.hasAttribute('data-hide'));
    var hasSelfClick = type !== 'click' && el.getAttribute('data-self-click') === '1';
    if (spec === null && !hasIntent && !hasSelfClick) return;

    // Modal-backdrop idiom: `if (event.target === this) close()`.
    if (el.getAttribute('data-click-self') === '1' && event.target !== el) return;

    // Key gating for keydown handlers.
    var keys = el.getAttribute('data-keys');
    if (keys && type.indexOf('key') === 0) {
      var wanted = keys.split(',').map(function (k) {
        k = k.trim();
        return KEY_ALIASES[k] || k;
      });
      if (wanted.indexOf(event.key) === -1) return;
    }

    if (el.getAttribute('data-stop') === '1' && event.stopPropagation) event.stopPropagation();
    if (el.getAttribute('data-prevent') === '1' && event.preventDefault) event.preventDefault();

    if (spec) dispatch(spec, el, event);

    // Keyboard accessibility idiom: a non-button element made operable with
    // Enter/Space by re-dispatching a click on itself. Guarded against
    // recursion — a click handler that clicks itself would loop forever.
    if (el.getAttribute('data-self-click') === '1' && type !== 'click' && el.click) {
      el.click();
    }

    if (hasIntent) {
      var close = el.getAttribute('data-close');
      if (close) performClose(el, close);
      var hide = el.getAttribute('data-hide');
      if (hide) performHide(el, hide);
    }
  }

  for (var i = 0; i < EVENTS.length; i++) {
    (function (type) {
      // Capture phase so a handler still fires if an ancestor stops
      // propagation. `error` does not bubble, so capture is required there.
      document.addEventListener(type, function (e) { handle(type, e); }, true);
    })(EVENTS[i]);
  }

  // Exposed for tests and for callers that need to trigger the same path.
  window.__delegateDispatch = dispatch;
  window.__delegateHandle = handle;
})();
