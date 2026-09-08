// Automated accessibility regression scan (axe-core) against the static app
// shell. jsdom cannot evaluate color-contrast (axe skips it) but DOES enforce
// structural rules (landmarks, name/content, aria-valid, duplicate-id, alt,
// label, heading-order, etc.) — precisely the regressions that silently return.
import { describe, it, expect } from 'vitest';
import { JSDOM } from 'jsdom';
import fs from 'fs';
import path from 'path';
import * as axe from 'axe-core';

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');

// Strip <script src> and <link href> so jsdom never reaches for the network;
// we want the static DOM structure. Keep the real <html lang/en> + <title>.
const staticHtml = html.replace(/<script\b[^>]*src=[^>]*><\/script>/gi, '')
  .replace(/<link\b[^>]*rel="stylesheet"[^>]*>/gi, '');

describe('axe-core: app shell must have no critical/serious a11y violations', () => {
  it('runs axe against the static shell', async () => {
    const dom = new JSDOM(staticHtml, { runScripts: 'outside-only' });
    const { window } = dom;
    // Inject axe-core inside the jsdom window so its globals match the DOM.
    window.eval(axe.source);
    const options = {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
      rules: {
        'color-contrast': { enabled: false }, // not computable in jsdom
        'region': { enabled: false },          // shell-only scan; region needs full page
      },
    };
    const result = window.eval('axe.run(document, ' + JSON.stringify(options) + ')');
    const violations = (await result).violations.filter(v => v.impact === 'critical' || v.impact === 'serious');
    const summary = violations.map(v => `${v.id}(${v.nodes.length}):${v.nodes.slice(0, 5).map(n => n.target.join(' ')).join(' | ')}`).join('\n');
    expect(summary, summary).toBe('');
  });
});
