// Regression guard: the help overlay must not lie.
//
// Found in the wild: the backend /api/onboarding/shortcuts feed documented
// "New agent (planned)" and "Run swarm (planned)" for ⌘⇧A / ⌘⇧S while the
// keys were ACTUALLY bound (undocumented) to Arena and Spec Builder; ⌘/ had
// three competing document-level handlers (focus chat input, open the old
// shortcuts modal, navigate to docs) that ALL fired on one keypress; and the
// ⌨️ header button and the ? key opened two different overlays with different
// content. This pins the single-handler, single-overlay, no-lies state.
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const read = (p) => fs.readFileSync(path.join(__dirname, '..', p), 'utf8');
const OVERLAY = read('js/93-shortcuts-overlay.js');
const STUDIO = read('js/02-studio.js');
const SPECS = read('js/04-workflow-specs.js');
const ONBOARDING_PY = read('../backend/routers/onboarding.py');

describe('keyboard shortcut truthfulness', () => {
  it('the help overlay documents the keys Sprint 16 actually binds', () => {
    // js/03-features-b.js binds A→arena, S→specs, H→hooks, G→codeindex
    const features = read('js/03-features-b.js');
    expect(features).toMatch(/e\.key==='A'\) \{ e\.preventDefault\(\); nav\('arena'\)/);
    expect(OVERLAY).toMatch(/'Open Arena'/);
    expect(OVERLAY).toMatch(/'Open Spec Builder'/);
    expect(OVERLAY).toMatch(/'Open Hooks'/);
    expect(OVERLAY).toMatch(/'Open Code Index'/);
  });

  it('no "(planned)" shortcut labels anywhere — document real behaviour or nothing', () => {
    expect(OVERLAY).not.toMatch(/\(planned\)/i);
    expect(ONBOARDING_PY).not.toMatch(/\(planned\)/i);
  });

  it('⌘/ has exactly ONE documented behaviour: focus the chat input (01-app-core)', () => {
    const core = read('js/01-app-core.js');
    expect(core).toMatch(/e\.key === '\/'/); // the focus-chat binding stays
    // the two rogue duplicates are gone (and stay gone)
    expect(STUDIO).not.toMatch(/e\.key === '\/'/);
    expect(SPECS).not.toMatch(/e\.key==='\/'/);
  });

  it('bare "?" is bound only by the shortcuts overlay module', () => {
    expect(OVERLAY).toMatch(/e\.key === '\?'/);
    expect(STUDIO).not.toMatch(/e\.key === '\?'/);
  });

  it('the header ⌨️ button and the palette command open the unified overlay', () => {
    const collab = read('js/32-collaboration.js');
    expect(collab).toMatch(/window\.showKeyboardShortcuts\s*\|\|\s*showShortcuts/);
  });
});
