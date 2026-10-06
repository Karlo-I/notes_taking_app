const CACHE_NAME = 'memory-bank-v1';

// ====================================================================
// 1. PWA CACHING (Your existing logic)
// ====================================================================
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

self.addEventListener('fetch', event => {
  event.respondWith(
    fetch(event.request).catch(() => {
      return caches.match(event.request);
    })
  );
});

// ====================================================================
// 2. WEB PUSH NOTIFICATIONS (New logic)
// ====================================================================
self.addEventListener('push', function(event) {
    // 1. Get the data sent from the Flask backend
    const data = event.data ? event.data.json() : {};
    const title = data.title || 'Deadline Reminder';
    const options = {
        body: data.body || 'You have an upcoming deadline.',
        icon: '/static/web-app-manifest-192x192.png', // Reusing your existing manifest icon
        badge: '/static/web-app-manifest-192x192.png',
        requireInteraction: true // Keeps notification on screen until clicked
    };

    // 2. Show the notification
    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

// 3. Handle notification click
self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    // Opens your app when the user clicks the notification
    event.waitUntil(
        clients.openWindow('/')
    );
});