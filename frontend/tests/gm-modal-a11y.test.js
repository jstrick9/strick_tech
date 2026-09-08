// Keyboard + focus contract for the shared gm modal. The dialog must be
// (a) dismissable with Escape, (b) restore focus to the element that opened it
// on close, and (c) focus the most useful control on open. This is the single
// most-used modal (gmAlert/gmConfirm/gmPrompt/gmDanger) so a regression here
// hits every pane. The gmodal DOM is copied verbatim from index.html.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

function escHtml(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c])); }
function jsArg(s) { return escHtml(s).replace(/"/g, '&quot;'); }

const GMODAL_HTML = `
<div id="gmodal" role="dialog" aria-modal="true" aria-labelledby="gm-title" aria-describedby="gm-body" style="display:none">
  <div id="gm-title"></div>
  <div id="gm-body"></div>
  <div id="gm-input-wrap" style="display:none"><input id="gm-input"><textarea id="gm-textarea" style="display:none"></textarea></div>
  <div id="gm-btns"></div>
</div>`;

let gm;

function loadModule() {
  const fs = require('fs'); const path = require('path');
  const src = fs.readFileSync(path.join(__dirname, '..', 'js', '01-app-core.js'), 'utf8');
  // Pull just the gm modal machinery (state, show/teardown/click/cancel, wrappers).
  const start = src.indexOf('let _gm_resolve = null;');
  const end = src.indexOf('// ── Extend nav() for Sprint 4');
  const frag = src.slice(start, end);
  gm = new Function('window', 'document', 'escHtml', 'jsArg',
    frag + ';return { gmAlert, gmConfirm, gmPrompt, gmDanger, cancel:function(){_gm_cancel()} };'
  )(globalThis.window, globalThis.document, escHtml, jsArg);
}

describe('gm modal keyboard + focus contract', () => {
  beforeEach(() => {
    document.body.innerHTML = GMODAL_HTML;
    // setup.js mocks getElementById -> null for non-app ids; restore the real
    // lookup so the modal machinery can reach its own controls.
    globalThis.document.getElementById = vi.fn((id) => document.querySelector('#' + id)) ;
    loadModule();
  });
  afterEach(() => { document.body.innerHTML = ''; });

  it('is dismissable with Escape (resolves cancel, closes dialog)', async () => {
    const opener = document.createElement('button');
    document.body.appendChild(opener);
    opener.focus();
    const p = gm.gmDanger('Delete', 'Are you sure?', 'Delete');
    const modal = document.getElementById('gmodal');
    expect(modal.style.display).toBe('flex');
    // Simulate Escape.
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    const r = await p;
    expect(r).toBe(false); // gmDanger resolves false on cancel
    expect(modal.style.display).toBe('none');
  });

  it('restores focus to the opener on close', async () => {
    const opener = document.createElement('button');
    document.body.appendChild(opener);
    opener.focus();
    const p = gm.gmAlert('Hi', 'Body');
    const modal = document.getElementById('gmodal');
    // Close via the modal cancel (the button's data-act-click is handled by the
    // app's delegated handler, not a native listener in jsdom).
    gm.cancel();
    await p;
    expect(document.activeElement).toBe(opener);
  });

  it('focuses the text input when a prompt has input (no focus dumped to body)', async () => {
    const opener = document.createElement('button');
    document.body.appendChild(opener);
    opener.focus();
    const p = gm.gmPrompt('Filename', 'name.html');
    // After the 50ms focus timer.
    await new Promise(r => setTimeout(r, 80));
    expect(document.activeElement).toBe(document.getElementById('gm-input'));
    gm.cancel();
    await p;
  });
});
