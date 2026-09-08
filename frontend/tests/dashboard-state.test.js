// UX regression: the Dashboard must route its loading/error states through the
// shared stateFeedback component (consistent + accessible), not a bespoke
// inline-styled div. Asserts both the loading call on entry and the error path
// on a failed fetch.
import { describe, it, expect, beforeEach, vi } from 'vitest';

function escHtml(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c])); }
function humanError(e) { return (e && e.message) || 'request failed'; }

function loadModule() {
  const fs = require('fs'); const path = require('path');
  const source = fs.readFileSync(path.join(__dirname, '..', 'js', '36-dashboard.js'), 'utf8')
    + '\n;window.renderDashboard = renderDashboard;';
  new Function('window','document','fetch','setTimeout','clearTimeout','escHtml','humanError','httpError','renderDashBody','exportDashboardCSV', source)(
    globalThis.window, globalThis.document, globalThis.fetch, setTimeout, clearTimeout,
    escHtml, humanError, (e) => ({ message: 'HTTP '+e }), () => {}, () => {}
  );
}

describe('Dashboard uses the shared state component', () => {
  let pane, body, sf;
  beforeEach(() => {
    document.body.innerHTML = '';
    pane = document.createElement('div');
    pane.id = 'pane-dashboard';
    document.body.appendChild(pane);
    // setup.js mocks getElementById -> null; override for the ids the module needs.
    globalThis.document.getElementById = vi.fn((id) => {
      return (id === 'pane-dashboard') ? pane
        : (id === 'dash-body') ? pane.querySelector('#dash-body')
        : (id === 'dash-days') ? { value: '30' }
        : null;
    });
    // Spy on the shared component.
    sf = {
      setLoading: vi.fn(() => { const e = document.createElement('div'); e.className='data-state state-loading'; return e; }),
      setError: vi.fn(() => { const e = document.createElement('div'); e.className='data-state state-error'; return e; }),
    };
    globalThis.window.stateFeedback = sf;
  });

  it('sets a loading state on entry, then renders the body on success', async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: true, json: async () => ({ ok: true }) }));
    // renderDashBody writes into #dash-body; stub it to insert nothing (we only
    // assert the loading transition + no error).
    await loadModule();
    globalThis.renderDashBody = () => {};
    // Re-run with renderDashBody available
    const fs = require('fs'); const path = require('path');
    const source = fs.readFileSync(path.join(__dirname, '..', 'js', '36-dashboard.js'), 'utf8');
    new Function('window','document','fetch','setTimeout','clearTimeout','escHtml','humanError','httpError','renderDashBody', source)(
      globalThis.window, globalThis.document, globalThis.fetch, setTimeout, clearTimeout,
      escHtml, humanError, (e)=>({message:'HTTP '+e}), () => {}
    );
    await window.renderDashboard();
    expect(sf.setLoading).toHaveBeenCalledWith(pane.querySelector('#dash-body'), { label: 'Loading dashboard…' });
    expect(sf.setError).not.toHaveBeenCalled();
  });

  it('renders the shared error state (with Retry) when the fetch fails', async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: false, status: 500, message: 'boom' }));
    await loadModule();
    await window.renderDashboard();
    expect(sf.setError).toHaveBeenCalledTimes(1);
    const call = sf.setError.mock.calls[0];
    const [el, opts] = call;
    expect(el).toBe(pane.querySelector('#dash-body'));
    expect(opts.retry).toBe('renderDashboard()');
  });
});
