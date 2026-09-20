const CACHE_NAME = 'knowledge-base-v1';

// 1. Install event: cache the core app shell
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll([
        '/',
        '/static/css/style.css',
        '/static/web-app-manifest-192x192.png',
        '/static/web-app-manifest-512x512.png'
      ]);
    })
  );
});

// 2. Fetch event: try network first, fallback to cache if offline
self.addEventListener('fetch', event => {
  event.respondWith(
    fetch(event.request).catch(() => {
      return caches.match(event.request);
    })
  );
});