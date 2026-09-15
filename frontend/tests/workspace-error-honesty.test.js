// Frontend failure honesty: the workspaces module discarded the response body
// on non-200 ("Import failed: server error 400"), hiding the server's reason —
// exactly the #142 deploy-error-honesty class. The server says WHY an action
// was refused ('GITHUB_TOKEN not set', 'Cannot delete active workspace',
// 'Invalid workspace id', 'Workspace not found'); the toast must show it.
//
// The backend half (500 + zombie workspace on a no-token import) is guarded
// in tests/unit/test_225_workspace_import_honesty.py.
import { describe, it, expect } from 'vitest';

const fs = require('fs');
const path = require('path');
const SOURCE = fs.readFileSync(path.join(__dirname, '..', 'js', '30-workspaces.js'), 'utf8');

// action label -> the async function that performs it
const ACTIONS = {
  Switch: 'activateWorkspace',
  Create: 'createNewWorkspace',
  Delete: 'deleteWorkspace',
  Import: 'importFromGitHub',
};

function fnSource(name) {
  const start = SOURCE.indexOf(`async function ${name}`);
  expect(start, `function ${name} not found`).toBeGreaterThan(-1);
  const next = SOURCE.indexOf('async function', start + 1);
  return SOURCE.slice(start, next === -1 ? undefined : next);
}

describe('workspace action failures surface the server reason', () => {
  for (const [action, fn] of Object.entries(ACTIONS)) {
    it(`${action} failure reads the body before falling back to the status`, () => {
      const src = fnSource(fn);
      const parse = `try { d=(await r.json()).error||''; } catch(e) {}`;
      const toast = `toast('${action} failed: ' + (d || ('server error ' + r.status)), 'err');`;
      expect(src).toContain(parse);
      expect(src).toContain(toast);
      // parse happens before the toast uses d
      expect(src.indexOf(parse)).toBeLessThan(src.indexOf(toast));
    });
  }

  it('no action toast leads with a bare status code anymore', () => {
    expect(SOURCE).not.toMatch(/toast\('(Switch|Create|Delete|Import) failed: server error ' \+ r\.status/);
  });
});
