/**
 * Docs pane tabs — a non-2xx / null API response must not crash the tab (#066).
 *
 * `docsTab('quickstarts')` did
 *   `fetch('/api/docs/quick-starts').then(r=>r.ok?r.json():null).catch(()=>({quick_starts:[]}))`
 * The `.catch()` only covers a NETWORK rejection. On a non-2xx response, `r.ok`
 * is false and `.then` resolves to `null`, so `d` was `null` and the very next
 * line `d.quick_starts` threw `TypeError: Cannot read properties of null
 * (reading 'quick_starts')` — blanking the whole tab on any server hiccup
 * (found by an automated click-fuzz across panes). Same bug in the `features`
 * tab (`d.features`).
 *
 * Guard: the response must be coerced to a non-null object (via `|| {}`) before
 * any property is read. This is a source-contract guard for both tabs.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const SRC = readFileSync(resolve(__dirname, '../js/04-workflow-specs.js'), 'utf8');

function seg(from, to) {
  const i = SRC.indexOf(from);
  if (i < 0) return '';
  const j = SRC.indexOf(to, i);
  return SRC.slice(i, j < 0 ? SRC.length : j);
}

describe('#066 docs tabs survive a null API response', () => {
  it('quick-starts coerces a null response to an object before reading quick_starts', () => {
    const body = seg("if (tab === 'quickstarts') {", "else if (tab === 'features') {");
    expect(body).toMatch(/fetch\('\/api\/docs\/quick-starts'\)/);
    expect(body).toMatch(/\|\|\s*\{\}/);   // null → {} so `d.quick_starts` is safe
    // The property access must come AFTER the null-coalescing read, on the
    // const d assignment line (anchor there so the inline comment can't skew it).
    const constIdx = body.indexOf("const d =");
    const constLine = body.slice(constIdx, body.indexOf('\n', constIdx));
    expect(constLine).toMatch(/\|\|\s*\{\}/);
    const coalesceAt = body.indexOf('|| {}', constIdx);
    const accessAt = body.indexOf('d.quick_starts', constIdx);
    expect(coalesceAt).toBeGreaterThan(-1);
    expect(accessAt).toBeGreaterThan(coalesceAt);
  });

  it('features coerces a null response to an object before reading features', () => {
    const body = seg("else if (tab === 'features') {", "else if (tab === 'faq') {");
    expect(body).toMatch(/fetch\('\/api\/docs\/features'\)/);
    expect(body).toMatch(/\|\|\s*\{\}/);
    const coalesceAt = body.indexOf('|| {}');
    const accessAt = body.indexOf('d.features');
    expect(coalesceAt).toBeGreaterThan(-1);
    expect(accessAt).toBeGreaterThan(coalesceAt);
  });
});
