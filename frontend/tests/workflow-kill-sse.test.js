// r51 regression: the workflow SSE consumer understands a run stopped from
// the Control Tower. The executor now emits {"type":"killed","reason":...}
// at the node boundary where it stopped, and the final "done" event carries
// status:"killed" (previously only success/failed existed — a stopped run
// would have printed "Workflow complete" for work that never finished).

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = () =>
  readFileSync(join(root, 'js', '03-features-a.js'), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\/\/[^\n]*/g, '');

describe('r51 workflow stream handles Control Tower stops', () => {
  it('handles the mid-stream killed event, distinguishing budget from user kills', () => {
    const s = src();
    expect(s).toContain("data.type === 'killed'");
    expect(s).toContain("data.reason === 'budget'");
  });

  it('the final done event distinguishes a killed run from success/failed', () => {
    expect(src()).toContain("data.status === 'killed'");
  });
});
