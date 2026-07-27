// Agentic OS — Sidebar Enhancements v4
// Fixed: stars only on ESSENTIALS, arrow directions correct
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
  setupFavorites();
  setupGroupTooltips();
  ensureDefaultState();
  
  console.log('✅ Sidebar v4 loaded');
}

// ── Ensure Default State ─────────────────────────────────────────
function ensureDefaultState() {
  // ESSENTIALS expanded, all others collapsed
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

// ── Favorites System (ONLY for ESSENTIALS items) ─────────────────
function setupFavorites() {
  const favorites = getFavorites();
  
  if (favorites.length > 0) {
    createFavoritesSection(favorites);
  }
  
  // ONLY add star buttons to ESSENTIALS items (data-tier="core")
  document.querySelectorAll('.nav-item[data-nav][data-tier="core"]').forEach(item => {
    addStarButton(item);
  });
}

function getFavorites() {
  try {
    return JSON.parse(localStorage.getItem('agentic_os_favorites') || '[]');
  } catch {
    return [];
  }
}

function saveFavorites(favorites) {
  localStorage.setItem('agentic_os_favorites', JSON.stringify(favorites));
}

function addStarButton(navItem) {
  const navId = navItem.dataset.nav;
  if (!navId) return;
  if (navItem.querySelector('.nav-star-btn')) return;

  const favorites = getFavorites();
  const isFav = favorites.includes(navId);
  
  const starBtn = document.createElement('button');
  starBtn.className = 'nav-star-btn';
  starBtn.type = 'button';
  starBtn.innerHTML = isFav ? '⭐' : '☆';
  starBtn.title = isFav ? 'Click to remove from favorites' : 'Click to add to favorites';
  starBtn.setAttribute('data-nav-id', navId);

  starBtn.style.cssText = `
    background: none;
    border: none;
    cursor: pointer;
    font-size: 14px;
    padding: 2px 6px;
    margin-left: auto;
    flex-shrink: 0;
    line-height: 1;
    opacity: ${isFav ? '1' : '0'};
    transition: opacity 0.15s;
    z-index: 10;
    position: relative;
  `;

  navItem.addEventListener('mouseenter', () => starBtn.style.opacity = '1');
  navItem.addEventListener('mouseleave', () => {
    if (!getFavorites().includes(navId)) {
      starBtn.style.opacity = '0';
    }
  });

  starBtn.addEventListener('click', function(e) {
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    
    const currentFavs = getFavorites();
    const isCurrentlyFav = currentFavs.includes(navId);
    
    if (isCurrentlyFav) {
      const newFavs = currentFavs.filter(id => id !== navId);
      saveFavorites(newFavs);
      this.innerHTML = '☆';
      this.title = 'Click to add to favorites';
      this.style.opacity = '0';
      if (typeof toast === 'function') toast('Removed from favorites', 'ok');
    } else {
      currentFavs.push(navId);
      saveFavorites(currentFavs);
      this.innerHTML = '⭐';
      this.title = 'Click to remove from favorites';
      this.style.opacity = '1';
      if (typeof toast === 'function') toast('Added to favorites', 'ok');
    }
    
    createFavoritesSection(getFavorites());
    return false;
  });

  navItem.appendChild(starBtn);
}

function createFavoritesSection(favorites) {
  const existing = document.getElementById('sidebar-favorites-section');
  if (existing) existing.remove();
  if (favorites.length === 0) return;
  
  const sidebarScroll = document.querySelector('.sidebar-scroll');
  if (!sidebarScroll) return;
  
  const section = document.createElement('div');
  section.id = 'sidebar-favorites-section';
  
  let html = `
    <div style="padding: 8px 12px 4px; display: flex; align-items: center; justify-content: space-between;">
      <span style="font-size: 10px; font-weight: 600; color: var(--text-3, #666); text-transform: uppercase; letter-spacing: 0.5px;">⭐ Favorites</span>
    </div>
  `;
  
  favorites.forEach(navId => {
    const original = document.querySelector(`.nav-item[data-nav="${navId}"]`);
    if (original) {
      const icon = original.querySelector('.icon')?.textContent || '📌';
      const label = original.querySelector('.label')?.textContent || navId;
      html += `
        <div class="nav-item fav-item" data-nav="${navId}" onclick="nav('${navId}')">
          <span class="icon">${icon}</span>
          <span class="label">${label}</span>
          <button type="button" class="fav-remove-btn" data-nav-id="${navId}" title="Remove from favorites" 
            onclick="event.stopPropagation(); removeFromFavorites('${navId}')">✕</button>
        </div>
      `;
    }
  });
  
  section.innerHTML = html;
  sidebarScroll.insertBefore(section, sidebarScroll.firstChild);
}

function removeFromFavorites(navId) {
  let favorites = getFavorites();
  favorites = favorites.filter(id => id !== navId);
  saveFavorites(favorites);
  
  const originalItem = document.querySelector(`.nav-item[data-nav="${navId}"]`);
  if (originalItem) {
    const starBtn = originalItem.querySelector('.nav-star-btn');
    if (starBtn) {
      starBtn.innerHTML = '☆';
      starBtn.title = 'Click to add to favorites';
      starBtn.style.opacity = '0';
    }
  }
  
  createFavoritesSection(favorites);
  if (typeof toast === 'function') toast('Removed from favorites', 'ok');
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

  /* Star button */
  .nav-star-btn {
    background: none;
    border: none;
    cursor: pointer;
    font-size: 14px;
    padding: 2px 6px;
    margin-left: auto;
    flex-shrink: 0;
    line-height: 1;
    opacity: 0;
    transition: opacity 0.15s;
    z-index: 10;
    position: relative;
  }
  .nav-item:hover .nav-star-btn {
    opacity: 1;
  }
  .nav-star-btn[data-favorited="true"] {
    opacity: 1;
  }

  /* Favorites section */
  #sidebar-favorites-section {
    padding: 4px 0;
    border-bottom: 1px solid var(--border, rgba(255,255,255,0.06));
    margin-bottom: 4px;
  }
  #sidebar-favorites-section .fav-item {
    padding: 6px 12px;
    position: relative;
  }
  .fav-remove-btn {
    background: none;
    border: none;
    color: var(--text-3, #666);
    cursor: pointer;
    font-size: 12px;
    padding: 2px 4px;
    opacity: 0;
    transition: opacity 0.15s;
    margin-left: auto;
  }
  .fav-item:hover .fav-remove-btn {
    opacity: 1;
  }
  .fav-remove-btn:hover {
    color: var(--danger, #ef4444);
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
  #sidebar.collapsed .nav-star-btn,
  #sidebar.collapsed .fav-remove-btn,
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
window.removeFromFavorites = removeFromFavorites;
window.ensureDefaultState = ensureDefaultState;

console.log('%c✅ Sidebar v4 loaded', 'color:#22c55e;font-weight:bold');
