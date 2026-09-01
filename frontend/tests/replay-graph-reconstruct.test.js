// Frontend correctness: ttdReconstructGraph must lay out every reconstructed
// node, not only those seen in node_start events. It previously built the
// layout from `frames.filter(event_type === 'node_start')`, so any node that
// only appeared in node_output/log frames — or a run with no node_start at all
// — never got a coordinate and rendered at (0,0), overlapping the others.
import { describe, it, expect, beforeEach } from 'vitest';

function escHtml(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }

function loadModule() {
  const fs = require('fs');
  const path = require('path');
  const source = fs.readFileSync(path.join(__dirname, '..', 'js', '08-replay-collab.js'), 'utf8');
  const code = source + `\n;window.__ttdReconstruct = (frames) => ttdReconstructGraph(frames);`;
  new Function('window', 'document', 'navigator', 'location', 'localStorage', 'console', 'fetch', 'toast', 'gmDanger', 'escHtml', 'S', 'setTimeout', 'clearInterval', 'setInterval', 'performance', code)(
    globalThis.window, globalThis.document, globalThis.navigator, (globalThis.location ?? {}),
    globalThis.localStorage, globalThis.console, globalThis.fetch, globalThis.toast, globalThis.gmDanger,
    escHtml, { agents: [] }, setTimeout, clearInterval, setInterval, (globalThis.performance ?? { now: () => 0 })
  );
}

describe('ttdReconstructGraph layout', () => {
  beforeEach(() => {
    globalThis.window = globalThis.window || {};
    loadModule();
  });

  it('lays out a run with NO node_start events (output-only)', () => {
    const frames = [
      { node_id: 'a', event_type: 'node_output', output: 'x' },
      { node_id: 'b', event_type: 'node_output', output: 'y' },
      { node_id: 'c', event_type: 'node_output', output: 'z' },
    ];
    const g = window.__ttdReconstruct(frames);
    expect(g.nodes).toHaveLength(3);
    // Every node gets a real, non-zero layout coordinate (previously all 0,0).
    const coords = g.nodes.map(n => [n.x, n.y]);
    for (const [x, y] of coords) { expect(x).toBeGreaterThan(0); expect(y).toBeGreaterThan(0); }
    // Distinct positions (not stacked on the same cell).
    const keys = new Set(coords.map(([x, y]) => `${x},${y}`));
    expect(keys.size).toBe(3);
    // Sequential edges still built from the first-appearance order.
    expect(g.edges).toEqual([
      { id: 'e0', from: 'a', to: 'b' },
      { id: 'e1', from: 'b', to: 'c' },
    ]);
  });

  it('lays out a node seen only via output frames, not just node_start', () => {
    const frames = [
      { node_id: 'a', event_type: 'node_start' },
      { node_id: 'b', event_type: 'node_output', output: 'x' }, // b never start
      { node_id: 'b', event_type: 'node_start' },
    ];
    const g = window.__ttdReconstruct(frames);
    expect(g.nodes).toHaveLength(2);
    for (const n of g.nodes) { expect(n.x).toBeGreaterThan(0); expect(n.y).toBeGreaterThan(0); }
  });

  it('does not divide by zero on an empty frame list', () => {
    const g = window.__ttdReconstruct([]);
    expect(g.nodes).toEqual([]);
    expect(g.edges).toEqual([]);
  });
});
