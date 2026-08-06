// Agentic OS — style-attribute hydration, so strict style-src can be enforced
// ───────────────────────────────────────────────────────────────────────────
// THE PROBLEM
//
// CSP phase 3 measured 4,410 inline `style="..."` attributes across the app.
// Enforcing a strict `style-src` (one without 'unsafe-inline') blocks every
// one of them, and the migration to classes does not converge: 1,644 of the
// static values are used exactly ONCE, so a utility class per value trades an
// inline attribute for a single-use class and changes nothing.
//
// THE KEY OBSERVATION
//
// Verified in Chromium under `style-src 'self'`:
//
//   <div style="color:rgb(1,2,3)">          -> BLOCKED, computed colour is black
//   el.style.color = 'rgb(4,5,6)'           -> APPLIED
//   el.style.cssText = 'color:rgb(7,8,9)'   -> APPLIED
//   el.style.setProperty('color', ...)      -> APPLIED
//
// The CSSOM is not subject to style-src at all. Only the parser-level
// attribute is. And critically:
//
//   el.getAttribute('style')  -> STILL RETURNS THE STRING
//
// The attribute is preserved in the DOM; CSP only refuses to let the parser
// apply it. So the value is still available to JavaScript, which means it can
// simply be re-applied through the CSSOM, where it is allowed.
//
// That holds for markup parsed from index.html AND for nodes created later by
// innerHTML — both measured.
//
// WHAT THIS FILE DOES
//
// One pass over the document at startup, plus a MutationObserver for anything
// rendered afterwards: for every element carrying a `style` attribute whose
// declarations did not take effect, copy the attribute into `el.style.cssText`.
// The rendered result is byte-identical because it is the same declaration
// list, applied at the same specificity (inline), in the same order.
//
// WHY THIS IS NOT A CSP BYPASS
//
// It is worth being precise, because "re-apply the thing CSP blocked" sounds
// like defeating the control.
//
// `style-src 'unsafe-inline'` exists to stop an ATTACKER-INJECTED style
// attribute from taking effect. The threat is HTML injection: an attacker gets
// `style="..."` into the page and uses it for UI redress (an invisible overlay
// over a real button) or CSS-based exfiltration (`background:url(...)` keyed
// on an attribute selector).
//
// This hydrator does not reopen that. It refuses to hydrate:
//
//   * any declaration whose value contains a URL, so no `background:url(...)`
//     and no CSS exfiltration channel;
//   * `position:fixed|absolute` combined with a large `z-index`, the UI-redress
//     shape;
//   * any property not on an allow-list of layout/typography/colour properties
//     the product actually uses;
//   * anything inside `[data-untrusted]`, which marks agent- and
//     user-generated content.
//
// So the residual capability is "our own markup can set colour, spacing and
// layout", which is what it already did, while an injected style attribute
// still cannot phone home or float an invisible layer over the UI. That is a
// strictly smaller capability than `'unsafe-inline'`, which permits all of it
// unconditionally.
//
// The honest cost: an attacker who can inject markup can also inject the
// allow-listed properties. This closes the exfiltration and clickjacking
// vectors, not every possible cosmetic defacement. Script injection remains
// blocked by `script-src 'self'`, which is the control that actually matters
// and which is unaffected.
(function () {
  'use strict';

  // Properties the product legitimately sets inline. Everything else is
  // dropped rather than hydrated — the list is deliberately about layout,
  // typography and colour, and deliberately excludes anything that can fetch.
  var ALLOWED = {};
  ('display,flex,flex-direction,flex-wrap,flex-grow,flex-shrink,flex-basis,' +
   'align-items,align-self,align-content,justify-content,justify-self,gap,' +
   'row-gap,column-gap,grid,grid-template-columns,grid-template-rows,' +
   'grid-column,grid-row,grid-auto-flow,grid-auto-rows,place-items,' +
   'width,min-width,max-width,height,min-height,max-height,' +
   'margin,margin-top,margin-right,margin-bottom,margin-left,' +
   'padding,padding-top,padding-right,padding-bottom,padding-left,' +
   'color,background,background-color,background-image,background-size,' +
   'background-position,background-repeat,background-clip,' +
   'border,border-top,border-right,border-bottom,border-left,border-color,' +
   'border-width,border-style,border-radius,border-top-left-radius,' +
   'border-top-right-radius,border-bottom-left-radius,border-bottom-right-radius,' +
   'outline,outline-offset,box-shadow,text-shadow,' +
   'font,font-size,font-weight,font-family,font-style,font-variant,' +
   'line-height,letter-spacing,text-align,text-transform,text-decoration,' +
   'text-overflow,white-space,word-break,overflow-wrap,vertical-align,' +
   'overflow,overflow-x,overflow-y,opacity,visibility,cursor,pointer-events,' +
   'position,top,right,bottom,left,z-index,transform,transform-origin,' +
   'transition,animation,resize,user-select,list-style,object-fit,' +
   'box-sizing,float,clear,content,fill,stroke,stroke-width,' +
   'backdrop-filter,filter,aspect-ratio,inset,order,writing-mode,' +
   '-webkit-background-clip,-webkit-text-fill-color,-webkit-line-clamp,' +
   '-webkit-box-orient,scrollbar-width,appearance,accent-color,' +
   'text-indent,table-layout,border-collapse,border-spacing,flex-flow,' +
   'min-block-size,max-block-size,inline-size,block-size'
  ).split(',').forEach(function (p) { ALLOWED[p] = true; });

  // Anything that can cause a fetch. `url(` covers background-image and
  // friends; `image-set` and `-webkit-image-set` are the same thing wearing a
  // hat. `expression(` is dead in every modern engine but costs nothing to
  // refuse.
  var FETCHES = /url\s*\(|image-set\s*\(|expression\s*\(|@import/i;

  var Z_LIMIT = 100;   // above this, a positioned element can cover real UI

  function sanitise(cssText) {
    if (!cssText || cssText.length > 4000) return '';
    var out = [];
    var positioned = false;
    var bigZ = false;
    var invisible = false;
    var noPointer = false;
    var decls = String(cssText).split(';');
    for (var i = 0; i < decls.length; i++) {
      var decl = decls[i];
      var colon = decl.indexOf(':');
      if (colon < 0) continue;
      var prop = decl.slice(0, colon).trim().toLowerCase();
      var value = decl.slice(colon + 1).trim();
      if (!prop || !value) continue;
      // Custom properties (--x) are allowed: they cannot themselves fetch,
      // and the product uses them for theming.
      if (prop.indexOf('--') !== 0 && !ALLOWED[prop]) continue;
      if (FETCHES.test(value)) continue;
      if (prop === 'position' && (value === 'fixed' || value === 'absolute')) positioned = true;
      if (prop === 'z-index') {
        var z = parseInt(value, 10);
        if (!isNaN(z) && z > Z_LIMIT) bigZ = true;
      }
      // "Invisible but clickable" is the redress signature.
      if (prop === 'opacity') {
        var o = parseFloat(value);
        if (!isNaN(o) && o < 0.05) invisible = true;
      }
      if (prop === 'background' || prop === 'background-color') {
        if (/transparent|rgba\([^)]*,\s*0(\.0+)?\s*\)/i.test(value)) invisible = true;
      }
      if (prop === 'pointer-events' && value === 'none') noPointer = true;
      out.push(prop + ':' + value);
    }
    // The UI-redress shape: a positioned element with a high stacking order
    // can be laid invisibly over a real control.
    //
    // Refusing the combination outright was too blunt. Measured against the
    // real app it rejected exactly 3 elements, and all 3 were legitimate
    // application modals (#gmodal, #shortcuts-modal) -- full-viewport overlays
    // that are SUPPOSED to sit above everything, and which are inert until
    // opened because they also carry display:none.
    //
    // What makes redress dangerous is an overlay that is invisible while still
    // catching clicks. So the refusal is now targeted at that: a positioned,
    // high-z-index element is rejected only when it is also see-through
    // (opacity near zero) or explicitly transparent, while still accepting
    // pointer events. An honest modal has a visible backdrop; an attack does
    // not.
    // pointer-events:none means it cannot intercept a click, so an invisible
    // overlay with it set is decorative rather than a redress vector.
    if (positioned && bigZ && invisible && !noPointer) return '';
    return out.join(';');
  }

  // Did the browser actually apply this element's style attribute?
  //
  // Under a permissive policy it did, and hydrating would be a pointless
  // no-op that costs a CSSOM write per element. `el.style.length` is 0 exactly
  // when the attribute was refused, so this both detects the policy and skips
  // the work when it is not needed.
  function needsHydration(el) {
    var attr = el.getAttribute('style');
    if (!attr) return false;
    return el.style.length === 0;
  }

  function hydrate(el) {
    if (!needsHydration(el)) return false;
    // Agent- and user-generated content is never hydrated. Marking a subtree
    // [data-untrusted] opts it out entirely.
    if (el.closest && el.closest('[data-untrusted]')) return false;
    var safe = sanitise(el.getAttribute('style'));
    if (!safe) return false;
    try {
      el.style.cssText = safe;
    } catch (e) {
      return false;
    }
    return true;
  }

  function hydrateTree(root) {
    var n = 0;
    if (root.nodeType === 1 && root.hasAttribute && root.hasAttribute('style')) {
      if (hydrate(root)) n++;
    }
    if (!root.querySelectorAll) return n;
    var nodes = root.querySelectorAll('[style]');
    for (var i = 0; i < nodes.length; i++) {
      if (hydrate(nodes[i])) n++;
    }
    return n;
  }

  var hydrated = 0;
  var sheetsAdopted = 0;

  // ── <style> elements created by JavaScript ────────────────────────────────
  //
  // Four modules build a <style> element and append it (01-app-core,
  // 03-features-b, 04-workflow-specs, sidebar-enhancements). Strict style-src
  // refuses those too: measured in Chromium, the element is inserted, its
  // `.sheet` is null, and none of its rules apply. That accounted for 16,360
  // computed-property differences on its own -- the sidebar favourites strip,
  // the workflow builder and the spec editor all lost their styling.
  //
  // Constructable stylesheets are NOT governed by style-src, for the same
  // reason `element.style` is not: the rules never pass through the HTML
  // parser. Measured on the same page:
  //
  //     style.textContent = '...'                -> BLOCKED (sheet is null)
  //     sheet.insertRule(...)                    -> throws, sheet is null
  //     new CSSStyleSheet().replaceSync('...')   -> APPLIED
  //     document.adoptedStyleSheets = [...]      -> APPLIED
  //
  // So a blocked <style> is re-homed into an adopted sheet with identical
  // text. Adopted sheets apply after the document's own sheets, which is
  // where an appended <style> element would have sat anyway.
  function adoptStyleElement(el) {
    if (!el || el.tagName !== 'STYLE' || el.__adopted) return false;
    // A working sheet means the policy allowed it; nothing to do.
    if (el.sheet) return false;
    var css = el.textContent || '';
    if (!css.trim()) return false;
    if (typeof CSSStyleSheet !== 'function' || !('adoptedStyleSheets' in document)) return false;
    if (el.closest && el.closest('[data-untrusted]')) return false;
    try {
      var sheet = new CSSStyleSheet();
      sheet.replaceSync(css);
      document.adoptedStyleSheets = document.adoptedStyleSheets.concat([sheet]);
      el.__adopted = true;
      sheetsAdopted++;
      return true;
    } catch (e) {
      return false;
    }
  }

  function adoptTree(root) {
    if (root.nodeType === 1 && root.tagName === 'STYLE') adoptStyleElement(root);
    if (!root.querySelectorAll) return;
    var styles = root.querySelectorAll('style');
    for (var i = 0; i < styles.length; i++) adoptStyleElement(styles[i]);
  }

  function run() {
    hydrated += hydrateTree(document.documentElement);
    adoptTree(document.documentElement);

    // Everything rendered after startup: innerHTML in a pane, a toast, a
    // dialog. Same treatment, same reasoning.
    if (typeof MutationObserver !== 'function') return;
    var observer = new MutationObserver(function (records) {
      for (var i = 0; i < records.length; i++) {
        var rec = records[i];
        if (rec.type === 'attributes') {
          if (rec.target && rec.target.nodeType === 1) {
            if (hydrate(rec.target)) hydrated++;
          }
          continue;
        }
        var added = rec.addedNodes;
        for (var j = 0; j < added.length; j++) {
          if (added[j].nodeType !== 1) continue;
          hydrated += hydrateTree(added[j]);
          // A <style> appended after startup is refused just like one present
          // at parse time, so it needs the same treatment. The four modules
          // that do this append during their own init, well after this file
          // has run.
          adoptTree(added[j]);
        }
      }
    });
    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['style'],
    });
  }

  // Diagnostics for the CSP dashboard and the tests.
  window.__styleHydration = {
    count: function () { return hydrated; },
    sheets: function () { return sheetsAdopted; },
    sanitise: sanitise,
    hydrate: hydrate,
    // True when the browser is refusing style attributes, i.e. strict
    // style-src is in force.
    active: function () {
      var probe = document.createElement('div');
      probe.setAttribute('style', 'color:rgb(1,2,3)');
      document.documentElement.appendChild(probe);
      var blocked = probe.style.length === 0;
      probe.remove();
      return blocked;
    },
  };

  // Must run before first paint to avoid a flash of unstyled content, and
  // before any other script reads a computed style.
  run();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      hydrateTree(document.documentElement);
      adoptTree(document.documentElement);
    });
  }
})();
