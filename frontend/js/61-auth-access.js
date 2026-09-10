// Agentic OS — Access & Sign-in (Settings → Security)
// ───────────────────────────────────────────────────────────────────────────
// THE GAP THIS CLOSES
// The backend has had a complete auth system since it was written —
// register, login, logout, /me, key rotation — and the frontend had no way
// to use any of it. Not one screen, button, or call site. The terminal's
// "authentication required" error told users to run
// `POST /api/auth/register` with curl; the session banner's "Sign in"
// button opened Settings, which had no sign-in form. An entire feature,
// built and tested server-side, unreachable by anyone who does not read
// API docs.
//
// This renders three states into Settings → Security, discovered from
// GET /api/auth/me:
//   * auth OFF            → create the first account (becomes admin)
//   * configured, signed out → sign in (with a register toggle)
//   * signed in           → identity, session expiry, sign out, rotate key
//
// The session token itself never touches this file's logic: login stores it
// through AgenticAPI.setToken(), and 00-csrf.js (the app's single fetch
// wrapper) attaches it to every same-origin API call. Sign-out removes it
// the same way.
'use strict';

(function () {
  var META_KEY = 'agentic_os_session_meta';

  function el(tag, css, text) {
    var n = document.createElement(tag);
    if (css) n.style.cssText = css;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function inputEl(type, placeholder, autocomplete) {
    var i = el('input',
      'width:100%;padding:8px 10px;background:var(--bg-2);border:1px solid var(--border-hi);' +
      'border-radius:8px;color:var(--text-0);font-size:13px;margin-bottom:10px;box-sizing:border-box;outline:none');
    i.type = type;
    if (placeholder) i.placeholder = placeholder;
    if (autocomplete) i.setAttribute('autocomplete', autocomplete);
    return i;
  }

  function buttonEl(label, kind) {
    var b = el('button', 'padding:8px 14px;border-radius:8px;font-weight:700;font-size:12.5px;cursor:pointer;border:1px solid transparent');
    b.type = 'submit';
    b.className = 'btn btn-sm ' + (kind || 'btn-primary');
    b.textContent = label;
    return b;
  }

  function readMeta() {
    try {
      var raw = _safeLS.get(META_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch (e) { return {}; }
  }

  function writeMeta(m) { try { _safeLS.set(META_KEY, JSON.stringify(m)); } catch (e) { /* private mode */ } }
  function clearMeta() { try { _safeLS.rm(META_KEY); } catch (e) { /* private mode */ } }

  function fmtExpiry(iso) {
    if (!iso) return '';
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return '';
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (e) { return ''; }
  }

  // ── One-shot credential reveal (register / rotate) ─────────────────────
  function revealOnceBox(host, secret, note) {
    var box = el('div',
      'background:var(--bg-3);border:1px solid var(--warning);border-radius:10px;padding:12px;margin-bottom:14px');
    box.appendChild(el('div', 'font-size:12px;font-weight:800;color:var(--warning);margin-bottom:6px',
      '⚠ Shown only once — copy it now'));
    var row = el('div', 'display:flex;gap:8px;align-items:center');
    var field = el('input',
      'flex:1;padding:7px 9px;background:var(--bg-1);border:1px solid var(--border-hi);border-radius:7px;' +
      'color:var(--text-0);font-family:monospace;font-size:12px');
    field.type = 'text';
    field.readOnly = true;
    field.value = secret;
    field.setAttribute('aria-label', 'Credential, shown once');
    var copy = el('button', 'padding:7px 12px;border-radius:7px;font-weight:700;font-size:12px;cursor:pointer');
    copy.type = 'button';
    copy.className = 'btn btn-sm btn-ghost';
    copy.textContent = 'Copy';
    copy.addEventListener('click', function () {
      field.select();
      field.setSelectionRange(0, 9999);
      var done = function () { copy.textContent = 'Copied ✓'; setTimeout(function () { copy.textContent = 'Copy'; }, 1600); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(secret).then(done, function () {
          try { document.execCommand('copy'); done(); } catch (e) { /* selection remains */ }
        });
      } else {
        try { document.execCommand('copy'); done(); } catch (e) { /* selection remains */ }
      }
    });
    row.appendChild(field);
    row.appendChild(copy);
    box.appendChild(row);
    if (note) box.appendChild(el('div', 'font-size:11.5px;color:var(--text-3);margin-top:6px', note));
    host.appendChild(box);
  }

  function errorLine(host, message) {
    var n = el('div',
      'color:var(--danger);font-size:12.5px;margin:0 0 10px;line-height:1.5', message);
    host.appendChild(n);
    return n;
  }

  async function api(path, method, body) {
    var init = { method: method || 'GET', headers: { 'Content-Type': 'application/json' } };
    if (body !== undefined) init.body = JSON.stringify(body);
    var r = await fetch(path, init);
    var data = null;
    try { data = await r.json(); } catch (e) { data = null; }
    return { status: r.status, ok: r.ok, data: data || {}, retryAfter: r.headers.get('Retry-After') };
  }

  function afterAuthChange() {
    // A sign-in/out changes what every other pane is allowed to do; the
    // banner watches responses and will clear itself, but resetting it here
    // makes the intent explicit and immediate.
    if (window.sessionStatus && window.sessionStatus.reset) { try { window.sessionStatus.reset(); } catch (e) { /* banner is optional */ } }
    window.renderAuthAccess();
  }

  // ── State renderers ────────────────────────────────────────────────────
  function renderRegisterForm(host, opts) {
    opts = opts || {};
    var form = el('form', 'max-width:380px');
    var heading = el('div', 'font-size:13px;font-weight:800;color:var(--text-0);margin-bottom:4px',
      opts.first ? 'Create the first account' : 'Create an account');
    form.appendChild(heading);
    if (opts.first) {
      form.appendChild(el('div', 'font-size:12px;color:var(--text-2);margin-bottom:12px;line-height:1.5',
        'Authentication is currently OFF — this app is open to anyone who can reach it. The first account you create becomes the administrator.'));
    }
    var username = inputEl('text', 'Username', 'username');
    var display = inputEl('text', 'Display name (optional)', 'name');
    var password = inputEl('password', 'Password (min 6 chars)', 'new-password');
    var confirm = inputEl('password', 'Confirm password', 'new-password');
    [username, display, password, confirm].forEach(function (f) { form.appendChild(f); });
    var submit = buttonEl(opts.first ? 'Create admin account' : 'Create account', 'btn-primary');
    form.appendChild(submit);

    form.addEventListener('submit', async function (ev) {
      ev.preventDefault();
      form.querySelectorAll('.auth-err').forEach(function (n) { n.remove(); });
      if (password.value !== confirm.value) {
        errorLine(form, 'Passwords do not match.');
        return;
      }
      submit.disabled = true;
      try {
        var r = await api('/api/auth/register', 'POST', {
          username: username.value.trim(),
          password: password.value,
          display_name: display.value.trim(),
        });
        if (!r.ok) {
          errorLine(form, (r.data && r.data.error) || ('Registration failed (HTTP ' + r.status + ').'));
          return;
        }
        // The API key is shown exactly once, here. Then sign the new account
        // straight in so the user never has to type the password again.
        var revealHost = el('div');
        revealOnceBox(revealHost, r.data.api_key, r.data.message || '');
        form.replaceWith(revealHost);
        var lr = await api('/api/auth/login', 'POST', { username: username.value.trim(), password: password.value });
        if (lr.ok && lr.data.token) {
          if (window.AgenticAPI && window.AgenticAPI.setToken) window.AgenticAPI.setToken(lr.data.token);
          writeMeta({
            username: lr.data.user ? lr.data.user.username : username.value.trim(),
            display_name: lr.data.user ? lr.data.user.display_name : '',
            role: lr.data.user ? lr.data.user.role : 'user',
            expires_at: lr.data.expires_at || '',
          });
        }
        revealHost.appendChild(el('div', 'font-size:12px;color:var(--success);margin-bottom:10px', 'Signed in.'));
        // The reveal STAYS until the user leaves it. An earlier version
        // re-rendered the signed-in card on a 1.4s timer, which replaced the
        // only copy of the key most users will ever see before they could
        // reach the Copy button — "shown only once" must not mean "shown for
        // 1.4 seconds".
        var cont = buttonEl('Continue →', 'btn-primary');
        cont.type = 'button';
        cont.addEventListener('click', afterAuthChange);
        revealHost.appendChild(cont);
      } finally {
        submit.disabled = false;
      }
    });
    host.appendChild(form);
  }

  function renderLoginForm(host) {
    var form = el('form', 'max-width:380px');
    form.appendChild(el('div', 'font-size:13px;font-weight:800;color:var(--text-0);margin-bottom:10px', 'Sign in'));
    var username = inputEl('text', 'Username', 'username');
    var password = inputEl('password', 'Password', 'current-password');
    form.appendChild(username);
    form.appendChild(password);
    var submit = buttonEl('Sign in', 'btn-primary');
    submit.style.marginRight = '8px';
    form.appendChild(submit);

    form.addEventListener('submit', async function (ev) {
      ev.preventDefault();
      form.querySelectorAll('.auth-err').forEach(function (n) { n.remove(); });
      submit.disabled = true;
      try {
        var r = await api('/api/auth/login', 'POST', { username: username.value.trim(), password: password.value });
        if (r.status === 429) {
          var secs = r.retryAfter || 'a few minutes';
          errorLine(form, (r.data && r.data.error) || ('Too many attempts. Try again in ' + secs + 's.'));
          return;
        }
        if (!r.ok) {
          errorLine(form, (r.data && r.data.error) || ('Sign-in failed (HTTP ' + r.status + ').'));
          return;
        }
        if (r.data.token) {
          if (window.AgenticAPI && window.AgenticAPI.setToken) window.AgenticAPI.setToken(r.data.token);
          writeMeta({
            username: r.data.user ? r.data.user.username : username.value.trim(),
            display_name: r.data.user ? r.data.user.display_name : '',
            role: r.data.user ? r.data.user.role : 'user',
            expires_at: r.data.expires_at || '',
          });
        }
        if (typeof toast === 'function') { try { toast('Signed in as ' + (r.data.user ? r.data.user.username : ''), 'success'); } catch (e) { /* toast is optional */ } }
        afterAuthChange();
      } finally {
        submit.disabled = false;
      }
    });
    host.appendChild(form);

    // Registration stays open by design in this local-first app; keep it one
    // deliberate click away rather than hiding it.
    var toggle = el('button',
      'background:none;border:none;color:var(--accent-text);font-size:12px;cursor:pointer;padding:6px 0;text-align:left');
    toggle.type = 'button';
    toggle.textContent = 'Need another account? Register →';
    toggle.addEventListener('click', function () {
      host.textContent = '';
      renderRegisterForm(host, { first: false });
      var back = el('button',
        'background:none;border:none;color:var(--text-3);font-size:12px;cursor:pointer;padding:6px 0');
      back.type = 'button';
      back.textContent = '← Back to sign in';
      back.addEventListener('click', function () {
        host.textContent = '';
        renderLoginForm(host);
      });
      host.appendChild(back);
    });
    host.appendChild(toggle);
  }

  function renderSignedIn(host, me) {
    var meta = readMeta();
    var user = (me && me.user) || {};
    var card = el('div',
      'background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px;max-width:520px');
    card.appendChild(el('div', 'font-size:15px;font-weight:800;color:var(--text-0);margin-bottom:2px',
      (user.display_name || user.username || meta.username || 'Signed in')));
    card.appendChild(el('div', 'font-size:12px;color:var(--text-3);margin-bottom:12px',
      '@' + (user.username || meta.username || 'user') + ' · role: ' + (user.role || meta.role || 'user')));

    if (user.last_login || meta.expires_at) {
      var bits = [];
      if (user.last_login) bits.push('Last sign-in: ' + String(user.last_login).replace('T', ' ').slice(0, 16));
      var until = fmtExpiry(meta.expires_at);
      if (until) bits.push('Session valid until ~' + until);
      card.appendChild(el('div', 'font-size:12px;color:var(--text-2);margin-bottom:14px;line-height:1.6', bits.join('  ·  ')));
    }

    var row = el('div', 'display:flex;gap:8px;flex-wrap:wrap');
    var signOut = buttonEl('Sign out', 'btn-ghost');
    signOut.type = 'button';
    signOut.addEventListener('click', async function () {
      signOut.disabled = true;
      try { await api('/api/auth/logout', 'POST'); } catch (e) { /* the token is cleared locally regardless */ }
      if (window.AgenticAPI && window.AgenticAPI.clearToken) window.AgenticAPI.clearToken();
      clearMeta();
      afterAuthChange();
    });
    row.appendChild(signOut);

    var rotate = buttonEl('Rotate API key', 'btn-ghost');
    rotate.type = 'button';
    rotate.title = 'Invalidate the current API key and issue a new one. Scripted clients using the old key stop working immediately.';
    rotate.addEventListener('click', async function () {
      rotate.disabled = true;
      try {
        var r = await api('/api/auth/rotate-key', 'POST');
        if (r.ok && r.data.api_key) {
          host.textContent = '';
          revealOnceBox(host, r.data.api_key, r.data.message || '');
          var done = el('div', 'font-size:13px;color:var(--text-0)', 'Your previous API key no longer works. Your current sign-in session is unaffected.');
          host.appendChild(done);
        } else {
          errorLine(host, (r.data && r.data.error) || ('Rotation failed (HTTP ' + r.status + ').'));
        }
      } finally { rotate.disabled = false; }
    });
    row.appendChild(rotate);
    card.appendChild(row);
    host.appendChild(card);
  }

  // ── Entry point ────────────────────────────────────────────────────────
  window.renderAuthAccess = async function () {
    var host = document.getElementById('auth-access-body');
    if (!host) return;
    host.textContent = '';
    // stateFeedback.loadingElement returns an HTML STRING (see 58-csp-monitor,
    // which assigns it the same way) — appendChild would throw.
    if (window.stateFeedback && typeof window.stateFeedback.loadingElement === 'function') {
      host.innerHTML = window.stateFeedback.loadingElement('Loading…');
    } else {
      host.textContent = 'Loading…';
    }

    var me;
    try {
      me = await api('/api/auth/me');
    } catch (err) {
      host.textContent = '';
      errorLine(host, 'Could not reach the server: ' + err.message);
      return;
    }

    host.textContent = '';
    if (me.status === 401) {
      // Users exist and the request carried no valid credential: signed out.
      renderLoginForm(host);
      return;
    }
    if (!me.ok) {
      errorLine(host, (me.data && me.data.error) || ('Unexpected response (HTTP ' + me.status + ').'));
      return;
    }
    if (me.data.authenticated) {
      renderSignedIn(host, me.data);
      return;
    }
    // Auth not configured at all: offer to create the first (admin) account.
    renderRegisterForm(host, { first: !me.data.auth_configured });
  };
})();
