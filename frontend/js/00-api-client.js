// Agentic OS — shared API transport
// Keeps request headers, secure-mode token handling, JSON parsing, and errors
// in one place while legacy feature modules migrate incrementally.
'use strict';

(function() {
  const TOKEN_KEY = 'agentic_os_auth_token';

  function authHeaders(headers) {
    const out = Object.assign({}, headers || {});
    const token = window.localStorage.getItem(TOKEN_KEY);
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
    setToken: (token) => token ? localStorage.setItem(TOKEN_KEY, token) : localStorage.removeItem(TOKEN_KEY),
    clearToken: () => localStorage.removeItem(TOKEN_KEY),
    websocketUrl: (path) => {
      const token = localStorage.getItem(TOKEN_KEY);
      if (!token) return path;
      const joiner = path.includes('?') ? '&' : '?';
      return `${path}${joiner}token=${encodeURIComponent(token)}`;
    },
  };
})();
