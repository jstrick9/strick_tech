// Frontend correctness: the fine-tune pane must not fabricate training data.
//
// finetuneStartJob used to render a full telemetry panel — Loss 0.384, Step
// 140/400, ETA 1m 45s and a five-epoch loss chart — the moment it was called,
// before any job existed, and to claim "initialized on local Metal
// accelerator" on any hardware. When the backend refused the job (501 on
// machines without a local training backend, which is most of them) the fake
// run stayed on screen with no error. The dataset list also read `d.id` /
// `d.rows` although the API returns `dataset_id` / `row_count`, so every
// Train button passed null and every dataset showed "0 training examples".
import { describe, it, expect, beforeEach, vi } from 'vitest';

const fs = require('fs');
const path = require('path');
const SOURCE = fs.readFileSync(path.join(__dirname, '..', 'js', '03-features-a.js'), 'utf8');

function escHtml(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }

// Full-line // comments only (the fixes document themselves in comments that
// quote the old fabricated literals, so assertions must run on code, not prose).
const CODE_ONLY = SOURCE.split('\n').filter(l => !/^\s*\/\//.test(l)).join('\n');

function extractFn(name) {
  const re = new RegExp(`window\\.${name} = (async function[\\s\\S]*?\\n};)`);
  const m = SOURCE.match(re);
  if (!m) throw new Error(`${name} not found in 03-features-a.js`);
  return m[1];
}

function makeDom() {
  const badge = { textContent: '', style: {} };
  const box = { innerHTML: '' };
  const document = {
    getElementById: (id) => ({ 'finetune-status-badge': badge, 'finetune-progress-box': box }[id] || null),
  };
  return { badge, box, document };
}

function loadStartJob(fetch, toast) {
  const { badge, box, document } = makeDom();
  const window = {};
  const code = `window.finetuneStartJob = ${extractFn('finetuneStartJob')}`;
  new Function('window', 'document', 'fetch', 'toast', 'escHtml', code)(
    window, document, fetch, toast, escHtml,
  );
  return { window, badge, box };
}

describe('fine-tune pane does not fabricate training data', () => {
  let toast;
  beforeEach(() => { toast = vi.fn(); });

  it('refuses a null dataset id instead of posting it', async () => {
    const fetch = vi.fn();
    const { window } = loadStartJob(fetch, toast);
    await window.finetuneStartJob(null);
    expect(fetch).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith(expect.stringContaining('No dataset selected'), 'warn', 3000);
  });

  it('shows the real reason when the backend refuses the job (501)', async () => {
    const fetch = vi.fn(async () => ({ ok: false, status: 501, json: async () => ({ detail: 'no training backend installed' }) }));
    const { window, badge, box } = loadStartJob(fetch, toast);
    await window.finetuneStartJob('ds_real');
    expect(badge.textContent).toBe('NOT TRAINING');
    expect(box.innerHTML).toContain('not started');
    expect(box.innerHTML).toContain('no training backend installed');
    expect(box.innerHTML).not.toMatch(/0\.384|140 \/ 400|1m 45s/);
  });

  it('registers a job and names it — without inventing loss metrics', async () => {
    const fetch = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ ok: true, job_id: 'job_7', dataset_id: 'ds_real' }) }));
    const { window, badge, box } = loadStartJob(fetch, toast);
    await window.finetuneStartJob('ds_real');
    expect(badge.textContent).toBe('TRAINING ACTIVE');
    expect(box.innerHTML).toContain('job_7');
    expect(box.innerHTML).not.toMatch(/Loss:|Step:|ETA:/);
  });

  it('reports network errors instead of leaving a fake run on screen', async () => {
    const fetch = vi.fn(async () => { throw new Error('boom'); });
    const { window, badge, box } = loadStartJob(fetch, toast);
    await window.finetuneStartJob('ds_real');
    expect(badge.textContent).toBe('NOT TRAINING');
    expect(box.innerHTML).toContain('Network error');
  });
});

describe('fine-tune dataset list uses the API contract', () => {
  it('renders dataset_id (not the non-existent .id) into train handlers', () => {
    expect(SOURCE).toContain('finetuneStartJob(${jsArg(d.dataset_id');
    expect(SOURCE).not.toContain('finetuneStartJob(${jsArg(d.id)}');
  });

  it('shows row_count, which the API actually returns', () => {
    expect(SOURCE).toMatch(/d\.row_count/);
    expect(SOURCE).not.toMatch(/Number\(d\.rows \|\| 0\)/);
  });

  it('reads the create response from j.dataset, not the top level', () => {
    const create = SOURCE.match(/window\.finetuneCreateChatDataset = [\s\S]*?\n};/)[0];
    expect(create).toContain('j.dataset');
    expect(create).not.toContain("j.dataset_id + ' (' + j.rows");
  });
});

describe('IVREN converter is real, not theater', () => {
  it('calls the hierarchy and datasets APIs instead of a setTimeout toast', () => {
    const conv = SOURCE.match(/window\.finetuneConvertIVREN = [\s\S]*?\n};/)[0]
      .split('\n').filter(l => !/^\s*\/\//.test(l)).join('\n');
    expect(conv).toContain("/api/hierarchy/projects");
    expect(conv).toContain("/api/finetune/datasets/create");
    expect(conv).not.toContain('setTimeout');
    expect(conv).not.toContain('84 instruction');
  });

  it('no hardcoded telemetry literals remain in the pane source', () => {
    expect(CODE_ONLY).not.toContain('140 / 400');
    expect(CODE_ONLY).not.toContain('1m 45s');
    expect(CODE_ONLY).not.toContain('Epoch 5 (0.384)');
    expect(CODE_ONLY).not.toContain('local Metal accelerator');
  });
});
