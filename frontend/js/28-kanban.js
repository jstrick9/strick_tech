// Agentic OS — Full Kanban Board with Drag-and-Drop
// Inspired by Jira, Linear, and Trello
'use strict';

// ── Kanban State ─────────────────────────────────────────────────
const KanbanState = {
  columns: [
    { id: 'backlog', label: 'Backlog', color: '#6b7280', icon: '📋' },
    { id: 'todo', label: 'To Do', color: '#3b82f6', icon: '📝' },
    { id: 'in-progress', label: 'In Progress', color: '#f59e0b', icon: '⚡' },
    { id: 'review', label: 'In Review', color: '#8b5cf6', icon: '👀' },
    { id: 'done', label: 'Done', color: '#22c55e', icon: '✅' }
  ],
  tasks: [],
  draggedTask: null,
  dragOverColumn: null
};

// ── Initialize Kanban ─────────────────────────────────────────────
async function renderKanban() {
  const pane = document.getElementById('pane-kanban');
  if (!pane) return;

  // Load tasks from API
  try {
    const data = await AgenticAPI.get('/api/kanban');
    KanbanState.tasks = flattenKanbanData(data);
  } catch (e) {
    KanbanState.tasks = getSampleTasks();
  }

  pane.innerHTML = `
    <div class="kanban-container">
      <!-- Header -->
      <div class="kanban-header">
        <div class="kanban-header-left">
          <h1 class="kanban-title">📋 Tasks</h1>
          <span class="kanban-subtitle">${KanbanState.tasks.length} tasks across ${KanbanState.columns.length} columns</span>
        </div>
        <div class="kanban-header-right">
          <button type="button" class="btn btn-ghost btn-sm" onclick="kanbanFilterToggle()" title="Filter tasks">
            🔍 Filter
          </button>
          <button type="button" class="btn btn-primary btn-sm" onclick="kanbanAddTask()">
            ＋ New Task
          </button>
        </div>
      </div>

      <!-- Board -->
      <div class="kanban-board" id="kanban-board">
        ${KanbanState.columns.map(col => renderKanbanColumn(col)).join('')}
      </div>
    </div>

    <!-- Add Task Modal -->
    <div id="kanban-add-modal" class="kanban-modal" style="display:none">
      <div class="kanban-modal-content">
        <div class="kanban-modal-header">
          <h2>Create New Task</h2>
          <button type="button" class="icon-btn" onclick="kanbanCloseModal()">✕</button>
        </div>
        <div class="kanban-modal-body">
          <div class="kanban-form-group">
            <label>Title</label>
            <input type="text" id="kanban-task-title" placeholder="What needs to be done?" class="kanban-input" autofocus>
          </div>
          <div class="kanban-form-group">
            <label>Description</label>
            <textarea id="kanban-task-desc" placeholder="Add more details..." class="kanban-textarea" rows="3"></textarea>
          </div>
          <div class="kanban-form-row">
            <div class="kanban-form-group">
              <label>Priority</label>
              <select id="kanban-task-priority" class="kanban-select">
                <option value="low">🟢 Low</option>
                <option value="medium" selected>🟡 Medium</option>
                <option value="high">🟠 High</option>
                <option value="urgent">🔴 Urgent</option>
              </select>
            </div>
            <div class="kanban-form-group">
              <label>Assignee</label>
              <select id="kanban-task-assignee" class="kanban-select">
                <option value="">Unassigned</option>
                <option value="builder">Builder</option>
                <option value="brain">Brain</option>
                <option value="researcher">Researcher</option>
                <option value="orchestrator">Orchestrator</option>
              </select>
            </div>
          </div>
          <div class="kanban-form-group">
            <label>Column</label>
            <select id="kanban-task-column" class="kanban-select">
              ${KanbanState.columns.map(col => `<option value="${col.id}">${col.icon} ${col.label}</option>`).join('')}
            </select>
          </div>
        </div>
        <div class="kanban-modal-footer">
          <button type="button" class="btn btn-ghost" onclick="kanbanCloseModal()">Cancel</button>
          <button type="button" class="btn btn-primary" onclick="kanbanSaveTask()">Create Task</button>
        </div>
      </div>
    </div>
  `;

  // Add drag-and-drop event listeners
  initKanbanDragDrop();
}

// ── Render Column ─────────────────────────────────────────────────
function renderKanbanColumn(column) {
  const tasks = KanbanState.tasks.filter(t => t.status === column.id);
  return `
    <div class="kanban-column" data-column="${column.id}"
         ondragover="kanbanDragOver(event, '${column.id}')"
         ondragleave="kanbanDragLeave(event, '${column.id}')"
         ondrop="kanbanDrop(event, '${column.id}')">
      <div class="kanban-column-header">
        <div class="kanban-column-title">
          <span class="kanban-column-icon">${column.icon}</span>
          <span>${column.label}</span>
          <span class="kanban-column-count">${tasks.length}</span>
        </div>
        <button type="button" class="icon-btn kanban-add-btn" onclick="kanbanAddTaskToColumn('${column.id}')" title="Add task">
          ＋
        </button>
      </div>
      <div class="kanban-column-body" id="kanban-col-${column.id}">
        ${tasks.map(task => renderKanbanCard(task)).join('')}
        ${tasks.length === 0 ? `
          <div class="kanban-empty-column">
            <span>No tasks</span>
          </div>
        ` : ''}
      </div>
    </div>
  `;
}

// ── Render Card ───────────────────────────────────────────────────
function renderKanbanCard(task) {
  const priorityColors = {
    low: '#22c55e',
    medium: '#f59e0b',
    high: '#f97316',
    urgent: '#ef4444'
  };
  const priorityLabels = {
    low: 'Low',
    medium: 'Medium',
    high: 'High',
    urgent: 'Urgent'
  };

  return `
    <div class="kanban-card" 
         draggable="true"
         data-task-id="${task.id}"
         ondragstart="kanbanDragStart(event, '${task.id}')"
         ondragend="kanbanDragEnd(event)"
         onclick="kanbanEditTask('${task.id}')">
      <div class="kanban-card-header">
        <span class="kanban-card-priority" style="background: ${priorityColors[task.priority] || '#6b7280'}">
          ${priorityLabels[task.priority] || 'Medium'}
        </span>
        ${task.assignee ? `
          <span class="kanban-card-assignee" title="${task.assignee}">
            ${getAssigneeAvatar(task.assignee)}
          </span>
        ` : ''}
      </div>
      <div class="kanban-card-title">${escapeHtml(task.title)}</div>
      ${task.description ? `
        <div class="kanban-card-desc">${escapeHtml(task.description)}</div>
      ` : ''}
      <div class="kanban-card-footer">
        <span class="kanban-card-id">#${task.id}</span>
        ${task.due_date ? `
          <span class="kanban-card-due ${isOverdue(task.due_date) ? 'overdue' : ''}">
            📅 ${formatDate(task.due_date)}
          </span>
        ` : ''}
      </div>
    </div>
  `;
}

// ── Drag and Drop ─────────────────────────────────────────────────
function initKanbanDragDrop() {
  // Add touch support for mobile
  document.querySelectorAll('.kanban-card').forEach(card => {
    card.addEventListener('touchstart', kanbanTouchStart, { passive: false });
    card.addEventListener('touchmove', kanbanTouchMove, { passive: false });
    card.addEventListener('touchend', kanbanTouchEnd);
  });
}

function kanbanDragStart(event, taskId) {
  KanbanState.draggedTask = taskId;
  event.dataTransfer.effectAllowed = 'move';
  event.dataTransfer.setData('text/plain', taskId);
  
  // Add dragging class after a small delay
  setTimeout(() => {
    event.target.classList.add('kanban-dragging');
  }, 0);
}

function kanbanDragEnd(event) {
  event.target.classList.remove('kanban-dragging');
  KanbanState.draggedTask = null;
  
  // Remove all drag-over styles
  document.querySelectorAll('.kanban-column').forEach(col => {
    col.classList.remove('kanban-drag-over');
  });
}

function kanbanDragOver(event, columnId) {
  event.preventDefault();
  event.dataTransfer.dropEffect = 'move';
  
  const column = event.currentTarget;
  column.classList.add('kanban-drag-over');
  KanbanState.dragOverColumn = columnId;
}

function kanbanDragLeave(event, columnId) {
  const column = event.currentTarget;
  // Only remove if we're actually leaving the column
  if (!column.contains(event.relatedTarget)) {
    column.classList.remove('kanban-drag-over');
  }
}

async function kanbanDrop(event, columnId) {
  event.preventDefault();
  const taskId = event.dataTransfer.getData('text/plain') || KanbanState.draggedTask;
  
  if (!taskId) return;
  
  // Remove drag-over style
  event.currentTarget.classList.remove('kanban-drag-over');
  
  // Update task status
  const task = KanbanState.tasks.find(t => String(t.id) === String(taskId));
  if (task) {
    task.status = columnId;
    
    // Save to API
    try {
      await fetch(`/api/tasks/${encodeURIComponent(taskId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: columnId })
      });
    } catch (e) {
      console.debug('Kanban: API save failed, using local state');
    }
    
    // Re-render
    renderKanban();
    toast('✅ Task moved', 'ok', 1500);
  }
  
  KanbanState.draggedTask = null;
}

// ── Touch Support for Mobile ──────────────────────────────────────
let kanbanTouchData = { startX: 0, startY: 0, taskId: null, clone: null };

function kanbanTouchStart(event) {
  const card = event.target.closest('.kanban-card');
  if (!card) return;
  
  const touch = event.touches[0];
  kanbanTouchData.startX = touch.clientX;
  kanbanTouchData.startY = touch.clientY;
  kanbanTouchData.taskId = card.dataset.taskId;
  
  // Long press to start drag
  kanbanTouchData.timeout = setTimeout(() => {
    card.classList.add('kanban-dragging');
    KanbanState.draggedTask = kanbanTouchData.taskId;
    
    // Create clone for visual feedback
    kanbanTouchData.clone = card.cloneNode(true);
    kanbanTouchData.clone.classList.add('kanban-touch-clone');
    kanbanTouchData.clone.style.position = 'fixed';
    kanbanTouchData.clone.style.pointerEvents = 'none';
    kanbanTouchData.clone.style.zIndex = '10000';
    kanbanTouchData.clone.style.width = card.offsetWidth + 'px';
    document.body.appendChild(kanbanTouchData.clone);
  }, 500);
}

function kanbanTouchMove(event) {
  if (!KanbanState.draggedTask) return;
  event.preventDefault();
  
  const touch = event.touches[0];
  if (kanbanTouchData.clone) {
    kanbanTouchData.clone.style.left = (touch.clientX - 50) + 'px';
    kanbanTouchData.clone.style.top = (touch.clientY - 20) + 'px';
  }
  
  // Find column under touch
  const element = document.elementFromPoint(touch.clientX, touch.clientY);
  const column = element?.closest('.kanban-column');
  
  document.querySelectorAll('.kanban-column').forEach(col => {
    col.classList.remove('kanban-drag-over');
  });
  
  if (column) {
    column.classList.add('kanban-drag-over');
    KanbanState.dragOverColumn = column.dataset.column;
  }
}

function kanbanTouchEnd(event) {
  clearTimeout(kanbanTouchData.timeout);
  
  if (kanbanTouchData.clone) {
    kanbanTouchData.clone.remove();
    kanbanTouchData.clone = null;
  }
  
  document.querySelectorAll('.kanban-card').forEach(card => {
    card.classList.remove('kanban-dragging');
  });
  
  if (KanbanState.draggedTask && KanbanState.dragOverColumn) {
    const task = KanbanState.tasks.find(t => String(t.id) === String(KanbanState.draggedTask));
    if (task) {
      task.status = KanbanState.dragOverColumn;
      renderKanban();
      toast('✅ Task moved', 'ok', 1500);
    }
  }
  
  KanbanState.draggedTask = null;
  KanbanState.dragOverColumn = null;
}

// ── Task Actions ──────────────────────────────────────────────────
function kanbanAddTask() {
  document.getElementById('kanban-add-modal').style.display = 'flex';
  document.getElementById('kanban-task-title').focus();
}

function kanbanAddTaskToColumn(columnId) {
  kanbanAddTask();
  document.getElementById('kanban-task-column').value = columnId;
}

function kanbanCloseModal() {
  document.getElementById('kanban-add-modal').style.display = 'none';
  // Clear form
  document.getElementById('kanban-task-title').value = '';
  document.getElementById('kanban-task-desc').value = '';
  document.getElementById('kanban-task-priority').value = 'medium';
  document.getElementById('kanban-task-assignee').value = '';
}

async function kanbanSaveTask() {
  const title = document.getElementById('kanban-task-title').value.trim();
  if (!title) {
    toast('⚠️ Title is required', 'warn');
    return;
  }
  
  const task = {
    id: Date.now().toString(),
    title: title,
    description: document.getElementById('kanban-task-desc').value.trim(),
    status: document.getElementById('kanban-task-column').value,
    priority: document.getElementById('kanban-task-priority').value,
    assignee: document.getElementById('kanban-task-assignee').value,
    created_at: new Date().toISOString()
  };
  
  // Save to API
  try {
    const response = await fetch('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(task)
    });
    const result = await response.json();
    if (result?.id) {
      task.id = result.id;
    }
  } catch (e) {
    console.debug('Kanban: API save failed, using local state');
  }
  
  KanbanState.tasks.push(task);
  kanbanCloseModal();
  renderKanban();
  toast('✅ Task created', 'ok');
}

function kanbanEditTask(taskId) {
  const task = KanbanState.tasks.find(t => String(t.id) === String(taskId));
  if (!task) return;
  
  // For now, just show a simple edit via prompt
  // In a full implementation, this would open a detailed edit modal
  const newTitle = prompt('Edit task title:', task.title);
  if (newTitle && newTitle !== task.title) {
    task.title = newTitle;
    
    // Save to API
    fetch(`/api/tasks/${encodeURIComponent(taskId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: newTitle })
    }).catch(() => {});
    
    renderKanban();
    toast('✅ Task updated', 'ok');
  }
}

async function kanbanDeleteTask(taskId) {
  if (!confirm('Delete this task?')) return;
  
  KanbanState.tasks = KanbanState.tasks.filter(t => String(t.id) !== String(taskId));
  
  // Delete from API
  try {
    await fetch(`/api/tasks/${encodeURIComponent(taskId)}`, { method: 'DELETE' });
  } catch (e) {
    console.debug('Kanban: API delete failed');
  }
  
  renderKanban();
  toast('🗑 Task deleted', 'ok');
}

function kanbanFilterToggle() {
  // Simple filter implementation
  const filter = prompt('Filter by priority (low/medium/high/urgent) or leave empty for all:');
  if (filter === null) return;
  
  if (filter === '') {
    renderKanban();
  } else {
    const filtered = KanbanState.tasks.filter(t => t.priority === filter.toLowerCase());
    // Re-render with filtered tasks
    const board = document.getElementById('kanban-board');
    if (board) {
      KanbanState.columns.forEach(col => {
        const colBody = document.getElementById(`kanban-col-${col.id}`);
        if (colBody) {
          const tasks = filtered.filter(t => t.status === col.id);
          colBody.innerHTML = tasks.map(task => renderKanbanCard(task)).join('') || `
            <div class="kanban-empty-column"><span>No tasks</span></div>
          `;
        }
      });
    }
  }
}

// ── Helper Functions ──────────────────────────────────────────────
function flattenKanbanData(data) {
  const tasks = [];
  for (const [status, columnTasks] of Object.entries(data)) {
    if (Array.isArray(columnTasks)) {
      columnTasks.forEach(task => {
        tasks.push({ ...task, status });
      });
    }
  }
  return tasks;
}

function getSampleTasks() {
  return [
    { id: '1', title: 'Design new landing page', description: 'Create a modern landing page with hero section', status: 'todo', priority: 'high', assignee: 'builder' },
    { id: '2', title: 'Fix authentication bug', description: 'Users getting logged out unexpectedly', status: 'in-progress', priority: 'urgent', assignee: 'brain' },
    { id: '3', title: 'Write API documentation', description: 'Document all REST endpoints', status: 'backlog', priority: 'medium', assignee: 'researcher' },
    { id: '4', title: 'Implement dark mode', description: 'Add theme switching capability', status: 'review', priority: 'low', assignee: 'builder' },
    { id: '5', title: 'Optimize database queries', description: 'Slow queries on user dashboard', status: 'done', priority: 'high', assignee: 'brain' },
    { id: '6', title: 'Add unit tests for auth module', description: 'Increase test coverage to 80%', status: 'todo', priority: 'medium', assignee: '' },
    { id: '7', title: 'Research competitor features', description: 'Analyze top 5 competitors', status: 'backlog', priority: 'low', assignee: 'researcher' },
    { id: '8', title: 'Setup CI/CD pipeline', description: 'GitHub Actions for auto deployment', status: 'in-progress', priority: 'high', assignee: 'builder' }
  ];
}

function getAssigneeAvatar(assignee) {
  const avatars = {
    builder: '⚡',
    brain: '🧠',
    researcher: '🔬',
    orchestrator: '🌀'
  };
  return avatars[assignee] || '👤';
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function formatDate(dateStr) {
  const date = new Date(dateStr);
  const now = new Date();
  const diff = date - now;
  const days = Math.ceil(diff / (1000 * 60 * 60 * 24));
  
  if (days < 0) return 'Overdue';
  if (days === 0) return 'Today';
  if (days === 1) return 'Tomorrow';
  if (days < 7) return `${days} days`;
  
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function isOverdue(dateStr) {
  return new Date(dateStr) < new Date();
}

// ── Global Functions (for onclick handlers) ───────────────────────
window.renderKanban = renderKanban;
window.kanbanDragStart = kanbanDragStart;
window.kanbanDragEnd = kanbanDragEnd;
window.kanbanDragOver = kanbanDragOver;
window.kanbanDragLeave = kanbanDragLeave;
window.kanbanDrop = kanbanDrop;
window.kanbanAddTask = kanbanAddTask;
window.kanbanAddTaskToColumn = kanbanAddTaskToColumn;
window.kanbanCloseModal = kanbanCloseModal;
window.kanbanSaveTask = kanbanSaveTask;
window.kanbanEditTask = kanbanEditTask;
window.kanbanDeleteTask = kanbanDeleteTask;
window.kanbanFilterToggle = kanbanFilterToggle;

console.log('%c✅ Kanban Board loaded', 'color:#22c55e;font-weight:bold');
