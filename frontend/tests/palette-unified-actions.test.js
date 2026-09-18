// r56 regression: the command palette's async sections render in ONE pass
// with actions index-aligned to the DOM.
//
// Found live while deep-diving the ⌘K command palette: each async section
// (Chat History, Global Search) did its own `results.innerHTML = html` as its
// fetch resolved, re-attaching listeners only for its own rows. Live-proven
// failures: (1) clicking a chat-history row navigated to Settings — the wrong
// action — because allActions was [items..., globalItems...] while the DOM
// order was [items..., chatRows..., globalRows...]; (2) the tail global rows
// were off by the chat-row count, so clicking them did nothing; (3) between
// the chat and global rebuilds, quick-command rows had no listeners at all;
// (4) the memory-section wrapper (02-studio) appended rows that the next
// innerHTML rebuild silently clobbered — memory results flickered and
// vanished. The fix: one Promise.all fetch pass, one innerHTML write, one
// listener attach, plus a debounce and stale-token guard so a slow response
// from an earlier keystroke can never overwrite a newer render.
//
// Verified live: 'please' (7 chat + 3 global results) — chat row loads its
// session (nav 'chat' + loadChatSession), last global row fires, quick
// command fires; 'agent' shows the 🌌 Memory Results section; rapid retype
// never leaves a stale section; keyboard ArrowDown+Enter works across all
// sections; memory rows insert into #chat-input and close the palette.

const fs = require('fs');
const path = require('path');

const core = fs.readFileSync(path.join(__dirname, '..', 'js', '01-app-core.js'), 'utf8');
const studio = fs.readFileSync(path.join(__dirname, '..', 'js', '02-studio.js'), 'utf8');
// The r56 comment quotes the old pattern verbatim, so strip comments before
// counting code occurrences.
const noComments = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

// Isolate filterPalette's body: from its declaration to handleGlobalItemClick.
const start = core.indexOf('async function filterPalette()');
const end = core.indexOf('function handleGlobalItemClick');
const fn = noComments(core.slice(start, end));
const r56 = fn.indexOf('clearTimeout(_paletteAsyncTimer)');
const asyncPart = fn.slice(r56);

describe('command palette unified render (r56)', () => {
  test('the async path writes innerHTML exactly once', () => {
    expect(asyncPart.match(/results\.innerHTML = html/g).length).toBe(1);
  });

  test('allActions is index-aligned with the DOM: items, chat, memory(null), global', () => {
    expect(asyncPart).toMatch(/\.\.\.items\.map\(c => c\.action\),\s*\.\.\.chatActions,\s*\.\.\.memResults\.map\(\(\) => null\),\s*\.\.\.globalActions,/);
  });

  test('listener attach skips null slots (memory rows stay delegation-only)', () => {
    expect(asyncPart).toMatch(/if \(allActions\[i\]\) el\.addEventListener/);
  });

  test('a stale response can never overwrite a newer keystroke', () => {
    expect(asyncPart).toContain('if (token !== _paletteQueryToken) return;');
    expect(asyncPart).toMatch(/clearTimeout\(_paletteAsyncTimer\)/);
  });

  test('all three sections are fetched in one Promise.all pass', () => {
    expect(asyncPart).toMatch(/Promise\.all\(\[[\s\S]*chat\/search[\s\S]*memory\/search[\s\S]*search\/global/);
  });

  test('memory rows keep their delegated handler and the guarded label class', () => {
    expect(asyncPart).toContain('data-act-click="hInsertAndClose(');
    expect(asyncPart).toContain('p-label u-6cb285c6');
  });

  test('chat rows load their session (the action that used to be mis-mapped)', () => {
    expect(asyncPart).toMatch(/loadChatSession\(item\.session_id\)/);
  });

  test('02-studio no longer wraps window.filterPalette (the clobbered append is gone)', () => {
    const ncStudio = noComments(studio);
    expect(ncStudio).not.toMatch(/window\.filterPalette\s*=/);
    expect(ncStudio).not.toContain('appendChild(section)');
    // and a pointer remains explaining where the memory section went
    expect(studio).toMatch(/r56 moved it into/);
  });
});
