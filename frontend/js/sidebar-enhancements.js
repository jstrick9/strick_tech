// Agentic OS — Sidebar Enhancements v6
// No favorites, no star icons - clean sidebar
'use strict';

// ── Sidebar State ────────────────────────────────────────────────
const SidebarState = {
  minWidth: 56,
  maxWidth: 400,
  defaultWidth: 240,
  collapsedWidth: 56,
  isResizing: false,
  startX: 0,
  startWidth: 0
};

// ── Initialize Sidebar ───────────────────────────────────────────
function initSidebar() {
  const savedWidth = localStorage.getItem('agentic_os_sidebar_width');
  if (savedWidth) {
    const width = parseInt(savedWidth);
    if (width >= SidebarState.minWidth && width <= SidebarState.maxWidth) {
      setSidebarWidth(width);
    }
  }

  const isCollapsed = localStorage.getItem('agentic_os_sidebar_collapsed') === 'true';
  if (isCollapsed) {
    const sidebar = document.getElementById('sidebar');
    if (sidebar) {
      sidebar.classList.add('collapsed');
      sidebar.style.width = SidebarState.collapsedWidth + 'px';
    }
  }

  setupSidebarResizer();
  setupGroupTooltips();
  ensureDefaultState();
  
  // Remove any existing favorite buttons and sections
  removeAllFavorites();
  
  console.log('✅ Sidebar v6 loaded');
}

// ── Remove All Favorites ─────────────────────────────────────────
function removeAllFavorites() {
  // Remove favorite buttons from nav items
  document.querySelectorAll('.nav-fav-btn, .nav-star-btn').forEach(btn => btn.remove());
  
  // Remove favorites section
  const favSection = document.getElementById('sidebar-favorites-section');
  if (favSection) favSection.remove();
}

// ── Ensure Default State ─────────────────────────────────────────
function ensureDefaultState() {
  const coreContent = document.getElementById('group-core');
  const coreArrow = document.getElementById('arrow-core');
  if (coreContent) coreContent.style.display = 'block';
  if (coreArrow) coreArrow.textContent = '▼';

  ['build', 'ship', 'tools', 'enterprise'].forEach(gid => {
    const content = document.getElementById('group-' + gid);
    const arrow = document.getElementById('arrow-' + gid);
    if (content) content.style.display = 'none';
    if (arrow) arrow.textContent = '▶';
  });
}

// ── Drag-to-Resize ───────────────────────────────────────────────
function setupSidebarResizer() {
  const resizer = document.getElementById('sidebar-resizer');
  const sidebar = document.getElementById('sidebar');
  if (!resizer || !sidebar) return;

  resizer.addEventListener('mousedown', startResize);
  document.addEventListener('mousemove', doResize);
  document.addEventListener('mouseup', stopResize);
  resizer.addEventListener('touchstart', startResize, { passive: false });
  document.addEventListener('touchmove', doResize, { passive: false });
  document.addEventListener('touchend', stopResize);
  resizer.addEventListener('dblclick', () => {
    setSidebarWidth(SidebarState.defaultWidth);
    if (typeof toast === 'function') toast('Sidebar width reset', 'ok');
  });
}

function startResize(e) {
  e.preventDefault();
  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;
  SidebarState.isResizing = true;
  SidebarState.startX = e.clientX || (e.touches?.[0]?.clientX) || 0;
  SidebarState.startWidth = sidebar.offsetWidth;
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
  sidebar.style.transition = 'none';
  document.getElementById('sidebar-resizer')?.classList.add('resizing');
}

function doResize(e) {
  if (!SidebarState.isResizing) return;
  e.preventDefault();
  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;
  const clientX = e.clientX || (e.touches?.[0]?.clientX) || 0;
  const diff = clientX - SidebarState.startX;
  const newWidth = Math.min(SidebarState.maxWidth, Math.max(SidebarState.minWidth, SidebarState.startWidth + diff));
  setSidebarWidth(newWidth);
}

function stopResize() {
  if (!SidebarState.isResizing) return;
  SidebarState.isResizing = false;
  document.body.style.cursor = '';
  document.body.style.userSelect = '';
  const sidebar = document.getElementById('sidebar');
  const resizer = document.getElementById('sidebar-resizer');
  if (sidebar) sidebar.style.transition = '';
  if (resizer) resizer.classList.remove('resizing');
  const width = sidebar ? sidebar.offsetWidth : SidebarState.defaultWidth;
  localStorage.setItem('agentic_os_sidebar_width', width.toString());
}

function setSidebarWidth(width) {
  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;
  sidebar.style.width = width + 'px';
  const isCollapsed = width <= SidebarState.collapsedWidth;
  sidebar.classList.toggle('collapsed', isCollapsed);
  const collapseBtn = document.getElementById('sidebar-toggle-btn');
  if (collapseBtn) {
    collapseBtn.textContent = isCollapsed ? '▶' : '◀';
    collapseBtn.title = isCollapsed ? 'Expand sidebar (Ctrl+B)' : 'Collapse sidebar (Ctrl+B)';
  }
  localStorage.setItem('agentic_os_sidebar_collapsed', isCollapsed ? 'true' : 'false');
}

// ── Group Tooltips ───────────────────────────────────────────────
function setupGroupTooltips() {
  const tooltipDescriptions = {
    'ESSENTIALS': 'Core features for everyday use. Chat with AI, write code, manage tasks, and customize your experience.',
    'AI TOOLS': 'AI-powered capabilities for research, coding, and creativity. Swarm, web search, image generation, and more.',
    'BUILD': 'Tools to build, test, and ship your projects. Code editor, pipelines, GitHub, and deployment.',
    'AGENTS': 'Manage AI agents and their workflows. Supervisors, goals, integrations, and autonomous loops.',
    'MONITORING': 'Track performance, costs, and security. Dashboards, audit logs, health checks, and encryption.'
  };
  
  document.querySelectorAll('.sidebar-help-tip').forEach(tip => {
    const parentText = tip.parentElement?.textContent || '';
    let description = tip.getAttribute('data-tip') || '';
    
    for (const [key, desc] of Object.entries(tooltipDescriptions)) {
      if (parentText.includes(key)) {
        description = desc;
        break;
      }
    }
    
    const tooltip = document.createElement('div');
    tooltip.className = 'sidebar-tooltip-popup';
    tooltip.textContent = description;
    
    tip.style.position = 'relative';
    tip.appendChild(tooltip);

    tip.addEventListener('mouseenter', () => {
      tooltip.style.opacity = '1';
      tooltip.style.visibility = 'visible';
    });
    tip.addEventListener('mouseleave', () => {
      tooltip.style.opacity = '0';
      tooltip.style.visibility = 'hidden';
    });
  });
}

// ── Keyboard Shortcut ────────────────────────────────────────────
document.addEventListener('keydown', function(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
    e.preventDefault();
    const toggleBtn = document.getElementById('sidebar-toggle-btn');
    if (toggleBtn) toggleBtn.click();
  }
});

// ── CSS ──────────────────────────────────────────────────────────
const sidebarStyles = document.createElement('style');
sidebarStyles.textContent = `
  /* Resizer */
  #sidebar-resizer {
    width: 4px;
    cursor: col-resize;
    background: transparent;
    transition: background 0.15s;
    flex-shrink: 0;
    position: relative;
    z-index: 10;
  }
  #sidebar-resizer:hover, #sidebar-resizer.resizing {
    background: var(--accent, #6366f1);
  }
  #sidebar-resizer.resizing {
    width: 6px;
    margin-left: -1px;
  }

  /* Collapse button */
  #sidebar-toggle-btn {
    width: 24px;
    height: 24px;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: var(--text-3, #666);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    transition: all 0.15s;
    flex-shrink: 0;
  }
  #sidebar-toggle-btn:hover {
    background: var(--bg-3, #222);
    color: var(--text-0, #fff);
  }

  /* Help tip */
  .sidebar-help-tip {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--bg-3, #222);
    border: 1px solid var(--border, rgba(255,255,255,0.06));
    color: var(--text-3, #666);
    font-size: 10px;
    font-weight: 700;
    cursor: help;
    margin-left: 4px;
    flex-shrink: 0;
    position: relative;
  }
  .sidebar-help-tip:hover {
    background: var(--accent-glow, rgba(99,102,241,0.15));
    border-color: var(--accent, #6366f1);
    color: var(--accent, #6366f1);
  }

  /* Tooltip */
  .sidebar-tooltip-popup {
    position: absolute;
    left: calc(100% + 4px);
    top: 0;
    background: var(--bg-4, #2a2a2a);
    color: var(--text-0, #fff);
    padding: 10px 14px;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 500;
    line-height: 1.5;
    width: 220px;
    pointer-events: none;
    opacity: 0;
    visibility: hidden;
    transition: opacity 0.15s, visibility 0.15s;
    z-index: 1000;
    box-shadow: 0 4px 16px rgba(0,0,0,0.5);
    border: 1px solid var(--border-hi, rgba(255,255,255,0.12));
  }

  /* Collapsed sidebar */
  #sidebar.collapsed {
    width: 56px !important;
  }
  #sidebar.collapsed .label,
  #sidebar.collapsed .sidebar-group-label,
  #sidebar.collapsed .count,
  #sidebar.collapsed .badge,
  #sidebar.collapsed .sidebar-help-tip,
  #sidebar.collapsed .agent-info,
  #sidebar.collapsed #sidebar-nav-label,
  #sidebar.collapsed #sidebar-agents-section > div:first-child {
    display: none !important;
  }
  #sidebar.collapsed .nav-item {
    justify-content: center;
    padding: 10px;
  }
  #sidebar.collapsed .nav-item .icon {
    font-size: 18px;
  }

  /* Agents section */
  #sidebar-agents-section {
    border-top: 1px solid var(--border, rgba(255,255,255,0.06));
    padding: 8px;
    flex-shrink: 0;
    max-height: 200px;
    overflow-y: auto;
  }
`;

document.head.appendChild(sidebarStyles);

// ── Initialize ───────────────────────────────────────────────────
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSidebar);
} else {
  setTimeout(initSidebar, 100);
}

// ── Global Exports ────────────────────────────────────────────────
window.initSidebar = initSidebar;
window.setSidebarWidth = setSidebarWidth;
window.ensureDefaultState = ensureDefaultState;

console.log('%c✅ Sidebar v6 loaded', 'color:#22c55e;font-weight:bold');
