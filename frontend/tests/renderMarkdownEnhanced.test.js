import { describe, it, expect } from 'vitest';

// Mirrors renderMarkdownEnhanced in frontend/js/01-app-core.js (the primary
// markdown renderer, wired as window.renderMarkdown). It handles the raw text
// directly and injects tags itself, so every user-content capture group must
// be HTML-escaped before embedding. Failing to escape one reintroduces
// HTML/beacon/phishing-link injection.

function escHtml(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#x27;');
}
const jsArg = (x) => JSON.stringify(x);

function renderMarkdownEnhanced(text) {
  if (!text) return '';
  let t = text;
  t = t.replace(/```(\w*)\n?([\s\S]*?)```/g, (_m, lang, code) => {
    const escaped = code.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    const langLabel = lang || 'code';
    const highlightedCode = escaped; // hljs not present in test
    const lineNumHtml = '';
    return `<div class="code-with-lines"><span>${escHtml(langLabel)}</span><pre id="x"><code class="hljs language-${langLabel}">${highlightedCode}</code></pre></div>`;
  });
  t = t.replace(/`([^`\n]+)`/g, (_m, c) => `<code>${escHtml(c)}</code>`);
  t = t.replace(/\*\*\*(.+?)\*\*\*/g, (_m, x) => `<strong><em>${escHtml(x)}</em></strong>`);
  t = t.replace(/\*\*(.+?)\*\*/g, (_m, x) => `<strong>${escHtml(x)}</strong>`);
  t = t.replace(/\*(.+?)\*/g, (_m, x) => `<em>${escHtml(x)}</em>`);
  t = t.replace(/^### (.+)$/gm, (_m, x) => `<h3>${escHtml(x)}</h3>`);
  t = t.replace(/^## (.+)$/gm, (_m, x) => `<h2>${escHtml(x)}</h2>`);
  t = t.replace(/^# (.+)$/gm, (_m, x) => `<h1>${escHtml(x)}</h1>`);
  t = t.replace(/^> (.+)$/gm, (_m, x) => `<blockquote>${escHtml(x)}</blockquote>`);
  t = t.replace(/^[\s]*[-•*] (.+)$/gm, (_m, x) => `<div><span>•</span><span>${escHtml(x)}</span></div>`);
  t = t.replace(/^[\s]*(\d+)\. (.+)$/gm, (_m, n, x) => `<div><span>${escHtml(n)}.</span><span>${escHtml(x)}</span></div>`);
  t = t.replace(/^---+$/gm, '<hr>');
  t = t.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_m, label, href) => {
    const safe = /^(https?:|\/\/|mailto:|\/|#)/i.test(href) ? href : '#';
    return `<a href="${escHtml(safe)}" target="_blank">${escHtml(label)}</a>`;
  });
  t = t.replace(/\n\n/g, '</p><p>');
  t = t.replace(/\n/g, '<br>');
  return '<p>' + t + '</p>';
}

function hasUnescapedUserTag(html) {
  const stripped = html.replace(/<\/?(?:p|strong|em|h\d|blockquote|div|span|br|pre|code|a|hr)\b[^>]*>/gi, '');
  return /<[a-z/]/i.test(stripped);
}

describe('renderMarkdownEnhanced', () => {
  it('escapes inline-code user content', () => {
    expect(hasUnescapedUserTag(renderMarkdownEnhanced('`<img src=x onerror=alert(1)>`'))).toBe(false);
  });
  it('escapes bold/italic user content', () => {
    expect(renderMarkdownEnhanced('**<script>alert(1)</script>**')).not.toContain('<script>');
    expect(renderMarkdownEnhanced('*<b x>y</b>*')).not.toContain('<b x>');
  });
  it('escapes headers, blockquotes and lists', () => {
    expect(hasUnescapedUserTag(renderMarkdownEnhanced('# <img src=x onerror=alert(2)>'))).toBe(false);
    expect(hasUnescapedUserTag(renderMarkdownEnhanced('> <svg onload=alert(1)>'))).toBe(false);
    expect(hasUnescapedUserTag(renderMarkdownEnhanced('- <a href="javascript:alert(1)">x</a>'))).toBe(false);
    expect(hasUnescapedUserTag(renderMarkdownEnhanced('1. <img onerror=alert(1)>'))).toBe(false);
  });
  it('blocks javascript:/data: links', () => {
    expect(renderMarkdownEnhanced('[click](javascript:alert(1))')).not.toMatch(/href="javascript:/i);
    expect(renderMarkdownEnhanced('[click](data:text/html,x)')).not.toMatch(/href="data:/i);
  });
  it('allows safe link schemes', () => {
    expect(renderMarkdownEnhanced('[ok](https://example.com)')).toContain('href="https://example.com"');
    expect(renderMarkdownEnhanced('[rel](/foo)')).toContain('href="/foo"');
  });
  it('escapes label content in links', () => {
    expect(renderMarkdownEnhanced('[<img src=x onerror=alert(1)>](https://x.com)')).not.toContain('<img src=x');
  });
  it('keeps benign formatting intact', () => {
    const out = renderMarkdownEnhanced('**bold** and `code here` and [link](https://x.com)');
    expect(out).toContain('<strong>bold</strong>');
    expect(out).toContain('<code>code here</code>');
    expect(out).toContain('href="https://x.com"');
  });
  it('preserves code-block content', () => {
    const out = renderMarkdownEnhanced('```js\nconsole.log("<b>hi</b>")\n```');
    expect(out).toContain('console.log');
    expect(out).toContain('&lt;b&gt;'); // code block content escaped
  });
});
