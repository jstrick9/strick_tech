// Frontend correctness: the Obsidian daily-note button must not look like it
// succeeded when it didn't — and must show the server's reason (#146).
//
// The backend now refuses to regenerate a daily note that already exists
// (HTTP 409) instead of overwriting it — the note's own template invites
// the user to write in the "Notes" section, so regenerate-overwrite silently
// destroyed their day's content. The pane used to toast the refusal as
// "✅ Daily note failed: HTTP 409" (a green check on a failure) and hide the
// reason; it must parse the body and surface the error as an error.
import { describe, it, expect } from 'vitest';

const fs = require('fs');
const path = require('path');
const SRC = fs.readFileSync(path.join(__dirname, '..', 'js', '20-obsidian.js'), 'utf8');

describe('obsidian daily note refusal is surfaced honestly', () => {
  const fn = SRC.match(/async function createDailyNote[\s\S]*?\n\}/)[0];

  it('parses the error body on a non-OK response', () => {
    expect(fn).toContain('if (!r.ok) {');
    expect(fn).toContain('r.json().catch');
  });

  it('shows the server reason, styled as an error', () => {
    expect(fn).toContain(
      "showToast('📅 ' + (j.error || ('Daily note failed: HTTP ' + r.status)), 'err');"
    );
  });

  it('every failure branch of createDailyNote toasts with err', () => {
    expect(fn).toContain("'📅 Daily note failed: '+(j.error||'Unknown'), 'err'");
    expect(fn).toContain("'📅 Daily note error: '+ex?.message, 'err'");
  });
});

describe('obsidian failure toasts are errors, not successes', () => {
  it('no failure toast in the pane keeps the default success style', () => {
    // showToast( ... ); statements, single-line in this file.
    const calls = SRC.match(/showToast\([^;]*\);/g) || [];
    expect(calls.length).toBeGreaterThan(5);
    const bad = calls.filter((c) => /fail|error/i.test(c) && !c.includes("'err'"));
    expect(bad).toEqual([]);
  });
});
