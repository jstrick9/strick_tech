// Frontend correctness: a fenced code block containing a backtick character
// (JS template literals, SQL backticks) must not be re-parsed by the inline
// `` `...` `` regex. Before the fix, block code was left with raw backticks and
// the inline-code transform ran after block replacement, so the template/SQL
// literal got wrapped in a nested <code style> span inside the <pre>, corrupting
// the block's content. We test the REAL renderMarkdownEnhanced (01-app-core.js).
import { describe, it, expect } from 'vitest';

function escHtml(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c])); }
function jsArg(v) { return JSON.stringify(v === undefined ? null : v).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
function safeUrl(u) { const s = String(u || ''); return /^(https?:|mailto:|#|\/)/i.test(s) && !/[\u0000-\u001f]/.test(s) ? s : '#'; }

// Extract the real function from the source and eval it with its globals.
function loadRealFn() {
  const fs = require('fs'); const path = require('path');
  const code = fs.readFileSync(path.join(__dirname, '..', 'js', '01-app-core.js'), 'utf8');
  const start = code.indexOf('function renderMarkdownEnhanced');
  const end = code.indexOf('\n}', start) + 2;
  const fn = code.slice(start, end);
  const win = { _hljsReady: false };
  return new Function('window', 'escHtml', 'safeUrl', 'jsArg', fn + '\nreturn {renderMarkdownEnhanced};')(win, escHtml, safeUrl, jsArg).renderMarkdownEnhanced;
}

describe('renderMarkdownEnhanced preserves backtick code blocks', () => {
  const render = loadRealFn();

  it('does not mangle a JS template literal inside a fenced block', () => {
    const out = render('```js\nconst s = `hi ${name}`;\n```');
    // The code must stay inside the pre/code block, not wrapped in inline <code>.
    expect(out).toContain('hi ${name}');
    expect(out).not.toContain('<code style="background');
  });

  it('does not mangle SQL backticks inside a fenced block', () => {
    const out = render('```sql\nSELECT * FROM `users` WHERE id=1;\n```');
    expect(out).toContain('SELECT * FROM `users` WHERE id=1;');
    expect(out).not.toContain('<code style="background');
  });

  it('still renders genuine inline code', () => {
    const out = render('use `npm i` to install');
    expect(out).toContain('<code');
    expect(out).toContain('npm i');
  });

  it('renders a plain fenced block normally', () => {
    const out = render('```js\nlet a = 1;\n```');
    expect(out).toContain('let a = 1;');
    expect(out).not.toContain('<code style="background');
  });
});
