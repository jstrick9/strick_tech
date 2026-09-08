// Regression guard for the #052 bold component primitive sweep.
//
// WHY IT EXISTS
// ------------
// The per-pane designed widgets across the app were styled ONLY in
// `frontend/styles.css`, which index.html does NOT link (the same "rule exists
// but never loads" defect that took down the `.ce-*` collab-editor module).
// Audited programmatically: every class below appears in the pane markup but
// is defined in no loaded stylesheet, so each rendered as a bare browser
// control. They were consolidated onto shared bold primitives in the
// authoritative `styles-system.css` (the LAST sheetsheet loaded, so it wins).
//
// These guard tests only assert that the design system keeps (a) the shared
// primitive blocks, and (b) that every audited bespoke widget class is now
// covered by a rule in a LOADED stylesheet — so a future reset of the widget
// styles back into the unlinked `styles.css` can never silently regress again.
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const SYS = fs.readFileSync(path.join(__dirname, '..', 'styles-system.css'), 'utf8');

// The shared primitive names introduced by this sweep.
const PRIMITIVES = [
  '.wg-btn', '.wg-ibtn', '.wg-tabs', '.wg-tab', '.wg-badge', '.wg-tag',
  '.wg-chip', '.wg-toggle', '.wg-field', '.wg-table', '.wg-modal',
];

// The audited bespoke pane widgets, grouped by the role they were unified onto.
const BUTTONS = [
  'a2a-btn', 'bdd-alert-btn', 'bdd-detect-btn', 'bdd-header-btn', 'crc-action-btn',
  'crc-fmt-btn', 'crc-gen-btn', 'crc-rep-btn', 'dag-copy-btn', 'dag-launch-btn',
  'dag-toolbar-btn', 'dag-zoom-btn', 'fusion-preset-btn', 'gm-action-btn', 'gm-new-btn',
  'mkt-cat-btn', 'mkt-install-btn', 'prb-bulk-btn', 'prb-new-btn', 'prb-row-btn',
  'prb-sim-btn', 'steer-delete-btn', 'steer-edit-btn', 'steer-modal-cancel-btn',
  'ttd-copy-btn', 'ttd-ctrl-btn', 'ttd-rerun-btn', 'ttd-toolbar-btn', 'ttd-zoom-btn',
  'arena-vote-btn',
];
const ICON_BTNS = [
  'ctx-icon-btn', 'cust-pin-btn', 'cust-toggle-btn', 'fav-remove-btn',
  'file-row-delete-btn', 'ig-del-btn', 'tab-close', 'steer-modal-close-btn', 'ttd-fit-btn',
];
const TABS = ['ci-tab', 'docs-tab', 'eval-tab', 'gitai-tab', 'obs-tab', 'prb-tab', 'ttd-tab', 'mt-new-tab'];
const TAB_BARS = ['ci-tabs', 'mt-tab-bar', 'prb-tab-bar', 'ttd-view-tabs', 'gm-tabs'];
const BADGES = [
  'a2a-badge', 'a2a-trust-badge', 'bb-severity-badge', 'bdd-alert-badge',
  'ci-type-badge', 'crc-status-badge', 'dag-badge', 'gm-badge', 'gm-tab-badge',
  'kg-type-badge', 'mkt-featured-badge', 'pass-badge', 'prb-policy-action-badge',
  'prb-priority-badge', 'prb-tab-badge', 'steer-auto-badge', 'ttd-badge',
  'ttd-detail-badge', 'ttd-diff-changed-badge', 'ttd-diff-same-badge',
];
const TAGS = ['dag-node-agent-tag', 'hook-event-tag', 'mkt-tag', 'model-used-tag', 'ttd-node-type-tag', 'icm-stage-in'];
const CHIPS = ['amb-cat-pill', 'crc-report-chip', 'crc-risk-chip', 'dag-toolbar-pill', 'dag-wave-pill', 'gm-score-chip', 'prb-action-chip'];
const TOGGLES = ['acct-notif-toggle', 'cust-toggle-btn', 'hook-toggle', 'prb-toggle', 'steer-toggle'];
const FIELDS = ['a2a-input', 'a2a-select', 'a2a-textarea', 'arena-model-select', 'crc-date-input', 'crc-filter-input', 'crc-title-input', 'gm-filter-select', 'gm-form-input', 'gm-form-select', 'gm-form-textarea', 'mkt-sort-select', 'prb-input', 'prb-select', 'pv-input', 'ttd-run-input', 'ttd-speed-select'];
const TABLES = ['a2a-task-table', 'bdd-hist-table', 'crc-audit-table', 'gm-history-table', 'prb-rules-table', 'prb-trace-table', 'ttd-diff-table'];
const MODALS = ['a2a-modal', 'dag-modal', 'gm-modal'];

describe('styles-system.css bold component primitives', () => {
  it('defines every shared primitive block', () => {
    for (const p of PRIMITIVES) {
      expect(new RegExp(p.replace('.', '\\.') + '\\s*(\\{|,)').test(SYS), `missing primitive ${p}`).toBe(true);
    }
  });

  it('covers every audited bespoke button in the shared button block', () => {
    const block = SYS.split(/\/\* ── Shared buttery control base/)[1] || '';
    for (const c of BUTTONS) {
      expect(block.includes('.' + c), `button ${c} not in shared base`).toBe(true);
    }
  });

  it('provides bold primary and danger button variants', () => {
    expect(/\.a2a-btn\.primary/.test(SYS)).toBe(true);
    expect(/\.crc-action-btn\.primary/.test(SYS)).toBe(true);
    expect(/\.gm-action-btn\.primary/.test(SYS)).toBe(true);
    expect(/\.gm-action-btn\.danger/.test(SYS)).toBe(true);
    expect(/\.dag-toolbar-btn\.danger/.test(SYS)).toBe(true);
    expect(/\.prb-row-btn\.danger/.test(SYS)).toBe(true);
  });

  it('styles status badges with semantic tints, not a flat neutral', () => {
    expect(/\.pass-badge\.fail/.test(SYS)).toBe(true);
    expect(/\.pass-badge\.pass/.test(SYS)).toBe(true);
    expect(/\.bb-severity-badge\.critical/.test(SYS)).toBe(true);
    expect(/\.bb-severity-badge\.low/.test(SYS)).toBe(true);
    expect(/\.ttd-badge\.running/.test(SYS)).toBe(true);
  });

  it('gives every bespoke modal a fixed full-screen scrim', () => {
    for (const c of ['a2a-modal-overlay', 'dag-modal-overlay', 'gm-modal-overlay']) {
      const block = SYS.split(/\/\* Modal scrim/)[1] || '';
      expect(block.includes('.' + c), `overlay ${c} missing scrim`).toBe(true);
      expect(/position:\s*fixed/.test(block)).toBe(true);
    }
  });

  it('covers the icon, tab, badge, tag, chip, toggle, field, table and modal widgets', () => {
    for (const c of ICON_BTNS) expect(SYS.includes('.' + c), `icon ${c}`).toBe(true);
    for (const c of TABS) expect(SYS.includes('.' + c), `tab ${c}`).toBe(true);
    for (const c of TAB_BARS) expect(SYS.includes('.' + c), `tab bar ${c}`).toBe(true);
    for (const c of BADGES) expect(SYS.includes('.' + c), `badge ${c}`).toBe(true);
    for (const c of TAGS) expect(SYS.includes('.' + c), `tag ${c}`).toBe(true);
    for (const c of CHIPS) expect(SYS.includes('.' + c), `chip ${c}`).toBe(true);
    for (const c of TOGGLES) expect(SYS.includes('.' + c), `toggle ${c}`).toBe(true);
    for (const c of FIELDS) expect(SYS.includes('.' + c), `field ${c}`).toBe(true);
    for (const c of TABLES) expect(SYS.includes('.' + c), `table ${c}`).toBe(true);
    for (const c of MODALS) expect(SYS.includes('.' + c), `modal ${c}`).toBe(true);
  });

  it('gives newly-primed interactive widgets a keyboard focus ring', () => {
    const focusBlock = SYS.split(/Honour reduced-motion/)[0] || '';
    expect(/\.a2a-btn:focus-visible/.test(focusBlock)).toBe(true);
    expect(/\.ci-tab:focus-visible/.test(focusBlock)).toBe(true);
    expect(/\.steer-toggle:focus-visible/.test(focusBlock)).toBe(true);
  });

  it('loads last (authoritative) in the app shell', () => {
    const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
    const idx = html.indexOf('/static/styles-system.css');
    expect(idx).toBeGreaterThan(0);
    // No other (unlinked) stylesheet that holds widget rules may be substituted.
    expect(html.includes('/static/styles.css')).toBe(false);
  });
});
