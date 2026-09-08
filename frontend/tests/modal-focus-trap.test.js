// Regression guard (#061): the bespoke / ad-hoc dialogs (the `*-modal-overlay`
// scrims: gm-create, dag-launch, a2a-delegate, a2a-register, and the
// account-settings dialog) had no Tab focus-trap, so pressing Tab walked focus
// out of the dialog and into the page behind it — a WCAG 2.4.3 focus-order
// failure and a "modal feels broken" bug. #gmodal traps itself (via _gm_show),
// so it is deliberately excluded from the shared trap. On Escape the removed
// modal's recorded opener must be re-focused.
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const SRC = fs.readFileSync(path.join(__dirname, '..', 'js', '01-app-core.js'), 'utf8');

function seg(from, to) {
  const i = SRC.indexOf(from);
  if (i < 0) return '';
  const j = to ? SRC.indexOf(to, i) : SRC.length;
  return SRC.slice(i, j < 0 ? SRC.length : j);
}

describe('master handler focus-traps the non-#gmodal dialogs', () => {
  it('collects open dialogs into a shared helper used by both Escape and the trap', () => {
    expect(SRC).toMatch(/function collectOpenModals\(\)/);
    const collect = seg('function collectOpenModals()', 'function isTrapRoot');
    // The bespoke overlay ids must still be discovered here.
    ['gm-create-modal', 'dag-launch-modal', 'a2a-delegate-modal', 'a2a-register-modal']
      .forEach(id => expect(collect).toContain(`'${id}'`));
  });

  it('dynamically discovers ANY `*-modal-overlay` scrim, not just four hardcoded ids', () => {
    // #064 regression: the kanban edit/delete modal
    // (`class="kanban-modal-overlay" id="kanban-modal-overlay"`) was absent from
    // the hardcoded id list, so Escape left it open (WCAG 2.1.2 keyboard trap)
    // and the Tab trap skipped it (WCAG 2.4.3). The collection must query for
    // all `-modal-overlay` scrims instead of enumerating ids.
    const collect = seg('function collectOpenModals()', 'function isTrapRoot');
    expect(collect).toMatch(/querySelectorAll/);
    expect(collect).toMatch(/-modal-overlay/);
    expect(collect).toMatch(/role.*dialog|role="dialog"/);
    // It must merge the enumerated ids with the discovered ones and de-dupe.
    expect(collect).toMatch(/isConnected/);
    expect(collect).toMatch(/filter\(m => m && m.isConnected/);
  });

  it('Escape handler uses the same shared dynamic collection (no duplicate hardcoded list)', () => {
    const esc = seg("masterEscapeHandler", "if (e.key === 'Tab')");
    expect(esc).toMatch(/const openModals = collectOpenModals\(\)/);
    // No second, hand-maintained id list that could drift out of sync.
    expect(esc).not.toMatch(/getElementById\('gm-create-modal'\)/);
  });

  it('Escape tears down ANY `*-modal-overlay` scrim by remove() + focus restore', () => {
    const esc = seg("masterEscapeHandler", "if (e.key === 'Tab')");
    // The bespoke-removal branch must match the scrim class, not four ids.
    expect(esc).toMatch(/\/-modal-overlay\/\.test\(m\.id/);
    expect(esc).toMatch(/\/-modal-overlay\/\.test\(m\.className/);
    expect(esc).toMatch(/m\.__ovOpener\.focus\(\)/);
    expect(esc).toMatch(/m\.remove\(\)/);
  });

  it('traps Tab only for real dialog containers (modal/dialog), excluding #gmodal', () => {
    const trap = seg("if (e.key === 'Tab')", "if ((e.metaKey||e.ctrlKey) && e.key === 'k')");
    expect(trap).toMatch(/collectOpenModals\(\)\.reverse\(\)\.find\(isTrapRoot\)/);
    expect(trap).toMatch(/modal\.contains\(document\.activeElement\)/);
    // Wraps forward and backward (Shift+Tab).
    expect(trap).toMatch(/shiftKey && document\.activeElement === first/);
    expect(trap).toMatch(/activeElement === last/);
    // The root predicate must rule out #gmodal (it self-traps).
    const root = seg('function isTrapRoot(m)');
    expect(root).toMatch(/m\.id === 'gmodal'/);
    expect(root).toMatch(/-modal-overlay/);
    expect(root).toMatch(/role.*dialog|roleDialog/);
  });

  it('restores the recorded opener when a bespoke overlay is removed on Escape', () => {
    // #064: the bespoke-removal branch is now generic (any `*-modal-overlay`
    // scrim), not a hardcoded id list.
    const esc = seg("if (e.key === 'Escape'", "if (e.key === 'Tab')");
    expect(esc).toMatch(/__ovOpener/);
    expect(esc).toMatch(/m\.__ovOpener\.focus\(\)/);
    expect(esc).toMatch(/m\.remove\(\)/);
  });
});

// Functional proof: load the REAL handler (collectOpenModals + isTrapRoot + the
// master keydown registration) against the real jsdom document, build an actual
// open overlay, and assert Tab wraps first→last→first in the real DOM. This
// tests behaviour, not just source text. (setup.js mocks document.getElementById
// and return-null, so the native method is restored here.)
function loadRealHandler() {
  const start = SRC.indexOf('function collectOpenModals()');
  const end = SRC.indexOf('}, { capture: true });', start) + '}, { capture: true });'.length;
  const code = SRC.slice(start, end);
  // Expose the helper so tests can assert discovery directly; it is local to
  // this Function scope, so it would otherwise not be reachable.
  new Function('document', 'window', 'openPalette', 'toggleSidebar',
    code + '\nwindow.collectOpenModals = collectOpenModals;')(document, window, () => {}, () => {});
}

describe('real handler traps focus in an open bespoke overlay (jsdom)', () => {
  beforeEach(() => {
    document.getElementById = Document.prototype.getElementById;
    document.body.innerHTML = '';
  });
  afterEach(() => { document.body.innerHTML = ''; });
  const tab = (el, opts = {}) => el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true, ...opts }));
  // jsdom has no layout, so offsetParent is always null; stub it to non-null on
  // the dialog's descendants so the handler's visibility filter keeps them.
  const makeVisible = (root) => {
    root.querySelectorAll('button,input,a,[tabindex]').forEach(el => {
      try { Object.defineProperty(el, 'offsetParent', { get: () => document.body }); } catch (e) {}
    });
  };

  it('Tab wraps forward and Shift+Tab wraps backward inside the overlay', () => {
    loadRealHandler();
    const ov = document.createElement('div');
    ov.id = 'gm-create-modal';
    ov.className = 'gm-modal-overlay';
    ov.style.display = 'flex';
    ov.innerHTML = '<button id="b1">1</button><input id="b2"><button id="b3">3</button>';
    document.body.appendChild(ov);
    makeVisible(ov);
    const b1 = ov.querySelector('#b1'), b2 = ov.querySelector('#b2'), b3 = ov.querySelector('#b3');

    b3.focus(); tab(b3);         // at last, Tab → wraps to first
    expect(document.activeElement).toBe(b1);
    b1.focus(); tab(b1, { shiftKey: true }); // Shift+Tab at first → wraps to last
    expect(document.activeElement).toBe(b3);
  });

  it('pulls focus back in if it wandered onto the page behind the dialog', () => {
    loadRealHandler();
    const ov = document.createElement('div');
    ov.id = 'a2a-delegate-modal';
    ov.className = 'a2a-modal-overlay';
    ov.style.display = 'flex';
    ov.innerHTML = '<button>Ok</button><button>Cancel</button>';
    document.body.appendChild(ov);
    makeVisible(ov);
    const behind = document.createElement('button');
    document.body.appendChild(behind);
    behind.focus(); // focus is OUTSIDE the dialog
    tab(behind);
    expect(document.activeElement).toBe(ov.querySelector('button')); // pulled into the modal
  });

  it('#064: a kanban editorial overlay (id not in the hardcoded list) is discovered and trapped', () => {
    loadRealHandler();
    const ov = document.createElement('div');
    ov.id = 'kanban-modal-overlay';            // absent from the enumerated ids
    ov.className = 'kanban-modal-overlay';     // but matches the `*-modal-overlay` discovery
    ov.style.display = 'flex';
    ov.innerHTML = '<button id="kb1">Save</button><input id="kb2"><button id="kb3">Cancel</button>';
    document.body.appendChild(ov);
    makeVisible(ov);
    const kb1 = ov.querySelector('#kb1'), kb2 = ov.querySelector('#kb2'), kb3 = ov.querySelector('#kb3');
    // It is picked up by collectOpenModals() through the dynamic query.
    const found = collectOpenModals().some(el => el.id === 'kanban-modal-overlay');
    expect(found).toBe(true);
    // And the trap wraps focus within it.
    kb3.focus(); tab(kb3);
    expect(document.activeElement).toBe(kb1);
    kb1.focus(); tab(kb1, { shiftKey: true });
    expect(document.activeElement).toBe(kb3);
  });

  it('does not trap #gmodal (it self-traps; the shared trap must not steal it)', () => {
    loadRealHandler();
    const g = document.createElement('div');
    g.id = 'gmodal';
    g.style.display = 'flex';
    g.innerHTML = '<button id="g1">1</button>';
    document.body.appendChild(g);
    const g1 = g.querySelector('#g1');
    const behind = document.createElement('button');
    document.body.appendChild(behind);
    g1.focus(); behind.focus(); // focus behind, but this is #gmodal → exempt
    tab(behind);
    expect(document.activeElement).toBe(behind); // shared handler did NOT yank it
  });
});

describe('the trap targets are real overlays that carry both id and scrim class', () => {
  const sup = fs.readFileSync(path.join(__dirname, '..', 'js', '48-supervisor.js'), 'utf8');
  const goals = fs.readFileSync(path.join(__dirname, '..', 'js', '49-goals.js'), 'utf8');
  const a2a = fs.readFileSync(path.join(__dirname, '..', 'js', '52-a2a.js'), 'utf8');

  it('each bespoke overlay sets id AND a -modal-overlay class on the same element', () => {
    expect(sup).toMatch(/overlay\.id = 'dag-launch-modal'[\s\S]*overlay\.className = 'dag-modal-overlay'/);
    expect(goals).toMatch(/overlay\.id = 'gm-create-modal'[\s\S]*overlay\.className = 'gm-modal-overlay'/);
    expect(a2a.match(/overlay\.className = 'a2a-modal-overlay'/g).length).toBeGreaterThanOrEqual(2);
  });

  it('account-settings-modal declares role=dialog so isTrapRoot treats it as a container', () => {
    const as = fs.readFileSync(path.join(__dirname, '..', 'js', '57-account-settings.js'), 'utf8');
    expect(as).toMatch(/setAttribute\('role', 'dialog'\)/);
  });
});
