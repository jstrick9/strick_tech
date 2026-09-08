/**
 * #072 — collectOpenModals() must use computed visibility and dedupe.
 *
 * Two bugs were in the modal "is open" predicate:
 *
 * 1. It tested INLINE `m.style.display` / `m.style.opacity`. Modals that are
 *    hidden by a STYLESHEET class (e.g. #palette-modal is `display:none` in CSS
 *    until `.open` is added) have an empty inline style, so they were reported
 *    as open on every page even when hidden. That made Escape fire a spurious
 *    `✕ Modal closed` toast with nothing open, and made the Tab focus-trap
 *    consider closed dialogs.
 *
 * 2. The same node could be collected twice (e.g. #agent-modal is both in the
 *    `named` list by id and matched by `.modal-back[style*="flex"]`), so Escape
 *    and the focus-trap ran twice on one element.
 *
 * Fix: test computed visibility (`getComputedStyle().display/visibility`) and
 * dedupe by node identity. Source-level regression tests.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const SRC = readFileSync(resolve(__dirname, '../js/01-app-core.js'), 'utf8');

describe('#072 collectOpenModals uses computed visibility + dedupes', () => {
  it('uses getComputedStyle() rather than inline style to test openness', () => {
    const i = SRC.indexOf('function collectOpenModals');
    expect(i).toBeGreaterThan(-1);
    let depth = 0, end = i;
    for (let k = i; k < SRC.length; k++) {
      if (SRC[k] === '{') depth++;
      else if (SRC[k] === '}') { depth--; if (depth === 0) { end = k; break; } }
    }
    const block = SRC.slice(i, end + 1);
    expect(block).toMatch(/getComputedStyle\(m\)/);
    // The openness test must read computed display and visibility (stylesheet-
    // aware), not an inline-style `m.style.display !== 'none'` check.
    expect(block).toMatch(/cs\.display\s*!==\s*'none'/);
    expect(block).toMatch(/cs\.visibility\s*!==\s*'hidden'/);
  });

  it('dedupes the returned nodes by identity', () => {
    const tail = SRC.slice(SRC.indexOf('function collectOpenModals'));
    expect(tail).toMatch(/new Set\(\)/);
    expect(tail).toMatch(/seen\.add\(m\)/);
    expect(tail).toMatch(/if \(seen\.has\(m\)\) return false/);
  });
});
