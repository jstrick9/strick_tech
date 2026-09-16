// Regression guard (r47): pane-poll lifecycle. Two pollers misbehaved in the
// timer sweep:
//   1. System Monitor (38): its 10s interval had NO inactive guard — once the
//      pane was opened it polled /api/system/{health,metrics,git} for the
//      rest of the app session (verified live: still firing 25s after
//      navigating away).
//   2. Control Tower (31): renderControlTower assigned its interval handle
//      AFTER an await — two overlapping renders interleaved as clear/A,
//      clear/B, set-t1, set-t2, leaking t1 forever (its inactive guard only
//      ever clears the module variable, which by then held t2). A
//      render-generation token now makes the newest render the sole owner.
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const j = (f) => fs.readFileSync(path.join(__dirname, '..', 'js', f), 'utf8')
  .replace(/\/\/[^\n]*/g, '')        // strip line comments (prose quotes code)
  .replace(/\/\*[\s\S]*?\*\//g, ''); // strip block comments

describe('system monitor stops polling when its pane is inactive (r47)', () => {
  it('refreshSystem self-clears the interval on the inactive guard, before fetching', () => {
    const src = j('38-system-monitor.js');
    const i = src.indexOf('async function refreshSystem');
    expect(i).toBeGreaterThan(0);
    const body = src.slice(i);
    const guardIdx = body.indexOf("getElementById('pane-system')");
    const clearIdx = body.indexOf('clearInterval(sysRefreshTimer)');
    const fetchIdx = body.indexOf('fetch(');
    expect(guardIdx).toBeGreaterThan(-1);
    expect(body.slice(guardIdx, body.indexOf('try {', guardIdx))).toMatch(/classList\.contains\('active'\)/);
    expect(clearIdx).toBeGreaterThan(guardIdx);
    expect(clearIdx).toBeLessThan(fetchIdx);
  });
});

describe('control tower renders cannot leak intervals (r47)', () => {
  it('renderControlTower assigns the interval only to the newest render', () => {
    const src = j('31-control-tower.js');
    const i = src.indexOf('async function renderControlTower');
    expect(i).toBeGreaterThan(0);
    const body = src.slice(i);
    const tokenIdx = body.indexOf('++_controlRenderSeq');
    const awaitIdx = body.indexOf('await refreshControlTower()');
    const staleIdx = body.indexOf('seq !== _controlRenderSeq');
    const setIdx = body.indexOf('setInterval(refreshControlTower');
    expect(tokenIdx).toBeGreaterThan(-1);
    expect(awaitIdx).toBeGreaterThan(tokenIdx);
    expect(staleIdx).toBeGreaterThan(awaitIdx);
    expect(setIdx).toBeGreaterThan(staleIdx);
  });
});
