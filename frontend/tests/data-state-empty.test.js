import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const JS = path.join(__dirname, '..', 'js');

// Empty states must route through the shared .data-state component
// (stateFeedback.setEmpty / emptyElement), not hand-rolled inline empty divs.
// Compact inline list notes (padding 6–8px), table-row placeholders, and small
// per-op statuses are intentionally out of scope.

describe('data-area empty states use the shared .data-state empty component', () => {
  it('repo-wide: no body-level inline empty div (centered, padded) survives', () => {
    const files = fs.readdirSync(JS).filter(f => f.endsWith('.js'));
    const bad = [];
    for (const f of files) {
      const code = fs.readFileSync(path.join(JS, f), 'utf8').replace(/\/\/[^\n]*/g, '');
      // A centered padded "No X…" div that is NOT the shared component.
      const re = /(<div\b[^>]*style="[^"]*color:var\(--text-3\)[^"]*(padding:(16|20|40)px)[^"]*"[^>]*>\s*(?:No [^<]{0,60}?(yet|found|available))){1}/g;
      for (const m of code.matchAll(re)) {
        const tag = m[0];
        if (/state-empty|emptyElement|setEmpty\.|stateFeedback\.setEmpty/.test(tag)) continue;
        const before = code.slice(Math.max(0, m.index - 60), m.index);
        if (/emptyElement|setEmpty/.test(before)) continue;
        bad.push(f + ': ' + tag.replace(/\s+/g, ' ').slice(0, 70));
      }
    }
    expect(bad, 'body-level inline empty divs (use stateFeedback.emptyElement):\n' + bad.join('\n')).toEqual([]);
  });

  it('the shared emptyElement() helper is exposed and setEmpty uses it', () => {
    const src = fs.readFileSync(path.join(JS, '00-state-feedback.js'), 'utf8');
    expect(src).toContain('function emptyElement');
    expect(src).toContain('function emptyHtml');
    expect(src).toContain('emptyElement: emptyElement');
    expect(src).toContain('state-empty');
    const setEmptySeg = src.slice(src.indexOf('function setEmpty'), src.indexOf('function setError'));
    expect(setEmptySeg).toContain('emptyHtml(opts)');
  });

  it('selected panes route their empty state through the component (contract)', () => {
    // 56-chat-history empty with a CTA, and 03-features-b tasks empty with CTA.
    const ch = fs.readFileSync(path.join(JS, '56-chat-history.js'), 'utf8');
    expect(ch).toContain('stateFeedback.emptyElement');
    expect(ch).toContain("action: \"nav('chat')\"");
    const fb = fs.readFileSync(path.join(JS, '03-features-b.js'), 'utf8');
    expect(fb).toContain('stateFeedback.emptyElement({ icon: \'🎯\'');
  });

  it('the bespoke pane empties are now the shared component (with CTAs)', () => {
    // Control-tower "No runs yet" got a Run-a-workflow CTA.
    const ct = fs.readFileSync(path.join(JS, '31-control-tower.js'), 'utf8');
    expect(ct).toContain("action:\"nav('workflow')\"");
    expect(ct).toContain("refreshControlTower()");
    // Replay "No Run Selected" and code-insights and workflow-canvas empties.
    const rp = fs.readFileSync(path.join(JS, '08-replay-collab.js'), 'utf8');
    expect(rp).toContain("icon: '⏮️'");
    expect(rp).toContain("action: \"nav('workflow')\"");
    const fb = fs.readFileSync(path.join(JS, '03-features-b.js'), 'utf8');
    expect(fb).toContain("icon: '🕸️'");
    expect(fb).toContain("action: 'ciIndexNow()'");
    const fa = fs.readFileSync(path.join(JS, '03-features-a.js'), 'utf8');
    expect(fa).toContain("icon: '🗺️'");
  });
});
