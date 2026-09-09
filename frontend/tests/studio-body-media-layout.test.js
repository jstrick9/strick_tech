/**
 * #075 — Studio body must lay out side-by-side on desktop, stacked+scrollable on mobile.
 *
 * The workstation refactor moved the .studio-sidebar (280px LEFT column,
 * border-right) and #studio-main-area (flex:1) into a COLUMN .ws-body. On
 * desktop that stacked the sidebar ON TOP of the editor, so the main-area
 * (and its 170px console child) swallowed the height and the Monaco editor +
 * live preview collapsed to 0px tall — the desktop studio editor was invisible.
 * On mobile (where the sidebar is taller than the viewport) the flex:1 editor
 * collapsed to 0 and was unreachable.
 *
 * Fix (styles-redesign.css): #ws-body-studio is ROW by default (desktop
 * side-by-side), and stacks to a column with vertical scroll + a real editor
 * height on mobile. Source-level regression tests.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const CSS = readFileSync(resolve(__dirname, '../styles-redesign.css'), 'utf8');

describe('#075 studio body is side-by-side on desktop', () => {
  it('makes #ws-body-studio a row by default (desktop), not the stale column', () => {
    // There must be a top-level (non-media) rule setting ws-body-studio to row.
    const idx = CSS.indexOf('#ws-body-studio { flex-direction: row; }');
    expect(idx).toBeGreaterThan(-1);
    // It must NOT be the mobile override (which sets column). The row rule is
    // authored at top level; the only column setter is inside a @media block.
    expect(CSS).toMatch(/#ws-body-studio\s*\{\s*flex-direction:\s*row\s*;?\s*\}/);
  });

  it('allows the Monaco host real height on mobile (editor panel min-height)', () => {
    // Inside the mobile media block, main-area gets a non-collapsing height.
    const mobile = CSS.slice(CSS.indexOf('@media (max-width: 900px)'));
    expect(mobile).toMatch(/#studio-main-area\s*\{\s*flex:\s*0 0 auto\s*;\s*min-height:\s*480px/);
    expect(mobile).toMatch(/#ws-body-studio\s*\{[^}]*overflow-y:\s*auto/s);
  });
});
