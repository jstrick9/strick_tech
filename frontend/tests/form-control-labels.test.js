// Accessible names for form controls (WCAG 3.3.2 Labels or Instructions).
// The live DOM audit (element.labels + aria-label/title/placeholder association,
// i.e. exactly what a screen reader resolves) found these controls carrying NO
// accessible name. Each is now wired via aria-label (no visible label present)
// or a <label for=...> association (visible label present). Guarding the ids
// directly is reliable: the static "has a name" heuristic over multi-line
// templates produces false positives, but id -> name association does not.
import { describe, it, expect } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';

const SRC = path.join(__dirname, '..', 'js');

// id -> { file, accessible: 'aria-label'|'title'|'label-for' }
const FIXES = {
  'img-size':              { f: '15-image-generation.js', a: 'aria-label' },
  'figma-framework':       { f: '15-image-generation.js', a: 'aria-label' },
  'st-style':              { f: '15-image-generation.js', a: 'aria-label' },
  'comp-framework':        { f: '19-composer.js',         a: 'aria-label' },
  's2c-framework':         { f: '19-composer.js',         a: 'aria-label' },
  'tmpl-sort':             { f: '21-template-gallery.js',  a: 'aria-label' },
  'eval-agent':            { f: '05-evals-observability.js', a: 'aria-label' },
  'prompt-sort':           { f: '14-prompt-library.js',    a: 'aria-label' },
  'sw-strategy':           { f: '26-swarm.js',             a: 'aria-label' },
  'lb-days-select':        { f: '45-leaderboard.js',       a: 'label-for' },
  'lb-task-select':        { f: '45-leaderboard.js',       a: 'label-for' },
  'ttd-wf-filter':         { f: '08-replay-collab.js',     a: 'aria-label' },
  'fusion-preset-select':  { f: '41-fusion.js',            a: 'aria-label' },
  'subagent-max':          { f: '41-fusion.js',            a: 'label-for' },
  'loop-agent':            { f: '40-loops.js',             a: 'label-for' },
  'loop-interval':         { f: '40-loops.js',             a: 'label-for' },
  'loop-max-runs':         { f: '40-loops.js',             a: 'label-for' },
  'hitl-timeout':          { f: '42-hitl.js',              a: 'aria-label' },
  'hitl-timeout-action':   { f: '42-hitl.js',              a: 'aria-label' },
  'fo-src':                { f: '54-finops.js',            a: 'aria-label' },
  'tg-file':               { f: '34-test-generator.js',     a: 'label-for' },
  'tg-framework':          { f: '34-test-generator.js',     a: 'label-for' },
  'pm-category':           { f: '14-prompt-library.js',     a: 'label-for' },
  'pm-agent':              { f: '14-prompt-library.js',     a: 'label-for' },
  'dash-days':             { f: '36-dashboard.js',          a: 'aria-label' },
  'redteam-agent':         { f: '05-evals-observability.js', a: 'aria-label' },
};

describe('form controls carry accessible names (browser-verified gaps)', () => {
  for (const [id, { f, a }] of Object.entries(FIXES)) {
    it(`${id} (${f})`, () => {
      const code = fs.readFileSync(path.join(SRC, f), 'utf8');
      // find this control's opening tag
      const re = new RegExp('<(select|textarea|input)[^>]*\\bid="' + id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '"[^>]*>', 'i');
      const m = code.match(re);
      expect(m, 'control tag not found').toBeTruthy();
      const tag = m[0];
      if (a === 'aria-label') {
        expect(tag, 'missing aria-label').toMatch(/aria-label\s*=/i);
      } else if (a === 'label-for') {
        expect(code, 'missing <label for="' + id + '">').toMatch(new RegExp('<label\\b[^>]*\\bfor\\s*=\\s*["\']' + id + '["\']', 'i'));
      } else if (a === 'title') {
        expect(tag, 'missing title').toMatch(/\btitle\s*=/i);
      }
    });
  }

  it('no regression on the returned set', () => {
    // assert the curated set is stable so a removed/fixed id doesn't silently rot
    expect(Object.keys(FIXES).length).toBe(26);
  });
});
