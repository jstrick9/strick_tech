// Settings flow: pressing Enter in the OpenRouter key field or the custom
// endpoint URL/key fields should trigger save, not silently do nothing. The
// field is the most common settings action, so this removes real friction.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

let frag;
function loadModule() {
  const fs = require('fs'); const path = require('path');
  const src = fs.readFileSync(path.join(__dirname, '..', 'js', '01-app-core.js'), 'utf8');
  // Extract only the delegated Enter handler block (not the whole 6k-line file).
  const start = src.indexOf('// Enter in the settings API-key');
  const end = src.indexOf('window.saveCustomConnection = async function');
  frag = src.slice(start, end);
  // The handler calls saveApiKey/window.saveCustomConnection; provide stubs.
  globalThis.window.saveCustomConnection = vi.fn(() => { globalThis.__customSaved = true; });
  new Function('window','document',
    'function saveApiKey(){ globalThis.__apiKeySaved = true; }\n' + frag
  )(globalThis.window, globalThis.document);
}

describe('settings Enter-to-save', () => {
  beforeEach(() => { document.body.innerHTML = ''; });
  afterEach(() => { document.body.innerHTML = ''; });

  it('Enter in #or-key-input triggers saveApiKey', () => {
    loadModule();
    const target = document.createElement('input');
    target.id = 'or-key-input';
    document.body.appendChild(target);
    target.focus();
    const ev = new KeyboardEvent('keydown', { key:'Enter', bubbles:true, cancelable:true });
    target.dispatchEvent(ev);
    expect(ev.defaultPrevented).toBe(true);
    expect(globalThis.__apiKeySaved).toBe(true);
  });

  it('Enter in #custom-api-base-url triggers saveCustomConnection', () => {
    loadModule();
    const target = document.createElement('input');
    target.id = 'custom-api-base-url';
    document.body.appendChild(target);
    target.focus();
    const ev = new KeyboardEvent('keydown', { key:'Enter', bubbles:true, cancelable:true });
    target.dispatchEvent(ev);
    expect(ev.defaultPrevented).toBe(true);
    expect(globalThis.__customSaved).toBe(true);
  });
});
