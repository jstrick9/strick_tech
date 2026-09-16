// Regression guard (r42): quick notes must never silently destroy an
// existing note. The filename is derived from the title alone, so saving
// the same title twice used to POST straight over the earlier file with
// only a success toast. The backend now refuses with 409 unless the caller
// sends overwrite: true — and this pane must (a) send overwrite:false
// first, (b) ask before replacing, (c) re-send with overwrite:true, and
// (d) refuse all-punctuation titles client-side instead of POSTing a
// nameless ".md" junk file.
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const SRC = fs.readFileSync(path.join(__dirname, '..', 'js', '20-obsidian.js'), 'utf8');

describe('saveQuickNote cannot silently overwrite or write junk files', () => {
  it('sends overwrite:false first and only re-sends with overwrite:true after confirming', () => {
    // The send() helper carries the overwrite flag in the body…
    expect(SRC).toMatch(/body:\s*JSON\.stringify\(\{path:\s*filename,\s*content,\s*overwrite\}\)/);
    // …the first attempt is a plain send(false)…
    expect(SRC).toMatch(/let r = await send\(false\)/);
    // …the 409 goes through gmDanger (a real confirmation, not a toast)…
    const idx = SRC.indexOf('if (r.status === 409)');
    expect(idx).toBeGreaterThan(0);
    const branch = SRC.slice(idx, SRC.indexOf('if (!r.ok)', idx));
    expect(branch).toMatch(/gmDanger\('Overwrite Note'/);
    // …declining keeps the existing note…
    expect(branch).toMatch(/if \(!replace\)/);
    // …and only the confirmed retry escalates.
    expect(branch).toMatch(/await send\(true\)/);
  });

  it('rejects titles that slugify to an empty stem before any request', () => {
    expect(SRC).toMatch(/Title needs at least one letter or number/);
    // The guard must run before saveQuickNote builds its request — scope to
    // the function so an earlier fetch in viewNote() doesn't fool the check.
    const fnIdx = SRC.indexOf('async function saveQuickNote');
    expect(fnIdx).toBeGreaterThan(0);
    const fn = SRC.slice(fnIdx, SRC.indexOf('\nasync function ', fnIdx + 10));
    const guardIdx = fn.indexOf('Title needs at least one letter or number');
    const sendIdx = fn.indexOf("fetch('/api/obsidian/note'");
    expect(guardIdx).toBeGreaterThan(0);
    expect(sendIdx).toBeGreaterThan(guardIdx);
  });
});
