/**
 * Studio — fenced-code extraction from AI replies.
 *
 * Regression guard for two real file-corrupting bugs in studioAIEdit():
 *
 *   • The old logic was `text.split('\n').slice(1).join('\n')`, which assumed a
 *     code fence always spans multiple lines. A single-line reply such as
 *     ```Hello World``` produced an EMPTY string, so "Accept & Apply" would
 *     blank the user's file.
 *   • Trailing prose after the closing fence ("...```\nHope that helps!") was
 *     kept verbatim, writing the fence and the chatter into the source file.
 */
import { describe, it, expect, beforeAll } from 'vitest';
import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const CORE_JS = readFileSync(resolve(__dirname, '../js/01-app-core.js'), 'utf-8');

let extract;

beforeAll(() => {
  // Pull the real implementation out of the bundle so the test exercises
  // shipped code rather than a copy.
  const match = CORE_JS.match(/window\.extractCodeFromResponse = function[\s\S]*?\n};/);
  if (!match) throw new Error('extractCodeFromResponse not found in 01-app-core.js');
  const sandbox = { window: {} };
  // eslint-disable-next-line no-new-func
  new Function('window', match[0])(sandbox.window);
  extract = sandbox.window.extractCodeFromResponse;
});

describe('extractCodeFromResponse', () => {
  it('keeps content of a single-line fence (used to blank the file)', () => {
    expect(extract('```Hello World```')).toBe('Hello World');
  });

  it('extracts a normal multi-line fenced block', () => {
    expect(extract('```html\n<h1>Hi</h1>\n```')).toBe('<h1>Hi</h1>');
  });

  it('drops trailing prose after the closing fence', () => {
    expect(extract('```html\n<h1>Hi</h1>\n```\nHope that helps!')).toBe('<h1>Hi</h1>');
  });

  it('finds a fenced block preceded by commentary', () => {
    expect(extract('Sure!\n```js\nconst a=1;\n```\ndone')).toBe('const a=1;');
  });

  it('returns unfenced code unchanged', () => {
    expect(extract('plain code no fence')).toBe('plain code no fence');
  });

  it('handles an unterminated opening fence', () => {
    expect(extract('```js\nunterminated')).toBe('unterminated');
  });

  it('treats a lone language tag as no code', () => {
    expect(extract('```js```')).toBe('');
  });

  it('handles empty and nullish input safely', () => {
    expect(extract('')).toBe('');
    expect(extract(null)).toBe('');
    expect(extract(undefined)).toBe('');
  });
});
