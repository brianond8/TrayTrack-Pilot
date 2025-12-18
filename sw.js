const CACHE_NAME = 'traytrack-v1';
const OFFLINE_QUEUE = 'traytrack-offline-queue';

// Files to cache for offline use
const STATIC_CACHE_URLS = [
  '/',
  '/index.html',
  '/manifest.json',
  'https://cdn.jsdelivr.net/npm/fullcalendar@6.1.15/main.min.css',
  'https://cdn.jsdelivr.net/npm/fullcalendar@6.1.15/index.global.min.js'
];

// Install event - cache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_CACHE_URLS);
    })
  );
  self.skipWaiting();
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME && cacheName !== OFFLINE_QUEUE) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// Fetch event - network first, then cache, with offline queue for POST/PUT/DELETE
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Handle API requests
  if (url.origin.includes('192.168.0.6:8000') || url.pathname.startsWith('/api')) {
    // For mutations (POST, PUT, DELETE), queue if offline
    if (request.method !== 'GET') {
      event.respondWith(
        fetch(request.clone())
          .then((response) => {
            return response;
          })
          .catch(() => {
            // Queue the request for later
            return queueOfflineRequest(request.clone()).then(() => {
              return new Response(
                JSON.stringify({ 
                  ok: true, 
                  offline: true, 
                  message: 'Request queued for sync when online' 
                }),
                { 
                  status: 202, 
                  headers: { 'Content-Type': 'application/json' } 
                }
              );
            });
          })
      );
      return;
    }

    // For GET requests, try network first, then cache
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Clone the response and cache it
          const responseToCache = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(request, responseToCache);
          });
          return response;
        })
        .catch(() => {
          // If network fails, try cache
          return caches.match(request);
        })
    );
    return;
  }

  // For static assets, cache first, then network
  event.respondWith(
    caches.match(request).then((response) => {
      return response || fetch(request);
    })
  );
});

// Queue offline requests
async function queueOfflineRequest(request) {
  const cache = await caches.open(OFFLINE_QUEUE);
  const requestData = {
    url: request.url,
    method: request.method,
    headers: {},
    body: null,
    timestamp: Date.now()
  };

  // Copy headers
  request.headers.forEach((value, key) => {
    requestData.headers[key] = value;
  });

  // Get body if present
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    requestData.body = await request.text();
  }

  // Store in cache with unique key
  const queueKey = `offline-${Date.now()}-${Math.random()}`;
  await cache.put(
    new Request(queueKey),
    new Response(JSON.stringify(requestData))
  );
}

// Background sync - replay queued requests when online
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-offline-requests') {
    event.waitUntil(syncOfflineRequests());
  }
});

async function syncOfflineRequests() {
  const cache = await caches.open(OFFLINE_QUEUE);
  const requests = await cache.keys();

  for (const request of requests) {
    try {
      const response = await cache.match(request);
      const requestData = await response.json();

      // Replay the request
      const replayResponse = await fetch(requestData.url, {
        method: requestData.method,
        headers: requestData.headers,
        body: requestData.body
      });

      if (replayResponse.ok) {
        // Remove from queue on success
        await cache.delete(request);
        
        // Notify clients of successful sync
        const clients = await self.clients.matchAll();
        clients.forEach(client => {
          client.postMessage({
            type: 'SYNC_SUCCESS',
            url: requestData.url
          });
        });
      }
    } catch (error) {
      console.error('Failed to sync request:', error);
      // Keep in queue for next sync attempt
    }
  }
}

// Periodic background sync (if supported)
self.addEventListener('periodicsync', (event) => {
  if (event.tag === 'sync-offline-requests') {
    event.waitUntil(syncOfflineRequests());
  }
});

// Message handler for manual sync trigger
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SYNC_NOW') {
    syncOfflineRequests();
  }
});