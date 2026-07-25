import { describe, it, expect } from 'vitest';

// Test the escHtml function that protects against XSS
// This is the most critical security function in the frontend

function escHtml(s) {
  if (!s) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;');
}

describe('escHtml', () => {
  it('escapes HTML tags', () => {
    expect(escHtml('<script>alert("xss")</script>')).toBe(
      '&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;'
    );
  });

  it('escapes ampersands', () => {
    expect(escHtml('a & b')).toBe('a &amp; b');
  });

  it('escapes quotes', () => {
    expect(escHtml('"hello" \'world\'')).toBe('&quot;hello&quot; &#x27;world&#x27;');
  });

  it('handles null/undefined', () => {
    expect(escHtml(null)).toBe('');
    expect(escHtml(undefined)).toBe('');
    expect(escHtml('')).toBe('');
  });

  it('handles numbers', () => {
    expect(escHtml(42)).toBe('42');
  });

  it('escapes nested HTML', () => {
    expect(escHtml('<div onclick="evil()">click</div>')).toBe(
      '&lt;div onclick=&quot;evil()&quot;&gt;click&lt;/div&gt;'
    );
  });

  it('handles already-escaped content', () => {
    expect(escHtml('&amp;')).toBe('&amp;amp;');
  });
});
