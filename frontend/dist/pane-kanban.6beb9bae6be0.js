
;/* 28-kanban.js */
'use strict';
const KANBAN_COLUMNS = [
{ id: 'todo', label: 'To Do', icon: '📝', color: '#3b82f6' },
{ id: 'doing', label: 'In Progress', icon: '⚡', color: '#f59e0b' },
{ id: 'blocked', label: 'Blocked', icon: '⛔', color: '#ef4444' },
{ id: 'done', label: 'Done', icon: '✅', color: '#22c55e' }
];
const KANBAN_PRIORITIES = {
low: { label: 'Low', color: '#22c55e', bg: 'rgba(34,197,94,0.15)' },
medium: { label: 'Medium', color: '#f59e0b', bg: 'rgba(245,158,11,0.15)' },
high: { label: 'High', color: '#f97316', bg: 'rgba(249,115,22,0.15)' }
};
const KANBAN_AGENTS = {
builder: { label: 'Builder', icon: '⚡' },
brain: { label: 'Brain', icon: '🧠' },
researcher: { label: 'Researcher', icon: '🔬' },
orchestrator: { label: 'Orchestrator', icon: '🌀' }
};
let kanbanTasks = [];
let kanbanLoadError = null;
let kanbanDraggedTaskId = null;
let kanbanActiveFilter = null;
let kanbanModalOpen = false;
async function renderKanban() {
const pane = document.getElementById('pane-kanban');
if (!pane) return;
pane.innerHTML = `
    <div class="kanban-root">
      <div class="kanban-topbar">
        <div class="kanban-topbar-left">
          <h1 class="kanban-title">📋 Tasks</h1>
          <span class="kanban-count" id="kanban-task-count">Loading...</span>
        </div>
        <div class="kanban-topbar-right">
          <div class="kanban-filter-group">
            <button type="button" class="kanban-filter-btn ${!kanbanActiveFilter ? 'active' : ''}" data-act-click="kanbanSetFilter(null)">All</button>
            <button type="button" class="kanban-filter-btn ${kanbanActiveFilter === 'high' ? 'active' : ''}" data-act-click="kanbanSetFilter('high')">🔴 High</button>
            <button type="button" class="kanban-filter-btn ${kanbanActiveFilter === 'medium' ? 'active' : ''}" data-act-click="kanbanSetFilter('medium')">🟡 Medium</button>
            <button type="button" class="kanban-filter-btn ${kanbanActiveFilter === 'low' ? 'active' : ''}" data-act-click="kanbanSetFilter('low')">🟢 Low</button>
          </div>
          <button type="button" class="kanban-add-btn" data-act-click="kanbanOpenCreateModal()">
            ＋ New Task
          </button>
        </div>
      </div>
      <div class="kanban-board" id="kanban-board">
        <div class="kanban-loading">Loading tasks...</div>
      </div>
    </div>
    <div id="kanban-modal-root"></div>
  `;
await kanbanFetchTasks();
kanbanRenderBoard();
}
async function kanbanFetchTasks() {
try {
const response = await fetch('/api/kanban');
if (response.ok) {
const data = await response.json();
kanbanTasks = [];
for (const [status, tasks] of Object.entries(data)) {
if (Array.isArray(tasks)) {
tasks.forEach(task => {
kanbanTasks.push({ ...task, status: status });
});
}
}
kanbanLoadError = null;
} else {
throw new Error(`HTTP ${response.status}`);
}
} catch (e) {
kanbanTasks = [];
kanbanLoadError = e && e.message ? e.message : String(e);
}
}
function kanbanRenderBoard() {
const board = document.getElementById('kanban-board');
const countEl = document.getElementById('kanban-task-count');
if (!board) return;
let filteredTasks = kanbanTasks;
if (kanbanActiveFilter) {
filteredTasks = kanbanTasks.filter(t => t.priority === kanbanActiveFilter);
}
if (countEl) {
countEl.textContent = kanbanLoadError
? 'unavailable'
: `${filteredTasks.length} task${filteredTasks.length !== 1 ? 's' : ''}`;
}
if (kanbanLoadError) {
board.innerHTML = `
      <div class="empty-state" role="alert" style="grid-column:1/-1">
        <div class="empty-state__icon">⚠️</div>
        <div class="empty-state__title">Couldn't load your tasks</div>
        <div class="empty-state__body">Your tasks are safe — this is a
          connection problem, not lost work. (${escHtml(kanbanLoadError)})</div>
        <button type="button" class="btn btn-primary btn-sm"
                data-act-click="renderKanban()">↻ Try again</button>
      </div>`;
return;
}
const boardIsEmpty = filteredTasks.length === 0;
board.innerHTML = KANBAN_COLUMNS.map((col, colIndex) => {
const isFirstColumn = colIndex === 0;
const columnTasks = filteredTasks
.filter(t => t.status === col.id)
.slice()
.sort((a, b) => {
const ao = Number.isFinite(Number(a.sort_order)) ? Number(a.sort_order) : Number(a.id);
const bo = Number.isFinite(Number(b.sort_order)) ? Number(b.sort_order) : Number(b.id);
if (ao !== bo) return ao - bo;
return Number(a.id) - Number(b.id);
});
return `
      <div class="kanban-column" data-column="${col.id}">
        <div class="kanban-column-header" style="border-top: 3px solid ${col.color}">
          <div class="kanban-column-title">
            <span>${col.icon}</span>
            <span>${col.label}</span>
            <span class="kanban-column-count">${columnTasks.length}</span>
          </div>
          <button type="button" class="kanban-column-add" data-act-click="kanbanOpenCreateModal(${jsArg(col.id)})">+</button>
        </div>
        <div class="kanban-column-body" 
             id="kanban-col-${col.id}"
             data-act-dragover="kanbanOnDragOver($event)"
             data-act-drop="kanbanOnDrop($event,${jsArg(col.id)})"
             data-act-dragleave="kanbanOnDragLeave($event)">
          ${columnTasks.length > 0
            ? columnTasks.map(task => kanbanRenderCard(task)).join('')
            : (isFirstColumn && boardIsEmpty
                ? `<div class="kanban-empty-col kanban-empty-col--intro">
                     <span class="kanban-empty-icon">📋</span>
                     <span class="kanban-empty-title">Track work across the board</span>
                     <span class="kanban-empty-hint">Add a task, then drag it between
                       To&nbsp;Do, In&nbsp;Progress, Blocked and Done. Agents can pick
                       tasks up from here too.</span>
                     <button type="button" class="btn btn-primary btn-sm"
                             data-act-click="kanbanOpenCreateModal('todo')">＋ Add your first task</button>
                   </div>`
                : `<div class="kanban-empty-col">
                     <span class="kanban-empty-icon">📋</span>
                     <span>No tasks</span>
                   </div>`)
          }
        </div>
      </div>
    `;
}).join('');
}
function kanbanRenderCard(task) {
const priority = KANBAN_PRIORITIES[task.priority] || KANBAN_PRIORITIES.medium;
const known = KANBAN_AGENTS[task.agent];
const agent = known || { label: task.agent || 'Unassigned', icon: '👤' };
const agentLabel = kanbanEscapeHtml(agent.label);
const agentLabelAttr = kanbanEscapeAttr(String(agent.label || ''));
const agentIcon = known ? agent.icon : kanbanEscapeHtml(agent.icon);
const taskId = task.id;
return `
    <div class="kanban-card" 
         draggable="true"
         data-task-id="${taskId}"
         data-act-dragstart="kanbanOnDragStart($event,${jsArg(taskId)})"
         data-act-dragend="kanbanOnDragEnd($event)">
      <div class="kanban-card-top">
        <span class="kanban-card-priority" style="background:${priority.bg};color:${priority.color}">
          ${priority.label}
        </span>
        <div class="kanban-card-actions">
          <button type="button" class="kanban-card-action" data-act-click="kanbanOpenEditModal(${jsArg(taskId)})" data-stop="1">✏️</button>
          <button type="button" class="kanban-card-action" data-act-click="kanbanDeleteTask(${jsArg(taskId)})" data-stop="1">🗑️</button>
        </div>
      </div>
      <div class="kanban-card-title">${kanbanEscapeHtml(task.title)}</div>
      ${task.description ? `<div class="kanban-card-desc">${kanbanEscapeHtml(task.description)}</div>` : ''}
      <div class="kanban-card-bottom">
        <span class="kanban-card-id">#${taskId}</span>
        <span class="kanban-card-agent" title="${agentLabelAttr}">${agentIcon} ${agentLabel}</span>
      </div>
    </div>
  `;
}
function kanbanOnDragStart(event, taskId) {
kanbanDraggedTaskId = taskId;
event.dataTransfer.effectAllowed = 'move';
event.dataTransfer.setData('text/plain', String(taskId));
const card = event.target.closest('.kanban-card');
if (card) {
card.classList.add('kanban-card-dragging');
}
console.debug('Kanban: Drag started for task', taskId);
}
function kanbanOnDragEnd(event) {
const card = event.target.closest('.kanban-card');
if (card) {
card.classList.remove('kanban-card-dragging');
}
document.querySelectorAll('.kanban-column-body').forEach(col => {
col.classList.remove('kanban-column-drag-over');
});
kanbanDraggedTaskId = null;
console.debug('Kanban: Drag ended');
}
function kanbanOnDragOver(event) {
event.preventDefault();
event.dataTransfer.dropEffect = 'move';
const dropZone = event.currentTarget;
dropZone.classList.add('kanban-column-drag-over');
}
function kanbanOnDragLeave(event) {
const dropZone = event.currentTarget;
if (!dropZone.contains(event.relatedTarget)) {
dropZone.classList.remove('kanban-column-drag-over');
}
}
async function kanbanOnDrop(event, targetColumn) {
event.preventDefault();
const dropZone = event.currentTarget;
dropZone.classList.remove('kanban-column-drag-over');
const taskId = event.dataTransfer.getData('text/plain');
console.debug('Kanban: Drop detected', { taskId, targetColumn });
if (!taskId) {
console.warn('Kanban: No task ID in drop data');
return;
}
const task = kanbanTasks.find(t => String(t.id) === String(taskId));
if (!task) {
console.warn('Kanban: Task not found:', taskId);
return;
}
const dropIndex = kanbanDropIndex(event, targetColumn, taskId);
if (task.status === targetColumn) {
await kanbanPersistOrder(targetColumn, taskId, dropIndex);
return;
}
console.debug('Kanban: Moving task', taskId, 'from', task.status, 'to', targetColumn);
const previousStatus = task.status;
task.status = targetColumn;
kanbanRenderBoard();
try {
const response = await fetch(`/api/tasks/${taskId}`, {
method: 'PATCH',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({ status: targetColumn })
});
if (response.ok) {
await kanbanPersistOrder(targetColumn, taskId, dropIndex, { silent: true });
kanbanShowToast('Task moved', 'success');
return;
}
let reason = `HTTP ${response.status}`;
try {
const body = await response.json();
if (body && body.error) reason = body.error;
} catch (e) {  }
task.status = previousStatus;
kanbanRenderBoard();
if (response.status === 404) {
kanbanShowToast('That task no longer exists — refreshing board', 'error');
await kanbanFetchTasks();
kanbanRenderBoard();
} else {
kanbanShowToast(`Could not move task: ${reason}`, 'error');
}
} catch (err) {
task.status = previousStatus;
kanbanRenderBoard();
kanbanShowToast(`Could not move task: ${err.message}`, 'error');
}
}
function kanbanDropIndex(event, targetColumn, draggedId) {
const body = document.getElementById(`kanban-col-${targetColumn}`);
if (!body) return null;
const cards = Array.from(body.querySelectorAll('.kanban-card'))
.filter(el => String(el.dataset.taskId) !== String(draggedId));
for (let i = 0; i < cards.length; i++) {
const box = cards[i].getBoundingClientRect();
if (event.clientY < box.top + box.height / 2) return i;
}
return cards.length;
}
async function kanbanPersistOrder(columnId, movedId, dropIndex, opts = {}) {
if (dropIndex === null || dropIndex === undefined) return;
const inColumn = kanbanTasks
.filter(t => t.status === columnId && String(t.id) !== String(movedId))
.sort((a, b) => {
const ao = Number.isFinite(Number(a.sort_order)) ? Number(a.sort_order) : Number(a.id);
const bo = Number.isFinite(Number(b.sort_order)) ? Number(b.sort_order) : Number(b.id);
return ao - bo || Number(a.id) - Number(b.id);
});
const moved = kanbanTasks.find(t => String(t.id) === String(movedId));
if (!moved) return;
const ordered = inColumn.slice();
ordered.splice(Math.max(0, Math.min(dropIndex, ordered.length)), 0, moved);
const updates = ordered.map((t, i) => ({ id: t.id, sort_order: i + 1 }));
ordered.forEach((t, i) => { t.sort_order = i + 1; });
kanbanRenderBoard();
try {
const r = await fetch('/api/tasks/bulk_update', {
method: 'POST',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({ updates })
});
if (!r.ok) {
kanbanShowToast('Order not saved — reloading board', 'error');
await kanbanFetchTasks();
kanbanRenderBoard();
return;
}
if (!opts.silent) kanbanShowToast('Order updated', 'success');
} catch (e) {
kanbanShowToast(`Order not saved: ${e.message}`, 'error');
await kanbanFetchTasks();
kanbanRenderBoard();
}
}
function kanbanOpenCreateModal(defaultColumn = 'todo') {
if (kanbanModalOpen) return;
kanbanModalOpen = true;
const root = document.getElementById('kanban-modal-root');
if (!root) { kanbanModalOpen = false; return; }
root.innerHTML = `
    <div class="kanban-modal-overlay" id="kanban-modal-overlay">
      <div class="kanban-modal" id="kanban-modal-content">
        <div class="kanban-modal-header">
          <h2>Create Task</h2>
          <button type="button" class="kanban-modal-close" id="kanban-modal-close-btn">✕</button>
        </div>
        <form id="kanban-create-form" class="kanban-modal-body">
          <div class="kanban-field">
            <label for="kb-title">Title *</label>
            <input type="text" id="kb-title" placeholder="What needs to be done?" required>
          </div>
          <div class="kanban-field">
            <label for="kb-desc">Description</label>
            <textarea id="kb-desc" placeholder="Add details..." rows="3"></textarea>
          </div>
          <div class="kanban-field-row">
            <div class="kanban-field">
              <label for="kb-priority">Priority</label>
              <select id="kb-priority">
                <option value="low">🟢 Low</option>
                <option value="medium" selected>🟡 Medium</option>
                <option value="high">🟠 High</option>
              </select>
            </div>
            <div class="kanban-field">
              <label for="kb-agent">Assignee</label>
              <select id="kb-agent">
                <option value="builder">⚡ Builder</option>
                <option value="brain">🧠 Brain</option>
                <option value="researcher">🔬 Researcher</option>
                <option value="orchestrator">🌀 Orchestrator</option>
              </select>
            </div>
          </div>
          <div class="kanban-field">
            <label for="kb-status">Column</label>
            <select id="kb-status">
              ${KANBAN_COLUMNS.map(col => 
                `<option value="${col.id}" ${col.id === defaultColumn ? 'selected' : ''}>${col.icon} ${col.label}</option>`
              ).join('')}
            </select>
          </div>
          <div class="kanban-modal-footer">
            <button type="button" class="kanban-btn-cancel" id="kanban-cancel-btn">Cancel</button>
            <button type="submit" class="kanban-btn-primary">Create Task</button>
          </div>
        </form>
      </div>
    </div>
  `;
const overlay = document.getElementById('kanban-modal-overlay');
const modalContent = document.getElementById('kanban-modal-content');
const closeBtn = document.getElementById('kanban-modal-close-btn');
const cancelBtn = document.getElementById('kanban-cancel-btn');
const form = document.getElementById('kanban-create-form');
overlay.addEventListener('click', function(e) {
if (e.target === overlay) kanbanCloseModal();
});
modalContent.addEventListener('click', function(e) { e.stopPropagation(); });
closeBtn.addEventListener('click', kanbanCloseModal);
cancelBtn.addEventListener('click', kanbanCloseModal);
form.addEventListener('submit', kanbanSubmitCreate);
setTimeout(() => document.getElementById('kb-title')?.focus(), 100);
}
async function kanbanSubmitCreate(event) {
event.preventDefault();
const title = document.getElementById('kb-title')?.value?.trim();
if (!title) return;
const taskData = {
title: title,
description: document.getElementById('kb-desc')?.value?.trim() || '',
status: document.getElementById('kb-status')?.value || 'todo',
priority: document.getElementById('kb-priority')?.value || 'medium',
agent: document.getElementById('kb-agent')?.value || 'builder'
};
try {
const response = await fetch('/api/tasks', {
method: 'POST',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify(taskData)
});
let result = null;
try {
result = await response.json();
} catch (e) {  }
if (!response.ok || !result || result.ok === false || !result.id) {
const reason = (result && result.error) || `HTTP ${response.status}`;
kanbanShowToast(`Could not create task: ${reason}`, 'error');
return;
}
taskData.id = result.id;
kanbanTasks.push(taskData);
kanbanCloseModal();
kanbanRenderBoard();
kanbanShowToast('Task created', 'success');
} catch (e) {
kanbanShowToast(`Could not create task: ${e.message}`, 'error');
}
}
function kanbanOpenEditModal(taskId) {
if (kanbanModalOpen) return;
kanbanModalOpen = true;
const task = kanbanTasks.find(t => String(t.id) === String(taskId));
if (!task) { kanbanModalOpen = false; return; }
const root = document.getElementById('kanban-modal-root');
if (!root) { kanbanModalOpen = false; return; }
root.innerHTML = `
    <div class="kanban-modal-overlay" id="kanban-modal-overlay">
      <div class="kanban-modal" id="kanban-modal-content">
        <div class="kanban-modal-header">
          <h2>Edit Task #${taskId}</h2>
          <button type="button" class="kanban-modal-close" id="kanban-modal-close-btn">✕</button>
        </div>
        <form id="kanban-edit-form" class="kanban-modal-body">
          <div class="kanban-field">
            <label for="kb-edit-title">Title *</label>
            <input type="text" id="kb-edit-title" value="${kanbanEscapeAttr(task.title)}" required>
          </div>
          <div class="kanban-field">
            <label for="kb-edit-desc">Description</label>
            <textarea id="kb-edit-desc" rows="3">${kanbanEscapeHtml(task.description || '')}</textarea>
          </div>
          <div class="kanban-field-row">
            <div class="kanban-field">
              <label for="kb-edit-priority">Priority</label>
              <select id="kb-edit-priority">
                <option value="low" ${task.priority === 'low' ? 'selected' : ''}>🟢 Low</option>
                <option value="medium" ${task.priority === 'medium' ? 'selected' : ''}>🟡 Medium</option>
                <option value="high" ${task.priority === 'high' ? 'selected' : ''}>🟠 High</option>
              </select>
            </div>
            <div class="kanban-field">
              <label for="kb-edit-agent">Assignee</label>
              <select id="kb-edit-agent">
                <option value="builder" ${task.agent === 'builder' ? 'selected' : ''}>⚡ Builder</option>
                <option value="brain" ${task.agent === 'brain' ? 'selected' : ''}>🧠 Brain</option>
                <option value="researcher" ${task.agent === 'researcher' ? 'selected' : ''}>🔬 Researcher</option>
                <option value="orchestrator" ${task.agent === 'orchestrator' ? 'selected' : ''}>🌀 Orchestrator</option>
              </select>
            </div>
          </div>
          <div class="kanban-field">
            <label for="kb-edit-status">Column</label>
            <select id="kb-edit-status">
              ${KANBAN_COLUMNS.map(col => 
                `<option value="${col.id}" ${col.id === task.status ? 'selected' : ''}>${col.icon} ${col.label}</option>`
              ).join('')}
            </select>
          </div>
          <div class="kanban-modal-footer">
            <button type="button" class="kanban-btn-delete" id="kanban-delete-btn">Delete</button>
            <div class="u-97445a8d"></div>
            <button type="button" class="kanban-btn-cancel" id="kanban-cancel-btn">Cancel</button>
            <button type="submit" class="kanban-btn-primary">Save Changes</button>
          </div>
        </form>
      </div>
    </div>
  `;
const overlay = document.getElementById('kanban-modal-overlay');
const modalContent = document.getElementById('kanban-modal-content');
const closeBtn = document.getElementById('kanban-modal-close-btn');
const cancelBtn = document.getElementById('kanban-cancel-btn');
const deleteBtn = document.getElementById('kanban-delete-btn');
const form = document.getElementById('kanban-edit-form');
overlay.addEventListener('click', function(e) {
if (e.target === overlay) kanbanCloseModal();
});
modalContent.addEventListener('click', function(e) { e.stopPropagation(); });
closeBtn.addEventListener('click', kanbanCloseModal);
cancelBtn.addEventListener('click', kanbanCloseModal);
deleteBtn.addEventListener('click', function() {
kanbanDeleteTask(taskId);
kanbanCloseModal();
});
form.addEventListener('submit', function(e) { kanbanSubmitEdit(e, taskId); });
}
async function kanbanSubmitEdit(event, taskId) {
event.preventDefault();
const task = kanbanTasks.find(t => String(t.id) === String(taskId));
if (!task) return;
const updates = {
title: document.getElementById('kb-edit-title')?.value?.trim() || task.title,
description: document.getElementById('kb-edit-desc')?.value?.trim() || '',
priority: document.getElementById('kb-edit-priority')?.value || task.priority,
agent: document.getElementById('kb-edit-agent')?.value || task.agent,
status: document.getElementById('kb-edit-status')?.value || task.status
};
const snapshot = { ...task };
Object.assign(task, updates);
kanbanCloseModal();
kanbanRenderBoard();
const revert = (message) => {
Object.assign(task, snapshot);
kanbanRenderBoard();
kanbanShowToast(message, 'error');
};
try {
const response = await fetch(`/api/tasks/${taskId}`, {
method: 'PATCH',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify(updates)
});
if (response.ok) {
kanbanShowToast('Task updated', 'success');
return;
}
if (response.status === 404) {
revert('That task no longer exists — refreshing board');
await kanbanFetchTasks();
kanbanRenderBoard();
return;
}
let reason = `HTTP ${response.status}`;
try {
const body = await response.json();
if (body && body.error) reason = body.error;
} catch (e) {  }
revert(`Could not save changes: ${reason}`);
} catch (e) {
revert(`Could not save changes: ${e.message}`);
}
}
async function kanbanDeleteTask(taskId) {
const ok = await gmDanger('Delete Task', 'Delete this task? This cannot be undone.', 'Delete');
if (!ok) return;
const removed = kanbanTasks.filter(t => String(t.id) === String(taskId));
kanbanTasks = kanbanTasks.filter(t => String(t.id) !== String(taskId));
kanbanRenderBoard();
const restore = (message) => {
kanbanTasks = kanbanTasks.concat(removed);
kanbanRenderBoard();
kanbanShowToast(message, 'error');
};
try {
const response = await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
if (response.ok) {
kanbanShowToast('Task deleted', 'success');
return;
}
if (response.status === 404) {
kanbanShowToast('That task was already deleted', 'success');
return;
}
let reason = `HTTP ${response.status}`;
try {
const body = await response.json();
if (body && body.error) reason = body.error;
} catch (e) {  }
restore(`Could not delete task: ${reason}`);
} catch (e) {
restore(`Could not delete task: ${e.message}`);
}
}
function kanbanSetFilter(priority) {
kanbanActiveFilter = priority;
kanbanRenderBoard();
}
function kanbanJumpToDone() {
const col = document.getElementById('kanban-col-done');
if (!col) { if (typeof toast === 'function') toast('Open the Tasks board first', 'warn'); return; }
col.closest('.kanban-column')?.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
const header = col.closest('.kanban-column')?.querySelector('.kanban-column-header');
if (header) {
header.style.transition = 'background-color .3s';
header.style.backgroundColor = 'rgba(34,197,94,0.25)';
setTimeout(() => { header.style.backgroundColor = ''; }, 1200);
}
}
function kanbanCloseModal() {
kanbanModalOpen = false;
const root = document.getElementById('kanban-modal-root');
if (root) root.innerHTML = '';
}
function kanbanEscapeHtml(text) {
if (!text) return '';
const div = document.createElement('div');
div.textContent = text;
return div.innerHTML;
}
function kanbanEscapeAttr(text) {
if (!text) return '';
return text.replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function kanbanShowToast(message, type) {
if (typeof toast === 'function') {
toast(message, type === 'success' ? 'ok' : type === 'error' ? 'err' : 'warn');
} else {
console.log(`[${type}] ${message}`);
}
}
window.renderKanban = renderKanban;
window.kanbanOnDragStart = kanbanOnDragStart;
window.kanbanOnDragEnd = kanbanOnDragEnd;
window.kanbanOnDragOver = kanbanOnDragOver;
window.kanbanOnDragLeave = kanbanOnDragLeave;
window.kanbanOnDrop = kanbanOnDrop;
window.kanbanOpenCreateModal = kanbanOpenCreateModal;
window.kanbanSubmitCreate = kanbanSubmitCreate;
window.kanbanOpenEditModal = kanbanOpenEditModal;
window.kanbanSubmitEdit = kanbanSubmitEdit;
window.kanbanDeleteTask = kanbanDeleteTask;
window.kanbanSetFilter = kanbanSetFilter;
window.kanbanJumpToDone = kanbanJumpToDone;
window.kanbanCloseModal = kanbanCloseModal;
console.log('%c✅ Kanban Board v4 loaded', 'color:#22c55e;font-weight:bold');
