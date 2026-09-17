// r50 regression: the notification bell reads the REAL notification store.
//
// The bell (29-notifications.js) used to read /api/notifications/* — an
// in-memory list seeded with fake demo entries ("Welcome to Agentic OS",
// "Quick Setup Tip", "New: Kanban Board") in notifications.py. Meanwhile the
// real store — control_tower's notifications table, written by run events
// (complete / fail / kill / budget stop) and webhook completions, announced
// live by r49's toast handler — had NO reader: the bell showed fabricated
// data next to real events that were never listed.
//
// Fix: the bell now targets the control endpoints (GET list, PATCH read,
// POST read-all — all previously unused by the frontend), maps run rows to
// the Control Tower on click, and the dead SAMPLE_NOTIFICATIONS block is
// gone. Verified live: seeded rows render with icons/unread styling, the
// badge counts unread, row click marks read + navigates + closes, mark-all
// clears the table, and no demo endpoint is ever called.

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = () =>
  readFileSync(join(root, 'js', '29-notifications.js'), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\/\/[^\n]*/g, '');

describe('r50 bell reads the real notification store (29-notifications.js)', () => {
  it('lists from /api/control/notifications', () => {
    expect(src()).toContain("fetch('/api/control/notifications?limit=30')");
  });

  it('trusts the real payload shape (http ok + notifications array), not a demo ok flag', () => {
    expect(src()).toContain('r.ok && Array.isArray(d.notifications)');
  });

  it('marks one read via the control PATCH endpoint', () => {
    expect(src()).toContain('`/api/control/notifications/${encodeURIComponent(id)}/read`');
    expect(src()).toContain("{ method: 'PATCH' }");
  });

  it('marks all read via the control read-all endpoint', () => {
    expect(src()).toContain("fetch('/api/control/notifications/read-all', { method: 'POST' })");
  });

  it('run notifications navigate to the Control Tower on click', () => {
    expect(src()).toContain("n.link || (n.run_id ? 'control' : '')");
  });

  it('the demo store is gone: no SAMPLE_NOTIFICATIONS, no /api/notifications endpoints', () => {
    const s = src();
    expect(s).not.toContain('SAMPLE_NOTIFICATIONS');
    expect(s).not.toContain('/api/notifications/list');
    expect(s).not.toContain('/api/notifications/mark-read');
    expect(s).not.toContain('/api/notifications/mark-all-read');
  });
});
