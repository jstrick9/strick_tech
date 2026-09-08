/**
 * #071 — Startup chat auto-focus timer must not steal focus from an open dialog.
 *
 * 14-prompt-library.js schedules `setTimeout(()=>…focus chat-input…, 1200)`.
 * It ran unconditionally (when pane-chat was active), so a user who opened the
 * command palette or another modal within ~1.2s of page load had focus ripped
 * out of the input into the chat box behind the modal — arrow/Enter keys then
 * went to chat, not the palette.
 *
 * Guard: the timer now checks collectOpenModals() and yields when any dialog is
 * open. This is a source-level regression test (the CSP blocks injecting axe).
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const SRC = readFileSync(resolve(__dirname, '../js/14-prompt-library.js'), 'utf8');

describe('#071 the startup chat auto-focus yields to an open dialog', () => {
  it('guards on collectOpenModals() before focusing chat-input', () => {
    const timer = SRC.indexOf('Auto-focus chat on startup');
    expect(timer).toBeGreaterThan(-1);
    // The startup-timer setTimeout must consult collectOpenModals() and bail
    // before it can reach the chat-input focus. Check this by asserting the
    // focus call sits after an explicit openDialog guard inside the same timer.
    const focusIdx = SRC.indexOf("getElementById('chat-input')?.focus()", timer);
    expect(focusIdx).toBeGreaterThan(-1);
    const region = SRC.slice(timer, focusIdx);
    expect(region).toMatch(/collectOpenModals/);      // guard consulted
    expect(region).toMatch(/if\s*\(openDialog\)\s*return/); // bails when a modal is open
  });

  it('focuses chat only when no dialog is open', () => {
    // The timer callback should return early when collectOpenModals() > 0.
    const block = SRC.slice(SRC.indexOf('Auto-focus chat on startup'),
      SRC.indexOf('Auto-focus chat on startup') + 700);
    expect(block).toMatch(/openDialog\s*=\s*.*collectOpenModals\(\).*length\s*>\s*0/);
    expect(block).toMatch(/if\s*\(openDialog\)\s*return/);
  });
});
