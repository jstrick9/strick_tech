// Frontend correctness: resetting profiler stats used to be a blind fetch —
// no response check, no catch. A network failure or a refused reset was a
// silent no-op: the user confirmed the dialog and nothing happened, with no
// re-render and no feedback. The pane kept its old numbers looking "reset".
import { describe, it, expect } from 'vitest';

const fs = require('fs');
const path = require('path');
const SOURCE = fs.readFileSync(path.join(__dirname, '..', 'js', '03-features-a.js'), 'utf8');

function fn(name) {
  const start = SOURCE.indexOf('async function ' + name + '(');
  if (start === -1) return '';
  const next = SOURCE.indexOf('\nasync function ', start + 10);
  return SOURCE.slice(start, next === -1 ? SOURCE.length : next);
}

describe('profiler reset is honest about failure', () => {
  it('checks the DELETE response before re-rendering', () => {
    const body = fn('resetProfilerStats');
    expect(body).not.toBe('');
    expect(body).toContain("'/api/profiler/stats/reset'");
    expect(body).toContain('!r.ok');
    expect(body).toContain('d.ok === false');
    // the failure branch must bail out BEFORE the re-render
    expect(body.indexOf('Reset failed')).toBeLessThan(body.indexOf('renderProfiler()'));
  });

  it('catches network errors instead of dying silently', () => {
    const body = fn('resetProfilerStats');
    expect(body).toContain('catch');
    expect(body).toContain('network error');
  });
});
