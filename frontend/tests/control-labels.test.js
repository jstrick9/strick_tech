import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const JS = path.join(__dirname, '..', 'js');

// Audit every frontend module for interactive controls that a screen reader
// cannot announce. A control is considered nameable if its open tag carries
// aria-label OR title OR id (id + <label for> / placeholder-association is
// out of scope here — we only require the tag to expose a role/name hook).
const hasName = (openTag) => /aria-label\s*=|\bid\s*=/.test(openTag);

describe('interactive controls expose an accessible name', () => {
  it('no <select> is left without aria-label or id', () => {
    const files = fs.readdirSync(JS).filter(f => f.endsWith('.js'));
    const bad = [];
    for (const f of files) {
      const code = fs.readFileSync(path.join(JS, f), 'utf8').replace(/\/\/[^\n]*/g, '');
      for (const m of code.matchAll(/<select\b[^>]*>/g)) {
        if (!hasName(m[0])) bad.push(f + ': ' + m[0].slice(0, 50));
      }
    }
    expect(bad, 'unlabeled <select>:\n' + bad.join('\n')).toEqual([]);
  });

  it('no text/number/search/email/password input is left without aria-label or id', () => {
    const files = fs.readdirSync(JS).filter(f => f.endsWith('.js'));
    const bad = [];
    for (const f of files) {
      // strip //-comments so documented examples (which aren't rendered) don't trip the scan
      const code = fs.readFileSync(path.join(JS, f), 'utf8').replace(/\/\/[^\n]*/g, '');
      for (const m of code.matchAll(/<input\b[^>]*>/g)) {
        const tag = m[0];
        // skip checkboxes/radios/hidden/submit/buttons — they're named by label/type.
        const type = (tag.match(/type\s*=\s*"([^"]*)"/) || [])[1] || 'text';
        if (['checkbox', 'radio', 'hidden', 'submit', 'button', 'file', 'range'].includes(type)) continue;
        if (!hasName(tag)) bad.push(f + ': ' + tag.slice(0, 55));
      }
    }
    expect(bad, 'unlabeled <input>:\n' + bad.join('\n')).toEqual([]);
  });

  it('no rendered <img> (in source) is missing alt', () => {
    const files = fs.readdirSync(JS).filter(f => f.endsWith('.js'));
    const bad = [];
    for (const f of files) {
      // strip comments so non-rendered/examples don't trip the scan
      const code = fs.readFileSync(path.join(JS, f), 'utf8').replace(/\/\/[^\n]*/g, '');
      for (const m of code.matchAll(/<img\b[^>]*>/g)) {
        if (!/alt\s*=/.test(m[0])) bad.push(f + ': ' + m[0].slice(0, 45));
      }
    }
    expect(bad, '<img> without alt:\n' + bad.join('\n')).toEqual([]);
  });

  it('workflow numeric config inputs still carry aria-label (specific contract)', () => {
    const src = fs.readFileSync(path.join(JS, '03-features-a.js'), 'utf8');
    expect(src).toContain('aria-label="Max tokens"');
    expect(src).toContain('aria-label="Delay seconds"');
    expect(src).toContain('aria-label="Loop iterations"');
  });
});
