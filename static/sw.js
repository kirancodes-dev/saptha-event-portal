/*
 * SapthaEvent Service Worker
 * - Cache-first for static assets and the SNPSU logo
 * - Network-first with offline fallback for pages
 * - Runtime cache of ticket pages so students can show their QR offline
 */
const VERSION = 'v1.0.0';
const STATIC_CACHE = `saptha-static-${VERSION}`;
const PAGE_CACHE = `saptha-pages-${VERSION}`;
const TICKET_CACHE = `saptha-tickets-${VERSION}`;

const STATIC_ASSETS = [
  '/static/snpsu-logo.png',
  '/static/css/global.css',
  '/static/css/style.css',
  '/static/manifest.webmanifest',
  '/offline'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => cache.addAll(STATIC_ASSETS).catch(() => null))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((k) => ![STATIC_CACHE, PAGE_CACHE, TICKET_CACHE].includes(k))
          .map((k) => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

const isTicketUrl = (url) =>
  url.pathname.startsWith('/ticket/') && !url.pathname.startsWith('/ticket/verify') && !url.pathname.startsWith('/ticket/api');

const isStaticUrl = (url) =>
  url.pathname.startsWith('/static/');

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // 1) Static assets → cache-first
  if (isStaticUrl(url)) {
    event.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(STATIC_CACHE).then((c) => c.put(req, copy));
        return res;
      }).catch(() => caches.match('/static/snpsu-logo.png')))
    );
    return;
  }

  // 2) Ticket pages → network-first, save for offline
  if (isTicketUrl(url)) {
    event.respondWith(
      fetch(req).then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(TICKET_CACHE).then((c) => c.put(req, copy));
        }
        return res;
      }).catch(() => caches.match(req).then((hit) => hit || caches.match('/offline')))
    );
    return;
  }

  // 3) HTML navigations → network-first with offline fallback
  if (req.mode === 'navigate' || (req.headers.get('accept') || '').includes('text/html')) {
    event.respondWith(
      fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(PAGE_CACHE).then((c) => c.put(req, copy));
        return res;
      }).catch(() => caches.match(req).then((hit) => hit || caches.match('/offline')))
    );
    return;
  }

  // 4) Everything else → network falling back to cache
  event.respondWith(
    fetch(req).catch(() => caches.match(req))
  );
});
