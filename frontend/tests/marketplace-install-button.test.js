// Regression guard: the marketplace rendered the same pack twice (featured
// strip + all-packs grid) with id="mkt-btn-<packId>" on BOTH copies. Beyond
// the duplicate-ID smell, mktInstallOrUninstall resolved the button with
// getElementById — which returns the FIRST match — so clicking Install in the
// grid flipped the FEATURED card's button to "Installing…" and left the
// clicked one untouched. The cards now carry data-pack-btn and the handler
// updates every card showing that pack, so both views stay in sync.
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const SRC = fs.readFileSync(path.join(__dirname, '..', 'js', '08-replay-collab.js'), 'utf8');

describe('marketplace install/uninstall button wiring', () => {
  it('cards are keyed by data-pack-btn, not a duplicate-prone id', () => {
    expect(SRC).toMatch(/data-pack-btn="\$\{escHtml\(p\.id\)\}"/);
    expect(SRC).not.toMatch(/id="mkt-btn-/);
  });

  it('no getElementById lookup of the old mkt-btn id remains', () => {
    expect(SRC).not.toMatch(/getElementById\(`mkt-btn-/);
  });

  it('the handler resolves buttons through the data attribute, matching on dataset value', () => {
    expect(SRC).toMatch(/function mktButtonsFor\(packId\)/);
    expect(SRC).toMatch(/querySelectorAll\('\[data-pack-btn\]'\)/);
    // no selector interpolation of the pack id — a data attribute comparison,
    // not a string-built CSS selector
    expect(SRC).toMatch(/getAttribute\('data-pack-btn'\) === packId/);
  });

  it('install and uninstall update EVERY card for the pack (featured + grid)', () => {
    const installBlock = SRC.slice(SRC.indexOf('async function mktInstallOrUninstall'));
    expect(installBlock).toMatch(/mktButtonsFor\(packId\)\.forEach/);
    // and nothing narrows it back to a single button
    expect(installBlock.slice(0, 2400)).not.toMatch(/const btn = document\.getElementById/);
  });
});
