// Regression guard (r46): the dead-export sweep. Eight window.* exports were
// removed after a full reference scan (frontend/js, index.html, tests,
// backend, preview) found ZERO callers for each — they were orphans of
// systems that no longer exist:
//
//   deleteChatSession, renameChatSessionModal  — the duplicate session system
//     removed from 01-app-core.js (the real UI is 56-chat-history.js's
//     drawer, with its own confirmed delete/rename); the removal comment at
//     the old site listed these functions' siblings but missed these two.
//   startGuidedChat, lpSaveVerifyKey — referenced #mission-launchpad-deck /
//     #lp-api-key, elements that exist nowhere in the app.
//   installPWA (+ its beforeinstallprompt listener) — showed #pwa-install-btn,
//     which was never rendered.
//   toggleAdvanced — toggled #advanced-toggle, which was never rendered.
//   aosSimpleMode, aosShowSimpleFooter — superseded by aosToggleSimpleMode
//     (the footer links wire data-act-click to it directly).
//
// Deliberately KEPT (zero refs but intentional affordances): the __-prefixed
// debug hooks, loadPaneChunk/paneChunkLoaded, studioOpenFileGlobal,
// showEmptyState, and 01-app-core's shadowed showKeyboardShortcuts (the
// documented intentional override in 93-shortcuts-overlay.js).
//
// If one of these names reappears, wire it to real UI in the same commit —
// an exported handler with no caller is exactly how the duplicate-session
// bug happened: two systems writing to the same backend, one invisible.
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const REMOVED = [
  'deleteChatSession',
  'renameChatSessionModal',
  'startGuidedChat',
  'lpSaveVerifyKey',
  'installPWA',
  'toggleAdvanced',
  'aosSimpleMode',
  'aosShowSimpleFooter',
];

describe('removed orphan exports stay removed (r46 sweep)', () => {
  it('no js file re-declares the eight dead exports', () => {
    const offenders = [];
    for (const f of fs.readdirSync(path.join(__dirname, '..', 'js'))) {
      if (!f.endsWith('.js')) continue;
      const code = fs.readFileSync(path.join(__dirname, '..', 'js', f), 'utf8')
        .replace(/\/\/[^\n]*/g, '')
        .replace(/\/\*[\s\S]*?\*\//g, '');
      for (const name of REMOVED) {
        if (new RegExp('window\\.' + name + '\\s*=').test(code)) {
          offenders.push(`${f}: window.${name}`);
        }
      }
    }
    expect(offenders, 'orphan exports resurrected without wiring: ' + offenders.join(', ')).toEqual([]);
  });

  it('the elements they waited on still do not exist (no half-wired revival)', () => {
    // Where each ghost id may still legitimately appear (a guarded
    // getElementById that never fires is not a revival):
    //   mission-launchpad-deck -> 01-app-core.js only (the shadowed
    //     showKeyboardShortcuts — documented override, left in place)
    //   advanced-toggle / adv-arrow -> 91-mode-switcher.js only (showAdv
    //     still guards them; applyMode drives it, not the removed toggle)
    //   pwa-install-btn, lp-api-key, lp-key-status -> nowhere at all.
    const ALLOWED = {
      'mission-launchpad-deck': ['01-app-core.js'],
      'advanced-toggle': ['91-mode-switcher.js'],
      'adv-arrow': ['91-mode-switcher.js'],
      'pwa-install-btn': [],
      'lp-api-key': [],
      'lp-key-status': [],
    };
    const offenders = [];
    const dir = path.join(__dirname, '..', 'js');
    for (const f of fs.readdirSync(dir)) {
      if (!f.endsWith('.js')) continue;
      const code = fs.readFileSync(path.join(dir, f), 'utf8');
      for (const [id, allowedIn] of Object.entries(ALLOWED)) {
        if (code.includes(id) && !allowedIn.includes(f)) {
          offenders.push(`${f}: #${id}`);
        }
      }
    }
    const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
    for (const id of Object.keys(ALLOWED)) {
      if (html.includes(id)) offenders.push(`index.html: #${id}`);
    }
    expect(offenders, 'ghost element ids wired up again: ' + offenders.join(', ')).toEqual([]);
  });
});
