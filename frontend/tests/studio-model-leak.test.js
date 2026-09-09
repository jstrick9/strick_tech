/**
 * #078 — Studio Monaco editor leaked an anonymous model on every file open.
 *
 * `openFile()` called `monaco.editor.createModel(text, lang)` + `setModel()`
 * for each file opened but never disposed the model it was leaving. Anonymous
 * models (no URI) are reference-counted but not auto-collected by Monaco, so
 * switching files kept every single model alive. Measured in the live app:
 * opening 2 files 4x grew `monaco.editor.getModels()` from 1 to 9 — a steady
 * memory leak that degrades a long-lived Studio session.
 *
 * Fix: capture `Studio.editor.getModel()` before attaching the new model and
 * call `.dispose()` on it. Guarded so it only disposes this editor's own model
 * (the diff editor keeps its own separate original/modified models).
 *
 * Verified live: after opening all files 4x, `getModels()` stays at 1 (stable),
 * edits/autosave/version-history/preview all still work, 0 page errors.
 * Source-level regression test.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const SRC = readFileSync(resolve(__dirname, '../js/01-app-core.js'), 'utf8');

describe('#078 studio does not leak a monaco model when switching files', () => {
  it('captures and disposes the previous model before attaching the new one', () => {
    const m = SRC.match(/const prevModel = Studio\.editor\.getModel\(\);[\s\S]{0,160}if \(prevModel\) prevModel\.dispose\(\);/);
    expect(m).not.toBeNull();
  });

  it('does not dispose the model while it is still set on the editor', () => {
    // Order matters: setModel with the new model must come before dispose of
    // the previous, so we never dispose the now-active model. Assert the
    // prevModel is captured, a new model created, setModel called, THEN prev
    // disposed.
    const start = SRC.indexOf('const prevModel = Studio.editor.getModel()');
    expect(start).toBeGreaterThan(-1);
    const body = SRC.slice(start, start + 600);
    const iCreate = body.indexOf('monaco.editor.createModel');
    const iSet = body.indexOf('Studio.editor.setModel(model)');
    const iDispose = body.indexOf('prevModel.dispose()');
    expect(iCreate).toBeGreaterThan(-1);
    expect(iSet).toBeGreaterThan(iCreate);
    expect(iDispose).toBeGreaterThan(iSet);
  });
});
