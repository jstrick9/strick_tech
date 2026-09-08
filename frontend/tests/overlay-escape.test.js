// Keyboard-dismiss for ad-hoc full-screen fixed overlays. The shared
// delegated Escape handler in 00-handlers.js must close the topmost open
// full-screen overlay but NEVER touch the gm modal (#gmodal), which has its own
// Escape handling and id. Prior to this, steering/replay/evals overlays could
// only be closed by clicking ✕/Cancel — a keyboard user was stuck.
import { describe, it, expect, beforeEach, afterEach, beforeAll } from 'vitest';

function loadHandlers() {
  const fs = require('fs'); const path = require('path');
  const src = fs.readFileSync(path.join(__dirname, '..', 'js', '00-handlers.js'), 'utf8');
  new Function('window', 'document', src)(globalThis.window, globalThis.document);
}

describe('Escape dismisses ad-hoc full-screen overlays', () => {
  // Bind the handler ONCE (the document persists across tests, so binding in
  // beforeEach would accumulate listeners and fire N times per Escape).
  beforeAll(() => { loadHandlers(); });
  beforeEach(() => {
    document.body.innerHTML = '<div id="gmodal" style="position:fixed;inset:0"></div>';
  });
  afterEach(() => { document.body.innerHTML = ''; });

  it('removes the topmost open full-screen overlay on Escape', () => {
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999';
    document.body.appendChild(overlay);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(document.body.contains(overlay)).toBe(false);
  });

  it('does NOT close the gm modal or other id-bearing fixed elements', () => {
    // #gmodal is id-bearing and has its own Escape handling. (querySelector
    // bypasses setup.js's getElementById mock, which returns null for gmodal.)
    const gmodal = document.querySelector('#gmodal');
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(document.body.contains(gmodal)).toBe(true);
  });

  it('only closes the topmost overlay (turns the stack into one), not all', () => {
    const a = document.createElement('div'); a.style.cssText = 'position:fixed;inset:0';
    const b = document.createElement('div'); b.style.cssText = 'position:fixed;inset:0';
    document.body.appendChild(a); document.body.appendChild(b);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(document.body.contains(b)).toBe(false);
    expect(document.body.contains(a)).toBe(true);
  });
});
