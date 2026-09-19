// r57 regression: window.showToast must have exactly one owner.
//
// Found live while deep-diving the ops cluster: Obsidian quick-note saves
// called showToast('📝 Note saved…') — the call ran and returned — but no
// toast appeared. Instrumentation showed why: 01-app-core.js sets
// window.showToast = toast (container-based, stacks, humanizes errors) as an
// alias for its 481+ call sites, but 08-replay-collab.js declared a
// top-level `function showToast` — a classic-script global binding that
// clobbered the alias the moment that chunk executed. Which implementation
// a user got depended on script load order (raw tags vs injected bundle),
// so the same save sometimes toasted and sometimes silently didn't.
//
// Fix: 08's duplicate was deleted; its 11 call sites now use the shared
// container toast through the global alias. This test pins the invariant:
// 01-app-core.js is the only file that may define or assign showToast.

const fs = require('fs');
const path = require('path');
const jsDir = path.join(__dirname, '..', 'js');
const files = fs.readdirSync(jsDir).filter((f) => f.endsWith('.js')).sort();

describe('showToast has a single owner (r57)', () => {
  test('01-app-core.js still exports the global alias', () => {
    const src = fs.readFileSync(path.join(jsDir, '01-app-core.js'), 'utf8');
    expect(src).toMatch(/window\.showToast\s*=\s*toast/);
  });

  test('no other file declares or assigns showToast', () => {
    const offenders = [];
    for (const f of files) {
      if (f === '01-app-core.js') continue;
      const src = fs.readFileSync(path.join(jsDir, f), 'utf8');
      // strip line comments so commented-out mentions don't count
      const code = src.replace(/^[ \t]*\/\/.*$/gm, '');
      if (/function\s+showToast\s*\(/.test(code)) offenders.push(`${f}: function declaration`);
      if (/window\.showToast\s*=/.test(code)) offenders.push(`${f}: global assignment`);
      // bare `showToast = …` rebinding (not preceded by `.` or a word char)
      if (/[^.\w]showToast\s*=[^=]/.test(code)) offenders.push(`${f}: bare assignment`);
    }
    expect(offenders).toEqual([]);
  });

  test('08-replay-collab.js no longer builds its own singleton toast', () => {
    const src = fs.readFileSync(path.join(jsDir, '08-replay-collab.js'), 'utf8');
    expect(src).not.toMatch(/getElementById\('_toast'\)/);
    expect(src).not.toMatch(/function\s+showToast\s*\(/);
    // its call sites still toast — via the shared global
    expect((src.match(/showToast\(/g) || []).length).toBeGreaterThan(5);
  });

  test('the alias comment records the collision for future editors', () => {
    const src = fs.readFileSync(path.join(jsDir, '01-app-core.js'), 'utf8');
    expect(src).toMatch(/window\.showToast = toast/);
  });
});
