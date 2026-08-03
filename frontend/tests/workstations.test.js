/**
 * Workstation consolidation — behavioural tests.
 *
 * The sidebar went from 67 top-level panes to 24 by folding 44 related panes
 * into 11 tabbed workstations. The guarantee these tests protect is that the
 * consolidation is LOSSLESS: every absorbed pane still exists, still renders,
 * and is still reachable by its original id (deep links, command palette,
 * keyboard shortcuts and cross-module nav() calls all use those ids).
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { JSDOM } from 'jsdom';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '../..');
const WS_JS = readFileSync(resolve(ROOT, 'frontend/js/00-workstations.js'), 'utf-8');
const INDEX_HTML = readFileSync(resolve(ROOT, 'frontend/index.html'), 'utf-8');

function loadWorkstations(dom) {
  const w = dom.window;
  // eslint-disable-next-line no-new-func
  new Function('window', 'document', 'console', WS_JS)(w, w.document, console);
  return w;
}

describe('workstation configuration', () => {
  const dom = new JSDOM('<!DOCTYPE html><body></body>');
  const w = loadWorkstations(dom);

  it('defines 11 workstations absorbing 43 panes (67 sidebar entries -> 24)', () => {
    const hosts = Object.keys(w.WORKSTATIONS);
    const absorbed = hosts.flatMap((h) => w.WORKSTATIONS[h]);
    expect(hosts).toHaveLength(11);
    expect(absorbed).toHaveLength(43);
  });

  it('never absorbs the same pane twice', () => {
    const absorbed = Object.values(w.WORKSTATIONS).flat();
    expect(new Set(absorbed).size).toBe(absorbed.length);
  });

  it('never absorbs a pane into itself', () => {
    Object.entries(w.WORKSTATIONS).forEach(([host, children]) => {
      expect(children).not.toContain(host);
    });
  });

  it('builds a complete reverse index', () => {
    const absorbed = Object.values(w.WORKSTATIONS).flat();
    absorbed.forEach((pane) => {
      expect(w.PANE_TO_WORKSTATION[pane]).toBeTruthy();
      expect(w.WORKSTATIONS[w.PANE_TO_WORKSTATION[pane]]).toContain(pane);
    });
  });

  it('gives every tab a human-readable label', () => {
    const all = Object.keys(w.WORKSTATIONS).concat(Object.values(w.WORKSTATIONS).flat());
    all.forEach((pane) => expect(w.WORKSTATION_LABELS[pane], `missing label for ${pane}`).toBeTruthy());
  });
});

describe('sidebar reflects the consolidation', () => {
  it('shows exactly 24 top-level nav items', () => {
    const sidebar = INDEX_HTML.slice(INDEX_HTML.indexOf('id="sidebar"'), INDEX_HTML.indexOf('id="statusbar"'));
    const navs = [...sidebar.matchAll(/data-nav="([a-z0-9-]+)"/g)].map((m) => m[1]);
    expect(new Set(navs).size).toBe(24);
  });

  it('keeps a pane container for every absorbed pane (nothing deleted)', () => {
    const dom = new JSDOM('<!DOCTYPE html><body></body>');
    const w = loadWorkstations(dom);
    Object.values(w.WORKSTATIONS).flat().forEach((pane) => {
      expect(INDEX_HTML, `#pane-${pane} must still exist`).toContain(`id="pane-${pane}"`);
    });
  });

  it('removes absorbed panes from the sidebar itself', () => {
    const dom = new JSDOM('<!DOCTYPE html><body></body>');
    const w = loadWorkstations(dom);
    const sidebar = INDEX_HTML.slice(INDEX_HTML.indexOf('id="sidebar"'), INDEX_HTML.indexOf('id="statusbar"'));
    Object.values(w.WORKSTATIONS).flat().forEach((pane) => {
      expect(sidebar).not.toContain(`data-nav="${pane}"`);
    });
  });
});

describe('workstation tab behaviour', () => {
  let w;

  beforeEach(() => {
    const dom = new JSDOM(`<!DOCTYPE html><body>
      <div id="content">
        <div class="pane" id="pane-observability"><p id="host-content">host body</p></div>
        <div class="pane" id="pane-finops">finops body</div>
        <div class="pane" id="pane-health">health body</div>
      </div></body>`);
    w = loadWorkstations(dom);
    w.WORKSTATIONS = { observability: ['finops', 'health'] };
    w.PANE_TO_WORKSTATION = { finops: 'observability', health: 'observability' };
    w.MASTER_PANE_REGISTRY = {};
  });

  it('moves absorbed panes inside the host and builds a tab per pane', () => {
    w.initWorkstation('observability');
    const host = w.document.getElementById('pane-observability');
    expect(host.querySelectorAll('.ws-tab')).toHaveLength(3); // host + 2
    expect(host.querySelector('#pane-finops')).not.toBeNull();
    expect(host.querySelector('#pane-health')).not.toBeNull();
  });

  it('preserves the host pane\'s original content as its own tab', () => {
    w.initWorkstation('observability');
    expect(w.document.getElementById('host-content')).not.toBeNull();
    expect(w.document.getElementById('ws-body-observability').textContent).toContain('host body');
  });

  it('is idempotent — re-initialising does not duplicate tabs', () => {
    w.initWorkstation('observability');
    w.initWorkstation('observability');
    expect(w.document.querySelectorAll('.ws-tab')).toHaveLength(3);
  });

  it('shows only the selected tab body', () => {
    w.showWorkstationTab('observability', 'finops');
    expect(w.document.getElementById('pane-finops').style.display).toBe('');
    expect(w.document.getElementById('pane-health').style.display).toBe('none');
    expect(w.document.getElementById('ws-body-observability').style.display).toBe('none');
  });

  it('invokes the absorbed pane\'s registered renderer when its tab opens', () => {
    let called = 0;
    w.MASTER_PANE_REGISTRY = { finops: () => { called += 1; } };
    w.showWorkstationTab('observability', 'finops');
    expect(called).toBe(1);
  });

  it('survives a renderer that throws', () => {
    w.MASTER_PANE_REGISTRY = { finops: () => { throw new Error('boom'); } };
    expect(() => w.showWorkstationTab('observability', 'finops')).not.toThrow();
    expect(w.document.getElementById('pane-finops').style.display).toBe('');
  });

  it('marks exactly one tab active with correct aria state', () => {
    w.showWorkstationTab('observability', 'health');
    const active = [...w.document.querySelectorAll('.ws-tab.active')];
    expect(active).toHaveLength(1);
    expect(active[0].dataset.wsTab).toBe('health');
    expect(active[0].getAttribute('aria-selected')).toBe('true');
  });

  it('remembers the last tab opened per workstation', () => {
    w.showWorkstationTab('observability', 'health');
    expect(w._activeWorkstationTab.observability).toBe('health');
  });
});
