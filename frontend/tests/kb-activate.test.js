// r48 regression: keyboard-operability sweep.
//
// Context: the delegated dispatcher (00-delegate.js) auto-upgrades every
// [data-act-click] element — tabindex, role, Enter/Space dispatch. But
// controls wired with addEventListener, or template rows served by a
// container-level delegation, are invisible to that upgrade: they were
// mouse-only. The r48 sweep found seven surfaces (chat drawer rows and
// folder headers, dbstudio table rows, workflow list items, skill cards,
// hierarchy project rows, terminal tabs/suggestions, swarm DAG nodes) and
// added window.kbActivate(el, role) — the same contract the delegate gives
// data-act-click elements — plus a call at each wiring/render site.
//
// These are source-shape asserts (with comments stripped first — see the
// r47 lesson in pane-poll-lifecycle.test.js: a file's own explanatory
// comment can quote the literal code being asserted).

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = (f) =>
  readFileSync(join(root, 'js', f), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\/\/[^\n]*/g, '');

describe('r48 kbActivate helper (00-handlers.js)', () => {
  const h = () => src('00-handlers.js');

  it('exposes window.kbActivate', () => {
    expect(h()).toContain('window.kbActivate');
  });

  it('grants the delegate contract: tab stop, role, Enter/Space -> click', () => {
    const s = h();
    expect(s).toContain("setAttribute('tabindex', '0')");
    expect(s).toContain("setAttribute('role', role || 'button')");
    expect(s).toContain("e.key !== 'Enter'");
    expect(s).toContain("el.click()");
    expect(s).toContain('e.preventDefault()');
  });

  it('never downgrades native controls and leaves explicit roles alone', () => {
    const s = h();
    expect(s).toContain("el.tagName === 'BUTTON'");
    expect(s).toContain("el.tagName === 'A'");
    expect(s).toContain("if (!el.getAttribute('role'))");
    expect(s).toContain("if (!el.hasAttribute('tabindex'))");
  });
});

describe('r48 kbActivate call sites', () => {
  it('56-chat-history: session rows and folder headers (both already had focusin handlers)', () => {
    const s = src('56-chat-history.js');
    expect(s).toContain('window.kbActivate(div)');
    expect(s).toContain('window.kbActivate(header)');
  });

  it('17-database-studio: [data-table-idx] rows served by the delegated list listener', () => {
    const s = src('17-database-studio.js');
    expect(s).toContain('#db-table-list [data-table-idx]');
    expect(s).toContain('window.kbActivate(el)');
  });

  it('03-features-a: .wf-list-item rows (action buttons were already native)', () => {
    const s = src('03-features-a.js');
    expect(s).toContain('#wf-list .wf-list-item');
    expect(s).toContain('window.kbActivate(el)');
  });

  it('25-skills: [data-skill-idx] cards served by the grid delegation', () => {
    const s = src('25-skills.js');
    expect(s).toContain('[data-skill-idx]');
    expect(s).toContain('window.kbActivate(el)');
  });

  it('12-information-hierarchy: [data-h-project] rows served by the list delegation', () => {
    const s = src('12-information-hierarchy.js');
    expect(s).toContain('[data-h-project]');
    expect(s).toContain('window.kbActivate(el)');
  });

  it('16-terminal: static tabs, dynamically created tabs, and autocomplete suggestions', () => {
    const s = src('16-terminal.js');
    expect(s).toContain(".terminal-tab').forEach(el => window.kbActivate");
    expect(s).toContain("window.kbActivate(t,'tab')");
    expect(s).toContain("[data-sugg-idx]').forEach(r => window.kbActivate");
  });

  it('26-swarm: DAG nodes with per-element click listeners', () => {
    const s = src('26-swarm.js');
    expect(s).toContain('[data-swarm-node-id]');
    expect(s).toContain('window.kbActivate(el)');
  });
});
