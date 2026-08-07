// Derive which frontend modules are safe to load lazily, one chunk per pane.
//
// WHY THIS IS A REAL PARSER AND NOT A CONFIG FILE OR A REGEX
// ──────────────────────────────────────────────────────────
// Two tempting shortcuts were tried and both are wrong for this codebase:
//
// 1. A hand-written "pane -> module" list. That is the exact "rule maintained
//    by hand at a second location" pattern behind repeated bugs in this
//    review: a module gains a dependency, nobody updates the list, and a pane
//    renders blank for whoever opens it.
//
// 2. A regex approximation in Python (to keep the build Node-free). It
//    disagreed with this analysis on 11 files, and disagreed in the DANGEROUS
//    direction: it declared modules safe to defer that `01-app-core.js`
//    actually snapshots during boot. Deferring those breaks their panes with
//    no error at all. Its function-body stripper silently ate real top-level
//    code -- `const wrappedRenders = {...}` vanished entirely. Approximating
//    a JavaScript parser with regular expressions cannot be made trustworthy
//    here, and "conservative enough to be safe" cost roughly half the win.
//
// Node is required only to CHANGE the split, never to run the app: the result
// is committed in frontend/dist/manifest.json, exactly like the bundle itself.
//
// WHAT "SAFE TO LAZY-LOAD" MEANS
// ──────────────────────────────
// These 79 modules have no imports; they communicate through globals. A
// module M may be deferred until its pane opens only if BOTH hold:
//
//   1. Exactly one pane needs it, resolved by mapping each MASTER_PANE_REGISTRY
//      entry to the file providing that renderer.
//
//   2. Nothing references any of its names at LOAD TIME. A reference inside a
//      function body is fine -- by the time it is called, the chunk has
//      loaded. A reference during top-level execution is a hard ordering
//      constraint. `01-app-core.js` contains:
//
//          const wrappedRenders = {
//            dashboard: typeof renderDashboard === 'function' ? renderDashboard : null,
//            ...
//          };
//
//      That captures the function reference while the page boots. Defer
//      36-dashboard.js and the entry becomes null -- the pane silently breaks.
//      Twelve modules are blocked by exactly this and are correctly excluded.
//
// IIFE bodies count as load time, because an IIFE runs immediately. Most of
// these modules are IIFE-wrapped, so getting that wrong in the other
// direction would make everything look trivially safe.
//
// Usage: node scripts/analyse_split.js  ->  JSON plan on stdout

const fs = require('fs');
const path = require('path');

let acorn, walk;
try {
  acorn = require('acorn');
  walk = require('acorn-walk');
} catch (e) {
  console.error('acorn not installed. Run: npm install --no-save acorn acorn-walk');
  process.exit(2);
}

const REPO = path.resolve(__dirname, '..');
const JS_DIR = path.join(REPO, 'frontend', 'js');

// Modules that boot the application. Never deferred regardless of analysis:
// deferring these would mean the page has no navigation with which to request
// them in the first place.
const ALWAYS_EAGER = new Set([
  '00-style-hydrate.js', '00-theme-boot.js', '00-store.js', '00-api-client.js',
  '00-navigation-state.js', '00-csrf.js', '00-delegate.js', '00-handlers.js',
  '00-net-feedback.js', '00-drafts.js', '00-mobile-nav.js', '00-pane-registry.js',
  '00-workstations.js', '00-errors.js', '01-app-core.js',
]);

function parse(src, file) {
  return acorn.parse(src, {
    ecmaVersion: 'latest',
    allowReturnOutsideFunction: true,
    sourceFile: file,
  });
}

// ── What each module provides ──────────────────────────────────────────
// Both `window.X = ...` and a bare top-level declaration, because the
// non-IIFE modules share global scope so their top-level declarations become
// globals implicitly. Missing the second form makes 38 panes look like their
// renderer is defined nowhere.
function providedNames(ast) {
  const names = new Set();
  for (const node of ast.body) {
    if ((node.type === 'FunctionDeclaration' || node.type === 'ClassDeclaration') && node.id) {
      names.add(node.id.name);
    }
    if (node.type === 'VariableDeclaration') {
      for (const d of node.declarations) {
        if (d.id.type === 'Identifier') names.add(d.id.name);
      }
    }
  }
  walk.full(ast, (n) => {
    if (n.type === 'AssignmentExpression' && n.left.type === 'MemberExpression'
        && n.left.object.type === 'Identifier' && n.left.object.name === 'window'
        && !n.left.computed && n.left.property.type === 'Identifier') {
      names.add(n.left.property.name);
    }
  });
  return names;
}

// ── Unguarded bare references ──────────────────────────────────────────
//
// A reference inside a function body is normally safe to defer -- by the time
// it runs, the chunk has loaded. There is one important exception, and it cost
// a round of broken panes before it was added:
//
//     nav = function(pane) {
//       if (pane === 'mcp')   renderMCP();      // bare identifier
//       if (pane === 'loops') renderLoops();
//     };
//
// `01-app-core.js` wraps nav() several times over, and each layer calls
// renderers DIRECTLY by bare identifier, bypassing MASTER_PANE_REGISTRY
// entirely. A bare identifier that was never declared throws ReferenceError --
// it does not quietly evaluate to undefined the way `window.renderMCP` would.
// So these are hard dependencies despite sitting inside a function.
//
// Guarded uses are fine and very common here:
//     if (typeof renderMCP === 'function') renderMCP();
//     window.renderMCP?.()
// Both tolerate the global being absent, so they do not block deferral.
function unguardedBareNames(ast) {
  // Guarding is decided PER CALL SITE, not per file.
  //
  // A first version collected every `typeof x` in the file into one set and
  // treated x as guarded everywhere. That masked a real crash:
  // 01-app-core.js has a guarded call at line 3070
  //
  //     if (typeof renderMCP === 'function') await renderMCP();
  //
  // and a completely unguarded one at line 2434
  //
  //     if (pane === 'mcp') renderMCP();
  //
  // The file-wide set said "guarded", the module was deferred, and opening
  // the MCP pane threw ReferenceError. A guard only protects the statement it
  // encloses, so that is what gets checked here: walking down from each
  // `typeof x` test, every reference to x inside that subtree is protected.
  const guardedNodes = new Set();

  walk.full(ast, (n) => {
    let test = null;
    if (n.type === 'IfStatement') test = n.test;
    else if (n.type === 'ConditionalExpression') test = n.test;
    else if (n.type === 'LogicalExpression' && (n.operator === '&&' || n.operator === '||')) {
      test = n.left;
    }
    if (!test) return;

    // Which names does this test prove are safe?
    const names = new Set();
    walk.full(test, (t) => {
      if (t.type === 'UnaryExpression' && t.operator === 'typeof'
          && t.argument.type === 'Identifier') names.add(t.argument.name);
    });
    if (!names.size) return;

    // Everything in the guarded branch(es) is protected.
    const bodies = [];
    if (n.type === 'IfStatement') { bodies.push(n.consequent); if (n.alternate) bodies.push(n.alternate); }
    else if (n.type === 'ConditionalExpression') { bodies.push(n.consequent, n.alternate); }
    else { bodies.push(n.right); }

    for (const body of bodies) {
      if (!body) continue;
      walk.full(body, (b) => {
        if (b.type === 'Identifier' && names.has(b.name)) guardedNodes.add(b);
      });
    }
  });

  const bare = new Set();
  walk.full(ast, (n) => {
    // `foo()` where foo is a bare identifier.
    if (n.type === 'CallExpression' && n.callee.type === 'Identifier'
        && !guardedNodes.has(n.callee)) {
      bare.add(n.callee.name);
    }
    // `foo.bar` where foo is a bare identifier: reading a property off an
    // undeclared binding throws exactly the same ReferenceError.
    if (n.type === 'MemberExpression' && n.object.type === 'Identifier'
        && n.object.name !== 'window' && !guardedNodes.has(n.object)) {
      bare.add(n.object.name);
    }
  });
  return bare;
}


// ── Load-time vs deferred references ───────────────────────────────────
function referenceSets(ast) {
  const loadTime = new Set();
  const deferred = new Set();

  function record(name, inFn) {
    (inFn ? deferred : loadTime).add(name);
  }

  function visit(node, inFn) {
    if (!node || typeof node.type !== 'string') return;

    if (node.type === 'Identifier') { record(node.name, inFn); return; }

    if (node.type === 'MemberExpression') {
      // `window.foo` reads the global `foo`; `obj.foo` does not.
      if (node.object.type === 'Identifier' && node.object.name === 'window'
          && !node.computed && node.property.type === 'Identifier') {
        record(node.property.name, inFn);
      }
      visit(node.object, inFn);
      if (node.computed) visit(node.property, inFn);
      return;
    }

    // A key in `{ foo: 1 }` is not a reference to `foo`.
    if (node.type === 'Property' && !node.computed) {
      visit(node.value, inFn);
      return;
    }

    const isFn = node.type === 'FunctionDeclaration'
              || node.type === 'FunctionExpression'
              || node.type === 'ArrowFunctionExpression';

    for (const key of Object.keys(node)) {
      if (key === 'start' || key === 'end' || key === 'loc' || key === 'range') continue;
      const child = node[key];
      let childInFn = inFn || isFn;

      // An IIFE's body executes immediately, so it is still load time.
      if (node.type === 'CallExpression' && key === 'callee' && child
          && (child.type === 'FunctionExpression' || child.type === 'ArrowFunctionExpression')) {
        childInFn = inFn;
      }

      if (Array.isArray(child)) child.forEach((c) => visit(c, childInFn));
      else if (child && typeof child.type === 'string') visit(child, childInFn);
    }
  }

  visit(ast, false);
  return { loadTime, deferred };
}

// ── The pane registry ──────────────────────────────────────────────────
function parseRegistry(ast) {
  const panes = {};
  walk.full(ast, (n) => {
    if (n.type === 'AssignmentExpression' && n.left.type === 'MemberExpression'
        && n.left.object.type === 'Identifier' && n.left.object.name === 'window'
        && n.left.property.name === 'MASTER_PANE_REGISTRY') {
      for (const prop of n.right.properties) {
        const key = prop.key.type === 'Literal' ? String(prop.key.value) : prop.key.name;
        const fns = new Set();
        walk.full(prop.value, (m) => {
          if (m.type === 'MemberExpression' && m.object.type === 'Identifier'
              && m.object.name === 'window' && m.property.type === 'Identifier') {
            fns.add(m.property.name);
          }
        });
        panes[key] = [...fns];
      }
    }
  });
  return panes;
}

// ── Analysis ───────────────────────────────────────────────────────────
const files = fs.readdirSync(JS_DIR).filter((f) => f.endsWith('.js')).sort();
const provides = {};
const loadTime = {};
const bareRefs = {};
const sizes = {};

for (const f of files) {
  const src = fs.readFileSync(path.join(JS_DIR, f), 'utf8');
  sizes[f] = Buffer.byteLength(src);
  const ast = parse(src, f);
  provides[f] = providedNames(ast);
  loadTime[f] = referenceSets(ast).loadTime;
  bareRefs[f] = unguardedBareNames(ast);
}

const registry = parseRegistry(
  parse(fs.readFileSync(path.join(JS_DIR, '00-pane-registry.js'), 'utf8'), 'registry'));

const definer = new Map();
for (const f of files) {
  for (const name of provides[f]) {
    if (!definer.has(name)) definer.set(name, new Set());
    definer.get(name).add(f);
  }
}

const paneFiles = {};
for (const [pane, fns] of Object.entries(registry)) {
  const set = new Set();
  for (const fn of fns) for (const f of (definer.get(fn) || [])) set.add(f);
  paneFiles[pane] = set;
}

const owners = new Map();
for (const set of Object.values(paneFiles)) {
  for (const f of set) owners.set(f, (owners.get(f) || 0) + 1);
}

const lazy = {};
const blocked = {};

for (const f of files) {
  if (ALWAYS_EAGER.has(f)) continue;
  if (owners.get(f) !== 1) continue;

  const blockers = files.filter((other) => {
    if (other === f) return false;
    for (const name of provides[f]) {
      if (loadTime[other].has(name)) return true;      // referenced during boot
      if (bareRefs[other].has(name)) return true;      // unguarded bare call
    }
    return false;
  });

  if (blockers.length) { blocked[f] = blockers; continue; }

  const pane = Object.keys(paneFiles).find((p) => paneFiles[p].has(f));
  (lazy[pane] = lazy[pane] || []).push(f);
}

for (const pane of Object.keys(lazy)) lazy[pane].sort();

const lazyFiles = new Set(Object.values(lazy).flat());
const unresolved = Object.keys(registry)
  .filter((p) => registry[p].length && paneFiles[p].size === 0);

console.log(JSON.stringify({
  lazy: Object.fromEntries(Object.entries(lazy).sort()),
  lazyFiles: [...lazyFiles].sort(),
  blocked: Object.fromEntries(Object.entries(blocked).sort()),
  unresolvedPanes: unresolved.sort(),
  lazyBytes: [...lazyFiles].reduce((a, f) => a + sizes[f], 0),
  totalBytes: files.reduce((a, f) => a + sizes[f], 0),
}, null, 2));
