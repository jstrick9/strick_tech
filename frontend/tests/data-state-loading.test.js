import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const JS = path.join(__dirname, '..', 'js');

// Every pane's loading state must use the shared .data-state component rendered
// by stateFeedback.loadingElement() — one DOM shape + one accessible role — not
// a hand-rolled inline-styled "Loading…" div. This guard fails on any raw
// loading placeholder that isn't the component.

// Intentional exceptions that are NOT pane-body placeholders:
//  .kanban-loading  — a dedicated designed loading component with its own CSS.
const ALLOWED_CLASS = /kanban-loading/;

describe('loading states route through the shared .data-state component', () => {
  it('repo-wide: no bare <div ...>Loading…</div> placeholder survives', () => {
    const files = fs.readdirSync(JS).filter(f => f.endsWith('.js'));
    const bad = [];
    for (const f of files) {
      const code = fs.readFileSync(path.join(JS, f), 'utf8').replace(/\/\/[^\n]*/g, '');
      // A <div> whose direct text content is "Loading…" (or "Loading <x>…")
      // and which is not part of the shared .data-state component.
      const re = /<div\b([^>]*)>(\s*(?:Loading[^<]*)?Loading)/g;
      for (const m of code.matchAll(re)) {
        const tag = m[0];
        if (/data-state|state-loading|loadingElement/.test(tag)) continue;
        if (ALLOWED_CLASS.test(tag)) continue;
        // Only flag when the placeholder div itself (not a nested component) has the text.
        if (m[1].includes('class=') && !/data-state|state-loading/.test(m[1])) {
          // It's a styled div carrying loading text with a class that isn't data-state.
          if (!/kanban-loading/.test(m[1])) bad.push(f + ': ' + tag.replace(/\s+/g, ' ').slice(0, 75));
        } else if (!/loadingElement/.test(code.slice(m.index - 40, m.index))) {
          bad.push(f + ': ' + tag.replace(/\s+/g, ' ').slice(0, 75));
        }
      }
    }
    expect(bad, 'raw inline loading placeholders (should use stateFeedback.loadingElement):\n' + bad.join('\n')).toEqual([]);
  });

  it('the shared loadingElement() helper exists and is exposed', () => {
    const src = fs.readFileSync(path.join(JS, '00-state-feedback.js'), 'utf8');
    expect(src).toContain('function loadingElement');
    expect(src).toContain('loadingElement: loadingElement');
    expect(src).toContain('data-state-spinner');
    expect(src).toContain('state-loading');
  });

  it('showInlineLoading uses the shared component', () => {
    const src = fs.readFileSync(path.join(JS, '01-app-core.js'), 'utf8');
    const idx = src.indexOf('function showInlineLoading');
    expect(idx).toBeGreaterThan(-1);
    const seg = src.slice(idx, idx + 200);
    expect(seg).toContain('stateFeedback.loadingElement');
  });
});
