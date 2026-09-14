// Frontend correctness: a chat stream that completes without error and without
// a single content delta (content-filtered or empty completion, or a 200 body
// that is not SSE at all) must not render a blank agent bubble, and must not
// push an empty assistant turn into chatHistory — that empty turn was sent to
// the model as `history` on the next message. Slash-command routing (action
// frames with no text) is legitimate and must not trip the notice.
import { describe, it, expect } from 'vitest';

const fs = require('fs');
const path = require('path');
const SOURCE = fs.readFileSync(path.join(__dirname, '..', 'js', '01-app-core.js'), 'utf8');

// Full-line comments only — the fix documents itself by quoting old behavior.
const CODE_ONLY = SOURCE.split('\n').filter(l => !/^\s*\/\//.test(l)).join('\n');
const SEND_FN = SOURCE.match(/async function sendChat\(\) \{[\s\S]*?\n\}/)?.[0] || '';

describe('chat refuses to fabricate an empty reply', () => {
  it('tracks whether the stream carried any actionable frame', () => {
    expect(SEND_FN).toContain('sawActionFrame = true');
    expect(SEND_FN).toContain('sawActionFrame = false');
  });

  it('replaces a zero-delta stream with an explicit notice, not a blank bubble', () => {
    expect(CODE_ONLY).toContain('emptyReply');
    expect(CODE_ONLY).toContain('(no response — the model returned no content');
    // The notice must not fire for action-only replies (slash commands) or
    // user-aborted streams.
    expect(SEND_FN).toMatch(/emptyReply = !\(fullText \|\| ''\)\.trim\(\) && !sawActionFrame && !clearHistorySeen && !aborted/);
  });

  it('does not push the empty assistant turn into history', () => {
    expect(CODE_ONLY).toContain("if (!clearHistorySeen && !emptyReply) S.chatHistory.push({ role: 'assistant', content: fullText });");
  });
});
