// Frontend UX: the shared inline state components must render consistent,
// accessible loading/empty/error states and never stack on top of each other.
// Regression coverage for js/00-state-feedback.js (CSS contract lives in
// styles-system.css; here we assert the DOM + ARIA contract).
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

function loadModule() {
  const fs = require('fs'); const path = require('path');
  const source = fs.readFileSync(path.join(__dirname, '..', 'js', '00-state-feedback.js'), 'utf8');
  // Expose internals for assertions by appending a hook before the IIFE close.
  new Function('window', 'document', source)(globalThis.window, globalThis.document);
}

describe('stateFeedback inline states', () => {
  let host;
  beforeEach(() => {
    // setup.js mocks getElementById to return null for non-app ids, so build
    // the host element directly instead.
    document.body.innerHTML = '';
    host = document.createElement('div');
    document.body.appendChild(host);
    globalThis.window.matchMedia = vi.fn(() => ({ matches: false }));
    loadModule();
  });
  afterEach(() => { delete globalThis.window.announceToScreenReader; });

  it('setLoading renders a role=status node with aria-live', () => {
    const el = window.stateFeedback.setLoading(host, { label: 'Fetching data' });
    expect(el.className).toContain('state-loading');
    expect(el.getAttribute('role')).toBe('status');
    expect(el.getAttribute('aria-live')).toBe('polite');
    expect(el.querySelector('.data-state-spinner')).toBeTruthy();
    expect(el.textContent).toContain('Fetching data');
  });

  it('loading honours prefers-reduced-motion', () => {
    window.matchMedia = vi.fn(() => ({ matches: true }));
    const el = window.stateFeedback.setLoading(host, {});
    expect(el.classList.contains('state-reduced-motion')).toBe(true);
  });

  it('setEmpty renders no role and carries an optional action button', () => {
    const el = window.stateFeedback.setEmpty(host, {
      icon: '📭', title: 'No runs yet', message: 'Run your first task to see it here.',
      action: "showPrompt('run')", actionLabel: 'Run a task',
    });
    expect(el.className).toContain('state-empty');
    expect(el.getAttribute('role')).toBeNull();
    expect(el.textContent).toContain('No runs yet');
    const btn = el.querySelector('button');
    expect(btn).toBeTruthy();
    // action expression survives as a quoted attribute (not truncated by a quote)
    expect(btn.getAttribute('data-act-click')).toBe("showPrompt('run')");
  });

  it('setError renders role=alert with a Retry button and announces', () => {
    const ann = vi.fn();
    globalThis.window.announceToScreenReader = ann;
    const el = window.stateFeedback.setError(host, { title: 'Couldn’t load', message: 'Server 500', retry: 'renderDashboard()' });
    expect(el.className).toContain('state-error');
    expect(el.getAttribute('role')).toBe('alert');
    expect(el.getAttribute('aria-live')).toBe('assertive');
    expect(el.textContent).toContain('Server 500');
    expect(el.querySelector('button').getAttribute('data-act-click')).toBe('renderDashboard()');
    expect(ann).toHaveBeenCalled();
  });

  it('replacing a state removes the previous one (no stacking)', () => {
    window.stateFeedback.setLoading(host);
    window.stateFeedback.setEmpty(host, { title: 'Nothing' });
    window.stateFeedback.setError(host, { title: 'Broken' });
    expect(host.querySelectorAll('.data-state').length).toBe(1);
    expect(host.querySelector('.data-state').classList.contains('state-error')).toBe(true);
  });

  it('clearState removes the injected node', () => {
    window.stateFeedback.setError(host, { title: 'x' });
    window.stateFeedback.clearState(host);
    expect(host.querySelectorAll('.data-state').length).toBe(0);
  });

  it('escapes injected strings so state text cannot inject markup', () => {
    const el = window.stateFeedback.setEmpty(host, { title: '<img src=x onerror=alert(1)>', message: '<script>x</script>' });
    expect(el.querySelector('img')).toBeNull();
    expect(el.querySelector('script')).toBeNull();
    expect(el.textContent).toContain('<img src=x onerror=alert(1)>');
  });
});
