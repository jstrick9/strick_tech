// Frontend correctness: inline data-act-* handlers must interpolate arguments
// through jsArg (the documented helper), NOT JSON.stringify.
//
// The delegate reads the attribute via getAttribute() (browser HTML-decodes it)
// and JSON.parses each argument. JSON.stringify emits the surrounding double
// quotes *into the attribute source*; the HTML parser sees the first `"` and
// terminates the attribute early, so getAttribute() returns a truncated handler
// (e.g. `sel(`). Any string argument thus makes the button a no-op. jsArg
// escapes each quote to an entity first, so the attribute survives parsing and
// decodes back to a valid JS literal.
import { describe, it, expect } from 'vitest';

// jsArg's exact algorithm (frontend/js/01-app-core.js).
function jsArg(value) {
  return JSON.stringify(value === undefined ? null : value)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function attrOf(interp) {
  document.body.innerHTML = `<button id="b" data-act-click="sel(${interp})">x</button>`;
  return document.querySelector('#b').getAttribute('data-act-click');
}

describe('inline handler argument escaping', () => {
  it('JSON.stringify breaks a string argument (attribute truncates)', () => {
    const v = "O'Brien";
    // Raw quoted string from JSON.stringify closes the attribute -> truncated.
    expect(attrOf(`${JSON.stringify(v)}`)).not.toBe(`sel(${JSON.stringify(v)})`);
  });

  it('jsArg round-trips a string (with apostrophe) to a parseable literal', () => {
    const v = "O'Brien's \"quoted\" & <tag>";
    const attr = attrOf(jsArg(v));
    // The attribute must survive intact (full function call, no truncation).
    expect(attr).toContain('O');
    expect(attr).toContain('Brien');
    // Entity-decoded back to the real characters; JSON.parse yields the value.
    expect(JSON.parse(attr.slice(4, -1))).toBe(v);
  });

  it('jsArg preserves a string with a double quote', () => {
    const v = 'say "hi"';
    const attr = attrOf(jsArg(v));
    expect(JSON.parse(attr.slice(4, -1))).toBe(v);
  });

  it('jsArg preserves numeric and boolean arguments unchanged', () => {
    expect(attrOf(jsArg(123))).toBe(`sel(123)`);
    expect(attrOf(jsArg(true))).toBe(`sel(true)`);
  });
});
