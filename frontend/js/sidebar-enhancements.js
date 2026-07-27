// Agentic OS — Sidebar Enhancements v2
// Fixed: favorites section, tooltip positioning, proper descriptions
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
  
  // Ensure only ESSENTIALS is expanded by default
  ensureDefaultState();
  
  console.log('✅ Sidebar enhancements loaded');
}

// ── Ensure Default State ─────────────────────────────────────────
function ensureDefaultState() {
  // Only expand ESSENTIALS, collapse all others
  const groups = ['build', 'ship', 'tools', 'enterprise'];
  groups.forEach(gid => {
    const content = document.getElementById('group-' + gid);
    const arrow = document.getElementById('arrow-' + gid);
    if (content) content.style.display = 'none';
    if (arrow) arrow.textContent = '▶';
  });
  
  // Ensure ESSENTIALS is expanded
  const coreContent = document.getElementById('group-core');
  const coreArrow = document.getElementById('arrow-core');
  if (coreContent) coreContent.style.display = 'block';
  if (coreArrow) coreArrow.textContent = '▼';
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

  document.body.style.cursor = '';
  document.body.style.userSelect = '';
  
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

// ── Favorites / Pins ─────────────────────────────────────────────
function setupFavorites() {
  const favorites = JSON.parse(localStorage.getItem('agentic_os_favorites') || '[]');
  
  // Create favorites section if it doesn't exist and there are favorites
  if (favorites.length > 0) {
    createFavoritesSection(favorites);
  }
  
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
    favBtn.setAttribute('data-favorited', isFav ? 'true' : 'false');

    // Show on hover (always show if favorited)
    if (!isFav) {
      item.addEventListener('mouseenter', function() {
        favBtn.style.opacity = '1';
      });
      item.addEventListener('mouseleave', function() {
        favBtn.style.opacity = '0';
      });
    }

    // Toggle favorite on click - STOP PROPAGATION is critical!
    favBtn.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();
      toggleFavorite(navId, favBtn, item);
      return false;
    });

    item.appendChild(favBtn);
  });
}

function toggleFavorite(navId, btn, navItem) {
  let favorites = JSON.parse(localStorage.getItem('agentic_os_favorites') || '[]');
  
  if (favorites.includes(navId)) {
    // Remove from favorites
    favorites = favorites.filter(id => id !== navId);
    btn.innerHTML = '☆';
    btn.title = 'Add to favorites';
    btn.setAttribute('data-favorited', 'false');
    btn.style.opacity = '0';
    if (typeof toast === 'function') toast('Removed from favorites', 'ok');
  } else {
    // Add to favorites
    favorites.push(navId);
    btn.innerHTML = '⭐';
    btn.title = 'Remove from favorites';
    btn.setAttribute('data-favorited', 'true');
    btn.style.opacity = '1';
    if (typeof toast === 'function') toast('Added to favorites', 'ok');
  }
  
  localStorage.setItem('agentic_os_favorites', JSON.stringify(favorites));
  
  // Update favorites section
  createFavoritesSection(favorites);
}

function createFavoritesSection(favorites) {
  // Remove existing favorites section
  const existing = document.getElementById('sidebar-favorites-section');
  if (existing) existing.remove();
  
  if (favorites.length === 0) return;
  
  const sidebarScroll = document.querySelector('.sidebar-scroll');
  if (!sidebarScroll) return;
  
  // Create favorites section
  const favSection = document.createElement('div');
  favSection.id = 'sidebar-favorites-section';
  favSection.style.cssText = 'padding: 4px 0; border-bottom: 1px solid var(--border); margin-bottom: 4px;';
  
  let html = '<div class="sidebar-group-label" style="color: #f59e0b; font-size: 10px; padding: 8px 12px 4px;">⭐ FAVORITES</div>';
  
  favorites.forEach(navId => {
    const originalItem = document.querySelector(`.nav-item[data-nav="${navId}"]`);
    if (originalItem) {
      const icon = originalItem.querySelector('.icon')?.textContent || '📌';
      const label = originalItem.querySelector('.label')?.textContent || navId;
      html += `<div class="nav-item" data-nav="${navId}" onclick="nav('${navId}')" style="padding: 6px 12px;">
        <span class="icon">${icon}</span>
        <span class="label">${label}</span>
      </div>`;
    }
  });
  
  favSection.innerHTML = html;
  
  // Insert at the top of sidebar scroll
  sidebarScroll.insertBefore(favSection, sidebarScroll.firstChild);
}

// ── Group Tooltips ───────────────────────────────────────────────
function setupGroupTooltips() {
  const tooltipDescriptions = {
    'ESSENTIALS': 'Core features for everyday use. Start here to chat with AI, write code, manage tasks, and customize your experience.',
    'AI TOOLS': 'AI-powered capabilities for research, coding, and creativity. Includes multi-agent swarm, web search, image generation, and more.',
    'BUILD': 'Tools to build, test, and ship your projects. Includes code editor, pipelines, GitHub integration, and deployment.',
    'AGENTS': 'Manage AI agents and their workflows. Configure supervisors, goals, integrations, and autonomous loops.',
    'MONITORING': 'Track performance, costs, and security. Includes dashboards, audit logs, health checks, and encryption.'
  };
  
  document.querySelectorAll('.sidebar-help-tip').forEach(tip => {
    const parentLabel = tip.parentElement?.textContent?.trim() || '';
    let description = tip.getAttribute('data-tip') || '';
    
    // Use better description if available
    for (const [key, desc] of Object.entries(tooltipDescriptions)) {
      if (parentLabel.includes(key)) {
        description = desc;
        break;
      }
    }
    
    // Create tooltip element
    const tooltip = document.createElement('div');
    tooltip.className = 'sidebar-tooltip-popup';
    tooltip.textContent = description;
    
    // Position the tip container
    tip.style.position = 'relative';
    tip.appendChild(tooltip);

    // Show/hide on hover
    tip.addEventListener('mouseenter', function() {
      tooltip.style.opacity = '1';
      tooltip.style.visibility = 'visible';
    });
    tip.addEventListener('mouseleave', function() {
      tooltip.style.opacity = '0';
      tooltip.style.visibility = 'hidden';
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

  /* Tooltip popup - positioned to fit in sidebar */
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
  #sidebar.collapsed #sidebar-favorites-section,
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

  /* Favorites section */
  #sidebar-favorites-section {
    padding: 4px 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 4px;
  }

  #sidebar-favorites-section .nav-item {
    padding: 6px 12px;
  }
`;

document.head.appendChild(sidebarStyles);

// ── Initialize on DOM Ready ──────────────────────────────────────
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSidebar);
} else {
  setTimeout(initSidebar, 100);
}

// ── Global Exports ────────────────────────────────────────────────
window.initSidebar = initSidebar;
window.setSidebarWidth = setSidebarWidth;
window.toggleFavorite = toggleFavorite;
window.ensureDefaultState = ensureDefaultState;

console.log('%c✅ Sidebar enhancements v2 loaded', 'color:#22c55e;font-weight:bold');
