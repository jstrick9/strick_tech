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
    const listIdx = SRC.indexOf("m.id === 'gm-create-modal'");
    expect(listIdx).toBeGreaterThan(0);
    // The overlay branch runs remove(); it must NOT reuse the generic
    // display:none fallback. The branch ends at the next `} else {`.
    const branchEnd = SRC.indexOf('} else {', listIdx);
    const branch = SRC.slice(listIdx, branchEnd);
    expect(branch).toMatch(/m\.id === 'gm-create-modal' \|\| m\.id === 'dag-launch-modal'/);
    expect(branch).toMatch(/a2a-delegate-modal.*a2a-register-modal/);
    expect(branch).toMatch(/m\.remove\(\)/);
    expect(branch).not.toMatch(/m\.style\.display/);
  });
});
