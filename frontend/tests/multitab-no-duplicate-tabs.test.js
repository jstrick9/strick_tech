// Frontend correctness: opening a URL that already has a multitab must reuse
// that tab, not stack a duplicate (#143).
//
// mtNewTab always POSTed /api/multitab/tabs, so every open of the same file
// added another tab — nothing deduped, on the client or the server, and the
// persisted runtime state was found carrying 42 copies of the same URL (the
// multitab bar a real user would see filled with duplicates). A plain open
// now activates the existing tab; a genuinely new URL still creates one.
import { describe, it, expect } from 'vitest';

const fs = require('fs');
const path = require('path');
const SOURCE = fs.readFileSync(path.join(__dirname, '..', 'js', '03-features-a.js'), 'utf8');

describe('multitab does not stack duplicate tabs', () => {
  it('mtNewTab reuses an existing tab with the same URL', () => {
    const fn = SOURCE.match(/async function mtNewTab[\s\S]*?\n\}/)[0];
    expect(fn).toContain("(_mtTabs || []).find(t => (t.url || '') === src)");
    expect(fn).toContain('mtActivateTab(existing.id, true)');
    // the reuse must happen before the POST that creates a new tab
    expect(fn.indexOf('(_mtTabs || []).find')).toBeLessThan(fn.indexOf("fetch('/api/multitab/tabs'"));
  });

  it('a tab is still created when no existing tab matches', () => {
    const fn = SOURCE.match(/async function mtNewTab[\s\S]*?\n\}/)[0];
    expect(fn).toMatch(/if \(existing\) \{ await mtActivateTab\(existing\.id, true\); return; \}/);
  });
});
