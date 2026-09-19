// r56 regression: the Loops pause/resume toggle decides by re-fetched state.
//
// Deep-diving the autonomy cluster (Loops/Goals/Supervisor/HitL) verified the
// full loop lifecycle live: create -> pause -> resume (same button, state
// re-fetched server-side) -> run-now -> history -> stop. One cleanup: an
// older render carried a data-loop-id attribute on each row, and pauseLoop
// kept a leftover querySelector('[data-loop-id="..."]') that always returned
// null — dead code implying a DOM contract the pane no longer has (it misled
// a live probe into "proving" resume was broken). This locks the real
// contract: the toggle is state-driven, and no element hook is assumed.

const fs = require('fs');
const path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', 'js', '40-loops.js'), 'utf8');

describe('loops pause/resume toggle (r56)', () => {
  test('pauseLoop picks its endpoint from re-fetched state, not the DOM', () => {
    expect(src).toMatch(/const isPaused = l && l\.status === 'paused';/);
    expect(src).toMatch(/const endpoint = isPaused \? 'resume' : 'pause';/);
  });

  test('no dead query for a data-loop-id attribute nothing renders', () => {
    expect(src).not.toMatch(/querySelector\(\`\[data-loop-id=/);
  });

  test('the row toggle renders both verbs from status (paused rows can resume)', () => {
    expect(src).toMatch(/l\.status==='paused'\?'▶ Resume':'⏸ Pause'/);
  });

  test('stopLoop confirms with an explicit Stop label', () => {
    expect(src).toMatch(/gmDanger\('Stop loop', `Stop loop "[^"]+"\? This cannot be undone\.\`, 'Stop'\)/);
  });
});
