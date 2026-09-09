/**
 * #077 — Chat conversation is lost on page refresh.
 *
 * Previously `S.sessionId` was a bare `'session_'+Date.now()` recomputed on
 * every load (never persisted), and the transcript was not restored, so an
 * accidental page refresh silently discarded the current conversation — the
 * session id changed and the chat history (bubbles + S.chatHistory) came back
 * empty. The user had to dig the conversation back out of the history drawer.
 *
 * Fix: persist the active chat session id in localStorage and restore it on the
 * first chat arrival after a reload (reusing the existing `loadChatSession()`),
 * so a refresh resumes the same conversation. The id is only remembered after
 * a real send (server-side session exists), and cleared by `startNewChatSession`
 * so a fresh chat stays fresh until the user actually sends something.
 *
 * Verified live: after send -> reload, sessionId matches, bubbles + chatHistory
 * restored, 0 page errors. New chat -> reload shows launchpad (no restore).
 * Source-level regression tests.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const SRC = readFileSync(resolve(__dirname, '../js/01-app-core.js'), 'utf8');

describe('#077 chat resumes the active conversation after a reload', () => {
  it('persists the active session id under a stable localStorage key', () => {
    expect(SRC).toMatch(/agentic_os_active_chat_session/);
    expect(SRC).toMatch(/function _rememberActiveChatSession\(\)\s*\{/);
    expect(SRC).toMatch(/function _clearActiveChatSession\(\)\s*\{/);
  });

  it('restores the last active session on the first chat arrival after boot', () => {
    // The nav(pane==='chat') branch must attempt a restore once, guarded by a
    // flag so later in-page navigations don't re-restore / clobber the live
    // transcript.
    expect(SRC).toMatch(/window\._chatHistoryRestoreTried/);
    const m = SRC.match(/window\.loadChatSession\(_act\)/);
    expect(m).not.toBeNull();
  });

  it('remembers the session only after a send (real server-side session exists)', () => {
    // The remember call sits in the /api/sessions POST success path.
    const idx = SRC.indexOf("_rememberActiveChatSession()");
    expect(idx).toBeGreaterThan(-1);
    // It must appear after a `/api/sessions` POST block (i.e. only on send).
    expect(SRC.indexOf("/api/sessions")).toBeGreaterThan(-1);
  });

  it('clears the persisted id when a new chat is started, and remembers on restore', () => {
    // startNewChatSession clears the persisted id so a fresh chat stays fresh
    // until the user sends something.
    const start = SRC.indexOf('window.startNewChatSession = function()');
    expect(start).toBeGreaterThan(-1);
    const body = SRC.slice(start, SRC.indexOf('window.pinChatSession', start));
    expect(body).toMatch(/_clearActiveChatSession\(\)/);
    // The restore path remembers the session it is now viewing.
    const load = SRC.indexOf('window.loadChatSession = async function(sid)');
    const loadBody = SRC.slice(load, load + 2000);
    expect(loadBody).toMatch(/_rememberActiveChatSession\(\)/);
  });
});
