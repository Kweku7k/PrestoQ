// Service Worker for PrestoQ PWA
const CACHE_NAME = 'prestoq-v1';
const urlsToCache = [
  '/',
  '/static/css/styles.css',
  '/static/script.js',
  '/static/img/icon-192x192.png',
  '/static/img/icon-512x512.png',
  '/static/img/b-logo.png',
  '/static/img/b-logo-full.png',
  '/static/img/w-logo.png',
  '/static/img/w-logo-full.png',
  '/static/offline.html'
];

// Install event - cache assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        return cache.addAll(urlsToCache);
      })
  );
});

// Fetch event - serve from cache, fall back to network
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        // Return cached response if found
        if (response) {
          return response;
        }
        
        // Clone the request
        const fetchRequest = event.request.clone();
        
        // Make network request and cache the response
        return fetch(fetchRequest)
          .then(response => {
            // Check if valid response
            if(!response || response.status !== 200 || response.type !== 'basic') {
              return response;
            }
            
            // Clone the response
            const responseToCache = response.clone();
            
            caches.open(CACHE_NAME)
              .then(cache => {
                cache.put(event.request, responseToCache);
              });
              
            return response;
          })
          .catch(() => {
            // If offline and requesting a page, show offline page
            if (event.request.mode === 'navigate') {
              return caches.match('/static/offline.html');
            }
          });
      })
  );
});