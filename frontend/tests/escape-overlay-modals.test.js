// Regression guard (#053): the bespoke overlay-modals (gm-create-modal,
// dag-launch-modal, a2a-delegate/register-modal) must be dismissable with
// Escape. They are built ad hoc with a `className='…-modal-overlay'` scrim and
// torn down with `.remove()`, so the global master Escape handler has to (a)
// discover them and (b) remove them — not just hide them with display:none,
// which would leave a stale scrim intercepting clicks.
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const SRC = fs.readFileSync(path.join(__dirname, '..', 'js', '01-app-core.js'), 'utf8');

describe('master Escape handler dismisses bespoke overlay-modals', () => {
  it('lists each bespoke overlay modal by id in the discoverable set', () => {
    for (const id of ['gm-create-modal', 'dag-launch-modal', 'a2a-delegate-modal', 'a2a-register-modal']) {
      expect(SRC.includes(`document.getElementById('${id}')`), `${id} missing from discovery`).toBe(true);
    }
  });

  it('removes (not merely hides) each overlay-modal on Escape', () => {
    // #064: the bespoke-removal branch is now generic — it matches ANY
    // `*-modal-overlay` scrim (id or className) rather than a hardcoded id list,
    // so a newly-added bespoke dialog (e.g. kanban) is torn down too.
    const listIdx = SRC.indexOf("-modal-overlay/.test(m.id");
    expect(listIdx).toBeGreaterThan(0);
    // The overlay branch runs remove(); it must NOT reuse the generic
    // display:none fallback. The branch ends at the next `} else {`.
    const branchEnd = SRC.indexOf('} else {', listIdx);
    const branch = SRC.slice(listIdx, branchEnd);
    expect(branch).toMatch(/m\.className/);
    expect(branch).toMatch(/m\.remove\(\)/);
    expect(branch).not.toMatch(/m\.style\.display/);
  });
});

describe('drawer detail scrims join the Escape nets by class (r41 sweep)', () => {
  // The plugin-hub and connect-hub detail overlays render INSIDE
  // #hub-drawer/#connect-drawer via innerHTML, so the body-level Escape net in
  // 00-handlers.js (body > div:not([id])) can never see them — they are not
  // body children and they carry ids. Their only route out is the master
  // handler, whose collectOpenModals matches the /-modal-overlay/ class. Until
  // this sweep they had id + inline styles only: a hard keyboard trap.
  // (The five bespoke modals in 04-workflow-specs/24-onboarding are covered by
  // escape-coverage-bespoke-modals.test.js.)
  const j = (f) => fs.readFileSync(path.join(__dirname, '..', 'js', f), 'utf8');

  it('hub-overlay carries the marker class + dialog role inside the drawer markup', () => {
    const src = j('34-plugin-hub.js');
    const tag = src.match(/id="hub-overlay"[^>]*/);
    expect(tag, 'hub-overlay div exists').toBeTruthy();
    expect(tag[0]).toMatch(/class="hub-modal-overlay"/);
    expect(tag[0]).toMatch(/role="dialog"/);
    expect(tag[0]).toMatch(/aria-modal="true"/);
  });

  it('connect-overlay carries the marker class + dialog role inside the drawer markup', () => {
    const src = j('35-connect-hub.js');
    const tag = src.match(/id="connect-overlay"[^>]*/);
    expect(tag, 'connect-overlay div exists').toBeTruthy();
    expect(tag[0]).toMatch(/class="connect-modal-overlay"/);
    expect(tag[0]).toMatch(/role="dialog"/);
    expect(tag[0]).toMatch(/aria-modal="true"/);
  });
});
