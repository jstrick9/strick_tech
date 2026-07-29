// Agentic OS — shared API transport
// Keeps request headers, secure-mode token handling, JSON parsing, and errors
// in one place while legacy feature modules migrate incrementally.
'use strict';
// NOTE: _safeLS is declared once in 00-store.js (loaded before this file) and
// is available here via the shared top-level script scope. Do not redeclare
// it — a duplicate `const _safeLS` in a later <script> tag throws a
// SyntaxError ("Identifier '_safeLS' has already been declared") which
// aborts this entire file, silently killing window.AgenticAPI.

(function() {
  const TOKEN_KEY = 'agentic_os_auth_token';

  function authHeaders(headers) {
    const out = Object.assign({}, headers || {});
    const token = _safeLS.get(TOKEN_KEY);
    if (token && !out.Authorization) out.Authorization = `Bearer ${token}`;
    return out;
  }

  async function request(path, options) {
    const opts = Object.assign({}, options || {});
    opts.headers = authHeaders(Object.assign({'Content-Type': 'application/json'}, opts.headers || {}));
    const response = await fetch(path, opts);
    let body = null;
    try { body = await response.json(); } catch (_) { body = null; }
    if (!response.ok) {
      const error = new Error((body && body.error) || `Request failed (${response.status})`);
      error.status = response.status;
      error.body = body;
      throw error;
    }
    return body;
  }

  window.AgenticAPI = {
    request,
    get: (path, options) => request(path, Object.assign({}, options || {}, {method: 'GET'})),
    post: (path, data, options) => request(path, Object.assign({}, options || {}, {method: 'POST', body: JSON.stringify(data || {})})),
    patch: (path, data, options) => request(path, Object.assign({}, options || {}, {method: 'PATCH', body: JSON.stringify(data || {})})),
    delete: (path, options) => request(path, Object.assign({}, options || {}, {method: 'DELETE'})),
    setToken: (token) => token ? _safeLS.set(TOKEN_KEY, token) : _safeLS.rm(TOKEN_KEY),
    clearToken: () => _safeLS.rm(TOKEN_KEY),
    websocketUrl: (path) => {
      let token = null; try { token = _safeLS.get(TOKEN_KEY); } catch {}
      if (!token) return path;
      const joiner = path.includes('?') ? '&' : '?';
      return `${path}${joiner}token=${encodeURIComponent(token)}`;
    },
  };
})();
