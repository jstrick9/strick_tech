// Regression guard: `.tag` and `.badge` are two pre-existing SHARED components
// that had drifted apart — `.badge` used the modern token family
// (badge-default/-accent/-success/-warning/-danger) with AA tints and token
// geometry, while `.tag` used hardcoded hex modifiers (.tag.green/.yellow/
// .red/.blue), literal 10px font and a different 99px/2px7px shape. A tag and a
// badge in the same row therefore rendered at two different sizes and two
// different colour shells. This guard locks the reconciliation: `.tag` now uses
// the same geometry and modifier vocabulary as `.badge`, with the legacy hex
// modifiers kept as aliases.
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const CSS = fs.readFileSync(path.join(__dirname, '..', 'styles-system.css'), 'utf8');

describe('.tag is reconciled onto the .badge token vocabulary', () => {
  it('gives .tag the same geometry as .badge (radius-full, same padding)', () => {
    // The reconcile block must set the token radius, not a literal 99px.
    const block = CSS.split(/The pre-existing shared `\.tag`/)[1];
    expect(block).toMatch(/border-radius:\s*var\(--radius-full\);/);
    expect(block).toMatch(/padding:\s*1px 8px;/);
    expect(block).not.toMatch(/font-size:\s*10px/);
    expect(CSS).not.toMatch(/\.tag\{\s*font-size:10px/);
  });

  it('exposes the canonical tag-<tint> tokens (default/accent/success/warning/danger)', () => {
    ['tag-default', 'tag-accent', 'tag-success', 'tag-warning', 'tag-danger']
      .forEach(t => expect(CSS).toMatch(new RegExp('\\.' + t.replace('-', '-') + '\\b')));
  });

  it('keeps the legacy .tag.green/yellow/red/blue modifiers as aliases', () => {
    expect(CSS).toMatch(/\.tag-accent, \.tag\.blue/);
    expect(CSS).toMatch(/\.tag-success, \.tag\.green/);
    expect(CSS).toMatch(/\.tag-warning, \.tag\.yellow/);
    expect(CSS).toMatch(/\.tag-danger, \.tag\.red/);
  });

  it('no longer hardcodes the old hex backgrounds for the legacy modifiers', () => {
    // The old block set e.g. .tag.green{background:#0d2a1a}. The alias must
    // now point at the token tint instead.
    const m = CSS.match(/\.tag-success, \.tag\.green\s*\{([^}]+)\}/);
    expect(m).toBeTruthy();
    expect(m[1]).toMatch(/rgba/);
    expect(m[1]).not.toMatch(/#0d2a1a/);
  });
});
