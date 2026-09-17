// r54 regression: Simple/Power mode has ONE writer.
//
// The mode used to be implemented four times over — 91-mode-switcher (topbar
// + first-run picker, default power), 94-novice-assist (sidebar 💡 + "Show
// all features" footer, default simple), 01-app-core's switchUIMode, and
// 04-workflow-specs' applyUIMode (a third pane list, SIMPLE_MODE_PANES, of
// six panes matching neither the sidebar's data-tier="core" eight nor
// anything else). Three state stores, two opposite defaults, and the CSS
// !important tier rules keyed on data-ui-mode overriding every inline
// display attempt. Live-verified failures this consolidation fixed:
//   * the sidebar footer's "Show all features" flipped its own label while
//     the advanced nav stayed hidden (it never wrote the attr)
//   * a fresh user landed in a state no layer had chosen (attr=simple while
//     localStorage said power and ⚡ showed active)
//   * the 💡 icon and footer showed the mode 94 last knew, not the mode the
//     app is in, after any toggle through the topbar, picker or settings
//
// The contract these tests lock in:
//   1. switchUIMode (01-app-core) is the single writer of data-ui-mode, the
//      single LS store, and the single profile PATCH; it syncs EVERY
//      indicator (topbar active, settings buttons, 94's icon/footer).
//   2. The only other setAttribute('data-ui-mode') calls are the two
//      pre-app-core FALLBACKS, each behind a switchUIMode delegation guard.
//   3. 91 and 94 never manipulate tier visibility inline (CSS owns it), and
//      94 reads the canonical attr — not its own store — for indicator state.
//   4. No module ships a competing pane list; the copy says 8 core features.
//
// Verified live after the consolidation: every toggle path (footer, topbar
// ×2, first-run picker, settings button) lands in a state where attr, both
// LS stores, ✨/⚡ active states, footer visibility, 💡 icon, core 8/8 and
// advanced 0↔18 visibility all agree, and reload restores the profile mode.

const fs = require('fs');
const path = require('path');

const read = (f) => fs.readFileSync(path.join(__dirname, '..', 'js', f), 'utf8');

const CORE = read('01-app-core.js');
const SPECS = read('04-workflow-specs.js');
const MODE = read('91-mode-switcher.js');
const NOVICE = read('94-novice-assist.js');
const SETTINGS = read('57-account-settings.js');

// Comments would let a deleted writer survive as prose; strip them.
const noComments = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

const strip = (src) => noComments(src);

describe('ui-mode single-writer contract (r54)', () => {
  test('01-app-core exposes the canonical switchUIMode writer', () => {
    const src = strip(CORE);
    expect(src).toMatch(/window\.switchUIMode\s*=\s*async function/);
    // writes the attr, the store, and mirrors to the profile
    expect(src).toContain("setAttribute('data-ui-mode', mode)");
    expect(src).toContain("_safeLS.set('agentic_os_mode', mode)");
    expect(src).toContain("body: JSON.stringify({ui_mode: mode})");
  });

  test('switchUIMode syncs every indicator surface', () => {
    const src = strip(CORE);
    // topbar ✨/⚡
    expect(src).toContain("getElementById('mode-simple-btn')");
    expect(src).toContain("getElementById('mode-power-btn')");
    // settings pane buttons + 94's icon/footer
    expect(src).toContain('updateSettingsModeButtons');
    expect(src).toContain('aosSyncModeIndicator');
    // mirrors into 94's store so the two never diverge again
    expect(src).toContain("'aos_novice_assist'");
  });

  test('switchUIMode no longer hides the agents section in simple mode', () => {
    const src = strip(CORE);
    expect(src).not.toContain('sidebar-add-agent');
    expect(src).not.toContain('#agent-list');
  });

  test('only 01 and the two guarded fallbacks may set data-ui-mode', () => {
    const dir = path.join(__dirname, '..', 'js');
    const allowed = new Set([
      '01-app-core.js',
      '04-workflow-specs.js',
      '91-mode-switcher.js',
    ]);
    for (const f of fs.readdirSync(dir)) {
      if (!f.endsWith('.js')) continue;
      const src = noComments(read(f));
      const writes = src.includes("setAttribute('data-ui-mode'");
      if (writes) expect(allowed.has(f)).toBe(true);
      if (!allowed.has(f)) expect(writes).toBe(false);
    }
  });

  test('the two fallback setAttribute calls sit behind delegation guards', () => {
    const specs = strip(SPECS);
    expect(specs).toContain('switchUIMode(mode, { patch: false })');
    const mode = strip(MODE);
    expect(mode).toContain('switchUIMode(mode)');
  });

  test('04-workflow-specs no longer ships a competing pane list', () => {
    const src = strip(SPECS);
    expect(src).not.toContain('SIMPLE_MODE_PANES');
    expect(src).not.toContain('ensureSimpleHeader');
    expect(src).not.toContain('simple-mode-header');
    // the power-user customization survives untouched
    expect(src).toContain('applyHiddenPanes');
    expect(src).toContain('pane-hidden-by-user');
  });

  test('91-mode-switcher defaults a new user to simple and stops styling tiers inline', () => {
    const src = strip(MODE);
    expect(src).toContain("localStorage.getItem(STORAGE_KEY) || 'simple'");
    // the old showAdv() inline loop and its orphan-arrow handling are gone.
    // (statement-bounded: the only remaining style.display in this file is
    // the picker overlay's own dismiss, unrelated to tier elements)
    expect(src).not.toContain('showAdv');
    expect(src).not.toMatch(/data-tier[^;]{0,300}style\.display/);
  });

  test('94-novice-assist delegates and reads the canonical attr, not its store', () => {
    const src = strip(NOVICE);
    expect(src).toContain('window.aosToggleSimpleMode = function');
    expect(src).toContain("window.switchUIMode(simpleOn() ? 'power' : 'simple')");
    expect(src).toContain("getAttribute('data-ui-mode')");
    // indicator-only: no tier/group visibility manipulation
    expect(src).not.toContain('ADVANCED_GROUP_IDS');
    expect(src).not.toMatch(/data-tier[^;]{0,300}style\.display/);
  });

  test('no module toggles tier visibility with inline styles anymore', () => {
    // CSS (styles-extracted.css [data-ui-mode] tier rules) is the only
    // enforcement; inline loops could only leave stale 'none' behind.
    const dir = path.join(__dirname, '..', 'js');
    for (const f of fs.readdirSync(dir)) {
      if (!f.endsWith('.js')) continue;
      const src = noComments(read(f));
      const m = src.match(
        /querySelector(?:All)?\((['"`])[^'"`]*data-tier[^'"`]*\1[^)]*\)[^;]{0,400}?style\.display/
      );
      if (m) throw new Error(`${f} still manipulates tier visibility inline`);
    }
  });

  test('copy says 8 core features, not 7', () => {
    for (const [name, src] of [
      ['91-mode-switcher', MODE],
      ['57-account-settings', SETTINGS],
    ]) {
      expect(noComments(src)).not.toMatch(/7 core|7 Core/);
    }
    expect(noComments(MODE)).toMatch(/8 core|8 Core/);
  });
});
