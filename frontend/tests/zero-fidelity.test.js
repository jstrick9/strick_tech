// Frontend correctness: legitimate numeric value 0 must never be silently
// replaced by a "default" via truthy `||` fallback in rendered scores, counts
// and confidences. e.g. a code-quality score of 0 (worst possible) rendered as
// 75, a CSP directive count of 0 rendered as 1, confidence 0 rendered as 100%.
// Same bug class as the earlier DAG/0-coordinate fixes (#022-#025).
import { describe, it, expect, beforeAll, vi } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

function escHtml(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c])); }
function readJS(name) { return fs.readFileSync(path.join(__dirname, '..', 'js', name), 'utf8'); }

describe('zero-fidelity: score 0 is not replaced by an optimistic default', () => {
  let resultsEl;
  beforeAll(() => {
    globalThis.document.getElementById = vi.fn((id) => (id === 'bb-results') ? resultsEl : null);
    globalThis.gmAlert = vi.fn();
    globalThis.showToast = vi.fn();
    const src = readJS('07-quality-tools.js') + '\n;window.__bbShowResults=bbShowResults;';
    new Function('window','document','escHtml','gmAlert','showToast','fetch', src)(
      globalThis.window, globalThis.document, escHtml, globalThis.gmAlert, globalThis.showToast, globalThis.fetch
    );
  });

  it('renders a legitimate score of 0 as 0 (not 75)', () => {
    resultsEl = document.createElement('div');
    window.__bbShowResults({ score: 0, issues: [], severity: 'low' });
    expect(resultsEl.innerHTML).toContain('>0</div>');
    expect(resultsEl.innerHTML).not.toContain('>75</div>');
    // A 0 score must be treated as the worst band (danger), not warning.
    expect(resultsEl.innerHTML).toContain('var(--danger)');
  });

  it('keeps a real score of 75 as 75', () => {
    resultsEl = document.createElement('div');
    window.__bbShowResults({ score: 75, issues: [], severity: 'medium' });
    expect(resultsEl.innerHTML).toContain('>75</div>');
  });
});

describe('zero-fidelity: no truthy-fallback on numeric renders (pattern guard)', () => {
  const guards = [
    ['07-quality-tools.js', /d\.score\s*\|\|\s*75/],
    ['05-evals-observability.js', /d\.confidence\s*\|\|\s*1\)/],
    ['42-hitl.js', /item\.confidence\s*\|\|\s*0\.65/],
    ['58-csp-monitor.js', /v\.count\s*\|\|\s*1/],
    ['01-app-core.js', /models_count\s*\|\|\s*1/],
    ['05-evals-observability.js', /attacks\.count\s*\|\|\s*8/],
  ];
  for (const [file, re] of guards) {
    it(`${file} does not swallow 0 with a numeric || default`, () => {
      // Strip // comments so documented prior fixes don't trip the guard.
      const code = readJS(file).replace(/\/\/[^\n]*/g, '');
      expect(code.match(re)).toBeNull();
    });
  }
});
