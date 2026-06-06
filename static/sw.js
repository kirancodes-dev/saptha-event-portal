/**
 * SapthaEvent Service Worker (v3)
 * ─────────────────────────────────────────────────────────────
 * Strategy overview:
 *   /static/*          → Cache-First  (assets never change mid-session)
 *   /login, /register  → Network-First (always fresh auth pages)
 *   /offline           → Cache-Only   (fallback page)
 *   everything else    → Network-First with cache fallback
 * ─────────────────────────────────────────────────────────────
 */

const CACHE_VERSION  = 'sapthaevent-v3';
const OFFLINE_URL    = '/offline';

// Assets cached immediately on install (shell)
const PRECACHE_ASSETS = [
  OFFLINE_URL,
  '/static/css/global.css',
  '/static/js/global.js',
  '/static/snpsu-logo.png',
  '/static/app-icon.png',
  '/static/manifest.webmanifest',
];

// ── INSTALL ────────────────────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION)
      .then((cache) => cache.addAll(PRECACHE_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// ── ACTIVATE ───────────────────────────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys
          .filter((key) => key !== CACHE_VERSION)
          .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

// ── FETCH ──────────────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;   // never intercept POST/PUT

  const url = new URL(req.url);

  // Skip cross-origin requests (CDN, external APIs)
  if (url.origin !== self.location.origin) return;

  // Skip chatbot & SSE (streaming connections must not be intercepted)
  if (url.pathname.includes('/chatbot') ||
      url.pathname.includes('/stream') ||
      url.pathname.includes('/events/sse')) {
    return;
  }

  // ── Static assets → Cache-First, background update ────
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(cacheFirstWithUpdate(req));
    return;
  }

  // ── Offline page → Cache-Only ────
  if (url.pathname === OFFLINE_URL) {
    event.respondWith(caches.match(OFFLINE_URL));
    return;
  }

  // ── All other pages → Network-First, cache fallback ────
  event.respondWith(networkFirstWithFallback(req));
});

// ── HELPER: Cache-First with background refresh ────────────────
async function cacheFirstWithUpdate(req) {
  const cache  = await caches.open(CACHE_VERSION);
  const cached = await cache.match(req);

  // Update cache in background without blocking
  const networkFetch = fetch(req).then((netResp) => {
    if (netResp && netResp.status === 200) {
      cache.put(req, netResp.clone());
    }
    return netResp;
  }).catch(() => null);

  return cached || await networkFetch;
}

// ── HELPER: Network-First with offline fallback ────────────────
async function networkFirstWithFallback(req) {
  const cache = await caches.open(CACHE_VERSION);
  try {
    const netResp = await fetch(req);
    // Cache successful HTML responses for offline use
    if (netResp && netResp.status === 200) {
      const ct = netResp.headers.get('content-type') || '';
      if (ct.includes('text/html')) {
        cache.put(req, netResp.clone());
      }
    }
    return netResp;
  } catch (_err) {
    // Offline: try cache, then show offline page
    const cached = await cache.match(req);
    return cached || await cache.match(OFFLINE_URL);
  }
}

// ── PUSH NOTIFICATIONS ─────────────────────────────────────────
self.addEventListener('push', (event) => {
  if (!event.data) return;
  let data = {};
  try { data = event.data.json(); }
  catch (_) { data = { title: 'SapthaEvent', body: event.data.text() }; }

  event.waitUntil(
    self.registration.showNotification(data.title || 'SapthaEvent', {
      body:    data.body   || '',
      icon:    data.icon   || '/static/app-icon.png',
      badge:   '/static/app-icon.png',
      tag:     data.tag    || 'saptha-notif',
      renotify: true,
      data:    { url: data.url || '/' },
      actions: data.actions || [],
      vibrate: [200, 100, 200],
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        for (const client of clientList) {
          if (client.url === targetUrl && 'focus' in client) {
            return client.focus();
          }
        }
        return clients.openWindow(targetUrl);
      })
  );
});
