
;/* 00-style-hydrate.js */
(function () {
'use strict';
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
var FETCHES = /url\s*\(|image-set\s*\(|expression\s*\(|@import/i;
var Z_LIMIT = 100;
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
if (prop.indexOf('--') !== 0 && !ALLOWED[prop]) continue;
if (FETCHES.test(value)) continue;
if (prop === 'position' && (value === 'fixed' || value === 'absolute')) positioned = true;
if (prop === 'z-index') {
var z = parseInt(value, 10);
if (!isNaN(z) && z > Z_LIMIT) bigZ = true;
}
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
if (positioned && bigZ && invisible && !noPointer) return '';
return out.join(';');
}
function needsHydration(el) {
var attr = el.getAttribute('style');
if (!attr) return false;
return el.style.length === 0;
}
function hydrate(el) {
if (!needsHydration(el)) return false;
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
function adoptStyleElement(el) {
if (!el || el.tagName !== 'STYLE' || el.__adopted) return false;
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
window.__styleHydration = {
count: function () { return hydrated; },
sheets: function () { return sheetsAdopted; },
sanitise: sanitise,
hydrate: hydrate,
active: function () {
var probe = document.createElement('div');
probe.setAttribute('style', 'color:rgb(1,2,3)');
document.documentElement.appendChild(probe);
var blocked = probe.style.length === 0;
probe.remove();
return blocked;
},
};
run();
if (document.readyState === 'loading') {
document.addEventListener('DOMContentLoaded', function () {
hydrateTree(document.documentElement);
adoptTree(document.documentElement);
});
}
})();

;/* 00-theme-boot.js */
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
