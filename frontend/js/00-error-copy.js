// Agentic OS — human error copy
//
// THE PROBLEM
// ───────────
// Forcing every /api/ call to return HTTP 500 and walking all 68 panes, twelve
// of them showed internal detail in the place reserved for an explanation:
//
//     templates   Failed to load templates: Templates API: HTTP 500
//     galaxy      Load failed — HTTP 500
//     obsidian    Error loading Obsidian status: HTTP 500
//     control     runs.filter is not a function
//     testgen     files.filter is not a function
//     profiler    DB size: undefined KB
//
// "HTTP 500" tells a developer where to look and tells everyone else nothing.
// "runs.filter is not a function" is not an error message, it is a stack
// frame. Neither says what happened, whether the user's data is safe, or what
// to do next -- the three things a person actually needs at that moment.
//
// THE APPROACH
// ────────────
// One function that turns a thrown error or a failed Response into a sentence,
// rather than rewriting ~110 call sites by hand. Call sites opt in by passing
// their error through `humanError()`; the technical detail is preserved for
// support and debugging, but demoted so it is not the headline.
//
// Guidance encoded here, in priority order:
//   1. Say what failed, in the user's terms  ("Couldn't load your templates")
//   2. Reassure about data when relevant     ("Nothing was lost")
//   3. Say what to do                        ("Try again")
//   4. Keep the technical detail available, in parentheses, last
'use strict';

(function () {
  // Maps an HTTP status to what it means for the person, not the protocol.
  var BY_STATUS = {
    400: 'The app sent something the server could not read.',
    401: 'You need to sign in again.',
    403: 'You do not have permission to do that.',
    404: 'That is no longer here — it may have been deleted or renamed.',
    408: 'The server took too long to respond.',
    409: 'Someone else changed this first. Reload to get the latest version.',
    413: 'That is too large to upload.',
    422: 'Some of the details were not valid.',
    429: 'Too many requests at once — wait a moment and try again.',
    500: 'The server ran into a problem.',
    502: 'The server is not reachable right now.',
    503: 'The service is temporarily unavailable.',
    504: 'The server took too long to respond.',
  };

  // Raw JS runtime errors. These reach the UI when a response shape is
  // unexpected -- almost always a symptom of a failed request, not a genuine
  // "bug in your data", so they are reported as a load failure.
  var RUNTIME_NOISE = /(is not a function|Cannot read propert|Cannot set propert|undefined is not|null is not|NetworkError|Failed to fetch|Load failed|Unexpected token|JSON\.parse|is not valid JSON)/i;

  function statusSentence(status) {
    if (!status) return null;
    if (BY_STATUS[status]) return BY_STATUS[status];
    if (status >= 500) return 'The server ran into a problem.';
    if (status >= 400) return 'That request could not be completed.';
    return null;
  }

  /**
   * Turn an error into a sentence a person can act on.
   *
   * @param {Error|Response|string} err   what went wrong
   * @param {Object}  [opts]
   * @param {string}  [opts.action]       what the user was doing, e.g. "load your templates"
   * @param {boolean} [opts.dataSafe]     append the reassurance that nothing was lost
   * @param {boolean} [opts.detail=true]  keep the technical detail in parentheses
   */
  function humanError(err, opts) {
    opts = opts || {};
    var status = null;
    var technical = '';

    if (err && typeof err === 'object') {
      if (typeof err.status === 'number') status = err.status;
      technical = err.message || err.statusText || '';
    } else if (typeof err === 'string') {
      technical = err;
    }

    // Pull a status out of text like "HTTP 500" when the caller only has a
    // string. This is what makes the function useful at existing call sites
    // that already stringified their error.
    if (!status && technical) {
      var m = technical.match(/\b(?:HTTP\s*)?(\d{3})\b/);
      if (m) {
        var code = parseInt(m[1], 10);
        if (code >= 400 && code <= 599) status = code;
      }
    }

    var lead = opts.action
      ? 'Couldn\u2019t ' + opts.action + '.'
      : 'Something went wrong.';

    var why = statusSentence(status);
    if (!why && RUNTIME_NOISE.test(technical)) {
      // The user does not benefit from knowing a property was undefined.
      why = 'The response from the server was not what the app expected.';
    }

    var parts = [lead];
    if (why) parts.push(why);
    if (opts.dataSafe) parts.push('Nothing was lost.');

    var sentence = parts.join(' ');

    // Technical detail is kept, but demoted to the end in parentheses so it
    // is available for a bug report without being the headline.
    if (opts.detail !== false && technical) {
      var shown = String(technical).trim().slice(0, 120);
      // Do not repeat a bare status code we have already explained in words.
      if (!/^(HTTP\s*)?\d{3}$/.test(shown)) sentence += ' (' + shown + ')';
    }
    return sentence;
  }

  /**
   * Convenience for the very common `if (!response.ok) throw ...` shape.
   * Produces an Error carrying `.status`, so humanError() can explain it.
   */
  function httpError(response, action) {
    var e = new Error(
      (response && response.statusText) || ('Request failed (' + (response && response.status) + ')')
    );
    e.status = response && response.status;
    e.action = action;
    return e;
  }

  window.humanError = humanError;
  window.httpError = httpError;
})();
