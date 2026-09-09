/**
 * #074 — Workstation host panes must lay out as a COLUMN.
 *
 * The workstation refactor (00-workstations.js) groups related panes under a
 * host pane that renders a top tab strip (#ws-tabs-*) plus the absorbed bodies
 * (#ws-bodies > .ws-body). #pane-studio and #pane-galaxy still set
 * `flex-direction:row` from a pre-workstation layout where the studio sidebar
 * and editor sat side by side directly under the pane. Once the workstation
 * moved those into .ws-body (a column), the host's `row` turned the tab strip
 * into a left-hand column and squeezed #ws-bodies to ZERO width — the studio
 * editor, preview and their toolbars clipped off-screen, and the galaxy graph
 * had no width.
 *
 * This fix forces those host panes to column (styles-redesign.css, loaded
 * last, wins the cascade). Source-level regression tests.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const REDESIGN = readFileSync(resolve(__dirname, '../styles-redesign.css'), 'utf8');
const INDEX = readFileSync(resolve(__dirname, '../index.html'), 'utf8');

describe('#074 workstation host panes are laid out as a column', () => {
  it('forces #pane-studio to column (workstation tab strip sits on top)', () => {
    expect(REDESIGN).toMatch(/#pane-studio\s*\{\s*flex-direction:\s*column\s*!important/);
  });

  it('forces #pane-galaxy to column, not the stale pre-workstation row', () => {
    expect(REDESIGN).toMatch(/#pane-galaxy\s*\{\s*flex-direction:\s*column\s*!important/);
  });
});

describe('#074 hierarchy header wraps on mobile', () => {
  it('adds targetable classes to the header action group and tab bar', () => {
    expect(INDEX).toMatch(/class="hier-header-actions"/);
    expect(INDEX).toMatch(/class="hier-tab-bar"/);
  });

  it('wraps the hierarchy header action group and tab bar on mobile', () => {
    expect(REDESIGN).toMatch(/\.hier-header-actions\s*\{\s*flex-wrap:\s*wrap/);
    expect(REDESIGN).toMatch(/\.hier-tab-bar\s*\{\s*flex-wrap:\s*wrap/);
  });
});
