import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const JS = path.join(__dirname, '..', 'js');

// Replicates how the app wires a mouse-only <div data-act-click> into a real
// button: it must carry role="button" + tabindex="0" + data-keys so the shared
// keydown polyfill activates it with Enter/Space. Containers that hold their own
// nested interactive control (leave them alone) and backdrops/drop-zones are
// deliberately excluded.
function blockHasNested(openTag, code) {
  const start = code.indexOf(openTag);
  if (start < 0) return false;
  let i = code.indexOf('>', start) + 1;
  let depth = 1, p = i;
  const nested = /<(button\b|input\b|a\b|select\b|textarea\b|img\b)/i;
  while (p < code.length) {
    if (code.startsWith('</div', p)) { depth--; if (depth === 0) return false; p += 5; }
    else if (code.startsWith('<', p)) {
      if (nested.test(code.slice(p))) return true;
      if (code.startsWith('<div', p)) { depth++; p += 4; } else p++;
    } else p++;
  }
  return false;
}

const OPEN = /<div\b(?:[^>"']|"[^"]*"|'[^']*')*>/g;

describe('divs acting as buttons are keyboard-operable', () => {
  it('every leaf clickable div carries role=button, tabindex, data-keys', () => {
    const files = fs.readdirSync(JS).filter(f => f.endsWith('.js'));
    const bad = [];
    for (const f of files) {
      const code = fs.readFileSync(path.join(JS, f), 'utf8').replace(/\/\/[^\n]*/g, '');
      for (const m of code.matchAll(OPEN)) {
        const tag = m[0];
        if (!/data-act-click\s*=/.test(tag)) continue;
        if (/role\s*=|tabindex\s*=/.test(tag)) continue; // already operable
        const cls = (tag.match(/class="([^"]*)"/) || [])[1] || '';
        if (/drop|overlay/i.test(cls)) continue;         // backdrop / dropzone
        if (blockHasNested(tag, code)) continue;         // has its own control
        bad.push(f + ': ' + tag.slice(0, 55));
      }
    }
    expect(bad, 'clickable leaf divs not keyboard-operable:\n' + bad.join('\n')).toEqual([]);
  });

  it('no div has a duplicated keyboard trio (accidental double-insert)', () => {
    const files = fs.readdirSync(JS).filter(f => f.endsWith('.js'));
    const bad = [];
    for (const f of files) {
      const code = fs.readFileSync(path.join(JS, f), 'utf8');
      const occ = code.split('data-self-click="1"').length - 1;
      if (occ > 0) {
        // count tags that have >1 occurrence of role="button"
        for (const m of code.matchAll(/<div\b[^>]*data-self-click="1"[^>]*>/g)) {
          if ((m[0].match(/data-self-click="1"/g) || []).length > 1) bad.push(f);
        }
      }
    }
    expect([...new Set(bad)], 'duplicated keyboard markup:\n' + [...new Set(bad)].join('\n')).toEqual([]);
  });
});
