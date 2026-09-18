// r55 regression: the sidebar pane customizer has a Settings entry again.
//
// The customizer (showSidebarCustomizer in 04-workflow-specs, backed by
// profile hidden_panes/pinned_panes + applyHiddenPanes) lost every surface
// entry when the "reclaim bottom real-estate" pass removed its sidebar
// button; the only remaining way in was Account Settings → Preferences →
// "Customize" — three levels deep in the IDENTITY modal, for a NAVIGATION
// feature. Found live while deep-diving the Settings pane as the admin
// persona: the Navigation & Layout tab had exactly two buttons (collapse,
// reset width) and no path to pane visibility at all.
//
// Contract locked here:
//   1. The Navigation & Layout tab carries a #settings-customize-panes-btn
//      wired to showSidebarCustomizer().
//   2. The entry is Power-mode only via the data-ui-mode CSS enforcement
//      layer — hidden_panes are enforced only in power mode
//      (applyHiddenPanes early-returns in simple), so a novice in Simple
//      toggling pane visibility would see nothing change.
//   3. The customizer itself still exists and renders pane rows.
//
// Verified live: button visible in power, opens the customizer (67 pane
// rows), hide/unhide round-trips; hidden in simple; the Account Settings →
// Preferences path still works (unchanged).

const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const read = (f) => fs.readFileSync(path.join(root, f), 'utf8');
const noComments = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

const HTML = read('index.html');
const CSS = noComments(read('styles-extracted.css'));
const SPECS = noComments(read('js/04-workflow-specs.js'));

describe('sidebar customizer Settings entry (r55)', () => {
  test('the Navigation & Layout tab carries the entry button', () => {
    const layout = HTML.slice(
      HTML.indexOf('id="settings-tab-layout"'),
      HTML.indexOf('settings-tab-agents"'));
    expect(layout).toContain('id="settings-customize-panes-btn"');
    expect(layout).toContain('data-act-click="showSidebarCustomizer()"');
  });

  test('the entry is power-mode only via the CSS enforcement layer', () => {
    expect(CSS).toContain('[data-ui-mode="simple"] #settings-customize-panes-btn');
    const m = CSS.match(/\[data-ui-mode="simple"\] #settings-customize-panes-btn\s*\{([^}]*)\}/);
    expect(m).toBeTruthy();
    expect(m[1]).toContain('display: none');
    expect(m[1]).toContain('!important');
  });

  test('the customizer itself still exists and renders pane rows', () => {
    expect(SPECS).toMatch(/function showSidebarCustomizer\s*\(/);
    expect(SPECS).toContain("getElementById('sidebar-customizer')");
    expect(SPECS).toMatch(/cust-row-/);
  });

  test('applyHiddenPanes still defers to simple mode (reason the entry is power-only)', () => {
    expect(SPECS).toMatch(/if \(_UI\.uiMode === 'simple'\) return;/);
  });
});
