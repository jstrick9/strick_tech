// Design-system regression guard: the consolidated stylesystem.css must keep
// the shared elevation scale (.surface-z1..z4), .card-elevated and the
// affordance rules. Without them, panes that use these classes render as bare
// divs (the classes were previously defined nowhere — the gap this closes).
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const css = fs.readFileSync(path.join(__dirname, '..', 'styles-system.css'), 'utf8');

describe('styles-system.css keeps the elevation + affordance primitives', () => {
  it('defines the full surface-z1..z4 elevation scale', () => {
    for (const z of ['surface-z1', 'surface-z2', 'surface-z3', 'surface-z4']) {
      expect(new RegExp('\\.' + z + '\\s*\\{').test(css)).toBe(true);
    }
  });
  it('defines .card-elevated', () => {
    expect(/\.card-elevated\s*\{/.test(css)).toBe(true);
  });
  it('provides press affordance on buttons', () => {
    expect(/\.btn:active/.test(css)).toBe(true);
  });
  it('loads last (authoritative) in the app shell', () => {
    const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
    const order = ['styles-redesign.css', 'styles-system.css'].map(f => html.indexOf('/static/' + f));
    expect(order[0]).toBeGreaterThanOrEqual(0);
    expect(order[1]).toBeGreaterThan(order[0]);
  });
});
