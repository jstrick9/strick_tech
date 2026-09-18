// r55 regression: the Inbox sweep says WHY items were not placed.
//
// Found live while deep-diving Inbox as the new-admin persona: capturing
// notes and sweeping on a fresh install reported "Filed 0. 2 left in the
// inbox — the router could not place them." — a dead-end sentence. The real
// reason ("no workspaces exist") lived only in the preview rows' tooltip,
// and it names the fix (create a workspace in the Knowledge pane). The
// module's own header comment promises "An item the router cannot place
// stays put and says why" — the sweep note now honors that, and the preview
// STAYS rows show the reason inline instead of tooltip-only.
//
// Verified live: capture on a workspace-less install -> sweep note reads
// "...could not place them (no workspaces exist). Create a workspace in the
// Knowledge pane first, then sweep again."; preview rows show
// "no-match — no workspaces exist" inline; after creating an ICM workspace,
// a matching capture files into it (Filed 1) with the reason recorded.

const fs = require('fs');
const path = require('path');

const SRC = fs.readFileSync(path.join(__dirname, '..', 'js', '60-inbox.js'), 'utf8');
const noComments = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
const NC = noComments(SRC);

describe('inbox sweep explains itself (r55)', () => {
  test('the sweep note surfaces the shared reason of unplaced items', () => {
    expect(NC).toContain("reasons.includes('no workspaces exist')");
    expect(NC).toMatch(/Create a workspace in the Knowledge pane first/);
    // reasons come from the sweep response's left_in_inbox, deduped
    expect(NC).toMatch(/left_in_inbox[\s\S]{0,80}map\(\(l\) => \(l\.reason/g);
  });

  test('the no-workspaces hint only fires when items actually remain', () => {
    // the reason block is built inside `if (d.remaining)`
    expect(NC).toMatch(/if \(d\.remaining\) \{[\s\S]{0,400}why = ' — the router could not place them';/);
    // and the note is Filed+remaining concatenated with the (possibly empty) why
    expect(NC).toMatch(/left in the inbox` \+ why;/);
  });

  test('preview STAYS rows render the reason inline, not tooltip-only', () => {
    expect(NC).toMatch(/\$\{esc\(l\.status\)\}\$\{l\.reason \? ' — ' \+ esc\(l\.reason\) : ''\}/);
  });

  test('the tooltip is kept (hover still carries the full reason)', () => {
    expect(NC).toContain('title="${esc(l.reason)}"');
  });
});
