// Regression guard (#059): `.badge` was defined in three loaded sheets and, in
// the one that wins (styles-extracted.css), used 2px 8px while its sibling
// `.tag` (reconciled in #057) used 1px 8px — so a tag and a badge rendered at
// different heights side by side in the same cluster (mkt-card-tags /
// mkt-card-badges). `.badge` is now reconciled onto the SAME geometry and tint
// vocabulary as `.tag`, with the legacy compound modifiers kept as aliases.
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const CSS = fs.readFileSync(path.join(__dirname, '..', 'styles-system.css'), 'utf8');

function blockOf(sel) {
  const m = CSS.match(new RegExp('(^|\n)' + sel.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s*\\{([^}]*)\\}'));
  return m ? m[2] : '';
}

describe('.badge matches the reconciled .tag geometry', () => {
  it('uses the same 1px 8px padding as .tag', () => {
    const b = blockOf('.badge');
    expect(b).toMatch(/padding:\s*1px 8px;/);
  });

  it('uses the same radius-full, weight and type scale as .tag', () => {
    const b = blockOf('.badge');
    expect(b).toMatch(/border-radius:\s*var\(--radius-full\);/);
    expect(b).toMatch(/font-size:\s*var\(--font-size-xs\);/);
    expect(b).toMatch(/font-weight:\s*600;/);
    expect(b).toMatch(/line-height:\s*1\.6;/);
  });

  it('exposes the canonical badge-default/-accent/-success/-warning/-danger tints', () => {
    ['badge-default', 'badge-accent', 'badge-success', 'badge-warning', 'badge-danger']
      .forEach(t => expect(CSS).toMatch(new RegExp('(^|\n)\\.' + t + '\\b')));
  });

  it('keeps legacy .badge.green/.blue/.live as aliases of the token tints', () => {
    expect(CSS).toMatch(/\.badge-accent, \.badge\.blue/);
    expect(CSS).toMatch(/\.badge-success, \.badge\.green/);
    expect(CSS).toMatch(/\.badge-live, \.badge\.live/);
  });
});
