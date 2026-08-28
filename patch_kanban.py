"""Fix Kanban drag-and-drop: take the element via $this, not currentTarget."""
from pathlib import Path

P = Path('frontend/js/28-kanban.js')
s = P.read_text(encoding='utf-8')
n = 0

# ── handlers: accept the element as an argument ──────────────────────────────
OLD_OVER = """function kanbanOnDragOver(event) {
  // REQUIRED: preventDefault allows drop
  event.preventDefault();
  event.dataTransfer.dropEffect = 'move';
  
  // Add visual highlight to drop zone
  const dropZone = event.currentTarget;
  dropZone.classList.add('kanban-column-drag-over');
}"""
NEW_OVER = """function kanbanOnDragOver(event, dropZone) {
  // REQUIRED: preventDefault allows drop
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';

  // `dropZone` is passed in as $this by the delegated dispatcher. It used to
  // read event.currentTarget, which is NEVER the column here: 00-delegate.js
  // binds one listener per event type on `document` in the capture phase, so
  // currentTarget is `document` during dispatch and undefined afterwards.
  // That threw "Cannot read properties of undefined (reading 'add')" on every
  // single dragover.
  if (dropZone && dropZone.classList) {
    dropZone.classList.add('kanban-column-drag-over');
  }
}"""
assert s.count(OLD_OVER) == 1
s = s.replace(OLD_OVER, NEW_OVER); n += 1

OLD_LEAVE = """function kanbanOnDragLeave(event) {
  // Remove highlight when leaving drop zone
  const dropZone = event.currentTarget;
  if (!dropZone.contains(event.relatedTarget)) {
    dropZone.classList.remove('kanban-column-drag-over');
  }
}"""
NEW_LEAVE = """function kanbanOnDragLeave(event, dropZone) {
  // Same fix as dragover: the element arrives as $this.
  if (!dropZone || !dropZone.classList) return;
  // relatedTarget is null when leaving the window entirely; treat that as a
  // real leave rather than throwing inside contains().
  const going = event && event.relatedTarget;
  if (!going || !dropZone.contains(going)) {
    dropZone.classList.remove('kanban-column-drag-over');
  }
}"""
assert s.count(OLD_LEAVE) == 1
s = s.replace(OLD_LEAVE, NEW_LEAVE); n += 1

OLD_DROP = """async function kanbanOnDrop(event, targetColumn) {
  event.preventDefault();
  
  // Remove highlight
  const dropZone = event.currentTarget;
  dropZone.classList.remove('kanban-column-drag-over');
  """
NEW_DROP = """async function kanbanOnDrop(event, targetColumn, dropZone) {
  event.preventDefault();

  // THE BUG THAT BROKE DRAG AND DROP ENTIRELY. This read
  // event.currentTarget, and because the handler is `async` the event has
  // finished dispatching by the time it runs -- so currentTarget was
  // `undefined` and `.classList.remove` threw BEFORE the task id was read.
  // The card snapped back, no request was sent, and nothing surfaced in the
  // UI. The element now arrives as $this.
  if (dropZone && dropZone.classList) {
    dropZone.classList.remove('kanban-column-drag-over');
  }
  """
assert s.count(OLD_DROP) == 1
s = s.replace(OLD_DROP, NEW_DROP); n += 1

# ── markup: pass $this ───────────────────────────────────────────────────────
PAIRS = [
    ('data-act-dragover="kanbanOnDragOver($event)"',
     'data-act-dragover="kanbanOnDragOver($event,$this)"'),
    ('data-act-drop="kanbanOnDrop($event,${jsArg(col.id)})"',
     'data-act-drop="kanbanOnDrop($event,${jsArg(col.id)},$this)"'),
    ('data-act-dragleave="kanbanOnDragLeave($event)"',
     'data-act-dragleave="kanbanOnDragLeave($event,$this)"'),
    ('data-act-dragstart="kanbanOnDragStart($event,${jsArg(taskId)})"',
     'data-act-dragstart="kanbanOnDragStart($event,${jsArg(taskId)},$this)"'),
    ('data-act-dragend="kanbanOnDragEnd($event)"',
     'data-act-dragend="kanbanOnDragEnd($event,$this)"'),
]
for old, new in PAIRS:
    assert s.count(old) == 1, f'markup not found: {old}'
    s = s.replace(old, new); n += 1

# ── the two handlers that take the element but did not declare it ────────────
OLD_START = "function kanbanOnDragStart(event, taskId) {"
NEW_START = "function kanbanOnDragStart(event, taskId, card) {"
assert s.count(OLD_START) == 1
s = s.replace(OLD_START, NEW_START); n += 1

OLD_END = "function kanbanOnDragEnd(event) {"
NEW_END = "function kanbanOnDragEnd(event, card) {"
assert s.count(OLD_END) == 1
s = s.replace(OLD_END, NEW_END); n += 1

P.write_text(s, encoding='utf-8')
print('applied', n, 'edits')
assert 'currentTarget' not in P.read_text(encoding='utf-8'), 'currentTarget still present'
print('no currentTarget remains')
