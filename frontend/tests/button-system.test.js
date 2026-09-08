// Regression guard (#056): the `.btn` / `.btn-3d` dual system was two parallel
// button classes that had drifted apart (different padding, radius, weight and
// a hover lift). They are consolidated so a control reads identically no
// matter which class authored it. Also locks the fix for the latent `.btn-sm`
// bug where the base `min-height:36px` overrode `.btn-sm{height:28px}`
// (min-height beats height), so every small button was actually 36px tall.
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const CSS = fs.readFileSync(path.join(__dirname, '..', 'styles-system.css'), 'utf8');

// The authoritative (loads-last) stylesheet is the only place reconciliation
// may live — an edit to a sheet that loads earlier is silently overridden.
const order = (['styles-redesign.css', 'styles-system.css'])
  .map(f => fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8')
    .indexOf('/static/' + f));

describe('styles-system.css reconciles the .btn / .btn-3d dual system', () => {
  it('applies one shared base (padding/radius/weight) to both classes', () => {
    const block = CSS.split(/BUTTONS — one reconciled system/)[1].split(/BUG FIX/)[0];
    // Both live in the same rule block, not separately authored.
    expect(block).toMatch(/\.btn,\n\.btn-3d\s*\{/);
    expect(block).toMatch(/padding:\s*7px 14px;/);
    expect(block).toMatch(/font-weight:\s*500;/);
    expect(block).toMatch(/border-radius:\s*var\(--radius\);/);
  });

  it('removes the btn-3d-only hover lift so hover is identical', () => {
    expect(CSS).toMatch(/\.btn:hover, \.btn-3d:hover \{\s*transform: none;/);
  });

  it('fixes btn-sm so it is actually 28px tall (min-height no longer wins)', () => {
    const block = CSS.split(/BUG FIX: `\.btn-sm`/)[1].split(/Press \+ hover/)[0];
    expect(block).toMatch(/\.btn-sm\s*\{/);
    expect(block).toMatch(/min-height:\s*28px;/);
    expect(block).toMatch(/height:\s*28px;/);
    expect(block).toMatch(/--ctl-h:\s*28px;/);
  });

  it('loads last (authoritative)', () => {
    expect(order[0]).toBeGreaterThanOrEqual(0);
    expect(order[1]).toBeGreaterThan(order[0]);
  });
});
