const CACHE_NAME = 'mdkdv-pwa-v2.11.0';
const SHELL = [
  '/',
  '/manifest.webmanifest',
  '/static/style.css?v=53',
  '/static/app.js?v=53',
  '/static/assets/default-background.png',
  '/static/pwa/icon-192.png',
  '/static/pwa/icon-512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Dynamic API calls and embedded apps must always use the live server.
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/embedded/')) return;

  // Navigation: live first, cached shell as offline fallback.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then(response => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put('/', copy));
          return response;
        })
        .catch(() => caches.match('/')
          .then(response => response || new Response('Dashboard недоступен офлайн', {
            status: 503,
            headers: {'Content-Type': 'text/plain; charset=utf-8'}
          })))
    );
    return;
  }

  // Static assets: cache first, refresh in background.
  event.respondWith(
    caches.match(request).then(cached => {
      const network = fetch(request).then(response => {
        if (response && response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
        }
        return response;
      }).catch(() => cached);
      return cached || network;
    })
  );
});
