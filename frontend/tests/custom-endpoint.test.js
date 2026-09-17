// r52 regression: custom endpoints (custom_url:) work end to end.
//
// resolve_model() parsed 'custom_url:<base>' model strings since v11.5.0 but
// nothing implemented the provider — the URL fell through to OpenRouter as a
// model name (live repro: a Settings-verified ONLINE endpoint answered "No
// OPENROUTER_API_KEY set"). These asserts pin the frontend half of the fix:
// the key travels with chat requests, model discovery goes through the app's
// backend (the page cannot fetch a cross-origin endpoint — CORS), the picker
// pins the chosen model in the option value, and the Settings connection
// test no longer probes from the browser.

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = () =>
  readFileSync(join(root, 'js', '01-app-core.js'), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\/\/[^\n]*/g, '');

describe('r52 custom endpoints (01-app-core.js)', () => {
  it('chat requests carry the saved custom key when a custom endpoint is selected', () => {
    const s = src();
    expect(s).toContain("custom_api_key: (selectedModel || '').startsWith('custom_url:')");
    expect(s).toContain("_safeLS.get('agentic_os_custom_api_key')");
  });

  it('the picker discovers models through the backend, not the browser', () => {
    expect(src()).toContain("fetch('/api/agents/models?base=' + encodeURIComponent(customUrl))");
  });

  it('discovered options pin the exact model in the value', () => {
    expect(src()).toContain('custom_url:${escHtml(customUrl)}|${escHtml(id)}');
  });

  it('the Settings connection test probes through the backend too', () => {
    const s = src();
    expect(s).toContain("fetch('/api/agents/models?base=' + encodeURIComponent(baseUrl))");
    expect(s).not.toContain('fetch(baseUrl + ');
  });

  it('a pinned custom model shows its model id, not the whole URL', () => {
    const s = src();
    expect(s).toContain("val.includes('|') ? val.split('|').pop()");
  });
});
