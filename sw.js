const CACHE_NAME = 'traytrack-v2';

// Files to cache for offline use
const STATIC_CACHE_URLS = [
  '/index.html',
  '/manifest.json',
  '/sw.js'
];


// Install event
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_CACHE_URLS);
    })
  );
  self.skipWaiting();
});

// Activate event
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// Fetch event
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // ✅ 1) Never intercept cross-origin requests (your API is cross-origin)
  if (url.origin !== self.location.origin) {
    return; // browser handles it
  }

  // ✅ 2) Never intercept non-GET requests (POST /users/login must pass through)
  if (event.request.method !== 'GET') {
    return;
  }

  // ✅ 3) Only cache-first for same-origin GETs (static assets)
  event.respondWith(
    caches.match(event.request).then((cached) => {
      return (
        cached ||
        fetch(event.request).then((resp) => {
          // Optional: update cache with fresh copies of same-origin GETs
          const copy = resp.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          return resp;
        })
      );
    })
  );
});
