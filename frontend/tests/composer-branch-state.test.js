// Frontend correctness: the Composer branch-preview list must distinguish a
// healthy empty state from a failed load. Previously a non-ok response fell
// through to j.branches?.length and rendered a false "No snapshots yet" on an
// outage, and a thrown network error was swallowed by catch(e){}, leaving an
// eternal "Loading…" with no error and no retry.
import { describe, it, expect, beforeEach, vi } from 'vitest';

function escHtml(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c])); }
function jsArg(s) { return escHtml(s).replace(/"/g, '&quot;'); }
function safeUrl(s) { return s; }

function loadModule() {
  const fs = require('fs'); const path = require('path');
  const source = fs.readFileSync(path.join(__dirname, '..', 'js', '19-composer.js'), 'utf8')
    + '\n;window.__loadBranchPreviews = loadBranchPreviews;';
  new Function('window','document','fetch','escHtml','jsArg','safeUrl','toast','gmPrompt','gmAlert','gmConfirm', source)(
    globalThis.window, globalThis.document, globalThis.fetch, escHtml, jsArg, safeUrl,
    globalThis.toast, globalThis.gmPrompt, globalThis.gmAlert, globalThis.gmConfirm
  );
}

describe('composer branch-preview load states', () => {
  let list, sf;
  beforeEach(() => {
    document.body.innerHTML = '';
    list = document.createElement('div'); list.id = 'branch-list';
    document.body.appendChild(list);
    globalThis.document.getElementById = vi.fn((id) => (id === 'branch-list') ? list : null);
    sf = {
      setLoading: vi.fn(() => { const e=document.createElement('div'); e.className='data-state state-loading'; return e; }),
      setEmpty: vi.fn(() => { const e=document.createElement('div'); e.className='data-state state-empty'; return e; }),
      setError: vi.fn(() => { const e=document.createElement('div'); e.className='data-state state-error'; return e; }),
    };
    globalThis.window.stateFeedback = sf;
    globalThis.toast = vi.fn();
    globalThis.gmPrompt = vi.fn();
    globalThis.gmAlert = vi.fn();
    globalThis.gmConfirm = vi.fn();
  });

  it('renders the shared error state (with retry) on a non-ok response', async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: false, status: 500, json: async () => ({ error: 'boom' }) }));
    loadModule();
    await window.__loadBranchPreviews();
    expect(sf.setError).toHaveBeenCalledTimes(1);
    const [, opts] = sf.setError.mock.calls[0];
    expect(opts.retry).toBe('loadBranchPreviews()');
    expect(sf.setEmpty).not.toHaveBeenCalled();
  });

  it('renders the shared error state when the fetch throws', async () => {
    globalThis.fetch = vi.fn(async () => { throw new Error('network down'); });
    loadModule();
    await window.__loadBranchPreviews();
    expect(sf.setError).toHaveBeenCalledTimes(1);
    expect(list.textContent).not.toContain('Loading');
  });

  it('renders the shared empty state only on a genuine healthy empty', async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ branches: [] }) }));
    loadModule();
    await window.__loadBranchPreviews();
    expect(sf.setEmpty).toHaveBeenCalledTimes(1);
    expect(sf.setError).not.toHaveBeenCalled();
  });
});
