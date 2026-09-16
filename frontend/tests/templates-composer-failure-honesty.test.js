// Templates + composer pane fixes:
//
// 1. The template gallery's no-match empty state had a broken string
//    interpolation — the whole message was ONE single-quoted literal, so
//    every zero-result search displayed the source code itself:
//        No templates match “" + escHtml(q) + "”
// 2. The template preview modal (#tmpl-preview-modal) had an id (excluded
//    from the no-id Escape handler in 00-handlers.js) and no -modal-overlay
//    class (excluded from the master Escape handler) — it fell through
//    every Escape net and could only be closed with the mouse. role=dialog
//    joins it to both the master Escape handler and the Tab focus-trap,
//    which discover bespoke dialogs by attribute.
// 3/4. createBranchPreview / deleteBranchPreview had no try/catch while
//    their sibling loadBranchPreviews() does — a network-level failure
//    escaped as an unhandled rejection: no toast, no status, the button
//    silently did nothing.
import { describe, it, expect } from 'vitest';

const fs = require('fs');
const path = require('path');
const TPL = fs.readFileSync(path.join(__dirname, '..', 'js', '21-template-gallery.js'), 'utf8');
const CMP = fs.readFileSync(path.join(__dirname, '..', 'js', '19-composer.js'), 'utf8');

describe('template gallery', () => {
  it('no-match message interpolates the query instead of quoting source code', () => {
    expect(TPL).not.toContain("'No templates match \\u201c\" + escHtml(q) + \"\\u201d'");
    const line = TPL.split('\n').find(l => l.includes('No templates match'));
    expect(line).toMatch(/'No templates match \\u201c' \+ escHtml\(q\) \+ '\\u201d'/);
  });

  it('preview overlay joins the Escape-removal and focus-trap conventions', () => {
    const fn = TPL.slice(TPL.indexOf('function showTemplatePreviewModal'));
    const head = fn.slice(0, fn.indexOf('overlay.style.cssText'));
    // -modal-overlay class -> the master handler's REMOVE branch (a bare
    // role=dialog only reached the display:none fallback, leaving a stale
    // scrim node); role=dialog/aria-modal add the dialog semantics.
    expect(head).toContain("overlay.className = 'tmpl-modal-overlay'");
    expect(head).toContain("setAttribute('role', 'dialog')");
    expect(head).toContain("setAttribute('aria-modal', 'true')");
  });
});

describe('composer branch-preview actions', () => {
  function fnSource(name) {
    const start = CMP.indexOf(`async function ${name}`);
    expect(start, `${name} not found`).toBeGreaterThan(-1);
    const next = CMP.indexOf('async function', start + 1);
    return CMP.slice(start, next === -1 ? undefined : next);
  }

  it('createBranchPreview catches network failures and reads the body first', () => {
    const src = fnSource('createBranchPreview');
    expect(src).toContain('} catch (e) {');
    expect(src).toMatch(/toast\("Couldn't create snapshot — "/);
    expect(src.indexOf('await r.json()')).toBeGreaterThan(-1);
    expect(src).toContain("(j && j.error) || ('server error ' + r.status)");
  });

  it('deleteBranchPreview catches network failures and surfaces the reason', () => {
    const src = fnSource('deleteBranchPreview');
    expect(src).toContain('} catch (e) {');
    expect(src).toMatch(/toast\("Couldn't delete snapshot — "/);
    expect(src).toContain('(await r.json()).error');
  });
});
