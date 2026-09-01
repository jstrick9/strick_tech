// Frontend correctness: the swarm DAG "Judge Consensus Hub" confidence must be
// the WINNER's score, not runs[0]'s.
//
// renderSwarmDAG used `Math.round((runs[0]?.score || 0.96)*100)% confidence`.
// The backend returns `runs` in agent order (asyncio.gather preserves order) —
// the winner can be any element — and `score` is only attached in judge/merge
// strategies. So the card either showed another agent's confidence, or a
// fabricated "96% confidence" whenever the first run had no score (fan-out) or
// there were no runs.
import { describe, it, expect, beforeEach } from 'vitest';

function escHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

function loadDag() {
  // 26-swarm.js defines window.renderSwarmDAG and relies on window.S + escHtml.
  globalThis.window = globalThis.window || {};
  globalThis.window.S = { agents: [] };
  globalThis.window.escHtml = escHtml;
  globalThis.window.openInspectionDrawer = () => {};
  const host = Object.assign(document.createElement('div'), { id: 'swarm-dag-host' });
  document.body.appendChild(host);
  // setup.js stubs getElementById to return null for most ids; make it resolve
  // real elements so renderSwarmDAG can find its host.
  const original = document.getElementById;
  document.getElementById = (id) => (id === 'swarm-dag-host' ? host : original(id));
  const code = require('fs').readFileSync(require('path').join(__dirname, '..', 'js', '26-swarm.js'), 'utf8');
  // Evaluate in a fresh scope so its window.* exports land on globalThis.window.
  new Function('window', 'document', 'console', code)(globalThis.window, globalThis.document, console);
  return host;
}

describe('Swarm DAG winner confidence', () => {
  let host;

  function render(runs, winner, { isRunning = false, activeAgents = [] } = {}) {
    const el = document.getElementById('swarm-dag-host');
    window.renderSwarmDAG(runs, winner, isRunning, activeAgents, 'test prompt');
    return el.textContent;
  }

  beforeEach(() => {
    document.body.innerHTML = '';
    host = loadDag();
  });

  it('shows the winning run score, not runs[0].score', () => {
    // Winner is "builder", which is runs[2], and its score differs from runs[0].
    const runs = [
      { agent: 'orchestrator', score: 0.20, tokens: 10, latency_ms: 1, output: 'a' },
      { agent: 'brain',        score: 0.30, tokens: 10, latency_ms: 1, output: 'b' },
      { agent: 'builder',      score: 0.87, tokens: 10, latency_ms: 1, output: 'c' },
    ];
    const text = render(runs, 'builder');
    // Should reflect the winner's 87%, never the 20% of runs[0].
    expect(text).toContain('87% confidence');
    expect(text).not.toContain('20% confidence');
  });

  it('does not fabricate 96% when runs[0] has no score (fan-out)', () => {
    const runs = [
      { agent: 'orchestrator', tokens: 10, latency_ms: 1, output: 'a' },
      { agent: 'builder',      tokens: 10, latency_ms: 1, output: 'b' },
    ];
    const text = render(runs, 'builder');
    expect(text).not.toContain('% confidence');
    expect(text).not.toContain('96%');
  });

  it('does not fabricate 96% when there are no runs', () => {
    const text = render([], 'builder');
    expect(text).not.toContain('% confidence');
    expect(text).not.toContain('96%');
  });

  it('shows confidence with no trailing double period', () => {
    const runs = [{ agent: 'builder', score: 0.5, tokens: 1, latency_ms: 1, output: 'x' }];
    const text = render(runs, 'builder');
    // Should render "50% confidence)." — not "50% confidence).."
    expect(text).toContain('50% confidence).');
  });
});
