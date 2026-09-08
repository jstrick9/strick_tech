// Regression guard (#058): the Account Settings modal had three gaps that
// made it feel unresponsive / keyboard-hostile:
//   1. It rendered ONLY after `await loadAccountData()` resolved — a slow
//      profile/prefs/license API meant a click that visibly did nothing.
//   2. The left tab rail had no focus / arrow-key navigation (WAI-ARIA tabs).
//   3. Focus was neither moved into the dialog on open nor restored on close.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const SRC = fs.readFileSync(path.join(__dirname, '..', 'js', '57-account-settings.js'), 'utf8');

// Minimal stubs the module touches at load (it runs as an IIFE referencing
// escHtml/toast/document). Keep the real document for the modal DOM.
const win = {};
global.window = win;
global.escHtml = (s) => String(s ?? '');
global.document = document;
global.toast = vi.fn();
global._safeLS = { get: () => null, set: () => {} };
// The module uses window.stateFeedback.loadingElement for its loading state.
win.stateFeedback = {
  loadingElement: (label) => `<div class="data-state state-loading" role="status">${label}</div>`,
};

function loadModule() {
  const fn = new Function('window', 'document', 'escHtml', 'toast',
    'globalThis', '_safeLS', SRC + '\n;return window;');
  // Provide the global names the module reads.
  const scope = { window: win, document: document, escHtml: global.escHtml, toast: global.toast, globalThis: globalThis, _safeLS: global._safeLS };
  fn.call(scope, win, document, global.escHtml, global.toast, globalThis, global._safeLS);
  return win;
}

// setup.js replaces document.getElementById with a mock; the module relies on
// the real DOM here, so restore the native prototype method.
const nativeGetElementById = Document.prototype.getElementById;

describe('Account Settings modal — responsiveness & a11y', () => {
  beforeEach(() => {
    document.getElementById = nativeGetElementById;
    document.body.innerHTML = '';
    global.fetch = vi.fn(() => Promise.resolve({
      ok: true, json: () => Promise.resolve({ name: 'Test' }),
    }));
  });
  afterEach(() => { document.body.innerHTML = ''; });

  it('renders a loading state synchronously (before awaiting the data fetch)', async () => {
    global.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }));
    const w = loadModule();
    const open = w.openAccountSettings('profile');
    // The modal + loading spinner must be in the DOM immediately — before any
    // await resolves (the old code only rendered after loadAccountData()).
    const overlay = document.getElementById('account-settings-modal');
    expect(overlay).toBeTruthy();
    expect(overlay.querySelector('#account-settings-body').innerHTML).toMatch(/Loading account settings/);
    await open; // let the data promise settle so no unhandled rejection
    // After the data lands the real content replaces the spinner.
    expect(overlay.querySelector('#account-settings-body').innerHTML).not.toMatch(/Loading account settings/);
  });

  it('gives the tab rail ARIA roles and arrow-key navigation', async () => {
    global.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }));
    const w = loadModule();
    await w.openAccountSettings('profile');
    const rail = document.getElementById('account-settings-tabs');
    expect(rail.getAttribute('role')).toBe('tablist');
    expect(rail.getAttribute('aria-orientation')).toBe('vertical');
    const tabs = rail.querySelectorAll('.account-tab-btn');
    expect(tabs.length).toBeGreaterThan(0);
    expect(tabs[0].getAttribute('role')).toBe('tab');
    // ArrowDown moves focus + activation to the next tab.
    tabs[0].focus();
    tabs[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true, cancelable: true }));
    expect(document.activeElement).toBe(tabs[1]);
    expect(tabs[1].getAttribute('aria-selected')).toBe('true');
  });

  it('restores focus to the invoking element on close', async () => {
    global.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }));
    const w = loadModule();
    const trigger = document.createElement('button');
    trigger.id = 'settings-trigger';
    document.body.appendChild(trigger);
    trigger.focus();
    await w.openAccountSettings('profile');
    w.closeAccountSettings();
    // The modal is gone and focus returns to the trigger.
    expect(document.getElementById('account-settings-modal')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});
