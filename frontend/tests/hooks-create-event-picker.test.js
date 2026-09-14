// Frontend correctness: hook creation must pick the event from the typed
// list, not free text.
//
// The backend only fires a fixed set of events (served by
// /api/hooks/events/types — the same list the pane's filter bar uses).
// The old free-text prompt accepted anything, so a typo ("file-save")
// created a hook that rendered fine, toggled fine, and could never fire —
// silently dead forever. Same class as the kgAddEntity/evalRunSuite
// picker fixes.
import { describe, it, expect } from 'vitest';

const fs = require('fs');
const path = require('path');
const SRC = fs.readFileSync(path.join(__dirname, '..', 'js', '03-features-b.js'), 'utf8');

describe('hookCreate picks the event from the typed list', () => {
  const fn = SRC.match(/async function hookCreate[\s\S]*?\n\}/)[0];

  it('fetches the known event types', () => {
    expect(fn).toContain("fetch('/api/hooks/events/types')");
  });

  it('offers a chooser built from the typed list', () => {
    expect(fn).toMatch(/gmChoose\('Hook Event'/);
    expect(fn).toMatch(/td\.events\.map\(e => \(\{ value: e\.id/);
  });

  it('cancel on the chooser means cancel, not create anyway', () => {
    expect(fn).toMatch(/if \(event === null\) return;/);
  });

  it('keeps a free-text fallback only when the types cannot be listed', () => {
    expect(fn).toMatch(/\/\/ Offline fallback/);
    // the fallback prompt must come after the chooser path, not replace it
    expect(fn.indexOf('gmChoose')).toBeLessThan(fn.indexOf("gmPrompt('Event (file_save"));
  });
});
