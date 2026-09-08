// Regression guard (#060): the shared `.data-state` component must be
// screen-reader-announceable in EVERY variant, not just loading/error.
// loadingElement → role=status + polite; errorElement → role=alert + assertive;
// emptyElement / setEmpty / the emptyState() factory → role=status + polite.
// An empty state that is injected dynamically (after a fetch resolves) without
// an aria-live region is invisible to a screen reader — the user simply never
// hears that a pane has "nothing here yet". This locks the contract.
import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const SF = fs.readFileSync(path.join(__dirname, '..', 'js', '00-state-feedback.js'), 'utf8');
const CORE = fs.readFileSync(path.join(__dirname, '..', 'js', '01-app-core.js'), 'utf8');

describe('every .data-state variant carries a live-region role', () => {
  it('loadingElement emits role=status and aria-live=polite', () => {
    const seg = SF.slice(SF.indexOf('function loadingElement'), SF.indexOf('function setEmpty'));
    expect(seg).toMatch(/role="status"/);
    expect(seg).toMatch(/aria-live="polite"/);
  });

  it('emptyElement emits role=status and aria-live=polite', () => {
    const seg = SF.slice(SF.indexOf('function emptyElement'), SF.indexOf('function setError'));
    expect(seg).toMatch(/role="status"/);
    expect(seg).toMatch(/aria-live="polite"/);
  });

  it('setEmpty routes through makeBase with the status role', () => {
    const seg = SF.slice(SF.indexOf('function setEmpty'), SF.indexOf('function emptyElement'));
    expect(seg).toMatch(/makeBase\(root, 'state-empty', 'status'\)/);
  });

  it('errorElement stays alert + assertive (a problem, not a status)', () => {
    const seg = SF.slice(SF.indexOf('function errorElement'), SF.indexOf('window.stateFeedback'));
    expect(seg).toMatch(/role="alert"/);
    expect(seg).toMatch(/aria-live="assertive"/);
  });

  it('the emptyState() factory emits the same status+polite live region', () => {
    expect(CORE).toMatch(/data-state state-empty" role="status" aria-live="polite"/);
  });
});

describe('the last bespoke inline error/empty states route through the shared component', () => {
  it('kanban board load error uses stateFeedback.errorElement (role=alert, retry)', () => {
    const kb = fs.readFileSync(path.join(__dirname, '..', 'js', '28-kanban.js'), 'utf8');
    expect(kb).toMatch(/stateFeedback\.errorElement\s*\(\{/);
    expect(kb).toMatch(/retry: 'renderKanban\(\)'/);
    // The old bespoke .empty-state block must be gone from the load-error path.
    expect(kb).not.toMatch(/'<div class="empty-state" role="alert"/);
  });

  it('pane-error-boundary empty state uses stateFeedback.emptyElement (no .empty-state__*)', () => {
    const pb = fs.readFileSync(path.join(__dirname, '..', 'js', '92-pane-error-boundary.js'), 'utf8');
    expect(pb).toMatch(/stateFeedback\.emptyElement/);
    // The legacy BEM markup must no longer be emitted.
    expect(pb).not.toMatch(/empty-state__icon/);
    expect(pb).not.toMatch(/class="empty-state surface-z1"/);
  });

  it('pane-error-boundary error state uses stateFeedback.errorElement', () => {
    const pb = fs.readFileSync(path.join(__dirname, '..', 'js', '92-pane-error-boundary.js'), 'utf8');
    expect(pb).toMatch(/stateFeedback\.errorElement/);
  });
});
