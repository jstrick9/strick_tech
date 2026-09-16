// Regression guard (r44): the search-input class sweep. data-act-input fires
// on EVERY keystroke, so a handler that fetches needs (a) a debounce and
// (b) a stale-response guard — without the guard a slow response for an old
// query overwrites the render of a newer one, leaving results on screen that
// don't match the search box. Verified live at every site before the fix:
// 4 fetches for 4 keystrokes, and a 900ms-delayed first-query response
// overwriting the final query's (correct) empty state.
//
// Sites: searchNotes (obsidian), kgSearch (knowledge graph) and mktSearch
// (marketplace) had NEITHER; obsSearchTraces (traces) and specSearch (specs)
// were debounced but had no stale-response guard.
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const j = (f) => fs.readFileSync(path.join(__dirname, '..', 'js', f), 'utf8');

function fnBody(src, name) {
  const i = src.indexOf(`function ${name}`);
  expect(i, `${name} not found`).toBeGreaterThan(0);
  // slice to the next top-level "function " or "window." export after it
  const rest = src.slice(i);
  const next = ['\nfunction ', '\nwindow.', '\nasync function ', '\nlet ', '\nconst ']
    .map((m) => rest.indexOf(m, 20)).filter((x) => x > 0);
  return rest.slice(0, next.length ? Math.min(...next) : undefined);
}

describe('search inputs debounce before fetching', () => {
  it('searchNotes (obsidian) debounces 250ms', () => {
    const body = fnBody(j('20-obsidian.js'), 'searchNotes');
    expect(body).toMatch(/clearTimeout\(_notesSearchTimer\)/);
    expect(body).toMatch(/setTimeout\(\(\)\s*=>\s*loadObsidianNotes\(q\),\s*250\)/);
    expect(body).not.toMatch(/loadObsidianNotes\(q\);\s*$/); // no immediate call
  });

  it('kgSearch (knowledge graph) debounces 250ms', () => {
    const src = j('05-evals-observability.js');
    const body = fnBody(src, 'kgSearch');
    expect(body).toMatch(/clearTimeout\(_kgSearchTimer\)/);
    expect(body).toMatch(/250\)/);
    // the fetch must live INSIDE the timeout, not beside it
    expect(body.indexOf('setTimeout')).toBeLessThan(body.indexOf('fetch('));
  });

  it('mktSearch (marketplace) debounces 250ms', () => {
    const body = fnBody(j('08-replay-collab.js'), 'mktSearch');
    expect(body).toMatch(/clearTimeout\(_mktSearchTimer\)/);
    expect(body).toMatch(/setTimeout\(\(\)\s*=>\s*mktLoadPacks\(_mktQuery,\s*_mktCategory,\s*_mktSort\),\s*250\)/);
    expect(body).not.toMatch(/mktLoadPacks\(q,\s*_mktCategory,\s*_mktSort\);\s*\}/); // no immediate call
  });
});

describe('async list loaders drop superseded responses', () => {
  const CASES = [
    ['20-obsidian.js', 'loadObsidianNotes', '_notesLoadSeq'],
    ['05-evals-observability.js', 'obsLoadTraces', '_obsTraceSeq'],
    ['08-replay-collab.js', 'mktLoadPacks', '_mktLoadSeq'],
    ['03-features-b.js', 'specLoadList', '_specListSeq'],
  ];

  for (const [file, fn, seqVar] of CASES) {
    it(`${fn} (${file}) guards renders with ${seqVar}`, () => {
      const src = j(file);
      const body = fnBody(src, fn);
      // capture a sequence token before awaiting…
      expect(body).toMatch(new RegExp(`const seq\\s*=\\s*\\+\\+${seqVar}`));
      // …and bail after the response if a newer call superseded it. The
      // guard must appear AFTER the first await (a guard before any await
      // protects nothing).
      const awaitIdx = body.indexOf('await fetch');
      const guardRe = new RegExp(`seq\\s*!==\\s*${seqVar}`);
      const guardMatch = guardRe.exec(body);
      expect(awaitIdx).toBeGreaterThan(0);
      expect(guardMatch, 'guard not found').not.toBeNull();
      expect(guardMatch.index).toBeGreaterThan(awaitIdx);
    });
  }

  it('kgSearch guards its render inside the debounced task', () => {
    const body = fnBody(j('05-evals-observability.js'), 'kgSearch');
    expect(body).toMatch(/const seq\s*=\s*\+\+_kgLoadSeq/);
    const guardMatch = /seq\s*!==\s*_kgLoadSeq/.exec(body);
    expect(guardMatch, 'guard not found').not.toBeNull();
    expect(guardMatch.index).toBeGreaterThan(body.indexOf('await fetch'));
  });
});
