// Regression guard: gmPrompt() returns null ONLY on Cancel and '' on
// OK-with-empty. Call sites written as
//
//     const agent = await gmPrompt(... , 'brain') || 'brain';
//
// converted a Cancel into "proceed with the default" — cancelling an eval
// run ran it anyway, cancelling a budget rule created it for ALL agents
// (*), and cancelling the final prompt of a hook edit PATCHed
// condition:null, wiping the stored value. 21 sites across 11 files.
//
// The invariant: gmPrompt's return value must be null-checked before any
// fallback is applied. A call directly followed by `||` cannot be.
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const JS_DIR = path.join(__dirname, '..', 'js');

/** Find every `gmPrompt(`/`gmChoose(` whose closing paren is followed by `||`. */
function fallbackCallSites() {
  const offenders = [];
  for (const file of fs.readdirSync(JS_DIR).filter(f => f.endsWith('.js'))) {
    const src = fs.readFileSync(path.join(JS_DIR, file), 'utf8');
    for (const fn of ['gmPrompt(', 'gmChoose(']) {
      let idx = 0;
      while ((idx = src.indexOf(fn, idx)) !== -1) {
        // balanced-paren scan to the call's real closing paren
        let i = idx + fn.length, depth = 1;
        while (depth && i < src.length) {
          if (src[i] === '(') depth += 1;
          else if (src[i] === ')') depth -= 1;
          i += 1;
        }
        if (/^\s*\|\|/.test(src.slice(i, i + 8))) {
          const line = src.slice(0, idx).split('\n').length;
          offenders.push(`${file}:${line}`);
        }
        idx = i;
      }
    }
  }
  return offenders;
}

describe('gmPrompt cancel semantics', () => {
  it('no call site converts a Cancel into a default (call followed by ||)', () => {
    expect(fallbackCallSites()).toEqual([]);
  });

  it('the representative flows null-check before defaulting', () => {
    // Eval framework now picks the agent via gmChoose (a <select>), so the
    // pinned shape is: cancel returns, and the chosen value is used verbatim
    // (a select can't be "blank-defaulted" — no `.trim() || default` left).
    const evalSrc = fs.readFileSync(path.join(JS_DIR, '55-eval-framework.js'), 'utf8');
    expect(evalSrc).toMatch(/const agentId = await gmChoose\('Run Eval Suite'[^;]*;\s*if \(agentId === null\) return;/);
    // The free-text fallback path (suites unreachable) still honours cancel.
    expect(evalSrc).toMatch(/const s = await gmPrompt\('Suite ID:', 'suite_general'\);\s*if \(s === null\) return;\s*suiteId = s\.trim\(\);/);

    const controlSrc = fs.readFileSync(path.join(JS_DIR, '31-control-tower.js'), 'utf8');
    expect(controlSrc).toMatch(/if \(agentIn === null\) return;\s*\/\/ cancelled — don't create a rule for ALL agents/);

    // the field-wipe case: hook edit must abort on cancel of ANY prompt
    const hooksSrc = fs.readFileSync(path.join(JS_DIR, '03-features-b.js'), 'utf8');
    expect(hooksSrc).toMatch(/const cond\s*= await gmPrompt\('Condition \(optional\):'[\s\S]{0,80}if \(cond === null\) return;/);
  });
});
