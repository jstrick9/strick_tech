// Agentic OS — Production Kanban Board
// Full drag-and-drop, CRUD, filtering, proper API integration
'use strict';

// ── Configuration ────────────────────────────────────────────────
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

// ── State ────────────────────────────────────────────────────────
let kanbanTasks = [];
let kanbanDragState = { taskId: null, sourceColumn: null };
let kanbanActiveFilter = null;

// ── Main Render Function ─────────────────────────────────────────
async function renderKanban() {
  const pane = document.getElementById('pane-kanban');
  if (!pane) return;

  // Show loading state
  pane.innerHTML = `
    <div class="kanban-root">
      <div class="kanban-topbar">
        <div class="kanban-topbar-left">
          <h1 class="kanban-title">📋 Tasks</h1>
          <span class="kanban-count" id="kanban-task-count">Loading...</span>
        </div>
        <div class="kanban-topbar-right">
          <div class="kanban-filter-group">
            <button type="button" class="kanban-filter-btn ${!kanbanActiveFilter ? 'active' : ''}" onclick="kanbanSetFilter(null)">All</button>
            <button type="button" class="kanban-filter-btn ${kanbanActiveFilter === 'high' ? 'active' : ''}" onclick="kanbanSetFilter('high')">🔴 High</button>
            <button type="button" class="kanban-filter-btn ${kanbanActiveFilter === 'medium' ? 'active' : ''}" onclick="kanbanSetFilter('medium')">🟡 Medium</button>
            <button type="button" class="kanban-filter-btn ${kanbanActiveFilter === 'low' ? 'active' : ''}" onclick="kanbanSetFilter('low')">🟢 Low</button>
          </div>
          <button type="button" class="kanban-add-btn" onclick="kanbanOpenCreateModal()">
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

  // Fetch tasks from API
  await kanbanFetchTasks();
  
  // Render the board
  kanbanRenderBoard();
}

// ── Fetch Tasks ──────────────────────────────────────────────────
async function kanbanFetchTasks() {
  try {
    const response = await fetch('/api/kanban');
    if (response.ok) {
      const data = await response.json();
      kanbanTasks = [];
      // API returns { todo: [...], doing: [...], blocked: [...], done: [...] }
      for (const [status, tasks] of Object.entries(data)) {
        if (Array.isArray(tasks)) {
          tasks.forEach(task => {
            kanbanTasks.push({ ...task, status: status });
          });
        }
      }
    } else {
      console.warn('Kanban: API returned', response.status);
      kanbanTasks = kanbanGetSampleTasks();
    }
  } catch (e) {
    console.warn('Kanban: Using sample tasks:', e.message);
    kanbanTasks = kanbanGetSampleTasks();
  }
}

// ── Render Board ─────────────────────────────────────────────────
function kanbanRenderBoard() {
  const board = document.getElementById('kanban-board');
  const countEl = document.getElementById('kanban-task-count');
  if (!board) return;

  // Apply filter
  let filteredTasks = kanbanTasks;
  if (kanbanActiveFilter) {
    filteredTasks = kanbanTasks.filter(t => t.priority === kanbanActiveFilter);
  }

  // Update count
  if (countEl) {
    countEl.textContent = `${filteredTasks.length} task${filteredTasks.length !== 1 ? 's' : ''}`;
  }

  // Render columns
  board.innerHTML = KANBAN_COLUMNS.map(col => {
    const columnTasks = filteredTasks.filter(t => t.status === col.id);
    return `
      <div class="kanban-column" data-column="${col.id}">
        <div class="kanban-column-header" style="border-top: 3px solid ${col.color}">
          <div class="kanban-column-title">
            <span>${col.icon}</span>
            <span>${col.label}</span>
            <span class="kanban-column-count">${columnTasks.length}</span>
          </div>
          <button type="button" class="kanban-column-add" onclick="kanbanOpenCreateModal('${col.id}')" title="Add task to ${col.label}">+</button>
        </div>
        <div class="kanban-column-body" 
             id="kanban-col-${col.id}"
             ondragover="kanbanHandleDragOver(event, '${col.id}')"
             ondragleave="kanbanHandleDragLeave(event)"
             ondrop="kanbanHandleDrop(event, '${col.id}')">
          ${columnTasks.length > 0 
            ? columnTasks.map(task => kanbanRenderCard(task)).join('')
            : `<div class="kanban-empty-col">
                 <span class="kanban-empty-icon">📋</span>
                 <span>No tasks</span>
               </div>`
          }
        </div>
      </div>
    `;
  }).join('');
}

// ── Render Card ───────────────────────────────────────────────────
function kanbanRenderCard(task) {
  const priority = KANBAN_PRIORITIES[task.priority] || KANBAN_PRIORITIES.medium;
  const agent = KANBAN_AGENTS[task.agent] || { label: task.agent || 'Unassigned', icon: '👤' };
  const taskId = task.id;

  return `
    <div class="kanban-card" 
         draggable="true"
         data-task-id="${taskId}"
         ondragstart="kanbanHandleDragStart(event, ${taskId})"
         ondragend="kanbanHandleDragEnd(event)">
      <div class="kanban-card-top">
        <span class="kanban-card-priority" style="background:${priority.bg};color:${priority.color}">
          ${priority.label}
        </span>
        <div class="kanban-card-actions">
          <button type="button" class="kanban-card-action" onclick="event.stopPropagation();kanbanOpenEditModal(${taskId})" title="Edit">✏️</button>
          <button type="button" class="kanban-card-action" onclick="event.stopPropagation();kanbanDeleteTask(${taskId})" title="Delete">🗑️</button>
        </div>
      </div>
      <div class="kanban-card-title">${kanbanEscapeHtml(task.title)}</div>
      ${task.description ? `<div class="kanban-card-desc">${kanbanEscapeHtml(task.description)}</div>` : ''}
      <div class="kanban-card-bottom">
        <span class="kanban-card-id">#${taskId}</span>
        <span class="kanban-card-agent" title="${agent.label}">${agent.icon} ${agent.label}</span>
      </div>
    </div>
  `;
}

// ── Drag & Drop Handlers ─────────────────────────────────────────
function kanbanHandleDragStart(event, taskId) {
  kanbanDragState.taskId = taskId;
  kanbanDragState.sourceColumn = event.target.closest('.kanban-column')?.dataset.column;
  
  event.dataTransfer.effectAllowed = 'move';
  event.dataTransfer.setData('text/plain', String(taskId));
  
  // Visual feedback
  setTimeout(() => {
    event.target.classList.add('kanban-card-dragging');
  }, 0);
}

function kanbanHandleDragEnd(event) {
  event.target.classList.remove('kanban-card-dragging');
  
  // Remove all drag-over highlights
  document.querySelectorAll('.kanban-column-body').forEach(col => {
    col.classList.remove('kanban-column-drag-over');
  });
  
  kanbanDragState = { taskId: null, sourceColumn: null };
}

function kanbanHandleDragOver(event, columnId) {
  event.preventDefault();
  event.dataTransfer.dropEffect = 'move';
  
  const colBody = event.currentTarget;
  colBody.classList.add('kanban-column-drag-over');
}

function kanbanHandleDragLeave(event) {
  // Only remove if we're leaving the column body
  if (!event.currentTarget.contains(event.relatedTarget)) {
    event.currentTarget.classList.remove('kanban-column-drag-over');
  }
}

async function kanbanHandleDrop(event, targetColumn) {
  event.preventDefault();
  event.currentTarget.classList.remove('kanban-column-drag-over');
  
  const taskId = parseInt(event.dataTransfer.getData('text/plain'));
  if (!taskId) return;
  
  const task = kanbanTasks.find(t => t.id === taskId);
  if (!task || task.status === targetColumn) return;
  
  // Update local state
  task.status = targetColumn;
  
  // Re-render immediately for responsiveness
  kanbanRenderBoard();
  
  // Save to API
  try {
    const response = await fetch(`/api/tasks/${taskId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: targetColumn })
    });
    
    if (response.ok) {
      kanbanShowToast('Task moved', 'success');
    } else {
      console.warn('Kanban: Failed to save move');
    }
  } catch (e) {
    console.warn('Kanban: API error:', e.message);
  }
}

// ── Create Task Modal ─────────────────────────────────────────────
function kanbanOpenCreateModal(defaultColumn = 'todo') {
  const root = document.getElementById('kanban-modal-root');
  if (!root) return;

  root.innerHTML = `
    <div class="kanban-modal-overlay" onclick="kanbanCloseModal()">
      <div class="kanban-modal" onclick="event.stopPropagation()">
        <div class="kanban-modal-header">
          <h2>Create Task</h2>
          <button type="button" class="kanban-modal-close" onclick="kanbanCloseModal()">✕</button>
        </div>
        <form onsubmit="kanbanSubmitCreate(event)" class="kanban-modal-body">
          <div class="kanban-field">
            <label for="kb-title">Title *</label>
            <input type="text" id="kb-title" placeholder="What needs to be done?" required autofocus>
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
            <button type="button" class="kanban-btn-cancel" onclick="kanbanCloseModal()">Cancel</button>
            <button type="submit" class="kanban-btn-primary">Create Task</button>
          </div>
        </form>
      </div>
    </div>
  `;

  // Focus title input
  setTimeout(() => {
    document.getElementById('kb-title')?.focus();
  }, 100);
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

  // Save to API first to get real ID
  try {
    const response = await fetch('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(taskData)
    });

    if (response.ok) {
      const result = await response.json();
      // Use the ID from the API response
      taskData.id = result.id;
      kanbanTasks.push(taskData);
      kanbanCloseModal();
      kanbanRenderBoard();
      kanbanShowToast('Task created', 'success');
    } else {
      kanbanShowToast('Failed to create task', 'error');
    }
  } catch (e) {
    // Fallback: use local ID
    taskData.id = Date.now();
    kanbanTasks.push(taskData);
    kanbanCloseModal();
    kanbanRenderBoard();
    kanbanShowToast('Task created (local)', 'success');
  }
}

// ── Edit Task Modal ───────────────────────────────────────────────
function kanbanOpenEditModal(taskId) {
  const task = kanbanTasks.find(t => t.id === taskId);
  if (!task) return;

  const root = document.getElementById('kanban-modal-root');
  if (!root) return;

  root.innerHTML = `
    <div class="kanban-modal-overlay" onclick="kanbanCloseModal()">
      <div class="kanban-modal" onclick="event.stopPropagation()">
        <div class="kanban-modal-header">
          <h2>Edit Task #${taskId}</h2>
          <button type="button" class="kanban-modal-close" onclick="kanbanCloseModal()">✕</button>
        </div>
        <form onsubmit="kanbanSubmitEdit(event, ${taskId})" class="kanban-modal-body">
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
            <button type="button" class="kanban-btn-delete" onclick="kanbanDeleteTask(${taskId});kanbanCloseModal()">Delete</button>
            <div style="flex:1"></div>
            <button type="button" class="kanban-btn-cancel" onclick="kanbanCloseModal()">Cancel</button>
            <button type="submit" class="kanban-btn-primary">Save Changes</button>
          </div>
        </form>
      </div>
    </div>
  `;
}

async function kanbanSubmitEdit(event, taskId) {
  event.preventDefault();

  const task = kanbanTasks.find(t => t.id === taskId);
  if (!task) return;

  const updates = {
    title: document.getElementById('kb-edit-title')?.value?.trim() || task.title,
    description: document.getElementById('kb-edit-desc')?.value?.trim() || '',
    priority: document.getElementById('kb-edit-priority')?.value || task.priority,
    agent: document.getElementById('kb-edit-agent')?.value || task.agent,
    status: document.getElementById('kb-edit-status')?.value || task.status
  };

  // Update local state
  Object.assign(task, updates);

  // Re-render immediately
  kanbanCloseModal();
  kanbanRenderBoard();

  // Save to API
  try {
    const response = await fetch(`/api/tasks/${taskId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates)
    });

    if (response.ok) {
      kanbanShowToast('Task updated', 'success');
    } else {
      kanbanShowToast('Failed to save changes', 'error');
    }
  } catch (e) {
    console.warn('Kanban: API error:', e.message);
  }
}

// ── Delete Task ───────────────────────────────────────────────────
async function kanbanDeleteTask(taskId) {
  if (!confirm('Delete this task? This cannot be undone.')) return;

  // Remove from local state
  kanbanTasks = kanbanTasks.filter(t => t.id !== taskId);

  // Re-render immediately
  kanbanRenderBoard();

  // Delete from API
  try {
    await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
    kanbanShowToast('Task deleted', 'success');
  } catch (e) {
    console.warn('Kanban: API error:', e.message);
  }
}

// ── Filter ────────────────────────────────────────────────────────
function kanbanSetFilter(priority) {
  kanbanActiveFilter = priority;
  kanbanRenderBoard();
}

// ── Close Modal ───────────────────────────────────────────────────
function kanbanCloseModal() {
  const root = document.getElementById('kanban-modal-root');
  if (root) root.innerHTML = '';
}

// ── Sample Tasks ──────────────────────────────────────────────────
function kanbanGetSampleTasks() {
  return [
    { id: 1001, title: 'Design new landing page', description: 'Create a modern landing page with hero section', status: 'todo', priority: 'high', agent: 'builder' },
    { id: 1002, title: 'Fix authentication bug', description: 'Users getting logged out unexpectedly', status: 'doing', priority: 'high', agent: 'brain' },
    { id: 1003, title: 'Write API documentation', description: 'Document all REST endpoints', status: 'todo', priority: 'medium', agent: 'researcher' },
    { id: 1004, title: 'Implement dark mode', description: 'Add theme switching capability', status: 'blocked', priority: 'low', agent: 'builder' },
    { id: 1005, title: 'Optimize database queries', description: 'Slow queries on user dashboard', status: 'done', priority: 'high', agent: 'brain' },
    { id: 1006, title: 'Add unit tests', description: 'Increase test coverage to 80%', status: 'todo', priority: 'medium', agent: 'builder' }
  ];
}

// ── Utility Functions ─────────────────────────────────────────────
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

// ── Global Exports ────────────────────────────────────────────────
window.renderKanban = renderKanban;
window.kanbanHandleDragStart = kanbanHandleDragStart;
window.kanbanHandleDragEnd = kanbanHandleDragEnd;
window.kanbanHandleDragOver = kanbanHandleDragOver;
window.kanbanHandleDragLeave = kanbanHandleDragLeave;
window.kanbanHandleDrop = kanbanHandleDrop;
window.kanbanOpenCreateModal = kanbanOpenCreateModal;
window.kanbanSubmitCreate = kanbanSubmitCreate;
window.kanbanOpenEditModal = kanbanOpenEditModal;
window.kanbanSubmitEdit = kanbanSubmitEdit;
window.kanbanDeleteTask = kanbanDeleteTask;
window.kanbanSetFilter = kanbanSetFilter;
window.kanbanCloseModal = kanbanCloseModal;

console.log('%c✅ Kanban Board v2 loaded', 'color:#22c55e;font-weight:bold');
