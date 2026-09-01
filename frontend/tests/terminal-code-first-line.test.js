// Frontend correctness: runCodeInTerminal must not silently claim that a
// multi-line code block was sent to the terminal when it only places the first
// line (the terminal input is a single-line <input>). It should warn that only
// line 1 was placed.
import { describe, it, expect, beforeEach, vi } from 'vitest';

function loadRunCodeInTerminal() {
  const fs = require('fs'); const path = require('path');
  const code = fs.readFileSync(path.join(__dirname, '..', 'js', '01-app-core.js'), 'utf8');
  const start = code.indexOf('window.runCodeInTerminal = function');
  const end = code.indexOf('};', start) + 2;
  const fn = code.slice(start, end);
  // Run the timer callback immediately for deterministic tests.
  const immediate = (cb) => { cb(); return 0; };
  new Function('window', 'document', 'nav', 'toast', 'setTimeout', 'decodeURIComponent', 'encodeURIComponent', fn)(
    globalThis.window, globalThis.document, globalThis.nav, globalThis.toast, immediate,
    globalThis.decodeURIComponent, globalThis.encodeURIComponent
  );
}

function setup(codeText) {
  // Build #codeId with code[data-raw]
  const codeEl = document.createElement('code');
  codeEl.setAttribute('data-raw', encodeURIComponent(codeText));
  codeEl.textContent = codeText;
  const wrap = Object.assign(document.createElement('div'), { id: 'cb_xyz' });
  wrap.innerHTML = '<code></code>';
  // simpler: create the host and override querySelector/getElementById.
  const termInput = Object.assign(document.createElement('input'), { id: 'term-input', value: '', focus: vi.fn() });
  document.body.appendChild(wrap); document.body.appendChild(termInput);
  const orig = document.getElementById;
  document.getElementById = (id) => ({ 'cb_xyz': wrap, 'term-input': termInput }[id] || orig(id));
  wrap.querySelector = () => codeEl;
  return { wrap, termInput, codeEl };
}

describe('runCodeInTerminal multi-line honesty', () => {
  let toasts, navs;
  beforeEach(() => {
    document.body.innerHTML = '';
    toasts = []; navs = [];
    globalThis.toast = vi.fn((m, t) => toasts.push({ m, t }));
    globalThis.nav = vi.fn((x) => navs.push(x));
    loadRunCodeInTerminal();
  });

  it('warns when a multi-line snippet is truncated to its first line', () => {
    const { termInput } = setup('line1\nline2\nline3');
    window.runCodeInTerminal('cb_xyz');
    expect(termInput.value).toBe('line1');
    expect(toasts.some(t => t.t === 'warn' && /of 3/.test(t.m))).toBe(true);
    expect(toasts.some(t => t.t === 'ok')).toBe(false);
  });

  it('reports success for a single-line snippet', () => {
    const { termInput } = setup('echo hi');
    window.runCodeInTerminal('cb_xyz');
    expect(termInput.value).toBe('echo hi');
    expect(toasts.some(t => t.t === 'ok')).toBe(true);
  });
});
