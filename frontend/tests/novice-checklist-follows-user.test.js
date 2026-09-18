// r55 regression: the Getting Started checklist follows the user.
//
// The checklist (94-novice-assist) used to render ONLY inside #chat-empty,
// which hideChatEmpty() hides on the first send — so the "Save your first
// note" and "Create your first task" steps could never be SEEN completing:
// the card went invisible the moment the novice started chatting and only
// resurfaced on a fresh empty session. Found live while deep-diving Chat as
// the new-admin persona.
//
// Same round, adjacent find: sendChat and the API-key save path called
// markChecklistStep('first_chat'/'api_key') — an API no module defines, with
// step ids no checklist uses. The real API is aosMarkStep with ids
// connect/message/note/task (the checklist's own listeners happened to cover
// the same events, so the dead calls were invisible).
//
// Contract locked here:
//   1. GS_STEPS ids are exactly connect/message/note/task — the id drift
//      that made the old calls dead must not come back.
//   2. 01-app-core marks steps through aosMarkStep with the correct ids and
//      contains no markChecklistStep references in executable code.
//   3. 94 places the card in the empty state when visible, otherwise pins it
//      above the message list while steps remain, and drops the pinned copy
//      once all steps are done.
//   4. Placement reacts to both mutation kinds: #chat-empty style/class
//      changes (send/clear) and #chat-messages childList changes (the
//      ensureChatEmpty clone path replaces the node wholesale).
//
// Verified live: send -> card pinned instantly (2/4 done); task created ->
// 3/4 visibly checks off while pinned; final step -> pinned copy removed;
// new session -> 🎉 card in the empty state; reload -> state persists;
// dismiss -> stays dismissed across sweeps.

const fs = require('fs');
const path = require('path');

const read = (f) => fs.readFileSync(path.join(__dirname, '..', 'js', f), 'utf8');
const noComments = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

const CORE = noComments(read('01-app-core.js'));
const NOVICE = read('94-novice-assist.js');
const NOVICE_NC = noComments(NOVICE);

describe('Getting Started checklist follows the user (r55)', () => {
  test('checklist step ids are exactly connect/message/note/task', () => {
    const m = NOVICE.match(/const GS_STEPS = \[([\s\S]*?)\];/);
    expect(m).toBeTruthy();
    const ids = [...m[1].matchAll(/id:\s*'(\w+)'/g)].map((x) => x[1]);
    expect(ids.sort()).toEqual(['connect', 'message', 'note', 'task']);
  });

  test('01-app-core marks steps through the real API with correct ids', () => {
    expect(CORE).toContain("window.aosMarkStep('message')");
    expect(CORE).toContain("window.aosMarkStep('connect')");
    // the dead API (wrong name AND wrong ids) must not come back
    expect(CORE).not.toContain('markChecklistStep');
    // no module defines it either — it never existed
    const dir = path.join(__dirname, '..', 'js');
    for (const f of fs.readdirSync(dir)) {
      if (!f.endsWith('.js')) continue;
      expect(noComments(read(f))).not.toMatch(/function\s+markChecklistStep/);
    }
  });

  test('94 exposes aosMarkStep and renders from the canonical store', () => {
    expect(NOVICE_NC).toContain('window.aosMarkStep = function');
    expect(NOVICE_NC).toMatch(/function\s+isDone\s*\(/);
    expect(NOVICE_NC).toMatch(/_st\.done\[id\]\s*=\s*true/);
  });

  test('placement: empty state when visible, pinned strip otherwise, dropped when done', () => {
    expect(NOVICE_NC).toMatch(/function\s+gsEmptyVisible\s*\(/);
    expect(NOVICE_NC).toMatch(/function\s+gsPinnedHost\s*\(/);
    expect(NOVICE_NC).toContain("getElementById('aos-gs-pinned')");
    // pinned host is inserted directly above the message list
    expect(NOVICE_NC).toMatch(/container\.insertBefore\(pinned,\s*msgs\)/);
    // while steps remain, the pinned host is the fallback surface
    expect(NOVICE_NC).toMatch(/else if \(!allDone\)\s*\{\s*host = gsPinnedHost\(\)/);
    // once all steps are done the pinned copy is removed (celebration stays
    // on the empty-state landing surface only)
    expect(NOVICE_NC).toMatch(/parentElement\.id === 'aos-gs-pinned'/);
  });

  test('re-parenting moves the existing card between hosts', () => {
    expect(NOVICE_NC).toMatch(/existing\.parentElement !== host/);
    expect(NOVICE_NC).toMatch(/host\.appendChild\(existing\)/);
  });

  test('placement reacts to both empty-state hiding and node replacement', () => {
    // style/class changes on #chat-empty (hideChatEmpty / clearChatHistory)
    expect(NOVICE_NC).toContain("attributeFilter: ['style', 'class']");
    // childList on #chat-messages (ensureChatEmpty replaces the node)
    expect(NOVICE_NC).toMatch(/__gsListObs/);
    expect(NOVICE_NC).toMatch(/observe\(msgs,\s*\{\s*childList:\s*true\s*\}\)/);
  });

  test('sweep refreshes placement and rebinds the observer', () => {
    const m = NOVICE_NC.match(/function sweep\(\)\s*\{([\s\S]*?)\n  \}/);
    expect(m).toBeTruthy();
    expect(m[1]).toContain('bindGsPlacementObserver()');
    expect(m[1]).toContain('renderGettingStarted()');
  });
});
