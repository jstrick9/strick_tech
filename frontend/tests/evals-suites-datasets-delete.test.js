// Frontend correctness: eval suites and datasets must be deletable (#145).
//
// Same create-without-delete asymmetry as #144: suites could be created from
// the Eval Framework pane ("+ New Suite") and datasets from the Evals pane
// ("+ New Dataset"), but neither could be removed — the lists only grew.
// Both panes now expose a confirmed delete. The built-in starter suites are
// refused by the API (they re-seed on the next request) and the refusal is
// surfaced as a toast rather than silently ignored.
import { describe, it, expect } from 'vitest';

const fs = require('fs');
const path = require('path');
const EF = fs.readFileSync(path.join(__dirname, '..', 'js', '55-eval-framework.js'), 'utf8');
const EV = fs.readFileSync(path.join(__dirname, '..', 'js', '05-evals-observability.js'), 'utf8');

describe('eval framework suites are deletable', () => {
  it('every suite card renders a delete affordance', () => {
    const render = EF.match(/async function renderEvalFramework[\s\S]*?\n\}/)[0];
    expect(render).toMatch(/data-act-click="evalDeleteSuite\(\$\{jsArg\(s\.suite_id\)\}/);
    expect(render).toContain('aria-label="Delete suite"');
  });

  it('evalDeleteSuite confirms, calls DELETE, re-renders, surfaces refusal', () => {
    const fn = EF.match(/async function evalDeleteSuite[\s\S]*?\n\}/)[0];
    expect(fn).toContain("gmDanger('Delete suite'");
    expect(fn).toContain("`/api/eval-framework/suites/${encodeURIComponent(suiteId)}`");
    expect(fn).toContain("{ method: 'DELETE' }");
    expect(fn).toContain('renderEvalFramework()');
    // the starter-suite refusal (403 + error) must be shown, not swallowed
    expect(fn).toMatch(/!r\.ok \|\| !d\.ok/);
  });

  it('evalDeleteSuite is exported for the delegated handler', () => {
    expect(EF).toContain('window.evalDeleteSuite = evalDeleteSuite;');
  });
});

describe('evals datasets are deletable', () => {
  it('every dataset row renders a delete affordance', () => {
    const render = EV.match(/async function renderEvals[\s\S]*?\n\}/)[0];
    expect(render).toMatch(/data-act-click="evalDeleteDataset\(\$\{jsArg\(ds\.id\)\}/);
    expect(render).toContain('aria-label="Delete dataset"');
  });

  it('evalDeleteDataset confirms, calls DELETE, re-renders', () => {
    const fn = EV.match(/async function evalDeleteDataset[\s\S]*?\n\}/)[0];
    expect(fn).toContain("gmDanger('Delete dataset'");
    expect(fn).toContain("`/api/evals/datasets/${encodeURIComponent(dsId)}`");
    expect(fn).toContain("{ method: 'DELETE' }");
    expect(fn).toContain('renderEvals()');
  });
});
