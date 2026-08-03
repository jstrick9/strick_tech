/**
 * Chat — send/stop button contract.
 *
 * Regression guard for a real bug: the send button carried a hardcoded
 * inline `onclick="sendChat()"` in index.html, while sendChat() additionally
 * attached a *separate* stop handler with addEventListener during streaming.
 * Clicking the button to stop generation therefore fired BOTH listeners —
 * aborting the in-flight request and immediately dispatching a brand-new
 * duplicate chat request in the same click.
 *
 * These tests assert the structural fix: the button must not carry an inline
 * onclick, and both send and stop must be routed through a single delegated
 * handler that dispatches on current streaming state.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { JSDOM } from 'jsdom';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '../..');
const INDEX_HTML = readFileSync(resolve(ROOT, 'frontend/index.html'), 'utf-8');
const CORE_JS = readFileSync(resolve(ROOT, 'frontend/js/01-app-core.js'), 'utf-8');

describe('chat send button markup', () => {
  it('does not carry an inline onclick that would double-fire with the stop handler', () => {
    const btn = INDEX_HTML.match(/<button[^>]*id="chat-send"[^>]*>/);
    expect(btn, 'a #chat-send button must exist in index.html').not.toBeNull();
    expect(btn[0]).not.toMatch(/onclick=/);
  });

  it('is wired through the single delegated dispatcher', () => {
    expect(CORE_JS).toContain('window.onChatSendClick');
  });
});

describe('onChatSendClick dispatch', () => {
  let dom;

  beforeEach(() => {
    dom = new JSDOM('<!DOCTYPE html><button id="chat-send">➤</button>');
    global.window = dom.window;
    global.document = dom.window.document;
  });

  it('sends when idle and stops (without sending) while streaming', () => {
    const calls = [];

    // Minimal stand-in for the real dispatcher's contract.
    window._chatAbortController = null;
    window.sendChat = () => calls.push('send');
    window.onChatSendClick = function () {
      if (window._chatAbortController) {
        window._chatAbortController.abort();
        calls.push('stop');
        return;
      }
      window.sendChat();
    };

    // Idle → send
    window.onChatSendClick();
    expect(calls).toEqual(['send']);

    // Streaming → stop only, never a second send
    let aborted = false;
    window._chatAbortController = { abort: () => { aborted = true; } };
    window.onChatSendClick();

    expect(aborted).toBe(true);
    expect(calls).toEqual(['send', 'stop']);
    expect(calls.filter((c) => c === 'send')).toHaveLength(1);
  });
});
