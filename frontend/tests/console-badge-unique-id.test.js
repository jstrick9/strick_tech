/**
 * Studio console badge — the two count badges must not share an id (#069).
 *
 * `addConsoleBtn()` created `#console-count-badge` TWICE: once in the console
 * panel header and once inside the Console toggle button. Duplicate ids are
 * invalid HTML; and the flash handler did `getElementById('console-count-badge')`
 * which resolves to the FIRST match only, so the toggle-button badge never
 * updated. (Confirmed live: duplicate #console-count-badge across every pane.)
 *
 * Guard: the two badges must have distinct ids, and the flash handler must
 * update both of them.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const SRC = readFileSync(resolve(__dirname, '../js/01-app-core.js'), 'utf8');

describe('#069 studio console badges use unique ids and both update', () => {
  it('the two badges have distinct ids (no duplicate #console-count-badge)', () => {
    expect(SRC).toContain('id="console-count-badge"');       // panel header badge
    expect(SRC).toContain('id="console-btn-count-badge"');   // toggle button badge
    // The exact duplicate-in-button string is gone.
    expect(SRC).not.toMatch(/btn\.innerHTML\s*=\s*'🔧 Console <span id="console-count-badge"/);
  });

  it('the flash handler updates both badges', () => {
    const i = SRC.indexOf("['console-count-badge', 'console-btn-count-badge']");
    expect(i).toBeGreaterThan(-1);
    const upd = SRC.slice(i, i + 320);
    expect(upd).toContain('console-count-badge');
    expect(upd).toContain('console-btn-count-badge');
    expect(upd).toContain('forEach');
    expect(upd).toContain('badge.textContent = consoleMessages.length');
  });
});
