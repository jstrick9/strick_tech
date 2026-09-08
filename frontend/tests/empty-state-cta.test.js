// UX consistency: the shared emptyState() factory renders an empty state
// alongside a next-action button. Panes that previously showed a bare
// "No X yet." line with no way forward now route through it with a real action.
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

function escHtml(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c])); }

// Evaluate the real global emptyState from app-core source.
function loadEmptyState() {
  const src = fs.readFileSync(path.join(__dirname, '..', 'js', '01-app-core.js'), 'utf8');
  const start = src.indexOf('function emptyState(');
  const end = src.indexOf('\n}', start) + 2;
  const fnSrc = src.slice(start, end);
  const f = new Function('escHtml', fnSrc + '; return emptyState;');
  return f(escHtml);
}

describe('shared emptyState factory offers a next action', () => {
  const emptyState = loadEmptyState();

  it('renders inside the shared .data-state state-empty component', () => {
    const html = emptyState({ icon:'🚀', title:'No deploys yet', body:'Run one to see it here.',
      actions:[{ label:'Deploy now', action:'renderDeploy()', primary:true }] });
    expect(html).toContain('data-state state-empty');
    expect(html).toContain('Deploy now');
    expect(html).toContain("data-act-click=\"renderDeploy()\"");
    expect(html).toContain('btn-primary');
  });

  it('routes the copy through the shared data-state markup', () => {
    const html = emptyState({ icon:'🚀', title:'No deploys yet', body:'Run one to see it here.',
      actions:[] });
    expect(html).toContain('data-state-title');
    expect(html).toContain('data-state-msg');
  });

  it('escapes title/body but keeps the action expression intact (quotes survive)', () => {
    const html = emptyState({ icon:'x', title:'<img onerror=1>', body:'a "quoted" body',
      actions:[{ label:'Go', action:"icmwsTab('describe')" }] });
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img');
    expect(html).toContain("icmwsTab('describe')");
  });

  it('renders multiple follow-up actions (generate + upload)', () => {
    const html = emptyState({ icon:'🖼️', title:'No images yet', body:'Generate or upload.',
      actions:[{ label:'Generate', action:'renderImageGen()', primary:true },
               { label:'Upload', action:'igUpload()' }] });
    expect(html).toContain('Generate');
    expect(html).toContain('Upload');
    expect(html).toContain('data-state-actions'); // row makes multiple CTAs flow
  });
});

describe('actionless fatal-empty-states are routed through the factory (pattern guard)', () => {
  const deploy = fs.readFileSync(path.join(__dirname, '..', 'js', '35-deploy.js'), 'utf8');
  const gallery = fs.readFileSync(path.join(__dirname, '..', 'js', '15-image-generation.js'), 'utf8');
  it('deploy history empty state calls emptyState with an action', () => {
    // The old action-less render must be gone.
    expect(deploy).not.toContain('No deploys yet.</div>');
    // And the empty state now goes through the factory with an action.
    const seg = deploy.slice(deploy.indexOf('loadDeployHistory'), deploy.indexOf('Deploy now') + 40);
    expect(seg).toContain('emptyState(');
    expect(seg).toContain("action:'renderDeploy()'");
  });
  it('image gallery empty state calls emptyState', () => {
    expect(gallery).toContain('emptyState(');
  });
});
