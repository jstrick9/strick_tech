// Bundle equivalence oracle.
//
// The minifier in scripts/build_bundle.py is hand-written, so it needs an
// independent check that it did not change what the code MEANS. This uses a
// real JavaScript parser (acorn) to build an abstract syntax tree of the
// original file and of the minified file, and compares them structurally.
//
// Positions and raw source text are ignored (they are supposed to change);
// everything else -- node types, identifier names, operators, and crucially
// the exact value of every string, template chunk and regex -- must match.
//
// An earlier hand-rolled version of this check compared acorn's character
// offsets (UTF-16 code units) against Python's (code points) and reported
// dozens of false "differences" on any file containing emoji. Comparing the
// trees rather than the offsets removes that entire class of error.
//
// Usage:  node scripts/verify_bundle_ast.js <original.js> <minified.js>
// Exits 0 if equivalent, 1 otherwise (printing the first differing node).

const fs = require('fs');

let acorn;
try {
  acorn = require('acorn');
} catch (e) {
  // acorn is a dev-only convenience. The Python build must not depend on it,
  // so a missing install is reported distinctly (exit 2) and the Python test
  // that shells out to this script skips rather than fails.
  console.error('acorn not installed');
  process.exit(2);
}

// Keys that legitimately differ between the original and the minified file.
const IGNORE = new Set(['start', 'end', 'loc', 'range', 'raw']);

function normalise(node) {
  if (Array.isArray(node)) return node.map(normalise);
  if (node === null || typeof node !== 'object') return node;
  const out = {};
  for (const key of Object.keys(node).sort()) {
    if (IGNORE.has(key)) continue;
    out[key] = normalise(node[key]);
  }
  return out;
}

function parse(file) {
  return acorn.parse(fs.readFileSync(file, 'utf8'), {
    ecmaVersion: 'latest',
    allowReturnOutsideFunction: true,
  });
}

function firstDiff(a, b, path) {
  if (JSON.stringify(a) === JSON.stringify(b)) return null;
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) {
      return `${path}: array length ${a.length} vs ${b.length}`;
    }
    for (let i = 0; i < a.length; i++) {
      const d = firstDiff(a[i], b[i], `${path}[${i}]`);
      if (d) return d;
    }
    return null;
  }
  if (a && b && typeof a === 'object' && typeof b === 'object') {
    const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
    for (const k of [...keys].sort()) {
      const d = firstDiff(a[k], b[k], `${path}.${k}`);
      if (d) return d;
    }
    return null;
  }
  return `${path}: ${JSON.stringify(a)} !== ${JSON.stringify(b)}`;
}

const [, , origFile, minFile] = process.argv;
if (!origFile || !minFile) {
  console.error('usage: verify_bundle_ast.js <original.js> <minified.js>');
  process.exit(2);
}

let a, b;
try {
  a = normalise(parse(origFile));
} catch (e) {
  console.error(`PARSE ERROR in original ${origFile}: ${e.message}`);
  process.exit(2);
}
try {
  b = normalise(parse(minFile));
} catch (e) {
  console.error(`PARSE ERROR in minified ${minFile}: ${e.message}`);
  process.exit(1);
}

const diff = firstDiff(a, b, '$');
if (diff) {
  console.error(`AST DIFFERS: ${diff}`);
  process.exit(1);
}
console.log('AST equivalent');
