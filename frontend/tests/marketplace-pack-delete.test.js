// Frontend correctness: marketplace packs must be deletable, and the delete
// button must not lie.
//
// Packs could be published, uploaded, or community-submitted but never
// removed — the grid only grew forever (same create-without-delete asymmetry
// as the eval suites/datasets fixes). The pane now offers a trash button on
// every card; the server refuses re-seeded built-ins, and that refusal must
// reach the user instead of being swallowed.
import { describe, it, expect } from 'vitest';

const fs = require('fs');
const path = require('path');
const SRC = fs.readFileSync(path.join(__dirname, '..', 'js', '08-replay-collab.js'), 'utf8');

describe('marketplace pack delete is wired into the pane', () => {
  const card = SRC.match(/function mktCardHTML[\s\S]*?\n\}/)[0];

  it('every card offers a delete action', () => {
    expect(card).toMatch(/data-act-click="mktDeletePack\(/);
  });

  it('the delete handler exists and is async', () => {
    expect(SRC).toMatch(/async function mktDeletePack\(packId, packName\) \{/);
  });
});

describe('marketplace pack delete behaves honestly', () => {
  const fn = SRC.match(/async function mktDeletePack[\s\S]*?\n\}/)[0];

  it('confirms before deleting', () => {
    expect(fn).toContain('gmDanger(');
    expect(fn).toContain('if (!ok) return;');
  });

  it('encodes the pack id in the URL', () => {
    expect(fn).toContain('`/api/marketplace/${encodeURIComponent(packId)}`');
  });

  it('surfaces the HTTP-level failure (incl. the built-in 403 refusal)', () => {
    expect(fn).toContain("if (!r.ok) {");
    expect(fn).toContain("'Delete failed: '+(d.error||('HTTP '+r.status))");
  });

  it('surfaces the body-level failure and refreshes the grid on success', () => {
    expect(fn).toContain("'Delete failed: '+(d.error||'Unknown error')");
    expect(fn).toContain('mktLoadPacks(_mktQuery, _mktCategory, _mktSort)');
  });
});
