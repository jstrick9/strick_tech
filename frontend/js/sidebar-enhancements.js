// Agentic OS — Sidebar Enhancements v7
// Favorites with ☆/★ icons on ALL components + FAVORITES section
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

  // Sidebar always starts expanded — never auto-collapse on page load
  // Users can collapse manually with the toggle button or ⌘+B
  const sidebar = document.getElementById('sidebar');
  if (sidebar) {
    sidebar.classList.remove('collapsed');
  }

  setupSidebarResizer();
  setupFavorites();
  setupGroupTooltips();
  ensureDefaultState();
  
  console.log('✅ Sidebar v7 loaded');
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

// ── Favorites System ─────────────────────────────────────────────
function setupFavorites() {
  const favorites = getFavorites();
  
  // Create favorites section if there are favorites
  if (favorites.length > 0) {
    createFavoritesSection(favorites);
  }
  
  // Add favorite ☆/★ buttons to ALL nav items
  document.querySelectorAll('.nav-item[data-nav]').forEach(item => {
    addFavoriteButton(item);
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

function addFavoriteButton(navItem) {
  const navId = navItem.dataset.nav;
  if (!navId) return;
  if (navItem.querySelector('.nav-fav-btn')) return;

  const favorites = getFavorites();
  const isFav = favorites.includes(navId);
  
  const favBtn = document.createElement('button');
  favBtn.className = 'nav-fav-btn';
  favBtn.type = 'button';
  favBtn.innerHTML = isFav ? '★' : '☆';
  favBtn.title = isFav ? 'Remove from favorites' : 'Add to favorites';
  favBtn.setAttribute('data-nav-id', navId);
  favBtn.setAttribute('data-favorited', isFav ? 'true' : 'false');

  // Show on hover, always show if favorited
  if (!isFav) {
    navItem.addEventListener('mouseenter', () => favBtn.classList.add('visible'));
    navItem.addEventListener('mouseleave', () => favBtn.classList.remove('visible'));
  } else {
    favBtn.classList.add('visible');
  }

  // Click handler - stop propagation to prevent navigation
  favBtn.addEventListener('click', function(e) {
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    
    const currentFavs = getFavorites();
    const isCurrentlyFav = currentFavs.includes(navId);
    
    if (isCurrentlyFav) {
      // Remove from favorites
      const newFavs = currentFavs.filter(id => id !== navId);
      saveFavorites(newFavs);
      this.innerHTML = '☆';
      this.title = 'Add to favorites';
      this.setAttribute('data-favorited', 'false');
      this.classList.remove('visible');
      if (typeof toast === 'function') toast('Removed from favorites', 'ok');
    } else {
      // Add to favorites
      currentFavs.push(navId);
      saveFavorites(currentFavs);
      this.innerHTML = '★';
      this.title = 'Remove from favorites';
      this.setAttribute('data-favorited', 'true');
      this.classList.add('visible');
      if (typeof toast === 'function') toast('Added to favorites', 'ok');
    }
    
    // Update favorites section
    createFavoritesSection(getFavorites());
    return false;
  });

  navItem.appendChild(favBtn);
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
    <div style="padding: 8px 12px 4px;">
      <span style="font-size: 10px; font-weight: 600; color: var(--text-3); text-transform: uppercase; letter-spacing: 0.5px;">⭐ Favorites</span>
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
          <button type="button" class="fav-remove-btn" title="Remove from favorites" 
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
  
  // Update the favorite button on the ORIGINAL nav item (not in favorites section)
  // Use :not(.fav-item) to exclude the favorites section items
  const originalItem = document.querySelector(`.nav-item[data-nav="${navId}"]:not(.fav-item)`);
  if (originalItem) {
    const favBtn = originalItem.querySelector('.nav-fav-btn');
    if (favBtn) {
      favBtn.innerHTML = '☆';
      favBtn.title = 'Add to favorites';
      favBtn.setAttribute('data-favorited', 'false');
      favBtn.classList.remove('visible');
    }
  }
  
  // Update favorites section
  createFavoritesSection(favorites);
  if (typeof toast === 'function') toast('Removed from favorites', 'ok');
}

// ── Group Tooltips ───────────────────────────────────────────────
// Help tips removed per user request
function setupGroupTooltips() {
  // No-op - help tips removed
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
    color: var(--text-3, #808080);
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
    color: var(--text-0, #ffffff);
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
    border: 1px solid var(--border, rgba(255,255,255,0.1));
    color: var(--text-3, #808080);
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
    color: var(--text-0, #ffffff);
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
    border: 1px solid var(--border-hi, rgba(255,255,255,0.2));
  }

  /* Favorite button ☆/★ */
  .nav-fav-btn {
    background: none;
    border: none;
    cursor: pointer;
    font-size: 14px;
    padding: 2px 6px;
    margin-left: auto;
    flex-shrink: 0;
    line-height: 1;
    opacity: 0;
    transition: opacity 0.15s, color 0.15s;
    z-index: 10;
    position: relative;
    color: var(--text-3, #808080);
  }
  .nav-fav-btn:hover {
    color: var(--accent, #6366f1);
  }
  .nav-fav-btn.visible {
    opacity: 1;
  }
  .nav-item:hover .nav-fav-btn {
    opacity: 1;
  }
  .nav-fav-btn[data-favorited="true"] {
    opacity: 1;
    color: var(--warning, #eab308);
  }

  /* Favorites section */
  #sidebar-favorites-section {
    padding: 4px 0;
    border-bottom: 1px solid var(--border, rgba(255,255,255,0.1));
    margin-bottom: 4px;
  }
  #sidebar-favorites-section .fav-item {
    padding: 6px 12px;
    position: relative;
  }
  .fav-remove-btn {
    background: none;
    border: none;
    color: var(--text-3, #808080);
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
  #sidebar.collapsed .nav-fav-btn,
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
    border-top: 1px solid var(--border, rgba(255,255,255,0.1));
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

console.log('%c✅ Sidebar v7 loaded', 'color:#22c55e;font-weight:bold');
