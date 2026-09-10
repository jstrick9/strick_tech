// Regression guard: 160+ error call sites still toast raw strings —
// "Create failed: server error 500", "runs.filter is not a function".
// Rewriting them all was out of scope, so the upgrade happens at the
// display boundary: toast() passes every 'err' message through
// humanizeRawError(), which turns protocol-speak into a sentence while
// leaving already-human and legitimate custom messages untouched.
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const SRC = fs.readFileSync(path.join(__dirname, '..', 'js', '00-error-copy.js'), 'utf8');
const TOAST_SRC = fs.readFileSync(path.join(__dirname, '..', 'js', '01-app-core.js'), 'utf8');

// The module is an IIFE that attaches to window; execute it in this
// jsdom context and use the real function rather than pattern-matching.
eval(SRC);

describe('humanizeRawError at the toast boundary', () => {
  it('upgrades status-bearing raw messages, keeping the caller’s own lead', () => {
    expect(window.humanizeRawError('Create failed: server error 500'))
      .toBe('Create failed. The server ran into a problem.');
    expect(window.humanizeRawError('Load failed — HTTP 502'))
      .toBe('Load failed. The server is not reachable right now.');
    expect(window.humanizeRawError('Failed to delete key: server error 404'))
      .toBe('Failed to delete key. That is no longer here — it may have been deleted or renamed.');
  });

  it('explains stack frames instead of showing them as the headline', () => {
    const out = window.humanizeRawError('runs.filter is not a function');
    expect(out).toMatch(/^Something went wrong\. The response from the server/);
    expect(out).toContain('(runs.filter is not a function)');
  });

  it('leaves already-human and custom messages untouched', () => {
    const human = "Couldn't load your templates. The server ran into a problem.";
    const custom = 'Invalid API key format';
    expect(window.humanizeRawError(human)).toBe(human);
    expect(window.humanizeRawError(custom)).toBe(custom);
  });

  it('toast() routes err messages through the humanizer', () => {
    expect(TOAST_SRC).toMatch(/type === 'err' && typeof window\.humanizeRawError === 'function'/);
  });
});
