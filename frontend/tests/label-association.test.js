// Regression guard: forms paired a bare <label> with the control that
// followed it — visually adjacent, but with no for= (and no wrapping),
// so no assistive technology associated them. The runtime a11y fallback
// then labelled fields with placeholders or machine ids ("gcf-domain",
// "Input field"). The pattern was measured at 51 label/control pairs
// across 11 files. This test fails if a statically-id'd control is ever
// preceded by a bare label again.
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const JS_DIR = path.join(__dirname, '..', 'js');
const LABEL_RE = /<label\b([^>]*)>([\s\S]*?)<\/label>/g;
const CONTROL_RE = /^\s*<(input|select|textarea)\b[^>]*?\bid="([^"${}\\]+)"/;

describe('labels are associated with the controls they introduce', () => {
  it('no bare label directly precedes a statically-id’d control', () => {
    const offenders = [];
    for (const file of fs.readdirSync(JS_DIR).filter(f => f.endsWith('.js'))) {
      const src = fs.readFileSync(path.join(JS_DIR, file), 'utf8');
      let m;
      while ((m = LABEL_RE.exec(src))) {
        const attrs = m[1];
        if (/for=/.test(attrs)) continue;
        if (/<(input|select|textarea)\b/.test(m[2])) continue; // wrapping label
        const cm = CONTROL_RE.exec(src.slice(m.index + m[0].length));
        if (cm) offenders.push(`${file}: label before #${cm[2]}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('the runtime fixer defers to native labels, then sibling labels, before ids', () => {
    const src = fs.readFileSync(path.join(JS_DIR, '11-ux-accessibility.js'), 'utf8');
    expect(src).toMatch(/label\[for="[^"]+"\]/);          // associated label wins
    expect(src).toMatch(/previousElementSibling/);        // sibling label next
    expect(src).toMatch(/placeholder \|\| title \|\| id/); // machine fallback last
  });
});
