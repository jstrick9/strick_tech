// Escape-coverage class sweep (#175 follow-up): the template preview modal
// fell through every Escape net (id → excluded from the no-id overlay
// handler; no -modal-overlay class → excluded from the master handler).
// A sweep of all 44 ad-hoc fixed-position overlay sites found five more
// id-bearing, classless, roleless blocking modals — mouse-only dismissal:
//
//   upgrade-modal, tier-plans-modal, license-activation-modal,
//   set-user-modal   (04-workflow-specs.js — data-close/remove lifecycle)
//   quick-setup-modal (24-onboarding.js — data-close/remove lifecycle)
//
// (Sites with className='modal-back' are covered by the master handler's
// .modal-back[style*=flex] matcher; the hierarchy modals, novice API guide
// and kb-shortcuts/tour overlays were verified covered or self-handled.)
//
// Each of the five now carries a *-modal-overlay class (the master
// handler's REMOVE branch — matching their data-close semantics — plus the
// Tab focus-trap) and role=dialog/aria-modal for semantics.
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const read = (p) => fs.readFileSync(path.join(__dirname, '..', p), 'utf8');
const WF = read('js/04-workflow-specs.js');
const QS = read('js/24-onboarding.js');

const CASES = [
  ['upgrade-modal', WF, 'wf-modal-overlay'],
  ['tier-plans-modal', WF, 'wf-modal-overlay'],
  ['license-activation-modal', WF, 'wf-modal-overlay'],
  ['set-user-modal', WF, 'wf-modal-overlay'],
  ['quick-setup-modal', QS, 'qs-modal-overlay'],
];

describe('bespoke modals join the Escape/focus-trap conventions', () => {
  for (const [id, src, cls] of CASES) {
    it(`${id} carries the -modal-overlay class and dialog role`, () => {
      const at = src.indexOf(`modal.id = '${id}'`);
      expect(at).toBeGreaterThan(-1);
      // the class/role additions sit directly after the id assignment
      const block = src.slice(at, at + 800);
      expect(block).toContain(`modal.className = '${cls}'`);
      expect(block).toContain("setAttribute('role', 'dialog')");
      expect(block).toContain("setAttribute('aria-modal', 'true')");
    });
  }

  it('the new class names have no CSS (purely functional markers)', () => {
    // an accidental style rule would change these modals' appearance
    for (const f of fs.readdirSync(path.join(__dirname, '..')).filter(x => x.endsWith('.css'))) {
      const css = read(f);
      expect(css, `${f} styles the marker class`).not.toMatch(/\.wf-modal-overlay|\.qs-modal-overlay/);
    }
  });
});
