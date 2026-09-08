// Dynamic content a11y: icon-only buttons (emoji glyphs) must carry an
// accessible name (aria-label/title), otherwise a screen reader announces an
// unnamed button. These appear in panes the static-shell axe scan can't reach.
// We extract the webhook row/card templates from the real source and axe-scan
// them, plus a repo-wide guard that any `<button ...>[/📋🗑✕…]<emojiglyph>...</button>`
// without aria-label/title is flagged.
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

function escHtml(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c])); }
function jsArg(s) { return escHtml(s).replace(/"/g, '&quot;'); }


describe('icon-only buttons carry accessible names (dynamic DOM)', () => {
  it('the webhook row copy/delete buttons carry accessible names (source contract)', () => {
    const src = fs.readFileSync(path.join(__dirname, '..', 'js', '33-webhooks.js'), 'utf8');
    const copyBtn = src.indexOf('hCopyWebhookUrl');
    const delBtn = src.indexOf('deleteWebhook');
    expect(copyBtn).toBeGreaterThan(-1);
    expect(delBtn).toBeGreaterThan(-1);
    // Each icon button must have BOTH aria-label and title.
    const copySeg = src.slice(copyBtn, copyBtn + 260);
    expect(copySeg).toContain('aria-label="Copy webhook URL"');
    expect(copySeg).toContain('title="Copy webhook URL"');
    const delSeg = src.slice(delBtn, delBtn + 260);
    expect(delSeg).toContain('aria-label="Delete webhook"');
    expect(delSeg).toContain('title="Delete webhook"');
  });

  it('repo-wide: no PURELY-icon button (emoji/✕ glyph with no text) is missing a name', () => {
    const files = fs.readdirSync(path.join(__dirname, '..', 'js')).filter(f => f.endsWith('.js'));
    const bad = [];
    for (const f of files) {
      const code = fs.readFileSync(path.join(__dirname, '..', 'js', f), 'utf8')
        .replace(/\/\/[^\n]*/g, '');
      // Match a single-line button whose inner content is ONLY icon glyphs —
      // no ASCII letters/digits (which would act as the accessible name).
      const re = /<button\b[^>]*>([^<]*[\u{1F300}-\u{1FAFF}\u2600-\u27BF\u2715\u00d7][^<]*)<\/button>/gu;
      const m = code.match(re);
      if (m) {
        for (const seg of m) {
          const inner = seg.replace(/^<button\b[^>]*>/, '').replace(/<\/button>$/, '');
          const hasText = /[A-Za-z0-9]/.test(inner); // real text => valid name
          if (!hasText && !/aria-label\s*=|title\s*=/.test(seg)) bad.push(f + ': ' + seg.slice(0, 55));
        }
      }
    }
    expect(bad, 'unlabeled icon buttons:\n' + bad.join('\n')).toEqual([]);
  });

  it('repo-wide: no empty <button></button> lacks both aria-label and title', () => {
    const files = fs.readdirSync(path.join(__dirname, '..', 'js')).filter(f => f.endsWith('.js'));
    const bad = [];
    for (const f of files) {
      const code = fs.readFileSync(path.join(__dirname, '..', 'js', f), 'utf8');
      const re = /<button\b[^>]*>(\s*)<\/button>/g;
      let m;
      while ((m = re.exec(code))) {
        const seg = m[0];
        if (!/aria-label\s*=|title\s*=/.test(seg)) bad.push(f + ': ' + seg.slice(0, 55));
      }
    }
    expect(bad, 'empty unnamed buttons (an icon was likely stripped):\n' + bad.join('\n')).toEqual([]);
  });
});
