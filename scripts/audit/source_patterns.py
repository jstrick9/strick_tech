#!/usr/bin/env python3
"""Recurring bug patterns, found by parsing the frontend source.

Needs no browser and no server, so it runs anywhere and is the cheapest audit
to keep in CI. Each pattern here corresponds to a bug class that was actually
found and fixed during the review.

  FABRICATED   a failure path that substitutes invented data. Kanban rendered
               "6 tasks" of sample work during an outage; a user could edit or
               delete cards that did not exist.

  RAW-ERROR    a user-visible message built from a raw exception or HTTP
               status as its HEADLINE. "runs.filter is not a function" is a
               stack frame, not an explanation.

  UNGUARDED    an array method called on a parsed response with no check that
               it is an array. A failed request returns an error OBJECT, so
               this throws and the TypeError becomes the user's error message.
               Two real crashes were found this way.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import AuditResult, emit  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
JS_DIR = REPO / 'frontend' / 'js'

NODE_SCRIPT = r'''
const fs = require('fs'), path = require('path');
let acorn, walk;
try { acorn = require('acorn'); walk = require('acorn-walk'); }
catch (e) { console.log(JSON.stringify({error: 'acorn-missing'})); process.exit(0); }

const JS = process.argv[2];
const FABRICATED = /sample|mock|demo|placeholder|dummy|fake|stub/i;
const out = [];

for (const f of fs.readdirSync(JS).filter(x => x.endsWith('.js')).sort()) {
  const src = fs.readFileSync(path.join(JS, f), 'utf8');
  let ast;
  try { ast = acorn.parse(src, {ecmaVersion:'latest', allowReturnOutsideFunction:true}); }
  catch (e) { continue; }
  const line = n => src.slice(0, n.start).split('\n').length;

  // FABRICATED: a failure branch that calls something sample-ish.
  const scanFailure = (node, why) => {
    if (!node) return;
    walk.full(node, n => {
      if (n.type === 'CallExpression' && n.callee.type === 'Identifier'
          && FABRICATED.test(n.callee.name)) {
        out.push({kind:'FABRICATED', file:f, line:line(n),
                  detail:n.callee.name + '() in ' + why});
      }
    });
  };
  walk.full(ast, n => {
    if (n.type === 'TryStatement' && n.handler) scanFailure(n.handler.body, 'catch');
    if (n.type === 'IfStatement' && n.alternate) {
      const t = src.slice(n.test.start, n.test.end);
      if (/\.ok\b/.test(t)) scanFailure(n.alternate, 'else of ' + t.slice(0, 24));
    }
  });

  // UNGUARDED: array method straight off an awaited .json() result.
  walk.full(ast, n => {
    if (n.type !== 'CallExpression') return;
    if (n.callee.type !== 'MemberExpression') return;
    const method = n.callee.property && n.callee.property.name;
    if (!['filter','map','forEach','reduce','slice','sort'].includes(method)) return;
    const obj = n.callee.object;
    if (obj.type !== 'Identifier') return;
    // Did this identifier come from an awaited response body? Two shapes:
    //   const [a, b] = await Promise.all([r.json(), ...])
    //   const a = await r.json()
    // An earlier version matched only the first and therefore missed
    // `const styles = await sR.json()` in 15-image-generation.js, which
    // crashed the pane exactly like the ones it did catch.
    // Follow ONE level of aliasing. `const wsRaw = await r.json();
    // const ws = wsRaw;` puts the array method on a name that never
    // syntactically touched `await`. Without this the detector went blind to
    // a crash it had previously reported -- caught by reverting a real fix
    // and checking the audit still fired.
    const cameFromResponse = (nm) =>
         new RegExp('\\[[^\\]]*\\b' + nm + '\\b[^\\]]*\\]\\s*=\\s*await').test(src)
      || new RegExp('\\b(const|let|var)\\s+' + nm
                    + '\\s*=\\s*await\\b[^;]*\\.json\\(\\)').test(src)
      || new RegExp('\\b(const|let|var)\\s+' + nm
                    + '\\s*=\\s*await\\s+AgenticAPI\\.').test(src);

    let provenance = cameFromResponse(obj.name);
    if (!provenance) {
      const alias = src.match(new RegExp(
        '\\b(?:const|let|var)\\s+' + obj.name + '\\s*=\\s*([A-Za-z_$][\\w$]*)\\s*;'));
      if (alias) provenance = cameFromResponse(alias[1]);
    }
    if (!provenance) return;
    // Is THIS name guarded, and is the guard between the assignment and the
    // use? A whole-file search for `Array.isArray(` was too coarse in both
    // directions: it cleared a file because some OTHER variable was guarded,
    // and it flagged `const ws = Array.isArray(wsRaw) ? ...` because the
    // coercion line itself contains the name. Both produced false positives
    // that cost a round of pointless edits.
    const guarded = new RegExp(
      'Array\\.isArray\\(\\s*' + obj.name + '(Raw)?\\s*\\)');
    if (guarded.test(src)) return;
    // A `.length` check anywhere before this use proves the value is
    // array-like: reading `.length` off a non-array object yields undefined,
    // and `if (!x.length) return;` therefore bails out before reaching the
    // array method. Five sites were flagged because an earlier version only
    // searched up to the ASSIGNMENT rather than up to the USE, so a guard
    // sitting between the two was invisible.
    const lengthChecked = new RegExp(
      '(!|\\.|\\()\\s*' + obj.name + '\\s*(\\?\\.)?\\s*\\.?length');
    if (lengthChecked.test(src.slice(0, n.start))) return;
    // Assigned from an explicit `|| []` fallback.
    const defaulted = new RegExp(
      '\\b' + obj.name + '\\s*=\\s*[^;\\n]*\\|\\|\\s*\\[\\]');
    if (defaulted.test(src)) return;
    // A parameter whose caller already defaulted it, e.g.
    // renderKGList(d.entities || [], el)
    const paramDefaulted = new RegExp(
      '\\(\\s*[^)]*\\|\\|\\s*\\[\\][^)]*\\)');
    const fnDecl = new RegExp('function\\s+\\w+\\s*\\([^)]*\\b' + obj.name + '\\b');
    if (fnDecl.test(src) && paramDefaulted.test(src)) return;
    out.push({kind:'UNGUARDED', file:f, line:line(n),
              detail:obj.name + '.' + method + '() with no Array.isArray guard'});
  });
}
console.log(JSON.stringify(out));
'''

# A headline built from a status code or raw exception. Trailing parenthesised
# detail is the documented place for technical info and is not matched.
RAW_HEADLINE = re.compile(
    r"(Failed to load|Error loading|Load failed|Failed to fetch)"
    r"[^\n]{0,50}(HTTP\s*[$'\"+]|\$\{\s*(e|ex|err|error))",
    re.I)


def _blank_comments(source: str) -> str:
    """Blank out comments while PRESERVING line positions.

    An earlier version deleted comment lines outright, so every reported line
    number was offset by however many comments preceded it -- which sent me
    to the wrong line in all ten files. Replacing each comment with the same
    number of newlines keeps `line = text[:pos].count('\\n') + 1` honest.
    """
    def _same_line_count(match: re.Match) -> str:
        return '\n' * match.group(0).count('\n')

    source = re.sub(r'/\*.*?\*/', _same_line_count, source, flags=re.S)
    return re.sub(r'(?m)^\s*//.*$', '', source)


def run() -> AuditResult:
    findings = []

    node = shutil.which('node')
    if node:
        script = REPO / 'scripts' / 'audit' / '_patterns.tmp.js'
        script.write_text(NODE_SCRIPT, encoding='utf-8')
        try:
            result = subprocess.run([node, str(script), str(JS_DIR)],
                                    cwd=REPO, capture_output=True, text=True)
            data = json.loads(result.stdout or '[]')
            if isinstance(data, dict) and data.get('error') == 'acorn-missing':
                findings.append('SKIP  acorn not installed; AST patterns not checked')
            else:
                for item in data:
                    findings.append(
                        f"{item['kind']:11} {item['file']}:{item['line']}  {item['detail']}")
        finally:
            script.unlink(missing_ok=True)
    else:
        findings.append('SKIP  node not installed; AST patterns not checked')

    for path in sorted(JS_DIR.glob('*.js')):
        code = _blank_comments(path.read_text(encoding='utf-8'))
        for match in RAW_HEADLINE.finditer(code):
            line = code[:match.start()].count('\n') + 1
            findings.append(
                f"RAW-ERROR   {path.name}:{line}  {match.group(0)[:56]}")

    counted = [f for f in findings if not f.startswith('SKIP')]
    return AuditResult(
        'source-patterns',
        len(counted),
        findings,
        note='fabricated data on failure paths, raw errors as headlines, '
             'unguarded array access on parsed responses',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
