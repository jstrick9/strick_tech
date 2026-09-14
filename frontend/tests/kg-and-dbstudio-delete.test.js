// Frontend correctness: created things must be removable (#144).
//
// Two create-without-delete asymmetries left junk permanent in the product:
// 1) Knowledge Graph entities could be added (POST /api/knowledge-graph/entities
//    upserts) but only wiped wholesale via "clear graph" — a mistyped or
//    hostile-named entity rendered in the pane forever.
// 2) DB Studio tables could be created in the Schema Designer but never
//    dropped — the SQL editor is read-only on purpose, so there was no path
//    at all short of deleting the DB file.
// Both panes now expose a confirmed delete; these tests pin the contract.
import { describe, it, expect } from 'vitest';

const fs = require('fs');
const path = require('path');
const KG = fs.readFileSync(path.join(__dirname, '..', 'js', '05-evals-observability.js'), 'utf8');
const DB = fs.readFileSync(path.join(__dirname, '..', 'js', '17-database-studio.js'), 'utf8');

describe('knowledge graph entities are deletable', () => {
  it('renders a delete affordance on every entity card', () => {
    const render = KG.match(/async function renderKnowledgeGraph[\s\S]*?\n\}/)[0];
    expect(render).toContain('kgDeleteEntity(');
    // the per-card button must be wired through the delegate, not onclick
    expect(render).toMatch(/data-act-click="kgDeleteEntity\(\$\{jsArg\(e\.id\)\}/);
  });

  it('kgDeleteEntity confirms, calls the DELETE endpoint, re-renders', () => {
    const fn = KG.match(/async function kgDeleteEntity[\s\S]*?\n\}/)[0];
    expect(fn).toContain("gmDanger('Delete entity'");
    expect(fn).toContain("`/api/knowledge-graph/entities/${encodeURIComponent(entityId)}`");
    expect(fn).toContain("{ method: 'DELETE' }");
    expect(fn).toContain('renderKnowledgeGraph()');
  });
});

describe('db studio tables are droppable', () => {
  it('table header offers a Drop action', () => {
    const load = DB.match(/async function dbLoadTable[\s\S]*?\n\}/)[0];
    expect(load).toContain('dbDropTable(');
  });

  it('dbDropTable confirms, calls the DELETE endpoint, refreshes the list', () => {
    const fn = DB.match(/async function dbDropTable[\s\S]*?\n\}/)[0];
    expect(fn).toContain("gmDanger('Drop table'");
    expect(fn).toContain("`/api/db/sqlite/table/${encodeURIComponent(table)}`");
    expect(fn).toContain("{ method: 'DELETE' }");
    expect(fn).toContain("dbSetTab('sqlite')");
  });
});
