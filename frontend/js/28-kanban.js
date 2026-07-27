// Agentic OS — Production Kanban Board v3
// Fixed: modal auto-close, drag-and-drop, proper event handling
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
let kanbanModalOpen = false;

// ── Main Render Function ─────────────────────────────────────────
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

  await kanbanFetchTasks();
  kanbanRenderBoard();
}

// ── Fetch Tasks ──────────────────────────────────────────────────
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
    } else {
      kanbanTasks = kanbanGetSampleTasks();
    }
  } catch (e) {
    kanbanTasks = kanbanGetSampleTasks();
  }
}

// ── Render Board ─────────────────────────────────────────────────
function kanbanRenderBoard() {
  const board = document.getElementById('kanban-board');
  const countEl = document.getElementById('kanban-task-count');
  if (!board) return;

  let filteredTasks = kanbanTasks;
  if (kanbanActiveFilter) {
    filteredTasks = kanbanTasks.filter(t => t.priority === kanbanActiveFilter);
  }

  if (countEl) {
    countEl.textContent = `${filteredTasks.length} task${filteredTasks.length !== 1 ? 's' : ''}`;
  }

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
             data-column="${col.id}">
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

  // Attach drag-and-drop event listeners AFTER rendering
  kanbanAttachDragListeners();
}

// ── Render Card ───────────────────────────────────────────────────
function kanbanRenderCard(task) {
  const priority = KANBAN_PRIORITIES[task.priority] || KANBAN_PRIORITIES.medium;
  const agent = KANBAN_AGENTS[task.agent] || { label: task.agent || 'Unassigned', icon: '👤' };
  const taskId = task.id;

  return `
    <div class="kanban-card" 
         draggable="true"
         data-task-id="${taskId}">
      <div class="kanban-card-top">
        <span class="kanban-card-priority" style="background:${priority.bg};color:${priority.color}">
          ${priority.label}
        </span>
        <div class="kanban-card-actions">
          <button type="button" class="kanban-card-action" data-action="edit" data-task-id="${taskId}" title="Edit">✏️</button>
          <button type="button" class="kanban-card-action" data-action="delete" data-task-id="${taskId}" title="Delete">🗑️</button>
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

// ── Attach Drag Listeners (AFTER render) ─────────────────────────
function kanbanAttachDragListeners() {
  // Card drag listeners
  document.querySelectorAll('.kanban-card[draggable="true"]').forEach(card => {
    card.addEventListener('dragstart', function(e) {
      const taskId = this.dataset.taskId;
      kanbanDragState.taskId = taskId;
      kanbanDragState.sourceColumn = this.closest('.kanban-column')?.dataset.column;
      
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', taskId);
      
      // Visual feedback - use 'this' instead of e.target
      setTimeout(() => {
        this.classList.add('kanban-card-dragging');
      }, 0);
    });

    card.addEventListener('dragend', function(e) {
      this.classList.remove('kanban-card-dragging');
      
      document.querySelectorAll('.kanban-column-body').forEach(col => {
        col.classList.remove('kanban-column-drag-over');
      });
      
      kanbanDragState = { taskId: null, sourceColumn: null };
    });
  });

  // Column drop zone listeners
  document.querySelectorAll('.kanban-column-body').forEach(colBody => {
    colBody.addEventListener('dragover', function(e) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      this.classList.add('kanban-column-drag-over');
    });

    colBody.addEventListener('dragleave', function(e) {
      if (!this.contains(e.relatedTarget)) {
        this.classList.remove('kanban-column-drag-over');
      }
    });

    colBody.addEventListener('drop', async function(e) {
      e.preventDefault();
      this.classList.remove('kanban-column-drag-over');
      
      const taskId = e.dataTransfer.getData('text/plain');
      const targetColumn = this.dataset.column;
      
      if (!taskId || !targetColumn) return;
      
      // Find task - compare as strings since dataset values are strings
      const task = kanbanTasks.find(t => String(t.id) === String(taskId));
      if (!task || task.status === targetColumn) return;
      
      // Update local state
      task.status = targetColumn;
      
      // Re-render immediately
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
        }
      } catch (err) {
        console.warn('Kanban: API error:', err.message);
      }
    });
  });

  // Card action button listeners
  document.querySelectorAll('.kanban-card-action').forEach(btn => {
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      const action = this.dataset.action;
      const taskId = this.dataset.taskId;
      
      if (action === 'edit') {
        kanbanOpenEditModal(taskId);
      } else if (action === 'delete') {
        kanbanDeleteTask(taskId);
      }
    });
  });
}

// ── Create Task Modal ─────────────────────────────────────────────
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

  // Attach event listeners AFTER DOM is ready
  const overlay = document.getElementById('kanban-modal-overlay');
  const modalContent = document.getElementById('kanban-modal-content');
  const closeBtn = document.getElementById('kanban-modal-close-btn');
  const cancelBtn = document.getElementById('kanban-cancel-btn');
  const form = document.getElementById('kanban-create-form');

  // Close when clicking overlay (outside modal)
  overlay.addEventListener('click', function(e) {
    if (e.target === overlay) {
      kanbanCloseModal();
    }
  });

  // Prevent clicks inside modal from closing it
  modalContent.addEventListener('click', function(e) {
    e.stopPropagation();
  });

  // Close buttons
  closeBtn.addEventListener('click', kanbanCloseModal);
  cancelBtn.addEventListener('click', kanbanCloseModal);

  // Form submission
  form.addEventListener('submit', kanbanSubmitCreate);

  // Focus title input
  setTimeout(() => {
    const titleInput = document.getElementById('kb-title');
    if (titleInput) titleInput.focus();
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

  try {
    const response = await fetch('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(taskData)
    });

    if (response.ok) {
      const result = await response.json();
      taskData.id = result.id;
      kanbanTasks.push(taskData);
      kanbanCloseModal();
      kanbanRenderBoard();
      kanbanShowToast('Task created', 'success');
    } else {
      kanbanShowToast('Failed to create task', 'error');
    }
  } catch (e) {
    taskData.id = Date.now();
    kanbanTasks.push(taskData);
    kanbanCloseModal();
    kanbanRenderBoard();
    kanbanShowToast('Task created (local)', 'success');
  }
}

// ── Edit Task Modal ───────────────────────────────────────────────
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
            <div style="flex:1"></div>
            <button type="button" class="kanban-btn-cancel" id="kanban-cancel-btn">Cancel</button>
            <button type="submit" class="kanban-btn-primary">Save Changes</button>
          </div>
        </form>
      </div>
    </div>
  `;

  // Attach event listeners AFTER DOM is ready
  const overlay = document.getElementById('kanban-modal-overlay');
  const modalContent = document.getElementById('kanban-modal-content');
  const closeBtn = document.getElementById('kanban-modal-close-btn');
  const cancelBtn = document.getElementById('kanban-cancel-btn');
  const deleteBtn = document.getElementById('kanban-delete-btn');
  const form = document.getElementById('kanban-edit-form');

  overlay.addEventListener('click', function(e) {
    if (e.target === overlay) {
      kanbanCloseModal();
    }
  });

  modalContent.addEventListener('click', function(e) {
    e.stopPropagation();
  });

  closeBtn.addEventListener('click', kanbanCloseModal);
  cancelBtn.addEventListener('click', kanbanCloseModal);
  
  deleteBtn.addEventListener('click', function() {
    kanbanDeleteTask(taskId);
    kanbanCloseModal();
  });

  form.addEventListener('submit', function(e) {
    kanbanSubmitEdit(e, taskId);
  });
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

  // Update local state
  Object.assign(task, updates);

  // Close modal and re-render
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

  kanbanTasks = kanbanTasks.filter(t => String(t.id) !== String(taskId));
  kanbanRenderBoard();

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
  kanbanModalOpen = false;
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
window.kanbanOpenCreateModal = kanbanOpenCreateModal;
window.kanbanSubmitCreate = kanbanSubmitCreate;
window.kanbanOpenEditModal = kanbanOpenEditModal;
window.kanbanSubmitEdit = kanbanSubmitEdit;
window.kanbanDeleteTask = kanbanDeleteTask;
window.kanbanSetFilter = kanbanSetFilter;
window.kanbanCloseModal = kanbanCloseModal;

console.log('%c✅ Kanban Board v3 loaded', 'color:#22c55e;font-weight:bold');
