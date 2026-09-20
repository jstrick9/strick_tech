/**
 * r58 — RAG pipeline deletion failures were silent.
 *
 * ragDeletePipeline() fired the DELETE and immediately re-rendered:
 * no status check, no error path, no feedback. A failed delete (network
 * error, 4xx/5xx) looked exactly like a successful one — the user only
 * found out when the "deleted" pipeline was still in the list. Its two
 * siblings in the same file (ragDeleteDoc) and the Plugin Hub's
 * hubUninstall both surface failures; the endpoint even returns a
 * `deleted` flag ("removed it" vs "nothing to remove") that this handler
 * discarded entirely.
 *
 * Fix: check the response, toast on every failure mode (HTTP error, ok:false,
 * network exception), distinguish already-gone from deleted, and re-render
 * only on success. Source-level regression tests.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const SRC = readFileSync(resolve(__dirname, '../js/05-evals-observability.js'), 'utf8');

function ragDeletePipelineSource() {
  const m = SRC.match(/async function ragDeletePipeline\(pipelineId\) \{[\s\S]*?\n\}/);
  expect(m).toBeTruthy();
  return m[0];
}

describe('r58 ragDeletePipeline surfaces failures', () => {
  it('checks the HTTP status and toasts on a non-ok response', () => {
    const fn = ragDeletePipelineSource();
    expect(fn).toMatch(/if\s*\(!r\.ok\)\s*\{\s*showToast\(/);
  });

  it('surfaces ok:false bodies from the endpoint', () => {
    const fn = ragDeletePipelineSource();
    expect(fn).toMatch(/j\.ok === false[\s\S]{0,80}showToast\(/);
  });

  it('distinguishes "deleted" from "already gone" via the endpoint flag', () => {
    const fn = ragDeletePipelineSource();
    expect(fn).toMatch(/j\.deleted[\s\S]{0,120}already gone/);
  });

  it('catches network exceptions instead of rejecting silently', () => {
    const fn = ragDeletePipelineSource();
    expect(fn).toMatch(/catch\s*\(ex\)\s*\{\s*showToast\(/);
  });

  it('re-renders only after a successful delete (not on the error paths)', () => {
    const fn = ragDeletePipelineSource();
    // every error branch returns before renderRAG(); the only renderRAG()
    // call must sit after the try/catch, i.e. on the success path.
    const renderIdx = fn.indexOf('renderRAG()');
    const catchIdx = fn.lastIndexOf('catch');
    expect(renderIdx).toBeGreaterThan(-1);
    expect(catchIdx).toBeGreaterThan(-1);
    expect(renderIdx).toBeGreaterThan(catchIdx);
    expect(fn.match(/renderRAG\(\)/g).length).toBe(1);
  });
});
