/**
 * Studio Monaco loader — must be appended exactly once even when Studio is
 * opened repeatedly before the load completes (#067).
 *
 * `studioLoadMonaco()` only guarded on `window.monaco` / `studioMonacoLoaded`,
 * both of which are false while the loader is in flight. So every `initStudio()`
 * call before the load finished re-appended another `<script src=loader.js>`.
 * Monaco's loader declares a top-level `_amdLoaderGlobal`, so the second script
 * threw `Identifier '_amdLoaderGlobal' has already been declared`, leaving
 * `define` undefined and the editor never bootstrapping. Reproduced live: 3
 * loader requests + 1 SyntaxError from rapidly toggling to Studio.
 *
 * Guard: an in-flight flag (`studioMonacoLoading`) short-circuits re-append, and
 * it is released on `onerror` so a transient failure can retry.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const SRC = readFileSync(resolve(__dirname, '../js/01-app-core.js'), 'utf8');
const seg = (from, to) => {
  const i = SRC.indexOf(from); if (i < 0) return '';
  const j = to ? SRC.indexOf(to, i) : SRC.length;
  return SRC.slice(i, j < 0 ? SRC.length : j);
};

describe('#067 studio Monaco loader is appended exactly once', () => {
  it('declares an in-flight guard and short-circuits the append', () => {
    const fn = seg('function studioLoadMonaco()', '// ── Init ──');
    expect(fn).toMatch(/studioMonacoLoading/);
    // The guard must return before append when a load is already in flight.
    const guardAt = fn.indexOf('if (studioMonacoLoading) return;');
    const appendAt = fn.indexOf("s.src = '/static/vendor/monaco/vs/loader.js'");
    expect(guardAt).toBeGreaterThan(-1);
    expect(appendAt).toBeGreaterThan(guardAt);
    // The flag is set once, right at the start, before the script append.
    expect(fn).toMatch(/studioMonacoLoading = true;/);
  });

  it('releases the in-flight guard on loader failure (so it can retry)', () => {
    const fn = seg('function studioLoadMonaco()', '// ── Init ──');
    const onerror = seg('s.onerror = () => {', 's.onload = () => {');
    expect(onerror).toMatch(/studioMonacoLoading = false;/);
  });

  it('keeps the happy-path guards on window.monaco / studioMonacoLoaded', () => {
    const fn = seg('function studioLoadMonaco()', '// ── Init ──');
    expect(fn).toMatch(/if \(window\.monaco && studioMonacoLoaded\)/);
    expect(fn).toMatch(/if \(window\.monaco\)/);
  });
});
