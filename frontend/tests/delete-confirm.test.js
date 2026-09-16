// UX consistency: destructive actions must use the app's gmDanger modal, not
// the native window.confirm() dialog, which the project's own comments flag as
// unsupported/unreliable in the Tauri WebKit webview. Bulk confirm/prompt were
// replaced with gm equivalents a long time ago (01-app-core.js); this guards
// the remaining stragglers so they can't silently return.
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const jsFiles = fs.readdirSync(path.join(__dirname, '..', 'js')).filter(f => f.endsWith('.js'));

describe('no native confirm()/prompt()/alert() survives (gmDanger standard)', () => {
  it('no JS file calls the native window.confirm / confirm(', () => {
    const offenders = [];
    for (const f of jsFiles) {
      const code = fs.readFileSync(path.join(__dirname, '..', 'js', f), 'utf8')
        .replace(/\/\/[^\n]*/g, '')      // strip line comments
        .replace(/\/\*[\s\S]*?\*\//g, ''); // strip block comments
      // gmDanger/gmConfirm/gmPrompt are the sanctioned replacements; a real
      // native dialog is always `confirm(`/`prompt(`/`alert(` with NO space.
      // Negative lookbehind keeps `gmPrompt(`/`gmAlert(` and shadowed local vars
      // (const prompt = ...) from counting; requiring immediate `(` (no `\s*`)
      // keeps prose like "prompt (use" inside a string literal from counting.
      // (The old deferredPrompt.prompt() exemption went with the removed
      // installPWA orphan — r46 dead-export sweep.)
      const nativeDialog = /(?<![A-Za-z$_])(?:window\.)?(?:confirm|prompt|alert)\(/;
      if (nativeDialog.test(code)) {
        offenders.push(f);
      }
    }
    expect(offenders, 'native dialogs found in: ' + offenders.join(', ')).toEqual([]);
  });
});

describe('inboxDelete uses the gmDanger modal', () => {
  it('inboxDelete body references gmDanger, not window.confirm', () => {
    const src = fs.readFileSync(path.join(__dirname, '..', 'js', '60-inbox.js'), 'utf8')
      .replace(/\/\/[^\n]*/g, '');
    expect(src).toContain('window.gmDanger(');
    expect(src).not.toMatch(/window\.confirm\s*\(/);
  });
});

describe('hClearVoiceHistory confirms before wiping all voice history (r45)', () => {
  // The r45 destructive-action audit found this was the only unconfirmed
  // wipe in the app: the voice panel's "🗑 Clear History" deleted ALL voice
  // history outright, while every sibling (websearch history, browser
  // sessions, note deletes) asks via gmDanger first.
  it('asks via gmDanger before the DELETE and bails when declined', () => {
    const src = fs.readFileSync(path.join(__dirname, '..', 'js', '00-handlers.js'), 'utf8');
    const i = src.indexOf("on('hClearVoiceHistory'");
    expect(i).toBeGreaterThan(0);
    // slice to the end of the handler (the closing "});" of on(...))
    const body = src.slice(i, src.indexOf('});', i));
    const askIdx = body.indexOf('window.gmDanger(');
    const delIdx = body.indexOf("fetch('/api/voice/history'");
    expect(askIdx, 'gmDanger call missing').toBeGreaterThan(-1);
    expect(delIdx, 'DELETE fetch missing').toBeGreaterThan(-1);
    expect(askIdx, 'confirmation must precede the DELETE').toBeLessThan(delIdx);
    // declining must return before the fetch fires
    expect(body).toMatch(/if\s*\(!ok\)\s*return/);
  });
});
