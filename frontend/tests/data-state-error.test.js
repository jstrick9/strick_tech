import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const JS = path.join(__dirname, '..', 'js');

// Error states must route through the shared .data-state component
// (stateFeedback.setError / errorElement), not hand-rolled inline error divs.
// Small inline form/result *status* spans (e.g. "Not reviewed", <option>, a
// per-operation <span>) are intentionally left as-is and are not in scope.

describe('pane-body error states use the shared .data-state error component', () => {
  it('no full-pane error placeholder (pane.innerHTML = danger padding div) survives', () => {
    const files = fs.readdirSync(JS).filter(f => f.endsWith('.js'));
    const bad = [];
    for (const f of files) {
      const code = fs.readFileSync(path.join(JS, f), 'utf8');
      for (const m of code.matchAll(
        /pane\.innerHTML\s*=\s*[`'"]?\s*<div[^>]*style="[^"]*color:var\(--(danger|error)\)[^"]*padding:20px[^"]*"[^>]*>/g
      )) {
        if (code.slice(m.index - 80, m.index).includes('errorElement')) continue;
        bad.push(f + ': ' + m[0].slice(0, 60));
      }
    }
    expect(bad, 'full-pane error placeholders (use stateFeedback.errorElement):\n' + bad.join('\n')).toEqual([]);
  });

  it('no ad-hoc "Retry" button lives inside an inline error div', () => {
    const files = fs.readdirSync(JS).filter(f => f.endsWith('.js'));
    const bad = [];
    for (const f of files) {
      if (f === '00-state-feedback.js' || f === '92-pane-error-boundary.js') continue;
      const code = fs.readFileSync(path.join(JS, f), 'utf8').replace(/\/\/[^\n]*/g, '');
      for (const m of code.matchAll(/<button[^>]*>\s*(?:↻ )?Retry\s*<\/button>/gi)) {
        const nearby = code.slice(Math.max(0, m.index - 300), m.index);
        if (/color:var\(--(danger|error|red)\)/.test(nearby) && !/errorElement/.test(nearby)) {
          bad.push(f + ': ' + m[0].trim());
        }
      }
    }
    expect(bad, 'inline error divs with a manual Retry button:\n' + bad.join('\n')).toEqual([]);
  });

  it('the shared errorElement() helper is exposed and setError uses it', () => {
    const src = fs.readFileSync(path.join(JS, '00-state-feedback.js'), 'utf8');
    expect(src).toContain('function errorElement');
    expect(src).toContain('function errorHtml');
    expect(src).toContain('errorElement: errorElement');
    expect(src).toContain('state-error');
    expect(src).toContain('role="alert"');
    expect(src).toContain('aria-live="assertive"');
    // setError must render through the same markup generator.
    const setErrorSeg = src.slice(src.indexOf('function setError'), src.length);
    expect(setErrorSeg).toContain('errorHtml(opts)');
  });

  it('dashboard uses setError (fallback path also uses the component, no inline retry)', () => {
    const src = fs.readFileSync(path.join(JS, '36-dashboard.js'), 'utf8');
    expect(src).toContain('stateFeedback.setError');
    expect(src).toContain("retry:'renderDashboard()'");
  });
});
