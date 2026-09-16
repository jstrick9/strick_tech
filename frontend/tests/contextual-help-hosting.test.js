/**
 * Contextual help button must be hosted in a pane header — never a stray
 * in-flow child of the pane root.
 *
 * Found live (r43 galaxy journey): the "?" help button's header chain ended
 * with `|| container`, and 27 panes have no .section-head/.chat-header/h2
 * (kanban's title is an h1, galaxy's a span, many JS panes render their
 * header async). For those panes the button was appended directly to the
 * pane root as an in-flow flex child: a stray "?" row at the pane's
 * bottom-left, clipped off-pane (galaxy measured 8px of phantom scroll) and
 * stealing layout space / intercepting clicks.
 *
 * The fix: the chain matches h1 and an opt-in .ctx-help-anchor class, ends
 * WITHOUT a container fallback (no header -> no button), and
 * _attachContextualHelpToPane retries once after 1200ms so async-rendered
 * headers still get the button. Galaxy/inbox/audit-log ship anchors.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const read = f => readFileSync(resolve(__dirname, '..', f), 'utf8');
const SRC = read('js/04-workflow-specs.js');
const INBOX = read('js/60-inbox.js');
const AUDIT = read('js/46-compliance-report.js');
const INDEX = read('index.html');
const REDESIGN = read('styles-redesign.css');

function fn(name) {
  const i = SRC.indexOf('function ' + name);
  if (i < 0) return '';
  const j = SRC.indexOf('\n}', i);
  return SRC.slice(i, j < 0 ? SRC.length : j + 2);
}

describe('contextual help button is hosted in a header, never on the pane root', () => {
  it('addContextualHelp matches h1 and opt-in anchors, and has no container fallback', () => {
    const body = fn('addContextualHelp');
    expect(body.length).toBeGreaterThan(10);
    expect(body).toMatch(/\.chat-header,\s*h1,\s*h2/);
    expect(body).toMatch(/\.ctx-help-anchor/);
    // The old chain ended with `|| container` — that injected a stray in-flow
    // button into the pane root for 27 headerless panes. It must not return.
    expect(body).not.toMatch(/\|\|\s*container\s*;/);
    // No header -> render nothing.
    expect(body).toMatch(/if\s*\(!header\)\s*return\s*;/);
  });

  it('_attachContextualHelpToPane retries once for async-rendered headers', () => {
    const body = fn('_attachContextualHelpToPane');
    expect(body).toMatch(/setTimeout/);
    expect(body).toMatch(/1200/);
    expect(body).toMatch(/querySelector\('\.ctx-help-btn'\)/);
  });

  it('headerless panes ship a .ctx-help-anchor host (galaxy, inbox, audit-log)', () => {
    expect(INDEX).toMatch(/class="ctx-help-anchor"[^>]*>🌌 Memory Galaxy/);
    expect(INBOX).toMatch(/class="ctx-help-anchor"[^>]*>📥 Inbox/);
    expect(AUDIT).toMatch(/crc-header-title ctx-help-anchor/);
  });
});

describe('galaxy pane: graph beside the panel (workstation column fix, #075 family)', () => {
  it('#ws-body-galaxy lays out as a row on desktop', () => {
    expect(REDESIGN).toMatch(/#ws-body-galaxy\s*\{\s*flex-direction:\s*row\s*;\s*\}/);
  });
  it('mobile falls back to a scrolling column with a usable graph height', () => {
    const row = REDESIGN.search(/#ws-body-galaxy\s*\{\s*flex-direction:\s*row\s*;\s*\}/);
    expect(row).toBeGreaterThan(0);
    // the @media (max-width: 900px) block with the mobile fallback follows the
    // desktop rule in this section of the file
    const after = REDESIGN.slice(row, row + 2500);
    expect(after).toMatch(/@media\s*\(max-width:\s*900px\)/);
    expect(after).toMatch(/#ws-body-galaxy\s*\{\s*flex-direction:\s*column/);
    expect(after).toMatch(/#galaxy-container\s*\{\s*min-height:\s*420px/);
  });;
});
