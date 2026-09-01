// Frontend correctness: wfAddNode must NOT snap a legitimate x=0 (or y=0)
// drop to the 200 default. The old `x: x || 200, y: y || 200` treated 0 as a
// missing coordinate, so a node dropped on the canvas world-origin (e.g. after
// panning) jumped 200px right/down. Only a non-finite coordinate should fall
// back to the default.
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import fs from 'fs';
import path from 'path';

function escHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

function evalWorkflowModule() {
  const source = fs.readFileSync(path.join(__dirname, '..', 'js', '03-features-a.js'), 'utf8');
  // Expose test hooks from within the module's closure so we can drive wfAddNode
  // and read the private _wfData.
  const code = source + `
    window.__setWfData = d => { _wfData = d; };
    window.__setWfNodeTypes = t => { _wfNodeTypes = t; };
    window.__wfAddNode = (type, x, y) => { wfAddNode(type, x, y); return _wfData.nodes[_wfData.nodes.length - 1]; };
  `;
  new Function('window', 'document', 'navigator', 'localStorage', 'console', 'fetch', 'toast', 'gmDanger', 'escHtml', code)(
    globalThis.window, globalThis.document, globalThis.navigator,
    globalThis.localStorage, globalThis.console, globalThis.fetch, globalThis.toast, globalThis.gmDanger, escHtml
  );
}

function makeEl(id) { return Object.assign(document.createElement('div'), { id }); }

function host() {
  const ids = [
    'wf-canvas', 'wf-edges-g', 'wf-svg', 'wf-canvas-wrap', 'wf-empty-state',
    'wf-properties', 'wf-props-content', 'wf-props-title', 'wf-minimap-canvas',
    'wf-undo-btn', 'wf-redo-btn', 'wf-zoom-label', 'wf-validation-badge',
    'wf-val-icon', 'wf-val-text',
  ];
  const map = {};
  const container = document.createElement('div');
  container.id = 'wf-harness';
  for (const id of ids) {
    const el = makeEl(id);
    map[id] = el;
    container.appendChild(el);
  }
  // minimap needs a 2d context
  map['wf-minimap-canvas'].getContext = () => ({
    clearRect: () => {}, fillRect: () => {}, beginPath: () => {}, moveTo: () => {},
    lineTo: () => {}, stroke: () => {}, fill: () => {}, roundRect: () => {},
    strokeRect: () => {},
  });
  map['wf-canvas-wrap'].getBoundingClientRect = () => ({ left: 0, top: 0, width: 800, height: 600 });
  map['wf-canvas'].getBoundingClientRect = () => ({ left: 0, top: 0, width: 800, height: 600 });
  document.body.appendChild(container);
  const original = document.getElementById;
  document.getElementById = (id) => map[id] || original(id);
  return { map, original };
}

describe('Workflow node coordinate handling', () => {
  let restore;

  beforeEach(() => {
    document.body.innerHTML = '';
    const h = host();
    restore = () => { document.getElementById = h.original; document.body.innerHTML = ''; };
    evalWorkflowModule();
    window.__setWfNodeTypes([]);
    window.__setWfData({ id: 'wf1', name: 'wf', nodes: [], edges: [] });
  });
  afterEach(() => restore && restore());

  it('keeps a node dropped at x=0, y=0', () => {
    const n = window.__wfAddNode('trigger', 0, 0);
    expect(n.x).toBe(0);
    expect(n.y).toBe(0);
  });

  it('keeps a node dropped on the left/top edge (x==0, y>0)', () => {
    const n = window.__wfAddNode('trigger', 0, 150);
    expect(n.x).toBe(0);
    expect(n.y).toBe(150);
  });

  it('defaults only when the coordinate is non-finite', () => {
    const n = window.__wfAddNode('agent', undefined, undefined);
    expect(n.x).toBe(200);
    expect(n.y).toBe(200);
  });

  it('rounds fractional drop positions to integers', () => {
    const n = window.__wfAddNode('agent', 12.6, 33.4);
    expect(n.x).toBe(13);
    expect(n.y).toBe(33);
  });
});
