/**
 * SapthaEvent Service Worker (v2)
 * ============================================================
 */

const CACHE_NAME = 'sapthaevent-v2';
const STATIC_ASSETS = [
  '/offline',
  '/static/css/global.css',
  '/static/css/mobile.css',
  '/static/js/pwa.js',
  '/static/snpsu-logo.png',
  '/static/manifest.webmanifest'
];

// INSTALL: cache base files
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => self.skipWaiting())
  );
});

// ACTIVATE: delete old versioned caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// FETCH INTERCEPTION
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Exclude third-party dynamic APIs and /chatbots
  if (url.origin !== self.location.origin || url.pathname.includes('/chatbot')) {
    return;
  }

  // 1. Static Assets (CSS, JS, images, fonts) -> Cache First
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(req).then((cachedResponse) => {
        if (cachedResponse) {
          // Fetch updated in background
          fetch(req).then((networkResponse) => {
            if (networkResponse.status === 200) {
              caches.open(CACHE_NAME).then((cache) => cache.put(req, networkResponse));
            }
          }).catch(() => {/* ignore */});
          return cachedResponse;
        }
        return fetch(req).then((networkResponse) => {
          return caches.open(CACHE_NAME).then((cache) => {
            cache.put(req, networkResponse.clone());
            return networkResponse;
          });
        });
      })
    );
    return;
  }

  // 2. HTML pages -> Network First with offline fallback
  if (req.mode === 'navigate' || (req.headers.get('accept') || '').includes('text/html')) {
    event.respondWith(
      fetch(req)
        .then((networkResponse) => {
          const copy = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
          return networkResponse;
        })
        .catch(() => {
          return caches.match(req).then((cachedResponse) => {
            return cachedResponse || caches.match('/offline');
          });
        })
    );
    return;
  }

  // 3. Fallback standard request -> Network falling back to cache
  event.respondWith(
    fetch(req).catch(() => caches.match(req))
  );
});

// PUSH NOTIFICATIONS
self.addEventListener('push', (event) => {
  if (!event.data) return;
  let data = {};
  try {
    data = event.data.json();
  } catch (err) {
    data = { title: 'SapthaEvent', body: event.data.text() };
  }

  event.waitUntil(
    self.registration.showNotification(data.title || 'SapthaEvent', {
      body: data.body || '',
      icon: data.icon || '/static/snpsu-logo.png',
      badge: '/static/snpsu-logo.png',
      data: { url: data.url || '/' },
      actions: data.actions || []
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then((clientList) => {
      for (const client of clientList) {
        if (client.url === targetUrl && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});
