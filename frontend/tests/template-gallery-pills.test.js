// Frontend correctness: category pills in the Template Gallery are rendered
// with data-act-click, but filterTemplates() read the onclick attribute to
// decide which pill shows its "active" state. The two never matched, so after
// clicking any category the grid filtered correctly while NO pill showed as
// selected — the category bar looked like nothing was active.
import { describe, it, expect, beforeEach } from 'vitest';
import fs from 'fs';
import path from 'path';

function escHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

function loadGallery() {
  const source = fs.readFileSync(path.join(__dirname, '..', 'js', '21-template-gallery.js'), 'utf8');
  const stateFeedback = {
    loadingElement: () => '',
    errorElement: () => '',
    emptyElement: () => '',
  };
  const _safeLS = { get: () => null, set: () => {} };
  new Function(
    'window', 'document', 'console', 'fetch', '_safeLS', 'stateFeedback',
    'escHtml', 'humanError', 'toast', 'gmPrompt', 'gmConfirm', 'gmDanger', 'nav',
    'autoResizeInput', 'studioLoadFileTree', 'studioReloadPreview', 'PALETTE_CMDS',
    source
  )(
    globalThis.window, globalThis.document, globalThis.console, globalThis.fetch,
    _safeLS, stateFeedback, escHtml, (e) => String(e), () => {},
    async () => null, async () => true, async () => true, () => {},
    () => {}, () => {}, () => {}, undefined
  );
}

function buildPane() {
  document.body.innerHTML = `
    <div id="tmpl-cats">
      <span class="bp-btn" data-act-click="filterTemplates('all')">All (3)</span>
      <span class="bp-btn" data-act-click="filterTemplates('saas')">Saas (2)</span>
      <span class="bp-btn" data-act-click="filterTemplates('marketing')">Marketing (1)</span>
    </div>
    <input id="tmpl-search" value="">
    <div id="tmpl-grid"></div>
    <span id="tmpl-count"></span>
  `;
}

describe('Template Gallery category pills', () => {
  beforeEach(() => {
    buildPane();
    loadGallery();
  });

  it('marks the clicked category pill active', () => {
    window.filterTemplates('saas');
    const pills = [...document.querySelectorAll('#tmpl-cats .bp-btn')];
    expect(pills[1].classList.contains('active')).toBe(true);
    expect(pills[0].classList.contains('active')).toBe(false);
    expect(pills[2].classList.contains('active')).toBe(false);
  });

  it('restores the All pill when returning to all', () => {
    window.filterTemplates('marketing');
    window.filterTemplates('all');
    const pills = [...document.querySelectorAll('#tmpl-cats .bp-btn')];
    expect(pills[0].classList.contains('active')).toBe(true);
    expect(pills[1].classList.contains('active')).toBe(false);
    expect(pills[2].classList.contains('active')).toBe(false);
  });

  it('reads the attribute the pills are actually rendered with', () => {
    // Source contract: pills are built with data-act-click — the highlight
    // logic must never go back to reading onclick.
    const source = fs.readFileSync(path.join(__dirname, '..', 'js', '21-template-gallery.js'), 'utf8');
    const start = source.indexOf('function filterTemplates');
    const body = source.slice(start, start + 700);
    expect(body).toContain("getAttribute('data-act-click')");
    expect(body).not.toContain("getAttribute('onclick')");
  });
});
