// r49 regression: run-lifecycle notifications.
//
// Found by the unused-endpoint sweep: the Control Tower pane fetched
// /api/control/notifications?limit=5 every 5s and destructured the payload
// as `nd` — which was never read. No pane renders them. Worse, the WebSocket
// path was dead too: _push_notification() (control_tower.py) persists run
// events to the notifications table AND broadcasts {type:'notification', …}
// to every client — but handleWSMessage had no case for that type, so a
// completed or failed run was never announced anywhere. (The bell,
// 29-notifications.js, reads a separate demo-seeded list in notifications.py;
// the only production emitter today is webhook completion.)
//
// Fix: 01-app-core handleWSMessage now toasts type:'notification' messages;
// 31-control-tower no longer polls the notifications endpoint it discarded.

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = (f) =>
  readFileSync(join(root, 'js', f), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\/\/[^\n]*/g, '');

describe('r49 ws notification handler (01-app-core.js)', () => {
  const s = () => src('01-app-core.js');

  it('handleWSMessage listens for type:"notification"', () => {
    expect(s()).toContain("msg.type === 'notification'");
  });

  it('maps notif_type to toast kind: error->err, budget_alert/system->warn, else ok', () => {
    const t = s();
    expect(t).toContain("msg.notif_type === 'error' ? 'err'");
    expect(t).toContain("msg.notif_type === 'budget_alert' || msg.notif_type === 'system'");
  });

  it('toasts title and body', () => {
    expect(s()).toContain("${msg.title}${msg.body ? ' — ' + msg.body : ''}");
  });
});

describe('r49 control tower stops polling notifications it never rendered (31-control-tower.js)', () => {
  const s = () => src('31-control-tower.js');

  it('no longer fetches /api/control/notifications', () => {
    expect(s()).not.toContain('/api/control/notifications');
  });

  it('still polls stats, runs and budget-rules', () => {
    const t = s();
    expect(t).toContain("fetch('/api/control/stats')");
    expect(t).toContain("fetch('/api/control/runs?limit=20')");
    expect(t).toContain("fetch('/api/control/budget-rules')");
  });

  it('the dead `nd` payload is gone and the ok-gate covers only the three live fetches', () => {
    const t = s();
    expect(t).not.toMatch(/\bnd\b/);
    expect(t).toContain('!sr.ok || !rr.ok || !br.ok');
    expect(t).not.toContain('!nr.ok');
  });
});
