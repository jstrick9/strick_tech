// Agentic OS — Sidebar Enhancements
// Drag-to-resize, collapse toggle, favorites, and more
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
  // Restore saved width
  const savedWidth = localStorage.getItem('agentic_os_sidebar_width');
  if (savedWidth) {
    const width = parseInt(savedWidth);
    if (width >= SidebarState.minWidth && width <= SidebarState.maxWidth) {
      setSidebarWidth(width);
    }
  }

  // Setup drag-to-resize
  setupSidebarResizer();
  
  // Setup collapse toggle
  setupCollapseToggle();
  
  // Setup favorites/pins
  setupFavorites();
  
  console.log('✅ Sidebar enhancements loaded');
}

// ── Drag-to-Resize ───────────────────────────────────────────────
function setupSidebarResizer() {
  const resizer = document.getElementById('sidebar-resizer');
  const sidebar = document.getElementById('sidebar');
  
  if (!resizer || !sidebar) return;

  // Mouse events
  resizer.addEventListener('mousedown', startResize);
  document.addEventListener('mousemove', doResize);
  document.addEventListener('mouseup', stopResize);

  // Touch events for mobile
  resizer.addEventListener('touchstart', startResize, { passive: false });
  document.addEventListener('touchmove', doResize, { passive: false });
  document.addEventListener('touchend', stopResize);

  // Double-click to reset width
  resizer.addEventListener('dblclick', function() {
    setSidebarWidth(SidebarState.defaultWidth);
    toast('Sidebar width reset', 'ok');
  });
}

function startResize(e) {
  e.preventDefault();
  
  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;

  SidebarState.isResizing = true;
  SidebarState.startX = e.clientX || (e.touches && e.touches[0].clientX) || 0;
  SidebarState.startWidth = sidebar.offsetWidth;

  // Add visual feedback
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
  sidebar.style.transition = 'none';
  
  // Add resize class for CSS feedback
  resizer.classList.add('resizing');
}

function doResize(e) {
  if (!SidebarState.isResizing) return;
  e.preventDefault();

  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;

  const clientX = e.clientX || (e.touches && e.touches[0].clientX) || 0;
  const diff = clientX - SidebarState.startX;
  const newWidth = Math.min(SidebarState.maxWidth, 
                   Math.max(SidebarState.minWidth, 
                           SidebarState.startWidth + diff));

  setSidebarWidth(newWidth);
}

function stopResize() {
  if (!SidebarState.isResizing) return;

  SidebarState.isResizing = false;

  const sidebar = document.getElementById('sidebar');
  const resizer = document.getElementById('sidebar-resizer');

  // Remove visual feedback
  document.body.style.cursor = '';
  document.body.style.userSelect = '';
  
  if (sidebar) {
    sidebar.style.transition = '';
  }
  
  if (resizer) {
    resizer.classList.remove('resizing');
  }

  // Save width
  const width = sidebar ? sidebar.offsetWidth : SidebarState.defaultWidth;
  localStorage.setItem('agentic_os_sidebar_width', width.toString());
}

function setSidebarWidth(width) {
  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;

  sidebar.style.width = width + 'px';
  
  // Update collapsed state
  const isCollapsed = width <= SidebarState.collapsedWidth;
  sidebar.classList.toggle('collapsed', isCollapsed);
  
  // Update collapse button icon
  const collapseBtn = document.getElementById('sidebar-collapse-btn');
  if (collapseBtn) {
    collapseBtn.textContent = isCollapsed ? '▶' : '◀';
    collapseBtn.title = isCollapsed ? 'Expand sidebar' : 'Collapse sidebar';
  }
}

// ── Collapse Toggle ──────────────────────────────────────────────
function setupCollapseToggle() {
  const collapseBtn = document.getElementById('sidebar-collapse-btn');
  if (!collapseBtn) return;

  collapseBtn.addEventListener('click', function() {
    const sidebar = document.getElementById('sidebar');
    if (!sidebar) return;

    const isCollapsed = sidebar.classList.contains('collapsed');
    
    if (isCollapsed) {
      // Expand to saved width or default
      const savedWidth = parseInt(localStorage.getItem('agentic_os_sidebar_width')) || SidebarState.defaultWidth;
      setSidebarWidth(savedWidth);
    } else {
      // Collapse
      setSidebarWidth(SidebarState.collapsedWidth);
    }
  });
}

// ── Favorites / Pins ─────────────────────────────────────────────
function setupFavorites() {
  // Load favorites from localStorage
  const favorites = JSON.parse(localStorage.getItem('agentic_os_favorites') || '[]');
  
  // Add favorite buttons to nav items
  document.querySelectorAll('.nav-item').forEach(item => {
    const navId = item.dataset.nav;
    if (!navId) return;

    // Check if already has favorite button
    if (item.querySelector('.nav-favorite')) return;

    const favBtn = document.createElement('button');
    favBtn.className = 'nav-favorite';
    favBtn.innerHTML = favorites.includes(navId) ? '⭐' : '☆';
    favBtn.title = favorites.includes(navId) ? 'Remove from favorites' : 'Add to favorites';
    favBtn.style.cssText = `
      background: none;
      border: none;
      cursor: pointer;
      font-size: 12px;
      padding: 2px;
      opacity: 0;
      transition: opacity 0.15s;
      margin-left: auto;
    `;

    // Show on hover
    item.addEventListener('mouseenter', () => favBtn.style.opacity = '1');
    item.addEventListener('mouseleave', () => favBtn.style.opacity = '0');

    // Toggle favorite
    favBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      toggleFavorite(navId, favBtn);
    });

    item.appendChild(favBtn);
  });
}

function toggleFavorite(navId, btn) {
  let favorites = JSON.parse(localStorage.getItem('agentic_os_favorites') || '[]');
  
  if (favorites.includes(navId)) {
    favorites = favorites.filter(id => id !== navId);
    btn.innerHTML = '☆';
    btn.title = 'Add to favorites';
    toast('Removed from favorites', 'ok');
  } else {
    favorites.push(navId);
    btn.innerHTML = '⭐';
    btn.title = 'Remove from favorites';
    toast('Added to favorites', 'ok');
  }
  
  localStorage.setItem('agentic_os_favorites', JSON.stringify(favorites));
  
  // Reorganize sidebar to show favorites at top
  reorganizeSidebar();
}

function reorganizeSidebar() {
  const favorites = JSON.parse(localStorage.getItem('agentic_os_favorites') || '[]');
  const sidebar = document.querySelector('.sidebar-scroll');
  if (!sidebar || favorites.length === 0) return;

  // Find or create favorites section
  let favSection = document.getElementById('sidebar-favorites');
  if (!favSection) {
    favSection = document.createElement('div');
    favSection.id = 'sidebar-favorites';
    favSection.innerHTML = `
      <div class="sidebar-group-label" style="color: #f59e0b;">
        <span>⭐</span> FAVORITES
      </div>
      <div id="favorites-list"></div>
    `;
    sidebar.insertBefore(favSection, sidebar.firstChild.nextSibling);
  }

  const favList = document.getElementById('favorites-list');
  if (!favList) return;

  // Move favorite items to top
  favorites.forEach(navId => {
    const item = document.querySelector(`.nav-item[data-nav="${navId}"]`);
    if (item && !favList.contains(item)) {
      favList.appendChild(item.cloneNode(true));
    }
  });
}

// ── Keyboard Shortcut ────────────────────────────────────────────
document.addEventListener('keydown', function(e) {
  // Ctrl+B or Cmd+B to toggle sidebar
  if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
    e.preventDefault();
    const collapseBtn = document.getElementById('sidebar-collapse-btn');
    if (collapseBtn) collapseBtn.click();
  }
});

// ── CSS for Resizer ──────────────────────────────────────────────
const resizerStyles = document.createElement('style');
resizerStyles.textContent = `
  #sidebar-resizer {
    width: 4px;
    cursor: col-resize;
    background: transparent;
    transition: background 0.15s;
    flex-shrink: 0;
    position: relative;
    z-index: 10;
  }

  #sidebar-resizer:hover,
  #sidebar-resizer.resizing {
    background: var(--accent, #6366f1);
  }

  #sidebar-resizer.resizing {
    width: 6px;
    margin-left: -1px;
  }

  /* Collapse button styling */
  #sidebar-collapse-btn {
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

  #sidebar-collapse-btn:hover {
    background: var(--bg-3, #222);
    color: var(--text-0, #fff);
  }

  /* Favorite button */
  .nav-favorite {
    opacity: 0;
    transition: opacity 0.15s;
  }

  .nav-item:hover .nav-favorite {
    opacity: 1;
  }

  /* Collapsed sidebar styles */
  #sidebar.collapsed {
    width: 56px !important;
  }

  #sidebar.collapsed .label,
  #sidebar.collapsed .sidebar-group-label,
  #sidebar.collapsed .count,
  #sidebar.collapsed .badge,
  #sidebar.collapsed .help-tip,
  #sidebar.collapsed .nav-favorite,
  #sidebar.collapsed .agent-info,
  #sidebar.collapsed #sidebar-top-nav-header > span:first-child {
    display: none !important;
  }

  #sidebar.collapsed .nav-item {
    justify-content: center;
    padding: 10px;
  }

  #sidebar.collapsed .nav-item .icon {
    font-size: 18px;
  }

  #sidebar.collapsed .sidebar-add-agent span:last-child {
    display: none;
  }

  /* Agents section - compact */
  #sidebar-agents-section {
    border-top: 1px solid var(--border, rgba(255,255,255,0.06));
    padding: 8px;
    flex-shrink: 0;
    max-height: 200px;
    overflow-y: auto;
  }

  #sidebar-agents-section .sidebar-label {
    font-size: 10px;
    font-weight: 600;
    color: var(--text-3, #666);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 4px 8px 8px;
  }
`;

document.head.appendChild(resizerStyles);

// ── Initialize on DOM Ready ──────────────────────────────────────
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSidebar);
} else {
  initSidebar();
}

// ── Global Exports ────────────────────────────────────────────────
window.initSidebar = initSidebar;
window.setSidebarWidth = setSidebarWidth;
window.toggleFavorite = toggleFavorite;

console.log('%c✅ Sidebar enhancements loaded', 'color:#22c55e;font-weight:bold');
