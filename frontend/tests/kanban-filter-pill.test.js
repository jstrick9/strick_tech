/**
 * Kanban filter pills must reflect the active filter.
 *
 * Found live (r42 pane journey): clicking "🔴 High" filtered the board, but
 * the highlighted pill never moved — the .active class was only computed in
 * renderKanban's static template, and kanbanSetFilter re-rendered only the
 * board (#kanban-board), never the topbar. The user had no indication which
 * filter was on, and "All" stayed lit even with a filter active.
 *
 * The fix: each filter button carries data-priority (all|high|medium|low),
 * and kanbanSetFilter toggles .active in place to match kanbanActiveFilter.
 * This guards the source contract so the pill-sync can't be silently dropped.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const SRC = readFileSync(resolve(__dirname, '../js/28-kanban.js'), 'utf8');
const CSS = ['styles-unified.css', 'styles-system.css', 'styles-redesign.css']
  .map(f => { try { return readFileSync(resolve(__dirname, '..', f), 'utf8'); } catch (e) { return ''; } })
  .join('\n');

function fn(name) {
  const i = SRC.indexOf('function ' + name);
  if (i < 0) return '';
  const j = SRC.indexOf('\n}', i);
  return SRC.slice(i, j < 0 ? SRC.length : j + 2);
}

describe('kanban filter pills track the active filter', () => {
  it('every filter button carries a data-priority attribute', () => {
    const buttons = SRC.match(/<button[^>]*kanban-filter-btn[^>]*>/g) || [];
    expect(buttons.length).toBe(4);
    const priorities = buttons.map(b => (b.match(/data-priority="([^"]*)"/) || [])[1]);
    expect(priorities).toEqual(['all', 'high', 'medium', 'low']);
  });

  it('kanbanSetFilter toggles .active on the pills to match the new filter', () => {
    const body = fn('kanbanSetFilter');
    expect(body.length, 'kanbanSetFilter not found').toBeGreaterThan(10);
    // Must update the pills, not just the board.
    expect(body).toMatch(/querySelectorAll\('\.kanban-filter-btn'\)/);
    expect(body).toMatch(/classList\.toggle\('active'/);
    // The toggle must compare the pill's data-priority against the active
    // filter (mapping "all" back to null, the unfiltered value).
    expect(body).toMatch(/dataset\.priority/);
    expect(body).toMatch(/kanbanActiveFilter/);
    // And it must still re-render the cards.
    expect(body).toMatch(/kanbanRenderBoard\(\)/);
  });

  it('the active pill has a visible style (the toggle must change something)', () => {
    expect(CSS).toMatch(/\.kanban-filter-btn\.active\s*\{/);
  });
});
