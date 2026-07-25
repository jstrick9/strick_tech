// Vitest setup — mock browser globals for Node.js testing
import { vi } from 'vitest';

// Mock DOM elements that the app expects
global.document.getElementById = vi.fn((id) => {
  if (id === 'toast-container') {
    return { appendChild: vi.fn(), remove: vi.fn() };
  }
  if (id === 'chat-input') {
    return { value: '', focus: vi.fn(), addEventListener: vi.fn() };
  }
  if (id === 'chat-send') {
    return { disabled: false, innerHTML: '➤', addEventListener: vi.fn(), removeEventListener: vi.fn() };
  }
  if (id === 'chat-messages') {
    return { appendChild: vi.fn(), scrollTop: 0, scrollHeight: 0, querySelector: vi.fn() };
  }
  if (id === 'sidebar') {
    return { classList: { toggle: vi.fn(() => false) }, style: {}, dataset: {} };
  }
  return null;
});

// Mock fetch
global.fetch = vi.fn(() => Promise.resolve({
  ok: true,
  status: 200,
  json: () => Promise.resolve({ ok: true }),
  text: () => Promise.resolve(''),
  body: {
    getReader: () => ({
      read: () => Promise.resolve({ done: true, value: undefined }),
    }),
  },
}));

// Mock localStorage
const _store = {};
global.localStorage = {
  getItem: (k) => _store[k] || null,
  setItem: (k, v) => { _store[k] = String(v); },
  removeItem: (k) => { delete _store[k]; },
};

// Mock window properties
global.window = global.window || {};
global.window.S = { chatHistory: [], sessionId: 'test', agents: [] };
global.window._safeLS = global.localStorage;
global.window.toast = vi.fn();
