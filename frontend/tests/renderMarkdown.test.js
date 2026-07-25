import { describe, it, expect } from 'vitest';

// Test the renderMarkdown function that converts markdown to HTML
// This is critical for chat message rendering

function escHtml(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#x27;');
}

function renderMarkdown(text) {
  if (!text) return '';
  let t = escHtml(text);
  t = t.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) =>
    `<pre><code class="lang-${lang}">${code}</code></pre>`);
  t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
  t = t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  t = t.replace(/\*(.+?)\*/g, '<em>$1</em>');
  t = t.replace(/\n/g, '<br>');
  return t;
}

describe('renderMarkdown', () => {
  it('renders bold text', () => {
    expect(renderMarkdown('**hello**')).toBe('<strong>hello</strong>');
  });

  it('renders italic text', () => {
    expect(renderMarkdown('*world*')).toBe('<em>world</em>');
  });

  it('renders inline code', () => {
    expect(renderMarkdown('`code`')).toBe('<code>code</code>');
  });

  it('renders code blocks', () => {
    const result = renderMarkdown('```python\nprint("hi")\n```');
    expect(result).toContain('<pre><code');
    expect(result).toContain('print');
  });

  it('escapes HTML in user content', () => {
    const result = renderMarkdown('<script>alert("xss")</script>');
    expect(result).not.toContain('<script>');
    expect(result).toContain('&lt;script&gt;');
  });

  it('handles empty input', () => {
    expect(renderMarkdown('')).toBe('');
    expect(renderMarkdown(null)).toBe('');
    expect(renderMarkdown(undefined)).toBe('');
  });

  it('renders line breaks', () => {
    expect(renderMarkdown('line1\nline2')).toBe('line1<br>line2');
  });

  it('preserves text without markdown', () => {
    expect(renderMarkdown('hello world')).toBe('hello world');
  });
});
