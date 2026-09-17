// r53 regression: dead CSS selectors stay out of the LINKED stylesheets.
//
// The five sheets index.html loads carried rules for classes that appear in
// NO app source (index.html, splash, index-simplified, sw.js, all frontend
// and vendor JS) — design-system residue: tag-default/-accent/-success/
// -warning/-danger ("canonical vocabulary" that no markup ever adopted),
// the .empty-state__* BEM that the data-state migration replaced, .dot-*
// status pills, .device-frame/.device-notch, .onboarding-steps, .cmd-chips…
// 39 rules / 49 selectors / ~3.8 KB shipped on every page load and matched
// nothing, ever.
//
// Deliberately NOT removed (verify they stay):
//   * .tag-default/-accent/-success/-warning/-danger — the guarded canonical
//     token vocabulary (badge-tag-reconcile.test.js); flagged as orphans by
//     the corpus scan but a committed guard test owns them
//   * .tight-target / .no-wrap-guard (+ their rationale rules) — guarded
//     adversarial-input defenses (test_126_adversarial_input.py): the touch-
//     target escape hatch and the unbroken-string containment opt-out. Flagged
//     as orphans by the corpus scan; a committed guard test owns them
//   * .wg-* primitives — the guarded design-system API
//     (widget-primitives.test.js owns the full assertion set)
//   * .cs-scope--workspace — data-driven: `cs-scope--${scope}` in
//     14-prompt-library.js, scope values come from the search API
//   * .is-warn — data-driven: `is-${p.kind}` in 12-information-hierarchy.js
//   * #ws-body-galaxy / #ws-body-studio — dynamic ids: 'ws-body-' + host
//
// Removal verified live: computed_style_diff --compare against a pre-change
// baseline reported 0 real differences (25 raw, under the instrument's own
// 518-property same-build noise floor).

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const sheet = (f) =>
  readFileSync(join(root, f), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');

const LINKED = [
  'styles-unified.css',
  'styles-extracted.css',
  'styles-print.css',
  'styles-redesign.css',
  'styles-system.css',
];

// Dead classes REMOVED (styles-extracted.css only — every other flagged
// family turned out to be guarded or data-driven and was kept).
const DEAD_CLASSES = [
  'big-icon', 'btn-icon', 'btn-lg', 'chat-agent-pill', 'cmd-chip', 'cmd-chips',
  'device-frame', 'device-notch', 'dot-active', 'dot-error', 'dot-idle', 'dot-working',
  'empty-state__actions', 'empty-state__body', 'empty-state__icon', 'empty-state__title',
  'file-ext', 'onboarding-actions', 'onboarding-step', 'onboarding-steps',
  'progress-bar__fill', 'stat-card__delta', 'studio-split', 'swarm-card-meta', 'toggle-arrow',
];

describe('r53 dead selectors stay out of the linked stylesheets', () => {
  for (const f of LINKED) {
    it(`${f} defines no dead class selectors`, () => {
      const css = sheet(f);
      for (const name of DEAD_CLASSES) {
        expect(css, `${f} still defines .${name}`).not.toMatch(
          new RegExp('\\.' + name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?![\\w-])')
        );
      }
    });
  }

  it('the dead settings id selector is gone', () => {
    for (const f of LINKED) {
      expect(sheet(f), `${f} still defines #settings-appearance-card`).not.toContain(
        '#settings-appearance-card'
      );
    }
  });
});

describe('r53 live data-driven and guarded selectors are untouched', () => {
  it('the guarded tag-<tint> canonical tokens stay (badge-tag-reconcile.test.js)', () => {
    const css = sheet('styles-system.css');
    for (const t of ['tag-default', 'tag-accent', 'tag-success', 'tag-warning', 'tag-danger']) {
      expect(css).toMatch(new RegExp('\\.' + t + '\\b'));
    }
  });

  it('.cs-scope--workspace stays (rendered via cs-scope--${scope})', () => {
    expect(sheet('styles-redesign.css')).toMatch(/\.cs-scope--workspace/);
  });

  it('.is-warn stays (rendered via is-${kind})', () => {
    expect(sheet('styles-redesign.css')).toMatch(/\.is-warn/);
  });

  it('.tight-target / .no-wrap-guard stay (guarded adversarial-input opt-outs)', () => {
    const css = sheet('styles-redesign.css');
    expect(css).toMatch(/\.no-wrap-guard/);
    expect(css).toMatch(/\.tight-target/);
  });

  it('the dynamic workstation ids keep their rules (#ws-body-<host>)', () => {
    const css = sheet('styles-redesign.css');
    expect(css).toMatch(/#ws-body-galaxy/);
    expect(css).toMatch(/#ws-body-studio/);
  });
});
