/**
 * Agentic OS — Service Worker
 * Enables PWA installation, offline support, and background sync.
 */
const CACHE_VERSION = 'agentic-v6-s18';
const CACHE_STATIC  = `${CACHE_VERSION}-static`;
const CACHE_API     = `${CACHE_VERSION}-api`;

// Files to pre-cache for offline support
const PRECACHE = [
  '/',
  '/static/index.html',
];

// API routes to cache with stale-while-revalidate
const CACHE_API_ROUTES = [
  '/api/agents',
  '/api/kanban',
  '/api/goals',
  '/api/templates',
  '/api/skills',
  '/api/voice/commands',
];

// ── Install ────────────────────────────────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_STATIC).then(cache => {
      return cache.addAll(PRECACHE).catch(() => {});
    })
  );
  self.skipWaiting();
});

// ── Activate ───────────────────────────────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_STATIC && k !== CACHE_API).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// ── Fetch strategy ─────────────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Skip non-GET and cross-origin
  if (event.request.method !== 'GET') return;
  if (url.origin !== location.origin) return;

  // API routes: stale-while-revalidate for cacheable endpoints
  if (url.pathname.startsWith('/api/')) {
    const isCacheable = CACHE_API_ROUTES.some(r => url.pathname.startsWith(r));
    if (isCacheable) {
      event.respondWith(staleWhileRevalidate(event.request, CACHE_API));
      return;
    }
    // SSE/WebSocket API — don't intercept
    if (url.pathname.includes('/stream') || url.pathname.includes('/ws')) return;
    return; // Network-only for other API routes
  }

  // Static assets: cache-first
  if (url.pathname.startsWith('/static/') || url.pathname.startsWith('/preview/')) {
    event.respondWith(cacheFirst(event.request, CACHE_STATIC));
    return;
  }

  // Navigation: network-first, fallback to cache
  if (event.request.mode === 'navigate') {
    event.respondWith(networkFirst(event.request, CACHE_STATIC));
    return;
  }
});

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response('Offline', { status: 503 });
  }
}

async function networkFirst(request, cacheName) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    return cached || new Response('Offline', { status: 503 });
  }
}

async function staleWhileRevalidate(request, cacheName) {
  const cache  = await caches.open(cacheName);
  const cached = await cache.match(request);
  const fetchPromise = fetch(request).then(response => {
    if (response.ok) cache.put(request, response.clone());
    return response;
  }).catch(() => null);

  return cached || fetchPromise;
}

// ── Push notifications ────────────────────────────────────────────────────────
self.addEventListener('push', event => {
  const data = event.data?.json() || {};
  event.waitUntil(
    self.registration.showNotification(data.title || 'Agentic OS', {
      body:  data.body || 'An agent has a message for you',
      icon:  '/static/icon-192.png',
      badge: '/static/icon-192.png',
      data:  data,
      actions: [
        { action: 'open', title: 'Open' },
        { action: 'dismiss', title: 'Dismiss' },
      ],
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  if (event.action === 'open') {
    event.waitUntil(clients.openWindow('/'));
  }
});

// ── Background sync ───────────────────────────────────────────────────────────
self.addEventListener('sync', event => {
  if (event.tag === 'sync-pending-tasks') {
    event.waitUntil(syncPendingTasks());
  }
});

async function syncPendingTasks() {
  try {
    await fetch('/api/audit', { method: 'GET' }); // ping to sync
  } catch {}
}

console.log('[AgenticOS SW] Service Worker v6 S18 loaded');
