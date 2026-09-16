// Regression guard (r43): the inbox pane's honesty gaps from the pane
// journey —
//   A. /api/inbox/share used to redirect to /?pane=inbox&captured=ok, a
//      query param nothing in the app reads: the share landed on the
//      default pane and the "✓ Captured from share." confirmation rendered
//      nowhere. Fixed on the backend by redirecting to /?captured=ok#/inbox
//      (the deep-link router understands #/pane hashes; backend behaviour
//      asserted in test_171_capture_inbox.py). Guarded here: the pane's
//      captured-flag reader must stay QUERY-STRING based, or that contract
//      breaks again.
//   B. a confirmed delete that failed (HTTP 5xx) was swallowed by an empty
//      catch — the item just stayed, with no message anywhere.
//   C. an empty Capture click did nothing while the previous "✓ Captured."
//      note still showed — silence next to a stale success.
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const SRC = fs.readFileSync(path.join(__dirname, '..', 'js', '60-inbox.js'), 'utf8');

describe('inbox pane honesty (r43 journey)', () => {
  it('reads the share-redirect captured flag from the query string', () => {
    // The backend redirects to /?captured=ok#/inbox: the flag is in
    // location.search, NOT location.hash. This reader must not "migrate"
    // to the hash — the fragment belongs to the pane router.
    expect(SRC).toMatch(/URLSearchParams\(window\.location\.search\)\.get\('captured'\)/);
    // And it must render the phone-side confirmation for all three states.
    expect(SRC).toMatch(/Captured from share/);
    expect(SRC).toMatch(/That share had nothing in it/);
    expect(SRC).toMatch(/Capture failed/);
  });

  it('a failed delete surfaces an error instead of an empty catch', () => {
    const fn = SRC.indexOf('async function inboxDelete');
    expect(fn).toBeGreaterThan(0);
    const body = SRC.slice(fn, SRC.indexOf('\n  }', fn));
    const catchIdx = body.indexOf('catch (e)');
    expect(catchIdx).toBeGreaterThan(0);
    const catchBody = body.slice(catchIdx);
    expect(catchBody).toMatch(/showToast\('Could not delete/);
    expect(catchBody).not.toMatch(/\/\* the list reload will show the truth \*\//);
  });

  it('an empty Capture click explains itself rather than staying silent', () => {
    const fn = SRC.indexOf('async function inboxCapture');
    expect(fn).toBeGreaterThan(0);
    const body = SRC.slice(fn, SRC.indexOf('\n  }', fn));
    const guardIdx = body.indexOf('!el.value.trim()');
    expect(guardIdx).toBeGreaterThan(0);
    const guard = body.slice(guardIdx, body.indexOf('return;', guardIdx));
    expect(guard).toMatch(/note\.textContent\s*=/);
    expect(guard).toMatch(/Nothing to capture/);
  });
});
