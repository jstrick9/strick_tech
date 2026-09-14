// Frontend correctness: a failed deploy must show the server's reason, not a
// bare status code (#142).
//
// /api/deploy/{provider} answers 401 with a JSON body that says exactly what
// is missing — {"ok":false,"error":"GITHUB_TOKEN not set","code":"no_token"}
// — and some providers add a step-by-step setup guide. doDeploy used to
// `throw new Error('Server error ' + r.status)` on any non-200 BEFORE reading
// the body, so the user saw "Error: Server error 401" and never the reason or
// the fix. Same pattern in startTunnel.
import { describe, it, expect } from 'vitest';

const fs = require('fs');
const path = require('path');
const SOURCE = fs.readFileSync(path.join(__dirname, '..', 'js', '35-deploy.js'), 'utf8');

describe('deploy failures surface the server reason', () => {
  it('no longer throws a bare "Server error <code>" before reading the body', () => {
    expect(SOURCE).not.toContain('throw new Error(`Server error ${r.status}`)');
  });

  it('parses the body first, so non-200 responses keep their detail', () => {
    const deployFn = SOURCE.match(/async function doDeploy[\s\S]*?\n\}/)[0];
    expect(deployFn.indexOf('r.json().catch')).toBeGreaterThan(-1);
    expect(deployFn.indexOf('r.json().catch')).toBeLessThan(deployFn.indexOf('if (!r.ok)'));
    const tunnelFn = SOURCE.match(/async function startTunnel[\s\S]*?\n\}/)[0];
    expect(tunnelFn.indexOf('r.json().catch')).toBeLessThan(tunnelFn.indexOf('if (!r.ok)'));
  });

  it('renders the body error, setup steps, and alternative on failure', () => {
    const deployFail = SOURCE.match(/async function doDeploy[\s\S]*?\n\}/)[0];
    expect(deployFail).toContain('j.error');
    expect(deployFail).toContain('j.setup');
    expect(deployFail).toContain('j.alternative');
  });

  it('the tunnel failure path also shows the body reason', () => {
    const tunnel = SOURCE.match(/async function startTunnel[\s\S]*?\n\}/)[0];
    expect(tunnel).toContain('j.error');
    expect(tunnel).not.toContain('throw new Error');
  });
});
