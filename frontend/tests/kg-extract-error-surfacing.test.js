/**
 * r59 — kgExtract went silent on failure.
 *
 * The handler toasted "🧠 Extracting entities…" and then had exactly one
 * branch: success. No HTTP status check, no ok:false branch, no catch — a
 * failed extraction (backend error, LLM returning unusable output, network
 * drop) left the user staring at a progress toast that nothing ever
 * followed up on. Same silent-failure class as ragDeletePipeline (r58).
 *
 * Fix: every failure mode now reports — HTTP error, ok:false body with the
 * server's error text, network exception — and only the success path
 * re-renders the graph. Source-level regression tests.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const SRC = readFileSync(resolve(__dirname, '../js/05-evals-observability.js'), 'utf8');

function kgExtractSource() {
  const m = SRC.match(/async function kgExtract\(\) \{[\s\S]*?\n\}/);
  expect(m).toBeTruthy();
  return m[0];
}

describe('r59 kgExtract surfaces failures', () => {
  it('checks the HTTP status and toasts on a non-ok response', () => {
    const fn = kgExtractSource();
    expect(fn).toMatch(/if\s*\(!r\.ok\)\s*\{\s*showToast\(/);
  });

  it('surfaces ok:false bodies with the server error text', () => {
    const fn = kgExtractSource();
    expect(fn).toMatch(/d\.ok !== true[\s\S]{0,90}showToast\(/);
  });

  it('catches network exceptions', () => {
    const fn = kgExtractSource();
    expect(fn).toMatch(/catch\s*\(ex\)\s*\{\s*showToast\(/);
  });

  it('re-renders the graph only on success', () => {
    const fn = kgExtractSource();
    // renderKnowledgeGraph() must appear exactly once, after the ok check,
    // and every error branch must return before it.
    expect(fn.match(/renderKnowledgeGraph\(\)/g).length).toBe(1);
    const renderIdx = fn.indexOf('renderKnowledgeGraph()');
    const okIdx = fn.indexOf('d.ok !== true');
    expect(renderIdx).toBeGreaterThan(okIdx);
  });
});
