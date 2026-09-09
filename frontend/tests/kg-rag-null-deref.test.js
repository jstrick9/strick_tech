/**
 * #076 — Knowledge Graph and RAG panes crashed when their backend was not ready.
 *
 * renderKnowledgeGraph() and renderRAG() fetched an endpoint and resolved it via
 *   .then(r=>r.ok?r.json():null).catch(()=>default)
 * On a non-2xx response `.then` resolves to **null** — and the trailing
 * `.catch` only fires on a *rejection*, not on a null return. The renderers then
 * dereferenced the null: `stats.entities` / `entities.entities` /
 * `pipelines.pipelines` threw "Cannot read properties of null (reading
 * 'entities'/'pipelines')". The Knowledge Graph pane collapsed to a single "?"
 * (the error boundary) and RAG never drew its list.
 *
 * The audit console_health.py reported both as uncaught exceptions +
 * unhandled rejections across every pane.
 *
 * Fix: default the non-2xx path to an empty object (`:{}`) instead of `null`,
 * so the renderers' existing `||0` / `||[]` guards take over and the pane draws
 * its legitimate empty state. Source-level regression tests.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const SRC = readFileSync(resolve(__dirname, '../js/05-evals-observability.js'), 'utf8');

describe('#076 knowledge-graph renderer does not deref a null response', () => {
  it('defaults a non-2xx /stats response to {} not null', () => {
    // The .then must not hand null to the consumer; the trailing .catch is not
    // a guard because a null resolve is not a rejection.
    expect(SRC).toMatch(
      /\/api\/knowledge-graph\/stats'\)\.then\(r=>r\.ok\?r\.json\(\)\.catch\(\(\)=>\{\}\):\{\}\)\.catch\(\(\)=>\(\{\}\)\)/
    );
  });

  it('defaults a non-2xx /entities response to {} not null', () => {
    expect(SRC).toMatch(
      /\/api\/knowledge-graph\/entities\?limit=20'\)\.then\(r=>r\.ok\?r\.json\(\)\.catch\(\(\)=>\{\}\):\{\}\)/
    );
  });

  it('defaults a non-2xx /rag/pipelines response to {} not null', () => {
    expect(SRC).toMatch(
      /\/api\/rag\/pipelines'\)\.then\(r=>r\.ok\?r\.json\(\)\.catch\(\(\)=>\{\}\):\{\}\)\.catch\(\(\)=>\(\{pipelines:\[\]\}\)\)/
    );
  });

  it('kgSearch does not reassign its const d (would itself throw)', () => {
    // The first fix attempt used `if(!d){d={};}` which is invalid on a const.
    // The fetch must set its own default instead. Search for the entities?q
    // fetch and require it to default the non-2xx path to {}.
    const m = SRC.match(/entities\?q=\$\{[^}]+\}&limit=20`\)\.then\(r=>r\.ok\?r\.json\(\):([^)]+)\)/);
    expect(m).not.toBeNull();
    expect(m[1]).toBe('{}');
    // No invalid const reassignment anywhere.
    expect(SRC).not.toMatch(/if\(!d\)\{d=\{\};\}/);
  });
});
