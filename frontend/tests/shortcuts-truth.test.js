// Regression guard: the help overlay must not lie.
//
// Found in the wild: the backend /api/onboarding/shortcuts feed documented
// "New agent (planned)" and "Run swarm (planned)" for ⌘⇧A / ⌘⇧S while the
// keys were ACTUALLY bound (undocumented) to Arena and Spec Builder; ⌘/ had
// three competing document-level handlers (focus chat input, open the old
// shortcuts modal, navigate to docs) that ALL fired on one keypress; and the
// ⌨️ header button and the ? key opened two different overlays with different
// content. This pins the single-handler, single-overlay, no-lies state.
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const read = (p) => fs.readFileSync(path.join(__dirname, '..', p), 'utf8');
const OVERLAY = read('js/93-shortcuts-overlay.js');
const STUDIO = read('js/02-studio.js');
const SPECS = read('js/04-workflow-specs.js');
const ONBOARDING_PY = read('../backend/routers/onboarding.py');

describe('keyboard shortcut truthfulness', () => {
  it('the help overlay documents the keys Sprint 16 actually binds', () => {
    // js/03-features-b.js binds A→arena, S→specs, H→hooks, G→codeindex
    const features = read('js/03-features-b.js');
    expect(features).toMatch(/e\.key==='A'\) \{ e\.preventDefault\(\); nav\('arena'\)/);
    expect(OVERLAY).toMatch(/'Open Arena'/);
    expect(OVERLAY).toMatch(/'Open Spec Builder'/);
    expect(OVERLAY).toMatch(/'Open Hooks'/);
    expect(OVERLAY).toMatch(/'Open Code Index'/);
  });

  it('no "(planned)" shortcut labels anywhere — document real behaviour or nothing', () => {
    expect(OVERLAY).not.toMatch(/\(planned\)/i);
    expect(ONBOARDING_PY).not.toMatch(/\(planned\)/i);
  });

  it('⌘/ has exactly ONE documented behaviour: focus the chat input (01-app-core)', () => {
    const core = read('js/01-app-core.js');
    expect(core).toMatch(/e\.key === '\/'/); // the focus-chat binding stays
    // the two rogue duplicates are gone (and stay gone)
    expect(STUDIO).not.toMatch(/e\.key === '\/'/);
    expect(SPECS).not.toMatch(/e\.key==='\/'/);
  });

  it('bare "?" is bound only by the shortcuts overlay module', () => {
    expect(OVERLAY).toMatch(/e\.key === '\?'/);
    expect(STUDIO).not.toMatch(/e\.key === '\?'/);
  });

  it('the header ⌨️ button and the palette command open the unified overlay', () => {
    // r95, #259: the showShortcuts() fallback is deleted along with the old
    // #shortcuts-modal; 93-shortcuts-overlay.js owns the only implementation.
    const collab = read('js/32-collaboration.js');
    expect(collab).toMatch(/window\.showKeyboardShortcuts\(\)/);
    expect(collab).not.toMatch(/showShortcuts\s*\(/);
  });

  it('r95: the overlay renders from classes, not per-open inline styles', () => {
    // The enforced `style-src 'self'` refuses parser-level style attributes;
    // the old overlay emitted ~25 per open (hydrator-rescued at a cost).
    // r96, #260: the overlay also joins the platform modal contract —
    // kbd-modal-overlay enrolls it in masterEscapeHandler's teardown and
    // the Tab focus trap (isTrapRoot in 01-app-core.js).
    expect(OVERLAY).toMatch(/className = 'kbs-overlay kbd-modal-overlay'/);
    expect(OVERLAY).not.toMatch(/style="/);
    expect(OVERLAY).not.toMatch(/style\.cssText/);
  });

  it('r95: the fictional shortcuts stay gone', () => {
    // F7/F8 ("Next/Previous diff") were never bound anywhere; Ctrl+Shift+M
    // was removed as a duplicate of Ctrl+Shift+V long before r95.
    expect(OVERLAY).not.toMatch(/'F7'/);
    expect(OVERLAY).not.toMatch(/'F8'/);
    expect(OVERLAY).not.toMatch(/Ctrl', 'Shift', 'M'/);
  });

  it('r96: one key, one action — the resolved double-binds stay resolved', () => {
    const core = read('js/01-app-core.js');
    const evals = read('js/05-evals-observability.js');
    const prompt = read('js/14-prompt-library.js');
    // ⌘⇧E is Health's key alone (07-quality-tools); the evals first-fire is gone
    expect(evals).not.toMatch(/e\.key==='E'/);
    // ⌘⇧P is Profiler's key alone (03-features-a); app-core's studio nav is gone
    expect(core).not.toMatch(/e\.shiftKey && e\.key === 'P'/);
    // ⌘P is the palette's key alone (app-core); the code-search nav is gone
    expect(prompt).not.toMatch(/e\.key==='p'/);
    // ⌘\ is the sidebar toggle's key alone: 90-sidebar-shortcut.js is
    // deleted outright and the split-workspace keydown binding is gone.
    expect(fs.existsSync(path.join(__dirname, '..', 'js', '90-sidebar-shortcut.js'))).toBe(false);
    expect(prompt).not.toContain('e.preventDefault();toggleSplitWorkspace();');
    // ⌘R really reviews: the old guard asked for 'r' WITH shift (never
    // matches — shift makes it 'R'); dead code the overlay documented.
    expect(prompt).toMatch(/e\.key==='r'&&!e\.shiftKey/);
  });

  it('r95: the old #shortcuts-modal and its feeder are deleted', () => {
    // (r96: this used to read '../index.html', which resolves OUTSIDE
    // frontend/ — an ENOENT that failed the test before it asserted anything.)
    const html = read('index.html');
    const core = read('js/01-app-core.js');
    expect(html).not.toMatch(/shortcuts-modal/);
    expect(core).not.toMatch(/function showShortcuts/);
    expect(core).not.toMatch(/shortcuts-modal/);
  });
});
