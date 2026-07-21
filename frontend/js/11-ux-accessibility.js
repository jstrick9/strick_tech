/*
 * Agentic OS — Accessibility (a11y) & UX Enhancements (frontend/js/11-ux-accessibility.js)
 * Implements: Screen Reader Announcements, Sidebar Keyboard Navigation, Focus Management / Trapping for Modals, and ARIA attributes pass.
 */
(function() {
  'use strict';

  // ── 1. Screen Reader Announcer (aria-live region) ───────────────────────────
  let srAnnouncer = document.getElementById('sr-announcer');
  if (!srAnnouncer) {
    srAnnouncer = document.createElement('div');
    srAnnouncer.id = 'sr-announcer';
    srAnnouncer.setAttribute('role', 'status');
    srAnnouncer.setAttribute('aria-live', 'polite');
    srAnnouncer.setAttribute('aria-atomic', 'true');
    srAnnouncer.style.cssText = 'position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0;';
    document.body.appendChild(srAnnouncer);
  }

  window.announceToScreenReader = function(msg) {
    if (!srAnnouncer || !msg) return;
    // Clear and set briefly delayed so screen readers notice repeat messages
    srAnnouncer.textContent = '';
    setTimeout(() => {
      srAnnouncer.textContent = msg;
    }, 50);
  };

  // Hook into window.nav to announce pane changes
  const origNav = window.nav;
  if (typeof origNav === 'function') {
    window.nav = function(pane) {
      origNav.apply(this, arguments);
      const navEl = document.querySelector(`[data-nav="${pane}"]`);
      const labelEl = navEl ? navEl.querySelector('.label') : null;
      const title = labelEl ? labelEl.textContent.trim() : pane;
      window.announceToScreenReader(`Switched to ${title} pane view.`);
      // Set aria-current / active on nav items
      document.querySelectorAll('.nav-item').forEach(el => {
        el.setAttribute('aria-selected', el.getAttribute('data-nav') === pane ? 'true' : 'false');
      });
    };
  }

  // Hook into toast to announce notifications
  const origToast = window.toast;
  if (typeof origToast === 'function') {
    window.toast = function(msg, type, duration) {
      origToast.apply(this, arguments);
      window.announceToScreenReader(`Alert: ${msg}`);
    };
  }

  // Hook into toggleMode
  const origToggleMode = window.toggleMode;
  if (typeof origToggleMode === 'function') {
    window.toggleMode = function() {
      origToggleMode.apply(this, arguments);
      const isPower = document.body.classList.contains('mode-power');
      window.announceToScreenReader(`Switched to ${isPower ? 'Power mode with all advanced tools' : 'Simple mode with core features'}.`);
    };
  }

  // ── 2. Sidebar & Panes Keyboard Navigation ──────────────────────────────────
  document.addEventListener('keydown', function(e) {
    // Alt + Number shortcut for core navigation panes (1-7)
    if (e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
      const shortcuts = {
        '1': 'chat',
        '2': 'studio',
        '3': 'templates',
        '4': 'swarm',
        '5': 'memory',
        '6': 'kanban',
        '7': 'settings'
      };
      if (shortcuts[e.key]) {
        e.preventDefault();
        window.nav(shortcuts[e.key]);
      }
    }

    // Arrow navigation inside sidebar nav items
    if (e.target && e.target.classList && e.target.classList.contains('nav-item')) {
      const visibleItems = Array.from(document.querySelectorAll('.nav-item')).filter(el => {
        return el.offsetParent !== null || window.getComputedStyle(el).display !== 'none';
      });
      const idx = visibleItems.indexOf(e.target);
      if (idx !== -1) {
        if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
          e.preventDefault();
          const nextIdx = (idx + 1) % visibleItems.length;
          visibleItems[nextIdx].focus();
        } else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
          e.preventDefault();
          const prevIdx = (idx - 1 + visibleItems.length) % visibleItems.length;
          visibleItems[prevIdx].focus();
        } else if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          e.target.click();
        }
      }
    }
  });

  // ── 3. Focus Management & Trapping for Modals ───────────────────────────────
  let lastFocusedElementBeforeModal = null;
  const FOCUSABLE_SELECTOR = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

  function setupModalAccessibility(modalEl) {
    if (!modalEl) return;
    if (!modalEl.hasAttribute('role')) modalEl.setAttribute('role', 'dialog');
    modalEl.setAttribute('aria-modal', 'true');

    // Observation of modal visibility transitions
    const observer = new MutationObserver(mutations => {
      mutations.forEach(m => {
        if (m.attributeName === 'class' || m.attributeName === 'style') {
          const isOpen = modalEl.classList.contains('open') || 
                         window.getComputedStyle(modalEl).display === 'flex' || 
                         window.getComputedStyle(modalEl).display === 'block';
          if (isOpen && !modalEl._a11yActive) {
            modalEl._a11yActive = true;
            lastFocusedElementBeforeModal = document.activeElement;
            setTimeout(() => {
              const focusables = modalEl.querySelectorAll(FOCUSABLE_SELECTOR);
              const firstFocusable = Array.from(focusables).find(el => el.offsetParent !== null && window.getComputedStyle(el).display !== 'none');
              if (firstFocusable) {
                firstFocusable.focus();
              } else {
                modalEl.focus();
              }
            }, 50);
          } else if (!isOpen && modalEl._a11yActive) {
            modalEl._a11yActive = false;
            if (lastFocusedElementBeforeModal && typeof lastFocusedElementBeforeModal.focus === 'function') {
              try { lastFocusedElementBeforeModal.focus(); } catch(err) {}
            }
          }
        }
      });
    });
    observer.observe(modalEl, { attributes: true });

    // Focus trap inside modal
    modalEl.addEventListener('keydown', function(e) {
      if (e.key === 'Tab') {
        const focusables = Array.from(modalEl.querySelectorAll(FOCUSABLE_SELECTOR)).filter(el => {
          return el.offsetParent !== null && window.getComputedStyle(el).display !== 'none';
        });
        if (focusables.length === 0) {
          e.preventDefault();
          return;
        }
        const firstEl = focusables[0];
        const lastEl = focusables[focusables.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === firstEl || !modalEl.contains(document.activeElement)) {
            e.preventDefault();
            lastEl.focus();
          }
        } else {
          if (document.activeElement === lastEl || !modalEl.contains(document.activeElement)) {
            e.preventDefault();
            firstEl.focus();
          }
        }
      } else if (e.key === 'Escape') {
        // If modal has a close action or close class, trigger close
        if (modalEl.classList.contains('open')) {
          modalEl.classList.remove('open');
        } else {
          modalEl.style.display = 'none';
        }
      }
    });
  }

  // Initialize modal tracking across all current and future modals
  function initModals() {
    const modals = document.querySelectorAll('.modal, #palette-modal, #onboarding-modal, #agent-modal, .dag-modal');
    modals.forEach(setupModalAccessibility);
  }

  // ── 4. ARIA Attributes Enhancements Pass ────────────────────────────────────
  function applyAriaPass() {
    try {
      // Nav items
      document.querySelectorAll('.nav-item').forEach(el => {
        try {
          el.setAttribute('role', 'menuitem');
          if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '0');
          const label = el.getAttribute('data-tooltip') || (el.querySelector('.label') ? el.querySelector('.label').textContent.trim() : '');
          if (label && !el.hasAttribute('aria-label')) el.setAttribute('aria-label', label);
        } catch(e) {}
      });

      // Clickable divs/spans (buttons masquerading as divs)
      document.querySelectorAll('[onclick]:not(button):not(a):not(input):not(select)').forEach(el => {
        try {
          if (!el.hasAttribute('role')) el.setAttribute('role', 'button');
          if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '0');
          const titleOrText = el.getAttribute('title') || el.getAttribute('data-tooltip') || (el.textContent || '').trim();
          if (titleOrText && !el.hasAttribute('aria-label')) el.setAttribute('aria-label', titleOrText.slice(0, 80));
          if (!el._a11yKeydown) {
            el._a11yKeydown = true;
            el.addEventListener('keydown', function(evt) {
              if (evt.key === 'Enter' || evt.key === ' ') {
                evt.preventDefault();
                el.click();
              }
            });
          }
        } catch(e) {}
      });

      // Icon buttons & standard buttons without accessible names
      document.querySelectorAll('button, input[type="button"], input[type="submit"]').forEach(btn => {
        try {
          if (!btn.hasAttribute('aria-label') && !(btn.textContent || '').trim()) {
            const fallbackLabel = btn.getAttribute('title') || btn.getAttribute('data-tooltip') || btn.id || 'Action button';
            btn.setAttribute('aria-label', fallbackLabel);
          }
        } catch(e) {}
      });

      // Form inputs and textareas
      document.querySelectorAll('input, textarea, select').forEach(input => {
        try {
          if (!input.hasAttribute('aria-label') && !input.getAttribute('aria-labelledby')) {
            const placeholder = input.getAttribute('placeholder');
            const title = input.getAttribute('title');
            const id = input.id;
            let labelText = placeholder || title || id || 'Input field';
            input.setAttribute('aria-label', labelText);
          }
        } catch(e) {}
      });
    } catch(err) {}
  }

  // Run initial passes after DOM content loaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      initModals();
      applyAriaPass();
    });
  } else {
    setTimeout(() => {
      initModals();
      applyAriaPass();
    }, 100);
  }

  // Observe DOM additions so new elements or dynamically rendered panes get ARIA attributes (debounced)
  let _ariaPassTimeout = null;
  const domObserver = new MutationObserver(() => {
    if (_ariaPassTimeout) clearTimeout(_ariaPassTimeout);
    _ariaPassTimeout = setTimeout(() => applyAriaPass(), 250);
  });
  domObserver.observe(document.documentElement, { childList: true, subtree: true });

  console.log('%c✅ Accessibility & UX Module loaded (SR Announcer, Panes Navigation, Focus Trapping)', 'color:#8b5cf6;font-weight:bold');
})();
