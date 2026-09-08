/**
 * Cost bar poller must be registered exactly once (#070).
 *
 * `setInterval(updateCostBar, 30000)` was registered in BOTH the Studio section
 * and the Prompt Library (Sprint 13) section of 01-app-core.js. That fired
 * `/api/cost` twice every 30s for the app's entire lifetime — a permanently
 * duplicated polling loop. `updateCostBar` is idempotent and side-effect free
 * (it only writes the cost into #sb-cost), so the duplicate merely wasted one
 * request per cycle.
 *
 * Guard: exactly one live `setInterval(updateCostBar, 30000)` statement.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const SRC = readFileSync(resolve(__dirname, '../js/01-app-core.js'), 'utf8');

describe('#070 the /api/cost poller is registered exactly once', () => {
  it('has exactly one live setInterval(updateCostBar, 30000) statement', () => {
    // Count lines that START with the interval registration (a live statement),
    // ignoring references inside comments.
    const live = SRC.split('\n').filter(line =>
      /^\s*setInterval\(updateCostBar,\s*30000\)/.test(line)
    );
    expect(live.length).toBe(1);
  });

  it('the function is defined once (single owner)', () => {
    const defs = SRC.match(/async function updateCostBar\(\)/g) || [];
    expect(defs.length).toBe(1);
  });
});
