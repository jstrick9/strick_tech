// Frontend failure honesty: studioSaveFile (manual save, Ctrl+S / 💾 button)
// did none of the things its sibling studioAutoSave (FIX 6) does:
//   - `r.json()` with no try/catch: a 500 with a non-JSON body (crashed
//     proxy, dropped connection) threw an unhandled rejection and the
//     user's own toast never fired — an unsaved edit looked saved.
//   - no r.ok check, and the failure branch toasted a bare 'Save failed',
//     discarding the server's reason ('path traversal', etc).
//     (backend/routers/builder.py documents this exact shape: the ok:false
//     middleware restatuses refusals to 4xx with the body preserved.)
// Verified live before the fix: a 400 with {"error":"path traversal"} gave
// the user '❌ Save failed' and nothing else.
import { describe, it, expect } from 'vitest';

const fs = require('fs');
const path = require('path');
const SOURCE = fs.readFileSync(path.join(__dirname, '..', 'js', '01-app-core.js'), 'utf8');

function fnSource(name) {
  const start = SOURCE.indexOf(`async function ${name}()`);
  expect(start, `function ${name} not found`).toBeGreaterThan(-1);
  const next = SOURCE.indexOf('async function', start + 1);
  return SOURCE.slice(start, next === -1 ? undefined : next);
}

describe('studio manual-save failure honesty', () => {
  it('parses the body inside a try/catch before branching on status', () => {
    const src = fnSource('studioSaveFile');
    const parseIdx = src.indexOf('await r.json()');
    const okIdx = src.indexOf('r.ok && j && j.ok');
    expect(parseIdx).toBeGreaterThan(-1);
    expect(okIdx).toBeGreaterThan(parseIdx);
    // the parse itself is guarded (non-JSON body must not escape)
    expect(src).toMatch(/try \{ j = await r\.json\(\); \} catch/);
  });

  it('surfaces the server reason with the status as fallback', () => {
    const src = fnSource('studioSaveFile');
    expect(src).toContain("(j && j.error) || ('server error ' + r.status)");
    expect(src).not.toMatch(/toast\('Save failed', 'err'\)/);
  });

  it('leads the failure toast with "Couldn\u2019t" so the humanizer keeps the reassurance', () => {
    // toast() routes 'err' messages through humanizeRawError(); a raw lead
    // ("Save failed: server error 500") is rewritten and everything after
    // the status is dropped — which ate the "still in the editor" note
    // (verified live). The "Couldn't" prefix short-circuits the humanizer.
    const src = fnSource('studioSaveFile');
    const toasts = src.match(/toast\(`Couldn't save[^`]*`/g) || [];
    expect(toasts.length).toBe(2); // reason branch + network branch
    for (const t of toasts) {
      expect(t).toContain('still safe in the editor');
    }
  });

  it('network failure is caught and still informs the user', () => {
    const src = fnSource('studioSaveFile');
    const outerCatch = src.indexOf('} catch (e) {', src.indexOf('studioReloadPreview'));
    expect(outerCatch).toBeGreaterThan(-1);
    expect(src.slice(outerCatch)).toContain("Couldn't save");
    expect(src.slice(outerCatch)).toContain("studioMarkAutosave('error')");
  });

  it('failure marks the autosave indicator as error (like autosave does)', () => {
    const src = fnSource('studioSaveFile');
    expect(src).toContain("studioMarkAutosave('error')");
    expect(src).toContain("studioMarkAutosave('saved')");
  });

  it('tells the user the edit survives in the editor', () => {
    const src = fnSource('studioSaveFile');
    expect(src).toContain('still safe in the editor');
  });
});
