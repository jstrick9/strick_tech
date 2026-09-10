/**
 * Access & Sign-in (auth UI + bearer transport).
 *
 * The backend has had a complete auth system (register/login/logout/rotate)
 * since it was written; the frontend had zero call sites for any of it, so
 * the feature was unreachable without curl. These tests cover:
 *
 *   1. source wiring: the single fetch wrapper attaches the session token to
 *      same-origin API calls; Settings → Security renders the card; the
 *      session banner lands on the Security tab;
 *   2. behaviour: the three UI states (auth off / signed out / signed in),
 *      register-then-autologin, throttled (429) sign-in, sign-out, and key
 *      rotation — each through the real module code under jsdom.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const SRC = {
  csrf: readFileSync(resolve(__dirname, '../js/00-csrf.js'), 'utf8'),
  auth: readFileSync(resolve(__dirname, '../js/61-auth-access.js'), 'utf8'),
  core: readFileSync(resolve(__dirname, '../js/01-app-core.js'), 'utf8'),
  banner: readFileSync(resolve(__dirname, '../js/00-session-status.js'), 'utf8'),
  html: readFileSync(resolve(__dirname, '../index.html'), 'utf8'),
};

// ── Source-level wiring ────────────────────────────────────────────────────
describe('auth wiring (source)', () => {
  it('the single fetch wrapper attaches the session bearer token to same-origin API calls', () => {
    expect(SRC.csrf).toMatch(/agentic_os_auth_token/);
    expect(SRC.csrf).toMatch(/headers\.set\('Authorization',\s*'Bearer '\s*\+\s*token\)/);
    // Only for /api/ paths…
    expect(SRC.csrf).toMatch(/u\.pathname\.indexOf\('\/api\/'\)\s*===\s*0/);
    // …only same-origin…
    expect(SRC.csrf).toMatch(/if \(sameOrigin\)/);
    // …and never over a caller-supplied header.
    expect(SRC.csrf).toMatch(/!headers\.has\('Authorization'\)/);
  });

  it('Settings → Security hosts the Access & Sign-in card and loads it on tab open', () => {
    expect(SRC.html).toMatch(/id="auth-access-body"/);
    expect(SRC.html).toMatch(/61-auth-access\.js/);
    expect(SRC.auth).toMatch(/window\.renderAuthAccess\s*=/);
    expect(SRC.core).toMatch(/renderAuthAccess\(\)/);
  });

  it('the lost-session banner routes Sign in to the Security tab', () => {
    expect(SRC.banner).toMatch(/switchSettingsTab\('security'\)/);
  });

  it('the card stores the token through the shared AgenticAPI transport, not ad-hoc storage', () => {
    expect(SRC.auth).toMatch(/AgenticAPI\.setToken/);
    expect(SRC.auth).toMatch(/AgenticAPI\.clearToken/);
  });

  it('handles throttled sign-ins (429) without pretending they were wrong passwords', () => {
    expect(SRC.auth).toMatch(/r\.status === 429/);
    expect(SRC.auth).toMatch(/Retry-After|retryAfter/);
  });
});

// ── Behaviour under jsdom ──────────────────────────────────────────────────
// jsdom's real localStorage lacks the .set/.rm helpers the app's _safeLS
// provides, so the module is handed a faithful shim backed by the same store
// the assertions read.
const LS = {
  get: (k) => { try { return globalThis.localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { globalThis.localStorage.setItem(k, v); } catch {} },
  rm: (k) => { try { globalThis.localStorage.removeItem(k); } catch {} },
};

function loadModule(fetchMock) {
  const source = SRC.auth + '\n;window.__renderAuthAccess = renderAuthAccess;';
  new Function('window', 'document', 'fetch', '_safeLS', 'toast', source)(
    globalThis.window, globalThis.document, fetchMock, LS, globalThis.toast,
  );
}

function jsonRes(status, body, headers) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    headers: { get: (h) => ((headers || {})[h.toLowerCase()]) || null },
  };
}

describe('Access & Sign-in card (behaviour)', () => {
  let host;
  beforeEach(() => {
    document.body.innerHTML = '';
    host = document.createElement('div');
    host.id = 'auth-access-body';
    document.body.appendChild(host);
    globalThis.document.getElementById = vi.fn((id) => (id === 'auth-access-body') ? host : null);
    globalThis.window.AgenticAPI = { setToken: vi.fn(), clearToken: vi.fn() };
    globalThis.window.sessionStatus = { reset: vi.fn() };
    globalThis.toast = vi.fn();
    ['agentic_os_auth_token', 'agentic_os_session_meta'].forEach((k) => globalThis.localStorage.removeItem(k));
  });

  it('auth off: offers to create the first (admin) account', async () => {
    loadModule(vi.fn(async () => jsonRes(200, { ok: true, authenticated: false, auth_configured: false })));
    await window.__renderAuthAccess();
    expect(host.textContent).toContain('Create the first account');
    expect(host.textContent).toContain('administrator');
    // No login form in this state — there is nothing to sign in to yet.
    expect(host.textContent).not.toContain('Need another account');
  });

  it('signed out: shows the sign-in form', async () => {
    loadModule(vi.fn(async () => jsonRes(401, { detail: 'API key required' })));
    await window.__renderAuthAccess();
    expect(host.textContent).toContain('Sign in');
    expect(host.textContent).toContain('Need another account? Register');
  });

  it('signed in: shows identity, and signing out clears the credential everywhere', async () => {
    globalThis.localStorage.setItem('agentic_os_session_meta', JSON.stringify({ username: 'ada', role: 'admin', expires_at: new Date(Date.now() + 3600e3).toISOString() }));
    const me = jsonRes(200, { ok: true, authenticated: true, auth_configured: true, user: { id: 'user_1', username: 'ada', display_name: 'Ada Lovelace', role: 'admin', last_login: '2026-09-09T12:00:00' } });
    const calls = [me, jsonRes(200, { ok: true, revoked: 1 })];
    loadModule(vi.fn(async () => calls.shift()));
    await window.__renderAuthAccess();
    expect(host.textContent).toContain('Ada Lovelace');
    expect(host.textContent).toContain('@ada');
    expect(host.textContent).toContain('role: admin');

    const signOut = Array.from(host.querySelectorAll('button')).find((b) => b.textContent === 'Sign out');
    expect(signOut).toBeTruthy();
    signOut.click();
    await vi.waitFor(() => expect(window.AgenticAPI.clearToken).toHaveBeenCalledTimes(1));
    expect(globalThis.localStorage.getItem('agentic_os_session_meta')).toBeNull();
    expect(window.sessionStatus.reset).toHaveBeenCalled();
  });

  it('login success: stores the token and session metadata', async () => {
    globalThis.localStorage.setItem('agentic_os_auth_token', 'ses_stale');
    const login = jsonRes(200, {
      ok: true, token: 'ses_fresh', expires_at: new Date(Date.now() + 43200e3).toISOString(),
      user: { username: 'grace', display_name: 'Grace', role: 'user' },
    });
    let n = 0;
    loadModule(vi.fn(async () => (n++ === 0 ? jsonRes(401, { detail: 'API key required' }) : login)));
    await window.__renderAuthAccess();

    const form = host.querySelector('form');
    form.querySelector('input[type="text"]').value = 'grace';
    form.querySelector('input[type="password"]').value = 'secret123';
    form.dispatchEvent(new Event('submit'));
    await vi.waitFor(() => expect(window.AgenticAPI.setToken).toHaveBeenCalledWith('ses_fresh'));
    const meta = JSON.parse(globalThis.localStorage.getItem('agentic_os_session_meta') || '{}');
    expect(meta.username).toBe('grace');
    expect(meta.role).toBe('user');
    expect(meta.expires_at).toBeTruthy();
  });

  it('login throttled (429): surfaces the wait instead of "invalid password"', async () => {
    let n = 0;
    loadModule(vi.fn(async () => (n++ === 0
      ? jsonRes(401, { detail: 'API key required' })
      : jsonRes(429, { ok: false, error: 'Too many failed sign-in attempts for this account. Try again in 742s.' }, { 'retry-after': '742' }))));
    await window.__renderAuthAccess();
    const form = host.querySelector('form');
    form.querySelector('input[type="text"]').value = 'victim';
    form.querySelector('input[type="password"]').value = 'guess';
    form.dispatchEvent(new Event('submit'));
    await vi.waitFor(() => expect(host.textContent).toContain('Too many failed sign-in attempts'));
    // It must NOT have been mistaken for a credentials error, and no token stored.
    expect(window.AgenticAPI.setToken).not.toHaveBeenCalled();
  });

  it('register: reveals the API key exactly once, then signs the new account in', async () => {
    const calls = [
      jsonRes(200, { ok: true, authenticated: false, auth_configured: false }),
      jsonRes(200, { ok: true, user_id: 'user_2', username: 'newbie', role: 'admin', api_key: 'ak_onceonly123', message: 'Save your API key — it is shown only once.' }),
      jsonRes(200, { ok: true, token: 'ses_new', expires_at: new Date(Date.now() + 43200e3).toISOString(), user: { username: 'newbie', display_name: 'Newbie', role: 'admin' } }),
    ];
    loadModule(vi.fn(async () => calls.shift()));
    await window.__renderAuthAccess();

    const form = host.querySelector('form');
    const inputs = form.querySelectorAll('input');
    inputs[0].value = 'newbie';           // username
    inputs[1].value = 'Newbie';           // display name
    inputs[2].value = 'hunter22';         // password
    inputs[3].value = 'hunter22';         // confirm
    form.dispatchEvent(new Event('submit'));

    await vi.waitFor(() => expect(host.textContent).toContain('Shown only once'));
    const field = host.querySelector('input[aria-label^="Credential"]');
    expect(field.value).toBe('ak_onceonly123');
    // Auto-login followed the reveal.
    await vi.waitFor(() => expect(window.AgenticAPI.setToken).toHaveBeenCalledWith('ses_new'));
    // The reveal persists until dismissed — it must NOT be on a timer that
    // replaces the only copy of the key before the user can copy it.
    const cont = Array.from(host.querySelectorAll('button')).find((b) => b.textContent === 'Continue →');
    expect(cont).toBeTruthy();
    expect(host.textContent).toContain('Signed in.');
  });

  it('rotate key: shows the new key once and notes the old one is dead', async () => {
    globalThis.localStorage.setItem('agentic_os_session_meta', JSON.stringify({ username: 'ada', role: 'admin', expires_at: '' }));
    const calls = [
      jsonRes(200, { ok: true, authenticated: true, auth_configured: true, user: { id: 'user_1', username: 'ada', display_name: 'Ada', role: 'admin', last_login: '' } }),
      jsonRes(200, { ok: true, api_key: 'ak_rotated_456', message: 'New API key generated. Old key is now invalid.' }),
    ];
    loadModule(vi.fn(async () => calls.shift()));
    await window.__renderAuthAccess();

    const rotate = Array.from(host.querySelectorAll('button')).find((b) => b.textContent === 'Rotate API key');
    rotate.click();
    await vi.waitFor(() => expect(host.textContent).toContain('Shown only once'));
    expect(host.textContent).toContain('no longer works');
    const field = host.querySelector('input[aria-label^="Credential"]');
    expect(field.value).toBe('ak_rotated_456');
  });

  it('server unreachable: an error card, not an eternal spinner', async () => {
    loadModule(vi.fn(async () => { throw new Error('boom'); }));
    await window.__renderAuthAccess();
    expect(host.textContent).toContain('Could not reach the server');
  });
});
