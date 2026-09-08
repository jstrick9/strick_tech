/**
 * Kanban edit/create modal — Escape-close must not make it single-use (#065).
 *
 * The global master Escape handler in 01-app-core.js dismisses bespoke
 * `*-modal-overlay` scrims by calling m.remove() directly; it cannot call the
 * owning module's close function. In the kanban module the "is open" state is a
 * JS flag (`kanbanModalOpen`) that is only ever reset by kanbanCloseModal(), so
 * after an Escape close the flag stayed true and kanbanOpenEditModal() /
 * kanbanOpenCreateModal() silently refused to open the modal ever again (a
 * single-use dialog).
 *
 * The fix: both open functions reconcile the flag against the actual DOM before
 * opening — if the overlay is no longer mounted, they clear the flag and open.
 * This guards the source contract (not a behavioural DOM test, which is covered
 * live) so the reconcile line can never be silently dropped again.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const SRC = readFileSync(resolve(__dirname, '../js/28-kanban.js'), 'utf8');

function fn(name) {
  const i = SRC.indexOf('function ' + name);
  if (i < 0) return '';
  const j = SRC.indexOf('\n}', i);
  return SRC.slice(i, j < 0 ? SRC.length : j + 2);
}

describe('#065 kanban modal reopens after an Escape-force-removed overlay', () => {
  it('every modal-open entry point reconciles the open flag against the DOM', () => {
    const create = fn('kanbanOpenCreateModal');
    const edit = fn('kanbanOpenEditModal');
    // Both must clear a stale flag when the overlay is no longer in the DOM.
    [create, edit].forEach((body, idx) => {
      expect(body.length, 'open function ' + idx + ' not found').toBeGreaterThan(10);
      expect(body).toMatch(/kanbanModalOpen\s*&&\s*!document\.getElementById\('kanban-modal-overlay'\)/);
      expect(body).toMatch(/kanbanModalOpen = false/);
      // The reconcile must run BEFORE the early-return guard.
      const reconcileAt = body.indexOf("kanbanModalOpen && !document");
      const guardAt = body.indexOf("if (kanbanModalOpen) return;");
      expect(reconcileAt, 'reconcile must precede the guard').toBeGreaterThan(-1);
      expect(guardAt).toBeGreaterThan(reconcileAt);
    });
  });

  it('kanbanCloseModal still resets the flag (the normal close path)', () => {
    const close = fn('kanbanCloseModal');
    expect(close).toMatch(/kanbanModalOpen = false/);
  });
});
