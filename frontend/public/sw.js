self.addEventListener("install", (e) => {
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(clients.claim());
});

// No fetch handler on purpose. A pass-through fetch handler
// (respondWith(fetch(e.request))) made the service worker hard-fail every request
// whenever a single fetch rejected (Render cold-start / transient network),
// knocking the app offline with "Failed to fetch". With no fetch handler the
// browser handles all network requests directly. The install/activate handlers
// above keep this SW registered and in control so it supersedes any previously
// installed pass-through version on the next navigation.
