// Regression guard: the webhooks pane's quick bar carried a "▶ Test" entry
// with an EMPTY action string. The renderer's guard (`action ? button : ''`)
// silently dropped it, so a button that was designed never existed — and
// the pattern is invisible in review because the entry looks like all its
// siblings. Every QUICK_ACTIONS entry must now carry a real action; the
// webhooks "▶ Test" tests the most recently created webhook and explains
// what to do first when none exist.
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const SRC = fs.readFileSync(path.join(__dirname, '..', 'js', '02-studio.js'), 'utf8');
const HOOKS = fs.readFileSync(path.join(__dirname, '..', 'js', '33-webhooks.js'), 'utf8');

const QUICK_BLOCK = SRC.slice(SRC.indexOf('const QUICK_ACTIONS'), SRC.indexOf('function showQuickActions'));

describe('quick actions: every designed button exists and does something', () => {
  it('no QUICK_ACTIONS entry has an empty action string', () => {
    const entries = QUICK_BLOCK.match(/\[[^\[\]]*\]/g) || [];
    expect(entries.length).toBeGreaterThan(5);
    const empty = entries.filter(e => /,\s*(""|'')\s*\]/.test(e));
    expect(empty, `phantom entries: ${empty.join(', ')}`).toEqual([]);
  });

  it('the webhooks ▶ Test quick action is wired to a handler', () => {
    expect(QUICK_BLOCK).toMatch(/\['▶ Test',"testLatestWebhook\?\.\(\)"\]/);
    expect(HOOKS).toMatch(/async function testLatestWebhook\(\)/);
  });

  it('testLatestWebhook handles the no-webhooks case instead of doing nothing', () => {
    expect(HOOKS).toMatch(/whs\.length === 0/);
    expect(HOOKS).toMatch(/No webhooks to test yet/);
  });
});
