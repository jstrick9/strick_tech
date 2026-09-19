// r56 regression: a confirm button must name the action it performs.
//
// gmDanger(title, body, confirmLabel='Delete') defaults the button to
// "Delete". Found live while deep-diving the integration cluster: toggling
// an MCP Gateway server asked "Disable Server?" — confirmed by a button
// that read "Delete". The sweep found ten call sites across seven files
// where the verb lied: Start Tauri Build (worst — a build confirmed by
// "Delete"), Disable/Enable Server, Cancel Task, Clear Canvas, Clear All
// Suggestions, Uninstall pack, Overwrite Note, Drop table, and two
// run-destructive-SQL confirms. Every site now passes an explicit
// confirmLabel; live-verified on the gateway toggle ("Disable") and the
// Tauri build ("Start Build", cancelled — no build started).

const fs = require('fs');
const path = require('path');
const read = (f) => fs.readFileSync(path.join(__dirname, '..', 'js', f), 'utf8');

describe('danger confirms name their action (r56)', () => {
  test.each([
    ['03-features-a.js', /'Start Tauri Build',[\s\S]{0,120}'Start Build'\)/],
    ['03-features-a.js', /'Clear Canvas', `Remove all [\s\S]{0,80}edges\?`, 'Clear'\)/],
    ['07-quality-tools.js', /'Clear All Suggestions', 'This cannot be undone\.', 'Clear'\)/],
    ['08-replay-collab.js', /gmDanger\(`Uninstall "\$\{packName\}"\?`, `Remove this pack[^`]*`, 'Uninstall'\)/],
    ['17-database-studio.js', /gmDanger\('Drop table', `Drop table "\$\{table\}" and ALL its rows\? This cannot be undone\.`, 'Drop'\)/],
    ['17-database-studio.js', /'Run destructive SQL\?',[\s\S]{0,200}'Run Anyway'/],
    ['17-database-studio.js', /Run AI-generated SQL[\s\S]{0,400}'Run Anyway'/],
    ['20-obsidian.js', /'Overwrite Note',[\s\S]{0,140}'Overwrite'\)/],
    ['50-mcp-gateway.js', /gmDanger\(`\$\{disable\?'Disable':'Enable'\} Server`,[\s\S]{0,240}disable \? 'Disable' : 'Enable'\)/],
    ['52-a2a.js', /'Cancel Task', `Cancel A2A task \$\{taskId\.slice\(0,20\)\}\?`, 'Cancel'\)/],
    ['53-agent-monitor.js', /gmDanger\('Kill Agent',[\s\S]{0,240}'Kill'\)/],
  ])('%s carries an explicit confirm label', (file, re) => {
    expect(read(file).replace(/^\s*\/\/.*$/gm, '')).toMatch(re);
  });

  test('no gmDanger call left where the verb disagrees with a "Delete" button', () => {
    const files = ['01-app-core.js','03-features-a.js','07-quality-tools.js','08-replay-collab.js','17-database-studio.js','20-obsidian.js','50-mcp-gateway.js','52-a2a.js','53-agent-monitor.js'];
    const bad = [];
    for (const f of files) {
      const src = read(f).replace(/^\s*\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');
      const calls = src.match(/gmDanger\((?:[^()]|\([^()]*\))*\)/g) || [];
      for (const call of calls) {
        const head = call.slice(0, 90);
        const nonDeleteVerb = /^(Start|Disable|Enable|Cancel|Overwrite|Run|Drop|Uninstall|Clear)/.test(head.replace(/gmDanger\(\s*['"`]/, '')) || /'\$\{disable\?'(Disable|Enable)'/.test(head);
        if (!nonDeleteVerb) continue;
        const hasLabel = /'(.*)'`?\s*\)$/.test(call.trim()) || /'(Start Build|Disable|Enable|Cancel|Clear|Uninstall|Overwrite|Drop|Run Anyway|Restore)'\s*\)/.test(call);
        if (!hasLabel) bad.push(f + ': ' + head.replace(/\s+/g, ' ').slice(0, 70));
      }
    }
    expect(bad).toEqual([]);
  });
});
