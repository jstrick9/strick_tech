// Agentic OS — CSP violation monitor
// ───────────────────────────────────────────────────────────────────────────
// The Report-Only Content-Security-Policy has been collecting violations at
// /api/security/csp-report since it was introduced, and nobody could see them
// without curling the endpoint. That is how the channel managed to sit at zero
// for weeks without anyone noticing: CSRF was rejecting every report with a
// 403, and the only way to find out was to ask the API directly.
//
// This surfaces the data in Settings → Security. It answers one question:
// "if we tightened the policy, what would break, and where?"
//
// The header is deliberately ONE RATCHET ahead of what is enforced. Right now
// it previews strict `style-src` — the last major weakness — so every inline
// style that WOULD be refused is reported while nothing actually breaks.
(function () {
  'use strict';

  var ENDPOINT = '/api/security/csp-report';

  function el(tag, css, text) {
    var n = document.createElement(tag);
    if (css) n.style.cssText = css;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function shortSource(src) {
    if (!src) return '(unknown)';
    try {
      var u = new URL(src, window.location.origin);
      var external = u.origin !== window.location.origin;
      var name = u.pathname.split('/').filter(Boolean).pop() || u.pathname;
      return (external ? '⧉ ' : '') + name;
    } catch (_) {
      return String(src).slice(-48);
    }
  }

  function isThirdParty(src) {
    if (!src) return false;
    try {
      return new URL(src, window.location.origin).origin !== window.location.origin;
    } catch (_) {
      return false;
    }
  }

  window.renderCspMonitor = async function () {
    var host = document.getElementById('csp-monitor-body');
    if (!host) return;
    host.textContent = 'Loading…';

    var data;
    try {
      var r = await fetch(ENDPOINT);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      data = await r.json();
    } catch (err) {
      host.textContent = '';
      host.appendChild(el('div',
        'color:var(--danger);font-size:13px', 'Could not load reports: ' + err.message));
      return;
    }

    var rows = data.violations || [];
    host.textContent = '';

    // ── Summary ──
    var ours = rows.filter(function (v) { return !isThirdParty(v.source_file); });
    var theirs = rows.filter(function (v) { return isThirdParty(v.source_file); });

    var summary = el('div',
      'display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:18px');
    [
      ['Distinct sites', data.distinct || 0, 'var(--text-0)'],
      ['Total events', data.total || 0, 'var(--text-0)'],
      ['In our code', ours.length, ours.length ? 'var(--warning)' : 'var(--success)'],
      ['Third-party', theirs.length, 'var(--text-2)'],
    ].forEach(function (spec) {
      var card = el('div',
        'background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:12px');
      var val = el('div', 'font-size:22px;font-weight:800;color:' + spec[2], String(spec[1]));
      var lab = el('div', 'font-size:10px;color:var(--text-3);text-transform:uppercase;letter-spacing:.04em', spec[0]);
      card.appendChild(val);
      card.appendChild(lab);
      summary.appendChild(card);
    });
    host.appendChild(summary);

    if (data.capped) {
      host.appendChild(el('div',
        'padding:8px 12px;margin-bottom:12px;border-radius:8px;background:var(--bg-3);' +
        'border:1px solid var(--border);font-size:11.5px;color:var(--text-2)',
        '⚠ The buffer is full — the oldest entries were evicted. Clear it and reproduce to get a complete picture.'));
    }

    if (!rows.length) {
      host.appendChild(el('div',
        'padding:16px;border-radius:10px;background:var(--bg-2);border:1px solid var(--border);' +
        'font-size:13px;color:var(--text-2);line-height:1.6',
        'No violations recorded. Either the stricter policy is safe to enforce, '
        + 'or the app has not been exercised since the buffer was last cleared — '
        + 'browse a few panes and refresh before drawing a conclusion.'));
      return;
    }

    // ── Table ──
    var table = el('table', 'width:100%;border-collapse:collapse;font-size:12px');
    var head = el('tr');
    ['Count', 'Directive', 'Source', 'Line'].forEach(function (h) {
      var th = el('th',
        'text-align:left;padding:7px 10px;font-size:10px;font-weight:700;color:var(--text-3);' +
        'text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid var(--border)', h);
      head.appendChild(th);
    });
    table.appendChild(head);

    rows.slice().sort(function (a, b) { return (b.count || 0) - (a.count || 0); })
      .forEach(function (v) {
        var tr = el('tr');
        var third = isThirdParty(v.source_file);
        tr.appendChild(el('td',
          'padding:6px 10px;border-bottom:1px solid var(--border);font-variant-numeric:tabular-nums',
          String(v.count || 1)));
        tr.appendChild(el('td',
          'padding:6px 10px;border-bottom:1px solid var(--border);color:var(--accent-text)',
          v.directive || '—'));
        var src = el('td',
          'padding:6px 10px;border-bottom:1px solid var(--border);color:' +
          (third ? 'var(--text-3)' : 'var(--text-1)'),
          shortSource(v.source_file));
        src.title = v.source_file || '';
        tr.appendChild(src);
        tr.appendChild(el('td',
          'padding:6px 10px;border-bottom:1px solid var(--border);color:var(--text-3)',
          v.line_number ? String(v.line_number) : '—'));
        table.appendChild(tr);
      });

    var wrap = el('div', 'max-height:340px;overflow:auto;border:1px solid var(--border);border-radius:10px');
    wrap.appendChild(table);
    host.appendChild(wrap);

    if (theirs.length) {
      host.appendChild(el('div',
        'margin-top:10px;font-size:11.5px;color:var(--text-3);line-height:1.6',
        '⧉ marks a third-party origin. Those come from vendored libraries '
        + 'injecting their own styles and cannot be fixed in this codebase — '
        + 'they would need a hash allowance or a local build.'));
    }
  };

  window.clearCspReports = async function () {
    try {
      await fetch(ENDPOINT, { method: 'DELETE' });
    } catch (_) { /* reported by the network layer */ }
    window.renderCspMonitor();
  };
})();
