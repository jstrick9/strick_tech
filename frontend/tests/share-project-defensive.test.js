/**
 * Prompt Library "Share Your App" — must not throw on a non-JSON 5xx (#068).
 *
 * `shareProject()` did `const j = await r.json()` on the /api/project/share
 * response with no guard. A non-2xx can carry a non-JSON body (e.g. a
 * plain-text "Internal Server Error"), so r.json() threw
 * `Unexpected token 'I'...` — an unhandled rejection surfaced by an automated
 * click-fuzz, instead of a friendly failure toast.
 *
 * Guard: the response is parsed defensively (non-JSON -> null) and the non-ok /
 * null case toasts an error and returns instead of throwing.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const SRC = readFileSync(resolve(__dirname, '../js/14-prompt-library.js'), 'utf8');

describe('#068 shareProject survives a non-JSON 5xx response', () => {
  it('parses the response defensively (does not throw on non-JSON)', () => {
    const fn = SRC.slice(SRC.indexOf('async function shareProject'), SRC.indexOf('}else toast'));
    expect(fn).toMatch(/const r\s*=\s*await fetch\('\/api\/project\/share'/);
    // Must guard the JSON.parse with try/catch, not call r.json() bare.
    expect(fn).toMatch(/try\s*{\s*j\s*=\s*await r\.json\(\);\s*}\s*catch/);
    expect(fn).not.toMatch(/const j\s*=\s*await r\.json\(\);/);
    // Non-ok or null payload must bail with an error toast rather than throw.
    expect(fn).toMatch(/if\s*\(!r\.ok\s*\|\|\s*!j\)/);
    expect(fn).toMatch(/toast\(/);
    expect(fn).toMatch(/return;/);
  });
});
