// Regression guard: three startup paths each fetched
// /api/secrets/get?key=OPENROUTER_API_KEY independently — measured 4
// requests inside the first second of a cold load, all 404s on a fresh
// install (where "not configured" is the normal state). The status now
// flows through one shared helper (getOpenRouterKeyStatus) with in-flight
// de-duplication and a short TTL, invalidated when a key is saved or
// removed so the next poll sees the new truth immediately.
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const SRC = fs.readFileSync(path.join(__dirname, '..', 'js', '01-app-core.js'), 'utf8');

// Every literal fetch of the key-status endpoint in app-core.
const FETCH_SITES = SRC.match(/fetch\('\+?\/api\/secrets\/get\?key=OPENROUTER_API_KEY'/g) || [];

describe('OpenRouter key status is fetched once, through one helper', () => {
  it('exactly one fetch call site remains — inside the shared helper', () => {
    // The helper is the single place allowed to hit this endpoint.
    expect(FETCH_SITES.length).toBe(1);
  });

  it('the helper de-duplicates in-flight and caches within a TTL', () => {
    expect(SRC).toMatch(/function getOpenRouterKeyStatus\(/);
    expect(SRC).toMatch(/_orKeyStatusPromise && Date\.now\(\) - _orKeyStatusAt < maxAgeMs/);
  });

  it('saving and removing a key invalidate the cache', () => {
    expect(SRC).toMatch(/updateKeyStatus\(true\);\s*\n\s*invalidateOpenRouterKeyStatus\(\)/);
    expect(SRC).toMatch(/updateKeyStatus\(false\);\s*\n\s*invalidateOpenRouterKeyStatus\(\)/);
  });

  it('checkKeyStatus and the model-status badge consume the helper, not raw fetches', () => {
    expect(SRC).toMatch(/const j = await getOpenRouterKeyStatus\(\);/);
    expect(SRC).toMatch(/getOpenRouterKeyStatus\(\)\s*\n\s*\]\);/);
  });
});
