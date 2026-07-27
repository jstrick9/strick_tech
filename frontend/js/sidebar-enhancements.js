// Agentic OS — Sidebar Enhancements
// Drag-to-resize, collapse toggle, favorites, tooltips
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

  // Check if sidebar should be collapsed
  const isCollapsed = localStorage.getItem('agentic_os_sidebar_collapsed') === 'true';
  if (isCollapsed) {
    const sidebar = document.getElementById('sidebar');
    if (sidebar) {
      sidebar.classList.add('collapsed');
      sidebar.style.width = SidebarState.collapsedWidth + 'px';
    }
  }

  // Setup drag-to-resize
  setupSidebarResizer();
  
  // Setup favorites/pins
  setupFavorites();
  
  // Setup tooltips for group labels
  setupGroupTooltips();
  
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
    if (typeof toast === 'function') toast('Sidebar width reset', 'ok');
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
  
  const resizer = document.getElementById('sidebar-resizer');
  if (resizer) resizer.classList.add('resizing');
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
  const collapseBtn = document.getElementById('sidebar-toggle-btn');
  if (collapseBtn) {
    collapseBtn.textContent = isCollapsed ? '▶' : '◀';
    collapseBtn.title = isCollapsed ? 'Expand sidebar (Ctrl+B)' : 'Collapse sidebar (Ctrl+B)';
  }
  
  // Save collapsed state
  localStorage.setItem('agentic_os_sidebar_collapsed', isCollapsed ? 'true' : 'false');
}

// ── Favorites / Pins ─────────────────────────────────────────────
function setupFavorites() {
  // Load favorites from localStorage
  const favorites = JSON.parse(localStorage.getItem('agentic_os_favorites') || '[]');
  
  // Add favorite buttons to nav items
  document.querySelectorAll('.nav-item[data-nav]').forEach(item => {
    const navId = item.dataset.nav;
    if (!navId) return;

    // Check if already has favorite button
    if (item.querySelector('.nav-favorite')) return;

    const isFav = favorites.includes(navId);
    
    const favBtn = document.createElement('button');
    favBtn.className = 'nav-favorite';
    favBtn.type = 'button';
    favBtn.innerHTML = isFav ? '⭐' : '☆';
    favBtn.title = isFav ? 'Remove from favorites' : 'Add to favorites';
    favBtn.setAttribute('data-nav-id', navId);
    favBtn.style.cssText = `
      background: none;
      border: none;
      cursor: pointer;
      font-size: 12px;
      padding: 2px 4px;
      opacity: ${isFav ? '1' : '0'};
      transition: opacity 0.15s;
      margin-left: auto;
      flex-shrink: 0;
      line-height: 1;
    `;

    // Show on hover
    item.addEventListener('mouseenter', function() {
      favBtn.style.opacity = '1';
    });
    item.addEventListener('mouseleave', function() {
      if (!favorites.includes(navId)) {
        favBtn.style.opacity = '0';
      }
    });

    // Toggle favorite on click
    favBtn.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      toggleFavorite(navId, favBtn);
    });

    item.appendChild(favBtn);
  });
}

function toggleFavorite(navId, btn) {
  let favorites = JSON.parse(localStorage.getItem('agentic_os_favorites') || '[]');
  
  if (favorites.includes(navId)) {
    // Remove from favorites
    favorites = favorites.filter(id => id !== navId);
    btn.innerHTML = '☆';
    btn.title = 'Add to favorites';
    btn.style.opacity = '0';
    if (typeof toast === 'function') toast('Removed from favorites', 'ok');
  } else {
    // Add to favorites
    favorites.push(navId);
    btn.innerHTML = '⭐';
    btn.title = 'Remove from favorites';
    btn.style.opacity = '1';
    if (typeof toast === 'function') toast('Added to favorites', 'ok');
  }
  
  localStorage.setItem('agentic_os_favorites', JSON.stringify(favorites));
}

// ── Group Tooltips ───────────────────────────────────────────────
function setupGroupTooltips() {
  document.querySelectorAll('.sidebar-help-tip').forEach(tip => {
    // Create tooltip element
    const tooltip = document.createElement('div');
    tooltip.className = 'sidebar-tooltip';
    tooltip.textContent = tip.getAttribute('data-tip');
    tooltip.style.cssText = `
      position: absolute;
      left: calc(100% + 8px);
      top: 50%;
      transform: translateY(-50%);
      background: var(--bg-4, #2a2a2a);
      color: var(--text-0, #fff);
      padding: 8px 12px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 500;
      line-height: 1.4;
      white-space: nowrap;
      max-width: 280px;
      white-space: normal;
      pointer-events: none;
      opacity: 0;
      transition: opacity 0.15s;
      z-index: 1000;
      box-shadow: 0 4px 12px rgba(0,0,0,0.4);
      border: 1px solid var(--border-hi, rgba(255,255,255,0.12));
    `;

    // Position the tip container
    tip.style.position = 'relative';
    tip.appendChild(tooltip);

    // Show/hide on hover
    tip.addEventListener('mouseenter', function() {
      tooltip.style.opacity = '1';
    });
    tip.addEventListener('mouseleave', function() {
      tooltip.style.opacity = '0';
    });
  });
}

// ── Keyboard Shortcut ────────────────────────────────────────────
document.addEventListener('keydown', function(e) {
  // Ctrl+B or Cmd+B to toggle sidebar
  if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
    e.preventDefault();
    const toggleBtn = document.getElementById('sidebar-toggle-btn');
    if (toggleBtn) toggleBtn.click();
  }
});

// ── CSS for Sidebar Enhancements ─────────────────────────────────
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

  #sidebar-resizer:hover,
  #sidebar-resizer.resizing {
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

  /* Help tip icon */
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

  /* Favorite button */
  .nav-favorite {
    opacity: 0;
    transition: opacity 0.15s;
    background: none;
    border: none;
    cursor: pointer;
    font-size: 12px;
    padding: 2px 4px;
    margin-left: auto;
    flex-shrink: 0;
    line-height: 1;
  }

  .nav-item:hover .nav-favorite {
    opacity: 1;
  }

  .nav-favorite[data-favorited="true"] {
    opacity: 1;
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
  #sidebar.collapsed .nav-favorite,
  #sidebar.collapsed .agent-info,
  #sidebar.collapsed #sidebar-nav-label,
  #sidebar.collapsed #sidebar-agents-section span:first-child {
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

  /* Agents section compact */
  #sidebar-agents-section {
    border-top: 1px solid var(--border, rgba(255,255,255,0.06));
    padding: 8px;
    flex-shrink: 0;
    max-height: 200px;
    overflow-y: auto;
  }
`;

document.head.appendChild(sidebarStyles);

// ── Initialize on DOM Ready ──────────────────────────────────────
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSidebar);
} else {
  // DOM already loaded, init after a short delay to ensure other scripts are ready
  setTimeout(initSidebar, 100);
}

// ── Global Exports ────────────────────────────────────────────────
window.initSidebar = initSidebar;
window.setSidebarWidth = setSidebarWidth;
window.toggleFavorite = toggleFavorite;

console.log('%c✅ Sidebar enhancements loaded', 'color:#22c55e;font-weight:bold');
